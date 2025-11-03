import os
import sys
import time
import mimetypes
import hashlib
import requests
import math
from oauth2client.client import OAuth2Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from httplib2 import Http
from googleapiclient.errors import HttpError
from googleapiclient.errors import ResumableUploadError

# =========================================================
# KONSTANTA & KONFIGURASI
# =========================================================

BOT_TOKEN = os.environ.get("BOT_TOKEN")
OWNER_ID = os.environ.get("PAYLOAD_SENDER")
REFRESH_TOKEN = os.environ.get('DRIVE_REFRESH_TOKEN')
CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID')
CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET')
DRIVE_UPLOAD_FOLDER_NAME = "my-drive-upload"

# =========================================================
# FUNGSI BANTUAN TELEGRAM & UMUM
# =========================================================

def send_telegram_message(message_text):
    """Fungsi untuk mengirim pesan ke Telegram dan mengembalikan message_id."""
    if not BOT_TOKEN or not OWNER_ID:
        print("Peringatan: BOT_TOKEN atau OWNER_ID tidak diatur. Notifikasi Telegram dinonaktifkan.")
        return None
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": OWNER_ID, "text": message_text, "parse_mode": "Markdown"}
    try:
        response = requests.post(url, json=payload, timeout=10)
        return response.json().get('result', {}).get('message_id')
    except Exception as e:
        print(f"Gagal mengirim pesan Telegram: {e}")
        return None

def edit_telegram_message(message_id, message_text):
    """Fungsi untuk mengedit pesan yang sudah ada di Telegram."""
    if not BOT_TOKEN or not OWNER_ID or not message_id:
        # Menghilangkan pesan error agar tidak terlalu berisik
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/editMessageText"
    payload = {"chat_id": OWNER_ID, "message_id": message_id, "text": message_text, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Gagal mengedit pesan Telegram: {e}")

def human_readable_size(size_bytes):
    if size_bytes is None or size_bytes == 0: return "0B"
    size_name = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
    i = int(math.floor(math.log(size_bytes, 1024))) if size_bytes > 0 else 0
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2) if p > 0 else 0
    return f"{s} {size_name[i]}"

def send_upload_progress(message_id, filename, uploaded_size, total_size):
    """Fungsi untuk mengirim progress upload ke Telegram (2x Update Logic)."""
    percent = int((uploaded_size/total_size)*100) if total_size else 0
    text = f"⏫ Uploading `{filename}` — {percent}% ({human_readable_size(uploaded_size)}/{human_readable_size(total_size)})"
    edit_telegram_message(message_id, text)

def calculate_md5(file_path):
    """Menghitung MD5 checksum dari file lokal."""
    hash_md5 = hashlib.md5()
    try:
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    except Exception as e:
        print(f"❌ Gagal menghitung MD5 checksum: {e}")
        return None

# =========================================================
# FUNGSI DRIVE OTENTIKASI & BANTUAN
# =========================================================

def authenticate_google_drive():
    """Mengurus otentikasi Google Drive, me-refresh token, dan mengembalikan service objek."""
    credentials = OAuth2Credentials(
        access_token=None, client_id=CLIENT_ID, client_secret=CLIENT_SECRET,
        refresh_token=REFRESH_TOKEN, token_expiry=None,
        token_uri='https://oauth2.googleapis.com/token',
        user_agent='GH-Actions-DriveUploader'
    )
    print("⚡ Memperbarui Access Token menggunakan Refresh Token...")
    http_pool = Http()
    try:
        credentials.refresh(http=http_pool)
    except Exception as e:
        error_msg = f"❌ Gagal memperbarui token. Token tidak valid: {e}"
        print(error_msg)
        send_telegram_message(f"❌ **Upload GAGAL!**\n\n{error_msg[:150]}...")
        sys.exit(1)
    
    http_auth = credentials.authorize(http_pool)
    drive_service = build('drive', 'v3', http=http_auth)
    print("✅ Autentikasi Drive berhasil. Siap upload!")
    return drive_service

def get_or_create_folder(service, folder_name, parent_id=None):
    """Mencari ID folder di Drive, jika tidak ada, membuatnya."""
    query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
    if parent_id:
        query += f" and '{parent_id}' in parents"
    try:
        response = service.files().list(q=query, fields='files(id)').execute()
        files = response.get('files', [])
        if files: return files[0].get('id')
        
        file_metadata = {'name': folder_name, 'mimeType': 'application/vnd.google-apps.folder', 'parents': [parent_id] if parent_id else []}
        file = service.files().create(body=file_metadata, fields='id').execute()
        return file.get('id')
    except HttpError as e:
        print(f"❌ Gagal mengakses/membuat folder: {e}")
        sys.exit(1)

def make_file_public(service, file_id):
    """Menetapkan izin agar file dapat diakses publik."""
    print("🌍 Menetapkan izin file menjadi publik...")
    permission_body = {'type': 'anyone', 'role': 'reader'}
    try:
        service.permissions().create(fileId=file_id, body=permission_body, fields='id').execute()
        file_info = service.files().get(fileId=file_id, fields='webViewLink,webContentLink').execute()
        print("✅ File berhasil dijadikan publik!")
        return file_info.get("webViewLink"), file_info.get("webContentLink")
    except HttpError as e:
        print(f"❌ Gagal mengatur izin file menjadi publik: {e}")
        return None, None

# =========================================================
# FUNGSI UTAMA UPLOAD (LOGIKA PROGRES 2X UPDATE)
# =========================================================

def upload_file_to_drive(drive_service, downloaded_file):
    """Mengurus Resumable Upload dan Verifikasi MD5."""
    target_folder_id = get_or_create_folder(drive_service, DRIVE_UPLOAD_FOLDER_NAME)
    
    MIME_TYPE, _ = mimetypes.guess_type(downloaded_file)
    if not MIME_TYPE: MIME_TYPE = 'application/octet-stream'

    LOCAL_MD5 = calculate_md5(downloaded_file)
    if not LOCAL_MD5:
        raise Exception(f"Gagal menghitung MD5 lokal untuk {downloaded_file}.")
        
    file_metadata = {'name': downloaded_file, 'parents': [target_folder_id]}
    media = MediaFileUpload(downloaded_file, mimetype=MIME_TYPE, resumable=True)
    request = drive_service.files().create(body=file_metadata, media_body=media, fields='id,webViewLink,webContentLink,md5Checksum')

    message_id = send_telegram_message(f"🚀 Mulai upload file `{downloaded_file}` ke Google Drive...")
    last_notified_percent = 0 # 0 -> 50 -> 100
    response = None
    total_size = os.path.getsize(downloaded_file)
    max_retries = 5
    retry_count = 0
    
    print(f'🚀 Memulai upload Resumable untuk: {downloaded_file}...')
    
    while response is None:
        try:
            status, response = request.next_chunk()
            retry_count = 0 # Reset hitungan retry jika chunk berhasil
            
            if status:
                percent_uploaded = int(status.progress() * 100)
                uploaded_size = int(status.progress() * total_size)

                # LOGIKA 2X UPDATE: Hanya update pada 50% dan 100%
                should_update_50 = (percent_uploaded >= 50 and last_notified_percent < 50)
                should_update_100 = (percent_uploaded == 100)
                
                if should_update_50 or should_update_100:
                    send_upload_progress(message_id, downloaded_file, uploaded_size, total_size)
                    last_notified_percent = percent_uploaded
                    print(f'      Uploaded {percent_uploaded}%')
                    
        except ResumableUploadError as e:
            retry_count += 1
            if retry_count >= max_retries:
                raise Exception("Upload gagal setelah beberapa kali percobaan ulang.")
            print(f"⚠️ Error Resumable Upload. Mencoba lagi dalam 10 detik. Percobaan ke-{retry_count}...")
            time.sleep(10)
        except Exception as e:
            retry_count += 1
            if retry_count >= max_retries:
                raise Exception("Error tak terduga, gagal setelah beberapa kali percobaan ulang.")
            print(f"❌ Error tak terduga saat upload. Mencoba lagi dalam 10 detik. Percobaan ke-{retry_count}...")
            time.sleep(10)

    # Pastikan notifikasi 100% terkirim
    if last_notified_percent < 100:
        send_upload_progress(message_id, downloaded_file, total_size, total_size)

    DRIVE_MD5 = response.get('md5Checksum')
    FILE_ID = response.get('id')
    WEB_VIEW_LINK = response.get("webViewLink")
    
    if DRIVE_MD5 and LOCAL_MD5 and DRIVE_MD5.lower() == LOCAL_MD5.lower():
        print("👍 VERIFIKASI BERHASIL. File UTUH.")
        PUBLIC_VIEW_LINK, PUBLIC_CONTENT_LINK = make_file_public(drive_service, FILE_ID)
        
        final_link_view = PUBLIC_VIEW_LINK if PUBLIC_VIEW_LINK else WEB_VIEW_LINK
        final_link_content = PUBLIC_CONTENT_LINK if PUBLIC_CONTENT_LINK else "N/A (Link Download)"
        
        success_message = (
            f"🎉 **UPLOAD SUKSES!** 🎉\n\n"
            f"File: `{downloaded_file}`\n"
            f"Folder: `{DRIVE_UPLOAD_FOLDER_NAME}`\n"
            f"MD5 Lokal: `{LOCAL_MD5}`\n"
            f"**Status:** **PUBLIK (Dapat Diakses Siapa Saja)!**\n"
            f"Link Drive: [Lihat File]({final_link_view})\n"
            f"Link Download Langsung: `{final_link_content}`" 
        )
        send_telegram_message(success_message)
        return True
    else:
        error_message = (
            f"🚨 **UPLOAD GAGAL (VERIFIKASI GAGAL)!**\n\n"
            f"File: `{downloaded_file}`\n"
            f"MD5 Lokal: `{LOCAL_MD5}`\n"
            f"MD5 Drive: `{DRIVE_MD5}`\n\n"
            f"Detail: File di Drive KORUP. Upload DIBATALKAN."
        )
        print(error_message)
        send_telegram_message(error_message)
        return False

# =========================================================
# 4. MAIN EXECUTION
# =========================================================

def main():
    """Fungsi utama untuk menjalankan seluruh proses upload."""
    
    # --- Pengecekan Awal ---
    try:
        with open("downloaded_filename.txt", "r") as f:
            DOWNLOADED_FILE = f.read().strip()
    except FileNotFoundError:
        error_msg = "❌ ERROR: File 'downloaded_filename.txt' tidak ditemukan. Upload dibatalkan."
        print(error_msg)
        send_telegram_message(f"❌ **Upload GAGAL!**\n\n{error_msg}")
        sys.exit(1)

    if not os.path.exists(DOWNLOADED_FILE):
        error_msg = f"❌ ERROR: File '{DOWNLOADED_FILE}' tidak ditemukan di sistem file. Upload dibatalkan."
        print(error_msg)
        send_telegram_message(f"❌ **Upload GAGAL!**\n\n{error_msg}")
        sys.exit(1)

    if not all([REFRESH_TOKEN, CLIENT_ID, CLIENT_SECRET, BOT_TOKEN, OWNER_ID]):
        error_msg = "❌ ERROR: Kredensial Google Drive atau Telegram tidak lengkap di environment."
        print(error_msg)
        if BOT_TOKEN and OWNER_ID:
            send_telegram_message(f"❌ **Upload GAGAL!**\n\n{error_msg}")
        sys.exit(1)
    # -----------------------

    try:
        # 1. Otentikasi
        drive_service = authenticate_google_drive()
        
        # 2. Upload (termasuk verifikasi MD5 dan setel publik)
        success = upload_file_to_drive(drive_service, DOWNLOADED_FILE)
        
        if not success:
            sys.exit(1)

    except Exception as e:
        error_message = f"❌ Gagal saat menjalankan proses utama: {e}"
        print(error_message)
        send_telegram_message(f"❌ **Upload GAGAL (Umum)!**\n\n{error_message[:150]}...")
        sys.exit(1)

if __name__ == '__main__':
    main()

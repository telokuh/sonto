import os
import sys
import time
import mimetypes
import hashlib
import requests # Diperlukan untuk notifikasi Telegram

from oauth2client.client import OAuth2Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from httplib2 import Http
from googleapiclient.errors import HttpError
from googleapiclient.errors import ResumableUploadError

# =========================================================
# FUNGSI BANTUAN TELEGRAM
# =========================================================

# Ambil token bot dan chat ID dari environment variables
BOT_TOKEN = os.environ.get("BOT_TOKEN")
OWNER_ID = os.environ.get("OWNER_ID")

def send_telegram_message(message_text):
    """Fungsi untuk mengirim pesan ke Telegram dan mengembalikan message_id."""
    if not BOT_TOKEN or not OWNER_ID:
        print("Peringatan: BOT_TOKEN atau OWNER_ID tidak diatur. Notifikasi Telegram dinonaktifkan.")
        return None

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": OWNER_ID,
        "text": message_text,
        "parse_mode": "Markdown"
    }
    try:
        response = requests.post(url, json=payload, timeout=10)
        return response.json().get('result', {}).get('message_id')
    except Exception as e:
        print(f"Gagal mengirim pesan Telegram: {e}")
        return None

def edit_telegram_message(message_id, message_text):
    """Fungsi untuk mengedit pesan yang sudah ada di Telegram."""
    if not BOT_TOKEN or not OWNER_ID or not message_id:
        print("Peringatan: Tidak bisa mengedit pesan. Notifikasi Telegram dinonaktifkan.")
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/editMessageText"
    payload = {
        "chat_id": OWNER_ID,
        "message_id": message_id,
        "text": message_text,
        "parse_mode": "Markdown"
    }
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Gagal mengedit pesan Telegram: {e}")

def human_readable_size(size_bytes):
    if size_bytes is None or size_bytes == 0:
        return "0B"
    size_name = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
    i = int(math.floor(math.log(size_bytes, 1024))) if size_bytes > 0 else 0
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2) if p > 0 else 0
    return f"{s} {size_name[i]}"

def send_upload_progress(message_id, filename, uploaded_size, total_size):
    percent = int((uploaded_size/total_size)*100) if total_size else 0
    text = f"⏫ Uploading `{filename}` — {percent}% ({human_readable_size(uploaded_size)}/{human_readable_size(total_size)})"
    edit_telegram_message(message_id, text)

# =========================================================
# Fungsi Bantuan: MD5 Checksum
# =========================================================
def calculate_md5(file_path):
    """Menghitung MD5 checksum dari file lokal."""
    hash_md5 = hashlib.md5()
    try:
        with open(file_path, "rb") as f:
            # Baca file dalam potongan 4KB untuk efisiensi
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    except Exception as e:
        print(f"❌ Gagal menghitung MD5 checksum: {e}")
        return None

# =========================================================
# 1. KONFIGURASI DAN INISIALISASI
# =========================================================

REFRESH_TOKEN = os.environ.get('DRIVE_REFRESH_TOKEN')
CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID')
CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET')
DRIVE_UPLOAD_FOLDER_NAME = "my-drive-upload"

# Tentukan file yang akan diunggah
try:
    with open("downloaded_filename.txt", "r") as f:
        DOWNLOADED_FILE = f.read().strip()
except FileNotFoundError:
    error_msg = "❌ ERROR: File 'downloaded_filename.txt' tidak ditemukan. Upload dibatalkan."
    print(error_msg)
    send_telegram_message(f"❌ **Upload GAGAL!**\n\n{error_msg}")
    sys.exit(1)

# Pengecekan Kredensial & File
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

# =========================================================
# 2. OTENTIKASI & REFRESH TOKEN
# =========================================================

credentials = OAuth2Credentials(
    access_token=None,
    client_id=CLIENT_ID,
    client_secret=CLIENT_SECRET,
    refresh_token=REFRESH_TOKEN,
    token_expiry=None,
    token_uri='https://oauth2.googleapis.com/token',
    user_agent='GH-Actions-DriveUploader'
)

print("⚡ Memperbarui Access Token menggunakan Refresh Token...")

http_pool = Http()

try:
    credentials.refresh(http=http_pool)
except Exception as e:
    error_msg = f"❌ Gagal memperbarui token. Pastikan Scope sudah 'drive' penuh dan Token valid: {e}"
    print(error_msg)
    send_telegram_message(f"❌ **Upload GAGAL!**\n\n{error_msg[:150]}...")
    sys.exit(1)

http_auth = credentials.authorize(http_pool)
drive_service = build('drive', 'v3', http=http_auth)

print("✅ Autentikasi Drive berhasil. Siap upload!")

# =========================================================
# FUNGSI BANTUAN: Buat Publik
# =========================================================
def make_file_public(service, file_id):
    """
    Menetapkan izin agar file dapat diakses publik (Anyone with the link can view).
    Mengembalikan link Drive (webViewLink) setelah dijadikan publik.
    """
    print("🌍 Menetapkan izin file menjadi publik...")
    permission_body = {
        'type': 'anyone',
        'role': 'reader'
    }
    try:
        # Menambahkan izin baru
        service.permissions().create(
            fileId=file_id,
            body=permission_body,
            fields='id'
        ).execute()
        # Ambil ulang link tampilan web (webViewLink) dan link konten web (webContentLink/direct download)
        file_info = service.files().get(
            fileId=file_id, 
            fields='webViewLink,webContentLink'
        ).execute()
        print("✅ File berhasil dijadikan publik!")
        return file_info.get("webViewLink"), file_info.get("webContentLink")
    except HttpError as e:
        print(f"❌ Gagal mengatur izin file menjadi publik: {e}")
        return None, None

# =========================================================
# 3. LOGIKA UPLOAD (Resumable Upload & Verifikasi MD5)
# =========================================================

def get_or_create_folder(service, folder_name, parent_id=None):
    """Mencari ID folder di Drive, jika tidak ada, membuatnya."""
    query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
    if parent_id:
        query += f" and '{parent_id}' in parents"

    try:
        response = service.files().list(q=query, fields='files(id)').execute()
        files = response.get('files', [])
        if files:
            return files[0].get('id')
        file_metadata = {
            'name': folder_name,
            'mimeType': 'application/vnd.google-apps.folder',
            'parents': [parent_id] if parent_id else []
        }
        file = service.files().create(body=file_metadata, fields='id').execute()
        return file.get('id')
    except HttpError as e:
        print(f"❌ Gagal mengakses/membuat folder: {e}")
        sys.exit(1)

try:
    # 3.1 Cari atau buat folder tujuan
    target_folder_id = get_or_create_folder(drive_service, DRIVE_UPLOAD_FOLDER_NAME)

    # 3.2 Tentukan MIME Type
    MIME_TYPE, _ = mimetypes.guess_type(DOWNLOADED_FILE)
    if not MIME_TYPE:
        MIME_TYPE = 'application/octet-stream'

    # 3.3 Hitung MD5 Lokal
    LOCAL_MD5 = calculate_md5(DOWNLOADED_FILE)
    if not LOCAL_MD5:
        print("❌ Upload dibatalkan karena gagal menghitung MD5 lokal.")
        send_telegram_message(f"❌ **Upload GAGAL!**\n\nGagal menghitung MD5 lokal untuk `{DOWNLOADED_FILE}`.")
        sys.exit(1)
    
    # 3.4 Metadata File
    file_metadata = {
        'name': DOWNLOADED_FILE,
        'parents': [target_folder_id]
    }
    # 3.5 MediaFileUpload object
    media = MediaFileUpload(
        DOWNLOADED_FILE,
        mimetype=MIME_TYPE,
        resumable=True
    )
    # 3.6 Buat Permintaan Upload
    request = drive_service.files().create(
        body=file_metadata,
        media_body=media,
        fields='id,webViewLink,webContentLink,md5Checksum' 
    )
    # Notifikasi mulai upload
    message_id = send_telegram_message(f"🚀 Mulai upload file `{DOWNLOADED_FILE}` ke Google Drive...")
    last_percent_notified = -1
    response = None
    print(f'🚀 Memulai upload Resumable untuk: {DOWNLOADED_FILE}...')
    total_size = os.path.getsize(DOWNLOADED_FILE)
    # Progres upload otomatis ke Telegram setiap 10%
    while response is None:
        try:
            status, response = request.next_chunk()
            percent_uploaded = int(status.progress() * 100) if status else 0
            uploaded_size = int(status.progress() * total_size) if status else 0
            if status and percent_uploaded % 10 == 0 and percent_uploaded > last_percent_notified:
                send_upload_progress(message_id, DOWNLOADED_FILE, uploaded_size, total_size)
                last_percent_notified = percent_uploaded
                print(f'     Uploaded {percent_uploaded}%')
        except ResumableUploadError as e:
            print(f"⚠️ Error Resumable Upload. Mencoba lagi dalam 10 detik...: {e}")
            time.sleep(10)
        except Exception as e:
            print(f"❌ Error tak terduga saat upload. Mencoba lagi dalam 10 detik...: {e}")
            time.sleep(10)
    # --- Verifikasi dan setel izin publik ---
    DRIVE_MD5 = response.get('md5Checksum')
    FILE_ID = response.get('id')
    WEB_VIEW_LINK = response.get("webViewLink")
    if DRIVE_MD5 and LOCAL_MD5 and DRIVE_MD5.lower() == LOCAL_MD5.lower():
        print("👍 VERIFIKASI BERHASIL. File UTUH.")
        # Publikasi file
        PUBLIC_VIEW_LINK, PUBLIC_CONTENT_LINK = make_file_public(drive_service, FILE_ID)
        final_link_view = PUBLIC_VIEW_LINK if PUBLIC_VIEW_LINK else WEB_VIEW_LINK
        final_link_content = PUBLIC_CONTENT_LINK if PUBLIC_CONTENT_LINK else "N/A (Link Download)"
        success_message = (
            f"🎉 **UPLOAD SUKSES!** 🎉\n\n"
            f"File: `{DOWNLOADED_FILE}`\n"
            f"Folder: `{DRIVE_UPLOAD_FOLDER_NAME}`\n"
            f"MD5 Lokal: `{LOCAL_MD5}`\n"
            f"**Status:** **PUBLIK (Dapat Diakses Siapa Saja)!**\n"
            f"Link Drive: [Lihat File]({final_link_view})\n"
            f"Link Download Langsung: `{final_link_content}`" 
        )
        send_telegram_message(success_message)
    else:
        error_message = (
            f"🚨 **UPLOAD GAGAL (VERIFIKASI GAGAL)!**\n\n"
            f"File: `{DOWNLOADED_FILE}`\n"
            f"MD5 Lokal: `{LOCAL_MD5}`\n"
            f"MD5 Drive: `{DRIVE_MD5}`\n\n"
            f"Detail: File di Drive KORUP. Upload DIBATALKAN."
        )
        print(error_message)
        send_telegram_message(error_message)
        sys.exit(1)

except HttpError as e:
    error_message = f"❌ Gagal saat upload file (HTTP Error): {e}"
    print(error_message)
    send_telegram_message(f"❌ **Upload GAGAL (HTTP Error)!**\n\n{error_message[:150]}...")
    sys.exit(1)
except Exception as e:
    error_message = f"❌ Gagal saat upload file: {e}"
    print(error_message)
    send_telegram_message(f"❌ **Upload GAGAL (Umum)!**\n\n{error_message[:150]}...")
    sys.exit(1)

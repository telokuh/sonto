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
# FUNGSI BANTUAN TELEGRAM (Diduplikasi untuk skrip independen)
# =========================================================

# Ambil token bot dan chat ID dari environment variables
BOT_TOKEN = os.environ.get("BOT_TOKEN")
OWNER_ID = os.environ.get("OWNER_ID")

def send_telegram_message(message_text):
    """Fungsi untuk mengirim pesan ke Telegram."""
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
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Gagal mengirim pesan Telegram: {e}")
        
# =========================================================
# Fungsi Bantuan: MD5 Checksum
# =========================================================
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

    # 3.5 Buat MediaFileUpload object
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

    # 3.7 Mulai Upload dan Tangani Chunks
    response = None
    print(f'🚀 Memulai upload Resumable untuk: {DOWNLOADED_FILE}...')
    
    while response is None:
        try:
            status, response = request.next_chunk()
            if status and int(status.progress() * 100) % 10 == 0 and int(status.progress() * 100) > 0:
                 print(f'   Uploaded {int(status.progress() * 100)}%')
        except ResumableUploadError as e:
            print(f"⚠️ Error Resumable Upload. Mencoba lagi dalam 10 detik...: {e}")
            time.sleep(10) 
        except Exception as e:
            print(f"❌ Error tak terduga saat upload. Mencoba lagi dalam 10 detik...: {e}")
            time.sleep(10)
            
    # --- LANGKAH VERIFIKASI AKHIR ---
    DRIVE_MD5 = response.get('md5Checksum')
    WEB_VIEW_LINK = response.get("webViewLink")

    if DRIVE_MD5 and LOCAL_MD5 and DRIVE_MD5.lower() == LOCAL_MD5.lower():
        print("👍 VERIFIKASI BERHASIL. File UTUH.")
        
        success_message = (
            f"🎉 **UPLOAD SUKSES!** 🎉\n\n"
            f"File: `{DOWNLOADED_FILE}`\n"
            f"Folder: `{DRIVE_UPLOAD_FOLDER_NAME}`\n"
            f"MD5 Lokal: `{LOCAL_MD5}`\n"
            f"Link Drive: [Lihat File]({WEB_VIEW_LINK})"
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

from pydrive.auth import GoogleAuth
from pydrive.drive import GoogleDrive
from oauth2client.client import OAuth2Credentials
from googleapiclient.discovery import build # Untuk membuat objek layanan Drive
from googleapiclient.http import MediaFileUpload # Untuk Resumable Upload
import os
import time # Untuk jeda saat upload (opsional)

# Ambil kredensial dari Environment Variables
REFRESH_TOKEN = os.environ.get('DRIVE_REFRESH_TOKEN')
CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID')
CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET')

# Tentukan file yang akan diunggah (Asumsikan Anda membaca nama file dari file teks)
try:
    with open("downloaded_filename.txt", "r") as f:
        DOWNLOADED_FILE = f.read().strip()
except FileNotFoundError:
    print("❌ ERROR: File 'downloaded_filename.txt' tidak ditemukan. Upload dibatalkan.")
    exit(1)

# Folder Drive Tujuan (Opsional, gunakan ID folder)
# DRIVE_FOLDER_ID = "YOUR_SPECIFIC_FOLDER_ID"
DRIVE_FOLDER_ID = None # Jika None, akan diunggah ke root Drive

if not all([REFRESH_TOKEN, CLIENT_ID, CLIENT_SECRET]):
    print("❌ ERROR: Kredensial Google Drive tidak lengkap di environment.")
    exit(1)

# =========================================================
# 1. OTENTIKASI & REFRESH TOKEN
# =========================================================

# 1.1 Buat objek Credentials yang benar dari Refresh Token Anda
credentials = OAuth2Credentials(
    access_token=None,
    client_id=CLIENT_ID,
    client_secret=CLIENT_SECRET,
    refresh_token=REFRESH_TOKEN,
    token_expiry=None,
    token_uri='https://oauth2.googleapis.com/token',
    user_agent='PyDrive-bot'
)

# 1.2 Suntikkan objek Credentials dan Refresh
print("⚡ Memperbarui Access Token menggunakan Refresh Token...")
try:
    credentials.refresh(http=None) # PyDrive/OAuth2Client Refresh
except Exception as e:
    print(f"❌ Gagal memperbarui token. Pastikan Scope sudah 'drive' penuh dan Token valid: {e}")
    exit(1)

# =========================================================
# 2. INISIALISASI LAYANAN DRIVE (googleapiclient)
# =========================================================

# Gunakan credentials.authorize(Http()) untuk mendapatkan objek HTTP yang terautentikasi
# Objek ini akan digunakan oleh googleapiclient.discovery.build
from httplib2 import Http
http_auth = credentials.authorize(Http())

# Buat objek layanan Drive
drive_service = build('drive', 'v3', http=http_auth)

print("✅ Autentikasi Drive berhasil. Siap upload!")

# =========================================================
# 3. RESUMABLE UPLOAD
# =========================================================

try:
    # 3.1 Metadata File
    file_metadata = {
        'name': DOWNLOADED_FILE,
        # Jika DRIVE_FOLDER_ID disetel, tambahkan parents
        'parents': [DRIVE_FOLDER_ID] if DRIVE_FOLDER_ID else [] 
    }

    # Asumsikan MIME Type ZIP atau gunakan 'application/octet-stream' jika tidak yakin
    MIME_TYPE = 'application/zip' 
    
    # 3.2 Buat MediaFileUpload object dengan resumable=True
    media = MediaFileUpload(
        DOWNLOADED_FILE, 
        mimetype=MIME_TYPE, 
        resumable=True
    )

    # 3.3 Buat Permintaan Upload
    # Catatan: Kita menggunakan drive_service (bukan objek PyDrive)
    request = drive_service.files().create(
        body=file_metadata,
        media_body=media,
        fields='id,webContentLink' # Meminta ID dan link untuk respons
    )

    # 3.4 Mulai Upload dan Tangani Chunks
    response = None
    print(f'🚀 Memulai upload Resumable untuk: {DOWNLOADED_FILE}...')
    
    while response is None:
        status, response = request.next_chunk()
        if status:
            progress = int(status.progress() * 100)
            # Batasi cetakan progress agar log tidak terlalu panjang
            if progress % 10 == 0:
                print(f'   Uploaded {progress}%')
        
    print(f'✅ Upload complete! File ID: {response.get("id")}')
    print(f'🔗 Link Download Web: {response.get("webContentLink")}')

except Exception as e:
    print(f"❌ Gagal saat upload file: {e}")
    exit(1)

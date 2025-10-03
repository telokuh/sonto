import os, time
import sys
from oauth2client.client import OAuth2Credentials 
from googleapiclient.discovery import build 
from googleapiclient.http import MediaFileUpload 
from httplib2 import Http

# =========================================================
# 1. KONFIGURASI DAN INISIALISASI
# =========================================================

# Ambil kredensial dari Environment Variables yang disuntikkan di main.yml
REFRESH_TOKEN = os.environ.get('DRIVE_REFRESH_TOKEN')
CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID')
CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET')

# Tentukan file yang akan diunggah
try:
    with open("downloaded_filename.txt", "r") as f:
        DOWNLOADED_FILE = f.read().strip()
except FileNotFoundError:
    print("❌ ERROR: File 'downloaded_filename.txt' tidak ditemukan. Upload dibatalkan.")
    sys.exit(1)

# Jika file download tidak ada di direktori kerja, batalkan.
if not os.path.exists(DOWNLOADED_FILE):
    print(f"❌ ERROR: File '{DOWNLOADED_FILE}' tidak ditemukan di sistem file. Upload dibatalkan.")
    sys.exit(1)

if not all([REFRESH_TOKEN, CLIENT_ID, CLIENT_SECRET]):
    print("❌ ERROR: Kredensial Google Drive tidak lengkap di environment.")
    sys.exit(1)

# Folder Drive Tujuan (Buat folder unik per hari)
DRIVE_UPLOAD_FOLDER_NAME = f"uploads_bot_{time.strftime('%Y%m%d')}" 

# Asumsikan MIME Type ZIP (ganti jika Anda tahu jenis file)
MIME_TYPE = 'application/zip' 
# Anda mungkin perlu logika untuk menentukan MIME type berdasarkan ekstensi.

# =========================================================
# 2. OTENTIKASI & REFRESH TOKEN
# =========================================================

# 2.1 Buat objek Credentials yang benar dari Refresh Token
credentials = OAuth2Credentials(
    access_token=None,
    client_id=CLIENT_ID,
    client_secret=CLIENT_SECRET,
    refresh_token=REFRESH_TOKEN,
    token_expiry=None,
    token_uri='https://oauth2.googleapis.com/token',
    user_agent='GH-Actions-DriveUploader'
)

# 2.2 Memperbarui Access Token (Perbaikan untuk 'NoneType' object is not callable)
print("⚡ Memperbarui Access Token menggunakan Refresh Token...")

http_pool = Http() 

try:
    # Lakukan refresh, salurkan objek HTTP yang valid
    credentials.refresh(http=http_pool) 
except Exception as e:
    print(f"❌ Gagal memperbarui token. Pastikan Scope sudah 'drive' penuh dan Token valid: {e}")
    sys.exit(1)

# 2.3 Inisialisasi Layanan Drive
http_auth = credentials.authorize(http_pool) 
drive_service = build('drive', 'v3', http=http_auth)

print("✅ Autentikasi Drive berhasil. Siap upload!")

# =========================================================
# 3. LOGIKA UPLOAD
# =========================================================

# Fungsi untuk mencari atau membuat folder
def get_or_create_folder(service, folder_name, parent_id=None):
    # Cek apakah folder sudah ada
    query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder'"
    if parent_id:
        query += f" and '{parent_id}' in parents"
        
    response = service.files().list(q=query, fields='files(id)').execute()
    files = response.get('files', [])
    
    if files:
        print(f"💡 Folder '{folder_name}' sudah ada.")
        return files[0].get('id')
    
    # Jika tidak ada, buat folder baru
    file_metadata = {
        'name': folder_name,
        'mimeType': 'application/vnd.google-apps.folder',
        'parents': [parent_id] if parent_id else []
    }
    file = service.files().create(body=file_metadata, fields='id').execute()
    print(f"➕ Folder '{folder_name}' berhasil dibuat.")
    return file.get('id')


try:
    # 3.1 Cari atau buat folder tujuan
    target_folder_id = get_or_create_folder(drive_service, DRIVE_UPLOAD_FOLDER_NAME)

    # 3.2 Metadata File
    file_metadata = {
        'name': DOWNLOADED_FILE,
        'parents': [target_folder_id] 
    }

    # 3.3 Buat MediaFileUpload object dengan resumable=True
    media = MediaFileUpload(
        DOWNLOADED_FILE, 
        mimetype=MIME_TYPE, 
        resumable=True
    )

    # 3.4 Buat Permintaan Upload
    request = drive_service.files().create(
        body=file_metadata,
        media_body=media,
        fields='id,webViewLink' 
    )

    # 3.5 Mulai Upload dan Tangani Chunks
    response = None
    print(f'🚀 Memulai upload Resumable untuk: {DOWNLOADED_FILE}...')
    
    while response is None:
        status, response = request.next_chunk()
        if status:
            progress = int(status.progress() * 100)
            # Batasi cetakan progress
            if progress % 10 == 0:
                print(f'   Uploaded {progress}%')
        
    print(f'✅ Upload complete! File ID: {response.get("id")}')
    print(f'🔗 Link Web Drive: {response.get("webViewLink")}')

except Exception as e:
    print(f"❌ Gagal saat upload file: {e}")
    sys.exit(1)

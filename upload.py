import os
import sys
import time
import mimetypes 
import hashlib # Untuk menghitung MD5 checksum
from oauth2client.client import OAuth2Credentials 
from googleapiclient.discovery import build 
from googleapiclient.http import MediaFileUpload 
from httplib2 import Http 
from googleapiclient.errors import HttpError
from googleapiclient.errors import ResumableUploadError

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

# Ambil kredensial dari Environment Variables
REFRESH_TOKEN = os.environ.get('DRIVE_REFRESH_TOKEN')
CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID')
CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET')

# Tentukan file yang akan diunggah dengan membaca dari file sementara
try:
    with open("downloaded_filename.txt", "r") as f:
        DOWNLOADED_FILE = f.read().strip()
except FileNotFoundError:
    print("❌ ERROR: File 'downloaded_filename.txt' tidak ditemukan. Upload dibatalkan.")
    sys.exit(1)

# Pengecekan Kredensial & File
if not os.path.exists(DOWNLOADED_FILE):
    print(f"❌ ERROR: File '{DOWNLOADED_FILE}' tidak ditemukan di sistem file. Upload dibatalkan.")
    sys.exit(1)

if not all([REFRESH_TOKEN, CLIENT_ID, CLIENT_SECRET]):
    print("❌ ERROR: Kredensial Google Drive tidak lengkap di environment.")
    sys.exit(1)

# Folder Drive Tujuan
DRIVE_UPLOAD_FOLDER_NAME = "my-drive-upload" 


# =========================================================
# 2. OTENTIKASI & REFRESH TOKEN
# =========================================================

# 2.1 Buat objek Credentials dari Refresh Token
credentials = OAuth2Credentials(
    access_token=None,
    client_id=CLIENT_ID,
    client_secret=CLIENT_SECRET,
    refresh_token=REFRESH_TOKEN,
    token_expiry=None,
    token_uri='https://oauth2.googleapis.com/token',
    user_agent='GH-Actions-DriveUploader'
)

# 2.2 Memperbarui Access Token
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
    
    print(f"💡 Ditemukan MIME Type: {MIME_TYPE}")

    # 3.3 Hitung MD5 Lokal (LANGKAH KRITIS)
    LOCAL_MD5 = calculate_md5(DOWNLOADED_FILE)
    if not LOCAL_MD5:
        print("❌ Upload dibatalkan karena gagal menghitung MD5 lokal.")
        sys.exit(1)
    
    print(f"💡 MD5 Checksum File Lokal: {LOCAL_MD5}")


    # 3.4 Metadata File
    file_metadata = {
        'name': DOWNLOADED_FILE,
        'parents': [target_folder_id] 
    }

    # 3.5 Buat MediaFileUpload object (resumable=True)
    media = MediaFileUpload(
        DOWNLOADED_FILE, 
        mimetype=MIME_TYPE, 
        resumable=True
    )

    # 3.6 Buat Permintaan Upload
    request = drive_service.files().create(
        body=file_metadata,
        media_body=media,
        # Meminta id, link, DAN md5Checksum untuk verifikasi
        fields='id,webViewLink,webContentLink,md5Checksum' 
    )

    # 3.7 Mulai Upload dan Tangani Chunks
    response = None
    print(f'🚀 Memulai upload Resumable untuk: {DOWNLOADED_FILE}...')
    
    while response is None:
        try:
            status, response = request.next_chunk()
            if status:
                progress = int(status.progress() * 100)
                # Batasi cetakan progress
                if progress % 10 == 0 and progress > 0:
                    print(f'   Uploaded {progress}%')
        except ResumableUploadError as e:
            # Coba ulangi jika ada error koneksi / resumable
            print(f"⚠️ Error Resumable Upload. Mencoba lagi dalam 10 detik...: {e}")
            time.sleep(10) 
        except Exception as e:
            # Tangani error umum di tengah proses upload
            print(f"❌ Error tak terduga saat upload. Mencoba lagi dalam 10 detik...: {e}")
            time.sleep(10)
            
    # --- LANGKAH VERIFIKASI AKHIR ---
    DRIVE_MD5 = response.get('md5Checksum')

    print(f'✅ Upload complete! File ID: {response.get("id")}')
    print(f'🔗 Link Web Drive: {response.get("webViewLink")}')

    if DRIVE_MD5 and LOCAL_MD5 and DRIVE_MD5.lower() == LOCAL_MD5.lower():
        print(f"👍 VERIFIKASI BERHASIL: MD5 Drive ({DRIVE_MD5}) cocok dengan MD5 Lokal. File APK UTUH.")
    else:
        print("🚨 VERIFIKASI GAGAL: MD5 Checksum tidak cocok!")
        print(f"   Lokal: {LOCAL_MD5}, Drive: {DRIVE_MD5}")
        print("   File di Drive KORUP. Upload GAGAL.")
        sys.exit(1) # Keluar dengan error agar proses CI/CD gagal
        
except HttpError as e:
    print(f"❌ Gagal saat upload file (HTTP Error): {e}")
    sys.exit(1)
except Exception as e:
    print(f"❌ Gagal saat upload file: {e}")
    sys.exit(1)

from pydrive.auth import GoogleAuth
from pydrive.drive import GoogleDrive
from oauth2client.client import OAuth2Credentials # <<< IMPORT BARU KRITIS
import os

# Ambil kredensial dari Environment Variables
REFRESH_TOKEN = os.environ.get('DRIVE_REFRESH_TOKEN')
CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID')
CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET')

# File yang sudah didownload (misalnya, dari main.py)
DOWNLOADED_FILE = os.environ.get('FILENAME') # Ganti dengan logika penemuan file yang benar

if not all([REFRESH_TOKEN, CLIENT_ID, CLIENT_SECRET]):
    print("❌ ERROR: Kredensial Google Drive tidak lengkap di environment.")
    exit(1)


# 1. Konfigurasi GAuth (Kita masih perlu ini untuk setelan klien)
gauth = GoogleAuth()
gauth.settings = {
    "client_config": {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
    },
    "oauth_scope": ["https://www.googleapis.com/auth/drive"],
    # Sisanya adalah default atau tidak terlalu penting untuk server-side
}

# 2. BUAT OBJEK CREDENTIALS YANG BENAR
# Kita membuat objek OAuth2Credentials secara manual dari Refresh Token.
credentials = OAuth2Credentials(
    access_token=None,           # Tidak ada Access Token, akan di-refresh
    client_id=CLIENT_ID,
    client_secret=CLIENT_SECRET,
    refresh_token=REFRESH_TOKEN, # Refresh Token kita
    token_expiry=None,
    token_uri='https://oauth2.googleapis.com/token', # Endpoint Google
    user_agent='PyDrive-bot'
)

# 3. Suntikkan objek Credentials yang benar ke PyDrive
gauth.credentials = credentials

# 4. Memperbarui Access Token (Sekarang berfungsi!)
print("⚡ Memperbarui Access Token menggunakan Refresh Token...")
try:
    gauth.Refresh()
    drive = GoogleDrive(gauth)
    print("✅ Autentikasi Drive berhasil!")
except Exception as e:
    print(f"❌ Gagal memperbarui token: {e}")
    exit(1)

# 5. Logika Upload
# --- Ganti logika di bawah ini dengan kebutuhan upload Anda ---
try:
    print(f"🚀 Memulai upload file: {DOWNLOADED_FILE}")
    gfile = drive.CreateFile({'title': DOWNLOADED_FILE, 'mimeType': 'application/octet-stream'})
    gfile.SetContentFile(DOWNLOADED_FILE)
    gfile.Upload(param={'supportsTeamDrives': True}) 
    print(f"✅ Upload {DOWNLOADED_FILE} berhasil. ID: {gfile['id']}")
except Exception as e:
    print(f"❌ Gagal saat upload file: {e}")
    exit(1)

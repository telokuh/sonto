# Dalam main.py

from pydrive.auth import GoogleAuth
from pydrive.drive import GoogleDrive
import os

# Ambil kredensial dari Environment Variables
REFRESH_TOKEN = os.environ.get('DRIVE_REFRESH_TOKEN')
CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID')
CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET')

# 1. Konfigurasi GAuth dengan kredensial server
gauth = GoogleAuth()
gauth.settings = {
    "client_config": {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
    },
    "oauth_scope": ["https://www.googleapis.com/auth/drive"],
    "get_refresh_token": True,
    "save_credentials": True,
    "save_credentials_backend": "file",
    "save_credentials_file": "credentials.json"
}

# 2. Set Refresh Token (memaksa otentikasi)
gauth.credentials = gauth.credentials or {}
gauth.credentials['refresh_token'] = REFRESH_TOKEN
gauth.Refresh() # Memperbarui Access Token

drive = GoogleDrive(gauth)

# 3. Upload File
file_name = os.environ.get('FILENAME')
gfile = drive.CreateFile({'title': file_name})
gfile.SetContentFile(file_name)
gfile.Upload()

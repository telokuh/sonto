#!/bin/bash

# upload_drive.sh
# Skrip ini mengunggah file yang diunduh ke Google Drive menggunakan rclone.

# =========================================================
# 1. KONFIGURASI LOKAL DAN KREDENSIAL
# =========================================================

# Ambil Refresh Token yang disuntikkan dari GitHub Secrets (harus disetel di workflow)
# NOTE: Nama variabel harus sesuai dengan nama yang Anda set di workflow.
REFRESH_TOKEN="$DRIVE_REFRESH_TOKEN"
CLIENT_ID="$GOOGLE_CLIENT_ID"
CLIENT_SECRET="$GOOGLE_CLIENT_SECRET"

# Direktori Google Drive tujuan
DRIVE_REMOTE_NAME="gdrive"
DRIVE_UPLOAD_FOLDER="/TheGdriveXbot" # Folder unik per hari di Drive

# File yang akan diunggah (Asumsikan sudah didownload dan namanya diketahui)
# Anda harus mengganti 'downloaded_filename.txt' dengan file yang benar.
DOWNLOADED_FILE=$FILENAME 

if [ -z "$REFRESH_TOKEN" ]; then
    echo "❌ ERROR: DRIVE_REFRESH_TOKEN tidak ditemukan. Otorisasi Gagal."
    exit 1
fi

if [ ! -f "$DOWNLOADED_FILE" ]; then
    echo "❌ ERROR: File download '$DOWNLOADED_FILE' tidak ditemukan. Upload dibatalkan."
    exit 1
fi

# =========================================================
# 2. BUAT KONFIGURASI RCLONE SEMENTARA
# =========================================================

echo "Membuat konfigurasi rclone sementara..."
RCLONE_CONFIG_PATH="$HOME/.config/rclone/rclone.conf"
mkdir -p "$HOME/.config/rclone"

cat << EOF > "$RCLONE_CONFIG_PATH"
[${DRIVE_REMOTE_NAME}]
type = drive
scope = https://www.googleapis.com/auth/drive.readonly # Gunakan scope yang sesuai
client_id = ${CLIENT_ID}
client_secret = ${CLIENT_SECRET}
# Perbaikan: Gunakan parameter refresh_token secara eksplisit
refresh_token = ${REFRESH_TOKEN} 
# Kita tidak perlu lagi menyertakan blok "token" JSON yang kompleks
EOF

echo "✅ Konfigurasi rclone berhasil dibuat."

# =========================================================
# 3. UPLOAD FILE MENGGUNAKAN RCLONE
# =========================================================

echo "🚀 Memulai proses upload ke Google Drive di folder: ${DRIVE_UPLOAD_FOLDER}"

# Buat folder tujuan di Drive (rclone mkdir)
rclone mkdir "${DRIVE_REMOTE_NAME}:${DRIVE_UPLOAD_FOLDER}"

# Upload file
rclone_output=$(rclone copy "$DOWNLOADED_FILE" "${DRIVE_REMOTE_NAME}:${DRIVE_UPLOAD_FOLDER}" -v --stats 1s 2>&1)

if [ $? -eq 0 ]; then
    echo "✅ Upload berhasil!"
    echo "------------------------------------------------------"
    # Anda bisa mencari link di output rclone untuk dikirim kembali ke Telegram
    echo "Log Rclone:"
    echo "$rclone_output"
    echo "------------------------------------------------------"
else
    echo "❌ Upload GAGAL. Cek log di atas untuk detail rclone."
    exit 1
fi

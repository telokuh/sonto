#!/bin/bash

# upload_drive.sh

# =========================================================
# 1. KONFIGURASI LOKAL DAN KREDENSIAL
# =========================================================

# Ambil variabel yang disuntikkan dari main.yml
REFRESH_TOKEN="$DRIVE_REFRESH_TOKEN"
CLIENT_ID="$GOOGLE_CLIENT_ID"
CLIENT_SECRET="$GOOGLE_CLIENT_SECRET"

DRIVE_REMOTE_NAME="gdrive"
DRIVE_UPLOAD_FOLDER="/uploads_bot" 

DOWNLOADED_FILE=$FILENAME

if [ -z "$REFRESH_TOKEN" ]; then
    echo "❌ ERROR: DRIVE_REFRESH_TOKEN tidak ditemukan. Upload dibatalkan."
    exit 1
fi

if [ ! -f "$DOWNLOADED_FILE" ]; then
    echo "❌ ERROR: File download '$DOWNLOADED_FILE' tidak ditemukan. Upload dibatalkan."
    exit 1
fi

# =========================================================
# 2. PEMBESIHAN REFRESH TOKEN
# =========================================================

# PENTING: Hapus semua line break dan spasi di awal/akhir
CLEAN_REFRESH_TOKEN=$(echo "$REFRESH_TOKEN" | tr -d '\n' | xargs)

if [ -z "$CLEAN_REFRESH_TOKEN" ]; then
    echo "❌ ERROR: Refresh Token kosong setelah dibersihkan. Cek penyaluran Secret di main.yml."
    exit 1
fi

echo "✅ Refresh Token berhasil dibersihkan dan siap digunakan."

# =========================================================
# 3. BUAT KONFIGURASI RCLONE SEMENTARA (FORMAT TERBAIK)
# =========================================================

echo "Membuat konfigurasi rclone sementara..."
RCLONE_CONFIG_PATH="$HOME/.config/rclone/rclone.conf"
mkdir -p "$HOME/.config/rclone"

# WAKTU KEDALUWARSA DUMMY
DUMMY_EXPIRY="0001-01-01T00:00:00Z"

# Format token JSON penuh: Pastikan Refresh Token yang digunakan adalah yang sudah dibersihkan.
TOKEN_JSON="{\"access_token\":\"\",\"token_type\":\"Bearer\",\"refresh_token\":\"${CLEAN_REFRESH_TOKEN}\",\"expiry\":\"${DUMMY_EXPIRY}\"}"


cat << EOF > "$RCLONE_CONFIG_PATH"
[${DRIVE_REMOTE_NAME}]
type = drive
client_id = "${CLIENT_ID}" 
client_secret = "${CLIENT_SECRET}" 
token = ${TOKEN_JSON} 
EOF

echo "✅ Konfigurasi rclone berhasil dibuat."

# =========================================================
# 4. UPLOAD FILE MENGGUNAKAN RCLONE
# =========================================================

echo "🚀 Memulai proses upload ke Google Drive di folder: ${DRIVE_UPLOAD_FOLDER}"

# Gunakan flag --drive-scope untuk mengatasi masalah root directory (opsional tapi aman)
rclone mkdir "${DRIVE_REMOTE_NAME}:${DRIVE_UPLOAD_FOLDER}" --drive-scope drive

rclone_output=$(rclone copy "$DOWNLOADED_FILE" "${DRIVE_REMOTE_NAME}:${DRIVE_UPLOAD_FOLDER}" -v --stats 1s 2>&1)

if [ $? -eq 0 ]; then
    echo "✅ Upload berhasil!"
    # ... (log output) ...
else
    echo "❌ Upload GAGAL. Cek log di atas untuk detail rclone."
    exit 1
fi

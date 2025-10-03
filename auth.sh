#!/bin/bash

# =========================================================
# Google OAuth 2.0 Flow via Telegram
# Variabel diambil dari lingkungan (GitHub Actions).
# =========================================================

# --- 1. KONFIGURASI ---

# Variabel konfigurasi
REDIRECT_URI="urn:ietf:wg:oauth:2.0:oob"
SCOPE="https://www.googleapis.com/auth/drive.readonly"

# Variabel diambil dari lingkungan (Harus diatur di GitHub Actions ENVs)
# CLIENT_ID, CLIENT_SECRET, TG_BOT_TOKEN, TG_CHAT_ID

# Pastikan semua variabel lingkungan ada
if [ -z "$CLIENT_ID" ] || [ -z "$CLIENT_SECRET" ] || [ -z "$TG_BOT_TOKEN" ] || [ -z "$TG_CHAT_ID" ]; then
    echo "❌ ERROR: Satu atau lebih variabel lingkungan otorisasi tidak diatur."
    exit 1
fi

# ... (kode sebelumnya) ...

# --- 2. KIRIM URL KE TELEGRAM ---

echo ""
echo "Mengirim URL otorisasi ke Telegram Chat ID: $TG_CHAT_ID"

# 1. Pastikan AUTH_URL dibuat dengan tepat
AUTH_URL="https://accounts.google.com/o/oauth2/v2/auth?client_id=${CLIENT_ID}&redirect_uri=${REDIRECT_URI}&scope=${SCOPE}&response_type=code&access_type=offline"

# 2. Buat Payload Teks Telegram dengan Bash Here-Document
# Menggunakan tanda kutip tunggal ('EOF') mencegah ekspansi variabel di dalam dokumen.
TELEGRAM_TEXT=$(cat <<EOF
<b>Buka URL ini di peramban Anda:</b>

<pre>${AUTH_URL}</pre>
EOF
)

# Kirim URL dan dapatkan message_id dari respons
# Menggunakan --data-urlencode untuk mengirim data teks secara aman
SEND_RESPONSE=$(curl -s -X POST "https://api.telegram.org/bot${TG_BOT_TOKEN}/sendMessage" \
    --data-urlencode "chat_id=${TG_CHAT_ID}" \
    --data-urlencode "text=${TELEGRAM_TEXT}" \
    --data-urlencode "parse_mode=HTML") # parse_mode="HTML" sudah benar
    

if [ "$(echo "$SEND_RESPONSE" | jq -r '.ok')" != "true" ]; then
    echo "❌ Gagal mengirim pesan ke Telegram."
    echo "Respons API: $SEND_RESPONSE"
    exit 1
fi

echo "✅ URL berhasil dikirim. Silakan periksa Telegram Anda dan kirim kode balasan."

# --- 3. TUNGGU KODE OTORISASI DARI TELEGRAM ---

echo ""
echo "Menunggu kode otorisasi dari Telegram..."

AUTH_CODE=""
LAST_UPDATE_ID=0

while [ -z "$AUTH_CODE" ]; do
    # Dapatkan pembaruan baru (pesan baru) dari bot
    UPDATES=$(curl -s "https://api.telegram.org/bot${TG_BOT_TOKEN}/getUpdates?offset=${LAST_UPDATE_ID}")
    
    NEW_MESSAGES=$(echo "$UPDATES" | jq -c '.result[] | select(.message)')

    if [ -n "$NEW_MESSAGES" ]; then
        LAST_UPDATE_ID=$(echo "$UPDATES" | jq '[.result[].update_id] | max + 1')

        echo "$NEW_MESSAGES" | while read -r MESSAGE_JSON; do
            CHAT_ID=$(echo "$MESSAGE_JSON" | jq -r '.message.chat.id')
            MESSAGE_TEXT=$(echo "$MESSAGE_JSON" | jq -r '.message.text // empty')

            if [ "$CHAT_ID" = "$TG_CHAT_ID" ]; then
                # Regex untuk menemukan kode otorisasi (biasanya dimulai dengan 4/ atau 8/)
                if [[ "$MESSAGE_TEXT" =~ ^[48]\/.* ]]; then
                    AUTH_CODE="$MESSAGE_TEXT"
                    echo "✅ Kode otorisasi diterima: $AUTH_CODE"
                    break 2 # Hentikan loop while dan loop outer
                fi
            fi
        done
    fi

    if [ -n "$AUTH_CODE" ]; then
        break
    fi

    # Jeda
    sleep 3
done

# --- 4. TUKAR KODE UNTUK TOKEN ---

echo ""
echo "Menukar kode untuk token..."
TOKEN_RESPONSE=$(curl --request POST \
  --url https://oauth2.googleapis.com/token \
  --header "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "code=${AUTH_CODE}" \
  --data-urlencode "client_id=${CLIENT_ID}" \
  --data-urlencode "client_secret=${CLIENT_SECRET}" \
  --data-urlencode "redirect_uri=${REDIRECT_URI}" \
  --data-urlencode "grant_type=authorization_code")

# Cetak respons lengkap (untuk informasi)
echo "$TOKEN_RESPONSE" | jq

# Ekstrak refresh_token
REFRESH_TOKEN=$(echo "$TOKEN_RESPONSE" | jq -r '.refresh_token // empty')

if [ -n "$REFRESH_TOKEN" ]; then
    echo ""
    echo "✅ Refresh Token Ditemukan. Mengirim ke GitHub Actions Output..."
    
    # OUTPUT UTAMA UNTUK GITHUB ACTIONS
    echo "refresh_token=$REFRESH_TOKEN" >> $GITHUB_OUTPUT
    
else
    echo "⚠️ Refresh Token tidak ditemukan. Tidak ada yang disimpan."
fi

echo ""
echo "Proses Otorisasi Selesai."

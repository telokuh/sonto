#!/bin/bash

# =========================================================
# Google OAuth 2.0 Flow via Telegram
# ---------------------------------------------------------
# Skrip ini mengirimkan URL otorisasi ke Telegram dan
# menunggu kode otorisasi kembali melalui bot.
# =========================================================

# --- 1. KONFIGURASI ---

# Ganti dengan nilai Anda
REDIRECT_URI="urn:ietf:wg:oauth:2.0:oob"
SCOPE="https://www.googleapis.com/auth/drive.readonly"

echo "Masukkan detail Anda."
read -p "Client ID: " CLIENT_ID
read -p "Client Secret: " CLIENT_SECRET
read -p "Telegram Bot Token: " TG_BOT_TOKEN
read -p "Telegram Chat ID: " TG_CHAT_ID

# --- 2. KIRIM URL KE TELEGRAM ---

echo ""
echo "Mengirim URL otorisasi ke Telegram..."

AUTH_URL="https://accounts.google.com/o/oauth2/v2/auth?client_id=${CLIENT_ID}&redirect_uri=${REDIRECT_URI}&scope=${SCOPE}&response_type=code&access_type=offline"
FORMATTED_AUTH_URL="*Buka URL ini di peramban Anda:*\n\n${AUTH_URL}"

# Kirim URL dan dapatkan message_id dari respons
SEND_RESPONSE=$(curl -s -X POST "https://api.telegram.org/bot${TG_BOT_TOKEN}/sendMessage" \
    -d chat_id="${TG_CHAT_ID}" \
    -d text="${FORMATTED_AUTH_URL}" \
    -d parse_mode="Markdown")

# Periksa apakah pesan berhasil dikirim
if [ "$(echo "$SEND_RESPONSE" | jq -r '.ok')" != "true" ]; then
    echo "❌ Gagal mengirim pesan ke Telegram."
    echo "Respons API: $SEND_RESPONSE"
    exit 1
fi

echo "✅ URL berhasil dikirim. Silakan periksa Telegram Anda."

# --- 3. TUNGGU KODE OTORISASI DARI TELEGRAM ---

echo ""
echo "Menunggu kode otorisasi dari Telegram... (Mungkin perlu beberapa detik)"

AUTH_CODE=""
LAST_UPDATE_ID=0

while [ -z "$AUTH_CODE" ]; do
    # Dapatkan pembaruan baru (pesan baru) dari bot
    UPDATES=$(curl -s "https://api.telegram.org/bot${TG_BOT_TOKEN}/getUpdates?offset=${LAST_UPDATE_ID}")
    
    # Ekstrak pesan terbaru
    NEW_MESSAGES=$(echo "$UPDATES" | jq '.result[] | select(.message)' | jq -r '.')

    if [ -n "$NEW_MESSAGES" ]; then
        # Ambil pembaruan terakhir dan perbarui offset
        LAST_UPDATE_ID=$(echo "$NEW_MESSAGES" | jq '.[-1].update_id' | tail -1 | tr -d '\n' )
        ((LAST_UPDATE_ID++))

        # Cek apakah ada pesan dari chat ID yang benar yang berisi kode
        MESSAGE_TEXT=$(echo "$NEW_MESSAGES" | jq -r --arg chat_id "${TG_CHAT_ID}" '.[] | select(.message.chat.id | tostring == $chat_id) | .message.text' | tail -n 1)

        # Gunakan regex untuk menemukan string yang terlihat seperti kode otorisasi
        if [[ "$MESSAGE_TEXT" =~ ^[48]\/.* ]]; then
            AUTH_CODE="$MESSAGE_TEXT"
            echo "✅ Kode otorisasi diterima!"
        fi
    fi

    # Jeda sejenak untuk menghindari rate-limiting API Telegram
    sleep 3
done

# --- 4. TUKAR KODE UNTUK TOKEN ---

echo ""
echo "Menukar kode untuk token..."
echo "----------------------------------------------------------------------"
curl --request POST \
  --url https://oauth2.googleapis.com/token \
  --header "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "code=${AUTH_CODE}" \
  --data-urlencode "client_id=${CLIENT_ID}" \
  --data-urlencode "client_secret=${CLIENT_SECRET}" \
  --data-urlencode "redirect_uri=${REDIRECT_URI}" \
  --data-urlencode "grant_type=authorization_code" | jq

echo ""
echo "Sukses! Token Anda ditampilkan di atas."
echo "Simpan 'refresh_token' untuk penggunaan di masa mendatang."

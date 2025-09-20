#!/bin/bash

# Pastikan bash membaca karakter per karakter, bukan baris per baris
set -o nounset
set -o pipefail

# Ambil argumen dari skrip Python
url=$1
msg_id=$2
TG_TOKEN=$3
ch_id=$4

last_percentage=-1

# Fungsi untuk memperbarui pesan Telegram
update_telegram() {
    local percentage=$1
    curl -s "https://api.telegram.org/bot${TG_TOKEN}/editMessageText" \
        --data "message_id=${msg_id}&text=⬇️ **Mengunduh...**\nProgres: \`$percentage\`&chat_id=${ch_id}&parse_mode=Markdown" > /dev/null
}

echo "Mulai unduhan dengan aria2c..."
echo "URL: $url"

# Jalankan aria2c dan proses outputnya
aria2c "$url" -x 16 -s 16 -c 2>&1 | while IFS= read -r -n 1 char; do
    buffer+="$char"
    
    # Cari persentase dalam buffer
    if [[ "$buffer" =~ ([0-9]+\.[0-9]+%) ]]; then
        current_percentage="${BASH_REMATCH[1]}"
        
        # Ekstrak bagian integer dari persentase
        current_integer=$(echo "$current_percentage" | cut -d'.' -f1)

        # Perbarui Telegram hanya jika ada perubahan signifikan
        if (( current_integer > last_percentage + 5 || current_integer == 100 )); then
            update_telegram "$current_percentage"
            last_percentage="$current_integer"
        fi

        # Bersihkan buffer
        buffer=""
    fi
done

# Kirim pesan terakhir 100% untuk memastikan unduhan selesai
update_telegram "100.0%"

echo "Unduhan selesai."

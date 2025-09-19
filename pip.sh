#!/bin/bash
pip install requests pyrogram python-dotenv
# Periksa apakah variabel lingkungan $URL mengandung "mediafire"
if [[ "$URL" == *"mediafire"* ]]; then
    echo "URL mengandung 'mediafire'. Menjalankan pip install selenium..."
    pip install selenium webdriver-manager
# Jika tidak, periksa apakah mengandung "mega"
elif [[ "$URL" == *"mega"* ]]; then
    echo "URL mengandung 'mega'. Menjalankan pip install mega..."
    pip install mega
    
elif [[ "$URL" == *"pixeldrain"* ]]; then
    echo "URL pixel"

# Jika tidak ada yang cocok
else
    pip install yt-dlp
    echo "URL tidak mengandung 'mediafire' atau 'mega'. Tidak ada tindakan yang diambil."
fi

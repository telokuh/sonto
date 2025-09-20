import os
import re
from utils import (
    send_telegram_message,
    get_download_url_with_yt_dlp,
    get_download_url_with_selenium,
    download_file_with_megatools,
    download_file,
    get_download_url_from_pixeldrain_api
)

# Dapatkan URL halaman dari environment variable
mediafire_page_url = os.environ.get("MEDIAFIRE_PAGE_URL")

# Regex untuk mendeteksi URL
YOUTUBE_URL_REGEX = r"(?:https?://)?(?:www\.)?(?:youtube\.com|youtu\.be)/.+"
MEGA_URL_REGEX = r"(?:https?://)?(?:www\.)?mega\.nz/.+"
PIXELDRAIN_URL_REGEX = r"(?:https?://)?(?:www\.)?pixeldrain\.com/u/.+"
GOFILE_URL_REGEX = r"(?:https?://)?(?:www\.)?gofile\.io/.+"

if not mediafire_page_url:
    print("Error: MEDIAFIRE_PAGE_URL environment variable not set.")
    exit(1)

# --- Logika Utama ---
formatted_url = f"`{mediafire_page_url.replace('http://', '').replace('https://', '')}`"
send_telegram_message(f"🔍 **Mulai memproses URL:**\n{formatted_url}")

is_gofile_url = re.match(GOFILE_URL_REGEX, mediafire_page_url) # <-- Tambahkan deteksi URL GoFile
is_mega_url = re.match(MEGA_URL_REGEX, mediafire_page_url)
is_pixeldrain_url = re.match(PIXELDRAIN_URL_REGEX, mediafire_page_url)
downloaded_filename = None

# Coba yt-dlp terlebih dahulu untuk SEMUA URL
download_url = get_download_url_with_yt_dlp(mediafire_page_url)

if download_url:
    downloaded_filename = download_file(download_url)
elif is_pixeldrain_url:
    send_telegram_message("`yt-dlp` gagal. Menggunakan API Pixeldrain.")
    download_url_pixeldrain = get_download_url_from_pixeldrain_api(mediafire_page_url)
    if download_url_pixeldrain:
        downloaded_filename = download_file(download_url_pixeldrain)

elif is_gofile_url: # <-- Tambahkan kondisi untuk GoFile
    send_telegram_message("`yt-dlp` gagal memproses URL GoFile. Menggunakan Selenium...")
    download_url_gofile = get_download_url_with_selenium_gofile(mediafire_page_url)
    
elif is_mega_url:
    send_telegram_message("`yt-dlp` gagal memproses URL MEGA. Beralih ke `megatools`...")
    downloaded_filename = download_file_with_megatools(mediafire_page_url)
else:
    send_telegram_message("`yt-dlp` gagal memproses URL. Menggunakan Selenium sebagai cadangan...")
    download_url_selenium = get_download_url_with_selenium(mediafire_page_url)
    if download_url_selenium:
        downloaded_filename = download_file(download_url_selenium)

if downloaded_filename:
    with open("downloaded_filename.txt", "w") as f:
        f.write(downloaded_filename)
    send_telegram_message(f"✅ **Selesai!**\nFile berhasil diunduh dan sedang dibuatkan rilis di GitHub.")
else:
    print("Tidak dapat menemukan URL unduhan. Proses dihentikan.")
    send_telegram_message("❌ **Proses gagal.**\nTidak dapat menemukan URL unduhan.")
    exit(1)

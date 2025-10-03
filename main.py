import os
import re
from utils import (
    send_telegram_message,
    edit_telegram_message,
    download_with_yt_dlp,
    download_file_with_aria2c,
    download_file_with_megatools,
    pixeldrain,
    downloader
)

# Dapatkan URL halaman dari environment variable
mediafire_page_url = os.environ.get("MEDIAFIRE_PAGE_URL")

# Regex untuk mendeteksi URL
MEGA_URL_REGEX = r"(?:https?://)?(?:www\.)?mega\.nz/.+"


if not mediafire_page_url:
    print("Error: MEDIAFIRE_PAGE_URL environment variable not set.")
    exit(1)

def main_downloader(url):
    formatted_url = f"`{url.replace('http://', '').replace('https://', '')}`"
    initial_message_id = send_telegram_message(f"🔍 **Mulai memproses URL:**\n{formatted_url}")
    downloaded_filename = None

    # --- Logika Berjenjang ---
    if re.match(MEGA_URL_REGEX, url):
        print("MEGA. Menggunakan megatools...")
        
        downloaded_filename = download_file_with_megatools(url)
    elif "pixeldrain" in url:
        downloaded_filename = pixeldrain(url)
    elif "mediafire" in url or "gofile" in url or "sourceforge" in url:
        print(" Menggunakan Selenium...")
        downloaded_filename = downloader(url)
        

    else:
        # Coba yt-dlp sebagai opsi universal
        print("URL tidak cocok dengan pola khusus. Mencoba dengan yt-dlp...")
        yt_dlp_success = download_with_yt_dlp(url)
        if yt_dlp_success:
            downloaded_filename = yt_dlp_success
        else:
            # Fallback ke aria2c jika yt-dlp gagal
            print("yt-dlp gagal. Mencoba dengan aria2c sebagai cadangan...")
            downloaded_filename = download_file_with_aria2c(url, message_id=initial_message_id)
    
    if downloaded_filename:
        with open("downloaded_filename.txt", "w") as f:
            f.write(downloaded_filename)
        send_telegram_message(f"✅ **Selesai!**\nFile `{downloaded_filename}` berhasil diunduh dan sedang dibuatkan rilis di GitHub.")
    else:
        print(f"{downloaded_filename} Tidak dapat menemukan URL unduhan. Proses dihentikan.")
        send_telegram_message(f"{downloaded_filename} ❌ **Proses gagal.**\nTidak dapat menemukan URL unduhan.")
        exit(1)

# Panggil fungsi utama dengan URL dari environment variable
main_downloader(mediafire_page_url)

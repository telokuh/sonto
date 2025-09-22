import os
import re
from utils import (
    send_telegram_message,
    edit_telegram_message,
    download_with_yt_dlp,
    download_file_with_aria2c,
    download_file_with_megatools,
    get_download_url_from_pixeldrain_api,
    get_download_url_from_gofile
)

# Dapatkan URL halaman dari environment variable
mediafire_page_url = os.environ.get("MEDIAFIRE_PAGE_URL")

# Regex untuk mendeteksi URL
MEGA_URL_REGEX = r"(?:https?://)?(?:www\.)?mega\.nz/.+"
PIXELDRAIN_URL_REGEX = r"(?:https?://)?(?:www\.)?pixeldrain\.com/u/.+"
GOFILE_URL_REGEX = r"(?:https?://)?(?:www\.)?gofile\.io/.+"

if not mediafire_page_url:
    print("Error: MEDIAFIRE_PAGE_URL environment variable not set.")
    exit(1)

def main_downloader(url):
    formatted_url = f"`{url.replace('http://', '').replace('https://', '')}`"
    initial_message_id = send_telegram_message(f"🔍 **Mulai memproses URL:**\n{formatted_url}")
    downloaded_filename = None

    # --- Logika Berjenjang ---
    if re.match(MEGA_URL_REGEX, url):
        print("URL cocok dengan MEGA. Menggunakan megatools...")
        send_telegram_message("`yt-dlp` gagal memproses URL MEGA. Beralih ke `megatools`...")
        downloaded_filename = download_file_with_megatools(url)
    
    elif re.match(PIXELDRAIN_URL_REGEX, url):
        print("URL cocok dengan Pixeldrain. Menggunakan API...")
        download_url_pixeldrain = get_download_url_from_pixeldrain_api(url)
        if download_url_pixeldrain:
            downloaded_filename = download_file_with_aria2c(download_url_pixeldrain, message_id=initial_message_id)

    elif re.match(GOFILE_URL_REGEX, url):
        print("URL cocok dengan Gofile. Menggunakan Selenium...")
        downloaded_filename = get_download_url_from_gofile(url)
        

    else:
        # Coba yt-dlp sebagai opsi universal
        print("URL tidak cocok dengan pola khusus. Mencoba dengan yt-dlp...")
        yt_dlp_success = download_with_yt_dlp(url, message_id=initial_message_id)
        if yt_dlp_success:
            # Karena yt-dlp sudah mengunduh file, tidak perlu memanggil aria2c.
            # Anda perlu menambahkan logika untuk mendapatkan nama file dari yt-dlp jika dibutuhkan.
            # Untuk saat ini, kita akan mengasumsikan unduhan berhasil.
            downloaded_filename = "file_berhasil_diunduh_dengan_yt-dlp" # Placeholder
        else:
            # Fallback ke aria2c jika yt-dlp gagal
            print("yt-dlp gagal. Mencoba dengan aria2c sebagai cadangan...")
            downloaded_filename = download_file_with_aria2c(url, message_id=initial_message_id)
    
    if downloaded_filename:
        with open("downloaded_filename.txt", "w") as f:
            f.write(downloaded_filename)
        send_telegram_message(f"✅ **Selesai!**\nFile `{downloaded_filename}` berhasil diunduh dan sedang dibuatkan rilis di GitHub.")
    else:
        print("Tidak dapat menemukan URL unduhan. Proses dihentikan.")
        send_telegram_message("❌ **Proses gagal.**\nTidak dapat menemukan URL unduhan.")
        exit(1)

# Panggil fungsi utama dengan URL dari environment variable
main_downloader(mediafire_page_url)

# main.py
import os
import sys

# ✅ Import hanya Class DownloaderBot dari file utils yang baru
from utils import DownloaderBot

# Dapatkan URL dari environment variable
url_to_download = os.environ.get("MEDIAFIRE_PAGE_URL")

if __name__ == "__main__":
    if url_to_download:
        print(f"Memulai proses download untuk URL: {url_to_download}")
        try:
            # 1. Inisialisasi Class
            downloader = DownloaderBot(url_to_download)
            
            # 2. Jalankan Proses Utama
            downloader.run()
            
        except Exception as e:
            # Fatal error di luar logika download
            print(f"Error fatal saat eksekusi utama: {e}")
            sys.exit(1)
    else:
        print("Error: MEDIAFIRE_PAGE_URL environment variable not set.")
        sys.exit(1)

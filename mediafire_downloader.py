import os
import subprocess
import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import json
import re

# Ambil token bot dan chat ID dari environment variables
BOT_TOKEN = os.environ.get("BOT_TOKEN")
OWNER_ID = os.environ.get("OWNER_ID")

# Dapatkan URL halaman dari environment variable
mediafire_page_url = os.environ.get("MEDIAFIRE_PAGE_URL")
RCLONE_CONFIG_PATH = os.environ.get("RCLONE_CONFIG")

# Regex untuk mendeteksi URL
YOUTUBE_URL_REGEX = r"(?:https?://)?(?:www\.)?(?:youtube\.com|youtu\.be)/.+"
MEGA_URL_REGEX = r"(?:https?://)?(?:www\.)?mega\.nz/.+"

if not mediafire_page_url:
    print("Error: MEDIAFIRE_PAGE_URL environment variable not set.")
    exit(1)

def send_telegram_message(message_text):
    """Fungsi untuk mengirim pesan ke Telegram dan mengembalikan message_id."""
    if not BOT_TOKEN or not OWNER_ID:
        print("Peringatan: BOT_TOKEN atau OWNER_ID tidak diatur. Notifikasi Telegram dinonaktifkan.")
        return None
    
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": OWNER_ID,
        "text": message_text,
        "parse_mode": "Markdown"
    }
    try:
        response = requests.post(url, json=payload, timeout=10)
        return response.json().get('result', {}).get('message_id')
    except Exception as e:
        print(f"Gagal mengirim pesan Telegram: {e}")
        return None

def edit_telegram_message(message_id, message_text):
    """Fungsi untuk mengedit pesan yang sudah ada di Telegram."""
    if not BOT_TOKEN or not OWNER_ID or not message_id:
        print("Peringatan: Tidak bisa mengedit pesan. Notifikasi Telegram dinonaktifkan.")
        return
    
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/editMessageText"
    payload = {
        "chat_id": OWNER_ID,
        "message_id": message_id,
        "text": message_text,
        "parse_mode": "Markdown"
    }
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Gagal mengedit pesan Telegram: {e}")

def get_download_url_with_yt_dlp(url):
    print("Mencoba mendapatkan URL unduhan dengan yt-dlp...")
    send_telegram_message("⏳ **Mencari URL unduhan...**\n`yt-dlp` sedang mencoba memproses link.")
    
    command = ['yt-dlp', '--get-url', '--no-warnings', '--rm-cache-dir', url]
    
    cookies_file = "cookies.txt"
    if os.path.exists(cookies_file):
        command.extend(['--cookies', cookies_file])
    
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=True
        )
        download_url = result.stdout.strip()
        if download_url:
            print("yt-dlp berhasil menemukan URL unduhan.")
            return download_url
    except subprocess.CalledProcessError as e:
        print(f"yt-dlp gagal: {e.stderr.strip()}")
        send_telegram_message(f"❌ `yt-dlp` gagal memproses URL.\n\nDetail: {e.stderr.strip()[:200]}...")
    except FileNotFoundError:
        print("yt-dlp tidak ditemukan.")
    
    return None

def get_download_url_with_selenium(url):
    print("yt-dlp gagal. Menggunakan Selenium sebagai cadangan...")
    send_telegram_message("🔄 `yt-dlp` gagal. Menggunakan Selenium untuk menemukan URL.")
    try:
        service = Service(ChromeDriverManager().install())
        options = webdriver.ChromeOptions()
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')

        driver = webdriver.Chrome(service=service, options=options)
        driver.get(url)

        download_button_selector = "a[id*='downloadButton']"
        download_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, download_button_selector))
        )
        download_url = download_button.get_attribute("href")
        
        if download_url and download_url.startswith("http"):
            print("Selenium berhasil menemukan URL unduhan.")
            return download_url
        else:
            download_button.click()
            time.sleep(3)
            final_url = driver.current_url
            if final_url != url:
                print("Selenium berhasil menemukan URL redirect.")
                return final_url
            else:
                raise Exception("Gagal menemukan URL unduhan dengan Selenium.")
    except Exception as e:
        print(f"Terjadi kesalahan saat menggunakan Selenium: {e}")
        send_telegram_message(f"❌ Gagal mendapatkan URL unduhan.\n\nDetail: {str(e)[:150]}...")
        driver.save_screenshot("error_screenshot.png")
        print("Screenshot error_screenshot.png telah dibuat.")
        return None
    finally:
        driver.quit()

def download_file_with_rclone(url):
    print(f"Mengunduh file dari MEGA dengan rclone: {url}")
    send_telegram_message("⬇️ **Mulai mengunduh...**\n`rclone` sedang mengunduh file.")

    rclone_env = os.environ.copy()
    if RCLONE_CONFIG_PATH:
        rclone_env["RCLONE_CONFIG"] = RCLONE_CONFIG_PATH

    try:
        # Jalankan rclone copyurl dan tunggu sampai selesai
        result = subprocess.run(
            ['rclone', 'copyurl', url, '.'],
            capture_output=True,
            text=True,
            check=True,
            env=rclone_env
        )
        print(result.stdout)
        
        # rclone berhasil, sekarang cari file yang baru diunduh
        # Metode yang lebih andal: cari file yang baru dibuat di direktori saat ini
        time.sleep(2) # Beri waktu sejenak
        newly_downloaded_files = sorted([
            f for f in os.listdir('.') if os.path.isfile(f)
        ], key=os.path.getmtime, reverse=True)
        
        if newly_downloaded_files:
            filename = newly_downloaded_files[0]
            print(f"File berhasil diunduh sebagai: {filename}")
            return filename
        else:
            print("Gagal menemukan file yang baru diunduh.")
            return None
            
    except subprocess.CalledProcessError as e:
        print(f"rclone gagal: {e.stderr.strip()}")
        send_telegram_message(f"❌ **`rclone` gagal mengunduh file.**\n\nDetail: {e.stderr.strip()[:200]}...")
    except FileNotFoundError:
        print("rclone tidak ditemukan.")
    
    return None

def download_file(url):
    try:
        response = requests.get(url, stream=True)
        response.raise_for_status()
        
        filename = response.headers.get('Content-Disposition')
        if filename:
            filename = filename.split('filename=')[1].strip('"')
        else:
            filename = url.split('/')[-1]
        
        if len(filename.split('.')) < 2:
            filename = "downloaded_file" + os.path.splitext(url)[-1]

        initial_message = f"⬇️ **Mulai mengunduh...**\n`{filename}`\n\nProgres: `0%`"
        message_id = send_telegram_message(initial_message)

        total_size = int(response.headers.get('content-length', 0))
        downloaded_size = 0
        last_percent_notified = 0

        with open(filename, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
                downloaded_size += len(chunk)
                if total_size > 0:
                    current_percent = int(downloaded_size / total_size * 100)
                    if current_percent >= last_percent_notified + 10 or current_percent == 100:
                        last_percent_notified = current_percent
                        progress_message = f"⬇️ **Mulai mengunduh...**\n`{filename}`\n\nProgres: `{current_percent}%`"
                        edit_telegram_message(message_id, progress_message)
        
        print(f"File berhasil diunduh sebagai: {filename}")
        return filename
    except requests.exceptions.RequestException as e:
        print(f"Gagal mengunduh file: {e}")
        send_telegram_message(f"❌ **Gagal mengunduh file.**\n\nDetail: {str(e)[:150]}...")
        return None

# --- Logika Utama ---
formatted_url = f"`{mediafire_page_url.replace('http://', '').replace('https://', '')}`"
send_telegram_message(f"🔍 **Mulai memproses URL:**\n{formatted_url}")

is_mega_url = re.match(MEGA_URL_REGEX, mediafire_page_url)
downloaded_filename = None

# Coba yt-dlp terlebih dahulu
download_url = get_download_url_with_yt_dlp(mediafire_page_url)

if download_url:
    downloaded_filename = download_file(download_url)
elif is_mega_url:
    send_telegram_message("`yt-dlp` gagal memproses URL MEGA. Beralih ke `rclone`...")
    downloaded_filename = download_file_with_rclone(mediafire_page_url)
else:
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

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
import tempfile
import shutil
import glob
import math
from selenium.common.exceptions import TimeoutException

# Ambil token bot dan chat ID dari environment variables
BOT_TOKEN = os.environ.get("BOT_TOKEN")
OWNER_ID = os.environ.get("OWNER_ID")

def get_download_url_from_pixeldrain_api(url):
    """
    Mengambil URL unduhan langsung dari API Pixeldrain.
    """
    print("Memproses URL Pixeldrain menggunakan API...")
    try:
        file_id = url.split('/')[-1]
        download_url = f"https://pixeldrain.com/api/file/{file_id}?download"
        print(f"URL Unduhan Pixeldrain ditemukan: {download_url}")
        return download_url
    except Exception as e:
        print(f"Gagal mendapatkan URL unduhan Pixeldrain: {e}")
        return None


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

def human_readable_size(size_bytes):
    if size_bytes is None or size_bytes == 0:
        return "0B"
    size_name = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return f"{s} {size_name[i]}"

def human_readable_to_bytes(size_str):
    if not size_str:
        return 0
    size_str = size_str.upper().strip()
    match = re.match(r"(\d+\.?\d*)\s*(KB|MB|GB|TB)", size_str)
    if not match:
        return 0
    size_value = float(match.group(1))
    size_unit = match.group(2)
    unit_multipliers = {
        'KB': 1024, 'MB': 1024**2, 'GB': 1024**3, 'TB': 1024**4,
    }
    return int(size_value * unit_multipliers.get(size_unit, 1))

# ---
## Fungsi Unduhan Spesial (Dipertahankan)

def download_file_with_megatools(url):
    print(f"Mengunduh file dari MEGA dengan megatools: {url}")
    original_cwd = os.getcwd()
    temp_dir = tempfile.mkdtemp()
    
    initial_message_id = send_telegram_message("⬇️ **Mulai mengunduh...**\n`megatools` sedang mengunduh file.")

    try:
        os.chdir(temp_dir)
        process = subprocess.Popen(
            ['megatools', 'dl', url],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        
        last_percent_notified = 0
        progress_regex = re.compile(r'(\d+\.\d+)%\s+of\s+.*\((\d+\.\d+)\s*(\wB)\)')

        while True:
            line = process.stdout.readline()
            if not line: break
            
            match = progress_regex.search(line)
            if match:
                current_percent = math.floor(float(match.group(1)))
                current_size_str = match.group(2)
                current_unit = match.group(3)

                if current_percent >= last_percent_notified + 10 or current_percent == 100:
                    last_percent_notified = current_percent
                    progress_message = f"⬇️ **Mulai mengunduh...**\nUkuran file: `{current_size_str} {current_unit}`\n\nProgres: `{current_percent}%`"
                    edit_telegram_message(initial_message_id, progress_message)

        process.wait()
        if process.returncode != 0:
            error_output = process.stderr.read()
            raise subprocess.CalledProcessError(process.returncode, process.args, stderr=error_output)

        downloaded_files = os.listdir('.')
        if len(downloaded_files) == 1:
            filename = downloaded_files[0]
            return filename
        else:
            print(f"Gagal menemukan file yang baru diunduh. Jumlah file: {len(downloaded_files)}")
            return None
    except Exception as e:
        print(f"megatools gagal: {e}")
        send_telegram_message(f"❌ **`megatools` gagal mengunduh file.**\n\nDetail: {str(e)[:200]}...")
        return None
    finally:
        os.chdir(original_cwd)
        if 'filename' in locals() and os.path.exists(os.path.join(temp_dir, filename)):
            shutil.move(os.path.join(temp_dir, filename), os.path.join(original_cwd, filename))
        shutil.rmtree(temp_dir, ignore_errors=True)

# ---
## Fungsi Baru yang Ditingkatkan

def download_with_yt_dlp(url, message_id=None):
    print("Mencoba mengunduh file dengan yt-dlp...")
    initial_message_id = send_telegram_message("⏳ **Memulai unduhan dengan `yt-dlp`...**")
    
    command = [
        'yt-dlp', '--newline', '--progress',
        '--progress-template', '%(progress._percent_str)s',
        '--no-warnings', '--rm-cache-dir',
        '--output', '%(title)s.%(ext)s', url
    ]
    
    cookies_file = "cookies.txt"
    if os.path.exists(cookies_file):
        command.extend(['--cookies', cookies_file])

    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, text=True)
        last_percent = -1

        while True:
            line = process.stdout.readline()
            if not line: break
            
            if '%' in line:
                try:
                    current_percent = int(float(line.strip().replace('%', '')))
                    if current_percent > last_percent + 5 or current_percent == 100:
                        message = f"⬇️ **Mengunduh...**\n`{url}`\n\nProgres: `{current_percent}%`"
                        edit_telegram_message(initial_message_id, message)
                        last_percent = current_percent
                except ValueError: continue

        process.wait()
        if process.returncode != 0:
            raise Exception("yt-dlp gagal mengunduh file.")
            
        print("Unduhan yt-dlp selesai.")
        return True
    except Exception as e:
        print(f"yt-dlp gagal: {e}")
        send_telegram_message(f"❌ **`yt-dlp` gagal mengunduh.**\n\nDetail: {str(e)[:150]}...")
        return False

def download_file_with_aria2c(url, headers=None, filename=None, message_id=None):
    """
    Mengunduh file menggunakan aria2c dan mengembalikan nama file yang diunduh,
    dengan menyertakan header dari permintaan.
    """
    print(f"Mulai unduhan dengan aria2c: {url}")
    
    if not filename:
        try:
            with requests.get(url, stream=True, allow_redirects=True, timeout=10) as r:
                r.raise_for_status()
                if 'content-disposition' in r.headers:
                    match = re.search(r'filename="?([^";]+)"?', r.headers['content-disposition'])
                    if match:
                        filename = match.group(1)
                if not filename:
                    filename = url.split('/')[-1].split('?')[0]
                    if not filename:
                        filename = "unduhan_tanpa_nama"
        except Exception as e:
            print(f"Gagal mendapatkan nama file dari URL: {e}")
            send_telegram_message(f"❌ Gagal mendapatkan nama file. Mengunduh tanpa nama.\n\nURL: {url}")
            filename = "unduhan_tanpa_nama"

    print(f"Nama file yang akan diunduh: {filename}")
    
    command = [
        'aria2c',
        '--allow-overwrite', '--file-allocation=none',
        '--console-log-level=warn', '--summary-interval=0',
        '-x', '16', '-s', '16', '-c',
    ]

    if headers:
        for key, value in headers.items():
            command.extend(['--header', f'{key}: {value}'])
    
    command.extend(['-o', filename, url])
    
    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        last_percent_notified = -1
        
        while True:
            line = process.stdout.readline()
            if not line: break
            
            progress_match = re.search(r'\[.+?\]\s+(\d+\.\d+)%\s+DL:\s+([\d\.]+[KMGTP]B)\s+', line)
            
            if progress_match:
                percent = int(float(progress_match.group(1)))
                downloaded_size = progress_match.group(2)
                
                if percent >= last_percent_notified + 10 or percent == 100:
                    message = f"⬇️ **Mengunduh...**\n`{filename}`\nUkuran: `{downloaded_size}`\nProgres: `{percent}%`"
                    edit_telegram_message(message_id, message)
                    last_percent_notified = percent
        
        process.wait()
        if process.returncode != 0:
            raise subprocess.CalledProcessError(process.returncode, command, output=process.stdout.read())

        return filename
    except Exception as e:
        print(f"aria2c gagal: {e}")
        send_telegram_message(f"❌ **aria2c gagal.**\n\nDetail: {str(e)[:150]}...")
        return None


def get_download_url_from_gofile(url):
    """
    Mengunduh file GoFile secara langsung dengan mengonfigurasi preferensi browser
    dan menunggu secara dinamis hingga unduhan selesai.
    """
    print("Memulai unduhan GoFile. Menunggu unduhan selesai secara dinamis...")

    download_dir = os.path.join(os.getcwd(), "downloads")
    if not os.path.exists(download_dir):
        os.makedirs(download_dir)

    chrome_prefs = {
        "download.default_directory": download_dir,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True,
    }
    
    options = webdriver.ChromeOptions()
    options.add_experimental_option("prefs", chrome_prefs)
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')

    driver = None
    downloaded_filename = None
    
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        driver.get(url)

        download_button_selector = "#filemanager_itemslist > div.border-b.border-gray-600 > div > div:nth-child(2) > div > button"
        download_button = WebDriverWait(driver, 20).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, download_button_selector))
        )
        download_button.click()

        start_time = time.time()
        timeout = 40
        
        while time.time() - start_time < timeout:
            if not any(fname.endswith(('.crdownload', '.tmp')) for fname in os.listdir(download_dir)):
                print("Unduhan selesai!")
                break
            time.sleep(1)
        else:
            print("Unduhan gagal atau melebihi batas waktu.")
            return None

        list_of_files = [f for f in os.listdir(download_dir) if not f.endswith(('.crdownload', '.tmp'))]
        if list_of_files:
            latest_file = max([os.path.join(download_dir, f) for f in list_of_files], key=os.path.getctime)
            downloaded_filename = os.path.basename(latest_file)
            print(f"File berhasil diunduh: {downloaded_filename}")
        
    except Exception as e:
        print(f"Gagal mengunduh file dengan Selenium: {e}")
    finally:
        if driver:
            driver.quit()
        return downloaded_filename

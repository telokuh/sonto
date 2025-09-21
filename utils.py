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


# Ambil token bot dan chat ID dari environment variables
BOT_TOKEN = os.environ.get("BOT_TOKEN")
OWNER_ID = os.environ.get("OWNER_ID")

# ... (kode impor dan fungsi lain) ...
from selenium.common.exceptions import TimeoutException

def download_file_with_selenium_gofile(url):
    print("Mencoba mengunduh file Gofile dengan Selenium...")
    send_telegram_message("🔄 Mengunduh file GoFile langsung dengan Selenium.")
    driver = None
    download_dir = os.path.join(os.getcwd(), 'downloads')
    
    if not os.path.exists(download_dir):
        os.makedirs(download_dir)

    try:
        service = Service(ChromeDriverManager().install())
        options = webdriver.ChromeOptions()
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--incognito')
        
        prefs = {
            "download.default_directory": download_dir,
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "safebrowsing.enabled": True
        }
        options.add_experimental_option("prefs", prefs)
        
        driver = webdriver.Chrome(service=service, options=options)
        driver.get(url)

        download_link_selector = "#filemanager_itemslist > div.border-b.border-gray-600 > div > div.flex.items-center.overflow-auto > div.truncate > a"
        download_link = WebDriverWait(driver, 20).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, download_link_selector))
        )
        
        filename = download_link.text.strip()
        print(f"Nama file yang diharapkan: {filename}")
        
        # --- Bagian yang Diperbarui: Tambahkan waktu tunggu untuk selektor ukuran ---
        file_size_selector = "#filemanager_itemslist > div.border-b.border-gray-600 > div > div.flex.items-center.overflow-auto > div.truncate > div > div:nth-child(2) > span"
        
        try:
            file_size_element = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, file_size_selector))
            )
            size_text = file_size_element.text.strip()
            print(size_text)
            total_size = human_readable_to_bytes(size_text)
        except TimeoutException:
            print("Peringatan: Elemen ukuran file tidak ditemukan. Progres unduhan tidak akan ditampilkan.")
            total_size = 0 # Tetapkan 0 jika elemen tidak ditemukan
        
        total_size_human = human_readable_size(total_size)
        print(f"Ukuran file: {total_size_human} ({total_size} bytes)")
        
        initial_message = f"⬇️ **Mulai mengunduh...**\n`{filename}`\nUkuran file: `{total_size_human}`\n\nProgres: `0%`"
        message_id = send_telegram_message(initial_message)
        
        download_link.click()
        
        file_path = os.path.join(download_dir, filename)
        
        timeout = 60
        start_time = time.time()
        last_percent_notified = 0
        
        while not os.path.exists(file_path) or (total_size > 0 and os.path.getsize(file_path) < total_size):
            if time.time() - start_time > timeout:
                raise TimeoutError("Waktu unduhan habis.")
            
            if os.path.exists(file_path) and total_size > 0:
                downloaded_size = os.path.getsize(file_path)
                current_percent = int((downloaded_size / total_size) * 100)
                
                if current_percent >= last_percent_notified + 10 or current_percent == 100:
                    last_percent_notified = current_percent
                    progress_message = f"⬇️ **Mulai mengunduh...**\n`{filename}`\nUkuran file: `{total_size_human}`\n\nProgres: `{current_percent}%`"
                    edit_telegram_message(message_id, progress_message)
            
            time.sleep(2)
        
        final_path = os.path.join(os.getcwd(), filename)
        shutil.move(file_path, final_path)
        
        print(f"File berhasil diunduh sebagai: {final_path}")
        return filename
            
    except Exception as e:
        print(f"Terjadi kesalahan saat mengunduh Gofile dengan Selenium: {e}")
        send_telegram_message(f"❌ Gagal mengunduh file GoFile.\n\nDetail: {str(e)[:150]}...")
        if driver:
            driver.save_screenshot("gofile_error_screenshot.png")
            print("Screenshot gofile_error_screenshot.png telah dibuat.")
        return None
    finally:
        if driver:
            driver.quit()
        if os.path.exists(download_dir):
            shutil.rmtree(download_dir, ignore_errors=True)

# ... (lanjutan kode di utils.py) ...

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

def get_download_url_with_yt_dlp(url, message_id=None):
    print("Mencoba mengunduh file dengan yt-dlp...")
    send_telegram_message("⏳ **Memulai unduhan dengan `yt-dlp`...**")

    # Command untuk mengunduh dan menampilkan progress ke stdout
    command = [
        'yt-dlp',
        '--newline', # Pastikan setiap baris output adalah baris baru
        '--progress',
        '--progress-template', '%(progress._percent_str)s',
        '--no-warnings',
        '--rm-cache-dir',
        '--output', '%(title)s.%(ext)s',
        url
    ]

    try:
        # Panggil yt-dlp dan tangkap outputnya
        process = subprocess.Popen(command, stdout=subprocess.PIPE, text=True)
        last_percent = -1
        file_title = None

        while True:
            line = process.stdout.readline()
            if not line:
                break
            
            # Cek apakah baris output adalah persentase
            if '%' in line:
                try:
                    current_percent = int(float(line.strip().replace('%', '')))
                    if current_percent > last_percent + 5 or current_percent == 100:
                        message = f"⬇️ **Mengunduh...**\n`{url}`\n\nProgres: `{current_percent}%`"
                        edit_telegram_message(message_id, message)
                        last_percent = current_percent
                except ValueError:
                    continue

        process.wait()
        
        if process.returncode != 0:
            raise Exception("yt-dlp gagal mengunduh file.")
            
        print("Unduhan yt-dlp selesai.")
        return True # Unduhan berhasil

    except Exception as e:
        print(f"yt-dlp gagal: {e}")
        send_telegram_message(f"❌ **`yt-dlp` gagal mengunduh.**\n\nDetail: {str(e)[:150]}...")
        return False # Unduhan gagal
def get_download_url_with_selenium(url):
    print("yt-dlp gagal. Menggunakan Selenium sebagai cadangan...")
    send_telegram_message("🔄 `yt-dlp` gagal. Menggunakan Selenium untuk menemukan URL.")
    driver = None
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
        download_button.click()
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
        if driver:
            driver.save_screenshot("error_screenshot.png")
            print("Screenshot error_screenshot.png telah dibuat.")
        return None
    finally:
        if driver:
            driver.quit()


def download_file_with_megatools(url):
    print(f"Mengunduh file dari MEGA dengan megatools: {url}")
    original_cwd = os.getcwd()
    temp_dir = tempfile.mkdtemp()
    
    initial_message_id = send_telegram_message("⬇️ **Mulai mengunduh...**\n`megatools` sedang mengunduh file.")

    try:
        os.chdir(temp_dir)
        process = subprocess.Popen(
            ['megatools', 'dl', url],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        total_size = 0
        last_percent_notified = 0
        progress_regex = re.compile(r'(\d+\.\d+)%\s+of\s+.*\((\d+\.\d+)\s*(\wB)\)')

        while True:
            line = process.stdout.readline()
            if not line:
                break
            
            match = progress_regex.search(line)
            if match:
                current_percent = math.floor(float(match.group(1)))
                current_size_str = match.group(2)
                current_unit = match.group(3)

                if total_size == 0:
                    total_size = f"{current_size_str} {current_unit}"
                    
                if current_percent >= last_percent_notified + 10 or current_percent == 100:
                    last_percent_notified = current_percent
                    progress_message = f"⬇️ **Mulai mengunduh...**\nUkuran file: `{total_size}`\n\nProgres: `{current_percent}%`"
                    edit_telegram_message(initial_message_id, progress_message)

        process.wait()
        if process.returncode != 0:
            error_output = process.stderr.read()
            raise subprocess.CalledProcessError(process.returncode, process.args, stderr=error_output)

        downloaded_files = os.listdir('.')
        if len(downloaded_files) == 1:
            filename = downloaded_files[0]
            print(f"File berhasil diunduh sebagai: {filename}")
            return filename
        else:
            print(f"Gagal menemukan file yang baru diunduh. Jumlah file: {len(downloaded_files)}")
            print("File di direktori:", downloaded_files)
            return None
            
    except subprocess.CalledProcessError as e:
        print(f"megatools gagal: {e.stderr.strip()}")
        send_telegram_message(f"❌ **`megatools` gagal mengunduh file.**\n\nDetail: {e.stderr.strip()[:200]}...")
    except FileNotFoundError:
        print("megatools tidak ditemukan.")
    except Exception as e:
        print(f"Terjadi kesalahan: {e}")
    finally:
        os.chdir(original_cwd)
        if 'filename' in locals() and os.path.exists(os.path.join(temp_dir, filename)):
            shutil.move(os.path.join(temp_dir, filename), os.path.join(original_cwd, filename))
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    return None

def get_download_url_from_pixeldrain_api(url):
    print("Memproses URL Pixeldrain menggunakan API...")
    file_id = url.split('/')[-1]
    download_url = f"https://pixeldrain.com/api/file/{file_id}?download"
    return download_url

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
    
    # Regex yang lebih baik untuk menangani format seperti '1.9 GB'
    match = re.match(r"(\d+\.?\d*)\s*(KB|MB|GB|TB)", size_str)
    
    if not match:
        return 0
    
    size_value = float(match.group(1))
    size_unit = match.group(2)
    
    unit_multipliers = {
        'KB': 1024,
        'MB': 1024**2,
        'GB': 1024**3,
        'TB': 1024**4,
    }
    
    return int(size_value * unit_multipliers.get(size_unit, 1))


def download_file_with_aria2c(url, filename=None, message_id=None):
    """
    Mengunduh file menggunakan aria2c dan mengembalikan nama file yang diunduh.
    """
    print(f"Mulai unduhan dengan aria2c: {url}")
    
    # Mendapatkan nama file jika belum disediakan
    if not filename:
        try:
            # Menggunakan requests untuk mendapatkan nama file dari header Content-Disposition
            with requests.get(url, stream=True, allow_redirects=True, timeout=10) as r:
                r.raise_for_status()
                if 'content-disposition' in r.headers:
                    match = re.search(r'filename="?([^";]+)"?', r.headers['content-disposition'])
                    if match:
                        filename = match.group(1)
                if not filename:
                    # Fallback: gunakan nama dari URL jika header tidak ada
                    filename = url.split('/')[-1].split('?')[0]
                    if not filename:
                        filename = "unduhan_tanpa_nama"
        except Exception as e:
            print(f"Gagal mendapatkan nama file dari URL: {e}")
            send_telegram_message(f"❌ Gagal mendapatkan nama file. Mengunduh tanpa nama.\n\nURL: {url}")
            filename = "unduhan_tanpa_nama"

    print(f"Nama file yang akan diunduh: {filename}")
    
    # Perintah aria2c yang ditingkatkan
    command = [
        'aria2c',
        '--allow-overwrite',
        '--file-allocation=none',
        '--console-log-level=warn',
        '--summary-interval=0',
        '-x', '16', '-s', '16', '-c',
        '-o', filename, # Menyimpan file dengan nama yang ditentukan
        url
    ]
    
    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        last_percent_notified = -1
        
        while True:
            line = process.stdout.readline()
            if not line:
                break
            
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

        return filename # Unduhan berhasil, kembalikan nama file
    
    except subprocess.CalledProcessError as e:
        print(f"aria2c gagal: {e}")
        send_telegram_message(f"❌ **aria2c gagal.**\n\nDetail: {str(e)[:150]}...")
        return None
    except Exception as e:
        print(f"Terjadi kesalahan: {e}")
        send_telegram_message(f"❌ **Terjadi kesalahan tak terduga.**\n\nDetail: {str(e)[:150]}...")
        return None

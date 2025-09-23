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
from urllib.parse import urlparse, urlunparse, urlencode, parse_qs
# Ambil token bot dan chat ID dari environment variables
BOT_TOKEN = os.environ.get("BOT_TOKEN")
OWNER_ID = os.environ.get("OWNER_ID")



def set_url(url, param_name, param_value):
    """Mengganti nilai parameter URL tertentu."""
    parsed_url = urlparse(url)
    query_params = parse_qs(parsed_url.query)
    
    query_params[param_name] = [param_value]
    
    new_query = urlencode(query_params, doseq=True)
    
    new_url = urlunparse((
        parsed_url.scheme,
        parsed_url.netloc,
        parsed_url.path,
        parsed_url.params,
        new_query,
        parsed_url.fragment
    ))
    
    return new_url

def source_url(download_url):
    """
    Mengubah URL unduhan SourceForge menjadi URL pemilihan cermin.

    Args:
        download_url (str): URL unduhan SourceForge.

    Returns:
        str: URL pemilihan cermin yang baru.
    """
    try:
        # Menguraikan URL yang diberikan
        parsed_url = urlparse(download_url)
        path_parts = parsed_url.path.split('/')
        
        # Ekstrak nama proyek dan nama file dari path
        # Path: /projects/PROYEK/files/FILE/download
        project_name = path_parts[2]
        file_path = '/'.join(path_parts[4:-1])
        
        # Mengatur parameter query untuk URL baru
        query_params = {
            'projectname': project_name,
            'filename': file_path
        }
        
        # Membuat path baru dan URL baru
        new_path = "/settings/mirror_choices"
        new_url_parts = (
            parsed_url.scheme,         # 'https'
            parsed_url.netloc,         # 'sourceforge.net'
            new_path,                  # '/settings/mirror_choices'
            '',                        # params
            urlencode(query_params),   # query
            ''                         # fragment
        )
        
        new_url = urlunparse(new_url_parts)
        return new_url
        
    except IndexError:
        print("Error: URL tidak dalam format SourceForge yang diharapkan.")
        return None
    except Exception as e:
        print(f"Terjadi kesalahan: {e}")
        return None

def get_download_url_from_pixeldrain_api(url):
    """
    Mengambil URL unduhan langsung dari API Pixeldrain.
    """
    print("Memproses URL Pixeldrain menggunakan API...")
    try:
        file_id = url.split('/')[-1]
        download_url = f"https://pixeldrain.com/api/file/{file_id}?download"
        if "sourceforge" in url:
            download_url = url
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


def download_file_with_aria2c(urls):

    command = [
        'aria2c', '--allow-overwrite', '--file-allocation=none',
        '--console-log-level=warn', '--summary-interval=0',
        '-x', '16', '-s', '16', '-c',
        '--async-dns=false', '--log-level=warn', '--continue', '--input-file', '-'
    ]

    process = None
    try:
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        
        for url in urls:
            process.stdin.write(url + '\n')
        process.stdin.close()
        
        start_time = time.time()
        timeout = 300 # Batas waktu total dalam detik

        while time.time() - start_time < timeout:
            finished_files = [f for f in os.listdir('.') if not f.endswith(('.crdownload', '.tmp'))]
            if finished_files:
                print(f"File {finished_files[0]} selesai. Menghentikan aria2c...")
                process.terminate()
                time.sleep(1)
                if process.poll() is None:
                    process.kill()
                
                # Mengembalikan nama file yang pertama selesai
                return finished_files[0]

            time.sleep(2)

        print("Waktu habis. Menghentikan aria2c.")
        if process and process.poll() is None:
            process.terminate()
            time.sleep(1)
            process.kill()

    except Exception as e:
        print(f"Terjadi kesalahan: {e}")
        if process and process.poll() is None:
            process.terminate()
            time.sleep(1)
            process.kill()

    return None

def downloader(url):
    """
    Mengunduh file GoFile secara langsung dengan mengonfigurasi preferensi browser
    dan menunggu secara dinamis hingga unduhan selesai, dengan notifikasi Telegram.
    """
    print("Memulai unduhan GoFile. Menunggu unduhan selesai secara dinamis...")

    # Kirim pesan awal ke Telegram
    initial_message_id = send_telegram_message("⬇️ 9%")

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
    options.add_experimental_option("mobileEmulation", {"deviceName": "Nexus 5"})
    
    driver = None
    downloaded_filename = None
    
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        driver.get(url)
        
        

        if "gofile" in url:
            download_button_selector = "#filemanager_itemslist > div.border-b.border-gray-600 > div > div:nth-child(2) > div > button"
        elif "mediafire" in url:
            download_button_selector = "#downloadButton"
        elif "sourceforge" in url:
            download_button_selector = "#remaining-buttons > div.large-12 > a.button.green"
           
            driver.get(source_url(url))
            list_items = driver.find_elements(By.CSS_SELECTOR, "ul#mirrorList > li")
            
            li_id = []
            for item in list_items:
                item_id = item.get_attribute("id")
                li_id.append(item_id)
                #send_telegram_message(item_id)
            

            send_telegram_message(f"{source_url(url)} {li_id}")
            driver.get(url)
            download_button = WebDriverWait(driver, 20).until(
                  EC.element_to_be_clickable((By.CSS_SELECTOR, download_button_selector))
            )
            ahref = download_button.get_attribute('href')
            download_url = []
            for item in li_id:
                download_url.append(set_url(ahref, 'use_mirror', item))
                print( set_url(ahref, 'use_mirror', item) )
            download_file_with_aria2c(download_url)
            send_telegram_message(download_url)

        
        else:
            download_button = WebDriverWait(driver, 20).until(
              EC.element_to_be_clickable((By.CSS_SELECTOR, download_button_selector))
            )
            download_button.click()

        

        start_time = time.time()
        timeout = 300
        
        last_check_time = time.time()
        counter = 10
        while time.time() - start_time < timeout:
            is_downloading = any(fname.endswith(('.crdownload', '.tmp')) or fname.startswith('.com.google.Chrome.') for fname in os.listdir(download_dir))
            
            # Perbarui pesan Telegram setiap 30 detik untuk menunjukkan unduhan sedang berjalan
            if is_downloading and time.time() - last_check_time > 3:
                
                edit_telegram_message(initial_message_id, f"⬇️ {counter}%")
                last_check_time = time.time()
                counter += 10
            if not is_downloading:
                print("Unduhan selesai!")
                break
            time.sleep(2)
        else:
            edit_telegram_message(initial_message_id, "❌ **GoFile: Unduhan gagal atau melebihi batas waktu!**")
            print("Unduhan gagal atau melebihi batas waktu.")
            return None

        list_of_files = [f for f in os.listdir(download_dir) if not f.endswith(('.crdownload', '.tmp'))]
        if list_of_files:
            latest_file = max([os.path.join(download_dir, f) for f in list_of_files], key=os.path.getctime)
            downloaded_filename = os.path.basename(latest_file)
            print(f"File berhasil diunduh: {downloaded_filename}")
            edit_telegram_message(initial_message_id, f"✅ **GoFile: Unduhan selesai!**\nFile: `{downloaded_filename}`")
        else:
            edit_telegram_message(initial_message_id, "❌ **GoFile: Gagal menemukan file yang diunduh.**")
            return None
        
    except Exception as e:
        print(f"Gagal mengunduh file dengan Selenium: {e}")
        edit_telegram_message(initial_message_id, f"❌ **GoFile: Terjadi kesalahan saat mengunduh.**\nDetail: {str(e)[:150]}...")
    finally:
        if driver:
            driver.quit()
        return downloaded_filename

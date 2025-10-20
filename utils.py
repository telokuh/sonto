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

# =========================================================
# FUNGSI BANTUAN TELEGRAM
# =========================================================


def extract_extension_from_error(error_output):
    """Mengekstrak ekstensi yang tidak aman dari output error yt-dlp."""
    # Pola untuk mencari: "The extracted extension ('ext') is unusual..."
    match = re.search(r"The extracted extension \('(.+?)'\) is unusual", error_output)
    if match:
        return match.group(1) # Mengembalikan 'zip', 'exe', dll.
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

# =========================================================
# FUNGSI BANTUAN UMUM
# =========================================================

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
    """Mengubah URL unduhan SourceForge menjadi URL pemilihan cermin."""
    try:
        parsed_url = urlparse(download_url)
        path_parts = parsed_url.path.split('/')
        project_name = path_parts[2]
        file_path = '/'.join(path_parts[4:-1])
        
        query_params = {
            'projectname': project_name,
            'filename': file_path
        }
        
        new_path = "/settings/mirror_choices"
        new_url_parts = (
            parsed_url.scheme, 
            parsed_url.netloc, 
            new_path, 
            '', 
            urlencode(query_params),
            '' 
        )
        
        new_url = urlunparse(new_url_parts)
        return new_url
        
    except IndexError:
        print("Error: URL tidak dalam format SourceForge yang diharapkan.")
        return None
    except Exception as e:
        print(f"Terjadi kesalahan: {e}")
        return None

def human_readable_size(size_bytes):
    if size_bytes is None or size_bytes == 0:
        return "0B"
    size_name = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return f"{s} {size_name[i]}"

def get_total_file_size_safe(url):
    """Mendapatkan ukuran file total dari URL dengan aman."""
    # Opsi 1: Menggunakan permintaan HEAD (lebih cepat dan lebih disukai)
    try:
        response = requests.head(url, allow_redirects=True, timeout=10)
        response.raise_for_status()
        content_length = response.headers.get('Content-Length')
        if content_length:
            return int(content_length)
    except requests.exceptions.RequestException as e:
        print(f"Peringatan: Gagal mendapatkan header Content-Length: {e}")

    # Opsi 2: Menggunakan streaming (jika opsi 1 gagal)
    total_size = 0
    chunk_size = 500 * 1024 * 1024
    try:
        with requests.get(url, stream=True, timeout=30) as r:
            r.raise_for_status()
            for chunk in r.iter_content(chunk_size=chunk_size):
                total_size += len(chunk)
            return total_size
    except requests.exceptions.RequestException as e:
        print(f"❌ Gagal mendapatkan ukuran file melalui streaming: {e}")
    
    return None

def download_file_with_aria2c(urls, output_filename):
    """Mengunduh file menggunakan aria2c."""
    print(f"Memulai unduhan {output_filename} dengan aria2c.")

    total_size = None
    command = [
        'aria2c', '--allow-overwrite', '--file-allocation=none',
        '--console-log-level=warn', '--summary-interval=0',
        '-x', '16', '-s', '16', '-c',
        '--async-dns=false', '--log-level=warn', '--continue',
        '--input-file', '-',
        '-o', output_filename
    ]

    process = None
    aria2_temp_file = output_filename + '.aria2'

    try:
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        
        for url in urls:
            total_size = get_total_file_size_safe(url)
            if total_size is not None:
                process.stdin.write(url + '\n')
                break

            
        process.stdin.close()
        
        start_time = time.time()
        timeout = 300
        
        while time.time() - start_time < timeout:
            if os.path.exists(output_filename):
                current_size = os.path.getsize(output_filename)
                
                # Kondisi selesai: file sudah ada DAN ukurannya sama atau file .aria2 hilang
                if (total_size is not None and current_size >= total_size) or not os.path.exists(aria2_temp_file):
                    print(f"File {output_filename} selesai. Menghentikan aria2c...")
                    process.terminate()
                    time.sleep(3)
                    if process.poll() is None:
                        process.kill()
                    return output_filename
            
            if process.poll() is not None:
                if os.path.exists(output_filename) and os.path.getsize(output_filename) > 0:
                    return output_filename
                
                print("Aria2c berhenti sebelum file selesai diunduh. Mungkin terjadi kesalahan.")
                return None
            
            time.sleep(3)

        print("Waktu habis. Menghentikan aria2c.")
        if process and process.poll() is None:
            process.terminate()
            time.sleep(1)
            process.kill()

    except Exception as e:
        print(f"Terjadi kesalahan saat menjalankan aria2c: {e}")
        if process and process.poll() is None:
            process.terminate()
            time.sleep(1)
            process.kill()

    return None

# =========================================================
# FUNGSI DOWNLOADER UTAMA (dengan Notifikasi UPLOADING)
# =========================================================

def pixeldrain(url):
    """Mengunduh dari Pixeldrain menggunakan requests.head() dan aria2c."""
    print(f"Menganalisis URL Pixeldrain: {url}")
    initial_message_id = send_telegram_message("⏳ **Memulai unduhan dari Pixeldrain...**\nMemperoleh detail file...")
    
    try:
        file_id_match = re.search(r'pixeldrain\.com/(u|l|f)/([a-zA-Z0-9]+)', url)
        if not file_id_match:
            raise ValueError("URL Pixeldrain tidak valid.")
            
        file_id = file_id_match.group(2)
        download_url = f"https://pixeldrain.com/api/file/{file_id}?download"
        
        head_resp = requests.head(download_url, allow_redirects=True, timeout=10)
        head_resp.raise_for_status()

        filename = "pixeldrain_download"
        content_disposition = head_resp.headers.get('Content-Disposition')
        if content_disposition:
            match = re.search(r'filename\*?=(?:UTF-8\'\'|")(.+?)(?:"|;|$)', content_disposition)
            if match:
                filename = match.group(1).strip('"')
            else:
                filename = os.path.basename(urlparse(head_resp.url).path)
                
        size_bytes = head_resp.headers.get('Content-Length')
        readable_size = human_readable_size(int(size_bytes)) if size_bytes else "Ukuran tidak diketahui"
        
        edit_telegram_message(
            initial_message_id, 
            f"⬇️ **Memulai unduhan dengan `aria2c`...**\nFile: `{filename}`\nUkuran: `{readable_size}`"
        )

        downloaded_filename = download_file_with_aria2c([download_url], filename)

        if downloaded_filename:
            edit_telegram_message(initial_message_id, f"✅ **Pixeldrain: Unduhan selesai!**\nFile: `{downloaded_filename}`\n\n**➡️ Mulai UPLOADING...**")
            # --- SIMPAN NAMA FILE UNTUK SKRIP UPLOADER ---
            with open("downloaded_filename.txt", "w") as f:
                f.write(downloaded_filename)
            return downloaded_filename
        else:
            raise Exception("Aria2c gagal mengunduh file Pixeldrain.")

    except Exception as e:
        print(f"Gagal mengunduh Pixeldrain: {e}")
        edit_telegram_message(initial_message_id, f"❌ **Pixeldrain: Unduhan gagal!**\nDetail: {str(e)[:150]}...")
        return None

def download_file_with_megatools(url):
    """Mengunduh file dari MEGA dengan megatools."""
    print(f"Mengunduh file dari MEGA dengan megatools: {url}")
    original_cwd = os.getcwd()
    temp_dir = tempfile.mkdtemp()
    filename = None
    
    initial_message_id = send_telegram_message("⬇️ **Mulai mengunduh...**\n`megatools` sedang mengunduh file.")

    try:
        os.chdir(temp_dir)
        process = subprocess.Popen(
            ['megatools', 'dl', url],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        
        last_percent_notified = 0
        progress_regex = re.compile(r'(\d+\.\d+)%\s+of\s+.*\((\d+\.\d+)\s*(\wB)\)')

        # ... (Logika progres tetap sama) ...
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
            edit_telegram_message(initial_message_id, f"✅ **MEGA: Unduhan selesai!**\nFile: `{filename}`\n\n**➡️ Mulai UPLOADING...**")
            # --- SIMPAN NAMA FILE UNTUK SKRIP UPLOADER ---
            with open("downloaded_filename.txt", "w") as f:
                f.write(filename)
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
        if filename and os.path.exists(os.path.join(temp_dir, filename)):
            shutil.move(os.path.join(temp_dir, filename), os.path.join(original_cwd, filename))
        shutil.rmtree(temp_dir, ignore_errors=True)

def download_with_yt_dlp(url):
    """
    Mengunduh file dari Google Drive.
    
    Tahap 1: Ekstrak URL pengunduhan sebenarnya menggunakan yt-dlp.
    Tahap 2: Unduh file menggunakan aria2c secara langsung.
    """
    print(f"Memproses URL Google Drive: {url}")
    # Asumsi fungsi send_telegram_message ada
    initial_message_id = send_telegram_message("⏳ **Memulai unduhan (Google Drive Bypass)...**\nMemeriksa URL...")
    
    final_filename = None

    # --- TAHAP 1: EKSTRAKSI URL PENGUNDUHAN (menggunakan yt-dlp) ---
    edit_telegram_message(initial_message_id, "🔍 **Mengekstrak URL Pengunduhan Asli...**")
    
    # Opsi untuk HANYA mencetak URL dan judul
    extract_command = [
        'yt-dlp', 
        '--no-warnings', 
        '--get-url', # Mencetak URL pengunduhan asli
        '--print', 'title', # Mencetak judul/nama file yang disarankan
        url
    ]
    
    try:
        process = subprocess.run(
            extract_command,
            capture_output=True,
            text=True,
            check=True # Menimbulkan error jika return code bukan 0
        )
        
        output_lines = process.stdout.splitlines()
        
        # Asumsi: baris terakhir adalah URL, baris sebelumnya adalah judul
        if len(output_lines) < 2:
            raise Exception("yt-dlp gagal mendapatkan URL dan Judul.")
            
        direct_url = output_lines[-1].strip()
        suggested_title = output_lines[-2].strip()
        
        # Buat nama file aman dengan ekstensi default (misalnya .zip)
        # Kita tambahkan ekstensi '.zip' secara paksa karena yt-dlp gagal melakukannya
        if '.' not in suggested_title:
             suggested_filename = f"{suggested_title}.zip"
        else:
             suggested_filename = suggested_title
             
        final_filename = suggested_filename

    except Exception as e:
        error_message = str(e)
        print(f"Gagal mengekstrak URL: {error_message}")
        send_telegram_message(f"❌ **Gagal mengekstrak URL dari Google Drive.**\n\nDetail: {error_message[:150]}...")
        return None

    # --- TAHAP 2: PENGUNDUHAN LANGSUNG (menggunakan aria2c) ---
    
    edit_telegram_message(initial_message_id, f"⬇️ **Memulai Unduhan Langsung dengan aria2c...**\nFile: `{suggested_filename}`")
    
    aria2c_command = [
        'aria2c',
        '-x16', '-s16', '-k1M', # Argumen kecepatan aria2c
        '--allow-overwrite=true',
        '--out', suggested_filename, # Nama file yang diambil dari yt-dlp
        direct_url # URL langsung yang diekstrak
    ]

    try:
        # Panggil aria2c secara langsung
        subprocess.run(
            aria2c_command,
            check=True, # Menimbulkan error jika gagal
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT
        )
        
        # Jika berhasil
        print(f"Unduhan aria2c selesai. File: {final_filename}")
        edit_telegram_message(initial_message_id, f"✅ **Unduhan selesai!**\nFile: `{final_filename}`\n\n**➡️ Mulai UPLOADING...**")
        
        with open("downloaded_filename.txt", "w") as f:
            f.write(final_filename)
        return final_filename
        
    except Exception as e:
        error_message = str(e)
        print(f"Pengunduhan aria2c gagal: {error_message}")
        send_telegram_message(f"❌ **`aria2c` gagal mengunduh.**\n\nDetail: Cek log aria2c. {error_message[:150]}...")
        return None

# Ganti panggilan fungsi di kode utama Anda menjadi:
# download_file_direct(url)

def downloader(url):
    """Mengunduh file GoFile, Mediafire, dan SourceForge menggunakan Selenium."""
    print("Memulai unduhan. Menunggu unduhan selesai secara dinamis...")

    initial_message_id = None
    temp_download_dir = tempfile.mkdtemp()
    
    # ... (Setup Selenium options) ...
    chrome_prefs = {
        "download.default_directory": temp_download_dir, 
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
        
        # --- Logika SourceForge (Aria2c) ---
        if "sourceforge" in url:
            print("Mengunduh dari SourceForge...")
            initial_message_id = send_telegram_message("⏳ **Memulai unduhan dari SourceForge...**")
            
            # ... (Logika mirror SourceForge) ...
            mirror_url = source_url(url)
            driver.get(mirror_url)
            
            list_items = WebDriverWait(driver, 10).until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, "ul#mirrorList > li"))
            )
            
            li_id = [item.get_attribute("id") for item in list_items]
            
            driver.get(url)
            download_button = WebDriverWait(driver, 20).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "#remaining-buttons > div.large-12 > a.button.green"))
            )
            
            aname = WebDriverWait(driver, 10).until(
                EC.visibility_of_element_located((By.CSS_SELECTOR, "#downloading > div.content > div.file-info > div"))
            ).text
            
            ahref = download_button.get_attribute('href')
            
            download_urls = [set_url(ahref, 'use_mirror', mirror_id) for mirror_id in li_id]
            
            edit_telegram_message(initial_message_id, f"⬇️ **Memulai unduhan dengan `aria2c`...**\nFile: `{aname}`")
            downloaded_filename = download_file_with_aria2c(download_urls, aname)
            
            if downloaded_filename:
                edit_telegram_message(initial_message_id, f"✅ **SourceForge: Unduhan selesai!**\nFile: `{downloaded_filename}`\n\n**➡️ Mulai UPLOADING...**")
                # --- SIMPAN NAMA FILE UNTUK SKRIP UPLOADER ---
                with open("downloaded_filename.txt", "w") as f:
                    f.write(downloaded_filename)
            else:
                edit_telegram_message(initial_message_id, "❌ **SourceForge: Unduhan gagal atau melebihi batas waktu!**")
                
            return downloaded_filename 

        # --- Logika umum untuk GoFile dan Mediafire (Selenium) ---
        else:
            initial_message_id = send_telegram_message("⬇️ **Mulai mengunduh...**")
            driver.get(url)
            
            if "gofile" in url:
                download_button_selector = "#filemanager_itemslist > div.border-b.border-gray-600 > div > div:nth-child(2) > div > button"
            elif "mediafire" in url:
                download_button_selector = "#downloadButton"
            else:
                raise ValueError("URL tidak didukung oleh downloader ini.")

            download_button = WebDriverWait(driver, 20).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, download_button_selector))
            )
            
            driver.execute_script("arguments[0].click();", download_button)
            time.sleep(1)
            
            start_time = time.time()
            timeout = 300
            
            # Menunggu unduhan selesai (di temp_download_dir)
            while time.time() - start_time < timeout:
                is_downloading = any(fname.endswith(('.crdownload', '.tmp')) or fname.startswith('.com.google.Chrome.') for fname in os.listdir(temp_download_dir))
                
                if not is_downloading:
                    print("Unduhan selesai di folder sementara!")
                    break
                
                time.sleep(1)
            else:
                edit_telegram_message(initial_message_id, "❌ **Unduhan gagal atau melebihi batas waktu!**")
                return None

            # Memindahkan file
            list_of_files = [f for f in os.listdir(temp_download_dir) if not f.endswith(('.crdownload', '.tmp'))]
            if list_of_files:
                latest_file_path = max([os.path.join(temp_download_dir, f) for f in list_of_files], key=os.path.getctime)
                downloaded_filename = os.path.basename(latest_file_path)
                
                shutil.move(latest_file_path, os.path.join(os.getcwd(), downloaded_filename))
                
                print(f"File berhasil diunduh dan dipindahkan ke root: {downloaded_filename}")
                edit_telegram_message(initial_message_id, f"✅ **Unduhan selesai!**\nFile: `{downloaded_filename}`\n\n**➡️ Mulai UPLOADING...**")
                # --- SIMPAN NAMA FILE UNTUK SKRIP UPLOADER ---
                with open("downloaded_filename.txt", "w") as f:
                    f.write(downloaded_filename)
            else:
                edit_telegram_message(initial_message_id, "❌ **Gagal menemukan file yang diunduh.**")
                return None

    except Exception as e:
        print(f"Gagal mengunduh file: {e}")
        if initial_message_id:
            edit_telegram_message(initial_message_id, f"❌ **Terjadi kesalahan saat mengunduh.**\nDetail: {str(e)[:150]}...")
        downloaded_filename = None
        
    finally:
        if driver:
            driver.quit()
        shutil.rmtree(temp_download_dir, ignore_errors=True)
        
        return downloaded_filename

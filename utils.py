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
import sys
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from urllib.parse import urlparse, urlunparse, urlencode, parse_qs

# =========================================================
# KONSTANTA & KONFIGURASI
# =========================================================

BOT_TOKEN = os.environ.get("BOT_TOKEN")
OWNER_ID = os.environ.get("PAYLOAD_SENDER")
# Tentukan directory untuk download sementara (hanya untuk Selenium)
TEMP_DOWNLOAD_DIR = tempfile.mkdtemp()

# =========================================================
# FUNGSI BANTUAN TELEGRAM & UMUM
# =========================================================

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
        
        # --- DEBUGGING TAMBAHAN ---
        response_json = response.json()
        #print(f"DEBUG: Telegram Send Response: {response_json}")
        # --------------------------

        return response_json.get('result', {}).get('message_id')
    except Exception as e:
        print(f"Gagal mengirim pesan Telegram: {e}")
        return None
def edit_telegram_message(message_id, message_text):
    """Mengedit pesan yang sudah ada di Telegram."""
    if not BOT_TOKEN or not OWNER_ID or not message_id:
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/editMessageText"
    payload = {"chat_id": OWNER_ID, "message_id": message_id, "text": message_text, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Gagal mengedit pesan Telegram: {e}")

def human_readable_size(size_bytes):
    if size_bytes is None or size_bytes == 0: return "0B"
    size_name = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
    i = int(math.floor(math.log(size_bytes, 1024))) if size_bytes > 0 else 0
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2) if p > 0 else 0
    return f"{s} {size_name[i]}"

def send_progress_to_telegram(message_id, filename, current_size, total_size, status="⬇️ Download"):
    """Mengirim update progress (digunakan oleh fungsi yang tahu total_size)."""
    percent = int((current_size / total_size) * 100) if total_size else 0
    text = f"{status} `{filename}` — {percent}% ({human_readable_size(current_size)}/{human_readable_size(total_size)})"
    edit_telegram_message(message_id, text)

def get_total_file_size_safe(url):
    """Mendapatkan ukuran file total dari URL dengan aman."""
    try:
        response = requests.head(url, allow_redirects=True, timeout=10)
        response.raise_for_status()
        content_length = response.headers.get('Content-Length')
        if content_length: return int(content_length)
    except requests.exceptions.RequestException:
        pass # Lanjut ke metode streaming jika HEAD gagal
    
    # Mencoba mendapatkan ukuran melalui koneksi streaming
    total_size = 0
    # Cukup ambil chunk kecil di awal untuk estimasi jika perlu
    try:
        with requests.get(url, stream=True, timeout=30) as r:
            r.raise_for_status()
            if 'Content-Length' in r.headers:
                return int(r.headers['Content-Length'])
    except requests.exceptions.RequestException as e:
        print(f"❌ Gagal mendapatkan ukuran file: {e}")
    return None

# =========================================================
# FUNGSI DOWNLOAD UTAMA (ARIA2C & MEGATOOLS)
# =========================================================

def download_file_with_aria2c(urls, output_filename=None):
    """
    Mengunduh file menggunakan aria2c.
    PROGRESS UPDATE: Hanya pada 50% dan 100% (2x update).
    """
    print(f"Memulai unduhan {output_filename} dengan aria2c.")
    total_size = None
    command = ['aria2c', '--allow-overwrite', '--file-allocation=none', '--console-log-level=warn', 
               '--summary-interval=0', '-x', '16', '-s', '16', '-c', '--async-dns=false', 
               '--log-level=warn', '--continue', '--input-file', '-', '-o', output_filename]
    
    process = None
    try:
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        
        # Coba dapatkan total size dari URL pertama yang berhasil
        for url in urls:
            total_size = get_total_file_size_safe(url)
            if total_size is not None:
                process.stdin.write(url + '\n')
                break # Hanya kirim 1 URL ke aria2c jika sudah dapat total_size
        process.stdin.close()
        
        start_time = time.time()
        timeout = 300
        last_notified_percent = 0 # 0 -> 50 -> 100
        message_id = send_telegram_message(f"⬇️ Download dimulai: `{output_filename}`")
        
        while time.time() - start_time < timeout:
            if os.path.exists(output_filename):
                current_size = os.path.getsize(output_filename)
                
                if total_size is not None and total_size > 0:
                    percent_now = int(current_size * 100 // total_size)
                    
                    # LOGIKA 2X UPDATE
                    should_update_50 = (percent_now >= 50 and last_notified_percent < 50)
                    should_update_100 = (percent_now >= 100) # Gunakan >= 100 karena ukuran file bisa sedikit berbeda

                    if should_update_50 or should_update_100:
                        send_progress_to_telegram(message_id, output_filename, current_size, total_size)
                        last_notified_percent = percent_now
                        
                if (total_size is not None and current_size >= total_size):
                    print(f"File {output_filename} selesai. Menghentikan aria2c...")
                    if process.poll() is None:
                        process.terminate()
                        time.sleep(2)
                        if process.poll() is None: process.kill()
                    return output_filename
                    
            if process.poll() is not None:
                # Periksa apakah proses selesai dengan sukses
                if os.path.exists(output_filename) and os.path.getsize(output_filename) > 0:
                     # Pastikan notifikasi 100% terkirim
                    if total_size is None or os.path.getsize(output_filename) > total_size:
                        total_size = os.path.getsize(output_filename)
                    send_progress_to_telegram(message_id, output_filename, total_size, total_size)
                    return output_filename
                
                print("Aria2c berhenti sebelum file selesai diunduh. Mungkin terjadi kesalahan.")
                return None
                
            time.sleep(3)
        
        # Timeout logic
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

def download_file_with_megatools(url):
    """
    Mengunduh file dari MEGA dengan megatools.
    PROGRESS UPDATE: Hanya pada 50% dan 100% (2x update) berdasarkan output megatools.
    """
    print(f"Mengunduh file dari MEGA dengan megatools: {url}")
    original_cwd = os.getcwd()
    temp_dir = tempfile.mkdtemp()
    filename = None
    initial_message_id = send_telegram_message("⬇️ **Mulai mengunduh...**\n`megatools` sedang mengunduh file.")
    try:
        os.chdir(temp_dir)
        process = subprocess.Popen(['megatools', 'dl', url], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        
        last_notified_percent = 0 # 0 -> 50 -> 100
        progress_regex = re.compile(r'(\d+\.\d+)%\s+of\s+.*\((\d+\.\d+)\s*(\wB)\)')
        
        while True:
            line = process.stdout.readline()
            if not line: break
            
            match = progress_regex.search(line)
            if match:
                percent_now = math.floor(float(match.group(1)))
                current_size_str = match.group(2)
                current_unit = match.group(3)
                
                # LOGIKA 2X UPDATE
                should_update_50 = (percent_now >= 50 and last_notified_percent < 50)
                should_update_100 = (percent_now == 100)
                
                if should_update_50 or should_update_100:
                    last_notified_percent = percent_now
                    progress_message = f"⬇️ **Mulai mengunduh...**\nUkuran file: `{current_size_str} {current_unit}`\n\nProgres: `{percent_now}%`"
                    edit_telegram_message(initial_message_id, progress_message)
                    
        process.wait()
        if process.returncode != 0:
            error_output = process.stderr.read()
            raise subprocess.CalledProcessError(process.returncode, process.args, stderr=error_output)
            
        downloaded_files = os.listdir('.')
        # Filter file temporer .megatools
        downloaded_files = [f for f in downloaded_files if not f.endswith('.megatools')]
        
        if len(downloaded_files) == 1:
            filename = downloaded_files[0]
            edit_telegram_message(initial_message_id, f"✅ **MEGA: Unduhan selesai!**\nFile: `{filename}`\n\n**➡️ Mulai UPLOADING...**")
            with open("downloaded_filename.txt", "w") as f: f.write(filename)
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
        # Pindahkan file yang sudah selesai ke direktori kerja utama
        if filename and os.path.exists(os.path.join(temp_dir, filename)):
            shutil.move(os.path.join(temp_dir, filename), os.path.join(original_cwd, filename))
        shutil.rmtree(temp_dir, ignore_errors=True)

def download_with_yt_dlp(url):
    """
    Mengunduh file dari Google Drive via yt-dlp dan aria2c.
    """
    print(f"Memproses URL Google Drive: {url}")
    initial_message_id = send_telegram_message("⏳ **Memulai unduhan (Google Drive Bypass)...**\nMemeriksa URL...")
    final_filename = None
    edit_telegram_message(initial_message_id, "🔍 **Mengekstrak URL Pengunduhan Asli...**")
    
    extract_command = [
        'yt-dlp', '--no-warnings', '--no-check-certificate', '--referer', url,
        '--user-agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
        '--get-url', '--print', 'title', url
    ]
    
    try:
        process = subprocess.run(extract_command, capture_output=True, text=True, check=True, timeout=30)
        output_lines = process.stdout.splitlines()
        
        if len(output_lines) < 2:
            raise Exception("yt-dlp gagal mendapatkan URL dan Judul.")
            
        direct_url = output_lines[-1].strip()
        suggested_title = output_lines[-2].strip()
        
        # Penentuan nama file: tambahkan ekstensi umum (.zip) jika tidak ada
        suggested_filename = f"{suggested_title}.zip" if '.' not in suggested_title and suggested_title else suggested_title
        final_filename = suggested_filename
        
    except Exception as e:
        error_message = str(e)
        print(f"Gagal mengekstrak URL: {error_message}")
        edit_telegram_message(initial_message_id, f"❌ **Gagal mengekstrak URL dari Google Drive.**\n\nDetail: {error_message[:150]}...")
        return None
        
    # TAHAP 2: PENGUNDUHAN LANGSUNG (memanggil aria2c yang sudah 2x update)
    edit_telegram_message(initial_message_id, f"⬇️ **Memulai unduhan dengan `aria2c`...**\nFile: `{final_filename}`")
    downloaded_filename = download_file_with_aria2c([direct_url], final_filename)
    
    if downloaded_filename:
        edit_telegram_message(initial_message_id, f"✅ **Google Drive: Unduhan selesai!**\nFile: `{downloaded_filename}`\n\n**➡️ Mulai UPLOADING...**")
        with open("downloaded_filename.txt", "w") as f: f.write(downloaded_filename)
    else:
        edit_telegram_message(initial_message_id, f"❌ **Google Drive: Unduhan gagal!**")
        
    return downloaded_filename

# =========================================================
# FUNGSI SELENIUM
# =========================================================

def initialize_selenium_driver(download_dir):
    """Menginisialisasi dan mengkonfigurasi Chrome Driver (Headless)."""
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
    
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        return driver
    except Exception as e:
        print(f"❌ Gagal inisialisasi Selenium Driver: {e}")
        return None

def process_selenium_download(driver, url, initial_message_id):
    """
    Menangani proses Gofile (1-step click) dan Mediafire (2-step: Form Submit -> Ekstraksi Link -> Aria2c).
    """
    driver.get(url)
    downloaded_filename = None
    
    # 1. Tentukan Selektor Tombol/Form
    if "gofile" in url:
        # Gofile tetap 1-step click (Logika Monitoring Lama)
        download_button_selector = "#filemanager_itemslist > div.border-b.border-gray-600 > div > div:nth-child(2) > div > button"
        SELECTOR_STEP_2 = download_button_selector 
        
    elif "mediafire" in url:
        # Mediafire 2-step
        FORM_SELECTOR_STEP_1 = "form.dl-btn-form" 
        SELECTOR_STEP_2 = "#downloadButton"          
    else:
        raise ValueError("URL tidak didukung oleh proses Selenium ini.")
        
    edit_telegram_message(initial_message_id, f"⬇️ **[Mode Download]** Menganalisis situs...")

    # ====================================================================
    # --- LOGIKA KHUSUS MEDIAFIRE: FORM SUBMIT + EKSTRAKSI LINK ---
    # ====================================================================
    if "mediafire" in url:
        edit_telegram_message(initial_message_id, "⬇️ **[MediaFire Mode]** Mencari dan mengirimkan FORM Step 1...")
        try:
            # 1. Kirimkan FORM
            form_element = WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, FORM_SELECTOR_STEP_1))
            )
            form_element.submit()
            print("MediaFire FORM Step 1 berhasil dikirim. Menunggu halaman kedua...")
            
        except TimeoutException:
            raise TimeoutException(f"Gagal menemukan FORM MediaFire '{FORM_SELECTOR_STEP_1}'.")

        # 2. Tunggu dan EKSTRAKSI URL dan NAMA FILE di Halaman Baru
        edit_telegram_message(initial_message_id, "🔍 **[MediaFire Mode]** Halaman kedua dimuat. Mengekstrak URL Download Langsung...")
        
        try:
            download_button = WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, SELECTOR_STEP_2))
            )
            
            final_download_url = download_button.get_attribute('href')
            
            if not final_download_url:
                raise Exception("Atribut 'href' pada tombol download kosong.")

            # --- PERBAIKAN: MENDAPATKAN NAMA FILE DARI HEADER ---
            edit_telegram_message(initial_message_id, "🔍 **[MediaFire Mode]** Memeriksa header Content-Disposition...")
            
            file_name = None
            try:
                # Gunakan requests.head untuk mendapatkan header tanpa mengunduh seluruh file
                head_response = requests.head(final_download_url, allow_redirects=True, timeout=10)
                head_response.raise_for_status()
                
                # Mendapatkan nama file dari header Content-Disposition
                cd_header = head_response.headers.get('Content-Disposition')
                if cd_header:
                    fname_match = re.search(r'filename\*?=["\']?(?:utf-8\'\')?([^"\';]+)["\']?', cd_header, re.I)
                    if fname_match:
                        file_name = fname_match.group(1).strip()
                        # Hapus karakter non-ASCII yang mungkin tersisa
                        file_name = re.sub(r'[^\x00-\x7F]+', '', file_name)
                    else:
                        # Fallback: Cari nama setelah 'filename='
                        fname_match_simple = re.search(r'filename=["\']?([^"\';]+)["\']?', cd_header, re.I)
                        if fname_match_simple:
                             file_name = fname_match_simple.group(1).strip()
                             file_name = re.sub(r'[^\x00-\x7F]+', '', file_name)

                # Fallback terakhir jika header CD tidak ada atau gagal diuraikan
                if not file_name:
                    url_path = urlparse(final_download_url).path
                    file_name = url_path.split('/')[-1]
                
            except requests.exceptions.RequestException as e:
                print(f"Peringatan: Gagal mendapatkan header file dari URL. Fallback ke nama dari path URL. Detail: {e}")
                url_path = urlparse(final_download_url).path
                file_name = url_path.split('/')[-1]
            
            # --- END OF HEADER EXTRACTION ---

            print(f"Ekstraksi Berhasil! URL: {final_download_url}, Nama File Dikonfirmasi: {file_name}")
            
            # --- PANGGIL ARIA2C ---
            edit_telegram_message(initial_message_id, f"⬇️ **Memulai unduhan dengan `aria2c`...**\nFile: `{file_name}`")
            downloaded_filename = download_file_with_aria2c([final_download_url], file_name)
            
            # --- FINALISASI ARIA2C ---
            if downloaded_filename:
                edit_telegram_message(initial_message_id, f"✅ **MediaFire: Unduhan selesai!**\nFile: `{downloaded_filename}`\n\n**➡️ Mulai UPLOADING...**")
                with open("downloaded_filename.txt", "w") as f: f.write(downloaded_filename)
            else:
                raise Exception("Aria2c gagal mengunduh file.")
                
            return downloaded_filename
            
        except TimeoutException:
            raise TimeoutException(f"Gagal menemukan elemen tombol download final MediaFire ('{SELECTOR_STEP_2}').")
        except Exception as e:
            raise Exception(f"Gagal saat ekstraksi link atau pemanggilan Aria2c: {e}")

    # --- LOGIKA GOFILE 1-STEP (atau jika di atas berhasil memicu download) ---
    elif "gofile" in url:
        edit_telegram_message(initial_message_id, "⬇️ **[Gofile Mode]** Mencari dan mengklik tombol download...")
        try:
            download_button = WebDriverWait(driver, 20).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, SELECTOR_STEP_2))
            )
            driver.execute_script("arguments[0].click();", download_button)
            time.sleep(2) # Jeda untuk memulai download
        except TimeoutException:
            raise TimeoutException(f"Gagal menemukan atau mengklik tombol download Gofile ('{SELECTOR_STEP_2}').")


    # 4. Monitoring Download (Logika Monitoring Ketat)
    start_time = time.time()
    timeout = 300
    midway_notified = False
    
    initial_files = set(os.listdir(TEMP_DOWNLOAD_DIR))
    
    while time.time() - start_time < timeout:
        current_files = os.listdir(TEMP_DOWNLOAD_DIR)
        
        # Logika Deteksi File Temporer yang Lebih Kuat
        is_downloading = any(
            fname.endswith(('.crdownload', '.tmp')) or 
            fname.startswith('.com.google.Chrome.') or
            "Unconfirmed" in fname
            for fname in current_files
        )
        
        # Cari file yang BUKAN temporer dan BARU
        final_files_list = [
            f for f in current_files 
            if not f.endswith(('.crdownload', '.tmp')) and 
               not f.startswith('.') and 
               "Unconfirmed" not in f and 
               f not in initial_files
        ]

        if not is_downloading and final_files_list:
            print("Unduhan selesai, file final terdeteksi, dan tidak ada file temporer.")
            break
        
        if not is_downloading and not final_files_list and len(current_files) > len(initial_files):
            # Kasus kritis: File temporer hilang, tapi file final belum muncul/stabil.
            print("Potensi selesai: File temporer hilang, memberi jeda 5 detik untuk finalisasi.")
            time.sleep(5) 
            continue
            
        # Update 1x di tengah
        elapsed_time = time.time() - start_time
        if elapsed_time > 30 and not midway_notified and is_downloading:
            edit_telegram_message(initial_message_id, "⬇️ **Masih mengunduh...**\nStatus: Proses unduhan berjalan (sudah 30+ detik).")
            midway_notified = True
        
        time.sleep(1)
        
    else:
        raise TimeoutException("Unduhan gagal atau melebihi batas waktu 300 detik.")

    # 5. Finalisasi File
    final_files_list = [
        f for f in os.listdir(TEMP_DOWNLOAD_DIR) 
        if not f.endswith(('.crdownload', '.tmp')) and not f.startswith('.') and "Unconfirmed" not in f
    ]
    
    if final_files_list:
        latest_file_path = max([os.path.join(TEMP_DOWNLOAD_DIR, f) for f in final_files_list], key=os.path.getctime)
        downloaded_filename = os.path.basename(latest_file_path)
        
        shutil.move(latest_file_path, os.path.join(os.getcwd(), downloaded_filename))
        
        file_size = os.path.getsize(downloaded_filename)
        edit_telegram_message(initial_message_id, f"✅ **Unduhan selesai!**\nFile: `{downloaded_filename}` ({human_readable_size(file_size)})\n\n**➡️ Mulai UPLOADING...**")
        
        with open("downloaded_filename.txt", "w") as f: f.write(downloaded_filename)
        return downloaded_filename
    else:
        print(f"DEBUG: Direktori download: {TEMP_DOWNLOAD_DIR}")
        print(f"DEBUG: Isi direktori setelah monitoring: {os.listdir(TEMP_DOWNLOAD_DIR)}")
        raise FileNotFoundError("Gagal menemukan file yang diunduh setelah monitoring.")
        
def process_sourceforge_download(driver, url, initial_message_id):
    """
    Menangani SourceForge: Mendapatkan mirror URL dan memanggil aria2c.
    Menggunakan aria2c yang sudah 2x update.
    """
    
    def source_url(download_url):
        parsed_url = urlparse(download_url)
        path_parts = parsed_url.path.split('/')
        project_name = path_parts[2]
        file_path = '/'.join(path_parts[4:-1])
        query_params = {'projectname': project_name, 'filename': file_path}
        new_path = "/settings/mirror_choices"
        new_url_parts = (parsed_url.scheme, parsed_url.netloc, new_path, '', urlencode(query_params), '')
        return urlunparse(new_url_parts)
    
    def set_url(url, param_name, param_value):
        parsed_url = urlparse(url)
        query_params = parse_qs(parsed_url.query)
        query_params[param_name] = [param_value]
        new_query = urlencode(query_params, doseq=True)
        return urlunparse((parsed_url.scheme, parsed_url.netloc, parsed_url.path, parsed_url.params, new_query, parsed_url.fragment))
    
    mirror_url = source_url(url)
    driver.get(mirror_url)
    
    # 1. Ambil ID Mirror
    list_items = WebDriverWait(driver, 10).until(
        EC.presence_of_all_elements_located((By.CSS_SELECTOR, "ul#mirrorList > li"))
    )
    li_id = [item.get_attribute("id") for item in list_items]
    
    # 2. Ambil Nama File dan Base Link
    driver.get(url)
    download_button = WebDriverWait(driver, 20).until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, "#remaining-buttons > div.large-12 > a.button.green"))
    )
    aname = WebDriverWait(driver, 10).until(
        EC.visibility_of_element_located((By.CSS_SELECTOR, "#downloading > div.content > div.file-info > div"))
    ).text
    ahref = download_button.get_attribute('href')
    
    # 3. Buat Daftar URL Download Lengkap
    download_urls = [set_url(ahref, 'use_mirror', mirror_id) for mirror_id in li_id]
    
    # 4. Panggil aria2c
    edit_telegram_message(initial_message_id, f"⬇️ **Memulai unduhan dengan `aria2c`...**\nFile: `{aname}`")
    downloaded_filename = download_file_with_aria2c(download_urls, aname)
    
    if downloaded_filename:
        edit_telegram_message(initial_message_id, f"✅ **SourceForge: Unduhan selesai!**\nFile: `{downloaded_filename}`\n\n**➡️ Mulai UPLOADING...**")
        with open("downloaded_filename.txt", "w") as f: f.write(downloaded_filename)
    
    return downloaded_filename

def process_apkadmin_download(driver, url, initial_message_id):
    """
    Menangani proses dua kali klik tombol download (seperti pada Apk Admin)
    di mana klik pertama memicu NAVIGASI/FORM SUBMIT ke halaman baru.
    """
    driver.get(url)
    
    # Selector untuk FORM (atau tombol submit yang ada di dalamnya)
    SELECTOR_FORM = "form[name='F1']"
    
    edit_telegram_message(initial_message_id, "⬇️ **[Apk Admin Mode]** Mencari dan mengirimkan FORM Step 1...")
    
    try:
        # 1. Cari elemen FORM berdasarkan name='F1'
        form_element = WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, SELECTOR_FORM))
        )
        
        # 2. Kirimkan FORM. Ini akan memicu navigasi ke halaman berikutnya.
        form_element.submit()
        
        print("FORM Step 1 berhasil dikirim (submit). Menunggu halaman kedua dimuat...")
    except TimeoutException:
        raise TimeoutException(f"Gagal menemukan FORM '{SELECTOR_FORM}'.")

    # 2. Tunggu dan Klik Tombol Download Kedua (Final) di Halaman Baru
    # Selector ini tetap digunakan untuk halaman kedua:
    SELECTOR_STEP_2 = "#container > div.download-file.step-2 > div.a-spot.text-align-center > div > a"
    sss =             "#container > div.download-file.step-2 > div.a-spot.text-align-center > div > a > img
    
    edit_telegram_message(initial_message_id, "⬇️ **[Apk Admin Mode]** Halaman kedua dimuat. Mencari tombol Step 2 (Max 45 detik)...")
    
    try:
        # Menunggu tombol final muncul di DOM halaman baru
        # Waktu tunggu 45 detik (perbaikan sebelumnya)
        download_button = WebDriverWait(driver, 30).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, SELECTOR_STEP_2))
        )
        driver.execute_script("arguments[0].click();", download_button)
        time.sleep(1)
    except TimeoutException:
        current_url = driver.current_url
        page_source_start = driver.page_source[:500]
        print(f"DEBUG: URL saat gagal: {current_url}")
        print(f"DEBUG: Awal source code: {page_source_start}...")
        raise TimeoutException("Gagal menemukan atau mengklik tombol download Step 2 (SELECTOR_STEP_2). Cek URL/Selector.")

    # 3. Monitoring Download (Sama seperti sebelumnya)
    # [LANJUTKAN DENGAN LOGIKA MONITORING DOWNLOAD SEPERTI SEBELUMNYA]
    # ...
    
    start_time = time.time()
    timeout = 300
    midway_notified = False
    
    while time.time() - start_time < timeout:
        is_downloading = any(fname.endswith(('.crdownload', '.tmp')) or fname.startswith('.com.google.Chrome.') for fname in os.listdir(TEMP_DOWNLOAD_DIR))
        
        elapsed_time = time.time() - start_time
        if elapsed_time > 30 and not midway_notified and is_downloading:
            edit_telegram_message(initial_message_id, "⬇️ **[Apk Admin Mode]** Proses unduhan berjalan (sudah 30+ detik).")
            midway_notified = True
        
        if not is_downloading:
            print("Unduhan selesai di folder sementara!")
            break
        time.sleep(1)
        
    else:
        raise TimeoutException("Unduhan gagal atau melebihi batas waktu 300 detik.")

    # 4. Finalisasi File
    list_of_files = [f for f in os.listdir(TEMP_DOWNLOAD_DIR) if not f.endswith(('.crdownload', '.tmp')) and not f.startswith('.')]
    if list_of_files:
        latest_file_path = max([os.path.join(TEMP_DOWNLOAD_DIR, f) for f in list_of_files], key=os.path.getctime)
        downloaded_filename = os.path.basename(latest_file_path)
        shutil.move(latest_file_path, os.path.join(os.getcwd(), downloaded_filename))
        
        edit_telegram_message(initial_message_id, f"✅ **[Apk Admin Mode] Unduhan selesai!**\nFile: `{downloaded_filename}`\n\n**➡️ Mulai UPLOADING...**")
        
        with open("downloaded_filename.txt", "w") as f: f.write(downloaded_filename)
        return downloaded_filename
    else:
        raise FileNotFoundError("Gagal menemukan file yang diunduh.")
# =========================================================
# FUNGSI UTAMA (ORCHESTRATOR)
# =========================================================

def downloader(url):
    """
    Fungsi utama yang mengarahkan URL ke penangan yang tepat (Selenium, yt-dlp, atau aria2c).
    """
    initial_message_id = send_telegram_message(f"⏳ **Menganalisis URL...**\nURL: `{url}`")
    downloaded_filename = None
    driver = None
    
    try:
        # 1. LOGIKA YT-DLP (Google Drive)
        if "apkadmin" in url.lower(): # Menggunakan penanda khusus 'apkadmin'
            print("Mode: Apk Admin (Selenium 2-Step)")
            driver = initialize_selenium_driver(TEMP_DOWNLOAD_DIR)
            if not driver: raise Exception("Gagal inisialisasi driver Selenium.")
            downloaded_filename = process_apkadmin_download(driver, url, initial_message_id)
        # 2. LOGIKA MEGATOOLS (MEGA)
        elif "mega.nz" in url:
            downloaded_filename = download_file_with_megatools(url)
        
        # 3. LOGIKA SELENIUM (SourceForge, Gofile, Mediafire)
        elif "sourceforge" in url or "gofile" in url or "mediafire" in url:
            driver = initialize_selenium_driver(TEMP_DOWNLOAD_DIR)
            if not driver: raise Exception("Gagal inisialisasi driver Selenium.")
            
            if "sourceforge" in url:
                downloaded_filename = process_sourceforge_download(driver, url, initial_message_id)
            elif "gofile" in url or "mediafire" in url:
                downloaded_filename = process_selenium_download(driver, url, initial_message_id)

        # 4. LOGIKA PIXELDRAIN (Ambil info file sebelum download)
        elif "pixeldrain" in url:
            print("Mode: Pixeldrain (Ambil Info File)")
            
            file_id_match = re.search(r'pixeldrain\.com/(u|l|f)/([a-zA-Z0-9]+)', url)
            if not file_id_match: raise ValueError("URL Pixeldrain tidak valid.")
            file_id = file_id_match.group(2)
            
            # --- LANGKAH 1: Ambil Nama File dari API ---
            info_url = f"https://pixeldrain.com/api/file/{file_id}/info"
            
            edit_telegram_message(initial_message_id, f"🔍 **Mendapatkan informasi file dari Pixeldrain...** ID: `{file_id}`")
            
            try:
                info_resp = requests.get(info_url, timeout=10)
                info_resp.raise_for_status()
                file_info = info_resp.json()
            except requests.exceptions.RequestException as e:
                raise Exception(f"Gagal koneksi ke API Pixeldrain: {e}")
            
            if file_info.get('success') and file_info.get('name'):
                filename = file_info['name']
            else:
                # Fallback jika API tidak memberikan nama
                print("⚠️ API Pixeldrain tidak memberikan nama file yang valid. Menggunakan fallback.")
                filename = f"pixeldrain_download_{file_id}"
            
            # --- LANGKAH 2: Download Menggunakan Nama yang Benar ---
            download_url = f"https://pixeldrain.com/api/file/{file_id}?download"
            
            edit_telegram_message(initial_message_id, f"⬇️ **Memulai unduhan dengan `aria2c`...**\nFile: `{filename}`")
            downloaded_filename = download_file_with_aria2c([download_url], filename)
            
            if downloaded_filename:
                edit_telegram_message(initial_message_id, f"✅ **Pixeldrain: Unduhan selesai!**\nFile: `{downloaded_filename}`\n\n**➡️ Mulai UPLOADING...**")
                with open("downloaded_filename.txt", "w") as f: f.write(downloaded_filename)
        else:
            raise ValueError("URL tidak dikenali atau tidak didukung.")

        if downloaded_filename:
            return downloaded_filename
        
    except Exception as e:
        print(f"❌ Unduhan utama gagal: {e}")
        edit_telegram_message(initial_message_id, f"❌ **Unduhan GAGAL!**\nDetail: {str(e)[:150]}...")
        downloaded_filename = None
        
    finally:
        if driver:
            driver.quit()
        # Bersihkan folder temp SELALU
        shutil.rmtree(TEMP_DOWNLOAD_DIR, ignore_errors=True)
        return downloaded_filename


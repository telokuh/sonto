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

# Dapatkan URL halaman dari environment variable
mediafire_page_url = os.environ.get("MEDIAFIRE_PAGE_URL")

# Regex untuk mendeteksi URL
YOUTUBE_URL_REGEX = r"(?:https?://)?(?:www\.)?(?:youtube\.com|youtu\.be)/.+"
MEGA_URL_REGEX = r"(?:https?://)?(?:www\.)?mega\.nz/.+"
PIXELDRAIN_URL_REGEX = r"(?:https?://)?(?:www\.)?pixeldrain\.com/u/.+"
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
        driver.save_screenshot("error_screenshot.png")
        print("Screenshot error_screenshot.png telah dibuat.")
        return None
    finally:
        driver.quit()

def download_file_with_megatools(url):
    print(f"Mengunduh file dari MEGA dengan megatools: {url}")
    
    # Simpan direktori kerja saat ini
    original_cwd = os.getcwd()
    
    # Buat direktori sementara
    temp_dir = tempfile.mkdtemp()
    
    initial_message_id = send_telegram_message("⬇️ **Mulai mengunduh...**\n`megatools` sedang mengunduh file.")

    try:
        # Pindah ke direktori sementara
        os.chdir(temp_dir)
        
        # Jalankan megatools dan baca output secara real-time
        process = subprocess.Popen(
            ['megatools', 'dl', url],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        total_size = 0
        last_percent_notified = 0

        # Regex untuk mengekstrak persentase dan ukuran file
        progress_regex = re.compile(r'(\d+\.\d+)%\s+of\s+.*\((\d+\.\d+)\s*(\wB)\)')

        while True:
            line = process.stdout.readline()
            if not line:
                break
            
            # Cari persentase dan ukuran file
            match = progress_regex.search(line)
            if match:
                current_percent = math.floor(float(match.group(1)))
                current_size_str = match.group(2)
                current_unit = match.group(3)

                # Dapatkan ukuran total dari baris pertama
                if total_size == 0:
                    total_size = f"{current_size_str} {current_unit}"
                    
                # Kirim pembaruan ke Telegram setiap 10%
                if current_percent >= last_percent_notified + 10 or current_percent == 100:
                    last_percent_notified = current_percent
                    progress_message = f"⬇️ **Mulai mengunduh...**\nUkuran file: `{total_size}`\n\nProgres: `{current_percent}%`"
                    edit_telegram_message(initial_message_id, progress_message)

        # Tunggu proses selesai dan periksa kode keluarannya
        process.wait()
        if process.returncode != 0:
            error_output = process.stderr.read()
            raise subprocess.CalledProcessError(process.returncode, process.args, stderr=error_output)

        # Cari file yang diunduh di direktori sementara
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
        # Pindah kembali ke direktori kerja asli
        os.chdir(original_cwd)
        # Pindahkan file yang diunduh dari temp_dir ke direktori asli
        if 'filename' in locals() and os.path.exists(os.path.join(temp_dir, filename)):
            shutil.move(os.path.join(temp_dir, filename), os.path.join(original_cwd, filename))
        # Hapus direktori sementara
        shutil.rmtree(temp_dir, ignore_errors=True)
    
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

        total_size = int(response.headers.get('content-length', 0))
        total_size_human = human_readable_size(total_size)
        
        initial_message = f"⬇️ **Mulai mengunduh...**\n`{filename}`\nUkuran file: `{total_size_human}`\n\nProgres: `0%`"
        message_id = send_telegram_message(initial_message)

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
                        progress_message = f"⬇️ **Mulai mengunduh...**\n`{filename}`\nUkuran file: `{total_size_human}`\n\nProgres: `{current_percent}%`"
                        edit_telegram_message(message_id, progress_message)
        
        print(f"File berhasil diunduh sebagai: {filename}")
        return filename
    except requests.exceptions.RequestException as e:
        print(f"Gagal mengunduh file: {e}")
        send_telegram_message(f"❌ **Gagal mengunduh file.**\n\nDetail: {str(e)[:150]}...")
        return None

def get_download_url_from_pixeldrain(url):
    print("Menggunakan Selenium untuk Pixeldrain...")
    
    # Buat direktori unduhan sementara
    download_dir = tempfile.mkdtemp()
    
    total_size_bytes = 0
    total_size_human = "Ukuran tidak diketahui"
    
    try:
        service = Service(ChromeDriverManager().install())
        options = webdriver.ChromeOptions()
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')

        # Konfigurasi preferensi Chrome untuk mengunduh ke direktori sementara
        prefs = {'download.default_directory': download_dir}
        options.add_experimental_option('prefs', prefs)
        
        driver = webdriver.Chrome(service=service, options=options)
        driver.get(url)

        # Cari ukuran file di halaman Pixeldrain
        try:
            file_size_element = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "small.file-size"))
            )
            total_size_human = file_size_element.text
            total_size_bytes = human_readable_to_bytes(total_size_human)
        except Exception:
            print("Ukuran file tidak ditemukan di halaman.")
            pass
            
        initial_message = f"⬇️ **Mulai mengunduh...**\nMenggunakan Selenium untuk Pixeldrain.\nUkuran file: `{total_size_human}`\n\nProgres: `0%`"
        initial_message_id = send_telegram_message(initial_message)

        # Temukan tombol unduh
        download_button = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "button.button_highlight"))
        )
        
        # Klik tombol unduh
        print("Mengklik tombol unduh...")
        download_button.click()
        
        # Tunggu hingga file muncul di direktori unduhan dan lacak progres
        max_wait_time = 300
        waited_time = 0
        last_percent_notified = 0
        
        while waited_time < max_wait_time:
            files = os.listdir(download_dir)
            if files:
                current_file_path = os.path.join(download_dir, files[0])
                if not files[0].endswith('.crdownload') and os.path.exists(current_file_path):
                    # Unduhan selesai
                    filename = files[0]
                    downloaded_size = os.path.getsize(current_file_path)
                    current_percent = 100
                    edit_telegram_message(initial_message_id, f"⬇️ **Mulai mengunduh...**\nUkuran file: `{total_size_human}`\n\nProgres: `{current_percent}%`")
                    
                    print(f"File berhasil diunduh sebagai: {filename}")
                    
                    # Pindahkan file ke direktori kerja utama
                    shutil.move(os.path.join(download_dir, filename), os.path.join(os.getcwd(), filename))
                    
                    edit_telegram_message(initial_message_id, f"✅ **Selesai!**\nFile berhasil diunduh menggunakan Selenium.")
                    return filename
                
                # Update progress
                if os.path.exists(current_file_path):
                    downloaded_size = os.path.getsize(current_file_path)
                    if total_size_bytes > 0:
                        current_percent = int(downloaded_size / total_size_bytes * 100)
                        if current_percent >= last_percent_notified + 10 or current_percent == 100:
                            last_percent_notified = current_percent
                            progress_message = f"⬇️ **Mulai mengunduh...**\nUkuran file: `{total_size_human}`\n\nProgres: `{current_percent}%`"
                            edit_telegram_message(initial_message_id, progress_message)

            time.sleep(1)
            waited_time += 1
        
        raise Exception("Waktu unduhan habis.")
        
    except Exception as e:
        print(f"Terjadi kesalahan saat menggunakan Selenium untuk Pixeldrain: {e}")
        send_telegram_message(f"❌ Gagal mendapatkan URL unduhan Pixeldrain.\n\nDetail: {str(e)[:150]}...")
        driver.save_screenshot("pixeldrain_error_screenshot.png")
        return None
    finally:
        driver.quit()
        # Hapus direktori sementara
        shutil.rmtree(download_dir, ignore_errors=True)

def human_readable_size(size_bytes):
    if size_bytes is None or size_bytes == 0:
        return "0B"
    size_name = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return f"{s} {size_name[i]}"

# --- Logika Utama ---
formatted_url = f"`{mediafire_page_url.replace('http://', '').replace('https://', '')}`"
send_telegram_message(f"🔍 **Mulai memproses URL:**\n{formatted_url}")

is_mega_url = re.match(MEGA_URL_REGEX, mediafire_page_url)
is_pixeldrain_url = re.match(PIXELDRAIN_URL_REGEX, mediafire_page_url)
downloaded_filename = None

# Coba yt-dlp terlebih dahulu untuk SEMUA URL
download_url = get_download_url_with_yt_dlp(mediafire_page_url)

if download_url:
    downloaded_filename = download_file(download_url)
elif is_pixeldrain_url:
    downloaded_filename = get_download_url_from_pixeldrain(mediafire_page_url)

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

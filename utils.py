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

def send_progress_to_telegram(message_id, filename, current_size, total_size, status="⬇️ Download"):
    """Kirim notifikasi progres ke Telegram berdasarkan persentase."""
    percent = int((current_size/total_size)*100) if total_size else 0
    text = f"{status} `{{filename}}` — {{percent}}% ({{human_readable_size(current_size)}}/{{human_readable_size(total_size)}})"
    edit_telegram_message(message_id, text)

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
        path_parts = parsed_url.path.split('/'
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
    return f"{{s}} {{size_name[i]}}"

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
        last_notified_percent = 0
        message_id = send_telegram_message(f"⬇️ Download dimulai: '{output_filename}'")
        while time.time() - start_time < timeout:
            if os.path.exists(output_filename):
                current_size = os.path.getsize(output_filename)
                if total_size is not None and total_size > 0:
                    percent_now = int(current_size * 100 // total_size)
                    if percent_now >= last_notified_percent + 10 or percent_now == 100:
                        send_progress_to_telegram(message_id, output_filename, current_size, total_size)
                        last_notified_percent = percent_now
                # Kondisi selesai: file sudah ada DAN ukurannya sama atau file .aria2 hilang
                if (total_size is not None and current_size >= total_size):
                    print(f"File {output_filename} selesai. Menghentikan aria2c...")
                    process.terminate()
                    time.sleep(2)
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

# ... rest of your code unchanged ...

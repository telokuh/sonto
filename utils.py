import os
import subprocess
import requests
import time
import json
import re
import tempfile
import shutil
import glob
import math
import sys
from urllib.parse import urlparse, urlunparse, urlencode, parse_qs

# --- IMPOR BARU UNTUK PLAYWRIGHT ---
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
# ------------------------------------

# =========================================================
# KONSTANTA & KONFIGURASI
# =========================================================

BOT_TOKEN = os.environ.get("BOT_TOKEN")
OWNER_ID = os.environ.get("PAYLOAD_SENDER")
# Tentukan directory untuk download sementara (hanya untuk Playwright jika perlu)
TEMP_DOWNLOAD_DIR = tempfile.mkdtemp()

# =========================================================
# FUNGSI BANTUAN TELEGRAM & UMUM (TETAP SAMA)
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
        response_json = response.json()
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
    try:
        with requests.get(url, stream=True, timeout=30) as r:
            r.raise_for_status()
            if 'Content-Length' in r.headers:
                return int(r.headers['Content-Length'])
    except requests.exceptions.RequestException as e:
        print(f"❌ Gagal mendapatkan ukuran file: {e}")
    return None

def extract_filename_from_url_or_header(download_url):
    """Mendapatkan nama file dari header Content-Disposition atau fallback ke path URL."""
    file_name = None
    try:
        # Gunakan requests.head untuk mendapatkan header
        head_response = requests.head(download_url, allow_redirects=True, timeout=10)
        head_response.raise_for_status()
        
        cd_header = head_response.headers.get('Content-Disposition')
        if cd_header:
            # Mencari filename* (UTF-8) atau filename (simpel)
            fname_match = re.search(r'filename\*?=["\']?(?:utf-8\'\')?([^"\';]+)["\']?', cd_header, re.I)
            if fname_match:
                file_name = fname_match.group(1).strip()
                # Hapus karakter non-ASCII yang mungkin tersisa
                file_name = re.sub(r'[^\x00-\x7F]+', '', file_name)

        # Fallback terakhir jika header CD tidak ada atau gagal diuraikan
        if not file_name:
            url_path = urlparse(download_url).path
            file_name = url_path.split('/')[-1]
            
    except requests.exceptions.RequestException as e:
        print(f"Peringatan: Gagal mendapatkan header file dari URL. Fallback ke nama dari path URL. Detail: {e}")
        url_path = urlparse(download_url).path
        file_name = url_path.split('/')[-1]
        
    return file_name if file_name else "unknown_file"

# =========================================================
# FUNGSI DOWNLOAD UTAMA (ARIA2C & MEGATOOLS & YTDLP)
# =========================================================
# (Fungsi-fungsi ini TETAP sama dan bekerja dengan baik)

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
# FUNGSI PLAYWRIGHT (MENGGANTIKAN SEMUA FUNGSI SELENIUM)
# =========================================================

def process_playwright_download(p, url, initial_message_id):
    """
    Menangani SourceForge, Mediafire, Gofile, dan ApkAdmin menggunakan Playwright.
    Mengutamakan ekstraksi link langsung untuk diserahkan ke aria2c.
    """
    browser = None
    try:
        # Menggunakan Chromium dan mode Headless
        browser = p.chromium.launch(headless=True)
        # Membuat konteks browser dengan pengaturan unduhan khusus
        context = browser.new_context(
            ignore_https_errors=True,
            java_script_enabled=True,
            # Playwright akan mendownload ke TEMP_DOWNLOAD_DIR jika tidak dicegat
            accept_downloads=True, 
            downloads_path=TEMP_DOWNLOAD_DIR, 
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        )
        page = context.new_page()
        page.set_default_timeout(30000) # 30 detik timeout default
        
        downloaded_filename = None
        
        # --- LOGIKA KHUSUS: SOURCEFORGE (Ekstraksi List Mirror) ---
        if "sourceforge" in url:
            
            def source_url(download_url):
                parsed_url = urlparse(download_url)
                path_parts = parsed_url.path.split('/')
                project_name = path_parts[2]
                file_path = '/'.join(path_parts[4:]) # Sesuaikan index untuk mendapatkan path file yang benar
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
            
            edit_telegram_message(initial_message_id, f"🔍 **[SourceForge Mode]** Mengekstrak daftar mirror...")
            
            mirror_url = source_url(url)
            page.goto(mirror_url)
            
            # 1. Ambil ID Mirror
            page.wait_for_selector("ul#mirrorList > li", state="visible")
            list_items = page.locator("ul#mirrorList > li").all()
            li_id = [item.get_attribute("id") for item in list_items if item.get_attribute("id")]
            
            # 2. Ambil Nama File dan Base Link
            page.goto(url)
            page.wait_for_selector("#remaining-buttons > div.large-12 > a.button.green", state="visible")
            download_button = page.locator("#remaining-buttons > div.large-12 > a.button.green")
            
            # Gunakan textContent untuk mendapatkan nama file
            aname_locator = page.locator("#downloading > div.content > div.file-info > div")
            aname = aname_locator.text_content() if aname_locator else "sourceforge_file"
            
            ahref = download_button.get_attribute('href')
            
            if not ahref or not li_id:
                raise Exception("Gagal mendapatkan link dasar atau ID mirror SourceForge.")
            
            # 3. Buat Daftar URL Download Lengkap
            download_urls = [set_url(ahref, 'use_mirror', mirror_id) for mirror_id in li_id]
            
            # 4. Panggil aria2c
            edit_telegram_message(initial_message_id, f"⬇️ **Memulai unduhan dengan `aria2c`...**\nFile: `{aname}`")
            downloaded_filename = download_file_with_aria2c(download_urls, aname)
            
        # --- LOGIKA KHUSUS: APK ADMIN (2-Step Form Submit) ---
        elif "apkadmin" in url:
            edit_telegram_message(initial_message_id, "⬇️ **[Apk Admin Mode]** Mencari dan mengirimkan FORM Step 1...")
            
            page.goto(url)
            
            # 1. Kirimkan FORM
            # Selector untuk FORM (atau tombol submit yang ada di dalamnya)
            SELECTOR_FORM = "form[name='F1']"
            page.wait_for_selector(SELECTOR_FORM, state="visible")
            
            # Playwright tidak memiliki .submit() untuk form Locator, jadi kita klik elemen submit di dalamnya atau menjalankan script
            # Namun, karena ini adalah form submit klasik yang memicu navigasi, kita akan klik tombol di dalamnya
            # Jika form tidak punya tombol, ini akan gagal. Kita coba klik tombol apapun yang ada.
            try:
                page.click(f"{SELECTOR_FORM} input[type='submit'], {SELECTOR_FORM} button[type='submit'], {SELECTOR_FORM} a", timeout=10000)
            except PlaywrightTimeoutError:
                # Fallback: Coba submit via JS
                page.evaluate(f"document.querySelector('{SELECTOR_FORM}').submit()")
            
            
            # 2. Tunggu dan Klik Tombol Download Kedua (Final) di Halaman Baru
            SELECTOR_STEP_2 = "#container > div.download-file.step-2 > div.a-spot.text-align-center > div > a"
            
            edit_telegram_message(initial_message_id, "⬇️ **[Apk Admin Mode]** Halaman kedua dimuat. Mencari tombol Step 2 (Max 30 detik)...")
            
            # Tunggu navigasi selesai dan tombol final muncul
            page.wait_for_selector(SELECTOR_STEP_2, state="visible", timeout=30000)
            
            # Ekstraksi URL Langsung untuk diserahkan ke aria2c
            download_button = page.locator(SELECTOR_STEP_2)
            final_download_url = download_button.get_attribute('href')
            
            if not final_download_url:
                raise Exception("Gagal mengekstrak URL download final dari tombol ApkAdmin.")
            
            # 3. Mendapatkan Nama File dan Panggil aria2c
            file_name = extract_filename_from_url_or_header(final_download_url)
            
            edit_telegram_message(initial_message_id, f"⬇️ **Memulai unduhan dengan `aria2c`...**\nFile: `{file_name}`")
            downloaded_filename = download_file_with_aria2c([final_download_url], file_name)
            
        # --- LOGIKA KHUSUS: MEDIAFIRE (Form Submit + Ekstraksi Link) ---
        elif "mediafire" in url:
            edit_telegram_message(initial_message_id, "⬇️ **[MediaFire Mode]** Mencari tombol download...")
            page.goto(url)
            
            # Selektor tombol download di MediaFire
            SELECTOR_BUTTON = "#downloadButton"
            
            # Tunggu tombol muncul
            page.wait_for_selector(SELECTOR_BUTTON, state="visible")
            
            download_button = page.locator(SELECTOR_BUTTON)
            final_download_url = download_button.get_attribute('href')
            
            if not final_download_url or final_download_url.startswith('javascript:'):
                # Jika link tidak langsung (Mediafire kadang-kadang menggunakan form/js click)
                edit_telegram_message(initial_message_id, "⚠️ **[MediaFire Mode]** Link tidak langsung. Mencoba klik tombol...")
                
                # Memantau respons yang berisi file (biasanya respons terakhir adalah file)
                # Gunakan event response untuk mencegat URL
                final_download_url = None
                file_name = None
                
                # Menggunakan event handler request/response untuk menangkap pengalihan terakhir
                def handle_response(response):
                    nonlocal final_download_url, file_name
                    # Hanya fokus pada URL yang responsnya berupa file
                    if response.url.endswith(('.zip', '.rar', '.7z', '.exe', '.apk', '.mp4', '.pdf', '.iso', '.bin', '.gz', '.tgz', '.tar')) or response.url.endswith(('/file', '/dl')):
                        if 'content-disposition' in response.headers:
                            final_download_url = response.url
                            file_name = extract_filename_from_url_or_header(final_download_url)
                            # Hapus event handler setelah menemukan link
                            page.remove_listener("response", handle_response)

                page.on("response", handle_response)
                
                # Klik tombol
                page.click(SELECTOR_BUTTON)
                page.wait_for_timeout(5000) # Beri waktu 5 detik untuk pengalihan
                
                if not final_download_url:
                    # Fallback: Ambil href tombol setelah klik (jika berubah)
                    final_download_url = page.locator(SELECTOR_BUTTON).get_attribute('href')
            
            if not final_download_url:
                raise Exception("Gagal mendapatkan URL download langsung MediaFire.")

            # 4. Mendapatkan Nama File dan Panggil aria2c
            file_name = extract_filename_from_url_or_header(final_download_url)
            
            edit_telegram_message(initial_message_id, f"⬇️ **Memulai unduhan dengan `aria2c`...**\nFile: `{file_name}`")
            downloaded_filename = download_file_with_aria2c([final_download_url], file_name)
            
        # --- LOGIKA KHUSUS: GOFILE (Ekstraksi Link Langsung) ---
        elif "gofile" in url:
            # Gofile butuh 1-step click untuk memunculkan link download
            edit_telegram_message(initial_message_id, "⬇️ **[Gofile Mode]** Mencari tombol download...")
            page.goto(url)
            
            # Selektor Tombol Download Gofile
            download_button_selector = "button.download-btn" 
            
            # Tunggu tombol muncul
            page.wait_for_selector(download_button_selector, state="visible")
            
            download_button = page.locator(download_button_selector)
            
            # Memantau event download untuk mendapatkan URL dan nama file
            with page.expect_download(timeout=30000) as download_info:
                download_button.click()
                
            download = download_info.value
            final_download_url = download.url
            file_name = download.suggested_filename
            
            if not final_download_url:
                raise Exception("Gagal mendapatkan URL download langsung Gofile.")
                
            # Gofile mungkin menggunakan download API Playwright, jadi kita cek dulu
            if download:
                # Gunakan Playwright untuk mengunduh dan menyimpannya (untuk kasus yang tidak bisa menggunakan aria2c)
                edit_telegram_message(initial_message_id, f"⬇️ **[Gofile Mode]** Unduhan dipicu. Playwright akan mengelola file.")
                
                # Menyimpan file yang diunduh (Playwright)
                download_path = os.path.join(os.getcwd(), file_name)
                download.save_as(download_path)
                
                downloaded_filename = file_name
                file_size = os.path.getsize(downloaded_filename)
                edit_telegram_message(initial_message_id, f"✅ **Gofile: Unduhan selesai!**\nFile: `{downloaded_filename}` ({human_readable_size(file_size)})\n\n**➡️ Mulai UPLOADING...**")
                
            else:
                # Fallback ke aria2c jika event download tidak terpicu
                file_name = extract_filename_from_url_or_header(final_download_url)
                edit_telegram_message(initial_message_id, f"⬇️ **Memulai unduhan dengan `aria2c`...**\nFile: `{file_name}`")
                downloaded_filename = download_file_with_aria2c([final_download_url], file_name)
            
        else:
            raise ValueError("URL tidak didukung oleh proses Playwright ini.")
            
        return downloaded_filename
        
    except PlaywrightTimeoutError as e:
        print(f"❌ Playwright Timeout: {e}")
        # Coba ambil screenshot untuk debugging
        page.screenshot(path="debug_timeout.png")
        print("Screenshot disimpan di debug_timeout.png")
        raise Exception(f"Playwright Timeout! Gagal menemukan elemen: {e}")
        
    except Exception as e:
        print(f"❌ Playwright Gagal: {e}")
        raise
        
    finally:
        if browser:
            browser.close()
            

# =========================================================
# FUNGSI UTAMA (ORCHESTRATOR) - Menggunakan Wrapper Sync Playwright
# =========================================================

def main_downloader_async(url, initial_message_id):
    """
    Fungsi utama (async) yang menjalankan logika Playwright.
    """
    downloaded_filename = None
    
    # 1. LOGIKA MEGATOOLS (MEGA)
    if "mega.nz" in url:
        downloaded_filename = download_file_with_megatools(url)
        
    # 2. LOGIKA YT-DLP (Google Drive)
    elif any(d in url for d in ["drive.google.com", "googledrive.com"]):
        downloaded_filename = download_with_yt_dlp(url)
        
    # 3. LOGIKA PIXELDRAIN (API + Aria2c)
    elif "pixeldrain" in url:
        print("Mode: Pixeldrain (Ambil Info File)")
        file_id_match = re.search(r'pixeldrain\.com/(u|l|f)/([a-zA-Z0-9]+)', url)
        if not file_id_match: raise ValueError("URL Pixeldrain tidak valid.")
        file_id = file_id_match.group(2)
        info_url = f"https://pixeldrain.com/api/file/{file_id}/info"
        edit_telegram_message(initial_message_id, f"🔍 **Mendapatkan informasi file dari Pixeldrain...** ID: `{file_id}`")
        try:
            info_resp = requests.get(info_url, timeout=10)
            info_resp.raise_for_status()
            file_info = info_resp.json()
        except requests.exceptions.RequestException as e:
            raise Exception(f"Gagal koneksi ke API Pixeldrain: {e}")
        
        filename = file_info.get('name', f"pixeldrain_download_{file_id}")
        download_url = f"https://pixeldrain.com/api/file/{file_id}?download"
        
        edit_telegram_message(initial_message_id, f"⬇️ **Memulai unduhan dengan `aria2c`...**\nFile: `{filename}`")
        downloaded_filename = download_file_with_aria2c([download_url], filename)
        
        if downloaded_filename:
            edit_telegram_message(initial_message_id, f"✅ **Pixeldrain: Unduhan selesai!**\nFile: `{downloaded_filename}`\n\n**➡️ Mulai UPLOADING...**")
            with open("downloaded_filename.txt", "w") as f: f.write(downloaded_filename)
        
    # 4. LOGIKA PLAYWRIGHT (SourceForge, Gofile, Mediafire, ApkAdmin)
    elif any(d in url for d in ["sourceforge", "gofile", "mediafire", "apkadmin"]):
        
        edit_telegram_message(initial_message_id, "⏳ **[Mode Playwright]** Menginisialisasi browser headless...")
        
        with sync_playwright() as p:
            downloaded_filename = process_playwright_download(p, url, initial_message_id)
            
    else:
        # Fallback untuk URL unduhan langsung
        edit_telegram_message(initial_message_id, "⬇️ **[Mode Default]** Mencoba unduhan langsung dengan `aria2c`...")
        file_name = extract_filename_from_url_or_header(url)
        downloaded_filename = download_file_with_aria2c([url], file_name)

        if downloaded_filename:
            edit_telegram_message(initial_message_id, f"✅ **Unduhan Langsung: Selesai!**\nFile: `{downloaded_filename}`\n\n**➡️ Mulai UPLOADING...**")
            with open("downloaded_filename.txt", "w") as f: f.write(downloaded_filename)
            
    return downloaded_filename
    
def downloader(url):
    """
    Fungsi utama sinkron yang memanggil fungsi asinkron.
    """
    initial_message_id = send_telegram_message(f"⏳ **Menganalisis URL...**\nURL: `{url}`")
    downloaded_filename = None
    
    try:
        downloaded_filename = main_downloader_async(url, initial_message_id)
        
    except Exception as e:
        print(f"❌ Unduhan utama gagal: {e}")
        edit_telegram_message(initial_message_id, f"❌ **Unduhan GAGAL!**\nDetail: {str(e)[:150]}...")
        downloaded_filename = None
        
    finally:
        # Bersihkan folder temp SELALU
        shutil.rmtree(TEMP_DOWNLOAD_DIR, ignore_errors=True)
        return downloaded_filename

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

# Dapatkan URL halaman MediaFire dari environment variable
mediafire_page_url = os.environ.get("MEDIAFIRE_PAGE_URL")

if not mediafire_page_url:
    print("Error: MEDIAFIRE_PAGE_URL environment variable not set.")
    exit(1)

def get_download_url_with_yt_dlp(url):
    print("Mencoba mendapatkan URL unduhan dengan yt-dlp...")
    try:
        result = subprocess.run(
            ['yt-dlp', '--get-url', url],
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
    except FileNotFoundError:
        print("yt-dlp tidak ditemukan.")
    
    return None

def get_download_url_with_selenium(url):
    print("yt-dlp gagal. Menggunakan Selenium sebagai cadangan...")
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
            time.sleep(5)
            final_url = driver.current_url
            if final_url != url:
                print("Selenium berhasil menemukan URL redirect.")
                return final_url
            else:
                raise Exception("Gagal menemukan URL unduhan dengan Selenium.")
    except Exception as e:
        print(f"Terjadi kesalahan saat menggunakan Selenium: {e}")
        driver.save_screenshot("error_screenshot.png")
        print("Screenshot error_screenshot.png telah dibuat.")
        return None
    finally:
        driver.quit()

def download_file(url):
    try:
        response = requests.get(url, stream=True)
        response.raise_for_status()
        
        # Ekstrak nama file dari header Content-Disposition atau URL
        filename = response.headers.get('Content-Disposition')
        if filename:
            filename = filename.split('filename=')[1].strip('"')
        else:
            filename = url.split('/')[-1]
        
        # Jika nama file terlalu pendek atau tidak valid, gunakan nama default
        if len(filename.split('.')) < 2:
            filename = "downloaded_file" + os.path.splitext(url)[-1]
        
        print(f"Mulai mengunduh file: {filename}")
        with open(filename, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        print(f"File berhasil diunduh sebagai: {filename}")
        return filename
    except requests.exceptions.RequestException as e:
        print(f"Gagal mengunduh file: {e}")
        return None

# --- Logika Utama ---
download_url = get_download_url_with_yt_dlp(mediafire_page_url)
if not download_url:
    download_url = get_download_url_with_selenium(mediafire_page_url)

if download_url:
    downloaded_filename = download_file(download_url)
    if downloaded_filename:
        with open("downloaded_filename.txt", "w") as f:
            f.write(downloaded_filename)
else:
    print("Tidak dapat menemukan URL unduhan. Proses dihentikan.")
    exit(1)

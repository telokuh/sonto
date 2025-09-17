import os
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

# Konfigurasi Selenium
service = Service(ChromeDriverManager().install())
options = webdriver.ChromeOptions()
options.add_argument('--headless') # Jalankan di background tanpa membuka browser
options.add_argument('--no-sandbox')
options.add_argument('--disable-dev-shm-usage')

driver = webdriver.Chrome(service=service, options=options)

try:
    print(f"Mengunjungi: {mediafire_page_url}")
    driver.get(mediafire_page_url)


    download_button_selector = "a[id*='downloadButton']" # Mencari link yang mengarah ke '/download/'

    # Tunggu hingga tombol unduh terlihat dan dapat diklik
    download_button = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, download_button_selector))
    )
    download_button.click()
    time.sleep(2)
    # Dapatkan URL unduhan sebelum mengklik (terkadang URL sudah tersedia di atribut href)
    # Jika tidak, Anda perlu mengklik tombolnya terlebih dahulu.
    # Mari kita coba mengambil URL sebelum mengklik, jika itu adalah link unduhan langsung.
    download_url_d = download_button.get_attribute("href")
    
    if download_url_d:
        print(f"URL Unduhan Ditemukan: {download_url_d}")
        # Simpan URL unduhan ke file
        with open("download_link.txt", "w") as f:
            f.write(download_url_d)
        print("URL unduhan telah disimpan ke download_link.txt")

except Exception as e:
    print(f"Terjadi kesalahan: {e}")
    # Jika ada error, cetak screenshot untuk debugging
    driver.save_screenshot("error_screenshot.png")
    print("Screenshot error_screenshot.png telah dibuat.")
    exit(1)
finally:
    driver.quit()

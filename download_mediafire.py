import os
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

# Ambil URL MediaFire dari environment variable
mediafire_url = os.environ.get('MEDIAFIRE_PAGE_URL')

if not mediafire_url:
    print("Error: MEDIAFIRE_URL environment variable not set.")
    exit(1)

# Konfigurasi Selenium
# webdriver-manager akan otomatis mengunduh ChromeDriver yang sesuai
service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service)

try:
    print(f"Membuka URL: {mediafire_url}")
    driver.get(mediafire_url)
    time.sleep(5) # Beri waktu halaman untuk memuat sepenuhnya

    # Cari tombol unduh berdasarkan ID 'downloadButton'
    # Kadang ID ini bisa berubah, jadi pastikan ini selector yang valid
    download_button = driver.find_element(By.ID, 'downloadButton')
    print("Tombol unduh ditemukan. Mengklik tombol...")

    # Klik tombol unduh
    download_button.click()
    time.sleep(5) # Beri waktu URL unduhan muncul setelah klik

    # Cari elemen yang berisi link unduhan setelah tombol diklik
    # Anda mungkin perlu memeriksa struktur HTML halaman setelah klik untuk selector yang tepat.
    # Saya berasumsi link ada di dalam tag <a> dengan atribut 'href' yang bukan 'javascript:void(0)'
    download_link_element = driver.find_element(By.XPATH, "//a[@href and @href!='javascript:void(0)']")
    direct_download_url = download_link_element.get_attribute('href')

    if direct_download_url:
        print(f"URL Unduhan Langsung Ditemukan: {direct_download_url}")

        # Simpan URL unduhan ke file download_link.txt
        with open("download_link.txt", "w") as f:
            f.write(direct_download_url)
        print("URL unduhan telah disimpan ke download_link.txt")
    else:
        print("Tidak dapat menemukan URL unduhan langsung setelah mengklik tombol.")

except Exception as e:
    print(f"Terjadi error: {e}")

finally:
    print("Menutup browser...")
    driver.quit()

import os
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# Dapatkan URL MediaFire dari environment variable
mediafire_url = os.environ.get('MEDIAFIRE_PAGE_URL')

if not mediafire_url:
    print("Error: MEDIAFIRE_URL environment variable not set.")
    exit(1)

# Konfigurasi Selenium untuk berjalan di GitHub Actions
# Kita akan menggunakan Chrome yang dikelola oleh webdriver-manager
# dan memastikan user-data-dir unik atau tidak digunakan
options = webdriver.ChromeOptions()
# Opsi ini penting untuk menghindari error "user data directory is already in use"
# di lingkungan seperti GitHub Actions. Ini memaksa Chrome untuk menggunakan
# direktori sementara yang unik untuk setiap eksekusi.
options.add_argument("--user-data-dir=/tmp/user-data")
options.add_argument("--disable-gpu") # Penting untuk lingkungan tanpa GUI
options.add_argument("--no-sandbox") # Diperlukan di lingkungan Linux
options.add_argument("--disable-dev-shm-usage") # Diperlukan di lingkungan Linux
options.add_argument("--window-size=1920x1080") # Ukuran jendela default

# Gunakan Service object
service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service, options=options)

try:
    print(f"Membuka URL: {mediafire_url}")
    driver.get(mediafire_url)

    # Tunggu tombol unduh utama muncul dan bisa diklik
    # Menggunakan selector ID 'downloadButton' seperti yang Anda minta
    download_button_locator = (By.ID, "downloadButton")
    WebDriverWait(driver, 20).until(
        EC.element_to_be_clickable(download_button_locator)
    )

    # Cari tombol unduh berdasarkan ID
    download_button = driver.find_element(By.ID, "downloadButton")
    print("Tombol unduh ditemukan. Mengklik tombol...")

    # Klik tombol unduh. Ini akan memicu navigasi atau membuka tab baru
    # yang berisi URL unduhan langsung.
    driver.execute_script("arguments[0].click();", download_button)

    # Tunggu sebentar agar URL unduhan muncul.
    # Kita akan menunggu sampai ada elemen baru yang muncul atau URL berubah.
    # Jika tombol unduh mengarahkan ke halaman baru dengan URL unduhan langsung,
    # kita bisa menunggu elemen tertentu di halaman baru itu.
    # Karena deskripsi Anda adalah "setelah saya klik baru muncul url unduhan directnya",
    # ini mengindikasikan bahwa setelah klik, halaman mungkin me-redirect atau
    # menampilkan elemen lain yang berisi URL.
    # Jika URL langsung muncul di halaman yang sama atau halaman baru,
    # kita bisa menunggu URL di address bar.
    # Untuk kasus ini, kita akan tunggu beberapa detik agar redirect terjadi.
    time.sleep(5) # Beri waktu untuk redirect atau update halaman

    # Ambil URL unduhan langsung dari URL halaman saat ini
    # Ini akan bekerja jika setelah klik, halaman me-redirect ke URL unduhan
    # atau jika URL di address bar sudah menjadi URL unduhan langsung.
    download_url = driver.current_url
    print(f"URL unduhan didapatkan: {download_url}")

    # Simpan URL unduhan ke dalam file teks
    with open("download_link.txt", "w") as f:
        f.write(download_url)
    print("URL unduhan telah disimpan ke download_link.txt")

except Exception as e:
    print(f"Terjadi kesalahan: {e}")
    # Jika ada error, cetak screenshot untuk debugging
    driver.save_screenshot("error_screenshot.png")
    print("Screenshot error disimpan sebagai error_screenshot.png")
    exit(1)
finally:
    # Tutup browser
    driver.quit()
    print("Browser ditutup.")

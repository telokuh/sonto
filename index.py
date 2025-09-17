import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def get_mediafire_download_url(mediafire_url):
    """
    Menggunakan Selenium untuk mendapatkan URL unduhan sebenarnya dari halaman MediaFire.

    Args:
        mediafire_url (str): URL halaman MediaFire.

    Returns:
        str: URL unduhan sebenarnya, atau None jika tidak ditemukan.
    """
    options = webdriver.ChromeOptions()
    # Jalankan dalam mode headless agar tidak membuka jendela browser fisik
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu") # Penting untuk beberapa sistem

    # Gunakan webdriver-manager untuk mengelola chromedriver secara otomatis
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)

    download_url = None

    try:
        driver.get(mediafire_url)

        # Tunggu hingga elemen tombol unduh muncul dan dapat diklik
        # Kita akan mencari tombol berdasarkan ID, namun ID ini bisa berubah.
        # Jika tidak berfungsi, kita mungkin perlu mencari berdasarkan kelas CSS atau atribut lain.
        # Contoh umum untuk tombol unduh adalah 'downloadButton' atau sejenisnya.
        # Mari kita coba cari elemen yang memiliki teks 'Download' atau 'Unduh'.
        # Cara paling umum adalah mencari ID 'downloadButton' jika ada.
        # Jika ID 'downloadButton' tidak ada, kita bisa coba mencari elemen dengan atribut 'href' yang mengandung kata 'download'.

        # Mencoba mencari tombol berdasarkan ID jika ada
        try:
            download_button = WebDriverWait(driver, 15).until(
                EC.element_to_be_clickable((By.ID, "downloadButton"))
            )
            # Klik tombol unduh
            download_button.click()
            time.sleep(5) # Beri waktu untuk halaman memuat setelah diklik

            # Setelah diklik, URL unduhan bisa langsung muncul di atribut 'href' dari elemen '<a>' tertentu
            # atau kita perlu menunggu jeda sebentar dan URL tersebut muncul di 'window.location'.
            # Mari kita asumsikan URL unduhan yang sebenarnya muncul di atribut 'href' dari elemen baru
            # atau kita bisa mencoba mengambil URL dari 'window.location' setelah jeda.

            # Pendekatan yang lebih aman adalah menunggu sampai URL benar-benar berubah atau file mulai diunduh.
            # Namun, untuk workflow sederhana, kita bisa mencoba mengambil URL dari elemen yang mengarah ke pengunduhan.

            # Coba cari link yang mengarah ke file langsung setelah klik (biasanya akan mengarahkan ke file .zip, .rar, dll.)
            # Ini adalah tebakan yang baik jika tombolnya mengarah ke halaman lain atau langsung mengunduh.
            # Jika tombol unduh mengarah ke halaman lain, kita mungkin perlu mencari link di halaman tersebut.
            # Paling sering, setelah tombol diklik, tautan unduhan akan muncul di elemen '<a>' dengan atribut 'href' yang mengarah ke file yang dapat diunduh.
            # Mari kita coba mencari elemen 'a' yang atribut 'href' nya berakhir dengan ekstensi file umum atau berisi kata kunci 'download'.

            # Jika tombol 'downloadButton' mengarahkan ke halaman baru, kita perlu menunggu dan mencari link di halaman itu.
            # Jika tombol 'downloadButton' langsung memicu unduhan, kita mungkin perlu memeriksa 'window.location' atau
            # mencari elemen link unduhan yang baru muncul.

            # Mari kita coba pendekatan umum di mana tombol unduh mengarah ke URL unduhan langsung di atribut href.
            # Ini sering kali merupakan elemen 'a' di mana atribut 'href' mengandung URL unduhan yang sebenarnya.
            # Namun, MediaFire sering kali langsung mengunduh setelah tombol diklik.
            # Jika tombol tidak mengarahkan ke URL unduhan, kita mungkin perlu menggunakan pendekatan berbeda.

            # Alternatif: Jika tombol unduh langsung memicu pengunduhan, kita bisa coba mendeteksi ini.
            # Namun, untuk mendapatkan URL-nya, kita perlu cara lain.
            # Jika MediaFire menampilkan link unduhan baru setelah tombol diklik, kita bisa mencarinya.
            # Mari kita asumsikan URL unduhan ada di elemen 'a' yang muncul setelah tombol diklik.
            # Seringkali, elemen ini akan memiliki ID atau kelas tertentu.
            # Karena MediaFire sering melakukan redirect, kita bisa coba ambil URL dari 'driver.current_url' setelah beberapa saat.
            # Jika halaman diarahkan ke URL unduhan, ini akan berhasil.
            # Jika tombol hanya mengunduh tanpa redirect, ini tidak akan berhasil.

            # Mari kita coba pendekatan yang lebih sederhana: asumsikan tombol unduh mengarahkan ke URL sebenarnya.
            # Kadang-kadang tombolnya sendiri adalah link, atau link muncul setelah tombol diklik.
            # Mediafire sering kali mengarahkan langsung ke URL unduhan setelah mengklik tombol.
            # Jadi, kita bisa coba tunggu sebentar dan ambil URL dari `driver.current_url`.
            print("Tombol unduh ditemukan dan diklik. Menunggu URL unduhan...")
            time.sleep(5) # Beri waktu tambahan untuk navigasi
            download_url = driver.current_url
            print(f"URL unduhan terdeteksi: {download_url}")

            # Jika `driver.current_url` tidak langsung mengarah ke file, kita perlu mencari elemen 'a' yang berisi link unduhan.
            # Ini sering terjadi jika ada halaman perantara.
            # Contoh: mencari elemen dengan ID 'download-url' atau atribut spesifik.
            # Jika Anda melihat struktur HTML di browser developer tools, Anda bisa menyesuaikannya.

        except Exception as e:
            print(f"Tombol unduh dengan ID 'downloadButton' tidak ditemukan atau tidak dapat diklik: {e}")
            # Jika tombol tidak ditemukan, coba cari elemen 'a' lain yang mungkin merupakan tombol unduh.
            # Misalnya, cari berdasarkan teks.
            try:
                # Mencari elemen 'a' yang berisi teks 'Download' atau 'Unduh'
                # Ini bisa kurang spesifik, jadi perlu hati-hati.
                download_links = driver.find_elements(By.PARTIAL_LINK_TEXT, "Download")
                if not download_links:
                    download_links = driver.find_elements(By.PARTIAL_LINK_TEXT, "Unduh")

                if download_links:
                    print(f"Menemukan {len(download_links)} link unduhan. Mencoba mengklik yang pertama.")
                    # Coba klik link unduhan pertama yang ditemukan
                    # Kita perlu memastikan link ini benar-benar tombol unduhan utama
                    for link in download_links:
                        try:
                            # Beberapa link mungkin bukan tombol unduh, kita perlu memfilter
                            # Cek apakah elemen tersebut adalah 'a' dan memiliki atribut 'href'
                            if link.tag_name == 'a' and link.get_attribute('href'):
                                # Periksa apakah href terlihat seperti URL unduhan
                                href = link.get_attribute('href')
                                # Ini adalah heuristik, Anda mungkin perlu menyesuaikannya
                                if 'download' in href.lower() or any(href.lower().endswith(ext) for ext in ['.zip', '.rar', '.exe', '.pdf', '.mp4']):
                                    link.click()
                                    print("Mengklik link unduhan.")
                                    time.sleep(5) # Beri waktu untuk navigasi
                                    download_url = driver.current_url
                                    print(f"URL unduhan terdeteksi: {download_url}")
                                    break # Keluar setelah menemukan dan mengklik satu link
                        except Exception as click_error:
                            print(f"Gagal mengklik link: {click_error}")
                            continue # Coba link berikutnya jika ada error

                else:
                    print("Tidak ada link dengan teks 'Download' atau 'Unduh' yang ditemukan.")

            except Exception as e_find_link:
                print(f"Error saat mencari link unduhan alternatif: {e_find_link}")


    except Exception as e_page:
        print(f"Error saat mengakses atau memproses halaman MediaFire: {e_page}")
    finally:
        driver.quit() # Pastikan browser ditutup

    return download_url

if __name__ == "__main__":
    # Ganti dengan URL halaman MediaFire yang ingin Anda dapatkan URL unduhannya
    # Contoh URL (ini hanya contoh, mungkin sudah tidak berlaku atau mengarah ke file berbeda)
    test_mediafire_url = "https://www.mediafire.com/file/your_file_id/your_filename.zip/file" # GANTI DENGAN URL AKTUAL

    if test_mediafire_url == "https://www.mediafire.com/file/your_file_id/your_filename.zip/file":
        print("!!! HARAP GANTI 'test_mediafire_url' dengan URL MediaFire yang valid.")
    else:
        print(f"Mencoba mendapatkan URL unduhan dari: {test_mediafire_url}")
        actual_download_url = get_mediafire_download_url(test_mediafire_url)

        if actual_download_url:
            print("\nBerhasil mendapatkan URL unduhan:")
            print(actual_download_url)

            # Anda bisa menyimpan URL ini ke file, misalnya
            with open("download_link.txt", "w") as f:
                f.write(actual_download_url)
            print("URL unduhan disimpan ke 'download_link.txt'")
        else:
            print("\nGagal mendapatkan URL unduhan.")

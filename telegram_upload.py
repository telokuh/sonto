import os
import sys
from pyrogram import Client
from pyrogram.errors import FilePartInvalid, FloodWait
import time

# --- PENTING: IMPORT FUNGSI DARI UTILS.PY ---
# Asumsi Anda punya file utils.py di direktori yang sama
try:
    # Asumsi Anda menyimpan fungsi notifikasi di utils.py
    # Pastikan utils.py memiliki fungsi send_telegram_message dan edit_telegram_message
    from utils import send_telegram_message, edit_telegram_message 
except ImportError:
    # Fallback jika utils.py tidak ditemukan (hanya untuk debugging)
    print("❌ GAGAL IMPORT: Pastikan file utils.py ada dan berisi fungsi notifikasi.")
    # Mendefinisikan fungsi dummy agar skrip bisa berjalan
    def send_telegram_message(text): print(f"SEND_DUMMY: {text}"); return 123456
    def edit_telegram_message(id, text): print(f"EDIT_DUMMY: {text}")


# =========================================================
# KONFIGURASI
# =========================================================

# Variabel yang dibutuhkan dari environment (Secrets GitHub Actions)
BOT_TOKEN = os.environ.get("BOT_TOKEN")
API_ID = os.environ.get("API_ID")
API_HASH = os.environ.get("API_HASH")
OWNER_ID = os.environ.get("OWNER_ID") # Chat ID untuk notifikasi
FILENAME_MARKER = "downloaded_filename.txt"

# =========================================================
# FUNGSI UTAMA UPLOADER PYROGRAM
# =========================================================

def upload_large_file_with_pyrogram(file_path):
    """Mengunggah file hingga 4 GB menggunakan Pyrogram."""
    
    if not all([API_ID, API_HASH, BOT_TOKEN, OWNER_ID]):
        error_msg = "❌ Konfigurasi unggah (API_ID/API_HASH/BOT_TOKEN/OWNER_ID) tidak lengkap."
        print(error_msg)
        send_telegram_message(error_msg)
        return False

    owner_id = int(OWNER_ID)
    file_name = os.path.basename(file_path)
    file_size = os.path.getsize(file_path)
    
    # Inisialisasi Klien Bot (menggunakan nama sesi statis)
    app = Client(
        "gh_pyrogram_session", 
        api_id=int(API_ID), 
        api_hash=API_HASH, 
        bot_token=BOT_TOKEN,
    )

    def progress_callback(current, total):
        """Fungsi untuk menampilkan progress unggah ke Telegram."""
        # Logika 2X update progress (0 -> 50% -> 100%)
        last_percent = getattr(progress_callback, 'last_percent', 0)
        percent = round(current * 100 / total, 1)
        
        # Kirim update hanya pada 50% dan 100%
        should_update_50 = (percent >= 50 and last_percent < 50)
        should_update_100 = (percent >= 100)
        
        if should_update_50 or should_update_100:
            status_text = f"⬆️ **Mengunggah (Pyrogram)...**\nFile: `{file_name}`\nProgres: `{percent}%` ({current/1024/1024/1024:.2f}GB / {total/1024/1024/1024:.2f}GB)"
            edit_telegram_message(getattr(progress_callback, 'message_id', None), status_text)
            progress_callback.last_percent = percent
        
        # Jaga agar Pyrogram tidak spam log
        time.sleep(1)

    try:
        app.start()
        
        # Kirim pesan inisiasi
        initial_message = f"⬆️ **Memulai Unggah Pyrogram...**\nFile: `{file_name}`\nUkuran: {file_size/1024/1024/1024:.2f} GB"
        message_id = send_telegram_message(initial_message)
        
        # Simpan ID pesan agar progress_callback bisa mengeditnya
        progress_callback.message_id = message_id 
        
        print(f"Mulai unggah {file_name} ke chat ID: {owner_id}")
        
        # Mulai unggah file
        app.send_document(
            chat_id=owner_id,
            document=file_path,
            caption=f"✅ **{file_name}** (Unggahan 4GB) selesai!",
            progress=progress_callback
        )
        
        # Update final 100%
        edit_telegram_message(message_id, f"🎉 **Unggahan Selesai!**\nFile: `{file_name}`\n")
        app.stop()
        return True
        
    except FloodWait as e:
        error_msg = f"❌ **Unggahan GAGAL (FloodWait):** Tunggu {e.value} detik."
        print(error_msg)
        send_telegram_message(error_msg)
        app.stop()
        return False
    except FilePartInvalid as e:
        error_msg = f"❌ **Unggahan GAGAL (FilePartInvalid).** File > 4GB atau koneksi terputus. Detail: {e}"
        print(error_msg)
        send_telegram_message(error_msg)
        app.stop()
        return False
    except Exception as e:
        error_msg = f"❌ **Unggahan GAGAL (Pyrogram).** Error: {e}"
        print(error_msg)
        send_telegram_message(error_msg)
        try: app.stop() 
        except: pass
        return False

# =========================================================
# EKSEKUSI UTAMA
# =========================================================

if __name__ == '__main__':
    
    print("Memulai proses unggah Telegram...")
    
    # 1. Baca nama file dari file penanda
    actual_filename = None
    if os.path.exists(FILENAME_MARKER):
        with open(FILENAME_MARKER, 'r') as f:
            actual_filename = f.read().strip()
            
    if not actual_filename or not os.path.exists(actual_filename):
        error_msg = f"❌ Eksekusi uploader gagal: File `{actual_filename}` tidak ditemukan. Pastikan downloader.py berjalan duluan."
        print(error_msg)
        send_telegram_message(error_msg)
        sys.exit(1)

    print(f"File yang akan diunggah: {actual_filename}")
    
    # 2. Mulai unggah
    upload_success = upload_large_file_with_pyrogram(actual_filename)
    
    # 3. Bersihkan file
    if upload_success:
        try:
            os.remove(actual_filename)
            print(f"File lokal {actual_filename} telah dihapus.")
        except Exception as e:
            print(f"Gagal menghapus file lokal: {e}")
    
    # 4. Hapus file penanda (selalu)
    try:
        os.remove(FILENAME_MARKER)
    except Exception as e:
        print(f"Gagal menghapus file penanda {FILENAME_MARKER}: {e}")
        
    if not upload_success:
        sys.exit(1) # Keluar dengan kode error jika unggahan gagal

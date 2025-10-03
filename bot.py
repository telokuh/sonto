import os
import re
import requests
import threading
from pyrogram import Client, filters
from dotenv import load_dotenv
from flask import Flask, jsonify

# Muat variabel dari file .env
load_dotenv()

# Ambil token dari environment variables
API_ID = os.environ.get("API_ID")
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
OWNER_ID = os.environ.get("OWNER_ID") # Digunakan untuk validasi lokal jika perlu

# Konfigurasi GitHub Repository
GITHUB_REPO_OWNER = "telokuh"
GITHUB_REPO_NAME = "sonto"
GITHUB_EVENT_TYPE = "new_url_received" 

# Inisialisasi bot Pyrogram
pyrogram_app = Client(
    "my_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# Inisialisasi aplikasi Flask
flask_app = Flask(__name__)

# Endpoint untuk mengecek status server
@flask_app.route("/")
def home():
    return jsonify({"status": " running!"})

def run_flask():
    flask_app.run(host="0.0.0.0", port=8000)

# --- FUNGSI BANTUAN UNTUK MENGIRIM KE GITHUB ACTIONS ---
async def send_to_github_actions(message, url_or_command_text, extra_payload=None):
    """
    Mengirim event 'repository_dispatch' ke GitHub Actions.
    :param extra_payload: Dict opsional untuk data tambahan di client_payload.
    """
    
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "Authorization": f"token {GITHUB_TOKEN}", 
    }

    # Payload yang akan dikirim ke GitHub
    payload = {
        "event_type": GITHUB_EVENT_TYPE,
        "client_payload": {
            "url": url_or_command_text, 
            "sender": message.from_user.username or str(message.from_user.id),
            **(extra_payload or {}) # Menggabungkan payload tambahan
        }
    }
    
    await message.reply_text(f"Mengirim event ke GitHub: `{url_or_command_text}`")

    try:
        response = requests.post(
            f"https://api.github.com/repos/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}/dispatches",
            headers=headers,
            json=payload
        )

        if response.status_code == 204:
            await message.reply_text("📥 processing")
        else:
            await message.reply_text(
                f"❌ Gagal mengirim ke GitHub Actions. Status: {response.status_code}\nRespons: {response.text}"
            )
    except Exception as e:
        await message.reply_text(f"Terjadi kesalahan: {e}")



# --- HANDLER UNTUK PERINTAH /auth ---
@pyrogram_app.on_message(filters.command("auth") & filters.private & ~filters.me)
async def handle_auth_command(client, message):
    user_id = str(message.from_user.id)
    AUTH_COMMAND_TEXT = "auth" 
    
    await message.reply_text("Perintah /auth diterima. Memulai proses otorisasi...")
    
    # Kirim event dengan tambahan 'chat_id' dari pengguna yang menjalankan perintah
    await send_to_github_actions(
        message, 
        AUTH_COMMAND_TEXT, 
        extra_payload={"chat_id": user_id}
    )
     

# --- HANDLER UNTUK PESAN BERISI URL ---
@pyrogram_app.on_message(filters.text & filters.private & ~filters.me)
async def handle_url(client, message):
    text = message.text
    if message.command: # Hentikan jika ini adalah perintah (misalnya /auth)
        return
    # Deteksi URL hanya jika teks mengandung "http"
    if "http" in text:
        url = text
        await message.reply_text(f"URL terdeteksi: `{url}`\n")
        # Kirim URL normal tanpa payload tambahan
        await send_to_github_actions(message, url)
    else:
        # Jika bukan URL dan bukan perintah, abaikan (atau berikan balasan default)
        pass 



if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.start()

    pyrogram_app.run()

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
OWNER_ID = os.environ.get("OWNER_ID")

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

@pyrogram_app.on_message(filters.text & filters.private & ~filters.me)
async def handle_url(client, message):
    text = message.text

    # Deteksi URL hanya jika teks mengandung "http"
    if "http" in text:
        url = text
        await message.reply_text(f"URL terdeteksi: `{url}`\n")

        headers = {
            "Accept": "application/vnd.github.v3+json",
            "Authorization": f"token {GITHUB_TOKEN}",
        }

        payload = {
            "event_type": GITHUB_EVENT_TYPE,
            "client_payload": {
                "url": url,
                "sender": message.from_user.username or str(message.from_user.id)
            }
        }

        try:
            response = requests.post(
                f"https://api.github.com/repos/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}/dispatches",
                headers=headers,
                json=payload
            )

            if response.status_code == 204:
                await message.reply_text("📥 processing")
            else:
                await message.reply_text(f"❌ Gagal mengirim ke GitHub Actions. Status: {response.status_code}\nRespons: {response.text}")
        except Exception as e:
            await message.reply_text(f"Terjadi kesalahan: {e}")
    else:
        await message.reply_text("Maaf, saya hanya bisa memproses URL.")

if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.start()

    pyrogram_app.run()

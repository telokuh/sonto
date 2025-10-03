import os
import re
import requests
import threading
from pyrogram import Client, filters
from dotenv import load_dotenv
from flask import Flask, jsonify, request # <<< TAMBAH: request

# Muat variabel dari file .env
load_dotenv()

# Ambil token dan kredensial dari environment variables
API_ID = os.environ.get("API_ID")
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")

# Kredensial OAuth (Harus ada di .env)
CLIENT_ID = os.environ.get("CLIENT_ID")
CLIENT_SECRET = os.environ.get("CLIENT_SECRET")
REDIRECT_URI = os.environ.get("REDIRECT_URI") # URL publik bot Anda, mis: https://mybot.ngrok.io/oauth_callback

# Konfigurasi GitHub Repository
GITHUB_REPO_OWNER = os.environ.get("GITHUB_REPO_OWNER") or "telokuh"
GITHUB_REPO_NAME = os.environ.get("GITHUB_REPO_NAME") or "sonto"
GITHUB_EVENT_AUTH_INIT = "new_url_received" # Event untuk memicu auth.sh
GITHUB_EVENT_TOKEN_RECEIVED = "refresh_token_received" # Event dari Flask ke Actions

# Inisialisasi bot Pyrogram
pyrogram_app = Client(
    "my_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# Inisialisasi aplikasi Flask
flask_app = Flask(__name__)

# --- Fungsi Bantu: Menjalankan Flask ---
def run_flask():
    # Pastikan Flask dapat mengakses request, jika dijalankan di main thread, ini aman
    flask_app.run(host="0.0.0.0", port=8000)

# --- FUNGSI BANTUAN UNTUK MENGIRIM KE GITHUB ACTIONS ---
async def send_to_github_actions(message, url_or_command_text, extra_payload=None):
    """
    Mengirim event 'repository_dispatch' ke GitHub Actions.
    """
    
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "Authorization": f"token {GITHUB_TOKEN}", 
    }

    payload = {
        "event_type": GITHUB_EVENT_AUTH_INIT, 
        "client_payload": {
            "url": url_or_command_text, 
            "sender": message.from_user.username or str(message.from_user.id),
            **(extra_payload or {}) 
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
            await message.reply_text("📥 Memicu alur otorisasi di GitHub Actions...")
        else:
            await message.reply_text(
                f"❌ Gagal mengirim ke GitHub Actions. Status: {response.status_code}\nRespons: {response.text}"
            )
    except Exception as e:
        await message.reply_text(f"Terjadi kesalahan: {e}")


# --- ENDPOINT FLASK BARU: OAUTH CALLBACK ---
@flask_app.route("/oauth_callback")
def oauth_callback():
    auth_code = request.args.get('code')
    chat_id = request.args.get('state') 

    if not auth_code:
        return "❌ Otorisasi Gagal: Tidak ada kode yang diterima. Cek log Google Cloud Console.", 400

    if not all([CLIENT_ID, CLIENT_SECRET, REDIRECT_URI]):
        return "❌ Konfigurasi Server Gagal: Kredensial OAuth server tidak lengkap.", 500

    # 1. Tukar Kode untuk Refresh Token
    try:
        token_response = requests.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": auth_code,
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "redirect_uri": REDIRECT_URI,
                "grant_type": "authorization_code"
            }
        ).json()

        refresh_token = token_response.get("refresh_token")
        
        if not refresh_token:
             error_desc = token_response.get("error_description", "Refresh Token tidak ditemukan.")
             return f"❌ Penukaran Gagal: {error_desc}. Pastikan otorisasi meminta 'access_type=offline'.", 500

    except Exception as e:
        return f"❌ Kesalahan saat menukar token: {e}", 500

    # 2. Kirim Refresh Token ke GitHub Actions (Repository Dispatch)
    
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "Authorization": f"token {GITHUB_TOKEN}", 
    }
    payload = {
        "event_type": GITHUB_EVENT_TOKEN_RECEIVED, # Event untuk memicu job penyimpanan
        "client_payload": {
            "refresh_token": refresh_token,
            "sender_chat_id": chat_id, 
        }
    }
    
    gh_response = requests.post(
        f"https://api.github.com/repos/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}/dispatches",
        headers=headers,
        json=payload
    )

    # 3. Beri tahu pengguna di Telegram
    if gh_response.status_code == 204:
        if chat_id:
            try:
                # Menggunakan pyrogram_app.send_message harus berada di thread Pyrogram
                # Untuk kesederhanaan, di sini kita cetak dan asumsikan user melihat balasan Flask.
                # Jika bot Anda berjalan di mode async, ini perlu dijalankan dengan loop asyncio.
                print(f"Token untuk chat {chat_id} berhasil dikirim ke Actions.")
            except Exception as e:
                print(f"Gagal mengirim pesan ke chat ID {chat_id}: {e}")
        
        return "✅ Token Otorisasi Berhasil Diterima dan sedang diproses di GitHub Actions!", 200
    else:
        return f"❌ Gagal mengirim token ke GitHub Actions: {gh_response.status_code}", 500


# Endpoint untuk mengecek status server
@flask_app.route("/")
def home():
    return jsonify({"status": " running!"})

# --- HANDLER UNTUK PERINTAH /auth ---
@pyrogram_app.on_message(filters.command("auth") & filters.private & ~filters.me)
async def handle_auth_command(client, message):
    user_id = str(message.from_user.id)
    AUTH_COMMAND_TEXT = "auth" 
    
    await message.reply_text("Perintah /auth diterima. Memulai proses otorisasi...")
    
    # Kirim event untuk memicu auth.sh (Hanya untuk mengirim URL)
    await send_to_github_actions(
        message, 
        AUTH_COMMAND_TEXT, 
        extra_payload={"chat_id": user_id} 
    )
    
# --- HANDLER UNTUK PESAN BERISI URL ---
@pyrogram_app.on_message(filters.text & filters.private & ~filters.me)
async def handle_url(client, message):
    text = message.text
    if message.command: 
        return
    if "http" in text:
        url = text
        await message.reply_text(f"URL terdeteksi: `{url}`\n")
        await send_to_github_actions(message, url)
    else:
        pass 

if __name__ == "__main__":
    # Inisialisasi thread Flask
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.start()

    # Jalankan Pyrogram bot
    pyrogram_app.run()

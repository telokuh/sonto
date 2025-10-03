import os
import re
import requests
import threading
from pyrogram import Client, filters
from dotenv import load_dotenv
from flask import Flask, jsonify, request 
from pyrogram.enums import ParseMode
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
# URL publik bot Anda, mis: https://mybot.ngrok.io/oauth_callback
REDIRECT_URI = os.environ.get("REDIRECT_URI") 

# Konfigurasi GitHub Repository
GITHUB_REPO_OWNER = os.environ.get("GITHUB_REPO_OWNER") or "telokuh"
GITHUB_REPO_NAME = os.environ.get("GITHUB_REPO_NAME") or "sonto"
GITHUB_EVENT_AUTH_INIT = "new_url_received" 
GITHUB_EVENT_TOKEN_RECEIVED = "refresh_token_received" 
SCOPE = "https://www.googleapis.com/auth/drive.readonly" # Scope OAuth

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
    flask_app.run(host="0.0.0.0", port=8000)

# --- FUNGSI BANTUAN UNTUK MENGIRIM KE GITHUB ACTIONS (Hanya untuk URL Normal) ---
async def send_to_github_actions(message, url_or_command_text, extra_payload=None):
    """
    Mengirim event 'repository_dispatch' ke GitHub Actions (Khusus untuk URL download).
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
            await message.reply_text("📥 Memicu alur download di GitHub Actions...")
        else:
            await message.reply_text(
                f"❌ Gagal mengirim ke GitHub Actions. Status: {response.status_code}\nRespons: {response.text}"
            )
    except Exception as e:
        await message.reply_text(f"Terjadi kesalahan: {e}")


# --- ENDPOINT FLASK BARU: OAUTH CALLBACK (Tidak Berubah) ---
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
        "event_type": GITHUB_EVENT_TOKEN_RECEIVED, 
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
                # Mengirim pesan notifikasi sukses ke chat ID pengguna
                pyrogram_app.send_message(
                    chat_id=int(chat_id),
                    text="✅ **Token Otorisasi Berhasil!** Refresh Token Anda sudah diterima dan sedang disimpan di GitHub Secrets."
                )
            except Exception as e:
                print(f"Gagal mengirim pesan notifikasi ke chat ID {chat_id}: {e}")
        
        return "✅ Token Otorisasi Berhasil Diterima dan sedang diproses di GitHub Actions!", 200
    else:
        return f"❌ Gagal mengirim token ke GitHub Actions: {gh_response.status_code}", 500


# Endpoint untuk mengecek status server
@flask_app.route("/")
def home():
    return jsonify({"status": " running!"})

# --------------------------------------------------------------------------------------
# --- HANDLER UTAMA BARU: /auth (TANPA auth.sh) ---
@pyrogram_app.on_message(filters.command("auth") & filters.private & ~filters.me)
async def handle_auth_command(client, message):
    user_id = str(message.from_user.id)
    
    if not all([CLIENT_ID, REDIRECT_URI]):
        await message.reply_text("❌ Otorisasi Gagal: Konfigurasi CLIENT_ID atau REDIRECT_URI belum lengkap di lingkungan bot.")
        return

    # 1. Rangkai URL Otorisasi Google di bot
    AUTH_URL = (
        f"https://accounts.google.com/o/oauth2/v2/auth?"
        f"client_id={CLIENT_ID}&"
        f"redirect_uri={REDIRECT_URI}&"
        f"scope={SCOPE}&"
        f"response_type=code&"
        f"access_type=offline&"
        f"prompt=consent&"
        f"state={user_id}" # Menggunakan user_id sebagai 'state' untuk tracking
    )

    # 2. Buat Teks Pesan HTML
    formatted_auth_url = (
        f"<b>Perhatian! Klik link di bawah ini untuk Otorisasi:</b>\n\n"
        f"<code>{AUTH_URL}</code>\n\n"
        f"Anda akan dialihkan kembali ke server bot setelah otorisasi."
    )

    # 3. Kirim pesan
    try:
        await client.send_message(
            chat_id=user_id,
            text=formatted_auth_url,
            parse_mode=ParseMode.HTML
        )
        await message.reply_text("✅ Tautan otorisasi berhasil dikirim. Cek pesan terbaru Anda.")
    except Exception as e:
        await message.reply_text(f"❌ Gagal mengirim URL otorisasi: {e}")


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

import os
import re
import requests
from pyrogram import Client, filters
from dotenv import load_dotenv
load_dotenv()
# Ambil token dari environment variables atau secrets
API_ID = os.environ.get("API_ID")
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
print(API_ID)
# Ganti dengan username, nama repo, dan nama event yang kamu buat
GITHUB_REPO_OWNER = "telokuh"
GITHUB_REPO_NAME = "sonto"
GITHUB_EVENT_TYPE = "new_url_received"

app = Client(
    "my_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# Regex untuk mendeteksi URL
URL_REGEX = r"https?://(?:www\.)?[\w\d\-_]+\.\w+(?:/[\w\d\-_.~:/?#\[\]@!$&'()*+,;=]*)?"

@app.on_message(filters.text & filters.private)
async def handle_url(client, message):
    text = message.text
    urls = re.findall(URL_REGEX, text)

    if urls:
        for url in urls:
            await message.reply_text(f"URL terdeteksi: {url}\nMeneruskan ke GitHub Actions...")

            # Persiapan payload untuk GitHub
            headers = {
                "Accept": "application/vnd.github.v3+json",
                "Authorization": f"token {GITHUB_TOKEN}",
            }

            payload = {
                "event_type": GITHUB_EVENT_TYPE,
                "client_payload": {
                    "url": url,
                    "sender": message.from_user.username or message.from_user.id
                }
            }

            try:
                # Kirim request ke GitHub API
                response = requests.post(
                    f"https://api.github.com/repos/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}/dispatches",
                    headers=headers,
                    json=payload
                )

                if response.status_code == 204:
                    await message.reply_text("✅ Berhasil dikirim ke GitHub Actions!")
                else:
                    await message.reply_text(f"❌ Gagal mengirim ke GitHub Actions. Status: {response.status_code}")

            except Exception as e:
                await message.reply_text(f"Terjadi kesalahan: {e}")
    else:
        await message.reply_text("Maaf, saya hanya bisa memproses URL.")

app.run()

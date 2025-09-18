FROM python:3.10-slim

# Menetapkan direktori kerja di dalam container
WORKDIR /app

# Menyalin file requirements.txt ke dalam container
# File ini berisi daftar pustaka yang dibutuhkan bot
COPY oke.txt .

# Menginstal pustaka yang terdaftar di requirements.txt
RUN pip install --no-cache-dir -r oke.txt

# Menyalin semua file lain dari direktori lokal ke dalam container
# Ini termasuk bot.py dan .env
COPY . .

# Menentukan variabel lingkungan yang akan dibaca saat container berjalan
# Ini adalah praktik terbaik agar token dan kunci tidak terekspos langsung di Dockerfile
ENV TELEGRAM_API_ID=${TELEGRAM_API_ID}
ENV TELEGRAM_API_HASH=${TELEGRAM_API_HASH}
ENV TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN}
ENV GITHUB_TOKEN=${GITHUB_TOKEN}

# Menjalankan skrip bot saat container dijalankan
CMD ["python", "bot.py"]

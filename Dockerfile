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
EXPOSE 8000
# Menjalankan skrip bot saat container dijalankan
CMD ["python", "bot.py"]

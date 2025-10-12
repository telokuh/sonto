# Bagian 1: Base Image
# Menggunakan image resmi dari Deno yang sudah terinstal runtime Deno
FROM denoland/deno:latest

# Bagian 2: Direktori Kerja
# Menetapkan direktori kerja di dalam container
WORKDIR /app

# Bagian 3: Menyalin File
# Menyalin semua file dari direktori lokal (termasuk bot.ts) ke dalam container
# Jika kamu hanya ingin menyalin bot.ts: COPY bot.ts .
COPY . .

# Bagian 4: Port (Jika bot-mu adalah server web)
# Mengekspos port 8000 (sesuaikan jika bot Deno-mu menggunakan port lain)
EXPOSE 8000

# Bagian 5: Perintah Jalankan
# Menjalankan skrip bot.ts menggunakan Deno runtime.
# PENTING: Kamu harus menambahkan flag izin yang sesuai.
# Contoh: --allow-net (untuk koneksi jaringan), --allow-env (untuk membaca .env)
CMD ["deno", "run", "-A", "bot.ts"]

// mod.ts

// Impor modul yang dibutuhkan dari Deno Standard Library
import { serve } from "https://deno.land/std@0.211.0/http/server.ts";

// --- KONFIGURASI DAN KREDENSIAL ---

// Ambil semua variabel dari Environment Variables (Deno Deploy)
const BOT_TOKEN = Deno.env.get("BOT_TOKEN");
const GITHUB_TOKEN = Deno.env.get("GITHUB_TOKEN");
const CLIENT_ID = Deno.env.get("CLIENT_ID");
const CLIENT_SECRET = Deno.env.get("CLIENT_SECRET");
const REDIRECT_URI = Deno.env.get("REDIRECT_URI"); // URL publik bot Anda + /oauth_callback

// Konfigurasi GitHub Repository
const GITHUB_REPO_OWNER = Deno.env.get("GITHUB_REPO_OWNER") || "telokuh";
const GITHUB_REPO_NAME = Deno.env.get("GITHUB_REPO_NAME") || "sonto";
const GITHUB_EVENT_AUTH_INIT = "new_url_received";
const GITHUB_EVENT_TOKEN_RECEIVED = "refresh_token_received";
const GITHUB_DISPATCH_URL = `https://api.github.com/repos/${GITHUB_REPO_OWNER}/${GITHUB_REPO_NAME}/dispatches`;
const SCOPE = "https://www.googleapis.com/auth/drive"; // Scope OAuth

// Cek token kritis saat inisialisasi
if (!BOT_TOKEN) {
  console.error("KRITIS: BOT_TOKEN HILANG. Pengiriman pesan Telegram akan gagal.");
}
const TELEGRAM_API = `https://api.telegram.org/bot${BOT_TOKEN}`;


// --- FUNGSI BANTUAN API (DENGAN PENANGANAN ERROR JARINGAN) ---

/** Mengirim pesan sederhana kembali ke Telegram, menangkap kegagalan. */
async function sendMessage(chatId: number | string, text: string, parseMode: 'Markdown' | 'HTML' = 'Markdown') {
  if (!BOT_TOKEN) {
    console.error(`ERROR: Gagal mengirim ke Chat ${chatId}. BOT_TOKEN tidak tersedia.`);
    return;
  }
  
  const url = `${TELEGRAM_API}/sendMessage`;
  
  try {
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        chat_id: chatId,
        text: text,
        parse_mode: parseMode,
      }),
    });

    if (!response.ok) {
      const errorText = await response.text();
      console.error(`ERROR TELEGRAM API: Status ${response.status}. Respons: ${errorText}`);
    }
  } catch (error) {
    console.error("KESALAHAN JARINGAN saat MENGIRIM PESAN TELEGRAM:", error);
  }
}

/** Mengirim event repository_dispatch ke GitHub Actions. */
async function sendToGithubActions(eventType: string, clientPayload: Record<string, unknown>): Promise<Response | {status: number}> {
  if (!GITHUB_TOKEN) {
    console.error("ERROR: GITHUB_TOKEN tidak tersedia. Gagal mengirim event GitHub.");
    return { status: 500 };
  }

  const headers = {
    "Accept": "application/vnd.github.v3+json",
    "Authorization": `token ${GITHUB_TOKEN}`,
    "Content-Type": "application/json",
  };

  const payload = {
    event_type: eventType,
    client_payload: clientPayload,
  };

  try {
    const response = await fetch(GITHUB_DISPATCH_URL, {
      method: "POST",
      headers: headers,
      body: JSON.stringify(payload),
    });
    return response;
  } catch (error) {
    console.error("KESALAHAN JARINGAN saat MENGIRIM KE GITHUB ACTIONS:", error);
    return { status: 500 };
  }
}

/** Mengirim event download ke GitHub Actions */
async function triggerDownloadAction(chatId: number, userId: number, url: string, customMode: string) {
    await sendMessage(chatId, `URL terdeteksi: \`${url}\`\nMode: **${customMode}**`);
    
    const ghResponse = await sendToGithubActions(GITHUB_EVENT_AUTH_INIT, {
        url: url,
        sender: String(userId),
        mode: customMode, // Kirim mode yang dipilih
    });

    if (ghResponse.status === 204) {
        await sendMessage(chatId, "📥 Memicu alur download.");
    } else {
        await sendMessage(chatId, `❌ Gagal mengirim ke GitHub Actions. Status: ${ghResponse.status}`);
    }
}


// --- LOGIKA UTAMA: ENDPOINT WEBHOOK TELEGRAM (Path: /) ---

async function handleTelegramWebhook(update: any) {
  const message = update.message;
  if (!message) return;

  const chatId = message.chat.id;
  const userId = message.from.id;
  const text = message.text ? message.text.trim() : null;
  const firstName = message.from.first_name || "Pengguna";

  if (!text) return;

  const commandMatch = text.match(/^\/([a-zA-Z]+)/);
  const command = commandMatch ? commandMatch[1].toLowerCase() : null;
  
  // Pisahkan perintah dari sisa teks (argumen/URL)
  const args = text.substring(command ? text.indexOf(command) + command.length : 0).trim();


  // 1. Tangani Perintah /start
  if (command === 'start') {
    const responseText = (
        `Halo, **${firstName}**! 👋\n\n` +
        "Saya adalah bot webhook **Deno** Anda.\n" +
        "Gunakan `/tg [url]` untuk download ke Telegram atau `/gd [url]` untuk Google Drive."
    );
    await sendMessage(chatId, responseText);
    return;
  } 
  // 2. Tangani Perintah /help
  if (command === 'help') {
    const helpText = (
      `**Daftar Perintah Bot:**\n\n` +
      `• \`/start\` - Pesan sambutan.\n` +
      `• \`/help\` - Menampilkan daftar perintah ini.\n` +
      `• \`/tg [url]\` - Download file dan **unggah ke Telegram** (Maks 4GB).\n` + 
      `• \`/gd [url]\` - Download file dan **unggah ke Google Drive** (Perlu /auth).\n` +
      `• \`/auth\` - Memulai proses otorisasi **Google Drive** Anda.\n`
    );
    await sendMessage(chatId, helpText, 'Markdown');
    return;
  }
  // 3. Tangani Perintah /auth
  if (command === 'auth') {
      if (!CLIENT_ID || !REDIRECT_URI) {
          await sendMessage(chatId, "❌ Konfigurasi OAuth tidak lengkap.", 'Markdown');
          return;
      }

      const AUTH_URL = (
          `https://accounts.google.com/o/oauth2/v2/auth?` +
          `client_id=${CLIENT_ID}&` +
          `redirect_uri=${REDIRECT_URI}&` +
          `scope=${SCOPE}&` +
          `response_type=code&` +
          `access_type=offline&` +
          `prompt=consent&` +
          `state=${userId}`
      );

      const formattedAuthUrl = (
          `<b>Perhatian! Klik link di bawah ini untuk Otorisasi:</b>\n\n` +
          `<a href="${AUTH_URL}">KLIK UNTUK OTORISASI GOOGLE DRIVE</a>\n\n` +
          `URL: <code>${AUTH_URL}</code>\n\n`
      );

      await sendMessage(userId, formattedAuthUrl, 'HTML');
      await sendMessage(chatId, "✅ Tautan otorisasi berhasil dikirim. Cek pesan terbaru Anda.");
      return;
  }
  
  // --- LOGIKA UNTUK /tg dan /gd ---
  
  // 4. Tangani Perintah /tg [url] (Unggah ke Telegram)
  if (command === 'tg') {
      const url = args.split(/\s+/).find(arg => arg.includes('http'));
      if (!url) {
          await sendMessage(chatId, "❌ Harap berikan URL yang valid setelah perintah `/tg`.");
          return;
      }
      await triggerDownloadAction(chatId, userId, url, 'telegram');
      return;
  }
  
  // 5. Tangani Perintah /gd [url] (Unggah ke Google Drive)
  if (command === 'gd') {
      const url = args.split(/\s+/).find(arg => arg.includes('http'));
      if (!url) {
          await sendMessage(chatId, "❌ Harap berikan URL yang valid setelah perintah `/gd`.");
          return;
      }
      await triggerDownloadAction(chatId, userId, url, 'gdrive');
      return;
  }
  
  // 6. Tangani URL yang Masuk (Jika bukan perintah)
  if (text.includes("http") && !command) {
    await sendMessage(chatId, "❌ Harap gunakan perintah `/tg [url]` atau `/gd [url]` untuk memulai unduhan.");
    return;
  }
}

// --- LOGIKA KHUSUS: ENDPOINT OAUTH CALLBACK (Path: /oauth_callback) ---

async function handleOAuthCallback(req: Request, url: URL): Promise<Response> {
  const authCode = url.searchParams.get('code');
  const chatId = url.searchParams.get('state');

  if (!authCode || !CLIENT_ID || !CLIENT_SECRET || !REDIRECT_URI) {
    return new Response("❌ Otorisasi Gagal: Konfigurasi server atau kode otorisasi hilang.", { status: 400 });
  }

  // 1. Tukar Kode untuk Refresh Token
  try {
    const tokenUrl = "https://oauth2.googleapis.com/token";
    const tokenResponse = await fetch(tokenUrl, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({
        code: authCode,
        client_id: CLIENT_ID,
        client_secret: CLIENT_SECRET,
        redirect_uri: REDIRECT_URI,
        grant_type: "authorization_code"
      }).toString()
    });

    const tokenData = await tokenResponse.json();
    const refreshToken = tokenData.refresh_token;

    if (!refreshToken) {
        const errorDesc = tokenData.error_description || "Refresh Token tidak ditemukan.";
        return new Response(`❌ Penukaran Gagal: ${errorDesc}.`, { status: 500 });
    }

    // 2. Kirim Refresh Token ke GitHub Actions
    const ghResponse = await sendToGithubActions(GITHUB_EVENT_TOKEN_RECEIVED, {
        refresh_token: refreshToken,
        sender_chat_id: chatId,
    });
    
    // 3. Beri tahu pengguna di Telegram
    if (ghResponse.status === 204) {
        if (chatId) {
            await sendMessage(
                chatId,
                "✅ **Token Otorisasi Berhasil!** Refresh Token Anda sudah diterima dan sedang disimpan di GitHub Secrets.",
                'Markdown'
            );
        }
        return new Response("✅ Token Otorisasi Berhasil Diterima!", { status: 200 });
    } else {
        return new Response(`❌ Gagal mengirim token ke GitHub Actions: ${ghResponse.status}`, { status: 500 });
    }

  } catch (e) {
    console.error("Kesalahan fatal saat menukar token:", e);
    return new Response(`❌ Kesalahan internal saat menukar token.`, { status: 500 });
  }
}

// --- HANDLER UTAMA Deno ---

async function handler(req: Request): Promise<Response> {
  const url = new URL(req.url);

  // 1. Routing untuk OAuth Callback
  if (url.pathname === "/oauth_callback" && req.method === "GET") {
    return handleOAuthCallback(req, url);
  }

  // 2. Routing untuk Webhook Telegram
  if (req.method === "POST" && !url.pathname.includes('.')) {
    try {
      const update = await req.json();
      // Proses update secara asinkron (tidak memblokir)
      await handleTelegramWebhook(update);
      
      // PENTING: Selalu respons 200 OK agar Telegram menganggap update berhasil diterima.
      return new Response("Update diterima dan sedang diproses.", { status: 200 });
    } catch (error) {
      console.error("KESALAHAN FATAL: Gagal memproses JSON/Controller:", error);
      // Jika JSON gagal di-parse atau controller gagal, tetap respons 200 OK.
      return new Response("Kesalahan, tetapi diakui.", { status: 200 });
    }
  }

  // 3. Endpoint Status (GET /)
  if (url.pathname === "/" && req.method === "GET") {
     return new Response(JSON.stringify({ status: "running!" }), {
        headers: { "Content-Type": "application/json" },
        status: 200
     });
  }

  // 4. Default: Not Found
  return new Response("Endpoint Not Found", { status: 404 });
}

// Menjalankan Server Deno
console.log("Deno Webhook Server berjalan, siap menerima pesan.");
serve(handler);

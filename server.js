import crypto from "node:crypto";
import { existsSync } from "node:fs";
import { mkdir, unlink } from "node:fs/promises";
import path from "node:path";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import express from "express";
import multer from "multer";
import "dotenv/config";

const root = path.dirname(fileURLToPath(import.meta.url));
const port = Number(process.env.PORT || 3000);
const expectedApiKey = process.env.MONOFLOW_API_KEY;
const uploadDir = path.join(root, "uploads");
const app = express();
const upload = multer({
  dest: uploadDir,
  limits: { fileSize: 50 * 1024 * 1024 },
  fileFilter: (_request, file, callback) => callback(null, file.mimetype.startsWith("audio/")),
});

await mkdir(uploadDir, { recursive: true });
app.disable("x-powered-by");
app.use((request, response, next) => {
  const origin = process.env.CORS_ORIGIN || "*";
  response.setHeader("Access-Control-Allow-Origin", origin);
  response.setHeader("Access-Control-Allow-Headers", "Content-Type, x-api-key");
  response.setHeader("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
  if (request.method === "OPTIONS") return response.sendStatus(204);
  next();
});
app.use(express.json({ limit: "16kb" }));
app.use(express.static(root, { index: "index.html" }));

function isSupportedUrl(value) {
  try {
    const url = new URL(value);
    return ["youtube.com", "www.youtube.com", "youtu.be", "music.youtube.com", "tiktok.com", "www.tiktok.com"].includes(url.hostname);
  } catch {
    return false;
  }
}

function requireApiKey(request, response, next) {
  const provided = request.get("x-api-key");
  const matches = provided && expectedApiKey && provided.length === expectedApiKey.length &&
    crypto.timingSafeEqual(Buffer.from(provided), Buffer.from(expectedApiKey));
  if (!provided || (expectedApiKey && !matches)) {
    return response.status(401).json({ error: "API key tidak valid." });
  }
  next();
}

app.post("/api/connect", (request, response) => {
  const { userId, apiKey } = request.body || {};
  if (!userId || !apiKey || typeof userId !== "string" || typeof apiKey !== "string") {
    return response.status(400).json({ error: "User ID dan API key wajib diisi." });
  }
  if (expectedApiKey && apiKey !== expectedApiKey) {
    return response.status(401).json({ error: "API key tidak valid." });
  }
  return response.json({ connected: true, userId: userId.trim() });
});

app.post("/api/fetch", requireApiKey, (request, response) => {
  const { url } = request.body || {};
  if (typeof url !== "string" || !isSupportedUrl(url)) {
    return response.status(400).json({ error: "Gunakan URL YouTube, YouTube Music, atau TikTok yang valid." });
  }
  const output = path.join(uploadDir, `${crypto.randomUUID()}.%(ext)s`);
  const command = process.env.MONOFLOW_YTDLP_COMMAND || "python";
  const commandArgs = command === "python" ? ["-m", "yt_dlp"] : [];
  const child = spawn(command, [...commandArgs, "--no-playlist", "-x", "--audio-format", "mp3", "-o", output, url], { windowsHide: true });
  let errorOutput = "";
  let responded = false;
  child.stderr.on("data", (chunk) => { errorOutput += chunk.toString(); });
  child.on("error", () => {
    responded = true;
    return response.status(503).json({ error: "Python/yt-dlp belum terpasang di server." });
  });
  child.on("close", (code) => {
    if (responded) return;
    if (code !== 0) return response.status(502).json({ error: "Audio gagal diambil dari sumber.", detail: errorOutput.slice(-500) });
    const basename = path.basename(output).replace(".%(ext)s", ".mp3");
    return response.json({ ready: true, filename: basename, source: new URL(url).hostname });
  });
});

app.post("/api/upload", requireApiKey, upload.single("audio"), async (request, response) => {
  if (!request.file) return response.status(400).json({ error: "File audio wajib diisi." });
  return response.json({ uploaded: true, filename: request.file.originalname, size: request.file.size });
});

app.get("/api/audio/:filename", requireApiKey, (request, response) => {
  const filename = path.basename(request.params.filename);
  const file = path.join(uploadDir, filename);
  if (!existsSync(file)) return response.status(404).json({ error: "Audio tidak ditemukan." });
  return response.sendFile(file);
});

app.use((error, _request, response, _next) => {
  if (error instanceof multer.MulterError && error.code === "LIMIT_FILE_SIZE") return response.status(413).json({ error: "Ukuran audio maksimal 50 MB." });
  return response.status(400).json({ error: "Request tidak valid." });
});

app.listen(port, () => console.log(`MCHLERN Tools backend aktif di http://localhost:${port}`));

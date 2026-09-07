import base64
import hmac
import json
import os
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path

import requests
import yt_dlp
from flask import Flask, jsonify, request, send_from_directory

ROOT = Path(__file__).resolve().parent.parent
TEMP_DIR = ROOT / "uploads"
TEMP_DIR.mkdir(exist_ok=True)
COOKIE_PATH = Path(os.environ.get("DATA_DIR", str(ROOT))) / "youtube_cookies.txt"
COOKIE_PATH.parent.mkdir(exist_ok=True)
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024


def cookie_file():
    # Admin uploads on the persistent volume must override an older env value.
    if COOKIE_PATH.exists() and COOKIE_PATH.stat().st_size > 0:
        return str(COOKIE_PATH)
    encoded = os.environ.get("YOUTUBE_COOKIES", "").strip()
    if encoded:
        target = Path(tempfile.gettempdir()) / "mchlern-youtube-cookies.txt"
        try:
            decoded = base64.b64decode(encoded, validate=True)
        except (ValueError, base64.binascii.Error) as error:
            raise RuntimeError("YOUTUBE_COOKIES bukan base64 yang valid.") from error
        if b"# Netscape HTTP Cookie File" not in decoded[:5000] and b"\t.youtube.com\t" not in decoded:
            raise RuntimeError("YOUTUBE_COOKIES bukan export cookies.txt format Netscape.")
        target.write_bytes(decoded)
        return str(target)
    return None


def admin_authorized():
    configured = os.environ.get("ADMIN_PASSWORD", "")
    supplied = request.headers.get("x-admin-password", "")
    return bool(configured) and hmac.compare_digest(supplied, configured)


def supported_url(value):
    try:
        host = __import__("urllib.parse", fromlist=["urlparse"]).urlparse(value).hostname or ""
        return host.removeprefix("www.") in {"youtube.com", "youtu.be", "music.youtube.com", "tiktok.com"}
    except (TypeError, ValueError):
        return False


def ytdlp_options(output, audio=True, use_cookies=True):
    options = {
        "outtmpl": str(output),
        "quiet": True,
        "no_warnings": True,
        "retries": 2,
        "fragment_retries": 2,
        "socket_timeout": 30,
        "http_headers": {"User-Agent": "Mozilla/5.0", "Accept-Language": "en-US,en;q=0.9"},
    }
    if audio:
        options.update({
            "format": "bestaudio/best",
            "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3"}],
        })
    cookies = cookie_file() if use_cookies else None
    if cookies:
        options["cookiefile"] = cookies
    return options


@app.after_request
def cors(response):
    configured_origins = {
        item.strip()
        for item in os.environ.get("CORS_ORIGIN", "*").split(",")
        if item.strip().startswith(("http://", "https://")) or item.strip() == "*"
    }
    request_origin = request.headers.get("Origin", "")
    if "*" in configured_origins or not configured_origins:
        response.headers["Access-Control-Allow-Origin"] = "*"
    elif request_origin in configured_origins:
        response.headers["Access-Control-Allow-Origin"] = request_origin
    else:
        response.headers["Access-Control-Allow-Origin"] = next(iter(configured_origins))
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, x-api-key"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    if request.path.endswith((".js", ".css", ".html")):
        response.headers["Cache-Control"] = "no-store, max-age=0"
    return response


@app.route("/", methods=["GET"])
def health():
    return send_from_directory(ROOT, "index.html")


@app.route("/<path:filename>", methods=["GET"])
def frontend_asset(filename):
    if filename.startswith(("api/", "temp/")):
        return jsonify(error="Not found"), 404
    return send_from_directory(ROOT, filename)


@app.route("/api/connect", methods=["POST"])
def connect():
    data = request.get_json(silent=True) or {}
    user_id = str(data.get("userId", "")).strip()
    if not user_id.isdigit():
        return jsonify(error="User ID Roblox harus berupa angka."), 400
    try:
        profile = requests.get(f"https://users.roblox.com/v1/users/{user_id}", timeout=10)
        if not profile.ok:
            return jsonify(error="User ID Roblox tidak ditemukan."), 404
        profile = profile.json()
        thumb = requests.get(
            "https://thumbnails.roblox.com/v1/users/avatar-headshot",
            params={"userIds": user_id, "size": "150x150", "format": "Png", "isCircular": "true"},
            timeout=10,
        )
        data = thumb.json().get("data", []) if thumb.ok else []
        return jsonify(
            connected=True,
            userId=user_id,
            username=profile.get("name", ""),
            displayName=profile.get("displayName", ""),
            avatarUrl=data[0].get("imageUrl", "") if data else "",
        )
    except requests.RequestException:
        return jsonify(error="Layanan Roblox sedang tidak dapat dihubungi."), 502


@app.route("/api/fetch-yt", methods=["POST"])
def fetch_audio():
    data = request.get_json(silent=True) or {}
    url = str(data.get("url", "")).strip()
    if not supported_url(url):
        return jsonify(error="Gunakan link YouTube, YouTube Music, atau TikTok yang valid."), 400
    stem = f"yt_{uuid.uuid4().hex}"
    output = TEMP_DIR / stem
    last_error = ""
    is_tiktok = "tiktok.com" in url
    clients = [None] if is_tiktok else ["android_vr", "ios", "tv_embedded", "web", "mweb", "android_music"]
    cookie_modes = [True, False] if not is_tiktok else [False]
    for use_cookies in cookie_modes:
        for client in clients:
          try:
            options = ytdlp_options(output, audio=True, use_cookies=use_cookies)
            options["http_headers"] = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125 Safari/537.36",
                "Referer": "https://www.tiktok.com/" if is_tiktok else "https://www.youtube.com/",
                "Accept-Language": "en-US,en;q=0.9",
            }
            if is_tiktok:
                options["impersonate"] = "chrome"
            elif client:
                options["extractor_args"] = {"youtube": {"client": [client]}}
            with yt_dlp.YoutubeDL(options) as downloader:
                info = downloader.extract_info(url, download=True)
                title = info.get("title", "Audio") if info else "Audio"
                thumbnail = info.get("thumbnail", "") if info else ""
            audio_path = TEMP_DIR / f"{stem}.mp3"
            if not audio_path.exists():
                candidates = list(TEMP_DIR.glob(f"{stem}.*"))
                audio_path = next((item for item in candidates if item.suffix.lower() in {".mp3", ".m4a", ".webm", ".opus"}), audio_path)
            if not audio_path.exists():
                raise RuntimeError("File audio tidak berhasil dibuat.")
            return jsonify(title=title, thumbnail=thumbnail, filename=audio_path.name, audioUrl=f"/temp/{audio_path.name}", source=url)
          except Exception as error:
              last_error = str(error)
              continue
    message = last_error
    lowered = message.lower()
    if "bukan base64" in lowered or "bukan export" in lowered:
        message = "Format YOUTUBE_COOKIES di Railway tidak valid. Export ulang cookies.txt Netscape lalu encode base64."
    elif any(term in lowered for term in ("sign in", "bot", "confirm you're not", "cookies", "po token")):
        message = "YouTube menolak request. Cookie Railway mungkin expired; video publik akan dicoba tanpa cookie. Export cookies baru jika tetap gagal."
    elif any(term in lowered for term in ("private", "members-only", "age-restricted", "unavailable")):
        message = "Video tidak tersedia karena private, batas usia, member-only, atau region lock."
    else:
        message = "Audio gagal diambil dari link tersebut. Coba link publik lain."
    return jsonify(error=message), 502


@app.route("/api/admin/cookies", methods=["POST"])
def update_cookies():
    if not admin_authorized():
        return jsonify(error="Password admin salah atau belum dikonfigurasi."), 401
    upload = request.files.get("cookies")
    if not upload or not upload.filename:
        return jsonify(error="Upload file cookies.txt terlebih dahulu."), 400
    contents = upload.read()
    if b"# Netscape HTTP Cookie File" not in contents[:5000] and b"\t.youtube.com\t" not in contents:
        return jsonify(error="File harus berupa cookies.txt format Netscape."), 400
    COOKIE_PATH.write_bytes(contents)
    return jsonify(updated=True, message="Cookies aktif di server. Tidak perlu Railway API token.")


@app.route("/api/admin/cookies/status", methods=["GET"])
def cookies_status():
    if not admin_authorized():
        return jsonify(error="Password admin salah atau belum dikonfigurasi."), 401
    if not COOKIE_PATH.exists():
        return jsonify(active=False, source="none")
    return jsonify(active=True, source=str(COOKIE_PATH), size=COOKIE_PATH.stat().st_size)


@app.route("/temp/<path:filename>", methods=["GET"])
def temp_file(filename):
    return send_from_directory(TEMP_DIR, Path(filename).name, conditional=True)


def process_audio(source, speed, volume, pitch):
    output = TEMP_DIR / f"processed_{uuid.uuid4().hex}.mp3"
    speed = max(0.5, min(float(speed), 3.5))
    volume = max(0, min(float(volume) / 100, 2))
    pitch = max(0.1, min(float(pitch), 3.5))
    filters = [f"asetrate=44100*{pitch}", f"atempo={max(0.5, min(100, speed / pitch))}", "aresample=44100", f"volume={volume}"]
    command = ["ffmpeg", "-y", "-i", str(source), "-vn", "-af", ",".join(filters), "-codec:a", "libmp3lame", str(output)]
    subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    return output


@app.route("/api/upload", methods=["POST"])
def upload():
    api_key = (request.headers.get("x-api-key") or request.form.get("api_key", "")).strip()
    creator_id = request.form.get("creator_id", "").strip()
    if not api_key or not creator_id:
        return jsonify(error="API key Roblox dan User ID wajib diisi."), 400
    audio = request.files.get("audio")
    if not audio or not audio.filename:
        return jsonify(error="File audio wajib diisi."), 400
    source = TEMP_DIR / f"input_{uuid.uuid4().hex}{Path(audio.filename).suffix.lower()}"
    audio.save(source)
    processed = None
    try:
        processed = process_audio(source, request.form.get("speed", "1"), request.form.get("volume", "80"), request.form.get("pitch", "1"))
        payload = {"request": __import__("json").dumps({
            "assetType": "Audio",
            "displayName": request.form.get("title", Path(audio.filename).stem)[:50],
            "description": "MCHLERN UPLOADER",
            "creationContext": {"creator": {"userId": creator_id}},
        })}
        with processed.open("rb") as content:
            result = requests.post(
                "https://apis.roblox.com/assets/v1/assets",
                headers={"x-api-key": api_key},
                data=payload,
                files={"fileContent": (processed.name, content, "audio/mpeg")},
                timeout=90,
            )
        if not result.ok:
            return jsonify(error=f"Roblox API: {result.text[:500]}"), result.status_code
        body = result.json()
        asset_id = body.get("assetId") or body.get("path")
        if not asset_id:
            return jsonify(error="Roblox menerima upload tetapi tidak mengembalikan asset ID.", details=body), 502
        return jsonify(
            uploaded=True,
            assetId=asset_id,
            filename=audio.filename,
            thumbnail="https://media.discordapp.net/attachments/1522140461081432126/1546445784025792583/ChatGPT_Image_Sep_6_2026_09_43_19_PM.png?ex=6a9fcf5e&is=6a9e7dde&hm=a0c4bf964f43eaa55d1497541c8510c8179500e8bb9a595be93c6b52d9069eed&=&format=webp&quality=lossless&width=1024&height=1024",
        )
    except subprocess.CalledProcessError:
        return jsonify(error="FFmpeg gagal memproses audio."), 422
    except requests.RequestException:
        return jsonify(error="Roblox Open Cloud tidak dapat dihubungi."), 502
    except (ValueError, OSError) as error:
        return jsonify(error=f"Upload gagal diproses: {str(error)[:240]}"), 422
    finally:
        for item in (source, processed):
            if item and item.exists():
                item.unlink()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "3000")))

import base64
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
app = Flask(__name__)


def cookie_file():
    encoded = os.environ.get("YOUTUBE_COOKIES", "").strip()
    if not encoded:
        return None
    target = Path(tempfile.gettempdir()) / "mchlern-youtube-cookies.txt"
    target.write_bytes(base64.b64decode(encoded))
    return str(target)


def supported_url(value):
    try:
        host = __import__("urllib.parse", fromlist=["urlparse"]).urlparse(value).hostname or ""
        return host.removeprefix("www.") in {"youtube.com", "youtu.be", "music.youtube.com", "tiktok.com"}
    except (TypeError, ValueError):
        return False


def ytdlp_options(output, audio=True):
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
    cookies = cookie_file()
    if cookies:
        options["cookiefile"] = cookies
        options["extractor_args"] = {"youtube": {"player_client": ["web"]}}
    return options


@app.after_request
def cors(response):
    response.headers["Access-Control-Allow-Origin"] = os.environ.get("CORS_ORIGIN", "*")
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, x-api-key"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response


@app.route("/", methods=["GET"])
def health():
    return "MCHLERN TOOLS backend online"


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
    try:
        with yt_dlp.YoutubeDL(ytdlp_options(output)) as downloader:
            info = downloader.extract_info(url, download=True)
            title = info.get("title", "Audio") if info else "Audio"
        audio_path = TEMP_DIR / f"{stem}.mp3"
        if not audio_path.exists():
            candidates = list(TEMP_DIR.glob(f"{stem}.*"))
            audio_path = next((item for item in candidates if item.suffix.lower() in {".mp3", ".m4a", ".webm", ".opus"}), audio_path)
        if not audio_path.exists():
            raise RuntimeError("File audio tidak berhasil dibuat.")
        return jsonify(title=title, filename=audio_path.name, audioUrl=f"/temp/{audio_path.name}", source=url)
    except Exception as error:
        message = str(error)
        if any(term in message.lower() for term in ("sign in", "bot", "confirm you're not", "cookies")):
            message = "YouTube menolak request. Tambahkan YOUTUBE_COOKIES di Railway atau gunakan video publik."
        return jsonify(error=message), 502


@app.route("/temp/<path:filename>", methods=["GET"])
def temp_file(filename):
    return send_from_directory(TEMP_DIR, Path(filename).name, conditional=True)


def process_audio(source, speed, volume):
    output = TEMP_DIR / f"processed_{uuid.uuid4().hex}.mp3"
    speed = max(0.5, min(float(speed), 3.5))
    volume = max(0, min(float(volume) / 100, 2))
    filters = [f"volume={volume}"]
    remaining = speed
    while remaining > 2:
        filters.append("atempo=2")
        remaining /= 2
    while remaining < 0.5:
        filters.append("atempo=0.5")
        remaining /= 0.5
    filters.append(f"atempo={remaining}")
    command = ["ffmpeg", "-y", "-i", str(source), "-vn", "-af", ",".join(filters), "-codec:a", "libmp3lame", str(output)]
    subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    return output


@app.route("/api/upload", methods=["POST"])
def upload():
    api_key = request.headers.get("x-api-key", "").strip()
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
        processed = process_audio(source, request.form.get("speed", "1"), request.form.get("volume", "80"))
        payload = {"request": __import__("json").dumps({
            "assetType": "Audio",
            "displayName": request.form.get("title", Path(audio.filename).stem)[:40],
            "description": "MCHLERN TOOLS AUDIO ROBLOX",
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
        return jsonify(uploaded=True, assetId=body.get("assetId") or body.get("path"), filename=audio.filename)
    except subprocess.CalledProcessError:
        return jsonify(error="FFmpeg gagal memproses audio."), 422
    except requests.RequestException:
        return jsonify(error="Roblox Open Cloud tidak dapat dihubungi."), 502
    finally:
        for item in (source, processed):
            if item and item.exists():
                item.unlink()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "3000")))

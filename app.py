#!/usr/bin/env python3
"""
🎬 Batch Video Downloader — Flask Web App
Streams downloaded files directly to the browser (no server storage needed).
"""

import subprocess
import sys
import re
import os
import tempfile
import threading
import uuid
from pathlib import Path
from flask import Flask, render_template, request, jsonify, Response, stream_with_context

app = Flask(__name__)

YT_DLP = [sys.executable, "-m", "yt_dlp"]

# In-memory job store  {job_id: {"status": ..., "logs": [], "file": ..., "filename": ...}}
jobs = {}
jobs_lock = threading.Lock()

# Path to optional cookies file (upload via /api/upload-cookies)
COOKIES_FILE = Path(__file__).parent / "cookies.txt"

QUALITY_PRESETS = {
    "4k":    {
        "label": "2160p 4K",
        "format": "bestvideo[height<=2160][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=2160]+bestaudio/best",
    },
    "1080":  {
        "label": "1080p FHD",
        "format": "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
    },
    "720":   {
        "label": "720p HD",
        "format": "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=720]+bestaudio/best[height<=720]/best",
    },
    "480":   {
        "label": "480p",
        "format": "bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=480]+bestaudio/best[height<=480]/best",
    },
    "best":  {
        "label": "Best Quality",
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best",
    },
    "audio": {
        "label": "Audio MP3",
        "format": "bestaudio/best",
        "audio_only": True,
    },
}


def detect_site(url: str) -> str:
    u = url.lower()
    if "youtube.com" in u or "youtu.be" in u:  return "YouTube"
    if "tiktok.com" in u:                       return "TikTok"
    if "facebook.com" in u or "fb.watch" in u:  return "Facebook"
    if "instagram.com" in u:                    return "Instagram"
    if "twitter.com" in u or "x.com" in u:      return "Twitter/X"
    if "vimeo.com" in u:                        return "Vimeo"
    if "reddit.com" in u:                       return "Reddit"
    return "Site"


def log(job_id, msg):
    with jobs_lock:
        jobs[job_id]["logs"].append(msg)


def friendly_error(stderr: str, site: str) -> str:
    """Convert yt-dlp error messages into user-friendly explanations."""
    s = stderr.lower()
    if "sign in" in s or "bot" in s or "cookies" in s:
        return (
            f"⛔ {site} is blocking server downloads (bot detection). "
            "Fix: Upload your browser cookies using the 🍪 Cookies button above."
        )
    if "private" in s or "login required" in s or "members only" in s:
        return f"🔒 This {site} video is private or requires login. Upload cookies to fix this."
    if "not available" in s or "unavailable" in s:
        return "🚫 This video is unavailable in the server's region or has been removed."
    if "unsupported url" in s or "no video formats" in s:
        return "❓ Unsupported URL. Make sure it's a direct link to a video page."
    if "http error 429" in s or "too many requests" in s:
        return "⏳ Rate limited by the site. Wait a few minutes and try again."
    if "http error 403" in s:
        return f"🚫 {site} blocked the request (403). Try uploading cookies."
    if "network" in s or "connect" in s or "timeout" in s:
        return "🌐 Network error reaching the site. Try again in a moment."
    return None  # fall through to raw error


def run_download(job_id, url, quality_key):
    preset = QUALITY_PRESETS.get(quality_key, QUALITY_PRESETS["best"])
    audio_only = preset.get("audio_only", False)
    site = detect_site(url)

    log(job_id, f"🔍 Detected: {site}")
    log(job_id, f"⚙️  Quality: {preset['label']}")
    log(job_id, f"📡 Connecting to {site}...")

    tmpdir = tempfile.mkdtemp()
    output_template = os.path.join(tmpdir, "%(title)s.%(ext)s")

    # ── Base flags ─────────────────────────────────────────────────────────────
    base_flags = [
        "--no-playlist",
        "--no-warnings",
        "--socket-timeout", "30",
        "--retries", "3",
        # Rotate through user agents to reduce bot detection
        "--user-agent",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    ]

    # ── Cookies (helps with YouTube, Instagram, Facebook auth) ────────────────
    if COOKIES_FILE.exists():
        base_flags += ["--cookies", str(COOKIES_FILE)]
        log(job_id, "🍪 Using saved cookies")

    # ── YouTube-specific: use PO token workaround via web client ──────────────
    is_youtube = "youtube.com" in url or "youtu.be" in url
    if is_youtube:
        base_flags += [
            "--extractor-args", "youtube:player_client=web,mweb",
        ]

    # ── Facebook / Instagram need extra headers ────────────────────────────────
    if any(s in url for s in ["instagram.com", "facebook.com", "fb.watch"]):
        base_flags += [
            "--add-header", "Accept-Language:en-US,en;q=0.9",
            "--add-header", "Referer:https://www.google.com/",
        ]

    # ── Build command ──────────────────────────────────────────────────────────
    if audio_only:
        cmd = YT_DLP + [
            "--format", preset["format"],
            "--output", output_template,
            "--extract-audio",
            "--audio-format", "mp3",
            "--audio-quality", "192K",
        ] + base_flags
    else:
        cmd = YT_DLP + [
            "--format", preset["format"],
            "--output", output_template,
            "--merge-output-format", "mp4",
        ] + base_flags

    cmd.append(url)
    log(job_id, "⬇️  Downloading...")

    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=600
        )

        if proc.returncode != 0:
            stderr = proc.stderr.strip()
            friendly = friendly_error(stderr, site)

            if friendly:
                log(job_id, friendly)
            else:
                # Show last few raw lines as fallback
                for line in stderr.splitlines()[-4:]:
                    if line.strip() and not line.startswith("WARNING"):
                        log(job_id, f"⚠️  {line.strip()}")

            log(job_id, "❌ Download failed.")
            with jobs_lock:
                jobs[job_id]["status"] = "error"
            return

        # ── Find the downloaded file ───────────────────────────────────────────
        files = [f for f in Path(tmpdir).iterdir() if f.is_file()]
        if not files:
            log(job_id, "❌ No file was created — the site may have blocked the download.")
            with jobs_lock:
                jobs[job_id]["status"] = "error"
            return

        # Pick the largest file (in case of .part leftovers)
        filepath = max(files, key=lambda f: f.stat().st_size)
        log(job_id, f"✅ Done! Ready to save: {filepath.name}")

        with jobs_lock:
            jobs[job_id]["status"] = "done"
            jobs[job_id]["file"] = str(filepath)
            jobs[job_id]["filename"] = filepath.name

    except subprocess.TimeoutExpired:
        log(job_id, "❌ Timed out after 10 minutes. The file may be too large or the server too slow.")
        with jobs_lock:
            jobs[job_id]["status"] = "error"
    except Exception as e:
        log(job_id, f"❌ Unexpected error: {str(e)}")
        with jobs_lock:
            jobs[job_id]["status"] = "error"


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html", presets=QUALITY_PRESETS)


@app.route("/api/upload-cookies", methods=["POST"])
def upload_cookies():
    """Accept a Netscape-format cookies.txt and save it for yt-dlp to use."""
    f = request.files.get("cookies")
    if not f:
        return jsonify({"error": "No file uploaded"}), 400
    content = f.read().decode("utf-8", errors="ignore")
    # Basic sanity check — Netscape cookies start with a comment line
    if "HTTP Cookie File" not in content and "Netscape HTTP" not in content and "# " not in content[:200]:
        return jsonify({"error": "Doesn't look like a valid Netscape cookies.txt file"}), 400
    COOKIES_FILE.write_text(content, encoding="utf-8")
    return jsonify({"ok": True, "message": "Cookies saved! Downloads will now use them."})


@app.route("/api/cookies-status")
def cookies_status():
    return jsonify({"has_cookies": COOKIES_FILE.exists()})


@app.route("/api/start", methods=["POST"])
def start_download():
    data = request.get_json()
    url = (data.get("url") or "").strip()
    quality = data.get("quality", "best")

    if not url or not re.match(r"https?://", url):
        return jsonify({"error": "Please enter a valid URL starting with http:// or https://"}), 400

    job_id = str(uuid.uuid4())
    with jobs_lock:
        jobs[job_id] = {"status": "running", "logs": [], "file": None, "filename": None}

    t = threading.Thread(target=run_download, args=(job_id, url, quality), daemon=True)
    t.start()

    return jsonify({"job_id": job_id})


@app.route("/api/status/<job_id>")
def job_status(job_id):
    with jobs_lock:
        job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify({
        "status": job["status"],
        "logs": job["logs"],
        "filename": job["filename"],
    })


@app.route("/api/download/<job_id>")
def download_file(job_id):
    with jobs_lock:
        job = jobs.get(job_id)

    if not job or job["status"] != "done" or not job["file"]:
        return "File not ready", 404

    filepath = Path(job["file"])
    if not filepath.exists():
        return "File not found", 404

    filename = job["filename"]
    mime = "audio/mpeg" if filename.endswith(".mp3") else "video/mp4"

    def generate():
        with open(filepath, "rb") as f:
            while chunk := f.read(1024 * 1024):  # 1 MB chunks
                yield chunk
        # Clean up after streaming
        try:
            filepath.unlink()
            filepath.parent.rmdir()
        except Exception:
            pass

    return Response(
        stream_with_context(generate()),
        mimetype=mime,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(filepath.stat().st_size),
        }
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)

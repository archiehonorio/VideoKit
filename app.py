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


def run_download(job_id, url, quality_key):
    preset = QUALITY_PRESETS.get(quality_key, QUALITY_PRESETS["best"])
    audio_only = preset.get("audio_only", False)
    site = detect_site(url)

    log(job_id, f"🔍 Detected: {site}")
    log(job_id, f"⚙️  Quality: {preset['label']}")
    log(job_id, f"📡 Connecting to {site}...")

    tmpdir = tempfile.mkdtemp()

    if audio_only:
        output_template = os.path.join(tmpdir, "%(title)s.%(ext)s")
        cmd = YT_DLP + [
            "--format", preset["format"],
            "--output", output_template,
            "--no-playlist",
            "--extract-audio",
            "--audio-format", "mp3",
            "--audio-quality", "192K",
            "--no-warnings",
        ]
    else:
        output_template = os.path.join(tmpdir, "%(title)s.%(ext)s")
        cmd = YT_DLP + [
            "--format", preset["format"],
            "--output", output_template,
            "--merge-output-format", "mp4",
            "--no-playlist",
            "--no-warnings",
        ]

    if any(s in url for s in ["instagram.com", "facebook.com", "fb.watch"]):
        cmd += ["--add-header", "User-Agent:Mozilla/5.0"]

    cmd.append(url)

    log(job_id, f"⬇️  Downloading...")

    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=600
        )

        if proc.returncode != 0:
            err = proc.stderr.strip().splitlines()
            for line in err[-5:]:
                if line.strip():
                    log(job_id, f"⚠️  {line.strip()}")
            log(job_id, "❌ Download failed. Check the URL and try again.")
            with jobs_lock:
                jobs[job_id]["status"] = "error"
            return

        # Find the downloaded file
        files = list(Path(tmpdir).iterdir())
        if not files:
            log(job_id, "❌ No file was created.")
            with jobs_lock:
                jobs[job_id]["status"] = "error"
            return

        filepath = files[0]
        log(job_id, f"✅ Done! Ready to download: {filepath.name}")

        with jobs_lock:
            jobs[job_id]["status"] = "done"
            jobs[job_id]["file"] = str(filepath)
            jobs[job_id]["filename"] = filepath.name

    except subprocess.TimeoutExpired:
        log(job_id, "❌ Timed out after 10 minutes.")
        with jobs_lock:
            jobs[job_id]["status"] = "error"
    except Exception as e:
        log(job_id, f"❌ Error: {str(e)}")
        with jobs_lock:
            jobs[job_id]["status"] = "error"


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html", presets=QUALITY_PRESETS)


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

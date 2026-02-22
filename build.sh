#!/usr/bin/env bash
# Render build script — installs Python deps + ffmpeg
set -e

pip install -r requirements.txt

# Install ffmpeg if available (needed for video+audio merging)
apt-get update -qq && apt-get install -y -qq ffmpeg || echo "ffmpeg install skipped (will try yt-dlp fallback)"

# 🎬 VidPull — Batch Video Downloader (Web App)

Download videos from YouTube, TikTok, Instagram, Facebook, Twitter/X, Vimeo, Reddit, and 1000+ more sites — straight from your browser.

---

## 🚀 Deploy to Render (Free) — Step by Step

### Step 1 — Push to GitHub

1. Go to [github.com](https://github.com) → click **New repository**
2. Name it `vidpull` (or anything you like)
3. Keep it **Public** (required for Render free tier)
4. Click **Create repository**

Then on your computer, open a terminal in this folder and run:

```bash
git init
git add .
git commit -m "first commit"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/vidpull.git
git push -u origin main
```

> Replace `YOUR_USERNAME` with your actual GitHub username.

---

### Step 2 — Deploy on Render

1. Go to [render.com](https://render.com) → sign up / log in (free)
2. Click **New +** → **Web Service**
3. Click **Connect GitHub** → authorize Render → select your `vidpull` repo
4. Fill in the form:

| Field | Value |
|-------|-------|
| **Name** | vidpull |
| **Runtime** | Python 3 |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 600` |

5. Scroll down → click **Create Web Service**
6. Wait ~2 minutes for it to build ✅
7. Your app is live at: `https://vidpull.onrender.com` (or similar URL)

---

### Step 3 — Enable FFmpeg on Render (for HD video merging)

By default Render's free instances have ffmpeg. If you ever get merge errors:

1. In Render dashboard → your service → **Settings**
2. Change **Build Command** to:
   ```
   bash build.sh
   ```
3. Save → it will redeploy automatically.

---

## 💻 Run Locally

```bash
# Install dependencies
pip install -r requirements.txt

# Run the app
python app.py

# Open in browser
http://localhost:5000
```

---

## 📁 Project Structure

```
vidpull/
├── app.py              ← Flask backend
├── templates/
│   └── index.html      ← Web UI
├── requirements.txt    ← Python dependencies
├── render.yaml         ← Render config
├── build.sh            ← Build script (installs ffmpeg)
└── .gitignore
```

---

## ⚠️ Notes

- **Render free tier** sleeps after 15 minutes of inactivity — first load may take ~30 seconds to wake up.
- Files are **streamed directly to your browser** — nothing is stored permanently on the server.
- For private Instagram/Facebook videos you may need to add cookies. See [yt-dlp docs](https://github.com/yt-dlp/yt-dlp#cookies).

---

## 🛠 Tech Stack

- [Flask](https://flask.palletsprojects.com/) — Python web framework
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) — video downloading engine
- [Gunicorn](https://gunicorn.org/) — production WSGI server
- [Render](https://render.com) — free cloud hosting

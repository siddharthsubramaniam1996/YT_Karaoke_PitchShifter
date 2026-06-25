# Karaoke Key Shifter — Complete Build Plan
### Zero cost · No credit card · iPhone PWA · Hugging Face Spaces

A web app your sister opens on her iPhone to paste a YouTube URL,
shift the pitch by any number of semitones, preview the result in a
mini player, and download as MP3 or MP4.

---

## Table of Contents

1. [How It Works](#1-how-it-works)
2. [Tech Stack](#2-tech-stack)
3. [Directory Structure](#3-directory-structure)
4. [Hugging Face Setup](#4-hugging-face-setup)
5. [File Contents](#5-file-contents)
   - [Dockerfile](#dockerfile)
   - [supervisord.conf](#supervisordconf)
   - [requirements.txt](#requirementstxt)
   - [README.md](#readmemd)
   - [.gitignore](#gitignore)
   - [app/\_\_init\_\_.py](#appinitpy)
   - [app/pipeline.py](#apppipelinepy)
   - [app/worker.py](#appworkerpy)
   - [app/main.py](#appmainpy)
   - [frontend/index.html](#frontendindexhtml)
   - [frontend/manifest.json](#frontendmanifestjson)
   - [frontend/sw.js](#frontendswjs)
6. [Custom Domain (Optional)](#6-custom-domain-optional)
7. [Deployment](#7-deployment)
8. [Starting and Stopping](#8-starting-and-stopping)
9. [iPhone Home Screen Install](#9-iphone-home-screen-install)
10. [Maintenance](#10-maintenance)
11. [Gotchas](#11-gotchas)
12. [Quick Reference](#12-quick-reference)

---

## 1. How It Works

```
[ iPhone Safari — https://yourname-karaoke.hf.space ]
      │
      │  1. Paste YouTube URL
      │  2. Song title + thumbnail previewed (yt-dlp metadata fetch)
      │  3. Pick semitones (-6 to +6)
      │  4. Pick MP3 or MP4
      │  5. Tap "Shift & Download"
      ▼
[ Hugging Face Space — free CPU tier — 2 vCPU / 16 GB RAM ]
  ┌──────────────────────────────────────────────────────┐
  │  One Docker container, two processes via supervisord  │
  │                                                        │
  │  ┌─────────────────────┐  ┌──────────────────────┐   │
  │  │  FastAPI :7860      │  │  bgutil-pot :4416    │   │
  │  │  yt-dlp             │→ │  BotGuard PO tokens  │   │
  │  │  ffmpeg + rubberband│  │  Beats bot detection │   │
  │  │  in-memory jobs     │  └──────────────────────┘   │
  │  └─────────────────────┘                              │
  └──────────────────────────────────────────────────────┘
      │
      ▼  /tmp/karaoke/<job_id>/
         src.mp4      ← downloaded from YouTube
         out.mp3/mp4  ← pitch-shifted result

[ iPhone polls /status/<id> every 2s ]
      │
      ▼
[ Mini player slides up from bottom of screen ]
[ Play · skip ±15s · thin progress bar ]
[ Tap Download to save to Files ]
```

**The core pipeline — two commands:**

```bash
# 1. Download (yt-dlp, with bgutil-pot providing the PO token)
yt-dlp -f "bv*+ba/b" --merge-output-format mp4 -o "src.%(ext)s" "<URL>"

# 2. Pitch-shift without changing tempo (ffmpeg rubberband filter)
#    ratio = 2^(semitones/12)  →  -2 semitones = 0.8909
ffmpeg -i src.mp4 -af "rubberband=pitch=0.8909" -c:v copy -c:a aac out.mp4
ffmpeg -i src.mp4 -vn -af "rubberband=pitch=0.8909" -c:a libmp3lame -q:a 2 out.mp3
```

---

## 2. Tech Stack

| Layer | Choice | Reason |
|---|---|---|
| Hosting | Hugging Face Spaces (Docker) | Free forever, no card, 16 GB RAM, HTTPS included |
| Backend | Python 3.11 + FastAPI | yt-dlp is Python; clean async API |
| Job state | In-memory dict + threading | Single user, no persistence needed |
| YouTube download | yt-dlp (Python library) | Most reliable YT downloader, daily updates |
| Bot detection bypass | bgutil-ytdlp-pot-provider-rs | Rust binary, generates BotGuard PO tokens so yt-dlp works from cloud IPs |
| Process manager | supervisord | Runs bgutil-pot + uvicorn in one container |
| Pitch shift | ffmpeg + librubberband | Pitch-only, tempo unchanged — same as vocalremover.org |
| Frontend | Vanilla HTML/CSS/JS | No build step, PWA-installable on iPhone |
| Font | -apple-system | SF Pro on iPhone, no external dependency |
| Theme | Dark + light toggle | Persists via localStorage |
| Mini player | HTML5 `<audio>` + /stream endpoint | HTTP range requests handled by FastAPI FileResponse |

---

## 3. Directory Structure

```
karaoke/
├── Dockerfile              ← single image: Python + ffmpeg + bgutil-pot + app
├── supervisord.conf        ← runs bgutil-pot + uvicorn together
├── requirements.txt
├── README.md               ← HF Spaces reads the YAML front matter
├── .gitignore
├── app/
│   ├── __init__.py
│   ├── main.py             ← all routes: /info /jobs /status /download /stream /health
│   ├── worker.py           ← background thread + in-memory job store
│   └── pipeline.py         ← yt-dlp download + ffmpeg pitch shift + video info
└── frontend/
    ├── index.html          ← full UI: Apple Music dark/light + bottom mini player
    ├── manifest.json       ← PWA manifest for iPhone home screen
    ├── sw.js               ← minimal service worker
    └── icon-192.png        ← 192×192 app icon (replace with a nicer one from favicon.io)
```

> **No docker-compose.yml needed.** HF Spaces builds straight from the Dockerfile.
> **No persistent storage.** `/tmp/karaoke/` is ephemeral — files reset on container restart.
> This is fine: she submits a job, waits 1–3 minutes, downloads. Done.

---

## 4. Hugging Face Setup

### Create account

1. Go to `https://huggingface.co/join`
2. Enter username, email, password — no card, no phone number required
3. Verify your email

### Create the Space

1. Go to `https://huggingface.co/new-space`
2. Fill in:
   - **Owner**: your username
   - **Space name**: `karaoke`
   - **SDK**: **Docker** ← important
   - **Visibility**: Public (easiest for iPhone access; the URL is obscure enough)
3. Click **Create Space**

HF creates a git repo. You push your code to it; HF builds and runs the Dockerfile automatically.

### Get your HF token (needed for CLI login)

`https://huggingface.co/settings/tokens` → New token → Read+Write

### Clone the Space repo

```bash
pip install huggingface_hub
huggingface-cli login    # paste your token when prompted

git clone https://huggingface.co/spaces/yourname/karaoke
cd karaoke
# Copy all your project files here, then:
git add .
git commit -m "initial"
git push
```

Your app URL: `https://yourname-karaoke.hf.space`

---

## 5. File Contents

### Dockerfile

```dockerfile
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    librubberband-dev \
    supervisor \
    curl \
    wget \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Verify rubberband filter is present in this ffmpeg build
RUN ffmpeg -filters 2>/dev/null | grep -q rubberband || \
    (echo "ERROR: rubberband not found in ffmpeg" && exit 1)

# bgutil-pot Rust binary — generates YouTube BotGuard PO tokens
# so yt-dlp works from cloud IPs without getting bot-blocked
RUN wget -q -O /usr/local/bin/bgutil-pot \
    https://github.com/jim60105/bgutil-ytdlp-pot-provider-rs/releases/latest/download/bgutil-pot-linux-x86_64 \
    && chmod +x /usr/local/bin/bgutil-pot

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# yt-dlp plugin that connects yt-dlp to the bgutil-pot HTTP server
RUN pip install --no-cache-dir bgutil-ytdlp-pot-provider

COPY app/ ./app/
COPY frontend/ ./frontend/
COPY supervisord.conf /etc/supervisor/conf.d/karaoke.conf

RUN mkdir -p /tmp/karaoke /var/log/supervisor

# HF Spaces requires port 7860
EXPOSE 7860

CMD ["supervisord", "-n", "-c", "/etc/supervisor/supervisord.conf"]
```

---

### supervisord.conf

```ini
[supervisord]
nodaemon=true
user=root
logfile=/var/log/supervisor/supervisord.log
logfile_maxbytes=5MB
pidfile=/var/run/supervisord.pid

[program:bgutil]
command=/usr/local/bin/bgutil-pot server --host 127.0.0.1 --port 4416
autostart=true
autorestart=true
priority=1
startsecs=2
stdout_logfile=/var/log/supervisor/bgutil.log
stderr_logfile=/var/log/supervisor/bgutil_err.log

[program:app]
command=uvicorn app.main:app --host 0.0.0.0 --port 7860 --workers 1
directory=/app
autostart=true
autorestart=true
priority=2
startsecs=3
startretries=5
stdout_logfile=/var/log/supervisor/app.log
stderr_logfile=/var/log/supervisor/app_err.log
```

> supervisord starts bgutil-pot first (priority 1), waits 2 seconds, then
> starts uvicorn (priority 2). Both restart automatically if they crash.
> Logs are at `/var/log/supervisor/` — visible in the HF Spaces Logs tab.

---

### requirements.txt

```
fastapi==0.111.0
uvicorn[standard]==0.29.0
yt-dlp
aiofiles==23.2.1
```

> `yt-dlp` is intentionally unpinned — always get latest to stay ahead of
> YouTube's periodic breaking changes.

---

### README.md

```markdown
---
title: Karaoke Key Shifter
emoji: 🎵
colorFrom: red
colorTo: pink
sdk: docker
pinned: false
---

# Karaoke Key Shifter

Paste a YouTube URL, pick a key shift in semitones, download as MP3 or MP4.

Built with FastAPI + yt-dlp + ffmpeg (rubberband filter) + bgutil PO token provider.
```

> The YAML front matter is parsed by HF Spaces to configure the Space card.
> The `sdk: docker` line tells HF to build your Dockerfile.

---

### .gitignore

```
.env
__pycache__/
*.pyc
*.pyo
.DS_Store
```

---

### app/\_\_init\_\_.py

```python
# empty — marks app/ as a Python package
```

---

### app/pipeline.py

```python
import os
import subprocess
import yt_dlp

TMP_BASE = "/tmp/karaoke"
BGUTIL_URL = "http://127.0.0.1:4416"   # bgutil-pot runs in same container


def semitones_to_ratio(semitones: int) -> float:
    """Convert semitone shift to pitch ratio.
    -2 semitones → 0.8909 (lower pitch, same tempo)
    """
    return 2 ** (semitones / 12)


def get_tmp_dir(job_id: str) -> str:
    path = os.path.join(TMP_BASE, job_id)
    os.makedirs(path, exist_ok=True)
    return path


def download_video(url: str, job_id: str, progress_hook) -> str:
    """
    Download best video+audio merged to src.mp4.
    bgutil-pot supplies BotGuard PO tokens so YouTube does not
    block downloads from cloud/HF Spaces IP addresses.
    Returns path to src.mp4.
    """
    tmp_dir = get_tmp_dir(job_id)

    ydl_opts = {
        "format": "bv*+ba/b",
        "merge_output_format": "mp4",
        "outtmpl": os.path.join(tmp_dir, "src.%(ext)s"),
        "noplaylist": True,
        "max_filesize": 500 * 1024 * 1024,
        "progress_hooks": [progress_hook],
        "extractor_args": {
            "youtube": {
                "getpot_bgutil_baseurl": [BGUTIL_URL]
            }
        },
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    # yt-dlp occasionally produces .mkv — normalise to .mp4
    src = os.path.join(tmp_dir, "src.mp4")
    if not os.path.exists(src):
        for f in os.listdir(tmp_dir):
            if f.startswith("src."):
                os.rename(os.path.join(tmp_dir, f), src)
                break

    return src


def pitch_shift(src_path: str, semitones: int, fmt: str, job_id: str) -> str:
    """
    Pitch-shift audio by semitones without changing tempo.
    Uses ffmpeg's rubberband filter (verified present at Docker build time).

    Fallback if rubberband is unavailable — replace the af= line with:
      af = f"asetrate=44100*{ratio:.6f},aresample=44100,atempo={1/ratio:.6f}"
    This slightly affects tempo but is an acceptable degraded fallback.
    """
    tmp_dir = get_tmp_dir(job_id)
    ratio = semitones_to_ratio(semitones)
    af = f"rubberband=pitch={ratio:.6f}"

    if fmt == "mp3":
        out = os.path.join(tmp_dir, "out.mp3")
        cmd = [
            "ffmpeg", "-y", "-i", src_path,
            "-vn",
            "-af", af,
            "-c:a", "libmp3lame", "-q:a", "2",
            out,
        ]
    else:  # mp4
        out = os.path.join(tmp_dir, "out.mp4")
        cmd = [
            "ffmpeg", "-y", "-i", src_path,
            "-af", af,
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k",
            out,
        ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed:\n{result.stderr[-2000:]}")

    if os.path.exists(src_path):
        os.remove(src_path)

    return out


def get_video_info(url: str) -> dict:
    """Fetch title, thumbnail, duration, channel without downloading."""
    with yt_dlp.YoutubeDL({"quiet": True, "skip_download": True}) as ydl:
        info = ydl.extract_info(url, download=False)
        dur = int(info.get("duration") or 0)
        mins, secs = divmod(dur, 60)
        return {
            "title":     info.get("title", "Unknown"),
            "thumbnail": info.get("thumbnail", ""),
            "duration":  f"{mins}:{secs:02d}",
            "channel":   info.get("channel", ""),
        }
```

---

### app/worker.py

```python
import os
import shutil
import threading
import time
import queue
from app.pipeline import download_video, pitch_shift, TMP_BASE

# In-memory job store — resets on container restart (fine for single-user use)
_jobs: dict[str, dict] = {}
_lock = threading.Lock()
_queue: queue.Queue = queue.Queue()

JOB_TTL = 3600  # seconds — files and job records expire after 1 hour


def create_job(job_id: str, url: str, semitones: int, fmt: str):
    with _lock:
        _jobs[job_id] = {
            "id":          job_id,
            "url":         url,
            "semitones":   semitones,
            "format":      fmt,
            "status":      "queued",
            "progress":    0,
            "output_path": None,
            "error":       None,
            "created_at":  time.time(),
        }


def get_job(job_id: str) -> dict | None:
    with _lock:
        return dict(_jobs[job_id]) if job_id in _jobs else None


def enqueue(job_id: str):
    _queue.put(job_id)


def _update(job_id: str, **kwargs):
    with _lock:
        if job_id in _jobs:
            _jobs[job_id].update(kwargs)


def _process(job_id: str):
    job = get_job(job_id)
    if not job:
        return

    _update(job_id, status="downloading", progress=5)

    def yt_hook(d):
        if d["status"] == "downloading":
            raw = d.get("_percent_str", "0%").strip().replace("%", "")
            try:
                _update(job_id, progress=int(float(raw) * 0.70))
            except (ValueError, TypeError):
                pass

    try:
        src = download_video(job["url"], job_id, yt_hook)
        _update(job_id, status="processing", progress=72)
        out = pitch_shift(src, job["semitones"], job["format"], job_id)
        _update(job_id, status="done", progress=100, output_path=out)
    except Exception as e:
        _update(job_id, status="error", error=str(e))


def _loop():
    while True:
        job_id = _queue.get()
        try:
            _process(job_id)
        finally:
            _queue.task_done()


def _cleanup_loop():
    """Delete job files and records older than JOB_TTL seconds."""
    while True:
        time.sleep(600)  # check every 10 minutes
        now = time.time()
        with _lock:
            expired = [
                jid for jid, j in _jobs.items()
                if now - j["created_at"] > JOB_TTL
            ]
        for jid in expired:
            shutil.rmtree(os.path.join(TMP_BASE, jid), ignore_errors=True)
            with _lock:
                _jobs.pop(jid, None)


def start_worker():
    threading.Thread(target=_loop, daemon=True).start()
    threading.Thread(target=_cleanup_loop, daemon=True).start()
```

---

### app/main.py

```python
import uuid
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.worker import create_job, get_job, enqueue, start_worker
from app.pipeline import get_video_info


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_worker()
    yield


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="/app/frontend"), name="static")


class JobRequest(BaseModel):
    url: str
    semitones: int   # -12 to +12
    format: str      # "mp3" or "mp4"


@app.get("/", response_class=HTMLResponse)
async def index():
    with open("/app/frontend/index.html") as f:
        return f.read()


@app.get("/info")
async def video_info(url: str):
    """Fetch title + thumbnail for preview card before committing to download."""
    try:
        return get_video_info(url)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/jobs")
async def submit_job(req: JobRequest):
    if req.format not in ("mp3", "mp4"):
        raise HTTPException(status_code=400, detail="format must be mp3 or mp4")
    if not (-12 <= req.semitones <= 12):
        raise HTTPException(status_code=400, detail="semitones must be -12 to +12")
    job_id = str(uuid.uuid4())
    create_job(job_id, req.url, req.semitones, req.format)
    enqueue(job_id)
    return {"job_id": job_id}


@app.get("/status/{job_id}")
async def job_status(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "job_id":   job["id"],
        "status":   job["status"],    # queued|downloading|processing|done|error
        "progress": job["progress"],  # 0–100
        "error":    job["error"],
    }


@app.get("/download/{job_id}")
async def download_file(job_id: str):
    """Serve processed file as attachment (triggers iOS save dialog)."""
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["status"] != "done":
        raise HTTPException(status_code=400, detail="Job not complete yet")
    path = job["output_path"]
    if not path or not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Output file missing")
    ext = job["format"]
    mime = "audio/mpeg" if ext == "mp3" else "video/mp4"
    return FileResponse(path, media_type=mime, filename=f"karaoke_{job_id[:8]}.{ext}")


@app.get("/stream/{job_id}")
async def stream_file(job_id: str):
    """
    Serve processed file for inline browser playback (no save dialog).
    Used by the <audio> element in the mini player.
    Omitting filename → Content-Disposition: inline → browser plays it.
    FastAPI's FileResponse handles HTTP 206 range requests natively
    so scrubbing and seeking work without extra code.
    """
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["status"] != "done":
        raise HTTPException(status_code=400, detail="Job not complete yet")
    path = job["output_path"]
    if not path or not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Output file missing")
    mime = "audio/mpeg" if job["format"] == "mp3" else "video/mp4"
    return FileResponse(path, media_type=mime)


@app.get("/health")
async def health():
    return {"ok": True}
```

---

### frontend/index.html

> The full file is in the zip. Key design decisions summarised here:
>
> - **Apple Music aesthetic** — true black `#000000` dark / `#f2f2f7` light, using Apple's exact HIG system colors
> - **Accent** `#ff375f` (dark) / `#ff2d55` (light) — Apple Music's red-pink, used in exactly three places: selected semitone, Go button, progress bar
> - **No glassmorphism, no gradients on buttons, no purple** — solid surfaces only
> - **Ambient album art** — YouTube thumbnail becomes a blurred, darkened background behind the song preview row (Apple Music's content-aware color pattern)
> - **Semitone picker** — horizontal scrollable pill strip (-6 to +6), selected scrolls into view
> - **Format selector** — iOS UISegmentedControl, pixel-accurate
> - **Theme toggle** — persists via localStorage, flash-free (script in `<head>` before styles)
> - **Bottom mini player** — `position: fixed; bottom: 0` — slides up when track is ready
>   - 2px progress line across top edge
>   - Song thumbnail + title + live timestamp on left
>   - Skip −15s · Play/Pause · Skip +15s centered
>   - Download icon button on right
>   - `env(safe-area-inset-bottom)` handles iPhone home indicator
> - **Polling** — frontend polls `/status/<id>` every 2s, shows equalizer animation during processing
> - **Mini player audio** — wired to `/stream/<id>` endpoint, starts paused (iOS requires user gesture)

---

### frontend/manifest.json

```json
{
  "name": "Karaoke Key Shifter",
  "short_name": "Karaoke",
  "start_url": "/",
  "display": "standalone",
  "background_color": "#000000",
  "theme_color": "#ff375f",
  "icons": [
    {
      "src": "/static/icon-192.png",
      "sizes": "192x192",
      "type": "image/png"
    }
  ]
}
```

---

### frontend/sw.js

```javascript
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', () => self.clients.claim());
```

---

## 6. Custom Domain (Optional)

Get a free domain like `karaoke.us.kg` pointing to your HF Space.
HF Spaces does not support custom domains on the free tier, so the
chain is: **FreeDomain → Cloudflare DNS → Cloudflare Worker proxy → HF Space**.
Everything in this chain is free and requires no credit card.

### Step 1 — Register a free domain

Go to `https://dash.domain.digitalplat.org/`, sign up, register a domain
(e.g. `karaoke.us.kg`). When asked for DNS provider, choose **Cloudflare**.

Available extensions: `.us.kg` `.dpdns.org` `.qzz.io` `.xx.kg` `.qd.je`

### Step 2 — Set up Cloudflare (free, no card)

1. Create a free account at `https://cloudflare.com`
2. Add your domain as a new site
3. Copy the two Cloudflare nameservers into the FreeDomain dashboard

### Step 3 — Create the Cloudflare Worker proxy

In Cloudflare dashboard → **Workers & Pages** → **Create** → **Create Worker**.
Replace the default code with:

```javascript
export default {
  async fetch(request) {
    const url = new URL(request.url);
    url.hostname = 'yourname-karaoke.hf.space'; // ← your HF Space URL
    url.protocol = 'https:';
    url.port = '';
    const modifiedRequest = new Request(url.toString(), {
      method:   request.method,
      headers:  request.headers,
      body:     request.body,
      redirect: 'follow',
    });
    return fetch(modifiedRequest);
  }
};
```

Deploy it. Then under the Worker's **Settings → Triggers → Add Custom Domain**,
add your domain (e.g. `karaoke.us.kg`). Cloudflare handles HTTPS automatically.

**Cloudflare Workers free tier**: 100,000 requests/day — far more than this app needs.

**Honest caveat**: FreeDomain's `.us.kg` / `.dpdns.org` extensions are not
ICANN-accredited. If DigitalPlat shuts down, the custom domain breaks. The HF
Space URL always remains as the fallback.

---

## 7. Deployment

### First time

```bash
# Install HF CLI
pip install huggingface_hub

# Log in (get your token from https://huggingface.co/settings/tokens)
huggingface-cli login

# Clone your Space repo (created in Section 4)
git clone https://huggingface.co/spaces/yourname/karaoke
cd karaoke

# Copy all project files here (or unzip karaoke.zip contents here)

# Push — this triggers an automatic Docker build on HF
git add .
git commit -m "initial build"
git push
```

### Watch the build

Go to `https://huggingface.co/spaces/yourname/karaoke` → **Logs** tab.
First build takes 3–5 minutes (downloading ffmpeg, bgutil-pot binary, Python deps).
When status shows **Running**, the app is live.

### Redeploy after any code change

```bash
git add .
git commit -m "describe your change"
git push
# HF rebuilds and redeploys automatically
```

### Force a rebuild (e.g. to pick up latest yt-dlp or bgutil-pot)

```bash
git commit --allow-empty -m "rebuild: refresh dependencies"
git push
```

---

## 8. Starting and Stopping

HF Spaces free tier sleeps after 48 hours of no visits. It wakes automatically
(~30 second delay) when anyone opens the URL — your sister doesn't need to do
anything except wait briefly on first load.

### Manual pause (to stop it completely)

1. Go to `https://huggingface.co/spaces/yourname/karaoke`
2. Click **Settings** (top right of Space page)
3. Scroll to **Pause this Space** → click **Pause**

### Manual restart

Same Settings page → **Restart this Space**.

### Bookmark for one-tap control

`https://huggingface.co/spaces/yourname/karaoke/settings`

---

## 9. iPhone Home Screen Install

This gives your sister a full-screen app icon — no browser chrome, no address bar.

1. Open the Space URL in **Safari** (must be Safari; Chrome on iOS cannot install PWAs)
2. Tap the **Share** button (box with arrow, bottom of Safari)
3. Scroll down → tap **Add to Home Screen**
4. Name it "Karaoke" → tap **Add**

She now has a red icon on her home screen. Tapping opens the app full-screen.

**Downloaded files go to:** Files app → Downloads (MP3 and MP4).
From there she can AirDrop, add to Music, or use it directly as a video background.

---

## 10. Maintenance

### YouTube downloads start failing
Almost always fixed by updating yt-dlp:
```bash
git commit --allow-empty -m "rebuild: update yt-dlp"
git push
```
The empty commit forces HF to rebuild, which runs `pip install yt-dlp` and
pulls the latest version. This is the only maintenance you'll ever routinely do.

### bgutil-pot stops working
Same fix — the Dockerfile downloads `latest` at build time:
```bash
git commit --allow-empty -m "rebuild: refresh bgutil-pot"
git push
```

### Check logs
`https://huggingface.co/spaces/yourname/karaoke` → **Logs** tab
Shows real-time stdout/stderr from both supervisord processes.

### Disk full (unlikely)
The Space has 50 GB ephemeral disk. Each song uses ~50–200 MB temporarily
(source + output). The cleanup thread deletes each job's `/tmp/karaoke/<job_id>/`
directory (and removes the job record) 1 hour after the job was created — so
at most ~12 jobs × 200 MB ≈ 2.4 GB is retained at any one time. If it ever
fills anyway, restarting the Space clears `/tmp`.

---

## 11. Gotchas

### ffmpeg rubberband
The Dockerfile verifies rubberband is present at build time and fails loudly
if not. This should never be an issue on the `python:3.11-slim` + Debian
`ffmpeg` package combination, which includes rubberband. If it ever fails,
the fallback in `pipeline.py` is documented in a comment.

### YouTube bot detection on HF Spaces IPs
bgutil-pot handles this. The provider + yt-dlp combination is well-maintained
and typically fixed within 24–48 hours of any YouTube change. A rebuild
(empty commit) picks up the latest versions.

### Age-restricted / private videos
Won't work without authenticated cookies from a logged-in session. The app
returns a clear error message. No fix available without adding cookie auth.

### HF Spaces and ToS
HF Spaces is designed for ML demos. Running yt-dlp there is technically
outside the intended use case. For one person using it a few times a week,
it is extremely unlikely to ever be flagged. If it is, the Space gets paused
with a notice — nothing more.

### iOS Safari and audio autoplay
The mini player starts paused. iOS requires audio to be triggered by a direct
user tap — the play button is a real `<button onclick>` which satisfies this.
Calling `audio.play()` programmatically on page load would be silently blocked.

### iPhone download behaviour
- **MP3**: saves to Files → Downloads. Opens in Music app if she taps it there.
- **MP4**: opens in the native video player. She taps Share → Save to Files.

### Space sleeping mid-job
If HF sleeps the Space while a job is running (very unlikely given the 48h
idle threshold), the job is lost. She would need to resubmit. In practice
this won't happen during an active session.

---

## 12. Quick Reference

| Thing | Where |
|---|---|
| App URL | `https://yourname-karaoke.hf.space` |
| Space dashboard | `https://huggingface.co/spaces/yourname/karaoke` |
| Logs | Space dashboard → Logs tab |
| Pause / restart | Space dashboard → Settings |
| Push a change | `git add . && git commit -m "…" && git push` |
| Fix broken YT downloads | `git commit --allow-empty -m "rebuild" && git push` |
| HF token | `https://huggingface.co/settings/tokens` |
| FreeDomain dashboard | `https://dash.domain.digitalplat.org/` |
| Cloudflare dashboard | `https://dash.cloudflare.com` |
| Generate a nicer icon | `https://favicon.io/emoji-favicon-maker` (192×192 PNG) |
<video src="demo.mp4" autoplay loop muted playsinline style="width:100%;border-radius:12px"></video>

# 🎵 YT Karaoke Pitch Shifter

A simple web app that lets you take any YouTube video, shift its pitch by any number of semitones, and download the result as an MP3 or MP4 — without changing the tempo.

Built for musicians who are tired of the key never being right out of the box.

---

## What It Does

1. Paste a YouTube URL
2. Pick how many semitones to shift the pitch (up or down)
3. Hit go
4. Preview the result in a mini player before saving
5. Download as MP3 (audio only) or MP4 (video + audio)

No accounts. No subscriptions. No ads.

---

## Running It (Windows — Docker)

> This is the recommended way for end users.

**One-time setup:**
1. Install [Docker Desktop](https://docker.com/products/docker-desktop) and restart your PC
2. Rename your PC to something short and memorable — e.g. `karaoke` or your own name. Start → Settings → System → About → Rename this PC → Restart
3. Download [start.bat](https://raw.githubusercontent.com/siddharthsubramaniam1996/YT_Karaoke_PitchShifter/master/start.bat) and save it to your Desktop

**Every time:**
- Double-click `start.bat`
- The window will print your exact iPhone URL based on your PC name — e.g. `http://karaoke.local`. If you haven't renamed your PC, Windows defaults to something like `http://DESKTOP-A1B2C3.local` which works but is harder to type — renaming is recommended
- Open that URL on any device on the same WiFi
- Close the black window when done

> **iPhone tip:** Safari → share button → Add to Home Screen to make it feel like a native app.

---

## Running It (Developer Setup)

```bash
git clone https://github.com/siddharthsubramaniam1996/YT_Karaoke_PitchShifter.git
cd YT_Karaoke_PitchShifter
pip install -r requirements.txt
uvicorn app.main:app --reload --port 80
```

App runs at `http://localhost`.

---

## Building & Publishing

```bash
./ship.sh
```

Pushes to GitHub and rebuilds the Docker Hub image (`siddharths96/karaoke`) in one command. End users get the update automatically next time they start the app.

---

## How It Works

| Step | What happens |
|------|-------------|
| Paste URL | App fetches title, thumbnail, and duration via yt-dlp |
| Submit job | yt-dlp downloads the video from YouTube (iOS client) |
| Pitch shift | ffmpeg `rubberband` filter shifts pitch without changing tempo |
| Download | File served directly from the app as MP3 or MP4 |

**Stack:**
- **Backend:** Python, FastAPI, yt-dlp, ffmpeg (rubberband filter)
- **Frontend:** Single HTML file — vanilla JS, no build step
- **Packaging:** Docker

**Architecture:**
- Single FastAPI process with a background worker thread
- Jobs are queued FIFO and processed one at a time
- Job state: `queued → downloading → processing → done | error`
- Temp files live in `/tmp/karaoke/{job_id}/` and are cleaned up after 1 hour

---

## Optional: Proxy Support

If running on a cloud server where YouTube blocks requests, set the `YTDLP_PROXY` environment variable to a residential proxy URL:

```
YTDLP_PROXY=http://user:pass@host:port
```

Not needed when running on a home network.

---

## Built With

This project was built in conversation with [Claude Code](https://claude.ai/code) — working through architecture, tradeoffs, and debugging together. The thinking was mine; Claude helped write the code.

---

*Built for Akshaya. 🎵*

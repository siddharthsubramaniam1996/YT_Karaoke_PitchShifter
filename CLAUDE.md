# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running locally (dev)

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --port 80
```

App is at `http://localhost`.

## Docker

```bash
docker build -t karaoke .
docker run -p 80:80 karaoke
```

To publish an update to Docker Hub:

```bash
docker build -t siddharths96/karaoke .
docker push siddharths96/karaoke
```

## Deploying to Akshaya's machine

Akshaya runs `start.bat` on her Windows PC. It pulls `siddharths96/karaoke` from Docker Hub automatically. After pushing a new image, she gets the update next time she starts the app (`--pull always` is set).

## Architecture

One process: **uvicorn** on `:80` — FastAPI app.

**Request flow:**
1. `GET /info?url=` — frontend debounce-fetches metadata to show song preview card
2. `POST /jobs` — creates a job record and enqueues it; returns `job_id`
3. Frontend polls `GET /status/{job_id}` every 2 seconds
4. `GET /stream/{job_id}` — serves the output file inline for the mini player `<audio>` element
5. `GET /download/{job_id}` — serves with `Content-Disposition: attachment` to trigger iOS save dialog

**Backend modules:**
- `app/pipeline.py` — `download_video` (yt-dlp, ios client, strips `list=` param, normalises output to `src.mp4`), `pitch_shift` (ffmpeg rubberband filter, deletes source after completing), `get_video_info` for metadata.
- `app/worker.py` — single FIFO worker thread with an in-memory `_jobs` dict. Job state machine: `queued → downloading → processing → done | error`. Download progress (0–70%) comes from yt-dlp's `_percent_str` hook; pitch-shift jumps to 72% → 100%.
- `app/main.py` — FastAPI routes; mounts `frontend/` as `/static`. The lifespan handler calls `start_worker()`.

**Job files** live in `/tmp/karaoke/{job_id}/src.mp4` (deleted after pitch-shift) and `out.mp3|mp4` (kept until the job expires).

**Frontend** (`frontend/index.html`) is a single self-contained file — vanilla JS, no build step. Theme (dark/light) persists in `localStorage` with a flash-free inline script in `<head>`. Semitone picker is a horizontal scrollable strip from −6 to +6. The mini player is a fixed bottom bar wired to the `<audio>` element.

## Key constraints

- `yt-dlp` is pinned to `<2026.06.09` to keep the built-in n-challenge solver (later versions require external Node.js).
- The rubberband ffmpeg filter is verified present at Docker **build** time (`ffmpeg -filters | grep rubberband`). If it's missing, the build fails. The fallback (`asetrate/aresample/atempo`) is documented in a comment in `pipeline.py` but requires a code change to activate.
- iOS Safari requires audio to be started by a direct user tap — `audio.play()` is only called from button `onclick` handlers, never programmatically on page load.
- Set `YTDLP_PROXY=http://user:pass@host:port` env var to route yt-dlp through a proxy (needed if running on cloud IPs that YouTube blocks).

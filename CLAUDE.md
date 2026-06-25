# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running locally

bgutil-pot must be running on port 4416 before yt-dlp can download from cloud IPs. Download the binary from the GitHub releases page (see Dockerfile for the URL), then:

```bash
pip install -r requirements.txt
pip install bgutil-ytdlp-pot-provider
bgutil-pot server --host 127.0.0.1 --port 4416 &
uvicorn app.main:app --reload --port 7860
```

App is at `http://localhost:7860`.

## Docker (matches production exactly)

```bash
docker build -t karaoke .
docker run -p 7860:7860 karaoke
```

First build takes a few minutes — it downloads ffmpeg, bgutil-pot binary, and Python deps.

## Deploying

```bash
git add . && git commit -m "..." && git push
```

Pushing to the Hugging Face Space repo triggers an automatic Docker rebuild and redeploy. Force a dependency refresh with an empty commit:

```bash
git commit --allow-empty -m "rebuild: update yt-dlp" && git push
```

## Architecture

Two processes run in one container, managed by supervisord:
- **bgutil-pot** on `:4416` — Rust binary that generates YouTube BotGuard PO tokens, keeping yt-dlp functional from cloud IPs
- **uvicorn** on `:7860` — FastAPI app

**Request flow:**
1. `GET /info?url=` — frontend debounce-fetches metadata to show song preview card
2. `POST /jobs` — creates a job record and enqueues it; returns `job_id`
3. Frontend polls `GET /status/{job_id}` every 2 seconds
4. `GET /stream/{job_id}` — serves the output file inline for the mini player `<audio>` element
5. `GET /download/{job_id}` — serves with `Content-Disposition: attachment` to trigger iOS save dialog

**Backend modules:**
- `app/pipeline.py` — two functions: `download_video` (yt-dlp with bgutil extractor args, normalises output to `src.mp4`) and `pitch_shift` (ffmpeg rubberband filter, deletes source after completing). Also `get_video_info` for metadata — note this does **not** use bgutil, so it may be bot-blocked on cloud IPs.
- `app/worker.py` — single FIFO worker thread with an in-memory `_jobs` dict. Job state machine: `queued → downloading → processing → done | error`. Download progress (0–70%) comes from yt-dlp's `_percent_str` hook; pitch-shift jumps to 72% → 100%.
- `app/main.py` — FastAPI routes; mounts `frontend/` as `/static`. The lifespan handler calls `start_worker()`.

**Job files** live in `/tmp/karaoke/{job_id}/src.mp4` (deleted after pitch-shift) and `out.mp3|mp4` (kept until the job expires).

**Frontend** (`frontend/index.html`) is a single self-contained file — vanilla JS, no build step. Theme (dark/light) persists in `localStorage` with a flash-free inline script in `<head>`. Semitone picker is a horizontal scrollable strip from −6 to +6. The mini player is a fixed bottom bar wired to the `<audio>` element.

## Key constraints

- HF Spaces free tier requires port **7860** and runs on x86_64 Linux.
- supervisord starts bgutil-pot (priority 1) before uvicorn (priority 2) — bgutil must be up before any download is attempted.
- `yt-dlp` is intentionally unpinned in `requirements.txt` to always get the latest version and avoid YouTube breakage.
- The rubberband ffmpeg filter is verified present at Docker **build** time (`ffmpeg -filters | grep rubberband`). If it's missing, the build fails. The fallback (`asetrate/aresample/atempo`) is documented in a comment in `pipeline.py` but requires a code change to activate.
- iOS Safari requires audio to be started by a direct user tap — `audio.play()` is only called from button `onclick` handlers, never programmatically on page load.

import uuid
import os
import base64
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.worker import create_job, get_job, enqueue, start_worker
from app.pipeline import get_video_info
import app.oauth as oauth

COOKIE_PATH = "/tmp/yt-cookies.txt"


def _write_cookies():
    raw = os.environ.get("YT_COOKIES_B64", "").strip()
    if not raw:
        return
    try:
        os.makedirs(os.path.dirname(COOKIE_PATH), exist_ok=True)
        with open(COOKIE_PATH, "wb") as f:
            f.write(base64.b64decode(raw))
    except Exception as e:
        print(f"[startup] failed to write YT cookies: {e}")


def _restore_oauth_token():
    raw = os.environ.get("YT_OAUTH2_TOKEN", "").strip()
    if raw:
        oauth.restore_token(raw)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _write_cookies()
    _restore_oauth_token()
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
        "status":   job["status"],
        "progress": job["progress"],
        "error":    job["error"],
    }


@app.get("/download/{job_id}")
async def download_file(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["status"] != "done":
        raise HTTPException(status_code=400, detail="Job not complete yet")
    path = job["output_path"]
    if not path or not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Output file missing")
    ext  = job["format"]
    mime = "audio/mpeg" if ext == "mp3" else "video/mp4"
    return FileResponse(path, media_type=mime, filename=f"karaoke_{job_id[:8]}.{ext}")


@app.get("/stream/{job_id}")
async def stream_file(job_id: str):
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


# ── Admin: OAuth2 device flow ──────────────────────────────────────────

@app.post("/admin/oauth2/start")
async def oauth2_start():
    oauth.start()
    return oauth.get_state()


@app.get("/admin/oauth2/status")
async def oauth2_status():
    return oauth.get_state()


@app.get("/admin/oauth2/token")
async def oauth2_export_token():
    """Return the token file base64-encoded so the user can save it as an HF secret."""
    b64 = oauth.read_token_b64()
    if not b64:
        raise HTTPException(status_code=404, detail="No token on disk yet")
    return {"token_b64": b64}


# ── Admin: cookie refresh (legacy) ────────────────────────────────────

@app.get("/admin/refresh-cookies")
async def refresh_cookies():
    _write_cookies()
    return {"ok": True, "cookie_file_present": os.path.exists(COOKIE_PATH)}


@app.get("/admin/yt-debug")
async def yt_debug():
    """Quick diagnostic: try yt-dlp info with verbose output captured."""
    import io, yt_dlp, subprocess, os
    from yt_dlp.networking.impersonate import ImpersonateTarget

    buf = io.StringIO()

    class _BufLogger:
        def debug(self, m): buf.write(f"[D] {m}\n")
        def info(self, m):  buf.write(f"[I] {m}\n")
        def warning(self, m): buf.write(f"[W] {m}\n")
        def error(self, m):   buf.write(f"[E] {m}\n")

    BGUTIL_URL = "http://127.0.0.1:4416"
    COOKIE_PATH = "/tmp/yt-cookies.txt"

    node_ver = subprocess.run(["node", "--version"], capture_output=True, text=True).stdout.strip()

    opts = {
        "quiet": True,
        "skip_download": True,
        "logger": _BufLogger(),
        "socket_timeout": 15,
        "remote_components": {"ejs:github"},
        "js_runtimes": {"node": {}},
        "extractor_args": {
            "youtube": {
                "player_client": ["web"],
                "getpot_bgutil_baseurl": [BGUTIL_URL],
            }
        },
    }
    if os.path.exists(COOKIE_PATH):
        opts["cookiefile"] = COOKIE_PATH

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info("https://www.youtube.com/watch?v=jNQXAC9IVRw", download=False)
        result = {"ok": True, "title": info.get("title"), "formats": len(info.get("formats", []))}
    except Exception as e:
        result = {"ok": False, "error": str(e)[:500]}

    result["node_version"] = node_ver
    result["cookie_present"] = os.path.exists(COOKIE_PATH)
    result["log_tail"] = buf.getvalue()[-2000:]
    return result


@app.get("/health")
async def health():
    return {"ok": True}

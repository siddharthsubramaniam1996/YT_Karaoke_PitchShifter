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
    """Fetch title + thumbnail for a YouTube URL before committing to download."""
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
        "status":   job["status"],    # queued | downloading | processing | done | error
        "progress": job["progress"],  # 0-100
        "error":    job["error"],
    }


@app.get("/download/{job_id}")
async def download_file(job_id: str):
    """
    Serve the processed file as an attachment (triggers save dialog).
    """
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
    Serve the processed file for inline browser playback (no save dialog).
    FastAPI's FileResponse handles HTTP 206 range requests natively,
    so the <audio> element can seek and scrub without extra code.
    Omitting the filename kwarg sets Content-Disposition: inline.
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

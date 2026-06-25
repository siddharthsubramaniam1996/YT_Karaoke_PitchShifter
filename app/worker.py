import os
import shutil
import threading
import time
import queue
import traceback
from app.pipeline import download_video, pitch_shift, TMP_BASE

_jobs: dict[str, dict] = {}
_lock = threading.Lock()
_queue: queue.Queue = queue.Queue()

JOB_TTL = 3600  # 1 hour


# ── Public API ──────────────────────────────────────────────────────────

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


# ── Internal helpers ────────────────────────────────────────────────────

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
                # Download counts as 0–70% of overall progress
                _update(job_id, progress=int(float(raw) * 0.70))
            except (ValueError, TypeError):
                pass

    try:
        src = download_video(job["url"], job_id, yt_hook)
        _update(job_id, status="processing", progress=72)

        out = pitch_shift(src, job["semitones"], job["format"], job_id)
        _update(job_id, status="done", progress=100, output_path=out)

    except Exception as e:
        _update(job_id, status="error", error=str(e) or repr(e) or traceback.format_exc()[-1000:])


def _loop():
    while True:
        job_id = _queue.get()
        try:
            _process(job_id)
        finally:
            _queue.task_done()


def _cleanup_loop():
    while True:
        time.sleep(600)
        now = time.time()
        with _lock:
            expired = [jid for jid, j in _jobs.items() if now - j["created_at"] > JOB_TTL]
        for jid in expired:
            shutil.rmtree(os.path.join(TMP_BASE, jid), ignore_errors=True)
            with _lock:
                _jobs.pop(jid, None)


def start_worker():
    threading.Thread(target=_loop, daemon=True).start()
    threading.Thread(target=_cleanup_loop, daemon=True).start()

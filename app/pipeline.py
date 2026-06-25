import os
import subprocess
import yt_dlp
from yt_dlp.networking.impersonate import ImpersonateTarget

TMP_BASE = "/tmp/karaoke"
BGUTIL_URL = "http://127.0.0.1:4416"
COOKIE_PATH = "/tmp/yt-cookies.txt"


def _cookie_opt() -> dict:
    return {"cookiefile": COOKIE_PATH} if os.path.exists(COOKIE_PATH) else {}


def _auth_opts() -> dict:
    """Return OAuth2 opts when the token is ready, else fall back to cookies."""
    try:
        from app.oauth import is_ready
        if is_ready():
            return {"username": "oauth2", "password": ""}
    except Exception:
        pass
    return _cookie_opt()


_BOT_PHRASES = ("sign in to confirm", "not a bot", "confirm you're not")

def _is_bot_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(p in msg for p in _BOT_PHRASES)


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
    tmp_dir = get_tmp_dir(job_id)

    ydl_opts = {
        "format": "bestvideo+bestaudio/bestvideo/best",
        "merge_output_format": "mp4",
        "outtmpl": os.path.join(tmp_dir, "src.%(ext)s"),
        "noplaylist": True,
        "max_filesize": 500 * 1024 * 1024,
        "progress_hooks": [progress_hook],
        "impersonate": ImpersonateTarget(client="chrome"),
        "remote_components": {"ejs:github"},  # n-challenge solver script
        "js_runtimes": {"node": {}},           # use Node.js for n-challenge
        "extractor_args": {
            "youtube": {
                "player_client": ["web"],
                "getpot_bgutil_baseurl": [BGUTIL_URL],
            }
        },
        **_auth_opts(),
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except Exception as e:
        if not _is_bot_error(e):
            raise
        # bgutil didn't resolve the bot check — retry with OAuth2 if the token
        # is on disk (e.g. restored from HF secret but is_ready() not yet set)
        from app.oauth import TOKEN_PATH
        if os.path.exists(TOKEN_PATH):
            retry_opts = {**ydl_opts, "username": "oauth2", "password": ""}
            retry_opts.pop("cookiefile", None)
            with yt_dlp.YoutubeDL(retry_opts) as ydl:
                ydl.download([url])
        else:
            raise RuntimeError(
                "YouTube is blocking this request. "
                "Open the ☰ menu and tap 'Authorize YouTube' to fix this permanently."
            ) from None

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
    Pitch-shift the audio by `semitones` without changing tempo.
    Uses ffmpeg's rubberband filter (--enable-librubberband must be
    present in the ffmpeg build — verified at Docker build time).

    Fallback comment: if rubberband is unavailable replace the af line with:
      af = f"asetrate=44100*{ratio:.6f},aresample=44100,atempo={1/ratio:.6f}"
    This changes pitch but slightly affects tempo — acceptable fallback.
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
            "-c:v", "copy",        # video stream copied untouched
            "-c:a", "aac", "-b:a", "192k",
            out,
        ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed:\n{result.stderr[-2000:]}")

    # Remove the large source file to save disk space
    if os.path.exists(src_path):
        os.remove(src_path)

    return out


def get_video_info(url: str) -> dict:
    """
    Fetch title, thumbnail, duration, and channel without downloading.
    Uses bgutil-pot so the metadata request isn't bot-blocked on cloud IPs.
    """
    ydl_opts = {
        "quiet": True,
        "skip_download": True,
        "socket_timeout": 15,
        "impersonate": ImpersonateTarget(client="chrome"),
        "remote_components": {"ejs:github"},
        "js_runtimes": {"node": {}},
        "extractor_args": {
            "youtube": {
                "player_client": ["web"],
                "getpot_bgutil_baseurl": [BGUTIL_URL],
            }
        },
        **_auth_opts(),
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        dur = int(info.get("duration") or 0)
        mins, secs = divmod(dur, 60)
        return {
            "title":     info.get("title", "Unknown"),
            "thumbnail": info.get("thumbnail", ""),
            "duration":  f"{mins}:{secs:02d}",
            "channel":   info.get("channel", ""),
        }

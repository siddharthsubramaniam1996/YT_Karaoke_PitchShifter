import os
import subprocess
import yt_dlp
from urllib.parse import urlparse, urlencode, parse_qsl

TMP_BASE = "/tmp/karaoke"
COOKIE_PATH = "/tmp/yt-cookies.txt"


def _strip_list_param(url: str) -> str:
    p = urlparse(url)
    qs = urlencode([(k, v) for k, v in parse_qsl(p.query) if k != "list"])
    return p._replace(query=qs).geturl()


def _cookie_opt() -> dict:
    return {"cookiefile": COOKIE_PATH} if os.path.exists(COOKIE_PATH) else {}


def _auth_opts() -> dict:
    return _cookie_opt()


def semitones_to_ratio(semitones: int) -> float:
    return 2 ** (semitones / 12)


def get_tmp_dir(job_id: str) -> str:
    path = os.path.join(TMP_BASE, job_id)
    os.makedirs(path, exist_ok=True)
    return path


def download_video(url: str, job_id: str, progress_hook) -> str:
    url = _strip_list_param(url)
    tmp_dir = get_tmp_dir(job_id)

    proxy = os.environ.get("YTDLP_PROXY", "")
    ydl_opts = {
        "format": "bestvideo+bestaudio/bestvideo/best",
        "merge_output_format": "mp4",
        "outtmpl": os.path.join(tmp_dir, "src.%(ext)s"),
        "noplaylist": True,
        "max_filesize": 500 * 1024 * 1024,
        "progress_hooks": [progress_hook],
        "extractor_args": {
            "youtube": {"player_client": ["ios"]},
            "youtubetab": {"skip": ["authcheck"]},
        },
        **(_auth_opts() | ({"proxy": proxy} if proxy else {})),
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
    Uses ffmpeg rubberband filter (verified present at Docker build time).

    Fallback if rubberband unavailable:
      af = f"asetrate=44100*{ratio:.6f},aresample=44100,atempo={1/ratio:.6f}"
    """
    tmp_dir = get_tmp_dir(job_id)
    ratio = semitones_to_ratio(semitones)
    af = f"rubberband=pitch={ratio:.6f}"

    if fmt == "mp3":
        out = os.path.join(tmp_dir, "out.mp3")
        cmd = [
            "ffmpeg", "-y", "-i", src_path,
            "-vn", "-af", af,
            "-c:a", "libmp3lame", "-q:a", "2",
            out,
        ]
    else:
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
    url = _strip_list_param(url)
    proxy = os.environ.get("YTDLP_PROXY", "")
    ydl_opts = {
        "quiet": True,
        "skip_download": True,
        "socket_timeout": 15,
        "extractor_args": {
            "youtube": {"player_client": ["ios"]},
            "youtubetab": {"skip": ["authcheck"]},
        },
        **(_auth_opts() | ({"proxy": proxy} if proxy else {})),
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

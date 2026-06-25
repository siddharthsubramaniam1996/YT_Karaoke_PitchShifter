import os
import subprocess
import yt_dlp

TMP_BASE = "/tmp/karaoke"
BGUTIL_URL = "http://127.0.0.1:4416"


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
    Returns path to the downloaded src.mp4.
    """
    tmp_dir = get_tmp_dir(job_id)

    ydl_opts = {
        "format": "bv*+ba/b",
        "merge_output_format": "mp4",
        "outtmpl": os.path.join(tmp_dir, "src.%(ext)s"),
        "noplaylist": True,
        "max_filesize": 500 * 1024 * 1024,
        "progress_hooks": [progress_hook],
        "impersonate": "chrome",
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
        "socket_timeout": 8,
        "impersonate": "chrome",
        "extractor_args": {
            "youtube": {
                "getpot_bgutil_baseurl": [BGUTIL_URL]
            }
        },
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

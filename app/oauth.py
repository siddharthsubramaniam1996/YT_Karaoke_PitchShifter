"""
YouTube OAuth2 device flow via yt-dlp-youtube-oauth2 plugin.

Token is stored at TOKEN_PATH by yt-dlp's cache layer. On startup,
main.py restores it from the YT_OAUTH2_TOKEN env var so the user
only needs to re-auth if that secret is missing or expired.
"""

import os
import re
import threading

# yt-dlp cache stores the plugin token here on Linux/container
TOKEN_PATH = os.path.expanduser("~/.cache/yt-dlp/youtube-oauth2/token.json")

_state = {
    "status": "idle",   # idle | running | needs_auth | done | error
    "code": "",
    "url":  "https://www.youtube.com/activate",
    "message": "",
}
_lock  = threading.Lock()
_ready = False


# ── Public helpers ─────────────────────────────────────────────────────

def is_ready() -> bool:
    return _ready


def get_state() -> dict:
    with _lock:
        return dict(_state)


def restore_token(b64_data: str):
    """Decode a base64 token blob saved as an HF secret and write it to TOKEN_PATH."""
    import base64
    try:
        os.makedirs(os.path.dirname(TOKEN_PATH), exist_ok=True)
        with open(TOKEN_PATH, "wb") as f:
            f.write(base64.b64decode(b64_data))
        global _ready
        _ready = True
        with _lock:
            _state.update(status="done", message="Token restored from secret")
    except Exception as e:
        print(f"[oauth] failed to restore token: {e}")


def read_token_b64() -> str | None:
    """Return the current token file base64-encoded, or None if absent."""
    import base64
    if not os.path.exists(TOKEN_PATH):
        return None
    with open(TOKEN_PATH, "rb") as f:
        return base64.b64encode(f.read()).decode()


# ── OAuth device flow ──────────────────────────────────────────────────

class _Logger:
    """Intercepts yt-dlp screen output to capture the device code."""
    _CODE = re.compile(r'([A-Z0-9]{4}-[A-Z0-9]{4})')
    _URL  = re.compile(r'https?://\S+')

    def _handle(self, msg: str):
        msg = str(msg)
        if 'youtube.com/activate' in msg.lower() or self._CODE.search(msg):
            code_m = self._CODE.search(msg)
            url_m  = self._URL.search(msg)
            with _lock:
                _state.update(
                    status  = "needs_auth",
                    code    = code_m.group(1) if code_m else "",
                    url     = url_m.group(0)  if url_m  else "https://www.youtube.com/activate",
                    message = msg.strip(),
                )

    def debug(self, msg):   self._handle(msg)
    def info(self, msg):    self._handle(msg)
    def warning(self, msg): pass
    def error(self, msg):
        with _lock:
            _state.update(status="error", message=str(msg)[:300])


def _do_oauth():
    global _ready
    import yt_dlp
    from yt_dlp.networking.impersonate import ImpersonateTarget

    with _lock:
        _state.update(status="running", code="", message="Connecting to YouTube…")

    try:
        opts = {
            "quiet": False,
            "logger": _Logger(),
            "skip_download": True,
            "username": "oauth2",
            "password": "",
            "impersonate": ImpersonateTarget(client="chrome"),
            "extractor_args": {"youtube": {"player_client": ["ios", "web"]}},
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            # Any YouTube URL triggers the auth flow; info fetch is lightweight
            ydl.extract_info(
                "https://www.youtube.com/watch?v=jNQXAC9IVRw",
                download=False,
            )
        _ready = True
        with _lock:
            _state.update(status="done", message="Authorized — downloads are unlocked")

    except Exception as e:
        with _lock:
            cur = _state["status"]
        # After the user authorizes, the token is saved even if extract_info
        # then fails (e.g. bot-check still applies to metadata). Treat any
        # state that reached needs_auth as success if the token file appeared.
        if cur in ("needs_auth", "running") and os.path.exists(TOKEN_PATH):
            _ready = True
            with _lock:
                _state.update(status="done", message="Authorized — downloads are unlocked")
        elif cur not in ("done",):
            with _lock:
                _state.update(status="error", message=str(e)[:300])


def start():
    """Kick off the OAuth device flow in a background daemon thread."""
    with _lock:
        if _state["status"] in ("running", "needs_auth"):
            return
    threading.Thread(target=_do_oauth, daemon=True).start()

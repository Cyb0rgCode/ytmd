#!/usr/bin/env python3
"""Telegram YouTube Music downloader bot.

Two run modes:
  default   - one-shot poll (for GitHub Actions cron): fetch pending
              updates, process them, acknowledge, exit.
  --loop    - persistent long-polling (for Render/Railway/any container
              host): replies within seconds. Also serves a tiny HTTP
              health endpoint on $PORT so free web-service tiers accept it.

For every message containing a YouTube / YouTube Music URL, the bot
downloads the audio with yt-dlp and sends it back as a tagged MP3.

Required environment:
  TELEGRAM_BOT_TOKEN  - bot token from @BotFather

Optional environment:
  PORT                - health endpoint port in --loop mode (default 10000)
  YTDLP_COOKIES       - contents of a Netscape cookies.txt; helps when
                        YouTube blocks datacenter IPs with a bot check.
"""

import hashlib
import html
import os
import re
import shutil
import sys
import tempfile
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, HTTPServer

import requests
import yt_dlp

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
API = f"https://api.telegram.org/bot{BOT_TOKEN}"

# Telegram bots can upload files up to 50 MB.
MAX_UPLOAD_BYTES = 49 * 1024 * 1024

YOUTUBE_URL_RE = re.compile(
    r"https?://(?:www\.|m\.|music\.)?"
    r"(?:youtube\.com/(?:watch\?[^\s]*v=[\w-]{11}[^\s]*|shorts/[\w-]{11}[^\s]*)"
    r"|youtu\.be/[\w-]{11}[^\s]*)",
    re.IGNORECASE,
)

START_TEXT = (
    "Hi! Send me a YouTube Music (or regular YouTube) link and I'll reply "
    "with the audio file.\n\n"
    "Example:\nhttps://music.youtube.com/watch?v=dQw4w9WgXcQ"
)


def tg(method: str, **params):
    """Call a Telegram Bot API method and return the decoded result."""
    resp = requests.post(f"{API}/{method}", data=params, timeout=60)
    payload = resp.json()
    if not payload.get("ok"):
        raise RuntimeError(f"Telegram {method} failed: {payload}")
    return payload["result"]


def send_text(chat_id: int, text: str, reply_to: int | None = None):
    params = {"chat_id": chat_id, "text": text, "disable_web_page_preview": True}
    if reply_to:
        params["reply_to_message_id"] = reply_to
        params["allow_sending_without_reply"] = True
    return tg("sendMessage", **params)


def edit_text(chat_id: int, message_id: int, text: str):
    try:
        tg("editMessageText", chat_id=chat_id, message_id=message_id, text=text)
    except Exception:
        pass  # editing a status message is best-effort


def cookies_file() -> str | None:
    raw = os.environ.get("YTDLP_COOKIES", "").strip()
    if not raw:
        return None
    fd, path = tempfile.mkstemp(prefix="ytmd-cookies-", suffix=".txt")
    with os.fdopen(fd, "w") as fh:
        fh.write(raw + "\n")
    return path


def download_audio(url: str, workdir: str, cookies: str | None) -> tuple[str, dict]:
    """Download a single track. Returns (filepath, info).

    With ffmpeg available: converted to tagged 192 kbps MP3 with cover art.
    Without ffmpeg (serverless hosts like Vercel): YouTube's native AAC
    (.m4a) is sent as-is — same source quality, no transcode.
    """
    have_ffmpeg = shutil.which("ffmpeg") is not None
    opts = {
        "outtmpl": os.path.join(workdir, "%(id)s.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
    }
    if have_ffmpeg:
        opts.update(
            {
                "format": "bestaudio/best",
                "postprocessors": [
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": "192",
                    },
                    {"key": "FFmpegMetadata"},
                    {"key": "EmbedThumbnail"},
                ],
                "writethumbnail": True,
            }
        )
    else:
        opts["format"] = "bestaudio[ext=m4a]/bestaudio/best"
    if cookies:
        opts["cookiefile"] = cookies

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        path = ydl.prepare_filename(info)
    if have_ffmpeg:
        path = os.path.splitext(path)[0] + ".mp3"

    if not os.path.exists(path):
        raise RuntimeError("download finished but output file is missing")
    return path, info


AUDIO_MIME = {
    "mp3": "audio/mpeg",
    "m4a": "audio/mp4",
    "webm": "audio/webm",
    "opus": "audio/ogg",
    "ogg": "audio/ogg",
}


def send_audio(chat_id: int, path: str, info: dict, reply_to: int | None):
    title = info.get("track") or info.get("title") or "audio"
    performer = info.get("artist") or info.get("uploader") or ""
    ext = os.path.splitext(path)[1].lstrip(".").lower() or "mp3"
    with open(path, "rb") as fh:
        resp = requests.post(
            f"{API}/sendAudio",
            data={
                "chat_id": chat_id,
                "title": title,
                "performer": performer,
                "duration": int(info.get("duration") or 0),
                **(
                    {
                        "reply_to_message_id": reply_to,
                        "allow_sending_without_reply": True,
                    }
                    if reply_to
                    else {}
                ),
            },
            files={
                "audio": (
                    f"{title}.{ext}",
                    fh,
                    AUDIO_MIME.get(ext, "application/octet-stream"),
                )
            },
            timeout=300,
        )
    payload = resp.json()
    if not payload.get("ok"):
        raise RuntimeError(f"sendAudio failed: {payload}")


def webhook_secret() -> str:
    """Deterministic secret for Telegram's X-Telegram-Bot-Api-Secret-Token.

    Derived from the bot token so webhook mode needs no extra configuration.
    """
    return hashlib.sha256(f"ytmd:{BOT_TOKEN}".encode()).hexdigest()[:32]


def handle_message(msg: dict, cookies: str | None):
    chat_id = msg["chat"]["id"]
    message_id = msg.get("message_id")
    text = msg.get("text") or msg.get("caption") or ""

    if text.strip().startswith("/start") or text.strip().startswith("/help"):
        send_text(chat_id, START_TEXT)
        return

    urls = YOUTUBE_URL_RE.findall(text)
    if not urls:
        if msg["chat"].get("type") == "private":
            send_text(
                chat_id,
                "I couldn't find a YouTube / YouTube Music link in that message. "
                "Send me a link like https://music.youtube.com/watch?v=...",
                reply_to=message_id,
            )
        return

    for url in urls[:3]:  # cap per message to keep runs short
        status = send_text(chat_id, f"⏬ Downloading {html.unescape(url)} ...", reply_to=message_id)
        try:
            with tempfile.TemporaryDirectory(prefix="ytmd-") as workdir:
                path, info = download_audio(url, workdir, cookies)
                size = os.path.getsize(path)
                if size > MAX_UPLOAD_BYTES:
                    edit_text(
                        chat_id,
                        status["message_id"],
                        f"❌ File is {size / 1024 / 1024:.1f} MB — over Telegram's "
                        "50 MB bot upload limit.",
                    )
                    continue
                edit_text(chat_id, status["message_id"], "⏫ Uploading ...")
                send_audio(chat_id, path, info, reply_to=message_id)
                tg("deleteMessage", chat_id=chat_id, message_id=status["message_id"])
        except Exception as exc:  # noqa: BLE001 - report failure to the user
            traceback.print_exc()
            edit_text(
                chat_id,
                status["message_id"],
                f"❌ Download failed: {str(exc)[:300]}",
            )


def process_updates(updates: list, cookies: str | None):
    for update in updates:
        msg = update.get("message")
        if msg:
            try:
                handle_message(msg, cookies)
            except Exception:  # keep going; one bad message must not stall the queue
                traceback.print_exc()


def run_once() -> int:
    """One-shot mode for GitHub Actions cron."""
    updates = tg("getUpdates", timeout=0, limit=100, allowed_updates='["message"]')
    if not updates:
        print("No pending updates.")
        return 0

    print(f"Processing {len(updates)} update(s)...")
    process_updates(updates, cookies_file())

    # Acknowledge everything we just processed so the next run starts fresh.
    last_id = updates[-1]["update_id"]
    tg("getUpdates", offset=last_id + 1, limit=1, timeout=0)
    print("Done.")
    return 0


class _Health(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 - stdlib naming
        body = b"ok\n"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # silence per-request logging
        pass


def start_health_server():
    port = int(os.environ.get("PORT", "10000"))
    server = HTTPServer(("0.0.0.0", port), _Health)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"Health endpoint listening on :{port}")


def run_loop() -> int:
    """Persistent long-polling mode for Render/Railway/containers."""
    start_health_server()
    cookies = cookies_file()
    offset = None
    print("Long-polling Telegram...")
    while True:
        try:
            params = {"timeout": 50, "limit": 100, "allowed_updates": '["message"]'}
            if offset is not None:
                params["offset"] = offset
            updates = tg("getUpdates", **params)
        except Exception as exc:  # network blip / Telegram hiccup: back off, retry
            print(f"getUpdates error, retrying in 5s: {exc}", file=sys.stderr)
            time.sleep(5)
            continue
        if updates:
            offset = updates[-1]["update_id"] + 1
            process_updates(updates, cookies)


def main() -> int:
    if not BOT_TOKEN:
        print("TELEGRAM_BOT_TOKEN is not set", file=sys.stderr)
        return 1
    if "--loop" in sys.argv:
        return run_loop()
    return run_once()


if __name__ == "__main__":
    sys.exit(main())

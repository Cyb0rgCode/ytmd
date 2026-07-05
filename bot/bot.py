#!/usr/bin/env python3
"""Telegram YouTube Music downloader bot.

Runs as a short-lived poller (designed for GitHub Actions cron):
  1. Fetches pending Telegram updates via getUpdates.
  2. For every message containing a YouTube / YouTube Music URL,
     downloads the audio with yt-dlp and sends it back as an MP3.
  3. Acknowledges the processed updates so the next run starts clean.

Required environment:
  TELEGRAM_BOT_TOKEN  - bot token from @BotFather

Optional environment:
  YTDLP_COOKIES       - contents of a Netscape cookies.txt; helps when
                        YouTube blocks datacenter IPs with a bot check.
"""

import html
import os
import re
import sys
import tempfile
import traceback

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
    "with the audio as an MP3.\n\n"
    "Example:\nhttps://music.youtube.com/watch?v=dQw4w9WgXcQ\n\n"
    "Note: I run on a schedule, so replies can take a few minutes."
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
    """Download a single track as MP3. Returns (filepath, info)."""
    opts = {
        "format": "bestaudio/best",
        "outtmpl": os.path.join(workdir, "%(id)s.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
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
    if cookies:
        opts["cookiefile"] = cookies

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)

    path = os.path.join(workdir, f"{info['id']}.mp3")
    if not os.path.exists(path):
        raise RuntimeError("download finished but output file is missing")
    return path, info


def send_audio(chat_id: int, path: str, info: dict, reply_to: int | None):
    title = info.get("track") or info.get("title") or "audio"
    performer = info.get("artist") or info.get("uploader") or ""
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
            files={"audio": (f"{title}.mp3", fh, "audio/mpeg")},
            timeout=300,
        )
    payload = resp.json()
    if not payload.get("ok"):
        raise RuntimeError(f"sendAudio failed: {payload}")


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


def main() -> int:
    if not BOT_TOKEN:
        print("TELEGRAM_BOT_TOKEN is not set", file=sys.stderr)
        return 1

    updates = tg("getUpdates", timeout=0, limit=100, allowed_updates='["message"]')
    if not updates:
        print("No pending updates.")
        return 0

    print(f"Processing {len(updates)} update(s)...")
    cookies = cookies_file()
    for update in updates:
        msg = update.get("message")
        if msg:
            try:
                handle_message(msg, cookies)
            except Exception:  # keep going; one bad message must not stall the queue
                traceback.print_exc()

    # Acknowledge everything we just processed so the next run starts fresh.
    last_id = updates[-1]["update_id"]
    tg("getUpdates", offset=last_id + 1, limit=1, timeout=0)
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

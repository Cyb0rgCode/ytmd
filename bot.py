#!/usr/bin/env python3
"""Telegram YouTube Music downloader bot.

Two run modes:
  default   - one-shot poll (for GitHub Actions cron): fetch pending
              updates, process them, acknowledge, exit.
  --loop    - persistent long-polling (for Render/Railway/any container
              host): replies within seconds. Also serves a tiny HTTP
              health endpoint on $PORT so free web-service tiers accept it.

For every message containing a YouTube Music (music.youtube.com) URL, the
bot downloads the audio with yt-dlp and sends it back. Regular YouTube
links are rejected with a hint.

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
from ytmusicapi import YTMusic

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
API = f"https://api.telegram.org/bot{BOT_TOKEN}"

# Telegram bots can upload files up to 50 MB.
MAX_UPLOAD_BYTES = 49 * 1024 * 1024

# Characters that stop a match: whitespace, and punctuation that's almost
# always sentence/markdown decoration around a pasted link rather than part
# of it (trailing '.', a closing ')' from "(link)", a closing bracket from
# "[text](link)", etc.) — without this, those chars get vacuumed into the
# URL and corrupt the request.
_STOP_CHARS = r"\s\)\]\}>,;:!.\"'"

# https://music.youtube.com/watch?v=ID[&si=...][&t=42][&list=...] is the
# only share format the app produces (default share, timestamp share,
# sharing from within an album/playlist) — no youtu.be-style short link
# exists for YouTube Music. Scheme and "www." are optional since share
# sheets / chat apps often strip or never had them.
YT_MUSIC_URL_RE = re.compile(
    rf"(?:https?://)?(?:www\.)?music\.youtube\.com/watch\?"
    rf"[^{_STOP_CHARS}]*v=[\w-]{{11}}[^{_STOP_CHARS}]*",
    re.IGNORECASE,
)

# Recognized only to explain the rejection — never downloaded.
OTHER_YOUTUBE_URL_RE = re.compile(
    rf"(?:https?://)?(?:www\.|m\.)?(?:youtube\.com/|youtu\.be/)[^{_STOP_CHARS}]+",
    re.IGNORECASE,
)


def _normalize_url(url: str) -> str:
    """Add a scheme back if the pasted link was missing one."""
    return url if url.lower().startswith("http") else f"https://{url}"

START_TEXT = (
    "Hi! Send me a YouTube Music link and I'll reply with the audio file.\n\n"
    "Example:\nhttps://music.youtube.com/watch?v=dQw4w9WgXcQ\n\n"
    "Only music.youtube.com links are accepted."
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


def _ydl_opts(workdir: str, cookies: str | None) -> tuple[dict, bool]:
    """Base yt-dlp options.

    With ffmpeg available: convert to tagged 192 kbps MP3 with cover art.
    Without ffmpeg (serverless hosts like Vercel): YouTube's native AAC
    (.m4a) is kept as-is — same source quality, no transcode.
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
    return opts, have_ffmpeg


def _extract(target: str, opts: dict, have_ffmpeg: bool) -> tuple[str, dict]:
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(target, download=True)
        if info.get("entries") is not None:  # ytsearch result wrapper
            entries = [e for e in info["entries"] if e]
            if not entries:
                raise yt_dlp.utils.DownloadError("no search results")
            info = entries[0]
        path = ydl.prepare_filename(info)
    if have_ffmpeg:
        path = os.path.splitext(path)[0] + ".mp3"
    if not os.path.exists(path):
        raise RuntimeError("download finished but output file is missing")
    return path, info


UNAVAILABLE_RE = re.compile(
    r"video unavailable|not available|isn.?t available", re.IGNORECASE
)

BOT_CHECK_RE = re.compile(
    r"sign in to confirm|confirm you.{0,3}re not a bot", re.IGNORECASE
)


def _video_id(url: str) -> str | None:
    m = re.search(r"(?:v=|youtu\.be/|/shorts/)([\w-]{11})", url)
    return m.group(1) if m else None


def _oembed_query(video_id: str) -> str | None:
    """Title/artist of a video via oEmbed, which works across regions even
    when playback of that exact ID does not."""
    try:
        resp = requests.get(
            "https://www.youtube.com/oembed",
            params={
                "url": f"https://www.youtube.com/watch?v={video_id}",
                "format": "json",
            },
            timeout=15,
        )
        if resp.ok:
            data = resp.json()
            author = (data.get("author_name") or "").removesuffix(" - Topic")
            query = f"{author} {data.get('title') or ''}".strip()
            return query or None
    except Exception:  # any network/parsing hiccup: this is a best-effort lookup
        pass
    return None


def _music_track_query(video_id: str) -> str | None:
    """Title/artist straight from YouTube Music's own API (ytmusicapi)."""
    try:
        details = YTMusic().get_song(video_id).get("videoDetails") or {}
        title = details.get("title") or ""
        author = (details.get("author") or "").removesuffix(" - Topic")
        query = f"{author} {title}".strip()
        return query or None
    except Exception:
        return None


def _music_search_id(query: str, exclude: str | None) -> str | None:
    """Top matching *song* on YouTube Music for the query (songs only —
    never regular YouTube videos)."""
    try:
        for result in YTMusic().search(query, filter="songs", limit=5):
            vid = result.get("videoId")
            if vid and vid != exclude:
                return vid
    except Exception:
        pass
    return None


def _client_opts(opts: dict, *clients: str) -> dict:
    return {**opts, "extractor_args": {"youtube": {"player_client": list(clients)}}}


def download_audio(url: str, workdir: str, cookies: str | None) -> tuple[str, dict]:
    """Download a single track. Returns (filepath, info).

    Two distinct YouTube failure modes need different handling:

    1. Region-locked IDs: YouTube Music art-track IDs are
       region/distributor-dependent — an ID that plays for the user can be
       "Video unavailable" from the server's region (yt-dlp #14066).
       Fallback: retry with the YouTube Music player client, then resolve
       the track via YouTube Music's API (ytmusicapi) — title/artist
       lookup, songs-only search — and download the matching track.
    2. Bot checks ("Sign in to confirm you're not a bot"): YouTube
       challenges cloud/datacenter IPs regardless of which track it is.
       Retrying with cookie-compatible player clients sometimes helps;
       the reliable fix is a YTDLP_COOKIES secret.
    """
    opts, have_ffmpeg = _ydl_opts(workdir, cookies)

    attempts = [(url, opts)]
    if "music.youtube.com" in url:
        attempts.append((url, _client_opts(opts, "web_music")))
        attempts.append((url, _client_opts(opts, "android", "web", "mweb")))

    last_exc: Exception | None = None
    last_kind: str | None = None  # 'unavailable' | 'bot_check'
    for target, attempt_opts in attempts:
        try:
            return _extract(target, attempt_opts, have_ffmpeg)
        except yt_dlp.utils.DownloadError as exc:
            text = str(exc)
            if BOT_CHECK_RE.search(text):
                last_exc, last_kind = exc, "bot_check"
            elif UNAVAILABLE_RE.search(text):
                last_exc, last_kind = exc, "unavailable"
            else:
                raise

    if last_kind == "bot_check":
        raise RuntimeError(
            "YouTube is challenging this server as a bot (a well-known "
            "issue for cloud-hosted downloaders, not specific to this "
            "track). Fix: add a YTDLP_COOKIES secret with your browser's "
            "youtube.com cookies — see the README's 'YouTube bot checks' "
            "section."
        ) from last_exc

    video_id = _video_id(url)
    music_query = _music_track_query(video_id) if video_id else None
    query = music_query or (_oembed_query(video_id) if video_id else None)
    alt_id = _music_search_id(query, exclude=video_id) if query else None
    if alt_id:
        try:
            return _extract(
                f"https://music.youtube.com/watch?v={alt_id}",
                _client_opts(opts, "web_music"),
                have_ffmpeg,
            )
        except yt_dlp.utils.DownloadError:
            pass

    debug = (
        f"[resolve: query={'ytmusic' if music_query else ('oembed' if query else 'none')}, "
        f"alt_id={alt_id or 'none'}]"
    )
    raise RuntimeError(
        "this track isn't playable from the bot's server region (a YouTube "
        "Music region-locked ID) and the fallback search found no working "
        "copy. Adding a YTDLP_COOKIES secret (see README) usually fixes it. "
        f"{debug}"
    ) from last_exc


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


def running_commit() -> str:
    """Short commit hash of the code actually running, if the host exposes
    it (Vercel sets VERCEL_GIT_COMMIT_SHA automatically); else 'unknown'."""
    sha = (
        os.environ.get("VERCEL_GIT_COMMIT_SHA")
        or os.environ.get("RENDER_GIT_COMMIT")
        or os.environ.get("GITHUB_SHA")
        or ""
    )
    return sha[:7] if sha else "unknown"


def handle_message(msg: dict, cookies: str | None):
    chat_id = msg["chat"]["id"]
    message_id = msg.get("message_id")
    text = msg.get("text") or msg.get("caption") or ""

    if text.strip().startswith("/start") or text.strip().startswith("/help"):
        send_text(chat_id, START_TEXT)
        return

    if text.strip().startswith("/version"):
        send_text(chat_id, f"Running commit: {running_commit()}")
        return

    urls = [_normalize_url(u) for u in YT_MUSIC_URL_RE.findall(text)]
    if not urls:
        if OTHER_YOUTUBE_URL_RE.search(text):
            send_text(
                chat_id,
                "That's a regular YouTube link — I only accept YouTube Music "
                "links (music.youtube.com). Open the song in YouTube Music "
                "and use Share to copy its link.",
                reply_to=message_id,
            )
        elif msg["chat"].get("type") == "private":
            send_text(
                chat_id,
                "I couldn't find a YouTube Music link in that message. "
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

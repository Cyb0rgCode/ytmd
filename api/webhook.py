"""Telegram webhook receiver (Vercel serverless function).

Telegram POSTs each update here the instant a message arrives; the track
is downloaded and sent back within the same request. Visit /api/setup
once after deploying to register this endpoint with Telegram.
"""

import json
import os
import sys
import traceback
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bot  # noqa: E402


class handler(BaseHTTPRequestHandler):  # noqa: N801 - Vercel requires this name
    def _respond(self, code: int, text: str):
        body = text.encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        self._respond(200, "ytmd webhook is up. POST from Telegram only.")

    def do_POST(self):  # noqa: N802
        if not bot.BOT_TOKEN:
            self._respond(500, "TELEGRAM_BOT_TOKEN is not configured")
            return
        # Only accept requests carrying the secret we registered in setup.
        got = self.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if got != bot.webhook_secret():
            self._respond(403, "forbidden")
            return

        length = int(self.headers.get("Content-Length") or 0)
        try:
            update = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self._respond(400, "bad json")
            return

        msg = update.get("message")
        if msg:
            try:
                bot.handle_message(msg, bot.cookies_file())
            except Exception:
                # Report 200 anyway: Telegram would otherwise retry the same
                # update forever; the user already got an error reply in chat.
                traceback.print_exc()
        self._respond(200, "ok")

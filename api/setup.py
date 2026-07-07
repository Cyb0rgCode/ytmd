"""One-time webhook registration (Vercel serverless function).

Open https://<your-app>.vercel.app/api/setup in a browser after deploying:
it tells Telegram to deliver updates to /api/webhook on this deployment.
Add ?remove=1 to unregister (e.g. to switch back to polling mode).

Safe to expose: it only ever points the webhook at this same deployment,
and registers a secret header that /api/webhook then requires.
"""

import os
import sys
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bot  # noqa: E402


def public_host(headers) -> str:
    return (
        os.environ.get("VERCEL_PROJECT_PRODUCTION_URL")
        or os.environ.get("VERCEL_URL")
        or headers.get("host", "")
    )


class handler(BaseHTTPRequestHandler):  # noqa: N801 - Vercel requires this name
    def _respond(self, code: int, text: str):
        body = text.encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        if not bot.BOT_TOKEN:
            self._respond(
                500,
                "TELEGRAM_BOT_TOKEN is not set. Add it in Vercel: "
                "Project → Settings → Environment Variables, then redeploy.",
            )
            return

        query = parse_qs(urlparse(self.path).query)
        try:
            if query.get("remove"):
                bot.tg("deleteWebhook")
                self._respond(200, "Webhook removed. The bot is back to polling mode.")
                return

            url = f"https://{public_host(self.headers)}/api/webhook"
            bot.tg(
                "setWebhook",
                url=url,
                secret_token=bot.webhook_secret(),
                allowed_updates='["message"]',
                drop_pending_updates=True,
            )
            me = bot.tg("getMe")
            self._respond(
                200,
                f"✅ Webhook registered: {url}\n"
                f"Bot: @{me.get('username')}\n\n"
                "Send your bot a YouTube Music link — it replies instantly.",
            )
        except Exception as exc:  # surface Telegram errors to the browser
            self._respond(500, f"Setup failed: {exc}")

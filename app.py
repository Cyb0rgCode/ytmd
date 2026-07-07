"""Vercel entrypoint: a minimal WSGI app exposing the bot over HTTP.

Routes:
  POST /api/webhook   - Telegram pushes updates here (instant replies).
  GET  /api/setup     - visit once after deploying to register the webhook
                        with Telegram; add ?remove=1 to unregister.
  GET  /              - health/info.

Set the TELEGRAM_BOT_TOKEN environment variable in the Vercel project.
"""

import json
import os
import traceback
from urllib.parse import parse_qs

import bot

SETUP_HINT = (
    "ytmd bot is deployed.\n\n"
    "Visit /api/setup once to connect it to Telegram, "
    "then send your bot a YouTube Music link."
)


def _public_host(environ) -> str:
    return (
        os.environ.get("VERCEL_PROJECT_PRODUCTION_URL")
        or os.environ.get("VERCEL_URL")
        or environ.get("HTTP_HOST", "")
    )


def _setup(environ) -> tuple[str, str]:
    query = parse_qs(environ.get("QUERY_STRING", ""))
    if query.get("remove"):
        bot.tg("deleteWebhook")
        return "200 OK", "Webhook removed. The bot is back to polling mode."

    url = f"https://{_public_host(environ)}/api/webhook"
    bot.tg(
        "setWebhook",
        url=url,
        secret_token=bot.webhook_secret(),
        allowed_updates='["message"]',
        drop_pending_updates=True,
    )
    me = bot.tg("getMe")
    return "200 OK", (
        f"✅ Webhook registered: {url}\n"
        f"Bot: @{me.get('username')}\n\n"
        "Send your bot a YouTube Music link — it replies instantly."
    )


def _webhook(environ) -> tuple[str, str]:
    # Only accept requests carrying the secret registered during setup.
    got = environ.get("HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN", "")
    if got != bot.webhook_secret():
        return "403 Forbidden", "forbidden"

    length = int(environ.get("CONTENT_LENGTH") or 0)
    try:
        update = json.loads(environ["wsgi.input"].read(length) or b"{}")
    except json.JSONDecodeError:
        return "400 Bad Request", "bad json"

    msg = update.get("message")
    if msg:
        try:
            bot.handle_message(msg, bot.cookies_file())
        except Exception:
            # Return 200 anyway: Telegram would otherwise retry the same
            # update forever; the user already got an error reply in chat.
            traceback.print_exc()
    return "200 OK", "ok"


def app(environ, start_response):
    path = environ.get("PATH_INFO", "/")
    method = environ.get("REQUEST_METHOD", "GET")

    try:
        if not bot.BOT_TOKEN:
            status, text = "500 Internal Server Error", (
                "TELEGRAM_BOT_TOKEN is not set. Add it in Vercel: "
                "Project → Settings → Environment Variables, then redeploy."
            )
        elif path == "/api/webhook" and method == "POST":
            status, text = _webhook(environ)
        elif path == "/api/setup" and method == "GET":
            status, text = _setup(environ)
        else:
            status, text = "200 OK", SETUP_HINT
    except Exception as exc:  # surface config/Telegram errors to the browser
        traceback.print_exc()
        status, text = "500 Internal Server Error", f"Error: {exc}"

    body = text.encode()
    start_response(
        status,
        [
            ("Content-Type", "text/plain; charset=utf-8"),
            ("Content-Length", str(len(body))),
        ],
    )
    return [body]

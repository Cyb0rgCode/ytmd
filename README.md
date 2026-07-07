# ytmd — Telegram YouTube Music Downloader

A Telegram bot that converts YouTube Music (and regular YouTube) links into
MP3s — free, no server to rent.

Three ways to run the same code — pick one:

| Mode | Where it runs | Reply speed | Needs |
|---|---|---|---|
| **Instant** (recommended) | Vercel — free serverless webhook, deploys straight from this repo | instant (webhook, no polling) | free Vercel account, no card |
| **Fallback** | GitHub Actions cron poller | ~5–10 min | nothing but this repo |
| **Local** | your own machine / Docker | seconds (while it's on) | Python or Docker |

The bot downloads links with [`yt-dlp`](https://github.com/yt-dlp/yt-dlp) +
ffmpeg and sends back a tagged 192 kbps MP3 with cover art. `docs/` is
published with GitHub Pages as a landing page.

> GitHub Pages itself can only host static files — it cannot run a bot.
> That's why the bot logic runs in a container / GitHub Actions and Pages
> just hosts the info page.

## Step 0 (all modes): create your bot

Talk to [@BotFather](https://t.me/BotFather) in Telegram, send `/newbot`,
and copy the token it gives you (looks like `123456789:AAF...`).

## Instant mode — Vercel (free, webhook = truly instant)

Instead of polling, Telegram pushes each message to a serverless function
the moment it arrives — no always-on server, no keep-alive pings, and
Vercel's Hobby plan is free with no credit card:

1. **Sign up** at [vercel.com](https://vercel.com) (log in with GitHub).

2. **Import this repo** — **Add New → Project**, pick this repository.
   Before hitting Deploy, expand **Environment Variables** and add
   `TELEGRAM_BOT_TOKEN` = your BotFather token. Deploy.

3. **Register the webhook** — open
   `https://<your-app>.vercel.app/api/setup` in your browser once.
   You should see "✅ Webhook registered".

4. **Done** — message your bot a YouTube Music link; it replies instantly.
   Vercel redeploys automatically whenever the repo changes.

Notes for this mode:
- Audio arrives as **`.m4a` (AAC)** — YouTube's native format, identical
  source quality to the MP3 the other modes produce (serverless has no
  ffmpeg to transcode with). Telegram plays it natively.
- To switch back to polling later, visit `/api/setup?remove=1`.

> ⚠️ Run **one** consumer at a time: while the webhook is registered,
> Telegram rejects polling — so don't add the `TELEGRAM_BOT_TOKEN` secret
> to GitHub Actions at the same time (the cron poller would just fail
> with 409 errors).

<details>
<summary><b>Other hosts (container-based, produce tagged MP3s)</b></summary>

The repo also ships a `Dockerfile` (long-polling + ffmpeg), so any
container host works and yields tagged 192 kbps MP3s with cover art:

- **Railway** ([railway.com](https://railway.com)): New Project → Deploy
  from GitHub repo → add the `TELEGRAM_BOT_TOKEN` variable. Slickest
  experience, but the free trial credit is one-time (~$5), then it's paid.
- **Hugging Face Spaces**: create a Docker Space and upload `bot.py`,
  `requirements.txt`, `Dockerfile`; add `TELEGRAM_BOT_TOKEN` as a Space
  secret. The `Deploy to Hugging Face Space` workflow in this repo can
  automate that (set secret `HF_TOKEN` + variable `HF_SPACE`). Pauses after
  48h idle unless pinged — set the `KEEP_ALIVE_URL` repo variable and the
  5-minute cron pings it.
- **Render**: free web service, no card; sleeps after 15 min idle — same
  `KEEP_ALIVE_URL` trick applies.
- **Fly.io / Google Cloud Run / any VPS**: `docker run` the image with
  `TELEGRAM_BOT_TOKEN` set (both require a credit card).
</details>

## Fallback mode — GitHub Actions only (no extra accounts)

Skip Hugging Face entirely and let the 5-minute cron poller answer
(~5–10 min per reply):

1. In this repo: **Settings → Secrets and variables → Actions → New
   repository secret** → name `TELEGRAM_BOT_TOKEN`, value = your BotFather
   token.
2. Go to the **Actions** tab and enable workflows if GitHub asks. The
   `Telegram bot` workflow then runs every 5 minutes; trigger it manually
   with **Run workflow** for an instant test.

## GitHub Pages landing page (optional)

In **Settings → Pages**, set **Source** to **GitHub Actions**. The
`Deploy GitHub Pages` workflow publishes `docs/` whenever it changes on the
default branch (or run it manually once).

## Notes & limits

- **Latency:** instant mode replies in seconds. Fallback (Actions-only) mode
  takes up to ~5–10 minutes because GitHub cron schedules are best-effort;
  for a quick test, trigger the workflow manually from the Actions tab.
- **File size:** Telegram bots can upload at most 50 MB per file.
- **Playlists** are not expanded — only the single linked track is downloaded.
- **Region-locked YouTube Music IDs:** some music.youtube.com track IDs only
  play in certain countries (auto-generated "art tracks" get different IDs
  per distributor/region). The bot handles this automatically: it retries
  with the YouTube Music player client, then falls back to finding the same
  track by title and downloading the closest match.
- **YouTube bot checks:** datacenter IPs (Vercel, GitHub, etc.) occasionally
  get blocked by YouTube ("Sign in to confirm you're not a bot"). If
  downloads start failing with that error, export your browser cookies for
  youtube.com in Netscape `cookies.txt` format and add the contents as an
  environment variable / secret named `YTDLP_COOKIES` — the bot picks it up
  automatically.
- **Legal:** download only content you have the rights to. This tool is for
  personal use.

## Repo layout

```
bot.py                           # core logic: Telegram → yt-dlp → audio reply
app.py                           # Vercel entrypoint: /api/webhook + /api/setup
pyproject.toml                   # deps + [tool.vercel] entrypoint
Dockerfile                       # container hosts (long-polling + ffmpeg/MP3)
.github/workflows/bot.yml        # cron: poll Telegram, or keep-alive ping
.github/workflows/deploy-hf.yml  # optional auto-deploy to a HF Space
.github/workflows/pages.yml      # GitHub Pages deploy of docs/
docs/index.html                  # landing page
requirements.txt                 # yt-dlp, requests, mutagen
```

## Run it on your own machine (zero accounts)

Instant replies while your computer is on — nothing to sign up for:

```bash
pip install -r requirements.txt   # plus ffmpeg: apt/brew install ffmpeg
TELEGRAM_BOT_TOKEN=123:ABC... python bot.py --loop
```

or with Docker:

```bash
docker build -t ytmd . && docker run -e TELEGRAM_BOT_TOKEN=123:ABC... ytmd
```

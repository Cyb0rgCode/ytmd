# ytmd — Telegram YouTube Music Downloader

A Telegram bot that converts YouTube Music (and regular YouTube) links into
MP3s — free, no server to rent.

Three ways to run the same code — pick one:

| Mode | Where it runs | Reply speed | Needs |
|---|---|---|---|
| **Instant** (recommended) | Koyeb — free Docker container, long-polling 24/7, deploys straight from this repo | seconds | free Koyeb account |
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

## Instant mode (replies in seconds) — Koyeb

Run the bot 24/7 in a free Koyeb container. Koyeb builds straight from this
GitHub repo — nothing to upload:

1. **Sign up** at [koyeb.com](https://www.koyeb.com) (log in with GitHub).

2. **Create the service** — click **Create Web Service → GitHub**, pick this
   repository (and your default branch). Koyeb auto-detects the `Dockerfile`.

3. **Configure** (all on the same creation page):
   - Instance type: **Free**
   - **Environment variables**: add `TELEGRAM_BOT_TOKEN` = your BotFather
     token (mark it as a secret)
   - **Exposed port**: set it to `7860` (the health endpoint)

4. **Deploy** — after the build finishes, message your bot: it answers in
   seconds. Koyeb redeploys automatically whenever the repo's default
   branch changes.

5. **Keep it awake** (recommended) — Koyeb's free instances scale down when
   idle, which adds a cold-start delay to the first reply. Copy the service's
   public URL (`https://....koyeb.app`) and in this GitHub repo add a
   repository **variable** (Settings → Secrets and variables → Actions →
   Variables):
   - `KEEP_ALIVE_URL` = that URL

   The 5-minute GitHub workflow then pings it so it never sleeps.
   Alternatively, any free uptime monitor (e.g. UptimeRobot) works too.

> ⚠️ Run **one** consumer at a time: if you use instant mode, either set
> `KEEP_ALIVE_URL` (which switches the GitHub cron from polling to pinging
> automatically) or don't add the `TELEGRAM_BOT_TOKEN` secret to GitHub at
> all. Two pollers on the same token steal each other's messages.

<details>
<summary><b>Other hosts that run the same Dockerfile</b></summary>

Nothing in this repo is Koyeb-specific — any container host works:

- **Railway** ([railway.com](https://railway.com)): New Project → Deploy
  from GitHub repo → add the `TELEGRAM_BOT_TOKEN` variable. Slickest
  experience, but the free trial credit is one-time (~$5), then it's paid.
- **Hugging Face Spaces**: create a Docker Space and upload `bot.py`,
  `requirements.txt`, `Dockerfile`; add `TELEGRAM_BOT_TOKEN` as a Space
  secret. The `Deploy to Hugging Face Space` workflow in this repo can
  automate that (set secret `HF_TOKEN` + variable `HF_SPACE`).
- **Fly.io / Google Cloud Run / any VPS**: `docker run` the image with
  `TELEGRAM_BOT_TOKEN` set.
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
- **YouTube bot checks:** GitHub's datacenter IPs occasionally get blocked by
  YouTube ("Sign in to confirm you're not a bot"). If downloads start failing
  with that error, export your browser cookies for youtube.com in Netscape
  `cookies.txt` format and add the file's contents as a repo secret named
  `YTDLP_COOKIES` — the bot picks it up automatically.
- **Legal:** download only content you have the rights to. This tool is for
  personal use.

## Repo layout

```
bot.py                           # Telegram → yt-dlp → MP3 (one-shot + --loop modes)
Dockerfile                       # container for instant mode (Koyeb / any host)
.github/workflows/bot.yml        # cron: poll Telegram, or keep-alive ping
.github/workflows/deploy-hf.yml  # optional auto-deploy to the HF Space
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

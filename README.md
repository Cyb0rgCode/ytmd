# ytmd — Telegram YouTube Music Downloader

A Telegram bot that converts YouTube Music (and regular YouTube) links into
MP3s — free, no server to rent.

Two run modes, same code:

| Mode | Where it runs | Reply speed | Setup |
|---|---|---|---|
| **Instant** (recommended) | Hugging Face Space (free Docker container, long-polling 24/7) | seconds | steps 1–2 + "Instant mode" below |
| **Fallback** | GitHub Actions cron poller | ~5–10 min | steps 1–3 only |

The bot downloads links with [`yt-dlp`](https://github.com/yt-dlp/yt-dlp) +
ffmpeg and sends back a tagged 192 kbps MP3 with cover art. `docs/` is
published with GitHub Pages as a landing page.

> GitHub Pages itself can only host static files — it cannot run a bot.
> That's why the bot logic runs in a container / GitHub Actions and Pages
> just hosts the info page.

## Setup (one time)

1. **Create the bot** — talk to [@BotFather](https://t.me/BotFather) in
   Telegram, send `/newbot`, and copy the token it gives you
   (looks like `123456789:AAF...`).

2. **Add the token as a secret** — in this repo go to
   **Settings → Secrets and variables → Actions → New repository secret** and
   create:
   - Name: `TELEGRAM_BOT_TOKEN`
   - Value: the token from BotFather

3. **Enable the workflows** — go to the **Actions** tab and enable workflows
   if GitHub asks. The `Telegram bot` workflow then runs automatically every
   5 minutes. You can also trigger it manually with **Run workflow** to test.

4. **Enable GitHub Pages** — in **Settings → Pages**, set **Source** to
   **GitHub Actions**. The `Deploy GitHub Pages` workflow publishes `docs/`
   whenever it changes on the default branch (or run it manually once).

5. **Use it** — open your bot in Telegram, press **Start**, and paste a link
   like `https://music.youtube.com/watch?v=dQw4w9WgXcQ`.

## Instant mode (replies in seconds) — Hugging Face Space

The GitHub cron poller above works with zero extra accounts, but replies take
~5–10 minutes. For instant replies, run the same bot 24/7 in a free
Hugging Face Docker Space:

1. **Create a Hugging Face account** at [huggingface.co](https://huggingface.co)
   (free, no credit card).

2. **Create the Space** — [New Space](https://huggingface.co/new-space):
   - Space name: `ytmd-bot` (anything works)
   - SDK: **Docker** → **Blank**
   - Hardware: **CPU basic (free)**
   - Visibility: **Private** (recommended)

3. **Add the bot token to the Space** — in the Space's
   **Settings → Variables and secrets**, add a **secret** named
   `TELEGRAM_BOT_TOKEN` with your BotFather token.

4. **Connect auto-deploy from this repo:**
   - On Hugging Face, create an access token with **Write** permission
     ([Settings → Access Tokens](https://huggingface.co/settings/tokens)).
   - In this GitHub repo: **Settings → Secrets and variables → Actions**
     - New **secret**: `HF_TOKEN` = the Hugging Face token
     - New **variable**: `HF_SPACE` = `your-hf-username/ytmd-bot`
   - Run the **Deploy to Hugging Face Space** workflow from the Actions tab
     (it also re-deploys automatically whenever the bot code changes).

5. **Keep it awake + avoid double replies** — free Spaces pause after 48h
   without traffic, so add one more repository **variable**:
   - `KEEP_ALIVE_URL` = the Space's direct URL, shown in the Space's
     **Embed this Space** dialog (looks like
     `https://your-hf-username-ytmd-bot.hf.space`).

   Setting this variable also automatically switches the 5-minute GitHub
   workflow from "poll Telegram" to "ping the Space", so the two runtimes
   never compete for the same messages.

That's it — the bot now answers within seconds.

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
bot/bot.py                       # Telegram → yt-dlp → MP3 (one-shot + --loop modes)
Dockerfile                       # container for instant mode (HF Space)
.github/workflows/bot.yml        # cron: poll Telegram, or keep-alive ping
.github/workflows/deploy-hf.yml  # auto-deploy bot to the HF Space
.github/workflows/pages.yml      # GitHub Pages deploy of docs/
docs/index.html                  # landing page
requirements.txt                 # yt-dlp, requests, mutagen
```

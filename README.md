# ytmd — Telegram YouTube Music Downloader

A Telegram bot that converts YouTube Music (and regular YouTube) links into
MP3s, running **entirely on GitHub** — no server needed.

- **Bot runtime:** a GitHub Actions workflow wakes up every ~5 minutes, polls
  Telegram for new messages, downloads any YouTube links with
  [`yt-dlp`](https://github.com/yt-dlp/yt-dlp) + ffmpeg, and sends the audio
  back to the chat as a tagged 192 kbps MP3 with cover art.
- **Landing page:** `docs/` is published with GitHub Pages.

> GitHub Pages itself can only host static files — it cannot run a bot.
> That's why the bot logic runs in GitHub Actions and Pages just hosts the
> info page.

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

## Notes & limits

- **Latency:** replies take up to ~5–10 minutes because GitHub cron schedules
  are best-effort. For an instant test, trigger the workflow manually from
  the Actions tab.
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
bot/bot.py                  # poll Telegram → yt-dlp → send MP3
.github/workflows/bot.yml   # cron runner (every 5 min + manual)
.github/workflows/pages.yml # GitHub Pages deploy of docs/
docs/index.html             # landing page
requirements.txt            # yt-dlp, requests, mutagen
```

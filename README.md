# ytmd — Telegram YouTube Music Downloader

A Telegram bot that converts YouTube Music (and regular YouTube) links into
MP3s — free, no server to rent.

Three ways to run the same code — pick one:

| Mode | Where it runs | Reply speed | Needs |
|---|---|---|---|
| **Instant** (recommended) | Hugging Face Space — free Docker container, long-polling 24/7 | seconds | free HF account, 3-file upload |
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

## Instant mode (replies in seconds) — Hugging Face Space

Run the same bot 24/7 in a free Hugging Face Docker Space (no credit card).
The whole thing is a drag-and-drop of 3 files:

1. **Create a free account** at [huggingface.co](https://huggingface.co),
   then create a Space at [huggingface.co/new-space](https://huggingface.co/new-space):
   - Space name: `ytmd-bot` (anything works)
   - SDK: **Docker** → **Blank**
   - Hardware: **CPU basic (free)**
   - Visibility: **Private** (recommended)

2. **Upload the bot** — on the Space page open **Files → + Add file →
   Upload files**, and drag in these 3 files from this repo:
   `bot.py`, `requirements.txt`, `Dockerfile`. Commit.

3. **Add your token** — in the Space's **Settings → Variables and secrets**,
   add a **secret** named `TELEGRAM_BOT_TOKEN` with your BotFather token.
   The Space rebuilds and the bot is live — message it and it answers in
   seconds.

4. **Keep it awake** (recommended) — free Spaces pause after 48 hours
   without web traffic. In this GitHub repo add a repository **variable**
   (Settings → Secrets and variables → Actions → Variables):
   - `KEEP_ALIVE_URL` = the Space's direct URL, shown in the Space's
     **Embed this Space** dialog (looks like
     `https://your-hf-username-ytmd-bot.hf.space`).

   The 5-minute GitHub workflow then pings it forever. Alternatively, any
   free uptime monitor (e.g. UptimeRobot) pointed at that URL works too.

> ⚠️ Run **one** consumer at a time: if you use instant mode, either set
> `KEEP_ALIVE_URL` (which switches the GitHub cron from polling to pinging
> automatically) or don't add the `TELEGRAM_BOT_TOKEN` secret to GitHub at
> all. Two pollers on the same token steal each other's messages.

<details>
<summary><b>Optional: auto-deploy from GitHub instead of uploading manually</b></summary>

If you'd rather have GitHub push the bot to the Space on every code change:
create a Hugging Face access token with **Write** permission
([Settings → Access Tokens](https://huggingface.co/settings/tokens)), then in
this repo add secret `HF_TOKEN` = that token and variable `HF_SPACE` =
`your-hf-username/ytmd-bot`, and run the **Deploy to Hugging Face Space**
workflow once from the Actions tab.
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
Dockerfile                       # container for instant mode (HF Space)
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

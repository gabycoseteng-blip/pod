# The Morning Commute — companion app

A no-build, installable **PWA** for the daily two-host news podcast:

- **Listen** — audio player (defaults to 1.5×, your speed) with a read-along transcript. Speaker-colored turns, tappable segment chips that jump the script (and approximately seek the audio), lock-screen controls, and a saved resume point.
- **Vocab** — a reference + learning surface for the daily Mandarin + Tagalog words across the whole archive. **Cards** mode gives flippable flashcards with a lightweight Leitner **spaced-repetition** schedule (flip for meaning / example / nuance, tap 🔊 to hear it); **List** mode is a scannable, tap-to-expand reference for revisiting old lessons. A **search** box filters everything (words, pinyin, meanings, notes), and a built-in **tutor chatbot** answers follow-up questions about any word (see *Vocab chat* below).
- **Search** — full-text search across every episode's transcript + vocab, with highlighted snippets; tap a result to open it. Runs client-side off a prebuilt `data/search.json`.
- **Archive** — every past episode, newest first; tap to open.

Tap **⤓ Save audio for offline** on an episode to download its MP3 into the cache for a no-signal commute.

Everything is static files + JSON; audio is served from object storage (Cloudflare R2). Works offline once an episode is opened (service worker caches the shell and data; audio caching is best-effort, see notes). Add to Home Screen for a full-screen app icon.

## Run locally
```bash
python3 -m http.server 8000     # then open http://localhost:8000
```

## Deploy (pick one)
- **GitHub Pages:** push this repo, then Settings → Pages → deploy from `main` / root. `.nojekyll` is already included. Open the Pages URL on your phone → Share → Add to Home Screen.
- **Vercel:** import the repo (framework preset: *Other*; output dir: root). `vercel.json` is included.

### Vocab chat
The Vocab tab has a built-in tutor chatbot for follow-up questions ("how is 一旦 different from 如果?", "give me another sentence with *banta*"). It's served by a tiny Vercel serverless function at [`api/chat.js`](api/chat.js) that proxies the Anthropic Messages API, so no key ever reaches the browser. To enable it, set project env vars in Vercel:

```
ANTHROPIC_API_KEY=sk-ant-…        # required
CHAT_MODEL=claude-sonnet-5        # optional, this is the default
```

The client posts the current card + the whole (small) deck as context. Without the key — or on static hosts like GitHub Pages that don't run the function — the chat degrades gracefully with a "not set up" message; every other feature keeps working.

## The daily routine
Each morning a scheduled **Claude routine** (Claude Code on the web → [Routines](https://claude.ai/code/routines)) runs the `/morning-commute` command (`.claude/commands/morning-commute.md`): it researches the day, writes the two-host script + `vocab.json`, renders audio with `routine/render_gemini.py` (Gemini multi-speaker TTS), and publishes with `tools/daily.sh`. The generation toolchain and editorial rules live in [`routine/`](routine/README.md); set a **Daily, 6:00 AM** schedule trigger on the routine and give its environment the R2 vars + `GEMINI_API_KEY`, with *Allow unrestricted branch pushes* so it can deploy to `main`.

## How an episode gets published
After the routine writes the day's script (named `…-YYYY-MM-DD.md`), renders audio, and emits `vocab.json`, one command publishes it:

```bash
tools/daily.sh  <script.md>  audio.mp3  vocab.json
```

That uploads audio to R2, builds the episode, archives the script under `scripts/`, rebuilds the index + search, then commits and pushes so the deploy picks it up. Set `NO_PUSH=1` to build + commit without pushing. The audio/R2 env vars below must be exported (without them it runs in dev mode and keeps the MP3 in git).

Under the hood it runs two tools you can also call directly:

```bash
python3 tools/upload_audio.py  audio.mp3  2026-06-23          # audio → R2
AUDIO_BASE_URL="$AUDIO_BASE_URL" \
  python3 tools/build_episode.py  <script.md>  audio.mp3  vocab.json
```

`build_episode.py` parses the `## SEGMENT` headers and `ALEX:` / `SAM:` turns into `data/episodes/<date>/episode.json`, estimates per-segment start times, copies `vocab.json`, and rebuilds `data/index.json` + `data/search.json`. The date comes from the script filename. The MP3 it's handed is used only to measure duration — with `AUDIO_BASE_URL` set, the file is **not** copied into git; `episode.json` stores `"<AUDIO_BASE_URL>/<date>.mp3"`. Without `AUDIO_BASE_URL`, the MP3 is copied into the repo (dev/legacy mode).

It also picks up an optional per-episode **digest** (`routine/digest-<date>.json` → copied to `data/episodes/<date>/digest.json`) and rebuilds **`data/history.jsonl`** — a compact, one-line-per-episode ledger of each show's `throughline`, `stories`, `explainers`, and `vocab`. The daily routine reads the tail of this file to avoid repeating stories, re-explaining concepts, or reusing vocab — **without** loading old scripts into context, which keeps token usage flat as the archive grows for years. It's rebuilt from the per-episode digests every run, so it's idempotent and self-healing.

## Audio storage (Cloudflare R2)
Audio is large and write-once, so it lives in an object store, not git — at one episode/day a committed MP3 archive would balloon past what git can hold within a year, while the *text* stays a few MB/year and fully greppable forever.

One-time setup:
1. Create an R2 bucket (e.g. `morning-commute-audio`).
2. Serve it publicly — either enable the bucket's **r2.dev** dev URL, or (recommended) connect a **custom domain** (e.g. `audio.yourdomain.com`). That public base is your `AUDIO_BASE_URL`.
3. Create an R2 **API token** (Object Read & Write) and note the account id, access key id, and secret.
4. Add **CORS** on the bucket so the PWA can fetch/cache audio cross-origin — allow your app origin(s) for `GET`/`HEAD`, e.g.
   ```json
   [{ "AllowedOrigins": ["https://your-app.vercel.app", "http://localhost:8000"],
      "AllowedMethods": ["GET", "HEAD"], "AllowedHeaders": ["Range"],
      "ExposeHeaders": ["Content-Length", "Content-Range", "Accept-Ranges"] }]
   ```
5. Provide these to the routine's environment (locally `export`, or as CI/GitHub secrets):
   ```
   AUDIO_BASE_URL=https://audio.yourdomain.com
   R2_ACCOUNT_ID=…  R2_ACCESS_KEY_ID=…  R2_SECRET_ACCESS_KEY=…  R2_BUCKET=morning-commute-audio
   ```
   The uploader needs `boto3`: `pip install -r tools/requirements.txt`.

Cost stays trivial — R2 storage is ~$0.015/GB·mo with **no egress fees**, so years of audio run well under $1/month.

### vocab.json schema (one file per episode)
```json
{ "date": "2026-06-23", "cards": [
  { "id": "2026-06-23-zh-1", "lang": "Mandarin", "word": "谈判",
    "pinyin": "tán pàn", "pronunciation": "tahn pahn", "tones": "2 (rising) · 4 (falling)",
    "meaning": "negotiation; to negotiate",
    "example": "两国正在进行谈判。", "examplePinyin": "liǎng guó …", "exampleMeaning": "The two countries are negotiating.",
    "note": "register / nuance / drill tip", "tiesTo": "Iran de-escalation talks" }
] }
```
`lang` is `Mandarin` or `Tagalog`. For Tagalog leave `pinyin`/`tones` empty and use `pronunciation`. To make this fully automatic, have the script step emit `vocab.json` directly from the VOCAB segment.

## Notes / tradeoffs
- **Audio lives in R2, not git.** New episodes store only the URL (set `AUDIO_BASE_URL`). The seed episode (`2026-06-23`) still has its MP3 committed; to migrate it, run `tools/upload_audio.py data/episodes/2026-06-23/audio.mp3 2026-06-23`, then re-run `build_episode.py` (with `AUDIO_BASE_URL` set) and `git rm` the committed MP3.
- **Offline audio:** the shell, transcript, vocab, and search always work offline. Audio is cross-origin (R2), and range requests (206) can't be cached automatically — so use **⤓ Save audio for offline** to download an episode for a no-signal commute.
- **Search scales as one file.** `data/search.json` is the whole archive's text loaded client-side — fine for the first several years (a few MB). Past a few thousand episodes, swap the client filter for a prebuilt index (e.g. MiniSearch) or a small serverless search endpoint; the per-episode JSON stays the source of truth either way.
- **Segment seek is approximate** — estimated from spoken-character share, since Gemini-TTS doesn't return word timings. Text jumps are exact; audio position is a best guess.
- Vocab SRS progress and playback position live in `localStorage` on the device (not synced).

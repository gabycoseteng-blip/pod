# The Morning Commute — companion app

A no-build, installable **PWA** for the daily two-host news podcast:

- **Listen** — audio player (defaults to 1.5×, your speed) with a read-along transcript. Speaker-colored turns, tappable segment chips that jump the script (and approximately seek the audio), lock-screen controls, and a saved resume point.
- **Vocab** — flashcards for the daily Mandarin + Tagalog words, with a lightweight Leitner **spaced-repetition** schedule across the whole archive. Flip for meaning / example / nuance, tap 🔊 to hear it.
- **Archive** — every past episode, newest first; tap to open.

Everything is static files + JSON; audio is served from object storage (Cloudflare R2). Works offline once an episode is opened (service worker caches the shell and data; audio caching is best-effort, see notes). Add to Home Screen for a full-screen app icon.

## Run locally
```bash
python3 -m http.server 8000     # then open http://localhost:8000
```

## Deploy (pick one)
- **GitHub Pages:** push this repo, then Settings → Pages → deploy from `main` / root. `.nojekyll` is already included. Open the Pages URL on your phone → Share → Add to Home Screen.
- **Vercel:** import the repo (framework preset: *Other*; output dir: root). `vercel.json` is included.

## How the daily routine adds an episode
After the routine writes the day's script and renders audio (and emits `vocab.json`):

```bash
# 1. audio → R2 bucket (keeps the MP3 out of git; see "Audio storage" below)
python3 tools/upload_audio.py  audio.mp3  2026-06-23

# 2. build the episode (records the R2 URL, not a copy) + rebuild the index
AUDIO_BASE_URL="$AUDIO_BASE_URL" \
  python3 tools/build_episode.py  <script.md>  audio.mp3  vocab.json

# 3. commit + push the text → Vercel/Pages auto-deploys
git add data scripts && git commit -m "Episode 2026-06-23" && git push
```

`build_episode.py` parses the `## SEGMENT` headers and `ALEX:` / `SAM:` turns into `data/episodes/<date>/episode.json`, estimates per-segment start times, copies `vocab.json`, and rebuilds `data/index.json`. The date comes from the script filename (`…-YYYY-MM-DD.md`). The MP3 it's handed is used only to measure duration — with `AUDIO_BASE_URL` set, the file is **not** copied into git; `episode.json` stores `"<AUDIO_BASE_URL>/<date>.mp3"`. Without `AUDIO_BASE_URL`, the MP3 is copied into the repo (dev/legacy mode).

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
- **Offline audio is best-effort.** Cross-origin range requests (206) can't be cached by the service worker, so a fully offline commute isn't guaranteed yet; the shell, transcript, and vocab always work offline. A deliberate "save for offline" (full-file fetch) is a sensible follow-up.
- **Segment seek is approximate** — estimated from spoken-character share, since Gemini-TTS doesn't return word timings. Text jumps are exact; audio position is a best guess.
- Vocab SRS progress and playback position live in `localStorage` on the device (not synced).

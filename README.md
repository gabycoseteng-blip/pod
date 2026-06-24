# The Morning Commute — companion app

A no-build, installable **PWA** for the daily two-host news podcast:

- **Listen** — audio player (defaults to 1.5×, your speed) with a read-along transcript. Speaker-colored turns, tappable segment chips that jump the script (and approximately seek the audio), lock-screen controls, and a saved resume point.
- **Vocab** — flashcards for the daily Mandarin + Tagalog words, with a lightweight Leitner **spaced-repetition** schedule across the whole archive. Flip for meaning / example / nuance, tap 🔊 to hear it.
- **Archive** — every past episode, newest first; tap to open.

Everything is static files + JSON. Works offline once an episode is opened (service worker caches the shell, data, and audio). Add to Home Screen for a full-screen app icon.

## Run locally
```bash
python3 -m http.server 8000     # then open http://localhost:8000
```

## Deploy (pick one)
- **GitHub Pages:** push this repo, then Settings → Pages → deploy from `main` / root. `.nojekyll` is already included. Open the Pages URL on your phone → Share → Add to Home Screen.
- **Vercel:** import the repo (framework preset: *Other*; output dir: root). `vercel.json` is included.

## How the daily routine adds an episode
After the routine writes the day's script (and renders audio), run:
```bash
python3 tools/build_episode.py  <script.md>  [audio.mp3]  [vocab.json]
```
It parses the `## SEGMENT` headers and `ALEX:` / `SAM:` turns into `data/episodes/<date>/episode.json`, estimates per-segment start times, copies the audio + vocab, and rebuilds `data/index.json`. The date comes from the script filename (`…-YYYY-MM-DD.md`). Then commit + push (or let CI deploy).

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
- **Audio in git:** the seed episode's MP3 (~26 MB) is committed for simplicity. At one episode/day this grows fast — for the long run, move audio to Git LFS or an external bucket/CDN and point `episode.json`'s `audio` at the URL.
- **Segment seek is approximate** — estimated from spoken-character share, since Gemini-TTS doesn't return word timings. Text jumps are exact; audio position is a best guess.
- Vocab SRS progress and playback position live in `localStorage` on the device (not synced).

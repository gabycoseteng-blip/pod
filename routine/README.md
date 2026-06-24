# routine/ — daily podcast generation toolchain

The pipeline that produces each episode the app consumes. Kept here so the repo
holds both the app **and** what feeds it.

## Files
- `notebooklm-steering-prompt.md` — reusable steering prompt (segment order, time
  budgets, audience/register rules). Source of truth for how a day's script is written.
- `render_gemini.py` — renders a two-host script to audio via Gemini-TTS multi-speaker.
  Voices Sulafat (Alex/expert) + Charon (Sam/generalist), British accent, financial-anchor
  style, model `gemini-2.5-flash-preview-tts`. Chunks + paces for the free tier; saves
  partial audio on failure. Needs `GEMINI_API_KEY` in the env.
- `test_voice.py` — audition voices (single or `--pair A B`) before committing to a render.
- `commute-brief-YYYY-MM-DD.md` — the day's research brief (source of record).
- `commute-two-host-script-YYYY-MM-DD.md` — the spoken two-host script (`ALEX:`/`SAM:` turns).
- `vocab-YYYY-MM-DD.json` — structured flashcards for the day (schema in the top-level README).

## Daily flow
A scheduled Claude routine runs `/morning-commute` (see
`.claude/commands/morning-commute.md`), which does steps 1–4 and then calls
`tools/daily.sh` to publish. To run it by hand:

```bash
date=2026-06-25
# 1. research + write brief -> routine/commute-brief-<date>.md
# 2. write two-host script   -> routine/commute-two-host-script-<date>.md
# 3. author vocab            -> routine/vocab-<date>.json   (emit it in step 2)

# 4. render audio (needs GEMINI_API_KEY; writes commute-gemini-<date>.mp3)
GEMINI_API_KEY=...  python3 routine/render_gemini.py \
    routine/commute-two-host-script-$date.md  commute-gemini-$date

# 5. publish: upload audio -> R2, build episode+index+search, archive, commit, push
#    (needs the R2 env vars — see the top-level README "Audio storage")
tools/daily.sh \
    routine/commute-two-host-script-$date.md  commute-gemini-$date.mp3  routine/vocab-$date.json
```

`daily.sh` keeps audio out of git (it goes to R2; only the URL is stored). The
rendered `commute-gemini-*.mp3` / `*.wav` at the repo root are gitignored.

Seed example included: **2026-06-23** (brief, script, vocab). Its MP3 is still in
`data/episodes/2026-06-23/audio.mp3` pending the R2 migration (see top-level README).

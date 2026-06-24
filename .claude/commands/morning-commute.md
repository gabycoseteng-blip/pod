---
description: Produce and publish today's episode of The Morning Commute (research → script → vocab → audio → deploy)
---

# The Morning Commute — daily routine

You are the producer and both hosts of **The Morning Commute**, a daily two-host
markets-and-world news podcast played at 1.5×. Run the whole pipeline for
**today's** episode end to end without stopping to ask — only stop if a required
credential is missing (and then say exactly which).

The toolchain already lives in the repo:
- `routine/notebooklm-steering-prompt.md` — **the editorial source of truth**:
  segment order, time budgets, audience/register rules. Follow it exactly.
- `routine/render_gemini.py` — renders the script to audio (Gemini multi-speaker TTS).
- `tools/daily.sh` — uploads audio → R2, builds the episode + index + search,
  archives the script, commits, and pushes to deploy.
- Look at `routine/commute-two-host-script-2026-06-23.md` and
  `routine/vocab-2026-06-23.json` as worked examples of the exact format.

Hosts: **ALEX** = Host A, the domain expert (voice Sulafat). **SAM** = Host B, the
sharp generalist (voice Charon). Stay on the `main` branch so the publish deploys.

## 0. Setup
```bash
date="$(date +%F)"          # YYYY-MM-DD — used in every filename
git checkout main 2>/dev/null || true
```
The publish step needs the R2 env vars and the renderer needs `GEMINI_API_KEY`
(see README → "Audio storage" and `routine/README.md`). If `GEMINI_API_KEY` is
missing, do steps 1–3, then stop and report — do not fabricate audio.

## 1. Research → `routine/commute-brief-$date.md`
Using web search + the connected market/news connectors (FMP for quotes / indices
/ calendar, news search), write the day's brief — the source of record. Cover
exactly what the steering prompt's segments require, with **real, accurate**
numbers (most-recent US close for S&P/Nasdaq/Dow, notable movers, rates/Fed angle,
2 world + 2 US-business + 2 international + 1 China item, the energy/AI-power
theme, Philippines weather + BSP + peso, art/pop, the trending meme, one good
thing). Include `[bracketed pronunciation hints]` for any foreign words. Pick one
throughline that connects the macro blocks.

**Accuracy:** pull the actual prior-session closes/levels and movers from the FMP
connector — never approximate index levels, prices, or yields from memory. If
markets were closed (weekend or holiday), use the **last trading session** and say
so in the script; do not invent a close for a day with no trading.

## 2. Write the script → `routine/commute-two-host-script-$date.md`
Turn the brief into the spoken two-host script, following
`routine/notebooklm-steering-prompt.md` for segment order, budgets, and rules, and
matching the format of the 2026-06-23 example. Requirements `tools/build_episode.py`
relies on:
- A `### <Weekday>, <Month> <D>, <YYYY>` title line, and a `## …` header per
  segment (only these are parsed; header-only segments with no turns are dropped).
- **One line per turn:** every `ALEX:` / `SAM:` turn is a single line of plain
  text — no markdown, no line breaks inside a turn (the parser and TTS both
  require it). Only `ALEX:` / `SAM:` lines are spoken.
- **Spell numbers as said aloud** ("seventy-four seventy-three", "thirty-seven
  basis points", "twenty twenty-seven").
- **Length target (this controls the duration):** write **~18,000–20,000
  characters** of `ALEX:`/`SAM:` dialogue (≈ 3,000–3,400 words ≈ 35–40 min of
  audio at ~8 chars per audio-second). The 2026-06-23 example is ~18.2k chars /
  37 min — match that scale. Before rendering, count the dialogue characters:
  ```bash
  grep -hoE '^(ALEX|SAM):.*' routine/commute-two-host-script-$date.md | wc -c
  ```
  If under ~16,000, expand the substantive segments (Headlines, Energy,
  Philippines, Vocab) with more real content — never pad or repeat; if over
  ~21,000, trim wording. Do this **before** step 4 so you don't render a bad length.
- Hosts announce each segment; no run-of-show in the cold open; the meme segment
  **reports** the meme (no performed bit); close on One Good Thing.
- VOCAB OF THE DAY is enrichment for a **proficient** listener, not a 101: 2
  Mandarin then 2 Tagalog, each tied to a story in today's show. Say each word
  clearly with correct tones, but **do not drill or explain tone numbers** or
  spell out pronunciation — assume Mandarin fluency. Spend the time on usage,
  register, collocations, and contrast with near-synonyms (same depth for both
  languages).

## 3. Write vocab → `routine/vocab-$date.json`
Per the schema in the top-level README. `lang` is `Mandarin` or `Tagalog`;
Tagalog leaves `pinyin`/`tones` empty, and you may leave `tones` empty for
Mandarin too (the app shows pinyin, not tone drills). Ids `"$date-zh-1/2"`,
`"$date-tl-1/2"`; write `note` on usage / register / collocation / near-synonym
contrast — **no tone-drill explanations**, assume Mandarin proficiency;
`tiesTo` the story. **The four words here
must be exactly the four taught in the VOCAB OF THE DAY segment** — same words,
same order (2 Mandarin then 2 Tagalog) — so the flashcards match the audio.

## 4. Render audio → `commute-gemini-$date.mp3`
```bash
python3 routine/render_gemini.py routine/commute-two-host-script-$date.md commute-gemini-$date
```
(ALEX→Sulafat, SAM→Charon; chunked; writes a 96 kbps MP3 via ffmpeg.) If it exits
non-zero — missing `GEMINI_API_KEY`, missing ffmpeg, or a partial render — stop and
report; do not publish silent or partial audio without flagging it.

## 5. Build + commit (no push yet)
```bash
NO_PUSH=1 tools/daily.sh routine/commute-two-host-script-$date.md commute-gemini-$date.mp3 routine/vocab-$date.json
```
This uploads audio to R2, builds the episode + index + search, and commits — but
holds the push so the guardrail can gate the deploy.

## 6. Guardrail check, then deploy
Inspect `data/index.json` for `$date` — it should show **~12 segments** and
**`durationSec` ≥ 1500** (25 min), with `hasAudio: true`. If segments are missing,
the duration is too short, or the audio is wrong, the episode is malformed: fix
the script/vocab, re-run step 5, and only continue once it looks right. Also
confirm (R2 mode) that `data/episodes/$date/episode.json`'s `audio` is the R2 URL
— the repo should have grown by KBs, not tens of MB. When it all checks out:
```bash
git push
```
Then report in a few lines: the throughline, segment count, the four vocab words,
the audio duration, and that the deploy push landed.

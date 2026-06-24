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
throughline that connects the macro blocks. Never invent figures.

## 2. Write the script → `routine/commute-two-host-script-$date.md`
Turn the brief into the spoken two-host script, following
`routine/notebooklm-steering-prompt.md` for segment order, budgets, and rules, and
matching the format of the 2026-06-23 example. Requirements `tools/build_episode.py`
relies on:
- A `### <Weekday>, <Month> <D>, <YYYY>` title line, and a `## …` header per
  segment (only these are parsed; header-only segments with no turns are dropped).
- Only `ALEX:` / `SAM:` lines are spoken. **Spell numbers as said aloud**
  ("seventy-four seventy-three", "thirty-seven basis points", "twenty twenty-seven").
- ~30–40 min at 1.5×; hosts announce each segment; no run-of-show in the cold open;
  the meme segment **reports** the meme (no performed bit); close on One Good Thing.
- VOCAB OF THE DAY is spoken teaching: 2 Mandarin (slow, say twice, drill tones)
  then 2 Tagalog (native-speaker nuance), each tied to a story in today's show.

## 3. Write vocab → `routine/vocab-$date.json`
The same four words taught in the VOCAB segment, per the schema in the top-level
README. `lang` is `Mandarin` or `Tagalog`; Tagalog leaves `pinyin`/`tones` empty.
Ids `"$date-zh-1/2"`, `"$date-tl-1/2"`; `note` from a register/nuance angle;
`tiesTo` the story.

## 4. Render audio → `commute-gemini-$date.mp3`
```bash
python3 routine/render_gemini.py routine/commute-two-host-script-$date.md commute-gemini-$date
```
(ALEX→Sulafat, SAM→Charon; chunked; writes a 96 kbps MP3 via ffmpeg.) If it exits
non-zero — missing `GEMINI_API_KEY`, missing ffmpeg, or a partial render — stop and
report; do not publish silent or partial audio without flagging it.

## 5. Publish (one command: upload → build → archive → commit → deploy)
```bash
tools/daily.sh routine/commute-two-host-script-$date.md commute-gemini-$date.mp3 routine/vocab-$date.json
```

## 6. Verify and report
Confirm `data/episodes/$date/episode.json` exists, `data/index.json` +
`data/search.json` include `$date`, and (R2 mode) `episode.json`'s `audio` is the
R2 URL — the repo grew by KBs, not tens of MB. Report in a few lines: the
throughline, segment count, the four vocab words, audio duration, and that the
deploy push landed.

---
description: Produce and publish today's episode of The Morning Commute (script + vocab + audio + deploy)
---

# The Morning Commute — daily routine

You are the producer and both hosts of **The Morning Commute**, a daily two-host
markets-and-world news podcast. Run the entire pipeline for **today's** episode:
research → write the script → write the vocab → render audio → publish. Work end
to end without stopping to ask; only stop if a required credential is missing.

The two hosts:
- **ALEX** — the analyst. Drives the "why it matters / how it trades" read.
- **SAM** — the anchor. Sets up stories, asks the sharp follow-up, keeps pace.

## 0. Setup
- `date="$(date +%F)"` (YYYY-MM-DD). The script filename **must** contain it:
  `commute-$date.md`.
- Work in the repo root. The publish step (`tools/daily.sh`) expects the R2 env
  vars to be set (see README → "Audio storage"); if `AUDIO_BASE_URL` is unset it
  falls back to keeping the MP3 in git — that's fine for a dry run.

## 1. Research (use real data — never invent numbers)
Gather today's material with web search and the connected market/news tools
(FMP for quotes/indices/calendar, news search, etc.):
- **Markets:** the most recent US close — S&P 500, Nasdaq, Dow (level + % move),
  notable single-stock moves, the rates/Fed angle, the FactSet earnings-growth
  blend if it's earnings season.
- **World/business headlines:** 2–3 top stories with a markets throughline.
- **US business:** 1–2 real deals / earnings (M&A, antitrust angle).
- **International:** G10 central-bank divergence, FX, a structural story.
- **China:** growth/policy, a datapoint that captures the model shift.
- **Energy / data centers / utilities:** the AI-power-demand theme, PJM/grid,
  nuclear/gas, ratepayer politics.
- **Philippines:** weather (typhoon/PAGASA signals if any), BSP policy, the peso,
  remittances/BPO, a bit of local color.
- **Art / pop, trending meme, one good thing:** light, current, real.
Pick a single **throughline** that connects the macro blocks (e.g. an oil move
rippling through rates, FX, and EM).

## 2. Write the script → `commute-$date.md`
Match this exact structure so `tools/build_episode.py` parses it. The date comes
from the filename; the `###` line is the title; every `##` is a segment; only
`ALEX:` / `SAM:` lines are spoken turns.

```
### <Weekday>, <Month> <D>, <YYYY>

## COLD OPEN
SAM: ...
ALEX: ...

## HEADLINES
...

## MARKET OVERVIEW
## U.S. BUSINESS
## INTERNATIONAL BUSINESS & POLITICS
## CHINA
## ENERGY / DATA CENTERS / UTILITIES
## PHILIPPINES
## VOCAB OF THE DAY
## ART / POP
## TRENDING MEME
## ONE GOOD THING
```

Style guide (learned from the archive):
- Dense, fluent, analytical banter — SAM sets up, ALEX delivers the "how it
  trades." Hand off naturally; end segments with a one-line bridge to the next.
- **Spell numbers as spoken** ("seventy-four seventy-three," "thirty-seven basis
  points," "twenty twenty-seven") — the script is read aloud by TTS.
- ~35–40 minutes total (the seed runs ~2,200s). Headlines / Energy / Philippines
  / Vocab are the long segments.
- **VOCAB OF THE DAY** is a spoken teaching segment: two Mandarin, two Tagalog,
  each tied to a story in today's show. Drill pronunciation and one nuance per
  word out loud (Mandarin: tones; Tagalog: native-speaker register).
- **ONE GOOD THING** closes hopeful, ideally echoing an earlier segment.

## 3. Write `vocab.json` (so flashcards are automatic)
Two Mandarin + two Tagalog words, the same ones taught in the VOCAB segment, tied
to today's stories. Follow the schema in the README exactly. `lang` is `Mandarin`
or `Tagalog`; for Tagalog leave `pinyin`/`tones` empty and use `pronunciation`.
Ids are `"$date-zh-1"`, `"$date-zh-2"`, `"$date-tl-1"`, `"$date-tl-2"`. Write the
`note` from a native-speaker register/nuance angle and set `tiesTo` to the story.

## 4. Render audio
```bash
python3 tools/render_gemini.py commute-$date.md audio.mp3
```
(ALEX and SAM map to two distinct voices; output is 96 kbps MP3.) If the render
tool or its API key is missing, stop and report — do not fabricate audio.

## 5. Publish (one command: upload → build → archive → commit → deploy)
Make sure you're on the deploy branch (`main`) so the push goes live — do **not**
create a side branch for this. The routine has unrestricted push enabled for the
deploy; `tools/daily.sh` commits and pushes:
```bash
git checkout main 2>/dev/null || true
tools/daily.sh commute-$date.md audio.mp3 vocab.json
```

## 6. Verify and report
- Confirm `data/episodes/$date/` has `episode.json` (+ `vocab.json`), the index
  and `search.json` include `$date`, and (R2 mode) `episode.json`'s `audio` is the
  R2 URL — the repo grew by KBs, not 26 MB.
- Report: the throughline, segment count, vocab words, audio duration, and the
  deploy push. Keep it to a few lines.

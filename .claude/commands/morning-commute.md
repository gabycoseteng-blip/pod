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
git pull --rebase origin main 2>/dev/null || true   # start from the live tip, not a stale clone
pip install -q -r "$(git rev-parse --show-toplevel 2>/dev/null || echo .)/tools/requirements.txt" 2>/dev/null || true  # boto3 (R2) + imageio-ffmpeg (mp3); a repo SessionStart hook also does this — render/upload fail cold without them
tail -n 60 data/history.jsonl 2>/dev/null   # what recent shows already covered
```
The publish step needs the R2 env vars and the renderer needs `GEMINI_API_KEY`
(see README → "Audio storage" and `routine/README.md`). If `GEMINI_API_KEY` is
missing, do steps 1–3, then stop and report — do not fabricate audio.

**Read the history ledger first (don't repeat the archive).** `data/history.jsonl`
is the show's compact memory — one JSON line per past episode with its
`throughline`, `stories`, `explainers`, and `vocab`. This exists so you can dedup
**without** loading old scripts into context (which would burn tokens). Read the
tail above and, throughout the day, **do not** re-run a story or re-explain a
concept already covered, and **never** reuse a vocab word that already appears in
any `vocab` array. Advancing a running story with genuinely new developments is
fine — advance it, don't recap from zero.

## 1. Research → `routine/commute-brief-$date.md`
Using web search + the connected market/news connectors (FMP for quotes / indices
/ calendar, news search), write the day's brief — the source of record. Cover
exactly what the steering prompt's segments require, with **real, accurate**
numbers (most-recent US close for S&P/Nasdaq/Dow, notable movers, rates/Fed angle,
2 world + 2 US-business + 2 international + 1 China item, the energy/AI-power
theme, Philippines weather + BSP + peso, art/pop, the trending meme, one good
thing). Pick one throughline that connects the macro blocks. Cross-check the
history ledger from step 0 — pick **fresh** stories, not ones already covered.

**Energy / data centers / utilities — research deep.** Assume the listener knows
the AI-infrastructure capex cycle cold. Pull from the sophisticated sources, not
general press: **SemiAnalysis** (accelerator/datacenter economics, capex models),
**Utility Dive** (utility ratebase, interconnection, PPAs, grid policy), plus IEA,
BloombergNEF, FERC, and the hyperscalers' own capex guidance/filings. Capture
specific projects, MW/GW and capex figures, off-takers, interconnection-queue and
transformer/turbine bottlenecks, and the second-order read — not a 101.

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
- **Write numbers as numerals** so the script is easy to read — `74.73`,
  `37 bps`, `2027`, `$3.2 trillion`, `1.5%`. Keep the unit/word right next to the
  figure so it's unambiguous when read aloud (the TTS handles digits fine).
- **Length target (this controls the duration — get it right the FIRST time so
  you render once, not twice):** the hard gate is step 7's guardrail —
  `durationSec` must be **≥ 1500** (25 min). The current renderer
  (`render_gemini.py` + `gemini-2.5-flash-preview-tts`) speaks **~19 characters of
  dialogue per audio-second** — measured, not the old ~8 figure — so **~18–20k
  chars renders only ~16–17 min and FAILS the guardrail.** Write **~30,000–33,000
  characters** of `ALEX:`/`SAM:` dialogue (≈ 5,000–5,600 words) to land **~26–29
  min**, comfortably clearing the 25-min floor with margin. Before rendering,
  count with a Unicode-aware counter (`wc -c` counts bytes and over-counts the
  Mandarin/Tagalog vocab segment ~3x):
  ```bash
  python3 - "routine/commute-two-host-script-$date.md" <<'PY'
  import re, sys
  t = open(sys.argv[1], encoding='utf-8').read()
  d = '\n'.join(m.group(0) for m in re.finditer(r'^(ALEX|SAM):.*', t, re.M))
  print(f"{len(d)} dialogue chars  ~{round(len(d)/19)}s  (~{round(len(d)/19/60,1)} min)")
  PY
  ```
  If under ~29,000, expand the substantive segments (Headlines, Energy,
  Philippines, Vocab) with more real content — never pad or repeat; if over
  ~35,000, trim wording. Do this **before** step 5 so you don't render a bad
  length and burn a second render. (If the render voice/model is ever changed,
  re-measure chars-per-second from one short calibration render and update this
  number — the char target follows the engine's pace.)
- Hosts announce each segment; no run-of-show in the cold open; the meme segment
  **reports** the meme (no performed bit); close on One Good Thing.
- **VOCAB OF THE DAY — conduct the whole segment IN-LANGUAGE** (immersion, not a
  101): 2 Mandarin then 2 Tagalog, each tied to a story in today's show, and each
  a **new** word not in the history ledger. For the Mandarin stretch the hosts
  actually **converse in Mandarin**, using the words in real sentences; for the
  Tagalog stretch they **converse in Tagalog**. English appears **only as a
  translation/gloss** right after each foreign sentence. Write Mandarin in
  **characters (汉字)** with the English gloss in parentheses, e.g.
  `ALEX: 尽管市场震荡，机构还是加仓了。(Despite the market turbulence, institutions still added to positions.)`;
  write Tagalog with its **natural spelling** so it's pronounced correctly, gloss
  in parentheses. Don't drill or explain tone numbers or spell out pronunciation —
  say each word correctly once, then spend the time on usage, register,
  collocation, and near-synonym contrast, all delivered in-language. For
  **Mandarin**, follow the **HSK 4 calibration** in
  `routine/notebooklm-steering-prompt.md`: pick HSK-4-level items targeting the
  listener's weak spots (advanced connectives, abstract pairings, formal/informal
  register), with at least one of the two being a connective or abstract
  collocation — not a concrete noun. (Note: the in-language stretch is denser, so
  re-check the dialogue char count after writing it.)

## 3. Write vocab → `routine/vocab-$date.json`
Per the schema in the top-level README. `lang` is `Mandarin` or `Tagalog`.
For **Mandarin**: `word` in characters, `pinyin` with tone marks, populate `tones`
concisely (tone numbers, e.g. `"2 · 4"`) — the card displays them for reference;
just don't drill them in the audio. For **Tagalog**: leave `tones` empty, but fill
`pronunciation` (and `pinyin` may stay empty) with a clear **Tagalog-syllable
respelling that marks stress**, e.g. `"a-lim-PÚ-yo"` (natural Tagalog vowels and a
stressed syllable) — not an English-phonetic respelling — so the card shows the
right pronunciation. Ids `"$date-zh-1/2"`, `"$date-tl-1/2"`; write `note` on
register (书面语/formal vs. 口语/informal) / collocation / near-synonym contrast,
calibrated to HSK 4 — **no tone-drill explanations**; `tiesTo` the story.
**The four words here must be exactly the four taught in the VOCAB OF THE DAY
segment** — same words, same order (2 Mandarin then 2 Tagalog) — so the flashcards
match the audio.

## 4. Write the digest → `routine/digest-$date.json`
The day's contribution to the show's compact memory (`data/history.jsonl`), so
future episodes can dedup without re-reading scripts. Keep it terse — slugs and
short phrases, not prose. Schema:
```json
{
  "throughline": "one short line — today's connecting thread",
  "stories": ["fed-holds-rates", "iran-talks-resume", "nvidia-capex-guide", "..."],
  "explainers": ["interconnection-queue mechanics", "what a PPA off-take is"],
  "comment": "stories = every distinct item you covered (short slugs); explainers = any concept you actually explained, so you won't re-explain it"
}
```
`build_episode.py` picks this up automatically and folds it (plus the vocab words)
into `data/history.jsonl`. Vocab words are added for you — don't list them here.

## 5. Render audio → `commute-gemini-$date.mp3`
```bash
python3 routine/render_gemini.py routine/commute-two-host-script-$date.md commute-gemini-$date
```
(ALEX→Sulafat, SAM→Charon; chunked; writes a 96 kbps MP3 via ffmpeg.) If it exits
non-zero — missing `GEMINI_API_KEY`, missing ffmpeg, or a partial render — stop and
report; do not publish silent or partial audio without flagging it.

## 6. Build + commit (no push yet)
```bash
NO_PUSH=1 tools/daily.sh routine/commute-two-host-script-$date.md commute-gemini-$date.mp3 routine/vocab-$date.json
```
This uploads audio to R2, builds the episode + index + search, folds today's
digest + vocab into `data/history.jsonl`, and commits — but holds the push so the
guardrail can gate the deploy.

## 7. Guardrail check, then deploy
Inspect `data/index.json` for `$date` — it should show **~12 segments** and
**`durationSec` ≥ 1500** (25 min), with `hasAudio: true`. If segments are missing,
the duration is too short, or the audio is wrong, the episode is malformed: fix
the script/vocab, re-run step 6, and only continue once it looks right. Confirm
(R2 mode) that `data/episodes/$date/episode.json`'s `audio` is the R2 URL — the
repo should have grown by KBs, not tens of MB — and that `data/history.jsonl`
gained a line for `$date`. When it all checks out:
```bash
git push
```
Then report in a few lines: the throughline, segment count, the four vocab words,
the audio duration, and that the deploy push landed.

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
DEPLOY_BRANCH="${DEPLOY_BRANCH:-main}"

# Pull ALL branches into local refs FIRST. A fresh clone may not have the deploy
# branch yet — then `git checkout main` silently fails and leaves you on whatever
# branch you started on (a stale, diverged one), running an OUTDATED command file
# and ledger. That is exactly how 2026-07-15 reused vocab and published to the
# wrong branch. Fetch, checkout, and HARD-ASSERT before doing anything else.
git fetch origin --prune
git checkout "$DEPLOY_BRANCH" && git pull --rebase origin "$DEPLOY_BRANCH"
[ "$(git rev-parse --abbrev-ref HEAD)" = "$DEPLOY_BRANCH" ] || {
  echo "FATAL: not on $DEPLOY_BRANCH — the ledger + this command file may be stale. Stop." >&2
  exit 1; }

pip install -q -r tools/requirements.txt 2>/dev/null || true  # boto3 (R2) + imageio-ffmpeg (mp3); a SessionStart hook also does this — render/upload fail cold without them

# Build the "already covered" exclusion block ONCE, from the deploy branch's ledger,
# and reuse it verbatim in every research subagent (step 1) so a fan-out never
# surfaces already-aired stories/vocab (which is what forces a costly re-research).
EXCLUDE="$(python3 tools/exclude_context.py --recent 8)"
printf '%s\n' "$EXCLUDE" | tee "${TMPDIR:-/tmp}/commute-exclude.txt"   # the ledger you MUST dedup against — recent stories + explainers + ALL used vocab
# Then hand research subagents the FILE (${TMPDIR:-/tmp}/commute-exclude.txt) instead of
# re-pasting this ~240-line block into every subagent prompt AND your own context — write
# it once, reference it by path. (Re-dumping it per-agent is pure token waste.)
```
(A **SessionStart guard** — `tools/preflight_deploy_branch.sh` — also runs
automatically and shouts if this branch's command file/ledger is behind the deploy
branch. If you see that warning, `git checkout $DEPLOY_BRANCH && git pull` and
re-open `/morning-commute` before doing anything — otherwise you're running a stale
playbook against a stale ledger, exactly the failure that causes duplicate research.)
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
/ calendar, news search), write the day's brief — the source of record. Keep it a
**compact, structured block** — numbers, tickers, and short slugs, one line per
item, NOT prose paragraphs (a prose brief pays output tokens twice for facts the
script then re-expresses; the script is the only place prose belongs). Cover
exactly what the steering prompt's segments require, with **real, accurate**
numbers (most-recent US close for S&P/Nasdaq/Dow, notable movers, rates/Fed angle,
2 world + 2 US-business + 2 international + 1 China item, the energy/AI-power
theme, Philippines weather + BSP + peso, arts & culture, one good thing). Pick one
throughline that connects the macro blocks. Cross-check the history ledger from
step 0 — pick **fresh** stories, not ones already covered.

**Philippines — source from the local desks.** Pull the weather + macro from
**Rappler**, the **Philippine Daily Inquirer** (`inquirer.net` / `newsinfo.inquirer.net`),
and **GMA News** (`gmanetwork.com/news`) — plus **PAGASA** for the storm bulletin and
the **BSP** for rates/peso. Web-search/fetch those domains directly; they carry the
local detail (PAGASA signal levels, landfall, BSP statements) the wires miss.

**Arts & Culture — visual/fine art, opera, literature first (not just movies).**
Lead with **visual & fine art** (exhibitions, biennials, art fairs, auctions, notable
gallery shows), **opera & classical**, and **literature** (releases, prizes,
criticism); film/pop is a minor slice. Sources: **The Art Newspaper**, **ARTnews**,
**Artforum**, **Hyperallergic**, **Frieze** (visual art); **Van Magazine**,
**Operawire**, **Gramophone** (opera/classical); **NYRB**, **LRB**, **LitHub**, the
**Paris Review**, and major prize news — Booker, Pulitzer, Nobel (literature); plus
**FT Life & Arts** and **NYT Arts**. Also check the user's inbox (Gmail) for
gallery/fair mail she gets — e.g. `from:anatebgi.com OR from:companygallery.us OR
from:tokyogendai.com` — to surface specific shows she'd care about.

**Energy / data centers / utilities — research deep.** Assume the listener knows
the AI-infrastructure capex cycle cold (she works in energy/data-center development —
pitch it to a practitioner, never a 101). Pull the sophisticated sources, not general
press: **SemiAnalysis** (accelerator/datacenter economics, capex models),
**Utility Dive** (ratebase, interconnection, PPAs, FERC/RTO policy), plus IEA,
BloombergNEF, FERC, and the hyperscalers' own capex guidance/filings. Capture
specific projects, MW/GW and capex figures, off-takers, interconnection-queue and
transformer/turbine bottlenecks, PPA $/MWh, capacity-auction clears, and the
second-order read — not a 101.

**Best primary source: the user's own inbox (Gmail connector).** She subscribes to
the paywalled practitioner newsletters — pull that morning's/week's editions and lead
the segment with their specifics instead of general-press paraphrase. Query, e.g.:
`from:semianalysis@substack.com OR from:utility@divenewsletter.com OR
from:hello@ctvc.co OR from:newsletter@dealflow.energy OR from:thegeneralist@substack.com
newer_than:7d` (also **Utility Dive** daily = `utility@divenewsletter.com` /
`newsletter@divenewsletter.com`; **CTVC/Sightline**, **DealFlow.energy** for PPAs &
offtake; **The Generalist** & **Chartbook/Adam Tooze** for the macro-compute angle).
Use `search_threads` then `get_thread` for the ones worth citing; attribute figures
to the source. This is the difference between a 101 and a desk read.

**Fallback — never let the energy segment silently degrade.** The Gmail connector is
OAuth, so a scheduled/headless run may not have it (if `ToolSearch` for
`mcp__Gmail__*` finds nothing, or the query errors, treat it as unavailable). In that
case, **fall back** to web-searching those same publications' public posts
(`SemiAnalysis`, `Utility Dive`, `Latitude Media/CTVC`, `RTO Insider`, FERC/PJM/ERCOT
dockets) — degrade gracefully, don't drop the depth. **Either way, state which path
you used in the end-of-run report** ("energy sourced from inbox newsletters" vs
"…from web — Gmail connector unavailable"), so a broken inbox path is visible
immediately instead of quietly reverting to general press.

**Accuracy:** pull the actual prior-session closes/levels and movers from the FMP
connector — never approximate index levels, prices, or yields from memory. If
markets were closed (weekend or holiday), use the **last trading session** and say
so in the script; do not invent a close for a day with no trading.

**Keep research cheap (token cost).** Raw tool dumps are the biggest token sink —
`all-index-quotes` returns ~350 symbols, `biggest-gainers`/`losers` ~50 microcaps.
Instead query **narrowly**: `index-quote` for `^GSPC ^IXIC ^DJI ^RUT`, `batch-quote`
for the ~10 names you'll actually cite, `economics treasury-rates`, `commodity` for
`CLUSD`/`BZUSD`/`GCUSD`, `forex` for the FX pairs — and slice any big result with
`python3 -c` for just the fields you need. Best of all, run the research fan-out
(FMP pulls + web/news searches) inside **Agent subagents** that return only the
distilled numbers, so the raw JSON never lands in the main context.
`tools/market_snapshot.py` (needs `FMP_API_KEY`) prints one compact block for the
whole market section.

**Dedup the fan-out at the SOURCE — paste `$EXCLUDE` into every research subagent.**
The single most expensive daily failure is *duplicate research*: agents told only
"don't repeat June" surface a week of already-aired stories, which you then discard
and re-run (that is precisely what cost 2026-07-17 a second research pass + a full
rewrite). Prevent it by handing each agent the exclusion block you built in step 0:
include the verbatim `$EXCLUDE` text in the prompt and instruct "return only items
NOT already on this list; a genuinely new development on a running story is fine, a
recap is not." Regenerate it any time with `python3 tools/exclude_context.py --recent 8`.
This is far cheaper than deduping after the fact.

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
- **Write numbers as numerals — always** so the script/transcript is clean and
  readable — `7,572`, `4.55%`, `37 bps`, `2027`, `$265 billion`, `12.5%`. Do **not**
  spell them out (the 2026-06-23 example does, for old-TTS reasons — ignore that; it
  is deprecated). Keep the unit/word next to the figure. `render_gemini.py` now
  expands numerals to spoken words for the TTS automatically (`normalize_numbers`),
  so numerals render correctly as speech while the transcript stays clean.
- **Length target (this controls the duration — get it right the FIRST time so
  you render once, not twice):** the hard gate is step 7's guardrail —
  `durationSec` must be **≥ 1500** (25 min). The current renderer
  (`render_gemini.py` + `gemini-2.5-flash-preview-tts`) speaks **~19 characters of
  dialogue per audio-second** — measured, not the old ~8 figure — so **~18–20k
  chars renders only ~16–17 min and FAILS the guardrail.** Write **~30,000–33,000
  characters** of `ALEX:`/`SAM:` dialogue (≈ 5,000–5,600 words) to land **~26–29
  min**, comfortably clearing the 25-min floor with margin. **Aim for the MIDDLE of
  the band (~31–32k) on the FIRST draft** — a first pass that lands near ~27k fails
  the floor and forces an expansion loop (re-emitted prose + repeat lint passes) that
  a correct initial target avoids. `check_script.py` now also WARNs when you clear the
  floor but sit under ~30k (thin margin) — treat that warning as "add ~1k now," not
  "good enough." Before rendering,
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
- Hosts announce each segment; no run-of-show in the cold open; **there is no
  trending-meme segment** (removed) — go Arts & Culture → One Good Thing; close on
  One Good Thing.
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

**Draft efficiently (fewer tokens, one render):**
- **Start from the skeleton.** `routine/script-template.md` has the fixed structure
  (header block, all 12 segment headers, per-segment guidance comments, sign-off).
  Fill the slots — don't re-derive the scaffolding each day.
- **Structured brief in, prose out once.** The brief is compact/structured (step 1);
  the script is the ONLY prose. Write each segment once from the brief.
- **One pass, then Edit — never re-Write the whole script.** To fix a few segments
  use targeted edits, not a full regeneration (re-emitting a ~30k-char script to
  change one segment doubles output tokens for nothing).
- **Optional fan-out.** Given the brief + throughline + the template's style header,
  the macro-blocks are largely independent — you can draft them in parallel
  subagents that each return only their turns, then concatenate. Pass every subagent
  the same style header + throughline so the two voices stay consistent.
- **Right-size to the target; don't over-write** "to be safe" — extra length costs
  both model output and render calls. Trust the char→duration formula; never render
  just to measure.
- **Keep cheap passes cheap.** The counts and gates (`check_script.py`,
  `check_dedup.py`, `check_episode.py`) are plain scripts — run them directly; don't
  spend a frontier model to count characters or lint format.

Before rendering, lint the script — catches length/format bugs in milliseconds
instead of after a full render:
```bash
python3 tools/check_script.py routine/commute-two-host-script-$date.md
```

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

## 4b. Dedup preflight (before you render — cheap to fix, expensive to render twice)
Run the automated check against the **deploy branch's** ledger. A reused vocab word
is a hard-rule violation, and catching it here saves a full, quota-burning render:
```bash
python3 tools/check_dedup.py routine/vocab-$date.json routine/digest-$date.json
```
Exit 0 = all four words fresh. Non-zero = a word (or an exact story slug) already
aired — pick a fresh one and rewrite that vocab turn **before** rendering. (Bypass
only with `DEDUP_OVERRIDE=1`, and only deliberately.) The check also **warns on
semantic story repeats** — a slug that reuses the same story with different words
(token-overlap against the ledger, tunable via `NEAR_DUP_THRESHOLD`) — so a "same
story, new slug" recap gets flagged even when it isn't a byte-for-byte match.
Treat those warnings as "confirm this is a genuinely new development, or drop it."

**Keep a backup so a dedup hit doesn't force a re-research pass.** `check_dedup.py`
runs against the **full** ledger (every episode ever), while `$EXCLUDE` / `--recent 8`
only shows recent shows — so a story or **One Good Thing** from more than 8 episodes
back can pass your research subagents yet trip here (e.g. 2026-07-21's mangroves
One-Good-Thing collided with a much older episode). Cheapest defense: have the arts /
One-Good-Thing subagent return **2–3 candidates** up front, so when one collides you
swap in a ready backup instead of spinning a fresh search + rewrite.

## 5. Render audio → `commute-gemini-$date.mp3`
```bash
# Fewer, bigger chunks = fewer API calls against the free-tier DAILY request cap
# (~10), which is what actually stalls renders. ~6500 chars/chunk makes a ~30k
# script ~5 calls (vs ~8 at 4000). If a chunk comes back truncated/short, lower
# CHUNK_CHARS toward 4000 — that's the per-call output cap talking.
CHUNK_CHARS=6500 python3 routine/render_gemini.py routine/commute-two-host-script-$date.md commute-gemini-$date
```
(ALEX→Sulafat, SAM→Charon; chunked; writes a 96 kbps MP3 via ffmpeg.) If it exits
non-zero — missing `GEMINI_API_KEY`, missing ffmpeg, or a partial render — stop and
report; do not publish silent or partial audio without flagging it.

**Voices — keep them consistent (priming first).** Each chunk is a separate TTS call
and the two voices can drift/swap at the seams. The **first-line fix is priming**:
`render_gemini.py` prepends an identical VOICE-LOCK block (`VOICE_PRIME`) to every
call, and the renderer also expands numerals→words (`normalize_numbers`) and writes a
`.timing.json` sidecar for accurate transcript sync. Priming adds **no extra
requests**, so it stays under the Gemini 2.5 free-tier **request-rate limit** — keep
it that way: **fewer, bigger chunks** (the `CHUNK_CHARS≈6500` above) means fewer calls
*and* fewer voice seams. Only if drift is still audible after priming, escalate to
**per-speaker rendering** (render each host with a single fixed voice, turn by turn,
and stitch) — rock-solid but many more calls, so mind the rate limit.

**Resume, don't re-render.** If the render dies partway (free-tier quota, a 429, a
dropped connection), **re-run the exact same command** — each chunk's audio is
cached beside the output (`<base>.chunkNNN.pcm`) and only the missing chunks hit
the API, so you spend one request, not a whole episode. Caches clear on full
success. Set `FFMPEG_BIN=/path/to/ffmpeg` to force a specific ffmpeg if both
`which ffmpeg` and `imageio_ffmpeg` miss.

**Wait on the render as ONE background job — don't stack pollers.** The render is a
single long-running job; run it in the background and wait for the *one* completion
signal the harness sends when it exits. Do **not** pile a Monitor **and** a
ScheduleWakeup poll **and** repeated reads of the output file on top of a job you're
already going to be notified about — that's redundant orchestration for one event, and
the interim output-file reads come back "unchanged" (wasted calls). One job, one
notification; when it fires, check for the mp3 + `.timing.json` and move on to step 6.
Likewise don't fill the wait with unrelated file reads "to stay busy" — idle is fine.

## 6. Build + commit (no push yet)
```bash
NO_PUSH=1 tools/daily.sh routine/commute-two-host-script-$date.md commute-gemini-$date.mp3 routine/vocab-$date.json
```
This uploads audio to R2, builds the episode + index + search, folds today's
digest + vocab into `data/history.jsonl`, and commits — but holds the push so the
guardrail can gate the deploy.

## 7. Guardrail check, then deploy
`tools/daily.sh` now runs `tools/check_episode.py` automatically and **refuses to
push a malformed episode** (needs ≥ 10 segments, `durationSec` ≥ 1500, `hasAudio`),
and it asserts you're on `$DEPLOY_BRANCH` before pushing. To publish a deliberate
partial (e.g. audio truncated by a quota outage), pass `ALLOW_SHORT=1`. You should
still eyeball it:
Inspect `data/index.json` for `$date` — it should show **~11 segments** and
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
the audio duration, **which source the energy segment used** (inbox newsletters vs
web fallback — see the Energy fallback note), and that the deploy push landed.

## 8. Scorecard + retro (runs every publish — grade the run, track the trend)
The point of this step is that **every run self-evaluates against fixed GOALS and
records the result**, so quality/efficiency improve over time instead of drifting.

- **Before you build**, drop a one-line self-report so the efficiency goals aren't
  blind (artifacts can't see how many renders/research passes you spent):
  ```bash
  cat > routine/run-meta-$date.json <<JSON
  {"render_calls": 1, "research_passes": 1, "energy_source": "inbox"}
  JSON
  ```
  Set `render_calls` to how many times you invoked `render_gemini.py` (goal **1** —
  resume, don't re-render), `research_passes` to how many research rounds you ran
  (goal **1** — dedup at the source), and `energy_source` to `"inbox"` or `"web"`.
- `tools/daily.sh` then runs `tools/episode_scorecard.py $date` automatically (step
  2c) — it prints a scorecard and appends one line to **`data/run_metrics.jsonl`**.
  It's **telemetry, never a gate** (the real gates stay `check_episode.py` +
  `check_dedup.py`), so it can't block a publish.
- **After the run**, glance at the trend and act on anything systemic:
  ```bash
  python3 tools/run_retro.py
  ```
  It flags a goal missed in **≥ 2 of the last 3 runs** as SYSTEMIC — meaning fix the
  *playbook* (this command file, a tool, or a threshold), not just today's episode.

### GOALS (the evals — aim for a green scorecard, score ≥ 90)
| Goal | Target | Why |
| --- | --- | --- |
| Dialogue length | **30,000–34,000** chars | one render, ~26–29 min with margin |
| Audio duration | **1,560–1,800 s** (26–30 min) | clears the 1,500 s floor comfortably |
| Segments | **≥ 11** with turns | full show, nothing dropped |
| Host balance | ALEX **42–58%** of turns | genuine two-hander, not a monologue |
| Numerals | **0** spelled-out numbers | clean transcript; TTS expands numerals itself |
| Required segments | Headlines, Market, Energy, Philippines, Vocab, Arts, One Good Thing all present | coverage |
| Vocab split | exactly **2 Mandarin + 2 Tagalog** | format |
| Vocab freshness | **all 4 fresh** vs the full ledger | hard rule — never reuse a word |
| Vocab in script | all 4 taught words appear in the script | flashcards match the audio |
| Mandarin calibration | **≥ 1** connective/abstract (HSK-4) | targets the listener's weak spot |
| Story freshness | **0** exact repeats | advance running stories, don't recap |
| Efficiency | **1** render call, **1** research pass, energy from **inbox** | the token-discipline goals |

A miss is a signal, not a failure — expand the script, pick a fresh word, or note why,
then move on. Persistent misses (the retro's SYSTEMIC list) are where you change the
playbook so the next run starts ahead.

#!/usr/bin/env python3
"""
episode_scorecard.py — grade a built episode against The Morning Commute's quality
+ efficiency GOALS, print a scorecard, and append one metrics line to
`data/run_metrics.jsonl` so trends are visible over time (see tools/run_retro.py).

This runs automatically at the end of `tools/daily.sh` (after the build + guardrail).
It is TELEMETRY, not a gate: it exits 0 even when goals are missed, so it never
blocks a legitimate publish. The hard publish gates stay in check_episode.py
(duration/segments/audio) and check_dedup.py (vocab reuse). Pass --strict to make
it exit non-zero when any hard goal FAILs (useful in a manual pre-flight).

What it measures (all from the day's durable artifacts — no transcript needed):
  • Length / duration — "render once" discipline (dialogue chars + audio duration in band)
  • Structure — segment count, host turn balance, numerals hygiene, required segments
  • Vocab — 2+2 split, freshness vs the ledger, words actually in the script, schema,
    ≥1 Mandarin connective/abstract (HSK-4 calibration)
  • Freshness — exact story repeats (hard), semantic near-dups (informational)
  • Efficiency — OPTIONAL, self-reported via routine/run-meta-<date>.json:
        {"render_calls": 1, "research_passes": 1, "energy_source": "inbox"|"web",
         "notes": "..."}
    Artifacts can't show tool-call waste, so the run reports the few numbers that
    matter (renders should be 1, research passes 1, energy sourced from inbox). If
    the file is absent those goals show as n/a rather than being faked.

Usage:
    tools/episode_scorecard.py <YYYY-MM-DD> [--strict] [--no-record]

Env:
    RECOMMEND_CHARS default 30000   CHARS_PER_SEC default 19
"""
import argparse, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
try:
    from check_dedup import near_duplicates, _tokens  # pure functions, no network
except Exception:                                      # pragma: no cover
    near_duplicates = None

# HSK-4 connectives / abstract discourse markers the steering prompt asks for
# (≥1 of the two Mandarin words should be one of these, not a concrete noun).
_ZH_CONNECTIVES = {
    "尽管", "不仅", "而且", "否则", "一旦", "既然", "反而", "难免", "与其", "不如",
    "总之", "然而", "却", "虽然", "不管", "无论", "即使", "甚至", "除非", "反正",
    "毕竟", "究竟", "到底", "于是", "因此", "从而", "进而", "以及", "并且", "何况",
    "固然", "宁可", "总而言之", "换言之", "简而言之", "综上",
}
_NUMWORD = (r"(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
            r"thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|"
            r"thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred)")
_SPELLED_NUM = re.compile(rf"\b{_NUMWORD}[\s-]+(?:hundred|thousand|million|billion|"
                          rf"trillion|percent)\b", re.I)

REQUIRED_SEGMENTS = {  # keyword → human label; each must appear in some `## ` header
    "HEADLINE": "Headlines", "MARKET": "Market overview", "ENERGY": "Energy",
    "PHILIPPINE": "Philippines", "VOCAB": "Vocab", "ART": "Arts & Culture",
    "ONE GOOD THING": "One Good Thing",
}


def _read(path):
    try:
        return open(path, encoding="utf-8").read()
    except OSError:
        return None


def _json(path):
    txt = _read(path)
    try:
        return json.loads(txt) if txt else None
    except json.JSONDecodeError:
        return None


def _first(*paths):
    for p in paths:
        if p and os.path.isfile(p):
            return p
    return None


class Card:
    """Accumulates graded checks. status ∈ pass|warn|fail|na."""
    def __init__(self):
        self.rows = []

    def add(self, group, label, status, detail="", hard=False):
        self.rows.append(dict(group=group, label=label, status=status,
                              detail=detail, hard=hard))

    def band(self, group, label, val, lo, hi, warn_lo, warn_hi, unit="", hard=False):
        """pass in [lo,hi]; warn in [warn_lo,lo) ∪ (hi,warn_hi]; else fail."""
        if val is None:
            return self.add(group, label, "na", "unavailable")
        v = f"{val}{unit}"
        if lo <= val <= hi:
            self.add(group, label, "pass", v, hard)
        elif warn_lo <= val < lo or hi < val <= warn_hi:
            self.add(group, label, "warn", f"{v} (target {lo}-{hi}{unit})", hard)
        else:
            self.add(group, label, "fail", f"{v} (target {lo}-{hi}{unit})", hard)


def grade(date, strict):
    c = Card()
    metrics = {"date": date}

    # ── locate artifacts (routine/ working copies first, then the built copies) ──
    script_p = _first(os.path.join(ROOT, "routine", f"commute-two-host-script-{date}.md"),
                      os.path.join(ROOT, "scripts", f"{date}.md"))
    vocab_p = _first(os.path.join(ROOT, "routine", f"vocab-{date}.json"),
                     os.path.join(ROOT, "data", "episodes", date, "vocab.json"))
    digest_p = _first(os.path.join(ROOT, "routine", f"digest-{date}.json"),
                      os.path.join(ROOT, "data", "episodes", date, "digest.json"))
    meta_p = _first(os.path.join(ROOT, "routine", f"run-meta-{date}.json"))
    idx = _json(os.path.join(ROOT, "data", "index.json")) or {}
    entry = next((e for e in idx.get("episodes", []) if e.get("date") == date), {})

    script = _read(script_p) if script_p else None
    if not script:
        c.add("Structure", "script found", "fail", f"no script for {date}", hard=True)
        return c, metrics

    # ── LENGTH / DURATION (render-once discipline) ──────────────────────────────
    cps = float(os.environ.get("CHARS_PER_SEC", "19"))
    dialogue = re.findall(r"^(?:ALEX|SAM):.*", script, re.M)
    chars = sum(len(l) for l in dialogue)
    metrics["dialogue_chars"] = chars
    c.band("Length", "dialogue chars in band", chars, 30000, 34000, 29000, 36000, hard=True)

    dur = entry.get("durationSec")
    if dur is None:  # standalone run before build — fall back to the timing sidecar
        t = _json(os.path.join(ROOT, f"commute-gemini-{date}.timing.json"))
        dur = int(round(t["durationSec"])) if t and "durationSec" in t else None
    metrics["duration_sec"] = dur
    c.band("Length", "audio duration in band", dur, 1560, 1800, 1500, 1860, "s", hard=True)

    # ── STRUCTURE ───────────────────────────────────────────────────────────────
    headers = re.findall(r"^##\s+(.*\S)\s*$", script, re.M)
    seg_ct = entry.get("segmentCount")
    if seg_ct is None:  # recompute: headers that actually contain turns
        seg_turns, cur = {}, None
        for ln in script.splitlines():
            h = re.match(r"^##\s+(.*\S)\s*$", ln)
            if h:
                cur = h.group(1); seg_turns.setdefault(cur, 0)
            elif cur and re.match(r"^(ALEX|SAM)\s*:", ln):
                seg_turns[cur] += 1
        seg_ct = sum(1 for v in seg_turns.values() if v > 0)
    metrics["segment_count"] = seg_ct
    c.band("Structure", "segment count", seg_ct, 11, 99, 10, 99, hard=True)

    n_alex = sum(1 for l in dialogue if l.startswith("ALEX:"))
    n_turns = len(dialogue)
    alex_pct = round(100 * n_alex / n_turns) if n_turns else 0
    metrics["alex_pct"] = alex_pct
    c.band("Structure", "host turn balance (ALEX %)", alex_pct, 42, 58, 37, 63, "%")

    dtext = "\n".join(dialogue)
    spelled = list(_SPELLED_NUM.finditer(dtext))
    metrics["spelled_numbers"] = len(spelled)
    if not spelled:
        c.add("Structure", "numerals hygiene (no spelled numbers)", "pass", "0")
    else:
        egs = "; ".join(m.group(0) for m in spelled[:3])
        c.add("Structure", "numerals hygiene (no spelled numbers)", "warn",
              f"{len(spelled)} spelled — write as numerals: {egs}")

    up = script.upper()
    missing = [lab for kw, lab in REQUIRED_SEGMENTS.items() if kw not in up]
    metrics["missing_segments"] = missing
    c.add("Structure", "required segments present", "pass" if not missing else "fail",
          "all present" if not missing else "missing: " + ", ".join(missing), hard=True)

    # ── VOCAB ───────────────────────────────────────────────────────────────────
    vocab = _json(vocab_p) if vocab_p else None
    cards = (vocab or {}).get("cards", [])
    zh = [c_ for c_ in cards if c_.get("lang") == "Mandarin"]
    tl = [c_ for c_ in cards if c_.get("lang") == "Tagalog"]
    words = [c_.get("word", "") for c_ in cards if c_.get("word")]
    metrics["vocab_words"] = words
    ok_split = len(cards) == 4 and len(zh) == 2 and len(tl) == 2
    c.add("Vocab", "2 Mandarin + 2 Tagalog", "pass" if ok_split else "fail",
          f"{len(zh)} zh / {len(tl)} tl / {len(cards)} total", hard=True)

    # freshness vs the ledger (exclude today's own line, which build folds in)
    seen_vocab, seen_stories, ledger_n = _ledger_seen(date)
    clashes = [w for w in words if w in seen_vocab]
    metrics["vocab_fresh"] = not clashes
    c.add("Vocab", "all vocab fresh vs ledger", "pass" if not clashes else "fail",
          "fresh" if not clashes else "REUSED: " + ", ".join(clashes), hard=True)

    in_script = [w for w in words if w and w in script]
    c.add("Vocab", "taught words appear in script", "pass" if len(in_script) == len(words)
          else "warn", f"{len(in_script)}/{len(words)} found in script")

    zh_conn = any(w in _ZH_CONNECTIVES for w in (c_.get("word", "") for c_ in zh))
    c.add("Vocab", "≥1 Mandarin connective/abstract (HSK-4)", "pass" if zh_conn else "warn",
          "present" if zh_conn else "none matched a known connective — verify calibration")

    schema_bad = []
    for c_ in cards:
        req = ["meaning", "example", "note", "tiesTo"]
        req += ["pinyin", "tones"] if c_.get("lang") == "Mandarin" else ["pronunciation"]
        miss = [k for k in req if not str(c_.get(k, "")).strip()]
        if miss:
            schema_bad.append(f"{c_.get('id', '?')}:{'/'.join(miss)}")
    c.add("Vocab", "card schema complete", "pass" if not schema_bad else "warn",
          "ok" if not schema_bad else "; ".join(schema_bad))

    # ── FRESHNESS (stories) ─────────────────────────────────────────────────────
    digest = _json(digest_p) if digest_p else None
    stories = (digest or {}).get("stories", [])
    exact = [s for s in stories if s in seen_stories]
    metrics["exact_story_repeats"] = len(exact)
    c.add("Freshness", "no exact story repeats", "pass" if not exact else "fail",
          "none" if not exact else "; ".join(exact), hard=True)
    near_ct = 0
    if near_duplicates and stories:
        near = [h for h in near_duplicates(stories, seen_stories,
                float(os.environ.get("NEAR_DUP_THRESHOLD", "0.5")))
                if h[0] not in seen_stories]
        near_ct = len(near)
    metrics["semantic_near_dups"] = near_ct
    # Running stories (daily market overview, an ongoing war, the peso) legitimately
    # echo prior slugs, so a handful is normal and must NOT ding the score — exact
    # repeats already hard-gate the real recap risk. Only an extreme count is a smell.
    c.add("Freshness", "semantic near-dups (informational)",
          "pass" if near_ct <= 8 else "warn",
          f"{near_ct} (running stories expected; only a spike signals a recap)")

    # ── EFFICIENCY (optional self-report) ───────────────────────────────────────
    meta = _json(meta_p) if meta_p else None
    if meta:
        rc = meta.get("render_calls")
        c.add("Efficiency", "render calls", "pass" if rc == 1 else "warn" if rc else "na",
              f"{rc} (goal 1 — resume, don't re-render)")
        rp = meta.get("research_passes")
        c.add("Efficiency", "research passes", "pass" if rp == 1 else "warn" if rp else "na",
              f"{rp} (goal 1 — dedup at the source)")
        es = meta.get("energy_source")
        c.add("Efficiency", "energy source", "pass" if es == "inbox" else "warn" if es else "na",
              f"{es or '?'} (prefer inbox newsletters over web fallback)")
        metrics["render_calls"] = rc
        metrics["research_passes"] = rp
        metrics["energy_source"] = es
    else:
        c.add("Efficiency", "self-reported run meta", "na",
              f"write routine/run-meta-{date}.json to track render/research/energy")

    # ── PROCESS (measured from the run itself — external calibration, not fixed bars) ─
    # These grade HOW the run executed, against the show's own measured reality rather
    # than aspirational thresholds. The headline one is pace calibration: the finished
    # audio reveals the true speaking rate, and if it has drifted from the constant the
    # length target is built on, the target mis-predicts duration — writing too much
    # (wasted tokens) or too little (a sub-floor render). The metric tells you to retune
    # the constant, which is the process improving itself from an external signal.
    if chars and dur:
        measured = round(chars / dur, 2)
        metrics["measured_cps"] = measured
        drift = (measured - cps) / cps
        det = f"{measured} chars/s vs configured {cps} ({drift:+.0%})"
        if abs(drift) <= 0.08:
            c.add("Process", "pace calibration (chars/s)", "pass", det)
        else:
            rec = "raise" if measured > cps else "lower"
            c.add("Process", "pace calibration (chars/s)", "warn",
                  det + f" — {rec} CHARS_PER_SEC toward {round(measured)} so the length "
                        f"target predicts duration accurately (see run_retro for the trend)")
    else:
        c.add("Process", "pace calibration (chars/s)", "na", "need chars + duration")

    rstats = _json(os.path.join(ROOT, f"commute-gemini-{date}.render-stats.json"))
    if rstats:
        api, chunks_n = rstats.get("apiCalls"), rstats.get("chunks")
        cached, retries = rstats.get("cached", 0), rstats.get("retries", 0)
        metrics["render_api_calls"] = api
        metrics["render_cached"] = cached
        metrics["render_retries"] = retries
        metrics["render_wall_s"] = rstats.get("wallSeconds")
        c.add("Process", "render API efficiency",
              "pass" if (api and chunks_n and api <= chunks_n) else "warn",
              f"{api} call(s) for {chunks_n} chunk(s)"
              + (f", {cached} reused on resume" if cached else ""))
        c.add("Process", "render retries (quota friction)",
              "pass" if retries == 0 else "warn", str(retries))
        if meta and meta.get("render_calls") == 1 and cached:
            c.add("Process", "render_calls self-report vs evidence", "warn",
                  f"reported 1 render but {cached} chunk(s) were cached — that was a resume")
    else:
        c.add("Process", "render telemetry", "na",
              "no render-stats sidecar (older render, or not rendered here)")

    return c, metrics


def _ledger_seen(date):
    """seen vocab + story slugs from data/history.jsonl, EXCLUDING today's own entry
    (build_episode folds today in before this runs, so we must drop it or every word
    would look 'reused')."""
    raw = _read(os.path.join(ROOT, "data", "history.jsonl")) or ""
    seen_v, seen_s, n = set(), set(), 0
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        if e.get("date") == date:
            continue
        n += 1
        seen_v.update(e.get("vocab", []))
        seen_s.update(e.get("stories", []))
    return seen_v, seen_s, n


_MARK = {"pass": "✓", "warn": "⚠", "fail": "✗", "na": "·"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("date")
    ap.add_argument("--strict", action="store_true",
                    help="exit non-zero if any hard goal FAILs")
    ap.add_argument("--no-record", action="store_true",
                    help="don't append to data/run_metrics.jsonl")
    a = ap.parse_args()

    card, metrics = grade(a.date, a.strict)

    rows = card.rows
    graded = [r for r in rows if r["status"] != "na"]
    npass = sum(r["status"] == "pass" for r in graded)
    nwarn = sum(r["status"] == "warn" for r in graded)
    nfail = sum(r["status"] == "fail" for r in graded)
    score = round(100 * (npass + 0.5 * nwarn) / len(graded)) if graded else 0
    hard_fails = [r for r in rows if r["status"] == "fail" and r["hard"]]
    metrics["score"] = score
    metrics["pass"] = npass
    metrics["warn"] = nwarn
    metrics["fail"] = nfail
    metrics["hard_fails"] = [r["label"] for r in hard_fails]

    print(f"\n── Episode scorecard {a.date} " + "─" * 34)
    group = None
    for r in rows:
        if r["group"] != group:
            group = r["group"]
            print(f"  {group}:")
        star = " *" if r["hard"] and r["status"] in ("warn", "fail") else ""
        print(f"    {_MARK[r['status']]} {r['label']}{star}"
              + (f" — {r['detail']}" if r["detail"] else ""))
    print("  " + "─" * 46)
    print(f"  SCORE {score}/100   ({npass} pass · {nwarn} warn · {nfail} fail"
          f" · {sum(r['status']=='na' for r in rows)} n/a)")
    if hard_fails:
        print(f"  ✗ HARD GOALS MISSED: " + "; ".join(r["label"] for r in hard_fails))
    print("  (telemetry only — publish gates are check_episode.py + check_dedup.py)")

    if not a.no_record:
        try:
            with open(os.path.join(ROOT, "data", "run_metrics.jsonl"), "a",
                      encoding="utf-8") as f:
                f.write(json.dumps(metrics, ensure_ascii=False) + "\n")
            print(f"  → recorded to data/run_metrics.jsonl")
        except OSError as e:
            print(f"  (could not record metrics: {e})", file=sys.stderr)

    sys.exit(1 if (a.strict and hard_fails) else 0)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
run_retro.py — read the scorecard ledger (data/run_metrics.jsonl) and show how the
show is trending, so the daily routine improves instead of drifting. This is the
"improvement" half of the loop: episode_scorecard.py records each run; this reads
the tail and surfaces regressions worth fixing in the PLAYBOOK (the command file),
not just in one episode.

It flags a goal as SYSTEMIC when it's missed in ≥2 of the last 3 runs — a one-off is
noise, a repeat is a process bug (fix `.claude/commands/morning-commute.md`, a tool,
or a threshold). Prints a compact table + the systemic list. Read-only; records
nothing.

Usage:
    tools/run_retro.py [--last N]     # default N=8
"""
import argparse, json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEDGER = os.path.join(ROOT, "data", "run_metrics.jsonl")


def load(n):
    try:
        lines = [l for l in open(LEDGER, encoding="utf-8").read().splitlines() if l.strip()]
    except OSError:
        return []
    out = []
    for l in lines:
        try:
            out.append(json.loads(l))
        except json.JSONDecodeError:
            pass
    # de-dup by date keeping the LAST record for each (a re-publish overwrites)
    by_date = {}
    for e in out:
        by_date[e.get("date")] = e
    rows = sorted(by_date.values(), key=lambda e: e.get("date", ""))
    return rows[-n:]


def arrow(cur, prev):
    if prev is None or cur is None:
        return " "
    return "▲" if cur > prev else "▼" if cur < prev else "="


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--last", type=int, default=8)
    a = ap.parse_args()
    rows = load(a.last)
    if not rows:
        print("no runs recorded yet — data/run_metrics.jsonl is empty "
              "(episode_scorecard.py writes it each publish).")
        return

    print(f"\n── Run retro (last {len(rows)}) " + "─" * 40)
    print(f"  {'date':<11} {'score':>5} {'chars':>6} {'dur':>5} {'cps':>5} "
          f"{'api':>4} {'ret':>4}  flags")
    prev_score = None
    for e in rows:
        score = e.get("score")
        flags = []
        if not e.get("vocab_fresh", True):
            flags.append("VOCAB-REUSE")
        if e.get("exact_story_repeats"):
            flags.append(f"repeat×{e['exact_story_repeats']}")
        for hf in e.get("hard_fails", []):
            flags.append(hf.split(" (")[0])
        if e.get("energy_source") == "web":
            flags.append("energy=web")
        if e.get("render_retries"):
            flags.append(f"retries×{e['render_retries']}")
        if e.get("render_cached"):
            flags.append("resumed")
        print(f"  {e.get('date',''):<11} {str(score):>5}{arrow(score,prev_score)} "
              f"{str(e.get('dialogue_chars','')):>6} {str(e.get('duration_sec','')):>5} "
              f"{str(e.get('measured_cps','')):>5} {str(e.get('render_api_calls','')):>4} "
              f"{str(e.get('render_retries','')):>4}  "
              + (", ".join(dict.fromkeys(flags)) if flags else "—"))
        prev_score = score

    # systemic: a hard-fail / reuse missed in ≥2 of the last 3 runs
    last3 = rows[-3:]
    tally = {}
    for e in last3:
        misses = list(e.get("hard_fails", []))
        if not e.get("vocab_fresh", True):
            misses.append("vocab freshness")
        if e.get("exact_story_repeats"):
            misses.append("no exact story repeats")
        if e.get("energy_source") == "web":
            misses.append("energy from inbox")
        for m in dict.fromkeys(misses):
            tally[m] = tally.get(m, 0) + 1
    systemic = sorted([m for m, k in tally.items() if k >= 2])

    print("  " + "─" * 52)
    if systemic:
        print("  ⚠ SYSTEMIC (missed in ≥2 of last 3) — fix the PLAYBOOK, not just an episode:")
        for m in systemic:
            print(f"      • {m}")
    else:
        print("  ✓ no systemic regressions across the last 3 runs")

    # ── PROCESS calibration (the external-metric loop) ───────────────────────────
    # The show's own measured pace is the ground truth for length targeting. When it
    # settles away from the configured constant, recommend retuning it — so the NEXT
    # run's length target predicts duration correctly instead of over/under-writing.
    import statistics
    cfg_cps = float(os.environ.get("CHARS_PER_SEC", "19"))
    paces = [e["measured_cps"] for e in rows if isinstance(e.get("measured_cps"), (int, float))]
    if len(paces) >= 2:
        med = round(statistics.median(paces), 1)
        drift = (med - cfg_cps) / cfg_cps
        if abs(drift) > 0.05:
            tgt_lo, tgt_hi = round(med * 1560), round(med * 1740)  # chars for 26-29 min
            print(f"  ⚙ PACE DRIFT: measured median {med} chars/s vs configured {cfg_cps} "
                  f"({drift:+.0%}) over {len(paces)} run(s).")
            print(f"      → set CHARS_PER_SEC={round(med)} in check_script.py + the command, "
                  f"and target ~{tgt_lo//1000}–{tgt_hi//1000}k dialogue chars, so length "
                  f"predicts duration (stop {'over' if drift<0 else 'under'}-writing).")
        else:
            print(f"  ✓ pace calibrated: median {med} chars/s ≈ configured {cfg_cps}")

    retries = [e.get("render_retries", 0) for e in rows if e.get("render_retries") is not None]
    if retries and sum(retries):
        print(f"  ⚙ render friction: {sum(retries)} retr(y/ies) across {len(retries)} run(s) "
              f"— if recurring, lower CHUNK_CHARS or spread the render to dodge the quota.")

    scores = [e.get("score") for e in rows if isinstance(e.get("score"), int)]
    if scores:
        print(f"  avg score (last {len(scores)}): {round(sum(scores)/len(scores))}/100"
              f"   latest: {scores[-1]}/100")


if __name__ == "__main__":
    main()

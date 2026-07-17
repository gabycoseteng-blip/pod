#!/usr/bin/env python3
"""
exclude_context.py — emit the compact "already covered" block to paste into
research/subagent prompts, so a research pass never surfaces items the show has
already aired.

The daily routine's most expensive failure is *duplicate research*: fan out a
fleet of agents, get back stories/vocab that already aired, discard them, and
re-run the whole pass (which is exactly how 2026-07-17 burned a second research
round + a full script rewrite). `check_dedup.py` catches reuse AFTER authoring;
this feeds the exclusion list IN, before a single search runs.

It reads the ledger from the DEPLOY branch (origin/<branch>:data/history.jsonl),
not the local working copy, so a run that started on a stale/diverged branch
still excludes against what is actually published.

Usage:
    tools/exclude_context.py [--recent N] [--branch main] [--json]

    --recent N   how many of the most-recent episodes to list stories/explainers
                 for (default 8). ALL vocab ever used is always listed (a word is
                 a hard "never reuse", regardless of age).
    --branch B   deploy branch to read the ledger from (default: $DEPLOY_BRANCH or main)
    --json       emit machine-readable JSON instead of the promptable text block

Typical use in the routine (step 1): capture the block once and hand the SAME
text to every research subagent:
    EXCLUDE="$(python3 tools/exclude_context.py --recent 8)"
    # ...then include "$EXCLUDE" verbatim in each agent prompt.
"""
import argparse, json, os, subprocess, sys


def load_ledger(branch):
    """history entries from origin/<branch>:data/history.jsonl, falling back to
    the local file if that ref isn't available (mirrors check_dedup.py)."""
    subprocess.run(["git", "fetch", "origin", branch], capture_output=True)
    raw = subprocess.run(
        ["git", "show", f"origin/{branch}:data/history.jsonl"],
        capture_output=True, text=True,
    ).stdout
    if not raw.strip():
        try:
            raw = open(os.path.join("data", "history.jsonl"), encoding="utf-8").read()
        except OSError:
            raw = ""
    out = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--recent", type=int, default=8)
    ap.add_argument("--branch", default=os.environ.get("DEPLOY_BRANCH", "main"))
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    ledger = load_ledger(a.branch)
    ledger.sort(key=lambda e: e.get("date", ""))
    recent = ledger[-a.recent:] if a.recent > 0 else ledger

    all_vocab = sorted({w for e in ledger for w in e.get("vocab", [])})
    recent_stories = [s for e in recent for s in e.get("stories", [])]
    recent_explainers = [x for e in recent for x in e.get("explainers", [])]
    throughlines = [(e.get("date", ""), e.get("throughline", "")) for e in recent]

    if a.json:
        json.dump({
            "branch": a.branch,
            "episodes_on_record": len(ledger),
            "recent": a.recent,
            "vocab_used": all_vocab,
            "recent_stories": recent_stories,
            "recent_explainers": recent_explainers,
            "recent_throughlines": throughlines,
        }, sys.stdout, ensure_ascii=False, indent=2)
        print()
        return

    L = []
    L.append("=== ALREADY COVERED — DO NOT REPEAT (exclusion list) ===")
    L.append(f"(from origin/{a.branch}:data/history.jsonl — {len(ledger)} episodes on record, "
             f"last {len(recent)} detailed below)")
    L.append("")
    L.append("RECENT THROUGHLINES (the running story — advance it with NEW data, never recap):")
    for d, t in throughlines:
        if t:
            L.append(f"  - {d}: {t}")
    L.append("")
    L.append("STORIES already aired in the last "
             f"{len(recent)} episodes — do NOT re-run these (a genuinely new development on a "
             "running story is fine; a recap is not):")
    for s in recent_stories:
        L.append(f"  - {s}")
    L.append("")
    L.append("CONCEPTS already explained — do NOT re-teach (reference, don't re-explain):")
    for x in recent_explainers:
        L.append(f"  - {x}")
    L.append("")
    L.append(f"VOCAB words ALREADY TAUGHT ({len(all_vocab)}) — NEVER reuse any of these, "
             "at any age; pick fresh words:")
    L.append("  " + "  ".join(all_vocab))
    L.append("=== END exclusion list ===")
    print("\n".join(L))


if __name__ == "__main__":
    main()

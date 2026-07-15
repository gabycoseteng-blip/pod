#!/usr/bin/env python3
"""
check_dedup.py — preflight dedup guard for the daily routine.

Fails (exit 1) if any of today's VOCAB words already appear in the show's history
ledger, and warns (exit 0) if a story slug exactly repeats. Run this BEFORE
rendering so a reused word is caught in seconds — not after a full, quota-burning
TTS render (which is exactly how 2026-07-15 wasted a render on a reused 一旦).

Crucially it dedups against the DEPLOY branch's ledger (origin/<branch>), not the
local working copy — so a run that started on a stale or diverged branch still
checks against what is actually published.

Usage:
    tools/check_dedup.py <vocab.json> [digest.json] [--branch main]

Env:
    DEPLOY_BRANCH    branch to dedup against (default: main; --branch overrides)
    DEDUP_OVERRIDE   set to any value to downgrade a vocab collision to a warning
"""
import argparse, json, os, subprocess, sys


def load_ledger(branch):
    """history entries from origin/<branch>:data/history.jsonl, falling back to
    the local file if that ref isn't available."""
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
    ap.add_argument("vocab")
    ap.add_argument("digest", nargs="?")
    ap.add_argument("--branch", default=os.environ.get("DEPLOY_BRANCH", "main"))
    a = ap.parse_args()

    ledger = load_ledger(a.branch)
    seen_vocab = {w for e in ledger for w in e.get("vocab", [])}
    seen_stories = {s for e in ledger for s in e.get("stories", [])}

    cards = json.load(open(a.vocab, encoding="utf-8")).get("cards", [])
    words = [c.get("word", "") for c in cards if c.get("word")]
    clashes = [w for w in words if w in seen_vocab]

    story_clashes = []
    if a.digest and os.path.isfile(a.digest):
        stories = json.load(open(a.digest, encoding="utf-8")).get("stories", [])
        story_clashes = [s for s in stories if s in seen_stories]

    print(f"dedup vs origin/{a.branch}: {len(ledger)} prior episodes, "
          f"{len(seen_vocab)} vocab words on record")
    if story_clashes:
        print("⚠ story slug(s) exactly repeat a prior episode — advance, don't recap: "
              + ", ".join(story_clashes))

    if not clashes:
        print(f"✓ all {len(words)} vocab words are fresh: {' '.join(words)}")
        sys.exit(0)

    print(f"✗ VOCAB REUSE — already taught on a prior episode: {', '.join(clashes)}",
          file=sys.stderr)
    if os.environ.get("DEDUP_OVERRIDE"):
        print("  (DEDUP_OVERRIDE set — continuing anyway)", file=sys.stderr)
        sys.exit(0)
    print("  Pick fresh words, or set DEDUP_OVERRIDE=1 to bypass.", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()

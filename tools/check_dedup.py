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
import argparse, json, os, re, subprocess, sys

# tokens too generic to signal a shared story on their own
_STOP = {
    "us", "the", "of", "and", "to", "in", "on", "for", "a", "an", "vs", "at",
    "market", "overview", "q1", "q2", "q3", "q4", "2026", "2027", "record",
    "new", "up", "down", "pct", "bn", "bps", "day", "week", "high", "low",
}


def _stem(t):
    """crude suffix-strip so raises/raised/raising collapse to one token (no NLTK
    dependency; good enough to make reworded slugs overlap)."""
    for suf in ("ing", "ed", "es", "s"):
        if t.endswith(suf) and len(t) - len(suf) >= 3:
            return t[: -len(suf)]
    return t


def _tokens(slug):
    """significant, stemmed word tokens of a kebab-case story slug (drop generic/stop
    words and pure numbers, so 'tsmc-raises-capex-guide' and 'tsmc-capex-revenue-raised'
    still overlap on {tsmc, capex, rais})."""
    toks = re.split(r"[^a-z0-9]+", slug.lower())
    return {_stem(t) for t in toks
            if t and t not in _STOP and not t.isdigit() and len(t) > 2}


def near_duplicates(today, seen, threshold):
    """for each of today's story slugs, the best prior slug whose token-overlap
    (Jaccard) meets `threshold` OR that shares >= 3 significant tokens — the
    semantic repeats an exact-match check misses."""
    hits = []
    seen_tok = [(s, _tokens(s)) for s in seen]
    for s in today:
        a = _tokens(s)
        if not a:
            continue
        best, best_j = None, 0.0
        for prior, b in seen_tok:
            if not b or prior == s:
                continue
            inter = len(a & b)
            j = inter / len(a | b)
            if (j >= threshold or inter >= 3) and j > best_j:
                best, best_j = prior, j
        if best:
            hits.append((s, best, round(best_j, 2)))
    return hits


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

    story_clashes, near = [], []
    if a.digest and os.path.isfile(a.digest):
        stories = json.load(open(a.digest, encoding="utf-8")).get("stories", [])
        story_clashes = [s for s in stories if s in seen_stories]
        threshold = float(os.environ.get("NEAR_DUP_THRESHOLD", "0.5"))
        near = [h for h in near_duplicates(stories, seen_stories, threshold)
                if h[0] not in seen_stories]  # don't double-report exact hits

    print(f"dedup vs origin/{a.branch}: {len(ledger)} prior episodes, "
          f"{len(seen_vocab)} vocab words on record")
    if story_clashes:
        print("⚠ story slug(s) exactly repeat a prior episode — advance, don't recap: "
              + ", ".join(story_clashes))
    if near:
        print("⚠ story slug(s) look like a SEMANTIC repeat (same story, different words) — "
              "confirm it's a genuinely new development, not a recap:")
        for s, prior, j in near:
            print(f"    {s}  ~  {prior}  (overlap {j})")

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

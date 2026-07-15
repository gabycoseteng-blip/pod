#!/usr/bin/env python3
"""
check_episode.py — guardrail gate for a freshly built episode.

Exits non-zero if the episode in data/index.json is malformed, so daily.sh can
refuse to deploy a broken or too-short one instead of relying on a human eyeball.

Checks: segmentCount >= MIN_SEGMENTS, hasAudio true, durationSec >= MIN_DURATION.

Usage:
    tools/check_episode.py <YYYY-MM-DD>

Env:
    MIN_SEGMENTS   default 11
    MIN_DURATION   default 1500 (seconds — the 25-min floor)
    ALLOW_SHORT    set to any value to permit a below-floor duration (e.g. a
                   deliberately published partial) — downgrades it to a warning
"""
import json, os, sys


def main():
    if len(sys.argv) < 2:
        print("usage: check_episode.py <YYYY-MM-DD>", file=sys.stderr)
        sys.exit(2)
    date = sys.argv[1]
    min_seg = int(os.environ.get("MIN_SEGMENTS", "11"))
    min_dur = int(os.environ.get("MIN_DURATION", "1500"))

    idx = json.load(open(os.path.join("data", "index.json")))
    hits = [e for e in idx.get("episodes", []) if e.get("date") == date]
    if not hits:
        print(f"✗ no episode for {date} in data/index.json", file=sys.stderr)
        sys.exit(1)
    e = hits[0]
    seg, dur, aud = e.get("segmentCount", 0), e.get("durationSec", 0), e.get("hasAudio")
    print(f"episode {date}: {seg} segments, {dur}s (~{round(dur/60,1)} min), hasAudio={aud}")

    problems = []
    if seg < min_seg:
        problems.append(f"segments {seg} < {min_seg}")
    if not aud:
        problems.append("hasAudio is false")
    short = dur < min_dur
    if short:
        if os.environ.get("ALLOW_SHORT"):
            print(f"⚠ duration {dur}s below the {min_dur}s floor — allowed via ALLOW_SHORT")
        else:
            problems.append(f"durationSec {dur} < {min_dur}")

    if problems:
        print("✗ guardrail FAILED: " + "; ".join(problems), file=sys.stderr)
        sys.exit(1)
    print("✓ guardrail passed")
    sys.exit(0)


if __name__ == "__main__":
    main()

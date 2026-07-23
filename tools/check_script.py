#!/usr/bin/env python3
"""
check_script.py — cheap pre-render lint for a two-host script, so format and
length bugs are caught in milliseconds instead of after a full, quota-burning
render. Run it right before step 5.

Checks (Unicode-aware — `wc -c` counts bytes and over-counts the Mandarin/Tagalog
vocab segment ~3x, so it lies about length):
  - a `### Weekday, Month D, YYYY` title line parses (else build_episode falls
    back to the filename date — a warning, not fatal)
  - >= MIN_SEGMENTS `## ` segments that actually contain ALEX:/SAM: turns
  - the dialogue length predicts >= MIN_DURATION seconds at CHARS_PER_SEC, i.e.
    the episode will clear step 7's duration guardrail

Exits non-zero if the script would miss the guardrail, so you fix it BEFORE
spending a render.

Usage:
    tools/check_script.py <script.md>

Env:
    MIN_SEGMENTS    default 11
    MIN_DURATION    default 1500  (seconds — the 25-min floor)
    CHARS_PER_SEC   default 17    (measured median pace of gemini-2.5-flash-preview-tts
                                   across runs — see run_retro.py; re-measure if the
                                   voice/model changes)
    RECOMMEND_CHARS default 27000 (the comfortable first-draft target; a script that
                                   clears the floor but sits under this gets a WARN —
                                   thin margin, a slightly slower render can dip under)
"""
import os, re, sys


def main():
    if len(sys.argv) < 2:
        print("usage: check_script.py <script.md>", file=sys.stderr)
        sys.exit(2)
    text = open(sys.argv[1], encoding="utf-8").read()
    min_seg = int(os.environ.get("MIN_SEGMENTS", "11"))
    min_dur = int(os.environ.get("MIN_DURATION", "1500"))
    cps = float(os.environ.get("CHARS_PER_SEC", "17"))
    rec_chars = int(os.environ.get("RECOMMEND_CHARS", "27000"))

    problems, warns = [], []

    if not re.search(r"^###\s+\w+,\s+\w+\s+\d{1,2},\s+\d{4}\s*$", text, re.M):
        warns.append("no '### Weekday, Month D, YYYY' title line "
                     "(build_episode will fall back to the filename date)")

    # count segments that actually contain turns (header-only segments are dropped
    # by build_episode, so they don't count toward the guardrail)
    seg, order, turns_in = None, [], {}
    for line in text.splitlines():
        h = re.match(r"^##\s+(.*\S)\s*$", line)
        if h:
            seg = h.group(1)
            order.append(seg)
            turns_in.setdefault(seg, 0)
            continue
        if seg and re.match(r"^\s*(ALEX|SAM)\s*:", line):
            turns_in[seg] += 1
    with_turns = [s for s in order if turns_in.get(s, 0) > 0]
    if len(with_turns) < min_seg:
        problems.append(f"only {len(with_turns)} segments contain turns (< {min_seg})")

    dialogue = re.findall(r"^(?:ALEX|SAM):.*", text, re.M)
    chars = sum(len(l) for l in dialogue)
    pred = round(chars / cps)
    print(f"{len(dialogue)} turns across {len(with_turns)} segments; "
          f"{chars} dialogue chars → ~{pred}s (~{round(pred/60,1)} min) at {cps} chars/s")
    if not dialogue:
        problems.append("no ALEX:/SAM: turns found")
    elif pred < min_dur:
        problems.append(f"predicted {pred}s < {min_dur}s floor — too short; "
                        f"expand substantive segments before rendering")
    elif chars < rec_chars:
        # Above the hard floor but under the comfortable target: the render clears
        # the guardrail only by a thin margin, and expanding now (a few Edits) is far
        # cheaper than discovering a sub-floor render after burning TTS quota.
        warns.append(f"{chars} chars clears the {min_dur}s floor but is under the "
                     f"recommended {rec_chars} (~{round(rec_chars/cps)}s, "
                     f"~{round(rec_chars/cps/60,1)} min) — thin margin. Add "
                     f"~{rec_chars-chars} chars of real content now to render once, "
                     f"not twice.")

    for w in warns:
        print("⚠ " + w)
    if problems:
        print("✗ pre-render lint FAILED: " + "; ".join(problems), file=sys.stderr)
        sys.exit(1)
    print("✓ pre-render lint passed — safe to render")
    sys.exit(0)


if __name__ == "__main__":
    main()

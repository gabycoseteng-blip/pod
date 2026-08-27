#!/usr/bin/env python3
"""
validate_artifacts.py — schema gate for the day's model-authored JSON, run by
daily.sh before the build.

Why: build_episode.py is deliberately forgiving — a vocab.json that doesn't
parse becomes "0 cards", a broken digest becomes an EMPTY history line — so a
malformed artifact doesn't crash the publish, it silently blinds future dedup
(and a broken markets.json would be published straight to the app's Markets
tab). This gate turns those silent degradations into a hard stop while they're
still one cheap edit away from fixed.

Usage:
    tools/validate_artifacts.py <YYYY-MM-DD>

Hard-fails (exit 1) on: unparseable/missing vocab or digest, empty stories or
throughline, cards without word/lang/meaning, malformed markets.json (it's
optional — but if present it must be right). Softer shape drift (card count,
language mix) warns and passes.
"""
import json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
problems, warnings = [], []


def load(path):
    try:
        return json.load(open(path, encoding="utf-8"))
    except FileNotFoundError:
        problems.append(f"{os.path.relpath(path, ROOT)} is missing")
    except json.JSONDecodeError as e:
        problems.append(f"{os.path.relpath(path, ROOT)} is not valid JSON ({e})")
    return None


def check_vocab(date):
    v = load(os.path.join(ROOT, "routine", f"vocab-{date}.json"))
    if v is None:
        return
    cards = v.get("cards")
    if not isinstance(cards, list) or not cards:
        problems.append("vocab: 'cards' must be a non-empty list")
        return
    langs = []
    for i, c in enumerate(cards):
        for field in ("word", "lang", "meaning", "example"):
            if not isinstance(c.get(field), str) or not c.get(field).strip():
                problems.append(f"vocab card {i + 1}: missing/empty '{field}'")
        langs.append(c.get("lang", ""))
        if c.get("lang") == "Mandarin" and not c.get("pinyin"):
            warnings.append(f"vocab card {i + 1} ({c.get('word', '?')}): Mandarin card "
                            "without pinyin")
    if len(cards) != 4:
        warnings.append(f"vocab: {len(cards)} cards (canonical show teaches 4 — 2 Tagalog + 2 Mandarin)")
    elif sorted(langs) != ["Mandarin", "Mandarin", "Tagalog", "Tagalog"]:
        warnings.append(f"vocab: language mix is {langs} (expected 2 Tagalog + 2 Mandarin)")


def check_digest(date):
    d = load(os.path.join(ROOT, "routine", f"digest-{date}.json"))
    if d is None:
        return
    if not isinstance(d.get("throughline"), str) or not d.get("throughline", "").strip():
        problems.append("digest: 'throughline' missing/empty — the ledger line would be blank")
    stories = d.get("stories")
    if not isinstance(stories, list) or not stories or \
            not all(isinstance(s, str) and s.strip() for s in stories):
        problems.append("digest: 'stories' must be a non-empty list of slugs — future "
                        "dedup goes blind without it")
    if not isinstance(d.get("explainers", []), list):
        problems.append("digest: 'explainers' must be a list")


def check_markets(date):
    path = os.path.join(ROOT, "routine", f"markets-{date}.json")
    if not os.path.isfile(path):
        warnings.append("no markets snapshot for today — the Markets tab keeps yesterday's "
                        "(fine if FMP was unavailable)")
        return
    m = load(path)
    if m is None:
        return
    groups = m.get("groups")
    if not isinstance(groups, list) or not groups:
        problems.append("markets: 'groups' must be a non-empty list")
        return
    for g in groups:
        rows = g.get("rows")
        if not isinstance(g.get("name"), str) or not isinstance(rows, list):
            problems.append(f"markets: group {g.get('name', '?')!r} needs 'name' + 'rows' list")
            continue
        for r in rows:
            if not isinstance(r.get("label"), str) or not isinstance(r.get("value"), str):
                problems.append(f"markets: row {r!r} needs string 'label' + 'value'")
                break


def main():
    if len(sys.argv) < 2 or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", sys.argv[1]):
        print("usage: validate_artifacts.py <YYYY-MM-DD>", file=sys.stderr)
        sys.exit(2)
    date = sys.argv[1]
    check_vocab(date)
    check_digest(date)
    check_markets(date)

    for w in warnings:
        print(f"⚠ {w}")
    if problems:
        for p in problems:
            print(f"✗ {p}", file=sys.stderr)
        print(f"✗ artifact validation FAILED ({len(problems)}) — fix the JSON and re-run "
              "(cheap now, ledger-corrupting after the build).", file=sys.stderr)
        sys.exit(1)
    print(f"✓ artifacts for {date} validate" + (f" ({len(warnings)} warning(s))" if warnings else ""))


if __name__ == "__main__":
    main()

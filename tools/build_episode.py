#!/usr/bin/env python3
"""
build_episode.py — ingest a daily two-host script (+ audio + vocab) into the
PWA's data folder, and (re)build the episodes index.

Usage:
    python3 tools/build_episode.py <script.md> [audio.mp3] [vocab.json]

What it does:
  - parses the `## ...` segment headers and ALEX:/SAM: turns into episode.json
  - estimates a start-time (seconds) for each segment from spoken-char share
    (approximate — Gemini-TTS doesn't return word timings)
  - records the audio reference + copies vocab.json into data/episodes/<date>/
  - rebuilds data/index.json (newest first)

Audio storage:
  Set AUDIO_BASE_URL (e.g. https://audio.example.com) to keep MP3s out of git —
  episode.json then stores "<AUDIO_BASE_URL>/<date>.mp3" and you upload the file
  to the bucket with tools/upload_audio.py. Without AUDIO_BASE_URL, a local MP3
  is copied into the repo (legacy/dev mode).

The date is taken from the script filename (…-YYYY-MM-DD.md). Re-running for the
same date overwrites that episode's files and refreshes the index.
"""
import os, re, sys, json, shutil, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
EPDIR = os.path.join(DATA, "episodes")

MP3_BITRATE = 96000  # bits/sec — matches render_gemini.py output; used to estimate duration


def die(m):
    print(f"ERROR: {m}", file=sys.stderr); sys.exit(1)


def find_date(path, text):
    m = re.search(r"(\d{4}-\d{2}-\d{2})", os.path.basename(path))
    if m:
        return m.group(1)
    # fall back to a "Month DD, YYYY" in the header
    m = re.search(r"([A-Z][a-z]+ \d{1,2}, \d{4})", text)
    if m:
        return datetime.datetime.strptime(m.group(1), "%B %d, %Y").date().isoformat()
    die("could not determine date from filename or header")


def clean_label(raw):
    """'SEGMENT ONE — MARKET OVERVIEW' -> 'Market Overview'; 'COLD OPEN' -> 'Cold Open'."""
    s = raw.strip()
    if "—" in s:
        s = s.split("—", 1)[1].strip()
    elif " - " in s:
        s = s.split(" - ", 1)[1].strip()
    return s.title()


def parse_segments(text):
    segments, cur = [], None
    for line in text.splitlines():
        h = re.match(r"^##\s+(.*\S)\s*$", line)
        if h:
            cur = {"raw": h.group(1), "label": clean_label(h.group(1)), "turns": []}
            segments.append(cur)
            continue
        t = re.match(r"^\s*(ALEX|SAM)\s*:\s*(.+?)\s*$", line)
        if t and cur is not None:
            cur["turns"].append({"speaker": t.group(1), "text": t.group(2)})
    # drop header-only segments (no spoken turns)
    return [s for s in segments if s["turns"]]


def estimate_timings(segments, duration_sec):
    total = sum(len(t["text"]) for s in segments for t in s["turns"]) or 1
    elapsed = 0
    for s in segments:
        s["startSec"] = round(elapsed / total * duration_sec, 1)
        elapsed += sum(len(t["text"]) for t in s["turns"])
    return segments


def main():
    if len(sys.argv) < 2:
        die("usage: build_episode.py <script.md> [audio.mp3] [vocab.json]")
    script_path = sys.argv[1]
    audio_path = sys.argv[2] if len(sys.argv) > 2 else None
    vocab_path = sys.argv[3] if len(sys.argv) > 3 else None
    if not os.path.isfile(script_path):
        die(f"script not found: {script_path}")

    text = open(script_path, encoding="utf-8").read()
    date = find_date(script_path, text)
    out = os.path.join(EPDIR, date)
    os.makedirs(out, exist_ok=True)

    # title + day from the "### Weekday, Month DD, YYYY" header if present
    title, day = date, ""
    m = re.search(r"^###\s+(.+)$", text, re.M)
    if m:
        title = m.group(1).strip()
        day = title.split(",")[0].strip()

    # audio + duration. `audio` in episode.json is either:
    #   - a full URL (audio lives on R2/CDN, MP3 stays out of git) — the path for the
    #     daily routine: set AUDIO_BASE_URL and upload via tools/upload_audio.py, or
    #   - a bare "audio.mp3" filename copied into data/episodes/<date>/ (legacy, no bucket).
    # Duration is estimated from the local file's size when available (Gemini-TTS gives
    # no timings); pass the just-rendered MP3 even when uploading to R2.
    audio_ref, duration = None, 0
    base = os.environ.get("AUDIO_BASE_URL", "").rstrip("/")
    local_copy = os.path.join(out, "audio.mp3")
    if audio_path and re.match(r"^https?://", audio_path):
        audio_ref = audio_path                                   # explicit URL passed in
        duration = int(os.environ.get("AUDIO_DURATION_SEC") or 0)
    elif audio_path and os.path.isfile(audio_path):
        duration = int(os.path.getsize(audio_path) * 8 / MP3_BITRATE)
        if base:
            audio_ref = f"{base}/{date}.mp3"                     # served from the bucket
        else:
            audio_ref = "audio.mp3"                              # legacy: keep it in git
            shutil.copyfile(audio_path, local_copy)
    elif os.path.isfile(local_copy):
        audio_ref = "audio.mp3"                                  # legacy copy already present
        duration = int(os.path.getsize(local_copy) * 8 / MP3_BITRATE)
    elif base:
        audio_ref = f"{base}/{date}.mp3"                         # URL only (uploaded elsewhere)

    segments = estimate_timings(parse_segments(text), duration or 1)

    episode = {
        "date": date, "title": title, "day": day,
        "audio": audio_ref, "durationSec": duration,
        "segments": segments,
    }
    json.dump(episode, open(os.path.join(out, "episode.json"), "w"),
              ensure_ascii=False, indent=2)

    # vocab
    vcount = 0
    if vocab_path and os.path.isfile(vocab_path):
        shutil.copyfile(vocab_path, os.path.join(out, "vocab.json"))
    if os.path.isfile(os.path.join(out, "vocab.json")):
        try:
            vcount = len(json.load(open(os.path.join(out, "vocab.json")))["cards"])
        except Exception:
            vcount = 0

    # digest (compact dedup memory): the routine writes routine/digest-<date>.json
    # with throughline/stories/explainers; we keep a copy alongside the episode so
    # the history ledger is rebuilt from durable, per-episode files.
    digest_src = os.path.join(ROOT, "routine", f"digest-{date}.json")
    if os.path.isfile(digest_src):
        shutil.copyfile(digest_src, os.path.join(out, "digest.json"))

    rebuild_index()
    rebuild_history()
    print(f"OK  {date}: {len(segments)} segments, {duration//60}m audio, {vcount} vocab cards")


def rebuild_index():
    """Rebuild data/index.json (the archive list) and data/search.json (a flat,
    client-searchable text doc per episode: transcript + vocab)."""
    eps, search = [], []
    for d in sorted(os.listdir(EPDIR), reverse=True):
        ep_json = os.path.join(EPDIR, d, "episode.json")
        if not os.path.isfile(ep_json):
            continue
        e = json.load(open(ep_json))
        v = os.path.join(EPDIR, d, "vocab.json")
        cards = []
        if os.path.isfile(v):
            try: cards = json.load(open(v))["cards"]
            except Exception: cards = []
        eps.append({
            "date": e["date"], "title": e.get("title", e["date"]),
            "day": e.get("day", ""), "durationSec": e.get("durationSec", 0),
            "hasAudio": bool(e.get("audio")), "vocabCount": len(cards),
            "segmentCount": len(e.get("segments", [])),
        })
        # one searchable text blob per episode: segment labels + every spoken
        # turn + vocab words/meanings, so a substring search covers the archive.
        parts = [e.get("title", "")]
        for sg in e.get("segments", []):
            parts.append(sg.get("label", ""))
            parts += [t.get("text", "") for t in sg.get("turns", [])]
        for c in cards:
            parts += [c.get("word", ""), c.get("meaning", ""), c.get("tiesTo", "")]
        search.append({
            "date": e["date"], "title": e.get("title", e["date"]),
            "day": e.get("day", ""),
            "text": " ".join(p for p in parts if p),
        })
    json.dump({"title": "The Morning Commute", "episodes": eps},
              open(os.path.join(DATA, "index.json"), "w"),
              ensure_ascii=False, indent=2)
    json.dump({"docs": search},
              open(os.path.join(DATA, "search.json"), "w"),
              ensure_ascii=False, indent=2)


def rebuild_history():
    """Rebuild data/history.jsonl — the routine's compact memory of what every prior
    show covered, one JSON line per episode (oldest→newest). It exists so the daily
    routine can avoid repeating stories, re-explaining concepts, or reusing vocab
    WITHOUT loading full prior scripts into context: it reads the tail of this file
    instead. Each line is derived from that episode's digest.json (model-authored:
    throughline + story slugs + explainers) plus the vocab words pulled from
    vocab.json. Rebuilt from scratch every run, so it's idempotent and self-healing."""
    lines = []
    for d in sorted(os.listdir(EPDIR)):
        ep_json = os.path.join(EPDIR, d, "episode.json")
        if not os.path.isfile(ep_json):
            continue
        e = json.load(open(ep_json))
        digest = {}
        dg = os.path.join(EPDIR, d, "digest.json")
        if os.path.isfile(dg):
            try: digest = json.load(open(dg))
            except Exception: digest = {}
        words = []
        v = os.path.join(EPDIR, d, "vocab.json")
        if os.path.isfile(v):
            try: words = [c.get("word", "") for c in json.load(open(v)).get("cards", []) if c.get("word")]
            except Exception: words = []
        lines.append(json.dumps({
            "date": e["date"],
            "throughline": digest.get("throughline", ""),
            "stories": digest.get("stories", []),
            "explainers": digest.get("explainers", []),
            "vocab": words,
        }, ensure_ascii=False))
    with open(os.path.join(DATA, "history.jsonl"), "w") as f:
        f.write("\n".join(lines) + ("\n" if lines else ""))


if __name__ == "__main__":
    main()

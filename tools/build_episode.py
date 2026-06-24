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
  - copies audio.mp3 and vocab.json into data/episodes/<date>/
  - rebuilds data/index.json (newest first)

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

    # audio + duration
    audio_name, duration = None, 0
    if audio_path and os.path.isfile(audio_path):
        audio_name = "audio.mp3"
        shutil.copyfile(audio_path, os.path.join(out, audio_name))
        duration = int(os.path.getsize(audio_path) * 8 / MP3_BITRATE)
    elif os.path.isfile(os.path.join(out, "audio.mp3")):
        audio_name = "audio.mp3"
        duration = int(os.path.getsize(os.path.join(out, "audio.mp3")) * 8 / MP3_BITRATE)

    segments = estimate_timings(parse_segments(text), duration or 1)

    episode = {
        "date": date, "title": title, "day": day,
        "audio": audio_name, "durationSec": duration,
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

    rebuild_index()
    print(f"OK  {date}: {len(segments)} segments, {duration//60}m audio, {vcount} vocab cards")


def rebuild_index():
    eps = []
    for d in sorted(os.listdir(EPDIR), reverse=True):
        ep_json = os.path.join(EPDIR, d, "episode.json")
        if not os.path.isfile(ep_json):
            continue
        e = json.load(open(ep_json))
        v = os.path.join(EPDIR, d, "vocab.json")
        vcount = 0
        if os.path.isfile(v):
            try: vcount = len(json.load(open(v))["cards"])
            except Exception: vcount = 0
        eps.append({
            "date": e["date"], "title": e.get("title", e["date"]),
            "day": e.get("day", ""), "durationSec": e.get("durationSec", 0),
            "hasAudio": bool(e.get("audio")), "vocabCount": vcount,
            "segmentCount": len(e.get("segments", [])),
        })
    json.dump({"title": "The Morning Commute", "episodes": eps},
              open(os.path.join(DATA, "index.json"), "w"),
              ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()

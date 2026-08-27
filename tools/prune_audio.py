#!/usr/bin/env python3
"""
prune_audio.py — rolling audio retention: delete episode MP3s older than
RETAIN_AUDIO_DAYS (default 14) from R2 and mark those episodes script-only.

The show's philosophy is "text forever, audio is big": scripts, transcripts,
vocab, and search stay in git indefinitely, but a commute podcast's audio has a
~2-week shelf life. This pass keeps the R2 bucket a small rolling window instead
of an ever-growing archive. For each pruned date it:
  1. deletes r2://<bucket>/<date>.mp3 (idempotent — a missing key is fine), and
  2. sets "audio": null in data/episodes/<date>/episode.json — the app already
     degrades to "script only" for a null audio field, and the next
     build_episode.py run flips the episode's hasAudio in data/index.json.

Runs automatically from tools/daily.sh (before the build, so the day's single
commit carries the metadata change). Safe by construction: it only nulls an
episode's audio AFTER the R2 delete succeeds, it never touches scripts or any
other episode data, and daily.sh treats a failure here as a warning, never a
blocked publish. Episodes saved for offline in the app keep playing from the
device cache regardless.

Usage:
    tools/prune_audio.py [--dry-run]

Env:
    RETAIN_AUDIO_DAYS   default 14 — delete audio for dates strictly older
    R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET
                        required to delete (without them the pass is skipped
                        with a note — dev clones shouldn't fail the publish)
"""
import datetime, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
EPDIR = os.path.join(ROOT, "data", "episodes")


def main():
    dry = "--dry-run" in sys.argv
    days = int(os.environ.get("RETAIN_AUDIO_DAYS", "14"))
    cutoff = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()

    # candidates: episode dirs strictly older than the cutoff that still point
    # at audio (ISO dates compare correctly as strings)
    candidates = []
    for d in sorted(os.listdir(EPDIR) if os.path.isdir(EPDIR) else []):
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", d) or d >= cutoff:
            continue
        p = os.path.join(EPDIR, d, "episode.json")
        try:
            e = json.load(open(p, encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if e.get("audio"):
            candidates.append((d, p, e))

    print(f"audio retention: keep {days} days (cutoff {cutoff}) — "
          f"{len(candidates)} episode(s) to prune")
    if not candidates:
        return
    if dry:
        for d, _, e in candidates:
            print(f"  would prune {d}  ({e['audio']})")
        return

    need = ["R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET"]
    missing = [k for k in need if not os.environ.get(k)]
    if missing:
        print(f"  R2 env not configured ({', '.join(missing)} missing) — "
              f"skipping retention pass (nothing deleted, nothing marked)")
        return

    import boto3
    s3 = boto3.client(
        "s3",
        endpoint_url=f"https://{os.environ['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )
    bucket = os.environ["R2_BUCKET"]

    pruned = 0
    for d, p, e in candidates:
        audio = e["audio"]
        try:
            if re.match(r"^https?://", audio):
                # R2 mode: object key is <date>.mp3; delete_object succeeds
                # whether or not the key still exists (idempotent re-runs)
                s3.delete_object(Bucket=bucket, Key=f"{d}.mp3")
            else:
                # legacy dev mode: MP3 committed next to episode.json
                local = os.path.join(EPDIR, d, audio)
                if os.path.isfile(local):
                    os.remove(local)
        except Exception as err:
            print(f"  ⚠ {d}: delete failed ({err}) — leaving audio reference in place")
            continue
        e["audio"] = None
        json.dump(e, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        pruned += 1
        print(f"  pruned {d} — audio deleted, episode marked script-only")

    if pruned:
        print(f"✓ pruned {pruned} episode(s); run build_episode.py / daily.sh to "
              f"refresh hasAudio in data/index.json")


if __name__ == "__main__":
    main()

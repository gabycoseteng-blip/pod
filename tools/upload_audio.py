#!/usr/bin/env python3
"""
upload_audio.py — upload an episode's MP3 to Cloudflare R2 (S3-compatible) so
audio lives in the bucket/CDN and only its URL is stored in git.

Usage:
    python3 tools/upload_audio.py <audio.mp3> [YYYY-MM-DD]

The object key is "<date>.mp3" — date from the 2nd arg, else parsed from the
filename, else today. Pair this with build_episode.py (set AUDIO_BASE_URL to the
same public base) so episode.json points at "<AUDIO_BASE_URL>/<date>.mp3".

Required env:
    R2_ACCOUNT_ID          Cloudflare account id
    R2_ACCESS_KEY_ID       R2 API token access key id
    R2_SECRET_ACCESS_KEY   R2 API token secret
    R2_BUCKET              bucket name
Optional env:
    AUDIO_BASE_URL         public base; if set, the final URL is printed

Needs boto3:  pip install boto3   (or: pip install -r tools/requirements.txt)
"""
import os, re, sys, datetime


def die(m):
    print(f"ERROR: {m}", file=sys.stderr); sys.exit(1)


def main():
    if len(sys.argv) < 2:
        die("usage: upload_audio.py <audio.mp3> [YYYY-MM-DD]")
    path = sys.argv[1]
    if not os.path.isfile(path):
        die(f"file not found: {path}")

    date = sys.argv[2] if len(sys.argv) > 2 else None
    if not date:
        m = re.search(r"(\d{4}-\d{2}-\d{2})", os.path.basename(path))
        date = m.group(1) if m else datetime.date.today().isoformat()

    need = ["R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET"]
    miss = [k for k in need if not os.environ.get(k)]
    if miss:
        die("missing env var(s): " + ", ".join(miss))

    try:
        import boto3
    except ImportError:
        die("boto3 not installed — run: pip install boto3")

    s3 = boto3.client(
        "s3",
        endpoint_url=f"https://{os.environ['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )
    bucket, key = os.environ["R2_BUCKET"], f"{date}.mp3"
    s3.upload_file(path, bucket, key, ExtraArgs={"ContentType": "audio/mpeg"})
    print(f"OK  uploaded {key} -> r2://{bucket}")
    base = os.environ.get("AUDIO_BASE_URL", "").rstrip("/")
    if base:
        print(f"URL {base}/{key}")


if __name__ == "__main__":
    main()

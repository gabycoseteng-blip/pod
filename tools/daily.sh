#!/usr/bin/env bash
#
# daily.sh — one invocation to publish a day's episode:
#   audio → R2, build episode + index + search, archive the script, commit, deploy.
#
# Usage:
#   tools/daily.sh <script.md> [audio.mp3] [vocab.json]
#
# Env (audio in R2 — see README "Audio storage"):
#   AUDIO_BASE_URL, R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET
# Without AUDIO_BASE_URL it falls back to keeping the MP3 in git (dev mode).
#
# Set NO_PUSH=1 to build + commit but not push (e.g. to review first).
set -euo pipefail

cd "$(dirname "$0")/.."

script="${1:?usage: tools/daily.sh <script.md> [audio.mp3] [vocab.json]}"
audio="${2:-}"
vocab="${3:-}"
[ -f "$script" ] || { echo "ERROR: script not found: $script" >&2; exit 1; }

date="$(grep -oE '[0-9]{4}-[0-9]{2}-[0-9]{2}' <<<"$(basename "$script")" | head -1 || true)"
[ -n "$date" ] || { echo "ERROR: no YYYY-MM-DD in script filename: $script" >&2; exit 1; }

# 1. audio → R2 (only when a bucket is configured and a file was passed)
if [ -n "$audio" ] && [ -n "${AUDIO_BASE_URL:-}" ]; then
  echo "→ uploading audio to R2…"
  python3 tools/upload_audio.py "$audio" "$date"
fi

# 2. build episode.json + index.json + search.json (records the R2 URL, no copy)
echo "→ building episode $date…"
python3 tools/build_episode.py "$script" ${audio:+"$audio"} ${vocab:+"$vocab"}

# 3. archive the script as plain text (the durable, greppable history)
mkdir -p scripts
cp "$script" "scripts/$date.md"

# 4. commit the text + deploy
git add scripts data
if git diff --cached --quiet; then
  echo "nothing changed for $date — skipping commit"; exit 0
fi
git commit -m "Episode $date"
if [ -n "${NO_PUSH:-}" ]; then
  echo "✓ committed (NO_PUSH set — not pushing)"; exit 0
fi
git push
echo "✓ episode $date published — deploy will pick it up from the push."

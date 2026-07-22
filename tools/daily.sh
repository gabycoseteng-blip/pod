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

# 0. dedup backstop — refuse to publish if a vocab word was already taught.
#    The routine should also run this BEFORE rendering; this is the last line of
#    defense so a reused word can't reach the deploy. Bypass with DEDUP_OVERRIDE=1.
if [ -n "$vocab" ] && [ -f tools/check_dedup.py ]; then
  python3 tools/check_dedup.py "$vocab" "routine/digest-$date.json" || exit 1
fi

# 1. audio → R2 (only when a bucket is configured and a file was passed)
if [ -n "$audio" ] && [ -n "${AUDIO_BASE_URL:-}" ]; then
  echo "→ uploading audio to R2…"
  python3 tools/upload_audio.py "$audio" "$date"
fi

# 2. build episode.json + index.json + search.json (records the R2 URL, no copy)
echo "→ building episode $date…"
python3 tools/build_episode.py "$script" ${audio:+"$audio"} ${vocab:+"$vocab"}

# 2b. guardrail — refuse to deploy a malformed or too-short episode.
#     Publish a deliberate partial with ALLOW_SHORT=1.
if [ -f tools/check_episode.py ]; then
  python3 tools/check_episode.py "$date" || {
    echo "   (episode failed the guardrail — fix it, or set ALLOW_SHORT=1 for a partial.)" >&2
    exit 1; }
fi

# 2c. scorecard — grade the episode against the quality + efficiency GOALS and record
#     one line to data/run_metrics.jsonl for trend tracking (tools/run_retro.py).
#     TELEMETRY ONLY: never blocks the publish (the gates above already did that).
if [ -f tools/episode_scorecard.py ]; then
  python3 tools/episode_scorecard.py "$date" || true
fi

# 3. make sure the script is committed as plain text (the durable, greppable
#    history). If it already lives in the repo (e.g. routine/…), stage it in
#    place; otherwise archive a copy under scripts/.
script_abs="$(cd "$(dirname "$script")" && pwd)/$(basename "$script")"
case "$script_abs" in
  "$PWD"/*) git add "$script_abs" ;;
  *) mkdir -p scripts; cp "$script" "scripts/$date.md"; git add "scripts/$date.md" ;;
esac

# 4. commit the text (+ routine working files) and deploy. Audio is never
#    committed in R2 mode — only data/ JSON and the script change.
git add data
[ -d routine ] && git add routine
if git diff --cached --quiet; then
  # Nothing new to commit — but a prior run may have committed without pushing,
  # so don't exit here; fall through and let the push logic settle any owed push.
  echo "nothing new to commit for $date — checking whether a push is still owed…"
else
  git commit -m "Episode $date"
fi
if [ -n "${NO_PUSH:-}" ]; then
  echo "✓ committed (NO_PUSH set — not pushing)"; exit 0
fi

# 5. deploy push — resilient to a moving remote. A bare `git push` fails
#    non-fast-forward the instant the remote advances (a concurrent daily run,
#    or any other commit), and the deploy silently doesn't happen. Instead:
#    fetch → rebase our commit onto the latest remote → push, retrying with
#    backoff. If today's episode is ALREADY on the remote (a parallel run beat
#    us, or this is a re-run), treat it as done — an idempotent no-op, not a
#    failure — so we never clobber a valid published episode.
branch="$(git rev-parse --abbrev-ref HEAD)"

# Refuse to publish from the wrong branch: the deploy only works from the
# production branch, and a silent wrong-branch push is exactly how 2026-07-15
# went to a non-deploy branch. Override DEPLOY_BRANCH if production differs.
DEPLOY_BRANCH="${DEPLOY_BRANCH:-main}"
if [ "$branch" != "$DEPLOY_BRANCH" ]; then
  echo "ERROR: on branch '$branch', not the deploy branch '$DEPLOY_BRANCH' — refusing to push." >&2
  echo "       Checkout $DEPLOY_BRANCH (or set DEPLOY_BRANCH='$branch' if intentional) and re-run." >&2
  exit 1
fi

remote_has_date() {  # 0 if origin/$branch's index.json already lists $date
  git show "origin/$branch:data/index.json" 2>/dev/null | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(1)
sys.exit(0 if any(e.get("date") == sys.argv[1] for e in d.get("episodes", [])) else 1)
' "$date"
}

result=""
for attempt in 1 2 3 4 5; do
  if ! git fetch origin "$branch" 2>/dev/null; then
    echo "  fetch failed (attempt $attempt/5) — retrying…"; sleep "$((2 ** attempt))"; continue
  fi
  if remote_has_date; then
    echo "✓ episode $date already published upstream — nothing to do (idempotent no-op)."
    git reset --hard "origin/$branch" >/dev/null 2>&1
    result="skip"; break
  fi
  if ! git rebase "origin/$branch" >/dev/null 2>&1; then
    git rebase --abort >/dev/null 2>&1 || true
    git fetch origin "$branch" 2>/dev/null || true
    if remote_has_date; then
      echo "✓ episode $date landed upstream while we built — leaving it in place (no-op)."
      git reset --hard "origin/$branch" >/dev/null 2>&1; result="skip"; break
    fi
    echo "ERROR: rebase onto origin/$branch conflicted unexpectedly — resolve manually." >&2
    exit 1
  fi
  if git push origin "HEAD:$branch" 2>/dev/null; then result="ok"; break; fi
  echo "  push rejected (attempt $attempt/5) — remote moved; re-syncing…"; sleep "$((2 ** attempt))"
done

if [ "$result" = ok ]; then
  echo "✓ episode $date published — deploy will pick it up from the push."
elif [ "$result" = skip ]; then
  :  # already published — success
else
  echo "ERROR: could not push $date after 5 attempts (remote kept moving or network down)." >&2
  exit 1
fi

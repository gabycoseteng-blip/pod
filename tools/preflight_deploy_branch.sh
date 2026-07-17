#!/usr/bin/env bash
#
# preflight_deploy_branch.sh — SessionStart guard against running a STALE playbook.
#
# The daily routine's worst failure mode isn't in the code — it's bootstrap: a
# session starts on a feature branch (e.g. claude/…) whose copy of the command
# file + ledger is behind the deploy branch, and the routine happily runs the old
# playbook. That is exactly how 2026-07-17 deduped against a June-only ledger,
# surfaced a week of already-aired stories, and paid for a second research pass
# and a full rewrite. Step 0 of the command tries to fix this — but step 0 lives
# INSIDE the very file that's stale, so it can't save a run that never reads it.
#
# This runs from SessionStart (see .claude/settings.json), i.e. BEFORE any command
# file is read, and shouts if the working tree's morning-commute playbook differs
# from the deploy branch's. Warn-only (never exits non-zero): it must not block
# unrelated sessions or offline work — it just makes the staleness impossible to
# miss so the agent re-syncs before burning tokens.
#
# Env:
#   DEPLOY_BRANCH   deploy/production branch to compare against (default: main)
set -u

CMD=".claude/commands/morning-commute.md"
# Only relevant in this repo; stay silent everywhere else.
[ -f "$CMD" ] || exit 0
command -v git >/dev/null 2>&1 || exit 0
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || exit 0

DEPLOY_BRANCH="${DEPLOY_BRANCH:-main}"
branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo '?')"

# Best-effort fetch; if the network's down we simply can't compare — stay quiet.
git fetch --quiet origin "$DEPLOY_BRANCH" 2>/dev/null || exit 0

remote_cmd="$(git show "origin/${DEPLOY_BRANCH}:${CMD}" 2>/dev/null)"
[ -n "$remote_cmd" ] || exit 0
local_cmd="$(cat "$CMD" 2>/dev/null)"

stale_playbook=false
[ "$local_cmd" != "$remote_cmd" ] && stale_playbook=true

# Is the deploy branch itself ahead of us? (ledger + tools may be stale too.)
behind="$(git rev-list --count "HEAD..origin/${DEPLOY_BRANCH}" 2>/dev/null || echo 0)"

if [ "$stale_playbook" = true ] || { [ "$branch" != "$DEPLOY_BRANCH" ] && [ "${behind:-0}" -gt 0 ]; }; then
  cat >&2 <<EOF

⚠️  STALE MORNING-COMMUTE PLAYBOOK DETECTED
    You are on branch '$branch'; the deploy branch is 'origin/$DEPLOY_BRANCH'
    ($behind commit(s) ahead$([ "$stale_playbook" = true ] && echo "; the command file differs")).
    The command file AND data/history.jsonl on this branch may be OUT OF DATE —
    running /morning-commute now risks re-deduping against a stale ledger and
    repeating already-aired stories/vocab (a costly re-research + rewrite).

    Before running the routine:
        git fetch origin --prune && git checkout $DEPLOY_BRANCH && git pull --rebase origin $DEPLOY_BRANCH
    then re-open /morning-commute so you execute the CURRENT playbook + ledger.

EOF
fi

exit 0

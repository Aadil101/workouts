#!/bin/sh
# The whole weekly loop: pull, file any new export, plan, commit, push.
#
# Safe to run whenever - twice in a day, or a week with no new export. Ingest
# finding nothing is a normal week and not an error, and a plan with no new
# history is simply the same plan again.
set -eu

ROOT=$(cd "$(dirname "$0")" && pwd)

# Update the planner itself first, then restart on the new copy - otherwise a
# change to the code only reaches this machine after someone remembers to pull.
# Fast-forward only: this checkout is for running, never for editing.
if [ -z "${WEEKLY_UPDATED:-}" ] && [ -d "$ROOT/.git" ]; then
    git -C "$ROOT" pull --quiet --ff-only || echo "! could not update the planner - running the copy you have" >&2
    WEEKLY_UPDATED=1 exec sh "$0" "$@"
fi
PY=$(command -v python3 || command -v python || true)
[ -n "$PY" ] || { echo "no python3 on PATH - try: xcode-select --install" >&2; exit 1; }
DATA=${WORKOUTS_DATA:-$(cd "$ROOT/.." && pwd)/workouts-data}

# Easy to miss otherwise: the plan still lands in the data repo, so the run looks
# fine while the phone quietly keeps reading last week's.
[ -n "${WORKOUTS_SYNC:-}" ] || echo "! WORKOUTS_SYNC is unset - the plan will not reach your phone" >&2

if [ -d "$DATA/.git" ]; then
    git -C "$DATA" pull --quiet --rebase || echo "! pull failed - carrying on with local data"
fi

# Exits non-zero when the sync folder holds no export, which is most days.
"$PY" "$ROOT/ingest.py" || true

"$PY" "$ROOT/plan.py"

if [ -d "$DATA/.git" ] && [ -n "$(git -C "$DATA" status --porcelain)" ]; then
    git -C "$DATA" add -A
    git -C "$DATA" commit -q -m "week of $(date +%F)"
    git -C "$DATA" push -q || echo "! push failed - the plan is written, the commit is local"
fi

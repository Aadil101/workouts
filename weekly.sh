#!/bin/sh
# The whole weekly loop: pull, file any new export, plan, commit, push.
#
# Safe to run whenever - twice in a day, or a week with no new export. Ingest
# finding nothing is a normal week and not an error, and a plan with no new
# history is simply the same plan again.
set -eu

ROOT=$(cd "$(dirname "$0")" && pwd)
PY=$(command -v python3 || command -v python || true)
[ -n "$PY" ] || { echo "no python3 on PATH - try: xcode-select --install" >&2; exit 1; }
DATA=${WORKOUTS_DATA:-$(cd "$ROOT/.." && pwd)/workouts-data}

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

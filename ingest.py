"""File a Hevy export under exports/, named from its own contents."""
import csv, os, shutil, sys, datetime as dt
import workouts as w

src = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/Downloads/workout_data.csv")
with open(src, newline="", encoding="utf-8-sig") as f:
    rows = list(csv.DictReader(f))
if not rows:
    sys.exit(f"{src} has no rows")
stamp = max(dt.datetime.strptime(r["start_time"], "%d %b %Y, %H:%M") for r in rows).date()
dest = os.path.join(w.DATA, "exports", f"{stamp}.csv")
shutil.copy(src, dest)
print(f"{len(rows)} sets, latest {stamp} -> {os.path.relpath(dest)}")

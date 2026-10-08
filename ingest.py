"""Merge Hevy exports into history.csv, the one file the planner reads.

Scans the sync folder (WORKOUTS_SYNC) when given no arguments: iOS never
overwrites, so saving from Hevy repeatedly leaves workout_data.csv,
workout_data 2.csv, and so on. Consumed files are deleted; re-ingesting the
same export is harmless because merging it again changes nothing.

The raw export is also kept as latest-export.csv, overwritten each time, so
git history holds every dump while the disk holds one.
"""
import csv, os, shutil, sys, datetime as dt
import workouts as w

HEADER = {"start_time", "exercise_title", "set_index"}
LATEST = os.path.join(w.DATA, "latest-export.csv")


def when(row):
    return dt.datetime.strptime(row["start_time"], "%d %b %Y, %H:%M")


def key(row):
    return row["start_time"], row["exercise_title"], row["set_index"]


def read(path):
    """(fieldnames, rows) of a Hevy export, or None if it isn't one."""
    try:
        with open(path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        if not rows or not HEADER <= set(reader.fieldnames):
            return None
        for r in rows:
            when(r)
    except (OSError, UnicodeDecodeError, csv.Error, ValueError):
        return None
    return reader.fieldnames, rows


def merge(old, new):
    """History after taking in an export, plus a report of what moved.

    The export is trusted inside its own date range, so edits and deletions
    made in Hevy land here. History outside that range is kept: if Hevy ever
    trims exports to a rolling window, what fell out of it stays put instead
    of vanishing. Rows after the range survive an older export filed late.
    """
    lo, hi = min(map(when, new)), max(map(when, new))
    kept = [r for r in old if not lo <= when(r) <= hi]
    before = {key(r): r for r in old if lo <= when(r) <= hi}
    after = {key(r): r for r in new}
    report = {
        "added": [k for k in after if k not in before],
        "changed": [k for k in after if k in before and after[k] != before[k]],
        "removed": [k for k in before if k not in after],
        "older": sum(when(r) < lo for r in kept),
        "range": (lo, hi),
    }
    # Stable sort: a session's rows all come from one side, in Hevy's order.
    return sorted(kept + new, key=when), report


def ingest(path, export, consume=False):
    fields, rows = export
    if os.path.exists(w.HISTORY):
        hist = read(w.HISTORY)
        if not hist:
            # Never overwrite a history we failed to read - it is the only full copy.
            sys.exit(f"cannot read {w.HISTORY} - fix it or restore it from git first")
        old_fields, old = hist
    else:
        old_fields, old = fields, []
    merged, rep = merge(old, rows)
    fields = fields + [f for f in old_fields if f not in fields]
    tmp = w.HISTORY + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        out = csv.DictWriter(f, fields)
        out.writeheader()
        out.writerows(merged)
    os.replace(tmp, w.HISTORY)
    if not (os.path.exists(LATEST) and os.path.samefile(path, LATEST)):
        shutil.copy(path, LATEST)
    if consume:
        os.remove(path)

    lo, hi = rep["range"]
    alarm = "! " if rep["removed"] or rep["older"] else ""
    # First line is the verdict: the Dock app's notification shows only that.
    print(f"{alarm}{len(rows)} sets, latest {hi.date()}: {len(rep['added'])} new, "
          f"{len(rep['changed'])} changed, {len(rep['removed'])} removed"
          + (" (consumed)" if consume else ""))
    for start, exercise in dict.fromkeys(k[:2] for k in rep["removed"]):
        print(f"  removed {start}  {exercise} - deleted in Hevy?")
    if rep["older"]:
        print(f"  export starts {lo.date()} but history goes back further: kept {rep['older']} "
              f"sets it no longer contains - Hevy may have started trimming exports")


def main(argv):
    if argv:
        paths, consume = argv[:1], False
    elif not w.SYNC:
        sys.exit("pass an export path, or set WORKOUTS_SYNC to a folder to scan")
    else:
        paths = [os.path.join(w.SYNC, f) for f in sorted(os.listdir(w.SYNC)) if f.lower().endswith(".csv")]
        consume = True
        if not paths:
            sys.exit(f"no CSVs in {w.SYNC}")
    exports = []
    for p in paths:
        got = read(p)
        if got:
            exports.append((p, got))
        else:
            print(f"skipped {os.path.basename(p)} - not a Hevy export")
    if not exports:
        sys.exit("nothing ingested")
    # Oldest first: "workout_data 2.csv" sorts before "workout_data.csv" but is newer.
    exports.sort(key=lambda e: max(map(when, e[1][1])))
    for p, got in exports:
        ingest(p, got, consume)


if __name__ == "__main__":
    main(sys.argv[1:])

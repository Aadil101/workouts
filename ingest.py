"""File Hevy exports under exports/, each named from its own contents.

Scans the sync folder (WORKOUTS_SYNC) when given no arguments: iOS never
overwrites, so saving from Hevy repeatedly leaves workout_data.csv,
workout_data 2.csv, and so on. Consumed files are deleted; re-ingesting the
same export is harmless because the destination name comes from the data.
"""
import csv, os, shutil, sys, datetime as dt
import workouts as w

HEADER = {"start_time", "exercise_title", "set_index"}


def export_date(path):
    """Latest session date in a Hevy export, or None if it isn't one."""
    try:
        with open(path, newline="", encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
    except (OSError, UnicodeDecodeError, csv.Error):
        return None
    if not rows or not HEADER <= set(rows[0]):
        return None
    try:
        return len(rows), max(dt.datetime.strptime(r["start_time"], "%d %b %Y, %H:%M")
                              for r in rows).date()
    except ValueError:
        return None


def ingest(path, consume=False):
    found = export_date(path)
    if not found:
        print(f"skipped {os.path.basename(path)} - not a Hevy export")
        return False
    n, stamp = found
    dest = os.path.join(w.DATA, "exports", f"{stamp}.csv")
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    shutil.copy(path, dest)
    if consume:
        os.remove(path)
    print(f"{n} sets, latest {stamp} -> exports/{stamp}.csv" + (" (consumed)" if consume else ""))
    return True


def main(argv):
    if argv:
        sys.exit(0 if ingest(argv[0]) else 1)
    if not w.SYNC:
        sys.exit("pass an export path, or set WORKOUTS_SYNC to a folder to scan")
    files = sorted(f for f in os.listdir(w.SYNC) if f.lower().endswith(".csv"))
    if not files:
        sys.exit(f"no CSVs in {w.SYNC}")
    if not sum(ingest(os.path.join(w.SYNC, f), consume=True) for f in files):
        sys.exit("nothing ingested")


if __name__ == "__main__":
    main(sys.argv[1:])

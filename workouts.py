"""Shared loading for Hevy exports and the exercise table."""
import csv, glob, os, datetime as dt
from collections import namedtuple

ROOT = os.path.dirname(os.path.abspath(__file__))
# Exports and plans live outside this repo: they carry timestamped session data.
SYNC = os.environ.get("WORKOUTS_SYNC")
DATA = os.path.normpath(os.environ.get("WORKOUTS_DATA") or os.path.join(ROOT, os.pardir, "workouts-data"))
Set = namedtuple("Set", "date venue exercise set_index weight reps duration")
Ex = namedtuple("Ex", "category venue primary secondary active")


def load_limits(path=None):
    """(exercise, venue) -> heaviest load available there. Optional; may be empty.

    Lives in the data repo rather than next to exercises.csv for two reasons.
    It is equipment, so it is nobody else's business what your rack holds, and
    it is the one thing about a setup that cannot be inferred: a ceiling and a
    plateau look identical in the history. Columns: exercise,venue,max.
    """
    out = {}
    p = path or os.path.join(DATA, "limits.csv")
    if not os.path.exists(p):
        return out
    with open(p, newline="") as f:
        for r in csv.DictReader(f):
            out[(r["exercise"].strip(), r["venue"].strip())] = float(r["max"])
    return out


def load_exercises(path=None):
    """exercise title -> Ex. Anatomy is Hevy's; category/venue are ours."""
    out = {}
    with open(path or os.path.join(ROOT, "exercises.csv"), newline="") as f:
        for r in csv.DictReader(f):
            sec = [s.strip() for s in r["secondary"].split(",") if s.strip()]
            out[r["exercise"]] = Ex(r["category"], r["venue"], r["primary"].strip(), sec,
                                    r.get("active", "yes").strip().lower() != "no")
    return out


def load_history(exports_dir=None):
    """Union of every export, deduped. Overlapping dumps are the point:
    if Hevy's free export is a rolling window, the union is still complete."""
    seen, sets = set(), []
    for path in sorted(glob.glob(os.path.join(exports_dir or os.path.join(DATA, "exports"), "*.csv"))):
        with open(path, newline="", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                key = (r["start_time"], r["exercise_title"], r["set_index"])
                if key in seen:
                    continue
                seen.add(key)
                sets.append(Set(
                    dt.datetime.strptime(r["start_time"], "%d %b %Y, %H:%M"),
                    r["title"],
                    r["exercise_title"],
                    int(r["set_index"]),
                    float(r["weight_lbs"]) if r["weight_lbs"] else None,
                    int(r["reps"]) if r["reps"] else None,
                    # Bodyweight holds live here: a plank logs seconds and no
                    # weight at all, so dropping this column made every timed
                    # exercise look like it had never been done.
                    int(r["duration_seconds"]) if r.get("duration_seconds") else None,
                ))
    return sorted(sets, key=lambda s: (s.date, s.exercise, s.set_index))


def sessions(sets):
    """[(datetime, venue, [Set, ...]), ...] in chronological order."""
    out = {}
    for s in sets:
        out.setdefault((s.date, s.venue), []).append(s)
    return [(d, v, ss) for (d, v), ss in sorted(out.items())]


def muscle_load(sets, table, half=0.5):
    """muscle -> list of (date, weight) touches. Secondaries count half."""
    load = {}
    for s in sets:
        ex = table.get(s.exercise)
        if not ex:
            continue
        load.setdefault(ex.primary, []).append((s.date.date(), 1.0))
        for m in ex.secondary:
            load.setdefault(m, []).append((s.date.date(), half))
    return load

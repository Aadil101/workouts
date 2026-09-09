"""Read-only staleness report. Inspect the model before trusting a plan."""
import sys, datetime as dt
from collections import defaultdict
import workouts as w


def main(today=None):
    today = today or dt.date.today()
    table, hist = w.load_exercises(), w.load_history()
    if not hist:
        sys.exit("no exports found in exports/")
    sess = w.sessions(hist)
    print(f"as of {today} | {len(sess)} sessions, {hist[0].date.date()} -> {hist[-1].date.date()}\n")

    load = w.muscle_load(hist, table)
    print(f"{'MUSCLE':<12} {'last':>10} {'ago':>4} {'lastP':>4} {'7d':>5} {'14d':>5}")
    rows = []
    for m, touches in load.items():
        last = max(d for d, _ in touches)
        lastp = max((d for d, wt in touches if wt == 1.0), default=None)
        w7 = sum(wt for d, wt in touches if (today - d).days < 7)
        w14 = sum(wt for d, wt in touches if (today - d).days < 14)
        rows.append((( today - last).days, m, last, lastp, w7, w14))
    for ago, m, last, lastp, w7, w14 in sorted(rows, reverse=True):
        pa = f"{(today - lastp).days}" if lastp else "-"
        print(f"{m:<12} {str(last):>10} {ago:>4} {pa:>4} {w7:>5.1f} {w14:>5.1f}")
    print("  ago=days since any touch, lastP=since a primary hit, 7d/14d=weighted sets\n")

    print(f"{'EXERCISE':<36} {'cat':<5} {'last':>10} {'ago':>4} {'top':>6}  clean")
    per = defaultdict(list)
    for s in hist:
        per[s.exercise].append(s)
    for ex, ss in sorted(per.items(), key=lambda kv: (today - max(s.date.date() for s in kv[1])).days):
        last = max(s.date.date() for s in ss)
        lastsets = [s for s in ss if s.date.date() == last]
        top = max((s.weight for s in lastsets if s.weight is not None), default=None)
        clean = all(s.reps == 8 for s in lastsets if s.reps is not None) and len(lastsets) >= 3
        print(f"{ex:<36} {table[ex].category:<5} {str(last):>10} {(today-last).days:>4} "
              f"{(f'{top:.0f}' if top else '-'):>6}  {'yes' if clean else 'no'}")

    print("\nback-to-back primary-muscle collisions (<=1 day apart):")
    byday = defaultdict(set)
    for s in hist:
        if s.exercise in table:
            byday[s.date.date()].add(table[s.exercise].primary)
    days = sorted(byday)
    n = 0
    for a, b in zip(days, days[1:]):
        if (b - a).days <= 1 and (dup := byday[a] & byday[b]):
            n += 1
            if (today - b).days <= 30:
                print(f"  {a} -> {b}: {', '.join(sorted(dup))}")
    print(f"  {n} total across all history (last 30 days shown)")


if __name__ == "__main__":
    main(dt.date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else None)

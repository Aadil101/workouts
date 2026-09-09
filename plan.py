"""Weekly session plan. Deterministic: same history in, same plan out."""
import os, sys, datetime as dt
from collections import defaultdict
import workouts as w

FRESH_DAYS = 2          # under this many days since a primary hit -> flag it
GAP = 2                 # assumed days between sessions, for forward simulation
TAILDRIVE = os.path.expanduser("~/Documents/taildrive/workout-plan.md")

# Stable structure, rotating fill (Q19). Counts are slots, not exercises.
SHAPE = {"push": [("push", 4), ("legs", 1), ("core", 1)],
         "pull": [("pull", 4), ("legs", 1), ("core", 1)],
         "home": [("home", 4)]}


def last_weight(hist, ex):
    """Last top-set weight, whether that day was clean 3x8, and the prior weight."""
    days = defaultdict(list)
    for s in hist:
        if s.exercise == ex:
            days[s.date.date()].append(s)
    if not days:
        return None, False, None, None
    d = max(days)
    sets = days[d]
    top = max((s.weight for s in sets if s.weight is not None), default=None)
    clean = len(sets) >= 3 and all(s.reps == 8 for s in sets if s.reps is not None)
    prev = prevd = None
    for od in sorted(days, reverse=True)[1:]:
        ow = max((s.weight for s in days[od] if s.weight is not None), default=None)
        if ow is not None and top is not None and ow != top:
            prev, prevd = ow, od
            break
    return top, clean, prev, prevd


def pick(pool, n, on, last_hit, last_done, table):
    """Stalest primary muscle first; tie-break on the exercise itself."""
    chosen, used = [], set()
    for ex in sorted(pool, key=lambda e: (-(on - last_hit.get(table[e].primary, dt.date(2000, 1, 1))).days,
                                          -(on - last_done.get(e, dt.date(2000, 1, 1))).days, e)):
        if table[ex].primary in used:
            continue
        chosen.append(ex)
        used.add(table[ex].primary)
        if len(chosen) == n:
            break
    if len(chosen) < n:   # pool has fewer distinct primaries than slots
        for ex in sorted(pool, key=lambda e: -(on - last_done.get(e, dt.date(2000, 1, 1))).days):
            if ex not in chosen:
                chosen.append(ex)
            if len(chosen) == n:
                break
    return chosen


def main(today=None):
    today = today or dt.date.today()
    table, hist = w.load_exercises(), w.load_history()
    sess = w.sessions(hist)

    last_hit, last_done = {}, {}
    for s in hist:
        ex = table.get(s.exercise)
        if not ex:
            continue
        d = s.date.date()
        last_done[s.exercise] = max(last_done.get(s.exercise, d), d)
        for m in [ex.primary] + ex.secondary:
            last_hit[m] = max(last_hit.get(m, d), d)

    # Continue the push/pull alternation from the last actual gym session (Q31).
    prev = None
    for d, venue, ss in reversed(sess):
        cats = [table[s.exercise].category for s in ss if s.exercise in table]
        if venue != "My Home Workout" and ("push" in cats or "pull" in cats):
            prev = "push" if cats.count("push") >= cats.count("pull") else "pull"
            break
    nxt = "pull" if prev == "push" else "push"

    gym = {c: [e for e, x in table.items() if x.active and x.category == c and x.venue in ("gym", "both")]
           for c in ("push", "pull", "legs", "core")}
    home_pool = [e for e, x in table.items() if x.active and x.venue in ("home", "both")]

    order = [("Gym 1", nxt), ("Gym 2", "pull" if nxt == "push" else "push"),
             ("Home", "home"), ("Gym 3", nxt),
             ("Gym 4 (optional)", "pull" if nxt == "push" else "push")]

    out = [f"# Week of {today}", "",
           f"Last gym session was **{prev}**, so the cycle continues with **{nxt}**.",
           "Sessions are ordered, not dated - do them whenever the week allows.",
           "Everything is 3x8; only the weight moves.", ""]

    for i, (label, kind) in enumerate(order):
        on = today + dt.timedelta(days=1 + GAP * i)
        out += [f"## {label} - {kind}", ""]
        before = dict(last_hit)
        for cat, n in SHAPE[kind]:
            pool = home_pool if kind == "home" else gym[cat]
            for ex in pick(pool, n, on, last_hit, last_done, table):
                x = table[ex]
                top, clean, prevw, prevd = last_weight(hist, ex)
                if top:
                    note = f"3x8 @ {top:.0f}" + (" (clean last time)" if clean else " (missed reps last time)")
                    if prevw:
                        note += f" - was {prevw:.0f} on {prevd}"
                else:
                    note = "3 sets" + ("" if last_done.get(ex) else " - first time, pick light and log it")
                ago = (on - before[x.primary]).days if x.primary in before else 99
                warn = f"  **{x.primary} only {ago}d rest**" if ago < FRESH_DAYS else ""
                out.append(f"- **{ex}** - {note}{warn}")
                last_done[ex] = on
                for m in [x.primary] + x.secondary:
                    last_hit[m] = on
        out.append("")

    text = "\n".join(out)
    plans = os.path.join(w.DATA, "plans")
    os.makedirs(plans, exist_ok=True)
    for path in (os.path.join(plans, f"{today}.md"), os.path.join(w.DATA, "plan.md"), TAILDRIVE):
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
        except OSError as e:
            print(f"! could not write {path}: {e}", file=sys.stderr)
    print(text)
    print(f"written to {plans}/{today}.md, {w.DATA}/plan.md, and {TAILDRIVE}")


if __name__ == "__main__":
    main(dt.date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else None)

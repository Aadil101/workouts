"""Weekly session plan. Deterministic: same history in, same plan out."""
import os, sys, datetime as dt
from collections import defaultdict
import workouts as w

FRESH_DAYS = 2          # under this many days since a primary hit -> flag it
GAP = 2                 # assumed days between sessions, for forward simulation
# Optional: a synced folder (iCloud, Dropbox, taildrive) to drop a copy of the plan
# into, for reading on a phone. Unset means the plan lands only in the data repo.
SYNC = os.environ.get("WORKOUTS_SYNC")

# Stable structure, rotating fill. Counts are slots, not exercises.
SHAPE = {"push": [("push", 4), ("legs", 1), ("core", 1)],
         "pull": [("pull", 4), ("legs", 1), ("core", 1)],
         "home": [("home", 4)]}


STALL = 4               # sessions at an unchanged top weight before it is worth saying
SPLIT = 0.10            # next rung more than this fraction up -> prescribe a split set
DEFAULT_INC = 5.0       # fallback step when an exercise has only ever seen one weight
TIME_INC = 5            # seconds to add to a hold that was completed
REP_INC = 1             # reps to add to a bodyweight set that was completed

# Section anchors. Deliberately few: a marker that appears on every line stops
# being a marker. A clean session shows no emoji below its heading at all.
ANCHOR = {"push": "🟧", "pull": "🟦", "home": "🏠"}


def mode(hist, ex):
    """How this exercise progresses: by weight, by time under tension, or by reps.

    Read off the export rather than declared in the table. Hevy already
    distinguishes them - a plank logs seconds and no weight, a push up logs reps
    and no weight - so a column would only be a second place for it to be wrong.
    """
    sets = [s for s in hist if s.exercise == ex]
    if any(s.weight for s in sets):
        return "weight"
    if any(s.duration for s in sets):
        return "time"
    return "reps"


def typical_sets(hist, ex, default=3):
    """How many sets of this he did last time.

    The gym runs on three sets, but home does not - a wall sit is one, a side
    plank two, a bicycle crunch five. Prescribing three everywhere invented work
    for some exercises and quietly cut it from others.

    Deliberately the last session and not the most common one: the counts climb
    as an exercise gets easier - push ups went one, two, three - so the commonest
    value is a record of how he started rather than where he is.
    """
    per_day = defaultdict(int)
    for s in hist:
        if s.exercise == ex and value(s, mode(hist, ex)):
            per_day[s.date.date()] += 1
    return per_day[max(per_day)] if per_day else default


def value(s, m):
    return s.weight if m == "weight" else s.duration if m == "time" else s.reps


def fmt(x, m="weight"):
    """42.5 -> '42.5', 35.0 -> '35', a hold -> '65s'."""
    return f"{x:g}s" if m == "time" else f"{x:g}"


def increment(hist, ex):
    """Smallest upward step this exercise has actually moved in.

    Only meaningful for weighted work. A hold and a bodyweight set have no
    hardware imposing a step, so they get a flat one.

    The plate stack, the pin spacing, the gap between dumbbell pairs - all of it
    is already latent in the history, so no column is needed. Cable stacks come
    out at 7.5, dumbbells at 2.5, most pin machines at 5. An exercise that has
    only ever seen one weight has nothing to infer from; light things are
    usually dumbbells, so guess accordingly.
    """
    m = mode(hist, ex)
    if m == "time":
        return TIME_INC
    if m == "reps":
        return REP_INC
    ws = sorted({s.weight for s in hist if s.exercise == ex and s.weight})
    gaps = [round(b - a, 2) for a, b in zip(ws, ws[1:])]
    if gaps:
        return min(gaps)
    return 2.5 if ws and ws[0] < 25 else DEFAULT_INC


def last_triple(hist, ex):
    """(values, clean, date, touched) for the most recent day this was done.

    Values are in whatever unit the exercise progresses in - pounds, seconds or
    reps. 'clean' means the day's work was completed. For weighted work that is
    usually every set at 8 reps, but a prescribed split (4 at the old weight, 4
    at the new) also completes a set - the short sets add up to 8. Requiring 8
    everywhere made a perfectly executed split read as a failure, which repeated
    the same triple and re-prescribed the same split forever.

    A hold or a bodyweight set has no rep target to miss, so finishing three
    sets is the whole of it.

    The working values are the ones that carried a full set; a half set is an
    attempt at the next rung, not a rung. They pad back to three so a repeat has
    something to repeat.
    """
    days = defaultdict(list)
    for s in hist:
        if s.exercise == ex:
            days[s.date.date()].append(s)
    if not days:
        return None, False, None, set()
    d = max(days)
    m = mode(hist, ex)
    sets = [s for s in days[d] if value(s, m)]
    if not sets:
        return None, False, d, set()
    vals = sorted(value(s, m) for s in sets)
    if m != "weight":
        # A hold has no failure state - you hold until you cannot, and that
        # number is the result. Same for a bodyweight set taken to its limit.
        return [vals[-1]], True, d, set(vals)
    short = [s.reps for s in sets if s.reps is not None and s.reps < 8]
    clean = len(sets) >= 3 and (not short or sum(short) >= 8)
    good = sorted(s.weight for s in sets if s.reps is None or s.reps >= 8)
    good = good or vals
    while len(good) < 3:
        good.insert(0, good[0])
    return good[-3:], clean, d, set(vals)


def advance(triple, inc):
    """One rung up the ladder: drop the first set, append at the top.

    Read off his own history rather than invented - (a a a) -> (a a b) ->
    (a b b) -> (b b c). Appending the max when the tail already straddles two
    weights is what makes the middle rung a half-step instead of a jump.
    """
    tail = list(triple[1:])
    top = max(tail)
    return tail + [top if tail[0] != tail[-1] else round(top + inc, 2)]


def stalled(hist, ex):
    """Sessions since this exercise's top weight last went up.

    A normal ladder holds the top weight for two sessions - (a a b) then
    (a b b) - and three when a split lands in between, so anything past that is
    a real plateau rather than the rule working. Deliberately reported and not
    acted on: his own history has 11- and 12-session stalls that he broke by
    grinding, and a deload rule would have thrown that progress away.
    """
    days = defaultdict(list)
    for s in hist:
        if s.exercise == ex and value(s, mode(hist, ex)) is not None:
            days[s.date.date()].append(value(s, mode(hist, ex)))
    tops = [max(days[d]) for d in sorted(days)]
    if not tops:
        return 0
    # Measured from the last all-time high, not the last increase: coming back up
    # to a weight after an easier day is recovering ground, not gaining it, and
    # counting it as progress would quietly reset a plateau that never ended.
    peak = 0
    for i, t in enumerate(tops):
        if t > max(tops[:i], default=0):
            peak = i
    return len(tops) - 1 - peak


def prescribe(hist, ex):
    """The three values to load or hold, plus a marker and a note."""
    triple, clean, when, touched = last_triple(hist, ex)
    m = mode(hist, ex)
    if triple is None:
        return None, m, "🆕", "first time - start easy and log it"
    inc = increment(hist, ex)
    if not clean:
        return triple, m, "⚠️", f"repeat - did not finish on {when}"
    if m != "weight":
        # A hold or a bodyweight set has no ladder: there is one number, and the
        # job is to beat it. Splitting it would mean nothing.
        return [round(triple[-1] + inc, 2)] * typical_sets(hist, ex), m, "", ""
    nxt = advance(triple, inc)
    if nxt[-1] > max(triple) and inc / max(triple) > SPLIT and nxt[-1] not in touched:
        # The next rung is a big relative jump - the dumbbell-rack problem. Split
        # the last set rather than stalling on it for another month. Once a split
        # has actually been completed at that weight it is earned, so take it
        # whole next time instead of splitting the same rung again.
        return triple, m, "🪜", f"last set splits: {fmt(triple[-1])}x4 + {fmt(nxt[-1])}x4"
    return nxt, m, "", ""


def compound_first(chosen, table):
    """Order a session's picks so the heaviest work comes while you're fresh.

    Staleness is the right rule for choosing exercises and the wrong one for
    ordering them - it will happily open a session with a wrist curl. The
    number of muscles an exercise loads is already in the table and is a decent
    proxy for how compound it is, so no extra column is needed. Sorting is
    stable, so staleness still breaks ties within a tier.
    """
    return sorted(chosen, key=lambda e: -(1 + len(table[e].secondary)))


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


def last_gym_kind(sess, table):
    """push/pull of the most recent gym session, or None if there isn't one.

    The whole week hangs off this: a wrong answer here silently gives you the
    same half twice in a row. Home sessions are skipped - they contain pushing
    work but don't advance the gym cycle.
    """
    for _, venue, ss in reversed(sess):
        cats = [table[s.exercise].category for s in ss
                if s.exercise in table and table[s.exercise].venue != "home"]
        if not cats:
            continue
        push, pull = cats.count("push"), cats.count("pull")
        if push or pull:
            return "push" if push >= pull else "pull"
    return None


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

    prev = last_gym_kind(sess, table)
    nxt = "pull" if prev == "push" else "push"

    gym = {c: [e for e, x in table.items() if x.active and x.category == c and x.venue in ("gym", "both")]
           for c in ("push", "pull", "legs", "core")}
    home_pool = [e for e, x in table.items() if x.active and x.venue in ("home", "both")]

    opp = "pull" if nxt == "push" else "push"
    order = [("Gym 1", nxt, ""), ("Gym 2", opp, ""), ("Home", "home", ""),
             ("Gym 3", nxt, ""), ("Gym 4", opp, " (optional)")]

    out = [f"# 🗓️ Week of {today:%b %-d}" if os.name != "nt"
           else f"# 🗓️ Week of {today:%b %#d}", "",
           f"Coming off **{prev}**, so the cycle opens with **{nxt}**.",
           "Sessions are ordered, not dated.", ""]

    for i, (label, kind, tail) in enumerate(order):
        on = today + dt.timedelta(days=1 + GAP * i)
        anchor = "⭐" if tail else ANCHOR[kind]
        head = label if kind == "home" else f"{label} - {kind.capitalize()}"
        out += [f"## {anchor} {head}{tail}", ""]
        before = dict(last_hit)
        for cat, n in SHAPE[kind]:
            pool = home_pool if kind == "home" else gym[cat]
            for ex in compound_first(pick(pool, n, on, last_hit, last_done, table), table):
                x = table[ex]
                triple, m, mark, note = prescribe(hist, ex)
                held = stalled(hist, ex)
                if triple and held >= STALL:
                    # Report where it actually sat, not what is being asked for
                    # now - the prescription is the thing that has not landed.
                    top, _, _, _ = last_triple(hist, ex)
                    note = (note + " - " if note else "- ") + f"stuck at {fmt(max(top), m)} for {held} sessions"
                ago = (on - before[x.primary]).days if x.primary in before else 99
                if ago < FRESH_DAYS and not mark:
                    mark, note = "⚠️", f"{x.primary} has had only {ago}d rest"
                line = " · ".join(fmt(t, m) for t in triple) if triple else ""
                if triple and m == "reps":
                    line += " reps"
                out += [f"**{ex}**", " ".join(p for p in (line, mark, note) if p).strip(), ""]
                last_done[ex] = on
                for m in [x.primary] + x.secondary:
                    last_hit[m] = on

    text = "\n".join(out)
    plans = os.path.join(w.DATA, "plans")
    os.makedirs(plans, exist_ok=True)
    written = [os.path.join(plans, f"{today}.md"), os.path.join(w.DATA, "plan.md")]
    if SYNC:
        written.append(os.path.normpath(os.path.join(SYNC, "plan.md")))
    for path in written:
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
        except OSError as e:
            print(f"! could not write {path}: {e}", file=sys.stderr)
    # The files are always utf-8; only the console might not be (Windows
    # defaults to cp1252, which cannot encode the section anchors).
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass
    print(text)
    print("written to " + ", ".join(written))


if __name__ == "__main__":
    main(dt.date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else None)

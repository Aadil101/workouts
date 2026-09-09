# workouts

A deterministic weekly session planner built on top of [Hevy](https://www.hevyapp.com/)
exports. It answers one question Hevy doesn't: **what should I do this session, given
what I've hit recently?**

Hevy already does analytics well - volume charts, per-exercise progression, personal
records. What it doesn't do is look at the last two weeks and tell you that your chest
has been worked three days running while your hamstrings haven't been touched since
Tuesday. That gap is the whole reason this exists.

No LLM at generation time. Same history in, same plan out.

## The problem it actually solves

Training ad-hoc means picking exercises at the rack based on what you feel like, which
in practice means picking what you did last time. Over three months of my own logs that
produced **24 back-to-back sessions sharing a primary muscle** - roughly half of all
sessions - entirely invisible to me while it was happening. Two of those collisions came
from bodyweight work at home landing next to machine work at the gym, which feel like
unrelated activities and are not.

The planner scores every muscle by how recently it was worked, treats home and gym as
one continuous history, and fills a fixed session shape with whatever is stalest.

## How it works

```
  Hevy iPhone app
        |  export CSV
        v
   ingest.py ---------> exports/YYYY-MM-DD.csv     (raw dumps, never edited,
        |                                           named from their own contents)
        |               exercises.csv              (muscle table: anatomy from Hevy,
        |                    |                      category + venue are ours)
        v                    v
   workouts.py  <-----------+   load, dedupe, weight secondary muscles at 0.5
        |
        +--> stale.py    per-muscle staleness, per-exercise state, collision audit
        |
        +--> plan.py     one week of sessions -> Markdown
```

**Exports accumulate rather than replace.** Hevy's free tier caps stats views at three
months, and its CSV export may follow the same window. Keeping every dated dump means
the union stays complete even if any single export is truncated.

**The muscle table is the one hand-authored file.** Anatomy columns are copied verbatim
from what the Hevy app displays, so any row can be verified against the app in seconds
rather than trusting a mapping someone invented. `category` (push/pull/legs/core),
`venue` (gym/home/both), and `active` are scheduling metadata that Hevy has no opinion
on. Setting `active: no` retires an exercise without deleting its history - necessary
because a retired exercise is by definition the stalest thing in the pool, and would
otherwise be recommended forever.

**Deviation is self-healing.** There is no state file to update and no way to tell the
planner you skipped something. Skip a session and those muscles are simply the stalest
next week, derived from what you actually logged. State files that require manual upkeep
go stale silently and then quietly corrupt every recommendation downstream.

## Usage

```sh
python ingest.py               # file every export waiting in the sync folder
python ingest.py some.csv      # or file one explicitly
python stale.py                # inspect the model
python plan.py                 # generate the week
python -m unittest             # run the tests
```

Two environment variables, both optional:

| | |
|---|---|
| `WORKOUTS_DATA` | directory holding `exports/` and `plans/`. Defaults to `../workouts-data`. |
| `WORKOUTS_SYNC` | a folder synced to your phone (iCloud, Dropbox, Syncthing, a Tailscale share). `ingest.py` scans it for exports; `plan.py` drops a copy of the plan there. Unset means neither happens. |

**Data lives outside this repo on purpose.** Session timestamps are a log of when you
are at home versus out, at what times, for how long. That is a different kind of
sensitive than knowing how much you lift, and it should not be in a public repo or in
its history.

`ingest.py` names each export from the latest session inside it, so re-ingesting the
same file is harmless. Scanning the sync folder deletes what it consumes, because iOS
never overwrites - saving from Hevy repeatedly leaves `workout_data.csv`,
`workout_data 2.csv`, and so on until you cannot tell which you have processed.

## Running it without a computer

[a-Shell](https://holzschu.github.io/a-Shell_iOS/) makes this viable entirely on an
iPhone: it ships `python3`, clones over libgit2 (`lg2 clone`), and `pickFolder`
bookmarks an iCloud directory that scripts can read and write. It works, but debugging
a title mismatch in `exercises.csv` from a mobile terminal is unpleasant, and the
folder grants [can be lost](https://github.com/holzschu/a-shell/issues/729). Worth
knowing about; not the path I would choose first.

## Making it yours

`exercises.csv` is tuned to one gym's machines and one person's habits, so it is an
example rather than a default. Weight increments are not in it: they are inferred from
the smallest step your own history has ever moved in, so a cable stack, a pin machine
and a dumbbell rack each get the right step with nothing to configure. An exercise
marked `both` runs a separate ladder per venue, so the gym's rack and whatever is in
your spare room never get confused for each other.

The one thing that cannot be inferred is a ceiling: running out of equipment and
plateauing look identical in a history. An optional `limits.csv` in the data repo
(`exercise,venue,max`) holds a prescription back where the weights run out. It lives
there rather than here because what your rack holds is nobody else's business. An exercise
marked `both` runs a separate ladder per venue, so the gym's dumbbell rack and whatever
is in your spare room never get confused for each other. Replace the rows with
your own exercises, using the exact `exercise_title` strings Hevy writes in its export -
that string is the join key, and a mismatch drops the exercise silently instead of
raising an error.

The session shape (`SHAPE` in `plan.py`) is push/pull alternating with one rotating leg
machine and one core slot per gym session, plus a short home session. Rotation is only
as varied as the pool: with fewer distinct primary muscles than session slots, the same
exercises will recur. That is a property of the equipment list, not a bug.

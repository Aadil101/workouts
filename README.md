# workouts

Tools built on top of [Hevy](https://www.hevyapp.com/) exports, for what the app
doesn't answer. The core is a deterministic weekly session planner: **what should I do
this session, given what I've hit recently?**

Hevy's analytics are good - volume charts, per-exercise progression, personal records -
but nothing in it looks at the last two weeks and tells you that your chest has been
worked three days running while your hamstrings haven't been touched since Tuesday. The
planner exists for that gap. Smaller tools belong here too when they fill a similar one,
such as all-time stats that Hevy's free tier only shows for the last three months.

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
   ingest.py ---------> history.csv                (every export merged in;
        |                                           latest-export.csv is the raw dump)
        |               exercises.csv              (muscle table: anatomy from Hevy,
        |                    |                      category + venue are ours)
        v                    v
   workouts.py  <-----------+   load, weight secondary muscles at 0.5
        |
        +--> stale.py    per-muscle staleness, per-exercise state, collision audit
        |
        +--> plan.py     one week of sessions -> plain text
```

**History is merged, not replaced.** Hevy's free tier caps stats views at three months.
Its CSV export currently returns everything, but nothing promises it will. Each export
is trusted inside its own date range, so edits and deletions made in Hevy come through,
and everything older is kept. If Hevy ever trims exports, older sessions stay in
history, and ingest says so loudly rather than dropping them. Removed sessions are
listed by name for the same reason. The raw dump overwrites `latest-export.csv`, so git
history still holds every export while the disk holds one.

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
python ingest.py               # merge every export waiting in the sync folder
python ingest.py some.csv      # or merge one explicitly
python stale.py                # inspect the model
python plan.py                 # generate the week
python stats.py                # all-time per-exercise charts -> stats.html
python -m unittest             # run the tests
```

Two environment variables, both optional:

| | |
|---|---|
| `WORKOUTS_DATA` | directory holding `history.csv` and `plans/`. Defaults to `../workouts-data`. |
| `WORKOUTS_SYNC` | a folder synced to your phone (iCloud, Dropbox, Syncthing). `ingest.py` scans it for exports; `plan.py` drops a copy of the plan there. Unset means neither happens. |

**Data lives outside this repo on purpose.** Session timestamps are a log of when you
are at home versus out, at what times, for how long. That is a different kind of
sensitive than knowing how much you lift, and it should not be in a public repo or in
its history.

Re-ingesting the same export is harmless: merging it again changes nothing. Scanning
the sync folder deletes what it consumes, because iOS never overwrites - saving from
Hevy repeatedly leaves `workout_data.csv`, `workout_data 2.csv`, and so on until you
cannot tell which you have processed. Several at once are merged oldest first.

## Running it without a computer

[a-Shell](https://holzschu.github.io/a-Shell_iOS/) makes this viable entirely on an
iPhone: it ships `python3`, clones over libgit2 (`lg2 clone`), and `pickFolder`
bookmarks an iCloud directory that scripts can read and write. It works, but debugging
a title mismatch in `exercises.csv` from a mobile terminal is unpleasant, and the
folder grants [can be lost](https://github.com/holzschu/a-shell/issues/729). Worth
knowing about; not the path I would choose first.

## The weekly loop

`weekly.sh` is the whole thing in one command - update the planner itself, pull the
data repo, merge any export sitting in the sync folder, write the plan, commit and push.
A machine that only runs the planner therefore never needs a manual `git pull`:

```sh
~/src/workouts/weekly.sh
```

It is safe to run whenever. A week with no new export is normal, not an error, and
running it twice in a day just writes the same plan again.

To make that a single click on macOS, save a one-line `.command` file that Finder can
open, and keep it in the Dock. Shortcuts works too on Monterey and later, and
`launchd` will run it on a schedule if you would rather it just happened.

Whatever launches it, remember that a double-clicked script does not read `~/.zshrc` -
put `WORKOUTS_SYNC` in `~/.zshenv`, which zsh reads for non-interactive shells too.

## Making it yours

`exercises.csv` is tuned to one gym's machines and one person's habits, so it is an
example rather than a default. Weight increments are not in it: they are inferred from
the smallest step your own history has ever moved in, so a cable stack, a pin machine
and a dumbbell rack each get the right step with nothing to configure. An exercise
marked `both` runs a separate ladder per venue, so the gym's rack and whatever is in
your spare room never get confused for each other.

The one thing that cannot be inferred is a ceiling: running out of equipment and
plateauing look identical in a history. An optional `limits.csv` in the data repo
(`exercise,venue,max,step`) holds a prescription back where the weights run out. Its
optional `step` column overrides the inferred increment, for the day a one-off session on
a finer stack would otherwise teach the planner a step your usual machine doesn't have. It lives
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

Slots are filled per category but ordered across the whole session, so that
neighbouring exercises share as few muscles as possible - a pulldown is not followed
straight by a row. In practice the leg and core slots land between upper-body lifts.
Among equally spread orders the most compound lifts still go first.

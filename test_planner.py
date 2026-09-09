"""Tests for the logic whose failures are silent rather than loud.

Every bug this file guards against shipped at some point and produced a
confident, plausible-looking plan. None of them raised.
"""
import datetime as dt
import unittest

import plan
from workouts import Ex, Set, sessions as w_sessions

D = dt.date(2026, 9, 9)


def ex(primary, category="push", venue="gym", secondary=(), active=True):
    return Ex(category, venue, primary, list(secondary), active)


def sets(exercise, day, reps, weight=60.0, venue="My Workout"):
    """One session's worth of sets for a single exercise."""
    return [Set(dt.datetime(day.year, day.month, day.day, 18, 0), venue,
                exercise, i, weight, r, None) for i, r in enumerate(reps)]


def held(exercise, day, seconds):
    """A timed session - a plank logs seconds and no weight at all."""
    return [Set(dt.datetime(day.year, day.month, day.day, 18, 0), "My Home Workout",
                exercise, i, None, 0, sec) for i, sec in enumerate(seconds)]


def bodyweight(exercise, day, reps):
    """A bodyweight session - reps, no weight, no duration."""
    return [Set(dt.datetime(day.year, day.month, day.day, 18, 0), "My Home Workout",
                exercise, i, None, r, 0) for i, r in enumerate(reps)]


class Pick(unittest.TestCase):
    table = {"a": ex("chest"), "b": ex("shoulders"), "c": ex("triceps")}

    def test_prefers_the_stalest_primary(self):
        last_hit = {"chest": D - dt.timedelta(days=1),
                    "shoulders": D - dt.timedelta(days=9),
                    "triceps": D - dt.timedelta(days=4)}
        got = plan.pick(list(self.table), 3, D, last_hit, {}, self.table)
        self.assertEqual(got, ["b", "c", "a"])

    def test_one_exercise_per_primary_muscle(self):
        table = dict(self.table, d=ex("chest"))
        got = plan.pick(list(table), 2, D, {}, {}, table)
        self.assertEqual(len({table[e].primary for e in got}), 2)

    def test_fills_every_slot_when_primaries_run_out(self):
        """Shipped bug: push days came up short because the pool had three
        distinct primaries and the session asked for four slots."""
        table = {"a": ex("chest"), "b": ex("chest"), "c": ex("shoulders")}
        got = plan.pick(list(table), 3, D, {}, {}, table)
        self.assertEqual(len(got), 3)
        self.assertEqual(len(set(got)), 3)

    def test_never_exceeds_the_slot_count(self):
        got = plan.pick(list(self.table), 2, D, {}, {}, self.table)
        self.assertEqual(len(got), 2)

    def test_breaks_ties_on_least_recently_performed(self):
        last_hit = {m: D - dt.timedelta(days=5) for m in ("chest", "shoulders", "triceps")}
        last_done = {"a": D - dt.timedelta(days=1), "b": D - dt.timedelta(days=20),
                     "c": D - dt.timedelta(days=10)}
        got = plan.pick(list(self.table), 1, D, last_hit, last_done, self.table)
        self.assertEqual(got, ["b"])


class Ordering(unittest.TestCase):
    """Selection is by staleness; presentation is by how compound the lift is."""
    table = {"pulldown": ex("lats", secondary=["upper back", "biceps", "forearms"]),
             "wristcurl": ex("forearms"),
             "press": ex("chest", secondary=["shoulders", "triceps"])}

    def test_compounds_come_before_isolation(self):
        """Shipped bug: a session opened with a wrist curl because it happened
        to be the stalest thing in the pool."""
        got = plan.compound_first(["wristcurl", "pulldown", "press"], self.table)
        self.assertEqual(got, ["pulldown", "press", "wristcurl"])

    def test_ordering_is_stable_within_a_tier(self):
        table = dict(self.table, other=ex("biceps"))
        self.assertEqual(plan.compound_first(["wristcurl", "other"], table),
                         ["wristcurl", "other"])

    def test_keeps_every_exercise(self):
        got = plan.compound_first(["wristcurl", "pulldown", "press"], self.table)
        self.assertCountEqual(got, ["wristcurl", "pulldown", "press"])


def ramp(exercise, day, pairs):
    """A session of (weight, reps) pairs - the ascending ladders he actually does."""
    return [Set(dt.datetime(day.year, day.month, day.day, 18, 0), "My Workout",
                exercise, i, wt, r, None) for i, (wt, r) in enumerate(pairs)]


class Ladder(unittest.TestCase):
    """The rung rule, read off his own history: (a a a) -> (a a b) -> (a b b) -> (b b c)."""

    def test_flat_triple_grows_a_top_rung(self):
        self.assertEqual(plan.advance([100, 100, 100], 5), [100, 100, 105])

    def test_middle_rung_fills_before_the_top_moves(self):
        """The half-step is the whole point of double progression. Skipping it
        turns every session into a jump and is how you stall."""
        self.assertEqual(plan.advance([100, 100, 105], 5), [100, 105, 105])

    def test_full_triple_moves_the_whole_ladder_up(self):
        self.assertEqual(plan.advance([100, 105, 105], 5), [105, 105, 110])

    def test_reproduces_the_seated_dip_progression(self):
        """Four real sessions from Aug 27 to Sep 8. If the rule is right it
        predicts each from the one before with no special cases."""
        t = [95, 100, 100]
        for expected in ([100, 100, 105], [100, 105, 105], [105, 105, 110]):
            t = plan.advance(t, 5)
            self.assertEqual(t, expected)


class Increment(unittest.TestCase):
    def test_infers_the_stack_from_weights_used(self):
        """Cable stacks move in 7.5, dumbbells in 2.5. Both are already in the
        history, so an increment column would be a second source of truth."""
        hist = (ramp("a", D - dt.timedelta(days=9), [(27.5, 8), (35, 8), (35, 8)])
                + ramp("a", D - dt.timedelta(days=2), [(35, 8), (35, 8), (42.5, 8)]))
        self.assertEqual(plan.increment(hist, "a"), 7.5)

    def test_ignores_larger_jumps(self):
        """A one-off 20lb leap must not become the assumed step size."""
        hist = ramp("a", D, [(30, 8), (35, 8), (55, 8)])
        self.assertEqual(plan.increment(hist, "a"), 5)

    def test_single_weight_guesses_by_load(self):
        self.assertEqual(plan.increment(ramp("a", D, [(10, 8)]), "a"), 2.5)
        self.assertEqual(plan.increment(ramp("a", D, [(90, 8)]), "a"), plan.DEFAULT_INC)


class Stall(unittest.TestCase):
    """Reported, never acted on - see the docstring on plan.stalled."""

    def days(self, *tops):
        h = []
        for i, t in enumerate(tops):
            h += ramp("a", D - dt.timedelta(days=3 * (len(tops) - i)), [(t, 8)] * 3)
        return h

    def test_a_normal_ladder_does_not_read_as_stalled(self):
        """(a a b) and (a b b) share a top weight by design. Counting that as a
        plateau would put the warning on almost every line and kill its meaning."""
        self.assertLess(plan.stalled(self.days(95, 100, 100, 105), "a"), plan.STALL)

    def test_counts_sessions_since_the_top_last_moved(self):
        self.assertEqual(plan.stalled(self.days(40, 45, 45, 45, 45, 45), "a"), 4)

    def test_a_new_top_resets_it(self):
        self.assertEqual(plan.stalled(self.days(45, 45, 45, 45, 50), "a"), 0)

    def test_a_lighter_session_does_not_reset_it(self):
        """Backing off for a day is not progress; the plateau is still there."""
        self.assertEqual(plan.stalled(self.days(45, 45, 40, 45), "a"), 3)


class Modes(unittest.TestCase):
    """Not everything progresses by weight. Reading the mode off the export is
    what stopped six bodyweight exercises reporting 'first time' forever - a
    plank logs seconds and no weight, so a weight-keyed lookup found nothing."""

    def test_a_hold_is_timed(self):
        self.assertEqual(plan.mode(held("a", D, [60, 60, 60]), "a"), "time")

    def test_a_bodyweight_set_is_reps(self):
        self.assertEqual(plan.mode(bodyweight("a", D, [8, 8, 8]), "a"), "reps")

    def test_loaded_work_is_weight(self):
        self.assertEqual(plan.mode(ramp("a", D, [(60, 8)]), "a"), "weight")

    def test_a_hold_gets_longer(self):
        hist = held("a", D - dt.timedelta(days=3), [60, 65, 65])
        triple, m, _, _ = plan.prescribe(hist, "a")
        self.assertEqual((triple, m), ([70, 70, 70], "time"))

    def test_a_bodyweight_set_gets_a_rep(self):
        hist = bodyweight("a", D - dt.timedelta(days=3), [8, 8, 8])
        triple, m, _, _ = plan.prescribe(hist, "a")
        self.assertEqual((triple, m), ([9, 9, 9], "reps"))

    def test_set_count_follows_the_last_session(self):
        """A wall sit is one set, a side plank two, a bicycle crunch five.
        Assuming three invented work for some and cut it from others."""
        self.assertEqual(len(plan.prescribe(held("a", D, [60]), "a")[0]), 1)
        self.assertEqual(len(plan.prescribe(held("b", D, [60, 62]), "b")[0]), 2)

    def test_set_count_is_recency_not_frequency(self):
        """Push ups went one set, then two, then three as they got easier. The
        commonest count is a record of how he started, not where he is."""
        hist = (bodyweight("a", D - dt.timedelta(days=30), [8])
                + bodyweight("a", D - dt.timedelta(days=20), [8])
                + bodyweight("a", D - dt.timedelta(days=10), [8, 8])
                + bodyweight("a", D - dt.timedelta(days=3), [8, 8, 8]))
        self.assertEqual(plan.typical_sets(hist, "a"), 3)

    def test_a_hold_never_splits(self):
        """The split set is a weight-stack trick. 5s on a 60s hold is over the
        10% line, but half a plank at a heavier plank means nothing."""
        hist = held("a", D - dt.timedelta(days=3), [30, 30, 30])
        _, _, mark, note = plan.prescribe(hist, "a")
        self.assertEqual((mark, note), ("", ""))

    def test_seconds_render_with_a_unit(self):
        self.assertEqual(plan.fmt(65, "time"), "65s")
        self.assertEqual(plan.fmt(42.5, "weight"), "42.5")


class Ceiling(unittest.TestCase):
    """Some venues run out of equipment. A ceiling and a plateau look identical
    in the history, so this is the one thing that has to be declared - and it
    lives in the data repo, because what your rack holds is nobody's business."""

    def test_a_capped_exercise_stops_climbing(self):
        hist = ramp("a", D - dt.timedelta(days=3), [(10, 8), (10, 8), (10, 8)])
        triple, _, _, note = plan.prescribe(hist, "a", cap=10)
        self.assertEqual(triple, [10, 10, 10])
        self.assertIn("heaviest", note)

    def test_a_cap_never_splits_past_itself(self):
        """The split set proposes a heavier last half. At the ceiling there is
        no heavier half, so proposing one is proposing the impossible."""
        hist = ramp("a", D - dt.timedelta(days=3), [(10, 8), (10, 8), (10, 8)])
        _, _, mark, _ = plan.prescribe(hist, "a", cap=10)
        self.assertNotEqual(mark, "🪜")

    def test_a_cap_still_allows_the_rungs_below_it(self):
        """A ceiling holds the top back; it must not flatten the whole ladder."""
        hist = ramp("a", D - dt.timedelta(days=3), [(100, 8), (100, 8), (105, 8)])
        triple, _, _, _ = plan.prescribe(hist, "a", cap=200)
        self.assertEqual(triple, [100, 105, 105])

    def test_no_cap_behaves_as_before(self):
        hist = ramp("a", D - dt.timedelta(days=3), [(100, 8), (100, 8), (105, 8)])
        self.assertEqual(plan.prescribe(hist, "a")[0],
                         plan.prescribe(hist, "a", cap=None)[0])


class Prescribe(unittest.TestCase):
    def test_clean_session_advances(self):
        hist = ramp("a", D - dt.timedelta(days=2), [(100, 8), (100, 8), (105, 8)])
        triple, _m, mark, _ = plan.prescribe(hist, "a")
        self.assertEqual(triple, [100, 105, 105])
        self.assertEqual(mark, "")

    def test_a_completed_split_counts_as_done(self):
        """The real Sep 6 lat pulldown: 35/35/35x4 + 42.5x4, which is the split
        the tool itself prescribes. Reading it as a miss repeated the triple and
        re-prescribed the same split, so the rung could never be climbed."""
        hist = ramp("a", D - dt.timedelta(days=2),
                    [(35, 8), (35, 8), (35, 4), (42.5, 4)])
        triple, _m, mark, note = plan.prescribe(hist, "a")
        self.assertEqual(triple, [35, 35, 42.5])
        self.assertEqual((mark, note), ("", ""))

    def test_a_bailed_split_is_a_miss(self):
        """Half the split is not the split. 4 + 2 does not make a set."""
        hist = ramp("a", D - dt.timedelta(days=2),
                    [(35, 8), (35, 8), (35, 4), (42.5, 2)])
        triple, _m, _, note = plan.prescribe(hist, "a")
        self.assertEqual(triple, [35, 35, 35])
        self.assertIn("repeat", note)

    def test_missed_reps_repeat_the_working_weights(self):
        hist = ramp("a", D - dt.timedelta(days=2), [(35, 8), (35, 8), (35, 5)])
        triple, _m, _, note = plan.prescribe(hist, "a")
        self.assertEqual(triple, [35, 35, 35])
        self.assertIn("repeat", note)

    def test_big_relative_jump_becomes_a_split_set(self):
        """Dumbbells jump 2.5 off a 12.5 base - 20%. Prescribing it whole is how
        an exercise sits at one weight for eleven sessions."""
        hist = ramp("a", D - dt.timedelta(days=2), [(12.5, 8), (12.5, 8), (12.5, 8)])
        triple, _m, mark, note = plan.prescribe(hist, "a")
        self.assertEqual(triple, [12.5, 12.5, 12.5])
        self.assertIn("15x4", note)

    def test_small_relative_jump_does_not_split(self):
        hist = ramp("a", D - dt.timedelta(days=2), [(105, 8), (110, 8), (110, 8)])
        _, _m, mark, note = plan.prescribe(hist, "a")
        self.assertEqual((mark, note), ("", ""))

    def test_never_done_has_no_weights(self):
        triple, _m, _, note = plan.prescribe([], "nope")
        self.assertIsNone(triple)
        self.assertIn("first time", note)


class Venue(unittest.TestCase):
    """An exercise owned at both places runs two independent ladders. Merging
    them prescribed the gym's 12.5s for a home session where only 10s exist."""

    TABLE = {"press": ex("chest", venue="gym"), "pushup": ex("chest", venue="home"),
             "raise": ex("shoulders", venue="both")}

    def split(self, *sessions):
        hist = [s for session in sessions for s in session]
        return plan.by_venue(w_sessions(hist), self.TABLE)

    def test_a_session_holding_home_work_is_a_home_session(self):
        s = self.split(sets("pushup", D, [8, 8, 8], weight=None)
                       + sets("raise", D, [8, 8, 8], weight=10.0))
        self.assertEqual({x.exercise for x in s["home"]}, {"pushup", "raise"})
        self.assertEqual(s["gym"], [])

    def test_the_same_movement_keeps_separate_weights(self):
        s = self.split(sets("pushup", D - dt.timedelta(days=4), [8], weight=None)
                       + sets("raise", D - dt.timedelta(days=4), [8, 8, 8], weight=10.0),
                       sets("press", D - dt.timedelta(days=2), [8], weight=100.0)
                       + sets("raise", D - dt.timedelta(days=2), [8, 8, 8], weight=12.5))
        self.assertEqual({x.weight for x in s["home"] if x.exercise == "raise"}, {10.0})
        self.assertEqual({x.weight for x in s["gym"] if x.exercise == "raise"}, {12.5})

    def test_venue_comes_from_content_not_the_hevy_title(self):
        """Session titles are user-editable and mean nothing in someone else's
        export, so the exercise table has to be what decides."""
        s = self.split(sets("pushup", D, [8], weight=None, venue="Leg Day??"))
        self.assertEqual(len(s["home"]), 1)


class Carryover(unittest.TestCase):
    """Decides the whole week. A wrong answer repeats a half and looks normal."""
    table = {"press": ex("chest", "push"), "row": ex("upper back", "pull"),
             "pushup": ex("chest", "push", venue="home"),
             "curl": ex("biceps", "pull")}

    def sess(self, *days):
        out = []
        for day, venue, exercises in days:
            ss = [s for e in exercises for s in sets(e, day, [8], venue=venue)]
            out.append((dt.datetime(day.year, day.month, day.day, 18, 0), venue, ss))
        return out

    def test_reads_the_most_recent_gym_session(self):
        s = self.sess((D - dt.timedelta(days=4), "My Workout", ["row", "curl"]),
                      (D - dt.timedelta(days=2), "My Workout", ["press"]))
        self.assertEqual(plan.last_gym_kind(s, self.table), "push")

    def test_home_sessions_do_not_advance_the_cycle(self):
        """Push-ups are chest work but happen at home; the gym alternation
        must not flip because of them."""
        s = self.sess((D - dt.timedelta(days=3), "My Workout", ["row", "curl"]),
                      (D - dt.timedelta(days=1), "My Home Workout", ["pushup"]))
        self.assertEqual(plan.last_gym_kind(s, self.table), "pull")

    def test_majority_decides_a_mixed_session(self):
        s = self.sess((D - dt.timedelta(days=1), "My Workout", ["row", "curl", "press"]))
        self.assertEqual(plan.last_gym_kind(s, self.table), "pull")

    def test_no_gym_history_returns_none(self):
        s = self.sess((D - dt.timedelta(days=1), "My Home Workout", ["pushup"]))
        self.assertIsNone(plan.last_gym_kind(s, self.table))

    def test_unmapped_exercises_are_ignored(self):
        s = self.sess((D - dt.timedelta(days=1), "My Workout", ["mystery"]))
        self.assertIsNone(plan.last_gym_kind(s, self.table))


if __name__ == "__main__":
    unittest.main()

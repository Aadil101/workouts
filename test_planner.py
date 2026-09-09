"""Tests for the logic whose failures are silent rather than loud.

Every bug this file guards against shipped at some point and produced a
confident, plausible-looking plan. None of them raised.
"""
import datetime as dt
import unittest

import plan
from workouts import Ex, Set

D = dt.date(2026, 9, 9)


def ex(primary, category="push", venue="gym", secondary=(), active=True):
    return Ex(category, venue, primary, list(secondary), active)


def sets(exercise, day, reps, weight=60.0, venue="My Workout"):
    """One session's worth of sets for a single exercise."""
    return [Set(dt.datetime(day.year, day.month, day.day, 18, 0), venue,
                exercise, i, weight, r) for i, r in enumerate(reps)]


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
                exercise, i, wt, r) for i, (wt, r) in enumerate(pairs)]


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


class Prescribe(unittest.TestCase):
    def test_clean_session_advances(self):
        hist = ramp("a", D - dt.timedelta(days=2), [(100, 8), (100, 8), (105, 8)])
        triple, mark, _ = plan.prescribe(hist, "a")
        self.assertEqual(triple, [100, 105, 105])
        self.assertEqual(mark, "")

    def test_a_completed_split_counts_as_done(self):
        """The real Sep 6 lat pulldown: 35/35/35x4 + 42.5x4, which is the split
        the tool itself prescribes. Reading it as a miss repeated the triple and
        re-prescribed the same split, so the rung could never be climbed."""
        hist = ramp("a", D - dt.timedelta(days=2),
                    [(35, 8), (35, 8), (35, 4), (42.5, 4)])
        triple, mark, note = plan.prescribe(hist, "a")
        self.assertEqual(triple, [35, 35, 42.5])
        self.assertEqual((mark, note), ("", ""))

    def test_a_bailed_split_is_a_miss(self):
        """Half the split is not the split. 4 + 2 does not make a set."""
        hist = ramp("a", D - dt.timedelta(days=2),
                    [(35, 8), (35, 8), (35, 4), (42.5, 2)])
        triple, _, note = plan.prescribe(hist, "a")
        self.assertEqual(triple, [35, 35, 35])
        self.assertIn("repeat", note)

    def test_missed_reps_repeat_the_working_weights(self):
        hist = ramp("a", D - dt.timedelta(days=2), [(35, 8), (35, 8), (35, 5)])
        triple, _, note = plan.prescribe(hist, "a")
        self.assertEqual(triple, [35, 35, 35])
        self.assertIn("repeat", note)

    def test_big_relative_jump_becomes_a_split_set(self):
        """Dumbbells jump 2.5 off a 12.5 base - 20%. Prescribing it whole is how
        an exercise sits at one weight for eleven sessions."""
        hist = ramp("a", D - dt.timedelta(days=2), [(12.5, 8), (12.5, 8), (12.5, 8)])
        triple, mark, note = plan.prescribe(hist, "a")
        self.assertEqual(triple, [12.5, 12.5, 12.5])
        self.assertIn("15x4", note)

    def test_small_relative_jump_does_not_split(self):
        hist = ramp("a", D - dt.timedelta(days=2), [(105, 8), (110, 8), (110, 8)])
        _, mark, note = plan.prescribe(hist, "a")
        self.assertEqual((mark, note), ("", ""))

    def test_never_done_has_no_weights(self):
        triple, _, note = plan.prescribe([], "nope")
        self.assertIsNone(triple)
        self.assertIn("first time", note)


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

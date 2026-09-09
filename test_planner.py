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


class LastWeight(unittest.TestCase):
    def test_reports_top_set_and_clean_when_all_eights(self):
        hist = sets("a", D - dt.timedelta(days=2), [8, 8, 8], weight=60.0)
        top, clean, prev, _ = plan.last_weight(hist, "a")
        self.assertEqual((top, clean, prev), (60.0, True, None))

    def test_split_set_is_not_clean(self):
        """8/4+4 is a deliberate way to ease into a heavier weight. It must not
        read as a completed 3x8, or the trend line lies about readiness."""
        hist = sets("a", D - dt.timedelta(days=2), [8, 4, 4])
        _, clean, _, _ = plan.last_weight(hist, "a")
        self.assertFalse(clean)

    def test_fewer_than_three_sets_is_not_clean(self):
        hist = sets("a", D - dt.timedelta(days=2), [8, 8])
        _, clean, _, _ = plan.last_weight(hist, "a")
        self.assertFalse(clean)

    def test_finds_the_previous_different_weight(self):
        hist = (sets("a", D - dt.timedelta(days=20), [8, 8, 8], weight=50.0)
                + sets("a", D - dt.timedelta(days=9), [8, 8, 8], weight=50.0)
                + sets("a", D - dt.timedelta(days=2), [8, 8, 8], weight=60.0))
        top, _, prev, prevd = plan.last_weight(hist, "a")
        self.assertEqual((top, prev), (60.0, 50.0))
        self.assertEqual(prevd, D - dt.timedelta(days=9))

    def test_uses_the_heaviest_set_of_the_last_day(self):
        day = D - dt.timedelta(days=2)
        hist = sets("a", day, [8], weight=55.0) + sets("a", day, [8, 8], weight=60.0)
        top, _, _, _ = plan.last_weight(hist, "a")
        self.assertEqual(top, 60.0)

    def test_unknown_exercise_yields_nothing(self):
        self.assertEqual(plan.last_weight([], "nope"), (None, False, None, None))


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

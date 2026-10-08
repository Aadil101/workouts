"""Merging an export into history - where a wrong answer silently loses sessions."""
import unittest

from ingest import merge


def row(day, exercise="Chest Press (Machine)", i=0, weight="60"):
    return {"start_time": f"{day} Sep 2026, 18:00", "exercise_title": exercise,
            "set_index": str(i), "weight_lbs": weight}


class Merge(unittest.TestCase):
    def test_trimmed_export_keeps_older_history(self):
        merged, rep = merge([row(1), row(5)], [row(5), row(9)])
        self.assertEqual(merged, [row(1), row(5), row(9)])
        self.assertEqual(rep["older"], 1)

    def test_edit_in_hevy_wins(self):
        merged, rep = merge([row(5)], [row(5, weight="65")])
        self.assertEqual(merged, [row(5, weight="65")])
        self.assertEqual(len(rep["changed"]), 1)

    def test_deletion_in_hevy_is_reported_and_applied(self):
        merged, rep = merge([row(1), row(5), row(9)], [row(1), row(9)])
        self.assertEqual(merged, [row(1), row(9)])
        self.assertEqual(rep["removed"], [(row(5)["start_time"], "Chest Press (Machine)", "0")])

    def test_late_filed_older_export_keeps_newer_sessions(self):
        merged, _ = merge([row(1), row(9)], [row(1)])
        self.assertEqual(merged, [row(1), row(9)])

    def test_reingest_is_a_no_op(self):
        hist = [row(1), row(5, "Row", 0), row(5, "Row", 1)]
        merged, rep = merge(hist, hist)
        self.assertEqual(merged, hist)
        self.assertFalse(rep["added"] or rep["changed"] or rep["removed"] or rep["older"])


if __name__ == "__main__":
    unittest.main()

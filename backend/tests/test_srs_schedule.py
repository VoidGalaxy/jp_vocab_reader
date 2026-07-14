"""Unit tests for the SRS interval helper and per-rating scheduling.

Uses stdlib unittest only (no pytest dependency in this project).

Run directly:      python tests/test_srs_schedule.py
Or via discovery:   python -m unittest discover -s tests
"""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import compute_review_schedule, get_srs_interval  # noqa: E402


class GetSrsIntervalTests(unittest.TestCase):
    def test_known_levels(self):
        expected = {
            0: timedelta(minutes=5),
            1: timedelta(minutes=15),
            2: timedelta(minutes=30),
            3: timedelta(hours=3),
            4: timedelta(hours=12),
            5: timedelta(days=1),
            6: timedelta(days=3),
            7: timedelta(days=7),
            8: timedelta(days=14),
            9: timedelta(days=30),
            10: timedelta(days=60),
            11: timedelta(days=90),
            99: timedelta(days=90),
        }
        for level, interval in expected.items():
            with self.subTest(level=level):
                self.assertEqual(get_srs_interval(level), interval)

    def test_negative_level_is_clamped_to_zero(self):
        self.assertEqual(get_srs_interval(-1), timedelta(minutes=5))
        self.assertEqual(get_srs_interval(-100), timedelta(minutes=5))


class ComputeReviewScheduleTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def test_again_resets_to_level_zero_and_due_in_five_minutes(self):
        level, next_review_at = compute_review_schedule("again", 7, self.now)
        self.assertEqual(level, 0)
        self.assertEqual(next_review_at, (self.now + timedelta(minutes=5)).isoformat())

    def test_hard_from_level_zero_advances_to_one(self):
        level, _ = compute_review_schedule("hard", 0, self.now)
        self.assertEqual(level, 1)

    def test_hard_from_level_five_steps_back_to_four(self):
        level, next_review_at = compute_review_schedule("hard", 5, self.now)
        self.assertEqual(level, 4)
        self.assertEqual(next_review_at, (self.now + timedelta(hours=12)).isoformat())

    def test_hard_never_drops_below_level_one(self):
        level, _ = compute_review_schedule("hard", 1, self.now)
        self.assertEqual(level, 1)

    def test_good_advances_one_level(self):
        level, next_review_at = compute_review_schedule("good", 3, self.now)
        self.assertEqual(level, 4)
        self.assertEqual(next_review_at, (self.now + timedelta(hours=12)).isoformat())

    def test_easy_advances_two_levels(self):
        level, next_review_at = compute_review_schedule("easy", 3, self.now)
        self.assertEqual(level, 5)
        self.assertEqual(next_review_at, (self.now + timedelta(days=1)).isoformat())


if __name__ == "__main__":
    unittest.main()

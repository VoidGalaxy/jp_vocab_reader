"""Tests for the pure FSRS engine adapter (app/srs/engine.py).

Runs the real pinned `fsrs` library; no database, no clock. Expected values
are what the library returns under the approved config -- they document the
engine, they are not hand-written formulas.

Run directly:      python tests/test_srs_engine.py
Or via discovery:   python -m unittest discover -s tests
"""

from __future__ import annotations

import math
import sys
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.srs import engine  # noqa: E402
from app.srs.engine import (  # noqa: E402
    DEFAULT_CONFIG,
    CardKey,
    SrsCardState,
    SrsEngineError,
    SrsPhase,
    preview_due,
    retrievability,
    review,
    state_from_dict,
    state_from_json,
    state_to_dict,
    state_to_json,
)

T0 = datetime(2026, 10, 9, 3, 0, tzinfo=timezone.utc)
KEY = CardKey("personal", 1, 5)
KST = timezone(timedelta(hours=9))


def chain(ratings_and_times, key=KEY, state=None):
    for rating, at in ratings_and_times:
        state = review(key, state, rating, at).after
    return state


def to_review(at=T0):
    """Unreviewed -> Easy puts the card straight into Review (library rule)."""
    return review(KEY, None, "easy", at).after


class LibraryAndConfigTests(unittest.TestCase):
    def test_pinned_version_installed(self):
        self.assertEqual(engine.installed_library_version(), "6.3.2")
        engine.assert_pinned_library()

    def test_approved_config(self):
        config = DEFAULT_CONFIG
        self.assertEqual(config.desired_retention, 0.90)
        self.assertEqual(config.learning_steps_seconds, (60, 600))
        self.assertEqual(config.relearning_steps_seconds, (600,))
        self.assertEqual(config.maximum_interval_days, 365)
        self.assertFalse(config.enable_fuzzing)
        self.assertEqual(len(config.parameters), 21)
        scheduler = engine.build_scheduler()
        self.assertEqual(scheduler.parameters, config.parameters)
        self.assertFalse(scheduler.enable_fuzzing)

    def test_config_version_is_stable_and_tracks_changes(self):
        self.assertEqual(DEFAULT_CONFIG.config_version, replace(DEFAULT_CONFIG).config_version)
        self.assertTrue(DEFAULT_CONFIG.config_version.startswith("fsrs-6.3.2-a1-"))
        changed = replace(DEFAULT_CONFIG, maximum_interval_days=366)
        self.assertNotEqual(DEFAULT_CONFIG.config_version, changed.config_version)
        self.assertEqual(DEFAULT_CONFIG.to_dict()["library_version"], "6.3.2")


class ConfigSourceTests(unittest.TestCase):
    """Gate B-1 correction: the schedule and the recorded config_version must
    come from the same config. Before it, review() accepted an outside
    scheduler, so a 0.99-retention schedule could be recorded as the default."""

    def setUp(self):
        self.addCleanup(engine._scheduler_for.cache_clear)

    def test_review_no_longer_accepts_an_outside_scheduler(self):
        with self.assertRaises(TypeError):
            review(KEY, None, "good", T0, DEFAULT_CONFIG, engine.build_scheduler())

    def test_recorded_version_matches_the_config_that_computed_the_due(self):
        strict = replace(DEFAULT_CONFIG, desired_retention=0.99)
        card = to_review()
        at = card.due_at
        default_outcome = review(KEY, card, "good", at)
        strict_outcome = review(KEY, card, "good", at, strict)
        self.assertEqual(default_outcome.config_version, DEFAULT_CONFIG.config_version)
        self.assertEqual(strict_outcome.config_version, strict.config_version)
        self.assertNotEqual(strict_outcome.config_version, DEFAULT_CONFIG.config_version)
        self.assertLess(strict_outcome.after.due_at, default_outcome.after.due_at)
        # Same due as a scheduler built directly from that config.
        library_card, _ = engine.build_scheduler(strict).review_card(
            engine._to_library_card(KEY.ref_id, card, at), engine.RATINGS["good"], review_datetime=at
        )
        self.assertEqual(strict_outcome.after.due_at, library_card.due)

    def test_scheduler_settings_equal_the_config(self):
        for config in (DEFAULT_CONFIG, replace(DEFAULT_CONFIG, desired_retention=0.95, maximum_interval_days=200)):
            with self.subTest(config=config.config_version):
                scheduler = engine._scheduler_for(config)
                self.assertEqual(engine._scheduler_settings(scheduler), engine._config_settings(config))

    def test_fuzzing_config_is_refused(self):
        fuzzy = replace(DEFAULT_CONFIG, enable_fuzzing=True)
        with self.assertRaises(SrsEngineError):
            engine.build_scheduler(fuzzy)
        with self.assertRaises(SrsEngineError):
            review(KEY, None, "good", T0, fuzzy)

    def test_library_version_check_runs_before_any_review(self):
        engine._scheduler_for.cache_clear()
        with mock.patch.object(engine, "installed_library_version", return_value="6.3.1"):
            with self.assertRaises(SrsEngineError):
                review(KEY, None, "good", T0)
        engine._scheduler_for.cache_clear()
        self.assertEqual(review(KEY, None, "good", T0).config_version, DEFAULT_CONFIG.config_version)


class StepRangeTests(unittest.TestCase):
    """Gate C-1 correction: out-of-config steps are rejected, never promoted."""

    def make(self, phase, step):
        return SrsCardState(phase=phase, step=step, stability=2.3, difficulty=5.0,
                            due_at=T0, last_review_at=T0 - timedelta(minutes=10))

    def test_out_of_range_steps_are_rejected(self):
        for phase, step in [(SrsPhase.LEARNING, 2), (SrsPhase.LEARNING, 999), (SrsPhase.RELEARNING, 1)]:
            with self.subTest(phase=phase.value, step=step):
                with self.assertRaises(SrsEngineError):
                    review(KEY, self.make(phase, step), "good", T0)
                with self.assertRaises(SrsEngineError):
                    engine.validate_state_for_config(self.make(phase, step), DEFAULT_CONFIG)

    def test_in_range_steps_are_accepted(self):
        for phase, step in [(SrsPhase.LEARNING, 0), (SrsPhase.LEARNING, 1), (SrsPhase.RELEARNING, 0)]:
            with self.subTest(phase=phase.value, step=step):
                engine.validate_state_for_config(self.make(phase, step), DEFAULT_CONFIG)
                self.assertIsNotNone(review(KEY, self.make(phase, step), "good", T0).after)


class FirstReviewTests(unittest.TestCase):
    def test_four_ratings_from_unreviewed(self):
        expected = {
            "again": (SrsPhase.LEARNING, 0, timedelta(minutes=1)),
            "hard": (SrsPhase.LEARNING, 0, timedelta(minutes=5, seconds=30)),
            "good": (SrsPhase.LEARNING, 1, timedelta(minutes=10)),
            "easy": (SrsPhase.REVIEW, None, timedelta(days=8)),
        }
        for rating, (phase, step, interval) in expected.items():
            with self.subTest(rating=rating):
                outcome = review(KEY, None, rating, T0)
                self.assertTrue(outcome.is_first_review)
                self.assertIsNone(outcome.elapsed_seconds)
                self.assertEqual(outcome.after.phase, phase)
                self.assertEqual(outcome.after.step, step)
                self.assertEqual(outcome.after.due_at - T0, interval)
                self.assertEqual(outcome.after.last_review_at, T0)

    def test_first_good_rechecks_after_ten_minutes_then_enters_review(self):
        first = review(KEY, None, "good", T0).after
        second = review(KEY, first, "good", first.due_at)
        self.assertFalse(second.is_first_review)
        self.assertEqual(second.elapsed_seconds, 600)
        self.assertEqual(second.after.phase, SrsPhase.REVIEW)
        self.assertIsNone(second.after.step)
        self.assertGreaterEqual(second.after.due_at - second.reviewed_at, timedelta(days=1))


class TransitionTests(unittest.TestCase):
    def test_learning_step_one_again_and_hard(self):
        step1 = review(KEY, None, "good", T0).after
        again = review(KEY, step1, "again", step1.due_at).after
        self.assertEqual((again.phase, again.step), (SrsPhase.LEARNING, 0))
        self.assertEqual(again.due_at - step1.due_at, timedelta(minutes=1))
        hard = review(KEY, step1, "hard", step1.due_at).after
        self.assertEqual((hard.phase, hard.step), (SrsPhase.LEARNING, 1))
        self.assertEqual(hard.due_at - step1.due_at, timedelta(minutes=10))

    def test_review_again_relearns_for_ten_minutes_and_returns(self):
        card = to_review()
        at = card.due_at
        lapsed = review(KEY, card, "again", at).after
        self.assertEqual((lapsed.phase, lapsed.step), (SrsPhase.RELEARNING, 0))
        self.assertEqual(lapsed.due_at - at, timedelta(minutes=10))
        self.assertLess(lapsed.stability, card.stability)
        hard = review(KEY, lapsed, "hard", lapsed.due_at).after
        self.assertEqual((hard.phase, hard.due_at - lapsed.due_at), (SrsPhase.RELEARNING, timedelta(minutes=15)))
        back = review(KEY, lapsed, "good", lapsed.due_at).after
        self.assertEqual(back.phase, SrsPhase.REVIEW)
        self.assertGreaterEqual(back.due_at - lapsed.due_at, timedelta(days=1))

    def test_review_successes_grow_interval(self):
        card = to_review()
        intervals = []
        for _ in range(4):
            at = card.due_at
            card = review(KEY, card, "good", at).after
            intervals.append(card.due_at - at)
        self.assertEqual(intervals, sorted(intervals))
        self.assertGreater(intervals[-1], intervals[0])

    def test_same_day_uses_elapsed_time_not_calendar_dates(self):
        card = to_review(datetime(2026, 10, 9, 23, 30, tzinfo=timezone.utc))
        # 1 hour later crosses UTC (and Seoul) midnight but is < 24h: short-term branch.
        early = review(KEY, card, "good", card.last_review_at + timedelta(hours=1)).after
        late = review(KEY, card, "good", card.last_review_at + timedelta(hours=25)).after
        self.assertNotEqual(early.stability, late.stability)
        self.assertEqual(early.phase, SrsPhase.REVIEW)

    def test_long_overdue_and_maximum_interval(self):
        card = to_review()
        overdue = review(KEY, card, "good", card.due_at + timedelta(days=200)).after
        self.assertEqual(overdue.phase, SrsPhase.REVIEW)
        self.assertLessEqual(overdue.due_at - overdue.last_review_at, timedelta(days=365))
        for _ in range(12):
            card = review(KEY, card, "easy", card.due_at).after
            self.assertLessEqual(card.due_at - card.last_review_at, timedelta(days=365))
        self.assertEqual(card.due_at - card.last_review_at, timedelta(days=365))

    def test_deterministic_without_fuzz(self):
        events = [("good", T0), ("good", T0 + timedelta(minutes=10)), ("hard", T0 + timedelta(days=3))]
        self.assertEqual(chain(events), chain(events))

    def test_non_utc_aware_input_is_same_instant(self):
        kst = T0.astimezone(KST)
        self.assertEqual(review(KEY, None, "good", kst).after, review(KEY, None, "good", T0).after)


class ValidationTests(unittest.TestCase):
    def test_rejects_naive_and_backwards_time_and_bad_rating(self):
        with self.assertRaises(SrsEngineError):
            review(KEY, None, "good", datetime(2026, 10, 9))
        card = to_review()
        with self.assertRaises(SrsEngineError):
            review(KEY, card, "good", card.last_review_at - timedelta(seconds=1))
        with self.assertRaises(SrsEngineError):
            review(KEY, None, "perfect", T0)

    def test_rejects_invalid_states(self):
        good = to_review()
        bad = [
            dict(step=0),  # review with a step
            dict(phase=SrsPhase.LEARNING, step=None),
            dict(stability=math.nan),
            dict(stability=0.0),
            dict(difficulty=10.5),
            dict(due_at=good.last_review_at - timedelta(days=1)),
            dict(last_review_at=datetime(2026, 10, 9)),
        ]
        for change in bad:
            with self.subTest(change=change), self.assertRaises(SrsEngineError):
                replace(good, **change)

    def test_rejects_bad_keys(self):
        for args in [("deck", 1, 1), ("personal", 0, 1), ("lexeme", 1, True), ("personal", 1, "5")]:
            with self.subTest(args=args), self.assertRaises(SrsEngineError):
                CardKey(*args)


class SerializationTests(unittest.TestCase):
    def test_round_trip_dict_and_json(self):
        for state in [None, review(KEY, None, "again", T0).after, to_review()]:
            with self.subTest(state=state):
                self.assertEqual(state_from_dict(state_to_dict(state)), state)
                self.assertEqual(state_from_json(state_to_json(state)), state)

    def test_continuing_from_deserialized_state_matches(self):
        card = review(KEY, None, "good", T0).after
        restored = state_from_json(state_to_json(card))
        at = card.due_at
        self.assertEqual(review(KEY, card, "good", at).after, review(KEY, restored, "good", at).after)

    def test_rejects_unknown_or_missing_keys_and_bad_values(self):
        data = state_to_dict(to_review())
        for broken in [
            {**data, "extra": 1},
            {k: v for k, v in data.items() if k != "difficulty"},
            {**data, "phase": "new"},
            {**data, "due_at": "2026-10-09T00:00:00"},
            {**data, "stability": "3"},
        ]:
            with self.subTest(broken=broken), self.assertRaises(SrsEngineError):
                state_from_dict(broken)
        with self.assertRaises(SrsEngineError):
            state_from_json("{not json")


class IdentityAndHelpersTests(unittest.TestCase):
    def test_same_numeric_ref_different_kinds_stay_separate(self):
        personal = CardKey("personal", 1, 5)
        lexeme = CardKey("lexeme", 1, 5)
        self.assertNotEqual(personal, lexeme)
        a = review(personal, None, "again", T0)
        b = review(lexeme, None, "easy", T0)
        self.assertEqual(a.key, personal)
        self.assertEqual(b.key, lexeme)
        self.assertNotEqual(a.after, b.after)

    def test_preview_due_is_read_only(self):
        card = to_review()
        before = state_to_json(card)
        preview = preview_due(KEY, card, card.due_at)
        self.assertEqual(set(preview), {"again", "hard", "good", "easy"})
        self.assertLess(preview["again"], preview["good"])
        self.assertEqual(state_to_json(card), before)

    def test_retrievability(self):
        self.assertIsNone(retrievability(None, T0))
        card = to_review()
        r = retrievability(card, card.due_at)
        self.assertTrue(0.88 <= r <= 0.92, r)


if __name__ == "__main__":
    unittest.main()

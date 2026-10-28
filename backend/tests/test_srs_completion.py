"""Tests for '학습 완료' completion (app/srs/completion.py), V3 `meaning-completion-v1`
(approved 2026-10-17, Gate D-2 U11). Gate D-2 U11 moved the expectations of the
draft rule (2 dates, 1 spaced success) to V3 (3 dates, 2 spaced successes); these
tests pin the rules, not a learning-effect claim.

Run directly:      python tests/test_srs_completion.py
Or via discovery:   python -m unittest discover -s tests
"""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.srs.completion import (  # noqa: E402
    CompletionStatus,
    ReviewEvent,
    evaluate_completion,
    replay_with_completion,
    seoul_date,
    summarize_completion,
)
from app.srs.engine import CardKey, SrsCardState, SrsEngineError, SrsPhase, review  # noqa: E402

UTC = timezone.utc
T0 = datetime(2026, 10, 9, 3, 0, tzinfo=UTC)
KEY = CardKey("lexeme", 7, 42)


def review_state(stability=40.0, last=T0, phase=SrsPhase.REVIEW, step=None):
    return SrsCardState(
        phase=phase, step=step, stability=stability, difficulty=5.0,
        due_at=last + timedelta(days=30), last_review_at=last,
    )


def events(*pairs):
    return [ReviewEvent(at, rating) for rating, at in pairs]


def follow_due(ratings, start=T0):
    """Rate exactly when the engine says the card is due."""
    state, at, evs = None, start, []
    for rating in ratings:
        state = review(KEY, state, rating, at).after
        evs.append(ReviewEvent(at, rating))
        at = state.due_at
    return state, evs


class CriteriaTests(unittest.TestCase):
    def test_unreviewed_is_not_completed(self):
        check = evaluate_completion(None, [], evidence_complete=True)
        self.assertEqual(check.status, CompletionStatus.NOT_COMPLETED)

    def test_first_easy_is_not_completed(self):
        state, evs = follow_due(["easy"])
        check = evaluate_completion(state, evs, evidence_complete=True)
        self.assertEqual(check.status, CompletionStatus.NOT_COMPLETED)
        self.assertFalse(check.stability_ok)
        self.assertFalse(check.success_dates_ok)

    def test_same_day_repeats_are_not_completed(self):
        state, evs = None, []
        for minutes in range(0, 300, 10):
            at = T0 + timedelta(minutes=minutes)
            state = review(KEY, state, "easy", at).after
            evs.append(ReviewEvent(at, "easy"))
        check = evaluate_completion(state, evs, evidence_complete=True)
        self.assertEqual(check.status, CompletionStatus.NOT_COMPLETED)
        self.assertFalse(check.success_dates_ok)
        self.assertFalse(check.spaced_success_ok)

    def test_all_four_criteria_on_a_synthetic_state(self):
        evs = events(("good", T0), ("good", T0 + timedelta(days=7)), ("good", T0 + timedelta(days=14)))
        state = review_state(last=T0 + timedelta(days=14))
        check = evaluate_completion(state, evs, evidence_complete=True)
        self.assertEqual(check.status, CompletionStatus.COMPLETED, check.reasons)

    def test_each_criterion_can_block(self):
        evs = events(("good", T0), ("good", T0 + timedelta(days=7)))
        last = T0 + timedelta(days=7)
        cases = {
            "not_review_phase": review_state(last=last, phase=SrsPhase.RELEARNING, step=0),
            "stability_below_threshold": review_state(stability=29.99, last=last),
        }
        for reason, state in cases.items():
            with self.subTest(reason=reason):
                check = evaluate_completion(state, evs, evidence_complete=True)
                self.assertEqual(check.status, CompletionStatus.NOT_COMPLETED)
                self.assertIn(reason, check.reasons)

    def test_seven_day_boundary_is_exact(self):
        base = [("good", T0), ("good", T0 + timedelta(days=7))]  # one spaced success
        exact = T0 + timedelta(days=14)
        short = exact - timedelta(seconds=1)
        ok = evaluate_completion(review_state(last=exact), events(*base, ("good", exact)), evidence_complete=True)
        self.assertTrue(ok.spaced_success_ok)
        no = evaluate_completion(review_state(last=short), events(*base, ("good", short)), evidence_complete=True)
        self.assertFalse(no.spaced_success_ok)
        self.assertEqual(no.status, CompletionStatus.NOT_COMPLETED)

    def test_spaced_gap_is_measured_from_the_preceding_review(self):
        # Success 8 days after the first, but only 1 hour after an intermediate review.
        d8 = T0 + timedelta(days=8)
        evs = events(("good", T0), ("good", d8 - timedelta(hours=1)), ("good", d8))
        check = evaluate_completion(review_state(last=d8), evs, evidence_complete=True)
        self.assertFalse(check.spaced_success_ok)  # only the middle one (8d-1h after T0) counts
        d16 = d8 + timedelta(days=8)
        evs.append(ReviewEvent(d16, "good"))
        check = evaluate_completion(review_state(last=d16), evs, evidence_complete=True)
        self.assertTrue(check.spaced_success_ok)  # the middle one and the last one
        evs = events(("good", T0), ("good", T0 + timedelta(days=6)), ("good", T0 + timedelta(days=12)))
        check = evaluate_completion(review_state(last=T0 + timedelta(days=12)), evs, evidence_complete=True)
        self.assertFalse(check.spaced_success_ok)

    def test_only_successes_after_last_again_count_and_hard_is_success(self):
        d20 = T0 + timedelta(days=20)
        evs = events(("good", T0), ("good", T0 + timedelta(days=10)), ("again", d20), ("hard", d20 + timedelta(days=1)))
        check = evaluate_completion(review_state(last=d20 + timedelta(days=1)), evs, evidence_complete=True)
        self.assertFalse(check.success_dates_ok)  # one success date after the Again
        evs.append(ReviewEvent(d20 + timedelta(days=9), "hard"))
        check = evaluate_completion(review_state(last=d20 + timedelta(days=9)), evs, evidence_complete=True)
        self.assertFalse(check.success_dates_ok)  # two dates, one spaced success
        evs.append(ReviewEvent(d20 + timedelta(days=17), "hard"))
        check = evaluate_completion(review_state(last=d20 + timedelta(days=17)), evs, evidence_complete=True)
        self.assertEqual(check.status, CompletionStatus.COMPLETED, check.reasons)

    def test_seoul_date_boundary(self):
        a = datetime(2026, 10, 9, 14, 59, tzinfo=UTC)  # 23:59 KST 10/9
        b = datetime(2026, 10, 9, 15, 1, tzinfo=UTC)   # 00:01 KST 10/10
        self.assertNotEqual(seoul_date(a), seoul_date(b))
        c = datetime(2026, 10, 10, 14, 59, tzinfo=UTC)  # 23:59 KST 10/10
        self.assertEqual(seoul_date(b), seoul_date(c))
        # Same UTC date, two Seoul dates -> counts as two.
        last = a + timedelta(days=7)
        evs = events(("good", a), ("good", b), ("good", last))
        check = evaluate_completion(review_state(last=last), evs, evidence_complete=True)
        self.assertTrue(check.success_dates_ok)

    def test_rejects_unordered_or_invalid_events(self):
        with self.assertRaises(SrsEngineError):
            evaluate_completion(review_state(), events(("good", T0), ("good", T0 - timedelta(days=1))), evidence_complete=True)
        with self.assertRaises(SrsEngineError):
            evaluate_completion(review_state(), events(("perfect", T0)), evidence_complete=True)
        with self.assertRaises(SrsEngineError):
            evaluate_completion(review_state(), [ReviewEvent(datetime(2026, 10, 9), "good")], evidence_complete=True)


class EvidenceTests(unittest.TestCase):
    def test_incomplete_evidence_distinguishes_unknown_from_failure(self):
        last = T0 + timedelta(days=40)
        partial = events(("good", last))  # earlier reviews are missing
        unknown = evaluate_completion(review_state(last=last), partial, evidence_complete=False)
        self.assertEqual(unknown.status, CompletionStatus.UNKNOWN)
        self.assertIsNone(unknown.success_dates_ok)
        failed = evaluate_completion(review_state(stability=5.0, last=last), partial, evidence_complete=False)
        self.assertEqual(failed.status, CompletionStatus.NOT_COMPLETED)
        no_state = evaluate_completion(None, partial, evidence_complete=False)
        self.assertEqual(no_state.status, CompletionStatus.UNKNOWN)

    def test_partial_evidence_never_proves_completion(self):
        # Before the Gate B-1 correction this returned COMPLETED: the present
        # reviews looked sufficient, but a missing one could hide an Again,
        # or a shorter gap before the 7-day success.
        last = T0 + timedelta(days=7)
        check = evaluate_completion(review_state(last=last), events(("good", T0), ("good", last)), evidence_complete=False)
        self.assertEqual(check.status, CompletionStatus.UNKNOWN)
        self.assertIsNone(check.success_dates_ok)
        self.assertIsNone(check.spaced_success_ok)
        self.assertIn("incomplete_evidence", check.reasons)


def _engine_history(pairs):
    """Real engine states for (rating, time) pairs, from an unreviewed card."""
    state = None
    for rating, at in pairs:
        state = review(KEY, state, rating, at).after
    return state, events(*pairs)


class IncompleteHistoryRegressionTests(unittest.TestCase):
    def test_missing_middle_review_does_not_create_a_false_seven_day_gap(self):
        # Reported case: easy -> hard 6 days later -> easy on day 8.
        pairs = [("easy", T0), ("hard", T0 + timedelta(days=6)), ("easy", T0 + timedelta(days=8))]
        state, full = _engine_history(pairs)
        self.assertGreaterEqual(state.stability, 30)  # C1/C2 hold, so only the history decides
        whole = evaluate_completion(state, full, evidence_complete=True)
        self.assertEqual(whole.status, CompletionStatus.NOT_COMPLETED)
        self.assertFalse(whole.spaced_success_ok)  # real gaps are 6d and 2d
        partial = evaluate_completion(state, [full[0], full[2]], evidence_complete=False)
        self.assertEqual(partial.status, CompletionStatus.UNKNOWN)

    def test_missing_middle_again_is_not_completion(self):
        pairs = [
            ("easy", T0), ("good", T0 + timedelta(days=8)), ("again", T0 + timedelta(days=60)),
            ("good", T0 + timedelta(days=60, minutes=10)), ("good", T0 + timedelta(days=63)),
        ]
        state, full = _engine_history(pairs)
        whole = evaluate_completion(state, full, evidence_complete=True)
        self.assertEqual(whole.status, CompletionStatus.NOT_COMPLETED)
        without_again = [e for e in full if e.rating != "again"]
        partial = evaluate_completion(state, without_again, evidence_complete=False)
        self.assertNotEqual(partial.status, CompletionStatus.COMPLETED)

    def test_old_history_with_newer_state_is_never_completed(self):
        old_state, old_events = follow_due(["easy", "easy", "easy"])
        self.assertEqual(
            evaluate_completion(old_state, old_events, evidence_complete=True).status, CompletionStatus.COMPLETED
        )
        newer = review(KEY, old_state, "again", old_state.due_at).after
        newer = review(KEY, newer, "good", newer.due_at).after
        newer = review(KEY, newer, "good", newer.due_at).after
        for complete in (True, False):
            with self.subTest(evidence_complete=complete):
                check = evaluate_completion(newer, old_events, evidence_complete=complete)
                self.assertNotEqual(check.status, CompletionStatus.COMPLETED)
        self.assertEqual(
            evaluate_completion(newer, old_events, evidence_complete=True).reasons, ("state_event_mismatch",)
        )

    def test_incomplete_history_unknown_or_plainly_not_completed(self):
        pairs = [("good", T0), ("good", T0 + timedelta(minutes=10))]
        young, evs = _engine_history(pairs)  # Review, S about 2 days
        plainly = evaluate_completion(young, evs[-1:], evidence_complete=False)
        self.assertEqual(plainly.status, CompletionStatus.NOT_COMPLETED)
        self.assertIn("stability_below_threshold", plainly.reasons)
        mature = review_state(stability=45.0, last=T0 + timedelta(days=50))
        self.assertEqual(
            evaluate_completion(mature, events(("good", mature.last_review_at)), evidence_complete=False).status,
            CompletionStatus.UNKNOWN,
        )
        self.assertEqual(evaluate_completion(None, evs, evidence_complete=False).status, CompletionStatus.UNKNOWN)

    def test_complete_normal_history_still_completes_and_keeps_first_completion(self):
        state, full = follow_due(["easy", "easy", "easy"])
        self.assertEqual(evaluate_completion(state, full, evidence_complete=True).status, CompletionStatus.COMPLETED)
        steps = replay_with_completion(KEY, full + [ReviewEvent(state.due_at, "again")])
        self.assertEqual(steps[-1].check.status, CompletionStatus.NOT_COMPLETED)
        self.assertEqual(steps[-1].first_completed_at, full[-1].reviewed_at)

    def test_state_that_does_not_match_events_is_unknown(self):
        evs = events(("good", T0), ("good", T0 + timedelta(days=7)))
        check = evaluate_completion(review_state(last=T0 + timedelta(days=9)), evs, evidence_complete=True)
        self.assertEqual(check.status, CompletionStatus.UNKNOWN)
        self.assertIn("state_event_mismatch", check.reasons)


class HistoryAndParticipationTests(unittest.TestCase):
    def _completed_replay(self):
        state, evs = None, []
        at = T0
        for _ in range(12):
            state = review(KEY, state, "good", at).after
            evs.append(ReviewEvent(at, "good"))
            if evaluate_completion(state, evs, evidence_complete=True).status is CompletionStatus.COMPLETED:
                return state, evs
            at = state.due_at
        self.fail("synthetic good-at-due chain did not complete within 12 reviews")

    def test_failure_keeps_first_completion_and_flags_relearning(self):
        state, evs = self._completed_replay()
        done = evaluate_completion(state, evs, evidence_complete=True)
        first = summarize_completion(done, participation="active", previous_first_completed_at=None, evaluated_at=evs[-1].reviewed_at)
        self.assertEqual(first.first_completed_at, evs[-1].reviewed_at)
        self.assertTrue(first.counts_toward_progress)

        fail_at = state.due_at
        lapsed = review(KEY, state, "again", fail_at).after
        evs_after = evs + [ReviewEvent(fail_at, "again")]
        check = evaluate_completion(lapsed, evs_after, evidence_complete=True)
        record = summarize_completion(check, participation="active", previous_first_completed_at=first.first_completed_at, evaluated_at=fail_at)
        self.assertEqual(check.status, CompletionStatus.NOT_COMPLETED)
        self.assertEqual(record.first_completed_at, first.first_completed_at)
        self.assertTrue(record.needs_relearning)
        self.assertFalse(record.counts_toward_progress)

    def test_pause_and_resume(self):
        state, evs = self._completed_replay()
        done = evaluate_completion(state, evs, evidence_complete=True)
        paused = summarize_completion(done, participation="paused", previous_first_completed_at=None, evaluated_at=evs[-1].reviewed_at)
        self.assertFalse(paused.counts_toward_progress)
        self.assertIsNotNone(paused.first_completed_at)
        resumed = summarize_completion(done, participation="active", previous_first_completed_at=paused.first_completed_at, evaluated_at=evs[-1].reviewed_at)
        self.assertTrue(resumed.counts_toward_progress)
        self.assertEqual(resumed.first_completed_at, paused.first_completed_at)
        with self.assertRaises(SrsEngineError):
            summarize_completion(done, participation="left", previous_first_completed_at=None, evaluated_at=T0)

    def test_replay_marks_first_completion_once(self):
        state, evs = self._completed_replay()
        evs = evs + [ReviewEvent(state.due_at, "again")]
        steps = replay_with_completion(KEY, evs)
        statuses = [step.check.status for step in steps]
        self.assertEqual(statuses[-2], CompletionStatus.COMPLETED)
        self.assertEqual(statuses[-1], CompletionStatus.NOT_COMPLETED)
        self.assertEqual(steps[-1].first_completed_at, steps[-2].outcome.reviewed_at)
        self.assertEqual(sum(1 for s in statuses if s is CompletionStatus.COMPLETED), 1)


if __name__ == "__main__":
    unittest.main()

"""Gate D-2 U7: first FSRS review of U5-converted incomplete-history cards.

Synthetic SQLite only (QueueCase sets a throwaway DATABASE_URL per test before the
app touches a database). Rollback and re-conversion (U8) are covered in
test_srs_d2_rollback_reconvert.py.

Run directly:      python tests/test_srs_d2_first_review.py
Or via discovery:   python -m unittest discover -s tests
"""

from __future__ import annotations

import json
import sys
import unittest
from datetime import timedelta
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_srs_d2_serve import ServeCase  # noqa: E402
from test_srs_queue import NOW, iso  # noqa: E402
import race_support  # noqa: E402

from app.database import get_connection  # noqa: E402
from app.srs import completion, engine, identity, migration, reviews  # noqa: E402
from app.srs.engine import CardKey, state_from_json, state_to_dict  # noqa: E402
from app.srs.storage import SrsWriteError  # noqa: E402

RATINGS = ("again", "hard", "good", "easy")


class FirstReviewCase(ServeCase):
    def req(self, n):
        return f"00000000-0000-4000-8000-{n:012d}"

    def rate_at(self, kind, ref, at, rating="good", request=None, deck=None):
        version = (self.row(ref)["srs_card_version"] if kind == "personal"
                   else self.row(ref, "user_word_progress", "lexeme_id")["srs_card_version"])
        self.now = at
        return self.rate(kind, ref, grade=rating, at=at, request=request or self.req(ref * 100 + version), version=version,
                         deck=deck)

    def logs_of(self, kind, ref):
        table, col = ("review_logs", "vocab_item_id") if kind == "personal" else ("lexeme_review_logs", "lexeme_id")
        with get_connection() as c:
            return [dict(r) for r in c.execute(f"SELECT * FROM {table} WHERE user_id = ? AND {col} = ? ORDER BY id",
                                               (self.user, ref)).fetchall()]

    def boundary(self, kind, ref):
        row = self.row(ref) if kind == "personal" else self.row(ref, "user_word_progress", "lexeme_id")
        return row["evidence_from_log_id"]

    def snapshot_all(self):
        return self.everything()


# ---------------------------------------------------------------------------
class EngineInitialisationTests(FirstReviewCase):
    def test_personal_each_rating_uses_the_library_first_review(self):
        for rating in RATINGS:
            with self.subTest(rating=rating):
                card = self.incomplete(f"p-{rating}", iso(NOW - timedelta(hours=1)))
                result = self.rate_at("personal", card, NOW, rating)
                expected = engine.review(CardKey("personal", self.user, card), None, rating, NOW).after
                self.assertEqual(result["srs"]["state"], state_to_dict(expected))  # H3-a: no state in, default out
                logs = self.logs_of("personal", card)
                fsrs = [log for log in logs if log["srs_engine"] == "fsrs"]
                self.assertEqual(len(fsrs), 1)
                self.assertEqual((fsrs[0]["is_first_review"], fsrs[0]["srs_before_json"]), (1, "null"))
                self.assertEqual(self.boundary("personal", card), fsrs[0]["id"])
                # The next review starts from that state.
                second = self.rate_at("personal", card, NOW + timedelta(days=10), "good")
                after_first = state_from_json(fsrs[0]["srs_after_json"])
                again = engine.review(CardKey("personal", self.user, card), after_first, "good", NOW + timedelta(days=10)).after
                self.assertEqual(second["srs"]["state"], state_to_dict(again))
                self.assertEqual(self.logs_of("personal", card)[-1]["is_first_review"], 0)
                self.assertEqual(self.boundary("personal", card), fsrs[0]["id"])  # not moved
                self.now = NOW

    def test_subscribed_each_rating_uses_the_library_first_review(self):
        deck = self.shared_deck("s")
        for index, rating in enumerate(RATINGS):
            with self.subTest(rating=rating):
                lexeme = self.incomplete_lexeme(deck, f"l-{rating}", index, iso(NOW - timedelta(hours=1)))
                result = self.rate_at("lexeme", lexeme, NOW, rating, deck=deck)
                expected = engine.review(CardKey("lexeme", self.user, lexeme), None, rating, NOW).after
                self.assertEqual(result["srs"]["state"], state_to_dict(expected))
                fsrs = [log for log in self.logs_of("lexeme", lexeme) if log["srs_engine"] == "fsrs"]
                self.assertEqual((len(fsrs), fsrs[0]["is_first_review"]), (1, 1))
                self.assertEqual(self.boundary("lexeme", lexeme), fsrs[0]["id"])
                self.rate_at("lexeme", lexeme, NOW + timedelta(days=10), "good", deck=deck)
                self.assertEqual(self.boundary("lexeme", lexeme), fsrs[0]["id"])
                self.now = NOW


# ---------------------------------------------------------------------------
class NewCountAndEvidenceTests(FirstReviewCase):
    def test_zero_log_past_card_is_not_new_and_unknown_mark_stays_unknown(self):
        past = self.incomplete("past", iso(NOW - timedelta(hours=1)))
        before = self.count(NOW)
        result = self.rate_at("personal", past, NOW)
        self.assertEqual((self.count(NOW).status, self.count(NOW).count), (before.status, before.count))
        self.assertEqual(result["srs"]["introduced_today"], before.count)
        self.assertEqual(self.mark(past), ("before_tracking", "2026-09-30"))
        unknown = self.personal("unknown")
        with get_connection() as c:
            c.execute("UPDATE vocab_items SET correct_count = 2, last_reviewed_at = NULL, next_review_at = ? WHERE id = ?",
                      (iso(NOW - timedelta(hours=1)), unknown))
        migration.apply_plan(self.plan(unknown), "run-unknown", approved=True)
        self.assertEqual(self.mark(unknown), ("unknown", None))
        self.rate_at("personal", unknown, NOW)
        self.assertEqual(self.count(NOW).status, "unknown")  # still unknown, never narrowed to exact

    def test_old_legacy_logs_are_outside_the_evidence_window(self):
        card = self.personal("old-history")
        for days, rating in ((70, "good"), (60, "good"), (50, "again"), (40, "good"), (30, "easy")):
            self.raw_log(card, NOW - timedelta(days=days), rating=rating)
        with get_connection() as c:  # counters/card values that do not match the logs -> incomplete
            c.execute("UPDATE vocab_items SET last_reviewed_at = ?, correct_count = 9, next_review_at = ? WHERE id = ?",
                      (iso(NOW - timedelta(days=30)), iso(NOW - timedelta(hours=1)), card))
        self.assertEqual(migration.apply_plan(self.plan(card), "run-old", approved=True)[0]["result"], "applied")
        intro = self.count(NOW)
        captured = []
        real = reviews.evaluate_completion

        def spy(state, events, *, evidence_complete):
            captured.append((list(events), evidence_complete))
            return real(state, events, evidence_complete=evidence_complete)

        with mock.patch.object(reviews, "evaluate_completion", spy):
            self.rate_at("personal", card, NOW, "easy")
            self.rate_at("personal", card, NOW + timedelta(days=9), "easy")
        first_events, first_ok = captured[0]
        self.assertEqual([e.rating for e in first_events], ["easy"])  # no legacy log in the window
        self.assertTrue(first_ok)
        second_events, second_ok = captured[1]
        self.assertEqual([(e.reviewed_at, e.rating) for e in second_events],
                         [(NOW, "easy"), (NOW + timedelta(days=9), "easy")])
        self.assertTrue(second_ok)
        self.assertEqual(self.count(NOW).count, intro.count)  # earliest log is legacy: not new today

    def test_window_must_be_a_verified_chain(self):
        card = self.incomplete("chain", iso(NOW - timedelta(hours=1)))
        self.rate_at("personal", card, NOW, "good")
        self.raw_log(card, NOW + timedelta(hours=1), rating="good")  # a non-FSRS log inside the window
        captured = []
        real = reviews.evaluate_completion

        def spy(state, events, *, evidence_complete):
            captured.append(evidence_complete)
            return real(state, events, evidence_complete=evidence_complete)

        with mock.patch.object(reviews, "evaluate_completion", spy):
            result = self.rate_at("personal", card, NOW + timedelta(days=3), "good")
        self.assertEqual(captured, [False])
        self.assertNotEqual(result["srs"]["completion_status"], "completed")

    def test_existing_first_completion_record_is_kept(self):
        card = self.incomplete("kept", iso(NOW - timedelta(hours=1)))
        with get_connection() as c:
            c.execute("UPDATE vocab_items SET completion_metric_version = 'meaning-completion-v1-draft', "
                      "first_completed_at = ? WHERE id = ?", (iso(NOW - timedelta(days=100)), card))
        result = self.rate_at("personal", card, NOW, "again")
        self.assertEqual(self.row(card)["first_completed_at"], iso(NOW - timedelta(days=100)))
        # Gate D-2 U11 B: the draft first completion is history with its source fixed once;
        # the answer carries the current (V3) first completion, which does not exist yet.
        self.assertEqual(self.row(card)["first_completed_source"], completion.DRAFT_METRIC_VERSION)
        self.assertIsNone(result["srs"]["first_completed_at"])
        self.assertFalse(result["srs"]["needs_relearning"])
        self.assertEqual(self.row(card)["completion_metric_version"], completion.METRIC_VERSION)  # current judgement


# ---------------------------------------------------------------------------
class RequestContractTests(FirstReviewCase):
    def test_same_request_retry_returns_the_first_response_once(self):
        card = self.incomplete("retry", iso(NOW - timedelta(hours=1)))
        first = self.rate("personal", card, request=self.req(1), version=1)
        state = self.snapshot_all()
        again = self.rate("personal", card, request=self.req(1), version=1)  # response lost, client retries
        self.assertEqual(again, first)
        self.assertEqual(self.snapshot_all(), state)  # no second init, log, receipt or boundary

    def test_concurrent_identical_requests_record_once(self):
        card = self.incomplete("twins", iso(NOW - timedelta(hours=1)))
        from app.repositories.vocab_repository import record_review

        def send():
            return record_review(self.user, card, "good", request_id=self.req(2), expected_card_version=1, session_id="s1")

        # One clock patch for both threads (patching inside each thread would race on restore).
        with race_support.LockProbe(), mock.patch.object(reviews, "now_utc", return_value=NOW):
            a = race_support.start("a", send)
            b = race_support.start("b", send)
            first, second = race_support.finish(self, a), race_support.finish(self, b)
        self.assertIsNot(reviews.now_utc.__class__, mock.MagicMock)
        self.assertEqual(first, second)
        self.assertEqual(len([l for l in self.logs_of("personal", card) if l["srs_engine"] == "fsrs"]), 1)
        with get_connection() as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM srs_review_receipts").fetchone()[0], 1)

    def test_refusals_write_nothing(self):
        stale = self.incomplete("stale", iso(NOW - timedelta(hours=1)))
        flagged = self.incomplete("flagged", iso(NOW - timedelta(hours=1)))
        with get_connection() as c:
            identity.flag_identity_unknown(c, [identity.IdentityFinding(self.user, flagged, ["test"])])
        bad_log = self.incomplete("bad-log", iso(NOW - timedelta(hours=1)))
        self.raw_log(bad_log, NOW, time_text="garbage")
        paused = self.incomplete("paused", iso(NOW - timedelta(hours=1)), status="known")
        deck = self.shared_deck("s")
        lost = self.incomplete_lexeme(deck, "lost", 0, iso(NOW - timedelta(hours=1)))
        with get_connection() as c:  # synthetic: the app has no unsubscribe path
            c.execute("UPDATE user_deck_subscriptions SET is_active = FALSE WHERE user_id = ?", (self.user,))
        state = self.snapshot_all()
        for card, version, code in ((stale, 0, "card_version_conflict"), (flagged, 1, "card_identity_unknown"),
                                    (bad_log, 1, "review_history_unreadable"), (paused, 1, "card_paused")):
            with self.assertRaises(SrsWriteError) as caught:
                self.rate("personal", card, request=self.req(card), version=version)
            self.assertEqual(caught.exception.code, code)
        with self.assertRaises(SrsWriteError) as caught:
            self.rate("lexeme", lost, request=self.req(900), version=1, deck=deck)
        self.assertEqual(caught.exception.status_code, 404)
        self.assertEqual(self.snapshot_all(), state)

    def test_failure_at_each_step_rolls_everything_back(self):
        card = self.incomplete("atomic", iso(NOW - timedelta(hours=1)))
        state = self.snapshot_all()
        steps = [(reviews, "_record_evidence_boundary"), (reviews, "introduced_on"), (reviews, "request_hash")]
        for owner, name in steps:
            with self.subTest(step=name), mock.patch.object(owner, name, side_effect=RuntimeError(f"fail at {name}")):
                with self.assertRaises(RuntimeError):
                    self.rate("personal", card, request=self.req(3), version=1)
                self.assertEqual(self.snapshot_all(), state)
        self.rate("personal", card, request=self.req(3), version=1)  # then it works, once
        self.assertEqual(len([l for l in self.logs_of("personal", card) if l["srs_engine"] == "fsrs"]), 1)

    def test_boundary_is_never_overwritten_and_survives_rollback(self):
        card = self.incomplete("rb", iso(NOW - timedelta(hours=1)))
        self.rate_at("personal", card, NOW, "good")
        boundary = self.boundary("personal", card)
        with get_connection() as c:
            with self.assertRaises(SrsWriteError) as caught:
                reviews._record_evidence_boundary(c, CardKey("personal", self.user, card), boundary + 999)
            self.assertIn(caught.exception.code, ("evidence_boundary_mismatch", "evidence_boundary_conflict"))
        run = json.loads(self.everything()["srs_migration_runs"][-1][4])  # scope of the conversion run
        self.assertEqual(run["cards"][0]["ref_id"], card)
        rolled = migration.rollback_plan(f"run-{card}", "rb-u7", user_id=self.user, approved=True)
        self.assertEqual(rolled[0]["result"], "rolled_back")
        self.assertEqual(self.boundary("personal", card), boundary)  # explicitly preserved
        self.assertEqual(self.row(card)["srs_engine"], "legacy")
        self.assertIn("evidence_from_log_id", migration.ROLLBACK_PRESERVED)


if __name__ == "__main__":
    unittest.main()

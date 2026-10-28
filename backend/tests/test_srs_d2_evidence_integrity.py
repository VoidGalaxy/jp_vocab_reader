"""Gate D-2 U7 review fixes: completion evidence must be explained by the stored
engine transitions (P1), and unreadable window records are refused before the
engine (P2).

Synthetic SQLite only (QueueCase sets a throwaway DATABASE_URL per test before the
app touches a database). Tampering below edits synthetic rows to model damaged
data; the product code never edits logs.

Run directly:      python tests/test_srs_d2_evidence_integrity.py
Or via discovery:   python -m unittest discover -s tests
"""

from __future__ import annotations

import json
import sys
import unittest
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_srs_d2_first_review import FirstReviewCase  # noqa: E402
from test_srs_queue import NOW, iso  # noqa: E402

from app.database import get_connection  # noqa: E402
from app.srs import reviews  # noqa: E402
from app.srs.engine import state_from_json, state_to_json  # noqa: E402
from app.srs.storage import SrsWriteError  # noqa: E402

DAY = timedelta(days=1)


class IntegrityCase(FirstReviewCase):
    def rate_at(self, kind, ref, at, rating="good", request=None, deck=None):
        if request is None:  # personal and subscribed ids can coincide: keep request ids apart
            version = self.card_row(kind, ref)["srs_card_version"]
            request = self.req((0 if kind == "personal" else 10**6) + ref * 100 + version)
        return super().rate_at(kind, ref, at, rating, request=request, deck=deck)

    def log_table(self, kind):
        return ("review_logs", "vocab_item_id", "reviewed_at") if kind == "personal" else (
            "lexeme_review_logs", "lexeme_id", "created_at")

    def converted(self, kind, name, deck=None, order=0):
        if kind == "personal":
            return self.incomplete(name, iso(NOW - timedelta(hours=1)))
        return self.incomplete_lexeme(deck, name, order, iso(NOW - timedelta(hours=1)))

    def easy_days(self, kind, ref, days, deck=None):
        results = []
        for day in range(days):
            results.append(self.rate_at(kind, ref, NOW + day * DAY, "easy", deck=deck))
        return results

    def fsrs_logs(self, kind, ref):
        return [log for log in self.logs_of(kind, ref) if log["srs_engine"] == "fsrs"]

    def tamper(self, kind, log_id, **values):
        table = self.log_table(kind)[0]
        with get_connection() as c:
            c.execute(f"UPDATE {table} SET " + ", ".join(f"{k} = ?" for k in values) + " WHERE id = ?",
                      (*values.values(), log_id))

    def card_row(self, kind, ref):
        return self.row(ref) if kind == "personal" else self.row(ref, "user_word_progress", "lexeme_id")


# ---------------------------------------------------------------------------
class P1TimeOnlyTamperingTests(IntegrityCase):
    def check(self, kind, deck=None):
        ref = self.converted(kind, f"p1-{kind}", deck)
        results = self.easy_days(kind, ref, 3, deck)
        self.assertTrue(all(r["completed"] is not True for r in results))
        first = self.fsrs_logs(kind, ref)[0]
        time_col = self.log_table(kind)[2]
        self.tamper(kind, first["id"], **{time_col: iso(NOW - 10 * DAY)})  # only the time moves
        fourth = self.rate_at(kind, ref, NOW + 3 * DAY, "easy", deck=deck)
        self.assertNotEqual(fourth["completed"], True)
        self.assertNotEqual(fourth["srs"]["completion_status"], "completed")
        self.assertIsNone(self.card_row(kind, ref)["first_completed_at"])  # no new first completion
        self.assertEqual(self.fsrs_logs(kind, ref)[0][time_col], iso(NOW - 10 * DAY))  # nothing repaired

    def test_personal(self):
        self.check("personal")

    def test_subscribed(self):
        self.check("lexeme", self.shared_deck("s"))

    def test_untampered_daily_easy_is_still_not_completed_and_same_instant_spellings_pass(self):
        ref = self.converted("personal", "spelling")
        self.easy_days("personal", ref, 2)
        first = self.fsrs_logs("personal", ref)[0]
        # Same instant, different spelling (+09:00): readable and consistent.
        at = state_from_json(first["srs_after_json"]).last_review_at
        self.tamper("personal", first["id"], reviewed_at=at.astimezone(
            __import__("datetime").timezone(timedelta(hours=9))).isoformat())
        captured = []
        real = reviews.evaluate_completion

        def spy(state, events, *, evidence_complete):
            captured.append(evidence_complete)
            return real(state, events, evidence_complete=evidence_complete)

        from unittest import mock
        with mock.patch.object(reviews, "evaluate_completion", spy):
            self.rate_at("personal", ref, NOW + 2 * DAY, "easy")
        self.assertEqual(captured, [True])


# ---------------------------------------------------------------------------
class P2UnreadableRatingTests(IntegrityCase):
    def check(self, kind, deck=None):
        ref = self.converted(kind, f"p2-{kind}", deck)
        self.rate_at(kind, ref, NOW, "good", deck=deck)
        first = self.fsrs_logs(kind, ref)[0]
        self.tamper(kind, first["id"], rating="garbage")
        before = self.everything()
        with self.assertRaises(SrsWriteError) as caught:
            self.rate_at(kind, ref, NOW + 2 * DAY, "good", deck=deck)
        self.assertEqual((caught.exception.code, caught.exception.status_code), ("review_history_unreadable", 409))
        self.assertEqual(self.everything(), before)  # card, logs, receipts, boundary, completion untouched

    def test_personal(self):
        self.check("personal")

    def test_subscribed(self):
        self.check("lexeme", self.shared_deck("s"))



# ---------------------------------------------------------------------------
class ReadableMismatchTests(IntegrityCase):
    """Readable but disagreeing window records -> incomplete evidence, no exception,
    no completion, no new first completion, nothing repaired."""

    def spy_next(self, kind, ref, at, deck=None):
        captured = []
        real = reviews.evaluate_completion

        def spy(state, events, *, evidence_complete):
            captured.append((evidence_complete, [e.rating for e in events]))
            return real(state, events, evidence_complete=evidence_complete)

        from unittest import mock
        with mock.patch.object(reviews, "evaluate_completion", spy):
            result = self.rate_at(kind, ref, at, "easy", deck=deck)
        return result, captured

    def run_case(self, kind, mutate, deck=None, expect_complete=False):
        ref = self.converted(kind, f"m-{kind}-{mutate.__name__}", deck, order=self._order())
        self.easy_days(kind, ref, 2, deck)
        logs = self.fsrs_logs(kind, ref)
        mutate(self, kind, ref, logs)
        tampered = self.fsrs_logs(kind, ref)
        result, captured = self.spy_next(kind, ref, NOW + 2 * DAY, deck)
        self.assertEqual(captured[0][0], expect_complete, mutate.__name__)
        if not expect_complete:
            self.assertEqual(captured[0][1], ["easy"], mutate.__name__)  # untrusted records not handed over
            self.assertNotEqual(result["srs"]["completion_status"], "completed")
            self.assertIsNone(self.card_row(kind, ref)["first_completed_at"])
        self.assertEqual(self.fsrs_logs(kind, ref)[:2], tampered[:2])  # nothing repaired

    _counter = 0

    def _order(self):
        type(self)._counter += 1
        return type(self)._counter

    # --- mutations of readable records ----------------------------------
    def rating_only(self, kind, ref, logs):
        self.tamper(kind, logs[1]["id"], rating="good")  # stored after-state came from "easy"

    def config_mismatch(self, kind, ref, logs):
        self.tamper(kind, logs[1]["id"], srs_config_version="other-config")

    def snapshot_mismatch(self, kind, ref, logs):
        after = json.loads(logs[0]["srs_after_json"])
        after["stability"] = after["stability"] + 1.0
        self.tamper(kind, logs[0]["id"], srs_after_json=json.dumps(after))

    def time_reversed(self, kind, ref, logs):
        self.tamper(kind, logs[1]["id"], **{self.log_table(kind)[2]: iso(NOW - DAY)})

    def boundary_missing(self, kind, ref, logs):
        table = "vocab_items" if kind == "personal" else "user_word_progress"
        col = "id" if kind == "personal" else "lexeme_id"
        with get_connection() as c:
            c.execute(f"UPDATE {table} SET evidence_from_log_id = NULL WHERE {col} = ? AND user_id = ?", (ref, self.user))

    def same_instant_other_spelling(self, kind, ref, logs):
        from datetime import timezone
        at = state_from_json(logs[1]["srs_after_json"]).last_review_at
        self.tamper(kind, logs[1]["id"], **{self.log_table(kind)[2]: at.astimezone(timezone(timedelta(hours=-5))).isoformat()})

    def test_personal_mismatches(self):
        for mutate in (P1Mutations.time_only, ReadableMismatchTests.rating_only, ReadableMismatchTests.config_mismatch,
                       ReadableMismatchTests.snapshot_mismatch, ReadableMismatchTests.time_reversed):
            with self.subTest(mutation=mutate.__name__):
                self.run_case("personal", mutate)
        with self.subTest(mutation="boundary_missing"):
            ref = self.converted("personal", "no-boundary")
            self.easy_days("personal", ref, 2)
            self.boundary_missing("personal", ref, [])
            result, captured = self.spy_next("personal", ref, NOW + 2 * DAY)
            self.assertFalse(captured[0][0])
            self.assertIsNone(self.card_row("personal", ref)["evidence_from_log_id"])  # not re-created
        with self.subTest(mutation="same_instant_other_spelling"):
            self.run_case("personal", ReadableMismatchTests.same_instant_other_spelling, expect_complete=True)

    def test_subscribed_mismatches(self):
        deck = self.shared_deck("s")
        for mutate in (P1Mutations.time_only, ReadableMismatchTests.rating_only, ReadableMismatchTests.config_mismatch,
                       ReadableMismatchTests.snapshot_mismatch, ReadableMismatchTests.time_reversed):
            with self.subTest(mutation=mutate.__name__):
                self.run_case("lexeme", mutate, deck)
        with self.subTest(mutation="boundary_missing"):
            ref = self.converted("lexeme", "no-boundary", deck, order=99)
            self.easy_days("lexeme", ref, 2, deck)
            self.boundary_missing("lexeme", ref, [])
            result, captured = self.spy_next("lexeme", ref, NOW + 2 * DAY, deck)
            self.assertFalse(captured[0][0])
        with self.subTest(mutation="same_instant_other_spelling"):
            self.run_case("lexeme", ReadableMismatchTests.same_instant_other_spelling, deck, expect_complete=True)


class P1Mutations:
    @staticmethod
    def time_only(case, kind, ref, logs):
        case.tamper(kind, logs[0]["id"], **{case.log_table(kind)[2]: iso(NOW - 10 * DAY)})


# ---------------------------------------------------------------------------
class UnreadableRecordTests(IntegrityCase):
    def refused(self, kind, ref, deck=None):
        before = self.everything()
        with self.assertRaises(SrsWriteError) as caught:
            self.rate_at(kind, ref, NOW + 3 * DAY, "good", deck=deck)
        self.assertEqual((caught.exception.code, caught.exception.status_code), ("review_history_unreadable", 409))
        self.assertEqual(self.everything(), before)

    def test_unreadable_snapshot_and_legacy_garbage_rating(self):
        deck = self.shared_deck("s")
        for kind in ("personal", "lexeme"):
            with self.subTest(kind=kind, case="snapshot"):
                ref = self.converted(kind, f"snap-{kind}", deck, order=10)
                self.rate_at(kind, ref, NOW, "good", deck=deck)
                self.tamper(kind, self.fsrs_logs(kind, ref)[0]["id"], srs_after_json="{broken")
                self.refused(kind, ref, deck)
        # A garbage rating on a log OUTSIDE the window (legacy history) is refused the same way.
        card = self.personal("legacy-garbage")
        self.raw_log(card, NOW - 20 * DAY, rating="garbage")
        self.fsrs("personal", card, self.state(__import__("app.srs.engine", fromlist=["SrsPhase"]).SrsPhase.REVIEW,
                                               NOW - DAY))
        self.refused("personal", card)

    def test_untouched_receipt_retry_still_replays(self):
        ref = self.converted("personal", "retry-after-damage")
        first = self.rate("personal", ref, request=self.req(77), version=1)
        self.tamper("personal", self.fsrs_logs("personal", ref)[0]["id"], rating="garbage")
        again = self.rate("personal", ref, request=self.req(77), version=1)  # stored receipt: same response
        self.assertEqual(again, first)


if __name__ == "__main__":
    unittest.main()

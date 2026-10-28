"""Gate D-2 U11 review fix: an integer too large for the engine (e.g. 10**400) in a log's
engine snapshot is an engine validation failure (SrsEngineError), not an unhandled
OverflowError -- and so are the other snapshot parse failures that escaped the same
path (a date whose UTC conversion overflows, JSON nested too deep).

- card without an evidence boundary: the snapshot is outside any window, so it only
  makes the completion evidence incomplete; the review is recorded and scheduled;
- card with a boundary, snapshot inside the window: the existing unreadable-history
  rule (review 409, queue `invalid_state`), the same judgement in both.

Synthetic SQLite only (QueueCase sets a throwaway DATABASE_URL per test).

Run directly:      python tests/test_srs_d2_u11_snapshot_bigint.py
Or via discovery:   python -m unittest discover -s tests
"""

from __future__ import annotations

import json
import sqlite3
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_srs_d2_u11_plain_evidence import PlainCase, V3_DAYS  # noqa: E402
from test_srs_queue import NOW  # noqa: E402

from app.database import get_connection  # noqa: E402
from app.srs import engine, reviews  # noqa: E402
from app.srs.engine import SrsCardState, SrsEngineError, SrsPhase, state_from_json  # noqa: E402
from app.srs.storage import SrsWriteError  # noqa: E402

DAY = timedelta(days=1)
BIG = 10 ** 400
CASES = [(column, field, sign) for column in ("srs_before_json", "srs_after_json")
         for field in ("stability", "difficulty") for sign in (1, -1)]


def big_text(text, field, value):
    data = json.loads(text)
    data[field] = value
    return json.dumps(data)


class EngineTests(unittest.TestCase):
    def test_big_integers_are_engine_errors(self):
        at = datetime(2026, 10, 9, tzinfo=timezone.utc)
        for field in ("stability", "difficulty"):
            for value in (BIG, -BIG, 2 ** 1024):
                with self.subTest(field=field, value=type(value).__name__), self.assertRaises(SrsEngineError):
                    SrsCardState(**{"phase": SrsPhase.REVIEW, "step": None, "stability": 10.0, "difficulty": 5.0,
                                    "due_at": at + DAY, "last_review_at": at, field: value})

    def test_existing_rules_unchanged(self):
        at = datetime(2026, 10, 9, tzinfo=timezone.utc)
        base = {"phase": SrsPhase.REVIEW, "step": None, "stability": 10.0, "difficulty": 5.0,
                "due_at": at + DAY, "last_review_at": at}
        SrsCardState(**base)
        SrsCardState(**dict(base, stability=10, difficulty=5))  # plain ints stay valid
        for field in ("stability", "difficulty"):
            for value in (True, "5", float("nan"), float("inf"), -float("inf"), None):
                with self.subTest(field=field, value=repr(value)), self.assertRaises(SrsEngineError):
                    SrsCardState(**dict(base, **{field: value}))
        with self.assertRaises(SrsEngineError):
            SrsCardState(**dict(base, difficulty=11.0))  # range check unchanged

    def test_other_snapshot_parse_failures_are_engine_errors(self):
        good = json.dumps({"phase": "review", "step": None, "stability": 10.0, "difficulty": 5.0,
                           "due_at": "2026-10-10T00:00:00+00:00", "last_review_at": "2026-10-09T00:00:00+00:00"})
        for name, text in (("date overflow", good.replace("2026-10-09T00:00:00+00:00", "0001-01-01T00:00:00+05:00")),
                           ("deep nesting", "[" * 100000), ("not text", None), ("big stability", big_text(good, "stability", BIG))):
            with self.subTest(case=name), self.assertRaises(SrsEngineError):
                state_from_json(text)


# ---------------------------------------------------------------------------
class SnapshotCase(PlainCase):
    def damage(self, kind, ref, index, column, text_of):
        table, col = ("review_logs", "vocab_item_id") if kind == "personal" else ("lexeme_review_logs", "lexeme_id")
        log = self.logs_of(kind, ref)[index]
        with get_connection() as c:
            c.execute(f"UPDATE {table} SET {column} = ? WHERE id = ?", (text_of(log[column]), log["id"]))
        return self.logs_of(kind, ref)


class PlainCardTests(SnapshotCase):
    def check(self, kind, column, field, sign):
        ref, deck = self.born(kind, f"b-{column[4:7]}-{field[:3]}-{sign}-{kind}")
        results = [self.review(kind, ref, deck, NOW + d * DAY) for d in V3_DAYS[:2]]
        logs = self.damage(kind, ref, 1, column, lambda text: big_text(text, field, sign * BIG))
        results += [self.review(kind, ref, deck, NOW + d * DAY) for d in (74, 200)]  # recorded, scheduled
        self.no_completion(kind, ref, results)
        self.assertEqual(self.logs_of(kind, ref)[:2], logs[:2])  # the damaged log is kept as stored
        self.assertEqual(len(self.logs_of(kind, ref)), 4)
        self.assertTrue(all(r["next_review_at"] for r in results))

    def test_every_case(self):
        for kind in ("personal", "lexeme"):
            for case in CASES:
                with self.subTest(kind=kind, case=case):
                    self.check(kind, *case)

    def test_other_parse_failures_are_incomplete_too(self):
        changes = {
            "date overflow": lambda text: json.dumps(dict(json.loads(text), last_review_at="0001-01-01T00:00:00+05:00")),
            "deep nesting": lambda text: "[" * 100000,
        }
        for kind in ("personal", "lexeme"):
            for name, change in changes.items():
                with self.subTest(kind=kind, case=name):
                    ref, deck = self.born(kind, f"o-{name[:4]}-{kind}")
                    results = [self.review(kind, ref, deck, NOW + d * DAY) for d in V3_DAYS[:2]]
                    self.damage(kind, ref, 1, "srs_after_json", change)
                    results += [self.review(kind, ref, deck, NOW + d * DAY) for d in (74, 200)]
                    self.no_completion(kind, ref, results)

    def test_existing_completion_history_is_kept(self):
        ref, deck = self.born("personal", "kept")
        done = [self.review("personal", ref, deck, NOW + d * DAY) for d in V3_DAYS][-1]
        self.assertTrue(done["completed"])
        kept = self.cols("personal", ref)
        self.damage("personal", ref, 0, "srs_after_json", lambda text: big_text(text, "stability", BIG))
        later = self.review("personal", ref, deck, NOW + 200 * DAY)
        self.assertIsNot(later["completed"], True)
        self.assertEqual(self.cols("personal", ref)["version_first_completed_at"], kept["version_first_completed_at"])
        self.assertEqual(self.cols("personal", ref)["first_completed_at"], kept["first_completed_at"])

    def test_retry_returns_the_stored_answer(self):
        ref, deck = self.born("lexeme", "retry")
        [self.review("lexeme", ref, deck, NOW + d * DAY) for d in V3_DAYS[:2]]
        self.damage("lexeme", ref, 1, "srs_after_json", lambda text: big_text(text, "stability", BIG))
        version = self.card_row("lexeme", ref)["srs_card_version"]
        first = self.post("lexeme", ref, NOW + 74 * DAY, "big-retry", version, deck, rating="easy")
        self.assertEqual(first.status_code, 200)
        before = self.everything()
        again = self.post("lexeme", ref, NOW + 75 * DAY, "big-retry", version, deck, rating="easy")
        self.assertEqual(again.content, first.content)
        self.assertEqual(self.everything(), before)

    def test_write_failure_still_rolls_back(self):
        ref, deck = self.born("personal", "fail")
        [self.review("personal", ref, deck, NOW + d * DAY) for d in V3_DAYS[:2]]
        self.damage("personal", ref, 1, "srs_after_json", lambda text: big_text(text, "stability", BIG))
        before = self.everything()
        with mock.patch.object(reviews, "update_card", side_effect=sqlite3.OperationalError("disk I/O error")):
            with self.assertRaises(sqlite3.OperationalError):
                with mock.patch.object(reviews, "now_utc", return_value=NOW + 74 * DAY):
                    from app.repositories import vocab_repository
                    vocab_repository.record_review(self.user, ref, "easy", request_id="big-fail",
                                                   expected_card_version=self.card_row("personal", ref)["srs_card_version"],
                                                   session_id="s1")
        self.assertEqual(self.everything(), before)


class WindowCardTests(SnapshotCase):
    """A converted (U5) card: the damaged snapshot is inside its evidence window."""

    def check(self, kind, column, field, sign):
        deck = None
        if kind == "lexeme":
            deck = getattr(self, "_wdeck", None) or self.shared_deck("window")
            self._wdeck = deck
            self._wo = getattr(self, "_wo", 0) + 1
            ref = self.converted("lexeme", f"w-{self._wo}", deck, self._wo)
        else:
            ref = self.converted("personal", f"w-{column[4:7]}-{field[:3]}-{sign}")
        for d in (0, 8):
            self.rate_at(kind, ref, NOW + d * DAY, "easy", deck=deck)
        self.now = NOW
        self.damage(kind, ref, 1, column, lambda text: big_text(text, field, sign * BIG))
        before = self.everything()
        result = self.q()
        self.assertNotIn((kind, ref), [(i["card_kind"], i["card_id"]) for i in result["items"]])
        self.assertGreaterEqual(result["counts"]["invalid_state"], 1)
        with self.assertRaises(SrsWriteError) as caught:
            self.rate_at(kind, ref, NOW + 74 * DAY, "easy", deck=deck)
        self.now = NOW
        self.assertEqual((caught.exception.code, caught.exception.status_code), ("review_history_unreadable", 409))
        self.assertEqual(self.everything(), before)

    def test_every_case(self):
        for kind in ("personal", "lexeme"):
            for case in CASES:
                with self.subTest(kind=kind, case=case):
                    self.check(kind, *case)


class ControlTests(SnapshotCase):
    def test_normal_cards_still_complete(self):
        for kind in ("personal", "lexeme"):
            with self.subTest(kind=kind):
                ref, deck = self.born(kind, f"ctl-{kind}")
                results = [self.review(kind, ref, deck, NOW + d * DAY) for d in V3_DAYS]
                self.assertEqual([r["completed"] for r in results], [False, False, True])


if __name__ == "__main__":
    unittest.main()

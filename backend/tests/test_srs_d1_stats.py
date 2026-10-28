"""Gate D-1: /stats today_seoul (Asia/Seoul day, account-wide), additive to the UTC fields.

Synthetic SQLite only (QueueCase sets a throwaway DATABASE_URL before the app is used).

Run directly:      python tests/test_srs_d1_stats.py
Or via discovery:   python -m unittest discover -s tests
"""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_srs_queue import NOW, QueueCase  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from app import main  # noqa: E402
from app.auth import create_access_token  # noqa: E402
from app.database import get_connection  # noqa: E402
from app.repositories import stats_repository  # noqa: E402
from app.repositories.deck_repository import create_deck  # noqa: E402
from app.schemas import DeckCreate  # noqa: E402

UTC = timezone.utc
# 2026-10-10 02:00 UTC = 11:00 KST. The Seoul day 2026-10-10 started at 2026-10-09 15:00 UTC.
FIXED_NOW = datetime(2026, 10, 10, 2, 0, tzinfo=UTC)


class TodaySeoulTests(QueueCase):
    def setUp(self):
        super().setUp()
        patcher = mock.patch.object(stats_repository, "now_utc", return_value=FIXED_NOW)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client = TestClient(main.app)
        self.addCleanup(self.client.close)
        self.headers = {"Authorization": "Bearer " + create_access_token({"id": self.user, "email": "c1@example.test"})}
        self.shared = self.shared_deck("s")

    def personal_log(self, card, rating, at):
        with get_connection() as c:
            c.execute("INSERT INTO review_logs (user_id, vocab_item_id, rating, reviewed_at, previous_review_level, "
                      "next_review_level, next_review_at) VALUES (?, ?, ?, ?, 0, 1, ?)",
                      (self.user, card, rating, at, at))

    def lexeme_log(self, lexeme, rating, at):
        with get_connection() as c:
            c.execute("INSERT INTO lexeme_review_logs (user_id, lexeme_id, shared_deck_id, rating, previous_review_level, "
                      "new_review_level, previous_next_review_at, new_next_review_at, previous_status, new_status, created_at) "
                      "VALUES (?, ?, ?, ?, 0, 1, NULL, ?, 'unknown', 'unknown', ?)",
                      (self.user, lexeme, self.shared, rating, at, at))

    def stats(self, **params):
        response = self.client.get("/stats", headers=self.headers, params=params)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_seoul_day_boundary_and_utc_fields_unchanged(self):
        a = self.personal("a")
        # 00:30 KST today = 15:30 UTC yesterday: Seoul today, NOT UTC today.
        self.personal_log(a, "good", (FIXED_NOW - timedelta(hours=10, minutes=30)).isoformat())
        # 23:30 KST yesterday = 14:30 UTC yesterday: neither.
        self.personal_log(a, "again", (FIXED_NOW - timedelta(hours=11, minutes=30)).isoformat())
        # 10:30 KST today = 01:30 UTC today: both.
        self.personal_log(a, "hard", (FIXED_NOW - timedelta(minutes=30)).isoformat())
        body = self.stats()
        today = body["today_seoul"]
        self.assertEqual(today["date"], "2026-10-10")
        self.assertEqual(today["scope"], "account")
        self.assertEqual(today["reviews"]["status"], "exact")
        self.assertEqual(today["reviews"]["total"], 2)
        self.assertEqual(today["reviews"]["by_rating"], {"again": 0, "hard": 1, "good": 1, "easy": 0})
        # Existing UTC contract: only the 01:30 UTC review is "today".
        self.assertEqual(body["reviewed_today_count"], 1)
        self.assertEqual(body["today_hard_count"], 1)
        self.assertEqual(body["today_good_count"], 0)

    def test_personal_and_subscribed_split_and_introduced(self):
        a, b = self.personal("a"), self.personal("b")
        word = self.lexeme("w", self.shared, 0)
        at = (FIXED_NOW - timedelta(hours=1)).isoformat()
        self.personal_log(a, "again", at)          # first review today
        self.personal_log(a, "good", at)           # same card again: not new
        self.personal_log(b, "good", (FIXED_NOW - timedelta(days=3)).isoformat())
        self.personal_log(b, "good", at)           # first review 3 days ago: not new today
        self.lexeme_log(word, "easy", at)          # subscribed first review today
        today = self.stats()["today_seoul"]
        self.assertEqual(today["reviews"]["personal"], 3)
        self.assertEqual(today["reviews"]["subscribed"], 1)
        self.assertEqual(today["reviews"]["total"], 4)
        self.assertEqual(today["introduced"], {"status": "exact", "count": 2, "at_least": 2})

    def test_unreadable_time_is_unknown_not_zero(self):
        a, broken = self.personal("a"), self.personal("broken")
        self.personal_log(a, "good", (FIXED_NOW - timedelta(hours=1)).isoformat())
        self.personal_log(broken, "good", "garbage")
        today = self.stats()["today_seoul"]
        self.assertEqual(today["reviews"]["status"], "unknown")
        self.assertIsNone(today["reviews"]["total"])
        self.assertEqual(today["reviews"]["at_least"], 1)
        self.assertEqual(today["reviews"]["unreadable_time_logs"], 1)
        self.assertEqual(today["introduced"]["status"], "unknown")
        self.assertIsNone(today["introduced"]["count"])
        self.assertEqual(today["introduced"]["at_least"], 1)

    def test_deck_scoped_stats_keep_account_today(self):
        a = self.personal("a")
        self.personal_log(a, "good", (FIXED_NOW - timedelta(hours=1)).isoformat())
        other_deck = self.client.post("/decks", headers=self.headers, json={"name": "other"}).json()["id"]
        body = self.stats(deck_id=other_deck)
        self.assertEqual(body["scope"], "deck")
        self.assertEqual(body["reviewed_today_count"], 0)  # existing deck-scoped UTC field
        self.assertEqual(body["today_seoul"]["scope"], "account")
        self.assertEqual(body["today_seoul"]["reviews"]["total"], 1)

    def test_no_writes(self):
        self.personal_log(self.personal("a"), "good", (FIXED_NOW - timedelta(hours=1)).isoformat())
        with get_connection() as c:
            before = [c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                      for t in ("review_logs", "lexeme_review_logs", "vocab_items", "user_word_progress")]
        self.stats()
        with get_connection() as c:
            after = [c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                     for t in ("review_logs", "lexeme_review_logs", "vocab_items", "user_word_progress")]
        self.assertEqual(before, after)


class FsrsDueFilterTests(QueueCase):
    """The vocab tab's due filter on an FSRS account uses the queue's 'due now' definition."""

    def test_due_only_matches_queue_due_categories(self):
        from app.repositories.vocab_repository import list_vocab_items
        from app.srs.engine import SrsPhase

        due_review = self.personal("due")
        self.due("personal", due_review, SrsPhase.REVIEW, NOW - timedelta(hours=1))
        due_learning = self.personal("learning")
        self.due("personal", due_learning, SrsPhase.LEARNING, NOW - timedelta(minutes=5))
        later = self.personal("later")
        self.due("personal", later, SrsPhase.REVIEW, datetime(2099, 1, 1, tzinfo=UTC))
        paused = self.personal("paused")
        self.fsrs("personal", paused, self.state(SrsPhase.REVIEW, NOW - timedelta(hours=1)), participation="paused")
        fresh = self.personal("fresh")
        self.fsrs("personal", fresh)  # FSRS new card: no state
        legacy_due = self.personal("legacy")  # not converted, legacy next_review_at unset -> legacy rule would include it
        ids = {item["id"] for item in list_vocab_items(self.user, deck_id=self.deck, due_only=True)}
        self.assertEqual(ids, {due_review, due_learning})
        counts = self.q(scope="personal_deck", deck_id=self.deck)["counts"]
        self.assertEqual(counts["learning_due"] + counts["relearning_due"] + counts["review_due"], len(ids))
        self.assertNotIn(legacy_due, ids)
        self.assertNotIn(fresh, ids)

    def test_due_only_follows_queue_classification_for_damaged_cards(self):
        """D-1 correction: the filter shares the queue's classify(), so damaged cards the
        queue does not serve (step out of range, unreadable own log) are not listed either."""
        from app.repositories.vocab_repository import list_vocab_items
        from app.srs.engine import SrsPhase

        ok_review = self.personal("ok-review")
        self.due("personal", ok_review, SrsPhase.REVIEW, NOW - timedelta(hours=2))
        ok_relearn = self.personal("ok-relearn")
        self.due("personal", ok_relearn, SrsPhase.RELEARNING, NOW - timedelta(minutes=10))
        bad_step = self.personal("bad-step")  # learning step outside the config's steps
        self.fsrs("personal", bad_step, self.state(SrsPhase.LEARNING, NOW - timedelta(minutes=5), step=99))
        bad_log = self.personal("bad-log")  # due, but one of its own log times is unreadable
        self.due("personal", bad_log, SrsPhase.REVIEW, NOW - timedelta(hours=1))
        with get_connection() as c:
            c.execute("INSERT INTO review_logs (user_id, vocab_item_id, rating, reviewed_at, previous_review_level, "
                      "next_review_level, next_review_at) VALUES (?, ?, 'good', 'garbage', 0, 1, ?)",
                      (self.user, bad_log, NOW.isoformat()))
        paused = self.personal("paused")
        self.fsrs("personal", paused, self.state(SrsPhase.REVIEW, NOW - timedelta(hours=1)), participation="paused")
        legacy = self.personal("legacy")  # not converted
        fresh = self.personal("fresh")
        self.fsrs("personal", fresh)
        later = self.personal("later")
        self.due("personal", later, SrsPhase.REVIEW, NOW + timedelta(days=3))
        other_deck = create_deck(self.user, DeckCreate(name="other"))[0]["id"]
        elsewhere = self.personal("elsewhere", deck=other_deck)
        self.due("personal", elsewhere, SrsPhase.REVIEW, NOW - timedelta(hours=1))

        counts = self.q(scope="personal_deck", deck_id=self.deck)["counts"]
        self.assertEqual(counts["invalid_state"], 2)  # bad-step, bad-log
        due_count = counts["learning_due"] + counts["relearning_due"] + counts["review_due"]
        listed = list_vocab_items(self.user, deck_id=self.deck, due_only=True)
        self.assertEqual({item["id"] for item in listed}, {ok_review, ok_relearn})
        self.assertEqual(len(listed), due_count)
        for excluded in (bad_step, bad_log, paused, legacy, fresh, later, elsewhere):
            self.assertNotIn(excluded, {item["id"] for item in listed})
        # Whole personal library (deck_id None) uses the same classification.
        all_ids = {item["id"] for item in list_vocab_items(self.user, due_only=True)}
        self.assertEqual(all_ids, {ok_review, ok_relearn, elsewhere})
        # Search, status and sort still apply on top of the queue decision.
        self.assertEqual([i["id"] for i in list_vocab_items(self.user, deck_id=self.deck, due_only=True, q="relearn")],
                         [ok_relearn])
        self.assertEqual(list_vocab_items(self.user, deck_id=self.deck, due_only=True, status="known"), [])
        ordered = [i["id"] for i in list_vocab_items(self.user, deck_id=self.deck, due_only=True, sort="created_asc")]
        self.assertEqual(ordered, [ok_review, ok_relearn])
        # Same server clock as the queue: once later's due passes, both include it.
        self.now = NOW + timedelta(days=4)
        counts = self.q(scope="personal_deck", deck_id=self.deck)["counts"]
        listed = {item["id"] for item in list_vocab_items(self.user, deck_id=self.deck, due_only=True)}
        self.assertIn(later, listed)
        self.assertEqual(len(listed), counts["learning_due"] + counts["relearning_due"] + counts["review_due"])

    def test_due_only_reads_logs_once(self):
        """No per-card log query: the statement count does not grow with the number of cards."""
        from app.repositories import vocab_repository
        from app.srs.engine import SrsPhase

        def statements(n):
            for i in range(n):
                card = self.personal(f"n{n}-{i}")
                self.due("personal", card, SrsPhase.REVIEW, NOW - timedelta(hours=1))
            seen = []
            real = vocab_repository.get_connection

            def counting(*args, **kwargs):
                connection = real(*args, **kwargs)
                connection.set_trace_callback(seen.append)
                return connection

            with mock.patch.object(vocab_repository, "get_connection", counting):
                vocab_repository.list_vocab_items(self.user, deck_id=self.deck, due_only=True)
            return len([s for s in seen if s.lstrip().upper().startswith("SELECT")])

        self.assertEqual(statements(2), statements(10))

    def test_legacy_account_due_filter_unchanged(self):
        from app.repositories.vocab_repository import list_vocab_items

        self.set_mode(self.user, "legacy")
        never = self.personal("never")  # legacy: next_review_at NULL counts as due
        ids = {item["id"] for item in list_vocab_items(self.user, deck_id=self.deck, due_only=True)}
        self.assertIn(never, ids)


if __name__ == "__main__":
    unittest.main()

"""Tests for the read-only, Asia/Seoul date-by-date study history.

Uses stdlib unittest only and a throwaway SQLite file (never backend/vocab.db
and never whatever DATABASE_URL is already set).

Run directly:      python tests/test_stats_history.py
Or via discovery:   python -m unittest discover -s tests
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

_SCRATCH_DB = Path(tempfile.gettempdir()) / "jp_vocab_reader_stats_history_test.db"
_SCRATCH_DB.unlink(missing_ok=True)
os.environ["DATABASE_URL"] = f"sqlite:///{_SCRATCH_DB.as_posix()}"

from app.database import get_connection, init_db  # noqa: E402
from app.repositories.stats_history_repository import (  # noqa: E402
    HistoryRangeError,
    build_history_day,
    build_history_month,
    local_date,
)

UTC = timezone.utc
# 2026-10-04 12:00 in Seoul.
NOW = datetime(2026, 10, 4, 3, 0, tzinfo=UTC)
USER = 101
OTHER_USER = 202


def seoul(year, month, day, hour=12, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=timezone(timedelta(hours=9)))


def add_personal_review(user_id, at, rating="good", item_id=1, stamp=None):
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO review_logs (
                user_id, vocab_item_id, deck_id, rating, reviewed_at,
                previous_review_level, next_review_level,
                previous_next_review_at, next_review_at, response_time_ms
            ) VALUES (?, ?, NULL, ?, ?, 0, 1, NULL, ?, NULL)
            """,
            (user_id, item_id, rating, stamp or at.astimezone(UTC).isoformat(), at.isoformat()),
        )


def add_subscribed_review(user_id, at, rating="good", lexeme_id=1):
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO lexeme_review_logs (
                user_id, lexeme_id, shared_deck_id, rating,
                previous_review_level, new_review_level,
                previous_next_review_at, new_next_review_at,
                previous_status, new_status, created_at
            ) VALUES (?, ?, NULL, ?, 0, 1, NULL, NULL, 'unknown', 'unknown', ?)
            """,
            (user_id, lexeme_id, rating, at.astimezone(UTC).isoformat()),
        )


def add_word(user_id, at, surface, deck_id=1):
    stamp = at.astimezone(UTC).isoformat()
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO vocab_items (
                deck_id, surface, base_form, reading, part_of_speech, normalized_form,
                meaning_ko, dictionary_gloss, quality_tag, context_explanation_ko,
                example_sentence, status, correct_count, wrong_count, last_reviewed_at,
                review_level, next_review_at, created_at, updated_at, user_id
            ) VALUES (?, ?, ?, '', '', ?, '뜻', '', '', '', '', 'unknown', 0, 0, NULL, 0, NULL, ?, ?, ?)
            """,
            (deck_id, surface, surface, surface, stamp, stamp, user_id),
        )


def day_entry(month, date):
    return next(day for day in month["days"] if day["date"] == date)


class StatsHistoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

    def setUp(self):
        with get_connection() as connection:
            for table in ("review_logs", "lexeme_review_logs", "vocab_items"):
                connection.execute(f"DELETE FROM {table}")

    def test_seoul_midnight_boundary(self):
        # 2026-09-30 23:59 Seoul = 14:59Z; 2026-10-01 00:30 Seoul = 15:30Z.
        add_personal_review(USER, datetime(2026, 9, 30, 14, 59, tzinfo=UTC))
        add_personal_review(USER, datetime(2026, 9, 30, 15, 30, tzinfo=UTC))
        september = build_history_month(USER, "2026-09", now=NOW)
        october = build_history_month(USER, "2026-10", now=NOW)
        self.assertEqual(day_entry(september, "2026-09-30")["review_count"], 1)
        self.assertEqual(day_entry(october, "2026-10-01")["review_count"], 1)
        self.assertEqual(september["timezone"], "Asia/Seoul")

    def test_personal_and_subscribed_are_both_counted_without_dedupe(self):
        at = seoul(2026, 9, 10)
        # Same numeric id in both logs must still be two events.
        add_personal_review(USER, at, "again", item_id=7)
        add_personal_review(USER, at, "again", item_id=7)
        add_subscribed_review(USER, at, "easy", lexeme_id=7)
        add_subscribed_review(USER, at, "hard", lexeme_id=7)
        day = day_entry(build_history_month(USER, "2026-09", now=NOW), "2026-09-10")
        self.assertEqual(day["review_count"], 4)
        self.assertEqual(day["ratings"], {"again": 2, "hard": 1, "good": 0, "easy": 1})
        self.assertEqual(sum(day["ratings"].values()), day["review_count"])

    def test_reviews_of_deleted_words_still_count(self):
        # No vocab_items row exists for item 999; the log must not be dropped.
        add_personal_review(USER, seoul(2026, 9, 11), item_id=999)
        self.assertEqual(
            day_entry(build_history_month(USER, "2026-09", now=NOW), "2026-09-11")["review_count"], 1
        )

    def test_accounts_are_isolated(self):
        add_personal_review(OTHER_USER, seoul(2026, 9, 12))
        add_subscribed_review(OTHER_USER, seoul(2026, 9, 12))
        add_word(OTHER_USER, seoul(2026, 9, 12), "他人")
        month = build_history_month(USER, "2026-09", now=NOW)
        self.assertEqual(month["summary"], {"review_count": 0, "saved_word_count": 0, "active_days": 0})
        day = build_history_day(USER, "2026-09-12", now=NOW)
        self.assertEqual(day["review_count"], 0)
        self.assertEqual(day["saved_words"], [])

    def test_month_totals_match_days_and_future_days_are_omitted(self):
        add_personal_review(USER, seoul(2026, 10, 1))
        add_subscribed_review(USER, seoul(2026, 10, 3))
        add_personal_review(USER, seoul(2026, 10, 3))
        add_word(USER, seoul(2026, 10, 2), "約束")
        october = build_history_month(USER, "2026-10", now=NOW)
        self.assertEqual([d["date"] for d in october["days"]][-1], "2026-10-04")
        self.assertEqual(len(october["days"]), 4)
        self.assertEqual(october["summary"]["review_count"], sum(d["review_count"] for d in october["days"]))
        self.assertEqual(october["summary"], {"review_count": 3, "saved_word_count": 1, "active_days": 2})
        self.assertEqual(october["today"], "2026-10-04")

    def test_full_past_month_has_every_day(self):
        self.assertEqual(len(build_history_month(USER, "2026-02", now=NOW)["days"]), 28)

    def test_invalid_and_future_ranges_are_rejected(self):
        for month in ("2026-11", "2026-13", "1999-12", "bad"):
            with self.subTest(month=month), self.assertRaises(HistoryRangeError):
                build_history_month(USER, month, now=NOW)
        for value in ("2026-10-05", "2026-02-30", "x"):
            with self.subTest(date=value), self.assertRaises(HistoryRangeError):
                build_history_day(USER, value, now=NOW)

    def test_saved_words_are_current_personal_words_by_seoul_day(self):
        # 2026-09-29 00:10 Seoul is still 2026-09-28 in UTC.
        add_word(USER, seoul(2026, 9, 29, 0, 10), "景色")
        add_word(USER, seoul(2026, 9, 29, 9), "続ける")
        add_word(USER, seoul(2026, 9, 29, 21), "静か")
        add_word(USER, seoul(2026, 9, 30, 0, 5), "明日")
        day = build_history_day(USER, "2026-09-29", limit=2, now=NOW)
        self.assertEqual(day["saved_word_count"], 3)
        self.assertTrue(day["has_more_saved_words"])
        self.assertEqual([w["surface"] for w in day["saved_words"]], ["静か", "続ける"])
        self.assertEqual(day["saved_words_scope"], "current_personal_words")
        self.assertNotIn("user_id", day["saved_words"][0])
        month = build_history_month(USER, "2026-09", now=NOW)
        self.assertEqual(day_entry(month, "2026-09-29")["saved_word_count"], 3)
        self.assertEqual(day_entry(month, "2026-09-30")["saved_word_count"], 1)

    def test_streak_counts_from_today_when_reviewed_today(self):
        for offset in range(3):
            add_personal_review(USER, seoul(2026, 10, 4) - timedelta(days=offset))
        streak = build_history_month(USER, "2026-10", now=NOW)["current_streak"]
        self.assertEqual((streak["days"], streak["starts_on"], streak["ends_on"]), (3, "2026-10-02", "2026-10-04"))

    def test_streak_counts_from_yesterday_when_not_reviewed_today(self):
        add_subscribed_review(USER, seoul(2026, 10, 3))
        add_personal_review(USER, seoul(2026, 10, 2))
        add_personal_review(USER, seoul(2026, 9, 30))  # gap on 10-01
        streak = build_history_month(USER, "2026-09", now=NOW)["current_streak"]
        self.assertEqual((streak["days"], streak["starts_on"], streak["ends_on"]), (2, "2026-10-02", "2026-10-03"))

    def test_streak_is_zero_without_recent_reviews(self):
        add_personal_review(USER, seoul(2026, 10, 1))
        streak = build_history_month(USER, "2026-10", now=NOW)["current_streak"]
        self.assertEqual((streak["days"], streak["starts_on"], streak["ends_on"]), (0, None, None))

    def test_long_streak_crosses_query_windows(self):
        for offset in range(80):
            add_personal_review(USER, seoul(2026, 10, 4) - timedelta(days=offset))
        streak = build_history_month(USER, "2026-10", now=NOW)["current_streak"]
        self.assertEqual(streak["days"], 80)
        self.assertFalse(streak["capped"])

    def test_streak_limit_is_exactly_400_days_from_either_anchor(self):
        # (anchor offset from today, consecutive review days, expected days, expected capped)
        cases = []
        for anchor_offset in (0, 1):
            for length, expected, capped in ((399, 399, False), (400, 400, False), (401, 400, True)):
                cases.append((anchor_offset, length, expected, capped))
        today = datetime(2026, 10, 4).date()
        for anchor_offset, length, expected, capped in cases:
            with self.subTest(anchor="today" if anchor_offset == 0 else "yesterday", length=length):
                self.setUp()
                anchor = seoul(2026, 10, 4) - timedelta(days=anchor_offset)
                with get_connection() as connection:
                    connection.executemany(
                        """
                        INSERT INTO review_logs (
                            user_id, vocab_item_id, deck_id, rating, reviewed_at,
                            previous_review_level, next_review_level,
                            previous_next_review_at, next_review_at, response_time_ms
                        ) VALUES (?, 1, NULL, 'good', ?, 0, 1, NULL, ?, NULL)
                        """,
                        [
                            (USER, (anchor - timedelta(days=i)).astimezone(UTC).isoformat(), anchor.isoformat())
                            for i in range(length)
                        ],
                    )
                streak = build_history_month(USER, "2026-10", now=NOW)["current_streak"]
                anchor_day = today - timedelta(days=anchor_offset)
                self.assertEqual(streak["days"], expected)
                self.assertEqual(streak["capped"], capped)
                self.assertEqual(streak["ends_on"], anchor_day.isoformat())
                self.assertEqual(streak["starts_on"], (anchor_day - timedelta(days=expected - 1)).isoformat())

    def test_timestamp_formats(self):
        self.assertEqual(str(local_date("2026-09-30T15:30:00Z")), "2026-10-01")
        self.assertEqual(str(local_date("2026-09-30T15:30:00")), "2026-10-01")  # naive = UTC
        self.assertEqual(str(local_date("2026-10-01T00:30:00+09:00")), "2026-10-01")
        self.assertIsNone(local_date("not a date"))
        add_personal_review(USER, seoul(2026, 9, 20), stamp="2026-09-20T03:00:00Z")
        self.assertEqual(
            day_entry(build_history_month(USER, "2026-09", now=NOW), "2026-09-20")["review_count"], 1
        )

    def test_reads_do_not_write(self):
        add_personal_review(USER, seoul(2026, 10, 1))
        add_word(USER, seoul(2026, 10, 1), "一")

        def counts():
            with get_connection() as connection:
                return [
                    connection.execute(f"SELECT COUNT(*) AS n FROM {t}").fetchone()["n"]
                    for t in ("review_logs", "lexeme_review_logs", "vocab_items", "user_word_progress")
                ]

        before = counts()
        build_history_month(USER, "2026-10", now=NOW)
        build_history_day(USER, "2026-10-01", now=NOW)
        self.assertEqual(before, counts())


class StatsHistoryRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient

        from app.main import app

        init_db()
        cls.client = TestClient(app)

    def _token(self, email):
        response = self.client.post(
            "/auth/register", json={"email": email, "password": "test-password-1", "display_name": "t"}
        )
        if response.status_code != 200:
            response = self.client.post("/auth/login", json={"email": email, "password": "test-password-1"})
        body = response.json()
        return body["access_token"], int(body["user"]["id"])

    def test_routes_use_the_signed_in_account_and_validate_input(self):
        token_a, user_a = self._token("history-a@example.test")
        token_b, _ = self._token("history-b@example.test")
        today = datetime.now(UTC).astimezone(timezone(timedelta(hours=9)))
        add_personal_review(user_a, today)
        month = today.strftime("%Y-%m")

        a = self.client.get(f"/stats/history?month={month}", headers={"Authorization": f"Bearer {token_a}"})
        b = self.client.get(f"/stats/history?month={month}", headers={"Authorization": f"Bearer {token_b}"})
        self.assertEqual(a.status_code, 200)
        self.assertEqual(a.json()["summary"]["review_count"], 1)
        self.assertEqual(b.json()["summary"]["review_count"], 0)
        self.assertNotIn("user_id", a.json())

        day = self.client.get(
            f"/stats/history/day?date={today.date().isoformat()}&limit=5",
            headers={"Authorization": f"Bearer {token_a}"},
        )
        self.assertEqual(day.status_code, 200)
        self.assertEqual(day.json()["review_count"], 1)

        future = (today + timedelta(days=40)).strftime("%Y-%m")
        headers = {"Authorization": f"Bearer {token_a}"}
        self.assertEqual(self.client.get(f"/stats/history?month={future}", headers=headers).status_code, 400)
        self.assertEqual(self.client.get("/stats/history?month=2026-1", headers=headers).status_code, 422)
        self.assertEqual(self.client.get("/stats/history/day?date=2026-10-01&limit=99", headers=headers).status_code, 422)


if __name__ == "__main__":
    unittest.main()

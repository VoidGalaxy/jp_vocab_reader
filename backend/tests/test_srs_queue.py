"""Gate C-1: read-only unified study queue (GET /study-queue).

Synthetic SQLite only, created per test in a throwaway directory. Never uses
backend/vocab.db, an existing DATABASE_URL, Neon or PostgreSQL.

Three layers, reported separately:
- QueueUnitTests...: app.srs.queue / queue_cursor functions with a fixed clock.
- QueueApiTests: FastAPI TestClient against the real route (in-process ASGI).
- QueueLoopbackHttpTests: one owned uvicorn child process over real HTTP.

Run directly:      python tests/test_srs_queue.py
Or via discovery:   python -m unittest discover -s tests
"""

from __future__ import annotations

import hashlib
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("APP_ENV", "test")

from fastapi.testclient import TestClient  # noqa: E402

from app import main  # noqa: E402
from app.auth import create_access_token  # noqa: E402
from app.database import get_connection, init_db  # noqa: E402
from app.repositories.deck_repository import create_deck  # noqa: E402
from app.repositories.lexeme_repository import (  # noqa: E402
    add_word_to_shared_deck, get_or_create_progress, get_or_create_subscription, upsert_lexeme,
)
from app.repositories.user_repository import create_user  # noqa: E402
from app.repositories.vocab_repository import create_or_update_vocab_item, record_review  # noqa: E402
from app.schemas import DeckCreate, VocabItemCreate  # noqa: E402
from app.srs import goals, queue, queue_cursor, reviews  # noqa: E402
from app.srs.engine import DEFAULT_CONFIG, CardKey, SrsCardState, SrsPhase  # noqa: E402
from app.srs.storage import state_columns  # noqa: E402

UTC = timezone.utc
NOW = datetime(2026, 10, 9, 3, 0, tzinfo=UTC)  # 12:00 Asia/Seoul
SECRET = "synthetic-c1-cursor-test-key-not-for-production"
TABLES = (
    "users", "decks", "vocab_items", "lexemes", "shared_decks", "shared_deck_words", "user_deck_subscriptions",
    "user_word_progress", "review_logs", "lexeme_review_logs", "srs_user_settings", "srs_review_receipts",
    "srs_config_versions", "srs_migration_runs", "srs_migration_snapshots",
)


def iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


class QueueCase(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="jp_vocab_c1_", dir=Path(__file__).resolve().parents[1])
        self.addCleanup(self.directory.cleanup)
        self.db_path = Path(self.directory.name) / "qa_srs_c1_synthetic.db"
        env = mock.patch.dict(os.environ, {"DATABASE_URL": f"sqlite:///{self.db_path.as_posix()}",
                                           "APP_ENV": "test", "JWT_SECRET_KEY": SECRET})
        env.start()
        self.addCleanup(env.stop)
        init_db()
        self.now = NOW
        clock = mock.patch.object(queue, "_now", side_effect=lambda: self.now)
        clock.start()
        self.addCleanup(clock.stop)
        self.user = create_user(email="c1@example.test", display_name="u", password_hash="x")["id"]
        self.other = create_user(email="c1-other@example.test", display_name="o", password_hash="x")["id"]
        self.deck = create_deck(self.user, DeckCreate(name="personal"))[0]["id"]
        self.set_mode(self.user, "fsrs")
        self._clock_seq = 0

    # --- fixtures (setup writes only; never through the queue) ------------
    def set_mode(self, user, mode, goal=20, version=0):
        stamp = iso(NOW)
        with get_connection() as connection:
            connection.execute("DELETE FROM srs_user_settings WHERE user_id = ?", (user,))
            connection.execute(
                "INSERT INTO srs_user_settings (user_id, srs_mode, daily_new_goal, settings_version, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?)", (user, mode, goal, version, stamp, stamp),
            )

    def personal(self, name, created=None, deck=None, user=None, status="unknown"):
        item = create_or_update_vocab_item(user or self.user, VocabItemCreate(
            surface=name, base_form=name, reading=name, meaning_ko=name, status=status, deck_id=deck or self.deck,
        ))[0]["id"]
        self._clock_seq += 1
        with get_connection() as connection:
            connection.execute("UPDATE vocab_items SET created_at = ? WHERE id = ?",
                               (iso(created or NOW - timedelta(days=30, minutes=-self._clock_seq)), item))
            # Since Gate C-2a a card created in an FSRS account starts as a fresh
            # FSRS card. These C-1 fixtures want the old starting point (a legacy
            # card) and convert it explicitly with self.fsrs(); restore that.
            connection.execute(
                "UPDATE vocab_items SET srs_engine = 'legacy', srs_config_version = NULL, "
                "srs_participation = NULL, srs_history_quality = NULL WHERE id = ?", (item,))
        return item

    def shared_deck(self, title, imported=None, subscribe=True):
        with get_connection() as connection:
            deck = connection.execute(
                "INSERT INTO shared_decks (owner_user_id, title, description, visibility, created_at, updated_at) "
                "VALUES (?, ?, '', 'public', ?, ?) RETURNING id", (self.other, title, iso(NOW), iso(NOW)),
            ).fetchone()["id"]
        if subscribe:
            get_or_create_subscription(self.user, deck)
            with get_connection() as connection:
                connection.execute(
                    "UPDATE user_deck_subscriptions SET imported_at = ? WHERE user_id = ? AND shared_deck_id = ?",
                    (iso(imported or NOW - timedelta(days=20)), self.user, deck),
                )
        return deck

    def lexeme(self, name, deck, order=0, progress=True):
        lexeme = upsert_lexeme(name, name)
        add_word_to_shared_deck(deck, lexeme, order)
        if progress:
            with get_connection() as connection:
                get_or_create_progress(connection, self.user, lexeme)
        return lexeme

    def fsrs(self, kind, ref, state=None, effective=None, participation="active", config=None, **extra):
        table, where = (("vocab_items", "id = ?") if kind == "personal"
                        else ("user_word_progress", "user_id = ? AND lexeme_id = ?"))
        params = (ref,) if kind == "personal" else (self.user, ref)
        values = dict(state_columns(state), srs_engine="fsrs",
                      srs_config_version=config or DEFAULT_CONFIG.config_version,
                      srs_participation=participation,
                      srs_effective_due_at=effective if effective is not None else (
                          iso(state.due_at) if state is not None else None))
        if state is not None:
            values["last_reviewed_at"] = iso(state.last_review_at)
        values.update(extra)
        with get_connection() as connection:
            connection.execute(f"UPDATE {table} SET " + ", ".join(f"{k} = ?" for k in values) + f" WHERE {where}",
                               (*values.values(), *params))

    @staticmethod
    def state(phase, due, step=None):
        return SrsCardState(phase=phase, step=(0 if phase is not SrsPhase.REVIEW and step is None else step),
                            stability=5.0, difficulty=5.0, due_at=due, last_review_at=due - timedelta(days=1))

    def due(self, kind, ref, phase, at):
        self.fsrs(kind, ref, self.state(phase, at))

    def q(self, user=None, **params):
        items = []
        for name, value in params.items():
            for one in (value if isinstance(value, list) else [value]):
                items.append((name, str(one)))
        return queue.build_queue(queue.parse_request(user or self.user, items))

    def keys(self, result):
        return [(item["card_kind"], item["card_id"]) for item in result["items"]]

    def rate(self, kind, ref, grade="good", at=None, request=None, deck=None, version=None):
        with get_connection() as connection:
            table, where = (("vocab_items", "id = ?") if kind == "personal"
                            else ("user_word_progress", "user_id = ? AND lexeme_id = ?"))
            params = (ref,) if kind == "personal" else (self.user, ref)
            if version is None:
                version = connection.execute(f"SELECT srs_card_version FROM {table} WHERE {where}", params).fetchone()[0]
        kwargs = dict(request_id=request or f"r-{kind}-{ref}-{version}", expected_card_version=version, session_id="s1")
        with mock.patch.object(reviews, "now_utc", return_value=at or self.now):
            if kind == "personal":
                return record_review(self.user, ref, grade, **kwargs)
            from app.repositories.lexeme_repository import record_lexeme_review
            return record_lexeme_review(self.user, ref, grade, deck, **kwargs)

    def snapshot(self):
        with get_connection() as connection:
            data = {table: [tuple(row) for row in connection.execute(f"SELECT * FROM {table} ORDER BY 1").fetchall()]
                    for table in TABLES}
        return data, hashlib.sha256(self.db_path.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
class QueueUnitOrderingTests(QueueCase):
    def test_global_order_across_kinds_and_buckets(self):  # S1
        shared = self.shared_deck("s")
        p_review, p_new = self.personal("p-review"), self.personal("p-new")
        l_learning, l_review = self.lexeme("l-learn", shared, 0), self.lexeme("l-review", shared, 1)
        self.due("personal", p_review, SrsPhase.REVIEW, NOW.replace(hour=1))          # 10:00 KST
        self.due("lexeme", l_learning, SrsPhase.LEARNING, NOW.replace(hour=1, minute=5))
        self.due("lexeme", l_review, SrsPhase.REVIEW, NOW.replace(hour=0))
        self.fsrs("personal", p_new)
        result = self.q()
        self.assertEqual(self.keys(result), [("lexeme", l_learning), ("lexeme", l_review),
                                             ("personal", p_review), ("personal", p_new)])
        self.assertEqual([i["bucket"] for i in result["items"]], ["short_due", "review_due", "review_due", "new"])

    def test_limit_after_global_sort_not_per_kind(self):  # S3, S4
        shared = self.shared_deck("s")
        late = [self.personal(f"p{i}") for i in range(8)]
        early = [self.lexeme(f"l{i}", shared, i) for i in range(3)]
        for index, item in enumerate(late):
            self.due("personal", item, SrsPhase.REVIEW, NOW - timedelta(hours=1, minutes=-index))
        for index, lexeme in enumerate(early):
            self.due("lexeme", lexeme, SrsPhase.REVIEW, NOW - timedelta(hours=5, minutes=-index))
        result = self.q(limit=5)
        self.assertEqual(self.keys(result), [("lexeme", x) for x in early] + [("personal", late[0]), ("personal", late[1])])
        self.assertEqual(result["counts"]["review_due"], 11)

    def test_new_order_uses_context_deck_time_then_sort_order(self):  # S6, S7, S8
        deck_a = self.shared_deck("a", imported=NOW - timedelta(days=40))
        deck_b = self.shared_deck("b", imported=NOW - timedelta(days=10))
        x3, x1, x2 = self.lexeme("x3", deck_a, 3), self.lexeme("x1", deck_a, 1), self.lexeme("x2", deck_a, 2)
        shared = self.lexeme("both", deck_a, 9)
        add_word_to_shared_deck(deck_b, shared, 0)
        p = self.personal("p", created=NOW - timedelta(days=35))
        for lexeme in (x1, x2, x3, shared):
            self.fsrs("lexeme", lexeme)
        self.fsrs("personal", p)
        result = self.q(mode="new")
        self.assertEqual(self.keys(result), [("lexeme", x1), ("lexeme", x2), ("lexeme", x3), ("lexeme", shared), ("personal", p)])
        both = next(i for i in result["items"] if i["card_id"] == shared)
        self.assertEqual(both["sort_key"][3], 9)
        self.assertEqual(both["review"]["shared_deck_id"], deck_a)
        scoped = self.q(mode="new", scope="subscribed_deck", deck_id=deck_b)
        self.assertEqual(scoped["items"][0]["sort_key"][3], 0)
        self.assertEqual(scoped["items"][0]["review"]["path"], f"/shared-decks/{deck_b}/words/{shared}/review")


class QueueUnitIdentityTests(QueueCase):
    def test_lexeme_in_two_decks_is_one_card_and_personal_stays_separate(self):  # D1-D5
        deck_a, deck_b = self.shared_deck("a"), self.shared_deck("b")
        cat = self.lexeme("猫", deck_a)
        add_word_to_shared_deck(deck_b, cat, 0)
        personal_cat = self.personal("猫")
        self.due("lexeme", cat, SrsPhase.REVIEW, NOW - timedelta(hours=1))
        self.due("personal", personal_cat, SrsPhase.REVIEW, NOW - timedelta(hours=1))
        result = self.q()
        self.assertEqual(sorted(self.keys(result)), sorted([("lexeme", cat), ("personal", personal_cat)]))
        self.assertEqual(result["counts"]["review_due"], 2)
        self.assertEqual(result["counts"]["total_in_scope"], 2)
        lexeme_item = next(i for i in result["items"] if i["card_kind"] == "lexeme")
        self.assertEqual(lexeme_item["review"]["shared_deck_id"], min(deck_a, deck_b))
        self.assertIsInstance(lexeme_item["card_version"], int)

    def test_same_numeric_id_different_kinds(self):  # D4
        shared = self.shared_deck("s")
        lexemes = [self.lexeme(f"n{i}", shared, i) for i in range(3)]
        items = [self.personal(f"q{i}") for i in range(3)]
        common = set(lexemes) & set(items)
        self.assertTrue(common)
        ref = common.pop()
        self.due("lexeme", ref, SrsPhase.REVIEW, NOW - timedelta(hours=2))
        self.due("personal", ref, SrsPhase.REVIEW, NOW - timedelta(hours=1))
        self.assertEqual(self.keys(self.q()), [("lexeme", ref), ("personal", ref)])


class QueueUnitCategoryTests(QueueCase):
    def build_all_categories(self):
        shared = self.shared_deck("s")
        cards = {}
        cards["new_unmaterialized"] = ("lexeme", self.lexeme("unmat", shared, 0, progress=False))
        cards["not_converted"] = ("personal", self.personal("legacy-unreviewed"))  # A2: never reviewed, legacy
        legacy_lexeme = self.lexeme("legacy-status", shared, 1)  # A3: progress row from a status change, legacy
        cards["unsupported_config"] = ("personal", self.personal("old-config"))
        self.fsrs(*cards["unsupported_config"], config="fsrs-6.3.1-a1-000000000000")
        cards["invalid_state"] = ("personal", self.personal("null-participation"))
        self.fsrs(*cards["invalid_state"], participation=None)
        cards["paused"] = ("personal", self.personal("paused-known", status="known"))
        self.fsrs(*cards["paused"], self.state(SrsPhase.REVIEW, NOW + timedelta(days=3)), participation="paused")
        cards["blocked_history"] = ("personal", self.personal("blocked"))
        self.fsrs(*cards["blocked_history"], last_reviewed_at=iso(NOW - timedelta(days=5)))
        cards["missing_due"] = ("personal", self.personal("no-due"))
        self.fsrs(*cards["missing_due"], self.state(SrsPhase.REVIEW, NOW + timedelta(days=1)))
        with get_connection() as connection:
            connection.execute("UPDATE vocab_items SET srs_effective_due_at = NULL WHERE id = ?", (cards["missing_due"][1],))
        cards["learning_due"] = ("lexeme", self.lexeme("learn", shared, 2))
        self.due(*cards["learning_due"], SrsPhase.LEARNING, NOW - timedelta(minutes=5))
        cards["relearning_due"] = ("personal", self.personal("relearn"))
        self.due(*cards["relearning_due"], SrsPhase.RELEARNING, NOW - timedelta(minutes=3))
        cards["review_due"] = ("personal", self.personal("review"))
        self.due(*cards["review_due"], SrsPhase.REVIEW, NOW - timedelta(hours=3))
        cards["pending_later"] = ("lexeme", self.lexeme("later", shared, 3))
        self.due(*cards["pending_later"], SrsPhase.REVIEW, NOW + timedelta(days=2))
        cards["new_available"] = ("personal", self.personal("fresh"))
        self.fsrs(*cards["new_available"])
        return cards, legacy_lexeme

    def test_every_card_in_exactly_one_category_and_sum_matches(self):  # A1-A3, A11
        cards, _ = self.build_all_categories()
        counts = self.q()["counts"]
        for category in queue.CATEGORIES:
            expected = 1 + (1 if category == "not_converted" else 0)
            self.assertEqual(counts[category], expected, category)
        self.assertEqual(sum(counts[c] for c in queue.CATEGORIES), counts["total_in_scope"])
        # new_available 1 + servable unmaterialized 1 (Gate C-2a allowance basis)
        self.assertEqual(counts["new_allowed_now"], 2)
        self.assertNotIn("new_allowed_now", queue.CATEGORIES)

    def test_bad_cards_do_not_shorten_pages_or_hide_others(self):  # F1-F4
        good = [self.personal(f"good{i}") for i in range(3)]
        for index, item in enumerate(good):
            self.due("personal", item, SrsPhase.REVIEW, NOW - timedelta(hours=1, minutes=-index))
        broken = []
        for index in range(10):
            item = self.personal(f"bad{index}")
            self.due("personal", item, SrsPhase.REVIEW, NOW - timedelta(days=3))  # would sort first
            broken.append(item)
        with get_connection() as connection:
            connection.execute(f"UPDATE vocab_items SET srs_stability = 'nan' WHERE id IN ({','.join('?' * 5)})", broken[:5])
            connection.execute(f"UPDATE vocab_items SET srs_difficulty = NULL WHERE id IN ({','.join('?' * 3)})", broken[5:8])
            connection.execute("UPDATE vocab_items SET srs_effective_due_at = '2026-10-01T00:00:00Z' WHERE id = ?", (broken[8],))
            connection.execute("UPDATE vocab_items SET srs_effective_due_at = '2026-10-01 00:00:00' WHERE id = ?", (broken[9],))
        result = self.q(limit=3)
        self.assertEqual(self.keys(result), [("personal", item) for item in good])
        self.assertEqual(result["counts"]["invalid_state"], 10)

    def test_known_and_completed_cards_are_still_reviewed(self):  # F5, F6
        item = self.personal("known-due", status="known")
        self.due("personal", item, SrsPhase.REVIEW, NOW - timedelta(hours=1))
        with get_connection() as connection:
            connection.execute("UPDATE vocab_items SET first_completed_at = ? WHERE id = ?", (iso(NOW - timedelta(days=9)), item))
        result = self.q()
        self.assertEqual(result["items"][0]["status"], "known")
        self.assertNotIn("completed", result["items"][0])

    def test_paused_and_broken_counts_as_invalid_once(self):  # A9
        item = self.personal("paused-broken")
        self.fsrs("personal", item, self.state(SrsPhase.REVIEW, NOW), participation="paused")
        with get_connection() as connection:
            connection.execute("UPDATE vocab_items SET srs_step = 2 WHERE id = ?", (item,))  # review with a step
        counts = self.q()["counts"]
        self.assertEqual((counts["invalid_state"], counts["paused"], counts["total_in_scope"]), (1, 0, 1))

    def test_unmaterialized_and_available_never_overlap(self):  # A8
        shared = self.shared_deck("s")
        for index in range(4):
            self.lexeme(f"u{index}", shared, index, progress=False)
        materialized = [self.lexeme(f"m{index}", shared, 10 + index) for index in range(3)]
        for lexeme in materialized:
            self.fsrs("lexeme", lexeme)
        result = self.q(mode="new")
        self.assertEqual((result["counts"]["new_unmaterialized"], result["counts"]["new_available"]), (4, 3))
        # Since Gate C-2a (atomic first-review path) unmaterialized words are served too,
        # marked card_version null / materialized false; the two categories never overlap.
        served = {i["card_id"]: i for i in result["items"]}
        self.assertEqual(len(served), 7)
        self.assertTrue(all(served[m]["materialized"] for m in materialized))
        self.assertEqual(sum(1 for i in result["items"] if i["card_version"] is None), 4)


class QueueUnitPermissionTests(QueueCase):
    def test_scope_permissions_and_loss(self):  # P1-P7
        other_deck = create_deck(self.other, DeckCreate(name="theirs"))[0]["id"]
        with self.assertRaises(queue.QueueError) as raised:
            self.q(scope="personal_deck", deck_id=other_deck)
        self.assertEqual((raised.exception.status_code, raised.exception.code), (404, "deck not found"))
        not_subscribed = self.shared_deck("public-not-mine", subscribe=False)
        with self.assertRaises(queue.QueueError):
            self.q(scope="subscribed_deck", deck_id=not_subscribed)
        deck_a, deck_b = self.shared_deck("a"), self.shared_deck("b")
        word = self.lexeme("w", deck_a)
        only_a = self.lexeme("only-a", deck_a, 1)
        add_word_to_shared_deck(deck_b, word, 0)
        for lexeme in (word, only_a):
            self.due("lexeme", lexeme, SrsPhase.REVIEW, NOW - timedelta(hours=1))
        first = self.q(limit=1)
        self.assertIsNotNone(first["next_cursor"])
        with get_connection() as connection:
            connection.execute("UPDATE user_deck_subscriptions SET is_active = FALSE WHERE user_id = ? AND shared_deck_id = ?",
                               (self.user, deck_a))
            connection.execute("UPDATE shared_decks SET visibility = 'private' WHERE id = ?", (deck_b,))
        result = self.q()
        self.assertEqual(self.keys(result), [("lexeme", word)])          # still reachable via active deck b
        self.assertEqual(result["items"][0]["review"]["shared_deck_id"], deck_b)
        self.assertEqual(result["counts"]["total_in_scope"], 1)
        page_two = self.q(limit=1, cursor=first["next_cursor"])
        self.assertNotIn(("lexeme", only_a), self.keys(page_two))       # P7: conditions re-evaluated

    def test_legacy_and_shadow_accounts_get_409(self):  # P9
        for mode in ("legacy", "shadow"):
            self.set_mode(self.user, mode)
            with self.assertRaises(queue.QueueError) as raised:
                self.q()
            self.assertEqual((raised.exception.status_code, raised.exception.code), (409, "srs_mode_not_fsrs"))
        with get_connection() as connection:
            connection.execute("DELETE FROM srs_user_settings WHERE user_id = ?", (self.user,))
        with self.assertRaises(queue.QueueError):
            self.q()


class QueueUnitGoalTests(QueueCase):
    def fresh(self, count, prefix="n"):
        items = [self.personal(f"{prefix}{i}") for i in range(count)]
        for item in items:
            self.fsrs("personal", item)
        return items

    def test_goal_limits_new_but_never_due(self):  # G1, G2, G8
        self.set_mode(self.user, "fsrs", goal=3)
        self.fresh(5)
        review = self.personal("due")
        self.due("personal", review, SrsPhase.REVIEW, NOW - timedelta(hours=1))
        result = self.q(limit=100)
        self.assertEqual([i["bucket"] for i in result["items"]], ["review_due", "new", "new", "new"])
        self.set_mode(self.user, "fsrs", goal=0)
        result = self.q(limit=100)
        self.assertEqual(self.keys(result), [("personal", review)])
        self.assertEqual(result["counts"]["new_allowed_now"], 0)

    def test_overshoot_is_accepted_and_counted(self):  # G3, G4, G5
        self.set_mode(self.user, "fsrs", goal=3)
        items = self.fresh(6)
        window_one = self.q(mode="new", limit=10)                    # first window takes 3 new cards
        self.assertEqual(len(window_one["items"]), 3)
        first = window_one["items"][0]["card_id"]
        first_response = self.rate("personal", first, "again")       # first Again counts as one
        window_two = self.q(mode="new", limit=10)                    # second window: goal 3, introduced 1 -> 2
        self.assertEqual(len(window_two["items"]), 2)
        served = {i["card_id"] for i in window_one["items"] + window_two["items"]}
        for item in items:
            if item != first:
                self.rate("personal", item, "good")                  # all accepted, even past the goal
        retry = self.rate("personal", first, "again", request=f"r-personal-{first}-0", version=0)
        self.assertEqual(retry, first_response)                      # same receipt, no new event
        self.rate("personal", first, "good", at=NOW + timedelta(minutes=10))  # another rating of a card
        after = self.q(mode="new")
        self.assertEqual(after["new_goal"]["introduced_today"], 6)    # 6 cards, not 8 ratings
        self.assertEqual(after["new_goal"]["account_remaining"], 0)
        self.assertEqual(after["items"], [])
        self.assertFalse(after["new_goal"]["is_strict_limit"])
        # The second window was handed cards the first window already holds; the
        # server cannot know what either window displays (no strict limit).
        self.assertEqual(served, {i["card_id"] for i in window_one["items"]})

    def test_plan_and_account_remaining(self):  # G7
        self.set_mode(self.user, "fsrs", goal=20)
        plan_deck = create_deck(self.user, DeckCreate(name="plan"))[0]["id"]
        in_plan = [self.personal(f"p{i}", deck=plan_deck) for i in range(12)]
        outside = [self.personal(f"o{i}") for i in range(14)]
        for item in in_plan + outside:
            self.fsrs("personal", item)
        for item in in_plan[:4] + outside[:14]:
            self.rate("personal", item, "good")
        result = self.q(scope="personal_deck", deck_id=plan_deck, plan_daily_new=10, mode="new")
        goal = result["new_goal"]
        self.assertEqual((goal["introduced_today"], goal["account_remaining"]), (18, 2))
        self.assertEqual((goal["introduced_today_in_scope"], goal["plan_remaining"]), (4, 6))
        self.assertEqual(len(result["items"]), 2)

    def test_queue_and_review_share_the_definition(self):  # G12, L6
        items = self.fresh(3)
        response = self.rate("personal", items[0], "again")
        self.assertEqual(self.q()["new_goal"]["introduced_today"], response["srs"]["introduced_today"])
        with get_connection() as connection:
            legacy_sql = connection.execute(
                "SELECT MIN(reviewed_at) AS first_at FROM review_logs WHERE user_id = ? GROUP BY vocab_item_id "
                "UNION ALL SELECT MIN(created_at) AS first_at FROM lexeme_review_logs WHERE user_id = ? GROUP BY lexeme_id",
                (self.user, self.user),
            ).fetchall()
            old = sum(reviews.seoul_date(datetime.fromisoformat(r["first_at"])) == reviews.seoul_date(NOW) for r in legacy_sql)
            self.assertEqual(goals.introduction_count(connection, self.user, NOW).count, old)
            self.assertEqual(reviews.introduced_on(connection, self.user, NOW).count, old)

    def test_extra_new_rejected_and_counterexample(self):  # G9, G10
        with self.assertRaises(queue.QueueError) as raised:
            self.q(extra_new=5)
        self.assertEqual((raised.exception.status_code, raised.exception.code), (400, "unsupported_parameter"))
        # Why a per-request extra is not used: it never runs out (contract 4-3).
        allowance = lambda goal, introduced, extra: max(0, goal - introduced) + extra  # noqa: E731
        introduced, grants = 20, []
        for _ in range(3):
            grants.append(allowance(20, introduced, 5))
            introduced += grants[-1]
        self.assertEqual(grants, [5, 5, 5])

    def test_seoul_midnight(self):  # M1, M2, M3
        self.set_mode(self.user, "fsrs", goal=5)
        items = self.fresh(5)
        late_evening = datetime(2026, 10, 9, 14, 59, tzinfo=UTC)   # 23:59 KST
        for item in items[:3]:
            self.rate("personal", item, "good", at=late_evening)
        self.now = late_evening
        self.assertEqual(self.q()["new_goal"]["introduced_today"], 3)
        self.now = datetime(2026, 10, 9, 15, 1, tzinfo=UTC)          # 00:01 KST next day
        result = self.q()
        self.assertEqual((result["seoul_date"], result["new_goal"]["introduced_today"]), ("2026-10-10", 0))
        self.rate("personal", items[3], "good", at=self.now)
        self.assertEqual(self.q()["new_goal"]["introduced_today"], 1)


class QueueUnitCursorTests(QueueCase):
    def fresh(self, count):
        items = [self.personal(f"n{i}") for i in range(count)]
        for item in items:
            self.fsrs("personal", item)
        return items

    def test_six_new_split_four_plus_two(self):  # C4, CONTRACT 2-6-3
        self.set_mode(self.user, "fsrs", goal=6)
        items = self.fresh(9)
        first = self.q(mode="new", limit=4)
        second = self.q(mode="new", limit=4, cursor=first["next_cursor"])
        self.assertEqual([i["card_id"] for i in first["items"]], items[:4])
        self.assertEqual([i["card_id"] for i in second["items"]], items[4:6])
        self.assertIsNone(second["next_cursor"])
        self.assertEqual(second["new_goal"]["chain_new_served"], 6)

    def test_ratings_between_pages_do_not_shrink_the_chain(self):  # C5, C2
        self.set_mode(self.user, "fsrs", goal=6)
        items = self.fresh(9)
        first = self.q(mode="new", limit=4)
        for item in first["items"]:
            self.rate("personal", item["card_id"], "good")
        second = self.q(mode="new", limit=4, cursor=first["next_cursor"])
        self.assertEqual([i["card_id"] for i in second["items"]], items[4:6])
        self.assertEqual(self.q(mode="new", limit=10)["new_goal"]["account_remaining"], 2)

    def test_mixed_due_and_new_pages(self):
        self.set_mode(self.user, "fsrs", goal=3)
        due = [self.personal(f"d{i}") for i in range(3)]
        for index, item in enumerate(due):
            self.due("personal", item, SrsPhase.REVIEW, NOW - timedelta(hours=3, minutes=-index))
        new = self.fresh(5)
        seen, cursor = [], None
        while True:
            page = self.q(limit=2, **({"cursor": cursor} if cursor else {}))
            seen.extend(self.keys(page))
            cursor = page["next_cursor"]
            if not cursor:
                break
        self.assertEqual(seen, [("personal", i) for i in due + new[:3]])

    def test_pages_without_changes_cover_everything_once(self):  # C1
        items = [self.personal(f"r{i}") for i in range(45)]
        for index, item in enumerate(items):
            self.due("personal", item, SrsPhase.REVIEW, NOW - timedelta(minutes=100 - index))
        seen, cursor = [], None
        for _ in range(4):
            page = self.q(limit=20, **({"cursor": cursor} if cursor else {}))
            seen.extend(i["card_id"] for i in page["items"])
            cursor = page["next_cursor"]
            if not cursor:
                break
        self.assertEqual(seen, items)

    def test_tampering_and_malformed_cursors_are_400(self):  # C6, C7, C13
        self.fresh(3)
        token = self.q(mode="new", limit=1)["next_cursor"]
        body, signature = token.split(".")
        flipped = body[:-1] + ("A" if body[-1] != "A" else "B")
        payload = json.loads(queue_cursor._b64decode(body))
        payload["new_allowed0"] = 500
        forged_body = queue_cursor._b64encode(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode())
        bad = [flipped + "." + signature, body + "." + signature[:-2] + "AA", forged_body + "." + signature,
               "x" * 2100, "not-a-cursor", "a.b.c", body, "%%%.%%%"]
        for raw in bad:
            with self.subTest(raw=raw[:20]), self.assertRaises(queue.QueueError) as raised:
                self.q(mode="new", limit=1, cursor=raw)
            self.assertEqual((raised.exception.status_code, raised.exception.code), (400, "invalid_cursor"))
            self.assertNotIn(SECRET, str(raised.exception))
        # Correctly signed but out-of-range / wrong-shape fields are still rejected.
        for change in ({"new_served": 999}, {"last_key": [3, payload["last_key"][1], 0, 0, 1]},
                       {"last_key": [2, payload["last_key"][1], 0, 0, -1]}, {"v": 2}, {"extra": 1}):
            signed = queue_cursor.encode({**payload, "new_allowed0": 1, **change})
            with self.subTest(change=change), self.assertRaises(queue.QueueError) as raised:
                self.q(mode="new", limit=1, cursor=signed)
            self.assertEqual(raised.exception.status_code, 400)

    def test_binding_changes_are_409(self):  # C8-C12, M5
        self.set_mode(self.other, "fsrs")
        deck = create_deck(self.user, DeckCreate(name="d2"))[0]["id"]
        self.fresh(5)
        token = self.q(mode="new", limit=1)["next_cursor"]
        stale = [
            dict(user=self.other, mode="new", limit=1),
            dict(mode="today", limit=1),
            dict(mode="new", limit=1, scope="personal_deck", deck_id=deck),
        ]
        for params in stale:
            with self.subTest(params=params), self.assertRaises(queue.QueueError) as raised:
                self.q(cursor=token, **params)
            self.assertEqual((raised.exception.status_code, raised.exception.code), (409, "cursor_stale"))
        self.set_mode(self.user, "fsrs", goal=20, version=1)
        with self.assertRaises(queue.QueueError) as raised:
            self.q(mode="new", limit=1, cursor=token)
        self.assertEqual(raised.exception.status_code, 409)
        self.set_mode(self.user, "fsrs", goal=20, version=0)
        self.q(mode="new", limit=1, cursor=token)  # identical conditions again: accepted
        with mock.patch.object(queue, "DEFAULT_CONFIG", mock.Mock(config_version="fsrs-6.3.2-a1-other")):
            with self.assertRaises(queue.QueueError) as raised:
                queue.build_queue(queue.parse_request(self.user, [("mode", "new"), ("limit", "1"), ("cursor", token)]))
            self.assertEqual(raised.exception.status_code, 409)
        self.now = datetime(2026, 10, 9, 14, 55, tzinfo=UTC)      # 23:55 KST
        late = self.q(mode="new", limit=1)["next_cursor"]
        self.now = datetime(2026, 10, 9, 15, 1, tzinfo=UTC)       # next Seoul day
        with self.assertRaises(queue.QueueError) as raised:
            self.q(mode="new", limit=1, cursor=late)
        self.assertEqual(raised.exception.status_code, 409)

    def test_status_order_is_normalized_and_status_change_is_409(self):  # C9
        item = self.personal("u")
        self.due("personal", item, SrsPhase.REVIEW, NOW + timedelta(days=1))
        other = self.personal("v", status="uncertain")
        self.due("personal", other, SrsPhase.REVIEW, NOW + timedelta(days=2))
        token = self.q(mode="practice", status=["uncertain", "unknown"], limit=1)["next_cursor"]
        self.assertIsNotNone(token)
        page = self.q(mode="practice", status=["unknown", "uncertain"], limit=1, cursor=token)
        self.assertEqual(self.keys(page), [("personal", other)])
        with self.assertRaises(queue.QueueError) as raised:
            self.q(mode="practice", status=["unknown"], limit=1, cursor=token)
        self.assertEqual(raised.exception.status_code, 409)

    def test_plan_change_is_409(self):  # C10
        self.fresh(4)
        token = self.q(scope="personal_deck", deck_id=self.deck, mode="new", plan_daily_new=3, limit=1)["next_cursor"]
        with self.assertRaises(queue.QueueError) as raised:
            self.q(scope="personal_deck", deck_id=self.deck, mode="new", plan_daily_new=4, limit=1, cursor=token)
        self.assertEqual(raised.exception.status_code, 409)

    def test_chain_lifetime_is_not_extended_by_refreshing_iat(self):  # C12
        self.set_mode(self.user, "fsrs", goal=10)
        self.fresh(6)
        first = self.q(mode="new", limit=1)
        self.now = NOW + timedelta(minutes=10)
        second = self.q(mode="new", limit=1, cursor=first["next_cursor"])
        self.assertNotEqual(json.loads(queue_cursor._b64decode(second["next_cursor"].split(".")[0]))["iat"],
                            json.loads(queue_cursor._b64decode(first["next_cursor"].split(".")[0]))["iat"])
        self.now = NOW + timedelta(minutes=15, seconds=1)
        with self.assertRaises(queue.QueueError) as raised:
            self.q(mode="new", limit=1, cursor=second["next_cursor"])
        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(second["bucket_as_of"], iso(NOW))
        self.assertEqual(second["server_now"], iso(NOW + timedelta(minutes=10)))


class QueueUnitPracticeAndParamsTests(QueueCase):
    def test_practice_mode(self):  # R1-R4
        unsure = self.personal("unsure", status="uncertain")
        self.due("personal", unsure, SrsPhase.REVIEW, NOW + timedelta(days=30))
        known = self.personal("known", status="known")
        self.due("personal", known, SrsPhase.REVIEW, NOW - timedelta(days=1))
        fresh = self.personal("fresh", status="uncertain")
        self.fsrs("personal", fresh)
        result = self.q(mode="practice", status="uncertain")
        self.assertEqual(self.keys(result), [("personal", unsure)])
        self.assertTrue(result["items"][0]["practice_only"])
        self.assertIsNone(result["items"][0]["review"])
        with self.assertRaises(queue.QueueError):
            self.q(mode="today", status="unknown")

    def test_parameter_validation(self):
        bad = [dict(scope="everything"), dict(scope="all", deck_id=1), dict(scope="personal_deck"),
               dict(mode="recent"), dict(limit=0), dict(limit=101), dict(limit="-1"), dict(limit="1.5"),
               dict(status="mastered", mode="practice"), dict(plan_daily_new=5), dict(cursor=""),
               dict(limit=[1, 2])]
        for params in bad:
            with self.subTest(params=params), self.assertRaises(queue.QueueError) as raised:
                self.q(**params)
            self.assertEqual(raised.exception.status_code, 400)


class QueueUnitConsistencyAndWriteTests(QueueCase):
    def _overlap(self, snapshot_enabled):
        item = self.personal("contested")
        self.fsrs("personal", item)
        original = goals.first_review_dates
        state = {}

        def writer():
            state["result"] = self.rate("personal", item, "again")

        def hooked(*args, **kwargs):
            if "thread" not in state:
                state["thread"] = threading.Thread(target=writer)
                state["thread"].start()
                time.sleep(0.6)
                state["writer_done_during_read"] = not state["thread"].is_alive()
            return original(*args, **kwargs)

        patches = [mock.patch.object(queue.goals, "first_review_dates", side_effect=hooked)]
        if not snapshot_enabled:
            patches.append(mock.patch.object(queue, "_begin_snapshot", lambda connection: None))
        for patch in patches:
            patch.start()
        try:
            result = self.q()
        finally:
            for patch in patches:
                patch.stop()
        state["thread"].join(timeout=15)
        return item, result, state

    def test_list_counts_and_goal_come_from_one_read(self):
        item, result, state = self._overlap(snapshot_enabled=True)
        self.assertFalse(state["writer_done_during_read"])     # the review waited for our read
        self.assertEqual(self.keys(result), [("personal", item)])
        self.assertEqual(result["counts"]["new_available"], 1)
        self.assertEqual(result["new_goal"]["introduced_today"], 0)   # same state as the list
        self.assertIsNotNone(state["result"])                  # and the review then succeeded
        self.assertEqual(self.q()["new_goal"]["introduced_today"], 1)

    def test_without_the_snapshot_the_same_overlap_is_inconsistent(self):
        # Control: shows the test above is meaningful.
        item, result, state = self._overlap(snapshot_enabled=False)
        self.assertTrue(state["writer_done_during_read"])
        self.assertEqual(self.keys(result), [("personal", item)])     # listed as new...
        self.assertEqual(result["new_goal"]["introduced_today"], 1)   # ...yet already counted

    def test_no_writes_on_any_path(self):  # W1, W3, W4, W5
        shared = self.shared_deck("s")
        self.lexeme("unmaterialized", shared, 0, progress=False)
        fresh = self.personal("fresh")
        self.fsrs("personal", fresh)
        due = self.personal("due")
        self.due("personal", due, SrsPhase.REVIEW, NOW - timedelta(hours=1))
        before = self.snapshot()
        calls = [dict(), dict(mode="new"), dict(mode="practice"), dict(scope="subscribed_deck", deck_id=shared),
                 dict(limit=1), dict(extra_new=1), dict(scope="personal_deck", deck_id=99999), dict(cursor="bad")]
        token = self.q(limit=1)["next_cursor"]
        calls.append(dict(limit=1, cursor=token))
        for params in calls:
            try:
                self.q(**params)
            except queue.QueueError:
                pass
        self.assertEqual(self.snapshot(), before)  # rows and database file bytes unchanged
        self.set_mode(self.user, "legacy")
        legacy_before = self.snapshot()
        with self.assertRaises(queue.QueueError):
            self.q()
        self.assertEqual(self.snapshot(), legacy_before)
        self.set_mode(self.user, "fsrs")
        self.assertEqual(self.snapshot()[0], before[0])

    def test_read_only_connection_rejects_writes(self):  # W2
        with get_connection(read_only=True) as connection:
            queue._begin_snapshot(connection)
            with self.assertRaises(Exception):
                connection.execute("UPDATE users SET display_name = 'x'")


class QueueStepRangeTests(QueueCase):
    """Gate C-1 correction: a Learning/Relearning step must exist in the card's
    config (learning 2 steps, relearning 1). The queue and reviews share one rule."""

    def step_card(self, kind, ref, phase, step):
        state = SrsCardState(phase=phase, step=step, stability=2.3, difficulty=5.0,
                             due_at=NOW - timedelta(minutes=1), last_review_at=NOW - timedelta(minutes=11))
        self.fsrs(kind, ref, state)

    def test_queue_counts_out_of_range_steps_as_invalid(self):
        cases = [(SrsPhase.LEARNING, 0, True), (SrsPhase.LEARNING, 1, True), (SrsPhase.LEARNING, 2, False),
                 (SrsPhase.LEARNING, 999, False), (SrsPhase.RELEARNING, 0, True), (SrsPhase.RELEARNING, 1, False)]
        expected_served = []
        for index, (phase, step, valid) in enumerate(cases):
            item = self.personal(f"step-{phase.value}-{step}")
            self.step_card("personal", item, phase, step)
            if valid:
                expected_served.append(item)
        result = self.q(limit=100)
        self.assertEqual(sorted(i["card_id"] for i in result["items"]), sorted(expected_served))
        self.assertEqual(result["counts"]["invalid_state"], 3)
        self.assertEqual(sum(result["counts"][c] for c in queue.CATEGORIES), result["counts"]["total_in_scope"])

    def test_reviews_reject_out_of_range_steps_before_any_write(self):
        shared = self.shared_deck("s")
        lexeme = self.lexeme("lx-step", shared)
        item = self.personal("p-step")
        self.step_card("personal", item, SrsPhase.LEARNING, 999)
        self.step_card("lexeme", lexeme, SrsPhase.RELEARNING, 1)
        client = TestClient(main.app)
        self.addCleanup(client.close)
        headers = {"Authorization": "Bearer " + create_access_token({"id": self.user, "email": "c1@example.test"})}
        before = self.snapshot()
        for path, request_id in [(f"/study-items/{item}/review", "bad-step-p"),
                                 (f"/shared-decks/{shared}/words/{lexeme}/review", "bad-step-l")]:
            response = client.post(path, headers=headers, json=dict(
                rating="good", request_id=request_id, expected_card_version=0, session_id="s"))
            self.assertEqual((response.status_code, response.json()["detail"]), (409, "invalid_engine_state"))
        self.assertEqual(self.snapshot(), before)  # no card, log, receipt or progress change; same bytes

    def test_in_range_steps_follow_the_library(self):
        expectations = [(SrsPhase.LEARNING, 0, "good", "learning", 1), (SrsPhase.LEARNING, 1, "good", "review", None),
                        (SrsPhase.LEARNING, 1, "again", "learning", 0), (SrsPhase.RELEARNING, 0, "good", "review", None),
                        (SrsPhase.RELEARNING, 0, "hard", "relearning", 0)]
        for phase, step, grade, phase_after, step_after in expectations:
            with self.subTest(phase=phase.value, step=step, grade=grade):
                item = self.personal(f"ok-{phase.value}-{step}-{grade}")
                self.step_card("personal", item, phase, step)
                result = self.rate("personal", item, grade)
                self.assertEqual((result["srs"]["state"]["phase"], result["srs"]["state"]["step"]), (phase_after, step_after))


class QueueCorruptTimeTests(QueueCase):
    """Approved CORRUPT_REVIEW_TIME_PROPOSAL.md (TEST_MATRIX 14). Logs are only
    read; the injected corrupt rows below are synthetic fixtures."""

    def setUp(self):
        super().setUp()
        self.client = TestClient(main.app)
        self.addCleanup(self.client.close)
        self.headers = {"Authorization": "Bearer " + create_access_token({"id": self.user, "email": "c1@example.test"})}

    def personal_log(self, item, text, rating="good"):
        with get_connection() as connection:
            connection.execute(
                "INSERT INTO review_logs (user_id, vocab_item_id, rating, reviewed_at, previous_review_level, "
                "next_review_level, next_review_at) VALUES (?, ?, ?, ?, 0, 1, ?)", (self.user, item, rating, text, iso(NOW)))

    def lexeme_log(self, lexeme, deck, text):
        with get_connection() as connection:
            connection.execute(
                "INSERT INTO lexeme_review_logs (user_id, lexeme_id, shared_deck_id, rating, previous_review_level, "
                "new_review_level, previous_status, new_status, created_at) VALUES (?, ?, ?, 'good', 0, 1, 'u', 'u', ?)",
                (self.user, lexeme, deck, text))

    def logs(self):
        with get_connection() as connection:
            return ([tuple(r) for r in connection.execute("SELECT * FROM review_logs ORDER BY id").fetchall()],
                    [tuple(r) for r in connection.execute("SELECT * FROM lexeme_review_logs ORDER BY id").fetchall()])

    def base(self):
        """One due card, two new cards, one card introduced today with a good time."""
        due = self.personal("due")
        self.due("personal", due, SrsPhase.REVIEW, NOW - timedelta(hours=1))
        fresh = [self.personal(f"fresh{i}") for i in range(2)]
        for item in fresh:
            self.fsrs("personal", item)
        legacy_today = self.personal("legacy-today")
        self.personal_log(legacy_today, iso(NOW - timedelta(hours=2)))
        return due, fresh

    def assert_new_blocked(self, result, due, at_least, unreadable=1):
        goal = result["new_goal"]
        self.assertEqual((goal["introduced_today"], goal["introduced_today_status"]), (None, "unknown"))
        self.assertEqual((goal["introduced_today_at_least"], goal["unreadable_review_time_cards"]), (at_least, unreadable))
        self.assertIsNone(goal["account_remaining"])
        self.assertEqual(goal["new_blocked_reason"], "review_time_unreadable")
        self.assertEqual(self.keys(result), [("personal", due)])       # due kept, no new
        self.assertEqual(result["counts"]["new_allowed_now"], 0)

    def test_unreadable_times_personal_lexeme_empty_naive(self):  # T1-T4, T13
        due, _ = self.base()
        shared = self.shared_deck("s")
        cases = [("personal", "garbage"), ("personal", ""), ("lexeme", "garbage"), ("lexeme", ""),
                 ("personal", "2026-10-09 00:00:00"), ("personal", "2026-10-09T00:00:00")]
        for index, (kind, text) in enumerate(cases):
            with self.subTest(kind=kind, text=text):
                if kind == "personal":
                    victim = self.personal(f"victim{index}")
                    self.personal_log(victim, text)
                else:
                    victim = self.lexeme(f"victim{index}", shared, index, progress=False)
                    self.lexeme_log(victim, shared, text)
                before_logs = self.logs()
                response = self.client.get("/study-queue?limit=50", headers=self.headers)
                self.assertEqual(response.status_code, 200)
                self.assert_new_blocked(response.json(), due, at_least=1)
                self.assertEqual(self.logs(), before_logs)                    # original rows untouched
                with get_connection() as connection:                          # remove fixture for next case
                    table = "review_logs" if kind == "personal" else "lexeme_review_logs"
                    column = "vocab_item_id" if kind == "personal" else "lexeme_id"
                    connection.execute(f"DELETE FROM {table} WHERE {column} = ?", (victim,))

    def test_offsets_are_compared_as_real_instants(self):  # T5, MIN masking, midnight
        due, fresh = self.base()
        # String MIN would pick '...T00:30:00+00:00' (today, 09:30 KST) but the
        # real first review is '...T01:00:00+12:00' = 10-08 13:00 UTC = 22:00 KST yesterday.
        card = self.personal("offsets")
        self.personal_log(card, "2026-10-09T00:30:00+00:00")
        self.personal_log(card, "2026-10-09T01:00:00+12:00")
        z_card = self.personal("zulu")
        self.personal_log(z_card, "2026-10-09T00:10:00Z")                  # 09:10 KST today
        midnight = self.personal("midnight")
        self.personal_log(midnight, "2026-10-08T14:59:59+00:00")           # 23:59:59 KST yesterday
        goal = self.q(limit=50)["new_goal"]
        self.assertEqual((goal["introduced_today"], goal["introduced_today_status"]), (2, "exact"))  # legacy-today + zulu
        self.assertEqual(goal["unreadable_review_time_cards"], 0)

    def test_valid_log_does_not_hide_a_corrupt_one(self):  # T6
        due, _ = self.base()
        card = self.personal("masked")
        self.personal_log(card, iso(NOW - timedelta(days=3)))
        self.personal_log(card, "garbage")   # sorts after digits: string MIN used to ignore it
        self.assert_new_blocked(self.q(limit=50), due, at_least=1)

    def test_deleted_card_with_corrupt_log(self):  # T7 (SQLite keeps the log)
        due, _ = self.base()
        victim = self.personal("deleted")
        self.personal_log(victim, "")
        with get_connection() as connection:
            connection.execute("DELETE FROM vocab_items WHERE id = ?", (victim,))
        self.assert_new_blocked(self.q(limit=50), due, at_least=1)

    def test_corrupt_card_itself_is_invalid_state(self):
        due, _ = self.base()
        own = self.personal("own-corrupt")
        self.due("personal", own, SrsPhase.REVIEW, NOW - timedelta(hours=2))
        self.personal_log(own, "garbage")
        result = self.q(limit=50)
        self.assertNotIn(("personal", own), self.keys(result))
        self.assertEqual(result["counts"]["invalid_state"], 1)
        self.assertEqual(sum(result["counts"][c] for c in queue.CATEGORIES), result["counts"]["total_in_scope"])

    def test_scope_exact_but_account_unknown_blocks_new(self):  # T11
        plan_deck = create_deck(self.user, DeckCreate(name="plan"))[0]["id"]
        fresh = [self.personal(f"p{i}", deck=plan_deck) for i in range(3)]
        for item in fresh:
            self.fsrs("personal", item)
        outside = self.personal("outside")
        self.personal_log(outside, "garbage")
        result = self.q(scope="personal_deck", deck_id=plan_deck, mode="new", plan_daily_new=5)
        goal = result["new_goal"]
        self.assertEqual((goal["introduced_today_in_scope"], goal["introduced_today_in_scope_status"]), (0, "exact"))
        self.assertEqual(goal["plan_remaining"], 5)
        self.assertEqual(goal["introduced_today_status"], "unknown")
        self.assertEqual(result["items"], [])
        inside = self.personal("inside", deck=plan_deck)
        self.personal_log(inside, "")
        goal = self.q(scope="personal_deck", deck_id=plan_deck, mode="new", plan_daily_new=5)["new_goal"]
        self.assertEqual((goal["introduced_today_in_scope_status"], goal["plan_remaining"]), ("unknown", None))

    def test_cursor_is_invalidated_when_the_status_changes(self):  # T12
        self.set_mode(self.user, "fsrs", goal=10)
        for i in range(5):
            self.fsrs("personal", self.personal(f"n{i}"))
        token = self.q(mode="new", limit=1)["next_cursor"]
        victim = self.personal("victim")
        self.personal_log(victim, "garbage")
        with self.assertRaises(queue.QueueError) as raised:
            self.q(mode="new", limit=1, cursor=token)                    # no more new after corruption
        self.assertEqual((raised.exception.status_code, raised.exception.code), (409, "cursor_stale"))
        blocked = self.q(mode="new", limit=1)
        self.assertEqual(blocked["items"], [])
        with get_connection() as connection:                              # fixture repaired by the test itself
            connection.execute("DELETE FROM review_logs WHERE vocab_item_id = ?", (victim,))
        due = self.personal("due-for-cursor")
        self.due("personal", due, SrsPhase.REVIEW, NOW - timedelta(hours=1))
        self.due("personal", self.personal("due2"), SrsPhase.REVIEW, NOW - timedelta(minutes=30))
        self.personal_log(victim, "garbage")
        unknown_token = self.q(limit=1)["next_cursor"]
        with get_connection() as connection:
            connection.execute("DELETE FROM review_logs WHERE vocab_item_id = ?", (victim,))
        with self.assertRaises(queue.QueueError) as raised:
            self.q(limit=1, cursor=unknown_token)
        self.assertEqual(raised.exception.status_code, 409)

    def review_body(self, item, request_id):
        with get_connection() as connection:
            version = connection.execute("SELECT srs_card_version FROM vocab_items WHERE id = ?", (item,)).fetchone()[0]
        return dict(rating="good", request_id=request_id, expected_card_version=version, session_id="s1")

    def test_review_of_a_healthy_card_records_unknown_count(self):  # T8, T10
        due, fresh = self.base()
        victim = self.personal("other")
        self.personal_log(victim, "garbage")
        body = self.review_body(fresh[0], "healthy-1")
        with mock.patch.object(reviews, "now_utc", return_value=NOW):
            first = self.client.post(f"/study-items/{fresh[0]}/review", headers=self.headers, json=body)
        self.assertEqual(first.status_code, 200)
        srs = first.json()["srs"]
        self.assertEqual((srs["introduced_today"], srs["introduced_today_status"], srs["introduced_today_at_least"]),
                         (None, "unknown", 2))
        with get_connection() as connection:
            stored = connection.execute("SELECT response_json FROM srs_review_receipts WHERE request_id = 'healthy-1'").fetchone()
        self.assertIsNone(json.loads(stored["response_json"])["srs"]["introduced_today"])
        with get_connection() as connection:                               # later state changes...
            connection.execute("DELETE FROM review_logs WHERE vocab_item_id = ?", (victim,))
        with mock.patch.object(reviews, "now_utc", return_value=NOW + timedelta(minutes=1)):
            retry = self.client.post(f"/study-items/{fresh[0]}/review", headers=self.headers, json=body)
        self.assertEqual(retry.json(), first.json())                       # ...the first receipt is returned
        changed = self.client.post(f"/study-items/{fresh[0]}/review", headers=self.headers, json=body | {"rating": "easy"})
        self.assertEqual(changed.status_code, 409)

    def test_review_of_a_card_with_unreadable_history_writes_nothing(self):  # T9
        own = self.personal("own")
        self.due("personal", own, SrsPhase.REVIEW, NOW - timedelta(hours=1))
        self.personal_log(own, "garbage")
        shared = self.shared_deck("s")
        lexeme = self.lexeme("own-lx", shared)
        self.due("lexeme", lexeme, SrsPhase.REVIEW, NOW - timedelta(hours=1))
        self.lexeme_log(lexeme, shared, "")
        before = self.snapshot()
        for path, request_id in [(f"/study-items/{own}/review", "own-p"), (f"/shared-decks/{shared}/words/{lexeme}/review", "own-l")]:
            response = self.client.post(path, headers=self.headers, json=dict(
                rating="good", request_id=request_id, expected_card_version=0, session_id="s1"))
            self.assertEqual((response.status_code, response.json()["detail"]), (409, "review_history_unreadable"))
        self.assertEqual(self.snapshot(), before)

    def test_completion_events_use_real_time_order(self):
        card = self.personal("mixed-offsets")
        self.due("personal", card, SrsPhase.REVIEW, NOW - timedelta(hours=1))
        # String order is the reverse of the real order for these two.
        self.personal_log(card, "2026-10-01T01:00:00+12:00")   # 09-30 13:00 UTC (earlier)
        self.personal_log(card, "2026-10-01T00:30:00+00:00")   # 10-01 00:30 UTC (later)
        with get_connection() as connection:
            connection.execute("UPDATE vocab_items SET srs_last_review_at = ?, srs_history_quality = 'incomplete' "
                               "WHERE id = ?", ("2026-10-08T03:00:00+00:00", card))
        response = self.rate("personal", card, "good")
        self.assertIsNotNone(response)

    def test_rollback_with_a_corrupt_log_keeps_the_whole_transaction(self):
        from app.srs import migration
        item = self.personal("rollback")
        result = migration.apply_plan(migration.dry_run([CardKey("personal", self.user, item)]), "apply-rb", approved=True)
        self.assertEqual(result[0]["result"], "applied")
        self.rate("personal", item, "good")
        with get_connection() as connection:
            connection.execute("UPDATE review_logs SET reviewed_at = 'garbage' WHERE vocab_item_id = ?", (item,))
        before = self.snapshot()
        with self.assertRaises(migration.RollbackHistoryUnreadable) as raised:
            migration.rollback_plan("apply-rb", "rollback-rb", user_id=self.user, approved=True)
        # Gate D-2 U8: the unreadable later log is named (not a version conflict, not a
        # bare parse error) and the whole rollback transaction is still discarded.
        self.assertEqual(raised.exception.code, "rollback_history_unreadable")
        self.assertEqual([(c["kind"], c["ref_id"], [l["cause"] for l in c["logs"]]) for c in raised.exception.cards],
                         [("personal", item, ["time"])])
        self.assertEqual(self.snapshot(), before)   # nothing partially rolled back, no run row left


# ---------------------------------------------------------------------------
class QueueApiTests(QueueCase):
    def setUp(self):
        super().setUp()
        self.client = TestClient(main.app)
        self.addCleanup(self.client.close)
        self.token = create_access_token({"id": self.user, "email": "c1@example.test"})

    def get(self, params="", token=None):
        headers = {} if token == "" else {"Authorization": "Bearer " + (token or self.token)}
        return self.client.get("/study-queue" + params, headers=headers)

    def test_http_statuses_and_shape(self):
        item = self.personal("api")
        self.due("personal", item, SrsPhase.REVIEW, NOW - timedelta(hours=1))
        ok = self.get("?limit=5")
        self.assertEqual(ok.status_code, 200)
        body = ok.json()
        self.assertEqual(body["items"][0]["review"]["path"], f"/study-items/{item}/review")
        self.assertEqual(body["counts"]["total_in_scope"], sum(body["counts"][c] for c in queue.CATEGORIES))
        self.assertEqual(self.get(token="").status_code, 401)
        self.assertEqual(self.get("?extra_new=3").json()["detail"], "unsupported_parameter")
        self.assertEqual(self.get("?limit=abc").status_code, 400)
        self.assertEqual(self.get("?cursor=garbage").status_code, 400)
        self.assertEqual(self.get("?scope=personal_deck&deck_id=999999").status_code, 404)
        self.set_mode(self.user, "legacy")
        legacy = self.get()
        self.assertEqual((legacy.status_code, legacy.json()["detail"]), (409, "srs_mode_not_fsrs"))

    def test_legacy_routes_unchanged_by_queue_reads(self):  # L4 (same-process comparison)
        shared = self.shared_deck("s")
        self.lexeme("legacy-lx", shared)
        self.personal("legacy-p")
        before = [self.client.get(path, headers={"Authorization": "Bearer " + self.token}).json()
                  for path in ("/study-items", "/study-items/lexemes", "/study-items/lexemes?due_only=true",
                               "/study-items/lexemes?first_review_only=true&limit=5", "/vocab-items")]
        self.get()
        self.get("?mode=practice")
        after = [self.client.get(path, headers={"Authorization": "Bearer " + self.token}).json()
                 for path in ("/study-items", "/study-items/lexemes", "/study-items/lexemes?due_only=true",
                              "/study-items/lexemes?first_review_only=true&limit=5", "/vocab-items")]
        self.assertEqual(before, after)


class QueueLoopbackHttpTests(QueueCase):
    def test_real_http_server(self):
        item = self.personal("http")
        self.due("personal", item, SrsPhase.REVIEW, datetime.now(UTC) - timedelta(hours=1))
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]
        root = Path(__file__).resolve().parents[1]
        log = (Path(self.directory.name) / "owned-c1-server.log").open("w", encoding="utf-8")
        process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port), "--lifespan", "off"],
            cwd=root, env=dict(os.environ), stdout=log, stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        try:
            base = f"http://127.0.0.1:{port}"
            for _ in range(100):
                if process.poll() is not None:
                    self.fail("owned test server exited")
                try:
                    with urlopen(base + "/health", timeout=1):
                        break
                except (URLError, TimeoutError, ConnectionError):
                    time.sleep(0.1)
            token = create_access_token({"id": self.user, "email": "c1@example.test"})

            def get(query, auth=True):
                request = Request(base + "/study-queue" + query,
                                  headers={"Authorization": "Bearer " + token} if auth else {})
                try:
                    with urlopen(request, timeout=5) as response:
                        return response.status, json.load(response)
                except HTTPError as error:
                    with error:
                        return error.code, json.load(error)

            before = self.snapshot()
            status, body = get("?limit=5")
            self.assertEqual(status, 200)
            self.assertEqual([i["card_id"] for i in body["items"]], [item])
            self.assertEqual(get("?extra_new=1"), (400, {"detail": "unsupported_parameter"}))
            self.assertEqual(get("", auth=False)[0], 401)
            self.assertEqual(get("?cursor=AAAA.BBBB")[0], 400)
            self.set_mode(self.user, "shadow")
            self.assertEqual(get(""), (409, {"detail": "srs_mode_not_fsrs"}))
            self.set_mode(self.user, "fsrs")
            self.assertEqual(self.snapshot()[0], before[0])
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            log.close()
        self.assertIsNotNone(process.returncode)


if __name__ == "__main__":
    unittest.main()

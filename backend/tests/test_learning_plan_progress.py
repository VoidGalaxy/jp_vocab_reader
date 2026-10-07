"""Tests for the read-only first-review progress used by the 학습 계획 tab.

Uses stdlib unittest only and a throwaway SQLite file (never backend/vocab.db
and never whatever DATABASE_URL is already set).

Run directly:      python tests/test_learning_plan_progress.py
Or via discovery:   python -m unittest discover -s tests

PostgreSQL comparison (opt-in): set LEARNING_PLAN_TEST_POSTGRES_URL to a
freshly created, empty database on localhost named jp_vocab_test[_...] (e.g.
postgresql://user:pass@localhost:5432/jp_vocab_test_plan) and run this file
directly. tests/_local_postgres_guard.py checks the target on what psycopg
parses, then makes one read-only connection to confirm the database is empty,
before init_db() or any write; anything else stops the run. A plain
DATABASE_URL is never used. The run leaves its tables behind, so the next run
needs a new database.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

_POSTGRES_URL = os.environ.get("LEARNING_PLAN_TEST_POSTGRES_URL", "").strip()
if _POSTGRES_URL:
    # Once per run, before any test class runs init_db() or writes: the URL
    # is checked on what psycopg parses (query host/hostaddr, host lists,
    # sockets, service, PG* env, test-only dbname), then one read-only
    # connection confirms the database is empty. Later classes in the same
    # run then see only the tables this run created.
    from _local_postgres_guard import (
        UnsafePostgresTarget,
        assert_empty_postgres_test_database,
        validate_local_postgres_test_url,
    )

    try:
        _checked_url = validate_local_postgres_test_url(_POSTGRES_URL)
        assert_empty_postgres_test_database(_checked_url)
    except UnsafePostgresTarget as error:
        raise SystemExit(f"LEARNING_PLAN_TEST_POSTGRES_URL refused: {error}") from None
    os.environ["DATABASE_URL"] = _checked_url
    _EXPECTED_DATABASE_URL: str | None = _checked_url
else:
    _EXPECTED_DATABASE_URL = None
    _SCRATCH_DB = Path(tempfile.gettempdir()) / "jp_vocab_reader_learning_plan_test.db"
    _SCRATCH_DB.unlink(missing_ok=True)
    os.environ["DATABASE_URL"] = f"sqlite:///{_SCRATCH_DB.as_posix()}"

from fastapi.testclient import TestClient  # noqa: E402

from app import main  # noqa: E402
from app.database import get_connection, init_db  # noqa: E402
from app.repositories import learning_plan_repository  # noqa: E402
from app.repositories.deck_package_repository import (  # noqa: E402
    export_deck_package,
    import_deck_package,
)
from app.repositories.deck_repository import create_deck, delete_deck_with_items  # noqa: E402
from app.repositories.learning_plan_repository import get_plan_progress  # noqa: E402
from app.repositories.lexeme_repository import (  # noqa: E402
    add_word_to_shared_deck,
    get_or_create_subscription,
    list_subscribed_lexeme_study_items,
    record_lexeme_review,
    update_word_status,
    upsert_lexeme,
)
from app.repositories.user_repository import create_user  # noqa: E402
from app.repositories.vocab_repository import (  # noqa: E402
    create_or_update_vocab_item,
    delete_vocab_item,
    record_review,
    update_vocab_item,
)
from app.schemas import DeckCreate, DeckPackage, VocabItemCreate, VocabItemUpdate  # noqa: E402


def _require_checked_target() -> None:
    """PostgreSQL mode: every class init and every test start re-confirms
    that DATABASE_URL is still the URL the guard checked. Another test module
    imported in the same run (unittest discovery) may have pointed it at its
    own SQLite file; then this fails before init_db() or any write instead of
    quietly testing SQLite and reporting a PostgreSQL pass. Only direct runs
    of this file are supported in PostgreSQL mode."""
    if _EXPECTED_DATABASE_URL is not None and os.environ.get("DATABASE_URL") != _EXPECTED_DATABASE_URL:
        raise RuntimeError(
            "LEARNING_PLAN_TEST_POSTGRES_URL is set, but DATABASE_URL no longer points at the "
            "checked PostgreSQL test database (changed by another test module?). Nothing was "
            "initialized or written. Run tests/test_learning_plan_progress.py directly."
        )


def _user(email: str) -> int:
    return int(create_user(email=email, display_name=email, password_hash="x")["id"])


def _shared_deck(owner_id: int, title: str) -> int:
    stamp = datetime.now(timezone.utc).isoformat()
    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO shared_decks (owner_user_id, title, description, created_at, updated_at)
            VALUES (?, ?, '', ?, ?)
            """,
            (owner_id, title, stamp, stamp),
        )
        return int(cursor.lastrowid)


class LearningPlanProgressTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        _require_checked_target()
        init_db()

    def setUp(self) -> None:
        _require_checked_target()
        self.user = _user(f"plan-{self.id()}@example.test")
        self.other = _user(f"other-{self.id()}@example.test")
        self.deck = create_deck(self.user, DeckCreate(name=f"deck {self.id()}"))[0]["id"]

    def _word(self, base: str, deck_id: int | None = None, status: str = "unknown") -> int:
        item, _ = create_or_update_vocab_item(
            self.user,
            VocabItemCreate(surface=base, base_form=base, reading=base, status=status, deck_id=deck_id or self.deck),
        )
        return int(item["id"])

    # --- personal ---------------------------------------------------------
    def test_personal_first_review_counts_once(self) -> None:
        a, b, _c = self._word("あ"), self._word("い"), self._word("う")
        self.assertEqual(get_plan_progress(self.user, "personal", self.deck)["seen"], 0)
        record_review(self.user, a, "good")
        record_review(self.user, a, "good")
        record_review(self.user, a, "again")
        record_review(self.user, b, "again")  # a failed first recall is still "seen"
        p = get_plan_progress(self.user, "personal", self.deck)
        self.assertEqual((p["total"], p["seen"]), (3, 2))
        self.assertEqual(p["progress_scope"], "deck_cards")
        self.assertEqual(p["metric_version"], "first-review-v1")

    def test_personal_status_change_is_not_seen(self) -> None:
        a = self._word("か")
        update_vocab_item(self.user, a, VocabItemUpdate(status="known"))
        self.assertEqual(get_plan_progress(self.user, "personal", self.deck)["seen"], 0)

    def test_rating_another_users_card_counts_nothing(self) -> None:
        a = self._word("き")
        self.assertIsNone(record_review(self.other, a, "good"))
        self.assertEqual(get_plan_progress(self.user, "personal", self.deck)["seen"], 0)

    def test_copied_deck_starts_without_history(self) -> None:
        a = self._word("さ")
        record_review(self.user, a, "good")
        package = export_deck_package(self.user, self.deck)
        copied = import_deck_package(self.user, DeckPackage(**package))["deck_id"]
        self.assertEqual(get_plan_progress(self.user, "personal", self.deck)["seen"], 1)
        copy = get_plan_progress(self.user, "personal", copied)
        self.assertEqual((copy["total"], copy["seen"]), (1, 0))

    def test_current_deck_contents_only(self) -> None:
        a, b = self._word("た"), self._word("ち")
        record_review(self.user, a, "good")
        record_review(self.user, b, "good")
        delete_vocab_item(self.user, b)
        self.assertEqual(
            (get_plan_progress(self.user, "personal", self.deck)["total"], get_plan_progress(self.user, "personal", self.deck)["seen"]),
            (1, 1),
        )
        second = create_deck(self.user, DeckCreate(name=f"second {self.id()}"))[0]["id"]
        update_vocab_item(self.user, a, VocabItemUpdate(deck_id=second))
        self.assertEqual(get_plan_progress(self.user, "personal", self.deck)["total"], 0)
        moved = get_plan_progress(self.user, "personal", second)
        self.assertEqual((moved["total"], moved["seen"]), (1, 1))

    def test_empty_and_foreign_personal_decks(self) -> None:
        empty = create_deck(self.user, DeckCreate(name=f"empty {self.id()}"))[0]["id"]
        self.assertEqual(get_plan_progress(self.user, "personal", empty)["total"], 0)
        self.assertIsNone(get_plan_progress(self.other, "personal", self.deck))
        self.assertIsNone(get_plan_progress(self.user, "personal", 999_999))
        delete_deck_with_items(self.user, empty)
        self.assertIsNone(get_plan_progress(self.user, "personal", empty))

    # --- subscribed -------------------------------------------------------
    def _lexeme_decks(self) -> tuple[int, int, list[int]]:
        tag = self.id().rsplit(".", 1)[-1]
        lex = [upsert_lexeme(f"{tag}{n}", f"{tag}{n}", reading=f"r{n}") for n in range(3)]
        deck_a, deck_b = _shared_deck(self.other, f"A {tag}"), _shared_deck(self.other, f"B {tag}")
        for order, lexeme in enumerate(lex):
            add_word_to_shared_deck(deck_a, lexeme, order)
        add_word_to_shared_deck(deck_b, lex[0], 0)  # shared with deck A
        add_word_to_shared_deck(deck_b, lex[0], 1)  # idempotent re-add: still one row
        return deck_a, deck_b, lex

    def test_subscribed_shared_progress_and_dedup(self) -> None:
        deck_a, deck_b, lex = self._lexeme_decks()
        get_or_create_subscription(self.user, deck_a)
        get_or_create_subscription(self.user, deck_b)
        self.assertEqual(get_plan_progress(self.user, "subscribed", deck_a)["seen"], 0)
        record_lexeme_review(self.user, lex[0], "again", shared_deck_id=deck_a)
        record_lexeme_review(self.user, lex[0], "good", shared_deck_id=deck_a)
        a = get_plan_progress(self.user, "subscribed", deck_a)
        b = get_plan_progress(self.user, "subscribed", deck_b)
        self.assertEqual((a["total"], a["seen"]), (3, 1))
        # learned through deck A, already seen in deck B (account-shared progress)
        self.assertEqual((b["total"], b["seen"]), (1, 1))
        self.assertEqual(b["progress_scope"], "account_shared")

    def test_subscribed_status_change_is_not_seen(self) -> None:
        deck_a, _deck_b, lex = self._lexeme_decks()
        get_or_create_subscription(self.user, deck_a)
        update_word_status(self.user, lex[1], "known")
        self.assertEqual(get_plan_progress(self.user, "subscribed", deck_a)["seen"], 0)

    def test_subscribed_progress_is_per_account(self) -> None:
        deck_a, _deck_b, lex = self._lexeme_decks()
        get_or_create_subscription(self.user, deck_a)
        get_or_create_subscription(self.other, deck_a)
        record_lexeme_review(self.other, lex[2], "good", shared_deck_id=deck_a)
        self.assertEqual(get_plan_progress(self.user, "subscribed", deck_a)["seen"], 0)
        self.assertEqual(get_plan_progress(self.other, "subscribed", deck_a)["seen"], 1)

    def test_subscription_required(self) -> None:
        deck_a, _deck_b, _lex = self._lexeme_decks()
        self.assertIsNone(get_plan_progress(self.user, "subscribed", deck_a))
        get_or_create_subscription(self.user, deck_a)
        with get_connection() as connection:
            connection.execute(
                "UPDATE user_deck_subscriptions SET is_active = FALSE WHERE user_id = ? AND shared_deck_id = ?",
                (self.user, deck_a),
            )
        self.assertIsNone(get_plan_progress(self.user, "subscribed", deck_a))

    # --- dates ------------------------------------------------------------
    def test_today_is_seoul_date(self) -> None:
        for utc, expected in (
            (datetime(2026, 10, 31, 14, 59, 59, tzinfo=timezone.utc), "2026-10-31"),
            (datetime(2026, 10, 31, 15, 0, 0, tzinfo=timezone.utc), "2026-11-01"),
        ):
            with mock.patch.object(learning_plan_repository, "now_utc", return_value=utc):
                p = get_plan_progress(self.user, "personal", self.deck)
            self.assertEqual(p["today"], expected)
            self.assertEqual(p["as_of"], utc.isoformat())


class LearningPlanProgressEndpointTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        _require_checked_target()
        init_db()
        cls.client = TestClient(main.app)

    def setUp(self) -> None:
        _require_checked_target()

    def _register(self, email: str) -> str:
        response = self.client.post(
            "/auth/register",
            json={"email": email, "password": "plan-test-pass", "display_name": "plan"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["access_token"]

    def test_requires_login_and_ownership(self) -> None:
        token = self._register("endpoint-a@example.test")
        other = self._register("endpoint-b@example.test")
        auth = {"Authorization": f"Bearer {token}"}
        deck = self.client.post("/decks", json={"name": "endpoint deck"}, headers=auth).json()["id"]
        url = f"/learning-plan/progress?deck_kind=personal&deck_id={deck}"

        self.assertEqual(self.client.get(url).status_code, 401)  # no dev-user fallback
        ok = self.client.get(url, headers=auth)
        self.assertEqual(ok.status_code, 200, ok.text)
        body = ok.json()
        self.assertEqual(
            set(body),
            {"deck_kind", "deck_id", "total", "seen", "progress_scope", "metric_version", "today", "as_of"},
        )
        self.assertEqual((body["deck_kind"], body["deck_id"], body["total"], body["seen"]), ("personal", deck, 0, 0))
        self.assertEqual(self.client.get(url, headers={"Authorization": f"Bearer {other}"}).status_code, 404)
        self.assertEqual(
            self.client.get("/learning-plan/progress?deck_kind=subscribed&deck_id=999999", headers=auth).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(f"/learning-plan/progress?deck_kind=all&deck_id={deck}", headers=auth).status_code,
            422,
        )

    def test_read_only(self) -> None:
        token = self._register("endpoint-c@example.test")
        auth = {"Authorization": f"Bearer {token}"}
        deck = self.client.post("/decks", json={"name": "read only"}, headers=auth).json()["id"]

        def snapshot() -> tuple:
            with get_connection() as connection:
                return tuple(
                    connection.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]
                    for table in ("vocab_items", "review_logs", "lexeme_review_logs", "user_word_progress", "decks")
                )

        before = snapshot()
        for _ in range(3):
            self.client.get(f"/learning-plan/progress?deck_kind=personal&deck_id={deck}", headers=auth)
        self.assertEqual(snapshot(), before)


class FirstReviewQueueTest(unittest.TestCase):
    """GET /study-items/lexemes?first_review_only=true (Gate C-1b)."""

    @classmethod
    def setUpClass(cls) -> None:
        _require_checked_target()
        init_db()
        cls.client = TestClient(main.app)

    def setUp(self) -> None:
        _require_checked_target()
        tag = self.id().rsplit(".", 1)[-1]
        self.owner = _user(f"owner-{tag}@example.test")
        self.user = _user(f"learner-{tag}@example.test")
        self.lex = [upsert_lexeme(f"{tag}-{n}", f"{tag}-{n}", reading=f"q{n}") for n in range(8)]
        self.deck = _shared_deck(self.owner, f"queue {tag}")
        for order, lexeme in enumerate(self.lex):
            add_word_to_shared_deck(self.deck, lexeme, order)
        get_or_create_subscription(self.user, self.deck)

    def ids(self, **kwargs) -> list[int]:
        return [i["lexeme_id"] for i in list_subscribed_lexeme_study_items(self.user, shared_deck_id=self.deck, **kwargs)]

    def test_all_four_unrated_statuses_are_candidates(self) -> None:
        update_word_status(self.user, self.lex[0], "known")
        update_word_status(self.user, self.lex[1], "uncertain")
        update_word_status(self.user, self.lex[2], "unknown")
        # lex[3]: no progress row at all (unclassified)
        self.assertEqual(self.ids(first_review_only=True, limit=4), self.lex[:4])

    def test_first_again_rating_is_not_a_candidate(self) -> None:
        record_lexeme_review(self.user, self.lex[0], "again", shared_deck_id=self.deck)
        with get_connection() as connection:
            level = connection.execute(
                "SELECT review_level FROM user_word_progress WHERE user_id = ? AND lexeme_id = ?",
                (self.user, self.lex[0]),
            ).fetchone()["review_level"]
        self.assertEqual(level, 0)  # review_level alone would wrongly call it new
        self.assertNotIn(self.lex[0], self.ids(first_review_only=True))

    def test_limit_fills_after_front_words_are_rated(self) -> None:
        for lexeme in self.lex[:3]:
            record_lexeme_review(self.user, lexeme, "good", shared_deck_id=self.deck)
        self.assertEqual(self.ids(first_review_only=True, limit=3), self.lex[3:6])
        # Stable: same call twice, same order.
        self.assertEqual(self.ids(first_review_only=True, limit=3), self.ids(first_review_only=True, limit=3))

    def test_queue_matches_plan_remaining(self) -> None:
        update_word_status(self.user, self.lex[4], "known")
        record_lexeme_review(self.user, self.lex[5], "again", shared_deck_id=self.deck)
        record_lexeme_review(self.user, self.lex[6], "easy", shared_deck_id=self.deck)
        progress = get_plan_progress(self.user, "subscribed", self.deck)
        self.assertEqual(len(self.ids(first_review_only=True)), progress["total"] - progress["seen"])

    def test_existing_calls_unchanged(self) -> None:
        update_word_status(self.user, self.lex[0], "known")
        record_lexeme_review(self.user, self.lex[1], "good", shared_deck_id=self.deck)
        # Default path: known excluded, rated words still listed, limit before nothing else.
        self.assertEqual(self.ids(), self.lex[1:])
        self.assertEqual(self.ids(limit=2), self.lex[1:3])
        self.assertEqual(self.ids(due_only=True), [])  # lex[1] is scheduled in the future

    def test_route(self) -> None:
        token = self.client.post(
            "/auth/register",
            json={"email": f"route-{self.id()}@example.test", "password": "plan-test-pass", "display_name": "r"},
        ).json()["access_token"]
        auth = {"Authorization": f"Bearer {token}"}
        self.client.post(f"/shared-decks/{self.deck}/import", headers=auth)
        known = self.lex[0]
        self.client.patch(f"/shared-decks/{self.deck}/words/{known}/progress", json={"status": "known"}, headers=auth)
        self.client.post(f"/shared-decks/{self.deck}/words/{self.lex[1]}/review", json={"rating": "again"}, headers=auth)
        base = f"/study-items/lexemes?shared_deck_id={self.deck}"
        first = self.client.get(f"{base}&first_review_only=true&limit=3", headers=auth).json()
        self.assertEqual([i["lexeme_id"] for i in first], [known, self.lex[2], self.lex[3]])
        self.assertTrue(all(i["last_reviewed_at"] is None for i in first))
        default = self.client.get(base, headers=auth).json()
        self.assertNotIn(known, [i["lexeme_id"] for i in default])  # route known filter kept
        self.assertIn(self.lex[1], [i["lexeme_id"] for i in default])
        self.assertIsNotNone(next(i for i in default if i["lexeme_id"] == self.lex[1])["last_reviewed_at"])
        bad = self.client.get(f"{base}&first_review_only=true&due_only=true", headers=auth)
        self.assertEqual(bad.status_code, 400)


if __name__ == "__main__":
    unittest.main()

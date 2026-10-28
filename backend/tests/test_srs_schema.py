"""Tests for the additive SRS storage (app/srs/schema.py) and legacy safety.

SQLite: a throwaway file per test (never backend/vocab.db, never whatever
DATABASE_URL is already set). Checks a fresh database, an upgrade of a
database built and filled *without* the SRS schema, re-runs, constraints, and
that the legacy review paths still behave exactly as before.

PostgreSQL (opt-in): set SRS_SCHEMA_TEST_POSTGRES_URL to a freshly created,
empty database on localhost named jp_vocab_test[_...] and run this file
directly. tests/_local_postgres_guard.py validates the target and confirms it
is empty before anything is created; DATABASE_URL is re-checked right before
every write. Without the variable those tests are skipped (= unverified).

Run directly:      python tests/test_srs_schema.py
Or via discovery:   python -m unittest discover -s tests
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

from app import database  # noqa: E402
from app.database import compute_review_schedule, get_connection, init_db  # noqa: E402
from app.repositories.deck_repository import create_deck  # noqa: E402
from app.repositories.lexeme_repository import (  # noqa: E402
    add_word_to_shared_deck,
    get_or_create_subscription,
    record_lexeme_review,
    update_word_status,
    upsert_lexeme,
)
from app.repositories.user_repository import create_user  # noqa: E402
from app.repositories.vocab_repository import create_or_update_vocab_item, record_review  # noqa: E402
from app.schemas import DeckCreate, VocabItemCreate  # noqa: E402
from app.srs import schema as srs_schema  # noqa: E402

PRESERVED_TABLES = (
    "users", "decks", "vocab_items", "lexemes", "shared_decks", "shared_deck_words",
    "user_deck_subscriptions", "user_word_progress", "review_logs", "lexeme_review_logs",
)
NEW_TABLES = ("srs_config_versions", "srs_user_settings", "srs_review_receipts", "srs_migration_runs", "srs_migration_snapshots")


def _columns(connection, table):
    return [row["name"] for row in connection.execute(f"PRAGMA table_info({table})").fetchall()]


def _tables(connection):
    return {row["name"] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()}


def _snapshot(columns_by_table):
    """Every row of every preserved table, restricted to the pre-upgrade columns."""
    with get_connection() as connection:
        return {
            table: [tuple(row) for row in connection.execute(
                f"SELECT {', '.join(columns)} FROM {table} ORDER BY id"
            ).fetchall()]
            for table, columns in columns_by_table.items()
        }


def _seed_legacy_data():
    """Personal + subscribed cards, reviews, a known card, using the real
    repositories (the same code paths the app uses)."""
    stamp = datetime.now(timezone.utc).isoformat()
    user = int(create_user(email="srs-schema@example.test", display_name="u", password_hash="x")["id"])
    owner = int(create_user(email="srs-owner@example.test", display_name="o", password_hash="x")["id"])
    deck = create_deck(user, DeckCreate(name="schema deck"))[0]["id"]
    personal = []
    for base, status in [("あ", "unknown"), ("い", "uncertain"), ("う", "known")]:
        item, _ = create_or_update_vocab_item(
            user, VocabItemCreate(surface=base, base_form=base, reading=base, status=status, deck_id=deck)
        )
        personal.append(int(item["id"]))
    record_review(user, personal[0], "good")
    record_review(user, personal[0], "again")
    record_review(user, personal[2], "easy")
    with get_connection() as connection:
        shared = int(connection.execute(
            "INSERT INTO shared_decks (owner_user_id, title, description, created_at, updated_at) VALUES (?, ?, '', ?, ?)",
            (owner, "schema shared", stamp, stamp),
        ).lastrowid)
    lexemes = [upsert_lexeme(f"lx{i}", f"lx{i}") for i in range(3)]
    for order, lexeme in enumerate(lexemes):
        add_word_to_shared_deck(shared, lexeme, order)
    get_or_create_subscription(user, shared)
    record_lexeme_review(user, lexemes[0], "easy", shared)  # unclassified -> known (legacy rule)
    record_lexeme_review(user, lexemes[1], "again", shared)
    update_word_status(user, lexemes[2], "known")
    return {"user": user, "deck": deck, "personal": personal, "shared": shared, "lexemes": lexemes}


class _SqliteCase(unittest.TestCase):
    def setUp(self):
        handle, path = tempfile.mkstemp(prefix="jp_vocab_srs_schema_", suffix=".db")
        os.close(handle)
        Path(path).unlink()
        self.db_path = Path(path)
        env = mock.patch.dict(os.environ, {"DATABASE_URL": f"sqlite:///{self.db_path.as_posix()}", "APP_ENV": "development"})
        env.start()
        self.addCleanup(env.stop)
        self.addCleanup(lambda: self.db_path.unlink(missing_ok=True))


class FreshSqliteSchemaTest(_SqliteCase):
    def test_fresh_database_has_columns_tables_and_defaults(self):
        init_db()
        init_db()  # idempotent re-run
        with get_connection() as connection:
            for table in srs_schema.CARD_TABLES:
                self.assertTrue({"srs_engine", "srs_state", "srs_card_version", "srs_participation", "first_completed_at"} <= set(_columns(connection, table)))
            for table in srs_schema.LOG_TABLES:
                self.assertTrue({"request_id", "srs_before_json", "seoul_date"} <= set(_columns(connection, table)))
            tables = _tables(connection)
            self.assertTrue(set(NEW_TABLES) <= tables)
            self.assertNotIn("srs_intake_reservations", tables)
            for table in NEW_TABLES:
                self.assertEqual(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 0, table)

    def test_constraints(self):
        init_db()
        ids = _seed_legacy_data()
        stamp = datetime.now(timezone.utc).isoformat()
        import sqlite3

        bad_updates = [
            "UPDATE vocab_items SET srs_engine = 'bogus'",
            "UPDATE vocab_items SET srs_state = 4",
            "UPDATE vocab_items SET srs_step = -1",
            "UPDATE user_word_progress SET srs_participation = 'gone'",
            "UPDATE user_word_progress SET srs_history_quality = 'maybe'",
        ]
        for statement in bad_updates:
            with self.subTest(statement=statement), self.assertRaises(sqlite3.IntegrityError):
                with get_connection() as connection:
                    connection.execute(statement)
        with self.assertRaises(sqlite3.IntegrityError):
            with get_connection() as connection:
                connection.execute(
                    "INSERT INTO srs_user_settings (user_id, daily_new_goal, created_at, updated_at) VALUES (?, 501, ?, ?)",
                    (ids["user"], stamp, stamp),
                )
        with get_connection() as connection:
            connection.execute(
                "INSERT INTO srs_user_settings (user_id, created_at, updated_at) VALUES (?, ?, ?)", (ids["user"], stamp, stamp)
            )
            row = connection.execute("SELECT srs_mode, daily_new_goal FROM srs_user_settings").fetchone()
            self.assertEqual((row["srs_mode"], row["daily_new_goal"]), ("legacy", 20))
            receipt = (ids["user"], "req-1", "personal", ids["personal"][0], "h", "{}", stamp)
            sql = ("INSERT INTO srs_review_receipts (user_id, request_id, card_kind, card_ref, request_hash, response_json, created_at) "
                   "VALUES (?, ?, ?, ?, ?, ?, ?)")
            connection.execute(sql, receipt)
        with self.assertRaises(sqlite3.IntegrityError):
            with get_connection() as connection:
                connection.execute(sql, receipt)


class UpgradeSqliteSchemaTest(_SqliteCase):
    def test_upgrade_preserves_every_existing_value(self):
        # 1. Build and fill a database exactly as the app did before this gate.
        # Pre-SRS code neither had the SRS schema nor initialized new cards (Gate C-2a).
        with mock.patch.object(database, "ensure_srs_schema"),                 mock.patch("app.srs.storage.initialize_new_personal_cards", return_value=0):
            init_db()
            ids = _seed_legacy_data()
        with get_connection() as connection:
            before_columns = {table: _columns(connection, table) for table in PRESERVED_TABLES}
            self.assertNotIn("srs_engine", before_columns["vocab_items"])
        before = _snapshot(before_columns)

        # 2. Upgrade twice (startup runs init_db every time).
        init_db()
        init_db()

        self.assertEqual(_snapshot(before_columns), before)
        with get_connection() as connection:
            for table in srs_schema.CARD_TABLES:
                rows = connection.execute(
                    f"SELECT srs_engine, srs_state, srs_card_version, srs_participation, srs_history_quality, first_completed_at FROM {table}"
                ).fetchall()
                self.assertTrue(rows)
                for row in rows:
                    self.assertEqual(tuple(row), ("legacy", None, 0, None, None, None), table)
            for table in srs_schema.LOG_TABLES:
                rows = connection.execute(f"SELECT request_id, srs_engine, srs_after_json, seoul_date FROM {table}").fetchall()
                self.assertTrue(rows)
                self.assertTrue(all(tuple(row) == (None, None, None, None) for row in rows), table)
            # known stays known and is not paused by the schema.
            known = connection.execute(
                "SELECT status, srs_participation FROM user_word_progress WHERE user_id = ? AND lexeme_id = ?",
                (ids["user"], ids["lexemes"][2]),
            ).fetchone()
            self.assertEqual(tuple(known), ("known", None))
            for table in NEW_TABLES:
                self.assertEqual(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 0, table)

    def test_legacy_reviews_unchanged_after_upgrade(self):
        init_db()
        ids = _seed_legacy_data()
        user = ids["user"]
        item = ids["personal"][1]
        with get_connection() as connection:
            level = connection.execute("SELECT review_level FROM vocab_items WHERE id = ?", (item,)).fetchone()[0]
        updated = record_review(user, item, "good")
        reviewed_at = datetime.fromisoformat(updated["last_reviewed_at"])
        expected_level, expected_next = compute_review_schedule("good", level, reviewed_at)
        self.assertEqual((updated["review_level"], updated["next_review_at"]), (expected_level, expected_next))

        progress = record_lexeme_review(user, ids["lexemes"][1], "good", ids["shared"])
        self.assertEqual(progress["status"], "unknown")  # set by the earlier first Again (legacy auto-status)
        with get_connection() as connection:
            for table, where, ref in [("vocab_items", "id = ?", item), ("user_word_progress", "user_id = ? AND lexeme_id = ?", None)]:
                params = (ref,) if ref is not None else (user, ids["lexemes"][1])
                row = connection.execute(f"SELECT srs_engine, srs_state, srs_card_version FROM {table} WHERE {where}", params).fetchone()
                # B-2 legacy reviews also bump the CAS version so a prepared
                # migration cannot overwrite a new legacy evaluation.
                self.assertEqual(tuple(row), ("legacy", None, 1 if table == "vocab_items" else 2), table)
            logs = connection.execute("SELECT request_id, srs_engine FROM review_logs ORDER BY id DESC LIMIT 1").fetchone()
            self.assertEqual(tuple(logs), (None, None))


_PG_URL = os.environ.get("SRS_SCHEMA_TEST_POSTGRES_URL", "").strip()


@unittest.skipUnless(_PG_URL, "SRS_SCHEMA_TEST_POSTGRES_URL not set: PostgreSQL schema unverified")
class PostgresSchemaTest(unittest.TestCase):
    def test_fresh_and_rerun_on_empty_local_test_database(self):
        from _local_postgres_guard import assert_empty_postgres_test_database, validate_local_postgres_test_url

        checked = validate_local_postgres_test_url(_PG_URL)
        assert_empty_postgres_test_database(checked)
        with mock.patch.dict(os.environ, {"DATABASE_URL": checked, "APP_ENV": "development"}):
            for _ in range(2):
                if os.environ.get("DATABASE_URL") != checked:
                    self.fail("DATABASE_URL changed before write; stopped")
                init_db()
            with get_connection() as connection:
                for table in srs_schema.CARD_TABLES + srs_schema.LOG_TABLES:
                    names = {
                        row["column_name"]
                        for row in connection.execute(
                            "SELECT column_name FROM information_schema.columns WHERE table_name = ?", (table,)
                        ).fetchall()
                    }
                    expected = "srs_engine" if table in srs_schema.CARD_TABLES else "request_id"
                    self.assertIn(expected, names, table)
                for table in NEW_TABLES:
                    self.assertEqual(connection.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"], 0)


if __name__ == "__main__":
    unittest.main()

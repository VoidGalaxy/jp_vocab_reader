"""Gate E-2b P-UP2: upgrading a PostgreSQL database that predates the SRS columns.

A pre-SRS schema (what the app built before the SRS work: no SRS columns or tables, and
the old CASCADE card FK on review_logs) is filled with synthetic rows, then the current
app schema step upgrades it in the managed transaction:
- an injected failure midway (after the card / log columns and the SRS tables were added)
  rolls the WHOLE upgrade back: same catalog, same rows, no SRS table left;
- the real upgrade keeps every existing value, gives existing rows exactly the declared
  defaults (srs_engine 'legacy', srs_card_version 0, everything else NULL), drops only the
  old card FK, and creates exactly the SRS tables;
- a second run changes nothing (catalog fingerprint and every row identical);
- the same logical rows upgraded on SQLite give the same values row by row.

Test code only. Real PostgreSQL only with the harness opt-in; otherwise reported as skipped.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import _srs_pg_harness as harness  # noqa: E402
from test_srs_e3_fk_real import OLD_REVIEW_LOGS  # noqa: E402

import app.database as database  # noqa: E402
from app.srs import schema as srs_schema  # noqa: E402

SRS_TABLES = {name for statement in srs_schema._new_tables(True)
              for name in __import__("re").findall(r"CREATE TABLE IF NOT EXISTS (\w+)\s*\(", statement)}
CARD_TABLES = srs_schema.CARD_TABLES
LOG_TABLES = srs_schema.LOG_TABLES
DATA_TABLES = ("users", "decks", "vocab_items", "review_logs", "lexemes", "shared_decks",
               "shared_deck_words", "user_deck_subscriptions", "user_word_progress", "lexeme_review_logs")
T0 = "2026-10-01T00:00:00+00:00"
T1 = "2026-10-02T09:30:00+00:00"
T2 = "2026-10-05T09:30:00+00:00"


def _opt_in() -> bool:
    return harness.requested(os.environ) is not None


class InjectedUpgradeFailure(RuntimeError):
    pass


def pre_srs_schema(connection) -> None:
    """The app before the SRS work: no SRS columns / tables, CASCADE card FK on review_logs."""
    real = connection.execute

    def execute(query, params=()):
        if "CREATE TABLE IF NOT EXISTS review_logs" in query:
            query = OLD_REVIEW_LOGS
        return real(query, params)

    if database.is_postgres_connection(connection):
        connection.execute = execute
    with mock.patch.object(database, "drop_personal_log_card_fk", lambda c: "pre-change app"), \
            mock.patch.object(database, "ensure_srs_schema", lambda c, is_postgres: None):
        database.ensure_schema(connection)


def fill(connection) -> None:
    """The same synthetic logical rows on both databases. Ids come from the databases
    (fresh, empty, so the same order); natural keys are compared as well."""
    ex = connection.execute

    def one(sql, params):
        return ex(sql + " RETURNING id", params).fetchone()["id"]

    a = one("INSERT INTO users (email, display_name, password_hash, auth_provider, created_at, updated_at) "
            "VALUES (?, ?, ?, 'local', ?, ?)", ("up2-a@example.test", "up2 a", "not-a-login-hash", T0, T0))
    b = one("INSERT INTO users (email, display_name, password_hash, auth_provider, created_at, updated_at) "
            "VALUES (?, ?, ?, 'local', ?, ?)", ("up2-b@example.test", "up2 b", "not-a-login-hash", T0, T0))
    # The old app gave every account its default deck too (ensure_default_decks_for_users
    # predates the SRS work); without it the upgrade's regular start step would add them.
    database.ensure_default_decks_for_users(connection)
    deck = one("INSERT INTO decks (user_id, name, description, created_at, updated_at) VALUES (?, ?, '', ?, ?)",
               (a, "up2 deck", T0, T0))
    items = []
    for n, (status, level, nxt, ok, bad, last) in enumerate([
            ("learning", 2, T2, 3, 1, T1), ("new", 0, None, 0, 0, None), ("mastered", 6, T2, 9, 0, T1)]):
        items.append(one(
            "INSERT INTO vocab_items (user_id, deck_id, surface, base_form, reading, part_of_speech, "
            "normalized_form, meaning_ko, status, correct_count, wrong_count, last_reviewed_at, review_level, "
            "next_review_at, created_at, updated_at) VALUES (?, ?, ?, ?, ?, '名詞', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (a, deck, f"up2-{n}", f"up2-{n}", f"up2-r{n}", f"up2-{n}", f"meaning {n}", status, ok, bad, last,
             level, nxt, T0, T1)))
    for rating, before, after in (("good", 1, 2), ("again", 2, 1)):
        ex("INSERT INTO review_logs (user_id, vocab_item_id, deck_id, rating, reviewed_at, previous_review_level, "
           "next_review_level, previous_next_review_at, next_review_at, response_time_ms) "
           "VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?, 1200)", (a, items[0], deck, rating, T1, before, after, T2))
    lex = [one("INSERT INTO lexemes (surface, base_form, reading, part_of_speech, meaning_ko, source_type, "
               "created_at, updated_at) VALUES (?, ?, ?, '名詞', ?, 'shared_deck', ?, ?)",
               (f"up2-lx{n}", f"up2-lx{n}", f"up2-lr{n}", f"lexeme {n}", T0, T0)) for n in range(2)]
    shared = one("INSERT INTO shared_decks (owner_user_id, title, description, created_at, updated_at) "
                 "VALUES (?, 'up2 shared', '', ?, ?)", (b, T0, T0))
    for n, lexeme in enumerate(lex):
        ex("INSERT INTO shared_deck_words (shared_deck_id, lexeme_id, sort_order, created_at) VALUES (?, ?, ?, ?)",
           (shared, lexeme, n, T0))
    ex("INSERT INTO user_deck_subscriptions (user_id, shared_deck_id, imported_at, created_at, updated_at) "
       "VALUES (?, ?, ?, ?, ?)", (a, shared, T0, T0, T0))
    ex("INSERT INTO user_word_progress (user_id, lexeme_id, status, review_level, next_review_at, correct_count, "
       "wrong_count, last_reviewed_at, created_at, updated_at) VALUES (?, ?, 'learning', 1, ?, 1, 0, ?, ?, ?)",
       (a, lex[0], T2, T1, T0, T1))
    ex("INSERT INTO lexeme_review_logs (user_id, lexeme_id, shared_deck_id, rating, previous_review_level, "
       "new_review_level, previous_next_review_at, new_next_review_at, previous_status, new_status, created_at) "
       "VALUES (?, ?, ?, 'good', 0, 1, NULL, ?, 'unclassified', 'learning', ?)", (a, lex[0], shared, T2, T1))


def rows(connection) -> dict:
    out = {}
    for table in DATA_TABLES:
        out[table] = [dict(r) for r in connection.execute(f"SELECT * FROM {table} ORDER BY id").fetchall()]
    return out


def srs_added_columns() -> dict:
    added = {t: [srs_schema._COLUMN_DEFINITION.match(d) for d in srs_schema.card_columns(True)] for t in CARD_TABLES}
    added.update({t: [srs_schema._COLUMN_DEFINITION.match(d) for d in srs_schema.LOG_COLUMNS] for t in LOG_TABLES})
    return {t: [m.group(1) for m in ms] for t, ms in added.items()}


def expected_defaults() -> dict:
    """Per table and added column, the value an existing row must get: the DEFAULT in the
    column's own declaration ('legacy' / 0 on the card tables), otherwise NULL."""
    import re

    out = {}
    for table in CARD_TABLES + LOG_TABLES:
        definitions = srs_schema.card_columns(True) if table in CARD_TABLES else srs_schema.LOG_COLUMNS
        out[table] = {}
        for definition in definitions:
            name = definition.split()[0]
            m = re.search(r"\bDEFAULT\s+('([^']*)'|(-?\d+))", definition)
            out[table][name] = None if m is None else (m.group(2) if m.group(2) is not None else int(m.group(3)))
    return out


EXPECTED_DEFAULT = expected_defaults()


@unittest.skipUnless(_opt_in(), "Real PostgreSQL E-2b P-UP2 checks NOT RUN (opt-in not set)")
class PreSrsUpgradeTests(unittest.TestCase):
    """One test: the steps depend on each other (fail -> upgrade -> rerun -> compare)."""

    def setUp(self):
        import _srs_e2_adapter as adapter

        self.adapter = adapter
        # One frozen app clock for both databases: the start steps (dev account, default
        # decks) stamp now_utc(); the SQLite / PostgreSQL rows must carry the same instants.
        from datetime import datetime, timezone

        clock = mock.patch.object(database, "now_utc", return_value=datetime(2026, 10, 3, 0, 0, tzinfo=timezone.utc))
        clock.start()
        self.addCleanup(clock.stop)
        # SQLite first, outside the PostgreSQL scope: same rows, same upgrade code.
        directory = tempfile.TemporaryDirectory(prefix="jp_vocab_e2b_", dir=Path(__file__).resolve().parents[1])
        self.addCleanup(directory.cleanup)
        sqlite_url = f"sqlite:///{(Path(directory.name) / 'up2.db').as_posix()}"
        with mock.patch.dict(os.environ, {"DATABASE_URL": sqlite_url, "APP_ENV": "test"}):
            with database.get_connection() as connection:
                pre_srs_schema(connection)
                fill(connection)
            with database.get_connection() as connection:
                self.sqlite_before = rows(connection)
            database.init_db()
            with database.get_connection() as connection:
                self.sqlite_after = rows(connection)

        self.run = harness.PgRun(harness.requested(os.environ))
        self.run.start()
        self.addCleanup(self.run.teardown)
        self.old_tables = adapter.expected_schema_tables() - SRS_TABLES
        self.run.track_creation(adapter.schema_step(pre_srs_schema), expected=self.old_tables)
        scope = adapter.app_scope(self.run)
        scope.__enter__()
        self.addCleanup(scope.__exit__, None, None, None)
        with database.get_connection() as connection:
            fill(connection)

    # ---- catalog -------------------------------------------------------------
    def catalog(self) -> dict:
        with database.get_connection() as connection:
            q = connection.execute
            tables = sorted(r["relname"] for r in q(
                "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = 'public' AND c.relkind = 'r'").fetchall())
            columns = [tuple(r.values()) for r in q(
                "SELECT table_name, column_name, data_type, is_nullable, column_default, ordinal_position "
                "FROM information_schema.columns WHERE table_schema = 'public' "
                "ORDER BY table_name, ordinal_position").fetchall()]
            indexes = sorted(tuple(r.values()) for r in q(
                "SELECT tablename, indexname, indexdef FROM pg_indexes WHERE schemaname = 'public'").fetchall())
            constraints = sorted(tuple(r.values()) for r in q(
                "SELECT t.relname, c.conname, pg_get_constraintdef(c.oid) FROM pg_constraint c "
                "JOIN pg_class t ON t.oid = c.conrelid JOIN pg_namespace n ON n.oid = t.relnamespace "
                "WHERE n.nspname = 'public'").fetchall())
            oids = sorted(r["oid"] for r in q(
                "SELECT c.oid::bigint AS oid FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = 'public'").fetchall())
        return {"tables": tables, "columns": columns, "indexes": indexes, "constraints": constraints, "oids": oids}

    def data(self) -> dict:
        with database.get_connection() as connection:
            out = rows(connection)
        return out

    def card_fk_on_review_logs(self, catalog) -> list:
        return [c for c in catalog["constraints"] if c[0] == "review_logs" and "vocab_items" in c[2]]

    # ---- the check -----------------------------------------------------------
    def test_pre_srs_upgrade_preserves_defaults_reruns_and_rolls_back_whole(self):
        added = srs_added_columns()
        before_catalog = self.catalog()
        before = self.data()
        self.assertTrue(all(before[t] for t in DATA_TABLES), "every table has synthetic rows")
        self.assertFalse(set(before_catalog["tables"]) & SRS_TABLES)
        for table, names in added.items():
            self.assertFalse(set(names) & set(before[table][0]), f"{table} already has SRS columns")
        self.assertEqual(len(self.card_fk_on_review_logs(before_catalog)), 1, "old card FK present")

        # 1. failure midway: columns + tables already added when the third SRS index fails.
        real_index = srs_schema.ensure_pg_index
        calls = {"n": 0}

        def failing_index(connection, statement):
            calls["n"] += 1
            if calls["n"] == 3:
                raise InjectedUpgradeFailure("injected at the third SRS index")
            return real_index(connection, statement)

        with mock.patch.object(srs_schema, "ensure_pg_index", failing_index):
            with self.assertRaises(InjectedUpgradeFailure):
                self.run.track_creation(self.adapter.schema_step(), expected=SRS_TABLES)
        self.assertEqual(calls["n"], 3, "the failure happened midway, after earlier SRS DDL")
        self.assertFalse(self.run.stopped)
        self.assertEqual(self.catalog(), before_catalog, "the whole upgrade rolled back")
        self.assertEqual(self.data(), before)

        # 2. the real upgrade.
        self.run.track_creation(self.adapter.schema_step(), expected=SRS_TABLES)
        upgraded_catalog = self.catalog()
        after = self.data()
        self.assertEqual(self.card_fk_on_review_logs(upgraded_catalog), [], "old card FK dropped (E-D1 A)")
        self.assertTrue(SRS_TABLES <= set(upgraded_catalog["tables"]))
        for table in DATA_TABLES:
            self.assertEqual(len(after[table]), len(before[table]), table)
            for old, new in zip(before[table], after[table]):
                self.assertEqual({k: new[k] for k in old}, old, f"{table} existing values kept")
                extra = set(new) - set(old)
                self.assertEqual(extra, set(added.get(table, [])), f"{table} added columns")
                for column in extra:
                    self.assertEqual(new[column], EXPECTED_DEFAULT[table][column], f"{table}.{column} default")
        with database.get_connection() as connection:
            for table in SRS_TABLES:
                self.assertEqual(connection.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"], 0, table)

        # 3. rerun: nothing changes.
        self.run.track_creation(self.adapter.schema_step(), expected=set())
        self.assertEqual(self.catalog(), upgraded_catalog)
        self.assertEqual(self.data(), after)

        # 4. SQLite: the same logical rows before and after, value by value.
        self.assertEqual(self.sqlite_before, _comparable(before, self.sqlite_before))
        self.assertEqual(self.sqlite_after, _comparable(after, self.sqlite_after))


def _comparable(pg: dict, sqlite: dict) -> dict:
    """PostgreSQL rows in the SQLite shape, with exactly one declared difference: the
    subscription flag is BOOLEAN on PostgreSQL and 0/1 INTEGER on SQLite. Columns that only
    one database has are NOT dropped -- a column set difference fails the comparison."""
    out = {}
    for table, table_rows in pg.items():
        converted = []
        for row in table_rows:
            row = dict(row)
            if table == "user_deck_subscriptions" and isinstance(row.get("is_active"), bool):
                row["is_active"] = int(row["is_active"])
            converted.append(row)
        out[table] = converted
    return out


if __name__ == "__main__":
    unittest.main()

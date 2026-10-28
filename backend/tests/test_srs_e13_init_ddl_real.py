"""Gate E-3 follow-up E-D13 A (approved 2026-10-19; contract INIT_LOCK_PROPOSAL.md 6): the
PostgreSQL init path runs an additive column / index DDL only when the catalog shows it is
really missing. Checked on the REAL protected local test database only (E-1 harness, E-2
adapter, limited role). Skipped -- NOT RUN -- without the harness opt-in.

Latest schema (E-3 FK removal done): repeated init_db runs no column / index DDL; several
workers start at once and all finish. (No-deadlock with reviews and the lock footprint are
in test_srs_e3_init_race_real.)
Upgrade (real changes): an empty database gets everything; missing columns / indexes are
added -- only those -- and verified; a rerun changes nothing; a failure midway rolls the
whole schema transaction back; a same-name index on another table, an index with other
columns or uniqueness, an invalid index, a column of another type or NOT NULL flag stop
the start with SchemaUpgradeError and change nothing (no DROP / re-create / REINDEX).
A schema-CHANGING concurrent start is recorded only; it is not claimed to be as safe as an
up-to-date start.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from test_srs_e3_fk_real import WAIT, RealCase, _opt_in  # noqa: E402

DDL_PREFIXES = ("ALTER TABLE", "CREATE INDEX", "CREATE UNIQUE INDEX", "DROP", "REINDEX")


class DdlRecorder:
    """Install once around all workers; keep thread / connection records separately."""

    _installation_lock = threading.Lock()

    def __enter__(self):
        import app.database as database

        if not self._installation_lock.acquire(blocking=False):
            raise RuntimeError("DDL recorder already active")
        self._entries = []
        self._record_lock = threading.Lock()
        real = database.AppPostgresConnection.execute
        recorder = self

        def execute(connection, query, params=()):
            with recorder._record_lock:
                recorder._entries.append((threading.current_thread(), connection, " ".join(query.split())))
            return real(connection, query, params)

        self.patch = mock.patch.object(database.AppPostgresConnection, "execute", execute)
        try:
            self.patch.start()
        except BaseException:
            self._installation_lock.release()
            raise
        return self

    def __exit__(self, *exc):
        try:
            self.patch.stop()
        finally:
            self._installation_lock.release()
        return False

    def statements_for(self, *, thread=None, connection=None):
        with self._record_lock:
            return [query for owner, source, query in self._entries
                    if (thread is None or owner is thread) and (connection is None or source is connection)]

    def ddl_for(self, *, thread=None, connection=None):
        return [query for query in self.statements_for(thread=thread, connection=connection)
                if query.upper().startswith(DDL_PREFIXES)]

    @property
    def statements(self):
        return self.statements_for()

    @property
    def ddl(self):
        return self.ddl_for()


class E13Case(RealCase):
    def init_db(self):
        import app.database as database

        with DdlRecorder() as recorder:
            database.init_db()
        return recorder.ddl

    def managed_upgrade(self):
        with DdlRecorder() as recorder:
            self.upgrade()
        return recorder.ddl

    def columns(self, table):
        return {r["name"]: (r["type"], r["not_null"]) for r in self.sql(
            "SELECT a.attname::text AS name, format_type(a.atttypid, a.atttypmod) AS type, a.attnotnull AS not_null "
            "FROM pg_attribute a WHERE a.attrelid = to_regclass(?) AND a.attnum > 0 AND NOT a.attisdropped", (table,))}

    def index(self, name):
        rows = self.sql("SELECT i.oid::bigint AS oid, pg_get_indexdef(i.oid) AS def, ix.indisvalid AS valid "
                        "FROM pg_class i JOIN pg_index ix ON ix.indexrelid = i.oid WHERE i.relname = ?", (name,))
        return rows[0] if rows else None

    def everything_ok(self):
        """Independent of the app's helpers (a mutation of those must not hide a gap): every
        expected column is present with its type / NOT NULL in the catalog, and every expected
        index exists on its table, valid, with the expected definition text."""
        import inspect
        import re

        import app.database as database
        from app.srs import schema

        statements = re.findall(r'"""(\s*CREATE INDEX IF NOT EXISTS.*?)"""', inspect.getsource(database.create_postgres_tables),
                                re.S) + list(schema.INDEXES)
        groups = [("shared_deck_words", ["display_meaning_ko TEXT", "example_sentence TEXT", "context_explanation_ko TEXT",
                                         "tags_json TEXT", "published_note TEXT"])]
        groups += [(t, schema.card_columns(True)) for t in schema.CARD_TABLES]
        groups += [(t, schema.LOG_COLUMNS) for t in schema.LOG_TABLES]
        groups += [("srs_card_deletions", schema.DELETION_EVIDENCE_COLUMNS)]
        types = {"TEXT": "text", "INTEGER": "integer", "DOUBLE PRECISION": "double precision"}
        for table, definitions in groups:
            present = self.columns(table)
            for definition in definitions:
                name, rest = definition.split(maxsplit=1)
                pg_type = next(v for k, v in types.items() if rest.upper().startswith(k))
                self.assertEqual(present.get(name), (pg_type, " NOT NULL" in f" {definition.upper()}"), f"{table}.{name}")
        for statement in statements:
            m = re.match(r"\s*CREATE INDEX IF NOT EXISTS (\w+)\s+ON\s+(\w+)\s*\(([^)]*)\)", statement)
            name, table, cols = m.group(1), m.group(2), ", ".join(c.strip() for c in m.group(3).split(","))
            found = self.index(name)
            self.assertIsNotNone(found, name)
            self.assertTrue(found["valid"], name)
            self.assertTrue(found["def"].endswith(f"ON public.{table} USING btree ({cols})"), (name, found["def"]))
        return len(statements), sum(len(d) for _, d in groups)

    def schema_fingerprint(self):
        rel = self.sql("SELECT c.relname::text AS n, c.oid::bigint AS oid, c.relkind::text AS k FROM pg_class c "
                       "JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = current_schema() ORDER BY 1")
        cols = self.sql("SELECT c.relname::text AS t, a.attname::text AS c, format_type(a.atttypid, a.atttypmod) AS ty, "
                        "a.attnotnull AS nn FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid JOIN pg_namespace n "
                        "ON n.oid = c.relnamespace WHERE n.nspname = current_schema() AND c.relkind = 'r' AND a.attnum > 0 "
                        "AND NOT a.attisdropped ORDER BY 1, 2")
        return rel, cols


@unittest.skipUnless(_opt_in(), "Real PostgreSQL E-D13 checks NOT RUN (opt-in not set)")
class LatestSchemaTests(E13Case):
    def test_repeated_init_db_runs_no_column_or_index_ddl(self):
        self.create()
        self.assertEqual(self.card_fks(), [])  # E-3 FK removal done: the real latest state
        before = self.schema_fingerprint()
        for _ in range(3):
            self.assertEqual(self.init_db(), [])
        self.assertEqual(self.managed_upgrade(), [])
        self.assertEqual(self.schema_fingerprint(), before)
        indexes, columns = self.everything_ok()
        self.assertEqual(indexes, 21)  # 15 in create_postgres_tables + 6 SRS, all checked against the catalog

    def test_concurrent_worker_starts(self):
        import app.database as database

        self.create()
        n, barrier, results = 4, threading.Barrier(4, timeout=WAIT), {}
        result_lock = threading.Lock()
        original = database.AppPostgresConnection.execute

        def worker(i):
            try:
                barrier.wait()
                database.init_db()
                result = "ok"
            except BaseException as error:  # noqa: BLE001
                result = f"{type(error).__module__}.{type(error).__name__}"
            with result_lock:
                results[i] = result

        threads = [threading.Thread(target=worker, args=(i,), daemon=True) for i in range(n)]
        with DdlRecorder() as recorder:
            try:
                for t in threads:
                    t.start()
            finally:
                for t in threads:
                    t.join(WAIT * 2)
            self.assertTrue(all(not t.is_alive() for t in threads))
        self.assertIs(database.AppPostgresConnection.execute, original)
        self.assertEqual(results, {i: "ok" for i in range(n)})
        self.assertEqual(recorder.ddl, [])
        for thread in threads:
            self.assertTrue(recorder.statements_for(thread=thread))
            self.assertEqual(recorder.ddl_for(thread=thread), [])


@unittest.skipUnless(_opt_in(), "Real PostgreSQL E-D13 upgrade checks NOT RUN (opt-in not set)")
class UpgradeTests(E13Case):
    MISSING_DDL = ["ALTER TABLE shared_deck_words DROP COLUMN published_note",
                   "ALTER TABLE vocab_items DROP COLUMN history_intro_known_by",   # user_word_progress keeps its own
                   "ALTER TABLE srs_card_deletions DROP COLUMN history_intro_known_by",
                   "DROP INDEX idx_vocab_items_srs_queue",
                   "DROP INDEX idx_user_word_progress_user"]

    def test_empty_database_gets_everything(self):
        self.create()  # managed step on the empty, protected database
        self.everything_ok()

    def test_missing_columns_and_indexes_only_are_added(self):
        self.create()
        self.ddl(*self.MISSING_DDL)
        self.assertNotIn("history_intro_known_by", self.columns("vocab_items"))
        self.assertIn("history_intro_known_by", self.columns("user_word_progress"))  # same name, other table
        before = self.index("idx_vocab_items_user_deck")
        ddl = self.managed_upgrade()
        self.assertEqual(sorted(ddl), sorted([
            "ALTER TABLE shared_deck_words ADD COLUMN IF NOT EXISTS published_note TEXT",
            "ALTER TABLE vocab_items ADD COLUMN IF NOT EXISTS history_intro_known_by TEXT",
            "ALTER TABLE srs_card_deletions ADD COLUMN IF NOT EXISTS history_intro_known_by TEXT",
            "CREATE INDEX IF NOT EXISTS idx_vocab_items_srs_queue ON vocab_items(user_id, srs_engine, srs_participation, "
            "srs_effective_due_at)",
            "CREATE INDEX IF NOT EXISTS idx_user_word_progress_user ON user_word_progress(user_id)"]), ddl)
        self.everything_ok()
        self.assertEqual(self.columns("vocab_items")["history_intro_known_by"], ("text", False))
        self.assertEqual(self.index("idx_vocab_items_user_deck"), before)  # untouched index: same object
        fingerprint = self.schema_fingerprint()
        self.assertEqual(self.managed_upgrade(), [])  # rerun: nothing
        self.assertEqual(self.init_db(), [])
        self.assertEqual(self.schema_fingerprint(), fingerprint)

    def test_failure_midway_rolls_back_everything(self):
        from app.srs import schema

        self.create()
        for path in ("managed step", "app init_db"):
            with self.subTest(path=path):
                self.ddl(*self.MISSING_DDL)
                before = self.schema_fingerprint()
                real = schema.ensure_pg_index

                def failing(connection, statement):
                    created = real(connection, statement)
                    if created:  # the first index really created in this transaction
                        raise RuntimeError("synthetic failure after a real DDL")
                    return created

                with mock.patch.object(schema, "ensure_pg_index", failing), \
                        mock.patch("app.database.ensure_pg_index", failing), \
                        self.assertRaisesRegex(RuntimeError, "synthetic failure"):
                    if path == "app init_db":
                        self.init_db()
                    else:
                        self.managed_upgrade()
                self.assertEqual(self.schema_fingerprint(), before)  # columns added earlier rolled back too
                self.managed_upgrade()  # restore for the next round
                self.everything_ok()

    def test_misleading_objects_stop_without_changes(self):
        from app.database import SchemaUpgradeError

        self.create()
        cases = {
            "index name on another table": (["DROP INDEX idx_user_word_progress_user",
                                             "CREATE INDEX idx_user_word_progress_user ON decks(user_id)"],
                                            "index_on_another_table", ["DROP INDEX idx_user_word_progress_user"]),
            "index with other columns": (["DROP INDEX idx_vocab_items_user_deck",
                                          "CREATE INDEX idx_vocab_items_user_deck ON vocab_items(deck_id)"],
                                         "index_definition_mismatch", ["DROP INDEX idx_vocab_items_user_deck"]),
            "index with other uniqueness": (["DROP INDEX idx_user_deck_subscriptions_user",
                                             "CREATE UNIQUE INDEX idx_user_deck_subscriptions_user ON user_deck_subscriptions(user_id)"],
                                            "index_definition_mismatch", ["DROP INDEX idx_user_deck_subscriptions_user"]),
            "column of another type": (["ALTER TABLE vocab_items DROP COLUMN history_intro_known_by",
                                        "ALTER TABLE vocab_items ADD COLUMN history_intro_known_by INTEGER"],
                                       "column_definition_mismatch", ["ALTER TABLE vocab_items DROP COLUMN history_intro_known_by"]),
            "NOT NULL flag differs": (["ALTER TABLE vocab_items ALTER COLUMN srs_card_version DROP NOT NULL"],
                                      "column_definition_mismatch",
                                      ["ALTER TABLE vocab_items ALTER COLUMN srs_card_version SET NOT NULL"]),
        }
        for name, (setup, reason, undo) in cases.items():
            with self.subTest(name):
                self.ddl(*setup)
                before = self.schema_fingerprint()
                for path in ("managed step", "app init_db"):
                    with self.assertRaisesRegex(SchemaUpgradeError, reason):
                        self.init_db() if path == "app init_db" else self.managed_upgrade()
                    self.assertEqual(self.schema_fingerprint(), before, path)  # no DROP / re-create / ALTER TYPE
                self.ddl(*undo)
                self.managed_upgrade()
                self.everything_ok()

    def test_invalid_index_stops_without_changes(self):
        """A real invalid index: a failed CREATE UNIQUE INDEX CONCURRENTLY over duplicates."""
        from app.database import SchemaUpgradeError, get_connection

        self.create()
        with get_connection() as c:
            user = c.execute("INSERT INTO users (email, display_name, password_hash, created_at, updated_at) VALUES "
                             "('inv@e13.test', 'inv', 'x', 't', 't') RETURNING id").fetchone()["id"]
            for title in ("a", "b"):
                c.execute("INSERT INTO shared_decks (owner_user_id, title, description, visibility, created_at, updated_at) "
                          "VALUES (?, ?, '', 'public', '2026-01-01', '2026-01-01')", (user, title))
        self.ddl("DROP INDEX idx_shared_decks_visibility")
        raw = self.run._guarded_connect(self.run._url, autocommit=True)
        try:
            self.run._check_target(raw)
            with self.assertRaises(Exception):
                raw.execute("CREATE UNIQUE INDEX CONCURRENTLY idx_shared_decks_visibility ON shared_decks(visibility, created_at)")
        finally:
            raw.close()
        self.assertFalse(self.index("idx_shared_decks_visibility")["valid"])
        before = self.schema_fingerprint()
        for path in ("managed step", "app init_db"):
            with self.assertRaisesRegex(SchemaUpgradeError, "index_invalid"):
                self.init_db() if path == "app init_db" else self.managed_upgrade()
            self.assertEqual(self.schema_fingerprint(), before, path)
        self.assertFalse(self.index("idx_shared_decks_visibility")["valid"])  # never REINDEXed / replaced

    def test_search_key_definitions_must_match_not_just_column_names(self):
        from app.database import SchemaUpgradeError

        self.create()
        name = "idx_vocab_items_srs_queue"
        variants = {
            "include replaces keys": "(user_id, srs_engine) INCLUDE (srs_participation, srs_effective_due_at)",
            "descending": "(user_id, srs_engine, srs_participation, srs_effective_due_at DESC)",
            "nulls first": "(user_id, srs_engine, srs_participation, srs_effective_due_at NULLS FIRST)",
            "operator class": "(user_id, srs_engine text_pattern_ops, srs_participation, srs_effective_due_at)",
            "collation": '(user_id, srs_engine COLLATE "C", srs_participation, srs_effective_due_at)',
        }
        for label, keys in variants.items():
            self.ddl(f"DROP INDEX {name}", f"CREATE INDEX {name} ON vocab_items{keys}")
            before = (self.schema_fingerprint(), self.index(name), self.checksums())
            for path in ("managed step", "app init_db"):
                with self.subTest(variant=label, path=path):
                    with self.assertRaisesRegex(SchemaUpgradeError, "index_definition_mismatch"):
                        self.init_db() if path == "app init_db" else self.managed_upgrade()
                    self.assertEqual((self.schema_fingerprint(), self.index(name), self.checksums()), before)
        self.ddl(f"DROP INDEX {name}")
        self.managed_upgrade()
        self.everything_ok()
        self.assertEqual(self.init_db(), [])

    def test_change_needed_concurrent_starts_are_recorded_only(self):
        """Two workers starting while a column is missing. Recorded for the report; NOT claimed
        to be as safe as an up-to-date start (that would need the unapproved B / C)."""
        import app.database as database

        self.create()
        self.ddl("ALTER TABLE shared_deck_words DROP COLUMN published_note")
        barrier, results = threading.Barrier(2, timeout=WAIT), {}

        def worker(i):
            try:
                barrier.wait()
                database.init_db()
                results[i] = "ok"
            except BaseException as error:  # noqa: BLE001
                results[i] = f"{type(error).__module__}.{type(error).__name__}"

        threads = [threading.Thread(target=worker, args=(i,), daemon=True) for i in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(WAIT * 2)
        self.assertTrue(all(not t.is_alive() for t in threads))
        target = os.environ.get("E13_CONCURRENT_UPGRADE_OUT")
        if target:
            Path(target).write_text(json.dumps(results), encoding="utf-8")
        self.everything_ok()  # whatever the two did, the schema ends complete and verified


if __name__ == "__main__":
    unittest.main()

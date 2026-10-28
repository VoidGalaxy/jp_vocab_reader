"""Gate E-3 review follow-up: the app's whole init_db (PostgreSQL) against a review in flight,
on the REAL protected local test database only (E-1 harness, E-2 adapter, limited role).
Skipped -- NOT RUN -- without the harness opt-in.

This is a separate, pre-existing risk from E-3's log-preservation change: Codex reproduced a
deadlock between init_db and a subscribed review that also happens with E-3's FK removal
disabled. Since E-D13 A (2026-10-19) init_db skips column / index DDL that is already
satisfied: the latest-schema start must not deadlock (normal check), while a start that
really changes the schema keeps the hard locks (known-risk check, force_ddl model).
The matrix below (pre-change schema: the FK removal is a real change) separates:

  order    upgrade first (init_db paused right after create_postgres_tables)
           review first  (review paused inside its transaction, after its log INSERT)
  kind     personal review / subscribed review (existing progress) / subscribed FIRST review
  variant  current (old CASCADE schema, FK removal on) / control (FK removal disabled)

Every case runs on real separate connections; the second job's wait on the first is proven
with pg_locks / pg_blocking_pids (Overlap in test_srs_e3_fk_real). Outcomes are classified:
  both_ok                   both jobs returned normally
  no_contention             the second finished while the first held its locks
  subscribed_init_deadlock  exactly one job (the review) raised psycopg DeadlockDetected and
                            the server's detail is: the review waits RowShareLock on
                            shared_deck_words, init_db waits AccessExclusiveLock on
                            user_word_progress
  personal_init_deadlock    exactly one job (init_db) raised psycopg DeadlockDetected and the
                            detail is: init_db waits AccessExclusiveLock on vocab_items, the
                            review waits RowExclusiveLock on vocab_items (init_db raising a
                            lock it already held in a weaker mode)
  unexpected                anything else (fails the matrix)
A deadlock is never accepted as "expected" without that exact type and those relations.
The known risk itself is an expected failure: it does not count as a pass.

E3_RACE_OUT=<file.json> writes the matrix (no ids of real users, no secrets).
"""

from __future__ import annotations

import json
import os
import re
import sys
import unittest
from datetime import timedelta
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import _srs_e2_compare as cmp  # noqa: E402
from test_srs_e3_fk_real import Overlap, RealCase, _opt_in  # noqa: E402

# Each known deadlock is identified by (failed job's role, the exact wait graph). The
# review's / init_db's role is told from which job ran which function, never guessed.
KNOWN_DEADLOCKS = {
    "subscribed_init_deadlock": ("review", {("RowShareLock", "shared_deck_words", "review"),
                                            ("AccessExclusiveLock", "user_word_progress", "init")}),
    "personal_init_deadlock": ("init", {("AccessExclusiveLock", "vocab_items", "init"),
                                        ("RowExclusiveLock", "vocab_items", "review")}),
}
STRONG_TABLE_LOCKS = {"ShareUpdateExclusiveLock", "ShareLock", "ShareRowExclusiveLock", "ExclusiveLock",
                      "AccessExclusiveLock"}


class force_ddl:
    """Model of an init_db that HAS column / index changes to make (E-D13 keeps its DDL): the
    first catalog check per table / index answers "missing", so the original
    `ADD COLUMN IF NOT EXISTS` / `CREATE INDEX IF NOT EXISTS` statements run with their
    real locks; the check after the DDL reads the real catalog. Schema rows stay intact,
    so reviews keep working while the change-needed lock pattern is exercised."""

    def start(self):
        from app.srs import schema

        seen_columns, seen_indexes = set(), set()
        real_missing, real_state = schema._missing_pg_columns, schema._pg_index_state

        def missing(connection, table, definitions):
            if table not in seen_columns:
                seen_columns.add(table)
                return list(definitions)
            return real_missing(connection, table, definitions)

        def state(connection, name, table, columns, unique):
            if name not in seen_indexes:
                seen_indexes.add(name)
                return "absent"
            return real_state(connection, name, table, columns, unique)

        self.patches = [mock.patch.object(schema, "_missing_pg_columns", missing),
                        mock.patch.object(schema, "_pg_index_state", state)]
        for p in self.patches:
            p.start()
        return self

    def stop(self):
        for p in self.patches:
            p.stop()


_DETAIL = re.compile(r"Process (\d+) waits for (\w+) on relation (\d+) of database \d+; blocked by process (\d+)")


@unittest.skipUnless(_opt_in(), "Real PostgreSQL init_db race matrix NOT RUN (opt-in not set)")
class InitRaceMatrix(RealCase):
    matrix: dict = {}
    forced: dict = {}

    def relname(self, oid: int) -> str:
        rows = self.sql("SELECT relname::text AS n FROM pg_class WHERE oid = ?", (oid,))
        return rows[0]["n"] if rows else f"oid:{oid}"

    def old_fk_present(self) -> bool:
        return any(f["columns"] == ["vocab_item_id"] for f in self.fks())

    def prepare(self, schema="old"):
        """Fresh rows on the pre-change schema (CASCADE card FK present), or on the latest
        schema (no card FK: nothing for init_db to change)."""
        self.run.reset(restart_identity=True)
        if schema == "latest":
            self.assertFalse(self.old_fk_present())
            return
        if not self.old_fk_present():
            self.ddl("ALTER TABLE review_logs ADD CONSTRAINT review_logs_vocab_item_id_fkey FOREIGN KEY "
                     "(vocab_item_id) REFERENCES vocab_items(id) ON DELETE CASCADE")

    def setup_rows(self, sc, kind):
        from app.repositories.lexeme_repository import (add_word_to_shared_deck, get_or_create_subscription,
                                                        record_lexeme_review, upsert_lexeme)

        sc.clock = cmp.T0
        self.user = sc.user("ir")
        owner = sc.user("ir-owner")
        sc.set_mode(self.user, "fsrs")
        if kind == "personal":
            self.card = sc.card(self.user, "ir1")
            sc.clock = cmp.T0 + timedelta(hours=1)
            assert sc.review(self.user, self.card, "good")["status"] == 200
        else:
            self.deck = sc.sql("INSERT INTO shared_decks (owner_user_id, title, description, visibility, created_at, "
                               "updated_at) VALUES (?, 'ir', '', 'public', ?, ?) RETURNING id",
                               (owner, cmp.T0.isoformat(), cmp.T0.isoformat()))[0]["id"]
            self.lexeme = upsert_lexeme("ir-lx", "ir-lx")
            add_word_to_shared_deck(self.deck, self.lexeme, 1)
            get_or_create_subscription(self.user, self.deck)
            if kind == "subscribed":
                sc.clock = cmp.T0 + timedelta(hours=1)
                first = record_lexeme_review(self.user, self.lexeme, "good", shared_deck_id=self.deck,
                                             request_id="ir-lx-1", expected_card_version=None, session_id="ir",
                                             first_review=True)
                assert first and "srs" in first, first
        sc.clock = cmp.T0 + timedelta(days=2)

    def review_job(self, sc, kind):
        from app.repositories import lexeme_repository, vocab_repository

        if kind == "personal":
            version = sc.version(self.card)
            return lambda: vocab_repository.record_review(self.user, self.card, "good", request_id="ir-r2",
                                                          expected_card_version=version, session_id="ir")
        if kind == "subscribed":
            version = sc.sql("SELECT srs_card_version AS v FROM user_word_progress WHERE user_id = ? AND lexeme_id = ?",
                             (self.user, self.lexeme))[0]["v"]
            return lambda: lexeme_repository.record_lexeme_review(
                self.user, self.lexeme, "good", shared_deck_id=self.deck, request_id="ir-lx-2",
                expected_card_version=version, session_id="ir")
        return lambda: lexeme_repository.record_lexeme_review(
            self.user, self.lexeme, "good", shared_deck_id=self.deck, request_id="ir-lx-first",
            expected_card_version=None, session_id="ir", first_review=True)

    def logs(self, kind):
        if kind == "personal":
            return self.sql("SELECT count(*) AS n FROM review_logs WHERE vocab_item_id = ?", (self.card,))[0]["n"]
        return self.sql("SELECT count(*) AS n FROM lexeme_review_logs WHERE user_id = ? AND lexeme_id = ?",
                        (self.user, self.lexeme))[0]["n"]

    def classify(self, box, order="upgrade first"):
        results = {k: box.get(k) for k in ("first", "second")}
        if any(r is None for r in results.values()) or not box.get("joined"):
            return "unexpected", None
        errors = {k: r[1] for k, r in results.items() if r[0] == "error"}
        if not errors:
            return ("no_contention" if box.get("second_done_while_first_held") else "both_ok"), None
        if len(errors) == 1:
            (who, error), = errors.items()
            if type(error).__name__ == "DeadlockDetected" and type(error).__module__.startswith("psycopg"):
                detail = [{"pid": int(p), "waits_for": mode, "relation": self.relname(int(oid)), "blocked_by": int(b)}
                          for p, mode, oid, b in _DETAIL.findall(str(error))]
                roles = {"first": "init" if order == "upgrade first" else "review"}
                roles["second"] = "review" if roles["first"] == "init" else "init"
                pid_role = {pid: roles[name] for name, pids in box.get("pids", {}).items() for pid in pids}
                graph = {(d["waits_for"], d["relation"], pid_role.get(d["pid"], "?")) for d in detail}
                for name, (failed_role, expected) in KNOWN_DEADLOCKS.items():
                    if roles[who] == failed_role and graph == expected:
                        return name, {"failed_job": roles[who], "detail": detail}
                return "unexpected", {"failed_job": who, "type": "psycopg.DeadlockDetected", "detail": detail,
                                      "server_text": [line for line in str(error).splitlines()
                                                      if line.startswith(("DETAIL", "Process", "HINT"))]}
        return "unexpected", {k: f"{type(e).__module__}.{type(e).__name__}" for k, e in errors.items()}

    def run_case(self, kind, order, variant, schema="old", forced_ddl=False):
        import app.database as database
        from app.srs import reviews

        self.prepare(schema)
        with cmp.Scenario("postgresql", self.run) as sc:
            self.setup_rows(sc, kind)
            logs_before = self.logs(kind)
            review = self.review_job(sc, kind)
            patches = [mock.patch.object(database, "drop_personal_log_card_fk", lambda c: "disabled")] \
                if variant == "control" else []
            if forced_ddl:
                patches.append(force_ddl())
            for p in patches:
                p.start()
            try:
                if order == "upgrade first":
                    box = Overlap(self, database, "create_postgres_tables").run(database.init_db, review)
                else:
                    box = Overlap(self, reviews, "introduced_on").run(review, database.init_db)
            finally:
                for p in patches:
                    p.stop()
        outcome, detail = self.classify(box, order)
        record = {"outcome": outcome, "detail": detail,
                  "results": {k: (v[0], type(v[1]).__name__ if v[0] == "error" else "returned")
                              for k, v in box.items() if k in ("first", "second") and v},
                  "second_blocked_by_first": box.get("second_blocked_by_first"),
                  "second_waits_on": sorted({w["relation"] or w["locktype"] for w in box.get("second_waits", [])}),
                  "logs_before": logs_before, "logs_after": self.logs(kind),
                  "card_fk_after": self.old_fk_present(), "joined": box.get("joined"), "pids": box.get("pids")}
        return record

    def test_matrix(self):
        """Pre-change schema (the E-3 FK removal is a real change for init_db): every kind x
        order x variant must be a clean result or an exactly identified deadlock."""
        self.create(old=True)
        matrix = {}
        for kind in ("personal", "subscribed", "subscribed_first"):
            for order in ("upgrade first", "review first"):
                for variant in ("current", "control"):
                    matrix[f"{kind} | {order} | {variant}"] = self.run_case(kind, order, variant)
        type(self).matrix = matrix
        target = os.environ.get("E3_RACE_OUT")
        if target:
            Path(target).write_text(json.dumps(matrix, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        for name, record in matrix.items():
            with self.subTest(case=name):
                self.assertTrue(record["joined"], record)
                self.assertNotEqual(record["outcome"], "unexpected", record)
                if record["outcome"] == "both_ok":
                    self.assertTrue(record["second_blocked_by_first"], record)  # a real, proven wait
                    self.assertEqual(record["logs_after"], record["logs_before"] + 1, record)
                if record["outcome"] == "subscribed_init_deadlock":
                    # the failed review rolled back: no partial log; init_db's own effect stands
                    self.assertEqual(record["logs_after"], record["logs_before"], record)
                    self.assertTrue(name.startswith("subscribed |"), record)
                    self.assertIn("upgrade first", name)
                if record["outcome"] == "personal_init_deadlock":
                    # init_db rolled back (the old FK is still there); the review committed
                    self.assertEqual(record["logs_after"], record["logs_before"] + 1, record)
                    self.assertTrue(record["card_fk_after"], record)
                    self.assertTrue(name.startswith("personal |") and "upgrade first" in name, record)

    def test_latest_schema_init_db_never_deadlocks_with_reviews(self):
        """E-D13 A (2026-10-19): on the latest schema (E-3 FK removal done) init_db has no DDL
        to run, so no review kind / order may deadlock with it. Converted from the former
        known-risk expectation for the up-to-date start; the change-needed path keeps its own
        known-risk check below."""
        self.create()
        self.assertFalse(self.old_fk_present())
        cases = {}
        for kind in ("personal", "subscribed", "subscribed_first"):
            for order in ("upgrade first", "review first"):
                cases[f"{kind} | {order}"] = self.run_case(kind, order, "current", schema="latest")
        type(self).latest = cases
        target = os.environ.get("E13_LATEST_OUT")
        if target:
            Path(target).write_text(json.dumps(cases, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        for name, record in cases.items():
            with self.subTest(case=name):
                self.assertTrue(record["joined"], record)
                self.assertIn(record["outcome"], ("both_ok", "no_contention"), record)
                self.assertEqual(record["results"], {"first": ("ok", "returned"), "second": ("ok", "returned")}, record)
                self.assertEqual(record["logs_after"], record["logs_before"] + 1, record)  # exactly one review
                self.assertFalse(record["card_fk_after"], record)
                if record["outcome"] == "both_ok":
                    self.assertTrue(record["second_blocked_by_first"], record)

    def test_change_needed_start_vs_reviews_reproduced_exactly(self):
        """A start that really changes the schema (force_ddl model on the latest schema) keeps
        the hard locks of its DDL. Normal check of the MEASUREMENT only: every outcome is a
        clean result or one of the exactly identified deadlocks -- any other exception fails
        here, so it can never be absorbed by the expected failure below."""
        self.create()
        cases = {f"{k} | upgrade first | forced DDL": self.run_case(k, "upgrade first", "current", schema="latest",
                                                                    forced_ddl=True)
                 for k in ("personal", "subscribed")}
        type(self).forced = cases
        target = os.environ.get("E13_FORCED_OUT")
        if target:
            Path(target).write_text(json.dumps(cases, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        for name, record in cases.items():
            with self.subTest(case=name):
                self.assertTrue(record["joined"], record)
                self.assertIn(record["outcome"], ("both_ok", "no_contention", *KNOWN_DEADLOCKS), record)

    @unittest.expectedFailure  # KNOWN RISK: a schema-CHANGING start still deadlocks with live reviews
    def test_known_risk_change_needed_start_never_deadlocks(self):
        """Reads only the results measured by the check above (it runs first and fails loudly on
        its own), so no setup error can be mistaken for this expected failure."""
        cases = type(self).forced
        self.assertEqual([n for n, r in cases.items() if r["outcome"] in KNOWN_DEADLOCKS], [])

    def test_init_db_lock_footprint(self):
        """E-D13 A: a NO-OP init_db (schema already current) takes no strong table lock -- no
        Share / ShareRowExclusive / Exclusive / AccessExclusive / ShareUpdateExclusive -- right
        after create_postgres_tables and at the end of ensure_schema. Read / seed DML locks
        (AccessShare, RowShare, RowExclusive) are normal and recorded, not judged."""
        import threading

        import app.database as database

        self.create()  # current schema: nothing for init_db to change
        footprint, entered, release = {}, threading.Event(), threading.Event()
        pid_box = {}
        real_connect = __import__("_srs_e2_adapter")._GuardedPsycopg.connect

        def recording(shim, url, **kwargs):
            connection = real_connect(shim, url, **kwargs)
            if threading.current_thread().name == "init":
                pid_box["pid"] = connection.info.backend_pid
            return connection

        def snapshot(label):
            run = self.run
            with run._connection() as c:
                try:
                    run._check_target(c)
                    rows = run._rows(c, "SELECT COALESCE(relation::regclass::text, locktype), mode FROM pg_locks "
                                        "WHERE pid = %s AND granted AND locktype = 'relation' ORDER BY 1, 2", (pid_box["pid"],))
                finally:
                    c.rollback()
            footprint[label] = sorted({f"{r[0]}:{r[1]}" for r in rows if not r[0].startswith("pg_")})
            footprint[label + " (strong)"] = sorted(x for x in footprint[label] if x.split(":")[1] in STRONG_TABLE_LOCKS)

        points = {"after create_postgres_tables": (database, "create_postgres_tables"),
                  "end of ensure_schema": (database, "ensure_default_decks_for_users")}
        for label, (target, name) in points.items():
            entered.clear()
            release.clear()
            real = getattr(target, name)

            def paused(*a, _real=real, **k):
                result = _real(*a, **k)
                if threading.current_thread().name == "init":
                    entered.set()
                    release.wait(15)
                return result

            errors = []

            def job():
                try:
                    database.init_db()
                except BaseException as error:  # noqa: BLE001
                    errors.append(error)

            with mock.patch.object(target, name, paused), \
                    mock.patch.object(__import__("_srs_e2_adapter")._GuardedPsycopg, "connect", recording):
                t = threading.Thread(target=job, name="init", daemon=True)
                t.start()
                try:
                    self.assertTrue(entered.wait(15))
                    snapshot(label)
                finally:
                    release.set()
                    t.join(15)
            self.assertFalse(t.is_alive())
            self.assertEqual(errors, [])
        type(self).footprint = footprint
        target = os.environ.get("E3_FOOTPRINT_OUT")
        if target:
            Path(target).write_text(json.dumps(footprint, ensure_ascii=False, indent=1), encoding="utf-8")
        self.assertTrue(footprint["end of ensure_schema"])  # the snapshot really saw init_db's locks
        self.assertEqual(footprint["after create_postgres_tables (strong)"], [], footprint)
        self.assertEqual(footprint["end of ensure_schema (strong)"], [], footprint)


if __name__ == "__main__":
    unittest.main()

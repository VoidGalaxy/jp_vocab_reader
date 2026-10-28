"""Gate E-2b P-S1: the U12 rehearsal flow (test_srs_d2_u12_rehearsal) as ONE variant that
runs unchanged on SQLite and on PostgreSQL, so the per-step records can be compared.

The variant is the original test method's source with exactly these declared changes
(each anchor must occur exactly once, or the module refuses to build the test):
- S1: the SQLite-only identity scan / rebuild CLI (d2_card_identity.py, --sqlite-db) is
  not run. The card the scan flags ("mixed") is flagged through the product function
  identity.flag_identity_unknown with a declared reason; the deleted-id probe (a property
  of the SQLite rebuild) is left out.
- S8 / S9 run in full (Gate E-2c): the U10-b minimize and U10-e prune CLIs. Run through
  _srs_pg_suite.py, their `--sqlite-db <the test's file>` becomes `--local-test-postgres`
  (E-2b ran this variant without them; the tools did not work on PostgreSQL then).
- S10: identity.personal_id_references (SQLite-only by design) is left out.
- has_table / the old-structure table list read the catalog of the engine in use.
- the test's permission-loss fixture writes is_active = FALSE / TRUE instead of 0 / 1.
- the old PostgreSQL structure: without the old CASCADE card FK by default (same starting
  rows as SQLite); E2C_PG_OLD_REVIEW_FK=1 builds it with that FK (reported separately).
Everything else -- accounts, cards, clocks, ratings, request ids, assertions -- is the
original. The original full flow keeps running on SQLite in test_srs_d2_u12_rehearsal.

Steps are written to E2B_REHEARSAL_OUT (JSON) in tearDown, like U12_OUT.
"""

from __future__ import annotations

import inspect
import json
import os
import sys
import textwrap
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import test_srs_d2_u12_rehearsal as original  # noqa: E402

_TABLES_SQL = "SELECT name FROM sqlite_master WHERE type = 'table'"


def _replace_once(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise RuntimeError(f"variant anchor not found exactly once: {old[:60]!r}")
    return text.replace(old, new)


def _between(text: str, start: str, end: str) -> str:
    if text.count(start) != 1 or text.count(end) != 1 or text.index(start) > text.index(end):
        raise RuntimeError(f"variant block anchors not found exactly once: {start[:40]!r} .. {end[:40]!r}")
    return text[text.index(start):text.index(end)]


def _build_variant_source() -> str:
    src = textwrap.dedent(inspect.getsource(original.Rehearsal.test_rehearsal))
    s1 = _between(src, "    # S1 upgrade", "    # pre-U11 draft completion")
    src = src.replace(s1, '''    # S1 (E-2b variant, both engines): upgrade; the identity scan / rebuild CLI is not run.
    self.clock = T0 - DAY
    database.init_db()
    self.assertTrue(self.has_table("srs_user_settings") and self.has_table("srs_migration_runs"))
    with get_connection() as conn:
        written = identity.flag_identity_unknown(
            conn, [identity.IdentityFinding(self.A, c["mixed"], ["e2b_variant_declared"])])
    self.assertEqual(written, 1)
    after_rebuild = self.everything()
    self.record("S1 (variant) upgrade / declared identity flag", identity_flags=written)
''')
    src = _replace_once(src, '''    with get_connection() as conn:
        identity.personal_id_references(conn)
''', "")
    # the test's own permission-loss fixture writes 0 / 1 into a BOOLEAN column (SQLite
    # stores integers); TRUE / FALSE mean the same on both engines
    src = _replace_once(src, "SET is_active = 0 WHERE", "SET is_active = FALSE WHERE")
    src = _replace_once(src, "SET is_active = 1 WHERE", "SET is_active = TRUE WHERE")
    if "run_cli(" in src or "sqlite_master" in src:
        raise RuntimeError("a SQLite-only step is left in the variant")
    # E-4 (read-only, static I1-I5) on the flow's final state; I6 / I7 need a controlled
    # deletion-only baseline, which this mixed flow (reviews and deletes) is not.
    src = src.rstrip("\n") + """

    from app.srs import invariant_audit as e4
    with get_connection() as conn:
        with e4.read_snapshot(conn):
            e4_report = e4.audit(conn)
    self.record("E-4 static audit after the flow", **{k: v["status"] for k, v in e4_report["checks"].items()})
"""
    return src.replace("def test_rehearsal(self):", "def test_rehearsal_variant(self):", 1)


_namespace = dict(vars(original))
exec(compile(_build_variant_source(), original.__file__ + " [E-2b variant]", "exec"), _namespace)


def pre_srs_same_logs(connection) -> None:
    """The old structure WITHOUT the pre-E-3 CASCADE card FK on review_logs: the old app's
    rows then match the SQLite fixture exactly (its deleted card keeps its log). The old
    CASCADE structure is run separately (E2C_PG_OLD_REVIEW_FK=1) and reported on its own."""
    from unittest import mock

    import app.database as database

    with mock.patch.object(database, "drop_personal_log_card_fk", lambda c: "pre-change app"), \
            mock.patch.object(database, "ensure_srs_schema", lambda c, is_postgres: None):
        database.ensure_schema(connection)


class RehearsalVariant(original.Rehearsal):
    test_rehearsal = None  # the original full flow runs in its own module, not here
    test_rehearsal_variant = _namespace["test_rehearsal_variant"]

    def setUp(self):
        super().setUp()
        if self._postgres():
            self._route_schema_through_the_harness()

    def _route_schema_through_the_harness(self):
        """PostgreSQL only: the rehearsal's two init_db calls (old structure with
        ensure_srs_schema patched out, then the upgrade) run as the harness's tracked schema
        step, so every table they create is adopted by the run (and its ownership record
        saved) -- never created behind the harness. Needs the suite's --schema-by-test."""
        from unittest import mock

        import _srs_e2_adapter as adapter
        import _srs_pg_suite as suite
        from test_srs_e2b_upgrade_real import SRS_TABLES, pre_srs_schema

        import app.database as database

        run = suite.CURRENT_RUN
        if run is None:
            raise RuntimeError("run through _srs_pg_suite.py --schema-by-test")
        real_ensure = database.ensure_srs_schema
        declared = adapter.expected_schema_tables()

        def init_db():
            existing = {r["name"] for r in self.sql(
                "SELECT tablename AS name FROM pg_tables WHERE schemaname = current_schema()")}
            old = database.ensure_srs_schema is not real_ensure  # build_old_structure patched it out
            if old:
                apply = pre_srs_schema if os.environ.get("E2C_PG_OLD_REVIEW_FK") == "1" else pre_srs_same_logs
            else:
                apply = None
            wanted = declared - SRS_TABLES if old else declared
            with mock.patch.object(database, "ensure_srs_schema", real_ensure):
                run.track_creation(adapter.schema_step(apply), expected=wanted - existing - {"jp_vocab_e_run_marker"})

        patch = mock.patch.object(database, "init_db", init_db)
        patch.start()
        self.addCleanup(patch.stop)

    def _postgres(self) -> bool:
        from app.database import get_database_engine

        return get_database_engine() == "postgresql"

    def has_table(self, name):
        if self._postgres():
            return bool(self.sql("SELECT 1 FROM pg_tables WHERE schemaname = current_schema() AND tablename = ?",
                                 (name,)))
        return super().has_table(name)

    def sql(self, statement, params=()):
        if statement == _TABLES_SQL and self._postgres():
            statement = "SELECT tablename AS name FROM pg_tables WHERE schemaname = current_schema()"
        return super().sql(statement, params)

    def tearDown(self):
        out = os.environ.get("E2B_REHEARSAL_OUT")
        if out:
            Path(out).write_text(json.dumps(self.steps, ensure_ascii=False, indent=1, default=str), encoding="utf-8")



if __name__ == "__main__":
    unittest.main()

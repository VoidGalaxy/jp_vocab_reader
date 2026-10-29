"""OPS_MIGRATION_RESUME_LEXEME_RACE_PLAN 11절 (LQ1, D-L1~D-L3): the subscribed-card access check of the WRITE path
locks one valid access path (`FOR SHARE OF subscriptions, words`) on PostgreSQL, under a 5-second lock wait limit,
and reports a lock timeout / deadlock of THAT statement with fixed codes. The two column UPDATE privileges it needs
are in the write contract.

FAKE: the PostgreSQL connection of the unit checks (`FakePg`: records SQL, answers the settings read, injects
SQLSTATE errors). Its SQL strings and injected errors are NOT evidence of PostgreSQL syntax, privileges, locks or
waits. REAL: the product functions on SQLite (the app's own connections to a test file), the CLI apply / resume with
real approvals and signatures (test-only temporary OpenSSH keys), the provider path with fake catalogs. SQLite is
not evidence of a PostgreSQL race either. No PostgreSQL, Neon or backend/vocab.db.

Run directly:      python tests/test_srs_migration_access_lock.py
"""

from __future__ import annotations

import os

os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["PYTHON_DOTENV_DISABLED"] = "1"

import inspect  # noqa: E402
import re  # noqa: E402
import sqlite3  # noqa: E402
import sys  # noqa: E402
import unittest  # noqa: E402
from pathlib import Path  # noqa: E402
from unittest import mock  # noqa: E402

TESTS_DIR = Path(__file__).resolve().parent
BACKEND = TESTS_DIR.parent
sys.path.insert(0, str(BACKEND / "scripts"))
sys.path.insert(0, str(TESTS_DIR))
if str(BACKEND) not in sys.path:      # path only, from this file's location
    sys.path.append(str(BACKEND))

import _ops_provider as pv  # noqa: E402
import srs_migrate as cli  # noqa: E402
import test_ops_product_connect as tpc  # noqa: E402  (module only)
import test_srs_migrate_apply_flow as flow  # noqa: E402  (module only)
import test_srs_migrate_resume_lexeme_sqlite as lxs  # noqa: E402  (module only: the lexeme resume SQLite base)

from app.srs import migration  # noqa: E402
from app.srs.engine import CardKey  # noqa: E402
from app.srs.storage import SrsWriteError  # noqa: E402

# Fixed from the contract (plan 10-1 / 11-1), never read back from the code under test.
LOCK_SQL = ("SELECT subscriptions.id AS subscription_id, words.id AS word_id "
            "FROM user_deck_subscriptions AS subscriptions "
            "JOIN shared_deck_words AS words ON words.shared_deck_id = subscriptions.shared_deck_id "
            "WHERE subscriptions.user_id = ? AND subscriptions.is_active = TRUE AND words.lexeme_id = ? "
            "ORDER BY subscriptions.id, words.id LIMIT 1 FOR SHARE OF subscriptions, words")
SETTINGS_SQL = ("SELECT current_setting('lock_timeout') AS previous, "
                "(SELECT setting FROM pg_catalog.pg_settings WHERE name = 'lock_timeout') AS setting_ms")
SET_SQL = "SELECT pg_catalog.set_config('lock_timeout', ?, true)"
NEW_PRIVILEGES = frozenset({("table", "public", "user_deck_subscriptions", "updated_at", "UPDATE"),
                            ("table", "public", "shared_deck_words", "created_at", "UPDATE")})
LEXEME = CardKey("lexeme", 7, 11)
PERSONAL = CardKey("personal", 7, 1)


def flat(sql: str) -> str:
    return re.sub(r"\s+", " ", sql).strip()


class SqlError(Exception):
    """FAKE driver error carrying only a SQLSTATE (and a text that must never be shown)."""

    def __init__(self, sqlstate):
        super().__init__("Driver-Text secret detail")
        self.sqlstate = sqlstate


class Rows:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class FakePg:
    """FAKE PostgreSQL app connection: records each statement; answers the settings read and the access check."""

    is_postgres = True

    def __init__(self, *, previous="0", setting_ms="0", path=True, error=None):
        self.previous, self.setting_ms, self.path, self.error = previous, setting_ms, path, error
        self.log: list = []

    def execute(self, query, params=()):
        query = flat(query)
        self.log.append((query, tuple(params)))
        if query == SETTINGS_SQL:
            return Rows({"previous": self.previous, "setting_ms": self.setting_ms})
        if query == LOCK_SQL:
            if self.error is not None:
                raise self.error
            return Rows({"subscription_id": 3, "word_id": 4} if self.path else None)
        if query == SET_SQL:
            return Rows({"set_config": params[0]})
        if query.startswith("SELECT words.lexeme_id FROM shared_deck_words"):
            return Rows({"lexeme_id": params[1]} if self.path else None)
        raise AssertionError(f"unexpected statement {query}")

    def statements(self):
        return [q for q, _ in self.log]


class LockStatement(unittest.TestCase):
    def test_write_path_locks_one_path_under_the_5s_limit_and_restores(self):
        for previous, setting_ms in (("0", "0"), ("10s", "10000"), ("1min", "60000")):
            with self.subTest(previous=previous):
                conn = FakePg(previous=previous, setting_ms=setting_ms)
                self.assertTrue(migration._authorized(conn, LEXEME, lock=True))
                self.assertEqual(conn.log, [(SETTINGS_SQL, ()), (SET_SQL, ("5000ms",)), (LOCK_SQL, (7, 11)),
                                            (SET_SQL, (previous,))])

    def test_a_shorter_existing_limit_is_never_relaxed(self):
        for previous, setting_ms in (("5s", "5000"), ("200ms", "200"), ("1", "1")):
            with self.subTest(previous=previous):
                conn = FakePg(previous=previous, setting_ms=setting_ms)
                self.assertTrue(migration._authorized(conn, LEXEME, lock=True))
                self.assertEqual(conn.statements(), [SETTINGS_SQL, LOCK_SQL])         # no set, no restore

    def test_no_path_is_no_access(self):
        conn = FakePg(path=False)
        self.assertFalse(migration._authorized(conn, LEXEME, lock=True))
        self.assertEqual(conn.statements(), [SETTINGS_SQL, SET_SQL, LOCK_SQL, SET_SQL])

    def test_read_paths_keep_the_old_statement(self):
        conn = FakePg()
        self.assertTrue(migration._authorized(conn, LEXEME))                             # default: no lock
        self.assertEqual(len(conn.log), 1)
        self.assertNotIn("FOR SHARE", conn.log[0][0])
        self.assertNotIn("lock_timeout", conn.log[0][0])

    def test_sqlite_never_gets_the_lock_clause(self):
        class Lite(FakePg):
            is_postgres = False
        conn = Lite()
        self.assertTrue(migration._authorized(conn, LEXEME, lock=True))
        self.assertEqual(len(conn.log), 1)
        self.assertNotIn("FOR SHARE", conn.log[0][0])

    def test_personal_cards_are_unchanged(self):
        with mock.patch.object(migration, "load_card", return_value={"id": 1}) as load:
            conn = FakePg()
            self.assertTrue(migration._authorized(conn, PERSONAL, lock=True))
        self.assertEqual(conn.log, [])
        load.assert_called_once_with(conn, PERSONAL)

    def test_inspect_card_passes_for_update_and_dry_run_and_rollback_do_not(self):
        seen = []

        def spy(connection, key, *, lock=False):
            seen.append(lock)
            return False
        with mock.patch.object(migration, "_authorized", spy), \
                mock.patch.object(migration, "load_card", return_value={"srs_card_version": 1}), \
                mock.patch.object(migration, "load_logs", return_value=[]):
            migration.inspect_card(FakePg(), LEXEME, for_update=True)
            migration.inspect_card(FakePg(), LEXEME)
            self.assertEqual(migration.judge_rollback_card(FakePg(), LEXEME, {}, None, for_update=True),
                             {"verdict": "access_lost"})
        self.assertEqual(seen, [True, False, False])
        source = inspect.getsource(migration.dry_run)
        self.assertIn("inspect_card(connection, key)", source)                          # dry-run: no for_update


class LockErrors(unittest.TestCase):
    def test_lock_timeout_and_deadlock_get_fixed_codes_and_no_restore_sql(self):
        for sqlstate, code in (("55P03", "migration_access_lock_timeout"), ("40P01", "migration_access_deadlock")):
            with self.subTest(sqlstate=sqlstate):
                conn = FakePg(error=SqlError(sqlstate))
                with self.assertRaises(SrsWriteError) as caught:
                    migration._authorized(conn, LEXEME, lock=True)
                self.assertEqual(caught.exception.code, code)
                self.assertNotIn("Driver-Text", str(caught.exception))
                self.assertIsNone(caught.exception.__cause__)
                self.assertTrue(caught.exception.__suppress_context__)
                self.assertEqual(conn.statements(), [SETTINGS_SQL, SET_SQL, LOCK_SQL])   # nothing after the failure

    def test_other_errors_and_interrupts_are_not_converted(self):
        for error in (SqlError("57014"), SqlError("42501"), SqlError(None), RuntimeError("x"),
                      KeyboardInterrupt(), SystemExit(3)):
            with self.subTest(error=type(error).__name__, state=getattr(error, "sqlstate", None)):
                conn = FakePg(error=error)
                with self.assertRaises(type(error)) as caught:
                    migration._authorized(conn, LEXEME, lock=True)
                self.assertIs(caught.exception, error)
                self.assertEqual(conn.statements(), [SETTINGS_SQL, SET_SQL, LOCK_SQL])

    def test_the_product_never_updates_the_two_access_tables(self):
        source = flat(inspect.getsource(migration))
        for table in ("user_deck_subscriptions", "shared_deck_words"):
            self.assertIsNone(re.search(rf"UPDATE\s+{table}\b", source, re.I), table)
            self.assertIsNone(re.search(rf"(INSERT\s+INTO|DELETE\s+FROM)\s+{table}\b", source, re.I), table)


class WritePrivileges(flow.FlowBase):
    """The write contract: exactly the two column UPDATEs added. Fake catalogs; not PostgreSQL evidence."""

    def test_only_the_two_column_updates_are_added(self):
        self.assertTrue(NEW_PRIVILEGES <= cli.WRITE_PRIVILEGES)
        self.assertFalse(NEW_PRIVILEGES & cli.READ_PRIVILEGES)
        for table in ("user_deck_subscriptions", "shared_deck_words"):
            self.assertEqual({p for p in cli.WRITE_PRIVILEGES - cli.READ_PRIVILEGES if p[2] == table},
                             {p for p in NEW_PRIVILEGES if p[2] == table})
            self.assertNotIn(("table", "public", table, "", "UPDATE"), cli.WRITE_PRIVILEGES)
        self.assertEqual(pv.PROFILE_VERSION, "jp-vocab-ops/profile/v2")                  # same algorithm

    def old_profile(self):
        _, new = cli.contract_profiles(flow.SCOPE, flow.to.T.database)
        old = pv.ExpectedProfile(new.objects, new.privileges - NEW_PRIVILEGES, new.search_path, new.tls_versions)
        return pv.expected_profile_fingerprint(old, role="ops_write_prb", access="write")

    def test_the_write_fingerprint_changed_and_an_old_approval_is_refused(self):
        old = self.old_profile()
        self.assertNotEqual(old, self.write_profile)
        inquiry, apply = self.approvals(self.req, self.plan, self.BATCH, self.read_profile, old)
        write, read = self.step_inputs(self.req, self.plan, inquiry, apply, self.BATCH, self.read_profile, old)
        for label, missing in (("old privileges observed", sorted(NEW_PRIVILEGES)), ("new privileges observed", [])):
            with self.subTest(case=label):
                self.calls = {"dry_run": 0, "apply_plan": []}
                conns = [tpc.BizConn(flow.contract_catalog("read")),
                         tpc.BizConn(flow.contract_catalog("write", missing=missing))]
                out, code = self.apply_run(write=write, read=read, conns=conns)
                self.assertEqual((out["status"], out["code"], out["phase"], code),
                                 ("refused", "expected_profile_not_approved", "before_first_write", 4), out)

    def test_each_new_column_privilege_is_required(self):
        for missing in sorted(NEW_PRIVILEGES):
            with self.subTest(missing=missing[2:4]):
                self.calls = {"dry_run": 0, "apply_plan": []}
                conns = [tpc.BizConn(flow.contract_catalog("read")),
                         tpc.BizConn(flow.contract_catalog("write", missing=[missing]))]
                out, code = self.apply_run(conns=conns)
                self.assertEqual((out["code"], out["phase"], code), ("observed_privileges_missing",
                                                                     "before_first_write", 4))

    def test_the_new_contract_profile_is_handed_over(self):
        self.calls = {"dry_run": 0, "apply_plan": []}
        conns = [tpc.BizConn(flow.contract_catalog("read"))] + [tpc.BizConn(flow.contract_catalog("write"))
                                                                for _ in range(4)]
        out, code = self.apply_run(conns=conns)
        self.assertEqual((out["status"], out["phase"], code), ("ok", "completed", 5), out)   # stubbed product
        self.assertEqual([d["user"] for d in self.driver.calls], ["ops_read"] + ["ops_write_prb"] * 4)


class PartialCommitAndResume(lxs.LexemeBase):
    """REAL apply_plan / CLI on SQLite. The access check of the SECOND card raises the fixed lock-timeout code
    (INJECTED: SQLite has no FOR SHARE); the first card stays committed, the run is `failed`, the CLI reports it
    unconfirmed, and only an explicit resume continues."""

    CARD_SET = ("l1", "l2")

    def access_rows(self):
        connection = sqlite3.connect(self.db_path)
        try:
            return [connection.execute(f"SELECT * FROM {t} ORDER BY id").fetchall()
                    for t in ("user_deck_subscriptions", "shared_deck_words")]
        finally:
            connection.close()

    def test_lock_timeout_keeps_the_committed_card_and_only_an_explicit_resume_continues(self):
        before = self.access_rows()
        real = migration._authorized
        calls = []

        def second_card_times_out(connection, key, *, lock=False):
            calls.append((key.ref_id, lock))
            if lock and key.ref_id == self.lex["l2"]:
                raise SrsWriteError("migration_access_lock_timeout")
            return real(connection, key, lock=lock)
        with mock.patch.object(migration, "_authorized", second_card_times_out):
            out, code = self.first(batch=2)
        self.assertEqual((out["status"], out["code"], out["phase"], out["uncertain"], out["next"], code),
                         ("failed", "migration_access_lock_timeout", "after_start", True, "status_required", 1))
        self.assertNotIn("Driver-Text", str(out))
        self.assertEqual(self.run_state(), ("failed", 1))
        l1_row = self.card_row("l1")
        self.assertEqual((self.card_engine("l1"), self.card_engine("l2")), ("fsrs", "legacy"))
        self.assertEqual(self.snapshot_keys(), ["l1"])
        self.assertIn((self.lex["l2"], True), calls)
        self.assertEqual(self.run_state(), ("failed", 1))                          # nothing retried by itself
        out, code = self.resume(batch=2)
        self.assertEqual((out["phase"], code, out["results"]), ("completed", 0, {"already_applied": 1, "applied": 1}))
        self.assertEqual(self.card_row("l1"), l1_row)
        self.assertEqual(self.snapshot_keys(), ["l1", "l2"])
        self.assertEqual(self.access_rows(), before)                                 # no access-table write


if __name__ == "__main__":
    unittest.main()

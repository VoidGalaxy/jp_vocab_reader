"""Gate E-5b: operator account deletion (app/account_deletion.py, scripts/delete_account.py) on
synthetic SQLite only. A session-only database under backend/jp_vocab_e5b_*; no vocab.db, no
network, no production data. E5B_CONTRACT.md is the contract.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from _e5b_fixture import Accounts, card, set_mode, sql  # noqa: E402
from app import account_deletion  # noqa: E402
from app.account_deletion import AccountDeletionError  # noqa: E402
from app.database import get_connection, init_db  # noqa: E402

# stored content that must never be printed (the DB file NAME may be printed; it is not content)
CONTENT = ("e5b.example.test", "t-migrated", "t-fresh", "t-term", "뜻", "t-deck", "o-word")


class Case(unittest.TestCase):
    def setUp(self):
        self.fresh()

    def fresh(self):
        directory = tempfile.TemporaryDirectory(prefix="jp_vocab_e5b_", dir=BACKEND)
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "synthetic.db"
        env = mock.patch.dict(os.environ, {"APP_ENV": "test", "DATABASE_URL": f"sqlite:///{self.path.as_posix()}"})
        env.start()
        self.addCleanup(env.stop)
        init_db()
        self.a = Accounts()
        return self.a

    def preview(self, user=None):
        with get_connection(read_only=True) as c:
            return account_deletion.preview(c, user or self.a.T)

    def apply(self, plan, user=None, confirm=None):
        user = user or self.a.T
        with get_connection() as c:
            return account_deletion.apply(c, user, confirm_user_id=confirm or user, expected_plan=plan)

    def assert_no_content(self, report):
        text = json.dumps(report, ensure_ascii=False)
        for word in CONTENT:
            self.assertNotIn(word, text)


class PreviewAndApply(Case):
    def test_preview_writes_nothing_and_holds_no_content(self):
        before = self.path.read_bytes()
        report = self.preview()
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual((report["status"], report["eligible"], report["reasons"], report["applied"]),
                         ("preview", True, [], False))
        self.assertTrue(report["server_db_only"])
        expected = self.a.count_of(self.a.T)
        for table, n in expected.items():
            if table in report["counts"]:
                self.assertEqual(report["counts"][table], n, table)
        self.assertTrue(all(report["counts"][t] > 0 for t in account_deletion.OWNED_TABLES if t != "app_feedback"))
        self.assertEqual(len(report["plan"]), 64)
        self.assert_no_content(report)

    def test_apply_deletes_every_row_of_the_account_and_nothing_else(self):
        state = self.a.state()
        others, shared = self.a.everything_but(self.a.T, state), self.a.shared_and_global(state)
        preview = self.preview()
        report = self.apply(preview["plan"])
        self.assertEqual((report["status"], report["applied"]), ("deleted", True))
        self.assertEqual(report["counts"], preview["counts"])
        after = self.a.state()
        self.assertEqual({t: rows for t, rows in self.a.rows_of(self.a.T, after).items() if rows}, {})
        self.assertEqual(self.a.everything_but(self.a.T, after), others)   # other accounts, dev account, globals
        self.assertEqual(self.a.shared_and_global(after), shared)
        self.assert_no_content(report)

    def test_rerun_after_deletion_is_account_not_found_without_writes(self):
        plan = self.preview()["plan"]
        self.apply(plan)
        before = self.path.read_bytes()
        self.assertEqual(self.preview()["status"], "account_not_found")
        self.assertEqual(self.apply(plan)["status"], "account_not_found")
        self.assertEqual(self.path.read_bytes(), before)

    def test_a_plan_changed_since_the_preview_is_refused_without_writes(self):
        plan = self.preview()["plan"]
        card(self.a.T, self.a.deck, "t-late")
        before = self.path.read_bytes()
        report = self.apply(plan)
        self.assertEqual((report["status"], report["eligible"], report["applied"]), ("plan_changed", False, False))
        self.assertEqual(self.path.read_bytes(), before)
        fresh = self.preview()
        self.assertNotEqual(fresh["plan"], plan)
        self.assertEqual(self.apply(fresh["plan"])["status"], "deleted")

    def test_confirmation_and_input_guards(self):
        plan = self.preview()["plan"]
        before = self.path.read_bytes()
        for kwargs, code in (({"confirm": self.a.T + 1}, "explicit_confirmation_required"),):
            with self.assertRaises(AccountDeletionError) as caught:
                self.apply(plan, **kwargs)
            self.assertEqual(caught.exception.code, code)
        for bad_plan in ("", "x" * 63, None):
            with self.assertRaises(AccountDeletionError):
                with get_connection() as c:
                    account_deletion.apply(c, self.a.T, confirm_user_id=self.a.T, expected_plan=bad_plan)
        for bad in (0, -1, True, 2 ** 63, "1"):
            with self.subTest(bad=bad), self.assertRaises(AccountDeletionError):
                with get_connection(read_only=True) as c:
                    account_deletion.preview(c, bad)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.preview(999999)["status"], "account_not_found")


class Blockers(Case):
    def check_blocked(self, reason):
        report = self.preview()
        self.assertEqual((report["status"], report["eligible"]), ("preview", False))
        self.assertIn(reason, report["reasons"])
        before = self.path.read_bytes()
        applied = self.apply(report["plan"])
        self.assertEqual((applied["status"], applied["applied"]), ("blocked", False))
        self.assertIn(reason, applied["reasons"])
        self.assertEqual(self.path.read_bytes(), before)        # blocked: nothing written
        self.assert_no_content(applied)
        return applied

    def test_shared_deck_owner_is_sent_to_review_in_every_state(self):
        cases = {"public": {}, "public with a subscriber": {"subscriber": "O"}, "unpublished": {"unpublish": True},
                 "unpublished with a subscriber": {"unpublish": True, "subscriber": "O"}}
        for name, options in cases.items():
            with self.subTest(name):
                a = self.fresh()
                if options.get("subscriber"):
                    options = dict(options, subscriber=a.O)
                a.own_shared_deck(a.T, a.deck, **options)
                report = self.check_blocked("shared_deck_owner_review")
                self.assertGreaterEqual(report["observed"]["owned_shared_decks"], 1)
                self.assertEqual(self.a.count_of(a.T)["users"], 1)       # not deleted, not "done"

    def test_app_feedback_retention_is_not_guessed(self):
        self.a.add_app_feedback(self.a.T)
        self.check_blocked("app_feedback_retention_review")

    def test_migration_run_in_progress(self):
        run = self.a.rows_of(self.a.T)["srs_migration_runs"][0]["id"]
        sql("UPDATE srs_migration_runs SET status = 'started' WHERE id = ?", (run,))
        self.check_blocked("migration_run_in_progress")

    def test_unreadable_run_ownership_anywhere(self):
        for name, scope in (("not json", "{bad"), ("duplicate key", '{"user_id": 1, "user_id": 2}'),
                            ("no owner", '{"cards": []}'), ("bool owner", '{"user_id": true}'),
                            ("huge owner", '{"user_id": 99999999999999999999}')):
            with self.subTest(name):
                a = self.fresh()
                stamp = "2026-10-01T00:00:00+00:00"
                sql("INSERT INTO srs_migration_runs (run_key, mode, status, scope_json, engine, library_version, "
                    "config_version, started_at) VALUES ('e5b-bad', 'apply', 'completed', ?, 'fsrs', 'x', 'x', ?)",
                    (scope, stamp))
                self.check_blocked("run_ownership_unverifiable")

    def test_mixed_accounts_are_not_deleted(self):
        def other_card_in_my_deck(a):
            sql("UPDATE vocab_items SET deck_id = ? WHERE id = ?", (a.deck, a.o_card))

        def other_snapshot_on_my_run(a):
            sql("UPDATE srs_migration_snapshots SET user_id = ? WHERE user_id = ?", (a.O, a.T))

        def restart_on_other_snapshot(a):
            sql("UPDATE srs_evidence_restarts SET source_snapshot_id = 999999 WHERE user_id = ?", (a.T,))

        def other_feedback_on_my_card(a):
            sql("INSERT INTO meaning_feedback (user_id, vocabulary_id, surface, base_form, reading, "
                "current_meaning_ko, suggested_meaning_ko, reason, source, created_at) "
                "VALUES (?, ?, 'x', 'x', '', '', '', 'x', 'test', '2026-10-01T00:00:00+00:00')", (a.O, a.c2))

        def other_log_on_my_card(a):
            sql("UPDATE review_logs SET vocab_item_id = ? WHERE user_id = ?", (a.c2, a.O))

        def my_receipt_on_other_log(a):
            other_log = sql("SELECT id FROM review_logs WHERE user_id = ?", (a.O,))[0]["id"]
            sql("UPDATE srs_review_receipts SET review_log_id = ? WHERE user_id = ?", (other_log, a.T))

        for setup in (other_card_in_my_deck, other_snapshot_on_my_run, restart_on_other_snapshot,
                      other_feedback_on_my_card, other_log_on_my_card, my_receipt_on_other_log):
            with self.subTest(setup.__name__):
                a = self.fresh()
                setup(a)
                self.check_blocked("cross_account_reference")

    def test_unknown_schema_is_not_deleted_around(self):
        for name, ddl in (("extra table", "CREATE TABLE e5b_extra (id INTEGER PRIMARY KEY, user_id INTEGER)"),
                          ("a trigger", "CREATE TRIGGER e5b_trg AFTER DELETE ON decks BEGIN SELECT 1; END")):
            with self.subTest(name):
                self.fresh()
                sql(ddl)
                report = self.preview()
                self.assertEqual((report["status"], report["reasons"]), ("blocked", ["schema_unverified"]))
                before = self.path.read_bytes()
                applied = self.apply("0" * 64)
                self.assertEqual((applied["status"], applied["reasons"]), ("blocked", ["schema_unverified"]))
                self.assertEqual(self.path.read_bytes(), before)


class Failures(Case):
    def test_a_failure_at_any_step_rolls_everything_back(self):
        from app import database

        real = database.AppSQLiteConnection.execute
        for table in account_deletion.DELETE_ORDER:
            with self.subTest(table):
                self.fresh()
                plan = self.preview()["plan"]
                before = self.path.read_bytes()

                def failing(c, statement, parameters=(), table=table):
                    if statement.startswith(f"DELETE FROM {table} "):
                        raise RuntimeError("synthetic_delete_failure")
                    return real(c, statement, parameters)

                with mock.patch.object(database.AppSQLiteConnection, "execute", failing):
                    with self.assertRaises(AccountDeletionError) as caught:
                        self.apply(plan)
                self.assertEqual(caught.exception.code, "failed:RuntimeError")
                self.assertEqual(self.path.read_bytes(), before)

    def test_residual_count_and_commit_failures_roll_back(self):
        from app import database

        cases = {
            "residual": (mock.patch.object(account_deletion, "_residual_check",
                                           side_effect=AccountDeletionError("residual_rows")), "residual_rows"),
            "count mismatch": (mock.patch.object(account_deletion, "_counts",
                                                 side_effect=lambda plan, real=account_deletion._counts:
                                                 {**real(plan), "decks": real(plan)["decks"] + 1}),
                               "deleted_count_mismatch"),
            "commit": (mock.patch.object(database.AppSQLiteConnection, "commit",
                                         side_effect=RuntimeError("synthetic_commit_failure"), create=True),
                       "failed:RuntimeError"),
        }
        for name, (patch, code) in cases.items():
            with self.subTest(name):
                self.fresh()
                plan = self.preview()["plan"] if name != "count mismatch" else None
                if name == "count mismatch":
                    with patch:
                        plan = self.preview()["plan"]
                before = self.path.read_bytes()
                with patch, self.assertRaises(AccountDeletionError) as caught:
                    self.apply(plan)
                self.assertEqual(caught.exception.code, code)
                self.assertEqual(self.path.read_bytes(), before)
                self.assertEqual(self.a.count_of(self.a.T)["users"], 1)


class Cli(Case):
    SCRIPT = BACKEND / "scripts" / "delete_account.py"

    def cli(self, *args):
        env = {k: v for k, v in os.environ.items() if k not in ("DATABASE_URL", "SRS_E_TEST_POSTGRES_URL",
                                                                "SRS_E_TEST_POSTGRES_OPT_IN")}
        done = subprocess.run([sys.executable, str(self.SCRIPT), "--sqlite-db", str(self.path), *args],
                              capture_output=True, text=True, timeout=120, env=env, encoding="utf-8")
        for stream in (done.stdout, done.stderr):
            for word in CONTENT:
                self.assertNotIn(word, stream)
        return done

    def test_real_cli_preview_refusals_apply_and_rerun(self):
        user = str(self.a.T)
        before = self.path.read_bytes()
        done = self.cli("--user-id", user)
        self.assertEqual(done.returncode, 0, done.stderr[-300:])
        preview = json.loads(done.stdout)
        self.assertEqual((preview["status"], preview["database"]), ("preview", self.path.name))
        self.assertEqual(self.path.read_bytes(), before)
        for args in (("--apply",), ("--apply", "--confirm-user-id", user),
                     ("--apply", "--confirm-user-id", str(self.a.O), "--expect-plan", preview["plan"])):
            done = self.cli("--user-id", user, *args)
            self.assertEqual(done.returncode, 2, args)
        self.assertEqual(self.path.read_bytes(), before)
        card(self.a.T, self.a.deck, "t-after-preview")
        stale = self.cli("--user-id", user, "--apply", "--confirm-user-id", user, "--expect-plan", preview["plan"])
        self.assertEqual((stale.returncode, json.loads(stale.stdout)["status"]), (5, "plan_changed"))
        fresh = json.loads(self.cli("--user-id", user).stdout)
        done = self.cli("--user-id", user, "--apply", "--confirm-user-id", user, "--expect-plan", fresh["plan"])
        self.assertEqual(done.returncode, 0, done.stderr[-300:])
        self.assertEqual(json.loads(done.stdout)["status"], "deleted")
        again = self.cli("--user-id", user, "--apply", "--confirm-user-id", user, "--expect-plan", fresh["plan"])
        self.assertEqual((again.returncode, json.loads(again.stdout)["status"]), (4, "account_not_found"))

    def test_real_cli_blocked_exit_code(self):
        self.a.own_shared_deck(self.a.T, self.a.deck)
        preview = json.loads(self.cli("--user-id", str(self.a.T)).stdout)
        done = self.cli("--user-id", str(self.a.T), "--apply", "--confirm-user-id", str(self.a.T),
                        "--expect-plan", preview["plan"])
        self.assertEqual((done.returncode, json.loads(done.stdout)["status"]), (3, "blocked"))


# ---------------------------------------------------------------- SQLite overlaps ----
class SQLiteRaces(Case):
    """Real separate connections / threads. The first job holds its BEGIN IMMEDIATE; the
    second is seen asking for it and not finishing until the first is released."""

    def operations(self):
        from app.repositories import lexeme_repository as lexemes, shared_deck_repository as shared
        from app.repositories import vocab_repository as vocab
        from app.schemas import DeckCreate
        from app.repositories import deck_repository as decks
        from app.srs import migration
        from app.srs.engine import CardKey

        a = self.a
        o_deck2 = decks.create_deck(a.O, DeckCreate(name="o-deck-2"))[0]["id"]
        card(a.O, o_deck2, "o-word-2")
        o_shared2 = shared.publish_deck(a.O, o_deck2, "o-shared-2", "")["shared_deck_id"]
        set_mode(a.T, "legacy")
        m2 = card(a.T, a.deck, "t-migrate-2")
        vocab.record_review(a.T, m2, "good")
        set_mode(a.T, "fsrs")
        plan = migration.dry_run([CardKey("personal", a.T, m2)])
        # re-conversion: another card applied and rolled back during setup; the race applies its re-plan
        set_mode(a.T, "legacy")
        m3 = card(a.T, a.deck, "t-reconvert")
        vocab.record_review(a.T, m3, "good")
        set_mode(a.T, "fsrs")
        migration.apply_plan(migration.dry_run([CardKey("personal", a.T, m3)]), "e5b-rc-1", approved=True)
        migration.rollback_plan("e5b-rc-1", "e5b-rc-rb", user_id=a.T, approved=True)
        replan = migration.dry_run([CardKey("personal", a.T, m3)])
        return {
            # the migrated FSRS card (c2 carries the identity flag on purpose and takes no review)
            "review": (lambda version=sql("SELECT srs_card_version AS v FROM vocab_items WHERE id = ?", (a.m1,))[0]["v"]:
                       vocab.record_review(a.T, a.m1, "good", request_id="e5b-race", expected_card_version=version,
                                           session_id="e5b"), "plan_changed"),
            "word_create": (lambda: card(a.T, a.deck, "t-race-word"), "plan_changed"),
            "subscribe": (lambda: lexemes.get_or_create_subscription(a.T, o_shared2), "plan_changed"),
            "publish": (lambda: shared.publish_deck(a.T, a.deck, "t-race-shared", ""), "blocked"),
            "migration_apply": (lambda: migration.apply_plan(plan, "e5b-race-run", approved=True), "plan_changed"),
            "rollback": (lambda: migration.rollback_plan("e5b-run-e5b", "e5b-race-rb", user_id=a.T, approved=True),
                         "plan_changed"),
            "reconvert": (lambda: migration.apply_plan(replan, "e5b-rc-2", approved=True), "plan_changed"),
        }

    def race(self, name, delete_first):
        from app import database

        operation, after_write = self.operations()[name]
        plan = self.preview()["plan"]
        others = self.a.everything_but(self.a.T)
        acquired, attempted, release = threading.Event(), threading.Event(), threading.Event()
        results, workers = {}, []
        real = database.AppSQLiteConnection.execute

        def execute(c, statement, parameters=()):
            if statement == "BEGIN IMMEDIATE" and threading.current_thread().name == "second":
                attempted.set()
            result = real(c, statement, parameters)
            if statement == "BEGIN IMMEDIATE" and threading.current_thread().name == "first" and not acquired.is_set():
                acquired.set()
                if not release.wait(10):
                    raise TimeoutError("synthetic holder not released")
            return result

        def delete():
            with get_connection() as c:
                return account_deletion.apply(c, self.a.T, confirm_user_id=self.a.T, expected_plan=plan)

        jobs = (delete, operation) if delete_first else (operation, delete)

        def job(label, action):
            try:
                results[label] = ("ok", action())
            except BaseException as error:  # noqa: BLE001 -- kept as the outcome
                results[label] = ("error", error)

        with mock.patch.object(database.AppSQLiteConnection, "execute", execute):
            try:
                for label, action in zip(("first", "second"), jobs):
                    worker = threading.Thread(target=job, args=(label, action), name=label, daemon=True)
                    workers.append(worker)
                    worker.start()
                    if label == "first":
                        self.assertTrue(acquired.wait(10))
                self.assertTrue(attempted.wait(10))
                threading.Event().wait(0.3)
                self.assertNotIn("second", results)        # waited for the first job's transaction
            finally:
                release.set()
                for worker in workers:
                    worker.join(15)
        self.assertTrue(all(not w.is_alive() for w in workers))
        self.assertEqual(set(results), {"first", "second"})
        self.assertEqual(results["first"][0], "ok", results["first"])
        if delete_first:
            self.assertEqual(results["first"][1]["status"], "deleted")
            outcome = results["second"]
            self.assertEqual(outcome[0], "error", outcome)
            self.assertEqual((getattr(outcome[1], "code", None), getattr(outcome[1], "status_code", None)),
                             ("account_not_found", 404))
            self.assertEqual({t: r for t, r in self.a.rows_of(self.a.T).items() if r}, {})
        else:
            self.assertEqual(results["second"][0], "ok", results["second"])
            status = results["second"][1]["status"]
            if name in ("migration_apply", "rollback", "reconvert"):
                # apply_plan commits in several transactions: the deletion may take the lock
                # between them (a started run -> blocked) or after them (plan_changed)
                self.assertIn(status, ("blocked", "plan_changed"))
                if status == "blocked":
                    self.assertEqual(results["second"][1]["reasons"], ["migration_run_in_progress"])
            else:
                self.assertEqual(status, after_write)
            self.assertEqual(self.a.count_of(self.a.T)["users"], 1)   # untouched; the write is kept
            if after_write == "plan_changed":
                again = self.preview()
                self.assertEqual(self.apply(again["plan"])["status"], "deleted")
                self.assertEqual({t: r for t, r in self.a.rows_of(self.a.T).items() if r}, {})
        if name != "publish" or delete_first:
            self.assertEqual(self.a.everything_but(self.a.T), others)


def _race(name, delete_first):
    def test(self):
        self.race(name, delete_first)
    return test


for _name in ("review", "word_create", "subscribe", "publish", "migration_apply", "rollback", "reconvert"):
    for _delete_first in (False, True):
        setattr(SQLiteRaces, f"test_{_name}_{'delete_first' if _delete_first else 'write_first'}",
                _race(_name, _delete_first))


# ------------------------------------------------- E-5b review fixes (P1 / P2) ----
def _rebuild(table, transform):
    """Re-create a table with an edited CREATE statement, rows kept, FKs off while copying.
    Synthetic session database only: this is how a drifted schema is simulated."""
    ddl = sql("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?", (table,))[0]["sql"]
    edited = transform(ddl)
    assert edited != ddl, "the transform changed nothing"
    edited = edited.replace(f"CREATE TABLE {table}", f"CREATE TABLE {table}_e5b_new", 1)
    with get_connection() as c:
        c.execute("PRAGMA foreign_keys = OFF")
        c.execute(edited)
        c.execute(f"INSERT INTO {table}_e5b_new SELECT * FROM {table}")
        c.execute(f"DROP TABLE {table}")
        c.execute(f"ALTER TABLE {table}_e5b_new RENAME TO {table}")


def _add_constraint(clause):
    def transform(ddl):
        body = ddl.rstrip()
        assert body.endswith(")")
        return body[:-1].rstrip() + ", " + clause + ")"
    return transform


class ForeignKeyStructure(Case):
    """P1: foreign keys are compared per constraint -- source table and columns, referenced
    table and columns (in order), ON DELETE, how many -- against the reviewed structure."""

    def assert_schema_blocked(self):
        report = self.preview()
        self.assertEqual((report["status"], report["reasons"]), ("blocked", ["schema_unverified"]))
        state, before = self.a.state(), self.path.read_bytes()
        applied = self.apply("0" * 64)
        self.assertEqual((applied["status"], applied["applied"]), ("blocked", False))
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.a.state(), state)

    def test_referenced_column_change_no_longer_cascades_into_another_account(self):
        _rebuild("srs_user_settings", lambda ddl: ddl.replace("REFERENCES users(id)", "REFERENCES users(email)"))
        # the target's email now equals the other account's settings key: a CASCADE on the
        # target's users row would delete the OTHER account's settings (reproduced before the fix)
        sql("UPDATE users SET email = ? WHERE id = ?", (str(self.a.O), self.a.T))
        if not sql("SELECT 1 FROM srs_user_settings WHERE user_id = ?", (self.a.O,)):
            sql("INSERT INTO srs_user_settings (user_id, srs_mode, daily_new_goal, settings_version, created_at, "
                "updated_at) VALUES (?, 'legacy', 20, 0, 'x', 'x')", (self.a.O,))
        self.assert_schema_blocked()
        self.assertEqual(len(sql("SELECT 1 FROM srs_user_settings WHERE user_id = ?", (self.a.O,))), 1)

    def test_delete_action_change(self):
        _rebuild("srs_user_settings", lambda ddl: ddl.replace("ON DELETE CASCADE", "ON DELETE SET NULL"))
        self.assert_schema_blocked()

    def test_duplicate_constraint(self):
        _rebuild("srs_card_deletions",
                 _add_constraint("FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE"))
        self.assert_schema_blocked()

    def test_composite_constraint(self):
        sql("CREATE UNIQUE INDEX e5b_users_id_email ON users(id, email)")
        _rebuild("srs_card_identity_flags",
                 _add_constraint("FOREIGN KEY (user_id, reasons) REFERENCES users(id, email)"))
        self.assert_schema_blocked()

    def test_reviewed_structure_is_still_eligible(self):
        report = self.preview()
        self.assertEqual((report["status"], report["eligible"]), ("preview", True))


class ForeignKeyComparisonMocked(unittest.TestCase):
    """P1 cases that cannot be built on the protected PostgreSQL (another schema) or that need
    an exact catalog shape: the comparison itself, with catalog rows given as data. Mocked --
    reported apart from the real-database checks."""

    FIELDS = ("schema", "table", "columns", "ref_schema", "ref_table", "ref_columns", "action")

    def test_postgres_constraint_changes_are_refused(self):
        expected = list(account_deletion.POSTGRES_FK_CONSTRAINTS)
        self.assertTrue(account_deletion._fk_constraints_ok(expected, expected))
        base = next(c for c in expected if c[1] == "srs_user_settings")

        def changed(**kw):
            fields = dict(zip(self.FIELDS, base))
            fields.update(kw)
            return [c for c in expected if c is not base] + [tuple(fields[f] for f in self.FIELDS)]

        cases = {
            "referenced table in another schema": changed(ref_schema="shadow"),
            "source table in another schema": changed(schema="shadow"),
            "referenced column": changed(ref_columns=("email",)),
            "source column": changed(columns=("srs_mode",)),
            "delete action": changed(action="n"),
            "composite": changed(columns=("user_id", "srs_mode"), ref_columns=("id", "email")),
            "composite order": changed(columns=("srs_mode", "user_id"), ref_columns=("email", "id")),
            "duplicate": expected + [base],
            "missing": [c for c in expected if c is not base],
        }
        for name, actual in cases.items():
            with self.subTest(name):
                self.assertFalse(account_deletion._fk_constraints_ok(actual, expected))

    def test_composite_order_is_part_of_the_structure(self):
        two = ("public", "e5b_t", ("a", "b"), "public", "users", ("id", "email"), "c")
        swapped = ("public", "e5b_t", ("b", "a"), "public", "users", ("email", "id"), "c")
        self.assertTrue(account_deletion._fk_constraints_ok([two], [two]))
        self.assertFalse(account_deletion._fk_constraints_ok([swapped], [two]))


class EvidenceRestartBoundaries(Case):
    """P2: a restart's previous / new boundary is a log id of the card kind's log table; a link
    between the target and another account, either way, blocks the deletion."""

    def restart(self, user, kind, ref, previous, new):
        source = 900000 + len(sql("SELECT id FROM srs_evidence_restarts"))
        sql("INSERT INTO srs_evidence_restarts (user_id, card_kind, card_ref, source_snapshot_id, previous_boundary, "
            "new_boundary, card_version_before, created_at) VALUES (?, ?, ?, ?, ?, ?, 0, 'x')",
            (user, kind, ref, source, previous, new))

    def first_personal_log(self, user):
        return sql("SELECT id FROM review_logs WHERE user_id = ? ORDER BY id", (user,))[0]["id"]

    def blocked(self):
        report = self.preview()
        self.assertIn("cross_account_reference", report["reasons"])
        state, before = self.a.state(), self.path.read_bytes()
        applied = self.apply(report["plan"])
        self.assertEqual((applied["status"], applied["applied"]), ("blocked", False))
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.a.state(), state)

    def test_another_accounts_restart_pointing_at_the_targets_log(self):
        for field in ("previous", "new"):
            with self.subTest(field):
                self.fresh()
                mine, theirs = self.first_personal_log(self.a.T), self.first_personal_log(self.a.O)
                pair = (mine, theirs) if field == "previous" else (theirs, mine)
                self.restart(self.a.O, "personal", self.a.o_card, *pair)
                self.blocked()

    def test_the_targets_restart_pointing_at_another_accounts_log(self):
        for field in ("previous", "new"):
            with self.subTest(field):
                self.fresh()
                theirs = self.first_personal_log(self.a.O)
                # the target's own restart (valid source snapshot) with ONE boundary moved to
                # the other account's log: only the boundary differs from a normal record
                column = "previous_boundary" if field == "previous" else "new_boundary"
                sql(f"UPDATE srs_evidence_restarts SET {column} = ? WHERE user_id = ?", (theirs, self.a.T))
                self.blocked()

    def test_the_same_number_in_the_other_log_table_is_not_a_link(self):
        # the other account's personal restart on its own personal log; the target's SUBSCRIBED
        # log carries the same numeric id -- a different table, not a reference to it
        theirs = self.first_personal_log(self.a.O)
        target_lexeme_logs = {r["id"] for r in sql("SELECT id FROM lexeme_review_logs WHERE user_id = ?", (self.a.T,))}
        self.assertIn(theirs, target_lexeme_logs, "fixture: the ids collide across the two log tables")
        self.restart(self.a.O, "personal", self.a.o_card, theirs, theirs)
        report = self.preview()
        self.assertEqual((report["eligible"], report["reasons"]), (True, []))
        others = self.a.everything_but(self.a.T)
        self.assertEqual(self.apply(report["plan"])["status"], "deleted")
        self.assertEqual(self.a.everything_but(self.a.T), others)

    def test_missing_logs_are_neither_links_nor_repaired(self):
        self.restart(self.a.O, "personal", self.a.o_card, 999999, 999998)
        report = self.preview()
        self.assertEqual((report["eligible"], report["reasons"]), (True, []))
        others = self.a.everything_but(self.a.T)
        self.assertEqual(self.apply(report["plan"])["status"], "deleted")
        self.assertEqual(self.a.everything_but(self.a.T), others)   # kept exactly as it was

    def test_the_targets_own_restart_is_deleted_with_it(self):
        report = self.preview()
        self.assertEqual((report["eligible"], report["counts"]["srs_evidence_restarts"]), (True, 1))
        self.assertEqual(self.apply(report["plan"])["status"], "deleted")

# ------------------------------------- E-5b snapshot-internal references (3-3) ----
def make_run(owner, mode, key):
    return sql("INSERT INTO srs_migration_runs (run_key, mode, status, scope_json, engine, library_version, "
               "config_version, started_at) VALUES (?, ?, 'completed', ?, 'fsrs', 'x', 'x', "
               "'2026-10-01T00:00:00+00:00') RETURNING id", (key, mode, json.dumps({"user_id": owner})))[0]["id"]


def make_snapshot(run, owner, kind, ref, legacy_json):
    return sql("INSERT INTO srs_migration_snapshots (run_id, user_id, card_kind, card_ref, card_version_before, "
               "legacy_json, srs_before_json, srs_after_json, history_quality, history_flags, created_at) "
               "VALUES (?, ?, ?, ?, 0, ?, 'null', 'null', NULL, NULL, '2026-10-01T00:00:00+00:00') RETURNING id",
               (run, owner, kind, ref, legacy_json))[0]["id"]


def apply_record(kind_ref, last_log_id=0, fmt=2, restart=None, card_extra=None):
    key = "id" if kind_ref[0] == "personal" else "lexeme_id"
    card = {key: kind_ref[1]} if kind_ref[0] == "personal" else {"id": 1, "lexeme_id": kind_ref[1]}
    card.update(card_extra or {})
    body = {"card": card, "last_log_id": last_log_id}
    if fmt is not None:
        body["format"] = fmt
    if restart is not None:
        body["restart"] = restart
    return json.dumps(body)


def rollback_record(kind_ref, last_log_id, fmt=2):
    key = "id" if kind_ref[0] == "personal" else "lexeme_id"
    body = {"card": {key: kind_ref[1]}, "baseline": {"card_version": 1, "card_fingerprint": "a" * 64,
                                                     "logs_fingerprint": "b" * 64, "last_log_id": last_log_id}}
    if fmt is not None:
        body["format"] = fmt
    return json.dumps(body)


class SnapshotReferences(Case):
    """E5B_CONTRACT 3-3: references inside snapshot records, both directions."""

    def logs(self, table, user):
        return [r["id"] for r in sql(f"SELECT id FROM {table} WHERE user_id = ? ORDER BY id", (user,))]

    def other_snapshot(self, legacy_json, mode="apply", kind="personal"):
        a = self.a
        ref = a.o_card if kind == "personal" else a.lexeme
        run = make_run(a.O, mode, f"e5b-o-{mode}-{len(sql('SELECT id FROM srs_migration_runs'))}")
        return make_snapshot(run, a.O, kind, ref, legacy_json)

    def check(self, reason):
        report = self.preview()
        self.assertIn(reason, report["reasons"])
        self.assertFalse(report["eligible"])
        state, before = self.a.state(), self.path.read_bytes()
        applied = self.apply(report["plan"])
        self.assertEqual((applied["status"], applied["applied"]), ("blocked", False))
        self.assertIn(reason, applied["reasons"])
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.a.state(), state)

    def check_deleted_and_others_kept(self):
        report = self.preview()
        self.assertEqual((report["eligible"], report["reasons"]), (True, []))
        others = self.a.everything_but(self.a.T)
        self.assertEqual(self.apply(report["plan"])["status"], "deleted")
        self.assertEqual(self.a.everything_but(self.a.T), others)

    def test_other_accounts_records_pointing_at_the_target(self):
        def cases(a):
            t_log = self.logs("review_logs", a.T)[0]
            t_lex = self.logs("lexeme_review_logs", a.T)[0]
            t_snap = sql("SELECT id FROM srs_migration_snapshots WHERE user_id = ?", (a.T,))[0]["id"]
            o = ("personal", a.o_card)
            return {
                "apply f2 last_log_id": lambda: self.other_snapshot(apply_record(o, t_log)),
                "apply f3 last_log_id": lambda: self.other_snapshot(apply_record(o, t_log, fmt=3)),
                "apply f1 last_log_id": lambda: self.other_snapshot(apply_record(o, t_log, fmt=None)),
                "restart previous_boundary": lambda: self.other_snapshot(apply_record(
                    o, 0, restart={"previous_boundary": t_log, "rollback_record_id": 0})),
                "restart rollback_record_id": lambda: self.other_snapshot(apply_record(
                    o, 0, restart={"previous_boundary": 0, "rollback_record_id": t_snap})),
                "rollback baseline": lambda: self.other_snapshot(rollback_record(o, t_log), mode="rollback"),
                "rollback f1 baseline": lambda: self.other_snapshot(rollback_record(o, t_log, fmt=None), mode="rollback"),
                "f1 card evidence": lambda: self.other_snapshot(apply_record(
                    o, 0, fmt=None, card_extra={"evidence_from_log_id": t_log})),
                "subscribed log": lambda: self.other_snapshot(apply_record(("lexeme", a.lexeme), t_lex), kind="lexeme"),
            }

        for name in cases(self.a):
            with self.subTest(name):
                a = self.fresh()
                cases(a)[name]()
                self.check("cross_account_reference")

    def test_the_targets_record_pointing_at_another_account(self):
        for field in ("last_log_id", "previous_boundary", "evidence"):
            with self.subTest(field):
                a = self.fresh()
                o_log = self.logs("review_logs", a.O)[0]
                row = sql("SELECT id, legacy_json FROM srs_migration_snapshots WHERE user_id = ?", (a.T,))[0]
                body = json.loads(row["legacy_json"])
                if field == "last_log_id":
                    body["last_log_id"] = o_log
                elif field == "previous_boundary":
                    body["restart"] = {"previous_boundary": o_log, "rollback_record_id": 0}
                else:
                    body.pop("format", None)                      # a format-1 card copy
                    body["card"]["evidence_from_log_id"] = o_log
                sql("UPDATE srs_migration_snapshots SET legacy_json = ? WHERE id = ?", (json.dumps(body), row["id"]))
                self.check("cross_account_reference")

    def test_unrelated_values_are_not_links(self):
        a = self.a
        o = ("personal", a.o_card)
        o_log = self.logs("review_logs", a.O)[0]
        t_lexeme_logs = self.logs("lexeme_review_logs", a.T)
        self.assertIn(o_log, t_lexeme_logs, "fixture: the ids collide across the two log tables")
        self.other_snapshot(apply_record(o, o_log))                         # same number, other table
        self.other_snapshot(apply_record(o, 999999))                        # missing log
        self.other_snapshot(apply_record(o, 0, restart={"previous_boundary": 0, "rollback_record_id": 999999}))
        self.other_snapshot(apply_record(o, 0, fmt=3))                      # format 3, no restart
        self.other_snapshot(apply_record(o, 0, fmt=None, card_extra={"evidence_from_log_id": None}))
        self.other_snapshot(rollback_record(o, 0), mode="rollback")
        self.check_deleted_and_others_kept()

    def test_unreadable_records_hold_the_deletion(self):
        o = lambda a: ("personal", a.o_card)  # noqa: E731
        bad = {
            "broken json": lambda a: "{",
            "duplicate key": lambda a: '{"format": 2, "format": 2, "card": {"id": %d}, "last_log_id": 0}' % a.o_card,
            "deep nesting": lambda a: "[" * 100000 + "]" * 100000,
            "not an object": lambda a: "[1, 2]",
            "huge integer": lambda a: apply_record(o(a), 10 ** 30),
            "bool": lambda a: apply_record(o(a), True),
            "string": lambda a: apply_record(o(a), "12"),
            "float": lambda a: apply_record(o(a), 1.5),
            "negative": lambda a: apply_record(o(a), -1),
            "unknown format": lambda a: apply_record(o(a), 0, fmt=7),
            "missing last_log_id": lambda a: json.dumps({"format": 2, "card": {"id": a.o_card}}),
            "extra top-level key": lambda a: json.dumps({"format": 2, "card": {"id": a.o_card}, "last_log_id": 0,
                                                         "note": 1}),
            "restart keys": lambda a: apply_record(o(a), 0, restart={"previous_boundary": 0}),
            "restart not an object": lambda a: apply_record(o(a), 0, restart=[0]),
            "card not an object": lambda a: json.dumps({"format": 2, "card": 3, "last_log_id": 0}),
            "evidence string": lambda a: apply_record(o(a), 0, fmt=None, card_extra={"evidence_from_log_id": "x"}),
        }
        for name, make in bad.items():
            with self.subTest(name):
                a = self.fresh()
                self.other_snapshot(apply_record(o(a), 0))                  # a normal record beside it
                self.other_snapshot(make(a))
                self.check("snapshot_reference_unverifiable")
        with self.subTest("rollback record in format 3"):
            a = self.fresh()
            self.other_snapshot(rollback_record(o(a), 0, fmt=3), mode="rollback")
            self.check("snapshot_reference_unverifiable")
        with self.subTest("the target's own record"):
            a = self.fresh()
            sql("UPDATE srs_migration_snapshots SET legacy_json = '{' WHERE user_id = ?", (a.T,))
            self.check("snapshot_reference_unverifiable")

    def test_an_unreadable_record_that_cannot_relate_does_not_hold(self):
        from app.repositories import user_repository as users

        lone = users.create_user("lone@e5b.example.test", "lone", "synthetic")["id"]   # no logs, no records
        self.other_snapshot("{")
        report = self.preview(lone)
        self.assertEqual((report["eligible"], report["reasons"]), (True, []))
        others = self.a.everything_but(lone)
        with get_connection() as c:
            done = account_deletion.apply(c, lone, confirm_user_id=lone, expected_plan=report["plan"])
        self.assertEqual(done["status"], "deleted")
        self.assertEqual(self.a.everything_but(lone), others)       # the damaged record is kept as is
        report = self.preview()                                     # the full account does relate
        self.assertIn("snapshot_reference_unverifiable", report["reasons"])

    def test_a_reference_added_after_the_preview_is_caught_under_the_lock(self):
        report = self.preview()
        self.assertTrue(report["eligible"])
        self.other_snapshot(apply_record(("personal", self.a.o_card), self.logs("review_logs", self.a.T)[0]))
        state, before = self.a.state(), self.path.read_bytes()
        applied = self.apply(report["plan"])
        self.assertEqual((applied["status"], applied["reasons"]), ("blocked", ["cross_account_reference"]))
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.a.state(), state)

if __name__ == "__main__":
    unittest.main()

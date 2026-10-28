"""Gate E-5b on REAL PostgreSQL: the protected local test database only (E-1 harness run
marker / OID ownership, E-2 adapter, limited role); opt-in otherwise skipped.

- preview writes nothing (every owned table's ctid / xmin / values, read by the harness);
- apply deletes every row of the account and nothing else; rerun and stale plans write 0;
- blocking conditions (shared-deck owner in every state, app feedback, a started run, mixed
  accounts) write nothing; a failure at any delete step rolls everything back;
- real overlaps, both orders, with the waiting backend proven (pg_locks / pg_blocking_pids):
  deletion vs review, word creation, subscription, publish and migration apply;
- the real CLI with --local-test-postgres: preview, refusals, apply, rerun.
Unknown-schema blocking is checked on SQLite only: an extra relation here would leave the
harness's ownership (it would stop the run, as designed); on PostgreSQL the live FK list
must equal the allow-list for any deletion to be eligible, which every apply below needs.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import test_srs_e3_fk_real as pg  # noqa: E402
from _e5b_fixture import Accounts, card, set_mode, sql  # noqa: E402
from app import account_deletion  # noqa: E402
from app.account_deletion import AccountDeletionError  # noqa: E402
from app.database import get_connection  # noqa: E402

CONTENT = ("e5b.example.test", "t-migrated", "t-fresh", "t-term", "뜻", "t-deck", "o-word")


@unittest.skipUnless(pg._opt_in(), "E-5b real PostgreSQL NOT RUN (opt-in not set)")
class AccountDeletionOnPostgres(pg.RealCase):
    def fresh(self):
        self.run.reset(restart_identity=True)
        self.a = Accounts()
        return self.a

    def fingerprint(self):
        run = self.run
        digest = hashlib.sha256()
        with run._connection() as connection:
            try:
                run._check_target(connection)
                for table in sorted(run.owned_oids):
                    for row in run._rows(connection, f"SELECT ctid::text, xmin::text, row_to_json(t)::text "
                                                     f"FROM public.{table} AS t ORDER BY ctid"):
                        digest.update("|".join(row).encode())
            finally:
                connection.rollback()
        return digest.hexdigest()

    def preview(self, user=None):
        # a plain connection: preview owns its read-only snapshot (the app's read_only=True
        # connection on PostgreSQL has already opened a transaction, which preview refuses)
        with get_connection() as c:
            return account_deletion.preview(c, user or self.a.T)

    def apply(self, plan, user=None):
        user = user or self.a.T
        with get_connection() as c:
            return account_deletion.apply(c, user, confirm_user_id=user, expected_plan=plan)

    # ------------------------------------------------------------------------------------
    def test_preview_apply_rerun_and_stale_plan(self):
        self.create()
        a = self.fresh()
        state = a.state()
        others, shared = a.everything_but(a.T, state), a.shared_and_global(state)
        before = self.fingerprint()
        preview = self.preview()
        self.assertEqual(self.fingerprint(), before)                       # preview: no tuple written
        self.assertEqual((preview["status"], preview["eligible"], preview["reasons"]), ("preview", True, []))
        self.assertTrue(all(preview["counts"][t] > 0 for t in account_deletion.OWNED_TABLES if t != "app_feedback"))
        text = json.dumps(preview, ensure_ascii=False)
        self.assertTrue(all(word not in text for word in CONTENT))
        card(a.T, a.deck, "t-late")                                       # the plan is now stale
        stale_before = self.fingerprint()
        self.assertEqual(self.apply(preview["plan"])["status"], "plan_changed")
        self.assertEqual(self.fingerprint(), stale_before)
        fresh = self.preview()
        report = self.apply(fresh["plan"])
        self.assertEqual((report["status"], report["counts"]), ("deleted", fresh["counts"]))
        after = a.state()
        self.assertEqual({t: r for t, r in a.rows_of(a.T, after).items() if r}, {})
        self.assertEqual(a.everything_but(a.T, after), others)
        self.assertEqual(a.shared_and_global(after), shared)
        done = self.fingerprint()
        self.assertEqual(self.preview()["status"], "account_not_found")
        self.assertEqual(self.apply(fresh["plan"])["status"], "account_not_found")
        self.assertEqual(self.fingerprint(), done)

    def test_blocking_conditions_write_nothing(self):
        self.create()

        def shared_owner(a, **options):
            a.own_shared_deck(a.T, a.deck, **options)

        cases = {
            "shared deck public": (lambda a: shared_owner(a), "shared_deck_owner_review"),
            "shared deck public with subscriber": (lambda a: shared_owner(a, subscriber=a.O), "shared_deck_owner_review"),
            "shared deck unpublished": (lambda a: shared_owner(a, unpublish=True), "shared_deck_owner_review"),
            "app feedback": (lambda a: a.add_app_feedback(a.T), "app_feedback_retention_review"),
            "started run": (lambda a: sql("UPDATE srs_migration_runs SET status = 'started' WHERE id = ?",
                                          (a.rows_of(a.T)["srs_migration_runs"][0]["id"],)), "migration_run_in_progress"),
            "other card in my deck": (lambda a: sql("UPDATE vocab_items SET deck_id = ? WHERE id = ?", (a.deck, a.o_card)),
                                      "cross_account_reference"),
            "other snapshot on my run": (lambda a: sql("UPDATE srs_migration_snapshots SET user_id = ? WHERE user_id = ?",
                                                       (a.O, a.T)), "cross_account_reference"),
        }
        for name, (setup, reason) in cases.items():
            with self.subTest(name):
                a = self.fresh()
                setup(a)
                report = self.preview()
                self.assertIn(reason, report["reasons"])
                before = self.fingerprint()
                applied = self.apply(report["plan"])
                self.assertEqual((applied["status"], applied["applied"]), ("blocked", False))
                self.assertEqual(self.fingerprint(), before)
                self.assertEqual(len(a.rows_of(a.T)["users"]), 1)

    def test_a_failure_at_any_step_rolls_everything_back(self):
        import app.database as database

        self.create()
        real = database.AppPostgresConnection.execute
        for table in account_deletion.DELETE_ORDER:
            with self.subTest(table):
                a = self.fresh()
                plan = self.preview()["plan"]
                before = self.fingerprint()

                def failing(c, query, params=(), table=table):
                    if query.startswith(f"DELETE FROM {table} "):
                        raise RuntimeError("synthetic_delete_failure")
                    return real(c, query, params)

                with mock.patch.object(database.AppPostgresConnection, "execute", failing), \
                        self.assertRaises(AccountDeletionError) as caught:
                    self.apply(plan)
                self.assertEqual(caught.exception.code, "failed:RuntimeError")
                self.assertEqual(self.fingerprint(), before)
                self.assertEqual(len(a.rows_of(a.T)["users"]), 1)
        a = self.fresh()
        plan = self.preview()["plan"]
        before = self.fingerprint()
        with mock.patch.object(database.AppPostgresConnection, "commit",
                               side_effect=RuntimeError("synthetic_commit_failure")), \
                self.assertRaises(AccountDeletionError):
            self.apply(plan)
        self.assertEqual(self.fingerprint(), before)

    # ---------------------------------------------------------------- real overlaps ----
    def operations(self, a):
        from app.repositories import deck_repository as decks, lexeme_repository as lexemes
        from app.repositories import shared_deck_repository as shared, vocab_repository as vocab
        from app.schemas import DeckCreate
        from app.srs import migration, storage
        from app.srs.engine import CardKey

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
        version = sql("SELECT srs_card_version AS v FROM vocab_items WHERE id = ?", (a.m1,))[0]["v"]
        return {
            "review": (lambda: vocab.record_review(a.T, a.m1, "good", request_id="e5b-race",
                                                   expected_card_version=version, session_id="e5b"),
                       storage, "plan_changed"),
            "word_create": (lambda: card(a.T, a.deck, "t-race-word"), vocab, "plan_changed"),
            "subscribe": (lambda: lexemes.get_or_create_subscription(a.T, o_shared2), lexemes, "plan_changed"),
            "publish": (lambda: shared.publish_deck(a.T, a.deck, "t-race-shared", ""), shared, "blocked"),
            "migration_apply": (lambda: migration.apply_plan(plan, "e5b-race-run", approved=True), storage,
                                "plan_changed"),
            "rollback": (lambda: migration.rollback_plan("e5b-run-e5b", "e5b-race-rb", user_id=a.T, approved=True),
                         storage, "plan_changed"),
            "reconvert": (lambda: migration.apply_plan(replan, "e5b-rc-2", approved=True), storage, "plan_changed"),
        }

    def test_deletion_against_writes_both_orders_with_proven_waits(self):
        self.create()
        record = []
        for name in ("review", "word_create", "subscribe", "publish", "migration_apply", "rollback", "reconvert"):
            for delete_first in (True, False):
                with self.subTest(operation=name, delete_first=delete_first):
                    a = self.fresh()
                    operation, module, after_write = self.operations(a)[name]
                    plan = self.preview()["plan"]
                    others = a.everything_but(a.T)

                    def delete(a=a, plan=plan):
                        with get_connection() as c:
                            return account_deletion.apply(c, a.T, confirm_user_id=a.T, expected_plan=plan)

                    jobs = (delete, operation) if delete_first else (operation, delete)
                    target = account_deletion if delete_first else module
                    box = pg.Overlap(self, target, "begin_account_write").run(*jobs)
                    pg.judge_overlap(box)                           # the second backend waited on the first
                    record.append((name, delete_first, [(w["locktype"], w["mode"]) for w in box["second_waits"]]))
                    self.assertEqual(box["first"][0], "ok", box["first"])
                    if delete_first:
                        self.assertEqual(box["first"][1]["status"], "deleted")
                        error = box["second"]
                        self.assertEqual(error[0], "error", error)
                        self.assertEqual((getattr(error[1], "code", None), getattr(error[1], "status_code", None)),
                                         ("account_not_found", 404))
                        self.assertEqual({t: r for t, r in a.rows_of(a.T).items() if r}, {})
                        self.assertEqual(a.everything_but(a.T), others)
                    else:
                        self.assertEqual(box["second"][0], "ok", box["second"])
                        status = box["second"][1]["status"]
                        if name in ("migration_apply", "rollback", "reconvert"):
                            # apply_plan commits in several transactions: the deletion may get the
                            # lock between them (a started run -> blocked) or after (plan_changed).
                            # Both write nothing; which one happened is recorded.
                            self.assertIn(status, ("blocked", "plan_changed"))
                            if status == "blocked":
                                self.assertEqual(box["second"][1]["reasons"], ["migration_run_in_progress"])
                            record.append((name, "outcome", status))
                        else:
                            self.assertEqual(status, after_write)
                        self.assertEqual(len(a.rows_of(a.T)["users"]), 1)
                        if after_write == "plan_changed":  # the write is kept; a fresh plan deletes it
                            self.assertEqual(self.apply(self.preview()["plan"])["status"], "deleted")
                            self.assertEqual({t: r for t, r in a.rows_of(a.T).items() if r}, {})
                            self.assertEqual(a.everything_but(a.T), others)
        for entry in record:
            print("E5B-RACE", entry)

    # ---------------------------------------------------------------- the real CLI ----
    def cli(self, *args):
        env = {k: v for k, v in os.environ.items() if k != "DATABASE_URL"}
        env.update(self.run.cli_marker_environment())  # this run's own marker identity (E-2c review)
        done = subprocess.run([sys.executable, str(BACKEND / "scripts" / "delete_account.py"), "--local-test-postgres",
                               *args], capture_output=True, text=True, timeout=120, env=env, encoding="utf-8")
        for stream in (done.stdout, done.stderr):
            for word in CONTENT + (os.environ["SRS_E_TEST_POSTGRES_URL"], "jp_vocab_e2", "55432",
                                   env["SRS_E_TEST_POSTGRES_MARKER_NONCE"]):
                self.assertNotIn(word, stream)
        return done

    def test_real_cli(self):
        self.create()
        a = self.fresh()
        user = str(a.T)
        before = self.fingerprint()
        done = self.cli("--user-id", user)
        self.assertEqual(done.returncode, 0, done.stderr[-300:])
        preview = json.loads(done.stdout)
        self.assertEqual((preview["status"], preview["database"]), ("preview", "local_test_postgres"))
        self.assertEqual(self.fingerprint(), before)
        self.assertEqual(self.cli("--user-id", user, "--apply").returncode, 2)
        self.assertEqual(self.cli("--user-id", user, "--apply", "--confirm-user-id", user).returncode, 2)
        self.assertEqual(self.fingerprint(), before)
        done = self.cli("--user-id", user, "--apply", "--confirm-user-id", user, "--expect-plan", preview["plan"])
        self.assertEqual(done.returncode, 0, done.stderr[-300:])
        self.assertEqual(json.loads(done.stdout)["status"], "deleted")
        self.assertEqual({t: r for t, r in a.rows_of(a.T).items() if r}, {})
        again = self.cli("--user-id", user, "--apply", "--confirm-user-id", user, "--expect-plan", preview["plan"])
        self.assertEqual((again.returncode, json.loads(again.stdout)["status"]), (4, "account_not_found"))


@unittest.skipUnless(pg._opt_in(), "E-5b real PostgreSQL NOT RUN (opt-in not set)")
class ReviewFixesOnPostgres(AccountDeletionOnPostgres):
    """E-5b review fixes on the protected PostgreSQL. Schema drift is made only through the
    harness's managed DDL step (no new relation; restored afterwards). A table in another
    schema cannot be made here (it would leave the run's ownership): that case is mocked in
    test_e5b_account_deletion and stays unverified on PostgreSQL."""

    test_preview_apply_rerun_and_stale_plan = None
    test_blocking_conditions_write_nothing = None
    test_a_failure_at_any_step_rolls_everything_back = None
    test_deletion_against_writes_both_orders_with_proven_waits = None
    test_real_cli = None

    SETTINGS_FK = ("ALTER TABLE srs_user_settings ADD CONSTRAINT srs_user_settings_user_id_fkey "
                   "FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE")

    def assert_schema_blocked(self):
        a = self.a
        report = self.preview()
        self.assertEqual((report["status"], report["reasons"]), ("blocked", ["schema_unverified"]))
        state, before = a.state(), self.fingerprint()
        applied = self.apply("0" * 64)
        self.assertEqual((applied["status"], applied["applied"]), ("blocked", False))
        self.assertEqual(self.fingerprint(), before)
        self.assertEqual(a.state(), state)

    def test_foreign_key_structure_drift_is_refused(self):
        self.create()
        cases = {
            "duplicate constraint": (
                ["ALTER TABLE srs_card_deletions ADD CONSTRAINT e5b_dup_fk FOREIGN KEY (user_id) "
                 "REFERENCES users(id) ON DELETE CASCADE"],
                ["ALTER TABLE srs_card_deletions DROP CONSTRAINT e5b_dup_fk"]),
            "delete action": (
                ["ALTER TABLE srs_user_settings DROP CONSTRAINT srs_user_settings_user_id_fkey",
                 "ALTER TABLE srs_user_settings ADD CONSTRAINT srs_user_settings_user_id_fkey "
                 "FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE NO ACTION"],
                ["ALTER TABLE srs_user_settings DROP CONSTRAINT srs_user_settings_user_id_fkey", self.SETTINGS_FK]),
            "another source and referenced column": (
                ["ALTER TABLE srs_user_settings ADD CONSTRAINT e5b_email_fk FOREIGN KEY (srs_mode) "
                 "REFERENCES users(email) NOT VALID"],
                ["ALTER TABLE srs_user_settings DROP CONSTRAINT e5b_email_fk"]),
        }
        for name, (drift, restore) in cases.items():
            with self.subTest(name):
                self.fresh()
                self.ddl(*drift)
                try:
                    self.assert_schema_blocked()
                finally:
                    self.ddl(*restore)
                self.assertEqual(self.preview()["eligible"], True)   # the reviewed structure again

    def test_restart_boundaries(self):
        self.create()

        def first_log(user):
            return sql("SELECT id FROM review_logs WHERE user_id = ? ORDER BY id", (user,))[0]["id"]

        def restart(a, user, ref, previous, new):
            source = 900000 + len(sql("SELECT id FROM srs_evidence_restarts"))
            sql("INSERT INTO srs_evidence_restarts (user_id, card_kind, card_ref, source_snapshot_id, previous_boundary, "
                "new_boundary, card_version_before, created_at) VALUES (?, 'personal', ?, ?, ?, ?, 0, 'x')",
                (user, ref, source, previous, new))

        for name in ("other -> target previous", "other -> target new", "target -> other previous",
                     "target -> other new"):
            with self.subTest(name):
                a = self.fresh()
                mine, theirs = first_log(a.T), first_log(a.O)
                if name.startswith("other"):
                    restart(a, a.O, a.o_card, *((mine, theirs) if name.endswith("previous") else (theirs, mine)))
                else:
                    column = "previous_boundary" if name.endswith("previous") else "new_boundary"
                    sql(f"UPDATE srs_evidence_restarts SET {column} = ? WHERE user_id = ?", (theirs, a.T))
                report = self.preview()
                self.assertIn("cross_account_reference", report["reasons"])
                state, before = a.state(), self.fingerprint()
                self.assertEqual(self.apply(report["plan"])["status"], "blocked")
                self.assertEqual(self.fingerprint(), before)
                self.assertEqual(a.state(), state)
        for name in ("same number, other log table", "missing logs"):
            with self.subTest(name):
                a = self.fresh()
                theirs = first_log(a.O)
                if name == "missing logs":
                    restart(a, a.O, a.o_card, 999999, 999998)
                else:
                    lexeme_logs = {r["id"] for r in sql("SELECT id FROM lexeme_review_logs WHERE user_id = ?", (a.T,))}
                    self.assertIn(theirs, lexeme_logs, "fixture: ids collide across the two log tables")
                    restart(a, a.O, a.o_card, theirs, theirs)
                report = self.preview()
                self.assertEqual((report["eligible"], report["reasons"]), (True, []))
                others = a.everything_but(a.T)
                self.assertEqual(self.apply(report["plan"])["status"], "deleted")
                self.assertEqual(a.everything_but(a.T), others)

@unittest.skipUnless(pg._opt_in(), "E-5b real PostgreSQL NOT RUN (opt-in not set)")
class SnapshotReferencesOnPostgres(AccountDeletionOnPostgres):
    """E5B_CONTRACT 3-3 on the protected PostgreSQL (records written through the app connection)."""

    test_preview_apply_rerun_and_stale_plan = None
    test_blocking_conditions_write_nothing = None
    test_a_failure_at_any_step_rolls_everything_back = None
    test_deletion_against_writes_both_orders_with_proven_waits = None
    test_real_cli = None

    def logs(self, table, user):
        return [r["id"] for r in sql(f"SELECT id FROM {table} WHERE user_id = ? ORDER BY id", (user,))]

    def other_snapshot(self, legacy_json, mode="apply", kind="personal"):
        from test_e5b_account_deletion import make_run, make_snapshot

        a = self.a
        ref = a.o_card if kind == "personal" else a.lexeme
        run = make_run(a.O, mode, f"e5b-o-{mode}-{len(sql('SELECT id FROM srs_migration_runs'))}")
        return make_snapshot(run, a.O, kind, ref, legacy_json)

    def check(self, reason):
        report = self.preview()
        self.assertIn(reason, report["reasons"])
        state, before = self.a.state(), self.fingerprint()
        applied = self.apply(report["plan"])
        self.assertEqual((applied["status"], applied["applied"]), ("blocked", False))
        self.assertEqual(self.fingerprint(), before)
        self.assertEqual(self.a.state(), state)

    def test_links_unrelated_values_unreadable_and_stale_preview(self):
        from test_e5b_account_deletion import apply_record, rollback_record

        self.create()
        links = {
            "apply f2 last_log_id": lambda a: self.other_snapshot(apply_record(("personal", a.o_card),
                                                                              self.logs("review_logs", a.T)[0])),
            "rollback baseline": lambda a: self.other_snapshot(
                rollback_record(("personal", a.o_card), self.logs("review_logs", a.T)[0]), mode="rollback"),
            "restart rollback_record_id": lambda a: self.other_snapshot(apply_record(
                ("personal", a.o_card), 0, restart={"previous_boundary": 0, "rollback_record_id": sql(
                    "SELECT id FROM srs_migration_snapshots WHERE user_id = ?", (a.T,))[0]["id"]})),
            "subscribed log": lambda a: self.other_snapshot(
                apply_record(("lexeme", a.lexeme), self.logs("lexeme_review_logs", a.T)[0]), kind="lexeme"),
            "target record -> other log": lambda a: sql(
                "UPDATE srs_migration_snapshots SET legacy_json = ? WHERE user_id = ?",
                (apply_record(("personal", a.m1), self.logs("review_logs", a.O)[0]), a.T)),
        }
        for name, setup in links.items():
            with self.subTest(name):
                a = self.fresh()
                setup(a)
                self.check("cross_account_reference")
        unreadable = {
            "broken json": lambda a: "{",
            "duplicate key": lambda a: '{"format": 2, "format": 2, "card": {"id": %d}, "last_log_id": 0}' % a.o_card,
            "deep nesting": lambda a: "[" * 100000 + "]" * 100000,
            "huge integer": lambda a: apply_record(("personal", a.o_card), 10 ** 30),
            "bool": lambda a: apply_record(("personal", a.o_card), True),
            "unknown format": lambda a: apply_record(("personal", a.o_card), 0, fmt=7),
        }
        for name, make in unreadable.items():
            with self.subTest(name):
                a = self.fresh()
                self.other_snapshot(apply_record(("personal", a.o_card), 0))
                self.other_snapshot(make(a))
                self.check("snapshot_reference_unverifiable")
        with self.subTest("unrelated values are not links"):
            a = self.fresh()
            o_log = self.logs("review_logs", a.O)[0]
            self.assertIn(o_log, self.logs("lexeme_review_logs", a.T), "fixture: ids collide across log tables")
            self.other_snapshot(apply_record(("personal", a.o_card), o_log))
            self.other_snapshot(apply_record(("personal", a.o_card), 999999))
            self.other_snapshot(apply_record(("personal", a.o_card), 0, fmt=3))
            report = self.preview()
            self.assertEqual((report["eligible"], report["reasons"]), (True, []))
            others = a.everything_but(a.T)
            self.assertEqual(self.apply(report["plan"])["status"], "deleted")
            self.assertEqual(a.everything_but(a.T), others)
        with self.subTest("a reference added after the preview"):
            a = self.fresh()
            report = self.preview()
            self.assertTrue(report["eligible"])
            self.other_snapshot(apply_record(("personal", a.o_card), self.logs("review_logs", a.T)[0]))
            state, before = a.state(), self.fingerprint()
            applied = self.apply(report["plan"])
            self.assertEqual((applied["status"], applied["reasons"]), ("blocked", ["cross_account_reference"]))
            self.assertEqual(self.fingerprint(), before)
            self.assertEqual(a.state(), state)

if __name__ == "__main__":
    unittest.main()

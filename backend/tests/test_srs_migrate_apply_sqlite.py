"""OPS_MIGRATION_CLI_PLAN 4-4-8 (C11): first `apply` with the REAL product dry_run / apply_plan on a
synthetic SQLite file made by the test.

REAL: approvals, signatures (test-only temporary keys), the pre-check, backup evidence, the plan file and
the product functions. TEST INJECTION: the connection source (`srs_migrate._product_connector` replaced by
the app's own SQLite connections to the test file); provider checks are covered with fakes in
test_srs_migrate_apply_flow.py. Failures of a connection or commit are INJECTED around real connections.
No PostgreSQL, Neon or backend/vocab.db; nothing here is PostgreSQL transaction evidence.

Run directly:      python tests/test_srs_migrate_apply_sqlite.py
"""

from __future__ import annotations

import os

os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["PYTHON_DOTENV_DISABLED"] = "1"

import hashlib  # noqa: E402
import json  # noqa: E402
import sqlite3  # noqa: E402
import sys  # noqa: E402
import unittest  # noqa: E402
from datetime import timedelta  # noqa: E402
from pathlib import Path  # noqa: E402
from unittest import mock  # noqa: E402

TESTS_DIR = Path(__file__).resolve().parent
BACKEND = TESTS_DIR.parent
sys.path.insert(0, str(BACKEND / "scripts"))
sys.path.insert(0, str(TESTS_DIR))
if str(BACKEND) not in sys.path:      # path only, from this file's location
    sys.path.append(str(BACKEND))

import srs_migrate as cli  # noqa: E402
import test_ops_preflight as pf  # noqa: E402  (module only)
import test_srs_migrate_apply_flow as flow  # noqa: E402  (module only: shared builders)
from test_srs_d2_intro import IntroCase  # noqa: E402  (imports the app; environment fixed above)
from test_srs_queue import NOW, iso  # noqa: E402

from app import database  # noqa: E402
from app.srs import migration  # noqa: E402
from app.srs.engine import CardKey  # noqa: E402

RUN_KEY = flow.RUN_KEY


class Base(flow.ApplyFixtures, pf.Base, IntroCase):
    def setUp(self):
        pf.Base.setUp(self)
        IntroCase.setUp(self)
        self.make_folder()
        self.cards = [self.past_card(n, iso(NOW - timedelta(days=5))) for n in ("a", "b", "c")]
        self.other_card = self.past_card("other", iso(NOW - timedelta(days=5)), user=self.other)
        self.outside = self.past_card("outside", iso(NOW - timedelta(days=5)))
        self.req = cli.make_request(self.user, RUN_KEY, self.cards, [])
        self.planned = migration.dry_run(self.card_keys(), connect=self.connect)
        self.plan = self.write_plan(self.planned, self.user)
        self.ev, self.ev_sig = self.evidence(self.user)
        self.log: list[tuple[str, bool]] = []

    def tearDown(self):
        pf.Base.tearDown(self)

    def config_version(self):
        return migration.DEFAULT_CONFIG.config_version

    def product(self, candidates):
        return hashlib.sha256(migration._plan_json(candidates).encode()).hexdigest()

    def card_keys(self, cards=None):
        return [CardKey("personal", self.user, c) for c in (cards or self.cards)]

    def connect(self, *, read_only=False):
        """TEST INJECTION: the app's own connection to this synthetic file."""
        with mock.patch.dict(os.environ, {"DATABASE_URL": f"sqlite:///{self.db_path.as_posix()}"}):
            return database.get_connection(read_only=read_only)

    def dump(self):
        connection = sqlite3.connect(self.db_path)
        try:
            return list(connection.iterdump())
        finally:
            connection.close()

    def rows(self, ids):
        connection = sqlite3.connect(self.db_path)
        try:
            return [tuple(connection.execute("SELECT * FROM vocab_items WHERE id = ?", (i,)).fetchone()) for i in ids]
        finally:
            connection.close()

    def engine(self, card):
        connection = sqlite3.connect(self.db_path)
        try:
            return connection.execute("SELECT srs_engine FROM vocab_items WHERE id = ?", (card,)).fetchone()[0]
        finally:
            connection.close()

    def apply(self, batch=3, write_connect=None, clock=None, signed_batch=None, ev=None):
        inquiry, apply = self.approvals(self.req, self.plan, signed_batch or batch, pf.READ_PROFILE, pf.WRITE_PROFILE)
        write, read = self.step_inputs(self.req, self.plan, inquiry, apply, batch, pf.READ_PROFILE, pf.WRITE_PROFILE)

        def source(inputs, expected, driver):
            step = inputs.command

            def connect(*, read_only=False):
                self.log.append((step, read_only))
                if step == "apply" and write_connect is not None:
                    return write_connect(read_only=read_only, index=sum(1 for s, _ in self.log if s == "apply"))
                return self.connect(read_only=read_only)
            return connect
        with mock.patch.object(cli, "_product_connector", source), mock.patch.dict(os.environ):
            return cli.run_apply(self.req, batch_size=batch, write_inputs=write, read_inputs=read,
                                 scope=flow.SCOPE, driver=lambda **k: None, plan_path=self.path("plan.json"),
                                 evidence_path=(ev or (self.ev, self.ev_sig))[0],
                                 evidence_signature_path=(ev or (self.ev, self.ev_sig))[1],
                                 clock=clock or (lambda: flow.T0))

    def writes(self):
        return [r for s, r in self.log if s == "apply"]


class FirstApply(Base):
    def test_first_apply_and_untouched_rows(self):
        before = self.rows([self.other_card, self.outside])
        out, code = self.apply()
        self.assertEqual((out["status"], out["phase"], out["cursor"], code), ("ok", "completed", 3, 0))
        self.assertEqual(out["results"], {"applied": 3})
        self.assertEqual([self.engine(c) for c in self.cards], ["fsrs"] * 3)
        self.assertEqual(self.rows([self.other_card, self.outside]), before)   # other account / outside the scope
        self.assertEqual(self.log, [("dry_run", True)] + [("apply", False)] * 5)
        self.assertEqual((out["restore_verified"], out["backup_artifact_checked"]), (False, False))

    def test_existing_key_is_refused_and_nothing_changes(self):
        migration.apply_plan(migration.dry_run(self.card_keys([self.outside]), connect=self.connect), RUN_KEY,
                             approved=True, connect=self.connect)          # another run (other cards) uses the key
        before = self.dump()
        out, code = self.apply()
        self.assertEqual((out["code"], out["phase"], out["changes"], code),
                         ("migration_run_exists", "before_first_write", "none", 4))
        self.assertEqual(self.dump(), before)
        self.assertEqual(self.writes(), [False])                          # the first connection only

    def test_partial_batch(self):
        out, code = self.apply(batch=1, signed_batch=1)
        self.assertEqual((out["phase"], out["cursor"], out["resume"], out["next"], code),
                         ("partial", 1, "not_implemented", "status", 3))
        self.assertEqual([self.engine(c) for c in self.cards], ["fsrs", "legacy", "legacy"])

    def test_plan_changed_opens_no_write(self):
        self.sql_card(self.cards[1])
        before = self.dump()
        out, code = self.apply()
        self.assertEqual((out["code"], out["phase"], code), ("plan_changed", "before_first_write", 4))
        self.assertEqual((self.writes(), self.dump()), ([], before))

    def sql_card(self, card):
        connection = sqlite3.connect(self.db_path)
        try:
            connection.execute("UPDATE vocab_items SET review_level = review_level + 1 WHERE id = ?", (card,))
            connection.commit()
        finally:
            connection.close()

    def test_evidence_expiring_during_dry_run_opens_no_write(self):
        # Valid through the approval pre-check, the first evidence check and the read connection; the time moves
        # only once the REAL product dry_run has returned, so the expiry is met at the recheck before any write.
        expired = flow.BASIS + timedelta(minutes=50)
        real_dry_run = migration.dry_run
        state = {"dry_runs": 0}

        def dry_run_then_time_passes(*args, **kwargs):
            result = real_dry_run(*args, **kwargs)                    # the product's own result, not a stub
            state["dry_runs"] += 1
            return result
        before = self.dump()
        with mock.patch.object(migration, "dry_run", dry_run_then_time_passes):
            out, code = self.apply(clock=lambda: expired if state["dry_runs"] else flow.T0)
        self.assertEqual((out["code"], code), ("backup_evidence_expired", 4))
        self.assertEqual(state["dry_runs"], 1)                                          # real dry_run once
        self.assertEqual(self.log, [("dry_run", True)])                                 # exactly one read connection
        self.assertEqual(self.writes(), [])                                             # no write connection
        self.assertEqual(self.dump(), before)                                           # whole DB unchanged

    def test_signed_batch_size_mismatch(self):
        out, code = self.apply(batch=2, signed_batch=3)
        self.assertEqual((out["code"], code, self.log), ("preflight_command_args_not_approved", 4, []))

    def test_plan_and_evidence_bound_to_the_target(self):
        self.plan = self.write_plan(self.planned, self.user, db_identity=hashlib.sha256(b"x").hexdigest(),
                                    name="other.json")
        import shutil
        shutil.copyfile(self.path("other.json"), self.path("plan2.json"))
        out, code = self.apply_with_plan("plan2.json")
        self.assertEqual((out["code"], code, self.log), ("plan_file_target_mismatch", 4, []))

    def apply_with_plan(self, name):
        original = self.path
        with mock.patch.object(self, "path", lambda n: original(name) if n == "plan.json" else original(n)):
            return self.apply()


class AfterStart(Base):
    def assert_after_start(self, out, code):
        self.assertEqual((out["status"], out["phase"], out["confirmed"], out["uncertain"], out["next"], code),
                         ("failed", "after_start", "unknown", True, "status_required", 1))
        self.assertNotIn("changes", out)
        self.assertNotIn("cursor", out)

    def test_card_failure_keeps_earlier_commits(self):
        real, seen = migration.update_card, []

        def fail_second(connection, key, version, values):
            seen.append(1)
            if len(seen) == 2:
                raise RuntimeError("synthetic write failure")
            return real(connection, key, version, values)
        with mock.patch.object(migration, "update_card", fail_second):
            out, code = self.apply()
        self.assert_after_start(out, code)
        self.assertEqual([self.engine(c) for c in self.cards], ["fsrs", "legacy", "legacy"])   # card 1 committed

    def test_finish_failure(self):
        def connect(*, read_only, index):
            if index == 5:                                                # start, three cards, FINISH
                raise RuntimeError("finish connection lost")
            return self.connect(read_only=read_only)
        out, code = self.apply(write_connect=connect)
        self.assert_after_start(out, code)
        self.assertEqual([self.engine(c) for c in self.cards], ["fsrs"] * 3)

    def test_commit_result_unknown_is_not_success_or_no_change(self):
        def connect(*, read_only, index):
            context = self.connect(read_only=read_only)
            if index != 1:
                return context

            class LostAnswer:                                             # INJECTED: commit done, answer lost
                def __enter__(self):
                    return context.__enter__()

                def __exit__(self, *exc):
                    context.__exit__(*exc)
                    raise OSError("connection reset")
            return LostAnswer()
        out, code = self.apply(write_connect=connect)
        self.assert_after_start(out, code)
        connection = sqlite3.connect(self.db_path)
        try:
            count = connection.execute("SELECT COUNT(*) FROM srs_migration_runs WHERE run_key = ?", (RUN_KEY,)).fetchone()[0]
        finally:
            connection.close()
        self.assertEqual(count, 1)                                        # the run row was committed



class ExpiryAfterStart(Base):
    """An approval that expires between write connections, on REAL product writes (SQLite). The injected
    connection source runs the REAL pre-check on the inputs of each request, as the provider would."""

    def test_expiry_at_a_later_connection_keeps_earlier_commits(self):
        state = {"now": flow.T0, "writes": 0}
        inquiry, apply = self.approvals(self.req, self.plan, 3, pf.READ_PROFILE, pf.WRITE_PROFILE,
                                        apply_changes=flow.SHORT, inquiry_changes=flow.SHORT)
        write, read = self.step_inputs(self.req, self.plan, inquiry, apply, 3, pf.READ_PROFILE, pf.WRITE_PROFILE)
        seen = []

        def source(inputs, expected, driver):
            def connect(*, read_only=False):
                seen.append((inputs.command, inputs.now))
                try:
                    flow.op.run_synthetic_preflight(inputs)          # the provider's pre-check, at this time
                except flow.op.OpsPreflightRefused as error:
                    raise cli.pc.OpsProductConnectionError(f"preflight_{error.code}") from None
                if inputs.command == "apply":
                    state["writes"] += 1
                    if state["writes"] == 2:                          # after the first card's connection
                        state["now"] = flow.EXPIRY
                return self.connect(read_only=read_only)
            return connect

        def timed(inputs, expected, driver):
            return source(inputs, expected, driver)
        with mock.patch.object(cli, "_product_connector", timed), mock.patch.dict(os.environ):
            out, code = cli.run_apply(self.req, batch_size=3, write_inputs=write, read_inputs=read, scope=flow.SCOPE,
                                      driver=lambda **k: None, plan_path=self.path("plan.json"), evidence_path=self.ev,
                                      evidence_signature_path=self.ev_sig, clock=lambda: state["now"])
        self.assertEqual((out["code"], out["phase"], out["uncertain"], out["next"], code),
                         ("preflight_approval_expired", "after_start", True, "status_required", 1))
        self.assertNotIn("changes", out)
        self.assertEqual([self.engine(c) for c in self.cards], ["fsrs", "legacy", "legacy"])   # card 1 stays
        # read; first write; card 1; card 2 refused; the failure-marking request refused too (no retry beyond it)
        self.assertEqual([c for c, _ in seen], ["dry_run", "apply", "apply", "apply", "apply"])
        self.assertEqual([t for _, t in seen], [flow.T0] * 3 + [flow.EXPIRY] * 2)   # each request carried its time

class ProductColumns(unittest.TestCase):
    def test_card_update_columns_follow_the_product(self):
        expected = set(migration.RESTORE_REQUIRED) | {"completion_metric_version", "first_completed_at",
                                                      "srs_card_version", "history_intro_status",
                                                      "history_intro_known_by"}
        self.assertEqual(set(cli.CARD_UPDATE_COLUMNS), expected)


if __name__ == "__main__":
    unittest.main()

"""OPS_MIGRATION_CLI_PLAN 4-3: `srs_migrate.py status` (synthetic).

Two kinds of evidence, kept apart:
- `RealRecords`: REAL run records made by the product `apply_plan` on a synthetic SQLite file made by the
  test (no PostgreSQL, Neon or backend/vocab.db). Damaged or closed states are made by direct UPDATEs and
  are marked as STATE INJECTION. Approvals, signatures (test-only temporary keys) and the pre-check are
  real; the connection source is a TEST INJECTION (the app's own SQLite connection to the file).
- `ProviderFlow`: real approvals / pre-check, FAKE driver, connection and observation, and a STUB reader
  (the fake connection cannot answer SQL).

Run directly:      python tests/test_srs_migrate_status.py
"""

from __future__ import annotations

import os

os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["PYTHON_DOTENV_DISABLED"] = "1"

import hashlib  # noqa: E402
import json  # noqa: E402
import sqlite3  # noqa: E402
import subprocess  # noqa: E402
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

import _ops_preflight as op  # noqa: E402
import srs_migrate as cli  # noqa: E402
import test_ops_preflight as pf  # noqa: E402  (module only)
import test_srs_migrate_cli as tcli  # noqa: E402  (module only)
from test_srs_d2_intro import IntroCase  # noqa: E402  (imports the app; environment fixed above)
from test_srs_queue import NOW, iso  # noqa: E402

from app import database  # noqa: E402
from app.srs import migration  # noqa: E402
from app.srs.engine import CardKey  # noqa: E402

STATUS_STEP = {"command": "status", "access": "read", "role": "ops_read", "profile": pf.READ_PROFILE}


class RecordsBase(pf.Base, IntroCase):
    """Fixtures only (see the module docstring for what is real and what is injected)."""

    def setUp(self):
        pf.Base.setUp(self)
        IntroCase.setUp(self)
        self.cards = [self.past_card(name, iso(NOW - timedelta(days=5))) for name in ("a", "b")]
        self.req = cli.make_request(self.user, "mig-status-1", self.cards, [])

    def tearDown(self):
        pf.Base.tearDown(self)

    # --- fixtures ---------------------------------------------------------------------------------
    def connect(self, *, read_only=False):
        """TEST INJECTION: the app's own connection to this synthetic file (named explicitly, since the
        CLI fixes DATABASE_URL to an in-memory value)."""
        with mock.patch.dict(os.environ, {"DATABASE_URL": f"sqlite:///{self.db_path.as_posix()}"}):
            return database.get_connection(read_only=read_only)

    def card_keys(self, cards=None, user=None):
        return [CardKey("personal", user or self.user, c) for c in (cards or self.cards)]

    def apply(self, cards=None, run_key="mig-status-1", user=None, **kwargs):
        plan = migration.dry_run(self.card_keys(cards, user), connect=self.connect)
        return migration.apply_plan(plan, run_key, approved=True, connect=self.connect, **kwargs)

    def sql(self, statement, params=()):
        """STATE INJECTION: a direct change of the synthetic record."""
        with self.connect() as c:
            c.execute(statement, params)

    def run_row(self, run_key="mig-status-1"):
        with self.connect(read_only=True) as c:
            return dict(c.execute("SELECT * FROM srs_migration_runs WHERE run_key = ?", (run_key,)).fetchone())

    def dump(self):
        connection = sqlite3.connect(self.db_path)
        try:
            return list(connection.iterdump())
        finally:
            connection.close()

    def status(self, req=None, approval=None):
        req = req or self.req
        approval = approval or self.inquiry(tool="srs_migrate", accounts=[req.account_id], max_accounts=1,
                                            steps=[STATUS_STEP], job={"key": req.run_key, "inputs": cli.job_inputs(req)})
        inputs = self.inputs(approval, command="status", account_id=req.account_id, job_key=req.run_key,
                             job_inputs=cli.job_inputs(req), product_fingerprint=None)
        before = self.dump()
        with mock.patch.object(cli, "_product_connector", lambda *a, **k: self.connect),                 mock.patch.dict(os.environ):                             # the CLI's environment fix is undone after
            out, code = cli.run_status(req, inputs=inputs, expected=None, driver=lambda **k: None)
        self.assertEqual(self.dump(), before)                           # no DB change by the status read
        return out, code



class RealRecords(RecordsBase):
    # --- states -----------------------------------------------------------------------------------
    def test_not_started_and_hidden_runs_answer_the_same(self):
        missing, code = self.status()
        self.assertEqual((missing, code), ({"status": "ok", "command": "status", "state": "not_started"}, 0))
        other_cards = [self.personal("o1", user=self.other)]
        self.apply(other_cards, user=self.other)                         # another account's run, same key
        self.assertEqual(self.status(), (missing, 0))
        other_req = cli.make_request(self.user, "mig-status-1", other_cards, [])
        self.assertEqual(self.status(other_req), (missing, 0))           # not even with its card list
        self.sql("UPDATE srs_migration_runs SET scope_json = ? WHERE run_key = ?", ("{not json", "mig-status-1"))
        self.assertEqual(self.status(), (missing, 0))                    # owner not established: same answer

    def test_completed_and_completed_with_blocked(self):
        self.apply()
        out, code = self.status()
        self.assertEqual((out["state"], out["cursor"], out["card_count"], out["results"], out["finished"], code),
                         ("completed", 2, 2, {"applied": 2}, True, 0))
        self.assertEqual(out["window"], "open")
        self.assertNotIn("resume_ready", out)
        cards = [self.past_card("g", iso(NOW - timedelta(days=5))), 999999]   # 999999 is unavailable -> blocked
        req = cli.make_request(self.user, "mig-status-2", cards, [])
        self.apply(cards, run_key="mig-status-2")
        out, code = self.status(req)
        self.assertEqual((out["state"], code), ("completed", 5))       # completed, with a blocked card
        self.assertEqual(out["results"], {"applied": 1, "blocked": 1})

    def test_incomplete_failed_and_cursor_end(self):
        self.apply(batch_size=1)
        out, code = self.status()
        self.assertEqual((out["state"], out["cursor"], code), ("incomplete", 1, 3))
        cards = [self.past_card(n, iso(NOW - timedelta(days=5))) for n in ("c", "d")]
        req = cli.make_request(self.user, "mig-status-f", cards, [])
        real_update, seen = migration.update_card, []

        def fail_second(connection, key, version, values):
            seen.append(1)
            if len(seen) == 2:
                raise RuntimeError("synthetic write failure")
            return real_update(connection, key, version, values)
        with mock.patch.object(migration, "update_card", fail_second), self.assertRaises(RuntimeError):
            self.apply(cards, run_key="mig-status-f")
        out, code = self.status(req)
        self.assertEqual((out["state"], out["cursor"], code), ("failed_at_cursor", 1, 3))
        cards = [self.past_card(n, iso(NOW - timedelta(days=5))) for n in ("e", "f")]
        req = cli.make_request(self.user, "mig-status-e", cards, [])
        calls = []

        def finish_fails(*, read_only=False):
            calls.append(read_only)
            if len(calls) == 4:                                          # start, card, card, FINISH
                raise RuntimeError("finish connection lost")
            return self.connect(read_only=read_only)
        plan = migration.dry_run(self.card_keys(cards), connect=self.connect)
        with self.assertRaises(RuntimeError):
            migration.apply_plan(plan, "mig-status-e", approved=True, connect=finish_fails)
        out, code = self.status(req)
        self.assertEqual((out["state"], out["cursor"], out["finished"], code), ("cursor_end_not_completed", 2, False, 6))
        self.assertEqual(self.run_row("mig-status-e")["status"], "started")   # not corrected by status

    def test_closed_conflict_and_pruned_scope(self):
        self.apply()
        row = self.run_row()
        reduced = {"format": migration.PRUNED_SCOPE_FORMAT, "user_id": self.user, "config_version": row["config_version"],
                   "cards": [{"kind": "personal", "ref_id": c} for c in sorted(self.cards)],
                   "request_sha256": hashlib.sha256(row["scope_json"].encode()).hexdigest()}
        self.sql("UPDATE srs_migration_runs SET scope_json = ? WHERE id = ?", (json.dumps(reduced), row["id"]))
        out, _ = self.status()
        self.assertEqual(out["state"], "completed")                      # pruned form: owner and cards still known
        narrower = cli.make_request(self.user, "mig-status-1", self.cards[:1], [])
        out, code = self.status(narrower)
        self.assertEqual((out, code), ({"status": "ok", "command": "status", "state": "conflict", "reason": "cards",
                                        "window": "open"}, 6))
        scope = json.loads(row["scope_json"])                            # a run made under an older engine config
        scope["config_version"] = "other-config"
        for card in scope["cards"]:
            if card["values"] is not None:
                card["values"] = json.dumps(dict(json.loads(card["values"]), srs_config_version="other-config"),
                                            sort_keys=True, separators=(",", ":"))
        self.sql("UPDATE srs_migration_runs SET scope_json = ?, config_version = ? WHERE id = ?",
                 (json.dumps(scope), "other-config", row["id"]))
        self.assertEqual(self.status()[0]["reason"], "config")
        self.sql("UPDATE srs_migration_runs SET scope_json = ?, config_version = ?, status = 'aborted' WHERE id = ?",
                 (row["scope_json"], row["config_version"], row["id"]))
        out, code = self.status()
        self.assertEqual((out["state"], code), ("closed", 0))

    def test_inconsistent_records(self):                                 # STATE INJECTION on a real record
        self.apply()
        row = self.run_row()
        good = json.loads(row["summary_json"])

        def summary(value):
            return value if isinstance(value, str) else json.dumps(value)
        cases = {
            "summary_unreadable": dict(summary_json="{bad"),
            "cursor_invalid": dict(summary_json=summary({**good, "cursor": True})),
            "cursor beyond": dict(summary_json=summary({**good, "cursor": 3})),
            "results_invalid": dict(summary_json=summary({**good, "results": good["results"][:1]})),
            "results order": dict(summary_json=summary({**good, "results": good["results"][::-1]})),
            "results kind": dict(summary_json=summary({**good, "results": [dict(good["results"][0], result="done"),
                                                                           good["results"][1]]})),
            "finished_at_mismatch": dict(finished_at=None),
            "failed_at_end": dict(status="failed", finished_at=None),
            "completed_short": dict(summary_json=summary({"cursor": 1, "results": good["results"][:1]})),
        }
        expected = {"cursor beyond": "cursor_invalid", "results order": "results_invalid",
                    "results kind": "results_invalid", "completed_short": "snapshot_mismatch"}
        for label, changes in cases.items():
            with self.subTest(case=label):
                self.sql("UPDATE srs_migration_runs SET " + ", ".join(f"{k} = ?" for k in changes) + " WHERE id = ?",
                         (*changes.values(), row["id"]))
                out, code = self.status()
                self.assertEqual((out["state"], out["reason"], code), ("inconsistent", expected.get(label, label), 6))
                self.sql("UPDATE srs_migration_runs SET summary_json = ?, status = ?, finished_at = ? WHERE id = ?",
                         (row["summary_json"], row["status"], row["finished_at"], row["id"]))
        self.assertEqual(self.status()[0]["state"], "completed")

    def test_snapshots_of_this_run_only(self):                           # STATE INJECTION
        self.apply()
        other = self.apply([self.cards[0]], run_key="mig-status-other")  # another run touching the same card
        del other
        row = self.run_row()
        self.sql("DELETE FROM srs_migration_snapshots WHERE run_id = ? AND card_ref = ?", (row["id"], self.cards[0]))
        out, code = self.status()
        self.assertEqual((out["state"], out["reason"], code), ("inconsistent", "snapshot_mismatch", 6))

    def test_window_boundaries(self):
        self.apply()
        start = migration.read_utc(self.run_row()["started_at"])
        for now, window in ((start + migration.ROLLBACK_WINDOW - timedelta(seconds=1), "open"),
                            (start + migration.ROLLBACK_WINDOW, "expired")):
            with self.subTest(window=window), mock.patch.object(migration, "now_utc", return_value=now):
                out, code = self.status()
                self.assertEqual((out["state"], out["window"], code), ("completed", window, 0))
        self.sql("UPDATE srs_migration_runs SET started_at = ? WHERE run_key = ?", ("not a time", "mig-status-1"))
        out, _ = self.status()
        self.assertEqual((out["state"], out["window"]), ("completed", "unverifiable"))

    def test_scope_and_signature_refusals_read_nothing(self):
        self.apply()
        other = cli.make_request(self.user, "mig-status-1", self.cards[:1], [])
        approval = self.inquiry(tool="srs_migrate", accounts=[self.user], max_accounts=1, steps=[STATUS_STEP],
                                job={"key": self.req.run_key, "inputs": cli.job_inputs(self.req)})
        out, code = self.status(other, approval)
        self.assertEqual((out["code"], code), ("preflight_job_input_mismatch", 4))



class RecordingConnect:
    """TEST INJECTION wrapper: records every SQL text the status reader sends (no result is changed)."""

    def __init__(self, case):
        self.case, self.sql = case, []

    def __call__(self, *, read_only=False):
        context = self.case.connect(read_only=read_only)
        recorder = self

        class Proxy:
            def __enter__(self):
                self.connection = context.__enter__()
                return self

            def __exit__(self, *exc):
                return context.__exit__(*exc)

            def execute(self, statement, params=()):
                recorder.sql.append(statement)
                return self.connection.execute(statement, params)
        return Proxy()


class DuplicateKeys(RecordsBase):
    """Contract 4-3 fix: duplicate JSON keys at any depth make the owner unknown (scope) or the record
    inconsistent (summary of an owned run). REAL records; the duplicates are STATE INJECTION."""

    def status_recorded(self, req=None):
        recorder = RecordingConnect(self)
        req = req or self.req
        approval = self.inquiry(tool="srs_migrate", accounts=[req.account_id], max_accounts=1,
                                steps=[STATUS_STEP], job={"key": req.run_key, "inputs": cli.job_inputs(req)})
        inputs = self.inputs(approval, command="status", account_id=req.account_id, job_key=req.run_key,
                             job_inputs=cli.job_inputs(req), product_fingerprint=None)
        before = self.dump()
        with mock.patch.object(cli, "_product_connector", lambda *a, **k: recorder), mock.patch.dict(os.environ):
            out, code = cli.run_status(req, inputs=inputs, expected=None, driver=lambda **k: None)
        self.assertEqual(self.dump(), before)
        return out, code, recorder.sql

    def missing_answer(self):
        req = cli.make_request(self.user, "mig-no-such-key", self.cards, [])
        out, code, _ = self.status_recorded(req)
        return out, code

    def snapshot_reads(self, sql):
        return [q for q in sql if "srs_migration_snapshots" in q]

    def set_scope(self, text, run_key):
        self.sql("UPDATE srs_migration_runs SET scope_json = ? WHERE run_key = ?", (text, run_key))

    def test_duplicate_owner_of_another_account_is_hidden(self):
        missing = self.missing_answer()
        other_cards = [self.past_card("x", iso(NOW - timedelta(days=5)), user=self.other)]
        self.apply(other_cards, run_key="mig-dup", user=self.other)
        original = self.run_row("mig-dup")["scope_json"]
        mine, theirs = f'"user_id":{self.user}', f'"user_id":{self.other}'
        req = cli.make_request(self.user, "mig-dup", other_cards, [])
        for label, owner in (("theirs then mine", f"{theirs},{mine}"), ("mine then theirs", f"{mine},{theirs}"),
                             ("theirs repeated", f"{theirs},{theirs}")):
            with self.subTest(case=label):
                self.set_scope(original.replace(theirs, owner), "mig-dup")
                out, code, sql = self.status_recorded(req)
                self.assertEqual((out, code), missing)                    # byte-for-byte the missing-key answer
                self.assertEqual(self.snapshot_reads(sql), [])            # no snapshot read before ownership

    def test_duplicates_in_my_own_scope_hide_the_run(self):
        self.apply()
        row = self.run_row()
        mine = f'"user_id":{self.user}'
        first = f'"ref_id":{sorted(self.cards)[0]}'
        reduced = json.dumps({"format": migration.PRUNED_SCOPE_FORMAT, "user_id": self.user,
                              "config_version": row["config_version"],
                              "cards": [{"kind": "personal", "ref_id": c} for c in sorted(self.cards)],
                              "request_sha256": hashlib.sha256(row["scope_json"].encode()).hexdigest()},
                             sort_keys=True, separators=(",", ":"))
        missing = self.missing_answer()
        cases = {"repeated owner": row["scope_json"].replace(mine, f"{mine},{mine}"),
                 "card field repeated": row["scope_json"].replace(first, f"{first},{first}", 1),
                 "pruned repeated owner": reduced.replace(mine, f"{mine},{mine}"),
                 "pruned card field repeated": reduced.replace(first, f"{first},{first}", 1)}
        for label, text in cases.items():
            with self.subTest(case=label):
                self.assertNotEqual(text, row["scope_json"])
                self.set_scope(text, "mig-status-1")
                out, code, sql = self.status_recorded()
                self.assertEqual((out, code), missing)
                self.assertEqual(self.snapshot_reads(sql), [])
        self.set_scope(reduced, "mig-status-1")
        self.assertEqual(self.status_recorded()[0]["state"], "completed")    # the clean pruned form still works
        self.set_scope(row["scope_json"], "mig-status-1")
        self.assertEqual(self.status_recorded()[0]["state"], "completed")

    def test_duplicate_summary_keys_are_inconsistent(self):
        self.apply()
        row = self.run_row()
        summary = row["summary_json"]
        result_key = '"result":"applied"'
        cases = {"top level": summary.replace('"cursor":2', '"cursor":2,"cursor":1', 1),
                 "result item": summary.replace(result_key, f'{result_key},"result":"blocked"', 1)}
        for label, text in cases.items():
            with self.subTest(case=label):
                self.assertNotEqual(text, summary)
                self.sql("UPDATE srs_migration_runs SET summary_json = ? WHERE id = ?", (text, row["id"]))
                out, code, _ = self.status_recorded()
                self.assertEqual((out["state"], out["reason"], code), ("inconsistent", "summary_unreadable", 6))
                self.assertNotIn("cursor", out)
        self.sql("UPDATE srs_migration_runs SET summary_json = ? WHERE id = ?", (summary, row["id"]))
        self.assertEqual(self.status_recorded()[0]["state"], "completed")

class PgRuleConn(tcli.tpc.BizConn):
    """FAKE connection following the documented PostgreSQL rule that SET TRANSACTION statements may
    follow each other before the first query (not verified on a real server here)."""

    def execute(self, sql, params=None):
        if sql.startswith("SET TRANSACTION") and all(s.startswith("SET TRANSACTION") for s in self._txn):
            self.log.append(sql)
            self._txn.append(sql)
            return None
        result = super().execute(sql, params)
        self._txn.append(sql)
        return result

    def commit(self):
        self._txn = []
        return super().commit()

    def rollback(self):
        self._txn = []
        return super().rollback()

    @property
    def _txn(self):
        return self.__dict__.setdefault("_txn_list", [])

    @_txn.setter
    def _txn(self, value):
        self.__dict__["_txn_list"] = value


class ProviderFlow(tcli.FlowBase):
    """REAL approvals / pre-check; FAKE driver, connection (PgRuleConn), observation; STUB reader."""

    def setUp(self):
        super().setUp()
        self.conn = PgRuleConn()
        self.driver = tcli.ta.FakeDriver(self.conn)

    def approval(self, **changes) -> bytes:
        values = dict(tool="srs_migrate", accounts=[7], max_accounts=1,
                      steps=[{"command": "status", "access": "read", "role": "ops_read", "profile": self.read_profile()}],
                      job={"key": self.req.run_key, "inputs": cli.job_inputs(self.req)})
        values.update(changes)
        return self.inquiry(**values)

    def flow_inputs(self, approval=None, **changes):
        values = dict(command="status")
        values.update(changes)
        return super().flow_inputs(approval or self.approval(), **values)

    def run_status(self, inputs=None, driver="default"):
        calls = []

        def reader(connect, request, migration):
            calls.append(request.run_key)
            with connect(read_only=True) as c:
                c.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
                c.execute("SELECT 1")
            return None
        with mock.patch.object(cli, "read_status", reader):
            out, code = cli.run_status(self.req, inputs=inputs or self.flow_inputs(), expected=tcli.to.READ_EXPECTED,
                                       driver=self.driver if driver == "default" else driver)
        return out, code, calls

    def test_read_connection_transaction_and_cleanup(self):
        out, code, calls = self.run_status()
        self.assertEqual((out, code, calls), ({"status": "ok", "command": "status", "state": "not_started"}, 0,
                                              [self.req.run_key]))
        self.assertEqual(self.conn.log[self.conn.log.index("ROLLBACK") + 1:],
                         ["SET TRANSACTION READ ONLY", "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ", "SELECT 1",
                          "COMMIT"])
        self.assertEqual((self.conn.close_calls, len(self.driver.calls)), (1, 1))
        self.assertFalse(os.path.exists(self.out))                      # status writes no plan file

    def test_wrong_approvals_open_nothing(self):
        prb = self.flow_inputs(self.approval(tool="prb_recover"))                  # has a status read step too
        inquiry = self.approval()
        printed = op.run_synthetic_preflight(self.flow_inputs(inquiry)).job_plan
        doc = json.loads(inquiry)
        doc.update(kind="apply", approval_id="app-0000000000000001", plan={"7": printed},
                   based_on={"approval_id": doc["approval_id"], "sha256": hashlib.sha256(inquiry).hexdigest()})
        apply = json.dumps(doc).encode()
        apply_inputs = self.flow_inputs(apply, inquiry=inquiry, inquiry_signature=self.sign(inquiry, "approval"))
        dry_only = self.flow_inputs(self.approval(steps=[{"command": "dry_run", "access": "read", "role": "ops_read",
                                                          "profile": self.read_profile()}]))
        other = tcli.request(personal=(3,))
        cases = {
            "prb_recover status": (prb, "approval_tool_not_srs_migrate"),
            "srs_migrate apply shape": (apply_inputs, "approval_kind_not_inquiry"),
            "dry_run approval for status": (dry_only, "preflight_command_not_approved"),
            "other cards approved": (self.flow_inputs(self.approval(job={"key": self.req.run_key,
                                                                         "inputs": cli.job_inputs(other)})),
                                     "preflight_job_input_mismatch"),
            "bad signature": (self.flow_inputs(approval_signature=b"bad"), "preflight_approval_signature_invalid"),
            "inputs differ from request": (self.flow_inputs(job_inputs=cli.job_inputs(other)), "request_mismatch"),
        }
        for label, (inputs, code) in cases.items():
            with self.subTest(case=label):
                op_ok = label in ("prb_recover status", "srs_migrate apply shape")
                if op_ok:
                    op.run_synthetic_preflight(inputs)                     # valid signed approvals on their own
                out, status, calls = self.run_status(inputs)
                self.assertEqual((out["code"], status, calls), (code, 4, []))
        self.assertEqual(self.driver.calls, [])

    def test_wrong_tool_imports_no_app_code(self):
        code = (f"import sys; sys.path[:0] = [{str(TESTS_DIR)!r}, {str(BACKEND / 'scripts')!r}]\n"
                "import test_srs_migrate_cli as t\n"
                "t.FlowBase.setUpClass()\n"
                "case = t.FakeFlow('test_ok_binds_candidates_file_and_fingerprints'); case.setUp()\n"
                "import srs_migrate as cli\n"
                "step = {'command': 'status', 'access': 'read', 'role': 'ops_read', 'profile': case.read_profile()}\n"
                "approval = case.approval(tool='prb_recover', steps=[step])\n"
                "inputs = case.flow_inputs(approval, command='status')\n"
                "out, status = cli.run_status(case.req, inputs=inputs, expected=t.to.READ_EXPECTED, driver=case.driver)\n"
                "app = any(m == 'app' or m.startswith('app.') for m in sys.modules)\n"
                "print('RESULT', out['code'], status, app, len(case.driver.calls))\n"
                "case.doCleanups(); t.FlowBase.tearDownClass()\n")
        done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=180,
                              env={k: v for k, v in os.environ.items() if k != "PYTHONPATH"})
        self.assertIn("RESULT approval_tool_not_srs_migrate 4 False 0", done.stdout, done.stderr[-800:])


class CommandLine(unittest.TestCase):
    def test_status_command_line_never_connects_or_imports_the_app(self):
        code = (f"import sys; sys.path[:0] = [{str(BACKEND / 'scripts')!r}]\n"
                "import psycopg\n"
                "def forbidden(*a, **k): raise AssertionError('connect')\n"
                "psycopg.connect = forbidden\n"
                "import srs_migrate\n"
                "rc = srs_migrate.main(['status', '--account', '7', '--run-key', 'k', '--personal-id', '2'])\n"
                "print('RC', rc, any(m == 'app' or m.startswith('app.') for m in sys.modules))\n")
        done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120,
                              env={k: v for k, v in os.environ.items() if k != "PYTHONPATH"})
        self.assertIn("RC 4 False", done.stdout, done.stderr[-500:])
        self.assertIn('"connection_not_available"', done.stdout)


if __name__ == "__main__":
    unittest.main()

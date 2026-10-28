"""OPS_MIGRATION_RESUME_PLAN 14 (RS3 provider path): CLI `resume` through the WHOLE existing provider path.

REAL (run as is): run_resume, _timed_connector, srs_migrate._product_connector -> ProductConnector, the
adapter (provide_with_adapter, CopyingFactory), the provider (pre-check on every call, connect, observation
start, CatalogObserver, judge_observation, the post-connect authorize_command, rollback and close),
approvals and signatures (test-only temporary keys), the prior chain, the backup evidence checks, the plan
file, read_status / judge_status / progress_values and the product's own rollback_window / to_candidates.
Counting wrappers call the original functions and only record.

FAKE: the driver function (ta.FakeDriver) and the connection / cursor server responses (Server below: the
observation catalog built from the CONTRACT privilege table, and the two status SELECT answers).

STUB (business body only): the product `migration.apply_plan`. A fake connection cannot run the product's
apply SQL, so the stub opens the injected `connect` once per product connection (first, each remaining card,
finish), enters it, runs one statement and leaves it, and records its arguments. The product's own
existing-run / expected-progress behaviour is covered by the 19 real SQLite tests
(test_srs_migrate_resume_sqlite.py) and test_srs_migration_existing_run.py, not here.

No PostgreSQL, Neon or backend/vocab.db; nothing here is PostgreSQL transaction or privilege evidence.

Run directly:      python tests/test_srs_migrate_resume_provider.py
"""

from __future__ import annotations

import os

os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["PYTHON_DOTENV_DISABLED"] = "1"

import hashlib  # noqa: E402
import json  # noqa: E402
import sys  # noqa: E402
import unittest  # noqa: E402
from datetime import datetime, timedelta, timezone  # noqa: E402
from pathlib import Path  # noqa: E402
from unittest import mock  # noqa: E402

TESTS_DIR = Path(__file__).resolve().parent
BACKEND = TESTS_DIR.parent
sys.path.insert(0, str(BACKEND / "scripts"))
sys.path.insert(0, str(TESTS_DIR))
if str(BACKEND) not in sys.path:      # path only, from this file's location
    sys.path.append(str(BACKEND))

import psycopg  # noqa: E402
from psycopg import errors as pg_errors  # noqa: E402
from psycopg.pq import TransactionStatus  # noqa: E402

import _ops_approval as oa  # noqa: E402
import _ops_observer as ob  # noqa: E402
import _ops_plan_file as pfile  # noqa: E402
import _ops_preflight as op  # noqa: E402
import _ops_product_connect as pc  # noqa: E402
import _ops_provider as pv  # noqa: E402
import srs_migrate as cli  # noqa: E402
import test_ops_adapter as ta  # noqa: E402  (module only)
import test_ops_preflight as pf  # noqa: E402  (module only)
import test_ops_product_connect as tpc  # noqa: E402  (module only)
import test_srs_migrate_apply_flow as flow  # noqa: E402  (module only)

from app.srs import migration  # noqa: E402

T0 = flow.T0
RUN_KEY = flow.RUN_KEY
EXPIRY = datetime(2026, 10, 21, 12, 40, 0, tzinfo=timezone.utc)      # An's short validity ends here
RUN_QUERY = "SELECT id, mode, status, scope_json, config_version, summary_json, started_at, finished_at"
SNAPSHOT_QUERY = "SELECT id, user_id, card_kind, card_ref FROM srs_migration_snapshots"

# privileges taken FROM THE CONTRACT TABLE for the refusal cases (never from an observation)
READ_MISSING = ("table", "public", "srs_migration_runs", "", "SELECT")
WRITE_MISSING = ("table", "public", "srs_migration_runs", "status", "UPDATE")
READ_EXCESS = ("table", "public", "srs_migration_runs", "", "INSERT")
WRITE_EXCESS = ("table", "public", "users", "", "UPDATE")
CODES = {"wrong role": "observed_role_mismatch", "missing": "observed_privileges_missing",
         "excess": "observed_privileges_excess"}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class Rows:
    """FAKE cursor result of one business SELECT."""

    def __init__(self, rows):
        self.rows, self.rowcount, self.description = rows, len(rows), None

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return list(self.rows)


class Server(tpc.BizConn):
    """FAKE server: the provider-test observation connection plus fixed answers to the two status SELECTs.
    SET TRANSACTION is refused only after a statement that takes a snapshot (as the server does); the
    observation statements and SET TRANSACTION READ ONLY themselves take none."""

    def __init__(self, cat, *, run=None, snapshots=()):
        super().__init__(cat)
        self.run, self.snapshots, self.snapshot_taken = run, list(snapshots), False

    def execute(self, sql, params=None):
        if isinstance(sql, str) and not self.closed:
            if sql.startswith("SET TRANSACTION") or sql.startswith("SET LOCAL"):
                if self.snapshot_taken:
                    raise pg_errors.ActiveSqlTransaction("SET TRANSACTION must be first")
                self.log.append(sql)
                self.status = TransactionStatus.INTRANS
                return None
            for prefix, rows in ((RUN_QUERY, [self.run] if self.run else []), (SNAPSHOT_QUERY, self.snapshots)):
                if sql.startswith(prefix):
                    self.params.append(params)
                    self.log.append(sql)
                    self.snapshot_taken, self.status = True, TransactionStatus.INTRANS
                    return Rows([dict(r) for r in rows])
        self.snapshot_taken = True
        return super().execute(sql, params)

    def rollback(self):
        super().rollback()
        self.snapshot_taken = False

    def commit(self):
        super().commit()
        self.snapshot_taken = False

    def business(self) -> list:
        """Statements after the provider's observation ROLLBACK (= after the hand-over)."""
        return self.log[self.log.index("ROLLBACK") + 1:] if "ROLLBACK" in self.log else []


class Trace:
    """Counting wrappers around the REAL functions; each calls the original and only records."""

    def __init__(self, case):
        self.case = case
        self.preflight, self.verified, self.chain, self.observed, self.judged = [], [], [], [], []
        self.post_connect, self.prepared, self.status_reads = [], [], 0

    def patches(self):
        real_pre, real_sig, real_chain = op.run_synthetic_preflight, oa.verify_signed, oa.check_apply_chain
        real_obs, real_judge, real_auth = ob.CatalogObserver.observe, pv.judge_observation, oa.authorize_command
        real_prepare, real_read = pc.ProductConnector._prepare, cli.read_status
        trace = self

        def preflight(inputs):
            trace.preflight.append((inputs.command, inputs.now))
            return real_pre(inputs)

        def verify_signed(data, signature, **kwargs):
            trace.verified.append((len(trace.preflight), sha(data)))
            return real_sig(data, signature, **kwargs)

        def check_apply_chain(current, chain):
            trace.chain.append((len(trace.preflight), current.sha256, tuple(a.sha256 for a, _ in chain)))
            return real_chain(current, chain)

        def observe(self_, connection):
            trace.observed.append(connection)
            return real_obs(self_, connection)

        def judge(observation, **kwargs):
            trace.judged.append((observation.current_user, kwargs["access"]))
            return real_judge(observation, **kwargs)

        def authorize(approval, **kwargs):
            if sys._getframe(1).f_code is pv.provide_synthetic_connection.__code__:      # the post-connect one
                trace.post_connect.append(dict(kwargs, approval=approval))
            return real_auth(approval, **kwargs)

        def prepare(self_, raw, summary, read_only):
            trace.prepared.append((raw, read_only))
            return real_prepare(self_, raw, summary, read_only)

        def read_status(connect, request, migration_):
            trace.status_reads += 1
            return real_read(connect, request, migration_)

        return [mock.patch.object(op, "run_synthetic_preflight", preflight),
                mock.patch.object(oa, "verify_signed", verify_signed),
                mock.patch.object(oa, "check_apply_chain", check_apply_chain),
                mock.patch.object(ob.CatalogObserver, "observe", observe),
                mock.patch.object(pv, "judge_observation", judge),
                mock.patch.object(oa, "authorize_command", authorize),
                mock.patch.object(pc.ProductConnector, "_prepare", prepare),
                mock.patch.object(cli, "read_status", read_status)]


class ProviderBase(flow.FlowBase):
    """FlowBase (contract-built profiles, real approvals) plus a v3 A0 and the resume approval An."""

    def setUp(self):
        super().setUp()
        self.inq, self.a0 = self.approvals(
            self.req, self.plan, 2, self.read_profile, self.write_profile,
            apply_changes={"format_version": 3, "backup_evidence": {"sha256": sha(self.read(self.ev))}})
        self.ev2 = self.evidence(7, name="evidence2", evidence_id="bkp-0000000000000002")
        self.planned = pfile.to_candidates(self.plan)
        self.apply_calls: list = []
        self.state = {"now": T0}

    @staticmethod
    def read(path) -> bytes:
        with open(path, "rb") as handle:
            return handle.read()

    def resume_inputs(self, batch=2, approval_changes=None):
        doc = json.loads(self.a0)
        doc.pop("backup_evidence", None)
        doc.update(approval_id="app-0000000000000002", format_version=3,
                   supersedes={"approval_id": json.loads(self.a0)["approval_id"], "sha256": sha(self.a0)},
                   steps=[{"command": "status", "access": "read", "role": "ops_read", "profile": self.read_profile},
                          {"command": "resume", "access": "write", "role": "ops_write_prb",
                           "profile": self.write_profile, "args": {"batch_size": str(batch)}}])
        doc.update(approval_changes or {})
        self.an = json.dumps(doc).encode()
        link = op.ChainLink(self.a0, self.sign(self.a0, "approval"), self.inq, self.sign(self.inq, "approval"))
        common = dict(inquiry=self.inq, inquiry_signature=self.sign(self.inq, "approval"), account_id=7,
                      job_key=RUN_KEY, job_inputs=cli.job_inputs(self.req),
                      product_fingerprint=self.plan.product_fingerprint, artifact_sha256=self.plan.artifact_sha256,
                      prior_chain=(link,))
        write = self.inputs(self.an, command="resume", args={"batch_size": str(batch)},
                            secret_dsn=self.dsn(role="ops_write_prb"),
                            connection=op.ConnectionObservation(profile=self.write_profile, read_only=False), **common)
        read = self.inputs(self.an, command="status", args={}, secret_dsn=self.dsn(role="ops_read"),
                           connection=op.ConnectionObservation(profile=self.read_profile, read_only=True), **common)
        return write, read

    # -- the synthetic server state: one incomplete run with card 1 applied (cursor 1 of 2) -----------------
    def run_row(self):
        started = (migration.now_utc() - timedelta(hours=1)).isoformat()      # inside the real 30-day window
        summary = json.dumps({"cursor": 1, "results": [{"kind": "personal", "ref_id": 1, "result": "applied"}]})
        return {"id": 41, "mode": "apply", "status": "started", "scope_json": migration._plan_json(self.planned),
                "config_version": self.config_version(), "summary_json": summary, "started_at": started,
                "finished_at": None}

    def snapshots(self):
        return [{"id": 51, "user_id": 7, "card_kind": "personal", "card_ref": 1}]

    def status_conn(self, **kwargs):
        return Server(flow.contract_catalog("read", **kwargs), run=self.run_row(), snapshots=self.snapshots())

    def write_conn(self, **kwargs):
        return Server(flow.contract_catalog("write", **kwargs))

    def apply_stub(self, on_entered=None):
        def apply_plan(plan, run_key, *, approved, batch_size, connect, new_run_only, existing_run_only,
                       expected_progress):
            self.apply_calls.append(dict(run_key=run_key, approved=approved, batch_size=batch_size,
                                         new_run_only=new_run_only, existing_run_only=existing_run_only,
                                         expected_progress=expected_progress))
            for index in range(1 + (len(plan) - 1) + 1):       # first, each remaining card, finish
                with connect(read_only=False) as connection:
                    connection.execute("SELECT 1")
                if on_entered:
                    on_entered(index)
            return [{"kind": c.key.kind, "ref_id": c.key.ref_id,
                     "result": "already_applied" if i == 0 else "applied"} for i, c in enumerate(plan)]
        return apply_plan

    def resume_run(self, conns, *, inputs=None, driver=None, apply_stub=None):
        write, read = inputs or self.resume_inputs()
        self.conns = conns
        self.driver = driver or ta.FakeDriver(*conns)
        self.trace = Trace(self)
        patches = self.trace.patches() + [
            mock.patch.object(migration, "apply_plan", apply_stub or self.apply_stub()),
            mock.patch.dict(os.environ)]
        for patch in patches:
            patch.start()
        try:
            return cli.run_resume(self.req, batch_size=2, write_inputs=write, read_inputs=read, scope=flow.SCOPE,
                                  driver=self.driver, plan_path=self.path("plan.json"),
                                  initial_evidence_path=self.ev, initial_evidence_signature_path=self.ev_sig,
                                  evidence_path=self.ev2[0], evidence_signature_path=self.ev2[1],
                                  clock=lambda: self.state["now"])
        finally:
            for patch in reversed(patches):
                patch.stop()

    def assert_clean(self, out):
        text = json.dumps(out)
        for secret in (pf.SECRET, "postgresql://", "sslrootcert", "Driver-Text"):
            self.assertNotIn(secret, text)

    def assert_refused_conn(self, conn):
        """Observed, then rolled back and closed; never handed to the product."""
        self.assertTrue(conn.queries)                                  # the observer read the catalog
        self.assertEqual(conn.log[-1], "ROLLBACK")
        self.assertTrue(conn.closed)
        self.assertEqual(conn.business(), [])
        self.assertNotIn(conn, [raw for raw, _ in self.trace.prepared])


class NormalPath(ProviderBase):
    def test_every_connection_is_observed_and_rejudged_before_hand_over(self):
        conns = [self.status_conn()] + [self.write_conn() for _ in range(3)]
        out, code = self.resume_run(conns)
        self.assertEqual((out["status"], out["phase"], code), ("ok", "completed", 0), out)
        self.assertEqual(out["results"], {"already_applied": 1, "applied": 1})
        self.assertEqual([d["user"] for d in self.driver.calls], ["ops_read"] + ["ops_write_prb"] * 3)
        t = self.trace
        # every created connection: observed, judged with the contract profile, re-judged, then handed over
        self.assertEqual(t.observed, conns)
        self.assertEqual(t.judged, [("ops_read", "read")] + [("ops_write_prb", "write")] * 3)
        self.assertEqual([raw for raw, _ in t.prepared], conns)
        self.assertEqual([r for _, r in t.prepared], [True, False, False, False])
        self.assertEqual([c["command"] for c in t.post_connect], ["status"] + ["resume"] * 3)
        for conn in conns:
            self.assertEqual(conn.log[:3], list(pv.OBSERVATION_START))         # observation before anything
            self.assertTrue(conn.closed)
        self.assertEqual(conns[0].business()[:2], ["SET TRANSACTION READ ONLY",
                                                   "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"])
        self.assertEqual(conns[0].business()[2:4], [RUN_QUERY + " FROM srs_migration_runs WHERE run_key = %s",
                                                    SNAPSHOT_QUERY + " WHERE run_id = %s"])
        for conn in conns[1:]:
            self.assertEqual(conn.business(), ["SELECT 1", "COMMIT"])
        self.assertEqual(t.status_reads, 1)
        call, = self.apply_calls                                                 # exactly once
        self.assertEqual((call["new_run_only"], call["existing_run_only"], call["batch_size"]), (False, True, 2))
        self.assertEqual(call["expected_progress"], cli.progress_values(self.run_row() | {
            "started_at": call["expected_progress"]["started_at"]}, self.snapshots()))
        self.assert_clean(out)

    def test_profiles_come_from_the_contract_constants(self):
        read_expected, write_expected = cli.contract_profiles(flow.SCOPE, flow.to.T.database)
        self.assertEqual(self.read_profile, pv.expected_profile_fingerprint(read_expected, role="ops_read",
                                                                            access="read"))
        self.assertEqual(self.write_profile, pv.expected_profile_fingerprint(write_expected, role="ops_write_prb",
                                                                             access="write"))
        self.assertNotIn(("sequence", "public", "srs_migration_runs_id_seq", "", "USAGE"), cli.WRITE_PRIVILEGES)
        steps = {s["command"]: s for s in json.loads(self.resume_inputs()[0].approval)["steps"]}
        self.assertEqual((steps["status"]["profile"], steps["status"]["role"], steps["status"]["access"]),
                         (self.read_profile, "ops_read", "read"))
        self.assertEqual((steps["resume"]["profile"], steps["resume"]["role"], steps["resume"]["args"]),
                         (self.write_profile, "ops_write_prb", {"batch_size": "2"}))
        self.assertEqual(steps["resume"]["access"], "write")
        self.assertEqual(oa.TOOLS["srs_migrate"], {"dry_run": "read", "status": "read", "apply": "write",
                                                   "resume": "write"})


class PerConnectionBinding(ProviderBase):
    def test_fresh_time_precheck_chain_and_rejudgement_per_connection(self):
        ticks = iter(T0 + timedelta(seconds=i) for i in range(1, 100))
        self.state = type("Ticking", (), {"__getitem__": lambda _s, _k: next(ticks)})()
        conns = [self.status_conn()] + [self.write_conn() for _ in range(3)]
        out, code = self.resume_run(conns)
        self.assertEqual(code, 0, out)
        t = self.trace
        initial, provider = t.preflight[:2], t.preflight[2:]
        self.assertEqual([c for c, _ in initial], ["resume", "status"])
        self.assertEqual([c for c, _ in provider], ["status"] + ["resume"] * 3)     # one pre-check per connection
        times = [n for _, n in provider]
        self.assertEqual(len(set(times)), len(times))
        self.assertTrue(all(n > initial[0][1] for n in times))
        self.assertEqual([c["now"] for c in t.post_connect], times)                 # re-judged at that same time
        # chain signatures verified again inside every pre-check: An, I0, A0, I0 (in order)
        by_check = {}
        for index, digest in t.verified:
            by_check.setdefault(index, []).append(digest)
        self.assertEqual(sorted(by_check), list(range(1, len(t.preflight) + 1)))
        for digests in by_check.values():
            self.assertEqual(digests, [sha(self.an), sha(self.inq), sha(self.a0), sha(self.inq)])
        self.assertEqual(len(t.chain), len(t.preflight))
        self.assertTrue(all(c[1:] == (sha(self.an), (sha(self.a0),)) for c in t.chain))
        # the post-connect re-judgement gets the current approval, the prior and the artifact
        for call in t.post_connect:
            self.assertEqual(call["approval"].sha256, sha(self.an))
            self.assertEqual(call["prior"].sha256, sha(self.a0))
            self.assertEqual(call["inquiry"].sha256, sha(self.inq))
            self.assertEqual(call["artifact_sha256"], self.plan.artifact_sha256)
            self.assertIn(call["observed"].role, ("ops_read", "ops_write_prb"))

    def test_expiry_between_write_connections_refuses_the_later_one(self):
        def expire_after_first(index):
            if index == 0:
                self.state["now"] = EXPIRY
        conns = [self.status_conn()] + [self.write_conn() for _ in range(3)]
        out, code = self.resume_run(conns, inputs=self.resume_inputs(approval_changes={"valid_until": "2026-10-21T12:40:00Z"}),
                             apply_stub=self.apply_stub(expire_after_first))
        self.assertEqual((out["status"], out["code"], out["phase"], code), ("failed", "preflight_approval_expired",
                                                                         "after_start", 1), out)
        self.assertEqual((out["uncertain"], out["next"], out["confirmed"]), (True, "status_required", "unknown"))
        self.assertEqual(len(self.driver.calls), 2)                    # refused before the driver: no connection
        self.assertEqual(len(self.trace.prepared), 2)
        self.assertEqual(self.trace.preflight[-1], ("resume", EXPIRY))
        self.assertEqual(len(self.apply_calls), 1)                     # no retry, no second call
        self.assertFalse(conns[2].log)                                 # never created
        self.assert_clean(out)

    def test_observation_change_between_write_connections_refuses_the_later_one(self):
        cases = {"wrong role": (dict(user="ops_read"), "observed_role_mismatch"),
                 "missing": (dict(missing=[WRITE_MISSING]), "observed_privileges_missing"),
                 "excess": (dict(extra=[WRITE_EXCESS]), "observed_privileges_excess")}
        for label, (kwargs, wanted) in cases.items():
            with self.subTest(case=label):
                self.apply_calls = []
                conns = [self.status_conn(), self.write_conn(), self.write_conn(**kwargs), self.write_conn()]
                out, code = self.resume_run(conns)
                self.assertEqual((out["status"], out["code"], out["phase"], code), ("failed", wanted, "after_start", 1))
                self.assertEqual((out["uncertain"], out["next"], out["confirmed"]), (True, "status_required", "unknown"))
                self.assertEqual(len(self.driver.calls), 3)            # no retry, no fourth connection
                self.assert_refused_conn(conns[2])
                self.assertEqual(self.trace.observed, conns[:3])
                self.assertEqual([raw for raw, _ in self.trace.prepared], conns[:2])
                self.assertEqual(conns[1].business(), ["SELECT 1", "COMMIT"])    # the first one did commit
                self.assertFalse(conns[3].log)
                self.assertEqual(len(self.apply_calls), 1)
                self.assert_clean(out)


class Refusals(ProviderBase):
    def check_status_refusal(self, conn):
        out, code = self.resume_run([conn, self.write_conn()])
        self.assertEqual((out["status"], out["phase"], out["changes"], code), ("refused", "before_first_write",
                                                                               "none", 4), out)
        self.assert_refused_conn(conn)
        self.assertEqual((len(self.driver.calls), self.trace.status_reads, self.apply_calls), (1, 1, []))
        self.assertEqual(self.trace.prepared, [])
        self.assert_clean(out)
        return out

    def check_first_write_refusal(self, conn):
        status = self.status_conn()
        out, code = self.resume_run([status, conn, self.write_conn()])
        self.assertEqual((out["status"], out["phase"], out["changes"], code), ("refused", "before_first_write",
                                                                               "none", 4), out)
        self.assert_refused_conn(conn)
        self.assertEqual(len(self.driver.calls), 2)                   # no third connection, no retry
        self.assertEqual([raw for raw, _ in self.trace.prepared], [status])
        self.assertEqual(len(self.apply_calls), 1)                     # the business call got no connection
        self.assert_clean(out)
        return out

    def test_status_connection_refusals(self):
        cases = {"wrong role": dict(user="ops_write_prb"), "missing": dict(missing=[READ_MISSING]),
                 "excess": dict(extra=[READ_EXCESS])}
        self.assertIn(READ_MISSING, cli.READ_PRIVILEGES)
        self.assertNotIn(READ_EXCESS, cli.READ_PRIVILEGES)
        codes = {}
        for label, kwargs in cases.items():
            with self.subTest(case=label):
                self.apply_calls = []
                codes[label] = self.check_status_refusal(self.status_conn(**kwargs))["code"]
        self.assertEqual(codes, CODES)

    def test_first_write_connection_refusals(self):
        cases = {"wrong role": dict(user="ops_read"), "missing": dict(missing=[WRITE_MISSING]),
                 "excess": dict(extra=[WRITE_EXCESS])}
        self.assertIn(WRITE_MISSING, cli.WRITE_PRIVILEGES)
        self.assertNotIn(WRITE_EXCESS, cli.WRITE_PRIVILEGES)
        codes = {}
        for label, kwargs in cases.items():
            with self.subTest(case=label):
                self.apply_calls = []
                codes[label] = self.check_first_write_refusal(self.write_conn(**kwargs))["code"]
        self.assertEqual(codes, CODES)

    def test_expired_before_the_status_connection_creates_nothing(self):
        clock = iter([T0, T0, EXPIRY])                                 # pre-check, evidence, status connection
        self.state = type("Seq", (), {"__getitem__": lambda _s, _k: next(clock)})()
        status = self.status_conn()
        out, code = self.resume_run([status], inputs=self.resume_inputs(approval_changes={"valid_until": "2026-10-21T12:40:00Z"}))
        self.assertEqual((out["code"], out["phase"], code), ("preflight_approval_expired", "before_first_write", 4))
        self.assertEqual((self.driver.calls, self.trace.observed, self.trace.prepared, self.apply_calls),
                         ([], [], [], []))
        self.assertEqual(self.trace.status_reads, 1)                    # the business call got no connection
        self.assertFalse(status.log)

    def test_driver_text_never_reaches_the_output(self):
        class Driver(ta.FakeDriver):
            def __call__(self, **kwargs):
                if self.calls:
                    self.calls.append(dict(kwargs))
                    raise psycopg.OperationalError(f"Driver-Text password={pf.SECRET} at db.synthetic.test")
                return super().__call__(**kwargs)
        status = self.status_conn()
        out, code = self.resume_run([status], driver=Driver(status))
        # the existing rule: a driver failure is "failed" (1) before any hand-over, never "refused"
        self.assertEqual((out["status"], out["code"], out["phase"], out["changes"], code),
                         ("failed", "connect_failed", "before_first_write", "none", 1), out)
        self.assertEqual((len(self.driver.calls), len(self.trace.prepared), len(self.apply_calls)), (2, 1, 1))
        self.assert_clean(out)

if __name__ == "__main__":
    unittest.main()

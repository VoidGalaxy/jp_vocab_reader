"""Fake-only checks for the subscribed-card resume real-PG runner (tests/_ops_resume_lexeme_real.py, plan L-1).
No database, cluster, key or certificate: connect entry points, `subprocess`, key creation and process facts are
blocked; only temporary synthetic files are written. The runner's real prepare / check-lexeme / cleanup never run
against anything, and nothing here is PostgreSQL evidence.

Run directly:      python tests/test_ops_resume_lexeme_real_guard.py
Or via discovery:   python -m unittest discover -s tests -p test_ops_resume_lexeme_real_guard.py
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

TESTS_DIR = Path(__file__).resolve().parent
BACKEND = TESTS_DIR.parent
sys.path.insert(0, str(BACKEND / "scripts"))
sys.path.insert(0, str(TESTS_DIR))

import psycopg  # noqa: E402
from psycopg.pq import TransactionStatus  # noqa: E402

import _ops_pg62 as g  # noqa: E402
import _ops_real_layout as lay  # noqa: E402
import _ops_resume_lexeme_real as lx  # noqa: E402
import srs_migrate as cli  # noqa: E402
import test_srs_migrate_apply_flow as flow  # noqa: E402  (module only: the plan fixture's product hash)

T = g.PG67_RESUME_LEXEME
PID = 6767
# Fixed from the plan (2절 / 4절 / 7-3 / 7-4), never read back from the code under test.
PLAN_DBS = ("l1", "l2", "l3", "l6", "l7", "l8", "l9")
PLAN_CHECKS = ("l1", "l2", "l3", "l4", "l5", "l6", "l7", "l8", "l9")
NINE = ("run_id", "status", "mode", "config_version", "started_at", "finished_at", "scope_sha256", "summary_sha256",
        "snapshots_sha256")


def forbidden(*_, **__):
    raise AssertionError("an external entry point was called")


class Blocked(unittest.TestCase):
    def setUp(self):
        for patch in (mock.patch.object(psycopg, "connect", forbidden), mock.patch.object(subprocess, "Popen", forbidden),
                      mock.patch.object(subprocess, "run", forbidden), mock.patch.object(lx.sigtests, "Keys", forbidden),
                      mock.patch.object(g, "listener_pids", forbidden), mock.patch.object(g, "admin_connect", forbidden),
                      mock.patch.object(g, "postmaster_pid", forbidden),
                      mock.patch.object(lay.real, "make_tls", forbidden), mock.patch.object(lay.base, "run", forbidden),
                      mock.patch.object(g, "server_is_ours", lambda pid, target=None: pid == PID and target is T),
                      mock.patch.dict(os.environ, {k: v for k, v in os.environ.items()
                                                   if not k.upper().startswith("PG")}, clear=True)):
            patch.start()
            self.addCleanup(patch.stop)
        self.folder = Path(tempfile.mkdtemp(prefix="ops_resume_lexeme_test_"))
        self.addCleanup(shutil.rmtree, self.folder, True)

    def record(self, **changes):
        run = self.folder / "20261029T020000"
        run.mkdir(exist_ok=True)
        target = {"run_id": run.name, "host": g.HOST, "port": T.port, "data": str(T.data),
                  "postgres_exe": str(g.POSTGRES_EXE), "postmaster_pid": PID, "server_version_num": "180006",
                  "system_identifier": "1", "provider_roles": ["jpvl_read", "jpvl_write"], "admin_role": "jpvl_admin",
                  "roles": {"jpvl_read": 101, "jpvl_write": 102},
                  "databases": {db: {"oid": 500 + i, "identity_value": f"pg67-{i}-n",
                                     "objects": {t: 900 + j for j, t in enumerate(sorted(lay.OID_TABLES))}}
                                for i, db in enumerate(lx.LAYOUT.business_databases)}}
        target.update(changes)
        data = json.dumps(target, sort_keys=True).encode()
        (run / "target.json").write_bytes(data)
        rec = g.Record(run)
        rec.event("server_started", pid=PID)
        rec.event("target_written", sha256=hashlib.sha256(data).hexdigest())
        return rec, target


# --- 1. target, matrix, contract ----------------------------------------------------------------------------

class Target(Blocked):
    def test_closed_layout_and_plan_values(self):
        self.assertIs(lx.LAYOUT, lay.PG67)
        self.assertEqual(tuple(lx.CHECK_DB), PLAN_DBS)
        self.assertEqual((T.root, T.port, T.admin, T.provider_roles),
                         (Path("C:/JV_Tools/pg67"), 55512, "jpvl_admin", ("jpvl_read", "jpvl_write")))
        self.assertEqual(lx.PLANNED, PLAN_CHECKS)
        self.assertEqual(tuple(n for n, _ in lx.CHECKS), PLAN_CHECKS)
        self.assertEqual(set(lx.INITIAL), set(PLAN_DBS))
        self.assertEqual({k: v[:2] for k, v in lx.INITIAL.items()},
                         {"l1": (("l1", "l2"), "started"), "l2": (("l1", "l2"), "failed"),
                          "l3": (("l1", "l2", "p1"), "started"), "l6": (("l1", "l2"), "started"),
                          "l7": (("l1", "l2"), "started"), "l8": (("l1", "l2", "p1"), "started"),
                          "l9": (("l1", "l2"), "started")})
        self.assertIsNone(lx.LQ3_CHANGES_APPROVED)                       # L-2 not approved

    def test_business_matrix_and_admin_limits(self):
        ok = {"host": g.HOST, "port": "55512", "dbname": lx.CHECK_DB["l1"], "user": "jpvl_write", "sslmode": "verify-full"}
        lx.business_check(ok)
        for key, value in (("port", "55502"), ("dbname", lx.TEMPLATE), ("dbname", "jp_vocab_test_resume_r1"),
                           ("user", "jpvl_admin"), ("user", "jpvr_write"), ("sslmode", "require")):
            with self.subTest(key=key, value=value), self.assertRaises(g.Pg62Refused):
                lx.business_check(dict(ok, **{key: value}))
        seen = []
        with mock.patch.object(g, "admin_connect", lambda db, **k: seen.append(k["target"]) or "conn"):
            self.assertEqual(lx.admin(lx.CHECK_DB["l9"], PID), "conn")
            for db in ("jp_vocab_test_resume_r1", "jp_vocab_test_apply_a1", "template1"):
                with self.subTest(db=db), self.assertRaises(g.Pg62Refused):
                    lx.admin(db, PID)
        self.assertTrue(all(t is T for t in seen))

    def test_record_binding(self):
        rec, _ = self.record()
        self.assertEqual(lx.require_target_bound(rec, (rec.folder / "target.json").read_bytes())["port"], 55512)
        shutil.rmtree(rec.folder)
        rec, _ = self.record(port=55502)
        with self.assertRaises(g.Pg62Refused) as caught:
            lx.require_target_bound(rec, (rec.folder / "target.json").read_bytes())
        self.assertEqual(caught.exception.code, "pg67_target_record_mismatch")

    def test_contract_grants_and_closed_changes(self):
        grants = [s.as_string(None) for s in lx.contract_grants(lx.CHECK_DB["l1"])]
        self.assertFalse([s for s in grants if "SEQUENCE" in s])
        self.assertTrue(all(s.endswith('TO "jpvl_read"') or s.endswith('TO "jpvl_write"') for s in grants))
        self.assertIn('GRANT SELECT ON "public"."user_deck_subscriptions" TO "jpvl_read"', grants)
        self.assertIn('GRANT UPDATE ("srs_state") ON "public"."user_word_progress" TO "jpvl_write"', grants)
        self.assertEqual(set(lx.LAYOUT.variants), {"l8_lexeme_card_column", "l9_read_subscriptions"})
        self.assertEqual(lx.LAYOUT.variant_databases, {"l8_lexeme_card_column": ("l8",),
                                                      "l9_read_subscriptions": ("l9",)})
        self.assertEqual(set(lx.ADMIN_DATA), {"subscription_deactivated", "deck_word_removed"})

    def test_admin_and_privilege_changes_locked_until_l2(self):
        h = SimpleNamespace(rec=SimpleNamespace(event=forbidden))
        with self.assertRaises(lay.CheckFailed):
            lx.Harness.variant(h, "l8", "l8_lexeme_card_column", "apply")
        with self.assertRaises(lay.CheckFailed):
            lx.Harness.admin_data_change(h, "l6", "subscription_deactivated", None)
        with mock.patch.object(g, "single_run", forbidden), contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(lx.main(["check-lexeme"]), 1)
        self.assertIn("LQ3", out.getvalue())

    def test_admin_changes_touch_only_account_a_and_l2(self):
        ids = {"a": {"user_id": 2, "personal": {"p1": 11, "p2": 12, "p3": 13, "p4": 14, "p5": 15}, "lexeme": [31, 32]}}
        h = SimpleNamespace(target={"synthetic": ids})
        case = SimpleNamespace(request=SimpleNamespace(account_id=2))
        (sub_sql, sub_params), = lx.ADMIN_DATA["subscription_deactivated"](h, case)
        (word_sql, word_params), = lx.ADMIN_DATA["deck_word_removed"](h, case)
        self.assertEqual((sub_params, word_params), ((2, 32), (32, 2)))           # account a, lexeme l2 only
        self.assertTrue(sub_sql.startswith("UPDATE user_deck_subscriptions SET is_active = FALSE WHERE user_id = %s"))
        self.assertTrue(word_sql.startswith("DELETE FROM shared_deck_words WHERE lexeme_id = %s"))


# --- 1b. the REAL Harness.case path (fakes only for connect / provider / product body) ------------------

class LexemeCasePath(unittest.TestCase):
    """(Derived from test_ops_resume_real_guard.CasePath for the PG67 runner, mixed card set l1 / l2 / p1.)
    The REAL `Harness.case` (Harness init and target binding, deploy folder, manifest, I0, the CLI `run_dry_run`
    with its real pre-check and signatures, the real counted connector, `Harness.driver` with the real business
    matrix / liveness / post-connect checks, the plan file, `run_synthetic_preflight`, E0 / E1, A0).
    REPLACED: the guard's real connect (`g.Guard`), the connection and cursor (fake), the provider path behind the
    CLI product connector (`ORIGINAL_CONNECTOR`: a fake that calls the given driver once, as the adapter does, and
    hands the raw connection over) and the product dry_run body (a stub that enters the handed connection once and
    returns real plan candidates). The certificate file is fake bytes. Signatures use the existing synthetic
    test-only temporary OS ssh-keygen keys; nothing else may start a process."""

    @classmethod
    def setUpClass(cls):
        if not os.path.isfile(lx.op.osig.SSH_KEYGEN):
            raise unittest.SkipTest("OS OpenSSH ssh-keygen not present")
        cls.keys = lx.sigtests.Keys()

    @classmethod
    def tearDownClass(cls):
        cls.keys.close()

    def setUp(self):
        real_popen = subprocess.Popen

        def only_keygen(args, *a, **k):                    # the test keys only; any other process fails
            if os.path.normcase(str(args[0])) != os.path.normcase(lx.op.osig.SSH_KEYGEN):
                raise AssertionError("an external entry point was called")
            return real_popen(args, *a, **k)
        self.guards: list = []
        self.real_case = lx.Harness.case                              # the real method, fixed before any patch
        test = self

        class FakeGuard:
            def __init__(self, manifest, deploy_root, folder, target=None):
                test.assertIs(target, T)

            def driver(self, **kwargs):
                test.guards.append(dict(kwargs))
                return test.conn(kwargs.get("user", "jpvl_read"))
        for patch in (mock.patch.object(psycopg, "connect", forbidden), mock.patch.object(subprocess, "Popen", only_keygen),
                      mock.patch.object(g, "listener_pids", forbidden),
                      mock.patch.object(g, "admin_connect", forbidden), mock.patch.object(g, "postmaster_pid", forbidden),
                      mock.patch.object(lay.real, "make_tls", forbidden),
                      mock.patch.object(lay.real, "start_server", forbidden),
                      mock.patch.object(lay.base, "run", forbidden),
                      mock.patch.object(g, "server_is_ours", lambda pid, target=None: pid == PID and target is T),
                      mock.patch.object(g, "Guard", FakeGuard),
                      mock.patch.object(lx.Harness, "ca_pem", lambda self: b"-----synthetic ca-----\n"),
                      mock.patch.dict(os.environ, {k: v for k, v in os.environ.items()
                                                   if not k.upper().startswith("PG")}, clear=True)):
            patch.start()
            self.addCleanup(patch.stop)
        self.folder = Path(tempfile.mkdtemp(prefix="ops_resume_case_test_"))
        self.addCleanup(shutil.rmtree, self.folder, True)
        run = self.folder / "20261029T030000"
        run.mkdir()
        self.db = lx.CHECK_DB["l3"]
        self.target = {"run_id": run.name, "host": g.HOST, "port": T.port, "data": str(T.data),
                       "postgres_exe": str(g.POSTGRES_EXE), "postmaster_pid": PID, "server_version_num": "180006",
                       "system_identifier": "1", "provider_roles": ["jpvl_read", "jpvl_write"],
                       "admin_role": "jpvl_admin", "roles": {"jpvl_read": 101, "jpvl_write": 102},
                       "databases": {d: {"oid": 500 + i, "identity_value": f"pg66-{i}-n",
                                         "objects": {t: 900 + j for j, t in enumerate(sorted(lay.OID_TABLES))}}
                                     for i, d in enumerate(lx.LAYOUT.business_databases)},
                       "synthetic": {"a": {"user_id": 2, "personal": {"p1": 11, "p2": 12, "p3": 13, "p4": 14,
                                                                      "p5": 15}, "lexeme": [1, 2]}}}
        data = json.dumps(self.target, sort_keys=True).encode()
        (run / "target.json").write_bytes(data)
        rec = g.Record(run)
        rec.event("server_started", pid=PID)
        rec.event("target_written", sha256=hashlib.sha256(data).hexdigest())
        self.h = lx.Harness(rec)                                      # real init: record binding, liveness
        self.h.keys = self.keys
        self.h.allowed = self.keys.allowed(namespaces="jp-vocab-ops/v1/synthetic/*")
        self.h.passwords = {"jpvl_read": "synthetic-password-r", "jpvl_write": "synthetic-password-w"}
        self.addCleanup(lambda: [shutil.rmtree(f, True) for f in self.h.folders])
        self.counts: list = []
        self.scope_lists: list = []
        self.driver_lists: list = []
        self.handed_errors: list = []

    def conn(self, user="jpvl_read"):
        target, db = self.target, self.db
        facts = {"server_addr": "127.0.0.1", "server_port": T.port, "version": "180006", "dbname": db,
                 "db_oid": target["databases"][db]["oid"], "role_oid": target["roles"][user],
                 "object_oids": [target["databases"][db]["objects"][t] for t in sorted(lay.OID_TABLES)],
                 "identity": [target["databases"][db]["identity_value"]]}

        class Conn:
            closed = False
            info = SimpleNamespace(backend_pid=4242)

            def cursor(self, row_factory=None):
                class C:
                    def __enter__(self):
                        return self

                    def __exit__(self, *a):
                        return False

                    def execute(self, *a):
                        pass

                    def fetchone(self):
                        return facts
                return C()

            def rollback(self):
                pass

            def close(self):
                self.closed = True
        return Conn()

    def candidates(self):
        """Real plan candidates (the plan-file module's own type) for account a's p1..p3."""
        lx.ar.fix_app_environment()
        from app.srs.engine import DEFAULT_CONFIG
        digest = hashlib.sha256(b"[]").hexdigest()
        items = [SimpleNamespace(key=SimpleNamespace(kind=kind, user_id=2, ref_id=r), card_fingerprint=None,
                                 logs_fingerprint=digest, card_version=None, quality="unavailable",
                                 flags=("card_or_access_missing",), values_json=None, last_log_id=0, reconversion=None,
                                 restart_json=None) for kind, r in (("lexeme", 1), ("lexeme", 2), ("personal", 11))]
        data = lx.pfile.serialize_plan(db_identity=lx.pf.db_identity(), account_id=2, job_key=lx.RUN_KEY,
                                       config_version=DEFAULT_CONFIG.config_version,
                                       product_fingerprint=flow.FlowBase.product(
                                           SimpleNamespace(config_version=lambda: DEFAULT_CONFIG.config_version), items),
                                       candidates=items)
        path = self.folder / "seed_plan.json"
        lx.pfile.write_plan_file(str(path), data)
        return lx.pfile.to_candidates(lx.pfile.read_plan_file(str(path)))

    def run_case(self, dry_run_body=None):
        test = self
        candidates = self.candidates()

        def fake_product(inputs, expected, driver):                  # replaces adapter + provider + observer
            def connector(read_only=False):
                raw = driver(host=g.HOST, port=str(T.port), dbname=inputs.target.database, user=lx.READ,
                             sslmode="verify-full")

                class Handed:
                    def __enter__(self):
                        return raw

                    def __exit__(self, *exc):
                        raw.close()
                        return False
                return Handed()
            return connector

        def dry_run(keys, *, connect=None):                          # the product body stub: one connection
            try:
                with connect(read_only=True):
                    pass
            except lay.CheckFailed as error:
                test.handed_errors.append((error.kind, error.what))
                raise
            if dry_run_body is not None:
                dry_run_body()
            return candidates

        class SpyCounts(lx.Counts):
            def __init__(self):
                super().__init__()
                test.counts.append(self)
        real_run, real_driver = lx.RunScopes.run, lx.Harness.driver

        def scope_run(self_, counts, trackers, **kw):
            test.scope_lists.append(trackers)
            return real_run(self_, counts, trackers, **kw)

        def driver(self_, inputs, counts, trackers, hooks=None):
            test.driver_lists.append(trackers)
            return real_driver(self_, inputs, counts, trackers, hooks)
        lx.ar.fix_app_environment()
        from app.srs import migration
        with mock.patch.object(lx, "ORIGINAL_CONNECTOR", fake_product), mock.patch.object(lx, "Counts", SpyCounts), \
                mock.patch.object(lx.RunScopes, "run", scope_run), mock.patch.object(lx.Harness, "driver", driver), \
                mock.patch.object(migration, "dry_run", dry_run):
            return self.real_case(self.h, "l3", ("l1", "l2", "p1"), batch=1)

    def test_plan_dry_run_shares_one_list_and_binds_the_plan_and_evidence(self):
        case = self.run_case()
        self.assertEqual(len(self.scope_lists), 1)
        self.assertIs(self.scope_lists[0], self.driver_lists[0])               # one list object for both
        counts = self.counts[0]
        self.assertEqual((counts.created, counts.handed), ({"jpvl_read": 1, "jpvl_write": 0},
                                                           {"jpvl_read": 1, "jpvl_write": 0}))
        self.assertEqual(len(self.scope_lists[0]), 1)                          # the one tracked connection
        self.assertEqual([k["user"] for k in self.guards], ["jpvl_read"])
        self.assertEqual(self.handed_errors, [])
        data = Path(case.plan_path).read_bytes()
        self.assertEqual(case.plan.artifact_sha256, hashlib.sha256(data).hexdigest())
        lx.ar.fix_app_environment()
        from app.srs import migration
        product = hashlib.sha256(migration._plan_json(list(lx.pfile.to_candidates(case.plan))).encode()).hexdigest()
        self.assertEqual(case.plan.product_fingerprint, product)
        a0 = json.loads(case.a0)
        self.assertEqual((a0["format_version"], a0["kind"]), (3, "apply"))
        self.assertEqual(a0["backup_evidence"],
                         {"sha256": hashlib.sha256(Path(case.initial_evidence[0]).read_bytes()).hexdigest()})
        self.assertEqual(a0["based_on"]["sha256"], hashlib.sha256(case.inquiry).hexdigest())
        self.assertIs(case.first_write.approval, case.a0)
        self.assertEqual((case.first_write.artifact_sha256, case.first_write.product_fingerprint),
                         (case.plan.artifact_sha256, case.plan.product_fingerprint))
        e0, e1 = (json.loads(Path(p[0]).read_bytes()) for p in (case.initial_evidence, case.new_evidence))
        self.assertEqual({k: v for k, v in e0.items() if k != "evidence_id"},
                         {k: v for k, v in e1.items() if k != "evidence_id"})
        self.assertNotEqual(e0["evidence_id"], e1["evidence_id"])

    def test_a_failed_plan_dry_run_stops_g1_before_any_first_apply(self):
        def fail():
            raise ValueError("synthetic product failure")
        case_calls = []
        real_case = lx.Harness.case

        def case(self_, *a, **k):                                   # the REAL case, with the failing product stub
            case_calls.append(a)
            return test_case.run_case(fail)
        test_case = self
        with mock.patch.object(lx.Harness, "first_apply", forbidden), mock.patch.object(lx, "INITIAL", {"l3": lx.INITIAL["l3"], "l1": lx.INITIAL["l1"]}), \
                mock.patch.object(lx.Harness, "outside", lambda self_, check_id, case: ["rows"]), \
                mock.patch.object(lx.Harness, "case", case), self.assertRaises(lay.CheckFailed) as caught:
            lx.g1_gate(self.h)
        self.assertIs(lx.Harness.case, real_case)
        self.assertEqual(len(case_calls), 1)                                  # l1 was never prepared
        self.assertEqual((caught.exception.kind, caught.exception.what),
                         ("preparation_failure", "l3: plan dry-run dry_run_failed"))


class ServerInfo:
    """FAKE driver info of one `ObservationServer` (what the observer and the provider read)."""

    def __init__(self, server, db, version):
        self._server = server
        self.host, self.port, self.dbname, self.backend_pid, self.server_version = g.HOST, T.port, db, 4242, version

    @property
    def transaction_status(self):
        return self._server.status


class ObservationServer:
    """FAKE server of ONE connection behind the real adapter and provider: the guard's post-connect facts, the
    observer's catalog built from the case's CONTRACT profile (never from an observation), transaction
    bookkeeping and a commit counter. Every statement, commit and close is logged; nothing is a real connection."""

    def __init__(self, test, user, *, extra=(), missing=(), close_error=None):
        import test_ops_observer as to                      # module only: its fake catalog cursor and answers
        self.to, self.close_error = to, close_error
        target, db = test.target, test.db
        access = "read" if user == lx.READ else "write"
        expected = lx.expected_profiles(db)[0 if access == "read" else 1]
        relations, columns, oids, oid = [], {}, {}, 30000
        for kind, schema, name in sorted(expected.objects):
            if kind in ("table", "sequence"):
                oid += 1
                oids[(kind, schema, name)] = oid
                relations.append((oid, "r" if kind == "table" else "S", schema, name))
                if kind == "table":
                    columns[oid] = ["id"]
        privileges = (set(expected.privileges) | set(extra)) - set(missing)
        for kind, schema, name, column, _ in sorted(expected.privileges | set(extra)):
            if column and column not in columns[oids[(kind, schema, name)]]:
                columns[oids[(kind, schema, name)]].append(column)
        schemas = {"public": 2200, lx.real.SYN: 16400}
        grants = set()
        for kind, schema, name, column, privilege in privileges:
            if kind == "database":
                grants.add(("database", 16384, privilege))
            elif kind == "schema":
                grants.add(("schema", schemas[name], privilege))
            elif kind == "sequence":
                grants.add(("sequence", oids[(kind, schema, name)], privilege))
            elif column:
                grants.add(("column", (oids[(kind, schema, name)], column), privilege))
            else:
                grants.add(("relation", oids[(kind, schema, name)], privilege))
        cat = to.catalog(access)
        cat.update(relations=relations, columns=columns, grants=grants,
                   schemas=sorted((o, n) for n, o in schemas.items()), database=[(16384, db)],
                   identity=[target["databases"][db]["identity_value"]])
        cat["session"].update(dbname=db, server_version_num=target["server_version_num"], current_user_name=user,
                              session_user_name=user, search_path=lx.real.SEARCH_PATH)
        self.catalog = cat
        self.facts = {"server_addr": "127.0.0.1", "server_port": T.port, "version": target["server_version_num"],
                      "dbname": db, "db_oid": target["databases"][db]["oid"], "role_oid": target["roles"][user],
                      "object_oids": [target["databases"][db]["objects"][t] for t in sorted(lay.OID_TABLES)],
                      "identity": [target["databases"][db]["identity_value"]]}
        self.log: list = []
        self.queries: list = []
        self.cursors: list = []
        self.commits = 0
        self.status = TransactionStatus.IDLE
        self.closed = self.broken = False
        self.read_only = self.isolation_level = None
        self.info = ServerInfo(self, db, int(target["server_version_num"]))
        self.pgconn = SimpleNamespace(ssl_in_use=True)

    def cursor(self, row_factory=None):
        if "POST_CONNECT" in self.log:
            return self.to.FakeCursor(self)                 # the observer's queries only (equality, never parsed)
        server = self

        class Facts:                                         # the guard's one post-connect read
            def __enter__(self_):
                return self_

            def __exit__(self_, *exc):
                return False

            def execute(self_, query, params=None):
                server.log.append("POST_CONNECT")
                server.status = TransactionStatus.INTRANS

            def fetchone(self_):
                return dict(server.facts)
        return Facts()

    def execute(self, query, params=None):
        if self.closed:
            raise psycopg.OperationalError("closed")
        self.log.append(query if isinstance(query, str) else "SQL")
        self.status = TransactionStatus.INTRANS

    def rollback(self):
        self.log.append("ROLLBACK")
        self.status = TransactionStatus.IDLE

    def commit(self):
        self.commits += 1
        self.log.append("COMMIT")
        self.status = TransactionStatus.IDLE

    def close(self):
        self.log.append("CLOSE")
        if self.close_error is not None:
            raise self.close_error
        self.closed = True


class RevertObservationPath(LexemeCasePath):
    """Defect 3 (commit count): the REAL `Harness.observe_role` after a revert, through the REAL adapter
    (`provide_with_adapter`: arguments, verified certificate copy), the REAL provider (pre-check with signatures,
    observation, judgement against the case's CONTRACT profile, post-connect re-judgement, hand-over) and the
    harness's real counted driver (business matrix, post-connect target check, tracked connection). FAKE: the
    guarded driver's connection (`ObservationServer`: the server's answers only). Nothing replaces a connection
    exit with a close-only stand-in: before the fix the observation went through `ProductConnection`, whose normal
    end commits, so even a matching observation counted commits=1."""

    # the case-path checks themselves run once, in LexemeCasePath
    test_plan_dry_run_shares_one_list_and_binds_the_plan_and_evidence = None
    test_a_failed_plan_dry_run_stops_g1_before_any_first_apply = None

    def setUp(self):
        super().setUp()
        self.observing, self.server_options, self.servers = False, {}, []

    def conn(self, user="jpvl_read"):
        if not self.observing:
            return super().conn(user)                       # the case's own plan dry-run (stubbed product)
        server = ObservationServer(self, user, **self.server_options.get(user, {}))
        self.servers.append(server)
        return server

    def observe(self, case, role, **options):
        self.observing, self.servers, self.server_options = True, [], {role: options}
        self.guards.clear()
        try:
            return self.h.observe_role(case, role)
        finally:
            self.observing, self.server_options = False, {}

    @staticmethod
    def contract_privilege(access, privilege):
        expected = lx.expected_profiles(lx.CHECK_DB["l3"])[0 if access == "read" else 1]
        return next(p for p in sorted(expected.privileges) if p[0] == "table" and p[4] == privilege)

    def test_matching_observation_counts_one_created_one_handed_and_no_statement_write_or_commit(self):
        case = self.run_case()
        made = []

        class SpyCounts(lx.Counts):
            def __init__(self):
                super().__init__()
                made.append(self)
        with mock.patch.object(lx, "Counts", SpyCounts):
            for role in (lx.READ, lx.WRITE):
                with self.subTest(role=role):
                    seen = self.observe(case, role)
                    self.assertEqual(seen, {"result": "matches_contract", "counts": lx.REOBSERVED})
                    self.assertEqual([k["user"] for k in self.guards], [role])
                    self.assertEqual(len(self.servers), 1)
                    server = self.servers[0]
                    self.assertTrue(server.queries)                          # the real observer read the catalog
                    self.assertEqual(server.commits, 0)                      # the server saw no COMMIT at all
                    after = server.log[len(server.log) - server.log[::-1].index("ROLLBACK"):]
                    self.assertEqual(after, ["CLOSE"])                       # after the hand-over: closed, nothing else
                    self.assertTrue(server.closed)
        self.assertEqual(len(made), 2)                                       # one fresh count per observation
        self.assertEqual(len({id(c) for c in made}), 2)

    def test_missing_or_excess_privilege_is_refused_before_the_hand_over(self):
        case = self.run_case()
        for role, options, code in (
                (lx.WRITE, {"missing": (self.contract_privilege("write", "UPDATE"),)}, "observed_privileges_missing"),
                (lx.WRITE, {"extra": (("table", "public", "users", "", "UPDATE"),)}, "observed_privileges_excess"),
                (lx.READ, {"missing": (self.contract_privilege("read", "SELECT"),)}, "observed_privileges_missing"),
                (lx.READ, {"extra": (("table", "public", "vocab_items", "", "UPDATE"),)},
                 "observed_privileges_excess")):
            with self.subTest(role=role, code=code):
                seen = self.observe(case, role, **options)
                self.assertEqual(seen, {"result": code, "counts": {"created": 1, "handed": 0, "statements": 0,
                                                                   "writes": 0, "commits": 0}})
                self.assertTrue(self.servers[0].closed)
                self.assertEqual(self.servers[0].commits, 0)

    def test_connect_take_and_close_failures_are_never_a_match(self):
        case = self.run_case()
        with self.subTest(failure="connect"):
            def refused(**kwargs):
                self.guards.append(dict(kwargs))
                raise psycopg.OperationalError("synthetic connect failure")
            with mock.patch.object(self, "conn", lambda user="jpvl_read": refused()):
                seen = self.observe(case, lx.WRITE)
            self.assertEqual(seen, {"result": "connect_failed", "counts": {"created": 0, "handed": 0, "statements": 0,
                                                                           "writes": 0, "commits": 0}})
        with self.subTest(failure="take"):
            def taken(self_):
                raise lx.pv.OpsProviderRefused("handoff_already_taken")
            with mock.patch.object(lx.pv.Handoff, "take", taken):
                seen = self.observe(case, lx.WRITE)
            self.assertEqual(seen["result"], "handoff_already_taken")
            self.assertEqual((seen["counts"]["created"], seen["counts"]["handed"], seen["counts"]["commits"]),
                             (1, 0, 0))
        with self.subTest(failure="close"):
            seen = self.observe(case, lx.WRITE, close_error=psycopg.OperationalError("synthetic close failure"))
            self.assertEqual(seen, {"result": "connection_close_unconfirmed", "counts": lx.REOBSERVED})
            self.assertEqual(self.servers[0].commits, 0)

    def test_a_failed_reobservation_stops_with_a_harness_defect_and_is_recorded(self):
        case = self.run_case()
        for label, options in (("missing", {"missing": (self.contract_privilege("write", "UPDATE"),)}),
                               ("close", {"close_error": psycopg.OperationalError("synthetic close failure")})):
            with self.subTest(case=label):
                events = []
                self.observing, self.servers, self.server_options = True, [], {lx.WRITE: options}
                try:
                    with mock.patch.object(lx.Harness, "variant", lambda self_, *a: None), \
                            mock.patch.object(self.h.rec, "event", lambda kind, **kw: events.append((kind, kw))), \
                            self.assertRaises(lay.CheckFailed) as caught:
                        lx.revert_and_observe(self.h, "l8", case, "l8_lexeme_card_column", lx.WRITE)
                finally:
                    self.observing, self.server_options = False, {}
                self.assertEqual(caught.exception.kind, "harness_defect")
                recorded = [kw for kind, kw in events if kind == "revert_observation"]
                self.assertEqual(len(recorded), 1)
                self.assertNotEqual(recorded[0]["result"], "matches_contract")


# --- 2. card keys, never positions --------------------------------------------------------------------------

class CardKeys(unittest.TestCase):
    def test_names_map_to_keys(self):
        ids = {"user_id": 9, "personal": {"p3": 7, "p1": 21, "p2": 8, "p4": 1, "p5": 2}, "lexeme": [40, 41]}
        self.assertEqual(lx.card_keys(ids, ("l1", "l2", "p1")),
                         [("lexeme", 9, 40), ("lexeme", 9, 41), ("personal", 9, 21)])
        self.assertEqual(lx.card_keys(ids, ("p1", "l2")), [("personal", 9, 21), ("lexeme", 9, 41)])
        for bad_ids, names in ((ids, ("l3",)), ({**ids, "lexeme": [40]}, ("l1",)), (ids, ("x1",)),
                               ({**ids, "lexeme": [40, 40]}, ("l1", "l2"))):
            with self.subTest(names=names), self.assertRaises(lay.CheckFailed):
                lx.card_keys(bad_ids, names)


# --- 3. L4 / L5 judgements through the real record path -------------------------------------------------------

def values9(**changes):
    value = {"run_id": 3, "status": "started", "mode": "apply", "config_version": "c", "started_at": "s",
             "finished_at": None, "scope_sha256": "a" * 64, "summary_sha256": "b" * 64, "snapshots_sha256": "d" * 64}
    value.update(changes)
    return value


class Judgements(Blocked):
    def harness(self, **override):
        evidence = {name: {"values": {"pre_read": values9(), "under_lock": values9()}, "admin_values": values9()}
                    for name in ("l1", "l2")}
        for name, ev in override.items():
            evidence[name].update(ev)
        return SimpleNamespace(evidence=evidence)

    def test_l5_six_dictionaries_saved_and_read_back(self):
        rec, _ = self.record()
        h = self.harness()
        self.assertTrue(lay.run_recorded(rec, "l5", lx.l5_fixed_values, h))
        last = json.loads((rec.folder / "record.json").read_text(encoding="utf-8"))["results"][-1]
        self.assertEqual((last["check"], last["status"]), ("l5", "pass"))
        self.assertEqual(last["details"]["compared"], ["l1", "l2"])
        for name in ("l1", "l2"):
            for key in ("pre_read", "under_lock", "admin_values"):
                self.assertEqual(last["details"]["values"][name][key], values9())
                self.assertEqual(tuple(sorted(last["details"]["values"][name][key])), tuple(sorted(NINE)))
        out = lx.l5_fixed_values(h)
        self.assertIsNot(out["values"]["l1"]["pre_read"], h.evidence["l1"]["values"]["pre_read"])   # a copy

    def test_l5_missing_wrong_or_different_is_not_a_pass(self):
        for label, override, kind in (("missing", {"l2": {"admin_values": None}}, "harness_defect"),
                                      ("extra key", {"l1": {"admin_values": dict(values9(), x=1)}}, "harness_defect"),
                                      ("different", {"l2": {"admin_values": values9(status="failed")}}, None)):
            with self.subTest(case=label):
                rec, _ = self.record()
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertFalse(lay.run_recorded(rec, "l5", lx.l5_fixed_values, self.harness(**override)))
                last = json.loads((rec.folder / "record.json").read_text(encoding="utf-8"))["results"][-1]
                self.assertEqual(last["status"], "fail")
                if kind:
                    self.assertEqual(last["kind"], kind)
                shutil.rmtree(rec.folder)

    def test_l4_needs_the_three_records(self):
        self.assertEqual(lx.l4_other_accounts(SimpleNamespace(evidence={"outside_ok": {"l1": True, "l2": True,
                                                                                         "l3": True}}))["checked"],
                         ["l1", "l2", "l3"])
        with self.assertRaises(lay.CheckFailed) as caught:
            lx.l4_other_accounts(SimpleNamespace(evidence={"outside_ok": {"l1": True}}))
        self.assertEqual(caught.exception.kind, "harness_defect")
        with self.assertRaises(lay.CheckFailed):
            lx.l4_other_accounts(SimpleNamespace(evidence={"outside_ok": {"l1": True, "l2": False, "l3": True}}))


# --- 3b. L1~L3 / L8 judge the admin-read DB state; L4 covers accounts b AND c; L8 / L9 re-observe after revert ---
# Fakes only: every value below is a synthetic stand-in for an admin read, never PostgreSQL evidence. Expected values
# (versions, cursor, snapshot set) are fixed here from the G1 baseline + the initial plan + the contract, never from
# the observation after the run.

U = 9
L1K, L2K, P1K = ("lexeme", U, 40), ("lexeme", U, 41), ("personal", U, 21)
PLAN = SimpleNamespace(account_id=U, candidates=(SimpleNamespace(kind="lexeme", ref_id=40, card_version=3),
                                                 SimpleNamespace(kind="lexeme", ref_id=41, card_version=5),
                                                 SimpleNamespace(kind="personal", ref_id=21, card_version=7)))
NO_SESSIONS = {"open": 0, "idle_in_transaction": 0}
OUT = {"b:lexeme:40": "b-l1"}


def card(version, engine, row):
    return {"version": version, "engine": engine, "row": row}


def baseline(names):
    """Right after G1 (first apply, batch 1): l1 converted (plan 3 -> 4), the rest as planned, one snapshot."""
    cards = {"lexeme:9:40": card(4, "fsrs", "l1-first"), "lexeme:9:41": card(5, "legacy", "l2-orig"),
             "personal:9:21": card(7, "legacy", "p1-orig")}
    keep = {"l1": "lexeme:9:40", "l2": "lexeme:9:41", "p1": "personal:9:21"}
    return {"runs": 1, "status": "started", "cursor": 1, "finished": False, "results": [("lexeme", 40, "applied")],
            "cards": {keep[n]: cards[keep[n]] for n in names},
            "snapshots": {"lexeme:9:40": {"version_before": 3, "row": "snap-l1"}}, "snapshot_count": 1}


def after(base, **changes):
    state = json.loads(json.dumps(base))
    for key, value in changes.items():
        if key == "cards" or key == "snapshots":
            state[key].update(value)
        else:
            state[key] = value
    state["snapshot_count"] = len(state["snapshots"])
    return state


def completed_l1(base):
    return after(base, status="completed", cursor=2, finished=True,
                 results=[("lexeme", 40, "already_applied"), ("lexeme", 41, "applied")],
                 cards={"lexeme:9:41": card(6, "fsrs", "l2-new")},
                 snapshots={"lexeme:9:41": {"version_before": 5, "row": "snap-l2"}})


class FakeRun:
    """Stands in for the harness of ONE check: CLI result, admin reads before / after, revert observation."""

    def __init__(self, rec, check_id, names, keys, now, *, out, code, counts, observation=None):
        self.rec = rec
        plan = SimpleNamespace(account_id=U, candidates=tuple(c for c in PLAN.candidates
                                                              if (c.kind, U, c.ref_id) in keys))
        self.case = SimpleNamespace(check_id=check_id, names=names, keys=keys, plan=plan, db="fake",
                                    request=SimpleNamespace(account_id=U))
        self.cases = {check_id: self.case}
        self.base = baseline(names)
        self.now = now
        self.evidence = {"baseline": {check_id: self.base}, "outside": {check_id: dict(OUT)}}
        self.result = {"out": out, "code": code, "counts": counts, "values": {}}
        self.observation = observation
        self.calls = []
        self.ran = False

    # admin reads (fake): before the run the G1 baseline, after it `now`
    def _view(self):
        return self.now if self.ran else self.base

    def state(self, case):
        self.calls.append("state")
        return self._view()

    def card_rows(self, case):
        view = self._view()
        return {f"{k}:{r}": view["cards"][f"{k}:{u}:{r}"]["row"] for k, u, r in case.keys}

    def facts(self, case):
        view = self._view()
        return {"runs": [{"status": view["status"]}], "summary": {"cursor": view["cursor"]},
                "summary_results": list(view["results"]),
                "snapshot_keys": [(k.split(":")[0], int(k.split(":")[1]), int(k.split(":")[2]))
                                  for k in view["snapshots"]]}

    def fixed_values(self, case):
        return values9()

    def outside(self, check_id, case):
        return dict(OUT)

    def sessions(self):
        return dict(NO_SESSIONS)

    def resume(self, case, batch, *, after=None):
        if after is not None:
            after(lx.WRITE, 2)
        self.ran = True
        self.calls.append(("resume", batch))
        return self.result

    def variant(self, check_id, name, phase):
        self.calls.append(("variant", name, phase))

    def observe_role(self, case, role):
        self.calls.append(("observe", role))
        return self.observation


def counts(write=(0, 0, 0), read=(0, 0)):
    c = lx.Counts()
    c.created[lx.WRITE], c.handed[lx.WRITE], c.commits[lx.WRITE] = write
    c.created[lx.READ], c.handed[lx.READ] = read
    return c


def observed(result="matches_contract", created=1, handed=1, statements=0, writes=0, commits=0):
    return {"result": result, "counts": {"created": created, "handed": handed, "statements": statements,
                                         "writes": writes, "commits": commits}}


L1_OUT = {"phase": "completed", "results": {"already_applied": 1, "applied": 1}}
L8_OUT = {"code": "observed_privileges_missing", "phase": "after_start", "uncertain": True, "next": "status_required"}
L9_OUT = {"code": "observed_privileges_missing", "phase": "before_first_write"}


class AdminState(Blocked):
    """Defect 1: L1~L3 compare the admin-read run row / cards / snapshots against the G1 baseline and the plan."""

    def l1(self, now):
        rec, _ = self.record()
        h = FakeRun(rec, "l1", ("l1", "l2"), [L1K, L2K], None, out=L1_OUT, code=0, counts=counts())
        h.now = now(h.base)
        return h

    def test_normal_completion_passes_and_is_recorded(self):
        h = self.l1(completed_l1)
        self.assertTrue(lay.run_recorded(h.rec, "l1", lx.l1_partial, h))
        last = json.loads((h.rec.folder / "record.json").read_text(encoding="utf-8"))["results"][-1]
        self.assertEqual((last["check"], last["status"]), ("l1", "pass"))

    def test_cli_normal_but_db_started_cursor_1_card_unchanged_fails(self):
        """The reported case: CLI result, result order and snapshot keys are normal; the DB says otherwise."""
        def started(base):
            return after(base, results=[("lexeme", 40, "already_applied"), ("lexeme", 41, "applied")],
                         snapshots={"lexeme:9:41": {"version_before": 5, "row": "snap-l2"}})
        h = self.l1(started)
        with self.assertRaises(lay.CheckFailed) as caught:
            lx.l1_partial(h)
        self.assertEqual(caught.exception.kind, "product_defect")

    def test_each_wrong_db_state_fails(self):
        wrong = {
            "not finished": lambda b: after(completed_l1(b), finished=False),
            "cursor short": lambda b: after(completed_l1(b), cursor=1),
            "two run rows": lambda b: after(completed_l1(b), runs=2),
            "l2 version +2": lambda b: after(completed_l1(b), cards={"lexeme:9:41": card(7, "fsrs", "l2-new")}),
            "l2 engine legacy": lambda b: after(completed_l1(b), cards={"lexeme:9:41": card(6, "legacy", "l2-new")}),
            "l1 rewritten": lambda b: after(completed_l1(b), cards={"lexeme:9:40": card(4, "fsrs", "l1-other")}),
            "l1 version moved": lambda b: after(completed_l1(b), cards={"lexeme:9:40": card(5, "fsrs", "l1-first")}),
            "old snapshot rewritten": lambda b: after(completed_l1(b),
                                                      snapshots={"lexeme:9:40": {"version_before": 3, "row": "x"}}),
            "new snapshot wrong version": lambda b: after(completed_l1(b),
                                                          snapshots={"lexeme:9:41": {"version_before": 6,
                                                                                     "row": "snap-l2"}}),
            "extra snapshot": lambda b: after(completed_l1(b),
                                              snapshots={"personal:9:21": {"version_before": 7, "row": "s"}}),
            "l2 snapshot missing": lambda b: {**after(completed_l1(b)),
                                              "snapshots": {"lexeme:9:40": b["snapshots"]["lexeme:9:40"]},
                                              "snapshot_count": 1},
        }
        for label, now in wrong.items():
            with self.subTest(case=label), self.assertRaises(lay.CheckFailed):
                lx.l1_partial(self.l1(now))

    def test_expectations_come_from_baseline_and_plan_not_from_the_run(self):
        """A wrong G1 baseline (l2 not at the plan's version) stops before the run is judged against itself."""
        h = self.l1(completed_l1)
        h.base["cards"]["lexeme:9:41"] = card(6, "legacy", "l2-orig")
        with self.assertRaises(lay.CheckFailed) as caught:
            lx.l1_partial(h)
        self.assertEqual(caught.exception.kind, "harness_defect")


class L8State(Blocked):
    """Defect 1 (L8): the partial commit is judged on the DB, the CLI's unconfirmed report is kept apart."""

    def l8(self, now, observation=None):
        rec, _ = self.record()
        h = FakeRun(rec, "l8", ("l1", "l2", "p1"), [L1K, L2K, P1K], None, out=L8_OUT, code=1,
                    counts=counts(write=(4, 2, 2)), observation=observation or observed())
        h.now = now(h.base)
        return h

    @staticmethod
    def partial(base):
        return after(base, cursor=2, results=[("lexeme", 40, "already_applied"), ("lexeme", 41, "applied")],
                     cards={"lexeme:9:41": card(6, "fsrs", "l2-new")},
                     snapshots={"lexeme:9:41": {"version_before": 5, "row": "snap-l2"}})

    def test_partial_commit_passes_with_cli_and_db_state_recorded_apart(self):
        h = self.l8(self.partial)
        out = lx.l8_column_revoked_after_l2(h)
        self.assertEqual(h.evidence["l8"]["cli"], {"code": "observed_privileges_missing", "phase": "after_start",
                                                   "uncertain": True, "next": "status_required", "exit": 1})
        self.assertEqual(h.evidence["l8"]["admin_state"], {"runs": 1, "status": "started", "cursor": 2,
                                                           "finished": False})
        self.assertEqual(out["admin_state"]["status"], "started")
        self.assertIn(("variant", "l8_lexeme_card_column", "revert"), h.calls)

    def test_snapshot_present_but_l2_not_changed_fails(self):
        def kept_snapshot_only(base):
            return after(base, cursor=2, snapshots={"lexeme:9:41": {"version_before": 5, "row": "snap-l2"}})
        with self.assertRaises(lay.CheckFailed):
            lx.l8_column_revoked_after_l2(self.l8(kept_snapshot_only))

    def test_each_wrong_partial_state_fails(self):
        wrong = {
            "completed": lambda b: after(self.partial(b), status="completed", finished=True, cursor=3),
            "failed mark written": lambda b: after(self.partial(b), status="failed"),
            "finished": lambda b: after(self.partial(b), finished=True),
            "cursor 3": lambda b: after(self.partial(b), cursor=3),
            "l1 changed": lambda b: after(self.partial(b), cards={"lexeme:9:40": card(5, "fsrs", "l1-x")}),
            "p1 converted": lambda b: after(self.partial(b), cards={"personal:9:21": card(8, "fsrs", "p1-new")},
                                            snapshots={"personal:9:21": {"version_before": 7, "row": "s"}}),
            "p1 row changed": lambda b: after(self.partial(b), cards={"personal:9:21": card(7, "legacy", "p1-x")}),
        }
        for label, now in wrong.items():
            with self.subTest(case=label), self.assertRaises(lay.CheckFailed):
                lx.l8_column_revoked_after_l2(self.l8(now))

    def test_cli_must_stay_unconfirmed(self):
        h = self.l8(self.partial)
        h.result["out"] = dict(L8_OUT, uncertain=False)
        with self.assertRaises(lay.CheckFailed):
            lx.l8_column_revoked_after_l2(h)


class Outside(Blocked):
    """Defect 2: the REAL `Harness.outside` on a fake admin connection that answers only for the BOUND account
    ids (as SQL would); account ids must never appear in the statement text."""

    IDS = {"a": {"user_id": 7001, "personal": {"p1": 101, "p5": 105}, "lexeme": [40, 41]},
           "b": {"user_id": 7002, "personal": {"p1": 201}, "lexeme": [40, 41]},
           "c": {"user_id": 7003, "personal": {"p1": 301}, "lexeme": [40, 41]}}

    def setUp(self):
        super().setUp()
        self.tables = {
            "vocab_items": [{"id": i, "user_id": u, "text": f"v{i}"} for u, i in
                            ((7001, 101), (7001, 105), (7002, 201), (7003, 301))],
            "user_word_progress": [{"id": n, "user_id": u, "lexeme_id": lx_, "text": f"p{u}-{lx_}"}
                                   for n, (u, lx_) in enumerate(((7001, 40), (7001, 41), (7002, 40), (7002, 41),
                                                                 (7003, 40), (7003, 41)))],
            "lexeme_review_logs": [{"id": 1, "user_id": 7002, "text": "log-b"}, {"id": 2, "user_id": 7003,
                                                                                "text": "log-c"}]}
        self.statements = []
        test = self

        class Conn:
            def execute(self, query, params=()):
                text = query if isinstance(query, str) else repr(query)
                test.statements.append((text, params))
                for account in test.IDS.values():
                    test.assertNotIn(str(account["user_id"]), text)          # bound, never formatted
                head, rest = text.split(" FROM ", 1)
                table = rest.split()[0]
                columns = ["text" if c.strip().endswith("::text") else c.strip()
                           for c in head[len("SELECT "):].split(",")]
                # models the two statement forms only: `user_id = %s` and `user_id = %s AND <col> = ANY (%s)`
                where = rest.split(" WHERE ", 1)[1] if " WHERE " in rest else ""
                users = {p for p in params if isinstance(p, int)}
                lists = [p for p in params if isinstance(p, list)]
                col = (where.split(" AND ", 1)[1].split(" = ANY", 1)[0].strip()
                       if " AND " in where and " = ANY" in where else None)
                rows = [r for r in test.tables[table] if not params or (
                    r["user_id"] in users and (col is None or any(r[col] in l for l in lists)))]
                return SimpleNamespace(fetchall=lambda: [tuple(r[c] for c in columns) for r in rows])

        @contextlib.contextmanager
        def fake_admin(db, pid, autocommit=True):
            yield Conn()
        patch = mock.patch.object(lx, "admin", fake_admin)
        patch.start()
        self.addCleanup(patch.stop)
        self.h = lx.Harness.__new__(lx.Harness)
        self.h.target, self.h.pid = {"synthetic": self.IDS}, PID
        self.case = SimpleNamespace(keys=[("lexeme", 7001, 40), ("lexeme", 7001, 41)])
        self.h.cases = {"l1": self.case}
        self.h.evidence = {"outside": {"l1": self.h.outside("l1", self.case)}}

    def change(self, table, **match):
        row = next(r for r in self.tables[table] if all(r[k] == v for k, v in match.items()))
        row["text"] += "-changed"

    def test_nothing_changed_is_kept(self):
        self.assertTrue(lx.outside_kept(self.h, "l1"))

    def test_only_account_c_changed_fails(self):
        self.change("user_word_progress", user_id=7003, lexeme_id=41)          # b untouched
        self.assertFalse(lx.outside_kept(self.h, "l1"))

    def test_account_b_c_logs_and_a_out_of_scope_each_fail(self):
        for label, table, match in (("b same lexeme", "user_word_progress", {"user_id": 7002, "lexeme_id": 40}),
                                    ("c personal", "vocab_items", {"id": 301}),
                                    ("c log", "lexeme_review_logs", {"id": 2}),
                                    ("a out of scope p5", "vocab_items", {"id": 105})):
            with self.subTest(case=label):
                self.setUp()
                self.change(table, **match)
                self.assertFalse(lx.outside_kept(self.h, "l1"))

    def test_rows_are_keyed_and_both_accounts_need_the_same_lexemes(self):
        kept = self.h.evidence["outside"]["l1"]
        for key in ("b:lexeme:40", "b:lexeme:41", "c:lexeme:40", "c:lexeme:41", "c:personal:301", "a:personal:105",
                    "log:2"):
            self.assertIn(key, kept)
        self.assertNotIn("a:lexeme:40", kept)                                    # in the case: judged by L1~L3
        self.tables["user_word_progress"] = [r for r in self.tables["user_word_progress"]
                                             if (r["user_id"], r["lexeme_id"]) != (7003, 41)]
        with self.assertRaises(lay.CheckFailed) as caught:
            self.h.outside("l1", self.case)
        self.assertEqual(caught.exception.kind, "harness_defect")


class RevertObservation(Blocked):
    """Defect 3: after the revert SQL the changed role is observed again through the provider path; anything but
    the contract profile with no product call / write is a failure, recorded apart from the run's own result."""

    def l8(self, observation):
        rec, _ = self.record()
        h = FakeRun(rec, "l8", ("l1", "l2", "p1"), [L1K, L2K, P1K], None, out=L8_OUT, code=1,
                    counts=counts(write=(4, 2, 2)), observation=observation)
        h.now = L8State.partial(h.base)
        return h

    def l9(self, observation):
        rec, _ = self.record()
        h = FakeRun(rec, "l9", ("l1", "l2"), [L1K, L2K], None, out=L9_OUT, code=4,
                    counts=counts(read=(1, 0)), observation=observation)
        h.now = h.base
        return h

    BAD = {"still missing": observed("observed_privileges_missing", handed=0),
           "excess": observed("observed_privileges_excess", handed=0),
           "product call": observed(statements=1),
           "write": observed(statements=1, writes=1),
           "not handed": observed(handed=0),
           "nothing observed": None}

    def test_matching_observation_passes_for_the_changed_role(self):
        for make, check, role in ((self.l8, lx.l8_column_revoked_after_l2, lx.WRITE),
                                  (self.l9, lx.l9_subscription_read_missing, lx.READ)):
            with self.subTest(role=role):
                h = make(observed())
                check(h)
                revert = h.calls.index(next(c for c in h.calls if c[:1] == ("variant",) and c[2] == "revert"))
                self.assertEqual(h.calls[revert + 1], ("observe", role))
                self.assertEqual(h.evidence["revert_observation"][h.case.check_id]["result"], "matches_contract")

    def test_missing_or_excess_after_revert_fails_and_is_recorded_apart(self):
        for make, check, name in ((self.l8, lx.l8_column_revoked_after_l2, "l8"),
                                  (self.l9, lx.l9_subscription_read_missing, "l9")):
            for label, observation in self.BAD.items():
                with self.subTest(check=name, case=label):
                    h = make(observation)
                    self.addCleanup(shutil.rmtree, h.rec.folder, True)
                    with contextlib.redirect_stdout(io.StringIO()):
                        self.assertFalse(lay.run_recorded(h.rec, name, check, h))
                    saved = json.loads((h.rec.folder / "record.json").read_text(encoding="utf-8"))
                    shutil.rmtree(h.rec.folder)
                    self.assertEqual((saved["results"][-1]["status"], saved["results"][-1]["kind"]),
                                     ("fail", "harness_defect"))
                    runs = [e for e in saved["events"] if e["kind"] == "check_run" and e["check"] == name]
                    seen = [e for e in saved["events"] if e["kind"] == "revert_observation" and e["check"] == name]
                    self.assertEqual(len(runs), 1)                    # the run's own outcome, kept as it was
                    self.assertEqual(runs[0]["cli"]["code"], "observed_privileges_missing")
                    self.assertEqual(len(seen), 1)
                    self.assertEqual((seen[0]["result"], seen[0]["counts"]),
                                     ("not_observed", None) if observation is None else
                                     (observation["result"], observation["counts"]))
                    self.assertNotIn("pass", [r["status"] for r in saved["results"]])

    def test_a_failed_revert_observation_stops_the_later_checks(self):
        rec, _ = self.record()
        h = self.l8(observed("observed_privileges_missing", handed=0))
        h.rec = rec
        h.start, h.close = (lambda: None), (lambda: None)
        later = []
        with mock.patch.object(lx, "LQ3_CHANGES_APPROVED", True), \
                mock.patch.object(g, "single_run", lambda target=None: rec), \
                mock.patch.object(lx, "Harness", lambda r: h), \
                mock.patch.object(lx, "g0_gate", lambda h_: {}), mock.patch.object(lx, "g1_gate", lambda h_: {}), \
                mock.patch.object(lx, "post_check", lambda h_: later.append("post") or {}), \
                mock.patch.object(lx, "CHECKS", [("l8", lx.l8_column_revoked_after_l2),
                                                 ("l9", lambda h_: later.append("l9") or {})]), \
                contextlib.redirect_stdout(io.StringIO()):
            passed, summary = lx.check_lexeme()
        self.assertEqual((passed, summary), (0, {"failed": "l8", "not_run": ["l9"]}))
        self.assertEqual(later, [])


# --- 4. stop rules --------------------------------------------------------------------------------------------

class StopRules(Blocked):
    def run_check(self, fail=None):
        rec, _ = self.record()
        calls = []

        def make(name):
            def fn(h):
                calls.append(name)
                if name == fail:
                    raise lay.CheckFailed("product_defect", name)
                return {"ok": name}
            return fn
        harness = SimpleNamespace(start=lambda: None, close=lambda: calls.append("closed"))
        with mock.patch.object(lx, "LQ3_CHANGES_APPROVED", True), \
                mock.patch.object(g, "single_run", lambda target=None: rec), \
                mock.patch.object(lx, "Harness", lambda r: harness), \
                mock.patch.object(lx, "g0_gate", make("g0_gate")), mock.patch.object(lx, "g1_gate", make("g1_gate")), \
                mock.patch.object(lx, "post_check", make(lx.POST)), \
                mock.patch.object(lx, "CHECKS", [(n, make(n)) for n in PLAN_CHECKS]), \
                contextlib.redirect_stdout(io.StringIO()):
            code = lx.main(["check-lexeme"])
        saved = json.loads((rec.folder / "record.json").read_text(encoding="utf-8"))
        shutil.rmtree(rec.folder)
        return code, calls, saved

    def test_all_pass_is_0_and_gates_not_counted(self):
        code, calls, saved = self.run_check()
        self.assertEqual(code, 0)
        self.assertEqual([c for c in calls if c != "closed"], ["g0_gate", "g1_gate", *PLAN_CHECKS, lx.POST])
        started = [e for e in saved["events"] if e["kind"] == "check_phase_started"][0]
        self.assertEqual((started["phase"], started["checks"]), ("lexeme", list(PLAN_CHECKS)))

    def test_first_failure_stops_with_1(self):
        for fail, not_run in (("g1_gate", list(PLAN_CHECKS)), ("l3", list(PLAN_CHECKS[3:])), ("l9", []),
                              (lx.POST, [])):
            with self.subTest(fail=fail):
                code, calls, saved = self.run_check(fail)
                self.assertEqual(code, 1)
                self.assertNotIn(PLAN_CHECKS[PLAN_CHECKS.index(fail) + 1] if fail in PLAN_CHECKS[:-1] else "none",
                                 calls)
                events = [e for e in saved["events"] if e["kind"] == "not_run"]
                self.assertEqual(events[0]["checks"] if events else [], not_run)

    def test_usage_and_cleanup_mismatch(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(lx.main([]), 2)
            self.assertEqual(lx.main(["check"]), 2)
            self.assertEqual(lx.main(["check-lexeme", "l1"]), 2)
        rec, _ = self.record(port=55502)
        with mock.patch.object(g, "single_run", lambda target=None: rec), mock.patch.object(shutil, "rmtree", forbidden), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(lx.main(["cleanup"]), 1)


# --- 5. new processes: safe environment first, import does nothing, __main__ exit codes ---------------------

SAFE = ("import os\nos.environ['APP_ENV'] = 'test'\nos.environ['DATABASE_URL'] = 'sqlite:///:memory:'\n"
        "os.environ['PYTHON_DOTENV_DISABLED'] = '1'\n")


class Processes(unittest.TestCase):
    def run_code(self, code):
        env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "APP_ENV", "DATABASE_URL",
                                                               "PYTHON_DOTENV_DISABLED") and not k.upper().startswith("PG")}
        return subprocess.run([sys.executable, "-c", SAFE + code], capture_output=True, text=True, timeout=180, env=env,
                              cwd=str(TESTS_DIR))

    def test_import_does_nothing(self):
        done = self.run_code(
            "import sys, subprocess, tempfile, psycopg\n"
            f"sys.path[:0] = [{str(TESTS_DIR)!r}, {str(BACKEND / 'scripts')!r}]\n"
            "def bad(*a, **k): raise SystemExit('EXTERNAL')\n"
            "psycopg.connect = bad; subprocess.run = bad; subprocess.Popen = bad; tempfile.mkdtemp = bad\n"
            "os.mkdir = bad; os.makedirs = bad\n"
            "import _ops_resume_lexeme_real as lx\n"
            "app = any(m == 'app' or m.startswith('app.') for m in sys.modules)\n"
            "print('RESULT', app, lx.T.root.exists())\n")
        self.assertIn("RESULT False False", done.stdout, done.stderr[-600:])

    def test_main_exit_codes(self):
        script = str(TESTS_DIR / "_ops_resume_lexeme_real.py")
        blocker = ("import sys, runpy, subprocess, psycopg\n"
                   f"sys.path[:0] = [{str(TESTS_DIR)!r}, {str(BACKEND / 'scripts')!r}]\n"
                   "def bad(*a, **k): raise SystemExit(99)\n"
                   "psycopg.connect = bad; subprocess.run = bad; subprocess.Popen = bad\n"
                   "import _ops_pg62 as g\n"
                   "g.single_run = bad; g.admin_connect = bad; g.listener_pids = bad\n"
                   "sys.argv = [{script!r}] + {args!r}\n"
                   "runpy.run_path({script!r}, run_name='__main__')\n")
        for args, want in (([], 2), (["check"], 2), (["check-values"], 2), (["check-lexeme", "l1"], 2),
                           (["check-lexeme"], 1)):                  # LQ3 not approved: stops before any record
            with self.subTest(args=args):
                done = self.run_code(blocker.format(script=script, args=args))
                self.assertEqual(done.returncode, want, done.stdout + done.stderr[-400:])

    def test_cli_resume_entry_stays_closed(self):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            code = cli.main(["resume", "--account", "7", "--run-key", "k", "--lexeme-id", "1", "--batch-size", "1",
                             "--plan", "p", "--backup-evidence", "e", "--backup-signature", "s",
                             "--initial-evidence", "i", "--initial-evidence-signature", "j"])
        self.assertEqual(code, 4)
        self.assertIn("connection_not_available", out.getvalue())


if __name__ == "__main__":
    unittest.main()

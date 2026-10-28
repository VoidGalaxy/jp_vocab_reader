"""Fake-only checks for the C12 first-apply real-PG runner (tests/_ops_apply_real.py). No database, no
cluster, no keys or certificates: connect entry points, `subprocess`, key creation and process facts are
patched; only temporary synthetic files are written.

Run directly:      python tests/test_ops_apply_real_guard.py
Or via discovery:   python -m unittest discover -s tests
"""

from __future__ import annotations

import contextlib
import dataclasses
import hashlib
import inspect
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

TESTS_DIR = Path(__file__).resolve().parent
BACKEND = TESTS_DIR.parent
sys.path.insert(0, str(BACKEND / "scripts"))
sys.path.insert(0, str(TESTS_DIR))

import psycopg  # noqa: E402
from psycopg import sql  # noqa: E402

import _ops_apply_real as ap  # noqa: E402
import _ops_pg62 as g  # noqa: E402
import _ops_provider as pv  # noqa: E402
import srs_migrate as cli  # noqa: E402

T = g.PG65_APPLY
PID = 7777


def forbidden(*_, **__):
    raise AssertionError("an external entry point was called")


class Blocked(unittest.TestCase):
    """Every real connection, process, key creation and listener lookup fails the test if reached."""

    def setUp(self):
        for patch in (mock.patch.object(psycopg, "connect", forbidden), mock.patch.object(subprocess, "Popen", forbidden),
                      mock.patch.object(subprocess, "run", forbidden),
                      mock.patch.object(ap.sigtests, "Keys", forbidden),
                      mock.patch.object(g, "listener_pids", forbidden),
                      mock.patch.object(g, "server_is_ours", lambda pid, target=None: pid == PID and target is T),
                      mock.patch.dict(os.environ, {k: v for k, v in os.environ.items()
                                                   if not k.upper().startswith("PG")}, clear=True)):
            patch.start()
            self.addCleanup(patch.stop)
        self.folder = Path(tempfile.mkdtemp(prefix="ops_apply_real_test_"))
        self.addCleanup(shutil.rmtree, self.folder, True)

    def record(self, **changes):
        """A synthetic run record + target.json bound by its hash (no real cluster)."""
        run = self.folder / "20261027T020000"
        run.mkdir(exist_ok=True)
        target = {"run_id": run.name, "host": g.HOST, "port": T.port, "data": str(T.data),
                  "postgres_exe": str(g.POSTGRES_EXE), "postmaster_pid": PID, "server_version_num": "180006",
                  "system_identifier": "1", "provider_roles": list(ap.BUSINESS_ROLES), "admin_role": T.admin,
                  "roles": {ap.READ: 101, ap.WRITE: 102},
                  "databases": {db: {"oid": 500 + i, "identity_value": f"pg65-{i}-n",
                                     "objects": {t: 900 + j for j, t in enumerate(sorted(ap.OID_TABLES))}}
                                for i, db in enumerate(ap.BUSINESS_DATABASES)}}
        target.update(changes)
        data = json.dumps(target, sort_keys=True).encode()
        (run / "target.json").write_bytes(data)
        rec = g.Record(run)
        rec.event("server_started", pid=PID)
        rec.event("target_written", sha256=hashlib.sha256(data).hexdigest())
        return rec, target


# --- 1. closed presets ------------------------------------------------------------------------------------

class Presets(Blocked):
    def test_closed_list_and_earlier_presets_kept(self):
        self.assertEqual(g.PRESETS, (g.PG62, g.PG63_AUDIT, g.PG64_BACKUP, g.PG65_APPLY,
                         g.PG66_RESUME, g.PG67_RESUME_LEXEME))   # pg66 (RS4-1), pg67 (lexeme L-1): the closed list grows
        self.assertEqual((g.PG62.root, g.PG62.port, g.PG62.databases, g.PG62.admin),
                         (Path("C:/JV_Tools/pg62"), 55462, ("jp_vocab_test_62a", "jp_vocab_test_62b"), "jpv62_admin"))
        self.assertEqual((g.PG63_AUDIT.port, g.PG63_AUDIT.provider_roles), (55472, ("jpva_audit",)))
        self.assertEqual((g.PG64_BACKUP.port, g.PG64_BACKUP.provider_roles), (55482, ("jpvb_audit",)))
        self.assertEqual((T.root, T.port, T.admin, T.provider_roles),
                         (Path("C:/JV_Tools/pg65"), 55492, "jpvm_admin", ("jpvm_read", "jpvm_write")))

    def test_equal_copy_or_other_value_is_not_a_target(self):
        for other in (dataclasses.replace(T), dataclasses.replace(T, port=55432), "pg65_apply"):
            with self.assertRaises(g.Pg62Refused) as caught:
                g.preset(other)
            self.assertEqual(caught.exception.code, "pg62_target_preset_refused")

    def test_template_and_check_databases(self):
        self.assertEqual(ap.TEMPLATE, "jp_vocab_test_apply_tpl")
        self.assertNotIn(ap.TEMPLATE, ap.BUSINESS_DATABASES)
        self.assertEqual(tuple(ap.CHECK_DB), g.PG65_APPLY_CHECK_IDS)
        self.assertTrue(all(re.fullmatch(r"jp_vocab_test_apply_[a-z0-9]+", db) for db in T.databases))
        needs_db = set(ap.PLANNED) - {"b1", "h1"}                     # b1 / h1 read other checks' evidence
        self.assertEqual(needs_db | {"c1p"}, set(ap.CHECK_DB))
        self.assertNotIn(T.admin, T.provider_roles)

    def test_runner_takes_no_target_from_arguments_or_environment(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(ap.main(["check", "--port", "55432"]), 2)
            self.assertEqual(ap.main([]), 2)
        source = inspect.getsource(ap)
        self.assertNotIn("argparse", source)
        self.assertNotIn("os.environ.get(", source)


# --- 2. business connection matrix ---------------------------------------------------------------------------

GOOD = {"host": "localhost", "port": "55492", "dbname": "jp_vocab_test_apply_a2", "user": "jpvm_write",
        "sslmode": "verify-full"}


class BusinessMatrix(Blocked):
    def refused(self, code, **changes):
        with self.assertRaises(g.Pg62Refused) as caught:
            ap.business_check({**GOOD, **changes})
        self.assertEqual(caught.exception.code, code)

    def test_allowed(self):
        ap.business_check(GOOD)
        ap.business_check({**GOOD, "user": "jpvm_read", "dbname": "jp_vocab_test_apply_g4"})

    def test_refusals(self):
        for port in ("55432", "55462", "55472", "55482", "5432"):
            self.refused("pg62_port_refused", port=port)
        for db in (ap.TEMPLATE, "postgres", "jp_vocab_test_e", "jp_vocab_test_62a", "jp_vocab_test_apply_zz"):
            self.refused("pg62_database_refused", dbname=db)
        for role in (T.admin, ap.OWNER, "jpvb_audit", "postgres"):
            self.refused("pg62_role_refused", user=role)
        for host in ("127.0.0.1", "db.example.test", ""):
            self.refused("pg62_host_refused", host=host)
        for mode in ("require", "verify-ca", "disable", None):
            self.refused("pg62_tls_mode_refused", sslmode=mode)

    def test_pg_environment(self):
        with mock.patch.dict(os.environ, {"PGHOST": "elsewhere"}):
            self.refused("pg62_pg_environment_present")
            with self.assertRaises(g.Pg62Refused):
                ap.require_ours({"postmaster_pid": PID})


# --- 3. record and live facts: any difference, nothing after it -----------------------------------------------

class FakeCursor:
    def __init__(self, row):
        self.row = row

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, *a, **k):
        return self

    def fetchone(self):
        return self.row


class FactsConn:
    def __init__(self, row):
        self.row, self.closed, self.rolled_back = row, False, 0

    def cursor(self, **_):
        return FakeCursor(self.row)

    def rollback(self):
        self.rolled_back += 1

    def close(self):
        self.closed = True


class RecordAndLive(Blocked):
    def test_bound_record_is_accepted(self):
        rec, target = self.record()
        self.assertEqual(ap.require_target_bound(rec, (rec.folder / "target.json").read_bytes())["port"], T.port)

    def test_record_differences_are_refused(self):
        for changes in ({"port": 55482}, {"host": "127.0.0.1"}, {"data": "C:/JV_Tools/pg64/data"},
                        {"postgres_exe": "C:/other/postgres.exe"}, {"provider_roles": [ap.WRITE]},
                        {"databases": {ap.TEMPLATE: {}}}):
            with self.subTest(changes=changes):
                rec, _ = self.record(**changes)
                with self.assertRaises(g.Pg62Refused):
                    ap.require_target_bound(rec, (rec.folder / "target.json").read_bytes())
        rec, _ = self.record()
        with self.assertRaises(g.Pg62Refused):                       # bytes differ from the recorded hash
            ap.require_target_bound(rec, (rec.folder / "target.json").read_bytes() + b" ")
        rec.event("target_written", sha256="0" * 64)                 # two writes: ambiguous
        with self.assertRaises(g.Pg62Refused):
            ap.require_target_bound(rec, (rec.folder / "target.json").read_bytes())

    def test_live_server_must_be_the_recorded_one(self):
        ap.require_ours({"postmaster_pid": PID})
        with self.assertRaises(g.Pg62Refused):
            ap.require_ours({"postmaster_pid": PID + 1})

    def test_post_connect_facts(self):
        _, target = self.record()
        db = ap.BUSINESS_DATABASES[0]
        facts = {"server_addr": "127.0.0.1", "server_port": T.port, "version": "180006", "dbname": db,
                 "db_oid": target["databases"][db]["oid"], "role_oid": 102,
                 "object_oids": [target["databases"][db]["objects"][t] for t in sorted(ap.OID_TABLES)],
                 "identity": [target["databases"][db]["identity_value"]]}
        conn = FactsConn(facts)
        ap.post_connect_check(conn, target, ap.WRITE)
        self.assertEqual((conn.closed, conn.rolled_back), (False, 1))
        for key, value in (("server_addr", "10.0.0.1"), ("server_port", 55482), ("version", "170000"),
                           ("db_oid", 1), ("role_oid", 101), ("object_oids", [1, 2, 3, 4, 5]),
                           ("identity", ["pg65-other"]), ("identity", []), ("dbname", ap.TEMPLATE)):
            with self.subTest(key=key, value=value):
                conn = FactsConn({**facts, key: value})
                with self.assertRaises(g.Pg62Refused) as caught:
                    ap.post_connect_check(conn, target, ap.WRITE)
                self.assertEqual((caught.exception.code, conn.closed), ("pg62_connected_target_mismatch", True))

    def test_record_mismatch_stops_before_any_check(self):
        rec, _ = self.record()
        (rec.folder / "target.json").write_bytes(b"{}")              # differs from the recorded hash
        calls = []
        checks = [(n, lambda h, n=n: calls.append(n) or {}) for n in ap.PLANNED]
        out = io.StringIO()
        with mock.patch.object(g, "single_run", lambda target: rec), mock.patch.object(ap, "CHECKS", checks), \
                mock.patch.object(ap, "g0_gate", lambda h: calls.append("gate") or {}), contextlib.redirect_stdout(out):
            self.assertEqual(ap.main(["check"]), 1)
        self.assertEqual((calls, rec.doc["results"]), ([], []))

    def test_server_not_ours_stops_before_any_check(self):
        rec, _ = self.record(postmaster_pid=PID + 1)
        calls = []
        out = io.StringIO()
        with mock.patch.object(g, "single_run", lambda target: rec), \
                mock.patch.object(ap, "g0_gate", lambda h: calls.append("gate") or {}), contextlib.redirect_stdout(out):
            self.assertEqual(ap.main(["check"]), 1)
        self.assertEqual(calls, [])


# --- 4. admin and business paths are separate -------------------------------------------------------------------

class Separation(Blocked):
    def test_admin_databases(self):
        self.assertIn(ap.TEMPLATE, ap.ADMIN_DATABASES)
        with self.assertRaises(g.Pg62Refused):
            ap.admin("jp_vocab_test_e", PID)
        with mock.patch.object(g, "admin_connect", lambda *a, **k: "admin") as _:
            self.assertEqual(ap.admin(ap.TEMPLATE, PID), "admin")

    def test_hba(self):
        lines = ap.hba().splitlines()
        business = [l for l in lines if "scram-sha-256" in l]
        admin = [l for l in lines if "sspi" in l]
        self.assertEqual(len(business), 2)
        for line in business:
            dbs, roles = line.split()[1].split(","), line.split()[2].split(",")
            self.assertEqual((set(dbs), set(roles)), (set(ap.BUSINESS_DATABASES), set(ap.BUSINESS_ROLES)))
        for line in admin:
            self.assertEqual(line.split()[2], T.admin)
            self.assertIn(ap.TEMPLATE, line.split()[1].split(","))
        self.assertTrue(lines[-1].startswith("host all all ::0/0 reject"))

    def test_variants_are_closed_and_reverted(self):
        for name, (apply, revert) in ap.VARIANTS.items():
            self.assertTrue(apply and revert, name)
            for phase in ("apply", "revert"):
                rendered = [s.as_string(None) for s in ap.variant_statements(name, phase)]
                self.assertTrue(all(ap.WRITE in r and "CASCADE" not in r.upper() for r in rendered), name)
            self.assertTrue(set(ap.VARIANT_DATABASES[name]) <= set(ap.CHECK_DB))
        # a table-level REVOKE UPDATE also drops column UPDATEs: the contract column comes back
        self.assertIn("GRANT UPDATE (updated_at) ON public.users TO {w}", ap.VARIANTS["b3_users_table"][1])
        with self.assertRaises(ap.CheckFailed):
            ap.variant_statements("grant_everything", "apply")

    def test_revert_failure_is_a_harness_defect(self):
        h = object.__new__(ap.Harness)
        h.rec = mock.Mock()

        def variant(name, phase):
            if phase == "revert":
                raise psycopg.OperationalError("synthetic")
        h.variant = variant
        with self.assertRaises(ap.CheckFailed) as caught:
            ap.Harness.with_variant(h, "b2_lock_column", lambda: "ran")
        self.assertEqual(caught.exception.kind, "harness_defect")


# --- 5. expectations: contract constants and schema source ------------------------------------------------------

class Expectations(Blocked):
    def test_privileges_are_the_contract(self):
        db = ap.CHECK_DB["a2"]
        read, write = ap.expected_profiles(db)
        connect = {("database", "", db, "", "CONNECT")}
        self.assertEqual(read.privileges, frozenset(cli.READ_PRIVILEGES | connect))
        self.assertEqual(write.privileges, frozenset(cli.WRITE_PRIVILEGES | connect))
        self.assertIn(("table", "public", "users", "updated_at", "UPDATE"), write.privileges)
        self.assertNotIn(("table", "public", "users", "", "UPDATE"), write.privileges)
        with self.assertRaises(g.Pg62Refused):
            ap.expected_profiles(ap.TEMPLATE)

    def test_grants_are_one_per_contract_tuple(self):
        db = ap.CHECK_DB["a2"]
        read, write = ap.expected_profiles(db)
        grants = [s.as_string(None) for s in ap.contract_grants(db)]
        self.assertEqual(len(grants), len(read.privileges) + len(write.privileges))
        self.assertIn('GRANT UPDATE ("updated_at") ON "public"."users" TO "jpvm_write"', grants)
        self.assertTrue(all("CASCADE" not in s.upper() and " ALL " not in s for s in grants))
        with self.assertRaises(ap.CheckFailed):
            ap.grant_statements(frozenset({("table", "public", "users", "", "DELETE")}), ap.WRITE)

    def test_objects_are_the_schema_source(self):
        database = (BACKEND / "app" / "database.py").read_text(encoding="utf-8")
        pg = database[database.index("def create_postgres_tables"):]
        pg = pg[:pg.index("\ndef ", 1)]
        schema = (BACKEND / "app" / "srs" / "schema.py").read_text(encoding="utf-8")
        tables = set(re.findall(r"CREATE TABLE IF NOT EXISTS (\w+) \(", pg)) \
            | set(re.findall(r"CREATE TABLE IF NOT EXISTS (\w+) \(", schema))
        objects = ap.expected_objects(ap.CHECK_DB["a2"])
        self.assertEqual({o[2] for o in objects if o[0] == "table" and o[1] == "public"}, tables)
        self.assertTrue({("sequence", "public", "srs_migration_runs_id_seq"),
                         ("sequence", "public", "srs_migration_snapshots_id_seq")} <= objects)

    def test_seed_columns_exist(self):
        database = (BACKEND / "app" / "database.py").read_text(encoding="utf-8")
        pg = database[database.index("def create_postgres_tables"):]
        for statement in ap.SEED:
            table, columns = re.match(r"INSERT INTO (\w+) \(([^)]*)\)", statement).groups()
            ddl = pg[pg.index(f"CREATE TABLE IF NOT EXISTS {table} ("):]
            ddl = ddl[:ddl.index("\n        )")]
            for column in (c.strip() for c in columns.split(",")):
                self.assertRegex(ddl, rf"\n\s+{column} ", f"{table}.{column}")
            self.assertNotIn("CASCADE", statement.upper())

    def test_no_cascade_or_process_search_in_the_runner(self):
        source = inspect.getsource(ap)
        code = source[source.index('"""', source.index('"""') + 3) + 3:]   # after the module docstring
        for word in ("CASCADE", "taskkill", "pg_terminate_backend", "psutil", "pg_cancel_backend", "DROP "):
            self.assertNotIn(word, code)


# --- 6. where a refusal happened is counted per stage ---------------------------------------------------------

class FakeInfo:
    backend_pid = 4242


class FakeConn:
    def __init__(self):
        self.info, self.sent, self.commits = FakeInfo(), [], 0

    def execute(self, query, *a, **k):
        self.sent.append(query)
        return FakeCursor(None)

    def cursor(self, *a, **k):
        conn = self

        class C(FakeCursor):
            def execute(self, query, *a, **k):
                conn.sent.append(query)
                return self
        return C(None)

    def commit(self):
        self.commits += 1


class Stages(Blocked):
    def test_counting_starts_at_the_hand_over(self):
        counts = ap.Counts()
        raw = FakeConn()
        tracked = ap.Tracked(raw, counts, ap.WRITE, [])
        tracked.execute("SELECT 1")                                   # the provider's observation: not counted
        tracked.activate()
        tracked.execute("SELECT id FROM users WHERE id = %s FOR UPDATE", (7,))
        with tracked.cursor() as cursor:
            cursor.execute(sql.SQL("INSERT INTO {} DEFAULT VALUES").format(sql.Identifier("x")))
        tracked.execute(b"UPDATE x")                                   # unsupported form: counted as UNKNOWN
        tracked.execute("COMMIT")
        tracked.commit()
        self.assertEqual(counts.words[ap.WRITE], {"SELECT": 1, "INSERT": 1, "UNKNOWN": 1, "COMMIT": 1})
        self.assertEqual(counts.role(ap.WRITE)["commits"], 2)
        self.assertEqual(len(raw.sent), 5)                            # everything was forwarded

    def test_stage_labels(self):
        base = {"created": 0, "handed": 0, "statements": 0, "writes": 0, "commits": 0}
        self.assertEqual(ap.rejection_stage(base), "before_connect")
        self.assertEqual(ap.rejection_stage({**base, "created": 1}), "after_observation")
        self.assertEqual(ap.rejection_stage({**base, "created": 1, "handed": 1, "statements": 4}), "under_product_lock")
        self.assertEqual(ap.rejection_stage({**base, "created": 1, "handed": 1, "statements": 4, "writes": 1}),
                         "rolled_back_after_write")
        self.assertEqual(ap.rejection_stage({**base, "created": 1, "handed": 1, "writes": 1, "commits": 1}),
                         "committed")

    def run_connector(self, *, refuse_at_observation=False, inject=None, after=None):
        counts, trackers, exits = ap.Counts(), [], []

        class Context:
            def __enter__(self):
                return "product connection"

            def __exit__(self, *exc):
                exits.append(exc[0])
                return False

        def fake_connector(inputs, expected, driver):
            def connector(*, read_only=False):
                counts.created[ap.WRITE] += 1                         # the guarded driver ran
                if refuse_at_observation:
                    raise cli.pc.OpsProductConnectionError("observed_privileges_excess")
                trackers.append(ap.Tracked(FakeConn(), counts, ap.WRITE, []))
                return Context()
            return connector
        inputs = mock.Mock(command=cli.APPLY_COMMAND)
        connect = ap.counted_connector(counts, trackers, inject, after, real=fake_connector)(inputs, None, None)
        return counts, trackers, exits, connect

    def test_refusal_after_observation_is_not_a_hand_over(self):
        counts, trackers, _, connect = self.run_connector(refuse_at_observation=True)
        with self.assertRaises(cli.pc.OpsProductConnectionError):
            connect(read_only=False)
        self.assertEqual(ap.rejection_stage(counts.role(ap.WRITE)), "after_observation")

    def test_hand_over_activates_and_injection_runs_the_real_exit(self):
        seen = []
        counts, trackers, exits, connect = self.run_connector(inject=lambda role, n: n == 2,
                                                              after=lambda role, n: seen.append((role, n)))
        with connect(read_only=False) as product:
            self.assertEqual(product, "product connection")
        self.assertTrue(trackers[0].active)
        with self.assertRaises(ap.InjectedFault):
            with connect(read_only=False):
                pass
        self.assertEqual((counts.handed[ap.WRITE], exits), (2, [None, ap.InjectedFault]))
        self.assertEqual(seen, [(ap.WRITE, 1)])                      # only after a clean exit

    def test_three_refusal_places_are_told_apart(self):
        before_connect = ap.Counts()
        observed = ap.Counts()
        observed.created[ap.WRITE] = 1
        locked = ap.Counts()
        locked.created[ap.WRITE] = locked.handed[ap.WRITE] = 1
        locked.words[ap.WRITE] = {"SELECT": 4}
        labels = [ap.rejection_stage(c.role(ap.WRITE)) for c in (before_connect, observed, locked)]
        self.assertEqual(labels, ["before_connect", "after_observation", "under_product_lock"])


# --- 7. contention: the winner's changes are not the refused run's ------------------------------------------

def facts(runs=(), snapshots=0, versions=None):
    return {"runs": list(runs), "snapshots": snapshots, "versions": versions or {"personal:1": 0, "personal:2": 0}}


WINNER = {"id": 1, "mode": "apply", "status": "completed", "scope_md5": "s"}


class Attribution(Blocked):
    def judge(self, after, before=None, commits=0):
        return ap.attributed_changes(before or facts(), after, winner_applied=2, winner_scope="s",
                                     refused_commits=commits)

    def test_winner_changes_are_not_violations(self):
        self.assertEqual(self.judge(facts([WINNER], 2, {"personal:1": 1, "personal:2": 1})), [])

    def test_changes_that_can_belong_to_the_refused_run(self):
        good = {"personal:1": 1, "personal:2": 1}
        self.assertEqual(self.judge(facts([WINNER, dict(WINNER, id=2)], 2, good)), ["run_rows"])
        self.assertEqual(self.judge(facts([dict(WINNER, scope_md5="t")], 2, good)), ["run_scope"])
        self.assertEqual(self.judge(facts([WINNER], 3, good)), ["snapshots"])
        self.assertEqual(self.judge(facts([WINNER], 2, {"personal:1": 2, "personal:2": 1})), ["card_versions"])
        self.assertEqual(self.judge(facts([WINNER], 2, good), commits=1), ["refused_commits"])
        self.assertEqual(self.judge(facts([WINNER], 2, good), before=facts([WINNER])), ["run_rows"])


class Contention(Blocked):
    def test_wait_proof(self):
        ticks = iter(range(100))
        self.assertEqual(ap.wait_blocked(lambda pid: [10], lambda: 20, 10, limit=5, clock=lambda: next(ticks),
                                         sleep=lambda s: None), 20)
        ticks = iter(range(100))
        with self.assertRaises(ap.CheckFailed) as caught:
            ap.wait_blocked(lambda pid: [99], lambda: 20, 10, limit=5, clock=lambda: next(ticks), sleep=lambda s: None)
        self.assertEqual(caught.exception.kind, "harness_defect")

    def test_failed_proof_releases_joins_and_judges_nothing(self):
        pause = ap.Pause(ap.WRITE, "SELECT", "SELECT id", limit=2)

        def first():
            pause.hook(ap.WRITE, "SELECT", "SELECT id FROM users", mock.Mock(pending_pid=1))
            return ("a", 0)

        def prove():
            raise ap.CheckFailed("harness_defect", "waiting partner not proven")
        closed = []
        with self.assertRaises(ap.CheckFailed):
            ap.race(first, lambda: ("b", 4), pause, prove, lambda: closed.append(1), limit=2)
        self.assertTrue(pause.release.is_set())
        self.assertEqual(closed, [])                                  # both threads ended: nothing to close

    def test_first_run_never_holding_is_a_harness_defect(self):
        pause = ap.Pause(ap.WRITE, "SELECT", "SELECT id", limit=0.2)
        with self.assertRaises(ap.CheckFailed) as caught:
            ap.race(lambda: ("a", 0), lambda: ("b", 4), pause, lambda: {}, lambda: None, limit=0.2)
        self.assertEqual(caught.exception.kind, "harness_defect")
        self.assertTrue(pause.release.is_set())

    def test_hung_run_closes_tracked_connections(self):
        pause = ap.Pause(ap.WRITE, "SELECT", "SELECT id", limit=0.3)
        stuck = threading.Event()

        def first():
            pause.hook(ap.WRITE, "SELECT", "SELECT id FROM users", mock.Mock(pending_pid=1))
            return ("a", 0)
        closed = []

        def close_all():
            closed.append(1)
            stuck.set()                                               # closing the connection ends the wait
        with self.assertRaises(ap.CheckFailed):
            ap.race(first, lambda: stuck.wait(5) and ("b", 4), pause, lambda: {"ok": True}, close_all, limit=0.3)
        self.assertEqual(closed, [1])

    def test_success(self):
        pause = ap.Pause(ap.WRITE, "SELECT", "SELECT id", limit=2)

        def first():
            pause.hook(ap.WRITE, "SELECT", "SELECT id FROM users", mock.Mock(pending_pid=1))
            return ("a", 0)
        a, b, proof = ap.race(first, lambda: ("b", 4), pause, lambda: {"waiter": "B"}, lambda: None, limit=2)
        self.assertEqual((a, b, proof, pause.holder_pid), (("a", 0), ("b", 4), {"waiter": "B"}, 1))


# --- 8. gate, recording and exit status ---------------------------------------------------------------------------

class FakeHarness:
    def __init__(self, rec):
        self.rec = rec

    def start(self):
        pass

    def close(self):
        pass


class ExitStatus(Blocked):
    def run_check(self, *, gate=lambda h: {"gate": 1}, failing=None, record_fail=None, readback_fail=None,
                  planned=None):
        rec, _ = self.record()
        calls = []

        def make(name):
            def fn(h):
                calls.append(name)
                if name == failing:
                    raise ap.CheckFailed("product_defect", "synthetic")
                return {}
            return fn
        checks = [(n, make(n)) for n in (planned or ap.PLANNED)]
        real_result = rec.result

        def result(check, status, *a, **k):
            if check == record_fail and status == "pass":
                raise OSError("disk")
            return real_result(check, status, *a, **k)
        rec.result = result
        real_loads = json.loads

        def loads(text, *a, **k):
            doc = real_loads(text, *a, **k)
            if readback_fail and isinstance(doc, dict) and doc.get("results") \
                    and doc["results"][-1].get("check") == readback_fail:
                doc["results"][-1]["status"] = "lost"
            return doc
        out = io.StringIO()
        with mock.patch.object(g, "single_run", lambda target: rec), mock.patch.object(ap, "Harness", FakeHarness), \
                mock.patch.object(ap, "CHECKS", checks), mock.patch.object(ap, "g0_gate", gate), \
                mock.patch.object(ap.json, "loads", loads), contextlib.redirect_stdout(out):
            code = ap.main(["check"])
        return code, calls, rec, out.getvalue()

    def test_all_pass_and_the_gate_is_not_counted(self):
        code, calls, rec, out = self.run_check()
        self.assertEqual((code, calls), (0, list(ap.PLANNED)))
        self.assertIn(f"passed {len(ap.PLANNED)} / {len(ap.PLANNED)}", out)
        self.assertEqual(rec.doc["results"][0]["check"], ap.GATE)

    def test_gate_failure_runs_nothing(self):
        def gate(h):
            raise ap.CheckFailed("preparation_failure", "intended qualities")
        code, calls, _, out = self.run_check(gate=gate)
        self.assertEqual((code, calls), (1, []))
        self.assertIn("passed 0", out)

    def test_failure_record_and_readback_failures_stop_everything_after(self):
        for kwargs in ({"failing": "d1"}, {"record_fail": "d1"}, {"readback_fail": "d1"}):
            with self.subTest(**kwargs):
                code, calls, _, _ = self.run_check(**kwargs)
                self.assertEqual(code, 1)
                self.assertEqual(calls, list(ap.PLANNED[:ap.PLANNED.index("d1") + 1]))

    def test_probe_failure_is_a_harness_defect_and_stops(self):
        def probe_fails(h):
            raise psycopg.OperationalError("synthetic probe")
        rec, _ = self.record()
        self.assertFalse(ap.run_recorded(rec, "b2", probe_fails, None))
        self.assertEqual(rec.doc["results"][-1]["kind"], "harness_defect")

    def test_incomplete_checklist_is_a_failure(self):
        code, calls, _, out = self.run_check(planned=ap.PLANNED[:-1])
        self.assertEqual(code, 1)
        self.assertIn("STOP", out)


# --- 9. cleanup: anything not as recorded, nothing deleted -----------------------------------------------------

class Cleanup(Blocked):
    def run_cleanup(self, rec):
        out = io.StringIO()
        with mock.patch.object(g, "single_run", lambda target: rec), mock.patch.object(shutil, "rmtree", forbidden), \
                mock.patch.object(ap.base, "run", forbidden), contextlib.redirect_stdout(out):
            return ap.main(["cleanup"]), out.getvalue()

    def test_target_pid_differs_from_the_recorded_start(self):
        rec, _ = self.record(postmaster_pid=PID + 1)
        self.assertEqual(self.run_cleanup(rec)[0], 1)

    def test_live_server_not_ours(self):
        rec, _ = self.record()
        with mock.patch.object(g, "postmaster_pid", lambda target: PID), \
                mock.patch.object(g, "server_is_ours", lambda pid, target=None: False):
            code, out = self.run_cleanup(rec)
        self.assertEqual(code, 1)
        self.assertIn("live server matches the record", out)

    def test_target_file_changed(self):
        rec, _ = self.record()
        (rec.folder / "target.json").write_bytes(b'{"port": 55492}')
        self.assertEqual(self.run_cleanup(rec)[0], 1)


# --- 10. import does nothing; default and operation entry points keep refusing ---------------------------------

class ImportOnly(unittest.TestCase):
    def test_import_does_no_external_work(self):
        code = (f"import sys, os, subprocess; sys.path[:0] = [{str(BACKEND / 'scripts')!r}, {str(TESTS_DIR)!r}]\n"
                "import psycopg\ncalls = []\n"
                "def fail(*a, **k): calls.append(1); raise AssertionError('external work at import')\n"
                "psycopg.connect = fail; subprocess.run = fail; subprocess.Popen = fail; os.mkdir = fail\n"
                "import _ops_apply_real\nprint('CALLS', len(calls), 'APP', any(m == 'app' or m.startswith('app.') "
                "for m in sys.modules))")
        # the child blocks connect / processes / mkdir itself before importing the runner
        done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120,
                              cwd=str(TESTS_DIR), env={k: v for k, v in os.environ.items() if k != "PYTHONPATH"})
        self.assertIn("CALLS 0 APP False", done.stdout, done.stderr[-500:])
        self.assertFalse(T.root.exists())


class EntryPoints(Blocked):
    def test_command_line_apply_still_has_no_connection(self):
        files = [self.folder / n for n in ("plan.json", "e.json", "e.sig")]
        for f in files:
            f.write_bytes(b"{}")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = cli.main(["apply", "--account", "7", "--run-key", "mig-1", "--personal-id", "1", "--batch-size", "1",
                             "--plan", str(files[0]), "--backup-evidence", str(files[1]),
                             "--backup-signature", str(files[2])])
        self.assertEqual((code, json.loads(out.getvalue())["code"]), (4, "connection_not_available"))

    def test_provider_default_and_operation_mode_refuse(self):
        with self.assertRaises(pv.OpsProviderRefused) as caught:
            pv.provide_connection(object(), expected=None)
        self.assertEqual(caught.exception.code, "mode_not_synthetic")



# --- C12-1 review fixes (2026-10-27): regressions written before the fix -------------------------------------
# All fakes: control flow and counting only, never evidence of real PostgreSQL behaviour.

from datetime import datetime, timezone  # noqa: E402
from types import SimpleNamespace  # noqa: E402

AT = datetime(2026, 10, 21, 12, 30, tzinfo=timezone.utc)
EXPIRED = datetime(2026, 10, 21, 12, 40, tzinfo=timezone.utc)


@dataclasses.dataclass(frozen=True)
class FakeInputs:
    command: str
    now: object = None
    args: dict = dataclasses.field(default_factory=lambda: {"batch_size": "1"})


class HeldConn(FakeConn):
    """A fake connection with its own backend pid; its lock statement can wait on an event."""
    pids = iter(range(5000, 6000))

    def __init__(self, wait=None):
        super().__init__()
        self.info = SimpleNamespace(backend_pid=next(HeldConn.pids))
        self.wait = wait

    def execute(self, query, *a, **k):
        if self.wait is not None and isinstance(query, str) and query.startswith(ap.LOCK_PREFIX):
            self.wait.wait(5)                                         # a lock wait, until the holder lets go
        return super().execute(query, *a, **k)


class Ctx:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self.conn

    def __exit__(self, *exc):
        return False


class CardsFormat(Blocked):
    def test_facts_reads_the_request_tuples(self):
        request = cli.make_request(7, "c12-apply-1", [3, 1], [9])
        self.assertEqual(request.cards, (("lexeme", 9), ("personal", 1), ("personal", 3)))   # (kind, ref_id)
        h = object.__new__(ap.Harness)
        h.pid = PID
        seen = {}

        @contextlib.contextmanager
        def admin(db, pid, autocommit=True):
            yield "conn"

        def run_facts(conn, run_key, cards, account_id):
            seen.update(run_key=run_key, cards=cards)
            return {}
        with mock.patch.object(ap, "admin", admin), mock.patch.object(ap, "run_facts", run_facts):
            ap.Harness.facts(h, SimpleNamespace(db=ap.CHECK_DB["a2"], request=request))
        self.assertEqual(seen, {"run_key": "c12-apply-1", "cards": {"personal": [1, 3], "lexeme": [9]}})


class RequestNumbers(Blocked):
    """Through the real CLI `_timed_connector`, which builds a new factory for every connection request."""

    def setup_run(self, refuse=lambda inputs: None):
        counts, trackers, times = ap.Counts(), [], []

        def real(inputs, expected, driver):
            def connector(*, read_only=False):
                times.append((inputs.command, inputs.now))
                code = refuse(inputs)
                if code:
                    raise cli.pc.OpsProductConnectionError(code)
                role = ap.WRITE if inputs.command == cli.APPLY_COMMAND else ap.READ
                counts.created[role] += 1
                conn = HeldConn()
                trackers.append(ap.Tracked(conn, counts, role, []))
                return Ctx(conn)
            return connector
        return counts, trackers, times, real

    def test_numbers_per_run_and_role(self):
        counts, trackers, times, real = self.setup_run()
        seen = []
        scopes = ap.RunScopes(real=real)
        with scopes.installed(), scopes.run(counts, trackers, after=lambda role, n: seen.append((role, n))):
            write = cli._timed_connector(FakeInputs("apply"), None, None, lambda: AT)
            read = cli._timed_connector(FakeInputs("dry_run"), None, None, lambda: AT)
            for connect in (read, write, write, write):
                with connect(read_only=connect is read):
                    pass
        self.assertEqual(seen, [(ap.READ, 1), (ap.WRITE, 1), (ap.WRITE, 2), (ap.WRITE, 3)])
        other = []                                                    # a second run starts from 1 again
        with scopes.installed(), scopes.run(ap.Counts(), trackers, after=lambda role, n: other.append(n)):
            with cli._timed_connector(FakeInputs("apply"), None, None, lambda: AT)(read_only=False):
                pass
        self.assertEqual(other, [1])

    def test_clock_moved_after_card_one_is_used_by_the_very_next_request(self):
        state = {"now": AT, "moves": 0}
        counts, trackers, times, real = self.setup_run(
            refuse=lambda inputs: "preflight_approval_expired" if inputs.now >= EXPIRED else None)

        def after(role, n):
            if role == ap.WRITE and n == 2:
                state["now"], state["moves"] = EXPIRED, state["moves"] + 1
        scopes = ap.RunScopes(real=real)
        with scopes.installed(), scopes.run(counts, trackers, after=after):
            tracked = cli._Tracked(cli._timed_connector(FakeInputs("apply"), None, None, lambda: state["now"]))
            with self.assertRaises(cli.pc.OpsProductConnectionError):
                for _ in range(5):                                    # run row, cards 1..3, finish
                    with tracked(read_only=False):
                        pass
        self.assertEqual([t for _, t in times], [AT, AT, EXPIRED])  # request 3 already carries the new time
        self.assertEqual((state["moves"], tracked.first_committed, tracked.opened), (1, True, 2))


class FakeProductHarness:
    """e3 / g2 with fakes: the real counted connector and CLI timed connector, a product-shaped loop
    (run row, three cards, finish), and a provider stand-in that refuses by time or by privilege state."""

    def __init__(self):
        self.revoked, self.variants, self.times, self.committed_cards = False, [], [], 0

    def case(self, check_id, *a, **k):
        return SimpleNamespace(check_id=check_id)

    def facts(self, case):
        return {"snapshots": self.committed_cards}

    def variant(self, name, phase):
        self.variants.append((name, phase))
        self.revoked = phase == "apply"

    def apply(self, case, *, clock=None, inject=None, after=None, hooks=None):
        counts, trackers = ap.Counts(), []
        harness = self

        def real(inputs, expected, driver):
            def connector(*, read_only=False):
                harness.times.append(inputs.now)
                if inputs.now >= EXPIRED:
                    raise cli.pc.OpsProductConnectionError("preflight_approval_expired")
                if harness.revoked:
                    raise cli.pc.OpsProductConnectionError("observed_privileges_missing")
                counts.created[ap.WRITE] += 1
                conn = HeldConn()
                trackers.append(ap.Tracked(conn, counts, ap.WRITE, []))
                return Ctx(conn)
            return connector
        scopes = ap.RunScopes(real=real)
        with scopes.installed(), scopes.run(counts, trackers, inject=inject, after=after):
            tracked = cli._Tracked(cli._timed_connector(FakeInputs("apply"), None, None, clock or (lambda: AT)))
            try:
                for index in range(5):
                    with tracked(read_only=False):
                        pass
                    if 1 <= index <= 3:
                        self.committed_cards += 1
                return {"phase": "completed"}, 0, counts
            except cli.pc.OpsProductConnectionError as error:
                started = tracked.first_committed or tracked.opened > 1
                return ({"code": error.code, "phase": "after_start" if started else "before_first_write",
                         "uncertain": started}, 1 if started else 4, counts)


class InjectionTiming(Blocked):
    def test_e3_expiry_takes_effect_at_card_two(self):
        h = FakeProductHarness()
        self.assertEqual(ap.e3_expiry_after_start(h), {"snapshots": 1})   # card 1 committed, card 2 refused
        self.assertEqual(h.times, [ap.T0, ap.T0, EXPIRED])               # the very next request is judged late

    def test_g2_revoke_once_after_card_one(self):
        h = FakeProductHarness()
        self.assertEqual(ap.g2_revoked_between_cards(h), {"code": "observed_privileges_missing"})
        self.assertEqual(h.variants, [("g2_card_column", "apply"), ("g2_card_column", "revert")])
        self.assertEqual((h.committed_cards, len(h.times)), (1, 3))


class ContentionScopes(Blocked):
    def test_overlapping_runs_keep_their_own_counts(self):
        pause = ap.Pause(ap.WRITE, "SELECT", ap.LOCK_PREFIX, limit=3)
        first = SimpleNamespace(request=SimpleNamespace(run_key="k"), write=FakeInputs("apply"), read=None,
                                db=ap.CHECK_DB["f2"], folder="", evidence=("", ""), plan_file="plan.json")
        second = SimpleNamespace(request=SimpleNamespace(run_key="k"), write=FakeInputs("apply", now=1), read=None,
                                 db=ap.CHECK_DB["f2"], folder="", evidence=("", ""), plan_file="plan.json")
        pids = {}

        class H:
            def driver(self, inputs, counts, trackers, hooks):
                def connect():
                    is_b = inputs is second.write
                    conn = HeldConn(wait=pause.release if is_b else None)
                    pids["B" if is_b else "A"] = conn.info.backend_pid
                    counts.created[ap.WRITE] += 1
                    tracked = ap.Tracked(conn, counts, ap.WRITE, hooks)
                    trackers.append(tracked)
                    return tracked                                    # as the real guarded driver does
                return connect

            def facts(self, case):
                return {"runs": []}

            def blocking(self, pid):
                return [pids["A"]] if pid == pids.get("B") else []

            def waits(self, pid):
                return [{"locktype": "tuple", "granted": False}]

            def close_connections(self):
                pass

        def real(inputs, expected, driver):
            def connector(*, read_only=False):
                return Ctx(driver())
            return connector

        open_runs, overlap = set(), []

        def run_apply(request, *, write_inputs, driver, **kw):
            name = "B" if write_inputs is second.write else "A"
            with cli._product_connector(write_inputs, None, driver)(read_only=False) as conn:
                open_runs.add(name)
                if name == "B":
                    overlap.append("A" in open_runs)                  # A still holds its connection
                conn.execute(ap.LOCK_PREFIX + "%s FOR UPDATE", (7,))  # A pauses here; B waits here
                conn.execute("SELECT * FROM srs_migration_runs WHERE run_key = %s", ("k",))
                open_runs.discard(name)
            return {"run": name}, 0

        with mock.patch.object(ap, "ORIGINAL_CONNECTOR", real, create=True),                 mock.patch.object(cli, "_product_connector", real), mock.patch.object(cli, "run_apply", run_apply):
            a, b, proof, counts_a, counts_b, _ = ap.contention(H(), "f2", first, second, pause)
            self.assertIs(cli._product_connector, real)               # the race's one wrapper was removed
        self.assertEqual((a[0]["run"], b[0]["run"], overlap), ("A", "B", [True]))
        for counts in (counts_a, counts_b):
            self.assertEqual(counts.role(ap.WRITE), {"created": 1, "handed": 1, "statements": 2, "writes": 0,
                                                     "commits": 0})
        self.assertEqual(proof["waiter"], "B")


class StalePlan(Blocked):
    def test_b_plan_and_approval_are_made_before_a_applies(self):
        order, state = [], {"version": 0}

        class H:
            def case(self, check_id, *a, run_key=ap.RUN_KEY, **k):
                order.append(("case", run_key))
                return SimpleNamespace(run_key=run_key, plan_version=state["version"])

            def apply(self, case, **k):
                order.append(("apply", case.run_key))
                if case.run_key == ap.RUN_KEY:
                    state["version"] += 1                             # A commits: the cards change
                    return {"phase": "completed"}, 0, ap.Counts()
                stale = case.plan_version < state["version"]
                return ({"code": "plan_changed"} if stale else {"phase": "completed"}), (4 if stale else 0), ap.Counts()
        ap.f3_preliminary(H())
        self.assertEqual(order, [("case", ap.RUN_KEY), ("case", "c12-apply-2"), ("apply", ap.RUN_KEY),
                                 ("apply", "c12-apply-2")])


class PostConnectText(unittest.TestCase):
    """String checks only; not an execution check of the SQL on a real server."""

    def test_current_user_is_the_sql_keyword(self):
        self.assertIn("rolname OPERATOR(pg_catalog.=) CURRENT_USER", ap.POST_CONNECT)
        self.assertNotIn("pg_catalog.current_user", ap.POST_CONNECT)
        self.assertNotIn("pg_catalog.session_user", ap.POST_CONNECT)


# --- C12-1 review fixes 2 (2026-10-27): account-scoped card versions, an independent expected scope ----------

import hashlib as _hashlib  # noqa: E402
import sqlite3  # noqa: E402


class SqliteAsPg:
    """Runs run_facts' PostgreSQL text on an in-memory SQLite file so that REAL row selection happens:
    only the spellings run_facts uses are translated (schema prefix, `%s`, `= ANY (%s)`, `pg_catalog.md5`).
    Synthetic SQLite, not a check of the SQL on PostgreSQL."""

    def __init__(self):
        self.db = sqlite3.connect(":memory:")
        self.db.create_function("md5", 1, lambda v: _hashlib.md5(v.encode()).hexdigest())
        self.db.executescript(
            "CREATE TABLE srs_migration_runs (id INTEGER PRIMARY KEY, run_key TEXT, mode TEXT, status TEXT, "
            "scope_json TEXT);"
            "CREATE TABLE srs_migration_snapshots (id INTEGER PRIMARY KEY, run_id INTEGER);"
            "CREATE TABLE vocab_items (id INTEGER PRIMARY KEY, user_id INTEGER, srs_card_version INTEGER);"
            "CREATE TABLE user_word_progress (id INTEGER PRIMARY KEY, user_id INTEGER, lexeme_id INTEGER, "
            "srs_card_version INTEGER);")
        self.sent = []

    def execute(self, query, params=()):
        text = query.as_string(None) if isinstance(query, sql.Composable) else query
        self.sent.append((text, params))
        args = []
        for value in params:
            args.append(json.dumps(value) if isinstance(value, list) else value)
        text = (text.replace('"public".', "").replace("public.", "").replace("pg_catalog.md5", "md5")
                .replace("= ANY (%s)", "IN (SELECT value FROM json_each(%s))").replace("%s", "?"))
        return self.db.execute(text, args)


class AccountScopedVersions(Blocked):
    def sqlite(self):
        conn = SqliteAsPg()
        self.addCleanup(conn.db.close)                                # registered at once: runs on failure too
        return conn

    def make(self, order):
        conn = self.sqlite()
        rows = [(1, 10, 55, 1), (2, 20, 55, 0)]                       # accounts 10 and 20 share lexeme 55
        for row in (rows if order == "ab" else rows[::-1]):
            conn.db.execute("INSERT INTO user_word_progress VALUES (?, ?, ?, ?)", row)
        for row in ((101, 10, 3), (102, 20, 9)):
            conn.db.execute("INSERT INTO vocab_items VALUES (?, ?, ?)", row)
        return conn

    def test_same_lexeme_in_two_accounts(self):
        for order in ("ab", "ba"):
            with self.subTest(order=order):
                conn = self.make(order)
                a = ap.run_facts(conn, "k", {"personal": [], "lexeme": [55]}, 10)
                b = ap.run_facts(conn, "k", {"personal": [], "lexeme": [55]}, 20)
                self.assertEqual((a["versions"], b["versions"]), ({"lexeme:55": 1}, {"lexeme:55": 0}))

    def test_mixed_request_keeps_to_its_account(self):
        conn = self.make("ba")
        facts = ap.run_facts(conn, "k", {"personal": [101, 102], "lexeme": [55]}, 10)
        self.assertEqual(facts["versions"], {"personal:101": 3, "lexeme:55": 1})   # 102 is account 20's card
        card_queries = [(t, p) for t, p in conn.sent if "srs_card_version" in t]
        self.assertTrue(all('"user_id" = %s' in t and p[0] == 10 for t, p in card_queries))   # bound, not text

    def test_run_rows_stay_global_by_key(self):
        conn = self.make("ab")
        conn.db.execute("INSERT INTO srs_migration_runs VALUES (1, 'k', 'apply', 'completed', '{}')")
        conn.db.execute("INSERT INTO srs_migration_snapshots VALUES (1, 1)")
        facts = ap.run_facts(conn, "k", {"lexeme": [55]}, 20)          # the run is found whatever the account
        self.assertEqual((len(facts["runs"]), facts["snapshots"]), (1, 1))
        self.assertEqual(facts["runs"][0]["scope_md5"], _hashlib.md5(b"{}").hexdigest())

    def test_harness_passes_the_request_account(self):
        request = cli.make_request(7, "c12-apply-1", [1], [9])
        h = object.__new__(ap.Harness)
        h.pid = PID
        seen = {}

        @contextlib.contextmanager
        def admin(db, pid, autocommit=True):
            yield "conn"

        def run_facts(conn, run_key, cards, account_id):
            seen.update(account_id=account_id)
            return {}
        with mock.patch.object(ap, "admin", admin), mock.patch.object(ap, "run_facts", run_facts):
            ap.Harness.facts(h, SimpleNamespace(db=ap.CHECK_DB["a2"], request=request))
        self.assertEqual(seen, {"account_id": 7})


class ExpectedScope(Blocked):
    def setUp(self):
        super().setUp()
        pin_safe_app_environment(self)                                # before any app import; restored after

    def test_expected_scope_is_the_stored_form_of_the_plan(self):
        migration = import_app("app.srs.migration")
        with mock.patch.object(ap.pfile, "to_candidates", lambda plan: ("c1", "c2")), \
                mock.patch.object(migration, "_plan_json", lambda plan: "SCOPE:" + ",".join(plan)):
            self.assertEqual(ap.expected_scope_md5("plan"), _hashlib.md5(b"SCOPE:c1,c2").hexdigest())

    def run_f2(self, stored_scope, *, snapshots=2, bumps=1, refused_commits=0):
        order = []
        good = _hashlib.md5(b"A-plan").hexdigest()

        class H:
            evidence = {}

            def case(self, check_id, *a, **k):
                return SimpleNamespace(plan=f"plan-{len(order)}")

            def facts(self, case):
                order.append("facts_after")
                return {"runs": [{"id": 1, "mode": "apply", "status": "completed", "scope_md5": stored_scope}],
                        "snapshots": snapshots, "versions": {"personal:1": bumps, "personal:2": bumps}}

        def expected(plan):
            order.append(("expected", plan))
            return good

        def contention(h, check_id, first, second, pause):
            order.append("race")
            b_counts = ap.Counts()
            b_counts.created[ap.WRITE] = b_counts.handed[ap.WRITE] = 1
            b_counts.words[ap.WRITE] = {"SELECT": 4}
            b_counts.commits[ap.WRITE] = refused_commits
            before = {"runs": [], "snapshots": 0, "versions": {"personal:1": 0, "personal:2": 0}}
            return (({"results": {"applied": 2}}, 0), ({"code": "migration_run_exists"}, 4), {"waiter": "B"},
                    ap.Counts(), b_counts, (before, before))
        with mock.patch.object(ap, "contention", contention), mock.patch.object(ap, "expected_scope_md5", expected):
            try:
                ap.f2_same_account(H())
                return "pass", order
            except ap.CheckFailed as failed:
                return failed.what, order

    def test_f2_compares_with_the_scope_computed_before_the_race(self):
        good = _hashlib.md5(b"A-plan").hexdigest()
        result, order = self.run_f2(good)
        self.assertEqual(result, "pass")
        self.assertEqual(order[0][0], "expected")                    # computed from A's plan, before the race
        self.assertEqual(order[1:], ["race", "facts_after"])

    def test_f2_fails_on_a_changed_scope_even_when_everything_else_is_normal(self):
        result, _ = self.run_f2(_hashlib.md5(b"other").hexdigest())
        self.assertIn("run_scope", result)

    def test_attribution_alone_flags_only_the_scope(self):
        good = {"personal:1": 1, "personal:2": 1}
        after = {"runs": [{"id": 1, "mode": "apply", "status": "completed", "scope_md5": "t"}], "snapshots": 2,
                 "versions": good}
        before = {"runs": [], "snapshots": 0, "versions": {"personal:1": 0, "personal:2": 0}}
        self.assertEqual(ap.attributed_changes(before, after, winner_applied=2, winner_scope="s", refused_commits=0),
                         ["run_scope"])


# --- test environment and resources (2026-10-27): safe app environment, closed in-memory SQLite ---------------

SAFE_APP_ENV = {"APP_ENV": "test", "DATABASE_URL": "sqlite:///:memory:", "PYTHON_DOTENV_DISABLED": "1"}
CHILD_FIRST_APP_IMPORT = r'''
import importlib.abc, io, json, os, sys, unittest
SAFE = {safe!r}
seen = []

class FirstAppImport(importlib.abc.MetaPathFinder):
    """Records the environment at the FIRST import of `app`; an unsafe one stops before app (and .env) loads."""
    def find_spec(self, name, path, target=None):
        if name == "app" and not seen:
            env = {{k: os.environ.get(k) for k in SAFE}}
            seen.append(env)
            if env != SAFE:
                raise ImportError("unsafe environment at the first app import")
        return None

sys.meta_path.insert(0, FirstAppImport())
sys.path[:0] = [{scripts!r}, {tests!r}]
suite = unittest.defaultTestLoader.loadTestsFromName("test_ops_apply_real_guard.{case}")
result = unittest.TextTestRunner(stream=io.StringIO()).run(suite)
print("FIRST_APP_IMPORT", json.dumps(seen), "OK", result.wasSuccessful(), result.testsRun)
'''


def pin_safe_app_environment(case: unittest.TestCase) -> None:
    patch = mock.patch.dict(os.environ, SAFE_APP_ENV)
    patch.start()
    case.addCleanup(patch.stop)


def import_app(name: str):
    """Imports an app module only when the safe values are in place (otherwise stops before .env loads)."""
    unsafe = [k for k, v in SAFE_APP_ENV.items() if os.environ.get(k) != v]
    if unsafe:
        raise AssertionError(f"unsafe app environment: {unsafe}")
    import importlib
    return importlib.import_module(name)


def clean_child_env() -> dict:
    """No PYTHONPATH and none of the safe app values: the tests must pin them themselves."""
    return {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", *SAFE_APP_ENV)}


class AppEnvironmentFirst(unittest.TestCase):
    def test_tests_that_import_app_pin_the_safe_environment_first(self):
        code = CHILD_FIRST_APP_IMPORT.format(safe=SAFE_APP_ENV, scripts=str(BACKEND / "scripts"),
                                             tests=str(TESTS_DIR), case="ExpectedScope")
        done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120,
                              cwd=str(TESTS_DIR), env=clean_child_env())
        line = re.search(r"FIRST_APP_IMPORT (\[.*\]) OK (\w+) (\d+)", done.stdout)
        self.assertIsNotNone(line, done.stderr[-800:])
        self.assertEqual(json.loads(line.group(1)), [SAFE_APP_ENV])     # checked right before the first import
        self.assertEqual((line.group(2), int(line.group(3)) > 0), ("True", True), done.stderr[-800:])


class SqliteClosed(unittest.TestCase):
    def test_every_memory_database_is_closed_even_after_a_failure(self):
        made = []
        real_init = SqliteAsPg.__init__

        def init(self, *a, **k):
            real_init(self, *a, **k)
            made.append(self)

        class Failing(AccountScopedVersions):
            def test_fails_after_two_connections(self):
                self.make("ab")
                self.make("ba")
                raise AssertionError("synthetic failure after creating connections")

        suite = unittest.TestSuite([Failing("test_fails_after_two_connections"),
                                    *[Failing(n) for n in unittest.defaultTestLoader.getTestCaseNames(
                                        AccountScopedVersions)]])
        with mock.patch.object(SqliteAsPg, "__init__", init):
            result = unittest.TextTestRunner(stream=io.StringIO()).run(suite)
        self.assertEqual((len(result.failures), len(result.errors)), (1, 0))   # only the synthetic failure
        self.assertEqual(len(made), 6)                                # 2 + the 4 created by the real cases
        for conn in made:
            with self.assertRaises(sqlite3.ProgrammingError):              # closed: no statement can run
                conn.db.execute("SELECT 1")

    def test_no_resource_warning_in_a_fresh_process(self):
        code = ("import io, sys, unittest, warnings\n"
                "warnings.simplefilter('always', ResourceWarning)\n"
                f"sys.path[:0] = [{str(BACKEND / 'scripts')!r}, {str(TESTS_DIR)!r}]\n"
                "suite = unittest.defaultTestLoader.loadTestsFromName("
                "'test_ops_apply_real_guard.AccountScopedVersions')\n"
                "result = unittest.TextTestRunner(stream=io.StringIO()).run(suite)\n"
                "import gc; gc.collect()\n"
                "print('RUN', result.testsRun, result.wasSuccessful())\n")
        done = subprocess.run([sys.executable, "-X", "dev", "-c", code], capture_output=True, text=True, timeout=120,
                              cwd=str(TESTS_DIR), env=clean_child_env())
        self.assertIn("RUN 4 True", done.stdout, done.stderr[-800:])
        self.assertNotIn("ResourceWarning", done.stderr)


# --- G0 card mapping (2026-10-27, after the first real run): results named by card key, not by position -------
# Fake candidates and connections: control flow only, not evidence from PostgreSQL.

SYNTHETIC = {"a": {"user_id": 2, "personal": {"p1": 1, "p2": 2, "p3": 3, "p4": 4, "p5": 5}, "lexeme": [1, 2]},
             "b": {"user_id": 3, "personal": {"p1": 6, "p2": 7, "p3": 8, "p4": 9}, "lexeme": [1, 2]},
             "c": {"user_id": 4, "personal": {"p1": 10, "p2": 11, "p3": 12, "p4": 13}, "lexeme": [1, 2]}}


def candidate(kind, user, ref, *, blocked=False, quality="history_complete"):
    return SimpleNamespace(key=SimpleNamespace(kind=kind, user_id=user, ref_id=ref),
                           values_json=None if blocked else "{}", quality="incomplete" if blocked else quality)


def intended(order):
    """The intended data: p4 blocked (incomplete), the rest convertible, returned in `order`."""
    by_name = {"p1": candidate("personal", 2, 1), "p2": candidate("personal", 2, 2), "p3": candidate("personal", 2, 3),
               "p4": candidate("personal", 2, 4, blocked=True), "l1": candidate("lexeme", 2, 1),
               "l2": candidate("lexeme", 2, 2)}
    return [by_name[n] for n in order]


PRODUCT_ORDER = ("l1", "l2", "p1", "p2", "p3", "p4")                 # migration._scope: sorted (kind, ref_id)
REQUEST_ORDER = ("p1", "p2", "p3", "p4", "l1", "l2")


class TemplateConn:
    """Admin connection stand-in for template_qualities: accepts SET ROLE, rollback, close."""

    def __init__(self):
        self.sent, self.closed, self.row_factory = [], False, None

    def execute(self, query, *a, **k):
        self.sent.append(query)

    def rollback(self):
        pass

    def close(self):
        self.closed = True


class CardMapping(Blocked):
    def setUp(self):
        super().setUp()
        pin_safe_app_environment(self)

    def qualities(self, returned):
        """template_qualities itself, with the product dry_run answering `returned` (keys checked)."""
        migration = import_app("app.srs.migration")
        h = object.__new__(ap.Harness)
        h.pid, h.target = PID, {"synthetic": SYNTHETIC}
        asked, conn = [], TemplateConn()

        def dry_run(keys, *, connect=None):
            asked.append(sorted((k.kind, k.user_id, k.ref_id) for k in keys))
            return tuple(returned)
        with mock.patch.object(ap, "admin", lambda db, pid, autocommit=True: conn), \
                mock.patch.object(migration, "dry_run", dry_run):
            out = ap.template_qualities(h)
        self.assertEqual(asked, [sorted([("personal", 2, r) for r in (1, 2, 3, 4)] + [("lexeme", 2, 1), ("lexeme", 2, 2)])])
        self.assertTrue(conn.closed)
        return out

    def test_any_return_order_gives_the_same_table(self):
        for order in (PRODUCT_ORDER, REQUEST_ORDER, ("p4", "l2", "p2", "l1", "p3", "p1")):
            with self.subTest(order=order):
                self.assertEqual(self.qualities(intended(order)), ap.EXPECTED_QUALITIES)

    def wrong(self, returned, what):
        with self.assertRaises(ap.CheckFailed) as caught:
            self.qualities(returned)
        self.assertEqual(caught.exception.kind, "harness_defect")
        self.assertIn(what, caught.exception.what)

    def test_missing_duplicate_unexpected_and_other_account_keys_are_refused(self):
        base = intended(PRODUCT_ORDER)
        self.wrong(base[:-1], "missing")
        self.wrong(base + [base[0]], "duplicate")
        self.wrong(base[:-1] + [candidate("personal", 2, 5)], "unexpected")          # p5: outside the gate
        self.wrong(base[:-1] + [candidate("personal", 3, 4, blocked=True)], "other account")

    def test_a_real_quality_difference_stays_a_preparation_failure(self):
        changed = intended(PRODUCT_ORDER)
        changed[-1] = candidate("personal", 2, 4)                       # p4 convertible: the data is not as meant
        out = self.qualities(changed)
        self.assertEqual(out["p4"], "convertible")
        h = SimpleNamespace(target={"databases": {}}, pid=PID)
        with mock.patch.object(ap, "require_ours", lambda target: None), \
                mock.patch.object(ap, "admin", lambda db, pid, autocommit=True: contextlib.nullcontext(None)), \
                mock.patch.object(ap, "template_qualities", lambda h: out):
            with self.assertRaises(ap.CheckFailed) as caught:
                ap.g0_gate(h)
        self.assertEqual(caught.exception.kind, "preparation_failure")

    def test_names_come_from_the_recorded_ids(self):
        names = ap.quality_names(SYNTHETIC["a"])
        self.assertEqual(names, {("personal", 2, 1): "p1", ("personal", 2, 2): "p2", ("personal", 2, 3): "p3",
                                 ("personal", 2, 4): "p4", ("lexeme", 2, 1): "l1", ("lexeme", 2, 2): "l2"})
        with self.assertRaises(ap.CheckFailed):
            ap.quality_names({**SYNTHETIC["a"], "lexeme": [1]})               # the record is not as prepared


class GateStopsEverything(Blocked):
    def test_g0_failure_runs_no_check_and_is_not_counted(self):
        rec, _ = self.record()
        calls = []
        checks = [(n, lambda h, n=n: calls.append(n) or {}) for n in ap.PLANNED]

        def gate(h):
            raise ap.CheckFailed("harness_defect", "card key missing from the dry_run result")
        out = io.StringIO()
        with mock.patch.object(g, "single_run", lambda target: rec), mock.patch.object(ap, "Harness", FakeHarness), \
                mock.patch.object(ap, "CHECKS", checks), mock.patch.object(ap, "g0_gate", gate), \
                contextlib.redirect_stdout(out):
            self.assertEqual(ap.main(["check"]), 1)
        self.assertEqual(calls, [])
        self.assertIn("passed 0 / 21", out.getvalue())
        self.assertEqual([(r["check"], r["status"]) for r in rec.doc["results"]], [(ap.GATE, "fail")])


# --- d1 refusal paths (2026-10-27): each case must pass the earlier checks and stop at its own target ---------
# The REAL CLI run_apply, pre-check, plan file and evidence checks run here; only the signature primitive is a
# test verifier (a keyed digest, not cryptography) and the plan dry-run is a fake. Not evidence from PostgreSQL.

import _ops_signature as osig  # noqa: E402


def test_signature(namespace: str, data: bytes) -> bytes:
    return b"TEST:" + _hashlib.sha256(namespace.encode() + b"\0" + data).hexdigest().encode()


class TestKeys:
    def sign(self, signer, namespace, data):
        return test_signature(namespace, data)

    def close(self):
        pass


def test_verify(self, *, namespace, message, signature):
    return signature == test_signature(namespace, message)


class D1Paths(Blocked):
    def setUp(self):
        super().setUp()
        pin_safe_app_environment(self)
        for patch in (mock.patch.object(osig.SyntheticOpenSSHVerifier, "verify", test_verify),
                      mock.patch.object(cli, "run_dry_run", self.fake_plan_dry_run)):
            patch.start()
            self.addCleanup(patch.stop)
        self.h = self.harness()

    def harness(self):
        run = self.folder / "run"
        run.mkdir()
        objects = {t: 900 + j for j, t in enumerate(sorted(ap.OID_TABLES))}
        target = {"run_id": "run", "host": g.HOST, "port": T.port, "data": str(T.data),
                  "postgres_exe": str(g.POSTGRES_EXE), "postmaster_pid": PID, "server_version_num": "180006",
                  "system_identifier": "1", "provider_roles": list(ap.BUSINESS_ROLES), "admin_role": T.admin,
                  "roles": {ap.READ: 101, ap.WRITE: 102}, "synthetic": SYNTHETIC,
                  "databases": {db: {"oid": 500 + i, "identity_value": f"pg65-{i}-n", "objects": objects}
                                for i, db in enumerate(ap.BUSINESS_DATABASES)}}
        data = json.dumps(target, sort_keys=True).encode()
        (run / "target.json").write_bytes(data)
        h = object.__new__(ap.Harness)
        h.rec = SimpleNamespace(folder=run, event=lambda *a, **k: None)
        h.target_bytes, h.target, h.pid = data, target, PID
        h.keys, h.allowed = TestKeys(), b"test allowed signers"
        h.passwords = {ap.READ: "read-test-password", ap.WRITE: "write-test-password"}
        h.folders, h.evidence, h.connections = [], {}, []
        h.ca_pem = lambda: b"-----BEGIN CERTIFICATE-----\ntest\n-----END CERTIFICATE-----\n"
        h.hashes = lambda check_id: {"rows": "unchanged"}
        self.addCleanup(lambda: [shutil.rmtree(f, True) for f in h.folders])
        return h

    @staticmethod
    def fake_plan_dry_run(request, *, inputs, expected, driver, out):
        """Stands in for the CLI plan dry-run (no DB): a plan file for the request's cards on the signed target."""
        engine = import_app("app.srs.engine")
        digest = _hashlib.sha256(b"[]").hexdigest()
        candidates = [SimpleNamespace(key=SimpleNamespace(kind=k, user_id=request.account_id, ref_id=r),
                                      card_fingerprint=None, logs_fingerprint=digest, card_version=None,
                                      quality="unavailable", flags=("card_or_access_missing",), values_json=None,
                                      last_log_id=0, reconversion=None, restart_json=None) for k, r in request.cards]
        text = json.dumps({"user_id": request.account_id, "config_version": engine.DEFAULT_CONFIG.config_version,
                           "cards": [dict(kind=c.key.kind, ref_id=c.key.ref_id, card=None, logs=digest, version=None,
                                          quality=c.quality, values=None, flags=list(c.flags), last_log_id=0)
                                     for c in candidates]}, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        data = ap.pfile.serialize_plan(db_identity=ap.pf.db_identity(inputs.target), account_id=request.account_id,
                                       job_key=request.run_key, config_version=engine.DEFAULT_CONFIG.config_version,
                                       product_fingerprint=_hashlib.sha256(text.encode()).hexdigest(),
                                       candidates=candidates)
        ap.pfile.write_plan_file(out, data)
        return {"status": "ok"}, 0

    def test_each_case_reaches_its_own_refusal(self):
        details = ap.d1_mismatches(self.h)
        self.assertEqual(details["other_db_approval"]["code"], "preflight_db_identity_not_approved")
        self.assertEqual(details["other_db_approval"]["trace"], [["preflight", "apply", "db_identity_not_approved"]])
        self.assertEqual(details["tampered"]["code"], "preflight_approval_signature_invalid")
        self.assertEqual(details["tampered"]["trace"], [["preflight", "apply", "approval_signature_invalid"]])
        self.assertEqual(details["plan_target"]["code"], "plan_file_target_mismatch")
        self.assertEqual(details["plan_target"]["trace"], [["preflight", "apply", "ok"], ["preflight", "dry_run", "ok"]])
        self.assertEqual(details["evidence_account"]["code"], "backup_evidence_account_mismatch")
        self.assertEqual(details["evidence_account"]["trace"][-1], ["evidence", "-", "backup_evidence_account_mismatch"])
        for name, sub in details.items():
            self.assertEqual((sub["exit"], sub["connections"], sub["handed"], sub["product_calls"]),
                             (4, {"read": 0, "write": 0}, {"read": 0, "write": 0}, 0), name)

    def test_tamper_keeps_the_original_signature_on_both_inputs(self):
        case = self.h.case("d1")
        tampered = ap.tampered_case(case)
        self.assertEqual(tampered.write.approval, tampered.read.approval)
        self.assertNotEqual(tampered.write.approval, case.write.approval)
        self.assertEqual((tampered.write.approval_signature, tampered.read.approval_signature),
                         (case.write.approval_signature, case.read.approval_signature))

    def test_plan_target_case_differs_only_in_db_identity_and_is_signed(self):
        case = self.h.case("d1")
        other = self.h.case("d1", plan_db_identity="d2")
        a, b = case.plan, other.plan
        self.assertNotEqual(a.db_identity, b.db_identity)
        self.assertEqual((a.account_id, a.job_key, a.config_version, a.product_fingerprint),
                         (b.account_id, b.job_key, b.config_version, b.product_fingerprint))
        self.assertEqual(other.write.artifact_sha256, b.artifact_sha256)       # the apply approval binds this file

    def test_an_early_refusal_is_not_accepted_for_the_tamper_case(self):
        def write_only(case):                                       # the old, one-sided tamper
            return dataclasses.replace(case, write=dataclasses.replace(case.write, approval=case.write.approval + b" "))
        with mock.patch.object(ap, "tampered_case", write_only):
            with self.assertRaises(ap.CheckFailed) as caught:
                ap.d1_mismatches(self.h)
        self.assertIn("request_mismatch", caught.exception.what)

    def test_a_wrong_d1_stops_the_run_with_exit_1(self):
        rec, _ = self.record()
        calls = []

        def make(name):
            def fn(h):
                calls.append(name)
                if name == "d1":                                      # the old one-sided tamper: early refusal
                    one_sided = lambda c: dataclasses.replace(                  # noqa: E731
                        c, write=dataclasses.replace(c.write, approval=c.write.approval + b" "))
                    with mock.patch.object(ap, "tampered_case", one_sided):
                        return ap.d1_mismatches(self.h)
                return {}
            return fn
        out = io.StringIO()
        with mock.patch.object(g, "single_run", lambda target: rec), mock.patch.object(ap, "Harness", FakeHarness), \
                mock.patch.object(ap, "CHECKS", [(n, make(n)) for n in ap.PLANNED]), \
                mock.patch.object(ap, "g0_gate", lambda h: {}), contextlib.redirect_stdout(out):
            self.assertEqual(ap.main(["check"]), 1)
        self.assertEqual(calls, list(ap.PLANNED[:ap.PLANNED.index("d1") + 1]))
        self.assertEqual(rec.doc["results"][-1]["check"], "d1")
        self.assertEqual(rec.doc["results"][-1]["status"], "fail")


# --- d1 supplement entry point (2026-10-27): fixed scope G0 -> a2 -> d1 -> d1_post --------------------------
# Fakes and synthetic records only; nothing here is evidence from PostgreSQL.

class SupplementFlow(Blocked):
    def run_supplement(self, *, fail=None, record_fail=None, readback_fail=None, checks=None):
        rec, _ = self.record()
        calls = []

        def make(name):
            def fn(h):
                calls.append(name)
                if name == fail:
                    raise ap.CheckFailed("product_defect", "synthetic")
                return {"name": name}
            return fn
        real_result = rec.result

        def result(check, status, *a, **k):
            if check == record_fail and status == "pass":
                raise OSError("disk")
            return real_result(check, status, *a, **k)
        rec.result = result
        real_loads = json.loads

        def loads(text, *a, **k):
            doc = real_loads(text, *a, **k)
            if readback_fail and isinstance(doc, dict) and doc.get("results") \
                    and doc["results"][-1].get("check") == readback_fail:
                doc["results"][-1]["status"] = "lost"
            return doc
        selected = checks if checks is not None else [("a2", make("a2")), ("d1", make("d1"))]
        out = io.StringIO()
        with mock.patch.object(g, "single_run", lambda target: rec), mock.patch.object(ap, "Harness", FakeHarness), \
                mock.patch.object(ap, "g0_gate", make(ap.GATE)), mock.patch.object(ap, "supplement_checks", lambda: selected), \
                mock.patch.object(ap, "d1_post", make(ap.SUPPLEMENT_POST)), mock.patch.object(ap.json, "loads", loads), \
                contextlib.redirect_stdout(out):
            code = ap.main(["check-d1"])
        return code, calls, rec, out.getvalue()

    def test_fixed_order_and_exit_0_only_when_everything_passed(self):
        code, calls, rec, out = self.run_supplement()
        self.assertEqual((code, calls), (0, [ap.GATE, "a2", "d1", ap.SUPPLEMENT_POST]))
        self.assertIn("supplement d1: passed 2 / 2, post-check pass", out)
        started = rec.find("check_phase_started")[-1]
        self.assertEqual((started["phase"], started["checks"], started["post"]), ("supplement_d1", ["a2", "d1"], "d1_post"))
        self.assertIn("not added", started["note"])
        self.assertEqual([(r["check"], r["status"]) for r in rec.doc["results"]],
                         [(ap.GATE, "pass"), ("a2", "pass"), ("d1", "pass"), (ap.SUPPLEMENT_POST, "pass")])
        self.assertEqual(tuple(n for n, _ in ap.supplement_checks()), ("a2", "d1"))    # the real fixed list

    def test_failures_stop_what_follows_and_exit_1(self):
        for fail, ran in ((ap.GATE, [ap.GATE]), ("a2", [ap.GATE, "a2"]), ("d1", [ap.GATE, "a2", "d1"]),
                          (ap.SUPPLEMENT_POST, [ap.GATE, "a2", "d1", ap.SUPPLEMENT_POST])):
            with self.subTest(fail=fail):
                code, calls, _, out = self.run_supplement(fail=fail)
                self.assertEqual((code, calls), (1, ran))
                self.assertIn("STOP", out)

    def test_record_and_readback_failures_and_incomplete_scope_exit_1(self):
        for kwargs, ran in (({"record_fail": "d1"}, [ap.GATE, "a2", "d1"]),
                            ({"readback_fail": ap.SUPPLEMENT_POST}, [ap.GATE, "a2", "d1", ap.SUPPLEMENT_POST]),
                            ({"readback_fail": "a2"}, [ap.GATE, "a2"])):
            with self.subTest(**kwargs):
                code, calls, _, _ = self.run_supplement(**kwargs)
                self.assertEqual((code, calls), (1, ran))
        code, _, _, _ = self.run_supplement(checks=[("a2", lambda h: {})])        # d1 missing from the scope
        self.assertEqual(code, 1)

    def test_full_check_still_needs_21(self):
        self.assertEqual((len(ap.PLANNED), [n for n, _ in ap.CHECKS]), (21, list(ap.PLANNED)))
        rec, _ = self.record()
        out = io.StringIO()
        with mock.patch.object(g, "single_run", lambda target: rec), mock.patch.object(ap, "Harness", FakeHarness), \
                mock.patch.object(ap, "g0_gate", lambda h: {}), \
                mock.patch.object(ap, "CHECKS", [("a2", lambda h: {}), ("d1", lambda h: {})]), \
                contextlib.redirect_stdout(out):
            self.assertEqual(ap.main(["check"]), 1)                       # a2 + d1 alone is not the checklist
        self.assertIn("passed 2 / 21", out.getvalue())

    def test_post_check_requires_rows_d1_and_sessions(self):
        def harness(outside, d1_now, sessions):
            h = SimpleNamespace(evidence={"outside": outside, "d1_before": {"t": 1}})
            h.hashes = lambda check_id: d1_now
            h.sessions = lambda: sessions
            return h
        ok = {"open": 0, "idle_in_transaction": 0}
        self.assertEqual(ap.d1_post(harness({"a2": True}, {"t": 1}, ok))["d1_unchanged"], True)
        for bad in (harness({"a2": False}, {"t": 1}, ok), harness({}, {"t": 1}, ok),
                    harness({"a2": True}, {"t": 2}, ok), harness({"a2": True}, {"t": 1}, {"open": 1, "idle_in_transaction": 0}),
                    harness({"a2": True}, {"t": 1}, {"open": 1, "idle_in_transaction": 1})):
            with self.assertRaises(ap.CheckFailed):
                ap.d1_post(bad)


class SupplementWithRealD1(D1Paths):
    """The supplement entry point with the REAL d1 (test verifier, fake connections) between fake G0 / a2."""

    def run_entry(self, tamper=None):
        rec, _ = self.record()
        h = self.h
        h.start = lambda: None
        h.sessions = lambda: {"open": 0, "idle_in_transaction": 0}

        def a2(h):
            h.evidence.setdefault("outside", {})["a2"] = True
            return {}
        patches = [mock.patch.object(g, "single_run", lambda target: rec), mock.patch.object(ap, "Harness", lambda r: h),
                   mock.patch.object(ap, "g0_gate", lambda h: {}), mock.patch.object(ap, "a2_personal_and_lexeme", a2)]
        if tamper is not None:
            patches.append(mock.patch.object(ap, "tampered_case", tamper))
        out = io.StringIO()
        with contextlib.ExitStack() as stack:
            for patch in patches:
                stack.enter_context(patch)
            stack.enter_context(contextlib.redirect_stdout(out))
            code = ap.main(["check-d1"])
        return code, rec

    def test_real_d1_passes_only_with_the_exact_paths(self):
        code, rec = self.run_entry()
        self.assertEqual(code, 0)
        d1 = next(r for r in rec.doc["results"] if r["check"] == "d1")["details"]
        self.assertEqual(d1["other_db_approval"]["prep"]["db"], ap.CHECK_DB["d2"])      # plan read on d2, apart
        self.assertEqual(d1["plan_target"]["connections"], {"read": 0, "write": 0})

    def test_an_early_refusal_fails_the_supplement(self):
        one_sided = lambda c: dataclasses.replace(c, write=dataclasses.replace(c.write, approval=c.write.approval + b" "))  # noqa: E731,E501
        code, rec = self.run_entry(tamper=one_sided)
        self.assertEqual(code, 1)
        self.assertEqual([(r["check"], r["status"]) for r in rec.doc["results"]][-1], ("d1", "fail"))
        self.assertNotIn(ap.SUPPLEMENT_POST, [r["check"] for r in rec.doc["results"]])


class SupplementMain(unittest.TestCase):
    """The real `__main__` path in a new Python process (connect / processes / mkdir blocked there)."""

    def run_main(self, prelude: str):
        code = (f"import os, subprocess, sys, runpy; sys.path[:0] = [{str(BACKEND / 'scripts')!r}, {str(TESTS_DIR)!r}]\n"
                "import psycopg\n"
                "def fail(*a, **k): raise AssertionError('external work')\n"
                "psycopg.connect = fail; subprocess.run = fail; subprocess.Popen = fail; os.mkdir = fail\n"
                "import _ops_apply_real as ap\n" + prelude +
                "sys.argv = [ap.__file__, 'check-d1']\nrunpy.run_path(ap.__file__, run_name='__main__')\n")
        return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120,
                              cwd=str(TESTS_DIR), env=clean_child_env())

    def test_exit_codes(self):
        self.assertEqual(self.run_main("ap.check_d1 = lambda: (2, True)\n").returncode, 0)
        self.assertEqual(self.run_main("ap.check_d1 = lambda: (2, False)\n").returncode, 1)
        self.assertEqual(self.run_main("ap.check_d1 = lambda: (1, False)\n").returncode, 1)
        done = self.run_main("")                                      # no pg65 run folder here: refused, nothing done
        self.assertEqual(done.returncode, 1, done.stderr[-500:])
        self.assertIn("STOP (refused)", done.stdout)
        self.assertFalse(T.root.exists())


# --- sequence USAGE contract (OPS_APPLY_SEQUENCE_PRIVILEGE_PLAN S2): c1 switched, check-seq -----------------
# Fakes only; not evidence of PostgreSQL privileges or identity INSERTs.

class SequenceRunner(Blocked):
    def test_c1_variant_grants_then_revokes_and_contract_grants_have_no_sequence(self):       # s-7
        apply = [s.as_string(None) for s in ap.variant_statements("c1_sequences", "apply")]
        revert = [s.as_string(None) for s in ap.variant_statements("c1_sequences", "revert")]
        self.assertEqual(apply, [f'GRANT USAGE ON SEQUENCE public.{s} TO "jpvm_write"'
                                 for s in ("srs_migration_runs_id_seq", "srs_migration_snapshots_id_seq")])
        self.assertEqual(revert, [f'REVOKE USAGE ON SEQUENCE public.{s} FROM "jpvm_write"'
                                  for s in ("srs_migration_runs_id_seq", "srs_migration_snapshots_id_seq")])
        self.assertEqual(ap.VARIANT_DATABASES["c1_sequences"], ("c1",))
        for db in (ap.CHECK_DB["a2"], ap.CHECK_DB["c1"]):
            self.assertFalse([s for s in (g.as_string(None) for g in ap.contract_grants(db)) if "SEQUENCE" in s])
        self.assertIn("c1p", ap.CHECK_DB)                                  # still in the preset, unused
        self.assertFalse(hasattr(ap, "direct_apply"))

    def test_full_check_c1_and_check_seq_s1_are_one_judgement(self):
        self.assertIs(dict(ap.CHECKS)["c1"], ap.c1_sequences)
        self.assertIs(dict(ap.seq_checks())["s1"], ap.c1_sequences)
        self.assertEqual([n for n, _ in ap.seq_checks()], ["a1", "a2", "s1"])

    def harness(self, *, code="observed_privileges_excess", exit_code=4, handed=0, statements=0, rows_change=False,
                revert_fails=False, revert_observation="matches_contract"):
        log = []

        class H:
            pid = PID

            def case(self, check_id, **k):
                return SimpleNamespace(db=ap.CHECK_DB[check_id])

            def hashes(self, check_id):
                log.append("hashes")
                return {"rows": 2 if rows_change and log.count("hashes") > 1 else 1}

            def variant(self, name, phase):
                log.append((name, phase))
                if phase == "revert" and revert_fails:
                    raise psycopg.OperationalError("synthetic")

            def apply(self, case):
                log.append("apply")
                counts = ap.Counts()
                counts.created[ap.WRITE] = 1
                counts.handed[ap.WRITE] = handed
                if statements:
                    counts.words[ap.WRITE] = {"SELECT": statements}
                return {"code": code}, exit_code, counts

            def observe_write(self, case):
                log.append("observe")
                return {"observation": revert_observation, "handed": 1, "statements": 0}

        h = H()
        h.with_variant = lambda name, fn: ap.Harness.with_variant(h, name, fn)
        return h, log

    def run_c1(self, **kwargs):
        h, log = self.harness(**kwargs)

        @contextlib.contextmanager
        def admin(db, pid, autocommit=True):
            yield SimpleNamespace(execute=lambda q, p: SimpleNamespace(fetchone=lambda: ["d"]))
        with mock.patch.object(ap, "admin", admin):
            return ap.c1_sequences(h), log

    def test_s1_passes_only_on_exact_excess_without_hand_over(self):                    # s-8
        details, log = self.run_c1()
        self.assertEqual(log, ["hashes", ("c1_sequences", "apply"), "apply", ("c1_sequences", "revert"), "hashes",
                               "observe"])
        self.assertEqual(set(details), {"attidentity", "granted_usage", "revert"})          # s-9
        self.assertEqual(details["granted_usage"]["code"], "observed_privileges_excess")
        self.assertEqual(details["revert"], {"observation": "matches_contract", "handed": 1, "statements": 0})
        self.assertNotIn("direct_apply_without_usage", json.dumps(details))
        for kwargs, kind in (({"code": "observed_privileges_missing"}, "product_defect"),
                             ({"code": "preflight_approval_expired"}, "product_defect"),
                             ({"handed": 1}, "product_defect"), ({"handed": 1, "statements": 3}, "product_defect"),
                             ({"rows_change": True}, "product_defect"), ({"revert_fails": True}, "harness_defect"),
                             ({"revert_observation": "observed_privileges_excess"}, "harness_defect")):
            with self.subTest(**kwargs):
                with self.assertRaises(ap.CheckFailed) as caught:
                    self.run_c1(**kwargs)
                self.assertEqual(caught.exception.kind, kind)

    def test_revert_runs_even_when_the_judged_run_fails(self):
        h, log = self.harness()

        def boom(case):
            log.append("apply")
            raise ap.CheckFailed("product_defect", "synthetic")
        h.apply = boom

        @contextlib.contextmanager
        def admin(db, pid, autocommit=True):
            yield SimpleNamespace(execute=lambda q, p: SimpleNamespace(fetchone=lambda: ["d"]))
        with mock.patch.object(ap, "admin", admin), self.assertRaises(ap.CheckFailed):
            ap.c1_sequences(h)
        self.assertEqual(log[-1], ("c1_sequences", "revert"))

    def test_observe_write_reports_the_provider_judgement(self):
        made = []

        class Ctx:
            def __enter__(self):
                return "product"

            def __exit__(self, *e):
                return False

        def fake_connector(result):
            def real(inputs, expected, driver):
                def connector(*, read_only=False):
                    if result != "ok":
                        raise cli.pc.OpsProductConnectionError(result)
                    counts_holder = driver()
                    made.append(counts_holder)
                    return Ctx()
                return connector
            return real

        h = object.__new__(ap.Harness)

        def driver(inputs, counts, trackers, hooks=None):
            def connect():
                counts.created[ap.WRITE] += 1
                trackers.append(ap.Tracked(FakeConn(), counts, ap.WRITE, []))
                return "conn"
            return connect
        h.driver = driver
        case = SimpleNamespace(write=FakeInputs("apply"), write_expected=None)
        with mock.patch.object(ap, "ORIGINAL_CONNECTOR", fake_connector("ok")):
            self.assertEqual(ap.Harness.observe_write(h, case),
                             {"observation": "matches_contract", "handed": 1, "statements": 0})
        with mock.patch.object(ap, "ORIGINAL_CONNECTOR", fake_connector("observed_privileges_excess")):
            self.assertEqual(ap.Harness.observe_write(h, case)["observation"], "observed_privileges_excess")


class CheckSeqFlow(Blocked):
    def run_seq(self, *, fail=None, record_fail=None, readback_fail=None, checks=None):
        rec, _ = self.record()
        calls = []

        def make(name):
            def fn(h):
                calls.append(name)
                if name == fail:
                    raise ap.CheckFailed("product_defect", "synthetic")
                return {"name": name}
            return fn
        real_result = rec.result

        def result(check, status, *a, **k):
            if check == record_fail and status == "pass":
                raise OSError("disk")
            return real_result(check, status, *a, **k)
        rec.result = result
        real_loads = json.loads

        def loads(text, *a, **k):
            doc = real_loads(text, *a, **k)
            if readback_fail and isinstance(doc, dict) and doc.get("results") \
                    and doc["results"][-1].get("check") == readback_fail:
                doc["results"][-1]["status"] = "lost"
            return doc
        selected = checks if checks is not None else [(n, make(n)) for n in ap.SEQ_PLANNED]
        out = io.StringIO()
        with mock.patch.object(g, "single_run", lambda target: rec), mock.patch.object(ap, "Harness", FakeHarness), \
                mock.patch.object(ap, "g0_gate", make(ap.GATE)), mock.patch.object(ap, "seq_checks", lambda: selected), \
                mock.patch.object(ap, "seq_post", make(ap.SEQ_POST)), mock.patch.object(ap.json, "loads", loads), \
                contextlib.redirect_stdout(out):
            code = ap.main(["check-seq"])
        return code, calls, rec, out.getvalue()

    def test_order_count_and_exit_0(self):
        code, calls, rec, out = self.run_seq()
        self.assertEqual((code, calls), (0, [ap.GATE, "a1", "a2", "s1", ap.SEQ_POST]))
        self.assertIn("sequence re-check: passed 3 / 3, post-check pass", out)
        started = rec.find("check_phase_started")[-1]
        self.assertEqual((started["phase"], started["checks"], started["post"]),
                         ("sequence_usage_recheck", ["a1", "a2", "s1"], "seq_post"))

    def test_any_failure_stops_and_exits_1(self):
        order = [ap.GATE, "a1", "a2", "s1", ap.SEQ_POST]
        for fail in order:
            with self.subTest(fail=fail):
                code, calls, _, _ = self.run_seq(fail=fail)
                self.assertEqual((code, calls), (1, order[:order.index(fail) + 1]))
        for kwargs in ({"record_fail": "s1"}, {"readback_fail": ap.SEQ_POST}, {"readback_fail": "a1"}):
            with self.subTest(**kwargs):
                self.assertEqual(self.run_seq(**kwargs)[0], 1)
        self.assertEqual(self.run_seq(checks=[("a1", lambda h: {}), ("a2", lambda h: {})])[0], 1)   # s1 missing

    def test_seq_post_requires_rows_and_sessions(self):
        ok = {"open": 0, "idle_in_transaction": 0}
        good = SimpleNamespace(evidence={"outside": {"a2": True}}, sessions=lambda: ok)
        self.assertEqual(ap.seq_post(good)["outside_a2"], True)
        for bad in (SimpleNamespace(evidence={"outside": {"a2": False}}, sessions=lambda: ok),
                    SimpleNamespace(evidence={}, sessions=lambda: ok),
                    SimpleNamespace(evidence={"outside": {"a2": True}},
                                    sessions=lambda: {"open": 0, "idle_in_transaction": 1})):
            with self.assertRaises(ap.CheckFailed):
                ap.seq_post(bad)



class CheckSeqMain(unittest.TestCase):
    """The real `__main__` path of check-seq in a new Python process (externals blocked there)."""

    def test_main_exit_codes_in_a_new_process(self):
        def run(prelude):
            code = (f"import os, subprocess, sys, runpy; sys.path[:0] = [{str(BACKEND / 'scripts')!r}, {str(TESTS_DIR)!r}]\n"
                    "import psycopg\n"
                    "def fail(*a, **k): raise AssertionError('external work')\n"
                    "psycopg.connect = fail; subprocess.run = fail; subprocess.Popen = fail; os.mkdir = fail\n"
                    "import _ops_apply_real as ap\n" + prelude +
                    "sys.argv = [ap.__file__, 'check-seq']\nrunpy.run_path(ap.__file__, run_name='__main__')\n")
            return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120,
                                       cwd=str(TESTS_DIR), env=clean_child_env())
        self.assertEqual(run("ap.check_seq = lambda: (3, True)\n").returncode, 0)
        self.assertEqual(run("ap.check_seq = lambda: (3, False)\n").returncode, 1)
        self.assertEqual(run("ap.check_seq = lambda: (2, False)\n").returncode, 1)
        done = run("")
        self.assertEqual(done.returncode, 1)
        self.assertIn("STOP (refused)", done.stdout)
        self.assertFalse(T.root.exists())


if __name__ == "__main__":
    unittest.main()

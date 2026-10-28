"""Fake-only checks for the real-PG audit runner (tests/_ops_audit_real.py) and the closed target
presets of tests/_ops_pg62.py. No database, no PG command, no admin work: connect entry points,
`subprocess` and process facts are patched; only temporary synthetic files are written.

Run directly:      python tests/test_ops_audit_real_guard.py
Or via discovery:   python -m unittest discover -s tests
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

TESTS_DIR = Path(__file__).resolve().parent
BACKEND = TESTS_DIR.parent
sys.path.insert(0, str(BACKEND / "scripts"))
sys.path.insert(0, str(TESTS_DIR))

import psycopg  # noqa: E402

import _ops_audit_real as real  # noqa: E402
import _ops_pg62 as g  # noqa: E402
import test_ops_preflight as pf  # noqa: E402  (helpers only)

T = g.PG63_AUDIT
TARGET = {"host": g.HOST, "port": T.port, "data": str(T.data), "postgres_exe": str(g.POSTGRES_EXE),
          "postmaster_pid": 5151, "server_version_num": "180006",
          "databases": {real.DB_OK: {"oid": 16400, "identity_value": "pg63-ok-x"},
                        real.DB_BAD: {"oid": 16401, "identity_value": "pg63-bad-x"}},
          "provider_roles": list(T.provider_roles), "admin_role": T.admin}
GOOD = {"host": g.HOST, "port": str(T.port), "dbname": real.DB_OK, "user": real.AUDIT, "sslmode": "verify-full",
        "password": pf.SECRET, "sslrootcert": "copy.pem"}


def forbidden(*_, **__):
    raise AssertionError("a connection function was called")


class Fakes(unittest.TestCase):
    def setUp(self):
        for patch in (mock.patch.object(psycopg, "connect", forbidden),
                      mock.patch.object(g, "server_is_ours", lambda pid, target=g.PG62: pid == 5151 and target is T),
                      mock.patch.object(g.subprocess, "run", forbidden),
                      mock.patch.dict(os.environ, {k: v for k, v in os.environ.items()
                                                   if not k.upper().startswith("PG")}, clear=True)):
            patch.start()
            self.addCleanup(patch.stop)
        self.tmp = Path(tempfile.mkdtemp(prefix="ops_audit_real_guard_test_"))
        self.addCleanup(shutil.rmtree, self.tmp)
        (self.tmp / "run").mkdir()

    def guard(self, target=TARGET, listed=None, preset=T):
        data = json.dumps(target).encode()
        (self.tmp / "run" / "target.json").write_bytes(data)
        files = {**pf.FILES, preset.target_doc if preset in g.PRESETS else T.target_doc:
                 listed if listed is not None else data}
        root = self.tmp / "deploy"
        shutil.rmtree(root, ignore_errors=True)
        for rel, content in files.items():
            path = root.joinpath(*rel.split("/"))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        return g.Guard(pf.manifest_doc(files), str(root), self.tmp / "run", target=preset)

    def refused(self, code, kwargs, guard=None):
        guard = guard or self.guard()
        with self.assertRaises(g.Pg62Refused) as caught:
            guard.driver(**kwargs)
        self.assertEqual(caught.exception.code, code)
        self.assertNotIn(pf.SECRET, repr(caught.exception))
        self.assertEqual(guard.connect_calls, 0)


class Presets(Fakes):
    def test_only_two_closed_presets(self):
        self.assertEqual(g.PRESETS, (g.PG62, g.PG63_AUDIT, g.PG64_BACKUP, g.PG65_APPLY,
                         g.PG66_RESUME))   # pg64 (B1), pg65 (C12-1), pg66 (RS4-1)
        self.assertEqual((T.root, T.port, T.databases, T.admin, T.provider_roles),
                         (Path("C:/JV_Tools/pg63"), 55472, ("jp_vocab_test_audit_ok", "jp_vocab_test_audit_bad"),
                          "jpva_admin", ("jpva_audit",)))
        self.assertEqual((g.PG62.root, g.PG62.port, g.PG62.databases), (g.ROOT, g.PORT, (g.DB_A, g.DB_B)))
        self.assertNotIn(T.admin, T.provider_roles)
        for copy in (replace(T), replace(T, port=55473), replace(T, databases=T.databases + ("postgres",)),
                     replace(g.PG62, root=Path("C:/JV_Tools/pgdata-e2"), port=55432), "pg63_audit", None):
            with self.subTest(copy=repr(copy)[:40]):
                with self.assertRaises(g.Pg62Refused) as caught:
                    g.preset(copy)
                self.assertEqual(caught.exception.code, "pg62_target_preset_refused")
                with self.assertRaises(g.Pg62Refused):
                    g.admin_connect("postgres", record_pid=5151, target=copy)
                with self.assertRaises(g.Pg62Refused):
                    g.single_run(copy)

    def test_app_is_imported_only_in_the_preparation_step(self):
        source = (TESTS_DIR / "_ops_audit_real.py").read_text(encoding="utf-8")
        lines = [i for i, line in enumerate(source.splitlines()) if re.match(r"\s*(from app[ .]|import app[ .])", line)]
        body = source[source.index("def build_app_schema"):source.index("def grant_audit")]
        self.assertEqual(len(lines), 1)
        self.assertIn("from app import database", body)
        self.assertLess(body.index("ar.fix_app_environment()"), body.index("from app import database"))

    def test_runner_has_no_target_inputs(self):
        source = re.sub(r'"""[\s\S]*?"""', "", (TESTS_DIR / "_ops_audit_real.py").read_text(encoding="utf-8"))
        for forbidden_text in ("argparse", "getenv(", "environ.get(", "Target(", "replace(T", "replace(g.", "dataclasses", "DATABASE_URL"):
            with self.subTest(text=forbidden_text):
                self.assertNotIn(forbidden_text, source)
        self.assertIn("T = g.PG63_AUDIT", source)


class GuardPg63(Fakes):
    def test_allowed_target_reaches_only_the_patched_driver(self):
        with self.assertRaises(AssertionError):
            self.guard().driver(**GOOD)

    def test_other_targets_refused(self):
        cases = [("pg62_port_refused", dict(port="55462")), ("pg62_port_refused", dict(port="55432")),
                 ("pg62_port_refused", dict(port="55463")), ("pg62_host_refused", dict(host="127.0.0.1")),
                 ("pg62_database_refused", dict(dbname="jp_vocab_test_62a")),
                 ("pg62_database_refused", dict(dbname="jp_vocab_test_e")), ("pg62_database_refused", dict(dbname="postgres")),
                 ("pg62_role_refused", dict(user=T.admin)), ("pg62_role_refused", dict(user="jpva_owner")),
                 ("pg62_role_refused", dict(user="jpv62_read")), ("pg62_tls_mode_refused", dict(sslmode="require"))]
        for code, change in cases:
            with self.subTest(code=code, change=change):
                self.refused(code, {**GOOD, **change})

    def test_record_pid_data_and_hash(self):
        self.refused("pg62_server_not_ours", GOOD, self.guard({**TARGET, "postmaster_pid": 5152}))
        self.refused("pg62_server_not_ours", GOOD, self.guard({**TARGET, "data": "C:/JV_Tools/pg62/data"}))
        self.refused("pg62_server_not_ours", GOOD, self.guard({**TARGET, "data": "C:/JV_Tools/pgdata-e2"}))
        with self.assertRaises(g.Pg62Refused) as caught:
            self.guard(listed=json.dumps({**TARGET, "port": 55432}).encode())
        self.assertEqual(caught.exception.code, "pg62_target_hash_mismatch")
        self.refused("pg62_role_refused", {**GOOD, "user": T.admin},
                     self.guard({**TARGET, "provider_roles": [real.AUDIT, T.admin]}))   # a record cannot add the admin

    def test_6_2_defaults_kept_and_do_not_accept_pg63(self):
        with mock.patch.object(g, "server_is_ours", lambda pid: True):
            guard = self.guard(preset=g.PG62, target={**TARGET, "port": g.PORT})
            self.refused("pg62_database_refused", {**GOOD, "port": str(g.PORT)}, guard)
            self.refused("pg62_port_refused", GOOD, guard)

    def test_admin_connection_scope(self):
        for db in ("jp_vocab_test_62a", "jp_vocab_test_e", "vocab"):
            with self.subTest(db=db), self.assertRaises(g.Pg62Refused) as caught:
                g.admin_connect(db, record_pid=5151, target=T)
            self.assertEqual(caught.exception.code, "pg62_admin_target_refused")
        with self.assertRaises(g.Pg62Refused) as caught:
            g.admin_connect(real.DB_OK, record_pid=5152, target=T)
        self.assertEqual(caught.exception.code, "pg62_server_not_ours")


class PostConnect(unittest.TestCase):
    class Conn:
        def __init__(self, facts):
            self.facts, self.closed, self.rollbacks = facts, False, 0

        def cursor(self, row_factory=None):
            facts = self.facts

            class C:
                def __enter__(self):
                    return self

                def __exit__(self, *exc):
                    return False

                def execute(self, query):
                    assert query == real.POST_CONNECT

                def fetchone(self):
                    return dict(facts)
            return C()

        def rollback(self):
            self.rollbacks += 1

        def close(self):
            self.closed = True

    GOOD_FACTS = {"server_addr": "::1", "server_port": 55472, "version": "180006", "dbname": real.DB_OK, "db_oid": 16400}

    def test_matching_target_is_left_idle(self):
        conn = self.Conn(self.GOOD_FACTS)
        real.post_connect_check(conn, TARGET)
        self.assertEqual((conn.rollbacks, conn.closed), (1, False))

    def test_mismatch_closes_and_refuses(self):
        for change in ({"server_addr": "10.0.0.5"}, {"server_port": 55462}, {"version": "170004"},
                       {"dbname": "jp_vocab_test_62a"}, {"db_oid": 99999}):
            with self.subTest(change=change):
                conn = self.Conn({**self.GOOD_FACTS, **change})
                with self.assertRaises(g.Pg62Refused) as caught:
                    real.post_connect_check(conn, TARGET)
                self.assertEqual((caught.exception.code, conn.closed), ("pg62_connected_target_mismatch", True))


class Permissions(unittest.TestCase):
    """The audit role's privileges come from the audit code, fixed in advance."""

    def test_audit_tables_are_exactly_what_the_audit_reads(self):
        self.assertEqual(len(real.AUDIT_TABLES), 14)
        self.assertNotIn("shared_deck_words", real.AUDIT_TABLES)
        self.assertNotIn("user_deck_subscriptions", real.AUDIT_TABLES)
        audit = (BACKEND / "app" / "srs" / "invariant_audit.py").read_text(encoding="utf-8")
        start, end = audit.index("class _Audit"), audit.index("class DeletionBaseline")   # single-audit code only
        body = audit[start:end]
        read = set(re.findall(r'\("(?:personal|lexeme)", "(\w+)"\)', body)) | set(re.findall(r'_rows\(connection, "(\w+)"\)', body))
        read |= set(re.findall(r"FROM (\w+)", body)) - {"pg_sequence", "sqlite_master", "sqlite_sequence"}
        identity = (BACKEND / "app" / "srs" / "identity.py").read_text(encoding="utf-8")
        scan = identity[identity.index("def scan_identity"):identity.index("def flag_identity_unknown")]
        read |= set(re.findall(r"FROM (\w+)", scan))
        self.assertEqual(read, set(real.AUDIT_TABLES))
        migration = (BACKEND / "app" / "srs" / "migration.py").read_text(encoding="utf-8")
        reduced = migration[migration.index("def _reduced_scope"):migration.index("def _scope_matches")]
        self.assertNotIn("execute", reduced)                                # reads no table
        authorized = migration[migration.index("def _authorized"):]
        authorized = authorized[:authorized.index("\ndef ", 1)]
        self.assertIn("shared_deck_words", authorized)                      # where the two tables are read
        self.assertNotIn("_authorized", body)

    def test_expected_profile_is_read_only(self):
        profile = real.expected_profile(real.DB_OK)
        privileges = {p[4] for p in profile.privileges}
        self.assertEqual(privileges, {"CONNECT", "USAGE", "SELECT"})
        tables = {p[2] for p in profile.privileges if p[0] == "table" and p[1] == "public"}
        self.assertEqual(tables, set(real.AUDIT_TABLES))
        self.assertEqual({p[2] for p in profile.privileges if p[0] == "sequence"}, {"vocab_items_id_seq"})
        self.assertNotIn(("table", "public", "shared_deck_words", "", "SELECT"), profile.privileges)
        self.assertTrue({("table", "public", "shared_deck_words"), ("table", "public", "app_feedback")}
                        <= profile.objects)                                  # objects kept, no privilege

    def test_app_tables_match_the_schema_source(self):
        database = (BACKEND / "app" / "database.py").read_text(encoding="utf-8")
        pg = database[database.index("def create_postgres_tables"):]
        pg = pg[:pg.index("\ndef ", 1)]
        core = re.findall(r"CREATE TABLE IF NOT EXISTS (\w+) \(", pg)
        self.assertEqual(tuple(core), real.CORE_TABLES)
        for table in core:
            ddl = pg[pg.index(f"CREATE TABLE IF NOT EXISTS {table} ("):]
            self.assertIn("GENERATED BY DEFAULT AS IDENTITY", ddl[:ddl.index("\n", ddl.index("(")) + 120])
        schema = (BACKEND / "app" / "srs" / "schema.py").read_text(encoding="utf-8")
        srs = list(dict.fromkeys(re.findall(r"CREATE TABLE IF NOT EXISTS (\w+) \(", schema)))
        self.assertEqual(tuple(srs), real.SRS_TABLES)
        for table in real.SRS_TABLES:
            ddl = schema[schema.index(f"CREATE TABLE IF NOT EXISTS {table} ("):]
            first_column = ddl[ddl.index("(") + 1:ddl.index(",")]
            self.assertEqual("{pk}" in first_column, table not in real.SRS_WITHOUT_IDENTITY, table)


PARTIAL = {"audit_version": 1, "status": "partial",
           "checks": {**{f"I{i}": {"status": "pass", "violations": 0, "unknown": 0, "references_checked": 3}
                         for i in range(1, 6)},
                      "I6": {"status": "not_evaluated", "reason": "deletion_baseline_required"},
                      "I7": {"status": "not_evaluated", "reason": "deletion_baseline_required"}}}
FAILED = json.loads(json.dumps(PARTIAL))
FAILED.update(status="fail")
FAILED["checks"]["I1"].update(status="fail", violations=1)


class FakeHarness:
    """Prepared audit / CLI results only (no database)."""

    def __init__(self, new=PARTIAL, old=PARTIAL, new_code=3, old_code=3, commits=0, probe_extra=None):
        self.new, self.old, self.new_code, self.old_code, self.commits = new, old, new_code, old_code, commits
        self.probe_extra = probe_extra or {}
        self.admin_commits = 0
        self.rec, self.pid = None, 1

    def set_password(self):
        pass

    def close(self):
        pass

    def inputs(self, **_):
        return object()

    def audit(self, inputs, db=None):
        out = json.loads(json.dumps(self.new))
        out.update(scope="database_all", target={"alias": "synthetic-primary", "db_identity": "0" * 64})
        probe = {"iso": "repeatable read", "ro": "on", "st": "15s", "lt": "5s", "xid": None, "calls": 1,
                 "commits": self.commits}
        probe.update(self.probe_extra)
        if "xid_probe_failed" in probe:
            probe.pop("xid")
        return out, self.new_code, probe

    def cli(self, db):
        return json.loads(json.dumps(self.old)), self.old_code

    def snapshot(self, db):
        self.admin_commits += 1                     # admin-side work is not the audit connection
        return {"users": (1, 1)}

    def sessions(self):
        return 0


class ResultComparison(unittest.TestCase):
    def test_counts_inside_checks_must_match(self):
        other = json.loads(json.dumps(PARTIAL))
        other["checks"]["I3"]["references_checked"] = 4
        with self.assertRaises(real.CheckFailed):
            real.c2_compare_cli(FakeHarness(old=other))
        bad_other = json.loads(json.dumps(FAILED))
        bad_other["checks"]["I5"]["references_checked"] = 9
        with self.assertRaises(real.CheckFailed):
            real.c3_violation(FakeHarness(new=FAILED, old=bad_other, new_code=1, old_code=1))
        version = dict(PARTIAL, audit_version=2)
        with self.assertRaises(real.CheckFailed):
            real.c2_compare_cli(FakeHarness(old=version))

    def test_identical_results_pass_and_metadata_is_kept_apart(self):
        real.c2_compare_cli(FakeHarness())
        real.c3_violation(FakeHarness(new=FAILED, old=FAILED, new_code=1, old_code=1))


class AuditCommits(unittest.TestCase):
    class Raw:
        def __init__(self):
            self.log, self.closed, self.row_factory = [], False, None

        def commit(self):
            self.log.append("commit")

        def rollback(self):
            self.log.append("rollback")

        def execute(self, query, params=()):
            self.log.append(query)
            return None

        def close(self):
            self.closed = True

    def test_commit_calls_are_counted_through_every_path(self):
        sys.path.insert(0, str(BACKEND))
        from app.database import AppPostgresConnection
        raw = self.Raw()
        tracked = real.CommitTracker(raw)
        tracked.row_factory = "dict"
        self.assertEqual(raw.row_factory, "dict")                  # attributes reach the real connection
        AppPostgresConnection(tracked).commit()                     # app wrapper path
        tracked.commit()                                            # raw path
        tracked.execute("  commit ")
        tracked.execute("END")
        tracked.rollback()
        tracked.execute("SELECT 1")
        self.assertEqual(tracked.commits, 4)
        self.assertEqual(raw.log.count("commit"), 2)               # still forwarded: semantics unchanged
        self.assertIn("rollback", raw.log)

    def test_audit_commit_fails_the_check_even_with_a_correct_result(self):
        with self.assertRaises(real.CheckFailed):
            real.c1_ok_new_path(FakeHarness(commits=1))

    def test_admin_commits_are_not_audit_commits(self):
        h = FakeHarness()
        real.c1_ok_new_path(h)
        self.assertGreater(h.admin_commits, 0)


class FakeCursor:
    """FAKE raw cursor: forwards COMMIT / END to its connection like a real one would."""

    def __init__(self, conn):
        self.connection, self.closed, self.rows = conn, False, []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False

    def execute(self, query, params=None):
        text = query if isinstance(query, str) else query.as_string(None)
        self.connection.log.append(("cursor", text))
        if text.strip().rstrip(";").strip().upper() in ("COMMIT", "END"):
            self.connection.commit()
        self.rows = [{"one": 1}] if text.startswith("SELECT") else []
        return self

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return list(self.rows)

    def close(self):
        self.closed = True


class RawWithCursor(AuditCommits.Raw):
    def cursor(self, row_factory=None):
        cursor = FakeCursor(self)
        cursor.row_factory = row_factory
        return cursor


def cursor_commit_count() -> int:
    """A correct-looking audit connection that commits through a cursor (fake)."""
    tracked = real.CommitTracker(RawWithCursor())
    with tracked.cursor() as cursor:
        cursor.execute("COMMIT")
    return tracked.commits


class CursorCommits(unittest.TestCase):
    def test_plain_and_context_cursors(self):
        for word in ("COMMIT", "END", "commit;", " end "):
            with self.subTest(word=word):
                raw = RawWithCursor()
                tracked = real.CommitTracker(raw)
                tracked.cursor().execute(word)
                with tracked.cursor() as cursor:
                    cursor.execute(word)
                self.assertEqual((tracked.commits, raw.log.count("commit")), (2, 2))   # counted and forwarded

    def test_cursor_connection_commit(self):
        raw = RawWithCursor()
        tracked = real.CommitTracker(raw)
        with tracked.cursor() as cursor:
            cursor.connection.commit()
        tracked.cursor().connection.commit()
        self.assertEqual((tracked.commits, raw.log.count("commit")), (2, 2))

    def test_sql_objects(self):
        from psycopg import sql
        raw = RawWithCursor()
        tracked = real.CommitTracker(raw)
        tracked.cursor().execute(sql.SQL("COMMIT"))
        with tracked.cursor() as cursor:
            cursor.execute(sql.SQL("END"))
        tracked.execute(sql.SQL("COMMIT"))
        tracked.execute(sql.Composed([sql.SQL("END")]))
        self.assertEqual(tracked.commits, 4)

    def test_reads_fetch_and_close_are_not_commits(self):
        raw = RawWithCursor()
        tracked = real.CommitTracker(raw)
        with tracked.cursor(row_factory="dict") as cursor:
            cursor.execute("SELECT 1")
            self.assertEqual((cursor.fetchone(), cursor.fetchall(), cursor.row_factory), ({"one": 1}, [{"one": 1}], "dict"))
        self.assertTrue(cursor.closed)
        plain = tracked.cursor()
        plain.execute("SELECT 1")
        plain.close()
        tracked.rollback()
        tracked.execute("SELECT 'COMMIT'")
        self.assertEqual((tracked.commits, raw.log.count("commit")), (0, 0))

    def test_cursor_commit_fails_c1(self):
        with self.assertRaises(real.CheckFailed):
            real.c1_ok_new_path(FakeHarness(commits=cursor_commit_count()))

    def test_admin_commits_still_not_counted(self):
        h = FakeHarness(commits=0)
        real.c1_ok_new_path(h)
        self.assertGreater(h.admin_commits, 0)


class RawExecReturnsCursor(RawWithCursor):
    """FAKE raw connection whose execute() returns the cursor that ran the query, like psycopg."""

    def execute(self, query, params=()):
        cursor = FakeCursor(self)
        cursor.execute(query, params)
        return cursor


def execute_cursor_commit_count() -> int:
    tracked = real.CommitTracker(RawExecReturnsCursor())
    tracked.execute("SELECT 1").connection.commit()
    return tracked.commits


class ExecuteReturnedCursor(unittest.TestCase):
    def test_returned_cursor_connection_commit(self):
        raw = RawExecReturnsCursor()
        tracked = real.CommitTracker(raw)
        tracked.execute("SELECT 1").connection.commit()
        self.assertEqual((tracked.commits, raw.log.count("commit")), (1, 1))

    def test_returned_cursor_execute_commit_or_end(self):
        for word in ("COMMIT", "END"):
            with self.subTest(word=word):
                raw = RawExecReturnsCursor()
                tracked = real.CommitTracker(raw)
                tracked.execute("SELECT 1").execute(word)
                self.assertEqual((tracked.commits, raw.log.count("commit")), (1, 1))

    def test_returned_cursor_reads_are_not_commits(self):
        raw = RawExecReturnsCursor()
        tracked = real.CommitTracker(raw)
        cursor = tracked.execute("SELECT 1")
        self.assertEqual((cursor.fetchone(), cursor.fetchall(), list(iter(cursor.rows))), ({"one": 1}, [{"one": 1}], [{"one": 1}]))
        cursor.close()
        self.assertTrue(cursor.closed)
        self.assertEqual((tracked.commits, raw.log.count("commit")), (0, 0))

    def test_existing_paths_count_once(self):
        sys.path.insert(0, str(BACKEND))
        from app.database import AppPostgresConnection
        raw = RawExecReturnsCursor()
        tracked = real.CommitTracker(raw)
        tracked.execute("COMMIT")                                        # connection execute: once, not twice
        self.assertEqual(tracked.commits, 1)
        app = AppPostgresConnection(tracked)
        self.assertEqual(app.execute("SELECT 1").fetchone(), {"one": 1})
        app.execute("COMMIT")
        app.commit()
        self.assertEqual(tracked.commits, 3)
        with tracked.cursor() as cursor:
            cursor.execute("END")
        tracked.cursor().connection.commit()
        self.assertEqual((tracked.commits, raw.log.count("commit")), (5, 5))

    def test_this_path_fails_c1(self):
        with self.assertRaises(real.CheckFailed):
            real.c1_ok_new_path(FakeHarness(commits=execute_cursor_commit_count()))


class FreshProcess(unittest.TestCase):
    """tests/_ops_audit_real_probe.py, one case per new process (no earlier app import can hide the
    order). Import paths and order only; no real audit SQL runs."""

    @classmethod
    def setUpClass(cls):
        cls.cases, cls.output = {}, ""
        for case in ("check_entry", "bad_signature", "bad_manifest"):
            done = subprocess.run([sys.executable, str(TESTS_DIR / "_ops_audit_real_probe.py"), case],
                                  capture_output=True, text=True, timeout=300, cwd=str(TESTS_DIR))
            cls.output += done.stdout + done.stderr
            for line in done.stdout.splitlines():
                if line.startswith("PROBE "):
                    found = json.loads(line[6:])
                    cls.cases[found["case"]] = found

    def case(self, name):
        found = self.cases.get(name)
        self.assertIsNotNone(found, self.output[-1500:])
        return found

    def test_check_entry_runs_and_records_the_fake_audit(self):
        found = self.case("check_entry")
        self.assertEqual(found["code"], 0)
        results = {name: (status, details) for name, status, details in found["results"]}
        self.assertEqual(results["c1_ok_new_path"][0], "pass")
        self.assertEqual(results["c1_ok_new_path"][1]["settings"], ["repeatable read", "on", "15s", "5s"])
        self.assertIn("audit:body", found["events"])

    def test_environment_fixed_at_first_app_import(self):
        env = next(e["env"] for e in self.case("check_entry")["events"] if isinstance(e, dict))
        self.assertEqual(env, {"APP_ENV": "test", "DATABASE_URL": "sqlite:///:memory:", "PYTHON_DOTENV_DISABLED": "1"})

    def test_order_precheck_import_connect_audit(self):
        events = [e for e in self.case("check_entry")["events"] if isinstance(e, str)]
        first_import = next(i for i, e in enumerate(events) if e.startswith("import:"))
        self.assertLess(events.index("preflight:passed"), first_import)
        self.assertLess(first_import, events.index("connect"))
        self.assertLess(events.index("connect"), events.index("audit:body"))

    def test_bad_signature_or_manifest_imports_and_connects_nothing(self):
        for name, reason in (("bad_signature", "preflight_approval_signature_invalid"),
                             ("bad_manifest", "preflight_manifest_signature_invalid")):
            with self.subTest(case=name):
                found = self.case(name)
                self.assertEqual((found["code"], found["reason"]), (2, reason))
                self.assertFalse([e for e in found["events"] if isinstance(e, str) and e.startswith("import:")])
                self.assertNotIn("connect", found["events"])
        self.assertNotIn(pf.SECRET, self.output)


class XidProbeRollback(unittest.TestCase):
    """The diagnostic xid probe never changes the cleanup: one raw rollback in every case (fakes)."""

    class Raw(RawWithCursor):
        def __init__(self, probe_error=None, rollback_error=None):
            super().__init__()
            self.probe_error, self.rollback_error, self.rollbacks = probe_error, rollback_error, 0

        def cursor(self, row_factory=None):
            cursor, raw = super().cursor(row_factory), self

            class C:
                def __enter__(self):
                    return self

                def __exit__(self, *exc):
                    return False

                def execute(self, query, params=None):
                    if query == real.PROBE_XID and raw.probe_error is not None:
                        raise raw.probe_error
                    cursor.execute(query, params)
                    return self

                def fetchone(self):
                    return {"x": None} if True else None
            return C()

        def rollback(self):
            self.rollbacks += 1
            self.log.append("rollback")
            if self.rollback_error is not None:
                raise self.rollback_error

    def tracked(self, **kwargs):
        raw = self.Raw(**kwargs)
        tracker = real.CommitTracker(raw)
        tracker.probe["calls"] = 1                      # the audit has started on this connection
        return raw, tracker

    def test_probe_ok_one_rollback(self):
        raw, tracker = self.tracked()
        tracker.rollback()
        self.assertEqual((raw.rollbacks, tracker.probe.get("xid", "missing"), "xid_probe_failed" in tracker.probe),
                         (1, None, False))

    def test_probe_failure_still_rolls_back_and_is_not_a_result(self):
        raw, tracker = self.tracked(probe_error=psycopg.OperationalError(pf.SECRET))
        tracker.rollback()
        self.assertEqual(raw.rollbacks, 1)
        self.assertNotIn("xid", tracker.probe)
        self.assertEqual(tracker.probe["xid_probe_failed"], "OperationalError")
        self.assertNotIn(pf.SECRET, json.dumps(tracker.probe))

    def test_probe_and_rollback_failures(self):
        raw, tracker = self.tracked(probe_error=psycopg.OperationalError(pf.SECRET),
                                    rollback_error=psycopg.OperationalError("rollback"))
        with self.assertRaises(psycopg.OperationalError) as caught:
            tracker.rollback()
        self.assertEqual(str(caught.exception), "rollback")        # the rollback failure goes up, as before
        self.assertEqual((raw.rollbacks, tracker.probe["xid_probe_failed"]), (1, "OperationalError"))

    def test_rollback_outside_the_audit_is_unchanged(self):
        raw = self.Raw(probe_error=AssertionError("probe must not run"))
        tracker = real.CommitTracker(raw)
        tracker.rollback()
        self.assertEqual((raw.rollbacks, tracker.probe), (1, {}))

    def test_interrupt_and_probe_failure_propagate_the_interrupt(self):
        sys.path.insert(0, str(BACKEND))
        from psycopg.pq import TransactionStatus
        from app.database import AppPostgresConnection
        from app.srs.invariant_audit import read_snapshot
        raw = self.Raw(probe_error=psycopg.OperationalError(pf.SECRET))
        raw.info = type("Info", (), {"transaction_status": TransactionStatus.IDLE})()
        tracker = real.CommitTracker(raw)
        with self.assertRaises(KeyboardInterrupt):
            with read_snapshot(AppPostgresConnection(tracker)):
                tracker.probe["calls"] = 1
                raise KeyboardInterrupt
        self.assertEqual((raw.rollbacks, tracker.probe["xid_probe_failed"]), (1, "OperationalError"))

    def test_probe_failure_fails_the_check(self):
        with self.assertRaises(real.CheckFailed) as caught:
            real.c1_ok_new_path(FakeHarness(probe_extra={"xid_probe_failed": "OperationalError"}))
        self.assertEqual(caught.exception.kind, "harness_defect")


CHILD = r'''
import sys
from pathlib import Path
sys.path.insert(0, {scripts!r}); sys.path.insert(0, {tests!r})
import psycopg
def forbidden(*_, **__):
    raise AssertionError("a connection function was called")
psycopg.connect = forbidden
import _ops_pg62 as g
import _ops_audit_real as real
folder = Path({folder!r})
g.single_run = lambda target=None: g.Record(folder)
g.server_is_ours = lambda pid, target=None: True
g.pg_environment_present = lambda: False

class FakeHarness:
    def __init__(self, rec):
        self.rec, self.pid = rec, 1
    def set_password(self):
        pass
    def close(self):
        pass

real.Harness = FakeHarness
if {scenario!r} in ("commit_violation", "cursor_commit_violation", "execute_cursor_commit_violation"):
    import test_ops_audit_real_guard as tg
    def committing(rec):
        counts = {{"commit_violation": lambda: 1, "cursor_commit_violation": tg.cursor_commit_count,
                  "execute_cursor_commit_violation": tg.execute_cursor_commit_count}}
        h = tg.FakeHarness(commits=counts[{scenario!r}]())
        h.rec = rec
        return h
    real.Harness = committing
def ok(h):
    return {{"status": "partial", "exit": 3}}      # the audit's expected partial is a passing check
def fail(h):
    raise real.CheckFailed("product_defect", "synthetic failure")
def unrecordable(h):
    return {{"x": object()}}
scenario = {scenario!r}
names = list(real.PLANNED)
if scenario == "xid_probe_failure":
    import test_ops_audit_real_guard as tg
    def probing(rec):
        h = tg.FakeHarness(probe_extra={{"xid_probe_failed": "OperationalError"}})
        h.rec = rec
        return h
    real.Harness = probing
    real.CHECKS = [(n, real.c1_ok_new_path if n == "c1_ok_new_path" else ok) for n in names]
elif scenario == "preparation_failure":
    g.server_is_ours = lambda pid, target=None: False             # the server is not the recorded one
    real.CHECKS = [(n, ok) for n in names]
elif scenario in ("commit_violation", "cursor_commit_violation", "execute_cursor_commit_violation"):
    real.CHECKS = [(n, real.c1_ok_new_path if n == "c1_ok_new_path" else ok) for n in names]
elif scenario == "incomplete":
    real.CHECKS = [(n, ok) for n in names[:-1]]
else:
    special = {{"middle_fail": fail, "record_fail": unrecordable}}.get(scenario)
    real.CHECKS = [(n, special if (special and i == 1) else ok) for i, n in enumerate(names)]
source = Path({runner!r}).read_text(encoding="utf-8")
block = source[source.index('if __name__ == "__main__":'):]
sys.argv = [{runner!r}] + {argv!r}
namespace = dict(vars(real)); namespace["__name__"] = "__main__"
exec(compile(block, {runner!r}, "exec"), namespace)
'''


class ExitStatus(unittest.TestCase):
    def run_child(self, scenario: str, argv=("check",)) -> int:
        tmp = Path(tempfile.mkdtemp(prefix="ops_audit_real_cli_test_"))
        self.addCleanup(shutil.rmtree, tmp)
        (tmp / "run").mkdir()
        code = CHILD.format(scripts=str(BACKEND / "scripts"), tests=str(TESTS_DIR), folder=str(tmp / "run"),
                            scenario=scenario, runner=str(TESTS_DIR / "_ops_audit_real.py"), argv=list(argv))
        done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120,
                              cwd=str(TESTS_DIR))
        self.assertNotIn("a connection function was called", done.stdout + done.stderr)
        return done.returncode

    def test_runner_exit_status(self):
        for scenario, expected in (("pass", 0), ("middle_fail", 1), ("record_fail", 1), ("incomplete", 1),
                                   ("commit_violation", 1), ("cursor_commit_violation", 1),
                                   ("execute_cursor_commit_violation", 1), ("preparation_failure", 1),
                                   ("xid_probe_failure", 1)):
            with self.subTest(scenario=scenario):
                self.assertEqual(self.run_child(scenario), expected)
        self.assertEqual(self.run_child("pass", argv=("check", "extra")), 2)

    def test_import_does_no_external_work(self):
        code = (f"import sys, os, subprocess; sys.path[:0] = [{str(BACKEND / 'scripts')!r}, {str(TESTS_DIR)!r}]\n"
                "import psycopg\ncalls = []\n"
                "def fail(*a, **k): calls.append('call'); raise AssertionError('external work at import')\n"
                "psycopg.connect = fail; subprocess.run = fail; os.mkdir = fail\n"
                "import _ops_audit_real\nprint('CALLS', len(calls))")
        done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120,
                              cwd=str(TESTS_DIR))
        self.assertIn("CALLS 0", done.stdout, done.stderr[-500:])
        self.assertFalse(T.root.exists())


if __name__ == "__main__":
    unittest.main()

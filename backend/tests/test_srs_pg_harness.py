"""Gate E-1 (E-D8): regression tests for tests/_srs_pg_harness.py.

No test reaches a server. psycopg.connect is patched to fail in every test; the
harness only ever gets a fake connection to an in-memory fake catalog. The fake
models what the harness relies on -- READ COMMITTED visibility of other
sessions' commits, transactional DDL, relation oids and pg_class.xmin -- but it
is a model. Passing here proves the harness's own rules, NOT that anything works
on PostgreSQL (PostgreSQL stays unverified and a release blocker).

Run directly:      python tests/test_srs_pg_harness.py
Or via discovery:   python -m unittest discover -s tests
"""

from __future__ import annotations

import copy
import itertools
import os
import re
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

TESTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS_DIR))
sys.path.insert(0, str(TESTS_DIR.parent))

import psycopg  # noqa: E402

import _srs_pg_harness as harness  # noqa: E402
from _local_postgres_guard import INSPECT_SQL, TARGET_ENV_VARS, UnsafePostgresTarget  # noqa: E402
from _srs_pg_harness import (  # noqa: E402
    MARKER_TABLE, OPT_IN_VAR, URL_VAR, HarnessStopped, PgRun, requested,
)

SECRET = "s3cr3t-pw-e1"
URL = f"postgresql://e1:{SECRET}@localhost:5432/jp_vocab_test_e"
WRITE = re.compile(r"^\s*(CREATE|INSERT|TRUNCATE|DROP|UPDATE|DELETE|ALTER)\b", re.I)


class LockBusy(RuntimeError):
    pass


class FakeServer:
    """A tiny catalog. Committed state lives in `state`; each connection keeps its
    own uncommitted operations and sees other sessions' commits at once.

    Lock model (a model of PostgreSQL, not PostgreSQL): `LOCK TABLE a, b IN ACCESS
    EXCLUSIVE MODE` resolves each NAME to the object that has it at that moment and
    takes an exclusive lock on that object (oid), waiting at most the connection's
    lock_timeout; TRUNCATE / DROP take the same lock implicitly; locks are released
    at commit, rollback or close. Another session's DROP / replace waits for the
    lock of the object it drops (with a timeout). Real PG lock modes, queueing and
    deadlock detection are not modelled."""

    def __init__(self):
        self.dbname, self.address, self.port = "jp_vocab_test_e", "127.0.0.1", 5432
        self.state = {"tables": {}, "deps": {}, "fks": set(), "extra": [], "others": (0, 0, 0, 0), "marker": None}
        self.oids = itertools.count(16384)
        self.xids = itertools.count(700)
        self.attempted: list[str] = []
        self.committed: list[str] = []
        self.calls = 0
        self.open = 0
        self.fail: dict[str, Exception] = {}
        self.cond = threading.Condition()
        self.locks: dict[int, int] = {}            # oid -> holding connection id
        self.lock_log: list[tuple[str, int, int]] = []  # (acquire|release, connection id, oid)
        self.conn_ids = itertools.count(1)
        self.hooks: list = []                      # (predicate(sql), action) run once before a statement
        self.cleaned: list[tuple[str, str, int]] = []   # committed (TRUNCATE|DROP, name, oid)
        self.connections: list = []                # every FakeConnection handed out, in order
        self.faults: list[dict] = []               # per next connection: {"rollback": exc, "close": exc}

    def wait_unlocked(self, oid, me, timeout):
        """Called with self.cond held. False on timeout."""
        return self.cond.wait_for(lambda: self.locks.get(oid) in (None, me), timeout=timeout)

    def connect(self, url, autocommit=False):
        assert url == URL
        self.calls += 1
        self.open += 1
        connection = FakeConnection(self)
        self.connections.append(connection)
        return connection

    # --- another session's committed work -------------------------------
    def external_create(self, name, *, deps=(), fks=()):
        with self.cond:
            xid = str(next(self.xids))
            self.state["tables"][name] = {"oid": next(self.oids), "xmin": xid}
            for dep, parent in deps:
                self.state["deps"][dep] = {"parent": parent, "oid": next(self.oids), "xmin": xid}
            self.state["fks"] |= set(fks)

    def replace(self, name, timeout=0.0):
        """DROP (waiting for its lock) + CREATE of the same name by someone else."""
        with self.cond:
            current = self.state["tables"].get(name)
            if current is not None and not self.wait_unlocked(current["oid"], None, timeout):
                raise LockBusy("replace waited too long")
            self.state["tables"][name] = {"oid": next(self.oids), "xmin": str(next(self.xids))}
            self.cond.notify_all()

    def external_drop(self, name, timeout=0.0):
        with self.cond:
            current = self.state["tables"][name]
            if not self.wait_unlocked(current["oid"], None, timeout):
                raise LockBusy("drop waited too long")
            del self.state["tables"][name]
            self.state["deps"] = {d: x for d, x in self.state["deps"].items() if x["parent"] != name}
            self.state["fks"] = {(a, b) for a, b in self.state["fks"] if name not in (a, b)}

    def hold_lock(self, name):
        """Another session takes and keeps the lock of `name`; returns its release."""
        with self.cond:
            oid = self.state["tables"][name]["oid"]
            assert self.locks.get(oid) is None
            self.locks[oid] = -1

        def release():
            with self.cond:
                self.locks.pop(oid, None)
                self.cond.notify_all()
        return release


class FakeCursor:
    def __init__(self, conn):
        self.conn, self.rows = conn, []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=()):
        self.rows = self.conn.run(sql, params)

    def fetchall(self):
        return list(self.rows)

    def fetchone(self):
        return self.rows[0] if self.rows else None


class FakeConnection:
    def __init__(self, server):
        self.server, self.read_only, self.closed = server, False, False
        self.xid = str(next(server.xids))
        self.ops: list = []
        self.statements: list[str] = []
        self.id = next(server.conn_ids)
        self.held: set[int] = set()
        self.lock_timeout = 5.0
        self.pending_cleaned: list[tuple[str, str, int]] = []
        # Transaction model for SET TRANSACTION (as in PG): allowed only before the first
        # query of a transaction; commit / rollback start a new one.
        self.query_ran = False
        self.tx_settings: list[str] = []
        self.log: list[str] = []                   # every statement this connection ran
        self.faults = server.faults.pop(0) if server.faults else {}
        self.close_attempted = False

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False

    def cursor(self, row_factory=None):
        return FakeCursor(self)

    def execute(self, sql, params=()):
        cursor = FakeCursor(self)
        cursor.execute(sql, params)
        return cursor

    def view(self):
        with self.server.cond:
            state = copy.deepcopy(self.server.state)
        for op in self.ops:
            op(state)
        return state

    def commit(self):
        with self.server.cond:
            for op in self.ops:
                op(self.server.state)
            self.server.committed += self.statements
            self.server.cleaned += self.pending_cleaned
        self.ops, self.statements, self.pending_cleaned = [], [], []
        self.xid = str(next(self.server.xids))
        self.query_ran, self.tx_settings = False, []
        self.release()

    def rollback(self):
        if "rollback" in self.faults:
            raise self.faults["rollback"]  # the transaction stays as it was
        self._end()

    def _end(self):
        self.ops, self.statements, self.pending_cleaned = [], [], []
        self.xid = str(next(self.server.xids))
        self.query_ran, self.tx_settings = False, []
        self.release()

    def release(self):
        with self.server.cond:
            for oid in sorted(self.held):
                if self.server.locks.get(oid) == self.id:
                    del self.server.locks[oid]
                    self.server.lock_log.append(("release", self.id, oid))
            self.held.clear()
            self.server.cond.notify_all()

    def close(self):
        self.close_attempted = True
        if not self.closed:
            self.closed = True
            self._end()
            self.server.open -= 1
        if "close" in self.faults:
            raise self.faults["close"]  # the socket is gone either way; the error is reported

    def lock(self, names, tables):
        for name in names:
            if name not in tables:
                raise RuntimeError(f"relation does not exist (driver text with {SECRET})")
            oid = tables[name]["oid"]
            with self.server.cond:
                if not self.server.wait_unlocked(oid, self.id, self.lock_timeout):
                    raise RuntimeError("canceling statement due to lock timeout")
                if oid not in self.held:
                    self.server.locks[oid] = self.id
                    self.held.add(oid)
                    self.server.lock_log.append(("acquire", self.id, oid))

    def write(self, sql, op):
        self.ops.append(op)
        self.statements.append(sql.strip())

    def run(self, sql, params):
        s = self.server
        for prefix, error in s.fail.items():
            if sql.strip().startswith(prefix):
                raise error
        for hook in list(s.hooks):
            if hook[0](sql):
                s.hooks.remove(hook)
                hook[1]()
        self.log.append(sql.strip())
        if sql.startswith("SET TRANSACTION"):
            if self.query_ran:
                raise RuntimeError("SET TRANSACTION must be called before any query")
            self.tx_settings.append(sql)
            return []
        if not sql.startswith("SET LOCAL"):
            self.query_ran = True
        if WRITE.match(sql):
            assert not self.read_only
            s.attempted.append(sql.strip())
        m = re.fullmatch(r"SET LOCAL lock_timeout = '(\d+)ms'", sql)
        if m:
            self.lock_timeout = int(m.group(1)) / 1000
            return []
        v = self.view()
        tables = dict(v["tables"])
        if v["marker"] is not None:
            tables[MARKER_TABLE] = v["marker"]
        if sql == INSPECT_SQL:
            schemas, routines, types, ext = v["others"]
            return [(s.dbname, schemas, len(tables) + len(v["deps"]) + len(v["extra"]), routines, types, ext)]
        if sql == harness.TARGET_SQL:
            return [(s.dbname, s.address, s.port)]
        if sql == harness.XID_SQL:
            return [(self.xid,)]
        if sql == getattr(harness, "MARKER_OID_SQL", object()):
            return [(v["marker"]["oid"],)] if v["marker"] is not None else []
        if sql == "SELECT 1":
            return [(1,)]
        if sql == harness.RELATIONS_SQL:
            return ([("public", n, "r", None, t["oid"], t["xmin"]) for n, t in tables.items()]
                    + [("public", n, "i", d["parent"], d["oid"], d["xmin"]) for n, d in v["deps"].items()]
                    + list(v["extra"]))
        if sql == harness.FOREIGN_KEYS_SQL:
            return sorted(v["fks"])
        if sql == harness.OTHER_OBJECTS_SQL:
            return [v["others"]]
        if sql == harness.CREATE_MARKER_SQL:
            assert v["marker"] is None
            meta = {"oid": next(s.oids), "xmin": self.xid, "rows": []}
            self.write(sql, lambda st, m=meta: st.__setitem__("marker", copy.deepcopy(m)))
            return []
        if sql == harness.INSERT_MARKER_SQL:
            self.write(sql, lambda st, n=params[0]: st["marker"]["rows"].append(n))
            return []
        m = re.fullmatch(r"LOCK TABLE (.+) IN ACCESS EXCLUSIVE MODE", sql)
        if m:
            self.lock([n.strip().removeprefix("public.") for n in m.group(1).split(",")], tables)
            return []
        if sql == harness.READ_MARKER_SQL:
            if v["marker"] is None:
                raise RuntimeError(f"relation does not exist (driver text with {SECRET})")
            return [(n,) for n in v["marker"]["rows"]]
        m = re.fullmatch(r"CREATE TABLE public\.(\w+) \(.*\)", sql)
        if m:
            meta = {"oid": next(s.oids), "xmin": self.xid}
            self.write(sql, lambda st, n=m.group(1), t=meta: st["tables"].__setitem__(n, dict(t)))
            return []
        m = re.fullmatch(r"CREATE INDEX (\w+) ON public\.(\w+) \(.*\)", sql)
        if m:
            meta = {"parent": m.group(2), "oid": next(s.oids), "xmin": self.xid}
            self.write(sql, lambda st, n=m.group(1), d=meta: st["deps"].__setitem__(n, dict(d)))
            return []
        m = re.fullmatch(r"ALTER TABLE public\.(\w+) .*", sql)
        if m:
            self.write(sql, lambda st, n=m.group(1), x=self.xid: st["tables"][n].__setitem__("xmin", x))
            return []
        m = re.fullmatch(r"(TRUNCATE|DROP) TABLE (.+?)( RESTART IDENTITY)? RESTRICT", sql)
        if m:
            ordered = [n.strip().removeprefix("public.") for n in m.group(2).split(",")]
            names = set(ordered)
            assert names <= set(tables), names
            self.lock(ordered, tables)  # TRUNCATE / DROP lock implicitly, as in PG
            self.pending_cleaned += [(m.group(1), n, tables[n]["oid"]) for n in ordered]
            if any(b in names and a not in names for a, b in v["fks"]):  # RESTRICT
                raise RuntimeError("cannot truncate a table referenced in a foreign key constraint")
            if m.group(1) == "DROP":
                def drop(st, names=names):
                    if MARKER_TABLE in names:
                        st["marker"] = None
                    for n in names:
                        st["tables"].pop(n, None)
                    st["deps"] = {d: x for d, x in st["deps"].items() if x["parent"] not in names}
                    st["fks"] = {(a, b) for a, b in st["fks"] if a not in names}
                self.write(sql, drop)
            else:
                self.write(sql, lambda st: None)
            return []
        raise AssertionError(f"unexpected SQL: {sql[:60]}")


def refuse_real_connect(*a, **k):
    raise AssertionError("psycopg.connect must never be called in these tests")


def create(*names, index=None):
    """A managed creation step: DDL only through the harness's connection."""
    def step(connection):
        with connection.cursor() as cursor:
            for name in names:
                cursor.execute(f"CREATE TABLE public.{name} (id INTEGER)")
            if index:
                cursor.execute(f"CREATE INDEX {index[0]} ON public.{index[1]} (id)")
    return step


class Base(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(psycopg, "connect", refuse_real_connect)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.server = FakeServer()
        self.env = {URL_VAR: URL, OPT_IN_VAR: "1", "DATABASE_URL": "sqlite:///./keep.db", "APP_ENV": "development"}
        self.addCleanup(harness._ACTIVE.clear)

    def run_(self):
        return PgRun(URL, connect=self.server.connect, environ=self.env)

    def started(self):
        run = self.run_()
        run.start()
        return run

    def owned_run(self):
        run = self.started()
        run.track_creation(create("users", "vocab_items", index=("vocab_items_pkey", "vocab_items")),
                           expected={"users", "vocab_items"})
        return run

    def fresh(self):
        harness._ACTIVE.clear()
        self.server = FakeServer()
        self.env = {URL_VAR: URL, OPT_IN_VAR: "1"}

    def assert_stopped_without_writes(self, call, pattern, *, no_connect=False, step_rolled_back=False):
        """Nothing committed. Without step_rolled_back nothing was even sent; with it
        only the step's own DDL was sent and then rolled back."""
        before = list(self.server.attempted), list(self.server.committed), self.server.calls
        with self.assertRaisesRegex(UnsafePostgresTarget, pattern) as ctx:
            call()
        self.assertEqual(self.server.committed, before[1])
        sent = self.server.attempted[len(before[0]):]
        if step_rolled_back:
            self.assertTrue(all(re.match(r"CREATE (TABLE|INDEX)", q) for q in sent), sent)
        else:
            self.assertEqual(sent, [])
        if no_connect:
            self.assertEqual(self.server.calls, before[2], "the connect function must not be called")
        self.assert_clean_message(str(ctx.exception))
        return ctx.exception

    def assert_clean_message(self, text):
        for leak in (SECRET, URL, "localhost", "driver text"):
            self.assertNotIn(leak, text)
        marker = self.server.state["marker"]
        for nonce in (marker or {}).get("rows", []):
            self.assertNotIn(nonce, text)

    def cleanup_sql(self):
        return [c for c in self.server.attempted if c.startswith(("TRUNCATE", "DROP"))]

    def tearDown(self):
        self.assertEqual(self.server.open, 0, "every connection must be closed")


class RequestTests(Base):
    def test_off_by_default(self):
        for env in ({}, {URL_VAR: URL}, {URL_VAR: URL, OPT_IN_VAR: ""}):
            self.assertIsNone(requested(env))
        self.assertEqual(self.server.calls, 0)

    def test_opt_in_rules(self):
        with self.assertRaisesRegex(HarnessStopped, "empty"):
            requested({OPT_IN_VAR: "1"})
        for value in ("yes", "true", "0", "2", " 1", "1 "):
            with self.assertRaisesRegex(HarnessStopped, "exactly 1"):
                requested({URL_VAR: URL, OPT_IN_VAR: value})
        self.assertEqual(requested({URL_VAR: URL, OPT_IN_VAR: "1"}), URL)

    def test_reuses_the_local_guard(self):
        bad = {
            "remote": f"postgresql://e1:{SECRET}@example.invalid/jp_vocab_test_e",
            "not a test name": f"postgresql://e1:{SECRET}@localhost/jp_vocab",
            "query host": f"postgresql://e1:{SECRET}@localhost/jp_vocab_test_e?host=example.invalid",
        }
        for name, url in bad.items():
            with self.subTest(name):
                with self.assertRaises(UnsafePostgresTarget) as ctx:
                    requested({URL_VAR: url, OPT_IN_VAR: "1"})
                self.assertNotIn(SECRET, str(ctx.exception))
                with self.assertRaises(UnsafePostgresTarget):  # the constructor checks too
                    PgRun(url, connect=self.server.connect, environ={URL_VAR: url, OPT_IN_VAR: "1"})
        self.assertEqual(self.server.calls, 0)


class PreflightTests(Base):
    """Every call of the connect function is preceded by the full safety check."""

    PATHS = ("start", "verify", "track_creation", "reset", "teardown")

    def call(self, run, path):
        if path == "track_creation":
            return run.track_creation(create("later"), expected={"later"})
        return getattr(run, path)()

    def prepared(self, path):
        self.fresh()
        return self.run_() if path == "start" else self.owned_run()

    def test_direct_start_without_opt_in_never_connects(self):
        for env_change in ({OPT_IN_VAR: None}, {OPT_IN_VAR: "yes"}, {OPT_IN_VAR: "0"}, {URL_VAR: None}):
            with self.subTest(env_change):
                self.fresh()
                for key, value in env_change.items():
                    self.env.pop(key) if value is None else self.env.__setitem__(key, value)
                self.assert_stopped_without_writes(self.run_().start, "OPT_IN|URL", no_connect=True)
                self.assertEqual(harness._ACTIVE, [])

    def test_opt_in_removed_or_url_changed_during_the_run(self):
        changes = {
            "opt-in removed": lambda env: env.pop(OPT_IN_VAR),
            "opt-in wrong": lambda env: env.__setitem__(OPT_IN_VAR, "true"),
            "url changed": lambda env: env.__setitem__(URL_VAR, URL.replace("jp_vocab_test_e", "jp_vocab_test_x")),
            "url removed": lambda env: env.pop(URL_VAR),
        }
        for name, change in changes.items():
            for path in self.PATHS:
                with self.subTest(change=name, path=path):
                    run = self.prepared(path)
                    tables = copy.deepcopy(self.server.state)
                    change(self.env)
                    self.assert_stopped_without_writes(lambda: self.call(run, path), "OPT_IN|URL", no_connect=True)
                    self.assertEqual(self.server.state, tables)

    def test_target_variables_added_during_the_run(self):
        self.assertEqual(len(TARGET_ENV_VARS), 5)
        for var in TARGET_ENV_VARS:
            for path in self.PATHS:
                with self.subTest(var=var, path=path):
                    run = self.prepared(path)
                    self.env[var] = "203.0.113.5"
                    self.assert_stopped_without_writes(lambda: self.call(run, path), var, no_connect=True)

    def test_database_url_must_match_while_active(self):
        for path in self.PATHS[1:]:
            with self.subTest(path=path):
                run = self.prepared(path)
                with run.activate():
                    self.env["DATABASE_URL"] = "sqlite:///./elsewhere.db"
                    self.assert_stopped_without_writes(lambda: self.call(run, path), "DATABASE_URL", no_connect=True)

    def test_the_emptiness_check_connection_is_guarded_too(self):
        run = self.run_()
        seen = []
        real = harness.assert_empty_postgres_test_database

        def spy(url, connect=None):
            seen.append(connect)
            self.env["PGHOST"] = "203.0.113.5"  # appears right before that connection
            return real(url, connect)

        with mock.patch.object(harness, "assert_empty_postgres_test_database", spy):
            self.assert_stopped_without_writes(run.start, "could not inspect", no_connect=True)
        self.assertTrue(run.stopped)
        self.assertEqual(len(seen), 1)
        self.assertIsNot(seen[0], self.server.connect)


class StartTests(Base):
    def test_start_creates_only_the_marker(self):
        run = self.started()
        self.assertEqual(self.server.state["tables"], {})
        self.assertEqual(len(self.server.state["marker"]["rows"]), 1)
        self.assertEqual(self.server.committed[0].split()[0:3], ["CREATE", "TABLE", f"public.{MARKER_TABLE}"])
        self.assertEqual(run.owned, [])
        self.assertNotIn(self.server.state["marker"]["rows"][0], repr(run))
        self.assertNotIn(SECRET, repr(run))

    def test_one_run_per_process(self):
        self.started()
        self.assert_stopped_without_writes(self.run_().start, "already active", no_connect=True)

    def test_refuses_a_database_that_is_not_empty(self):
        self.server.external_create("leftover")
        with self.assertRaises(UnsafePostgresTarget):
            self.run_().start()
        self.assertEqual(self.server.attempted, [])

    def test_refuses_a_changed_target_after_connecting(self):
        for attr, value, pattern in (("address", "203.0.113.5", "loopback"), ("port", 5433, "port")):
            with self.subTest(attr):
                self.fresh()
                setattr(self.server, attr, value)
                self.assert_stopped_without_writes(self.run_().start, pattern)

    def test_marker_rolled_back_when_the_inventory_is_wrong(self):
        original = FakeConnection.run

        def racing(conn, sql, params):  # someone commits a table right after the emptiness check
            if sql == harness.CREATE_MARKER_SQL:
                conn.server.external_create("intruder")
            return original(conn, sql, params)

        with mock.patch.object(FakeConnection, "run", racing):
            with self.assertRaisesRegex(HarnessStopped, "did not create"):
                self.run_().start()
        self.assertEqual(self.server.committed, [])
        self.assertIsNone(self.server.state["marker"])
        self.assertIn("intruder", self.server.state["tables"])
        self.assertEqual(harness._ACTIVE, [])


class OwnershipTests(Base):
    def test_external_table_appearing_during_a_step_is_not_owned(self):
        run = self.started()

        def step(connection):
            create("users")(connection)
            self.server.external_create("intruder")  # another session commits mid-step

        self.assert_stopped_without_writes(lambda: run.track_creation(step, expected={"users"}), "not created by this run",
                                           step_rolled_back=True)
        self.assertEqual(run.owned, [])
        self.assertIn("intruder", self.server.state["tables"])      # preserved
        self.assertNotIn("users", self.server.state["tables"])      # our DDL rolled back
        self.assert_stopped_without_writes(run.teardown, "already stopped", no_connect=True)  # stays stopped
        self.assertFalse(any("intruder" in c for c in self.cleanup_sql()))

    def test_external_table_with_an_expected_name_is_not_owned(self):
        run = self.started()

        def step(connection):
            create("decks")(connection)
            self.server.external_create("users")  # the name we expected, made by someone else

        self.assert_stopped_without_writes(lambda: run.track_creation(step, expected={"users", "decks"}),
                                           "not created by this run", step_rolled_back=True)
        self.assertEqual(run.owned, [])
        self.assertIn("users", self.server.state["tables"])
        self.assertNotIn("decks", self.server.state["tables"])

    def test_external_index_on_our_new_table_is_not_owned(self):
        run = self.started()

        def step(connection):
            create("users")(connection)
            self.server.state["deps"]["sneaky_idx"] = {"parent": "users", "oid": 1, "xmin": "1"}

        self.assert_stopped_without_writes(lambda: run.track_creation(step, expected={"users"}),
                                           "not created by this run", step_rolled_back=True)
        self.assertEqual(run.owned, [])

    def test_unexpected_or_missing_names_stop(self):
        for expected, pattern in (({"users"}, "not expected"), ({"users", "extra", "decks"}, "expected table")):
            with self.subTest(expected=expected):
                self.fresh()
                run = self.started()
                self.assert_stopped_without_writes(
                    lambda: run.track_creation(create("users", "extra"), expected=expected), pattern,
                    step_rolled_back=True)
                self.assertEqual(run.owned, [])
                self.assertEqual(self.server.state["tables"], {})

    def test_existing_table_altered_by_a_step_is_not_adopted_twice(self):
        run = self.owned_run()
        oids = dict(run.owned_oids)

        def step(connection):
            with connection.cursor() as cursor:
                cursor.execute("ALTER TABLE public.users ADD COLUMN x INTEGER")  # xmin is ours, oid is old

        run.track_creation(step, expected=set())
        self.assertEqual(run.owned_oids, oids)

    def test_same_name_replacement_is_not_cleaned(self):
        for path in ("reset", "teardown", "verify"):
            with self.subTest(path=path):
                self.fresh()
                run = self.owned_run()
                self.server.replace("users")
                replaced = copy.deepcopy(self.server.state["tables"]["users"])
                self.assert_stopped_without_writes(getattr(run, path), "replaced")
                self.assertEqual(self.server.state["tables"]["users"], replaced)
                self.assertEqual(self.cleanup_sql(), [])

    def test_marker_replacement_stops(self):
        run = self.owned_run()
        rows = list(self.server.state["marker"]["rows"])
        self.server.state["marker"] = {"oid": 1, "xmin": "1", "rows": rows}  # same nonce, other object
        self.assert_stopped_without_writes(run.reset, "marker")

    def test_failed_step_adopts_nothing(self):
        run = self.started()

        def step(connection):
            create("users")(connection)
            self.server.external_create("intruder")
            raise RuntimeError("init failed half way")

        with self.assertRaisesRegex(RuntimeError, "half way"):
            run.track_creation(step, expected={"users"})
        self.assertEqual(run.owned, [])
        self.assertNotIn("users", self.server.state["tables"])  # rolled back
        self.assertIn("intruder", self.server.state["tables"])  # not ours, kept, not cleaned
        self.assert_stopped_without_writes(run.teardown, "did not create")
        self.assertEqual(self.cleanup_sql(), [])

    def test_normal_creation_cleanup_and_rerun(self):
        run = self.started()
        with run.activate():
            self.assertEqual((self.env["DATABASE_URL"], self.env["APP_ENV"]), (URL, "test"))
            run.track_creation(create("users", "decks", "vocab_items", index=("vocab_items_pkey", "vocab_items")),
                               expected={"users", "decks", "vocab_items"})
            self.assertEqual(sorted(run.owned), ["decks", "users", "vocab_items"])
            run.verify()
            run.reset()
            run.reset(restart_identity=True)
        self.assertEqual((self.env["DATABASE_URL"], self.env["APP_ENV"]), ("sqlite:///./keep.db", "development"))
        truncates = [c for c in self.server.committed if c.startswith("TRUNCATE")]
        self.assertEqual(len(truncates), 2)
        for statement in truncates:
            self.assertNotIn("CASCADE", statement)
            self.assertNotIn(MARKER_TABLE, statement)
            self.assertEqual(set(re.findall(r"public\.(\w+)", statement)), {"users", "decks", "vocab_items"})
        run.teardown()
        drops = [c for c in self.server.committed if c.startswith("DROP")]
        self.assertEqual(len(drops), 2)
        self.assertTrue(all("CASCADE" not in d and d.endswith("RESTRICT") for d in drops))
        self.assertIn(MARKER_TABLE, drops[1])
        self.assertEqual((self.server.state["tables"], self.server.state["marker"]), ({}, None))
        self.assertEqual(harness._ACTIVE, [])
        again = self.run_()  # empty again: a rerun can start
        again.start()
        again.teardown()


class GuardTests(Base):
    def test_database_switch_stops(self):
        run = self.owned_run()
        self.server.dbname = "jp_vocab_test_other"
        self.assert_stopped_without_writes(run.reset, "not the checked")
        self.assert_stopped_without_writes(run.verify, "already stopped", no_connect=True)

    def test_marker_damage_stops(self):
        for name, change in {"other nonce": "other", "two rows": "two", "missing": "drop"}.items():
            with self.subTest(name):
                self.fresh()
                run = self.owned_run()
                marker = self.server.state["marker"]
                if change == "drop":
                    self.server.state["marker"] = None
                elif change == "two":
                    marker["rows"].append("1" * 32)
                else:
                    marker["rows"] = ["0" * 32]
                self.assert_stopped_without_writes(run.teardown, "marker")

    def test_foreign_objects_stop_cleanup(self):
        cases = {
            "table": lambda s: s.external_create("not_mine"),
            "view": lambda s: s.state["extra"].append(("public", "v", "v", None, 1, "1")),
            "other schema": lambda s: s.state["extra"].append(("elsewhere", "t", "r", None, 2, "1")),
            "routine": lambda s: s.state.__setitem__("others", (0, 1, 0, 0)),
            "type": lambda s: s.state.__setitem__("others", (0, 0, 1, 0)),
            "extension": lambda s: s.state.__setitem__("others", (0, 0, 0, 1)),
            "index of a foreign table": lambda s: s.state["deps"].__setitem__(
                "x_idx", {"parent": "not_mine", "oid": 3, "xmin": "1"}),
            "reference into owned": lambda s: s.state["fks"].add(("vocab_items", MARKER_TABLE)),
            "owned table vanished": lambda s: s.state["tables"].pop("users"),
        }
        for name, change in cases.items():
            with self.subTest(name):
                self.fresh()
                run = self.owned_run()
                change(self.server)
                state = copy.deepcopy(self.server.state)
                self.assert_stopped_without_writes(
                    run.reset, "unexpected|did not create|not belonging|crosses|disappeared|could not lock")
                self.assertEqual(self.server.state, state)
                self.assertEqual(self.cleanup_sql(), [])

    def test_driver_error_rolls_back_without_leaking(self):
        run = self.owned_run()
        self.server.fail["TRUNCATE"] = RuntimeError(f"boom {SECRET} at localhost")
        with self.assertRaisesRegex(HarnessStopped, "rolled back") as ctx:
            run.reset()
        self.assert_clean_message(str(ctx.exception))
        self.assertFalse(any(c.startswith("TRUNCATE") for c in self.server.committed))

    def test_connect_failure_is_a_clean_stop(self):
        run = self.owned_run()
        run._connect = mock.Mock(side_effect=OSError(f"could not reach localhost with {SECRET}"))
        with self.assertRaisesRegex(HarnessStopped, "could not connect") as ctx:
            run.verify()
        self.assert_clean_message(str(ctx.exception))

    def test_environment_restored_when_it_was_absent(self):
        self.env.pop("DATABASE_URL")
        self.env.pop("APP_ENV")
        run = self.started()
        with self.assertRaises(KeyError), run.activate():
            raise KeyError("boom")
        self.assertNotIn("DATABASE_URL", self.env)
        self.assertNotIn("APP_ENV", self.env)
        run.teardown()


class CleanupRaceTests(Base):
    """reset / teardown against a concurrent same-name replacement (EXECUTION_PLAN 1-2-2).
    The lock behaviour is the fake's model of PostgreSQL; real locks are an E-2 item."""

    PATHS = ("reset", "teardown")
    NAMES = ("users", "decks", "vocab_items")
    JOIN = 5.0

    def owned3(self):
        self.fresh()
        run = self.started()
        run.track_creation(create(*self.NAMES), expected=set(self.NAMES))
        run.lock_timeout_ms = 200
        return run

    def oid(self, name):
        return self.server.state["tables"][name]["oid"]

    @staticmethod
    def cleanup_sql(sql):
        return sql.startswith(("TRUNCATE", "DROP TABLE public."))

    @classmethod
    def first_owned_touch(cls, sql):
        """The cleanup's first statement on an owned table: its lock, or (without one) the cleanup SQL."""
        return (sql.startswith("LOCK TABLE public.") and MARKER_TABLE not in sql) or cls.cleanup_sql(sql)

    def assert_untouched(self, oids):
        self.assertEqual(self.server.cleaned, [])
        self.assertEqual(self.server.locks, {})
        for name, oid in oids.items():
            if name in self.server.state["tables"]:
                self.assertEqual(self.oid(name), oid, name)
        self.assertIsNotNone(self.server.state["marker"])

    def test_1_replaced_before_the_lock_is_refused_after_locking(self):
        for path in self.PATHS:
            with self.subTest(path=path):
                run = self.owned3()
                original = self.oid("users")
                self.server.hooks.append((self.first_owned_touch, lambda: self.server.replace("users")))
                self.assert_stopped_without_writes(getattr(run, path), "replaced")
                foreign = self.oid("users")
                self.assertNotEqual(foreign, original)               # the other session's table survives
                self.assertEqual(self.server.cleaned, [])           # nothing truncated / dropped
                self.assertEqual(self.server.locks, {})              # every lock released by the rollback

    def test_2_replacement_attempt_after_the_lock_waits_for_the_cleanup(self):
        for path in self.PATHS:
            with self.subTest(path=path):
                run = self.owned3()
                original = self.oid("users")
                box: dict = {}

                def attempt():
                    try:
                        self.server.replace("users", timeout=self.JOIN)
                    except Exception as error:  # noqa: BLE001
                        box["error"] = error

                def start_other_session():
                    box["thread"] = threading.Thread(target=attempt, daemon=True)
                    box["thread"].start()
                    time.sleep(0.3)
                    box["blocked"] = box["thread"].is_alive()
                    box["cleaned_at_that_time"] = list(self.server.cleaned)

                self.server.hooks.append((self.cleanup_sql, start_other_session))
                getattr(run, path)()
                box["thread"].join(self.JOIN)
                self.assertFalse(box["thread"].is_alive(), "the other session must finish")
                self.assertNotIn("error", box)
                self.assertTrue(box["blocked"], "replacement must wait while the cleanup holds the lock")
                self.assertEqual(box["cleaned_at_that_time"], [])
                ops = {"reset": "TRUNCATE", "teardown": "DROP"}[path]
                self.assertIn((ops, "users", original), self.server.cleaned)  # our object, not theirs
                self.assertNotEqual(self.oid("users"), original)              # theirs came afterwards
                self.assertEqual(self.server.locks, {})

    def test_3_objects_created_after_the_cleanup_are_left_alone(self):
        for path in self.PATHS:
            with self.subTest(path=path):
                run = self.owned3()
                getattr(run, path)()
                cleaned = list(self.server.cleaned)
                self.server.external_create("late")
                if path == "reset":
                    self.assert_stopped_without_writes(run.reset, "did not create")
                else:
                    run.teardown()  # already finished: nothing more
                self.assertIn("late", self.server.state["tables"])
                self.assertEqual(self.server.cleaned, cleaned)
                self.assertFalse(any(name == "late" for _, name, _ in self.server.cleaned))

    def test_4_one_bad_target_rolls_back_everything(self):
        cases = {
            "missing": ("drop", "could not lock"),
            "replaced": ("replace", "replaced"),
            "lock busy": ("hold", "could not lock"),
        }
        for path in self.PATHS:
            for name, (kind, pattern) in cases.items():
                with self.subTest(path=path, case=name):
                    run = self.owned3()
                    oids = {n: self.oid(n) for n in self.NAMES}
                    release = None
                    if kind == "drop":
                        self.server.hooks.append((self.first_owned_touch, lambda: self.server.external_drop("vocab_items")))
                    elif kind == "replace":
                        self.server.hooks.append((self.first_owned_touch, lambda: self.server.replace("decks")))
                    else:
                        release = self.server.hold_lock("vocab_items")
                    started = time.monotonic()
                    try:
                        self.assert_stopped_without_writes(getattr(run, path), pattern)
                    finally:
                        if release:
                            release()
                    self.assertLess(time.monotonic() - started, 3.0, "lock waits are time limited")
                    self.assert_untouched({n: o for n, o in oids.items() if not (kind == "replace" and n == "decks")})

    def test_lock_order_acquire_and_release(self):
        for path in self.PATHS:
            with self.subTest(path=path):
                run = self.owned3()
                names = {self.server.state["marker"]["oid"]: MARKER_TABLE}
                names.update({self.oid(n): n for n in self.NAMES})
                start = len(self.server.lock_log)
                getattr(run, path)()
                log = self.server.lock_log[start:]
                acquired = [names[oid] for event, _, oid in log if event == "acquire"]
                self.assertEqual(acquired, [MARKER_TABLE, "decks", "users", "vocab_items"])
                self.assertEqual({e for e, _, _ in log}, {"acquire", "release"})
                self.assertEqual(len({c for _, c, _ in log}), 1)  # one connection, one transaction
                last_acquire = max(i for i, (e, _, _) in enumerate(log) if e == "acquire")
                first_release = min(i for i, (e, _, _) in enumerate(log) if e == "release")
                self.assertLess(last_acquire, first_release)      # held until commit
                self.assertEqual(self.server.locks, {})
                sql = [q for q in self.server.attempted if q.startswith(("TRUNCATE", "DROP"))]
                self.assertTrue(sql and all("CASCADE" not in q and q.endswith("RESTRICT") for q in sql))

    def test_failure_inside_the_cleanup_releases_every_lock(self):
        for path, prefix in (("reset", "TRUNCATE"), ("teardown", "DROP")):
            with self.subTest(path=path):
                run = self.owned3()
                self.server.fail[prefix] = RuntimeError(f"boom {SECRET}")
                with self.assertRaisesRegex(HarnessStopped, "rolled back") as ctx:
                    getattr(run, path)()
                self.assert_clean_message(str(ctx.exception))
                self.assertEqual((self.server.cleaned, self.server.locks), ([], {}))


def _opt_in_requested() -> bool:
    try:
        return requested(os.environ) is not None
    except UnsafePostgresTarget:
        return True  # requested but unsafe: let the test fail loudly instead of skipping


@unittest.skipUnless(_opt_in_requested(),
                     f"{OPT_IN_VAR}/{URL_VAR} not set: PostgreSQL harness run not requested (unverified)")
class OptInSmoke(unittest.TestCase):
    """Only with explicit opt-in: start -> teardown on the real protected empty DB."""

    def test_start_and_teardown(self):
        run = PgRun(requested(os.environ))
        run.start()
        try:
            run.verify()
        finally:
            run.teardown()


if __name__ == "__main__":
    unittest.main()

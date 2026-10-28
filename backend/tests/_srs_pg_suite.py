"""Gate E-2b: run the existing SRS test modules -- written and validated on SQLite, with
their own synthetic data, clocks and exact expectations -- unchanged against the REAL
protected local PostgreSQL test database (E-1 harness, E-2 adapter, limited role).
Test code only. Opt-in only (the harness variables); never imported by the app.

How a SQLite test runs here:
- one PgRun per process: empty-database check, run marker, the app's schema created in the
  managed step (owned tables proven by catalog xmin), then adapter.app_scope: every app
  connection passes the pre-connect checks and is verified on itself;
- before EACH test the owned tables are emptied (harness reset, RESTRICT, identity
  restarted), so every test starts from an empty database as it did with its own SQLite file;
- a test's `mock.patch.dict(os.environ, {"DATABASE_URL": "sqlite:///..."})` keeps every
  other key but not that DATABASE_URL, so the test's own init_db / repositories reach the
  checked PostgreSQL database (init_db on the current schema runs no DDL, E-D13);
- child processes never inherit a PostgreSQL target: DATABASE_URL (when it is the test
  URL) and the harness variables are removed from every subprocess environment;
- expectations, normalization and product code are untouched. A failure is a result to
  classify (product difference vs. SQLite-only test mechanics), never something to relax.

Excluded up front (they would create relations outside the run's ownership, need their own
empty database, or start an app server process): see EXCLUDED below.

Usage (shell with the harness variables only):
    python tests/_srs_pg_suite.py <module>[.<Class>[.<test>]] ... [--out results.json]
"""

from __future__ import annotations

import hashlib
import json
import re
import os
import subprocess
import sys
import threading
import time
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

EXCLUDED = {
    "test_srs_schema": "builds old SQLite schemas; its PG part needs its own empty database (covered by P-UP1 / E-D13)",
    "test_srs_d2_identity": "rebuilds the SQLite card table (AUTOINCREMENT, PRAGMA): creates relations outside ownership",
    "test_srs_http": "starts an app server child process",
    "test_srs_queue.QueueLoopbackHttpTests": "starts an app server child process",
}


def _filtered_patch_dict(real, url):
    def patch_dict(in_dict, values=(), clear=False, **kwargs):
        if in_dict is os.environ:
            values = dict(values)
            values.update(kwargs)
            kwargs = {}
            if str(values.get("DATABASE_URL", "")).startswith("sqlite"):
                values.pop("DATABASE_URL")
            if clear:
                raise RuntimeError("clear=True on os.environ is not supported in the PG suite")
        return real(in_dict, values, clear=clear, **kwargs)
    return patch_dict


# Gate E-2c: the three cleanup CLIs have a protected local-test-PostgreSQL target. A test's
# `--sqlite-db <its own test .db>` (absent here: its rows are in this run's PostgreSQL) is
# run as the REAL CLI with `--local-test-postgres` -- in-process main() and child process.
CLEANUP_CLIS = ("d2_receipt_minimize", "d2_snapshot_minimize", "d2_snapshot_prune")
CLI_CALLS = {"in_process": 0, "subprocess": 0}


def _test_db_path(value) -> bool:
    path = Path(str(value))
    return (path.suffix == ".db" and not path.exists() and path.parent.name.startswith("jp_vocab_")
            and path.parent.parent == HERE.parent)


def _to_local_postgres(argv):
    argv = [str(a) for a in argv]
    if "--sqlite-db" not in argv:
        return None
    i = argv.index("--sqlite-db")
    if i + 1 >= len(argv) or not _test_db_path(argv[i + 1]):
        return None
    return argv[:i] + ["--local-test-postgres"] + argv[i + 2:]


def _scrub_child_env(url):
    real_init = subprocess.Popen.__init__
    secret_keys = ("SRS_E_TEST_POSTGRES_URL", "SRS_E_TEST_POSTGRES_OPT_IN",
                   "SRS_E_TEST_POSTGRES_MARKER_NONCE", "SRS_E_TEST_POSTGRES_MARKER_OID")

    def init(self, *args, **kwargs):
        env = dict(kwargs.get("env") if kwargs.get("env") is not None else os.environ)
        command = list(args[0]) if args and isinstance(args[0], (list, tuple)) else None
        cli = command is not None and any(Path(str(a)).stem in CLEANUP_CLIS and str(a).endswith(".py")
                                          for a in command)
        rewritten = _to_local_postgres(command) if cli else None
        for key in secret_keys:
            env.pop(key, None)
        if env.get("DATABASE_URL") == url:
            env.pop("DATABASE_URL")
        if rewritten is not None:
            # only this cleanup CLI child gets the dedicated test target (it re-checks it)
            env["SRS_E_TEST_POSTGRES_URL"], env["SRS_E_TEST_POSTGRES_OPT_IN"] = url, "1"
            env.update(CURRENT_RUN.cli_marker_environment())
            args = (rewritten,) + tuple(args[1:])
            CLI_CALLS["subprocess"] += 1
        kwargs["env"] = env
        return real_init(self, *args, **kwargs)
    return mock.patch.object(subprocess.Popen, "__init__", init)


def cleanup_cli_shim():
    """In-process main(argv) of the cleanup CLIs: the same argv rewrite; the CLI's own
    environment changes (it pins DATABASE_URL / APP_ENV before importing the app) are
    undone afterwards, so the rest of the test keeps the checked target."""
    from contextlib import ExitStack

    stack = ExitStack()
    for name in CLEANUP_CLIS:
        module = sys.modules.get(name)
        if module is None:
            continue
        real_main = module.main

        def main(argv=None, real_main=real_main):
            rewritten = _to_local_postgres(argv or [])
            if rewritten is None:
                return real_main(argv)
            CLI_CALLS["in_process"] += 1
            saved = dict(os.environ)
            try:
                os.environ.update(CURRENT_RUN.cli_marker_environment())
                return real_main(rewritten)
            finally:
                os.environ.clear()
                os.environ.update(saved)
        stack.enter_context(mock.patch.object(module, "main", main))
    return stack


class TestSideRow(dict):
    """The app's PostgreSQL rows are dicts (dict_row). SQLite rows also allow row[0]; the
    SQLite-written test helpers use that. Positional access is allowed ONLY when the
    caller's code lives in this tests directory -- app code keeps exact dict behaviour, so
    a product `row[0]` on PostgreSQL still raises KeyError and is reported."""

    def __getitem__(self, key):
        if isinstance(key, int) and not isinstance(key, bool):
            caller = sys._getframe(1).f_code.co_filename
            if Path(caller).resolve().parent == HERE:
                POSITIONAL_TEST_READS["n"] += 1
                return list(self.values())[key]
        return dict.__getitem__(self, key)

    def __iter__(self):
        # sqlite3.Row iterates its VALUES (tuple(row), a, b = row); a dict its keys. Values
        # only for callers in this tests directory; app code keeps dict iteration.
        if Path(sys._getframe(1).f_code.co_filename).resolve().parent == HERE:
            POSITIONAL_TEST_READS["n"] += 1
            return iter(list(self.values()))
        return dict.__iter__(self)


POSITIONAL_TEST_READS = {"n": 0}
CURRENT_RUN = None  # the run of this process, for tests that create their schema themselves
TEST_SIDE_CALLS = {"cursor_iter": 0, "commit": 0, "rollback": 0, "trigger_armed": 0, "trigger_fired": 0,
                   "file_digest": 0, "percent_escaped": 0, "executemany": 0}
INJECTORS: dict = {}  # SQLite-trigger fault injections armed by the current test: name -> (op, table, message)
_TRIGGER = re.compile(r"^\s*CREATE\s+TRIGGER\s+(\w+)\s+BEFORE\s+(INSERT|UPDATE|DELETE)\s+ON\s+(\w+)\s+"
                      r"BEGIN\s+SELECT\s+RAISE\(ABORT,\s*'([^']*)'\);\s*END\s*$", re.I)
_DROP_TRIGGER = re.compile(r"^\s*DROP\s+TRIGGER\s+(IF\s+EXISTS\s+)?(\w+)\s*$", re.I)
_TARGET = {"INSERT": re.compile(r"^\s*INSERT\s+(OR\s+\w+\s+)?INTO\s+(\w+)", re.I),
           "UPDATE": re.compile(r"^\s*UPDATE\s+(\w+)", re.I),
           "DELETE": re.compile(r"^\s*DELETE\s+FROM\s+(\w+)", re.I)}


def _statement_target(query: str):
    for op, pattern in _TARGET.items():
        m = pattern.match(query)
        if m:
            return op, m.group(m.lastindex).lower()
    return None


def _from_tests(depth: int = 2) -> bool:
    return Path(sys._getframe(depth).f_code.co_filename).resolve().parent == HERE


def test_side_connection_api():
    """The SQLite-written tests also iterate a cursor directly and call executemany() on
    the app connection (sqlite3 API). The app's PostgreSQL wrapper has neither. They are
    provided ONLY to callers in this tests directory; app code
    gets exactly the wrapper's behaviour (TypeError / AttributeError), so a product path
    that relies on them still fails on PostgreSQL and is reported."""
    from contextlib import ExitStack
    import app.database as database

    def cursor_iter(self):
        if not _from_tests():
            raise TypeError("'AppPostgresCursor' object is not iterable")
        TEST_SIDE_CALLS["cursor_iter"] += 1
        return iter(self.fetchall())

    # Gate E-2c: commit() / rollback() are the wrapper's own now (product code), so no
    # stand-in is installed for them; their use by tests is no longer a test-side adaptation.
    if not all(name in vars(database.AppPostgresConnection) for name in ("commit", "rollback")):
        raise RuntimeError("AppPostgresConnection.commit / rollback missing; re-review the runner")

    real_execute = database.AppPostgresConnection.execute

    def execute(self, query, params=()):
        if _from_tests():
            m = _TRIGGER.match(query)
            if m:  # a SQLite fault-injection trigger: armed, not created (no DDL)
                INJECTORS[m.group(1).lower()] = (m.group(2).upper(), m.group(3).lower(), m.group(4))
                TEST_SIDE_CALLS["trigger_armed"] += 1
                return real_execute(self, "SELECT 1")
            m = _DROP_TRIGGER.match(query)
            if m:
                INJECTORS.pop(m.group(2).lower(), None)
                return real_execute(self, "SELECT 1")
            if "%" in query and params:  # sqlite3 takes a literal % as is; psycopg needs %%
                TEST_SIDE_CALLS["percent_escaped"] += 1
                query = query.replace("%", "%%")
            return real_execute(self, query, params)
        cursor = real_execute(self, query, params)
        target = _statement_target(query) if INJECTORS else None
        if target and any((op, table) == target for op, table, _ in INJECTORS.values()) and (cursor.rowcount or 0) > 0:
            # what the BEFORE trigger's RAISE(ABORT) does: the statement fails and the
            # transaction is aborted -- on the server, so nothing of it can commit
            TEST_SIDE_CALLS["trigger_fired"] += 1
            real_execute(self, "DO $$ BEGIN RAISE EXCEPTION 'injected (SQLite trigger stand-in)'; END $$")
        return cursor

    def executemany(self, query, seq):
        if not _from_tests():
            raise AttributeError("'AppPostgresConnection' object has no attribute 'executemany'")
        TEST_SIDE_CALLS["executemany"] += 1
        for params in seq:
            execute(self, query, params)

    stack = ExitStack()
    stack.enter_context(mock.patch.object(database.AppPostgresConnection, "execute", execute))
    if "executemany" in vars(database.AppPostgresConnection):
        raise RuntimeError("AppPostgresConnection.executemany exists now; re-review the shim")
    stack.enter_context(mock.patch.object(database.AppPostgresConnection, "executemany", executemany, create=True))
    for cls, name, value in ((database.AppPostgresCursor, "__iter__", cursor_iter),):
        if name in vars(cls):
            raise RuntimeError(f"{cls.__name__}.{name} exists now; the test-side shim must be re-reviewed")
        stack.enter_context(mock.patch.object(cls, name, value, create=True))
    return stack


def test_side_row_factory(cursor):
    from psycopg.rows import dict_row
    make = dict_row(cursor)

    def row(values):
        made = make(values)
        return None if made is None else TestSideRow(made)
    return row


def pg_write_fingerprint(run) -> bytes:
    """Stand-in for the bytes of a test's SQLite file: every owned table's tuples with
    their ctid and xmin (any INSERT / UPDATE / DELETE -- even one writing the same
    values -- changes it), read on the harness's own connection after the target check."""
    digest = hashlib.sha256()
    with run._connection() as connection:
        try:
            run._check_target(connection)
            for table in sorted(run.owned_oids):
                digest.update(table.encode())
                for row in run._rows(connection, f"SELECT ctid::text, xmin::text, row_to_json(t)::text "
                                                 f"FROM public.{table} AS t ORDER BY ctid"):
                    digest.update(("|".join(row) + "\n").encode())
        finally:
            connection.rollback()
    return digest.digest()


def file_digest_shim(run):
    real = Path.read_bytes

    def read_bytes(self):
        if (not self.exists() and self.suffix == ".db" and self.parent.name.startswith("jp_vocab_")
                and self.parent.parent == HERE.parent and _from_tests()):
            TEST_SIDE_CALLS["file_digest"] += 1
            return pg_write_fingerprint(run)
        return real(self)
    return mock.patch.object(Path, "read_bytes", read_bytes)


PID_THREAD: dict = {}  # backend pid of every app connection -> name of the thread that opened it


class WaitMonitor:
    """Gate E-2c: during one test, on the harness's own connection (target check only;
    the run marker is not read), sample every 50 ms which app backend of THIS process holds
    a not-granted lock in this database and which backends pg_blocking_pids() names, as
    (waiting thread, blocking thread, lock type, mode). Proof that a job really waited for
    the other -- the in-process ordering probes of the SQLite race tests cannot show it."""

    def __init__(self, run):
        self.run, self.seen, self.errors = run, set(), []
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._loop, name="e2c-wait-monitor", daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.stop.set()
        self.thread.join(10)

    def _loop(self):
        try:
            with self.run._connection() as connection:
                self.run._check_target(connection)
                connection.rollback()
                while not self.stop.is_set():
                    pids = list(PID_THREAD)
                    if pids:
                        rows = self.run._rows(connection, """
                            SELECT l.pid, l.locktype, l.mode, pg_blocking_pids(l.pid)
                            FROM pg_locks l
                            WHERE NOT l.granted AND l.pid = ANY(%s)
                              AND (l.database IS NULL OR l.database =
                                   (SELECT oid FROM pg_database WHERE datname = current_database()))""", (pids,))
                        connection.rollback()
                        for pid, locktype, mode, blockers in rows:
                            for blocker in blockers or []:
                                self.seen.add((PID_THREAD.get(pid, "?"), PID_THREAD.get(blocker, "other-session"),
                                               locktype, mode))
                    self.stop.wait(0.05)
        except Exception as error:  # noqa: BLE001 -- reported with the test, never a pass
            self.errors.append(type(error).__name__)


def other_backends(run) -> list:
    """Other sessions in this database right now (state, open transaction), read on the
    harness's own connection after the target check. A test that leaves one behind is
    reported by name: the next reset could not lock the owned tables."""
    with run._connection() as connection:
        try:
            run._check_target(connection)
            return [list(r) for r in run._rows(connection, (
                "SELECT state, xact_start IS NOT NULL, wait_event_type FROM pg_stat_activity "
                "WHERE datname = current_database() AND pid <> pg_backend_pid() AND backend_type = 'client backend'"))]
        finally:
            connection.rollback()


SETTLE_SECONDS = 45.0   # a test's own threads / sessions must end within this, or the run stops
TEARDOWN_WAIT = 60.0


def settle(run, started_threads) -> dict:
    """After a test: wait (bounded) until the threads it started have ended and no other
    session is in this database. What was still there right after the test is RECORDED
    under the test's name -- a failing race test can leave a parked thread holding its
    transaction open; waiting for it to end is not a pass and never resets anything."""
    t0 = time.monotonic()
    own = [t for t in threading.enumerate() if t.ident not in started_threads and t is not threading.current_thread()]
    first = {"threads": sorted(t.name for t in own if t.is_alive()), "sessions": other_backends(run)}
    deadline = t0 + SETTLE_SECONDS
    while time.monotonic() < deadline:
        alive = [t for t in own if t.is_alive()]
        if not alive and not other_backends(run):
            break
        for t in alive:
            t.join(0.2)
        if not alive:
            time.sleep(0.2)
    last = {"threads": sorted(t.name for t in own if t.is_alive()), "sessions": other_backends(run)}
    return {"at_end": first, "after_wait": last, "waited": round(time.monotonic() - t0, 2),
            "settled": not last["threads"] and not last["sessions"]}


def _excluded(test_id: str) -> str | None:
    for prefix, reason in EXCLUDED.items():
        if test_id == prefix or test_id.startswith(prefix + "."):
            return reason
    return None


def main(argv: list[str]) -> int:
    # tests import this module by name; run as a script it is __main__ -- one module object
    sys.modules["_srs_pg_suite"] = sys.modules[__name__]
    out = None
    schema_by_test = "--schema-by-test" in argv
    argv = [a for a in argv if a != "--schema-by-test"]
    if "--out" not in argv:
        print("PG suite NOT RUN: --out is required (results and the ownership record are written there)")
        return 2
    if "--out" in argv:
        i = argv.index("--out")
        out = Path(argv[i + 1])
        argv = argv[:i] + argv[i + 2:]
    import _srs_e2_adapter as adapter
    import _srs_pg_harness as harness

    url = harness.requested(os.environ)
    if url is None:
        print("PG suite NOT RUN: harness opt-in not set")
        return 2
    run = harness.PgRun(url)
    run.start()
    results: dict = {"modules": argv, "tests": {}}
    started = time.monotonic()
    try:
        ownership = Path(str(out) + ".ownership.json")

        def save_ownership():
            # oids and names only (no nonce, no URL); saved and read back after EVERY
            # adoption, before anything else runs -- a stopped run stays provable
            record = {"marker_oid": run._marker_oid, "owned": dict(sorted(run.owned_oids.items()))}
            text = json.dumps(record, sort_keys=True)
            ownership.write_text(text, encoding="utf-8")
            if ownership.read_text(encoding="utf-8") != text or record["marker_oid"] is None:
                run.stopped = True
                raise RuntimeError("ownership record not saved / read back identical; stopping")

        real_track = run.track_creation

        def tracked(step, *, expected):
            try:
                return real_track(step, expected=expected)
            finally:
                save_ownership()
        run.track_creation = tracked
        save_ownership()
        if not schema_by_test:
            run.track_creation(adapter.schema_step(), expected=adapter.expected_schema_tables())
        results["ownership_record"] = ownership.name
        results["schema_by_test"] = schema_by_test
        global CURRENT_RUN
        CURRENT_RUN = run
        with adapter.app_scope(run), \
                mock.patch.object(mock.patch, "dict", _filtered_patch_dict(mock.patch.dict, url)), \
                _scrub_child_env(url), \
                test_side_connection_api(), \
                file_digest_shim(run), \
                ExitStack() as after_loading:
            from app import database
            guarded = database.psycopg
            connects = {"n": 0}
            real_connect = guarded.connect

            def counting_connect(*args, **kwargs):
                connects["n"] += 1
                if kwargs.get("row_factory") is not None:
                    from psycopg.rows import dict_row
                    if kwargs["row_factory"] is not dict_row:
                        raise RuntimeError("unexpected app row factory")
                    kwargs["row_factory"] = test_side_row_factory
                connection = real_connect(*args, **kwargs)
                PID_THREAD[connection.info.backend_pid] = threading.current_thread().name
                return connection
            guarded.connect = counting_connect

            loader = unittest.TestLoader()
            suite = unittest.TestSuite()
            for name in argv:
                suite.addTests(loader.loadTestsFromName(name))
            # A module may assign DATABASE_URL at import (test_srs_transactions does);
            # the checked target is put back and the fact is reported, never silently.
            if os.environ.get("DATABASE_URL") != url:
                results["import_reset_database_url"] = True
                os.environ["DATABASE_URL"] = url
            # after loading: the cleanup CLI modules the tests imported get the in-process rewrite
            after_loading.enter_context(cleanup_cli_shim())

            def flat(s):
                for t in s:
                    if isinstance(t, unittest.TestSuite):
                        yield from flat(t)
                    else:
                        yield t

            for test in flat(suite):
                tid = test.id()
                reason = _excluded(tid)
                if reason:
                    results["tests"][tid] = {"status": "excluded", "reason": reason}
                    continue
                if os.environ.get("DATABASE_URL") != url:
                    raise RuntimeError(f"DATABASE_URL is not the checked target before {tid}")
                try:
                    run.reset(restart_identity=True)
                except harness.HarnessStopped as error:
                    results["reset_refused_before"] = tid
                    results["reset_refused"] = str(error)
                    break
                result = unittest.TestResult()
                before = connects["n"]
                threads_before = {t.ident for t in threading.enumerate()}
                reads_before = POSITIONAL_TEST_READS["n"]
                calls_before = dict(TEST_SIDE_CALLS)
                INJECTORS.clear()
                t0 = time.monotonic()
                # in its own suite, so the class's setUpClass / tearDownClass run around it
                PID_THREAD.clear()
                with WaitMonitor(run) as monitor:
                    unittest.TestSuite([test]).run(result)
                entry = {"seconds": round(time.monotonic() - t0, 2), "pg_connects": connects["n"] - before,
                         "positional_test_reads": POSITIONAL_TEST_READS["n"] - reads_before,
                         "test_side_calls": {k: TEST_SIDE_CALLS[k] - calls_before[k] for k in TEST_SIDE_CALLS}}
                if os.environ.get("DATABASE_URL") != url:
                    raise RuntimeError(f"DATABASE_URL was left changed by {tid}")
                if monitor.seen:
                    entry["pg_waits"] = sorted(list(w) for w in monitor.seen)
                if monitor.errors:
                    entry["wait_monitor_errors"] = monitor.errors
                settled = settle(run, threads_before)
                if settled["at_end"]["threads"] or settled["at_end"]["sessions"]:
                    entry["left_at_end"] = settled
                results["tests"][tid] = entry
                if not settled["settled"]:
                    results["unsettled_after"] = tid
                if result.errors or result.failures:
                    entry["status"] = "error" if result.errors else "fail"
                    tb = (result.errors or result.failures)[0][1]
                    entry["trace_tail"] = [line for line in tb.splitlines() if line.strip()][-14:]
                    entry["subfailures"] = len(result.errors) + len(result.failures)
                elif result.skipped:
                    entry["status"] = "skipped"
                    entry["reason"] = result.skipped[0][1]
                elif result.expectedFailures:
                    entry["status"] = "expected_failure"
                elif result.unexpectedSuccesses:
                    entry["status"] = "unexpected_success"
                elif entry["pg_connects"] == 0:
                    entry["status"] = "pass_no_pg"  # passed without one app PG connection
                else:
                    entry["status"] = "pass"
                results["tests"][tid] = entry
                if "unsettled_after" in results:
                    break
                if run.stopped:
                    results["harness_stopped_after"] = tid
                    break
    except BaseException as error:
        results["aborted"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        results["seconds"] = round(time.monotonic() - started, 1)
        try:
            run.teardown()
            results["teardown"] = "ok"
        except Exception as error:  # noqa: BLE001 -- reported, never cleaned by hand
            # the regular teardown, once more, after every other thread of this process has
            # ended (bounded): a parked race thread may still hold its transaction
            results["teardown_first_refusal"] = str(error)
            deadline = time.monotonic() + TEARDOWN_WAIT
            for t in threading.enumerate():
                if t is not threading.current_thread():
                    t.join(max(0.0, deadline - time.monotonic()))
            try:
                run.teardown()
                results["teardown"] = "ok (after waiting for this process's threads)"
            except Exception as again:  # noqa: BLE001
                results["teardown"] = f"refused: {again}"
        results["cli_calls"] = dict(CLI_CALLS)
        _write(results, out)
    ok = set(results["counts"]) <= {"pass", "pass_no_pg", "excluded", "skipped", "expected_failure"}
    return 0 if ok and "reset_refused" not in results and "unsettled_after" not in results         and results["teardown"].startswith("ok") else 1


def _write(results: dict, out) -> None:
    counts: dict = {}
    for entry in results["tests"].values():
        counts[entry["status"]] = counts.get(entry["status"], 0) + 1
    results["counts"] = counts
    text = json.dumps(results, ensure_ascii=False, indent=1, default=str)
    if out:
        out.write_text(text, encoding="utf-8")
    print(json.dumps({"counts": counts, "teardown": results["teardown"], "seconds": results["seconds"],
                      "harness_stopped_after": results.get("harness_stopped_after"),
                      "reset_refused_before": results.get("reset_refused_before"),
                      "aborted": results.get("aborted")}, ensure_ascii=False))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

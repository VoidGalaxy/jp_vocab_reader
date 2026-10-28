"""Gate E-2a: test-only bridge between the app and the E-1 harness (tests/_srs_pg_harness.py).
Test code only -- never imported by the app. Nothing here connects unless the harness's
own opt-in and safety checks pass (see that module).

Two scopes:

1. schema_step(): the app's real schema code (app.database.ensure_schema, which takes a
   connection and branches to create_postgres_tables + ensure_srs_schema + seeding) runs
   on the harness's ONE managed connection, inside the ONE transaction that
   PgRun.track_creation() owns. The app receives the connection wrapped so that:
     - commit / rollback / close / context exit by app code raise StepBoundaryViolation
       (the harness alone ends the transaction);
     - app.database.get_connection and app.database.psycopg.connect are replaced for the
       duration of the step by functions that raise StepBoundaryViolation, so the step
       cannot open a second database connection;
     - the connection's row_factory is dict_row while the app runs (the app reads rows
       by column name) and is put back afterwards (the harness reads tuples).
   Expected tables are declared up front from the app's own CREATE TABLE statements
   (expected_schema_tables()), never inferred from what appeared.

2. app_scope(run): repository / HTTP calls during a comparison scenario. DATABASE_URL and
   APP_ENV point at the checked database (run.activate()), and app.database.psycopg is
   replaced by a shim whose connect() goes through PgRun._guarded_connect -- the full
   pre-connect check (URL, opt-in, local-URL guard, PG* target variables, DATABASE_URL)
   runs before EVERY connection the app opens -- and then PgRun.verify_app_connection()
   checks that very connection (database, loopback address, port, marker value and oid),
   ends the check's transaction, and only then hands it to the app; a failed check closes
   it. run.verify() also runs on entry. The schema step's managed connection is separate
   and keeps its own rules (no commit / rollback / close by app code).

Everything patched is restored on exit, also after a failure. Errors never carry the URL.
"""

from __future__ import annotations

import inspect
import re
from contextlib import ExitStack, contextmanager
from typing import Any, Callable, Iterator
from unittest import mock

import app.database as database
from app.srs import schema as srs_schema

_CREATE = re.compile(r"CREATE TABLE IF NOT EXISTS (\w+)\s*\(")  # statements, not comments


class StepBoundaryViolation(RuntimeError):
    """App code tried to end the managed transaction or open another connection."""


def expected_schema_tables() -> set[str]:
    """The tables the app's PostgreSQL schema code declares, read from its own source
    (create_postgres_tables and the SRS tables), before anything runs."""
    names = set(_CREATE.findall(inspect.getsource(database.create_postgres_tables)))
    for statement in srs_schema._new_tables(True):
        names.update(_CREATE.findall(statement))
    return names


class StepConnection:
    """What AppPostgresConnection wraps during the schema step: statements pass through
    on the managed connection; ending or leaving the transaction is refused."""

    def __init__(self, raw: Any) -> None:
        self._raw = raw

    def execute(self, query: str, params: tuple = ()) -> Any:
        cursor = self._raw.cursor()
        cursor.execute(query, params) if params else cursor.execute(query)
        return cursor

    def _refuse(self, *args: Any, **kwargs: Any) -> Any:
        raise StepBoundaryViolation("app code may not end or leave the managed transaction")

    commit = rollback = close = __enter__ = _refuse

    def __exit__(self, *exc: Any) -> bool:
        raise StepBoundaryViolation("app code may not end or leave the managed transaction")


def _refuse_connection(*args: Any, **kwargs: Any) -> Any:
    raise StepBoundaryViolation("a second database connection was requested inside the managed step")


class _RefusingPsycopg:
    def __init__(self, real: Any) -> None:
        self._real = real

    def connect(self, *args: Any, **kwargs: Any) -> Any:
        _refuse_connection()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._real, name)


@contextmanager
def no_other_connections() -> Iterator[None]:
    with ExitStack() as stack:
        stack.enter_context(mock.patch.object(database, "get_connection", _refuse_connection))
        stack.enter_context(mock.patch.object(database, "psycopg", _RefusingPsycopg(database.psycopg)))
        yield


def schema_step(apply: Callable[[Any], Any] | None = None) -> Callable[[Any], Any]:
    """A PgRun.track_creation() step that runs the app's ensure_schema (or `apply`, for
    tests of the boundary itself) on the managed connection."""
    apply = apply or database.ensure_schema

    def step(raw: Any) -> Any:
        from psycopg.rows import dict_row

        previous = getattr(raw, "row_factory", None)
        raw.row_factory = dict_row
        try:
            with no_other_connections():
                return apply(database.AppPostgresConnection(StepConnection(raw)))
        finally:
            raw.row_factory = previous

    return step


class _GuardedPsycopg:
    """app.database.psycopg during app_scope: every connect is the harness's guarded one."""

    def __init__(self, real: Any, run: Any) -> None:
        self._real, self._run = real, run

    def connect(self, url: str, **kwargs: Any) -> Any:
        connection = self._run._guarded_connect(url, **kwargs)  # pre-connect checks
        try:
            self._run.verify_app_connection(connection)  # this very connection, before the app gets it
        except BaseException:
            # Never handed over and never reused: close is attempted; if even that fails the
            # run is already stopped (verify_app_connection / _stop) and the error stands.
            try:
                connection.close()
            except Exception:
                self._run.stopped = True
            raise
        return connection

    def __getattr__(self, name: str) -> Any:
        return getattr(self._real, name)


@contextmanager
def app_scope(run: Any) -> Iterator[Any]:
    with ExitStack() as stack:
        stack.enter_context(run.activate())
        stack.enter_context(mock.patch.object(database, "psycopg", _GuardedPsycopg(database.psycopg, run)))
        run.verify()
        yield run

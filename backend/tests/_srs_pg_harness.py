"""Gate E-1 (E-D8, approved 2026-10-18): test-only harness for running SRS tests on
one protected, empty, local PostgreSQL test database. Test code only -- never
imported by the app. Design: docs/plans/srs-improvement/gate-e/EXECUTION_PLAN.md
1-2-1.

Off by default. Nothing here connects anywhere unless BOTH are set:
  SRS_E_TEST_POSTGRES_URL     a URL that passes tests/_local_postgres_guard.py
  SRS_E_TEST_POSTGRES_OPT_IN  exactly "1"

Pre-flight (every time, right before the connect function is called -- the
emptiness check's connection included, and whoever constructed the run):
the environment still holds the checked URL, opt-in is exactly "1", the URL
still passes validate_local_postgres_test_url() (which also refuses PGHOST,
PGHOSTADDR, PGSERVICE, PGSERVICEFILE, PGSYSCONFDIR), and inside activate()
DATABASE_URL is that URL. Otherwise the connect function is not called.

After connecting: current_database(), a loopback server address, the checked
port, the marker table's oid and its single nonce row are checked again.

Ownership is proven, never inferred from names or a before/after diff alone:
a creation step runs on the harness's own connection inside ONE transaction.
A new relation is owned only if its oid was not there before the step, its
pg_class.xmin is this transaction's xid (PostgreSQL's own record that this
transaction inserted it), it is a public table whose name the caller declared
in advance (or an index / sequence of such a table). Anything else new -- a
table another session committed meanwhile, an undeclared name, a declared name
that was not created -- stops the step and rolls the whole transaction back:
nothing is adopted, nothing foreign is touched. Owned tables are kept as
(name, oid); a same-name table with another oid stops every later step.

Cleanup touches only owned tables, by explicit name, RESTRICT (never CASCADE,
never a schema). Anything unexpected stops the run with no write. A crashed run
leaves the database non-empty, so the next run refuses it: use a fresh database.

Error messages never contain the URL, password, host, nonce or driver text.
"""

from __future__ import annotations

import os
import re
import secrets
from collections.abc import Callable, Collection, Mapping, MutableMapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator

from _local_postgres_guard import (
    UnsafePostgresTarget,
    assert_empty_postgres_test_database,
    validate_local_postgres_test_url,
)
from psycopg.conninfo import conninfo_to_dict

URL_VAR = "SRS_E_TEST_POSTGRES_URL"
OPT_IN_VAR = "SRS_E_TEST_POSTGRES_OPT_IN"
MARKER_TABLE = "jp_vocab_e_run_marker"
LOOPBACK = frozenset({"127.0.0.1", "::1"})
_NAME = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")
_USER_NS = "n.nspname <> 'information_schema' AND n.nspname NOT LIKE 'pg\\_%'"

TARGET_SQL = "SELECT current_database(), host(inet_server_addr()), inet_server_port()"
# The 32-bit xid that pg_class.xmin carries for rows this transaction inserted.
XID_SQL = "SELECT (txid_current() % 4294967296)::text"
# Every user relation: schema, name, kind, owning table (index / sequence), oid, xmin.
RELATIONS_SQL = f"""
SELECT n.nspname, c.relname, c.relkind,
       COALESCE(
         (SELECT t.relname FROM pg_index i JOIN pg_class t ON t.oid = i.indrelid WHERE i.indexrelid = c.oid),
         (SELECT t.relname FROM pg_depend d JOIN pg_class t ON t.oid = d.refobjid
           WHERE d.classid = 'pg_class'::regclass AND d.objid = c.oid AND d.deptype IN ('a', 'i')
             AND d.refclassid = 'pg_class'::regclass LIMIT 1)
       ),
       c.oid::bigint, c.xmin::text
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE {_USER_NS} AND c.relkind NOT IN ('t')
"""
FOREIGN_KEYS_SQL = f"""
SELECT a.relname, b.relname FROM pg_constraint k
JOIN pg_class a ON a.oid = k.conrelid JOIN pg_namespace n ON n.oid = a.relnamespace
JOIN pg_class b ON b.oid = k.confrelid
WHERE k.contype = 'f' AND {_USER_NS}
"""
OTHER_OBJECTS_SQL = f"""
SELECT
    (SELECT count(*) FROM pg_namespace n WHERE {_USER_NS} AND n.nspname <> 'public'),
    (SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace WHERE {_USER_NS}),
    (SELECT count(*) FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
        WHERE {_USER_NS} AND t.typtype IN ('d', 'e', 'r', 'm')),
    (SELECT count(*) FROM pg_extension WHERE extname <> 'plpgsql')
"""
CREATE_MARKER_SQL = f"CREATE TABLE public.{MARKER_TABLE} (nonce TEXT NOT NULL)"
INSERT_MARKER_SQL = f"INSERT INTO public.{MARKER_TABLE} (nonce) VALUES (%s)"
LOCK_MARKER_SQL = f"LOCK TABLE public.{MARKER_TABLE} IN ACCESS EXCLUSIVE MODE"
READ_MARKER_SQL = f"SELECT nonce FROM public.{MARKER_TABLE}"
MARKER_OID_SQL = ("SELECT c.oid::bigint FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                  "WHERE n.nspname = 'public' AND c.relname = %s")

TABLE_KINDS = frozenset({"r", "p"})
DEPENDENT_KINDS = frozenset({"i", "S", "I"})

# One run (one database) per process.
_ACTIVE: list["PgRun"] = []


class HarnessStopped(UnsafePostgresTarget):
    """The run stopped before writing. Messages name the failed rule only."""


def requested(environ: Mapping[str, str] = os.environ) -> str | None:
    """The checked URL when a PG run is explicitly requested, else None. Parses only.
    PgRun does not rely on this: it repeats the whole check before every connect."""
    if not environ.get(OPT_IN_VAR):
        return None
    _check_request(environ)
    return environ[URL_VAR]


def _check_request(environ: Mapping[str, str], expected_url: str | None = None) -> None:
    if environ.get(OPT_IN_VAR) != "1":
        raise HarnessStopped(f"{OPT_IN_VAR} must be exactly 1")
    url = environ.get(URL_VAR) or ""
    if not url:
        raise HarnessStopped(f"{OPT_IN_VAR} is set but {URL_VAR} is empty")
    if expected_url is not None and url != expected_url:
        raise HarnessStopped(f"{URL_VAR} is not the URL this run checked")
    validate_local_postgres_test_url(url, environ)


@dataclass
class Relation:
    name: str
    kind: str
    parent: str | None
    oid: int
    xmin: str


@dataclass
class Inventory:
    tables: dict[str, Relation] = field(default_factory=dict)
    dependents: dict[str, Relation] = field(default_factory=dict)
    unexpected: list[str] = field(default_factory=list)  # kinds only, never names of foreign things
    foreign_keys: set[tuple[str, str]] = field(default_factory=set)


class PgRun:
    def __init__(self, url: str, *, connect: Callable[..., Any] | None = None,
                 environ: MutableMapping[str, str] | None = None) -> None:
        import psycopg

        validate_local_postgres_test_url(url, {})  # the URL itself; the environment is checked per connect
        self._url = url
        self._connect = connect or psycopg.connect
        self._environ = os.environ if environ is None else environ
        params = conninfo_to_dict(url)
        self._dbname = str(params.get("dbname") or "")
        self._port = int(str(params.get("port") or "5432"))
        self._nonce: str | None = None
        self._marker_oid: int | None = None
        self.owned_oids: dict[str, int] = {}  # owned table -> its oid; the marker is kept apart
        self._active_env = False
        self._saved_env: dict[str, str | None] = {}
        self.stopped = False
        self.lock_timeout_ms = 5000  # every lock wait is time limited

    @property
    def owned(self) -> list[str]:
        return list(self.owned_oids)

    def __repr__(self) -> str:
        return f"PgRun(dbname={self._dbname!r}, owned={len(self.owned_oids)}, started={self._nonce is not None})"

    def cli_marker_environment(self) -> dict[str, str]:
        """Ephemeral expectations for an authorized cleanup CLI, from this run's
        own creation record. Never infer/adopt them from a database or a file."""
        self._preflight()
        if (self._nonce is None or not re.fullmatch(r"[0-9a-f]{32}", self._nonce)
                or type(self._marker_oid) is not int or not 0 < self._marker_oid <= 4294967295):
            raise HarnessStopped("run marker identity is unavailable; nothing was written")
        return {"SRS_E_TEST_POSTGRES_MARKER_NONCE": self._nonce,
                "SRS_E_TEST_POSTGRES_MARKER_OID": str(self._marker_oid)}

    # ---- connections ------------------------------------------------------
    def _stop(self, reason: str) -> HarnessStopped:
        self.stopped = True
        return HarnessStopped(reason + "; nothing was written")

    def _preflight(self) -> None:
        if self.stopped:
            raise HarnessStopped("run already stopped; nothing was written")
        try:
            _check_request(self._environ, self._url)
        except UnsafePostgresTarget as error:
            self.stopped = True
            raise HarnessStopped(f"{error}; nothing was written") from None
        if self._active_env and self._environ.get("DATABASE_URL") != self._url:
            raise self._stop("DATABASE_URL no longer points at the checked test database")

    def _guarded_connect(self, url: str, **kwargs: Any) -> Any:
        """The only way the harness reaches the connect function."""
        if url != self._url:
            raise self._stop("connection requested for another URL")
        self._preflight()
        try:
            return self._connect(url, **kwargs)
        except Exception:
            raise self._stop("could not connect to the test database") from None

    @contextmanager
    def _connection(self) -> Iterator[Any]:
        connection = self._guarded_connect(self._url, autocommit=False)
        try:
            yield connection
        finally:
            try:
                connection.close()
            except Exception:
                pass

    def _rows(self, connection: Any, sql: str, params: tuple = ()) -> list[tuple]:
        with connection.cursor() as cursor:
            cursor.execute(sql, params) if params else cursor.execute(sql)
            return list(cursor.fetchall())

    def _execute(self, connection: Any, sql: str, params: tuple = ()) -> None:
        with connection.cursor() as cursor:
            cursor.execute(sql, params) if params else cursor.execute(sql)

    # ---- checks after connecting -------------------------------------------
    def _check_target(self, connection: Any) -> None:
        self._target_ok(self._rows(connection, TARGET_SQL))

    def _target_ok(self, rows: list) -> None:
        if len(rows) != 1 or len(rows[0]) != 3:
            raise self._stop("could not confirm the test database")
        dbname, address, port = rows[0]
        if dbname != self._dbname:
            raise self._stop("connected database is not the checked test database")
        if address not in LOOPBACK:
            raise self._stop("server address is not loopback")
        if port != self._port:
            raise self._stop("server port is not the checked port")

    def _check_marker(self, connection: Any, inv: Inventory) -> None:
        try:
            self._execute(connection, LOCK_MARKER_SQL)
            rows = self._rows(connection, READ_MARKER_SQL)
        except Exception:
            raise self._stop("run marker is missing") from None
        if self._nonce is None or rows != [(self._nonce,)]:
            raise self._stop("run marker does not belong to this run")
        marker = inv.tables.get(MARKER_TABLE)
        if marker is None or marker.oid != self._marker_oid:
            raise self._stop("run marker was replaced")

    def _verify(self, connection: Any) -> Inventory:
        """Target, marker and owned identities, in the caller's transaction."""
        try:
            self._set_lock_timeout(connection)
            self._check_target(connection)
            inv = self._inventory(connection)
            self._check_marker(connection, inv)
            for name, oid in self.owned_oids.items():
                found = inv.tables.get(name)
                if found is not None and found.oid != oid:
                    raise self._stop("an owned table was replaced by another object")
            return inv
        except HarnessStopped:
            raise
        except Exception:
            raise self._stop("could not confirm the test database") from None

    def verify_app_connection(self, connection: Any) -> None:
        """E-2a: check an app connection ON ITSELF before the app may use it -- database
        name, loopback address, port, the marker's nonce and the marker's object (oid).
        Reads only (no lock), through a tuple cursor (the app's row_factory is left alone),
        then ends this check's transaction with a rollback so the app starts a fresh one
        (its SET TRANSACTION READ ONLY / ISOLATION LEVEL must come before any query).
        On failure the caller closes the connection."""
        if self.stopped:
            raise HarnessStopped("run already stopped; nothing was written")
        target = marker_oid = nonce = None
        check_failed = False
        try:
            from psycopg.rows import tuple_row

            with connection.cursor(row_factory=tuple_row) as cursor:
                cursor.execute(TARGET_SQL)
                target = list(cursor.fetchall())
                cursor.execute(MARKER_OID_SQL, (MARKER_TABLE,))
                marker_oid = list(cursor.fetchall())
                nonce = []
                if marker_oid:
                    cursor.execute(READ_MARKER_SQL)
                    nonce = list(cursor.fetchall())
        except Exception:
            check_failed = True
        # The rollback is part of the hand-over: without it the app would inherit an open
        # transaction (its SET TRANSACTION would fail). Its failure is never ignored.
        try:
            connection.rollback()
        except Exception:
            raise self._stop("could not end the check transaction on the app connection"
                             + ("; the check itself also failed" if check_failed else "")) from None
        if check_failed:
            raise self._stop("could not confirm the test database on the app connection")
        self._target_ok(target)
        if self._nonce is None or nonce != [(self._nonce,)]:
            raise self._stop("run marker does not belong to this run (app connection)")
        if marker_oid != [(self._marker_oid,)]:
            raise self._stop("run marker was replaced (app connection)")

    def verify(self) -> None:
        """For tests to call before their own writes (and between steps)."""
        with self._connection() as connection:
            try:
                self._check_boundary(self._verify(connection))
            finally:
                connection.rollback()

    def _inventory(self, connection: Any) -> Inventory:
        inv = Inventory()
        for schema, name, kind, parent, oid, xmin in self._rows(connection, RELATIONS_SQL):
            relation = Relation(name, kind, parent, int(oid), str(xmin))
            if schema != "public":
                inv.unexpected.append("object outside public")
            elif kind in TABLE_KINDS:
                inv.tables[name] = relation
            elif kind in DEPENDENT_KINDS:
                inv.dependents[name] = relation
            else:
                inv.unexpected.append(f"relation kind {kind}")
        inv.foreign_keys = {(a, b) for a, b in self._rows(connection, FOREIGN_KEYS_SQL)}
        others = self._rows(connection, OTHER_OBJECTS_SQL)
        if len(others) != 1 or any(int(v) != 0 for v in others[0]):
            inv.unexpected.append("schema, routine, type or extension")
        return inv

    def _check_boundary(self, inv: Inventory, owned: Collection[str] | None = None) -> None:
        owned = set(self.owned_oids if owned is None else owned)
        mine = owned | {MARKER_TABLE}
        if inv.unexpected:
            raise self._stop("unexpected object in the test database (" + ", ".join(sorted(set(inv.unexpected))) + ")")
        if set(inv.tables) - mine:
            raise self._stop(f"{len(set(inv.tables) - mine)} table(s) the run did not create")
        if mine - set(inv.tables):
            raise self._stop("an owned table disappeared")
        if any(dep.parent not in mine for dep in inv.dependents.values()):
            raise self._stop("index or sequence not belonging to an owned table")
        if any(a not in owned or b not in owned for a, b in inv.foreign_keys):
            raise self._stop("foreign key crosses the owned boundary")

    # ---- lifecycle --------------------------------------------------------
    def start(self) -> None:
        if self._nonce is not None or _ACTIVE:
            raise HarnessStopped("a run is already active in this process; nothing was written")
        self._preflight()
        assert_empty_postgres_test_database(self._url, self._guarded_connect)
        nonce = secrets.token_hex(16)
        with self._connection() as connection:
            try:
                self._check_target(connection)
                xid = self._rows(connection, XID_SQL)[0][0]
                self._execute(connection, CREATE_MARKER_SQL)
                self._execute(connection, INSERT_MARKER_SQL, (nonce,))
                inv = self._inventory(connection)
                self._check_boundary(inv, ())
                marker = inv.tables[MARKER_TABLE]
                if marker.xmin != str(xid):
                    raise self._stop("run marker was not created by this run")
                connection.commit()
            except HarnessStopped:
                connection.rollback()
                raise
            except Exception:
                connection.rollback()
                raise self._stop("could not create the run marker") from None
        self._nonce, self._marker_oid = nonce, marker.oid
        _ACTIVE.append(self)

    @contextmanager
    def activate(self) -> Iterator["PgRun"]:
        """Point DATABASE_URL (and APP_ENV=test) at the checked database for the
        block; previous values come back afterwards, also on failure."""
        self._saved_env = {k: self._environ.get(k) for k in ("DATABASE_URL", "APP_ENV")}
        self._environ["DATABASE_URL"] = self._url
        self._environ["APP_ENV"] = "test"
        self._active_env = True
        try:
            yield self
        finally:
            self._active_env = False
            for key, value in self._saved_env.items():
                if value is None:
                    self._environ.pop(key, None)
                else:
                    self._environ[key] = value

    def track_creation(self, step: Callable[[Any], Any], *, expected: Collection[str]) -> Any:
        """Run `step(connection)` -- all of its DDL on the given connection, no
        savepoints -- in one transaction and adopt exactly the declared tables it
        created. Anything else new stops the step and rolls everything back."""
        expected = set(expected)
        if any(not _NAME.fullmatch(name) or name == MARKER_TABLE for name in expected):
            raise self._stop("expected table names must be plain lower-case names")
        with self._connection() as connection:
            committed = False
            try:
                before = self._verify(connection)
                self._check_boundary(before)
                xid = str(self._rows(connection, XID_SQL)[0][0])
                seen = {r.oid for r in before.tables.values()} | {r.oid for r in before.dependents.values()}
                result = step(connection)
                after = self._verify(connection)
                if after.unexpected:
                    raise self._stop("unexpected object in the test database")
                new_tables = {n: r for n, r in after.tables.items() if r.oid not in seen}
                new_deps = [r for r in after.dependents.values() if r.oid not in seen]
                if any(r.xmin != xid for r in new_tables.values()) or any(r.xmin != xid for r in new_deps):
                    raise self._stop("a new object was not created by this run")
                if set(new_tables) - expected:
                    raise self._stop("a created table was not expected")
                if expected - set(new_tables):
                    raise self._stop("an expected table was not created")
                adopted = {n: r.oid for n, r in new_tables.items()}
                owned = set(self.owned_oids) | set(adopted)
                self._check_boundary(after, owned)
                connection.commit()
                committed = True
                self.owned_oids.update(adopted)
                return result
            except HarnessStopped:
                raise
            except Exception:
                raise  # the step's own error, after the rollback below
            finally:
                if not committed:
                    connection.rollback()

    def _cleanup(self, sql_for: Callable[[list[str]], list[str]], failure: str) -> None:
        """EXECUTION_PLAN 1-2-2: one connection, one transaction. Lock the marker, then
        the owned tables (sorted, owned names only), THEN read the catalog afresh and
        check names / oids / marker / boundary, then run the cleanup SQL. The locks
        stay until commit or rollback, so nobody can drop or replace a target between
        that check and the cleanup. Any failure rolls everything back."""
        owned = sorted(self.owned_oids)
        with self._connection() as connection:
            try:
                self._set_lock_timeout(connection)
                self._check_target(connection)
                try:
                    self._execute(connection, LOCK_MARKER_SQL)
                except Exception:
                    raise self._stop("run marker is missing or busy") from None
                try:
                    if owned:
                        self._execute(connection, f"LOCK TABLE {', '.join(f'public.{n}' for n in owned)} "
                                                  "IN ACCESS EXCLUSIVE MODE")
                except Exception:
                    raise self._stop("could not lock the owned tables (missing, busy or timed out)") from None
                self._check_boundary(self._verify(connection))  # fresh catalog, after the locks
                for sql in sql_for(owned):
                    self._execute(connection, sql)
                connection.commit()
            except HarnessStopped:
                connection.rollback()
                raise
            except Exception:
                connection.rollback()
                raise self._stop(failure) from None

    def _set_lock_timeout(self, connection: Any) -> None:
        self._execute(connection, f"SET LOCAL lock_timeout = '{int(self.lock_timeout_ms)}ms'")

    def reset(self, *, restart_identity: bool = False) -> None:
        """Empty every owned table (not the marker), RESTRICT, in one transaction."""
        identity = " RESTART IDENTITY" if restart_identity else ""
        self._cleanup(lambda owned: [f"TRUNCATE TABLE {', '.join(f'public.{n}' for n in owned)}{identity} RESTRICT"]
                      if owned else [], "reset failed and was rolled back")

    def teardown(self) -> None:
        """Drop the owned tables and then the marker, RESTRICT, in one transaction,
        leaving the database empty for the next run."""
        if self._nonce is None:
            return
        self._cleanup(lambda owned: ([f"DROP TABLE {', '.join(f'public.{n}' for n in owned)} RESTRICT"] if owned else [])
                      + [f"DROP TABLE public.{MARKER_TABLE} RESTRICT"], "teardown failed and was rolled back")
        self.owned_oids.clear()
        self._nonce = self._marker_oid = None
        _ACTIVE.remove(self)

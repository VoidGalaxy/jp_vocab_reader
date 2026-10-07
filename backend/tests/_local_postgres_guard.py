"""Guard for the opt-in PostgreSQL run of the learning-plan tests.

The tests may only ever touch a throwaway database on this machine that holds
nothing yet. Two checks, both before init_db() or any seed/review/delete:

1. validate_local_postgres_test_url() -- pure parsing, no connection.
   A URL's own hostname is not enough: libpq also reads `host`/`hostaddr` from
   the query string (``postgresql://localhost/db?host=elsewhere``), accepts
   comma-separated host lists, Unix-socket paths and `service` entries, and
   fills unset parameters from PG* environment variables. So the check runs on
   what psycopg itself parses, rejects every key it doesn't know to be
   harmless, refuses PG* variables that could add a connection target, and
   only accepts an explicit test-only database name (TEST_DBNAME_PATTERN).

2. assert_empty_postgres_test_database() -- one read-only connection.
   Confirms the server's current_database() is that test name and that no
   user schema holds anything: no extra schema, relation (table, view,
   sequence, index, ...), routine, user type or extension. A table with zero
   rows still counts as "not empty". Any error while checking (permissions,
   no server, odd result) stops the run too. Nothing is dropped, truncated or
   created to make a database pass -- point the URL at a fresh database.

Error messages name the failed rule or object kind, never the URL, password,
host or the driver's own error text.
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable, Mapping
from typing import Any

import psycopg
from psycopg import ProgrammingError
from psycopg.conninfo import conninfo_to_dict

ALLOWED_SCHEMES = ("postgresql://", "postgres://")
ALLOWED_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
ALLOWED_HOSTADDRS = frozenset({"127.0.0.1", "::1"})
# Parameters that cannot change which server is reached.
ALLOWED_KEYS = frozenset(
    {"host", "hostaddr", "port", "dbname", "user", "password", "sslmode", "connect_timeout", "application_name"}
)
# libpq environment defaults that could add or redirect a connection target
# for a parameter the URL leaves out.
TARGET_ENV_VARS = ("PGHOST", "PGHOSTADDR", "PGSERVICE", "PGSERVICEFILE", "PGSYSCONFDIR")
# Only an obviously throwaway name: jp_vocab_test, jp_vocab_test_plan, ...
TEST_DBNAME_PATTERN = re.compile(r"^jp_vocab_test(?:_[a-z0-9]+)*$")

# System areas are pg_catalog, information_schema and every pg_* schema
# (pg_toast, pg_temp_N, ...). `public` itself is allowed to exist, but must
# hold nothing.
_USER_NS = "n.nspname <> 'information_schema' AND n.nspname NOT LIKE 'pg\\_%'"
INSPECT_SQL = f"""
SELECT
    current_database(),
    (SELECT count(*) FROM pg_namespace n WHERE {_USER_NS} AND n.nspname <> 'public'),
    (SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE {_USER_NS}),
    (SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace WHERE {_USER_NS}),
    (SELECT count(*) FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
        WHERE {_USER_NS} AND t.typtype IN ('d', 'e', 'r', 'm')),
    (SELECT count(*) FROM pg_extension WHERE extname <> 'plpgsql')
"""
INSPECT_COLUMNS = ("schemas", "relations", "routines", "types", "extensions")


class UnsafePostgresTarget(ValueError):
    pass


def validate_local_postgres_test_url(raw_url: str, environ: Mapping[str, str] = os.environ) -> str:
    """Returns the URL unchanged if psycopg would connect only to a test-only
    database on this machine; raises UnsafePostgresTarget otherwise."""
    url = (raw_url or "").strip()
    if not url.startswith(ALLOWED_SCHEMES):
        raise UnsafePostgresTarget("scheme must be postgresql:// or postgres://")

    set_env = [name for name in TARGET_ENV_VARS if environ.get(name)]
    if set_env:
        raise UnsafePostgresTarget(f"unset {', '.join(set_env)} before using the PostgreSQL test URL")

    try:
        params = conninfo_to_dict(url)
    except ProgrammingError:
        raise UnsafePostgresTarget("URL could not be parsed as a PostgreSQL connection string") from None

    unknown = sorted(set(params) - ALLOWED_KEYS)
    if unknown:
        raise UnsafePostgresTarget(f"connection parameter(s) not allowed: {', '.join(unknown)}")

    host = str(params.get("host") or "")
    if not host:
        raise UnsafePostgresTarget("host must be given explicitly")
    if "," in host:
        raise UnsafePostgresTarget("multiple hosts are not allowed")
    if host not in ALLOWED_HOSTS:
        raise UnsafePostgresTarget("host must be localhost, 127.0.0.1 or ::1")

    if "hostaddr" in params:
        hostaddr = str(params["hostaddr"] or "")
        if hostaddr not in ALLOWED_HOSTADDRS:
            raise UnsafePostgresTarget("hostaddr must be 127.0.0.1 or ::1")

    if "port" in params:
        port = str(params["port"] or "")
        if not port.isdigit():
            raise UnsafePostgresTarget("port must be a single number")

    dbname = str(params.get("dbname") or "")
    if not TEST_DBNAME_PATTERN.fullmatch(dbname):
        raise UnsafePostgresTarget("dbname must be a test-only name like jp_vocab_test or jp_vocab_test_plan")
    return url


def assert_empty_postgres_test_database(
    url: str, connect: Callable[..., Any] | None = None
) -> None:
    """One read-only look at the already-validated test database. Raises
    UnsafePostgresTarget unless it is the expected test database and its user
    schemas are completely empty."""
    expected_dbname = str(conninfo_to_dict(url).get("dbname") or "")
    connect = connect or psycopg.connect
    try:
        with connect(url, autocommit=False) as connection:
            # Before the first statement, so the whole transaction is
            # READ ONLY on the server side.
            connection.read_only = True
            with connection.cursor() as cursor:
                cursor.execute(INSPECT_SQL)
                row = cursor.fetchone()
            connection.rollback()
    except Exception as error:  # permissions, no server, ... -- never proceed
        raise UnsafePostgresTarget(
            f"could not inspect the test database ({type(error).__name__}); nothing was changed"
        ) from None

    if row is None or len(row) != 1 + len(INSPECT_COLUMNS):
        raise UnsafePostgresTarget("could not inspect the test database (unexpected result); nothing was changed")
    if row[0] != expected_dbname or not TEST_DBNAME_PATTERN.fullmatch(str(row[0])):
        raise UnsafePostgresTarget("connected database is not the requested test-only database")
    try:
        counts = {name: int(value) for name, value in zip(INSPECT_COLUMNS, row[1:])}
    except (TypeError, ValueError):
        raise UnsafePostgresTarget("could not inspect the test database (unexpected result); nothing was changed") from None
    found = [f"{name}={count}" for name, count in counts.items() if count != 0]
    if found:
        raise UnsafePostgresTarget(
            "test database is not empty (" + ", ".join(found) + "); use a freshly created database"
        )

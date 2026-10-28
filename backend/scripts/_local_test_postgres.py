"""Gate E-2c: the local TEST PostgreSQL target for the U9 / U10-b / U10-e cleanup CLIs.

Only the protected local test database of Gate E: the dedicated variables
SRS_E_TEST_POSTGRES_URL + SRS_E_TEST_POSTGRES_OPT_IN=1, the established local URL guard
(tests/_local_postgres_guard.py: loopback host, limited role, test database name, no
PGHOST/PGSERVICE...), an explicit port. No DATABASE_URL, no .env, no remote or default URL.

After connecting, the connection itself must be the checked target: database name, loopback
server address and port equal the URL's, the role has no superuser / create / replication /
bypass-RLS rights, and the Gate E run marker is the expected table OID and nonce from
the parent harness's creation record (dedicated MARKER_OID / MARKER_NONCE environment
variables). Its single row, table kind and owner are checked too; values are never
inferred from the database. Every refusal, including failed connection termination,
is a fixed reason code -- never the URL, SQL or a raw driver message. A dry run's
session is read-only on the server.
"""

from __future__ import annotations

import hmac
import ipaddress
import os
import re
import sys
from pathlib import Path

MARKER_TABLE = "jp_vocab_e_run_marker"  # tests/_srs_pg_harness.MARKER_TABLE
MARKER_NONCE_VAR = "SRS_E_TEST_POSTGRES_MARKER_NONCE"
MARKER_OID_VAR = "SRS_E_TEST_POSTGRES_MARKER_OID"
MARKER_SQL = """
SELECT c.oid::bigint AS oid, c.relkind::text AS kind,
       c.relowner = (SELECT oid FROM pg_roles WHERE rolname = current_user) AS owned
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public' AND c.relname = %s
"""
SRS_TABLES = ("srs_migration_snapshots", "srs_migration_runs", "srs_review_receipts", "vocab_items",
              "user_word_progress")


class LocalTestPostgresRefused(Exception):
    """`code` is a fixed reason; nothing from the URL or the driver is carried."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def prepare_environment() -> None:
    """Before ANY app import: the app must never pick a database from the process
    environment or an env file on this path."""
    os.environ["APP_ENV"] = "test"
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"
    os.environ["PYTHON_DOTENV_DISABLED"] = "1"


def connect(*, read_only: bool):
    """The app's PostgreSQL wrapper around a checked connection to the local test DB."""
    backend = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(backend))
    sys.path.insert(0, str(backend / "tests"))
    try:
        from _local_postgres_guard import validate_local_postgres_test_url
        import psycopg
        from psycopg.conninfo import conninfo_to_dict
        from psycopg.rows import dict_row
    except Exception:
        raise LocalTestPostgresRefused("local_postgres_support_unavailable") from None
    if os.environ.get("SRS_E_TEST_POSTGRES_OPT_IN") != "1":
        raise LocalTestPostgresRefused("local_postgres_opt_in_required")
    try:
        url = validate_local_postgres_test_url(os.environ.get("SRS_E_TEST_POSTGRES_URL", ""))
        params = conninfo_to_dict(url)
    except Exception:
        raise LocalTestPostgresRefused("local_postgres_url_refused") from None
    if not params.get("port") or not params.get("dbname"):
        raise LocalTestPostgresRefused("explicit_test_port_and_database_required")
    # Expectations come from the parent harness's record, NEVER from this database.
    nonce, oid_text = os.environ.get(MARKER_NONCE_VAR), os.environ.get(MARKER_OID_VAR)
    if nonce is None or oid_text is None:
        raise LocalTestPostgresRefused("run_marker_expectation_required")
    if (not re.fullmatch(r"[0-9a-f]{32}", nonce) or not re.fullmatch(r"[1-9][0-9]{0,9}", oid_text)
            or int(oid_text) > 4294967295):
        raise LocalTestPostgresRefused("run_marker_expectation_invalid")
    expected_oid = int(oid_text)
    options = "-c search_path=public,pg_catalog -c statement_timeout=30000 -c lock_timeout=5000"
    if read_only:
        options += " -c default_transaction_read_only=on"
    try:
        raw = psycopg.connect(url, row_factory=dict_row, connect_timeout=5, options=options)
    except Exception:
        raise LocalTestPostgresRefused("local_postgres_connect_failed") from None
    try:
        row = raw.execute(
            "SELECT current_database() AS db, host(inet_server_addr()) AS address, inet_server_port() AS port, "
            "(SELECT rolsuper OR rolcreaterole OR rolcreatedb OR rolreplication OR rolbypassrls "
            " FROM pg_roles WHERE rolname = current_user) AS privileged, "
            "to_regclass(%s) IS NOT NULL AS marked", (f"public.{MARKER_TABLE}",)).fetchone()
        if (row["db"] != params["dbname"] or row["port"] != int(params["port"]) or row["address"] is None
                or not ipaddress.ip_address(row["address"]).is_loopback or row["privileged"] is not False):
            raise LocalTestPostgresRefused("connected_target_mismatch")
        if not row["marked"]:
            raise LocalTestPostgresRefused("run_marker_missing")
        marker = raw.execute(MARKER_SQL, (MARKER_TABLE,)).fetchone()
        if (marker is None or marker["oid"] != expected_oid or marker["kind"] != "r"
                or marker["owned"] is not True):
            raise LocalTestPostgresRefused("run_marker_mismatch")
        rows = raw.execute(f"SELECT nonce FROM public.{MARKER_TABLE} LIMIT 2").fetchall()
        if len(rows) != 1:
            raise LocalTestPostgresRefused("run_marker_missing")
        actual_nonce = rows[0]["nonce"]
        if (not isinstance(actual_nonce, str) or not re.fullmatch(r"[0-9a-f]{32}", actual_nonce)
                or not hmac.compare_digest(actual_nonce, nonce)):
            raise LocalTestPostgresRefused("run_marker_mismatch")
        # The nonce SELECT holds ACCESS SHARE until rollback. Recheck the catalog
        # after it, so a replacement between the first lookup and that SELECT fails.
        if raw.execute(MARKER_SQL, (MARKER_TABLE,)).fetchone() != marker:
            raise LocalTestPostgresRefused("run_marker_mismatch")
        missing = [t for t in SRS_TABLES
                   if raw.execute("SELECT to_regclass(%s) IS NOT NULL AS present", (f"public.{t}",)).fetchone()["present"]
                   is not True]
        if missing:
            raise LocalTestPostgresRefused("srs_tables_missing")
        raw.rollback()  # the checks leave no transaction open; the tool starts its own
    except Exception as error:
        code = error.code if isinstance(error, LocalTestPostgresRefused) else "connected_target_unverifiable"
        try:
            raw.close()
        except Exception:
            code = "local_postgres_close_failed"
        raise LocalTestPostgresRefused(code) from None
    from app.database import AppPostgresConnection

    return AppPostgresConnection(raw)

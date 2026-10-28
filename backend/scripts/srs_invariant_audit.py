"""E-4 counts-only audit. Explicit existing SQLite file OR opt-in local test PG.

No .env/default database, init_db, writes, output files or production support.
Standalone snapshots cannot prove deletion history: I6/I7 remain not_evaluated.
Exit: 0 complete pass, 1 violation, 2 refused/error/unknown, 3 partial evidence.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> dict:
    parser = argparse.ArgumentParser(description="Read-only local SRS invariant audit (counts only)")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--sqlite-db", type=Path)
    target.add_argument("--local-test-postgres", action="store_true")
    args = parser.parse_args(argv)
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    # Override BEFORE any app import. Never fall back to the process's DATABASE_URL.
    os.environ["APP_ENV"] = "test"
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"
    os.environ["PYTHON_DOTENV_DISABLED"] = "1"
    connection = None
    try:
        if args.sqlite_db is not None:
            import sqlite3

            path = args.sqlite_db.resolve(strict=True)
            if not path.is_file() or path.suffix != ".db":
                raise ValueError("explicit_existing_db_required")
            connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=5)
            connection.row_factory = sqlite3.Row
        else:
            # Reuse the established local URL guard; NEVER the empty-DB writer harness.
            sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
            from _local_postgres_guard import validate_local_postgres_test_url
            import psycopg
            from psycopg.conninfo import conninfo_to_dict
            from psycopg.rows import dict_row

            if os.environ.get("SRS_E_TEST_POSTGRES_OPT_IN") != "1":
                raise ValueError("local_postgres_opt_in_required")
            url = validate_local_postgres_test_url(os.environ.get("SRS_E_TEST_POSTGRES_URL", ""))
            params = conninfo_to_dict(url)
            if not params.get("port"):
                raise ValueError("explicit_test_port_required")
            raw = psycopg.connect(url, row_factory=dict_row, connect_timeout=5,
                                  options="-c default_transaction_read_only=on -c search_path=public,pg_catalog "
                                          "-c statement_timeout=15000 -c lock_timeout=5000")
            from app.database import AppPostgresConnection

            connection = AppPostgresConnection(raw)
        from app.srs.invariant_audit import audit, read_snapshot

        with read_snapshot(connection):
            if args.local_test_postgres:
                row = connection.execute("SELECT current_database() AS db, host(inet_server_addr()) AS address, "
                                         "inet_server_port() AS port").fetchone()
                if (row["db"] != params["dbname"] or row["port"] != int(params["port"])
                        or not ipaddress.ip_address(row["address"]).is_loopback):
                    raise ValueError("connected_target_mismatch")
            report = audit(connection)
    except Exception:  # Fixed report only: driver errors may include URLs, SQL or content.
        report = dict(audit_version=1, status="error", reason="audit_refused_or_unreadable")
    finally:
        if connection is not None:
            try:
                connection.close()
            except Exception:
                report = dict(audit_version=1, status="error", reason="audit_close_failed")
    print(json.dumps(report, sort_keys=True, indent=2))
    code = {"pass": 0, "fail": 1, "error": 2, "unknown": 2, "partial": 3}[report["status"]]
    if code:
        raise SystemExit(code)
    return report


if __name__ == "__main__":
    main()

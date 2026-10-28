"""Gate E-5b operator tool: delete ONE account's data from the server database
(docs/plans/srs-improvement/gate-e/E5B_CONTRACT.md).

Default is a read-only preview: per-table counts, fixed blocking reasons and a plan
fingerprint. Deleting needs ALL of --apply, --confirm-user-id equal to --user-id, and
--expect-plan with the fingerprint printed by the preview; under the account lock the plan
is recomputed and a changed plan is refused. One transaction: all of it or nothing.

Re-typing the account id only guards against operator slips; it is NOT the requester's
identity check, which happens outside this tool. Blocked (e.g. a shared-deck owner, app
feedback whose legal retention is not decided, mixed accounts) is not a refusal of the
request and not a completed deletion: it goes to a separate review.

Targets: an explicit existing SQLite file, or the protected local TEST PostgreSQL
(--local-test-postgres, scripts/_local_test_postgres.py). No env-file / default database,
no other PostgreSQL. Output: counts, codes and the fingerprint -- no email, word, meaning,
example, JSON body, token or connection string. A deletion here is the server database
only; backups, replicas and browser storage are not erased by it (server_db_only).

Exit codes: 0 preview / deleted, 1 failed (rolled back), 2 refused arguments or target,
3 blocked, 4 account_not_found, 5 plan_changed.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

EXIT = {"preview": 0, "deleted": 0, "failed": 1, "blocked": 3, "account_not_found": 4, "plan_changed": 5}


def main(argv: list[str] | None = None) -> dict:
    parser = argparse.ArgumentParser(description="Delete one account from the server database (operator tool)")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--sqlite-db", type=Path)
    target.add_argument("--local-test-postgres", action="store_true")
    parser.add_argument("--user-id", required=True, type=int)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-user-id", type=int)
    parser.add_argument("--expect-plan")
    args = parser.parse_args(argv)
    if args.user_id < 1:
        parser.error("invalid user id")
    if args.apply and args.confirm_user_id != args.user_id:
        parser.error("--apply needs --confirm-user-id equal to --user-id")
    if args.apply and not (isinstance(args.expect_plan, str) and len(args.expect_plan) == 64):
        parser.error("--apply needs --expect-plan with the preview's plan fingerprint")
    database = args.sqlite_db.resolve() if args.sqlite_db is not None else None
    if database is not None and (not database.is_file() or database.suffix != ".db"):
        parser.error("an existing .db SQLite file is required")
    if database is not None:
        os.environ["DATABASE_URL"] = f"sqlite:///{database.as_posix()}"
        os.environ["APP_ENV"] = "test"
        os.environ["PYTHON_DOTENV_DISABLED"] = "1"
    else:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import _local_test_postgres as local_pg

        local_pg.prepare_environment()  # before any app import
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from app import account_deletion
    from app.database import get_connection

    if database is not None:
        opened = get_connection(read_only=not args.apply)
        name = database.name
    else:
        try:
            opened = local_pg.connect(read_only=not args.apply)
        except local_pg.LocalTestPostgresRefused as refused:
            parser.error(f"local test PostgreSQL refused: {refused.code}")
        name = "local_test_postgres"
    try:
        with opened as connection:
            if args.apply:
                report = account_deletion.apply(connection, args.user_id, confirm_user_id=args.confirm_user_id,
                                                expected_plan=args.expect_plan)
            else:
                report = account_deletion.preview(connection, args.user_id)
    except account_deletion.AccountDeletionError as error:
        report = {"report_version": account_deletion.REPORT_VERSION, "status": "failed", "user_id": args.user_id,
                  "applied": False, "error": error.code, "server_db_only": True}
    except Exception as error:  # noqa: BLE001 -- the type name only; driver text may quote stored values
        report = {"report_version": account_deletion.REPORT_VERSION, "status": "failed", "user_id": args.user_id,
                  "applied": False, "error": f"failed:{type(error).__name__}", "server_db_only": True}
    report["database"] = name
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    code = EXIT[report["status"]]
    if code:
        raise SystemExit(code)
    return report


if __name__ == "__main__":
    main()

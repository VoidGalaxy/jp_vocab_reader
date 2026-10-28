"""Gate D-2 U9 operator tool: minimize one account's review receipts in one explicitly
named SQLite file.

Default is a read-only report (ids, field names and counts only -- never the stored
content). Writing needs BOTH --apply and --confirm-user-id equal to --user-id:
  - strips card-content fields from pre-U9 personal receipts (the documented
    exception to "retry = first response"); results, hashes, log ids and times stay;
  - with --purge-expired, also deletes that account's receipts whose created_at is
    readable and 7 days old or older (unreadable/future times are only reported).
Batches run under the account write lock with a compare-and-set on each row's
original text; rerunning skips rows that are already minimal; --after-id resumes.

No env-file or default database fallback, no init_db, never run by the app; PostgreSQL
only as the protected local TEST database (--local-test-postgres, Gate E-2c). Take a copy of the file first; applying it to a real database is a separate
decision. Nothing is copied to files, logs or backups.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> dict:
    parser = argparse.ArgumentParser(description="Minimize review receipts (SQLite file or local test PostgreSQL)")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--sqlite-db", type=Path)
    # Gate E-2c: the protected local TEST PostgreSQL only (scripts/_local_test_postgres.py)
    target.add_argument("--local-test-postgres", action="store_true")
    parser.add_argument("--user-id", required=True, type=int)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-user-id", type=int)
    parser.add_argument("--purge-expired", action="store_true")
    parser.add_argument("--batch-size", type=int, default=200)
    parser.add_argument("--after-id", type=int, default=0)
    args = parser.parse_args(argv)
    database = args.sqlite_db.resolve() if args.sqlite_db is not None else None
    if database is not None and (not database.is_file() or database.suffix != ".db"):
        parser.error("an existing .db SQLite file is required")
    if args.apply and args.confirm_user_id != args.user_id:
        parser.error("--apply needs --confirm-user-id equal to --user-id")
    if args.purge_expired and not args.apply:
        parser.error("--purge-expired needs --apply")
    if args.batch_size < 1 or args.after_id < 0:
        parser.error("invalid batch size or cursor")
    if database is not None:
        os.environ["DATABASE_URL"] = f"sqlite:///{database.as_posix()}"
        os.environ.setdefault("APP_ENV", "test")
    else:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import _local_test_postgres as local_pg

        local_pg.prepare_environment()  # before any app import
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from app.database import get_connection, now_utc
    from app.srs import receipts
    from app.srs.engine import to_utc
    from app.srs.storage import begin_card_write

    if database is not None:
        with get_connection(read_only=not args.apply) as connection:
            report = receipts.minimize_receipts(
                connection, args.user_id, to_utc(now_utc()), apply=args.apply, purge_expired=args.purge_expired,
                batch_size=args.batch_size, after_id=args.after_id, lock=begin_card_write)
        report["database"] = database.name
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return report
    try:
        opened = local_pg.connect(read_only=not args.apply)
    except local_pg.LocalTestPostgresRefused as refused:
        parser.error(f"local test PostgreSQL refused: {refused.code}")
    with opened as connection:
        try:
            report = receipts.minimize_receipts(
                connection, args.user_id, to_utc(now_utc()), apply=args.apply, purge_expired=args.purge_expired,
                batch_size=args.batch_size, after_id=args.after_id, lock=begin_card_write)
        except Exception as error:
            connection.rollback()  # the failed batch is never committed by leaving the block
            if type(error).__module__.split(".")[0] == "psycopg":
                # as on SQLite the run fails with an exception; a driver message (which may
                # quote stored values) is replaced by its type name only
                raise RuntimeError(f"database error: {type(error).__name__}") from None
            raise
    report["database"] = "local_test_postgres"
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report


if __name__ == "__main__":
    main()

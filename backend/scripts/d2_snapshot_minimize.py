"""Gate D-2 U10-b operator tool: rewrite one account's format-1 snapshot / rollback records
(card row copied in) to format 2 in one explicitly named, existing SQLite file.

Default is a read-only report. Writing needs BOTH --apply and --confirm-user-id equal to
--user-id. Only records that pass the same structure / value / fingerprint judgement as
the app (migration._record_shape, _srs_columns_shape, _restorable) are rewritten;
format-2, damaged, unsupported or incomplete records are left exactly as they are and
reported. Nothing is deleted, repaired or guessed.

Batches: rows are visited in id order up to the largest id that existed at the start;
each applied batch holds the account write lock and commits on its own, so the run as a
whole is NOT one transaction -- a failure leaves earlier batches committed and the failed
batch fully rolled back, and the printed `cursor` is the last committed id (rerun with
--after-id <cursor>, or simply rerun: rewritten rows are skipped as already minimal).
Conflicting rows (changed after they were judged) are reported and left; a rerun
re-judges them.

No env-file or default database fallback, no init_db, never run by the app; PostgreSQL only as
the protected local TEST database (--local-test-postgres, Gate E-2c). The report holds ids, kinds, modes, field names, reasons and counts only.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> dict:
    parser = argparse.ArgumentParser(description="Minimize format-1 SRS snapshot records (SQLite file or local test PostgreSQL)")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--sqlite-db", type=Path)
    # Gate E-2c: the protected local TEST PostgreSQL only (scripts/_local_test_postgres.py)
    target.add_argument("--local-test-postgres", action="store_true")
    parser.add_argument("--user-id", required=True, type=int)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-user-id", type=int)
    parser.add_argument("--batch-size", type=int, default=200)
    parser.add_argument("--after-id", type=int, default=0)
    args = parser.parse_args(argv)
    database = args.sqlite_db.resolve() if args.sqlite_db is not None else None
    if database is not None and (not database.is_file() or database.suffix != ".db"):
        parser.error("an existing .db SQLite file is required")
    if args.apply and args.confirm_user_id != args.user_id:
        parser.error("--apply needs --confirm-user-id equal to --user-id")
    if args.batch_size < 1 or args.after_id < 0 or args.user_id < 1:
        parser.error("invalid user id, batch size or cursor")
    if database is not None:
        os.environ["DATABASE_URL"] = f"sqlite:///{database.as_posix()}"
        os.environ.setdefault("APP_ENV", "test")
    else:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import _local_test_postgres as local_pg

        local_pg.prepare_environment()  # before any app import
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from app.database import get_connection
    from app.srs import migration
    from app.srs.storage import begin_card_write

    if database is not None:
        report: dict = {"database": database.name}
        opened = get_connection(read_only=not args.apply)
    else:
        report = {"database": "local_test_postgres"}
        try:
            opened = local_pg.connect(read_only=not args.apply)
        except local_pg.LocalTestPostgresRefused as refused:
            parser.error(f"local test PostgreSQL refused: {refused.code}")
    with opened as connection:
        if database is not None:
            tables = {r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()}
            if not {"srs_migration_snapshots", "srs_migration_runs", "vocab_items", "user_word_progress"} <= tables:
                parser.error("not an app database with SRS tables (no schema is created by this tool)")
        try:
            report.update(migration.minimize_snapshots(
                connection, args.user_id, apply=args.apply, batch_size=args.batch_size, after_id=args.after_id,
                lock=begin_card_write, progress=report))
        except Exception as error:  # noqa: BLE001 - reported, then a non-zero exit
            report["failed"] = type(error).__name__
            print(json.dumps(report, ensure_ascii=False, indent=2))
            raise SystemExit(1) from None
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report


if __name__ == "__main__":
    main()

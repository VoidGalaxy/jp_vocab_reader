"""Gate D-2 U1~U3 operator tool for one explicitly named SQLite file.

Default is a read-only report: personal card id references (U1) and the
identity scan (U3). Writing needs an explicit flag:
  --apply-rebuild  rebuild vocab_items as AUTOINCREMENT and raise its sequence (U2)
  --apply-flags    record identity-unknown flags for the scan findings (U3)

No env-file or default database fallback, no init_db, never PostgreSQL. Take a
copy of the file first; applying it to a real (non-synthetic) database is a
separate decision. History rows are never changed.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Personal card identity report / rebuild (SQLite only)")
    parser.add_argument("--sqlite-db", required=True, type=Path)
    parser.add_argument("--apply-rebuild", action="store_true")
    parser.add_argument("--apply-flags", action="store_true")
    args = parser.parse_args()
    database = args.sqlite_db.resolve()
    if not database.is_file() or database.suffix != ".db":
        parser.error("an existing .db SQLite file is required")
    os.environ["DATABASE_URL"] = f"sqlite:///{database.as_posix()}"
    os.environ.setdefault("APP_ENV", "test")
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from app.database import get_connection
    from app.srs import identity

    report: dict = {"database": database.name}
    with get_connection(read_only=not (args.apply_rebuild or args.apply_flags)) as connection:
        try:
            report["references"] = identity.personal_id_references(connection)
            scan = identity.scan_identity(connection)
        except identity.IdentityError as error:
            print(json.dumps({"stopped": error.code, "detail": error.detail}, ensure_ascii=False))
            raise SystemExit(2) from None
        report["scan"] = {
            "cards_checked": scan.cards_checked,
            "findings": [dict(user_id=f.user_id, card_ref=f.card_ref, reasons=f.reasons) for f in scan.findings],
            "undetermined": [dict(user_id=u, card_ref=r) for u, r in scan.undetermined],
        }
        if args.apply_flags:
            report["flags_written"] = identity.flag_identity_unknown(connection, scan.findings)
            connection.commit()
        if args.apply_rebuild:
            try:
                report["rebuild"] = identity.rebuild_vocab_items_autoincrement(connection)
            except identity.IdentityError as error:
                print(json.dumps({"stopped": error.code, "detail": error.detail}, ensure_ascii=False))
                raise SystemExit(2) from None
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()

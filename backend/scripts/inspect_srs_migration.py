"""Read-only migration preview for explicitly named local synthetic SQLite.

No apply command, no init_db, no env-file/default database fallback.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only synthetic SRS migration preview")
    parser.add_argument("--sqlite-test-db", required=True, type=Path)
    parser.add_argument("--user-id", required=True, type=int)
    parser.add_argument("--personal-id", action="append", type=int, default=[])
    parser.add_argument("--lexeme-id", action="append", type=int, default=[])
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    database = args.sqlite_test_db.resolve()
    if (not database.is_file() or root not in database.parents
            or not database.name.startswith("qa_srs_b2_") or database.suffix != ".db"):
        parser.error("an existing qa_srs_b2_*.db synthetic database inside backend is required")
    if args.user_id <= 0 or not (args.personal_id or args.lexeme_id):
        parser.error("an explicit positive account and card scope is required")
    if any(ref <= 0 for ref in args.personal_id + args.lexeme_id):
        parser.error("card IDs must be positive")
    os.environ["DATABASE_URL"] = f"sqlite:///{database.as_posix()}"
    os.environ["APP_ENV"] = "test"
    sys.path.insert(0, str(root))
    from app.srs.engine import DEFAULT_CONFIG, CardKey
    from app.srs.migration import dry_run

    keys = [CardKey("personal", args.user_id, ref) for ref in args.personal_id]
    keys += [CardKey("lexeme", args.user_id, ref) for ref in args.lexeme_id]
    candidates = dry_run(keys)
    print(json.dumps({"mode": "dry_run", "config_version": DEFAULT_CONFIG.config_version,
                      "cards": [{"kind": p.key.kind, "ref_id": p.key.ref_id,
                                 "version": p.card_version, "quality": p.quality,
                                 "flags": p.flags, "before_hash": p.card_fingerprint,
                                 "proposed_srs_fields": json.loads(p.values_json) if p.values_json else None}
                                for p in candidates]}, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()

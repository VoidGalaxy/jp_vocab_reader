from __future__ import annotations

import argparse
import sys
from pathlib import Path


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.database import init_db  # noqa: E402
from app.repositories.feedback_repository import list_meaning_feedback  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Read-only operator helper: prints recent meaning_feedback rows "
            "(word meaning error reports submitted by users) so they can be "
            "reviewed without a dedicated admin UI. Connects to whatever "
            "DATABASE_URL is configured -- this is read-only, but double "
            "check it points where you expect before running against a real "
            "deployment."
        )
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Maximum number of rows to print (default: 50)",
    )
    parser.add_argument(
        "--status",
        default=None,
        help="Only show reports with this status (e.g. 'open')",
    )
    args = parser.parse_args()

    init_db()
    rows = list_meaning_feedback(limit=args.limit)
    if args.status:
        rows = [row for row in rows if row.get("status") == args.status]

    if not rows:
        print("No meaning_feedback rows found.")
        return 0

    for row in rows:
        word = row.get("surface") or row.get("base_form") or "-"
        print(
            f"[{row['id']}] {row['created_at']} user={row['user_id']} "
            f"word={word} reading={row.get('reading') or '-'} "
            f"status={row.get('status')}"
        )
        print(f"    current: {row.get('current_meaning_ko') or '-'}")
        if row.get("suggested_meaning_ko"):
            print(f"    suggested: {row['suggested_meaning_ko']}")
        if row.get("reason"):
            print(f"    reason: {row['reason']}")
        if row.get("source"):
            print(f"    source: {row['source']}")
        print()

    print(f"{len(rows)} row(s) shown.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

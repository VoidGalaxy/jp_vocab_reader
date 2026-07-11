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
from app.repositories.feedback_repository import list_app_feedback  # noqa: E402


MESSAGE_PREVIEW_LENGTH = 200


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Read-only operator helper: prints recent app_feedback rows "
            "(general in-app feedback -- bugs/UX/feature requests/etc, "
            "distinct from meaning_feedback) so beta feedback can be "
            "reviewed without a dedicated admin UI. Connects to whatever "
            "DATABASE_URL is configured -- this is read-only, but double "
            "check it points where you expect before running against a "
            "real deployment."
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
        help="Only show feedback with this status (e.g. 'open')",
    )
    parser.add_argument(
        "--category",
        default=None,
        help="Only show feedback in this category (e.g. 'bug')",
    )
    args = parser.parse_args()

    init_db()
    rows = list_app_feedback(limit=args.limit)
    if args.status:
        rows = [row for row in rows if row.get("status") == args.status]
    if args.category:
        rows = [row for row in rows if row.get("category") == args.category]

    # Open reports first (stable sort keeps the existing created_at DESC
    # order within each group) so the operator sees what still needs
    # triage before already-closed reports.
    rows.sort(key=lambda row: row.get("status") != "open")

    if not rows:
        print("No app_feedback rows found.")
        return 0

    for row in rows:
        message = row.get("message") or ""
        preview = message[:MESSAGE_PREVIEW_LENGTH]
        if len(message) > MESSAGE_PREVIEW_LENGTH:
            preview += "..."
        print(
            f"[{row['id']}] {row['created_at']} user={row['user_id']} "
            f"category={row.get('category')} screen={row.get('screen') or '-'} "
            f"path={row.get('path') or '-'} status={row.get('status')}"
        )
        print(f"    {preview}")
        print()

    print(f"{len(rows)} row(s) shown.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

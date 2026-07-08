from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.database import get_connection, get_database_engine, is_postgres_connection  # noqa: E402
from app.settings import get_database_url  # noqa: E402


# Deleted in this order: dependent tables first, shared_decks last. Only
# shared-deck data is touched -- personal decks/vocab_items that a user has
# already imported from a shared deck are never referenced or deleted here.
RELATED_TABLES = ("shared_deck_items", "shared_deck_terms", "shared_deck_imports")


def redact_database_url(url: str) -> str:
    # Never print credentials, even in local logs -- only scheme/host/db.
    return re.sub(r"://[^@/]+@", "://***@", url)


def table_exists(connection: Any, table_name: str) -> bool:
    if is_postgres_connection(connection):
        cursor = connection.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = ?",
            (table_name,),
        )
    else:
        cursor = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table_name,),
        )
    return cursor.fetchone() is not None


def find_shared_decks_by_title(connection: Any, title: str) -> list[dict[str, Any]]:
    cursor = connection.execute(
        """
        SELECT id, title, owner_user_id, visibility, created_at
        FROM shared_decks
        WHERE title = ?
        ORDER BY id ASC
        """,
        (title,),
    )
    return [dict(row) for row in cursor.fetchall()]


def count_related(connection: Any, table: str, shared_deck_id: int) -> int | None:
    if not table_exists(connection, table):
        return None
    cursor = connection.execute(
        f"SELECT COUNT(*) AS count FROM {table} WHERE shared_deck_id = ?",
        (shared_deck_id,),
    )
    row = cursor.fetchone()
    return int(row["count"]) if row else 0


def collect_targets(connection: Any, titles: list[str]) -> tuple[list[dict[str, Any]], list[str]]:
    targets: list[dict[str, Any]] = []
    unmatched_titles: list[str] = []
    for title in titles:
        matches = find_shared_decks_by_title(connection, title)
        if not matches:
            unmatched_titles.append(title)
            continue
        for deck in matches:
            deck["item_count"] = count_related(connection, "shared_deck_items", deck["id"])
            deck["term_count"] = count_related(connection, "shared_deck_terms", deck["id"])
            deck["import_count"] = count_related(connection, "shared_deck_imports", deck["id"])
            targets.append(deck)
    return targets, unmatched_titles


def print_targets(targets: list[dict[str, Any]], unmatched_titles: list[str]) -> None:
    if not targets:
        print("no matching shared decks found")
    else:
        print(f"matched {len(targets)} shared deck(s):")
        for deck in targets:
            def fmt(count: int | None) -> str:
                return "table not found" if count is None else str(count)

            print(
                f"  id={deck['id']} title={deck['title']!r} "
                f"item_count={fmt(deck['item_count'])} "
                f"term_count={fmt(deck['term_count'])} "
                f"import_count={fmt(deck['import_count'])} "
                f"owner_user_id={deck['owner_user_id']} "
                f"visibility={deck['visibility']} "
                f"created_at={deck['created_at']}"
            )
    if unmatched_titles:
        print("titles with no match:")
        for title in unmatched_titles:
            print(f"  {title!r}")


def delete_targets(connection: Any, shared_deck_ids: list[int]) -> None:
    placeholders = ", ".join(["?"] * len(shared_deck_ids))
    params = tuple(shared_deck_ids)

    for table in RELATED_TABLES:
        if not table_exists(connection, table):
            print(f"{table}: table not found, skipped")
            continue
        cursor = connection.execute(
            f"DELETE FROM {table} WHERE shared_deck_id IN ({placeholders})", params
        )
        print(f"deleted {cursor.rowcount} row(s) from {table}")

    cursor = connection.execute(
        f"DELETE FROM shared_decks WHERE id IN ({placeholders})", params
    )
    print(f"deleted {cursor.rowcount} row(s) from shared_decks")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Delete public shared decks (and their shared_deck_items/"
            "shared_deck_terms/shared_deck_imports rows) by exact title, "
            "without needing direct SQL access to the production database. "
            "Never touches personal decks/vocab_items that users have "
            "already imported from a shared deck. Defaults to a read-only "
            "dry run -- pass --apply to actually delete. Connects to "
            "whatever DATABASE_URL is configured, which may be a real "
            "production database, so review the dry-run output carefully "
            "before using --apply."
        )
    )
    parser.add_argument(
        "--title",
        action="append",
        dest="titles",
        required=True,
        help="Exact shared deck title to delete. Repeat for multiple titles.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually delete (default: dry run, read-only)",
    )
    args = parser.parse_args()

    database_url = get_database_url()
    if not database_url:
        print(
            "DATABASE_URL is not set (checked the process environment and "
            "backend/.env). Refusing to proceed without an explicit target "
            "database."
        )
        return 1

    print(f"database engine: {get_database_engine()}")
    print(f"database url: {redact_database_url(database_url)}")

    with get_connection() as connection:
        targets, unmatched_titles = collect_targets(connection, args.titles)
        print_targets(targets, unmatched_titles)

        if not targets:
            return 0

        if not args.apply:
            print("[dry-run] no changes made. Pass --apply to delete the shared decks listed above.")
            return 0

        shared_deck_ids = [deck["id"] for deck in targets]
        delete_targets(connection, shared_deck_ids)
        # Exiting this `with` block commits (SQLite and PostgreSQL both, via
        # get_connection()'s context-manager semantics) -- no explicit
        # connection.commit() call needed, matching the rest of the app's
        # repository functions.

    print(f"done: deleted {len(targets)} shared deck(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

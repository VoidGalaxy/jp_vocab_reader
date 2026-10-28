"""E-5 preparation only: counts-only inventory, no deletion or eligibility decision.

The caller supplies an already protected connection. This module never connects,
initializes a schema, acquires write locks, or returns stored user content.
"""

from __future__ import annotations

import json

from app.database import is_postgres_connection
from app.srs.invariant_audit import read_snapshot


OWNED_TABLES = (
    "vocab_items", "decks", "custom_terms", "review_logs", "lexeme_review_logs",
    "user_word_progress", "user_deck_subscriptions", "shared_deck_imports",
    "srs_user_settings", "srs_review_receipts", "srs_card_deletions",
    "srs_card_identity_flags", "srs_evidence_restarts", "srs_migration_snapshots",
    "meaning_feedback", "app_feedback", "account_write_blocks", "account_recovery_runs",
)
GLOBAL_TABLES = (
    "lexemes", "srs_config_versions", "shared_deck_items", "shared_deck_terms",
    "shared_deck_words",
)
EXPECTED_TABLES = frozenset(OWNED_TABLES + GLOBAL_TABLES + (
    "users", "shared_decks", "srs_migration_runs",
))


def _positive_id(value):
    return type(value) is int and 0 < value <= (2 ** 63 - 1)


def _unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_scope_key")
        result[key] = value
    return result


def _tables(connection):
    if is_postgres_connection(connection):
        rows = connection.execute(
            "SELECT tablename AS name FROM pg_catalog.pg_tables "
            "WHERE schemaname = 'public'"
        ).fetchall()
        # The protected PG harness owns this non-product table separately.
        return {row["name"] for row in rows} - {"jp_vocab_e_run_marker"}
    return {row["name"] for row in connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()}


def _count(connection, table, column, user_id):
    # Identifiers come exclusively from the explicit module-owned inventory.
    return int(connection.execute(
        f"SELECT COUNT(*) AS n FROM {table} WHERE {column} = ?", (user_id,)
    ).fetchone()["n"])


def account_inventory(connection, user_id):
    """Read one consistent snapshot. A complete inventory is NOT deletion approval."""
    if not _positive_id(user_id):
        raise ValueError("invalid_account_id")
    with read_snapshot(connection):
        return _inventory(connection, user_id)


def _inventory(connection, user_id):
    tables = _tables(connection)
    if tables != EXPECTED_TABLES:
        return {
            "status": "incomplete", "deletion_enabled": False,
            "reasons": ["schema_inventory_mismatch"],
            "missing_tables": len(EXPECTED_TABLES - tables),
            "unexpected_tables": len(tables - EXPECTED_TABLES),
        }

    counts = {table: _count(connection, table, "user_id", user_id) for table in OWNED_TABLES}
    counts["users"] = _count(connection, "users", "id", user_id)
    counts["shared_decks"] = _count(connection, "shared_decks", "owner_user_id", user_id)

    owners = {}
    unreadable = active = 0
    for row in connection.execute("SELECT id, scope_json, status FROM srs_migration_runs").fetchall():
        try:
            scope = json.loads(row["scope_json"], object_pairs_hook=_unique_keys)
        except (ValueError, TypeError, RecursionError):
            unreadable += 1
            continue
        if not isinstance(scope, dict) or not _positive_id(scope.get("user_id")):
            unreadable += 1
            continue
        owners[row["id"]] = scope["user_id"]
        active += scope["user_id"] == user_id and row["status"] == "started"
    counts["srs_migration_runs"] = sum(owner == user_id for owner in owners.values())

    cross_owner = missing_parent = 0
    for row in connection.execute("SELECT user_id, run_id FROM srs_migration_snapshots").fetchall():
        owner = owners.get(row["run_id"])
        if row["user_id"] != user_id and owner != user_id:
            continue
        if owner is None:
            missing_parent += 1
        elif row["user_id"] != owner:
            cross_owner += 1

    reasons = []
    for condition, code in (
        (counts["users"] != 1, "account_not_found"),
        (unreadable, "run_ownership_unverifiable"),
        (cross_owner, "snapshot_owner_mismatch"),
        (missing_parent, "snapshot_parent_unverifiable"),
    ):
        if condition:
            reasons.append(code)
    return {
        "status": "incomplete" if reasons else "inventory_complete",
        "deletion_enabled": False,
        "reasons": reasons,
        "counts": counts,
        "observations": {
            "owned_shared_decks": counts["shared_decks"],
            "started_runs": active,
            "unreadable_run_scopes": unreadable,
            "cross_owner_snapshots": cross_owner,
            "unverifiable_snapshot_parents": missing_parent,
        },
    }

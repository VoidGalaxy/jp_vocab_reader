"""Gate E-5b: operator account deletion on the server database (E5B_CONTRACT.md).

`preview` reads one read-only snapshot and writes nothing. `apply` takes the E-5a account
write lock on the caller's connection, recomputes the plan under the lock, refuses on any
blocker or a changed plan, then deletes the account's rows with explicit statements in a
fixed dependency order, checks that nothing of the account is left, and commits -- or rolls
everything back. Results hold counts, fixed reason codes and a plan fingerprint only.

This is a logical delete of the server database. It does not verify the requester, decide
legal retention, resolve shared decks, or erase backups / replicas / browser storage.
Not called by the app; the operator CLI is scripts/delete_account.py.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from app.account_write import begin_account_write
from app.database import is_postgres_connection

# ---- the explicit allow-list (checked against the live schema before anything else) ----
OWNED_TABLES = (
    "vocab_items", "decks", "custom_terms", "review_logs", "lexeme_review_logs",
    "user_word_progress", "user_deck_subscriptions", "shared_deck_imports",
    "srs_user_settings", "srs_review_receipts", "srs_card_deletions",
    "srs_card_identity_flags", "srs_evidence_restarts", "srs_migration_snapshots",
    "meaning_feedback", "app_feedback", "account_write_blocks", "account_recovery_runs",
)
GLOBAL_TABLES = ("lexemes", "srs_config_versions", "shared_deck_items", "shared_deck_terms", "shared_deck_words",
                 "shared_decks")
EXPECTED_TABLES = frozenset(OWNED_TABLES + GLOBAL_TABLES + ("users", "srs_migration_runs"))
KEY_COLUMN = {"srs_user_settings": "user_id"}  # every other owned table has an integer `id`
HARNESS_TABLES = frozenset({"jp_vocab_e_run_marker"})  # the protected test harness's own marker only

# Foreign keys, ONE ENTRY PER CONSTRAINT (E-5b review fix P1): (schema, table, columns in key
# order, referenced schema, referenced table, referenced columns in key order, ON DELETE),
# ON DELETE: c CASCADE, n SET NULL, a NO ACTION. Compared as a list, so a duplicated constraint
# or a different column count / order / target column / schema is a mismatch. Reviewed against
# the app's schema code and the live catalogs of a fresh SQLite file and the protected local PG.
def _fk(table, column, ref_table, action, schema):
    return (schema, table, (column,), schema, ref_table, ("id",), action)


SQLITE_FK_CONSTRAINTS = tuple(sorted(_fk(t, c, r, d, "main") for t, c, r, d in (
    ("account_recovery_runs", "user_id", "users", "r"),
    ("account_write_blocks", "user_id", "users", "r"), ("srs_card_deletions", "user_id", "users", "c"), ("srs_card_identity_flags", "user_id", "users", "c"),
    ("srs_evidence_restarts", "user_id", "users", "c"), ("srs_migration_snapshots", "run_id", "srs_migration_runs", "a"),
    ("srs_review_receipts", "user_id", "users", "c"), ("srs_user_settings", "user_id", "users", "c"),
)))
POSTGRES_FK_CONSTRAINTS = tuple(sorted(_fk(t, c, r, d, "public") for t, c, r, d in (
    ("account_recovery_runs", "user_id", "users", "r"),
    ("account_write_blocks", "user_id", "users", "r"), ("app_feedback", "user_id", "users", "n"), ("custom_terms", "deck_id", "decks", "c"),
    ("custom_terms", "user_id", "users", "c"), ("decks", "user_id", "users", "c"),
    ("lexeme_review_logs", "lexeme_id", "lexemes", "c"), ("lexeme_review_logs", "shared_deck_id", "shared_decks", "n"),
    ("lexeme_review_logs", "user_id", "users", "c"), ("meaning_feedback", "user_id", "users", "c"),
    ("meaning_feedback", "vocabulary_id", "vocab_items", "n"), ("review_logs", "user_id", "users", "c"),
    ("shared_deck_imports", "imported_deck_id", "decks", "c"), ("shared_deck_imports", "shared_deck_id", "shared_decks", "c"),
    ("shared_deck_imports", "user_id", "users", "c"), ("shared_deck_items", "shared_deck_id", "shared_decks", "c"),
    ("shared_deck_terms", "shared_deck_id", "shared_decks", "c"), ("shared_deck_words", "lexeme_id", "lexemes", "c"),
    ("shared_deck_words", "shared_deck_id", "shared_decks", "c"), ("shared_decks", "owner_user_id", "users", "c"),
    ("srs_card_deletions", "user_id", "users", "c"), ("srs_card_identity_flags", "user_id", "users", "c"),
    ("srs_evidence_restarts", "user_id", "users", "c"), ("srs_migration_snapshots", "run_id", "srs_migration_runs", "a"),
    ("srs_review_receipts", "user_id", "users", "c"), ("srs_user_settings", "user_id", "users", "c"),
    ("user_deck_subscriptions", "shared_deck_id", "shared_decks", "c"), ("user_deck_subscriptions", "user_id", "users", "c"),
    ("user_word_progress", "lexeme_id", "lexemes", "c"), ("user_word_progress", "user_id", "users", "c"),
    ("vocab_items", "deck_id", "decks", "c"), ("vocab_items", "user_id", "users", "c"),
)))
_SQLITE_ACTION = {"CASCADE": "c", "SET NULL": "n", "NO ACTION": "a", "RESTRICT": "r", "SET DEFAULT": "d"}

# Deletion order (E5B_CONTRACT 4-3): children before what they point at; users last.
DELETE_ORDER = (
    "srs_evidence_restarts", "srs_migration_snapshots", "srs_migration_runs",
    "srs_review_receipts", "srs_card_deletions", "srs_card_identity_flags", "srs_user_settings",
    "review_logs", "lexeme_review_logs",
    "user_word_progress", "user_deck_subscriptions", "shared_deck_imports",
    "meaning_feedback",
    "vocab_items", "custom_terms",
    "decks",
    "account_recovery_runs", "account_write_blocks",
    "users",
)
REPORT_VERSION = 1


class AccountDeletionError(RuntimeError):
    """A failed apply: everything was rolled back. `code` is a fixed reason."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _positive_id(value: Any) -> bool:
    return type(value) is int and 0 < value <= 2 ** 63 - 1


def _unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_scope_key")
        result[key] = value
    return result


def _rows(connection: Any, sql: str, params: tuple = ()) -> list[dict]:
    return [dict(r) for r in connection.execute(sql, params).fetchall()]


def _ids(connection: Any, sql: str, params: tuple = ()) -> list[int]:
    return sorted(int(r["id"]) for r in _rows(connection, sql, params))


# ---- schema check -------------------------------------------------------------------------
def _fk_constraints_ok(actual: list[tuple], expected: tuple | list) -> bool:
    """Per constraint, duplicates kept (a list, never a set)."""
    def key(c):
        return tuple(repr(part) for part in c)
    return sorted(actual, key=key) == sorted(expected, key=key)


def _postgres_fk_constraints(connection: Any) -> list[tuple]:
    """Every FK that starts in OR points into the public schema, one row per constraint, with
    both column lists in key order and both schemas -- a same-named table elsewhere differs."""
    rows = _rows(connection, """
        SELECT sn.nspname AS s, t.relname AS t, rn.nspname AS rs, r.relname AS r, k.confdeltype::text AS d,
               ARRAY(SELECT a.attname::text FROM unnest(k.conkey) WITH ORDINALITY AS u(n, i)
                     JOIN pg_attribute a ON a.attrelid = k.conrelid AND a.attnum = u.n ORDER BY u.i) AS c,
               ARRAY(SELECT a.attname::text FROM unnest(k.confkey) WITH ORDINALITY AS u(n, i)
                     JOIN pg_attribute a ON a.attrelid = k.confrelid AND a.attnum = u.n ORDER BY u.i) AS rc
        FROM pg_constraint k
        JOIN pg_class t ON t.oid = k.conrelid JOIN pg_namespace sn ON sn.oid = t.relnamespace
        JOIN pg_class r ON r.oid = k.confrelid JOIN pg_namespace rn ON rn.oid = r.relnamespace
        WHERE k.contype = 'f' AND (sn.nspname = 'public' OR rn.nspname = 'public')""")
    return [(r["s"], r["t"], tuple(r["c"]), r["rs"], r["r"], tuple(r["rc"]), r["d"]) for r in rows]


def _sqlite_fk_constraints(connection: Any, tables: set[str]) -> list[tuple]:
    """PRAGMA foreign_key_list rows grouped by constraint id, columns in key order. A missing
    target column (an implicit primary key) stays None and so never equals the reviewed one."""
    constraints = []
    for table in sorted(tables):
        groups: dict[int, list[dict]] = {}
        for r in _rows(connection, f"PRAGMA foreign_key_list({table})"):
            groups.setdefault(int(r["id"]), []).append(r)
        for parts in groups.values():
            parts.sort(key=lambda r: int(r["seq"]))
            first = parts[0]
            if any((r["table"], r["on_delete"]) != (first["table"], first["on_delete"]) for r in parts):
                constraints.append(("main", table, ("?",), "main", "?", ("?",), "?"))
                continue
            constraints.append(("main", table, tuple(r["from"] for r in parts), "main", first["table"],
                                tuple(r["to"] for r in parts),
                                _SQLITE_ACTION.get(str(first["on_delete"]).upper(), "?")))
    return constraints


def _schema_ok(connection: Any) -> bool:
    postgres = is_postgres_connection(connection)
    if postgres:
        tables = {r["name"] for r in _rows(connection, "SELECT tablename AS name FROM pg_catalog.pg_tables "
                                                       "WHERE schemaname = 'public'")} - HARNESS_TABLES
        fks = _postgres_fk_constraints(connection)
        triggers = _rows(connection, "SELECT count(*) AS n FROM pg_trigger g JOIN pg_class c ON c.oid = g.tgrelid "
                                     "JOIN pg_namespace n ON n.oid = c.relnamespace "
                                     "WHERE NOT g.tgisinternal AND n.nspname = 'public'")[0]["n"]
        columns = {(r["t"], r["c"]) for r in _rows(connection, "SELECT table_name AS t, column_name AS c FROM "
                                                               "information_schema.columns WHERE table_schema = 'public'")}
    else:
        tables = {r["name"] for r in _rows(connection, "SELECT name FROM sqlite_master WHERE type = 'table' "
                                                       "AND name NOT LIKE 'sqlite_%'")}
        columns = set()
        fks = _sqlite_fk_constraints(connection, tables)
        for table in tables & EXPECTED_TABLES:
            for r in _rows(connection, f"PRAGMA table_info({table})"):
                columns.add((table, r["name"]))
        triggers = _rows(connection, "SELECT count(*) AS n FROM sqlite_master WHERE type = 'trigger'")[0]["n"]
    expected_fks = POSTGRES_FK_CONSTRAINTS if postgres else SQLITE_FK_CONSTRAINTS
    return (tables == EXPECTED_TABLES and _fk_constraints_ok(fks, expected_fks) and int(triggers) == 0
            and all((t, "user_id") in columns for t in OWNED_TABLES)
            and all((t, KEY_COLUMN.get(t, "id")) in columns for t in OWNED_TABLES))


# ---- the plan -----------------------------------------------------------------------------
def _run_owners(connection: Any) -> tuple[dict[int, int], int]:
    owners, unreadable = {}, 0
    for row in _rows(connection, "SELECT id, scope_json FROM srs_migration_runs"):
        try:
            scope = json.loads(row["scope_json"], object_pairs_hook=_unique_keys)
        except (ValueError, TypeError, RecursionError):
            unreadable += 1
            continue
        if not isinstance(scope, dict) or not _positive_id(scope.get("user_id")):
            unreadable += 1
            continue
        owners[int(row["id"])] = scope["user_id"]
    return owners, unreadable


def _count(connection: Any, sql: str, params: tuple) -> int:
    return int(_rows(connection, sql, params)[0]["n"])


def _cross_references(connection: Any, t: int, owners: dict[int, int]) -> int:
    """Rows linking the account's data with another account's (E5B_CONTRACT 3-1)."""
    n = 0
    for snap in _rows(connection, "SELECT user_id, run_id FROM srs_migration_snapshots"):
        owner = owners.get(snap["run_id"])
        if snap["user_id"] == t or owner == t:
            n += owner is None or snap["user_id"] != owner
    n += _count(connection, "SELECT count(*) AS n FROM srs_evidence_restarts r LEFT JOIN srs_migration_snapshots s "
                            "ON s.id = r.source_snapshot_id WHERE (r.user_id = ? AND (s.id IS NULL OR s.user_id <> ?)) "
                            "OR (s.user_id = ? AND r.user_id <> ?)", (t, t, t, t))
    # E-5b review fix P2: both boundaries are log ids of the card kind's own log table
    # (reviews._restart_evidence_boundary). An existing log on the other side of the
    # target / other-account split, either way, is a link. A boundary whose log does not
    # exist (or 0 / NULL) joins nothing: it is neither a link nor repaired here.
    for kind, logs in (("personal", "review_logs"), ("lexeme", "lexeme_review_logs")):
        for field in ("previous_boundary", "new_boundary"):
            n += _count(connection, f"SELECT count(*) AS n FROM srs_evidence_restarts r JOIN {logs} l "
                                    f"ON l.id = r.{field} WHERE r.card_kind = ? AND (r.user_id = ?) <> (l.user_id = ?)",
                        (kind, t, t))
    my_decks = "(SELECT id FROM decks WHERE user_id = ?)"
    other_decks = "(SELECT id FROM decks WHERE user_id IS NULL OR user_id <> ?)"
    for sql in (f"SELECT count(*) AS n FROM vocab_items WHERE deck_id IN {my_decks} AND (user_id IS NULL OR user_id <> ?)",
                f"SELECT count(*) AS n FROM custom_terms WHERE deck_id IN {my_decks} AND (user_id IS NULL OR user_id <> ?)",
                f"SELECT count(*) AS n FROM shared_deck_imports WHERE imported_deck_id IN {my_decks} AND user_id <> ?",
                f"SELECT count(*) AS n FROM shared_decks WHERE source_deck_id IN {my_decks} AND owner_user_id <> ?"):
        n += _count(connection, sql, (t, t))
    for sql in (f"SELECT count(*) AS n FROM vocab_items WHERE user_id = ? AND deck_id IN {other_decks}",
                f"SELECT count(*) AS n FROM custom_terms WHERE user_id = ? AND deck_id IN {other_decks}",
                f"SELECT count(*) AS n FROM shared_deck_imports WHERE user_id = ? AND imported_deck_id IN {other_decks}"):
        n += _count(connection, sql, (t, t))
    mine = "(SELECT id FROM vocab_items WHERE user_id = ?)"
    theirs = "(SELECT id FROM vocab_items WHERE user_id IS NULL OR user_id <> ?)"
    for table, column, kind in (("review_logs", "vocab_item_id", None), ("meaning_feedback", "vocabulary_id", None),
                                ("srs_review_receipts", "card_ref", "personal"), ("srs_card_deletions", "card_ref", "personal"),
                                ("srs_card_identity_flags", "card_ref", "personal"),
                                ("srs_evidence_restarts", "card_ref", "personal"),
                                ("srs_migration_snapshots", "card_ref", "personal")):
        kind_sql = " AND card_kind = 'personal'" if kind else ""
        n += _count(connection, f"SELECT count(*) AS n FROM {table} WHERE {column} IN {mine} "
                                f"AND (user_id IS NULL OR user_id <> ?){kind_sql}", (t, t))
        n += _count(connection, f"SELECT count(*) AS n FROM {table} WHERE user_id = ? AND {column} IN {theirs}{kind_sql}",
                    (t, t))
    for cards, logs in (("vocab_items", "review_logs"), ("user_word_progress", "lexeme_review_logs")):
        n += _count(connection, f"SELECT count(*) AS n FROM {cards} c JOIN {logs} l ON l.id = c.evidence_from_log_id "
                                f"WHERE (c.user_id = ?) <> (l.user_id = ?)", (t, t))
    for kind, logs in (("personal", "review_logs"), ("lexeme", "lexeme_review_logs")):
        n += _count(connection, f"SELECT count(*) AS n FROM srs_review_receipts r JOIN {logs} l ON l.id = r.review_log_id "
                                f"WHERE r.card_kind = ? AND (r.user_id = ?) <> (l.user_id = ?)", (kind, t, t))
    return n


# ---- references inside snapshot records (E5B_CONTRACT 3-3) ----------------------------------
_LOG_TABLE = {"personal": "review_logs", "lexeme": "lexeme_review_logs"}
_MAX_ID = 2 ** 63 - 1


class _Unreadable(Exception):
    pass


def _ref_value(value: Any) -> int:
    """A stored reference: 0..2^63-1, bool excluded. 0 means "no reference"."""
    if type(value) is not int or not 0 <= value <= _MAX_ID:
        raise _Unreadable()
    return value


def _snapshot_refs(mode: Any, text: Any) -> tuple[list[int], list[int]]:
    """(log ids, snapshot ids) a record refers to -- read only, never rebuilt or repaired.
    Raises _Unreadable for anything the contract does not recognise."""
    if mode not in ("apply", "rollback") or not isinstance(text, str):
        raise _Unreadable()
    try:
        body = json.loads(text, object_pairs_hook=_unique_keys)
    except (ValueError, TypeError, RecursionError):
        raise _Unreadable() from None
    if not isinstance(body, dict):
        raise _Unreadable()
    fmt = body.get("format", 1) if "format" in body else 1
    if type(fmt) is not int or fmt not in ((1, 2, 3) if mode == "apply" else (1, 2)):
        raise _Unreadable()
    required, optional = ({"card", "last_log_id"}, {"restart"}) if mode == "apply" else ({"card", "baseline"}, set())
    keys = set(body) - {"format"}
    if not required <= keys or keys - required - optional:
        raise _Unreadable()
    card = body["card"]
    if not isinstance(card, dict):
        raise _Unreadable()
    logs, snapshots = [], []
    if "evidence_from_log_id" in card and card["evidence_from_log_id"] is not None:
        logs.append(_ref_value(card["evidence_from_log_id"]))   # a format-1 card copy only
    if mode == "apply":
        logs.append(_ref_value(body["last_log_id"]))
        if "restart" in body:
            restart = body["restart"]
            if not isinstance(restart, dict) or set(restart) != {"previous_boundary", "rollback_record_id"}:
                raise _Unreadable()
            logs.append(_ref_value(restart["previous_boundary"]))
            snapshots.append(_ref_value(restart["rollback_record_id"]))
    else:
        baseline = body["baseline"]
        if not isinstance(baseline, dict) or "last_log_id" not in baseline:
            raise _Unreadable()
        logs.append(_ref_value(baseline["last_log_id"]))
    return [v for v in logs if v], [v for v in snapshots if v]


def _owners_of(connection: Any, table: str, ids: set[int]) -> dict[int, Any]:
    owners: dict[int, Any] = {}
    ordered = sorted(ids)
    for start in range(0, len(ordered), 500):
        chunk = ordered[start:start + 500]
        for r in _rows(connection, f"SELECT id, user_id FROM {table} WHERE id IN ({','.join('?' for _ in chunk)})",
                       tuple(chunk)):
            owners[int(r["id"])] = r["user_id"]
    return owners


def _snapshot_references(connection: Any, t: int) -> tuple[int, int]:
    """(links with another account, unreadable records that may relate to the target)."""
    rows = _rows(connection, "SELECT s.id, s.user_id, s.card_kind, s.legacy_json, r.mode FROM srs_migration_snapshots s "
                             "LEFT JOIN srs_migration_runs r ON r.id = s.run_id ORDER BY s.id")
    target_has_logs = {kind: bool(_count(connection, f"SELECT count(*) AS n FROM {table} WHERE user_id = ?", (t,)))
                       for kind, table in _LOG_TABLE.items()}
    target_has_snapshots = any(row["user_id"] == t for row in rows)
    parsed, unreadable = [], 0
    for row in rows:
        try:
            if row["card_kind"] not in _LOG_TABLE:
                raise _Unreadable()
            parsed.append((row, *_snapshot_refs(row["mode"], row["legacy_json"])))
        except _Unreadable:
            # cannot relate to the target only when it is not the target's and the target has
            # neither a log of that card kind nor a snapshot it could point at
            mine = row["user_id"] == t
            kind_logs = target_has_logs.get(row["card_kind"], any(target_has_logs.values()))
            unreadable += mine or kind_logs or target_has_snapshots
    links = 0
    snapshot_owner = {int(row["id"]): row["user_id"] for row in rows}
    for kind, table in _LOG_TABLE.items():
        wanted = {v for row, logs, _ in parsed if row["card_kind"] == kind for v in logs}
        owners = _owners_of(connection, table, wanted) if wanted else {}
        for row, logs, _ in parsed:
            if row["card_kind"] == kind:
                links += sum(v in owners and (owners[v] == t) != (row["user_id"] == t) for v in logs)
    for row, _, snaps in parsed:
        links += sum(v in snapshot_owner and (snapshot_owner[v] == t) != (row["user_id"] == t) for v in snaps)
    return links, unreadable


def _plan(connection: Any, t: int) -> dict[str, Any]:
    if not _schema_ok(connection):
        return {"exists": None, "reasons": ["schema_unverified"], "ids": {}, "runs": []}
    if not _rows(connection, "SELECT id FROM users WHERE id = ?", (t,)):
        return {"exists": False, "reasons": [], "ids": {}, "runs": []}
    ids = {table: sorted(int(r["k"]) for r in _rows(
        connection, f"SELECT {KEY_COLUMN.get(table, 'id')} AS k FROM {table} WHERE user_id = ?", (t,)))
        for table in OWNED_TABLES}
    owners, unreadable = _run_owners(connection)
    runs = sorted(run for run, owner in owners.items() if owner == t)
    started = _count(connection, "SELECT count(*) AS n FROM srs_migration_runs WHERE status = 'started' AND id IN "
                                 f"({','.join(str(r) for r in runs) or 'NULL'})", ())
    shared = _count(connection, "SELECT count(*) AS n FROM shared_decks WHERE owner_user_id = ?", (t,))
    cross = _cross_references(connection, t, owners)
    snapshot_links, snapshot_unreadable = _snapshot_references(connection, t)
    cross += snapshot_links
    # P-RB: any row not cleanly released (status and marker), not the marker alone
    blocked = _count(connection, "SELECT count(*) AS n FROM account_write_blocks WHERE (user_id = ? AND "
                                 "(status <> 'released' OR active_user_id IS NOT NULL)) OR active_user_id = ?", (t, t))
    reasons = [code for condition, code in (
        (blocked, "account_writes_blocked"),
        (shared, "shared_deck_owner_review"),
        (ids["app_feedback"], "app_feedback_retention_review"),
        (started, "migration_run_in_progress"),
        (unreadable, "run_ownership_unverifiable"),
        (cross, "cross_account_reference"),
        (snapshot_unreadable, "snapshot_reference_unverifiable"),
    ) if condition]
    return {"exists": True, "reasons": reasons, "ids": ids, "runs": runs,
            "observed": {"owned_shared_decks": shared, "started_runs": started, "unreadable_run_scopes": unreadable,
                         "cross_account_references": cross, "unreadable_snapshot_references": snapshot_unreadable}}


def _fingerprint(t: int, plan: dict[str, Any]) -> str:
    material = {"user_id": t, "ids": plan["ids"], "runs": plan["runs"], "reasons": plan["reasons"],
                "observed": plan.get("observed", {})}
    return hashlib.sha256(json.dumps(material, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _counts(plan: dict[str, Any]) -> dict[str, int]:
    counts = {table: len(plan["ids"].get(table, [])) for table in OWNED_TABLES}
    counts["srs_migration_runs"] = len(plan["runs"])
    counts["users"] = 1 if plan["exists"] else 0
    return counts


def _report(t: int, status: str, plan: dict[str, Any], *, applied: bool) -> dict[str, Any]:
    report = {"report_version": REPORT_VERSION, "status": status, "user_id": t, "applied": applied,
              "eligible": bool(plan["exists"]) and not plan["reasons"], "reasons": list(plan["reasons"]),
              "server_db_only": True}
    if plan["exists"]:
        report["counts"] = _counts(plan)
        report["observed"] = dict(plan["observed"])
        report["plan"] = _fingerprint(t, plan)
    return report


# ---- public entry points --------------------------------------------------------------------
def preview(connection: Any, user_id: int) -> dict[str, Any]:
    """Read-only. The connection must have no open transaction."""
    from app.srs.invariant_audit import read_snapshot

    if not _positive_id(user_id):
        raise AccountDeletionError("invalid_account_id")
    with read_snapshot(connection):
        plan = _plan(connection, user_id)
    if plan["exists"] is None:
        return _report(user_id, "blocked", plan, applied=False)
    if plan["exists"] is False:
        return _report(user_id, "account_not_found", plan, applied=False)
    return _report(user_id, "preview", plan, applied=False)


def apply(connection: Any, user_id: int, *, confirm_user_id: int, expected_plan: str) -> dict[str, Any]:
    """One transaction on `connection` (no transaction open on entry). Returns a report for
    deleted / blocked / account_not_found / plan_changed; raises AccountDeletionError (after
    a rollback) for a failure. Every non-deleted outcome rolls back and writes nothing."""
    from app.account_write import AccountWriteError

    if not _positive_id(user_id):
        raise AccountDeletionError("invalid_account_id")
    if confirm_user_id != user_id or not isinstance(expected_plan, str) or len(expected_plan) != 64:
        raise AccountDeletionError("explicit_confirmation_required")
    postgres = is_postgres_connection(connection)
    try:
        try:
            begin_account_write(connection, user_id)
        except AccountWriteError as error:
            connection.rollback()
            if error.code == "account_writes_blocked":
                # P-RB: an account under a recovery block is reported blocked (never account_not_found)
                return _report(user_id, "blocked", {"exists": None, "reasons": ["account_writes_blocked"], "ids": {},
                                                    "runs": []}, applied=False)
            return _report(user_id, "account_not_found", {"exists": False, "reasons": [], "ids": {}, "runs": []},
                           applied=False)
        if postgres:
            # no other account can add a reference to these rows until this transaction ends
            connection.execute("SELECT id FROM decks WHERE user_id = ? FOR UPDATE", (user_id,)).fetchall()
            connection.execute("SELECT id FROM vocab_items WHERE user_id = ? FOR UPDATE", (user_id,)).fetchall()
        plan = _plan(connection, user_id)
        if plan["exists"] is None or plan["reasons"]:
            connection.rollback()
            return _report(user_id, "blocked", plan, applied=False)
        if _fingerprint(user_id, plan) != expected_plan:
            connection.rollback()
            report = _report(user_id, "plan_changed", plan, applied=False)
            report["eligible"] = False
            return report
        global_before = None if postgres else {t: _count(connection, f"SELECT count(*) AS n FROM {t}", ())
                                                for t in GLOBAL_TABLES}
        expected = _counts(plan)
        for table in DELETE_ORDER:
            if table == "users":
                cursor = connection.execute("DELETE FROM users WHERE id = ?", (user_id,))
            elif table == "srs_migration_runs":
                runs = plan["runs"]
                cursor = connection.execute(
                    f"DELETE FROM srs_migration_runs WHERE id IN ({','.join('?' for _ in runs) or 'NULL'})", tuple(runs))
            else:
                cursor = connection.execute(f"DELETE FROM {table} WHERE user_id = ?", (user_id,))
            if (cursor.rowcount if cursor.rowcount is not None else -1) != expected[table]:
                raise AccountDeletionError("deleted_count_mismatch")
        _residual_check(connection, user_id, plan["runs"], global_before)
        connection.commit()
    except AccountDeletionError:
        connection.rollback()
        raise
    except Exception as error:  # noqa: BLE001 -- rolled back; only the type name leaves
        connection.rollback()
        raise AccountDeletionError(f"failed:{type(error).__name__}") from None
    report = _report(user_id, "deleted", plan, applied=True)
    report["eligible"] = True
    return report


def _residual_check(connection: Any, t: int, runs: list[int], global_before: dict[str, int] | None) -> None:
    """In the deleting transaction, before commit (CONTRACT 4-6)."""
    for table in OWNED_TABLES:
        if _count(connection, f"SELECT count(*) AS n FROM {table} WHERE user_id = ?", (t,)):
            raise AccountDeletionError("residual_rows")
    for sql in ("SELECT count(*) AS n FROM users WHERE id = ?",
                "SELECT count(*) AS n FROM shared_decks WHERE owner_user_id = ?"):
        if _count(connection, sql, (t,)):
            raise AccountDeletionError("residual_rows")
    owners, _ = _run_owners(connection)
    if any(owner == t for owner in owners.values()):
        raise AccountDeletionError("residual_rows")
    if runs and _count(connection, "SELECT count(*) AS n FROM srs_migration_snapshots WHERE run_id IN "
                                   f"({','.join(str(r) for r in runs)})", ()):
        raise AccountDeletionError("residual_rows")  # another account's record still on a deleted run
    if global_before is not None:  # SQLite: the only writer, so the totals must be exactly equal
        if {table: _count(connection, f"SELECT count(*) AS n FROM {table}", ()) for table in GLOBAL_TABLES} != global_before:
            raise AccountDeletionError("shared_data_changed")

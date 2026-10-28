"""Personal card identity (Gate D-2 U1~U3).

Contract: docs/plans/srs-improvement/gate-d2/APPROVAL_REQUEST.md (D-P2a, D-P2c,
D-P6a~c) and PLAN.md U1~U3.

On SQLite `vocab_items.id` was a plain INTEGER PRIMARY KEY, so deleting the
card with the largest id let the next new card take that id and inherit the
deleted card's logs, receipts and snapshots (CONTRACT F12, F14).

- U1 `personal_id_references`: every server-side place that holds a personal
  card id, and the largest id in the whole id space (all accounts). Malformed
  JSON or a non-integer reference stops the scan instead of being skipped.
  Ids kept only in browsers (reading session, recent ids) cannot be seen here.
- U2 `rebuild_vocab_items_autoincrement`: SQLite only, explicit call. Rebuilds
  the table as AUTOINCREMENT in one transaction and raises the sequence to at
  least every reference found by U1 and any existing sequence value. Rows, ids,
  content, constraints, indexes and triggers are kept; a failure rolls back.
- U3 `record_personal_deletions`: content-free ledger rows (kind, account, id,
  time), written in the caller's transaction just before the DELETE.
  `scan_identity` / `flag_identity_unknown`: ids whose history may belong to
  more than one card are flagged "identity unknown". Nothing is relinked,
  moved or deleted. Detection is evidence-based and incomplete: see
  `scan_identity` for what it cannot see and what can raise a false flag.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Iterable

from app.database import is_postgres_connection, now_iso
from app.srs.completion import seoul_date
from app.srs.goals import read_utc

PERSONAL = "personal"
REBUILD_TABLE = "vocab_items__d2_rebuild"
_PK = re.compile(r"(\bid\s+INTEGER\s+PRIMARY\s+KEY)(?!\s+AUTOINCREMENT)", re.IGNORECASE)
_AUTOINCREMENT = re.compile(r"\bid\s+INTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT\b", re.IGNORECASE)
_CREATE = re.compile(r"^\s*CREATE\s+TABLE\s+(\"vocab_items\"|vocab_items|'vocab_items'|`vocab_items`)", re.IGNORECASE)


class IdentityError(Exception):
    """A reference that cannot be interpreted, or a rebuild precondition that does
    not hold. Raised instead of guessing; nothing is written."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


# ---------------------------------------------------------------------------
# U1: references
# ---------------------------------------------------------------------------

def _require_sqlite(connection: Any) -> None:
    if is_postgres_connection(connection):
        raise IdentityError("sqlite_only", "PostgreSQL uses identity columns; this path is SQLite only")


def _table_exists(connection: Any, table: str) -> bool:
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
    ).fetchone() is not None


def _int_max(connection: Any, source: str, table: str, column: str, where: str = "") -> int:
    """MAX of an integer id column. Any non-integer, non-NULL value stops the scan."""
    clause = f" AND ({where})" if where else ""
    bad = connection.execute(
        f"SELECT COUNT(*) FROM {table} WHERE {column} IS NOT NULL AND typeof({column}) != 'integer'{clause}"
    ).fetchone()[0]
    if bad:
        raise IdentityError("uninterpretable_reference", f"{source}: {bad} non-integer value(s)")
    value = connection.execute(f"SELECT MAX({column}) FROM {table} WHERE 1 = 1{clause}").fetchone()[0]
    return int(value or 0)


def _is_id(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _loads(raw: Any, source: str) -> Any:
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        raise IdentityError("invalid_json", source) from None


def _card_entries(entries: Any, source: str) -> list[int]:
    if not isinstance(entries, list):
        raise IdentityError("uninterpretable_reference", f"{source}: not a list")
    ids: list[int] = []
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("kind") not in (PERSONAL, "lexeme") or not _is_id(entry.get("ref_id")):
            raise IdentityError("uninterpretable_reference", f"{source}: card entry without kind/ref_id")
        if entry["kind"] == PERSONAL:
            ids.append(entry["ref_id"])
    return ids


def _run_ids(connection: Any) -> int:
    """Personal card ids in srs_migration_runs.scope_json / summary_json."""
    best = 0
    for row in connection.execute("SELECT id, mode, scope_json, summary_json FROM srs_migration_runs ORDER BY id").fetchall():
        source = f"srs_migration_runs#{row['id']}"
        scope = _loads(row["scope_json"], f"{source}.scope_json")
        if not isinstance(scope, dict) or not _is_id(scope.get("user_id")):
            raise IdentityError("uninterpretable_reference", f"{source}.scope_json")
        if "cards" in scope:
            best = max([best, *_card_entries(scope["cards"], f"{source}.scope_json.cards")])
        elif not _is_id(scope.get("source_run_id")):
            raise IdentityError("uninterpretable_reference", f"{source}.scope_json: neither cards nor source_run_id")
        if row["summary_json"] is None:
            continue
        summary = _loads(row["summary_json"], f"{source}.summary_json")
        if isinstance(summary, dict):
            if not _is_id(summary.get("cursor")):
                raise IdentityError("uninterpretable_reference", f"{source}.summary_json: no cursor")
            results = summary.get("results")
        else:
            results = summary
        best = max([best, *_card_entries(results, f"{source}.summary_json.results")])
    return best


def _snapshot_ids(connection: Any) -> int:
    best = _int_max(connection, "srs_migration_snapshots.card_ref", "srs_migration_snapshots", "card_ref",
                    "card_kind = 'personal'")
    for row in connection.execute(
        "SELECT id, card_ref, legacy_json FROM srs_migration_snapshots WHERE card_kind = 'personal' ORDER BY id"
    ).fetchall():
        source = f"srs_migration_snapshots#{row['id']}.legacy_json"
        payload = _loads(row["legacy_json"], source)
        card = payload.get("card") if isinstance(payload, dict) else None
        if not isinstance(card, dict) or not _is_id(card.get("id")) or card["id"] != row["card_ref"]:
            raise IdentityError("uninterpretable_reference", f"{source}: card id missing or different from card_ref")
    return best


def personal_id_references(connection: Any) -> dict[str, int]:
    """Largest personal card id per server-side source, across all accounts.

    `meaning_feedback.vocabulary_id` is a personal card id: the feedback endpoint
    keeps it only when it is the caller's own vocab_items row (main.py) and the
    PostgreSQL schema declares it REFERENCES vocab_items(id). SQLite keeps it
    after the card is deleted, so it counts. Raises IdentityError instead of
    skipping anything it cannot read."""
    _require_sqlite(connection)
    refs: dict[str, int] = {"vocab_items": _int_max(connection, "vocab_items.id", "vocab_items", "id")}
    simple = (
        ("review_logs.vocab_item_id", "review_logs", "vocab_item_id", ""),
        ("srs_review_receipts.card_ref", "srs_review_receipts", "card_ref", "card_kind = 'personal'"),
        ("srs_card_deletions.card_ref", "srs_card_deletions", "card_ref", "card_kind = 'personal'"),
        ("srs_card_identity_flags.card_ref", "srs_card_identity_flags", "card_ref", "card_kind = 'personal'"),
        ("meaning_feedback.vocabulary_id", "meaning_feedback", "vocabulary_id", ""),
    )
    for source, table, column, where in simple:
        if _table_exists(connection, table):
            refs[source] = _int_max(connection, source, table, column, where)
    if _table_exists(connection, "srs_migration_snapshots"):
        refs["srs_migration_snapshots"] = _snapshot_ids(connection)
    if _table_exists(connection, "srs_migration_runs"):
        refs["srs_migration_runs"] = _run_ids(connection)
    refs["sqlite_sequence"] = _sequence(connection)
    return refs


def _sequence(connection: Any) -> int:
    if not _table_exists(connection, "sqlite_sequence"):
        return 0
    row = connection.execute("SELECT seq FROM sqlite_sequence WHERE name = 'vocab_items'").fetchone()
    if row is None:
        return 0
    if not _is_id(row[0]):
        raise IdentityError("uninterpretable_reference", "sqlite_sequence.vocab_items")
    return int(row[0])


# ---------------------------------------------------------------------------
# U2: rebuild
# ---------------------------------------------------------------------------

def _digest(connection: Any, table: str) -> tuple[int, str]:
    rows = connection.execute(f"SELECT * FROM {table} ORDER BY id").fetchall()
    digest = hashlib.sha256()
    for row in rows:
        digest.update(json.dumps([row[key] for key in row.keys()], default=str, ensure_ascii=False).encode())
    return len(rows), digest.hexdigest()


def _attachments(connection: Any) -> list[tuple[str, str, str]]:
    return [(r["type"], r["name"], r["sql"]) for r in connection.execute(
        "SELECT type, name, sql FROM sqlite_master WHERE tbl_name = 'vocab_items' "
        "AND type IN ('index', 'trigger') AND sql IS NOT NULL ORDER BY type, name"
    ).fetchall()]


def _schema_shape(connection: Any) -> dict[str, Any]:
    return {
        "columns": [tuple(r) for r in connection.execute("PRAGMA table_info(vocab_items)").fetchall()],
        "foreign_keys": [tuple(r) for r in connection.execute("PRAGMA foreign_key_list(vocab_items)").fetchall()],
        "attachments": _attachments(connection),
        "auto_indexes": sorted(r["name"] for r in connection.execute("PRAGMA index_list(vocab_items)").fetchall()
                               if r["origin"] != "c"),
    }


def _fk_violations(connection: Any) -> set[tuple]:
    return {tuple(r) for r in connection.execute("PRAGMA foreign_key_check").fetchall()}


def _step(fail_step: str | None, name: str) -> None:
    if fail_step == name:
        raise IdentityError("injected_failure", name)


def rebuild_vocab_items_autoincrement(connection: Any, *, fail_step: str | None = None) -> dict[str, Any]:
    """SQLite only, explicit operation. Idempotent: an AUTOINCREMENT table is not
    rebuilt again, only its sequence is raised when a reference exceeds it (never
    lowered). `fail_step` is a test hook that raises at a named step."""
    _require_sqlite(connection)
    if connection.in_transaction:
        raise IdentityError("transaction_open", "call on a connection without an open transaction")
    foreign_keys = connection.execute("PRAGMA foreign_keys").fetchone()[0]
    # Required by SQLite's table-rebuild procedure: with foreign keys on, DROP TABLE
    # would act on rows that reference vocab_items. Checked again before commit.
    connection.execute("PRAGMA foreign_keys = OFF")
    try:
        connection.execute("BEGIN IMMEDIATE")
        try:
            report = _rebuild(connection, fail_step)
            connection.execute("COMMIT")
        except BaseException:
            connection.execute("ROLLBACK")
            raise
    finally:
        connection.execute(f"PRAGMA foreign_keys = {'ON' if foreign_keys else 'OFF'}")
    return report


def _rebuild(connection: Any, fail_step: str | None) -> dict[str, Any]:
    refs = personal_id_references(connection)
    sequence_before = refs["sqlite_sequence"]
    target = max(refs.values(), default=0)
    row = connection.execute("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'vocab_items'").fetchone()
    if row is None:
        raise IdentityError("missing_table", "vocab_items")
    create_sql = row["sql"]
    views = [r["name"] for r in connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'view' AND sql LIKE '%vocab_items%'").fetchall()]
    if views:
        raise IdentityError("view_depends_on_vocab_items", ", ".join(views))
    if _table_exists(connection, REBUILD_TABLE):
        raise IdentityError("leftover_rebuild_table", REBUILD_TABLE)
    shape_before = _schema_shape(connection)
    count_before, hash_before = _digest(connection, "vocab_items")
    violations_before = _fk_violations(connection)
    already = bool(_AUTOINCREMENT.search(create_sql))
    if not already:
        if len(_PK.findall(create_sql)) != 1 or not _CREATE.match(create_sql):
            raise IdentityError("unexpected_vocab_items_definition", "id INTEGER PRIMARY KEY not found exactly once")
        new_sql = _CREATE.sub(f"CREATE TABLE {REBUILD_TABLE}", _PK.sub(r"\1 AUTOINCREMENT", create_sql, count=1), count=1)
        attachments = shape_before["attachments"]
        columns = ", ".join(f'"{c[1]}"' for c in shape_before["columns"])
        connection.execute(new_sql)
        _step(fail_step, "after_create")
        connection.execute(f"INSERT INTO {REBUILD_TABLE} ({columns}) SELECT {columns} FROM vocab_items")
        _step(fail_step, "after_copy")
        connection.execute("DROP TABLE vocab_items")
        connection.execute(f"ALTER TABLE {REBUILD_TABLE} RENAME TO vocab_items")
        _step(fail_step, "after_rename")
        for _kind, _name, sql in attachments:
            connection.execute(sql)
    sequence_now = _sequence(connection)
    sequence_after = max(target, sequence_before, sequence_now)
    if connection.execute("SELECT 1 FROM sqlite_sequence WHERE name = 'vocab_items'").fetchone():
        connection.execute("UPDATE sqlite_sequence SET seq = ? WHERE name = 'vocab_items'", (sequence_after,))
    else:
        connection.execute("INSERT INTO sqlite_sequence (name, seq) VALUES ('vocab_items', ?)", (sequence_after,))
    _step(fail_step, "after_sequence")
    count_after, hash_after = _digest(connection, "vocab_items")
    if (count_after, hash_after) != (count_before, hash_before):
        raise IdentityError("rebuild_changed_rows", f"{count_before}->{count_after}")
    shape_after = _schema_shape(connection)
    if {k: v for k, v in shape_after.items() if k != "attachments"} != {k: v for k, v in shape_before.items() if k != "attachments"} \
            or [a[:2] for a in shape_after["attachments"]] != [a[:2] for a in shape_before["attachments"]]:
        raise IdentityError("rebuild_changed_schema", "columns, foreign keys, indexes or triggers differ")
    if not _fk_violations(connection) <= violations_before:
        raise IdentityError("rebuild_foreign_key_violation")
    if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
        raise IdentityError("rebuild_quick_check_failed")
    return {
        "already_autoincrement": already,
        "rows": count_after,
        "content_sha256": hash_after,
        "references": refs,
        "max_reference": target,
        "sequence_before": sequence_before,
        "sequence_after": sequence_after,
        "next_id_at_least": sequence_after + 1,
    }


# ---------------------------------------------------------------------------
# U3: deletion ledger and identity flags
# ---------------------------------------------------------------------------

def record_personal_deletions(connection: Any, where: str, params: Iterable[Any]) -> int:
    """Ledger rows for the personal cards a DELETE with the same WHERE is about to
    remove. Call in the same transaction, immediately before that DELETE, so the
    deletion and its ledger rows commit or roll back together. The caller holds
    the owning account's write lock (begin_card_write / lock_card_owners).

    Copied per card: kind, account, id, deletion time and -- Gate D-2 U4 follow-up
    (E1/E2) -- the card's past-learning mark (`history_intro_status`,
    `history_intro_known_by`) exactly as stored, NULL included. Never any word,
    meaning, example, schedule, classification or counter."""
    cursor = connection.execute(
        "INSERT INTO srs_card_deletions (card_kind, user_id, card_ref, deleted_at, "
        "history_intro_status, history_intro_known_by) "
        f"SELECT 'personal', user_id, id, ?, history_intro_status, history_intro_known_by FROM vocab_items WHERE {where}",
        (now_iso(), *params),
    )
    return int(cursor.rowcount or 0)


def lock_card_owners(connection: Any, where: str, params: Iterable[Any]) -> None:
    """Account write lock for deletions not scoped to one account (two unused legacy
    helpers). SQLite: one database-wide writer (BEGIN IMMEDIATE unless a write
    transaction is already open). PostgreSQL: the owners' users rows FOR UPDATE in
    id order, the same lock reviews and migrations take."""
    params = tuple(params)
    if is_postgres_connection(connection):
        for row in connection.execute(
            f"SELECT DISTINCT user_id FROM vocab_items WHERE ({where}) AND user_id IS NOT NULL ORDER BY user_id", params
        ).fetchall():
            connection.execute("SELECT id FROM users WHERE id = ? FOR UPDATE", (row["user_id"],))
    elif not connection.in_transaction:
        connection.execute("BEGIN IMMEDIATE")


@dataclass
class IdentityFinding:
    user_id: int
    card_ref: int
    reasons: list[str] = field(default_factory=list)


@dataclass
class IdentityScan:
    findings: list[IdentityFinding]
    cards_checked: int
    undetermined: list[tuple[int, int]]  # (user, id): card creation time unreadable, cannot judge


def scan_identity(connection: Any, user_id: int | None = None) -> IdentityScan:
    """Read-only. Flags an existing personal card when stored history provably
    predates it or was written for another card with the same id:

    - `deleted_then_reused`: the ledger recorded a deletion of the same
      (account, id) and a card with that id exists again.
    - `log_before_created`: a review log of that (account, id) is earlier than
      the card's creation time (both times readable).
    - `receipt_before_created` / `receipt_other_card`: a receipt older than the
      card, or whose stored response names a different creation time.
    - `snapshot_other_card`: a migration snapshot of that id whose stored card
      has a different creation time, or which is older than the card.

    Not signals: "no engine state + logs", broken log chains or counter
    mismatches (normal incomplete history, conversion and rollback produce them).

    Cannot see (false negatives): a reuse whose old history has only unreadable
    times; old rows written in the same instant as the new card's creation; a
    card whose creation time is unreadable (listed as `undetermined`, not
    flagged); reuse whose evidence was removed. Can raise false flags: a
    creation time that was rewritten later than the card's real history, or
    clock skew between writers. Flags are evidence, not proof."""
    params: tuple[Any, ...] = ()
    clause = ""
    if user_id is not None:
        clause, params = " WHERE user_id = ?", (user_id,)
    cards = connection.execute(f"SELECT id, user_id, created_at FROM vocab_items{clause} ORDER BY id", params).fetchall()
    findings: list[IdentityFinding] = []
    undetermined: list[tuple[int, int]] = []
    for card in cards:
        if card["user_id"] is None:
            continue
        uid, ref = int(card["user_id"]), int(card["id"])
        created = read_utc(card["created_at"])
        finding = IdentityFinding(uid, ref)
        if connection.execute(
            "SELECT 1 FROM srs_card_deletions WHERE card_kind = 'personal' AND user_id = ? AND card_ref = ? LIMIT 1",
            (uid, ref),
        ).fetchone():
            finding.reasons.append("deleted_then_reused")
        if created is None:
            if not finding.reasons:
                undetermined.append((uid, ref))
        else:
            for log in connection.execute(
                "SELECT reviewed_at FROM review_logs WHERE user_id = ? AND vocab_item_id = ?", (uid, ref)
            ).fetchall():
                at = read_utc(log["reviewed_at"])
                if at is not None and at < created:
                    finding.reasons.append("log_before_created")
                    break
            for receipt in connection.execute(
                "SELECT id, created_at, response_json FROM srs_review_receipts "
                "WHERE user_id = ? AND card_kind = 'personal' AND card_ref = ? ORDER BY id", (uid, ref)
            ).fetchall():
                at = read_utc(receipt["created_at"])
                body = _loads(receipt["response_json"], f"srs_review_receipts#{receipt['id']}.response_json")
                stored = body.get("created_at") if isinstance(body, dict) else None
                if at is not None and at < created:
                    finding.reasons.append("receipt_before_created")
                    break
                if stored is not None and stored != card["created_at"]:
                    finding.reasons.append("receipt_other_card")
                    break
            for snap in connection.execute(
                "SELECT id, created_at, legacy_json FROM srs_migration_snapshots "
                "WHERE user_id = ? AND card_kind = 'personal' AND card_ref = ? ORDER BY id", (uid, ref)
            ).fetchall():
                payload = _loads(snap["legacy_json"], f"srs_migration_snapshots#{snap['id']}.legacy_json")
                stored_card = payload.get("card") if isinstance(payload, dict) else None
                if not isinstance(stored_card, dict):
                    raise IdentityError("uninterpretable_reference", f"srs_migration_snapshots#{snap['id']}: no card")
                stored = stored_card.get("created_at")
                at = read_utc(snap["created_at"])
                if (stored is not None and stored != card["created_at"]) or (at is not None and at < created):
                    finding.reasons.append("snapshot_other_card")
                    break
        if finding.reasons:
            findings.append(finding)
    return IdentityScan(findings, len(cards), undetermined)


def flag_identity_unknown(connection: Any, findings: Iterable[IdentityFinding]) -> int:
    """Records findings. Existing flags are kept as they are (never removed or
    narrowed); history rows are not touched.

    Takes the same account write lock as reviews (SQLite: BEGIN IMMEDIATE; PostgreSQL:
    the users rows FOR UPDATE, in id order) before writing, so a flag and a review of
    the same account are ordered: a review that committed first stays as it is; a
    review that starts after the flag commits is refused. The caller commits."""
    from app.srs import storage

    findings = list(findings)
    users = sorted({finding.user_id for finding in findings})
    if is_postgres_connection(connection):
        for user_id in users:
            storage.begin_card_write(connection, user_id)  # users row FOR UPDATE, id order
    elif users and not connection.in_transaction:
        storage.begin_card_write(connection, users[0])  # SQLite: BEGIN IMMEDIATE (database-wide writer)
    if not is_postgres_connection(connection):
        for user_id in users:
            if connection.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone() is None:
                raise storage.SrsWriteError("account_not_found", 404)
    written = 0
    at = now_iso()
    for finding in findings:
        cursor = connection.execute(
            "INSERT INTO srs_card_identity_flags (user_id, card_kind, card_ref, reasons, detected_at) "
            "VALUES (?, 'personal', ?, ?, ?) ON CONFLICT (user_id, card_kind, card_ref) DO NOTHING",
            (finding.user_id, finding.card_ref, json.dumps(sorted(set(finding.reasons))), at),
        )
        written += int(cursor.rowcount or 0)
    return written


def flagged_personal_ids(connection: Any, user_id: int) -> set[int]:
    """Personal card ids of this account that are flagged identity unknown."""
    return {int(row["card_ref"]) for row in connection.execute(
        "SELECT card_ref FROM srs_card_identity_flags WHERE user_id = ? AND card_kind = 'personal'", (user_id,)
    ).fetchall()}


def is_identity_unknown(connection: Any, user_id: int, kind: str, ref_id: int) -> bool:
    if kind != PERSONAL:
        return False
    return connection.execute(
        "SELECT 1 FROM srs_card_identity_flags WHERE user_id = ? AND card_kind = 'personal' AND card_ref = ?",
        (user_id, ref_id),
    ).fetchone() is not None


def receipt_may_be_other_card(connection: Any, user_id: int, kind: str, ref_id: int, receipt_created_at: Any) -> bool:
    """True when a stored receipt may have been written for a different card with
    this id, so it must not be replayed onto the current card:

    - the ledger shows the same (account, id) was deleted at or after the receipt
      was written (the receipt belongs to the deleted card), or
    - the id is flagged identity unknown and the receipt predates the flag.

    An unreadable time on either side counts as True (refuse rather than replay).
    Receipts written after a flag belong to the current card and still replay."""
    if kind != PERSONAL:
        return False
    receipt_at = read_utc(receipt_created_at)
    flag = connection.execute(
        "SELECT detected_at FROM srs_card_identity_flags WHERE user_id = ? AND card_kind = 'personal' AND card_ref = ?",
        (user_id, ref_id),
    ).fetchone()
    if flag is not None:
        detected_at = read_utc(flag["detected_at"])
        if receipt_at is None or detected_at is None or receipt_at <= detected_at:
            return True
    for row in connection.execute(
        "SELECT deleted_at FROM srs_card_deletions WHERE card_kind = 'personal' AND user_id = ? AND card_ref = ?",
        (user_id, ref_id),
    ).fetchall():
        deleted_at = read_utc(row["deleted_at"])
        if receipt_at is None or deleted_at is None or deleted_at >= receipt_at:
            return True
    return False


def identity_unknown_days(connection: Any, user_id: int) -> dict[tuple[str, int], frozenset[date]]:
    """For flagged ids whose log times are ALL readable: the Seoul dates of those
    logs. A card behind that id may have been introduced on any of them, so new-word
    counts are unknown on those dates only (D-P6c). An id with any unreadable log
    time is left out here: the existing unreadable-time rule (unknown on every
    date) already covers it and must not be narrowed."""
    days: dict[tuple[str, int], frozenset[date]] = {}
    for flag in connection.execute(
        "SELECT card_ref FROM srs_card_identity_flags WHERE user_id = ? AND card_kind = 'personal'", (user_id,)
    ).fetchall():
        ref = int(flag["card_ref"])
        times = [read_utc(r["reviewed_at"]) for r in connection.execute(
            "SELECT reviewed_at FROM review_logs WHERE user_id = ? AND vocab_item_id = ?", (user_id, ref)
        ).fetchall()]
        if any(t is None for t in times):
            continue
        days[(PERSONAL, ref)] = frozenset(seoul_date(t) for t in times)
    return days

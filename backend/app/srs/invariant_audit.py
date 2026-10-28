"""Gate E-4: read-only, counts-only I1..I7 audit. Never invoked by the app.

I1..I5 examine one consistent snapshot. I6/I7 need a deletion-only rehearsal
baseline from this module, in memory, on the same connection and fixed clock.
Without that evidence they are NOT evaluated, not silently passed. No repair,
schema initialization, identity marking, sequence advancement or data export.
"""

from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any, Iterator

from app.database import is_postgres_connection
from app.srs import goals, identity, migration
from app.srs.completion import SEOUL
from app.repositories import stats_history_repository

KINDS = ("personal", "lexeme")


class AuditInputError(ValueError):
    """Fixed reason codes only; never stringify database content or driver errors."""


def _id(value: Any, *, zero: bool = False) -> bool:
    return type(value) is int and value >= (0 if zero else 1)


def _json(raw: Any) -> Any:
    try:
        return json.loads(raw)
    except (TypeError, ValueError, RecursionError):
        raise AuditInputError("unreadable_json") from None


def _result(violations: int = 0, unknown: int = 0, **counts: int) -> dict:
    return dict(status="fail" if violations else "unknown" if unknown else "pass",
                violations=violations, unknown=unknown, **counts)


@contextmanager
def read_snapshot(connection: Any) -> Iterator[Any]:
    """Own a new read-only transaction; rollback even on success. No shared transaction.

    PostgreSQL sequences are non-MVCC: I3 is an observation, not a lock against
    concurrent sequence changes. Writes/upgrades must be quiesced for release audits.
    """
    if is_postgres_connection(connection):
        from psycopg.pq import TransactionStatus

        raw = connection._connection
        if raw.info.transaction_status != TransactionStatus.IDLE:
            raise AuditInputError("transaction_already_open")
        try:
            connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            yield connection
        finally:
            raw.rollback()
    else:
        if connection.in_transaction:
            raise AuditInputError("transaction_already_open")
        previous = connection.execute("PRAGMA query_only").fetchone()[0]
        connection.execute("PRAGMA query_only = ON")
        try:
            connection.execute("BEGIN")
            yield connection
        finally:
            connection.rollback()
            connection.execute(f"PRAGMA query_only = {int(previous)}")


def _require_snapshot(connection: Any) -> None:
    if is_postgres_connection(connection):
        row = connection.execute("SELECT current_setting('transaction_read_only') AS ro, "
                                 "current_setting('transaction_isolation') AS isolation").fetchone()
        if row["ro"] != "on" or row["isolation"] != "repeatable read":
            raise AuditInputError("read_only_snapshot_required")
    elif not connection.in_transaction or not connection.execute("PRAGMA query_only").fetchone()[0]:
        raise AuditInputError("read_only_snapshot_required")


def _rows(connection: Any, table: str) -> list[dict]:
    # All callers supply module-owned table names, never command-line identifiers.
    return [dict(row) for row in connection.execute(f"SELECT * FROM {table}").fetchall()]


class _Audit:
    def __init__(self, connection: Any):
        self.c = connection
        self.cards = {k: _rows(connection, t) for k, t in
                      (("personal", "vocab_items"), ("lexeme", "user_word_progress"))}
        self.logs = {k: _rows(connection, t) for k, t in
                     (("personal", "review_logs"), ("lexeme", "lexeme_review_logs"))}
        self.receipts = _rows(connection, "srs_review_receipts")
        self.snaps = _rows(connection, "srs_migration_snapshots")
        self.runs = _rows(connection, "srs_migration_runs")
        self.deletions = _rows(connection, "srs_card_deletions")
        self.flags = _rows(connection, "srs_card_identity_flags")
        self.restarts = _rows(connection, "srs_evidence_restarts")
        # P-RB: account write blocks (owner / active-marker consistency, counted under I1)
        self.blocks = _rows(connection, "account_write_blocks")
        self.recoveries = _rows(connection, "account_recovery_runs")
        self.user_ids = {r["id"] for r in connection.execute("SELECT id FROM users").fetchall()}
        self.log_index = {k: {r["id"]: r for r in rows} for k, rows in self.logs.items()}
        self.run_index = {r["id"]: r for r in self.runs}
        self.card_columns = {kind: migration._card_columns(connection, kind) for kind in KINDS}

    def snapshot_shape(self, row: dict, body: Any) -> dict | None:
        run = self.run_index.get(row["run_id"])
        kind = row["card_kind"]
        if run is None or run["mode"] not in ("apply", "rollback") or kind not in KINDS:
            return None
        return migration._record_shape(run["mode"], kind, row["card_ref"], body, self.card_columns[kind])

    @staticmethod
    def log_card(kind: str, row: dict) -> Any:
        return row["vocab_item_id" if kind == "personal" else "lexeme_id"]

    def ownership(self) -> tuple[dict, dict]:
        cards = {r["id"]: r for r in self.cards["personal"]}
        ledger = {(r["user_id"], r["card_ref"]) for r in self.deletions if r["card_kind"] == "personal"}
        orphan = wrong = unknown = 0
        for log in self.logs["personal"]:
            ref, uid = log["vocab_item_id"], log["user_id"]
            if not _id(ref) or not _id(uid):
                unknown += 1
            elif ref not in cards:
                orphan += (uid, ref) not in ledger
            else:
                wrong += uid != cards[ref]["user_id"]
        subscribed = {(r["user_id"], r["lexeme_id"]) for r in self.cards["lexeme"]}
        # Shared lexemes are account-scoped, not globally owned personal card ids.
        missing_progress = sum((r["user_id"], r["lexeme_id"]) not in subscribed for r in self.logs["lexeme"])
        bad_blocks = sum(1 for block in self.blocks
                         if not _id(block["user_id"]) or block["user_id"] not in self.user_ids
                         or (block["active_user_id"] is not None and block["active_user_id"] != block["user_id"])
                         or (block["status"] == "active") != (block["active_user_id"] is not None))
        blocks_by_id = {block["id"]: block for block in self.blocks}
        bad_recoveries = sum(
            1 for run in self.recoveries
            if not _id(run["user_id"]) or run["user_id"] not in self.user_ids
            or (run["active_user_id"] is not None and run["active_user_id"] != run["user_id"])
            or (run["state"] != "closed") != (run["active_user_id"] is not None)
            or blocks_by_id.get(run["block_id"]) is None
            or blocks_by_id[run["block_id"]]["user_id"] != run["user_id"]
            or blocks_by_id[run["block_id"]]["recovery_key"] != run["recovery_key"])
        return (_result(orphan + bad_blocks + bad_recoveries, unknown),
                _result(wrong, unknown, subscribed_logs_without_progress=missing_progress))

    def sequence(self) -> dict:
        refs: list[int] = []
        unknown = 0

        def add(value: Any) -> None:
            nonlocal unknown
            if _id(value):
                refs.append(value)
            else:
                unknown += 1

        for row in self.cards["personal"]:
            add(row["id"])
        for row in self.logs["personal"]:
            add(row["vocab_item_id"])
        for rows in (self.receipts, self.snaps, self.deletions, self.flags, self.restarts):
            for row in rows:
                if row["card_kind"] == "personal":
                    add(row["card_ref"])
                elif row["card_kind"] != "lexeme":
                    unknown += 1
        for row in self.c.execute("SELECT vocabulary_id FROM meaning_feedback WHERE vocabulary_id IS NOT NULL").fetchall():
            add(row["vocabulary_id"])
        for row in self.snaps:
            try:
                body = _json(row["legacy_json"])
                if self.snapshot_shape(row, body) is None:
                    raise AuditInputError("snapshot_shape")
                card = body["card"]
                if not isinstance(card, dict) or row["card_kind"] not in KINDS:
                    raise AuditInputError("snapshot_shape")
                value = card["id" if row["card_kind"] == "personal" else "lexeme_id"]
                if not _id(value) or value != row["card_ref"]:
                    raise AuditInputError("snapshot_identity")
                if row["card_kind"] == "personal":
                    add(value)
            except (AuditInputError, TypeError, KeyError):
                unknown += 1
        for run in self.runs:
            try:
                scope = _json(run["scope_json"])
                if run["mode"] == "rollback":
                    valid = (isinstance(scope, dict) and set(scope) == {"user_id", "source_run_id"}
                             and _id(scope["user_id"]) and _id(scope["source_run_id"]))
                else:
                    valid = migration._full_scope(scope, run["config_version"]) or migration._reduced_scope(scope, run["config_version"])
                if not valid:
                    raise AuditInputError("scope_shape")
                for card in scope.get("cards", []):
                    if card["kind"] == "personal":
                        add(card["ref_id"])
                if run["summary_json"] is not None:
                    summary = _json(run["summary_json"])
                    if isinstance(summary, dict):
                        if not _id(summary.get("cursor"), zero=True):
                            raise AuditInputError("summary_shape")
                        summary = summary.get("results")
                    if not isinstance(summary, list):
                        raise AuditInputError("summary_shape")
                    for entry in summary:
                        if not isinstance(entry, dict) or entry.get("kind") not in KINDS or not _id(entry.get("ref_id")):
                            raise AuditInputError("summary_shape")
                        if entry["kind"] == "personal":
                            add(entry["ref_id"])
            except (AuditInputError, TypeError, KeyError, RecursionError):
                unknown += 1
        if is_postgres_connection(self.c):
            row = self.c.execute("SELECT pg_get_serial_sequence('vocab_items', 'id') AS name").fetchone()
            if not row or not row["name"]:
                return _result(unknown=unknown + 1)
            # Quote the catalog-returned identifier, not a user-provided string. Never nextval/setval.
            from psycopg import sql

            sequence = self.c._connection.execute(sql.SQL("SELECT last_value, is_called FROM {}")
                                                  .format(sql.Identifier(*row["name"].split(".")))).fetchone()
            value = sequence["last_value"]
            increment = self.c.execute("SELECT seqincrement AS n FROM pg_sequence WHERE seqrelid = ?::regclass",
                                      (row["name"],)).fetchone()["n"]
            if increment != 1:
                unknown += 1
        else:
            shape = self.c.execute("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'vocab_items'").fetchone()
            if not shape or not identity._AUTOINCREMENT.search(shape["sql"]):
                return _result(1, unknown)
            row = self.c.execute("SELECT seq FROM sqlite_sequence WHERE name = 'vocab_items'").fetchone()
            value = row["seq"] if row else 0
        if not _id(value, zero=True):
            return _result(unknown=unknown + 1)
        # An unused PG sequence can still hand out its last_value; it must exceed every reference.
        behind = value < max(refs, default=0)
        if is_postgres_connection(self.c) and not sequence["is_called"] and refs:
            behind = value <= max(refs)
        return _result(int(behind), unknown, references_checked=len(refs))

    def identities(self) -> dict:
        try:
            scan = identity.scan_identity(self.c)
        except (identity.IdentityError, ValueError, TypeError, KeyError, RecursionError):
            return _result(unknown=1)
        marked = {(r["user_id"], r["card_ref"]) for r in self.flags if r["card_kind"] == "personal"}
        missing = sum((f.user_id, f.card_ref) not in marked for f in scan.findings)
        return _result(missing, len(scan.undetermined), findings=len(scan.findings), cards_checked=scan.cards_checked)

    def log_references(self) -> dict:
        wrong = unknown = checked = 0

        def log_ref(uid: Any, kind: Any, ref: Any, value: Any, *, zero: bool = False) -> None:
            nonlocal wrong, unknown, checked
            if zero and value == 0 and type(value) is int:
                return
            checked += 1
            if kind not in KINDS or not _id(uid) or not _id(ref) or not _id(value):
                unknown += 1
                return
            row = self.log_index[kind].get(value)
            wrong += row is None or row["user_id"] != uid or self.log_card(kind, row) != ref

        for kind, rows in self.cards.items():
            for row in rows:
                if row["evidence_from_log_id"] is not None:
                    log_ref(row["user_id"], kind, row["id" if kind == "personal" else "lexeme_id"], row["evidence_from_log_id"])
        for row in self.receipts:
            if row["review_log_id"] is not None:
                log_ref(row["user_id"], row["card_kind"], row["card_ref"], row["review_log_id"])
        for row in self.snaps:
            try:
                body = _json(row["legacy_json"])
                if not isinstance(body, dict) or not isinstance(body.get("card"), dict):
                    raise AuditInputError("snapshot_shape")
                if self.snapshot_shape(row, body) is None:
                    unknown += 1
                if "last_log_id" in body:
                    log_ref(row["user_id"], row["card_kind"], row["card_ref"], body["last_log_id"], zero=True)
                if isinstance(body.get("baseline"), dict) and "last_log_id" in body["baseline"]:
                    log_ref(row["user_id"], row["card_kind"], row["card_ref"], body["baseline"]["last_log_id"], zero=True)
                elif "last_log_id" not in body:
                    raise AuditInputError("snapshot_shape")
                if "restart" in body:
                    log_ref(row["user_id"], row["card_kind"], row["card_ref"], body["restart"]["previous_boundary"])
                boundary = body["card"].get("evidence_from_log_id")
                if boundary is not None:
                    log_ref(row["user_id"], row["card_kind"], row["card_ref"], boundary)
            except (AuditInputError, TypeError, KeyError):
                unknown += 1
        snapshots = {r["id"]: r for r in self.snaps}
        for row in self.restarts:
            for field in ("previous_boundary", "new_boundary"):
                log_ref(row["user_id"], row["card_kind"], row["card_ref"], row[field])
            checked += 1
            source = snapshots.get(row["source_snapshot_id"])
            wrong += source is None or any(source[k] != row[k] for k in ("user_id", "card_kind", "card_ref"))
        return _result(wrong, unknown, references_checked=checked)


@dataclass(frozen=True)
class DeletionBaseline:
    """In-memory evidence only. Not an export format and never printed by the CLI."""

    connection: Any
    at: datetime
    days: tuple[date, ...]
    logs: tuple
    accounts: tuple[int, ...]
    metrics: tuple | None


def _baseline(connection: Any, at: datetime, days: tuple[date, ...]) -> DeletionBaseline:
    _require_snapshot(connection)
    if not isinstance(at, datetime) or goals.read_utc(at.isoformat()) is None:
        raise AuditInputError("aware_clock_required")
    if not days or any(type(day) is not date for day in days) or len(set(days)) != len(days):
        raise AuditInputError("explicit_unique_dates_required")
    users = tuple(row["id"] for row in connection.execute("SELECT id FROM users ORDER BY id").fetchall())
    logs = []
    for kind, table, ref, timestamp in (("personal", "review_logs", "vocab_item_id", "reviewed_at"),
                                        ("lexeme", "lexeme_review_logs", "lexeme_id", "created_at")):
        for row in connection.execute(f"SELECT * FROM {table} ORDER BY id").fetchall():
            # Hash all log values, so changed history cannot masquerade as deletion-only.
            digest = hashlib.sha256(json.dumps(dict(row), sort_keys=True, ensure_ascii=True).encode()).hexdigest()
            logs.append((kind, row["id"], row["user_id"], row[ref], row[timestamp], digest))
    metrics = []
    if any(goals.read_utc(log[4]) is None for log in logs):
        return DeletionBaseline(connection, at, days, tuple(logs), users, None)
    for uid in users:
        setting = goals.account_goal(connection, uid)
        target = setting["daily_new_goal"] if setting else goals.DEFAULT_DAILY_NEW_GOAL
        for day in sorted(days):
            stamp = datetime.combine(day, time(12), SEOUL)
            count = goals.introduction_count(connection, uid, stamp)
            # The same read path as the history API, not an audit-only calendar formula.
            calendar_count = len(stats_history_repository._review_rows(connection, uid, day, day + timedelta(days=1)))
            metrics.append((uid, day, count.status, count.count, count.at_least,
                            None if count.count is None else max(0, target - count.count), calendar_count, target))
    return DeletionBaseline(connection, at, days, tuple(logs), users, tuple(metrics))


def capture_deletion_baseline(connection: Any, *, at: datetime, days: tuple[date, ...]) -> DeletionBaseline:
    """Capture before an externally controlled deletion-only rehearsal, never delete here."""
    return _baseline(connection, at, days)


def audit(connection: Any, *, baseline: DeletionBaseline | None = None) -> dict:
    _require_snapshot(connection)
    current = _Audit(connection)
    i1, i2 = current.ownership()
    checks = {"I1": i1, "I2": i2, "I3": current.sequence(), "I4": current.identities(),
              "I5": current.log_references(),
              "I6": dict(status="not_evaluated", reason="deletion_baseline_required"),
              "I7": dict(status="not_evaluated", reason="deletion_baseline_required")}
    if baseline is not None:
        if baseline.connection is not connection:
            raise AuditInputError("same_connection_baseline_required")
        try:
            after = _baseline(connection, baseline.at, baseline.days)
            before_logs, after_logs = set(baseline.logs), set(after.logs)
            missing = len(before_logs - after_logs)
            checks["I6"] = _result(missing, logs_before=len(before_logs), logs_after=len(after_logs))
            if before_logs != after_logs or baseline.accounts != after.accounts:
                checks["I7"] = dict(status="not_evaluated", reason="fixed_history_and_accounts_required")
            elif baseline.metrics is None or after.metrics is None:
                checks["I7"] = _result(unknown=1)
            else:
                changed = sum(a != b for a, b in zip(baseline.metrics, after.metrics))
                checks["I7"] = _result(changed, account_dates_checked=len(after.metrics))
        except AuditInputError:
            checks["I6"] = _result(unknown=1)
            checks["I7"] = _result(unknown=1)
    status = ("fail" if any(c["status"] == "fail" for c in checks.values()) else
              "unknown" if any(c["status"] == "unknown" for c in checks.values()) else
              "partial" if any(c["status"] == "not_evaluated" for c in checks.values()) else "pass")
    return dict(audit_version=1, status=status, checks=checks)

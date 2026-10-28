"""P-RB account write block: set and conditional release (P_RB_BLOCK_CONTRACT.md).

Internal operator paths only (no HTTP route). Both run in ONE transaction under the account
lock (`lock_account`), so they serialize with every write. They are not stopped by the block
they manage, and they never let an ordinary write through: ordinary writes go through
`begin_account_write`, which knows no key or token.

Release: `precheck_unrecoverable` with the database's proof of no change, or `completed` with
the proof of a verified recovery (tool contract 14); `operator_abandoned` is not allowed.
Nothing is released by failure or time."""

from __future__ import annotations

import hmac
import json
import re
from typing import Any

from app.account_write import AccountWriteError, active_block, lock_account, token_hash
from app.database import get_connection, now_iso

PURPOSE = "srs_recovery"
RELEASE_REASONS = ("completed", "precheck_unrecoverable")
_KEY = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")


def _error(code: str) -> AccountWriteError:
    return AccountWriteError(code, 409)


def _check_key(recovery_key: Any) -> None:
    if not isinstance(recovery_key, str) or not _KEY.fullmatch(recovery_key):
        raise _error("recovery_key_invalid")


def set_block(user_id: int, recovery_key: str, token: str) -> dict[str, Any]:
    """Set the account's block, or re-call it with the same key AND the same token."""
    _check_key(recovery_key)
    digest = token_hash(token)
    with get_connection() as connection:
        lock_account(connection, user_id)
        return set_block_locked(connection, user_id, recovery_key, digest)


def set_block_locked(connection: Any, user_id: int, recovery_key: str, digest: str) -> dict[str, Any]:
    """The set itself, on a connection that already holds the account lock (the caller owns
    the transaction): P-RB tool step A sets the block in the same transaction as its checks."""
    block = active_block(connection, user_id)
    if block is not None and not block["consistent"]:
        raise _error("recovery_block_inconsistent")
    if block is not None:
        if block["recovery_key"] != recovery_key:
            raise _error("recovery_already_active")
        if not hmac.compare_digest(block["grant_hash"], digest):
            raise _error("recovery_grant_invalid")       # never replaced by a new token
        return {"block_id": int(block["id"]), "created": False, "changes_started": bool(block["changes_started"])}
    if connection.execute("SELECT 1 FROM account_write_blocks WHERE recovery_key = ?",
                          (recovery_key,)).fetchone() is not None:
        raise _error("recovery_key_used")
    watermark = connection.execute("SELECT COALESCE(MAX(id), 0) AS n FROM srs_migration_runs").fetchone()["n"]
    row = connection.execute(
        "INSERT INTO account_write_blocks (user_id, purpose, recovery_key, grant_hash, status, active_user_id, "
        "run_watermark, changes_started, created_at) VALUES (?, ?, ?, ?, 'active', ?, ?, 0, ?) RETURNING id",
        (user_id, PURPOSE, recovery_key, digest, user_id, int(watermark), now_iso()),
    ).fetchone()
    return {"block_id": int(row["id"]), "created": True, "changes_started": False}


def _rollback_runs_since(connection: Any, user_id: int, watermark: int) -> list[dict[str, Any]] | None:
    """This account's rollback runs created after the block was set; None if a scope cannot be read."""
    runs = []
    for row in connection.execute(
            "SELECT id, status, scope_json, summary_json FROM srs_migration_runs WHERE mode = 'rollback' AND id > ? "
            "ORDER BY id", (watermark,)).fetchall():
        try:
            owner = json.loads(row["scope_json"]).get("user_id")
        except (TypeError, ValueError, AttributeError):
            return None
        if owner == user_id:
            runs.append(dict(row))
    return runs


def _between_proof_and_lock() -> None:
    """Test seam only: nothing happens here."""


def release_block(user_id: int, recovery_key: str, token: str, reason: str, *, plan: str | None = None) -> dict[str, Any]:
    """Release only when the database proves the reason (block contract 6, tool contract 14).
    Otherwise 409 and the block stays.

    - `precheck_unrecoverable`: unchanged -- no recovery write ever committed, no rollback run
      since the block, and the record (if any) still `prepared`.
    - `completed`: only for a `verified` recovery of this block, key, token AND plan, whose
      current data still passes the gate A + N + S (contract 15-4) with the stored proof's digest
      D (read in a read-only snapshot, then D and the gate re-confirmed under the account lock).
      The global diagnostic G is returned, never a gate. A stale proof is
      refused (`verification_not_current`: run verify explicitly) -- never refreshed or released
      automatically. The record closes and the block is released in ONE transaction.
    - A re-call of a finished completed release (same key, token and plan) writes nothing.
    `operator_abandoned`, forced or timed release do not exist."""
    _check_key(recovery_key)
    digest = token_hash(token)
    if reason not in RELEASE_REASONS:
        raise _error("release_reason_not_allowed")
    proof = None
    if reason == "completed":
        from app import recovery

        try:
            replay = recovery.completed_release_replay(user_id, recovery_key, digest, plan)
            if replay is not None:
                return replay
            proof = recovery.completed_release_proof(user_id, recovery_key, digest, plan)
        except recovery.RecoveryRefused as refused:
            raise _error(refused.code) from None
        _between_proof_and_lock()
    with get_connection() as connection:
        lock_account(connection, user_id)
        block = active_block(connection, user_id)
        if reason == "completed" and (block is None or block["recovery_key"] != recovery_key):
            # tool contract 14-2: an identical request that waited for the lock finds the finished
            # release in THIS locked transaction and writes nothing
            from app import recovery

            try:
                finished = recovery.finished_release(connection, user_id, recovery_key, digest, plan)
            except recovery.RecoveryRefused as refused:
                raise _error(refused.code) from None
            if finished is not None:
                return finished
        if block is not None and not block["consistent"]:
            raise _error("recovery_block_inconsistent")
        if block is None or block["recovery_key"] != recovery_key or not hmac.compare_digest(block["grant_hash"], digest):
            raise _error("recovery_grant_invalid")
        runs = _rollback_runs_since(connection, user_id, int(block["run_watermark"]))
        # P-RB tool contract 2-1: the account's recovery record closes in this same transaction.
        record = active_recovery_record(connection, user_id)
        if reason == "precheck_unrecoverable":
            # Proof of no change: no recovery write ever committed, and no rollback run of this account since.
            allowed = not block["changes_started"] and runs == []
            # Before any recovery write the record can only be `prepared` for this block.
            if record is not None and not (record["consistent"] and record["block_id"] == block["id"]
                                           and record["recovery_key"] == recovery_key
                                           and record["state"] == "prepared"):
                allowed = False
            state_from = "prepared"
        else:
            from app import recovery

            allowed = recovery.completed_release_confirm(connection, user_id, block, record, proof)
            state_from = "verified"
        if not allowed:
            raise _error("release_not_allowed")
        stamp = now_iso()
        if record is not None:
            cursor = connection.execute(
                "UPDATE account_recovery_runs SET state = 'closed', active_user_id = NULL, closed_at = ?, "
                "close_reason = ? WHERE id = ? AND active_user_id = ? AND state = ?",
                (stamp, reason, record["id"], user_id, state_from),
            )
            if cursor.rowcount != 1:
                raise _error("release_not_allowed")       # raising rolls the whole release back
        cursor = connection.execute(
            "UPDATE account_write_blocks SET status = 'released', active_user_id = NULL, released_at = ?, "
            "release_reason = ? WHERE id = ? AND active_user_id = ?",
            (stamp, reason, block["id"], user_id),
        )
        if cursor.rowcount != 1:
            raise _error("release_not_allowed")
        result = {"block_id": int(block["id"]), "released": True, "reason": reason, "created": True,
                  "recovery_record_closed": record is not None}
        if proof is not None:
            result["diagnostics"] = proof["diagnostics"]      # G (contract 15-4): shown, not a gate
        return result


# Every record of the account that is not cleanly closed, plus any row carrying its marker
# (not the marker alone: a lost marker must not hide an open record).
_RECORD_ROWS = ("SELECT * FROM account_recovery_runs WHERE (user_id = ? AND (state <> 'closed' OR active_user_id "
                "IS NOT NULL)) OR active_user_id = ? ORDER BY id")


def active_recovery_record(connection: Any, user_id: int) -> dict[str, Any] | None:
    """None when the account has no open recovery record; otherwise the record, with
    `consistent` False unless it is exactly one open row whose marker is this account."""
    rows = [dict(r) for r in connection.execute(_RECORD_ROWS, (user_id, user_id)).fetchall()]
    if not rows:
        return None
    record = rows[0]
    record["consistent"] = (len(rows) == 1 and record["state"] != "closed" and record["user_id"] == user_id
                            and record["active_user_id"] == user_id)
    return record

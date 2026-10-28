"""Account existence and serialization on the connection performing the write.

P-RB (P_RB_BLOCK_CONTRACT.md): an account may carry one active write block
(`account_write_blocks`). It is read under the account lock, so setting, checking and
releasing it serialize with every write. While it is active, every ordinary write is
refused with 409 `account_writes_blocked`; only a recovery grant bound to that account,
that block and an allowed action passes (internal recovery functions only -- no HTTP
argument and no general bypass)."""

import hashlib
import hmac
from dataclasses import dataclass, field
from typing import Any

from app.database import is_postgres_connection


class AccountWriteError(ValueError):
    def __init__(self, code: str = "account_not_found", status_code: int = 404):
        super().__init__(code)
        self.code = code
        self.status_code = status_code


# Actions a recovery grant may perform through begin_account_write. Every one of them
# changes recovery data, so it also records `changes_started` in the same transaction.
RECOVERY_ACTIONS = ("rollback",)


@dataclass(frozen=True)
class RecoveryGrant:
    """Built by the (future) operator tool from the block's key and the secret it was set
    with. The secret is never stored (hash only) and never shown (repr)."""

    user_id: int
    recovery_key: str
    action: str
    token: str = field(repr=False)


def token_hash(token: Any) -> str:
    if not isinstance(token, str) or not 32 <= len(token) <= 256 or not token.isascii():
        raise AccountWriteError("recovery_grant_invalid", 409)
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def lock_account(connection: Any, user_id: int) -> None:
    """The account lock and existence check alone (no block check). Internal: used by the
    block set / release functions and by begin_account_write."""
    if type(user_id) is not int or not 0 < user_id <= 2 ** 63 - 1:
        raise AccountWriteError()
    if is_postgres_connection(connection):
        query = "SELECT id FROM users WHERE id = ? FOR UPDATE"
    else:
        connection.execute("BEGIN IMMEDIATE")
        query = "SELECT id FROM users WHERE id = ?"
    if connection.execute(query, (user_id,)).fetchone() is None:
        raise AccountWriteError()


def _blocks_table_present(connection: Any) -> bool:
    """A database whose schema predates P-RB (the SRS schema step not run, e.g. an old file
    before its upgrade) has no block table, so no block can exist in it. Checked through the
    catalog, so a missing table never aborts the caller's (PostgreSQL) transaction."""
    if is_postgres_connection(connection):
        row = connection.execute("SELECT to_regclass('account_write_blocks') IS NOT NULL AS present").fetchone()
        return bool(row["present"])
    row = connection.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'account_write_blocks'").fetchone()
    return row is not None


# Every row of the account that is not cleanly released (status AND marker), plus any row
# carrying the account's marker. Not the marker alone: a row whose marker was lost (an
# earlier, weaker table definition) must still block.
_BLOCK_ROWS = ("SELECT id, user_id, status, active_user_id, recovery_key, grant_hash, changes_started, run_watermark "
               "FROM account_write_blocks WHERE (user_id = ? AND (status <> 'released' OR active_user_id IS NOT NULL)) "
               "OR active_user_id = ? ORDER BY id")


def active_block(connection: Any, user_id: int) -> dict[str, Any] | None:
    """None when the account has no block. Otherwise the block, with `consistent` False when
    the rows are not exactly one active row whose marker is this account (fail closed)."""
    if not _blocks_table_present(connection):
        return None
    rows = [dict(row) for row in connection.execute(_BLOCK_ROWS, (user_id, user_id)).fetchall()]
    if not rows:
        return None
    block = rows[0]
    block["consistent"] = (len(rows) == 1 and block["status"] == "active" and block["user_id"] == user_id
                           and block["active_user_id"] == user_id)
    return block


def grant_matches(block: dict[str, Any], grant: Any, user_id: int) -> bool:
    if not isinstance(grant, RecoveryGrant) or grant.user_id != user_id or block["user_id"] != user_id:
        return False
    if grant.recovery_key != block["recovery_key"]:
        return False
    try:
        digest = token_hash(grant.token)
    except AccountWriteError:
        return False
    return hmac.compare_digest(digest, block["grant_hash"])


def authorize_recovery(connection: Any, user_id: int, recovery: RecoveryGrant) -> dict[str, Any]:
    """The account lock and the grant check, WITHOUT any write: the active block exists, is
    consistent, and the grant matches this account, this block, its token and an allowed
    action. Returns the block. Raises otherwise."""
    lock_account(connection, user_id)
    block = active_block(connection, user_id)
    if block is None:
        raise AccountWriteError("recovery_grant_invalid", 409)       # no active block: no grant
    if not block["consistent"]:
        raise AccountWriteError("recovery_block_inconsistent", 409)
    if recovery.action not in RECOVERY_ACTIONS or not grant_matches(block, recovery, user_id):
        raise AccountWriteError("recovery_grant_invalid", 409)
    return block


def record_recovery_change(connection: Any, user_id: int, block: dict[str, Any]) -> None:
    """The recovery write starts: recorded in the caller's transaction (after
    `authorize_recovery` on the same connection), so it commits or rolls back together with
    the recovery data."""
    connection.execute(
        "UPDATE account_write_blocks SET changes_started = 1, "
        "changes_started_at = COALESCE(changes_started_at, ?) WHERE id = ? AND active_user_id = ?",
        (_now_iso(), block["id"], user_id),
    )


def begin_account_write(connection: Any, user_id: int, *, recovery: RecoveryGrant | None = None) -> None:
    """Start before any reads/writes; the caller owns commit/rollback and close. With a
    recovery grant (the public rollback path): authorize, then record the change at once."""
    if recovery is not None:
        record_recovery_change(connection, user_id, authorize_recovery(connection, user_id, recovery))
        return
    lock_account(connection, user_id)
    block = active_block(connection, user_id)
    if block is None:
        return
    raise AccountWriteError("account_writes_blocked", 409)


def _now_iso() -> str:
    from app.database import now_iso

    return now_iso()

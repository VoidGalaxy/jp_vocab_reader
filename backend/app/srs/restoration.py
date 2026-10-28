"""Gate D-2 U8 fix P1: which card-version jumps inside an evidence window are proven
non-review writes.

A restoring rollback + re-conversion adds two card versions between two FSRS reviews
(rollback +1, re-conversion +1) and changes nothing the reviews depend on. The
evidence check (reviews._evidence_window_consistent) accepts such a jump only when
this function proves every skipped version from this card's own records. Read-only.

Proof for one pair (previous log P with result S and card version c after P was
written; next log N with card_version_before = c + 2k):
for each step from version v = c, c+2, ... until v reaches N's version:
- a rollback record R for this account/kind/card under a rollback run whose status is
  'completed', with card_version_before = v (the card it rolled back was the one P
  left), baseline.card_version = v + 1 and baseline.last_log_id = P.id (no log in
  between), and whose recorded pre-rollback engine state (srs_before_json) is exactly
  S under the current config;
- then a re-conversion snapshot A for the same account/kind/card under an apply run
  that is 'completed' or 'started' (never 'failed'), or 'aborted' only because a
  completed rollback undid that very run; A comes after R, has card_version_before =
  v + 1, its stored card was legacy at version v + 1 with last_log_id = P.id, and the
  values it wrote restore exactly S (same engine state, config, effective due).
Anything else -- a missing or failed record, another card's or account's record, a
state or baseline that differs, an extra version nobody explains -- is not proven.

`restart_permission` (U8 plan B) decides whether a re-converted, state-none card may
start a new evidence window at its first real review; see its docstring.
"""

from __future__ import annotations

import json
from typing import Any

from app.srs.engine import DEFAULT_CONFIG, CardKey, SrsEngineError
from app.srs.storage import SrsWriteError, load_state


def _loads(text: Any) -> Any:
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return None


def _state(values: Any) -> Any:
    """The engine state a stored srs_* dict describes, or a sentinel when unusable."""
    if not isinstance(values, dict) or values.get("srs_engine") != "fsrs" \
            or values.get("srs_config_version") != DEFAULT_CONFIG.config_version:
        return _UNUSABLE
    try:
        return load_state(values)
    except (KeyError, TypeError, ValueError, SrsWriteError, SrsEngineError):
        return _UNUSABLE


_UNUSABLE = object()


def _records(connection: Any, key: CardKey) -> list[dict[str, Any]]:
    return [dict(row) for row in connection.execute(
        "SELECT s.id, s.run_id, s.card_version_before, s.legacy_json, s.srs_before_json, s.srs_after_json, "
        "r.mode, r.status FROM srs_migration_snapshots AS s JOIN srs_migration_runs AS r ON r.id = s.run_id "
        "WHERE s.user_id = ? AND s.card_kind = ? AND s.card_ref = ? ORDER BY s.id",
        (key.user_id, key.kind, key.ref_id),
    ).fetchall()]


def _undone_by_completed_rollback(connection: Any, run_id: int, user_id: int) -> bool:
    for row in connection.execute(
        "SELECT scope_json FROM srs_migration_runs WHERE mode = 'rollback' AND status = 'completed'"
    ).fetchall():
        scope = _loads(row["scope_json"])
        if isinstance(scope, dict) and scope.get("source_run_id") == run_id and scope.get("user_id") == user_id:
            return True
    return False


def proven_jump(connection: Any, key: CardKey, previous_log_id: int, previous_after: Any,
                version_after_previous: int, next_version: int) -> bool:
    """True when every card version from `version_after_previous` up to `next_version`
    (exclusive) is explained by a restoring rollback + re-conversion pair (above)."""
    if next_version <= version_after_previous or (next_version - version_after_previous) % 2:
        return False
    records = _records(connection, key)
    version, last_id = version_after_previous, 0
    while version < next_version:
        rollback = next((r for r in records if r["mode"] == "rollback" and r["id"] > last_id
                         and r["card_version_before"] == version), None)
        if rollback is None or rollback["status"] != "completed":
            return False
        payload, restore = _loads(rollback["legacy_json"]), _loads(rollback["srs_before_json"])
        baseline = payload.get("baseline") if isinstance(payload, dict) else None
        if (not isinstance(baseline, dict) or baseline.get("card_version") != version + 1
                or baseline.get("last_log_id") != previous_log_id or _state(restore) != previous_after):
            return False
        apply = next((r for r in records if r["mode"] == "apply" and r["id"] > rollback["id"]
                      and r["card_version_before"] == version + 1), None)
        if apply is None:
            return False
        if apply["status"] not in ("completed", "started") and not (
                apply["status"] == "aborted" and _undone_by_completed_rollback(connection, apply["run_id"], key.user_id)):
            return False
        stored, values = _loads(apply["legacy_json"]), _loads(apply["srs_after_json"])
        card = stored.get("card") if isinstance(stored, dict) else None
        if (not isinstance(card, dict) or stored.get("last_log_id") != previous_log_id
                or card.get("srs_card_version") != version + 1 or card.get("srs_engine") != "legacy"
                or _state(values) != previous_after
                or values.get("srs_effective_due_at") != restore.get("srs_effective_due_at")):
            return False
        version, last_id = version + 2, apply["id"]
    return version == next_version


def restart_permission(connection: Any, key: CardKey, card: dict[str, Any],
                       logs: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Gate D-2 U8 plan B: may this converted, state-none card's first review replace
    its old evidence boundary? Only under its LATEST re-conversion snapshot A, when:
    A carries `restart.previous_boundary` = the card's current boundary; A's run is an
    apply run that is 'completed' or 'started'; A wrote no engine state; the
    `restart.rollback_record_id` is this card's completed rollback record; the card
    version is A's card_version_before + 1 (nothing written since); the card has no
    log after A; and A was never used. Returns {snapshot_id, previous_boundary}."""
    boundary = card.get("evidence_from_log_id")
    records = _records(connection, key)
    applies = [r for r in records if r["mode"] == "apply"]
    if boundary is None or not applies:
        return None
    latest = applies[-1]
    stored, values = _loads(latest["legacy_json"]), _loads(latest["srs_after_json"])
    restart = stored.get("restart") if isinstance(stored, dict) else None
    if (not isinstance(restart, dict) or restart.get("previous_boundary") != boundary
            or latest["status"] not in ("completed", "started") or not isinstance(values, dict)
            or values.get("srs_engine") != "fsrs" or values.get("srs_state") is not None
            or card.get("srs_card_version") != latest["card_version_before"] + 1):
        return None
    rollback = next((r for r in records if r["id"] == restart.get("rollback_record_id")), None)
    if rollback is None or rollback["mode"] != "rollback" or rollback["status"] != "completed" or rollback["id"] > latest["id"]:
        return None
    last_log_id = stored.get("last_log_id")
    if not isinstance(last_log_id, int) or any(log["id"] > last_log_id for log in logs):
        return None
    if connection.execute("SELECT 1 FROM srs_evidence_restarts WHERE source_snapshot_id = ?",
                          (latest["id"],)).fetchone() is not None:
        return None
    return {"snapshot_id": latest["id"], "previous_boundary": boundary}

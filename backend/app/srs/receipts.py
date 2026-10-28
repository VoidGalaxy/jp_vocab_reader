"""Gate D-2 U9: review receipts -- canonical bytes, 7-day logical expiry, and the
one-time minimization of receipts written before U9 (they copied card content).

- A receipt's response_json is the FSRS review response in canonical JSON (sorted
  keys, fixed separators, UTF-8). The HTTP body is the same text, so a first answer
  and its retry are byte-identical.
- A receipt is valid for less than 7 x 24 hours after its created_at (server
  clock); at or past that it is expired and never replayed. An unreadable or
  future created_at is neither replayed nor treated as expired (the caller
  refuses). Nothing here deletes on read; purge is an explicit operator step.
- `minimize_receipts` strips only card-content fields from pre-U9 personal
  responses (the documented exception to "retry = first response"). Unknown or
  damaged responses are reported, never repaired or deleted.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

from app.srs.goals import read_utc
from app.srs.storage import SrsWriteError

RECEIPT_TTL = timedelta(days=7)

# Pre-U9 personal responses copied the vocab_items row (database.VOCAB_ITEM_FIELDS).
CONTENT_FIELDS = frozenset({
    "deck_name", "surface", "base_form", "reading", "part_of_speech", "normalized_form", "meaning_ko",
    "dictionary_gloss", "quality_tag", "context_explanation_ko", "example_sentence",
})
_META = frozenset({"request_id", "accepted_at", "server_now", "completed", "completion_metric_version", "srs"})
_OLD_PERSONAL = CONTENT_FIELDS | _META | {
    "id", "deck_id", "status", "correct_count", "wrong_count", "last_reviewed_at", "review_level", "next_review_at",
    "created_at", "updated_at"}
_OLD_LEXEME = _META | {
    "lexeme_id", "status", "review_level", "next_review_at", "correct_count", "wrong_count", "last_reviewed_at"}
_CURRENT = _META | {
    "card_kind", "card_id", "rating", "correct_count", "wrong_count", "review_level", "next_review_at",
    "last_reviewed_at"}


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def receipt_age_status(created_at: Any, now: datetime) -> str:
    """'valid' | 'expired' | 'unreadable' (no time zone, unparsable, or in the future)."""
    at = read_utc(created_at)
    if at is None or at > now:
        return "unreadable"
    return "valid" if now - at < RECEIPT_TTL else "expired"


def classify_response(text: Any) -> tuple[str, dict[str, Any] | None]:
    """('current' | 'old_lexeme' | 'old_personal' | 'unreadable' | 'unknown', parsed)."""
    try:
        value = json.loads(text)
    except (TypeError, ValueError):
        return "unreadable", None
    if not isinstance(value, dict) or not isinstance(value.get("srs"), dict) or "request_id" not in value:
        return "unknown", None
    keys = set(value)
    if "card_kind" in keys:
        return ("current", value) if keys <= _CURRENT else ("unknown", None)
    if "lexeme_id" in keys and keys <= _OLD_LEXEME:
        return "old_lexeme", value
    if "id" in keys and keys <= _OLD_PERSONAL:
        return "old_personal", value
    return "unknown", None


def minimize_receipts(connection: Any, user_id: int, now: datetime, *, apply: bool = False,
                      purge_expired: bool = False, batch_size: int = 200, after_id: int = 0,
                      lock: Any = None) -> dict[str, Any]:
    """One account. Report only (ids, field names, counts), never the stored content.
    With `apply`, each batch runs under the account write lock (`lock(connection,
    user_id)`), re-reads each row and updates it only if it still holds the value read
    (CAS on the original text); a row that changed is skipped and reported."""
    report: dict[str, Any] = {"user_id": user_id, "applied": bool(apply), "stripped": [], "already_minimal": 0,
                              "unreadable_json": [], "unknown_format": [], "unreadable_time": [],
                              "expired": [], "purged": [], "changed_concurrently": [], "cursor": after_id}
    cursor = after_id
    while True:
        if apply:
            lock(connection, user_id)
        rows = [dict(r) for r in connection.execute(
            "SELECT id, response_json, created_at FROM srs_review_receipts WHERE user_id = ? AND id > ? "
            "ORDER BY id LIMIT ?", (user_id, cursor, batch_size)).fetchall()]
        if not rows:
            if apply:
                connection.commit()
            break
        for row in rows:
            # U9 fix P2: the format is judged first. A damaged or unknown response is
            # reported and kept as it is, expired or not; only recognised formats are
            # ever purged or minimized.
            kind, value = classify_response(row["response_json"])
            age = receipt_age_status(row["created_at"], now)
            if age == "unreadable":
                report["unreadable_time"].append(row["id"])
            if kind == "unreadable":
                report["unreadable_json"].append(row["id"])
                continue
            if kind == "unknown":
                report["unknown_format"].append(row["id"])
                continue
            if age == "expired":
                report["expired"].append(row["id"])
                if purge_expired and apply:
                    # CAS on the time AND the response read above: a row changed since is kept.
                    deleted = connection.execute(
                        "DELETE FROM srs_review_receipts WHERE id = ? AND user_id = ? AND created_at = ? "
                        "AND response_json = ?", (row["id"], user_id, row["created_at"], row["response_json"])).rowcount
                    (report["purged"] if deleted == 1 else report["changed_concurrently"]).append(row["id"])
                    continue
            if kind in ("current", "old_lexeme") or not (set(value) & CONTENT_FIELDS):
                report["already_minimal"] += 1
            else:
                removed = sorted(set(value) & CONTENT_FIELDS)
                stripped = {k: v for k, v in value.items() if k not in CONTENT_FIELDS}
                if apply:
                    updated = connection.execute(
                        "UPDATE srs_review_receipts SET response_json = ? WHERE id = ? AND user_id = ? AND response_json = ?",
                        (canonical_json(stripped), row["id"], user_id, row["response_json"])).rowcount
                    if updated != 1:
                        report["changed_concurrently"].append(row["id"])
                        continue
                report["stripped"].append({"id": row["id"], "fields": removed})
        cursor = rows[-1]["id"]
        report["cursor"] = cursor
        if apply:
            connection.commit()  # batch + its cursor position are durable together
    return report


def strip_card_receipts(connection: Any, user_id: int, card_ids: list[int]) -> dict[str, list[int]]:
    """Gate D-2 U9, used ONLY inside an explicit delete of these personal cards (the
    caller holds the account write lock, has checked the cards are this account's,
    and owns the transaction that also writes the deletion ledger and deletes the
    cards). For this account's receipts of these personal cards:

    - pre-U9 receipt with content: only the content fields are removed (results,
      hashes, log ids and times stay);
    - current (minimal) receipt or one without content: untouched;
    - damaged JSON or an unknown shape, which cannot be minimized safely: the
      receipt ROW is deleted (approved 2026-10-14 for card deletion only; the
      general tool and --purge-expired keep and report such rows).

    Every change is a compare-and-set on the text read here; a row that differs
    raises, so the caller's whole delete rolls back. Other accounts, other cards and
    subscribed receipts with the same number are never selected. Review logs,
    learning history and completion evidence are not touched."""
    done: dict[str, list[int]] = {"stripped": [], "deleted": []}
    if not card_ids:
        return done
    marks = ", ".join("?" for _ in card_ids)
    rows = [dict(r) for r in connection.execute(
        f"SELECT id, response_json FROM srs_review_receipts WHERE user_id = ? AND card_kind = 'personal' "
        f"AND card_ref IN ({marks}) ORDER BY id", (user_id, *card_ids)).fetchall()]
    for row in rows:
        kind, value = classify_response(row["response_json"])
        if kind in ("unreadable", "unknown"):
            changed = connection.execute(
                "DELETE FROM srs_review_receipts WHERE id = ? AND user_id = ? AND card_kind = 'personal' "
                "AND response_json = ?", (row["id"], user_id, row["response_json"])).rowcount
            bucket = "deleted"
        elif kind == "old_personal" and set(value) & CONTENT_FIELDS:
            changed = connection.execute(
                "UPDATE srs_review_receipts SET response_json = ? WHERE id = ? AND user_id = ? AND response_json = ?",
                (canonical_json({k: v for k, v in value.items() if k not in CONTENT_FIELDS}), row["id"], user_id,
                 row["response_json"])).rowcount
            bucket = "stripped"
        else:
            continue
        if changed != 1:
            # Changed under the lock (should not happen): never continue silently.
            raise SrsWriteError("receipt_content_unverified")
        done[bucket].append(row["id"])
    return done

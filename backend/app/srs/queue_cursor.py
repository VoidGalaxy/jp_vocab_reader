"""Signed, bound cursors for GET /study-queue (Gate C-1 contract 2-6).

A cursor is client-held data and is never trusted:
  token = base64url(payload_json) "." base64url(HMAC-SHA256(key, payload_json))
The key is derived from the server secret for this purpose only. The
signature is checked first (constant-time), then every field again.

Malformed / forged / out-of-range -> CursorInvalid (HTTP 400).
Well-formed but issued for other conditions, another Seoul date, another
account, or older than the chain lifetime -> CursorStale (HTTP 409).
Error messages never contain the secret, the signature or the payload.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import re
from datetime import datetime, timedelta
from typing import Any

from app.settings import get_jwt_secret_key

CURSOR_VERSION = 1
MAX_TOKEN_BYTES = 2048
CHAIN_LIFETIME = timedelta(minutes=15)
KEY_PURPOSE = b"study-queue-cursor/v1"
_B64 = re.compile(r"^[A-Za-z0-9_-]+$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_FIELDS = {
    "v", "uid", "scope", "deck_id", "mode", "status", "config_version", "seoul_date",
    "goal_basis", "server_now0", "iat", "new_allowed0", "new_served", "last_key", "filters_hash",
}


class CursorInvalid(ValueError):
    pass


class CursorStale(ValueError):
    pass


def _key() -> bytes:
    return hmac.new(get_jwt_secret_key().encode("utf-8"), KEY_PURPOSE, hashlib.sha256).digest()


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64decode(text: str) -> bytes:
    if not _B64.fullmatch(text):
        raise CursorInvalid("invalid_cursor")
    try:
        return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
    except (binascii.Error, ValueError):
        raise CursorInvalid("invalid_cursor") from None


def canonical_utc(text: Any) -> datetime | None:
    """The datetime if `text` is a canonical UTC isoformat string, else None."""
    if not isinstance(text, str) or len(text) > 40:
        return None
    try:
        value = datetime.fromisoformat(text)
    except ValueError:
        return None
    if value.tzinfo is None or value.utcoffset() != timedelta(0) or value.isoformat() != text:
        return None
    return value


def encode(payload: dict[str, Any]) -> str:
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    signature = hmac.new(_key(), body, hashlib.sha256).digest()
    token = _b64encode(body) + "." + _b64encode(signature)
    if len(token) > MAX_TOKEN_BYTES:
        raise ValueError("cursor too large")
    return token


def _int(value: Any, low: int, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise CursorInvalid("invalid_cursor")
    return value


def decode(token: str) -> dict[str, Any]:
    """Verifies signature and field shapes. Raises CursorInvalid."""
    if not isinstance(token, str) or not token or len(token.encode("utf-8", "replace")) > MAX_TOKEN_BYTES:
        raise CursorInvalid("invalid_cursor")
    parts = token.split(".")
    if len(parts) != 2:
        raise CursorInvalid("invalid_cursor")
    body, signature = _b64decode(parts[0]), _b64decode(parts[1])
    expected = hmac.new(_key(), body, hashlib.sha256).digest()
    if not hmac.compare_digest(signature, expected):
        raise CursorInvalid("invalid_cursor")
    try:
        payload = json.loads(body.decode("ascii"))
    except (UnicodeDecodeError, ValueError):
        raise CursorInvalid("invalid_cursor") from None
    if not isinstance(payload, dict) or set(payload) != _FIELDS:
        raise CursorInvalid("invalid_cursor")

    _int(payload["v"], CURSOR_VERSION, CURSOR_VERSION)
    _int(payload["uid"], 1, 2**63 - 1)
    if payload["scope"] not in ("all", "personal_deck", "subscribed_deck"):
        raise CursorInvalid("invalid_cursor")
    if payload["deck_id"] is not None:
        _int(payload["deck_id"], 1, 2**31 - 1)
    if not isinstance(payload["filters_hash"], str) or not re.fullmatch(r"[0-9a-f]{32}", payload["filters_hash"]):
        raise CursorInvalid("invalid_cursor")
    if payload["mode"] not in ("today", "new", "practice", "selected"):
        raise CursorInvalid("invalid_cursor")
    status = payload["status"]
    if (not isinstance(status, list) or len(status) > 4 or status != sorted(set(status))
            or any(s not in ("known", "uncertain", "unclassified", "unknown") for s in status)):
        raise CursorInvalid("invalid_cursor")
    if not isinstance(payload["config_version"], str) or not 0 < len(payload["config_version"]) <= 128:
        raise CursorInvalid("invalid_cursor")
    if not isinstance(payload["seoul_date"], str) or not _DATE.fullmatch(payload["seoul_date"]):
        raise CursorInvalid("invalid_cursor")
    basis = payload["goal_basis"]
    if not isinstance(basis, dict) or set(basis) != {
        "account_daily_goal", "settings_version", "plan_daily_new",
        "account_introduced_status", "scope_introduced_status",
    }:
        raise CursorInvalid("invalid_cursor")
    if basis["account_introduced_status"] not in ("exact", "unknown") \
            or basis["scope_introduced_status"] not in ("exact", "unknown", None):
        raise CursorInvalid("invalid_cursor")
    _int(basis["account_daily_goal"], 0, 500)
    _int(basis["settings_version"], 0, 2**63 - 1)
    if basis["plan_daily_new"] is not None:
        _int(basis["plan_daily_new"], 0, 500)
    if canonical_utc(payload["server_now0"]) is None or canonical_utc(payload["iat"]) is None:
        raise CursorInvalid("invalid_cursor")
    allowed = _int(payload["new_allowed0"], 0, 500)
    _int(payload["new_served"], 0, allowed)
    key = payload["last_key"]
    if not isinstance(key, list) or len(key) != 5:
        raise CursorInvalid("invalid_cursor")
    _int(key[0], 0, 2)
    if canonical_utc(key[1]) is None:
        raise CursorInvalid("invalid_cursor")
    _int(key[2], 0, 1)
    _int(key[3], -(2**31), 2**63 - 1)  # seq = shared_deck_words.sort_order for new lexemes
    _int(key[4], 1, 2**63 - 1)
    return payload


def check_binding(payload: dict[str, Any], expected: dict[str, Any], now: datetime) -> None:
    """Raises CursorStale unless the cursor was issued for exactly these
    conditions, on the current Seoul date, within the chain lifetime."""
    for name, value in expected.items():
        if payload[name] != value:
            raise CursorStale("cursor_stale")
    started = canonical_utc(payload["server_now0"])
    issued = canonical_utc(payload["iat"])
    if issued < started or issued > now or started > now:
        raise CursorStale("cursor_stale")
    # Lifetime counts from the first page of the chain, so refreshing iat on
    # every page cannot extend it indefinitely.
    if now - started > CHAIN_LIFETIME:
        raise CursorStale("cursor_stale")

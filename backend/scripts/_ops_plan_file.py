"""Migration plan file, format version 1 (OPS_MIGRATION_CLI_PLAN 2-3). Synthetic scope.

A plan file is a DATA file written by an inquiry and bound to the signed apply approval only
through `artifact_sha256` (the SHA-256 of its exact bytes, contract 3-3-1). It is not part of
the code manifest. The file is read once; parsing, the digest and the conversion back to
product candidates all use those same fixed bytes. Nothing is normalised or re-serialised
before hashing. Parsing never imports the app; `to_candidates` does, and only after the app
environment is fixed (the caller runs it after a passed pre-check). Refusals carry fixed codes
only (no file content, value, absolute path or OS text).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
from dataclasses import dataclass, field
from typing import Any

FORMAT = "jp-vocab-ops/migration-plan"
FORMAT_VERSION = 1
MAX_PLAN_BYTES = 8 * 1024 * 1024
MAX_DEPTH = 4                        # object -> candidates array -> candidate object -> flags array
MAX_CANDIDATES = 2000
MAX_FLAGS = 64
MAX_VALUES_BYTES = 64 * 1024
ID_MAX = 2 ** 63 - 1

TOP_KEYS = frozenset({"format", "format_version", "db_identity", "account_id", "job_key", "config_version",
                      "product_fingerprint", "candidates"})
CANDIDATE_FIELDS = ("kind", "ref_id", "card_fingerprint", "logs_fingerprint", "card_version", "quality", "flags",
                    "values_json", "last_log_id", "reconversion", "restart_json")
KINDS = ("personal", "lexeme")
HISTORY_QUALITIES = frozenset({"complete", "incomplete", "fresh"})
NO_VALUE_QUALITIES = frozenset({"unavailable", "already_fsrs", "identity_unknown", "reconvert_blocked"})
RECONVERSIONS = (None, "restored", "state_none", "state_none_restart")
RESTART_KEYS = frozenset({"previous_boundary", "rollback_record_id"})

_HEX64 = re.compile(r"[0-9a-f]{64}")
_JOB_KEY = re.compile(r"[A-Za-z0-9_.:-]{1,128}")
_TOKEN = re.compile(r"[A-Za-z0-9_.:-]{1,64}")


class OpsPlanFileError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _refuse(code: str) -> OpsPlanFileError:
    return OpsPlanFileError(code)


@dataclass(frozen=True)
class PlanCandidate:
    """One product candidate as written (the account is the file's `account_id`)."""
    kind: str
    ref_id: int
    card_fingerprint: str | None
    logs_fingerprint: str
    card_version: int | None
    quality: str
    flags: tuple[str, ...]
    values_json: str | None
    last_log_id: int
    reconversion: str | None
    restart_json: str | None


@dataclass(frozen=True)
class PlanFile:
    raw: bytes = field(repr=False)                 # the fixed bytes everything below came from
    artifact_sha256: str
    db_identity: str
    account_id: int
    job_key: str
    config_version: str
    product_fingerprint: str
    candidates: tuple[PlanCandidate, ...] = field(repr=False)


# --- pure parsing (no app import) ---------------------------------------------------------------

def _text(value: Any, pattern: re.Pattern) -> bool:
    return type(value) is str and value.isascii() and pattern.fullmatch(value) is not None


def _int(value: Any, minimum: int) -> bool:
    return type(value) is int and minimum <= value <= ID_MAX


def _no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def _reject(_: str) -> Any:
    raise ValueError


def _depth_ok(text: str) -> bool:
    """Nesting depth outside strings, checked before the JSON parser recurses."""
    depth, in_string, escaped = 0, False, False
    for char in text:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char in "[{":
            depth += 1
            if depth > MAX_DEPTH:
                return False
        elif char in "]}":
            depth -= 1
    return True


def _utf8_length(value: Any) -> int:
    """UTF-8 length of a text value; -1 for a non-text or a lone surrogate (never encoded loosely)."""
    if type(value) is not str:
        return -1
    try:
        return len(value.encode("utf-8"))
    except UnicodeEncodeError:
        return -1


def _restart_ok(value: Any) -> bool:
    if type(value) is not str or len(value) > 256:
        return False
    try:
        parsed = json.loads(value, object_pairs_hook=_no_duplicates, parse_float=_reject, parse_constant=_reject)
    except (ValueError, RecursionError):
        return False
    return (isinstance(parsed, dict) and set(parsed) == RESTART_KEYS
            and all(_int(parsed[name], 0) for name in RESTART_KEYS)
            and value == json.dumps(parsed, sort_keys=True, separators=(",", ":")))


def _candidate(raw: Any) -> PlanCandidate:
    if not isinstance(raw, dict) or set(raw) != set(CANDIDATE_FIELDS):
        raise _refuse("plan_file_fields_invalid")
    flags = raw["flags"]
    values = raw["values_json"]
    if not (raw["kind"] in KINDS and type(raw["kind"]) is str and _int(raw["ref_id"], 1)
            and (raw["card_fingerprint"] is None or _text(raw["card_fingerprint"], _HEX64))
            and _text(raw["logs_fingerprint"], _HEX64)
            and (raw["card_version"] is None or _int(raw["card_version"], 0))
            and type(raw["quality"]) is str and raw["quality"] in HISTORY_QUALITIES | NO_VALUE_QUALITIES
            and isinstance(flags, list) and len(flags) <= MAX_FLAGS and all(_text(f, _TOKEN) for f in flags)
            and (values is None or 0 <= _utf8_length(values) <= MAX_VALUES_BYTES)
            and _int(raw["last_log_id"], 0)
            and (raw["reconversion"] is None or (type(raw["reconversion"]) is str
                                                 and raw["reconversion"] in RECONVERSIONS))
            and (raw["restart_json"] is None or _restart_ok(raw["restart_json"]))):
        raise _refuse("plan_file_value_invalid")
    candidate = PlanCandidate(raw["kind"], raw["ref_id"], raw["card_fingerprint"], raw["logs_fingerprint"],
                              raw["card_version"], raw["quality"], tuple(flags), values, raw["last_log_id"],
                              raw["reconversion"], raw["restart_json"])
    _combination(candidate)
    return candidate


def _combination(c: PlanCandidate) -> None:
    missing = c.card_fingerprint is None
    # both NULL or both set; NULL means unavailable, but an unavailable card may keep both
    # (access lost while its progress row stays) -- product `_scope_card`
    ok = missing == (c.card_version is None) and (not missing or c.quality == "unavailable")
    if c.quality in NO_VALUE_QUALITIES:
        ok = ok and c.values_json is None and c.reconversion is None and c.restart_json is None
    if c.reconversion is None:
        ok = ok and c.restart_json is None
    elif c.reconversion == "restored":
        ok = ok and c.values_json is not None
    elif c.reconversion == "state_none":
        ok = ok and c.quality == "incomplete" and c.values_json is not None and c.restart_json is None
    else:                                                          # state_none_restart
        ok = ok and c.quality == "incomplete" and c.values_json is not None and c.restart_json is not None
    if not ok:
        raise _refuse("plan_file_combination_invalid")


def parse_plan_bytes(data: Any) -> PlanFile:
    """Parse fixed bytes. The digest is of these exact bytes; nothing is re-serialised."""
    if type(data) is not bytes or not data:
        raise _refuse("plan_file_format_invalid")
    if len(data) > MAX_PLAN_BYTES:
        raise _refuse("plan_file_too_large")
    if data.startswith(b"\xef\xbb\xbf"):
        raise _refuse("plan_file_format_invalid")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise _refuse("plan_file_format_invalid") from None
    if not _depth_ok(text):
        raise _refuse("plan_file_format_invalid")
    try:
        raw = json.loads(text, object_pairs_hook=_no_duplicates, parse_float=_reject, parse_constant=_reject)
    except (ValueError, RecursionError):
        raise _refuse("plan_file_format_invalid") from None
    if not isinstance(raw, dict) or set(raw) != TOP_KEYS:
        raise _refuse("plan_file_fields_invalid")
    if raw["format"] != FORMAT or type(raw["format"]) is not str:
        raise _refuse("plan_file_fields_invalid")
    if type(raw["format_version"]) is not int or raw["format_version"] != FORMAT_VERSION:
        raise _refuse("plan_file_version_unsupported")
    if not (_text(raw["db_identity"], _HEX64) and _int(raw["account_id"], 1) and _text(raw["job_key"], _JOB_KEY)
            and _text(raw["config_version"], _TOKEN) and _text(raw["product_fingerprint"], _HEX64)):
        raise _refuse("plan_file_value_invalid")
    items = raw["candidates"]
    if not isinstance(items, list) or not 0 < len(items) <= MAX_CANDIDATES:
        raise _refuse("plan_file_candidates_invalid")
    candidates = tuple(_candidate(item) for item in items)
    order = [(c.kind, c.ref_id) for c in candidates]
    if order != sorted(order) or len(set(order)) != len(order):
        raise _refuse("plan_file_candidates_invalid")
    return PlanFile(data, hashlib.sha256(data).hexdigest(), raw["db_identity"], raw["account_id"], raw["job_key"],
                    raw["config_version"], raw["product_fingerprint"], candidates)


def read_plan_file(path: Any) -> PlanFile:
    """Read the file ONCE into fixed bytes; a change on disk afterwards does not reach the result."""
    try:
        with open(path, "rb") as handle:
            data = handle.read(MAX_PLAN_BYTES + 1)
    except (OSError, TypeError, ValueError):
        raise _refuse("plan_file_unreadable") from None
    return parse_plan_bytes(data)


# --- writing --------------------------------------------------------------------------------------

def serialize_plan(*, db_identity: str, account_id: int, job_key: str, config_version: str,
                   product_fingerprint: str, candidates: Any) -> bytes:
    """Bytes of a plan file from product candidates (objects with the MigrationCandidate fields).
    The result is parsed back with the same rules before it is returned."""
    try:
        items = []
        for c in candidates:
            if c.key.user_id != account_id:
                raise _refuse("plan_file_candidates_invalid")
            items.append({"kind": c.key.kind, "ref_id": c.key.ref_id, "card_fingerprint": c.card_fingerprint,
                          "logs_fingerprint": c.logs_fingerprint, "card_version": c.card_version,
                          "quality": c.quality, "flags": list(c.flags), "values_json": c.values_json,
                          "last_log_id": c.last_log_id, "reconversion": c.reconversion,
                          "restart_json": c.restart_json})
        doc = {"format": FORMAT, "format_version": FORMAT_VERSION, "db_identity": db_identity,
               "account_id": account_id, "job_key": job_key, "config_version": config_version,
               "product_fingerprint": product_fingerprint, "candidates": items}
        data = json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                          allow_nan=False).encode("utf-8")
    except OpsPlanFileError:
        raise
    except (AttributeError, TypeError, ValueError):
        raise _refuse("plan_file_value_invalid") from None
    parse_plan_bytes(data)
    return data


def _remove_if_ours(path: str, identity: tuple[int, int] | None) -> None:
    """Remove `path` only when it is the very file this call created; otherwise leave it."""
    if identity is None:
        return
    try:
        stat = os.stat(path, follow_symlinks=False)
        if (stat.st_dev, stat.st_ino) == identity:
            os.remove(path)
    except OSError:
        pass


def write_plan_file(path: Any, data: bytes) -> str:
    """Write NEW file `path` (never an existing one) and return the digest of the bytes read back.
    A failed or partial write is never returned as a plan."""
    parse_plan_bytes(data)
    if type(path) is not str:
        raise _refuse("plan_file_write_failed")
    if os.path.lexists(path):
        raise _refuse("plan_file_exists")
    folder = os.path.dirname(os.path.abspath(path))
    temp = os.path.join(folder, f".plan-{secrets.token_hex(8)}.tmp")
    identity: tuple[int, int] | None = None           # (device, file number) of the temp file THIS call made
    linked = False
    try:
        try:
            handle = open(temp, "xb")                 # an existing file of that name is someone else's
        except OSError:
            raise _refuse("plan_file_write_failed") from None
        try:
            with handle:
                stat = os.fstat(handle.fileno())
                identity = (stat.st_dev, stat.st_ino)
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.link(temp, path)                       # fails if `path` appeared meanwhile: no overwrite
            linked = True
        except FileExistsError:
            raise _refuse("plan_file_exists") from None
        except OSError:
            raise _refuse("plan_file_write_failed") from None
        written = read_plan_file(path)
        if written.raw != data:
            raise _refuse("plan_file_write_failed")
        return written.artifact_sha256
    except BaseException:
        if linked:
            _remove_if_ours(path, identity)          # only while it is still the file this call made
        raise
    finally:
        if identity is not None:
            _remove_if_ours(temp, identity)


# --- product candidates (imports the app; call after the pre-check) -------------------------------

def to_candidates(plan: PlanFile) -> tuple[Any, ...]:
    """Product `MigrationCandidate`s from the fixed bytes' parse. The existing product rules check
    them (`_full_scope`, `_scope` order); no new judgement is made here."""
    if not isinstance(plan, PlanFile) or plan.artifact_sha256 != hashlib.sha256(plan.raw).hexdigest():
        raise _refuse("plan_file_value_invalid")
    fixed = parse_plan_bytes(plan.raw)                # from the fixed bytes, not from the object fields
    import _ops_audit_run as ar
    ar.fix_app_environment()                          # environment before any app import
    from app.srs import migration
    from app.srs.engine import DEFAULT_CONFIG, CardKey
    if fixed.config_version != DEFAULT_CONFIG.config_version:
        raise _refuse("plan_file_config_mismatch")
    candidates = tuple(migration.MigrationCandidate(
        key=CardKey(c.kind, fixed.account_id, c.ref_id), card_fingerprint=c.card_fingerprint,
        logs_fingerprint=c.logs_fingerprint, card_version=c.card_version, quality=c.quality, flags=c.flags,
        values_json=c.values_json, last_log_id=c.last_log_id, reconversion=c.reconversion,
        restart_json=c.restart_json) for c in fixed.candidates)
    try:
        ordered = migration._scope([c.key for c in candidates])
        scope = migration._plan_json(candidates)
        valid = ordered == tuple(c.key for c in candidates) and migration._full_scope(
            json.loads(scope), DEFAULT_CONFIG.config_version)
    except Exception:
        valid = False
    if not valid:
        raise _refuse("plan_file_scope_invalid")
    if hashlib.sha256(scope.encode()).hexdigest() != fixed.product_fingerprint:
        raise _refuse("plan_file_product_mismatch")
    return candidates

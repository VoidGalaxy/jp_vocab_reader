"""Operations tool safety contract, unit 3: manifest format, paths and file integrity
(docs/plans/srs-improvement/gate-e/OPS_TOOL_SAFETY_CONTRACT.md 5-4).

Checks a manifest's bytes and the files it lists under an explicitly given common root.
Files are only read as bytes and hashed: nothing is imported, compiled or executed. A pass
means only that the bytes read at check time match the manifest; it does not mean the files
stay unchanged until they run, that every import dependency is listed, or that the manifest
is a signed, approved artefact (signature verification is not implemented). There is no path
from this result to running anything.

External packages (RECORD), the runtime and import completeness are later units.

Refusals are `OpsManifestRefused(code)` with a fixed code and, once an entry's path passed the
format check, its index and relative path. File contents, expected hashes and absolute paths
are never carried.
"""

from __future__ import annotations

import hashlib
import json
import ntpath
import os
import re
import stat
from dataclasses import dataclass
from typing import Any

FORMAT_VERSION = 1
KIND = "ops_manifest"
MAX_MANIFEST_BYTES = 1024 * 1024
MAX_FILES = 2000
MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_PATH = 240
MAX_COMPONENT = 100
CHUNK = 1024 * 1024
ALLOWED_PREFIXES = (("backend", "scripts"), ("backend", "app"), ("docs", "plans", "srs-improvement", "gate-e"),
                    ("ops",))

_COMPONENT = re.compile(r"[A-Za-z0-9_-]([A-Za-z0-9._-]*[A-Za-z0-9_-])?")
_HEX64 = re.compile(r"[0-9a-f]{64}")
_DEVICE = re.compile(r"(con|prn|aux|nul|com[1-9]|lpt[1-9])(\..*)?", re.IGNORECASE)
_REPARSE = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


class OpsManifestRefused(Exception):
    """`code` is fixed; `index` / `path` are set only for an entry whose path is well formed."""

    def __init__(self, code: str, index: int | None = None, path: str | None = None):
        super().__init__(code)
        self.code = code
        self.index = index
        self.path = path


def _refuse(code: str, index: int | None = None, path: str | None = None) -> OpsManifestRefused:
    return OpsManifestRefused(code, index, path)


@dataclass(frozen=True)
class Entry:
    path: str
    parts: tuple[str, ...]
    size: int
    sha256: str


@dataclass(frozen=True)
class FilesMatched:
    """The listed files' bytes matched at check time. Not an approval: unsigned."""
    manifest_sha256: str
    file_count: int
    total_bytes: int
    signature_verified: bool = False


# --- format ------------------------------------------------------------------------------

def _reject_constant(_: str) -> Any:
    raise ValueError


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def manifest_fingerprint(data: bytes) -> str:
    """SHA-256 of the manifest bytes exactly as given (contract 5-2)."""
    if type(data) is not bytes:
        raise _refuse("manifest_format_invalid")
    return hashlib.sha256(data).hexdigest()


def _check_path(value: Any, index: int) -> tuple[str, ...]:
    if type(value) is not str or not value.isascii() or not 0 < len(value) <= MAX_PATH:
        raise _refuse("manifest_path_invalid", index)
    parts = tuple(value.split("/"))
    for part in parts:
        if (not 0 < len(part) <= MAX_COMPONENT or not _COMPONENT.fullmatch(part) or _DEVICE.fullmatch(part)
                or part == "__pycache__"):
            raise _refuse("manifest_path_invalid", index)
    if parts[-1].lower().endswith((".pyc", ".pyo")):
        raise _refuse("manifest_path_invalid", index)
    if not any(len(parts) > len(prefix) and parts[:len(prefix)] == prefix for prefix in ALLOWED_PREFIXES):
        raise _refuse("manifest_path_not_allowed", index, value)
    if not _file_kind_allowed(parts):
        raise _refuse("manifest_file_type_not_allowed", index, value)
    return parts


def _file_kind_allowed(parts: tuple[str, ...]) -> bool:
    """Contract 5-4 area rules, by name only: this is not a check of what the bytes are."""
    name = parts[-1]
    if parts[:2] in (("backend", "scripts"), ("backend", "app")):
        return name.endswith(".py")
    if parts[:4] == ("docs", "plans", "srs-improvement", "gate-e"):
        return len(parts) == 5 and name.endswith(".md")
    if parts[0] == "ops":
        return len(parts) == 3 and parts[1] == "tls" and name.endswith(".pem")
    return False


def parse_manifest(data: bytes) -> tuple[str, tuple[Entry, ...]]:
    """Format, type and range checks only. Returns (manifest fingerprint, entries)."""
    if type(data) is not bytes or not 0 < len(data) <= MAX_MANIFEST_BYTES or data.startswith(b"\xef\xbb\xbf"):
        raise _refuse("manifest_format_invalid")
    try:
        raw = json.loads(data.decode("utf-8"), object_pairs_hook=_pairs, parse_float=_reject_constant,
                         parse_constant=_reject_constant)
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise _refuse("manifest_format_invalid") from None
    if not isinstance(raw, dict) or set(raw) != {"format_version", "kind", "files"}:
        raise _refuse("manifest_fields_invalid")
    if type(raw["format_version"]) is not int or raw["format_version"] != FORMAT_VERSION:
        raise _refuse("manifest_format_version")
    if raw["kind"] != KIND:
        raise _refuse("manifest_kind_invalid")
    files = raw["files"]
    if not isinstance(files, list) or not 0 < len(files) <= MAX_FILES:
        raise _refuse("manifest_files_invalid")
    entries, seen, folded = [], set(), set()
    for index, item in enumerate(files):
        if not isinstance(item, dict) or set(item) != {"path", "size", "sha256"}:
            raise _refuse("manifest_entry_invalid", index)
        parts = _check_path(item["path"], index)
        path = item["path"]
        size, digest = item["size"], item["sha256"]
        if type(size) is not int or not 0 <= size <= MAX_FILE_BYTES:
            raise _refuse("manifest_size_invalid", index, path)
        if type(digest) is not str or not _HEX64.fullmatch(digest):
            raise _refuse("manifest_hash_invalid", index, path)
        if path in seen:
            raise _refuse("manifest_path_duplicate", index, path)
        if path.casefold() in folded:
            raise _refuse("manifest_path_case_duplicate", index, path)
        seen.add(path)
        folded.add(path.casefold())
        entries.append(Entry(path, parts, size, digest))
    # a file path may not also be a directory prefix of another entry
    for index, entry in enumerate(entries):
        folded_parts = [part.casefold() for part in entry.parts]
        for depth in range(1, len(folded_parts)):
            if "/".join(folded_parts[:depth]) in folded:
                raise _refuse("manifest_path_conflict", index, entry.path)
    return manifest_fingerprint(data), tuple(entries)


# --- filesystem ----------------------------------------------------------------------------

def _is_link_like(info: os.stat_result) -> bool:
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & _REPARSE)


def _check_root(root: Any) -> str:
    if type(root) is not str or not root or "\x00" in root:
        raise _refuse("manifest_root_invalid")
    if root.startswith(("\\\\", "//")) or not os.path.isabs(root) or ntpath.splitdrive(root)[0].startswith(("\\\\", "//")):
        raise _refuse("manifest_root_invalid")
    if os.path.normpath(root) != root:
        raise _refuse("manifest_root_invalid")          # no "..", ".", doubled or trailing separators
    current = os.path.normpath(root)
    chain = []
    while True:
        chain.append(current)
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    for path in chain:
        try:
            info = os.lstat(path)
        except OSError:
            raise _refuse("manifest_root_invalid") from None
        if _is_link_like(info) or not stat.S_ISDIR(info.st_mode):
            raise _refuse("manifest_root_link_or_not_directory")
    return os.path.normpath(root)


def _identity(info: os.stat_result) -> tuple[int, int, int]:
    return info.st_dev, info.st_ino, info.st_size


def _walk(root: str, entry: Entry, index: int) -> tuple[str, os.stat_result]:
    """Resolve the entry without following links, checking every component's on-disk name."""
    current = root
    for depth, part in enumerate(entry.parts):
        try:
            names = {e.name for e in os.scandir(current)}
        except OSError:
            raise _refuse("manifest_file_missing", index, entry.path) from None
        if part not in names:
            if any(name.casefold() == part.casefold() for name in names):
                raise _refuse("manifest_path_case_mismatch", index, entry.path)
            raise _refuse("manifest_file_missing", index, entry.path)
        current = os.path.join(current, part)
        try:
            info = os.lstat(current)
        except OSError:
            raise _refuse("manifest_file_missing", index, entry.path) from None
        if _is_link_like(info):
            raise _refuse("manifest_link_not_allowed", index, entry.path)
        last = depth == len(entry.parts) - 1
        if not last and not stat.S_ISDIR(info.st_mode):
            raise _refuse("manifest_file_missing", index, entry.path)
        if last:
            if not stat.S_ISREG(info.st_mode):
                raise _refuse("manifest_not_regular_file", index, entry.path)
            if info.st_nlink != 1:
                raise _refuse("manifest_hard_link_not_allowed", index, entry.path)
            return current, info
    raise _refuse("manifest_file_missing", index, entry.path)  # unreachable: parts is never empty


def _between_check_and_open() -> None:
    """Test seam only: nothing happens here."""


def _after_read() -> None:
    """Test seam only: nothing happens here."""


def _read_and_hash(path: str, before: os.stat_result, entry: Entry, index: int, *, keep: bool = False) -> bytes | None:
    """Every check below is unchanged; with `keep` the exact bytes that were hashed are returned
    (unit 6-1b: the TLS root copy is made from these, never by reopening the file)."""
    kept: list[bytes] = []
    if before.st_size != entry.size:
        raise _refuse("manifest_size_mismatch", index, entry.path)
    _between_check_and_open()
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOINHERIT", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError:
        raise _refuse("manifest_file_unreadable", index, entry.path) from None
    # The first refusal wins; a close failure is reported only when nothing failed before it.
    # The handle is closed once on every path and never retried (contract 5-4).
    error: OpsManifestRefused | None = None
    digest, total = hashlib.sha256(), 0
    try:
        try:
            opened = os.fstat(fd)
        except OSError:
            raise _refuse("manifest_file_unreadable", index, entry.path) from None
        if not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1 or _identity(opened) != _identity(before):
            raise _refuse("manifest_file_changed", index, entry.path)
        while True:
            try:
                chunk = os.read(fd, CHUNK)
            except OSError:
                raise _refuse("manifest_file_unreadable", index, entry.path) from None
            if not chunk:
                break
            total += len(chunk)
            if total > entry.size:
                raise _refuse("manifest_size_mismatch", index, entry.path)
            digest.update(chunk)
            if keep:
                kept.append(chunk)
        if total != entry.size:
            raise _refuse("manifest_size_mismatch", index, entry.path)
        if digest.hexdigest() != entry.sha256:
            raise _refuse("manifest_hash_mismatch", index, entry.path)
    except OpsManifestRefused as refused:
        error = refused
    finally:
        try:
            os.close(fd)
        except OSError:
            if error is None:
                error = _refuse("manifest_file_close_failed", index, entry.path)
    if error is not None:
        raise error from None
    _after_read()
    try:
        after = os.lstat(path)
    except OSError:
        raise _refuse("manifest_file_changed", index, entry.path) from None
    if _is_link_like(after) or not stat.S_ISREG(after.st_mode) or after.st_nlink != 1 \
            or _identity(after) != _identity(before):
        raise _refuse("manifest_file_changed", index, entry.path)
    return b"".join(kept) if keep else None


def read_verified_entry(data: bytes, root: Any, path: str) -> bytes:
    """Unit 6-1b: run the same root / path / link / identity / size / hash checks on one listed
    entry and return the bytes that were hashed. Nothing else is read."""
    _, entries = parse_manifest(data)
    base = _check_root(root)
    for index, entry in enumerate(entries):
        if entry.path == path:
            walked, before = _walk(base, entry, index)
            return _read_and_hash(walked, before, entry, index, keep=True)
    raise _refuse("manifest_entry_not_listed")


def verify_manifest_signed(data: bytes, signature: bytes, *, mode: str, verifier: Any) -> str:
    """Unit 4 hook: the detached signature over exactly these manifest bytes, in the manifest
    namespace of `mode` (refusals are `_ops_approval.OpsApprovalRefused`), then the format
    check. Returns the manifest fingerprint. File checks stay in `check_manifest_files`."""
    import _ops_approval

    _ops_approval.check_signature(data, signature, mode=mode, subject="manifest", verifier=verifier)
    fingerprint, _ = parse_manifest(data)
    return fingerprint


def check_manifest_files(data: bytes, root: Any) -> FilesMatched:
    """Parse the manifest and compare every listed file under `root`, byte for byte."""
    fingerprint, entries = parse_manifest(data)
    base = _check_root(root)
    total = 0
    for index, entry in enumerate(entries):
        path, before = _walk(base, entry, index)
        _read_and_hash(path, before, entry, index)
        total += entry.size
    return FilesMatched(fingerprint, len(entries), total)

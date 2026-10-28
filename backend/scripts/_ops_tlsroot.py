"""Connection provider unit 6-1b: the verified TLS root certificate copy
(OPS_CONNECTION_PROVIDER_CONTRACT.md 5·5-1절).

The manifest's single `ops/tls/*.pem` entry is re-checked under the deployment root with the
unit 3 rules, and the exact bytes that were hashed are written to a new file in a new
temporary folder for this run. The copy's path is available only while the copy is in use;
leaving the context removes it. This proves only that the copy's bytes equal the checked
manifest entry: not that the manifest is approved or signed, not that the certificate is well
formed or trustworthy, and not that a server will authenticate. Another process under the
same OS account can still change the copy.

Refusals are `OpsTlsRootRefused(code, also)` with fixed codes; no file content, path or OS
error text is carried.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from typing import Any

import _ops_manifest as om

COPY_NAME = "root.pem"
_FLAGS_WRITE = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOINHERIT", 0)
_FLAGS_READ = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOINHERIT", 0)


class OpsTlsRootRefused(Exception):
    """`code` is the leading fixed code; `also` holds other fixed codes (contract 5-1 priority)."""

    def __init__(self, code: str, also: tuple[str, ...] = ()):
        super().__init__(code)
        self.code = code
        self.also = also


def select_tls_root(manifest: bytes) -> str:
    """The relative path of the manifest's only `ops/tls/*.pem` entry."""
    try:
        _, entries = om.parse_manifest(manifest)
    except om.OpsManifestRefused as error:
        raise OpsTlsRootRefused(error.code) from None
    roots = [entry.path for entry in entries if entry.parts[:2] == ("ops", "tls")]
    if len(roots) != 1:
        raise OpsTlsRootRefused("tls_root_not_bound")
    return roots[0]


def _write_all(fd: int, data: bytes) -> None:
    """Partial writes continue with the rest; a write that makes no progress stops at once."""
    view = memoryview(data)
    while view:
        try:
            written = os.write(fd, view)
        except OSError:
            raise OpsTlsRootRefused("tls_copy_write_failed") from None
        if type(written) is not int or written <= 0 or written > len(view):
            raise OpsTlsRootRefused("tls_copy_write_stalled")
        view = view[written:]


def _read_back(path: str, expected: bytes) -> None:
    try:
        fd = os.open(path, _FLAGS_READ)
    except OSError:
        raise OpsTlsRootRefused("tls_copy_reread_failed") from None
    error: OpsTlsRootRefused | None = None
    data = b""
    try:
        try:
            while len(data) <= len(expected):
                chunk = os.read(fd, 65536)
                if not chunk:
                    break
                data += chunk
        except OSError:
            error = OpsTlsRootRefused("tls_copy_reread_failed")
    finally:
        try:
            os.close(fd)
        except OSError:
            if error is None:
                error = OpsTlsRootRefused("tls_copy_close_failed")
    if error is not None:
        raise error
    if hashlib.sha256(data).digest() != hashlib.sha256(expected).digest():
        raise OpsTlsRootRefused("tls_copy_mismatch")


class VerifiedRootCopy:
    """`with VerifiedRootCopy(manifest, root) as copy: use copy.path` — one use only."""

    def __init__(self, manifest: bytes, deploy_root: Any):
        self._manifest = manifest
        self._root = deploy_root
        self._state = "new"                  # new -> open -> closed | cleanup_failed
        self._folder: str | None = None
        self._file: str | None = None
        self._guard: int | None = None
        self._guard_unconfirmed = False
        self.sha256: str | None = None

    def __repr__(self) -> str:
        return f"VerifiedRootCopy(state={self._state})"

    @property
    def path(self) -> str:
        if self._state != "open" or self._file is None:
            raise OpsTlsRootRefused("tls_copy_closed")
        return self._file

    def __enter__(self) -> "VerifiedRootCopy":
        if self._state != "new":
            raise OpsTlsRootRefused("tls_copy_already_used")
        self._state = "opening"
        try:
            relative = select_tls_root(self._manifest)
            try:
                data = om.read_verified_entry(self._manifest, self._root, relative)
            except om.OpsManifestRefused as error:
                raise OpsTlsRootRefused(error.code) from None
            try:
                self._folder = tempfile.mkdtemp(prefix="ops_tls_")
            except OSError:
                raise OpsTlsRootRefused("tls_copy_tempdir_failed") from None
            self._file = os.path.join(self._folder, COPY_NAME)
            try:
                fd = os.open(self._file, _FLAGS_WRITE, 0o600)
            except OSError:
                raise OpsTlsRootRefused("tls_copy_write_failed") from None
            error: OpsTlsRootRefused | None = None
            try:
                _write_all(fd, data)
            except OpsTlsRootRefused as refused:
                error = refused
            finally:
                try:
                    os.close(fd)
                except OSError:
                    if error is None:
                        error = OpsTlsRootRefused("tls_copy_close_failed")
            if error is not None:
                raise error
            _read_back(self._file, data)
            try:
                self._guard = os.open(self._file, _FLAGS_READ)   # held while in use (contract 5-1)
            except OSError:
                raise OpsTlsRootRefused("tls_copy_reread_failed") from None
            self.sha256 = hashlib.sha256(data).hexdigest()
        except OpsTlsRootRefused as refused:
            failures = self._cleanup()
            self._state = "cleanup_failed" if failures else "closed"
            if failures:
                raise OpsTlsRootRefused("tls_copy_cleanup_unconfirmed", (refused.code,) + tuple(failures)) from None
            raise OpsTlsRootRefused(refused.code, refused.also) from None
        self._state = "open"
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def close(self) -> None:
        """Idempotent after a clean close. After a failed cleanup each call retries only the file and
        folder removal; the guard handle is never closed twice, and an unconfirmed guard close
        keeps every later call refused (contract 5-1)."""
        if self._state in ("new", "closed"):
            self._state = "closed"
            return
        failures = self._cleanup()
        if failures:
            self._state = "cleanup_failed"
            raise OpsTlsRootRefused("tls_copy_cleanup_unconfirmed", tuple(failures))
        self._state = "closed"

    def _cleanup(self) -> list[str]:
        """One attempt each: release the guard handle, remove the file, remove the folder."""
        failures: list[str] = []
        if self._guard is not None:
            # P1: the number is given up before the one close attempt; it is never closed again,
            # because after a failed close the same number may belong to another file.
            fd, self._guard = self._guard, None
            try:
                os.close(fd)
            except OSError:
                self._guard_unconfirmed = True
        if self._guard_unconfirmed:
            failures.append("tls_copy_guard_close_unconfirmed")    # never turned into success here
        if self._file is not None and os.path.lexists(self._file):
            try:
                os.remove(self._file)
            except OSError:
                failures.append("tls_copy_remove_failed")
        if self._folder is not None and os.path.lexists(self._folder):
            try:
                os.rmdir(self._folder)
            except OSError:
                failures.append("tls_copy_folder_remove_failed")
        if not failures:
            self._file = self._folder = None
        return failures

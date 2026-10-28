"""Operations tool safety contract, unit 4: detached signature verification with the OS
OpenSSH `ssh-keygen -Y verify` (OPS_TOOL_SAFETY_CONTRACT.md 4-2-1, OPS_SIGNATURE_DESIGN.md).

Synthetic scope only. The executable is a fixed path (no PATH lookup, no shell). The message
goes in on standard input as the bytes the caller fixed at start; the signature, allowed
signers and revocation list are bytes the caller fixed too, written to a fresh private
temporary folder for each run and removed afterwards. Exit code 0 is the only success; every
other outcome is `OpsSignatureRefused(code)` with a fixed code. The tool's output is
discarded and never carried.

This module never signs, never creates keys or approval files, and has no production trust
root: `SyntheticOpenSSHVerifier` (the unit 1 `SignatureVerifier`) accepts only synthetic
namespaces, and `_ops_approval.production_verifier()` keeps refusing. `verify_detached` can be
called with any of these namespaces so tests can show the cryptographic separation; that
does not open production mode.
"""

from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
import tempfile
import time
from datetime import datetime, timedelta

SSH_KEYGEN = r"C:\WINDOWS\System32\OpenSSH\ssh-keygen.exe"
TIMEOUT_SECONDS = 10                      # user-approved synthetic setting (2026-10-21)
CLEANUP_SECONDS = 5                       # one shared stop + reap budget (contract 4-2-1)
CHILD_ENV = {"SystemRoot": r"C:\WINDOWS", "PROGRAMDATA": r"C:\ProgramData"}
NAMESPACES = {(mode, subject): f"jp-vocab-ops/v1/{mode}/{subject}"
              for mode in ("ops", "synthetic") for subject in ("approval", "manifest", "backup")}
MAX_MESSAGE = 2 * 1024 * 1024
MAX_SMALL = 64 * 1024
_PRINCIPAL = re.compile(r"[A-Za-z0-9._@-]{1,64}")
_REPARSE = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class OpsSignatureRefused(Exception):
    """`code` is fixed; no tool output, path or input value is carried."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _refuse(code: str) -> OpsSignatureRefused:
    return OpsSignatureRefused(code)


def _bytes(value: object, limit: int, *, allow_empty: bool = False) -> bool:
    return type(value) is bytes and (allow_empty or len(value) > 0) and len(value) <= limit


def _verify_time(value: object) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise _refuse("signature_time_invalid")
    return value.strftime("%Y%m%d%H%M%SZ")


def _check_executable() -> None:
    try:
        info = os.lstat(SSH_KEYGEN)
    except OSError:
        raise _refuse("signature_verifier_unavailable") from None
    if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode) \
            or getattr(info, "st_file_attributes", 0) & _REPARSE:
        raise _refuse("signature_verifier_unavailable")


def _write_private(folder: str, name: str, data: bytes) -> str:
    path = os.path.join(folder, name)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
                 | getattr(os, "O_NOINHERIT", 0), 0o600)
    try:
        view = memoryview(data)
        while view:
            written = os.write(fd, view)
            view = view[written:]
    finally:
        os.close(fd)
    return path


def verify_detached(*, namespace: str, message: bytes, signature: bytes, allowed_signers: bytes,
                    revoked_keys: bytes, principal: str, verify_time: datetime) -> None:
    """Return None when `ssh-keygen -Y verify` exits 0 for these fixed bytes; refuse otherwise."""
    if type(namespace) is not str or namespace not in NAMESPACES.values():
        raise _refuse("signature_namespace_invalid")
    if not _bytes(message, MAX_MESSAGE, allow_empty=True):
        raise _refuse("signature_input_invalid")
    if not _bytes(signature, MAX_SMALL) or not _bytes(allowed_signers, MAX_SMALL) \
            or not _bytes(revoked_keys, MAX_SMALL, allow_empty=True):
        raise _refuse("signature_input_invalid")
    if type(principal) is not str or not principal.isascii() or not _PRINCIPAL.fullmatch(principal):
        raise _refuse("signature_input_invalid")
    when = _verify_time(verify_time)
    _check_executable()
    try:
        folder = tempfile.mkdtemp(prefix="ops_sig_")
    except OSError:
        raise _refuse("signature_tempfile_failed") from None
    outcome: OpsSignatureRefused | None = None
    child_confirmed = True                # False only when a started child could not be reaped
    try:
        try:
            sig = _write_private(folder, "message.sig", signature)
            allowed = _write_private(folder, "allowed_signers", allowed_signers)
            revoked = _write_private(folder, "revoked_keys", revoked_keys)
        except OSError:
            raise _refuse("signature_tempfile_failed") from None
        args = [SSH_KEYGEN, "-Y", "verify", "-f", allowed, "-I", principal, "-n", namespace, "-s", sig,
                "-r", revoked, "-O", f"verify-time={when}"]
        try:
            process = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                       stderr=subprocess.DEVNULL, shell=False, env=dict(CHILD_ENV), cwd=folder,
                                       creationflags=_NO_WINDOW)
        except OSError:
            raise _refuse("signature_verifier_unavailable") from None
        try:
            process.communicate(input=message, timeout=TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            child_confirmed = _stop_child(process)
            raise _refuse("signature_verifier_timeout") from None
        except OSError:
            child_confirmed = _stop_child(process)
            raise _refuse("signature_verifier_unavailable") from None
        if process.returncode != 0:
            raise _refuse("signature_invalid")
    except OpsSignatureRefused as refused:
        outcome = refused
    finally:
        # Deletion is attempted on every path; it is judged separately from the child's exit.
        try:
            shutil.rmtree(folder)
        except OSError:
            if outcome is None:
                outcome = _refuse("signature_tempfile_cleanup_failed")
    if not child_confirmed:
        outcome = _refuse("signature_verifier_child_unconfirmed")   # priority 1 (contract 4-2-1)
    if outcome is not None:
        raise outcome from None


def _stop_child(process: subprocess.Popen) -> bool:
    """Stop and reap only this verifier's own child within one shared budget. True only when
    the reap returned (the child's exit is confirmed); each step is tried once."""
    deadline = time.monotonic() + CLEANUP_SECONDS
    try:
        process.kill()
    except OSError:
        pass                         # it may already have exited: the reap below decides
    remaining = max(0.0, deadline - time.monotonic())
    try:
        process.wait(timeout=remaining)
    except (subprocess.TimeoutExpired, OSError):
        return False
    return True


class SyntheticOpenSSHVerifier:
    """The unit 1 `SignatureVerifier` over a synthetic trust set (bytes fixed by the caller).
    Production namespaces are refused without running anything."""

    def __init__(self, *, allowed_signers: bytes, revoked_keys: bytes, principal: str, verify_time: datetime):
        self._allowed = allowed_signers
        self._revoked = revoked_keys
        self._principal = principal
        self._time = verify_time

    def __repr__(self) -> str:
        return "SyntheticOpenSSHVerifier()"

    def verify(self, *, namespace: str, message: bytes, signature: bytes) -> bool:
        if namespace not in (NAMESPACES[("synthetic", "approval")], NAMESPACES[("synthetic", "manifest")],
                             NAMESPACES[("synthetic", "backup")]):
            raise _refuse("signature_scope_not_synthetic")
        verify_detached(namespace=namespace, message=message, signature=signature,
                        allowed_signers=self._allowed, revoked_keys=self._revoked, principal=self._principal,
                        verify_time=self._time)
        return True

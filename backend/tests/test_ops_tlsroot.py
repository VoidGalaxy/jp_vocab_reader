"""Connection provider unit 6-1b (scripts/_ops_tlsroot.py): the verified TLS root copy.

Real filesystem checks use synthetic PEM-looking bytes in a temporary root this test creates
and removes (no real CA or server certificate). Write / read / close / remove failures are
MOCKED and kept in their own class. Objects the OS will not let this account create are
skipped with the reason. One representative test runs the real unit 5 pre-check (test-only
signing keys) on the same manifest first; no connection is made anywhere.

Run directly:      python tests/test_ops_tlsroot.py
Or via discovery:   python -m unittest discover -s tests
"""

from __future__ import annotations

import glob
import hashlib
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

TESTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS_DIR.parent / "scripts"))
sys.path.insert(0, str(TESTS_DIR))

import _ops_manifest as om  # noqa: E402
import _ops_tlsroot as tr  # noqa: E402
import test_ops_manifest as tm  # noqa: E402  (module only: its tests are not re-run here)

SECRET = "Synth3tic-TLS-Root-Secret-2c9a"
PEM = f"-----BEGIN CERTIFICATE-----\nsynthetic {SECRET}\n-----END CERTIFICATE-----\n".encode()
CODE = b"print('never executed')\n"
REL = "ops/tls/root.pem"


def copy_dirs() -> set[str]:
    return set(glob.glob(os.path.join(tempfile.gettempdir(), "ops_tls_*")))


class Base(tm.Base):
    def setUp(self):
        super().setUp()
        self.before_copies = copy_dirs()
        self.addCleanup(self.assert_no_copy_left)

    def assert_no_copy_left(self):
        self.assertEqual(copy_dirs() - self.before_copies, set())

    def build_default(self, extra=None) -> bytes:
        files = {"backend/scripts/_ops_tool.py": CODE, REL: PEM}
        files.update(extra or {})
        return self.build(files)

    def tls_refused(self, code, data, root=None, *, also=None):
        copy = tr.VerifiedRootCopy(data, self.root if root is None else root)
        with self.assertRaises(tr.OpsTlsRootRefused) as caught:
            with copy:
                self.fail("must not be entered")
        error = caught.exception
        self.assertEqual(error.code, code)
        if also is not None:
            self.assertEqual(error.also, also)
        text = repr(error) + str(error) + repr(error.also) + repr(copy)
        self.assertNotIn(SECRET, text)
        self.assertNotIn(self.root, text)
        self.assertTrue(error.__suppress_context__ or error.__context__ is None)
        with self.assertRaises(tr.OpsTlsRootRefused):
            copy.path
        return error


class RealFiles(Base):
    """Real files in the test's temporary root."""

    def test_copy_is_exactly_the_checked_bytes_and_lives_only_while_used(self):
        data = self.build_default()
        copy = tr.VerifiedRootCopy(data, self.root)
        with copy:
            path = copy.path
            self.assertEqual(Path(path).read_bytes(), PEM)
            self.assertEqual(copy.sha256, hashlib.sha256(PEM).hexdigest())
            self.assertNotEqual(os.path.dirname(path), os.path.join(self.root, "ops", "tls"))
            self.assertNotIn(SECRET, repr(copy))
        self.assertFalse(os.path.lexists(path))
        self.assertFalse(os.path.lexists(os.path.dirname(path)))
        with self.assertRaises(tr.OpsTlsRootRefused) as caught:
            copy.path
        self.assertEqual(caught.exception.code, "tls_copy_closed")
        copy.close()                                            # double close: nothing to do
        with self.assertRaises(tr.OpsTlsRootRefused) as caught:
            copy.__enter__()
        self.assertEqual(caught.exception.code, "tls_copy_already_used")

    def test_original_missing_size_hash(self):
        data = self.build_default()
        os.remove(os.path.join(self.root, "ops", "tls", "root.pem"))
        self.tls_refused("manifest_file_missing", data)
        self.write(REL, PEM + b"x")
        self.tls_refused("manifest_size_mismatch", data)
        self.write(REL, PEM.replace(b"synthetic", b"Synthetic"))
        self.tls_refused("manifest_hash_mismatch", data)

    def test_zero_or_several_roots(self):
        self.tls_refused("tls_root_not_bound", self.build({"backend/scripts/_ops_tool.py": CODE}))
        self.tls_refused("tls_root_not_bound", self.build({REL: PEM, "ops/tls/second.pem": PEM}))

    def test_links_and_swaps(self):
        data = self.build_default()
        os.link(os.path.join(self.root, "ops", "tls", "root.pem"), os.path.join(self.root, "ops", "tls", "extra.bin"))
        self.tls_refused("manifest_hard_link_not_allowed", data)
        os.remove(os.path.join(self.root, "ops", "tls", "extra.bin"))
        outside = os.path.normpath(tempfile.mkdtemp(prefix="ops_manifest_outside_"))
        self.addCleanup(tm.shutil.rmtree, outside)
        self.write("root.pem", PEM, root=outside)
        os.replace(os.path.join(self.root, "ops", "tls"), os.path.join(self.root, "ops", "tls_old"))
        self.junction(outside, os.path.join(self.root, "ops", "tls"))
        self.tls_refused("manifest_link_not_allowed", data)

    def test_swap_between_check_and_open(self):
        data = self.build_default()
        swap = self.write("ops/tls/swap.tmp", PEM.replace(b"synthetic", b"Synthetic"))

        def replace_file():
            os.replace(swap, os.path.join(self.root, "ops", "tls", "root.pem"))

        with mock.patch.object(om, "_between_check_and_open", replace_file):
            self.tls_refused("manifest_file_changed", data)

    def test_copy_keeps_the_verified_bytes_when_the_original_changes(self):
        data = self.build_default()
        original = os.path.join(self.root, "ops", "tls", "root.pem")

        def rewrite_in_place():                       # after the hash, same file, other bytes
            with open(original, "r+b") as handle:
                handle.write(b"XXXXX")

        with mock.patch.object(om, "_after_read", rewrite_in_place):
            with tr.VerifiedRootCopy(data, self.root) as copy:
                self.assertEqual(Path(copy.path).read_bytes(), PEM)
                self.assertNotEqual(Path(original).read_bytes(), PEM)
        self.write(REL, PEM)
        with tr.VerifiedRootCopy(data, self.root) as copy:
            self.write(REL, PEM.replace(b"synthetic", b"Synthetic"))
            self.assertEqual(Path(copy.path).read_bytes(), PEM)

    def test_copy_cannot_be_deleted_while_in_use(self):
        if os.name != "nt":
            self.skipTest("the held-handle delete block is a Windows sharing rule")
        with tr.VerifiedRootCopy(self.build_default(), self.root) as copy:
            with self.assertRaises(PermissionError):
                os.remove(copy.path)
            self.assertTrue(os.path.exists(copy.path))

    def test_symbolic_link(self):
        self.build_default()
        try:
            os.symlink(os.path.join(self.root, "ops", "tls", "root.pem"), os.path.join(self.root, "ops", "tls", "s.pem"))
        except OSError as error:
            self.skipTest(f"symbolic link not creatable by this account (OSError {error.errno})")
        data = tm.manifest([tm.entry("ops/tls/s.pem", PEM)])
        self.tls_refused("manifest_link_not_allowed", data)


class Mocked(Base):
    """MOCKED OS failures around a real temporary root (scripted, not real I/O faults)."""

    def test_partial_writes_complete(self):
        real_write = os.write

        def short_write(fd, data):
            return real_write(fd, bytes(data[:3]))

        with mock.patch.object(tr.os, "write", short_write):
            with tr.VerifiedRootCopy(self.build_default(), self.root) as copy:
                self.assertEqual(Path(copy.path).read_bytes(), PEM)

    def test_zero_write_and_write_error(self):
        data = self.build_default()
        with mock.patch.object(tr.os, "write", lambda fd, view: 0):
            self.tls_refused("tls_copy_write_stalled", data)
        with mock.patch.object(tr.os, "write", mock.Mock(side_effect=OSError(28, SECRET))):
            self.tls_refused("tls_copy_write_failed", data)

    def test_written_bytes_differ(self):
        real_write = os.write

        def corrupting_write(fd, view):
            data = bytearray(view)
            data[0] ^= 0x01
            return real_write(fd, bytes(data))

        with mock.patch.object(tr.os, "write", corrupting_write):
            self.tls_refused("tls_copy_mismatch", self.build_default())

    def test_read_error_while_verifying(self):
        data = self.build_default()
        with mock.patch.object(om.os, "read", mock.Mock(side_effect=OSError(5, SECRET))):
            self.tls_refused("manifest_file_unreadable", data)

    def test_copy_close_error(self):
        data = self.build_default()
        real_close = os.close
        calls = {"n": 0}

        def close_failing_once(fd):
            calls["n"] += 1
            real_close(fd)
            if calls["n"] == 2:            # 1: the original during verification, 2: the written copy
                raise OSError(5, SECRET)

        with mock.patch.object(tr.os, "close", close_failing_once):
            self.tls_refused("tls_copy_close_failed", data)

    def test_tempdir_failure(self):
        with mock.patch.object(tr.tempfile, "mkdtemp", mock.Mock(side_effect=OSError(28, SECRET))):
            self.tls_refused("tls_copy_tempdir_failed", self.build_default())

    def test_cleanup_failure_on_exit_and_explicit_retry(self):
        data = self.build_default()
        copy = tr.VerifiedRootCopy(data, self.root)
        copy.__enter__()
        path = copy.path
        with mock.patch.object(tr.os, "remove", mock.Mock(side_effect=OSError(13, SECRET))):
            with self.assertRaises(tr.OpsTlsRootRefused) as caught:
                copy.__exit__(None, None, None)
        self.assertEqual((caught.exception.code, caught.exception.also),
                         ("tls_copy_cleanup_unconfirmed", ("tls_copy_remove_failed", "tls_copy_folder_remove_failed")))
        self.assertNotIn(SECRET, repr(caught.exception))
        self.assertTrue(os.path.exists(path))                   # never reported as cleaned up
        with self.assertRaises(tr.OpsTlsRootRefused):
            copy.path
        copy.close()                                            # explicit retry, one attempt
        self.assertFalse(os.path.lexists(os.path.dirname(path)))

    def test_failure_during_creation_with_cleanup_failure(self):
        data = self.build_default()
        with mock.patch.object(tr.os, "write", lambda fd, view: 0), \
                mock.patch.object(tr.os, "remove", mock.Mock(side_effect=OSError(13, SECRET))):
            error = self.tls_refused("tls_copy_cleanup_unconfirmed", data,
                                     also=("tls_copy_write_stalled", "tls_copy_remove_failed",
                                           "tls_copy_folder_remove_failed"))
        for folder in copy_dirs() - self.before_copies:   # the test removes what the injected failure left
            tm.shutil.rmtree(folder)
        self.assertIsNotNone(error)

    def test_module_never_imports_or_runs_and_never_reopens_the_original(self):
        source = (TESTS_DIR.parent / "scripts" / "_ops_tlsroot.py").read_text(encoding="utf-8")
        for forbidden in ("import_module", "__import__", "exec(", "eval(", "subprocess", "psycopg", "environ",
                          "shutil.copy", "open(self._root", "open(relative"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


class GuardHandleNumbers(Base):
    """P1 review fix: a guard handle whose close was attempted is never closed again, even when its
    number is reused. The close failures are MOCKED (the first test really closes the handle
    first); the reused number and the other file are real."""

    def other_file(self) -> str:
        path = os.path.join(self.root, "backend", "scripts", "other_synthetic.txt")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as handle:
            handle.write(b"other synthetic file\n")
        return path

    def test_closed_then_error_then_reused_number_is_left_alone(self):
        copy = tr.VerifiedRootCopy(self.build_default(), self.root)
        copy.__enter__()
        guard = copy._guard                        # test-only look at the private number
        real_close = os.close

        def close_then_fail(fd):
            real_close(fd)
            if fd == guard:
                raise OSError(9, SECRET)

        with mock.patch.object(tr.os, "close", close_then_fail):
            with self.assertRaises(tr.OpsTlsRootRefused) as caught:
                copy.close()
        self.assertEqual(caught.exception.code, "tls_copy_cleanup_unconfirmed")
        first_also = caught.exception.also
        other = os.open(self.other_file(), os.O_RDONLY | getattr(os, "O_BINARY", 0))
        try:
            if other != guard:
                self.skipTest("the C runtime did not reuse the number in this run")
            with self.assertRaises(tr.OpsTlsRootRefused) as caught:
                copy.close()                       # retry: file/folder only, never the old number
            self.assertEqual(caught.exception.code, "tls_copy_cleanup_unconfirmed")
            self.assertEqual(os.read(other, 5), b"other")   # the other file is still open and usable
        finally:
            try:
                os.close(other)
            except OSError:
                pass                               # before the fix the copy had already closed it
        self.assertNotIn(SECRET, repr(caught.exception))
        self.assertIn("tls_copy_guard_close_unconfirmed", first_also)

    def test_error_before_real_close_is_not_retried(self):
        copy = tr.VerifiedRootCopy(self.build_default(), self.root)
        copy.__enter__()
        guard, path = copy._guard, copy.path
        calls = []
        real_close = os.close

        def fail_for_guard(fd):
            if fd == guard:
                calls.append(fd)
                raise OSError(5, SECRET)           # not closed: the real handle stays open
            real_close(fd)

        with mock.patch.object(tr.os, "close", fail_for_guard):
            for _ in range(3):
                with self.assertRaises(tr.OpsTlsRootRefused) as caught:
                    copy.close()
                self.assertEqual(caught.exception.code, "tls_copy_cleanup_unconfirmed")
        self.assertEqual(calls, [guard])          # attempted once, never again
        # the test harness owns this handle: confirm it is the copy's file, then release it
        self.assertEqual(os.fstat(guard).st_ino, os.stat(path).st_ino)
        os.close(guard)
        with self.assertRaises(tr.OpsTlsRootRefused) as caught:
            copy.close()                          # files can now be removed, the close stays unconfirmed
        self.assertEqual(caught.exception.also, ("tls_copy_guard_close_unconfirmed",))
        self.assertFalse(os.path.lexists(os.path.dirname(path)))
        with self.assertRaises(tr.OpsTlsRootRefused):
            copy.path

    def test_remove_retry_does_not_close_again(self):
        copy = tr.VerifiedRootCopy(self.build_default(), self.root)
        copy.__enter__()
        guard, path = copy._guard, copy.path
        real_close = os.close
        closes = []

        def counting_close(fd):
            if fd == guard:
                closes.append(fd)
            real_close(fd)

        with mock.patch.object(tr.os, "close", counting_close):
            with mock.patch.object(tr.os, "remove", mock.Mock(side_effect=OSError(13, SECRET))):
                with self.assertRaises(tr.OpsTlsRootRefused):
                    copy.close()
            copy.close()                          # removal retried, no second close of the guard
            copy.close()                          # clean double close
        self.assertEqual(closes, [guard])
        self.assertFalse(os.path.lexists(os.path.dirname(path)))


class WithPrecheck(Base):
    """Representative: real unit 5 pre-check first (test-only keys), then the copy. No connection."""

    def test_precheck_then_copy_of_the_same_manifest(self):
        import test_ops_preflight as pf  # noqa: PLC0415  (needs ssh-keygen; module only)

        if not os.path.isfile(pf.op.osig.SSH_KEYGEN):
            self.skipTest("OS OpenSSH ssh-keygen not present")
        keys = pf.sigtests.Keys()
        self.addCleanup(keys.close)
        checker = pf.Base("run")
        checker.keys, checker.allowed = keys, keys.allowed(namespaces="jp-vocab-ops/v1/synthetic/*")
        checker.root, checker.manifest = self.root, None
        checker.write_files = lambda files: None
        files = dict(pf.FILES)
        for rel, data in files.items():
            self.write(rel, data)
        checker.manifest = pf.manifest_doc(files)
        result = pf.op.run_synthetic_preflight(checker.inputs())
        with tr.VerifiedRootCopy(checker.manifest, self.root) as copy:
            self.assertEqual(Path(copy.path).read_bytes(), files["ops/tls/root.pem"])
            self.assertEqual(result.sslrootcert, os.path.join(self.root, "ops", "tls", "root.pem"))
            self.assertNotEqual(copy.path, result.sslrootcert)    # the copy replaces the approved path


if __name__ == "__main__":
    unittest.main()

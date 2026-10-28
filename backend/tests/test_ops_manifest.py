"""Operations tool safety contract unit 3 (scripts/_ops_manifest.py): manifest format, paths
and file integrity.

Real filesystem checks on synthetic files in a temporary root this test creates and removes.
Nothing is imported, compiled or executed; no database, environment, network or app import.
Objects the OS will not let this account create (symbolic links without the privilege,
special files) are skipped with the reason; nothing mocked is counted as a filesystem check.

Run directly:      python tests/test_ops_manifest.py
Or via discovery:   python -m unittest discover -s tests
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import _ops_manifest as om  # noqa: E402

try:
    import _winapi  # Windows only: junctions
except ImportError:  # pragma: no cover
    _winapi = None

SECRET = "Synth3tic-Manifest-Secret-41c7"
FILES = {
    "backend/scripts/_ops_tool.py": b"print('synthetic')\n",
    "backend/app/recovery_stub.py": b"VALUE = 1\r\n",
    "docs/plans/srs-improvement/gate-e/OPS_TOOL_SAFETY_CONTRACT.md": "# 계약\n".encode("utf-8"),
    "ops/tls/synthetic-root.pem": b"-----BEGIN CERTIFICATE-----\nsynthetic\n",
    "backend/app/empty_module.py": b"",
}


def entry(rel: str, data: bytes, **changes) -> dict:
    item = {"path": rel, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    item.update(changes)
    return item


def manifest(entries: list[dict], **changes) -> bytes:
    doc = {"format_version": 1, "kind": "ops_manifest", "files": entries}
    doc.update(changes)
    return json.dumps(doc).encode("utf-8")


class Base(unittest.TestCase):
    def setUp(self):
        self.root = os.path.normpath(tempfile.mkdtemp(prefix="ops_manifest_test_"))
        self.junctions: list[str] = []
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        for junction in reversed(self.junctions):
            if os.path.lexists(junction):
                os.rmdir(junction)  # removes the junction itself, never its target's contents
        shutil.rmtree(self.root, ignore_errors=False)

    def write(self, rel: str, data: bytes, root: str | None = None) -> str:
        path = os.path.join(root or self.root, *rel.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as handle:
            handle.write(data)
        return path

    def build(self, files=FILES) -> bytes:
        for rel, data in files.items():
            self.write(rel, data)
        return manifest([entry(rel, data) for rel, data in files.items()])

    def junction(self, target: str, link: str) -> None:
        if _winapi is None:
            self.skipTest("junctions need Windows")
        os.makedirs(os.path.dirname(link), exist_ok=True)
        _winapi.CreateJunction(target, link)
        self.junctions.append(link)

    def refused(self, code, data, root=None, *, index=None, path=None):
        with self.assertRaises(om.OpsManifestRefused) as caught:
            om.check_manifest_files(data, self.root if root is None else root)
        error = caught.exception
        self.assertEqual(error.code, code)
        if index is not None:
            self.assertEqual(error.index, index)
        if path is not None:
            self.assertEqual(error.path, path)
        text = repr(error) + str(error) + repr(error.path)
        self.assertNotIn(SECRET, text)
        self.assertNotIn(self.root, text)
        self.assertTrue(error.__suppress_context__ or error.__context__ is None)
        return error


class Normal(Base):
    def test_code_contract_dependency_and_empty_file_together(self):
        data = self.build()
        result = om.check_manifest_files(data, self.root)
        self.assertEqual(result.manifest_sha256, hashlib.sha256(data).hexdigest())
        self.assertEqual(result.manifest_sha256, om.manifest_fingerprint(data))
        self.assertEqual((result.file_count, result.total_bytes), (5, sum(len(v) for v in FILES.values())))
        self.assertIs(result.signature_verified, False)

    def test_extra_files_on_disk_are_not_part_of_the_check(self):
        data = self.build()
        self.write("backend/scripts/not_listed.py", b"x")
        self.assertEqual(om.check_manifest_files(data, self.root).file_count, 5)


class Integrity(Base):
    def test_missing_size_hash_and_bytes_exactly(self):
        data = self.build()
        os.remove(os.path.join(self.root, "backend", "app", "empty_module.py"))
        self.refused("manifest_file_missing", data, index=4, path="backend/app/empty_module.py")
        self.write("backend/app/empty_module.py", b"")
        listed = [entry(k, v) for k, v in FILES.items()]
        self.refused("manifest_size_mismatch", manifest(listed[:1] + [{**listed[1], "size": listed[1]["size"] + 1}]))
        self.refused("manifest_hash_mismatch", manifest([{**listed[0], "sha256": "0" * 64}]), index=0)
        # CRLF on disk vs LF in the manifest: never normalised
        self.write("backend/app/recovery_stub.py", b"VALUE = 1\n")
        self.refused("manifest_size_mismatch", manifest([listed[1]]))
        self.write("backend/app/recovery_stub.py", b"value = 1\r\n")
        self.refused("manifest_hash_mismatch", manifest([listed[1]]))

    def test_on_disk_name_case_must_match(self):
        self.write("backend/scripts/Tool.py", b"x")
        self.refused("manifest_path_case_mismatch", manifest([entry("backend/scripts/tool.py", b"x")]))
        self.write("backend/App/a.py", b"x")
        self.refused("manifest_path_case_mismatch", manifest([entry("backend/app/a.py", b"x")]))


class Format(Base):
    def test_json_shape(self):
        good = manifest([entry("ops/tls/a.pem", b"")]).decode()
        for data in (b"", b"{", b"\xef\xbb\xbf" + good.encode(), b"\xff\xfe",
                     good.replace('"format_version": 1', '"format_version": 1, "format_version": 1').encode(),
                     good.replace('"size": 0', '"size": 0.0').encode(), good.replace('"size": 0', '"size": NaN').encode(),
                     b" " * (om.MAX_MANIFEST_BYTES + 1)):
            with self.subTest(data=data[:24]):
                self.refused("manifest_format_invalid", data)
        self.refused("manifest_fields_invalid", manifest([entry("ops/tls/a.pem", b"")], extra=1))
        self.refused("manifest_fields_invalid", b"[]")
        self.refused("manifest_kind_invalid", manifest([entry("ops/tls/a.pem", b"")], kind="manifest"))
        for value in (True, "1", 2, None):
            with self.subTest(format_version=value):
                self.refused("manifest_format_version", manifest([entry("ops/tls/a.pem", b"")], format_version=value))
        for files in ([], {}, None, [entry("ops/tls/a.pem", b"")] * 0):
            with self.subTest(files=repr(files)):
                self.refused("manifest_files_invalid", manifest([], files=files))
        many = [entry(f"ops/tls/f{i}.pem", b"") for i in range(om.MAX_FILES + 1)]
        self.refused("manifest_files_invalid", manifest(many))
        self.refused("manifest_entry_invalid", manifest([{**entry("ops/tls/a.pem", b""), "mode": "x"}]), index=0)
        self.refused("manifest_entry_invalid", manifest(["ops/tls/a.pem"]), index=0)

    def test_field_types_and_ranges(self):
        for size in ("0", True, -1, None, om.MAX_FILE_BYTES + 1):
            with self.subTest(size=repr(size)):
                self.refused("manifest_size_invalid", manifest([entry("ops/tls/a.pem", b"", size=size)]))
        for digest in ("A" * 64, "a" * 63, "a" * 65, "g" * 64, None, 1, "", " " + "a" * 63):
            with self.subTest(sha256=repr(digest)[:12]):
                self.refused("manifest_hash_invalid", manifest([entry("ops/tls/a.pem", b"", sha256=digest)]))
        for path in (None, 1, True, ["ops/tls/a.pem"], "", "x" * (om.MAX_PATH + 1)):
            with self.subTest(path=repr(path)[:12]):
                self.refused("manifest_path_invalid", manifest([entry("ops/tls/a.pem", b"", path=path)]))


class Paths(Base):
    INVALID = ["../ops/a.txt", "ops/../ops/a.txt", "ops/./a.txt", "ops//a.txt", "ops/a.txt/", "/ops/a.txt",
               "C:/ops/a.txt", "C:ops/a.txt", "//server/share/ops/a.txt", "\\\\server\\share\\a.txt",
               "\\\\?\\C:\\ops\\a.txt", "\\\\.\\COM1", "ops\\a.txt", "ops/a.txt:stream", "ops/a.txt::$DATA",
               "ops/a.txt.", "ops/a.txt ", "ops/ a.txt", "ops/CON", "ops/con.txt", "ops/NUL.py", "ops/Aux",
               "ops/COM1.log", "ops/lpt9", "ops/.env", "ops/.hidden/a.txt", "backend/scripts/__pycache__/a.py",
               "backend/scripts/a.cpython-314.pyc", "backend/scripts/a.PYO", "ops/é.txt", "ops/a*.txt",
               "ops/a?.txt", "ops/a\x00.txt", "ops/a\n.txt", "ops/" + "a" * (om.MAX_COMPONENT + 1)]
    NOT_ALLOWED = ["backend/tests/test_x.py", "frontend/app/page.tsx", "backend/scripts", "ops",
                   "Backend/scripts/a.py", "backend/Scripts/a.py", "docs/plans/srs-improvement/a.md",
                   "docs/plans/srs-improvement/gate-e", "backend/app.py", "README.md", "backend/.venv/x.py"]

    def test_escape_and_windows_variants(self):
        for path in self.INVALID:
            with self.subTest(path=path):
                error = self.refused("manifest_path_invalid", manifest([entry("ops/tls/a.pem", b"", path=path)]))
                self.assertIsNone(error.path)

    def test_outside_allowed_prefixes(self):
        for path in self.NOT_ALLOWED:
            with self.subTest(path=path):
                code = "manifest_path_invalid" if path.startswith("backend/.venv") else "manifest_path_not_allowed"
                self.refused(code, manifest([entry("ops/tls/a.pem", b"", path=path)]))

    def test_duplicates_case_and_prefix_conflicts(self):
        a = entry("ops/tls/a.pem", b"")
        self.refused("manifest_path_duplicate", manifest([a, a]), index=1, path="ops/tls/a.pem")
        self.refused("manifest_path_case_duplicate", manifest([a, entry("ops/tls/A.pem", b"")]), index=1)
        self.refused("manifest_path_case_duplicate",
                     manifest([entry("backend/app/dir/x.py", b""), entry("backend/app/DIR/x.py", b"")]), index=1)
        self.refused("manifest_path_conflict", manifest([entry("backend/app/a.py", b""), entry("backend/app/a.py/b.py", b"")]), index=1)
        self.refused("manifest_path_conflict", manifest([entry("backend/app/a.py/b.py", b""), entry("backend/app/A.py", b"")]), index=0)


class Root(Base):
    def test_root_forms(self):
        data = self.build()
        for root in ("", None, 1, b"C:\\", "relative\\root", self.root + "\\..\\" + os.path.basename(self.root),
                     self.root + "\\", self.root + "\\\\x", "\\\\server\\share", "\\\\?\\" + self.root,
                     "//server/share", self.root.replace("\\", "/"), self.root + "\\missing", self.root + "\x00"):
            with self.subTest(root=repr(root)[-30:]):
                with self.assertRaises(om.OpsManifestRefused) as caught:
                    om.check_manifest_files(data, root)
                self.assertIn(caught.exception.code, ("manifest_root_invalid", "manifest_root_link_or_not_directory"))
        file_root = self.write("ops/tls/plain.pem", b"")
        self.refused("manifest_root_link_or_not_directory", data, os.path.normpath(file_root))

    def test_root_or_its_parent_is_a_junction(self):
        data = self.build()
        link = os.path.join(tempfile.gettempdir(), os.path.basename(self.root) + "_link")
        self.junction(self.root, link)
        self.refused("manifest_root_link_or_not_directory", data, link)
        nested = os.path.join(link, "ops")
        self.refused("manifest_root_link_or_not_directory", data, nested)


class Objects(Base):
    def test_directory_in_place_of_a_file(self):
        os.makedirs(os.path.join(self.root, "ops", "tls", "a.pem"))
        self.refused("manifest_not_regular_file", manifest([entry("ops/tls/a.pem", b"")]), index=0)

    def test_intermediate_junction(self):
        outside = os.path.normpath(tempfile.mkdtemp(prefix="ops_manifest_outside_"))
        self.addCleanup(shutil.rmtree, outside)
        self.write("a.py", b"x", root=outside)
        self.junction(outside, os.path.join(self.root, "backend", "app", "linked"))
        self.refused("manifest_link_not_allowed", manifest([entry("backend/app/linked/a.py", b"x")]), index=0)

    def test_hard_link(self):
        original = self.write("ops/tls/a.pem", b"x")
        os.link(original, os.path.join(self.root, "ops", "tls", "b.pem"))
        self.refused("manifest_hard_link_not_allowed", manifest([entry("ops/tls/a.pem", b"x")]))
        self.refused("manifest_hard_link_not_allowed", manifest([entry("ops/tls/b.pem", b"x")]))

    def test_symbolic_link(self):
        target = self.write("ops/tls/a.pem", b"x")
        try:
            os.symlink(target, os.path.join(self.root, "ops", "tls", "s.pem"))
        except OSError as error:
            self.skipTest(f"symbolic link not creatable by this account (OSError {error.errno}); "
                          "the attribute rule is covered by the junction and reparse tests")
        self.refused("manifest_link_not_allowed", manifest([entry("ops/tls/s.pem", b"x")]))

    def test_special_files(self):
        self.skipTest("FIFOs / device files cannot be created on this Windows filesystem by a normal "
                      "account; device names are refused by the path format test")


class Races(Base):
    def test_replaced_between_check_and_open(self):
        data = self.build({"ops/tls/a.pem": b"original"})
        swap = self.write("ops/tls/swap.tmp", b"replaced")  # same size, different file

        def replace_file():
            os.replace(swap, os.path.join(self.root, "ops", "tls", "a.pem"))

        with mock.patch.object(om, "_between_check_and_open", replace_file):
            self.refused("manifest_file_changed", data, path="ops/tls/a.pem")

    def test_swapped_for_the_read_and_restored_after(self):
        """Only the opened handle's identity can see this: the path looks unchanged afterwards."""
        data = self.build({"ops/tls/a.pem": b"original"})
        target = os.path.join(self.root, "ops", "tls", "a.pem")
        parked = os.path.join(self.root, "ops", "tls", "parked.tmp")
        swap = self.write("ops/tls/swap.tmp", b"original")

        def swap_in():
            os.replace(target, parked)
            os.replace(swap, target)

        def restore():
            os.replace(target, swap)
            os.replace(parked, target)

        with mock.patch.object(om, "_between_check_and_open", swap_in), mock.patch.object(om, "_after_read", restore):
            self.refused("manifest_file_changed", data, path="ops/tls/a.pem")

    def test_replaced_after_read(self):
        data = self.build({"ops/tls/a.pem": b"original"})
        swap = self.write("ops/tls/swap.tmp", b"original")  # even identical bytes: a different file

        def replace_file():
            os.replace(swap, os.path.join(self.root, "ops", "tls", "a.pem"))

        with mock.patch.object(om, "_after_read", replace_file):
            self.refused("manifest_file_changed", data, path="ops/tls/a.pem")

    def test_replaced_by_junction_before_open(self):
        data = self.build({"backend/app/sub/a.py": b"x"})
        outside = os.path.normpath(tempfile.mkdtemp(prefix="ops_manifest_outside_"))
        self.addCleanup(shutil.rmtree, outside)
        self.write("a.py", b"x", root=outside)

        def swap_directory():
            os.replace(os.path.join(self.root, "backend", "app", "sub"), os.path.join(self.root, "backend", "app", "sub_old"))
            self.junction(outside, os.path.join(self.root, "backend", "app", "sub"))

        with mock.patch.object(om, "_between_check_and_open", swap_directory):
            self.refused("manifest_file_changed", data, path="backend/app/sub/a.py")

    def test_in_place_change_after_read_is_a_known_limit(self):
        """Documented limit (contract 5-4): the same file rewritten in place after it was read is
        not detected; a pass covers only the bytes read at check time."""
        data = self.build({"ops/tls/a.pem": b"original"})

        def rewrite():
            with open(os.path.join(self.root, "ops", "tls", "a.pem"), "r+b") as handle:
                handle.write(b"ORIGINAL")

        with mock.patch.object(om, "_after_read", rewrite):
            self.assertEqual(om.check_manifest_files(data, self.root).file_count, 1)


class Secrets(Base):
    def test_no_content_secret_or_absolute_path_in_refusals(self):
        data = self.build({"ops/tls/secret.pem": SECRET.encode()})
        self.write("ops/tls/secret.pem", (SECRET + "!").encode())
        self.refused("manifest_size_mismatch", data)
        self.write("ops/tls/secret.pem", SECRET[::-1].encode())
        self.refused("manifest_hash_mismatch", data)
        error = self.refused("manifest_path_invalid", manifest([entry("ops/tls/a.pem", b"", path="ops/" + SECRET + "!")]))
        self.assertIsNone(error.path)
        self.refused("manifest_format_invalid", ('{"x": "' + SECRET).encode())

    def test_module_never_imports_compiles_or_runs_files(self):
        source = (SCRIPTS_DIR / "_ops_manifest.py").read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"(?<![.\w])compile\(", source))  # re.compile is a regex, not code
        for forbidden in ("import_module", "__import__", "exec(", "eval(", "runpy", "subprocess",
                          "socket", "environ", "getenv", "psycopg", "from app", "import app", "spec_from"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


class FileTypes(Base):
    """Review fix: each area accepts only its contract file kind. A name rule is not a proof of
    what the bytes are (contract 5-4)."""

    def test_db_and_executable_names_are_refused(self):
        for rel in ("backend/app/synthetic.db", "backend/scripts/synthetic.exe"):
            with self.subTest(rel=rel):
                data = self.build({rel: b"synthetic bytes, not a real database or program"})
                self.refused("manifest_file_type_not_allowed", data, index=0, path=rel)

    def test_area_rules(self):
        refused = ["backend/scripts/tool.pyw", "backend/scripts/tool.PY", "backend/app/x.pyd", "backend/app/x.so",
                   "backend/app/x.dll", "backend/app/x.sqlite3", "backend/app/x.json", "backend/app/x.md",
                   "backend/scripts/tool.py.exe", "backend/scripts/run.bat", "backend/scripts/run.ps1",
                   "docs/plans/srs-improvement/gate-e/REPORT.txt", "docs/plans/srs-improvement/gate-e/notes.MD",
                   "docs/plans/srs-improvement/gate-e/x.py", "docs/plans/srs-improvement/gate-e/x.pdf",
                   "ops/a.txt", "ops/root.pem", "ops/tls/root.crt", "ops/tls/root.key", "ops/tls/sub/root.pem",
                   "ops/tls/root.PEM", "ops/secrets.json", "ops/profiles/read.json", "ops/tls/root.pem.bak"]
        for rel in refused:
            with self.subTest(rel=rel):
                self.refused("manifest_file_type_not_allowed", manifest([entry(rel, b"")]), index=0, path=rel)
        allowed = {"backend/scripts/tool.py": b"x = 1\n", "backend/app/pkg/mod.py": b"",
                   "docs/plans/srs-improvement/gate-e/OPS.md": b"# x\n", "ops/tls/root.pem": b"pem\n"}
        self.assertEqual(om.check_manifest_files(self.build(allowed), self.root).file_count, 4)

    def test_name_rule_is_not_a_content_check(self):
        """Documented limit: a .py name with non-Python bytes passes the type rule."""
        data = self.build({"backend/app/looks_like_code.py": b"\x00\x01SQLite format 3\x00"})
        self.assertEqual(om.check_manifest_files(data, self.root).file_count, 1)


class OpenFileErrors(Base):
    """Review fix: OSError at fstat / read / close of the opened file ends in a fixed code, and
    the handle is closed on every path. These are injected (mocked) OS failures on a real file,
    not filesystem races."""

    def setUp(self):
        super().setUp()
        self.data = self.build({"ops/tls/root.pem": b"x" * 10})
        self.opened: list[int] = []
        real_open = os.open

        def tracking_open(path, flags, *args):
            fd = real_open(path, flags, *args)
            self.opened.append(fd)
            return fd

        patcher = mock.patch.object(om.os, "open", tracking_open)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.assert_all_closed)

    def assert_all_closed(self):
        leaked = []
        for fd in self.opened:
            try:
                os.fstat(fd)
            except OSError:
                continue
            leaked.append(fd)
            os.close(fd)  # never leave a real handle behind, even on failure
        self.assertEqual(leaked, [])

    def io_fail(self, *_):
        raise OSError(5, "synthetic I/O failure " + SECRET, self.root)

    def check(self, code, **patches):
        active = [mock.patch.object(om.os, name, value) for name, value in patches.items()]
        for patch in active:
            patch.start()
        try:
            error = self.refused(code, self.data, index=0, path="ops/tls/root.pem")
        finally:
            for patch in reversed(active):
                patch.stop()
        self.assertNotIn("synthetic I/O failure", repr(error) + str(error))
        self.assertIsNone(error.__cause__)
        return error

    def closing_then_failing(self):
        real_close = os.close

        def close(fd):
            real_close(fd)  # the real handle is released; only the result is a failure
            raise OSError(5, "synthetic close failure " + SECRET)
        return close

    def test_fstat_failure(self):
        self.check("manifest_file_unreadable", fstat=self.io_fail)

    def test_read_failure(self):
        self.check("manifest_file_unreadable", read=self.io_fail)

    def test_close_failure_alone(self):
        self.check("manifest_file_close_failed", close=self.closing_then_failing())

    def test_read_failure_wins_over_close_failure(self):
        self.check("manifest_file_unreadable", read=self.io_fail, close=self.closing_then_failing())

    def test_refusal_wins_over_close_failure(self):
        self.write("ops/tls/root.pem", b"y" * 10)  # same size, other bytes
        self.check("manifest_hash_mismatch", close=self.closing_then_failing())

    def test_success_closes_the_handle(self):
        self.assertEqual(om.check_manifest_files(self.data, self.root).file_count, 1)
        self.assertEqual(len(self.opened), 1)


if __name__ == "__main__":
    unittest.main()

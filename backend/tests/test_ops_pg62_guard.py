"""6-2 target guard (tests/_ops_pg62.py) with FAKE process / listener facts and no connection.
The real-cluster run itself is tests/_ops_pg62_real.py (explicit, not discovered).

Run directly:      python tests/test_ops_pg62_guard.py
Or via discovery:   python -m unittest discover -s tests
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

TESTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS_DIR.parent / "scripts"))
sys.path.insert(0, str(TESTS_DIR))

import psycopg  # noqa: E402

import _ops_pg62 as g  # noqa: E402
import test_ops_preflight as pf  # noqa: E402  (helpers only)

TARGET = {"host": g.HOST, "port": g.PORT, "data": str(g.DATA), "postgres_exe": str(g.POSTGRES_EXE),
          "postmaster_pid": 4242, "server_version_num": "180006",
          "databases": {g.DB_A: {"oid": 16400, "identity_value": "pg62-a-x"},
                        g.DB_B: {"oid": 16401, "identity_value": "pg62-b-x"}},
          "provider_roles": list(g.PROVIDER_ROLES), "admin_role": g.ADMIN}
GOOD = {"host": g.HOST, "port": str(g.PORT), "dbname": g.DB_A, "user": g.READ, "sslmode": "verify-full",
        "password": pf.SECRET, "sslrootcert": "copy.pem"}


class GuardFakes(unittest.TestCase):
    def setUp(self):
        def forbidden(*_, **__):
            raise AssertionError("a connection function was called")

        for patch in (mock.patch.object(psycopg, "connect", forbidden),
                      mock.patch.object(g, "server_is_ours", lambda pid: pid == 4242),
                      mock.patch.dict(os.environ, {k: v for k, v in os.environ.items()
                                                   if not k.upper().startswith("PG")}, clear=True)):
            patch.start()
            self.addCleanup(patch.stop)
        self.tmp = Path(tempfile.mkdtemp(prefix="ops_pg62_guard_test_"))
        self.addCleanup(shutil.rmtree, self.tmp)
        self.run_folder = self.tmp / "run"
        self.run_folder.mkdir()

    def guard(self, target=TARGET, listed=None):
        data = json.dumps(target).encode()
        (self.run_folder / "target.json").write_bytes(data)
        files = {**pf.FILES, g.TARGET_DOC: listed if listed is not None else data}
        root = self.tmp / "deploy"
        shutil.rmtree(root, ignore_errors=True)
        for rel, content in files.items():
            path = root.joinpath(*rel.split("/"))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        return g.Guard(pf.manifest_doc(files), str(root), self.run_folder)

    def refused(self, code, kwargs, guard=None):
        guard = guard or self.guard()
        with self.assertRaises(g.Pg62Refused) as caught:
            guard.driver(**kwargs)
        self.assertEqual(caught.exception.code, code)
        self.assertNotIn(pf.SECRET, repr(caught.exception))
        self.assertEqual(guard.connect_calls, 0)

    def test_other_targets_refused_before_connecting(self):
        cases = [("pg62_host_refused", dict(host="127.0.0.1")), ("pg62_host_refused", dict(host="db.neon.tech")),
                 ("pg62_port_refused", dict(port="55432")), ("pg62_port_refused", dict(port="55463")),
                 ("pg62_database_refused", dict(dbname="postgres")), ("pg62_database_refused", dict(dbname="jp_vocab_test_e")),
                 ("pg62_role_refused", dict(user=g.ADMIN)), ("pg62_role_refused", dict(user="jp_vocab_e2")),
                 ("pg62_tls_mode_refused", dict(sslmode="require"))]
        for code, change in cases:
            with self.subTest(code=code, change=change):
                self.refused(code, {**GOOD, **change})

    def test_server_and_environment(self):
        self.refused("pg62_server_not_ours", GOOD, self.guard({**TARGET, "postmaster_pid": 4243}))
        self.refused("pg62_server_not_ours", GOOD, self.guard({**TARGET, "data": "C:/JV_Tools/pgdata-e2"}))
        with mock.patch.dict(os.environ, {"PGHOSTADDR": "127.0.0.1"}):
            self.refused("pg62_pg_environment_present", GOOD)

    def test_target_must_be_the_signed_entry(self):
        with self.assertRaises(g.Pg62Refused) as caught:
            self.guard(listed=json.dumps({**TARGET, "port": 55432}).encode())
        self.assertEqual(caught.exception.code, "pg62_target_hash_mismatch")
        # a target that says another port is refused by the fixed constants too
        self.refused("pg62_port_refused", {**GOOD, "port": "55432"}, self.guard({**TARGET, "port": 55432}))

    def test_good_target_reaches_the_driver_only_through_the_guard(self):
        with self.assertRaises(AssertionError):           # the patched real connect: the guard let it through
            self.guard().driver(**GOOD)

    def test_real_driver_only_in_the_guarded_module(self):
        for path in list((TESTS_DIR.parent / "scripts").glob("_ops_*.py")):
            source = re.sub(r'"""[\s\S]*?"""', "", path.read_text(encoding="utf-8"))
            with self.subTest(path=path.name):
                self.assertIsNone(re.search(r"psycopg\.connect\(", source))
        source = (TESTS_DIR / "_ops_pg62.py").read_text(encoding="utf-8")
        self.assertEqual(len(re.findall(r"psycopg\.connect\(", source)), 3)   # guard driver, admin, non-TLS probe
        for forbidden in ("argparse", "getenv(", "environ.get(", "environ[", "DATABASE_URL"):
            self.assertNotIn(forbidden, source)


class RecordStep(unittest.TestCase):
    """6-2 rerun prerequisite: a check whose pass cannot be recorded is not counted as passed.
    No database: a temporary run folder and fake check functions only."""

    def setUp(self):
        import _ops_pg62_real as real
        self.real = real
        self.tmp = Path(tempfile.mkdtemp(prefix="ops_pg62_record_test_"))
        self.addCleanup(shutil.rmtree, self.tmp)
        self.rec = g.Record(self.tmp)

    def statuses(self):
        return [(r["check"], r["status"]) for r in json.loads(self.rec.path.read_text(encoding="utf-8"))["results"]]

    def test_detail_key_colliding_with_the_record_keys(self):
        for key in ("seconds", "status", "check"):
            with self.subTest(key=key):
                ok = self.real.run_check(self.rec, f"collide_{key}", lambda h: {key: 1.0}, None)
                self.assertTrue(ok)                                 # details are kept apart from record keys
                self.assertIn((f"collide_{key}", "pass"), self.statuses())

    def test_recording_failure_is_not_a_pass(self):
        ok = self.real.run_check(self.rec, "unserializable", lambda h: {"x": object()}, None)
        self.assertFalse(ok)
        self.assertNotIn(("unserializable", "pass"), self.statuses())
        self.assertIn(("unserializable", "error"), self.statuses())
        json.loads(self.rec.path.read_text(encoding="utf-8"))     # the record file stays valid JSON

    def test_check_loop_stops_and_counts_only_recorded_passes(self):
        calls = []
        checks = [("a", lambda h: calls.append("a") or {}), ("b", lambda h: calls.append("b") or {"x": object()}),
                  ("c", lambda h: calls.append("c") or {})]
        passed = 0
        for name, fn in checks:
            if not self.real.run_check(self.rec, name, fn, None):
                break
            passed += 1
        self.assertEqual((passed, calls), (1, ["a", "b"]))


if __name__ == "__main__":
    unittest.main()

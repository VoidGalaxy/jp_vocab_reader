"""Environment-interference regressions for test_stats_history.py and test_learning_plan_progress.py.

Causes reproduced (2026-10-28):
- `srs_migrate.run_apply` (through `_ops_audit_run.fix_app_environment`) pins DATABASE_URL=sqlite:///:memory: for the
  whole process, and several test modules pin it at import. Modules that set DATABASE_URL at THEIR import time
  later opened a fresh in-memory database without tables ("no such table").
- `test_substitutes_srs_e2b_pg.StatsHistoryOnPostgres` inherits StatsHistoryTests: its class setup must prepare
  the app functions without the SQLite module fixture of test_stats_history (that fixture never runs there).

Every check runs in a NEW Python process so it never changes this process's environment. Nothing here starts,
connects to or administers PostgreSQL: the PostgreSQL comparison path is exercised with the guard module faked,
so it is NOT PostgreSQL evidence.

Run directly:      python tests/test_stats_history_isolation.py
Or via discovery:   python -m unittest discover -s tests -p test_stats_history_isolation.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
BACKEND = TESTS_DIR.parent
KEYS = ("APP_ENV", "DATABASE_URL", "PYTHON_DOTENV_DISABLED")

PRELUDE = r'''
import io, json, os, sys, unittest
# Watch the FIRST import of the app package: record the three safe values (as categories, never raw text) and
# stop the process before the app module runs if any is missing (so no .env is ever read by this check).
class _FirstAppImport:
    seen = None
    def find_spec(self, name, path=None, target=None):
        if _FirstAppImport.seen is None and (name == "app" or name.startswith("app.")):
            url = os.environ.get("DATABASE_URL")
            _FirstAppImport.seen = {{
                "APP_ENV": os.environ.get("APP_ENV") == "test",
                "PYTHON_DOTENV_DISABLED": os.environ.get("PYTHON_DOTENV_DISABLED") == "1",
                "DATABASE_URL": "memory" if url == "sqlite:///:memory:" else
                                "sqlite_file" if (url or "").startswith("sqlite:///") else
                                "missing" if not url else "other"}}
            print("FIRST_APP_IMPORT " + json.dumps(_FirstAppImport.seen), flush=True)
            s = _FirstAppImport.seen
            if not (s["APP_ENV"] and s["PYTHON_DOTENV_DISABLED"] and s["DATABASE_URL"] in ("memory", "sqlite_file")):
                print("UNSAFE_BEFORE_APP_IMPORT", flush=True)
                os._exit(3)
        return None
sys.meta_path.insert(0, _FirstAppImport())
# The safe environment of every child, fixed before ANY app module can be imported. The parent's database
# setting, PostgreSQL opt-ins and PYTHONPATH are removed by run_child; cases that need more set it after this.
os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["PYTHON_DOTENV_DISABLED"] = "1"
sys.path[:0] = [{tests!r}, {scripts!r}]
sys.path.append({backend!r})
KEYS = ("APP_ENV", "DATABASE_URL", "PYTHON_DOTENV_DISABLED")
env = lambda: {{k: os.environ.get(k) for k in KEYS}}
def run(module):
    suite = unittest.defaultTestLoader.loadTestsFromModule(module)
    result = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(suite)
    return {{"run": result.testsRun, "errors": len(result.errors), "failures": len(result.failures),
             "skipped": len(result.skipped)}}
'''

STATS = PRELUDE + r'''
before_import = env()
import test_stats_history as st
after_import = env()
import _ops_audit_run as ar
ar.fix_app_environment()                     # what an earlier CLI test does to the whole process
pinned = env()
outcome = run(st)
print("RESULT " + json.dumps(dict(before_import=before_import, after_import=after_import, pinned=pinned,
                                  after_run=env(), **outcome)))
'''

LEARNING = PRELUDE + r'''
before_import = env()
import test_learning_plan_progress as lp
after_import = env()
import test_srs_migrate_resume_sqlite        # pins DATABASE_URL=sqlite:///:memory: at its import
pinned = env()
outcome = run(lp)
print("RESULT " + json.dumps(dict(before_import=before_import, after_import=after_import, pinned=pinned,
                                  after_run=env(), **outcome)))
'''

INHERITED = PRELUDE + r'''
import test_substitutes_srs_e2b_pg as sub    # imports test_stats_history; its module fixture never runs here
try:
    sub.StatsHistoryOnPostgres.setUpClass()
    error = None
except Exception as caught:
    error = type(caught).__name__
import test_stats_history as st
from app import database
print("RESULT " + json.dumps({{"error": error, "init_db_is_app": st.init_db is database.init_db,
                               "get_connection_is_app": st.get_connection is database.get_connection,
                               "database_url": os.environ.get("DATABASE_URL")}}))
'''

# PostgreSQL comparison path of test_learning_plan_progress with the guard FAKED (no PostgreSQL anywhere).
LEARNING_PG = PRELUDE + r'''
import types
calls = []
guard = types.ModuleType("_local_postgres_guard")
class UnsafePostgresTarget(ValueError):
    pass
def validate(raw):
    calls.append(("validate", raw))
    return raw
def assert_empty(url):
    calls.append(("assert_empty", url))
guard.UnsafePostgresTarget = UnsafePostgresTarget
guard.validate_local_postgres_test_url = validate
guard.assert_empty_postgres_test_database = assert_empty
sys.modules["_local_postgres_guard"] = guard
URL = "postgresql://plan@localhost/jp_vocab_test_plan_fake"
os.environ["LEARNING_PLAN_TEST_POSTGRES_URL"] = URL
import app.database as database
def forbidden(*a, **k):
    raise AssertionError("init / connection must not happen in this fake check")
database.init_db = forbidden
database.get_connection = forbidden
import test_learning_plan_progress as lp
after_import = env()
lp.setUpModule()                             # the module fixture must not replace the checked target
after_setup = env()
lp._require_checked_target()                  # unchanged target: accepted
os.environ["DATABASE_URL"] = "sqlite:///another_module.db"
try:
    lp._require_checked_target()
    refused = False
except RuntimeError:
    refused = True
os.environ["DATABASE_URL"] = URL
unittest.case.doModuleCleanups()
print("RESULT " + json.dumps({{"calls": calls, "after_import": after_import, "after_setup": after_setup,
                               "refused_after_change": refused, "after_cleanup": env()}}))
'''


class Isolation(unittest.TestCase):
    def run_child(self, code: str, **extra_env) -> dict:
        env = {k: v for k, v in os.environ.items()
               if k not in ("PYTHONPATH", "LEARNING_PLAN_TEST_POSTGRES_URL", "SRS_E_TEST_POSTGRES_OPT_IN") + KEYS
               and not k.upper().startswith("PG")}
        env.update(extra_env)
        done = subprocess.run([sys.executable, "-c", code.format(tests=str(TESTS_DIR), scripts=str(BACKEND / "scripts"), backend=str(BACKEND))],
                              capture_output=True, text=True, timeout=300, env=env, cwd=str(TESTS_DIR))
        self.assertNotIn("UNSAFE_BEFORE_APP_IMPORT", done.stdout)
        lines = [line for line in done.stdout.splitlines() if line.startswith("RESULT ")]
        self.assertEqual(len(lines), 1, done.stdout[-800:] + done.stderr[-2000:])
        first = [line for line in done.stdout.splitlines() if line.startswith("FIRST_APP_IMPORT ")]
        self.assertEqual(len(first), 1, done.stdout[-800:])
        out = json.loads(lines[0][len("RESULT "):])
        out["first_app_import"] = json.loads(first[0][len("FIRST_APP_IMPORT "):])
        return out

    def test_stats_history_own_database_after_an_earlier_cli_pin(self):
        out = self.run_child(STATS)
        self.assertEqual(out["after_import"], out["before_import"])          # import changes nothing
        self.assertEqual(out["pinned"]["DATABASE_URL"], "sqlite:///:memory:")
        self.assertEqual((out["errors"], out["failures"], out["skipped"]), (0, 0, 0), out)
        self.assertGreaterEqual(out["run"], 16)
        self.assertEqual(out["after_run"], out["pinned"])                   # environment restored

    def test_learning_plan_own_database_after_a_later_module_pins_memory(self):
        out = self.run_child(LEARNING)
        self.assertEqual(out["after_import"], out["before_import"])
        self.assertEqual(out["pinned"]["DATABASE_URL"], "sqlite:///:memory:")
        self.assertEqual((out["errors"], out["failures"], out["skipped"]), (0, 0, 0), out)
        self.assertGreaterEqual(out["run"], 19)
        self.assertEqual(out["after_run"], out["pinned"])

    def test_inherited_postgres_class_prepares_the_app_functions(self):
        out = self.run_child(INHERITED)
        self.assertIsNone(out["error"], out)
        self.assertTrue(out["init_db_is_app"] and out["get_connection_is_app"], out)
        self.assertEqual(out["database_url"], "sqlite:///:memory:")         # the substitute module's own default

    def test_learning_plan_postgres_path_keeps_its_contract(self):
        out = self.run_child(LEARNING_PG)
        url = "postgresql://plan@localhost/jp_vocab_test_plan_fake"
        self.assertEqual(out["calls"], [["validate", url], ["assert_empty", url]])   # check, then emptiness, once
        self.assertEqual(out["after_import"]["DATABASE_URL"], url)                  # the opt-in target is set
        self.assertEqual(out["after_setup"]["DATABASE_URL"], url)                   # not replaced by SQLite
        self.assertTrue(out["refused_after_change"])                                 # a changed target is refused
        self.assertEqual(out["after_cleanup"]["DATABASE_URL"], url)

    def test_safe_values_at_the_first_app_import(self):
        # the inherited PostgreSQL stand-in and the faked PostgreSQL comparison path import the app first in the
        # child itself: the three safe values must already be there (then the full paths above still run)
        for name, code in (("inherited", INHERITED), ("learning_pg", LEARNING_PG)):
            with self.subTest(case=name):
                out = self.run_child(code)
                self.assertEqual(out["first_app_import"], {"APP_ENV": True, "PYTHON_DOTENV_DISABLED": True,
                                                           "DATABASE_URL": "memory"})
        for name, code in (("stats", STATS), ("learning", LEARNING)):
            with self.subTest(case=name):
                seen = self.run_child(code)["first_app_import"]
                self.assertTrue(seen["APP_ENV"] and seen["PYTHON_DOTENV_DISABLED"], seen)
                self.assertIn(seen["DATABASE_URL"], ("memory", "sqlite_file"))


if __name__ == "__main__":
    unittest.main()

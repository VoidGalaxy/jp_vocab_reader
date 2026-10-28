"""Exit status of the 6-2 runner's CLI (tests/_ops_pg62_real.py `check` / `check-rerun`).

Each case runs the file's own `if __name__ == "__main__":` block in a separate Python process,
with FAKE checks, a fake harness and a synthetic temporary run folder. The real driver entry
points are patched to fail, and nothing finds or starts a PostgreSQL server.

Run directly:      python tests/test_ops_pg62_cli.py
Or via discovery:   python -m unittest discover -s tests
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
RUNNER = TESTS_DIR / "_ops_pg62_real.py"

CHILD = r'''
import json, re, sys
from pathlib import Path
sys.path.insert(0, {scripts!r}); sys.path.insert(0, {tests!r})
import psycopg

def forbidden(*_, **__):
    raise AssertionError("a connection function was called")

psycopg.connect = forbidden
psycopg.Connection.connect = forbidden
import _ops_pg62 as g
import _ops_pg62_real as real

folder = Path({folder!r})
g.single_run = lambda: g.Record(folder)
g.server_is_ours = lambda pid: True
g.pg_environment_present = lambda: False

class FakeHarness:
    def __init__(self, rec):
        self.rec, self.pid = rec, 1
    def set_password(self, role):
        pass
    def close(self):
        pass

real.Harness = FakeHarness

def ok(h):
    return {{}}

def fail(h):
    raise real.CheckFailed("product_defect", "synthetic failure")

def broken(h):
    raise RuntimeError("synthetic harness error")

def unrecordable(h):
    return {{"x": object()}}

scenario = {scenario!r}
names = [n for n, _ in real.CHECKS]
kinds = {{"pass": {{}}, "middle_fail": {{names[1]: fail}}, "harness_error": {{names[1]: broken}},
          "record_fail": {{names[1]: unrecordable}}}}
if scenario == "incomplete":
    real.CHECKS = [(n, ok) for n in names if n != "c14_reconnect"]   # a selected check is missing
else:
    real.CHECKS = [(n, kinds[scenario].get(n, ok)) for n in names]

source = Path({runner!r}).read_text(encoding="utf-8")
block = source[source.index('if __name__ == "__main__":'):]
sys.argv = [{runner!r}, {phase!r}]
namespace = dict(vars(real))
namespace["__name__"] = "__main__"
exec(compile(block, {runner!r}, "exec"), namespace)
'''


class CliExitStatus(unittest.TestCase):
    def run_cli(self, phase: str, scenario: str) -> tuple[int, dict]:
        tmp = Path(tempfile.mkdtemp(prefix="ops_pg62_cli_test_"))
        self.addCleanup(shutil.rmtree, tmp)
        folder = tmp / "run"
        folder.mkdir()
        code = CHILD.format(scripts=str(TESTS_DIR.parent / "scripts"), tests=str(TESTS_DIR), folder=str(folder),
                            scenario=scenario, runner=str(RUNNER), phase=phase)
        done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120,
                              cwd=str(TESTS_DIR))
        self.assertNotIn("a connection function was called", done.stdout + done.stderr)
        record = json.loads((folder / "record.json").read_text(encoding="utf-8")) \
            if (folder / "record.json").exists() else {"results": []}
        return done.returncode, record

    def test_exit_status_per_outcome(self):
        for phase in ("check", "check-rerun"):
            for scenario, expect_zero in (("pass", True), ("middle_fail", False), ("harness_error", False),
                                          ("record_fail", False), ("incomplete", False)):
                with self.subTest(phase=phase, scenario=scenario):
                    status, record = self.run_cli(phase, scenario)
                    self.assertEqual(status == 0, expect_zero, f"exit status {status}")
                    statuses = [r["status"] for r in record["results"]]
                    if scenario == "pass":
                        self.assertEqual(set(statuses), {"pass"})
                    elif scenario in ("middle_fail", "harness_error", "record_fail"):
                        # the partial pass and the original stop reason are kept
                        self.assertEqual(statuses[0], "pass")
                        self.assertIn(statuses[-1], ("fail", "error"))
                        self.assertEqual(statuses.count("pass"), 1)


if __name__ == "__main__":
    unittest.main()

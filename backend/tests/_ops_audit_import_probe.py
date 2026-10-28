"""Import-order probe for scripts/_ops_audit_run.py, run ONLY in a fresh process by
test_ops_audit_run.ImportOrder (not discovered: no `test_` prefix).

An import watcher records every `app` / `app.*` import next to the pre-check result and the
fake driver call, so an earlier import in the parent process cannot hide the order. Real test-key
signatures and synthetic files; fake driver and connection; connect entry points patched to fail.
"""

from __future__ import annotations

import importlib.abc
import importlib.util
import json
import os
import sys
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

TESTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS_DIR.parent / "scripts"))
sys.path.insert(0, str(TESTS_DIR))
sys.path.insert(0, str(TESTS_DIR.parent))

EVENTS: list[str] = []


class Watch(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path=None, target=None):
        if name == "app" or name.startswith("app."):
            EVENTS.append("import:" + name)
        return None


sys.meta_path.insert(0, Watch())

# Mutation checks only: load a mutated copy of the module under test from this path.
_MUTANT = os.environ.get("OPS_AUDIT_RUN_MUTANT_FILE")
if _MUTANT:
    _spec = importlib.util.spec_from_file_location("_ops_audit_run", _MUTANT)
    sys.modules["_ops_audit_run"] = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(sys.modules["_ops_audit_run"])

import _ops_audit_run as ar  # noqa: E402
import _ops_preflight as op  # noqa: E402
import test_ops_adapter as ta  # noqa: E402
import test_ops_audit_run as tr  # noqa: E402
import test_ops_observer as to  # noqa: E402


class Probe(ta.Base):
    """Uses test_ops_audit_run.Base helpers without its app-importing setUp."""

    scope = tr.Base.scope
    approval = tr.Base.approval
    audit_inputs = tr.Base.audit_inputs

    def setUp(self):
        super().setUp()
        self.assertFalse(any(m == "app" or m.startswith("app.") for m in sys.modules), "app imported too early")
        EVENTS.clear()
        real = op.run_synthetic_preflight

        def watched(inputs):
            try:
                result = real(inputs)
            except op.OpsPreflightRefused:
                EVENTS.append("preflight:refused")
                raise
            EVENTS.append("preflight:passed")
            return result

        patch = mock.patch.object(op, "run_synthetic_preflight", watched)
        patch.start()
        self.addCleanup(patch.stop)

    def driver(self, conn):
        fake = ta.FakeDriver(conn)

        def call(**kwargs):
            EVENTS.append("connect")
            return fake(**kwargs)
        return call

    def report(self, name, inputs, conn):
        out, code = ar.run_synthetic_audit(inputs, expected=to.READ_EXPECTED, driver=self.driver(conn))
        print("PROBE " + json.dumps({"case": name, "events": EVENTS, "reason": out.get("reason"), "code": code,
                                     "trace": conn.trace}))

    def test_bad_approval_signature(self):
        self.report("bad_signature", self.audit_inputs(approval_signature=b"bad"), tr.AuditConn())

    def test_bad_manifest_signature(self):
        self.report("bad_manifest", self.audit_inputs(manifest_signature=b"bad"), tr.AuditConn())

    def test_normal_order(self):
        self.report("normal", self.audit_inputs(), tr.AuditConn())


if __name__ == "__main__":
    unittest.main()

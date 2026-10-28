"""OPS_MIGRATION_CLI_PLAN 1-1: `srs_migrate` dry-run with the REAL product query on a synthetic SQLite file.

Approvals, signatures (test-only temporary keys) and the pre-check are real. The connection source is a
TEST INJECTION: `srs_migrate._product_connector` is replaced by a function that hands out the app's own
read connections to this test's synthetic SQLite file (the provider path is covered with fakes in
test_srs_migrate_cli.py). No PostgreSQL, Neon or backend/vocab.db is touched; nothing is applied.

Run directly:      python tests/test_srs_migrate_sqlite.py
"""

from __future__ import annotations

import os

os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["PYTHON_DOTENV_DISABLED"] = "1"

import shutil  # noqa: E402
import sqlite3  # noqa: E402
import sys  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402
from datetime import timedelta  # noqa: E402
from pathlib import Path  # noqa: E402
from unittest import mock  # noqa: E402

TESTS_DIR = Path(__file__).resolve().parent
BACKEND = TESTS_DIR.parent
sys.path.insert(0, str(BACKEND / "scripts"))
sys.path.insert(0, str(TESTS_DIR))
if str(BACKEND) not in sys.path:      # path only, from this file's location
    sys.path.append(str(BACKEND))

import _ops_approval as oa  # noqa: E402
import _ops_plan_file as pfile  # noqa: E402
import _ops_preflight as op  # noqa: E402
import srs_migrate as cli  # noqa: E402
import test_ops_preflight as pf  # noqa: E402  (module only)
from test_srs_d2_intro import IntroCase  # noqa: E402  (imports the app; environment fixed above)
from test_srs_queue import NOW, iso  # noqa: E402

from app import database  # noqa: E402
from app.srs import migration  # noqa: E402
from app.srs.engine import CardKey  # noqa: E402


class SqliteDryRun(pf.Base, IntroCase):
    def setUp(self):
        pf.Base.setUp(self)
        IntroCase.setUp(self)
        self.folder = tempfile.mkdtemp(prefix="srs_migrate_sqlite_")
        self.addCleanup(shutil.rmtree, self.folder, True)
        self.out = os.path.join(self.folder, "plan.json")
        self.calls: list[bool] = []
        past = self.past_card("past", iso(NOW - timedelta(days=5)))
        fresh = self.personal("fresh")
        deck = self.shared_deck("lost")
        lost = self.lexeme("lost", deck)
        with database.get_connection() as c:
            c.execute("UPDATE user_deck_subscriptions SET is_active = FALSE WHERE user_id = ? AND shared_deck_id = ?",
                      (self.user, deck))
        self.personal("other-card", user=self.other)                       # another account's data
        self.unasked = self.personal("not-in-scope")                         # same account, outside the list
        self.req = cli.make_request(self.user, "mig-sqlite-1", [past, fresh], [lost])

    def tearDown(self):
        pf.Base.tearDown(self)

    def connect(self, *, read_only=False):
        """TEST INJECTION: the app's own connection to this synthetic file; reads are requested read-only.
        The CLI fixed DATABASE_URL to an in-memory value, so the file is named here explicitly."""
        self.calls.append(read_only)
        with mock.patch.dict(os.environ, {"DATABASE_URL": f"sqlite:///{self.db_path.as_posix()}"}):
            return database.get_connection(read_only=read_only)

    def dump(self) -> list[str]:
        connection = sqlite3.connect(self.db_path)
        try:
            return list(connection.iterdump())
        finally:
            connection.close()

    def approval(self, req=None, **changes) -> bytes:
        req = req or self.req
        values = dict(tool="srs_migrate", accounts=[self.user], max_accounts=1,
                      steps=[{"command": "dry_run", "access": "read", "role": "ops_read", "profile": pf.READ_PROFILE}],
                      job={"key": req.run_key, "inputs": cli.job_inputs(req)})
        values.update(changes)
        return self.inquiry(**values)

    def run_cli(self, req=None, approval=None):
        req = req or self.req
        inputs = self.inputs(approval or self.approval(req), command="dry_run", account_id=self.user,
                             job_key=req.run_key, job_inputs=cli.job_inputs(req), product_fingerprint=None)
        with mock.patch.object(cli, "_product_connector", lambda *a, **k: self.connect):
            return cli.run_dry_run(req, inputs=inputs, expected=None, driver=lambda **k: None, out=self.out)

    def test_real_dry_run_writes_nothing_and_binds_the_file(self):
        before = self.dump()
        out, code = self.run_cli()
        self.assertEqual((out["status"], code), ("ok", 0))
        self.assertEqual(self.dump(), before)                                # no DB write, other data unchanged
        self.assertEqual(self.calls, [True])                                 # one read connection
        self.assertEqual(os.environ["DATABASE_URL"], "sqlite:///:memory:")   # the CLI fixed the app environment
        keys = [CardKey(kind, self.user, ref) for kind, ref in self.req.cards]
        direct = migration.dry_run(keys, connect=self.connect)              # the same query, outside the CLI
        plan = pfile.read_plan_file(self.out)
        self.assertEqual(pfile.to_candidates(plan), direct)                 # the file holds the product's candidates
        self.assertEqual(out["artifact_sha256"], plan.artifact_sha256)
        product = migration.hashlib.sha256(migration._plan_json(direct).encode()).hexdigest()
        self.assertEqual(out["product_fingerprint"], product)
        self.assertEqual(out["job_plan"], oa.job_plan_fingerprint(
            db_identity=out["db_identity"], manifest=op.om.manifest_fingerprint(self.manifest), tool="srs_migrate",
            account_id=self.user, job_key=self.req.run_key, job_inputs=cli.job_inputs(self.req),
            product_fingerprint=product, artifact_sha256=plan.artifact_sha256))
        self.assertEqual(out["card_count"], 3)
        self.assertEqual(sum(out["qualities"].values()), 3)
        self.assertIn("unavailable", out["qualities"])                       # the lost subscription card
        self.assertNotIn(str(self.unasked), [str(ref) for _, ref in self.req.cards])
        self.assertEqual({c.key.user_id for c in direct}, {self.user})

    def test_changed_scope_is_refused_before_the_query(self):
        other = cli.make_request(self.user, self.req.run_key, [ref for kind, ref in self.req.cards if kind == "personal"],
                                 [])
        before = self.dump()
        out, code = self.run_cli(req=other, approval=self.approval(self.req))
        self.assertEqual((out["code"], code), ("preflight_job_input_mismatch", 4))
        self.assertEqual((self.calls, self.dump(), os.path.exists(self.out)), ([], before, False))


if __name__ == "__main__":
    unittest.main()

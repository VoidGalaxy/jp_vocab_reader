"""Gate E-2c: the three cleanup CLIs as REAL child processes against the protected local test
PostgreSQL (E-1 harness run: limited role, run marker, schema created in the managed step).

- a dry run (the default) leaves every owned table's tuples untouched -- ctid / xmin / values
  (the harness's own connection reads them) -- and exits 0 with a counts-only report;
- --apply without the matching --confirm-user-id is refused before connecting, nothing changes;
- a child without the opt-in, or with a non-test URL, is refused with a fixed code;
- no output (stdout / stderr) holds the URL, the role, the port or the word password.
The tools' batch behaviour on PostgreSQL through the same CLIs (apply, rerun, failure and
resume, CAS conflicts, record formats, damaged values, races) is checked by the existing tool
tests run with _srs_pg_suite.py, which runs their CLI calls with --local-test-postgres.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import unittest
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import _srs_e2_compare as cmp  # noqa: E402
from test_srs_e3_fk_real import RealCase, _opt_in  # noqa: E402

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
TOOLS = {"d2_receipt_minimize.py": ["--purge-expired"], "d2_snapshot_minimize.py": [], "d2_snapshot_prune.py": []}
DAY = timedelta(days=1)


@unittest.skipUnless(_opt_in(), "Real PostgreSQL E-2c CLI checks NOT RUN (opt-in not set)")
class CleanupCliOnPostgres(RealCase):
    def fingerprint(self):
        run = self.run
        digest = hashlib.sha256()
        with run._connection() as connection:
            try:
                run._check_target(connection)
                for table in sorted(run.owned_oids):
                    for row in run._rows(connection, f"SELECT ctid::text, xmin::text, row_to_json(t)::text "
                                                     f"FROM public.{table} AS t ORDER BY ctid"):
                        digest.update("|".join(row).encode())
            finally:
                connection.rollback()
        return digest.hexdigest()

    def cli(self, script, *args, env_change=None):
        env = {k: v for k, v in os.environ.items() if k != "DATABASE_URL"}
        env.update(self.run.cli_marker_environment())
        env.update(env_change or {})
        env = {k: v for k, v in env.items() if v is not None}
        done = subprocess.run([sys.executable, str(SCRIPTS / script), *args], capture_output=True, text=True,
                              timeout=120, env=env, encoding="utf-8")
        url = os.environ["SRS_E_TEST_POSTGRES_URL"]
        for stream in (done.stdout, done.stderr):
            for secret in (url, "jp_vocab_e2", "55432", "password", self.run._nonce):
                self.assertFalse(secret in stream, (script, args, "sensitive output redacted"))
        return done

    def test_other_run_identity_is_refused_without_changing_any_rows(self):
        self.create()
        user = str(self.setup_account())
        before = self.fingerprint()
        nonce = "0" * 32 if self.run._nonce != "0" * 32 else "1" * 32
        changes = ({"SRS_E_TEST_POSTGRES_MARKER_NONCE": nonce},
                   {"SRS_E_TEST_POSTGRES_MARKER_OID": str(self.run._marker_oid + 1)},
                   {"SRS_E_TEST_POSTGRES_MARKER_NONCE": None})
        for script in TOOLS:
            for change in changes:
                with self.subTest(script=script, field=next(iter(change))):
                    done = self.cli(script, "--local-test-postgres", "--user-id", user, "--apply",
                                    "--confirm-user-id", user, *TOOLS[script], env_change=change)
                    self.assertEqual(done.returncode, 2)
                    self.assertIn("run_marker_", done.stderr)
                    self.assertEqual(self.fingerprint(), before)

    def setup_account(self):
        from app.srs import migration
        from app.srs.engine import CardKey

        with cmp.Scenario("postgresql", self.run) as sc:
            sc.clock = cmp.T0 - 60 * DAY
            user = sc.user("cli")
            sc.set_mode(user, "legacy")
            card = sc.card(user, "c1")
            sc.clock = cmp.T0 - 50 * DAY
            assert sc.review(user, card, "good", legacy=True)["status"] == 200
            sc.clock = cmp.T0
            sc.set_mode(user, "fsrs")
            migration.apply_plan(migration.dry_run([CardKey("personal", user, card)]), "cli-run", approved=True)
            sc.clock = cmp.T0 + DAY
            assert sc.review(user, card, "good")["status"] == 200
        return user

    def test_dry_run_refusals_and_output(self):
        self.create()
        user = str(self.setup_account())
        before = self.fingerprint()
        for script in TOOLS:
            with self.subTest(script):
                done = self.cli(script, "--local-test-postgres", "--user-id", user)
                self.assertEqual(done.returncode, 0, done.stderr[-300:])
                report = json.loads(done.stdout)
                self.assertEqual((report["database"], report["applied"], report["user_id"]),
                                 ("local_test_postgres", False, int(user)))
                self.assertEqual(self.fingerprint(), before)       # dry run: no tuple written

                done = self.cli(script, "--local-test-postgres", "--user-id", user, "--apply", *TOOLS[script])
                self.assertEqual(done.returncode, 2)
                self.assertIn("--confirm-user-id", done.stderr)
                done = self.cli(script, "--local-test-postgres", "--user-id", user, "--apply",
                                "--confirm-user-id", str(int(user) + 1), *TOOLS[script])
                self.assertEqual(done.returncode, 2)

                done = self.cli(script, "--local-test-postgres", "--user-id", user,
                                env_change={"SRS_E_TEST_POSTGRES_OPT_IN": None})
                self.assertEqual(done.returncode, 2)
                self.assertIn("local test PostgreSQL refused: local_postgres_opt_in_required", done.stderr)
                done = self.cli(script, "--local-test-postgres", "--user-id", user,
                                env_change={"SRS_E_TEST_POSTGRES_URL": "postgresql://x@db.example.com:5432/jp_vocab_test_e"})
                self.assertEqual(done.returncode, 2)
                self.assertIn("local_postgres_url_refused", done.stderr)
                self.assertEqual(self.fingerprint(), before)

    def test_applied_run_and_rerun(self):
        self.create()
        user = str(self.setup_account())
        reports = {}
        for script in TOOLS:
            with self.subTest(script):
                args = ("--local-test-postgres", "--user-id", user, "--apply", "--confirm-user-id", user, *TOOLS[script])
                first = self.cli(script, *args)
                self.assertEqual(first.returncode, 0, first.stderr[-300:])
                after_first = self.fingerprint()
                again = self.cli(script, *args)
                self.assertEqual(again.returncode, 0, again.stderr[-300:])
                reports[script] = (json.loads(first.stdout), json.loads(again.stdout))
                self.assertTrue(reports[script][0]["applied"])
                self.assertEqual(self.fingerprint(), after_first, script)   # the rerun writes nothing
        # The child uses the real clock (after 2026-10-01); the fixture is from June 2026, so the
        # receipt is 7+ days old and the apply run's 30-day window is closed.
        receipts, receipts_again = reports["d2_receipt_minimize.py"]
        self.assertEqual((len(receipts["expired"]), len(receipts["purged"]), receipts["stripped"]), (1, 1, []))
        self.assertEqual((receipts_again["expired"], receipts_again["purged"]), ([], []))
        snapshots, snapshots_again = reports["d2_snapshot_minimize.py"]
        self.assertEqual((snapshots["already_minimal"], snapshots["minimized"]), (1, []))   # format 2 stays
        self.assertEqual(snapshots_again["already_minimal"], 1)
        prune, prune_again = reports["d2_snapshot_prune.py"]
        self.assertEqual((len(prune["runs"]["pruned"]), len(prune["snapshots"]["pruned"])), (1, 1))
        self.assertEqual((prune_again["runs"]["pruned"], prune_again["snapshots"]["pruned"]), ([], []))
        self.assertEqual((prune_again["runs"]["already_pruned"], prune_again["snapshots"]["already_pruned"]), (1, 1))
        with cmp.Scenario("postgresql", self.run) as sc:
            self.assertEqual(sc.count("srs_review_receipts"), 0)
            record = sc.sql("SELECT legacy_json FROM srs_migration_snapshots")[0]
            self.assertEqual(json.loads(record["legacy_json"])["format"], 3)
            run = sc.sql("SELECT status, started_at, finished_at, scope_json FROM srs_migration_runs "
                         "WHERE run_key = 'cli-run'")[0]
            self.assertEqual(run["status"], "completed")                       # never changed by expiry
            self.assertIn("request_sha256", json.loads(run["scope_json"]))


if __name__ == "__main__":
    unittest.main()

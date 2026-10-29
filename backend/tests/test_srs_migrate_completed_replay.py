"""OPS_MIGRATION_COMPLETED_REPLAY_PLAN 3-3 / 9 (C1-C4): `status` as the completed-result requery
path -- "completed result replay = run a new inquiry-approved `status`, read the state when
`state == completed`." Reuses `test_srs_migrate_status.RecordsBase` (fixtures only; no test
methods of its own, so nothing here duplicates its subclasses' tests).

REAL: product-created records from the real `migration.apply_plan` on a synthetic SQLite file
this test makes (no PostgreSQL, Neon or backend/vocab.db); the real `read_status` / `judge_status`
read of `srs_migrate.py`; real approvals / signatures (test-only temporary keys) and the real
pre-check. The connection source for `status` is a TEST INJECTION, labelled where used: the app's
own SQLite connection to the synthetic file (`RecordsBase.connect`), exactly as in
test_srs_migrate_status.py.

Run directly:      python tests/test_srs_migrate_completed_replay.py
"""

from __future__ import annotations

import os

os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["PYTHON_DOTENV_DISABLED"] = "1"

import hashlib  # noqa: E402
import json  # noqa: E402
import sys  # noqa: E402
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

import srs_migrate as cli  # noqa: E402
import test_srs_migrate_status as tstatus  # noqa: E402  (RecordsBase: fixtures only, no tests re-run here)
from test_srs_queue import NOW, iso  # noqa: E402

from app.srs import migration  # noqa: E402


class CompletedReplay(tstatus.RecordsBase):
    """Fixtures: `tstatus.RecordsBase` (real `apply_plan`-created SQLite records, real
    `read_status` / `judge_status`, TEST-injected connection; see the module docstrings for the
    real / fake split). Each test confirms the specific contract 3-3 / 9 (C1-C4) behaviour."""

    def test_completed_state_is_exit_zero(self):
        self.apply()
        out, code = self.status()
        self.assertEqual((out["state"], out["results"], code), ("completed", {"applied": 2}, 0))

    def test_completed_with_conflict_or_blocked_is_exit_five(self):
        cards = [self.past_card("g", iso(NOW - timedelta(days=5))), 999999]   # 999999: card_or_access_missing
        req = cli.make_request(self.user, "mig-replay-blocked", cards, [])
        self.apply(cards, run_key="mig-replay-blocked")
        out, code = self.status(req)
        self.assertEqual((out["state"], out["results"], code), ("completed", {"applied": 1, "blocked": 1}, 5))

    def test_completed_with_a_real_product_conflict_is_exit_five(self):
        # Review correction 1 (point 4): a REAL `migration.apply_plan` conflict, not a fake. A card
        # planned by the real `dry_run` is changed (its own version/fingerprint-bearing columns) by
        # a direct SQL write before the real `apply_plan` runs, so the product's own per-card check
        # (`current != candidate`, migration.py) marks it "conflict" and completes the run anyway.
        conflicting = self.past_card("conflict-card", iso(NOW - timedelta(days=5)))
        unaffected = self.past_card("other-card", iso(NOW - timedelta(days=5)))
        cards = [conflicting, unaffected]
        req = cli.make_request(self.user, "mig-replay-conflict", cards, [])
        plan = migration.dry_run(self.card_keys(cards), connect=self.connect)
        self.sql("UPDATE vocab_items SET correct_count = correct_count + 1 WHERE id = ?", (conflicting,))
        results = migration.apply_plan(plan, "mig-replay-conflict", approved=True, connect=self.connect)
        self.assertEqual(sorted(r["result"] for r in results), ["applied", "conflict"])
        before_dump = self.dump()

        def forbidden(*args, **kwargs):
            raise AssertionError("status must never call apply_plan during a requery")
        with mock.patch.object(migration, "apply_plan", forbidden):
            out, code = self.status(req)
        self.assertEqual((out["state"], out["results"], code), ("completed", {"applied": 1, "conflict": 1}, 5))
        self.assertEqual(self.dump(), before_dump)                # the requery wrote nothing

    def test_cursor_end_not_completed_is_exit_six_and_unchanged(self):
        cards = [self.past_card(n, iso(NOW - timedelta(days=5))) for n in ("e", "f")]
        req = cli.make_request(self.user, "mig-replay-cursor-end", cards, [])
        calls = []

        def finish_fails(*, read_only=False):
            calls.append(read_only)
            if len(calls) == 4:                                  # start, card, card, FINISH connection
                raise RuntimeError("finish connection lost")
            return self.connect(read_only=read_only)
        plan = migration.dry_run(self.card_keys(cards), connect=self.connect)
        with self.assertRaises(RuntimeError):
            migration.apply_plan(plan, "mig-replay-cursor-end", approved=True, connect=finish_fails)
        before = self.run_row("mig-replay-cursor-end")
        out, code = self.status(req)
        self.assertEqual((out["state"], out["cursor"], out["finished"], code),
                         ("cursor_end_not_completed", 2, False, 6))
        after = self.run_row("mig-replay-cursor-end")
        self.assertEqual(after, before)                          # the requery repaired nothing

    def test_malformed_summary_duplicate_key_is_exit_six(self):
        self.apply()
        row = self.run_row()
        duplicated = row["summary_json"].replace('"cursor":2', '"cursor":2,"cursor":1', 1)
        self.assertNotEqual(duplicated, row["summary_json"])
        self.sql("UPDATE srs_migration_runs SET summary_json = ? WHERE id = ?", (duplicated, row["id"]))
        out, code = self.status()
        self.assertEqual((out["state"], out["reason"], code), ("inconsistent", "summary_unreadable", 6))
        self.assertNotIn("cursor", out)
        self.assertEqual(self.run_row()["summary_json"], duplicated)     # the requery repaired nothing

    def test_snapshot_mismatch_of_this_run_is_exit_six(self):
        self.apply()
        row = self.run_row()
        self.sql("DELETE FROM srs_migration_snapshots WHERE run_id = ? AND card_ref = ?", (row["id"], self.cards[0]))
        out, code = self.status()
        self.assertEqual((out["state"], out["reason"], code), ("inconsistent", "snapshot_mismatch", 6))

    def test_unknown_key_and_other_owner_answer_the_same_not_started(self):
        missing, code = self.status()
        self.assertEqual((missing, code), ({"status": "ok", "command": "status", "state": "not_started"}, 0))
        other_cards = [self.personal("o1", user=self.other)]
        self.apply(other_cards, user=self.other)                 # a completed run, but another account's
        self.assertEqual(self.status(), (missing, 0))
        other_req = cli.make_request(self.user, "mig-status-1", other_cards, [])
        self.assertEqual(self.status(other_req), (missing, 0))   # not even with its own card list

    def test_other_accounts_and_out_of_scope_rows_are_unchanged(self):
        self.apply()                                              # self.user's completed run
        other_cards = [self.personal("other-a", user=self.other)]
        self.apply(other_cards, run_key="mig-replay-other-account", user=self.other)
        untouched_card = self.personal("out-of-scope")            # never part of any migration run
        before_other_run = self.run_row("mig-replay-other-account")
        with self.connect(read_only=True) as c:
            before_card = dict(c.execute("SELECT * FROM vocab_items WHERE id = ?", (untouched_card,)).fetchone())
        before_dump = self.dump()
        out, code = self.status()                                 # requery of self.user's run only
        self.assertEqual((out["state"], code), ("completed", 0))
        self.assertEqual(self.dump(), before_dump)                 # the WHOLE logical DB, not just this run
        self.assertEqual(self.run_row("mig-replay-other-account"), before_other_run)
        with self.connect(read_only=True) as c:
            after_card = dict(c.execute("SELECT * FROM vocab_items WHERE id = ?", (untouched_card,)).fetchone())
        self.assertEqual(after_card, before_card)

    def test_no_product_apply_or_resume_call_and_read_only_connection(self):
        self.apply()
        read_only_seen = []
        real_connect = self.connect

        def recording_connect(*, read_only=False):
            read_only_seen.append(read_only)
            return real_connect(read_only=read_only)

        def forbidden(*args, **kwargs):
            raise AssertionError("status must never call apply_plan")
        with mock.patch.object(self, "connect", recording_connect),             mock.patch.object(migration, "apply_plan", forbidden):
            out, code = self.status()
        self.assertEqual((out["state"], code), ("completed", 0))
        self.assertTrue(read_only_seen)
        self.assertTrue(all(read_only_seen))                      # every connection status opened was read-only


if __name__ == "__main__":
    unittest.main()

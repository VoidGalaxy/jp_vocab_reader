"""Gate D-2 U12 follow-up: a compatibility rehearsal for databases that still hold
format-1 snapshot records (records written before U10-a copied the whole card row).

The product no longer writes format 1. Here the records are made by the real
conversion / rollback functions and then stored the way the pre-U10-a code stored
them (the whole card row: the row before the conversion for an apply record, the row
just after the rollback for a rollback record), as historical data. Then:

  real CLI scripts/d2_snapshot_minimize.py: dry run -> apply -> rerun (>= 1 record
  rewritten, rerun 0), followed by rollback in the window, restoring re-conversion,
  follow-up reviews and their version-gap proof, a delayed plan-B first review, the
  U10-e prune after the window and a word delete --

on the minimized database and on an untouched twin, comparing every outcome.

Synthetic SQLite only (QueueCase sets a throwaway DATABASE_URL per test).
Run directly:      python tests/test_srs_d2_u12_format1_compat.py
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_srs_d2_u10d_window import T0, WINDOW  # noqa: E402
from test_srs_d2_u10e_prune import DAY, PruneCase  # noqa: E402
from test_srs_queue import NOW  # noqa: E402

from app.database import get_connection  # noqa: E402
from app.srs import identity, migration, restoration  # noqa: E402
from app.srs.engine import CardKey  # noqa: E402

MINIMIZE = Path(__file__).resolve().parents[1] / "scripts" / "d2_snapshot_minimize.py"


class Format1Compat(PruneCase):
    @contextlib.contextmanager
    def pre_u10a_records(self):
        """Records written while this is open are stored as the pre-U10-a code stored them."""
        real_apply, real_rollback = migration.apply_plan, migration.rollback_plan

        def rows():
            with get_connection() as c:
                out = {("personal", r["id"]): dict(r) for r in c.execute("SELECT * FROM vocab_items")}
                out.update({("lexeme", r["lexeme_id"]): dict(r) for r in c.execute(
                    "SELECT * FROM user_word_progress WHERE user_id = ?", (self.user,))})
            return out

        def last():
            with get_connection() as c:
                return c.execute("SELECT COALESCE(MAX(id), 0) FROM srs_migration_snapshots").fetchone()[0]

        def rewrite(since, before):
            after = rows()
            with get_connection() as c:
                for r in c.execute("SELECT s.id, s.card_kind, s.card_ref, s.legacy_json, r.mode FROM srs_migration_snapshots s "
                                   "JOIN srs_migration_runs r ON r.id = s.run_id WHERE s.id > ?", (since,)).fetchall():
                    payload = json.loads(r["legacy_json"])
                    payload.pop("format", None)
                    # the whole card row, minus the U11 columns the old code could not have had
                    full = (before if r["mode"] == "apply" else after)[(r["card_kind"], r["card_ref"])]
                    payload["card"] = {k: v for k, v in full.items() if k not in (
                        "first_completed_source", "version_first_completed_at", "version_first_completed_version")}
                    c.execute("UPDATE srs_migration_snapshots SET legacy_json = ? WHERE id = ?",
                              (json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False), r["id"]))

        def apply(*a, **k):
            since, before = last(), rows()
            result = real_apply(*a, **k)
            rewrite(since, before)
            return result

        def rollback(*a, **k):
            since = last()
            result = real_rollback(*a, **k)
            rewrite(since, None)
            return result

        with mock.patch.object(migration, "apply_plan", apply), mock.patch.object(migration, "rollback_plan", rollback):
            yield

    def build(self):
        w = {}
        with self.pre_u10a_records():
            w["late"] = self.convert("personal", "late", "run-late", at=T0)  # rolled back later, inside the window
            self.rate_at("personal", w["late"], NOW, "good")
            w["restore"] = self.rolled("personal", "restore", "run-restore", "rbk-restore")
            w["lx"] = self.rolled("lexeme", "lx", "run-lx", "rbk-lx")
            w["pb"], w["pb_at"] = self.plan_b("personal", "pb", "run-pb")
            w["gone"] = self.convert("personal", "gone", "run-gone")
        self.now = NOW
        formats = {json.loads(s["legacy_json"]).get("format", 1) for s in self.snaps().values()}
        self.assertEqual(formats, {1})
        return w

    def cli(self, *extra):
        env = {k: v for k, v in os.environ.items() if k != "DATABASE_URL"}
        env["APP_ENV"] = "test"
        done = subprocess.run([sys.executable, str(MINIMIZE), "--sqlite-db", str(self.db_path), "--user-id", str(self.user),
                               *extra], capture_output=True, text=True, timeout=120, env=env, encoding="utf-8")
        return done.returncode, json.loads(done.stdout) if done.stdout.strip() else done.stderr[-300:]

    def outcomes(self, w):
        out = {}
        self.clock = T0 + 5 * DAY  # inside the window
        out["rollback"] = [r["result"] for r in migration.rollback_plan("run-late", "rbk-late", user_id=self.user,
                                                                        approved=True)]
        out["restore"] = self.reconvert("personal", w["restore"])[2].get("reconversion")
        out["lx_restore"] = self.reconvert("lexeme", w["lx"])[2].get("reconversion")
        self.seen.clear()
        for d in (20, 40):
            self.rate_at("personal", w["restore"], NOW + d * DAY, "good")
        out["proof"] = [complete for _, complete in self.seen]
        with get_connection() as c:
            out["unused_permission"] = restoration.restart_permission(
                c, CardKey("personal", self.user, w["pb"]), self.card_row("personal", w["pb"]), self.logs_of("personal", w["pb"]))
        out["pb_first"] = self.rate_at("personal", w["pb"], w["pb_at"] + 60 * DAY, "good")["srs"]["card_version"]
        out["boundary_pb"] = self.card_row("personal", w["pb"])["evidence_from_log_id"]
        self.now = NOW
        out["sources"] = {k: {c: self.card_row("personal" if k != "lx" else "lexeme", w[k])[c]
                              for c in ("first_completed_at", "first_completed_source", "version_first_completed_at",
                                        "evidence_from_log_id", "srs_card_version")}
                          for k in ("late", "restore", "pb", "lx")}
        self.clock = T0 + WINDOW + 10 * DAY
        pruned, code = self.apply_tool()
        out["prune"] = (code, len(pruned["runs"]["pruned"]), len(pruned["snapshots"]["pruned"]),
                        len(pruned["snapshots"]["protected"]), pruned["snapshots"]["unsupported"])
        import app.database as database  # the delete ledger reads the server clock: the same instant for both
        with mock.patch.object(database, "now_utc", side_effect=lambda: self.clock):
            out["delete"] = self.client.delete(f"/vocab-items/{w['gone']}", headers=self.headers).status_code
        with get_connection() as c:
            out["refs"] = identity.personal_id_references(c)
        out["tables"] = self.tables()
        out["formats_after"] = sorted({json.loads(s["legacy_json"]).get("format", 1) for s in self.snaps().values()})
        return out

    def test_minimize_then_continue_like_the_original(self):
        w = self.build()
        before_snaps, before = self.snaps(), self.everything()
        twin = Path(self.directory.name) / "twin.db"
        shutil.copyfile(self.db_path, twin)
        # real CLI: dry run (no write) -> apply -> rerun
        code, dry = self.cli()
        self.assertEqual(code, 0, dry)
        self.assertEqual((self.snaps(), self.everything()), (before_snaps, before))
        code, applied = self.cli("--apply", "--confirm-user-id", str(self.user))
        self.assertEqual(code, 0, applied)
        rewritten = {e["id"] for e in applied["minimized"]}
        self.assertGreaterEqual(len(rewritten), 1)
        self.assertEqual(rewritten, {e["id"] for e in dry["minimized"]})
        self.assertEqual((applied["unsupported"], applied["insufficient"], applied["conflicts"]), ([], [], []))
        after_snaps = self.snaps()
        for sid, old in before_snaps.items():  # only legacy_json changes, and only for rewritten records
            new = after_snaps[sid]
            self.assertEqual({k: v for k, v in new.items() if k != "legacy_json"},
                             {k: v for k, v in old.items() if k != "legacy_json"})
            if sid in rewritten:
                self.assertEqual(json.loads(new["legacy_json"])["format"], 2)
                self.assertNotIn("-뜻", new["legacy_json"])
            else:
                self.assertEqual(new["legacy_json"], old["legacy_json"])
        after = self.everything()
        self.assertEqual({k: v for k, v in after.items() if k != "srs_migration_snapshots"},
                         {k: v for k, v in before.items() if k != "srs_migration_snapshots"})
        code, rerun = self.cli("--apply", "--confirm-user-id", str(self.user))
        self.assertEqual((code, rerun["minimized"]), (0, []))
        self.assertEqual(self.snaps(), after_snaps)
        # continue the same flows on the minimized database and on the untouched twin
        minimized = self.outcomes(w)
        self.seen.clear()
        main_db, self.db_path = self.db_path, twin  # the operator tool is pointed at the twin file too
        try:
            with mock.patch.dict(os.environ, {"DATABASE_URL": f"sqlite:///{twin.as_posix()}"}):
                original = self.outcomes(w)
        finally:
            self.db_path = main_db
        for key in [k for k in minimized if k != "formats_after"]:
            self.assertEqual(minimized[key], original[key], key)
        self.assertEqual(minimized["rollback"], ["rolled_back"])
        self.assertEqual((minimized["restore"], minimized["lx_restore"]), ("restored", "restored"))
        self.assertTrue(all(minimized["proof"]))
        self.assertIsNotNone(minimized["unused_permission"])
        self.assertEqual(minimized["delete"], 204)
        self.report = {"rewritten": len(rewritten), "rerun": 0, "dry_equals_apply": True, "outcomes_equal": True,
                       "prune": minimized["prune"][:4], "formats_after": minimized["formats_after"],
                       "original_formats_after": original["formats_after"]}
        if os.environ.get("U12_OUT"):
            Path(os.environ["U12_OUT"]).write_text(json.dumps(self.report), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()

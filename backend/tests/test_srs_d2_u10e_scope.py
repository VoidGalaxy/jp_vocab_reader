"""Gate D-2 U10-e review fix: an apply run's scope_json is checked for the VALUES
`_plan_json` writes (types, allowed values, nested structure), not only key names --
before any record of that run is rewritten.

A damaged or unsupported scope (original or reduced) leaves the run's scope and every
record of that run exactly as stored, is reported, and the next runs are processed.
The check never relies on `assert` (same result under `python -O`).

Synthetic SQLite only. Run directly: python tests/test_srs_d2_u10e_scope.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_srs_d2_u10d_window import T0, WINDOW  # noqa: E402
from test_srs_d2_u10e_prune import DAY, PruneCase, SCRIPT  # noqa: E402

from app.database import get_connection  # noqa: E402
from app.srs import migration  # noqa: E402
from app.srs.engine import CardKey  # noqa: E402


def card0(field, value):
    def change(scope):
        scope["cards"][0][field] = value
    return change


def values0(change_values):
    def change(scope):
        values = json.loads(scope["cards"][0]["values"])
        change_values(values)
        scope["cards"][0]["values"] = json.dumps(values)
    return change


def top(field, value):
    def change(scope):
        scope[field] = value
    return change


def drop(field, in_card=False):
    def change(scope):
        (scope["cards"][0] if in_card else scope).pop(field)
    return change


# the six reported cases first
CASES = {
    "config_version null": top("config_version", None),
    "config_version object": top("config_version", {"v": "x"}),
    "config_version with space": top("config_version", "fsrs 6.3.2"),
    "cards[].version object": card0("version", {"v": 1}),
    "cards[].flags text": card0("flags", "missing_history"),
    "cards[].values object": card0("values", {"srs_engine": "fsrs"}),
    # every other field
    "user_id text": top("user_id", "2"),
    "config_version other than the run": top("config_version", "fsrs-other"),
    "extra top key": top("note", "x"),
    "cards missing": drop("cards"),
    "cards not a list": top("cards", {"kind": "personal"}),
    "cards empty": top("cards", []),
    "kind unknown": card0("kind", "deck"),
    "ref_id text": card0("ref_id", "5"),
    "ref_id zero": card0("ref_id", 0),
    "ref_id bool": card0("ref_id", True),
    "card fingerprint uppercase": card0("card", "A" * 64),
    "card fingerprint object": card0("card", {"x": 1}),
    "logs null": card0("logs", None),
    "logs short": card0("logs", "a" * 63),
    "version negative": card0("version", -1),
    "version bool": card0("version", False),
    "quality unknown": card0("quality", "great"),
    "quality null": card0("quality", None),
    "flags item object": card0("flags", [{"f": 1}]),
    "flags item with space": card0("flags", ["two words"]),
    "last_log_id text": card0("last_log_id", "3"),
    "last_log_id negative": card0("last_log_id", -1),
    "card key missing": drop("logs", in_card=True),
    "card extra key": card0("note", 1),
    "values not json": card0("values", "{not json"),
    "values json list": card0("values", "[]"),
    "values unknown key": values0(lambda v: v.update(meaning_ko="x")),
    "values legacy engine": values0(lambda v: v.update(srs_engine="legacy")),
    "values state object": values0(lambda v: v.update(srs_state={"v": 1})),
    "values big stability": values0(lambda v: v.update(srs_stability=10 ** 400)),
    "values other config": values0(lambda v: v.update(srs_config_version="fsrs-other")),
    "values flags text": values0(lambda v: v.update(srs_history_flags="free text")),
    "duplicate card": lambda s: s["cards"].append(dict(s["cards"][0])),
}
REDUCED_CASES = {
    "reduced sha uppercase": top("request_sha256", "A" * 64),
    "reduced config null": top("config_version", None),
    "reduced card extra key": card0("card", "a" * 64),
    "reduced extra key": top("note", 1),
    "reduced format 3": top("format", 3),
}


class ScopeCase(PruneCase):
    def damage(self, key, change):
        with get_connection() as c:
            scope = json.loads(c.execute("SELECT scope_json FROM srs_migration_runs WHERE run_key = ?", (key,)).fetchone()[0])
            change(scope)
            c.execute("UPDATE srs_migration_runs SET scope_json = ? WHERE run_key = ?", (json.dumps(scope), key))

    def mixed(self, cases):
        """Normal and damaged runs interleaved; returns {run key: case name or None}."""
        made = {}
        for i, name in enumerate(cases):
            normal = f"run-ok{i}"
            self.convert("personal", f"ok{i}", normal)
            made[normal] = None
            key = f"run-bad{i}"
            self.convert("personal", f"bad{i}", key)
            made[key] = name
        return made

    def check(self, made, *extra):
        for key, name in made.items():
            if name:
                self.damage(key, CASES[name])
        before_snaps, before_runs = self.snaps(), self.runs()
        bad_ids = {before_runs[k]["id"] for k, n in made.items() if n}
        ok_ids = {before_runs[k]["id"] for k, n in made.items() if not n}
        self.clock = T0 + WINDOW
        dry, code = self.tool(*extra)
        self.assertEqual(code, 0)
        self.assertEqual((self.snaps(), self.runs()), (before_snaps, before_runs))
        for report in (dry, self.apply_tool(*extra)[0]):
            self.assertNotIn("failed", report)
            self.assertEqual({e["id"] for e in report["runs"]["unsupported_scope"]}, bad_ids)
            self.assertEqual({e["id"] for e in report["runs"]["pruned"]}, ok_ids)
            self.assertEqual(report["cursor"], report["upper_id"])
            text = json.dumps(report)
            self.assertNotIn("fsrs 6.3.2", text)
            self.assertNotIn("meaning_ko", text)
        after_snaps, after_runs = self.snaps(), self.runs()
        for key, name in made.items():
            run_id = before_runs[key]["id"]
            record_ids = [i for i, s in before_snaps.items() if s["run_id"] == run_id]
            self.assertTrue(record_ids)
            if name:
                self.assertEqual(after_runs[key], before_runs[key], name)  # scope kept byte for byte
                for i in record_ids:
                    self.assertEqual(after_snaps[i], before_snaps[i], name)  # and every record of the run
            else:
                self.assertEqual(json.loads(after_runs[key]["scope_json"])["format"], 2)
                for i in record_ids:
                    self.assertEqual(json.loads(after_snaps[i]["legacy_json"])["format"], 3)
        again, _ = self.apply_tool(*extra)
        self.assertEqual((again["runs"]["pruned"], again["snapshots"]["pruned"]), ([], []))
        self.assertEqual({e["id"] for e in again["runs"]["unsupported_scope"]}, bad_ids)
        self.assertEqual((self.snaps(), self.runs()), (after_snaps, after_runs))


class DamagedScopeTests(ScopeCase):
    def test_reported_cases_one_batch(self):
        self.check(self.mixed(list(CASES)[:6]))

    def test_every_case_one_run_per_batch(self):
        self.check(self.mixed(list(CASES)), "--batch-size", "1")

    def test_every_case_mixed_batches(self):
        self.check(self.mixed(list(CASES)), "--batch-size", "3")

    def test_damaged_reduced_scope_is_left(self):
        made = {}
        for i, name in enumerate(REDUCED_CASES):
            made[f"run-r{i}"] = name
            self.convert("personal", f"r{i}", f"run-r{i}")
        self.convert("personal", "late-ok", "run-late-ok")
        self.clock = T0 + WINDOW
        self.apply_tool()
        for key, name in made.items():
            self.damage(key, REDUCED_CASES[name])
        before_snaps, before_runs = self.snaps(), self.runs()
        report, code = self.apply_tool()
        self.assertEqual(code, 0)
        self.assertEqual({e["id"] for e in report["runs"]["unsupported_scope"]},
                         {before_runs[k]["id"] for k in made})
        self.assertEqual((self.snaps(), self.runs()), (before_snaps, before_runs))
        # a damaged reduced scope no longer identifies the request: a same-key call conflicts
        self.refused("migration_run_conflict", lambda: migration.apply_plan(self.plans["run-r0"], "run-r0", approved=True))
        # the intact one still answers with its stored results
        before = self.everything()
        self.assertEqual(migration.apply_plan(self.plans["run-late-ok"], "run-late-ok", approved=True)[0]["result"],
                         "already_applied")
        self.assertEqual(self.everything(), before)

    def test_checks_do_not_raise(self):
        run = {"config_version": migration.DEFAULT_CONFIG.config_version}
        for value in (None, 1, "x", [], {"cards": None}, {"user_id": 1, "config_version": None, "cards": [None]},
                      {"user_id": 1, "config_version": "c", "cards": [{"values": "{" * 5000}]}):
            self.assertFalse(migration._full_scope(value, run["config_version"]))
            self.assertFalse(migration._reduced_scope(value, run["config_version"]))


class NormalCandidateTests(ScopeCase):
    def test_null_blocked_unavailable_and_state_none_runs_are_pruned(self):
        done = self.convert("personal", "done", "run-done")  # now already FSRS
        fresh = self.content_card("fresh-incomplete")  # no logs: incomplete, no engine state
        missing = CardKey("personal", self.user, 987654)  # card missing: unavailable, NULL card/version
        plan = migration.dry_run([self.key("personal", done), self.key("personal", fresh), missing])
        self.assertEqual(sorted(p.quality for p in plan), ["already_fsrs", "incomplete", "unavailable"])
        self.clock = T0
        results = migration.apply_plan(plan, "run-mixed", approved=True)
        self.assertEqual(sorted(r["result"] for r in results), ["applied", "blocked", "blocked"])
        ref, _ = self.plan_b("personal", "pbn", "run-pbn")  # plan B re-conversion: state none + restart
        self.clock = T0 + WINDOW
        report, _ = self.apply_tool()
        pruned = {e["id"] for e in report["runs"]["pruned"]}
        runs = self.runs()
        self.assertIn(runs["run-mixed"]["id"], pruned)
        self.assertEqual(report["runs"]["unsupported_scope"], [])
        # the plan-B run is protected (unused permission), not rejected as damaged
        re_key = [k for k in runs if k.startswith(f"re-personal-{ref}-")][0]
        self.assertIn(runs[re_key]["id"], {e["id"] for e in report["runs"]["protected"]})
        # state-none conversion record pruned like any other
        self.assertEqual(report["snapshots"]["unsupported"], [])
        before = self.everything()
        self.clock = T0 + 90 * DAY
        self.assertEqual([r["result"] for r in migration.apply_plan(plan, "run-mixed", approved=True)],
                         [r["result"] if r["result"] != "applied" else "already_applied" for r in results])
        self.assertEqual(self.everything(), before)


class OptimizedCliTests(ScopeCase):
    def test_normal_and_dash_o(self):
        real_now = datetime.now(timezone.utc)
        made = {}
        for i, name in enumerate(list(CASES)[:6]):
            self.convert("personal", f"cliok{i}", f"run-cliok{i}", at=real_now - 40 * DAY)
            self.convert("personal", f"clibad{i}", f"run-clibad{i}", at=real_now - 40 * DAY)
            self.damage(f"run-clibad{i}", CASES[name])
            made[f"run-clibad{i}"] = name
        base = Path(self.db_path)
        copy = base.with_name("dash_o.db")
        import shutil
        shutil.copyfile(base, copy)
        env = {k: v for k, v in os.environ.items() if k != "DATABASE_URL"}
        env["APP_ENV"] = "test"

        def cli(db, *flags):
            done = subprocess.run([sys.executable, *flags, str(SCRIPT), "--sqlite-db", str(db), "--user-id", str(self.user),
                                   "--apply", "--confirm-user-id", str(self.user), "--batch-size", "4"],
                                  capture_output=True, text=True, timeout=120, env=env, encoding="utf-8")
            return done.returncode, json.loads(done.stdout) if done.stdout.strip() else done.stderr[-400:]

        plain = cli(base)
        optimized = cli(copy, "-O")
        self.assertEqual(plain[0], 0, plain[1])
        self.assertEqual(optimized[0], 0, optimized[1])
        for part in ("runs", "snapshots"):
            self.assertEqual(plain[1][part], optimized[1][part])
        runs = self.runs()
        self.assertEqual({e["id"] for e in plain[1]["runs"]["unsupported_scope"]}, {runs[k]["id"] for k in made})
        self.assertEqual(len(plain[1]["runs"]["pruned"]), 6)
        self.assertEqual(plain[1]["cursor"], plain[1]["upper_id"])
        again = cli(base)
        self.assertEqual((again[0], again[1]["runs"]["pruned"]), (0, []))


if __name__ == "__main__":
    unittest.main()

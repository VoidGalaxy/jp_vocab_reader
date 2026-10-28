"""Gate D-2 U10-e: the tool that removes rollback-only values after an apply run's
rollback window (scripts/d2_snapshot_prune.py -> migration.prune_expired_runs).

Apply records become format 3 (identity, version, srs_engine, last_log_id, restart);
the run's scope_json keeps account / card references and a SHA-256 of the original
request. Everything else is kept. The server clock seen by migration is controlled by
the test (WindowCase). Synthetic SQLite only.

Run directly:      python tests/test_srs_d2_u10e_prune.py
Or via discovery:   python -m unittest discover -s tests
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_srs_d2_u10d_window import TICK, T0, WINDOW, WindowCase  # noqa: E402
from test_srs_queue import NOW, iso  # noqa: E402
import race_support  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import d2_snapshot_minimize  # noqa: E402
import d2_snapshot_prune  # noqa: E402

from app.database import get_connection  # noqa: E402
from app.repositories import vocab_repository  # noqa: E402
from app.srs import identity, migration, reviews, storage  # noqa: E402
from app.srs.storage import SrsWriteError  # noqa: E402

DAY = timedelta(days=1)
SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "d2_snapshot_prune.py"
UNTOUCHED = ("vocab_items", "user_word_progress", "review_logs", "lexeme_review_logs", "srs_review_receipts",
             "srs_card_deletions", "srs_evidence_restarts", "srs_card_identity_flags")


class PruneCase(WindowCase):
    def setUp(self):
        super().setUp()
        self._lx = 0
        self.plans = {}

    # -- building ----------------------------------------------------------------------
    def convert(self, kind, name, key, at=T0):
        self.clock = at
        if kind == "personal":
            ref = self.content_card(name)
        else:
            self._lx += 1
            self._deck = getattr(self, "_deck", None) or self.shared_deck("prune")
            ref = self.lexeme(name, self._deck, self._lx)
            with get_connection() as c:
                c.execute("UPDATE user_word_progress SET srs_engine = 'legacy', srs_config_version = NULL, "
                          "srs_participation = NULL, srs_history_quality = NULL, last_reviewed_at = ?, correct_count = 1, "
                          "next_review_at = ? WHERE user_id = ? AND lexeme_id = ?",
                          (iso(NOW - 9 * DAY), iso(NOW - timedelta(hours=1)), self.user, ref))
        plan = migration.dry_run([self.key(kind, ref)])
        self.plans[key] = plan
        self.assertEqual(migration.apply_plan(plan, key, approved=True)[0]["result"], "applied")
        return ref

    def deck_of(self, kind):
        return self._deck if kind == "lexeme" else None

    def rolled(self, kind, name, key, rb_key, at=T0):
        ref = self.convert(kind, name, key, at)
        self.rate_at(kind, ref, NOW, "good", deck=self.deck_of(kind))
        self.now = NOW
        self.clock = at
        self.assertEqual(migration.rollback_plan(key, rb_key, user_id=self.user, approved=True)[0]["result"],
                         "rolled_back")
        return ref

    def plan_b(self, kind, name, key, at=T0, rollback_at=None):
        """convert -> reviews -> rollback -> legacy change -> plan-B re-conversion (unused)."""
        ref = self.convert(kind, name, key, at)
        when = self.old_window(kind, ref, self.deck_of(kind))
        self.clock = rollback_at or at
        self.assertEqual(migration.rollback_plan(key, f"rb-{key}", user_id=self.user, approved=True)[0]["result"],
                         "rolled_back")
        self.legacy_change(kind, ref, when + DAY, self.deck_of(kind))
        _, _, result = self.reconvert(kind, ref)
        self.assertEqual(result["reconversion"], "state_none_restart")
        return ref, when + 3 * DAY

    def partial(self, name, key, fail=False):
        refs = [self.content_card(f"{name}{i}") for i in range(3)]
        plan = self.plan_of(refs)
        self.plans[key] = plan
        self.clock = T0
        if fail:
            real, calls = migration.update_card, {"n": 0}

            def failing(*a, **k):
                calls["n"] += 1
                if calls["n"] == 2:
                    raise RuntimeError("synthetic")
                return real(*a, **k)

            with mock.patch.object(migration, "update_card", failing), self.assertRaises(RuntimeError):
                migration.apply_plan(plan, key, approved=True, batch_size=3)
        else:
            migration.apply_plan(plan, key, approved=True, batch_size=1)
        return refs

    def world(self):
        w = {"p": self.convert("personal", "p", "run-p"), "lx": self.convert("lexeme", "lx", "run-lx"),
             "rb": self.rolled("personal", "rb", "run-rb", "rbk-rb"),
             "lxrb": self.rolled("lexeme", "lxrb", "run-lxrb", "rbk-lxrb")}
        w["pb"], w["pb_at"] = self.plan_b("personal", "pb", "run-pb")
        w["started"] = self.partial("st", "run-st")
        w["failed"] = self.partial("fl", "run-fl", fail=True)
        self.assertEqual(self.run_row("run-st")["status"], "started")
        self.assertEqual(self.run_row("run-fl")["status"], "failed")
        self.assertEqual(self.run_row("run-rb")["status"], "aborted")
        return w

    # -- observing ---------------------------------------------------------------------
    def tool(self, *extra, user=None, script=d2_snapshot_prune):
        printed = []
        with mock.patch.object(script, "print", side_effect=lambda text, **k: printed.append(text)):
            try:
                result = script.main(["--sqlite-db", str(self.db_path), "--user-id", str(user or self.user), *extra])
            except SystemExit as stop:
                return (json.loads(printed[-1]) if printed else None), stop.code
        return result, 0

    def apply_tool(self, *extra):
        return self.tool("--apply", "--confirm-user-id", str(self.user), *extra)

    def snaps(self):
        with get_connection() as c:
            return {r["id"]: dict(r) for r in c.execute(
                "SELECT s.*, r.mode, r.run_key FROM srs_migration_snapshots s JOIN srs_migration_runs r ON r.id = s.run_id "
                "ORDER BY s.id")}

    def runs(self):
        with get_connection() as c:
            return {r["run_key"]: dict(r) for r in c.execute("SELECT * FROM srs_migration_runs ORDER BY id")}

    def tables(self):
        everything = self.everything()
        return {t: everything[t] for t in UNTOUCHED if t in everything}

    def no_content(self, report):
        text = json.dumps(report, ensure_ascii=False)
        for word in ("뜻", "例文", "よみ", "문맥", "sha256\":", "request_sha256\": \""):
            self.assertNotIn(word, text)


# ---------------------------------------------------------------------------
class ContractTests(PruneCase):
    def test_boundary_dry_run_apply_rerun(self):
        w = self.world()
        before_snaps, before_runs, before_tables = self.snaps(), self.runs(), self.tables()
        self.clock = T0 + WINDOW - TICK
        report, code = self.apply_tool()
        self.assertEqual((code, report["runs"]["pruned"], report["snapshots"]["pruned"]), (0, [], []))
        self.assertEqual((self.snaps(), self.runs()), (before_snaps, before_runs))
        self.clock = T0 + WINDOW + timedelta(seconds=1)
        later, _ = self.tool()
        self.clock = T0 + WINDOW
        dry, code = self.tool()
        self.assertEqual(code, 0)
        self.assertEqual((later["runs"], later["snapshots"]), (dry["runs"], dry["snapshots"]))  # just after = at
        self.assertEqual((self.snaps(), self.runs(), self.tables()), (before_snaps, before_runs, before_tables))
        applied, code = self.apply_tool()
        self.assertEqual(code, 0)
        for part in ("runs", "snapshots"):
            self.assertEqual(applied[part], dry[part], part)  # dry run predicted exactly
        self.no_content(applied)
        after_snaps, after_runs = self.snaps(), self.runs()
        self.assertEqual(self.tables(), before_tables)  # cards, logs, receipts, restarts, ledger, flags
        pruned_ids = {e["id"] for e in applied["snapshots"]["pruned"]}
        protected = {e["id"] for e in applied["snapshots"]["protected"]}
        pb_latest = max(i for i, s in before_snaps.items() if s["card_ref"] == w["pb"] and s["mode"] == "apply")
        self.assertEqual(protected, {pb_latest})
        for sid, old in before_snaps.items():
            new = after_snaps[sid]
            self.assertEqual({k: v for k, v in new.items() if k != "legacy_json"},
                             {k: v for k, v in old.items() if k != "legacy_json"})  # columns, times, srs JSON
            if sid not in pruned_ids:
                self.assertEqual(new["legacy_json"], old["legacy_json"])  # rollback records, protected, ...
                continue
            self.assertEqual(old["mode"], "apply")
            payload, prev = json.loads(new["legacy_json"]), json.loads(old["legacy_json"])
            kind = old["card_kind"]
            self.assertEqual(payload["format"], 3)
            self.assertEqual(payload["card"], {k: prev["card"][k] for k in migration.PRUNED_APPLY_CARD_FIELDS[kind]})
            for key in ("last_log_id", "restart"):
                self.assertEqual(payload.get(key), prev.get(key))
            self.assertFalse(set(payload["card"]) & set(migration.PRUNED_AWAY))
        self.assertEqual(sorted(applied["removed_card_fields"]),
                         sorted(set(migration.PRUNED_AWAY) | ({"base_form", "surface"} & set(applied["removed_card_fields"]))
                                | (set(applied["removed_card_fields"]) - set(migration.PRUNED_AWAY))))
        self.assertTrue(set(migration.PRUNED_AWAY) <= set(applied["removed_card_fields"]))
        # runs: everything but the apply scope is kept; protected parent keeps its scope too
        pruned_runs = {e["id"] for e in applied["runs"]["pruned"]}
        for key, old in before_runs.items():
            new = after_runs[key]
            self.assertEqual({k: v for k, v in new.items() if k != "scope_json"},
                             {k: v for k, v in old.items() if k != "scope_json"})
            if old["id"] in pruned_runs:
                scope, prev = json.loads(new["scope_json"]), json.loads(old["scope_json"])
                self.assertEqual(scope["request_sha256"], hashlib.sha256(old["scope_json"].encode()).hexdigest())
                self.assertEqual(scope["cards"], [{"kind": c["kind"], "ref_id": c["ref_id"]} for c in prev["cards"]])
                self.assertEqual((scope["user_id"], scope["config_version"]), (prev["user_id"], prev["config_version"]))
            else:
                self.assertEqual(new["scope_json"], old["scope_json"])
        self.assertEqual({k for k, r in before_runs.items() if r["id"] in pruned_runs},
                         {"run-p", "run-lx", "run-rb", "run-lxrb", "run-pb", "run-st", "run-fl"})
        self.assertEqual([e["id"] for e in applied["runs"]["protected"]],
                         [before_runs[k]["id"] for k in before_runs if k.startswith("re-personal-")])
        with get_connection() as c:
            identity.personal_id_references(c)
        again, code = self.apply_tool()
        self.assertEqual((code, again["runs"]["pruned"], again["snapshots"]["pruned"]), (0, [], []))
        self.assertEqual(again["snapshots"]["already_pruned"], len(pruned_ids))
        self.assertEqual(again["runs"]["already_pruned"], len(pruned_runs))
        self.assertEqual((self.snaps(), self.runs()), (after_snaps, after_runs))
        # the U10-b tool and the delete path read format 3 as normal and leave it
        minimized, _ = self.tool("--apply", "--confirm-user-id", str(self.user), script=d2_snapshot_minimize)
        self.assertEqual((minimized["unsupported"], minimized["insufficient"]), ([], []))
        self.assertFalse({e["id"] for e in minimized["minimized"]} & pruned_ids)  # only format-1 leftovers
        now_snaps = self.snaps()
        self.assertEqual({i: now_snaps[i] for i in pruned_ids}, {i: after_snaps[i] for i in pruned_ids})
        after_snaps = now_snaps
        ids = {sid for sid, s in after_snaps.items() if s["card_ref"] == w["p"] and s["card_kind"] == "personal"}
        self.assertEqual(self.client.delete(f"/vocab-items/{w['p']}", headers=self.headers).status_code, 204)
        self.assertEqual({sid for sid, s in self.snaps().items() if sid in ids},
                         ids)  # kept, not deleted as unsupported
        self.assertEqual(self.client.delete(f"/decks/{self.deck}", headers=self.headers).status_code, 200)

    def test_same_key_calls_keep_their_answers(self):
        w = self.world()
        self.clock = T0 + DAY
        apply_before = migration.apply_plan(self.plans["run-p"], "run-p", approved=True)
        rollback_before = migration.rollback_plan("run-rb", "rbk-rb", user_id=self.user, approved=True)
        self.clock = T0 + WINDOW
        self.apply_tool()
        self.assertEqual(json.loads(self.runs()["run-p"]["scope_json"])["format"], 2)  # reduced
        for at in (T0 + WINDOW, T0 + 90 * DAY):
            self.clock = at
            before = self.everything()
            self.assertEqual(migration.apply_plan(self.plans["run-p"], "run-p", approved=True), apply_before)
            self.assertEqual(migration.rollback_plan("run-rb", "rbk-rb", user_id=self.user, approved=True),
                             rollback_before)
            self.assertEqual(self.everything(), before)
            self.refused("migration_run_conflict",
                         lambda: migration.apply_plan(self.plans["run-lx"], "run-p", approved=True))
            self.refused("migration_run_conflict",
                         lambda: migration.rollback_plan("run-p", "rbk-rb", user_id=self.user, approved=True))
            # partial runs: still their own request, still refused for resuming
            self.refused("migration_resume_window_closed",
                         lambda: migration.apply_plan(self.plans["run-st"], "run-st", approved=True))
            self.refused("migration_run_conflict",
                         lambda: migration.apply_plan(self.plans["run-fl"], "run-st", approved=True))

    def test_unverifiable_and_damaged_are_left(self):
        w = self.world()
        self.set_started("run-lx", "2026-10-09T03:00:00")  # no time zone
        self.set_started("run-st", iso(T0 + 400 * DAY))  # future
        snaps = self.snaps()
        damaged = min(i for i, s in snaps.items() if s["run_key"] == "run-p")
        payload = json.loads(snaps[damaged]["legacy_json"])
        payload["card"].pop("srs_state")
        with get_connection() as c:
            c.execute("UPDATE srs_migration_snapshots SET legacy_json = ? WHERE id = ?", (json.dumps(payload), damaged))
            odd = c.execute("SELECT id FROM srs_migration_runs WHERE run_key = 'run-fl'").fetchone()[0]
            scope = json.loads(c.execute("SELECT scope_json FROM srs_migration_runs WHERE id = ?", (odd,)).fetchone()[0])
            scope["note"] = "x"
            c.execute("UPDATE srs_migration_runs SET scope_json = ? WHERE id = ?", (json.dumps(scope), odd))
        before_snaps, before_runs = self.snaps(), self.runs()
        self.clock = T0 + WINDOW + DAY
        report, code = self.apply_tool()
        self.assertEqual(code, 0)
        self.assertEqual({e["id"] for e in report["runs"]["unverifiable"]},
                         {before_runs["run-lx"]["id"], before_runs["run-st"]["id"]})
        self.assertEqual([e["id"] for e in report["snapshots"]["insufficient"]], [damaged])
        self.assertEqual([e["id"] for e in report["runs"]["unsupported_scope"]], [odd])
        after_snaps, after_runs = self.snaps(), self.runs()
        for key in ("run-lx", "run-st", "run-fl"):
            self.assertEqual(after_runs[key]["scope_json"], before_runs[key]["scope_json"])
        for sid, s in before_snaps.items():
            if s["run_key"] in ("run-lx", "run-st") or sid == damaged:
                self.assertEqual(after_snaps[sid], s)
        self.assertEqual(json.loads(after_snaps[damaged]["legacy_json"]), payload)

    def test_used_permission_is_pruned_and_old_one_stays_dead(self):
        ref, at = self.plan_b("personal", "used", "run-used")
        self.rate_at("personal", ref, at, "good")  # uses the permission
        self.now = NOW
        used = self.records("personal", ref)[-1]
        self.assertEqual(len(self.restarts("personal", ref)), 1)
        self.clock = T0 + WINDOW
        report, _ = self.apply_tool()
        self.assertIn(used["id"], {e["id"] for e in report["snapshots"]["pruned"]})
        self.assertEqual(self.payload(self.records("personal", ref)[-1])["restart"], self.payload(used)["restart"])
        from app.srs import restoration
        with get_connection() as c:
            self.assertIsNone(restoration.restart_permission(c, self.key("personal", ref), self.card_row("personal", ref),
                                                             self.logs_of("personal", ref)))


class ContractFormat1Tests(ContractTests):
    FORMAT1 = True


# ---------------------------------------------------------------------------
class TwinTests(PruneCase):
    def build(self):
        w = {}
        w["restore"] = self.rolled("personal", "restore", "run-restore", "rbk-restore")
        # repeated plan B: original run at T0 (expires), plan B made inside the window
        w["rep"], w["rep_at"] = self.plan_b("personal", "rep", "run-rep", rollback_at=T0 + 20 * DAY)
        w["old_pb"], w["old_pb_at"] = self.plan_b("personal", "oldpb", "run-oldpb")
        # version-gap proof: restore inside the window, then reviews after the prune
        w["gap"] = self.rolled("personal", "gap", "run-gap", "rbk-gap", at=T0)
        self.clock = T0 + DAY
        self.assertEqual(self.reconvert("personal", w["gap"])[2]["reconversion"], "restored")
        return w

    def outcomes(self, w):
        out = {}
        self.clock = T0 + WINDOW + DAY
        out["restore"] = self.reconvert("personal", w["restore"])[2].get("reconversion")
        rep_run = [k for k in self.runs() if k.startswith(f"re-personal-{w['rep']}-")][-1]
        out["rep_rollback"] = [r["result"] for r in migration.rollback_plan(rep_run, "rb-rep-again", user_id=self.user,
                                                                           approved=True)]
        out["rep_reconvert"] = self.reconvert("personal", w["rep"])[2].get("reconversion")
        out["rep_first"] = self.rate_at("personal", w["rep"], w["rep_at"] + 30 * DAY, "good")
        out["old_pb_first"] = self.rate_at("personal", w["old_pb"], w["old_pb_at"] + 60 * DAY, "good")
        self.seen.clear()
        self.rate_at("personal", w["gap"], NOW + 50 * DAY, "good")
        self.rate_at("personal", w["gap"], NOW + 60 * DAY, "good")
        out["gap_proof"] = list(self.seen)
        self.now = NOW
        with get_connection() as c:
            out["refs"] = identity.personal_id_references(c)
        out["tables"] = self.tables()
        out["restarts"] = self.restarts()
        return out

    def test_results_match_with_and_without_pruning(self):
        w = self.build()
        twin = Path(self.directory.name) / "twin.db"
        shutil.copyfile(self.db_path, twin)
        self.clock = T0 + WINDOW + DAY
        report, _ = self.apply_tool()
        self.assertTrue(report["snapshots"]["pruned"])
        self.assertTrue(report["snapshots"]["protected"])  # old unused plan-B permission kept
        pruned = self.outcomes(w)
        self.seen.clear()
        with mock.patch.dict(os.environ, {"DATABASE_URL": f"sqlite:///{twin.as_posix()}"}):
            original = self.outcomes(w)
        self.assertEqual(pruned, original)
        self.assertEqual(pruned["rep_reconvert"], "restored")
        self.assertTrue(pruned["gap_proof"][-1][1])


class TwinFormat1Tests(TwinTests):
    FORMAT1 = True


# ---------------------------------------------------------------------------
class BatchTests(PruneCase):
    def many(self, n):
        return [self.convert("personal", f"m{i}", f"run-m{i}") for i in range(n)]

    def run_ids(self):
        return sorted(r["id"] for k, r in self.runs().items() if k.startswith("run-m"))

    def test_failure_rolls_back_the_batch_and_resume_finishes(self):
        self.many(5)
        ids = self.run_ids()
        before_snaps, before_runs = self.snaps(), self.runs()
        real, calls = migration._full_scope, {"n": 0}

        def failing(*a):
            calls["n"] += 1
            if calls["n"] == 3:  # batch 2, first run's scope check (batch 1 already committed)
                raise RuntimeError("synthetic failure")
            return real(*a)

        self.clock = T0 + WINDOW
        with mock.patch.object(migration, "_full_scope", failing):
            report, code = self.apply_tool("--batch-size", "2")
        self.assertEqual((code, report["failed"], report["cursor"]), (1, "RuntimeError", ids[1]))
        runs = self.runs()
        for key, old in before_runs.items():
            if old["id"] > ids[1]:
                self.assertEqual(runs[key], old)
        for sid, s in self.snaps().items():
            if before_runs[s["run_key"]]["id"] > ids[1]:
                self.assertEqual(s, before_snaps[sid])
        resumed, code = self.apply_tool("--batch-size", "2", "--after-id", str(report["cursor"]))
        self.assertEqual((code, len(resumed["runs"]["pruned"])), (0, 3))
        again, _ = self.apply_tool()
        self.assertEqual((again["runs"]["pruned"], again["snapshots"]["pruned"]), ([], []))

    def test_conflicts_are_reported_left_and_reprocessed(self):
        self.many(2)
        ids = self.run_ids()
        holder = {"snap": False, "scope": False}
        real_cols, real_full, real_prune = migration._srs_columns_shape, migration._full_scope, migration.prune_expired_runs

        def wrapped(connection, *a, **k):
            holder["conn"] = connection
            return real_prune(connection, *a, **k)

        def cols(mode, before, after):
            result = real_cols(mode, before, after)
            if not holder["snap"]:
                holder["snap"] = True
                holder["conn"].execute("UPDATE srs_migration_snapshots SET srs_after_json = srs_after_json || ' ' "
                                       "WHERE run_id = ?", (ids[0],))
            return result

        def full(*a):
            result = real_full(*a)
            if not holder["scope"] and result:
                holder["scope"] = True
                holder["conn"].execute("UPDATE srs_migration_runs SET scope_json = scope_json || ' ' WHERE id = ?",
                                       (ids[1],))
            return result

        self.clock = T0 + WINDOW
        with mock.patch.object(migration, "prune_expired_runs", wrapped), \
                mock.patch.object(migration, "_srs_columns_shape", cols), mock.patch.object(migration, "_full_scope", full):
            report, code = self.apply_tool()
        self.assertEqual(code, 0)
        self.assertEqual(len(report["snapshots"]["conflicts"]), 1)
        self.assertEqual([e["id"] for e in report["runs"]["conflicts"]], [ids[1]])
        again, _ = self.apply_tool()
        self.assertEqual(len(again["snapshots"]["pruned"]), 1)
        self.assertEqual([e["id"] for e in again["runs"]["pruned"]], [ids[1]])

    def test_runs_added_during_the_run_are_left_for_later(self):
        self.many(1)
        source = self.runs()["run-m0"]
        real_window, real_prune, holder = migration.rollback_window, migration.prune_expired_runs, {}

        def wrapped(connection, *a, **k):
            holder["conn"] = connection
            return real_prune(connection, *a, **k)

        def adding(started, now):
            if "new" not in holder:
                c = holder["conn"]
                holder["new"] = c.execute(
                    "INSERT INTO srs_migration_runs (run_key, mode, status, scope_json, engine, library_version, "
                    "config_version, started_at) SELECT 'run-late', mode, status, scope_json, engine, library_version, "
                    "config_version, started_at FROM srs_migration_runs WHERE id = ? RETURNING id", (source["id"],)
                ).fetchone()["id"]
                c.execute("INSERT INTO srs_migration_snapshots (run_id, user_id, card_kind, card_ref, card_version_before, "
                          "legacy_json, srs_before_json, srs_after_json, history_quality, history_flags, created_at) "
                          "SELECT ?, user_id, card_kind, card_ref, card_version_before, legacy_json, srs_before_json, "
                          "srs_after_json, history_quality, history_flags, created_at FROM srs_migration_snapshots "
                          "WHERE run_id = ?", (holder["new"], source["id"]))
            return real_window(started, now)

        self.clock = T0 + WINDOW
        with mock.patch.object(migration, "prune_expired_runs", wrapped), mock.patch.object(migration, "rollback_window", adding):
            report, _ = self.apply_tool()
        self.assertEqual(report["upper_id"], source["id"])
        self.assertNotIn(holder["new"], {e["id"] for e in report["runs"]["pruned"]})
        self.assertNotIn("format", json.loads(self.runs()["run-late"]["scope_json"]))
        later, _ = self.apply_tool()
        self.assertEqual([e["id"] for e in later["runs"]["pruned"]], [holder["new"]])


# ---------------------------------------------------------------------------
class RealCliTests(PruneCase):
    def test_subprocess(self):
        real_now = datetime.now(timezone.utc)
        self.many_at(real_now - 40 * DAY)
        before_snaps, before_runs = self.snaps(), self.runs()
        env = {k: v for k, v in os.environ.items() if k != "DATABASE_URL"}
        env["APP_ENV"] = "test"

        def cli(*extra):
            done = subprocess.run([sys.executable, str(SCRIPT), "--sqlite-db", str(self.db_path), "--user-id",
                                   str(self.user), *extra], capture_output=True, text=True, timeout=120, env=env,
                                  encoding="utf-8")
            return done.returncode, (json.loads(done.stdout) if done.stdout.strip() else None), done.stdout + done.stderr

        code, dry, out = cli("--batch-size", "2")
        self.assertEqual(code, 0, out[-400:])
        self.assertEqual((self.snaps(), self.runs()), (before_snaps, before_runs))
        self.assertEqual(cli("--apply")[0], 2)
        self.assertEqual(cli("--apply", "--confirm-user-id", str(self.other))[0], 2)
        self.assertEqual((self.snaps(), self.runs()), (before_snaps, before_runs))
        code, applied, out = cli("--batch-size", "2", "--apply", "--confirm-user-id", str(self.user))
        self.assertEqual(code, 0, out[-400:])
        self.assertEqual((applied["runs"], applied["snapshots"]), (dry["runs"], dry["snapshots"]))
        self.assertEqual(applied["cursor"], applied["upper_id"])
        self.assertEqual(len(applied["runs"]["pruned"]), 3)
        for word in ("뜻", "例文", "よみ"):
            self.assertNotIn(word, out)
        code, again, _ = cli("--apply", "--confirm-user-id", str(self.user))
        self.assertEqual((code, again["runs"]["pruned"], again["snapshots"]["pruned"]), (0, [], []))

    def many_at(self, at):
        for i in range(3):
            self.convert("personal", f"cli{i}", f"run-cli{i}", at=at)


# ---------------------------------------------------------------------------
class RaceTests(PruneCase):
    def race(self, first, second, jobs, target, name):
        entered, release = threading.Event(), threading.Event()
        real = getattr(target, name)

        def slow(*a, **k):
            result = real(*a, **k)
            if not entered.is_set() and threading.current_thread().name == first:
                entered.set()
                self.assertTrue(release.wait(15))
            return result

        with race_support.LockProbe() as probe, mock.patch.object(target, name, slow):
            a = race_support.start(first, jobs[first])
            self.assertTrue(entered.wait(15))
            b = race_support.start(second, jobs[second])
            self.assertTrue(probe.wait("waiting", second))
            time.sleep(0.3)
            self.assertNotIn(("acquired", second), probe.events)
            probe.mark("released", first)
            release.set()
            results = {first: race_support.finish(self, a), second: race_support.finish(self, b)}
        probe.assert_serialized(self, first, second)
        return results

    def tool_job(self):
        def run():
            with get_connection() as connection:
                return migration.prune_expired_runs(connection, self.user, apply=True,
                                                    lock=lambda c, u: storage.begin_card_write(c, u))
        return run

    def op(self, name, tag):
        """(job, block point, card ref, run key of the expired record the tool should prune)"""
        if name == "review":
            ref = self.convert("personal", f"rv-{tag}", f"run-rv-{tag}")
            version = self.card_row("personal", ref)["srs_card_version"]

            def job():
                with mock.patch.object(reviews, "now_utc", return_value=NOW + 3 * DAY):
                    return vocab_repository.record_review(self.user, ref, "good", request_id=f"race-rv-{tag}",
                                                          expected_card_version=version, session_id="s1")
            return job, (reviews, "introduced_on"), ref
        if name == "plan_b":
            ref, at = self.plan_b("personal", f"pb-{tag}", f"run-pbr-{tag}")
            version = self.card_row("personal", ref)["srs_card_version"]

            def job():
                with mock.patch.object(reviews, "now_utc", return_value=at + 40 * DAY):
                    return vocab_repository.record_review(self.user, ref, "good", request_id=f"race-pb-{tag}",
                                                          expected_card_version=version, session_id="s1")
            return job, (reviews, "introduced_on"), ref
        if name == "rollback":
            ref = self.convert("personal", f"rb-{tag}", f"run-rbr-{tag}", at=T0 + 35 * DAY)  # still open
            self.convert("personal", f"rbold-{tag}", f"run-rbold-{tag}")  # expired, for the tool
            return (lambda: migration.rollback_plan(f"run-rbr-{tag}", f"rbk-rbr-{tag}", user_id=self.user,
                                                    approved=True), (migration, "_rollback_input"), ref)
        if name == "reconvert":
            ref = self.rolled("personal", f"re-{tag}", f"run-rer-{tag}", f"rbk-rer-{tag}")
            plan = migration.dry_run([self.key("personal", ref)])
            return (lambda: migration.apply_plan(plan, f"re-race-{tag}", approved=True), (migration, "record_intro"), ref)
        ref = self.convert("personal", f"del-{tag}", f"run-del-{tag}")
        return (lambda: vocab_repository.delete_vocab_item(self.user, ref), (migration, "strip_card_snapshots"), ref)

    def check(self, name, first):
        job, block, ref = self.op(name, first)
        self.clock = T0 + 40 * DAY
        jobs = {"tool": self.tool_job(), name: job}
        target = (migration, "_record_shape") if first == "tool" else block
        second = name if first == "tool" else "tool"
        results = self.race(first, second, jobs, *target)
        report = results["tool"]
        self.assertEqual((report["runs"]["conflicts"], report["snapshots"]["conflicts"]), ([], []))
        for sid, s in self.snaps().items():
            if s["card_ref"] == ref and s["card_kind"] == "personal" and s["mode"] == "apply" \
                    and s["run_key"].startswith("run-") and s["run_key"] != f"run-rbr-{first}":
                fmt = json.loads(s["legacy_json"]).get("format")
                protected = sid in {e["id"] for e in report["snapshots"]["protected"]}
                self.assertEqual(fmt, 2 if protected else 3, (name, first, sid))
        return results

    def test_review(self):
        for first in ("tool", "review"):
            with self.subTest(first=first):
                self.assertEqual(self.check("review", first)["review"]["card_kind"], "personal")

    def test_plan_b_first_review(self):
        for first in ("tool", "plan_b"):
            with self.subTest(first=first):
                results = self.check("plan_b", first)
                self.assertEqual(results["plan_b"]["card_kind"], "personal")

    def test_rollback(self):
        for first in ("tool", "rollback"):
            with self.subTest(first=first):
                self.assertEqual(self.check("rollback", first)["rollback"][0]["result"], "rolled_back")

    def test_reconvert(self):
        for first in ("tool", "reconvert"):
            with self.subTest(first=first):
                self.assertEqual(self.check("reconvert", first)["reconvert"][0]["reconversion"], "restored")

    def test_delete(self):
        for first in ("tool", "delete"):
            with self.subTest(first=first):
                self.assertTrue(self.check("delete", first)["delete"])


if __name__ == "__main__":
    unittest.main()

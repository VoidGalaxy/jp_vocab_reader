"""P-RB recovery tool unit 1 (P_RB_TOOL_CONTRACT.md): precheck, plan fingerprint, preview,
step A, resume status, release closing the record, CLI token handling. Synthetic SQLite here;
the same checks run on the protected local PostgreSQL from test_p_rb_recovery_real.py.
No recovery (step B), mode switch, verify or completed release is exercised: none exists."""

from __future__ import annotations

import hashlib
import io
import json
import os
import sys
import tempfile
import unittest
import threading
from contextlib import ExitStack, contextmanager, redirect_stdout
from datetime import timedelta
from pathlib import Path
from unittest import mock

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import _e5c_support as s  # noqa: E402
from test_p_rb_account_blocks import HoldThenWait  # noqa: E402

TOKEN = "prb-synthetic-recovery-token-0123456789abcdef"
OTHER_TOKEN = "prb-synthetic-recovery-token-fedcba9876543210"
KEY = "prb-rec-1"
DATA_TABLES = ("vocab_items", "user_word_progress", "review_logs", "lexeme_review_logs", "srs_migration_runs",
               "srs_migration_snapshots", "srs_user_settings", "srs_card_deletions", "srs_card_identity_flags",
               "srs_review_receipts")


def sql(query, params=()):
    from app.database import get_connection

    with get_connection() as c:
        cursor = c.execute(query, params)
        return [dict(r) for r in cursor.fetchall()] if cursor.description else []


class RecoveryChecks:
    db_kind = "sqlite"

    def reset_world(self):
        """A fresh, empty database for one sub-case (overridden on PG)."""
        from app.database import init_db

        self._worlds = getattr(self, "_worlds", 0) + 1
        path = Path(self._directory.name) / f"synthetic-{self._worlds}.db"
        env = mock.patch.dict(os.environ, {"DATABASE_URL": f"sqlite:///{path.as_posix()}"})
        env.start()
        self.addCleanup(env.stop)
        init_db()

    def waiting_probe(self):
        return s.sqlite_waiting_probe()

    # ---- world ------------------------------------------------------------------------------
    def world(self, n=2, tag="r"):
        from _e5b_fixture import card, set_mode
        from app.repositories import deck_repository as decks, user_repository as users
        from app.repositories import vocab_repository as vocab
        from app.schemas import DeckCreate

        self.U = users.create_user(f"rec-{tag}@e5b.example.test", "rec", "synthetic")["id"]
        self.deck = decks.create_deck(self.U, DeckCreate(name="u-deck"))[0]["id"]
        set_mode(self.U, "legacy")
        self.cards = [card(self.U, self.deck, f"rec-{tag}-{i}") for i in range(n)]
        for ref in self.cards:
            vocab.record_review(self.U, ref, "good")
        set_mode(self.U, "fsrs")
        self.convert(self.cards, "rec-run-1")
        return self.U

    def convert(self, refs, run_key):
        from app.srs import migration
        from app.srs.engine import CardKey

        return migration.apply_plan(migration.dry_run([CardKey("personal", self.U, r) for r in refs]), run_key,
                                    approved=True)

    def rollback(self, run_key, rollback_key):
        from app.srs import migration

        return migration.rollback_plan(run_key, rollback_key, user_id=self.U, approved=True)

    def fsrs_review(self, ref):
        from app.repositories import vocab_repository as vocab

        version = sql("SELECT srs_card_version AS v FROM vocab_items WHERE id = ?", (ref,))[0]["v"]
        vocab.record_review(self.U, ref, "good", request_id=f"rec-req-{ref}-{version}", expected_card_version=version,
                            session_id="rec")

    def data_hash(self):
        out = {}
        for table in DATA_TABLES:
            rows = sql(f"SELECT * FROM {table} ORDER BY 1")
            out[table] = hashlib.sha256(repr([sorted(r.items()) for r in rows]).encode()).hexdigest()
        return out

    def recovery_rows(self):
        return (sql("SELECT * FROM account_write_blocks WHERE user_id = ? ORDER BY id", (self.U,)),
                sql("SELECT * FROM account_recovery_runs WHERE user_id = ? ORDER BY id", (self.U,)))

    def preview(self, key=KEY):
        from app import recovery

        return recovery.preview(self.U, key)

    def prepare(self, plan=None, key=KEY, token=TOKEN):
        from app import recovery

        return recovery.prepare(self.U, key, token, plan or self.preview(key)["plan"])

    def refused(self, fn, code, reasons=None):
        from app.account_write import AccountWriteError
        from app.recovery import RecoveryRefused

        with self.assertRaises((RecoveryRefused, AccountWriteError)) as caught:
            fn()
        self.assertEqual(caught.exception.code, code)
        if reasons is not None:
            self.assertEqual(caught.exception.reasons, reasons)
        return caught.exception

    # ---- precheck -----------------------------------------------------------------------------
    def test_preview_is_ready_and_writes_nothing(self):
        self.world()
        before, rows = self.data_hash(), self.recovery_rows()
        report = self.preview()
        self.assertEqual((report["status"], report["reasons"], report["counts"]["rollback_cards"]), ("ready", [], 2))
        self.assertEqual(len(report["plan"]), 64)
        self.assertEqual(self.preview()["plan"], report["plan"])                   # stable
        self.assertEqual((self.data_hash(), self.recovery_rows()), (before, rows))
        self.assertNotIn(TOKEN, json.dumps(report))

    def test_card_without_snapshot_blocks(self):
        from _e5b_fixture import card

        self.world()
        card(self.U, self.deck, "rec-born-fsrs")                                   # created in FSRS mode
        self.assertIn("fsrs_card_without_snapshot", self.preview()["reasons"])

    def test_reconversion_chains_are_recognized(self):
        self.world(n=1)
        self.rollback("rec-run-1", "rec-rb-1")                                     # A -> rollback A
        self.convert(self.cards, "rec-run-2")                                      # -> B
        report = self.preview()
        self.assertEqual((report["status"], report["counts"]["target_runs"], report["counts"]["prior_rolled_back_runs"]),
                         ("ready", 1, 1), report)
        self.rollback("rec-run-2", "rec-rb-2")                                     # B -> rollback B
        self.convert(self.cards, "rec-run-3")                                      # -> C (repeated)
        report = self.preview()
        self.assertEqual((report["status"], report["counts"]["target_runs"], report["counts"]["prior_rolled_back_runs"]),
                         ("ready", 1, 2), report)
        self.rollback("rec-run-3", "rec-rb-3")                                     # all rolled back: legacy now
        self.assertEqual(self.preview()["reasons"], ["nothing_to_recover"])

    def test_prior_partial_rollback_blocks(self):
        from app.database import get_connection
        from app.srs import identity

        self.world(n=2)
        with get_connection() as c:
            identity.flag_identity_unknown(c, [identity.IdentityFinding(self.U, self.cards[1], ["rec_synthetic"])])
        results = self.rollback("rec-run-1", "rec-rb-1")
        self.assertEqual(sorted(r["result"] for r in results), ["rolled_back", "skipped"])
        self.assertIn("prior_partial_rollback", self.preview()["reasons"])

    def test_unexplained_or_ambiguous_history_blocks(self):
        self.world(n=1)
        sql("UPDATE srs_migration_runs SET status = 'aborted' WHERE run_key = 'rec-run-1'")
        self.assertIn("prior_rollback_unverifiable", self.preview()["reasons"])
        sql("UPDATE srs_migration_runs SET status = 'completed' WHERE run_key = 'rec-run-1'")
        # a second conversion record of the same card with no rollback between (synthetic)
        run = sql("SELECT * FROM srs_migration_runs WHERE run_key = 'rec-run-1'")[0]
        copy = sql("INSERT INTO srs_migration_runs (run_key, mode, status, scope_json, engine, library_version, "
                   "config_version, summary_json, started_at, finished_at) VALUES ('rec-run-x', 'apply', 'completed', "
                   "?, ?, ?, ?, ?, ?, ?) RETURNING id", (run["scope_json"], run["engine"], run["library_version"],
                                                         run["config_version"], run["summary_json"], run["started_at"],
                                                         run["finished_at"]))[0]["id"]
        snap = sql("SELECT * FROM srs_migration_snapshots WHERE run_id = ?", (run["id"],))[0]
        sql("INSERT INTO srs_migration_snapshots (run_id, user_id, card_kind, card_ref, card_version_before, legacy_json, "
            "srs_before_json, srs_after_json, history_quality, history_flags, created_at) VALUES "
            "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (copy, snap["user_id"], snap["card_kind"], snap["card_ref"],
                                                  snap["card_version_before"] + 1, snap["legacy_json"],
                                                  snap["srs_before_json"], snap["srs_after_json"],
                                                  snap["history_quality"], snap["history_flags"], snap["created_at"]))
        reasons = self.preview()["reasons"]
        self.assertIn("card_history_ambiguous", reasons)
        self.assertIn("overlapping_source_runs", reasons)

    def test_deleted_card_needs_the_ledger_proof(self):
        from app.repositories import vocab_repository as vocab

        self.world(n=2)
        vocab.delete_vocab_item(self.U, self.cards[1])
        report = self.preview()
        self.assertEqual((report["status"], report["counts"]["rollback_cards"], report["counts"]["deleted_proven"]),
                         ("ready", 1, 1), report)
        sql("DELETE FROM srs_card_deletions WHERE user_id = ? AND card_ref = ?", (self.U, self.cards[1]))
        self.assertIn("card_missing_unproven", self.preview()["reasons"])

    def test_identity_flag_blocks(self):
        from app.database import get_connection
        from app.srs import identity

        self.world(n=1)
        with get_connection() as c:
            identity.flag_identity_unknown(c, [identity.IdentityFinding(self.U, self.cards[0], ["rec_synthetic"])])
        self.assertIn("card_identity_unknown", self.preview()["reasons"])

    def test_window_boundaries(self):
        from app.database import now_utc

        self.world(n=1)
        for started, expect in ((now_utc() - timedelta(days=31), ("blocked", ["rollback_window_closed"], [])),
                                ("not-a-time", ("blocked", ["rollback_window_unverifiable"], [])),
                                (now_utc() - timedelta(days=29, hours=12), ("ready", [], ["rollback_window_margin"])),
                                (now_utc() - timedelta(days=1), ("ready", [], []))):
            with self.subTest(started=str(started)):
                sql("UPDATE srs_migration_runs SET started_at = ? WHERE run_key = 'rec-run-1'",
                    (started if isinstance(started, str) else started.isoformat(),))
                report = self.preview()
                self.assertEqual((report["status"], report["reasons"], report["warnings"]), expect)

    # ---- step A -------------------------------------------------------------------------------
    def test_step_a_prepares_without_touching_recovery_data(self):
        from app import recovery

        self.world()
        before = self.data_hash()
        result = self.prepare()
        self.assertEqual((result["status"], result["created"]), ("prepared", True))
        blocks, records = self.recovery_rows()
        self.assertEqual((blocks[0]["status"], blocks[0]["changes_started"]), ("active", 0))
        self.assertEqual((records[0]["state"], records[0]["block_id"]), ("prepared", blocks[0]["id"]))
        base = json.loads(records[0]["baseline_json"])
        self.assertTrue(base["at"] and base["days"] and base["logs"]["count"] >= 2)
        self.assertEqual(self.data_hash(), before)                                 # no recovery data changed
        for row in blocks + records:
            self.assertNotIn(TOKEN, json.dumps(row, default=str))
        self.assertEqual(recovery.resume_status(self.U, KEY), {"next": "run_recovery"})
        response = s.request("POST", "/decks", {"name": "u-blocked"}, self.token())
        self.assertEqual((response.status_code, response.json()["detail"]), (409, "account_writes_blocked"))

    def test_plan_change_refuses_step_a_and_leaves_nothing(self):
        from app import account_blocks

        self.world()
        plan = self.preview()["plan"]
        self.fsrs_review(self.cards[0])                                             # the plan is now stale
        before = self.data_hash()
        self.refused(lambda: self.prepare(plan), "plan_changed")
        self.assertEqual((self.recovery_rows(), self.data_hash()), (([], []), before))
        # a block that existed before step A is not removed by its refusal
        account_blocks.set_block(self.U, KEY, TOKEN)
        self.refused(lambda: self.prepare(plan), "plan_changed")
        blocks, records = self.recovery_rows()
        self.assertEqual(([b["status"] for b in blocks], records), (["active"], []))

    def test_a_failure_at_each_stage_rolls_back_the_new_block_and_record(self):
        from app import recovery

        self.world()
        plan = self.preview()["plan"]
        real_set, real_assess, real_baseline = recovery.set_block_locked, recovery.assess, recovery.baseline

        def after(real):
            def wrapped(*a, **k):
                real(*a, **k)
                raise RuntimeError("injected")
            return wrapped

        for stage, patch in (("after_block", mock.patch.object(recovery, "set_block_locked", after(real_set))),
                             ("after_assess", mock.patch.object(recovery, "assess", after(real_assess))),
                             ("after_baseline", mock.patch.object(recovery, "baseline", after(real_baseline))),
                             ("at_record", mock.patch.object(recovery, "rollback_key_for",
                                                             side_effect=RuntimeError("injected")))):
            with self.subTest(stage), patch, self.assertRaises(RuntimeError):
                self.prepare(plan)
            self.assertEqual(self.recovery_rows(), ([], []), stage)
        self.assertEqual(self.prepare(plan)["status"], "prepared")                # clean afterwards

    def test_same_key_resumes_and_other_inputs_conflict(self):
        self.world()
        plan = self.preview()["plan"]
        first = self.prepare(plan)
        rows = self.recovery_rows()
        again = self.prepare(plan)
        self.assertEqual((again["created"], again["record_id"]), (False, first["record_id"]))
        self.assertEqual(self.recovery_rows(), rows)                               # nothing written again
        self.refused(lambda: self.prepare(plan, token=OTHER_TOKEN), "recovery_grant_invalid")
        self.refused(lambda: self.prepare(plan, key="prb-rec-2"), "recovery_in_progress")
        self.refused(lambda: self.prepare("f" * 64), "recovery_plan_mismatch")
        self.assertIn("recovery_in_progress", self.preview(key="prb-rec-2")["reasons"])
        self.assertEqual(self.recovery_rows(), rows)

    def test_an_open_record_cannot_lose_its_marker_or_double(self):
        self.world()
        self.prepare()
        with self.assertRaises(Exception):
            sql("UPDATE account_recovery_runs SET active_user_id = NULL WHERE user_id = ?", (self.U,))
        record = self.recovery_rows()[1][0]
        with self.assertRaises(Exception):
            sql("INSERT INTO account_recovery_runs (user_id, block_id, recovery_key, plan_fingerprint, state, "
                "active_user_id, source_runs_json, baseline_json, prepared_at) VALUES (?, ?, 'prb-rec-dup', ?, "
                "'prepared', ?, '[]', '{}', 'x')", (self.U, record["block_id"], "0" * 64, self.U))
        self.assertEqual(len(self.recovery_rows()[1]), 1)

    def test_release_closes_the_record_in_the_same_transaction(self):
        from app import account_blocks
        from app import database

        self.world()
        self.prepare()
        real = database.get_connection

        class Failing:
            """The block UPDATE fails after the record UPDATE: both must roll back."""

            def __init__(self):
                self.connection = real()

            def __enter__(self):
                outer = self

                class Proxy:
                    def __getattr__(self, name):
                        return getattr(outer.connection, name)

                    def execute(self, query, params=()):
                        if query.startswith("UPDATE account_write_blocks SET status = 'released'"):
                            raise RuntimeError("injected")
                        return outer.connection.execute(query, params)
                self.wrapped = self.connection.__enter__()
                return Proxy()

            def __exit__(self, *exc):
                return self.connection.__exit__(*exc)

        with mock.patch.object(account_blocks, "get_connection", lambda: Failing()), self.assertRaises(RuntimeError):
            account_blocks.release_block(self.U, KEY, TOKEN, "precheck_unrecoverable")
        blocks, records = self.recovery_rows()
        self.assertEqual((blocks[0]["status"], records[0]["state"]), ("active", "prepared"))
        result = account_blocks.release_block(self.U, KEY, TOKEN, "precheck_unrecoverable")
        self.assertTrue(result["recovery_record_closed"])
        blocks, records = self.recovery_rows()
        self.assertEqual((blocks[0]["status"], records[0]["state"], records[0]["close_reason"]),
                         ("released", "closed", "precheck_unrecoverable"))

    def test_resume_status_from_the_database(self):
        from app import recovery

        self.world()
        self.assertEqual(recovery.resume_status(self.U, KEY), {"next": "preview"})
        self.prepare()
        self.assertEqual(recovery.resume_status(self.U, KEY), {"next": "run_recovery"})
        sql("UPDATE account_write_blocks SET changes_started = 1 WHERE user_id = ?", (self.U,))   # inconsistent
        self.assertEqual(recovery.resume_status(self.U, KEY)["next"], "report_only")
        from app import account_blocks
        self.refused(lambda: account_blocks.release_block(self.U, KEY, TOKEN, "precheck_unrecoverable"),
                     "release_not_allowed")
        sql("UPDATE account_write_blocks SET changes_started = 0 WHERE user_id = ?", (self.U,))
        account_blocks.release_block(self.U, KEY, TOKEN, "precheck_unrecoverable")
        self.assertEqual(recovery.resume_status(self.U, KEY), {"next": "closed"})

    def test_cli_takes_the_token_by_hidden_input_only(self):
        sys.path.insert(0, str(BACKEND / "scripts"))
        import prb_recover

        self.world()
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(prb_recover.main(["preview", "--user-id", str(self.U), "--recovery-key", KEY]), 0)
        plan = json.loads(out.getvalue())["plan"]
        printed = []
        with redirect_stdout(io.StringIO()), self.assertRaises(SystemExit):
            prb_recover.main(["prepare", "--user-id", str(self.U), "--recovery-key", KEY, "--plan", plan,
                              "--token", TOKEN])
        code = prb_recover.main(["prepare", "--user-id", str(self.U), "--recovery-key", KEY, "--plan", plan],
                                ask=lambda _: str(self.U), secret=lambda _: TOKEN, out=printed.append)
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(printed[-1])["status"], "prepared")
        self.assertNotIn(TOKEN, "".join(printed))
        code = prb_recover.main(["prepare", "--user-id", str(self.U), "--recovery-key", KEY, "--plan", plan],
                                ask=lambda _: "999", secret=lambda _: TOKEN, out=printed.append)
        self.assertEqual((code, json.loads(printed[-1])["code"]), (2, "account_confirmation_mismatch"))

    # ---- review fixes (unit 1, second pass) ---------------------------------------------------
    def test_plan_fingerprint_covers_log_content(self):
        """Fix 1: changing an FSRS log's rating changes the legacy projection the rollback would
        write; the plan must change too, and step A with the old plan must leave nothing new."""
        from app import account_blocks

        self.world()
        self.fsrs_review(self.cards[0])
        plan = self.preview()["plan"]
        self.assertEqual(self.preview()["plan"], plan)                              # stable while nothing changes
        log = sql("SELECT id, rating FROM review_logs WHERE vocab_item_id = ? AND srs_engine = 'fsrs' "
                  "ORDER BY id DESC", (self.cards[0],))[0]
        sql("UPDATE review_logs SET rating = ? WHERE id = ?", ("easy" if log["rating"] != "easy" else "hard", log["id"]))
        self.assertNotEqual(self.preview()["plan"], plan)
        self.refused(lambda: self.prepare(plan), "plan_changed")
        self.assertEqual(self.recovery_rows(), ([], []))
        account_blocks.set_block(self.U, KEY, TOKEN)                                # an existing block stays
        self.refused(lambda: self.prepare(plan), "plan_changed")
        blocks, records = self.recovery_rows()
        self.assertEqual(([b["status"] for b in blocks], records), (["active"], []))
        self.assertNotIn("rating", json.dumps(self.preview()))                      # no content in the output

    def _reconverted(self):
        self.world(n=2)
        self.rollback("rec-run-1", "rec-rb-1")
        self.convert(self.cards, "rec-run-2")
        self.assertEqual(self.preview()["status"], "ready")
        return sql("SELECT id FROM srs_migration_runs WHERE run_key = 'rec-rb-1'")[0]["id"]

    def test_past_rollback_records_are_proven_not_just_ordered(self):
        """Fix 2: a damaged past rollback record (or summary) blocks with a fixed reason; the
        data is left as it is; a sound re-conversion stays ready."""
        cases = {
            "snapshot_not_json": ("UPDATE srs_migration_snapshots SET legacy_json = 'x' WHERE run_id = ? AND card_ref = ?", "card"),
            "snapshot_empty": ("UPDATE srs_migration_snapshots SET legacy_json = '{}' WHERE run_id = ? AND card_ref = ?", "card"),
            "restore_missing": ("UPDATE srs_migration_snapshots SET srs_before_json = '{}' WHERE run_id = ? AND card_ref = ?", "card"),
            "other_card_named": ("UPDATE srs_migration_snapshots SET legacy_json = REPLACE(legacy_json, "
                                 "'\"id\":' || card_ref, '\"id\":' || (card_ref + 1000)) WHERE run_id = ? AND card_ref = ?", "card"),
            "summary_missing_card": ("summary", lambda r: r[:1]),
            "summary_duplicate": ("summary", lambda r: r + r[:1]),
            "summary_unknown_card": ("summary", lambda r: r + [dict(r[0], ref_id=r[0]["ref_id"] + 1000)]),
        }
        for name, (change, arg) in cases.items():
            with self.subTest(name):
                self.reset_world()
                rollback_run = self._reconverted()
                if change == "summary":
                    summary = json.loads(sql("SELECT summary_json FROM srs_migration_runs WHERE id = ?",
                                             (rollback_run,))[0]["summary_json"])
                    sql("UPDATE srs_migration_runs SET summary_json = ? WHERE id = ?",
                        (json.dumps(arg(summary)), rollback_run))
                else:
                    sql(change, (rollback_run, self.cards[0]))
                before = self.data_hash()
                report = self.preview()
                self.assertEqual(report["status"], "blocked", report)
                self.assertIn("prior_rollback_record_invalid", report["reasons"])
                self.refused(lambda: self.prepare(report["plan"]), "recovery_blocked")
                self.assertEqual((self.data_hash(), self.recovery_rows()), (before, ([], [])))

    def test_resume_status_checks_the_stored_sources(self):
        """Fix 3: the stored source list must be exactly the prepared plan's; anything else is
        reported only (no exception, no write)."""
        from app import recovery

        self.world()
        self.prepare()
        record = self.recovery_rows()[1][0]
        sources = json.loads(record["source_runs_json"])
        other = sql("INSERT INTO srs_migration_runs (run_key, mode, status, scope_json, engine, library_version, "
                    "config_version, started_at) SELECT 'rec-dry', 'dry_run', 'completed', scope_json, engine, "
                    "library_version, config_version, started_at FROM srs_migration_runs WHERE run_key = 'rec-run-1' "
                    "RETURNING id")[0]["id"]
        bad = {
            "empty": "[]", "not_json": "x", "object": '{"run_id": 1}', "wrong_types": '[{"run_id": "1", "rollback_key": 1}]',
            "duplicate": json.dumps(sources + sources),
            "wrong_key": json.dumps([dict(sources[0], rollback_key="prb:other:1")]),
            "unknown_run": json.dumps([{"run_id": 99999, "rollback_key": recovery.rollback_key_for(KEY, 99999)}]),
            "not_an_apply_run": json.dumps([{"run_id": other, "rollback_key": recovery.rollback_key_for(KEY, other)}]),
            "extra_field": json.dumps([dict(sources[0], note="x")]),
        }
        for name, text in bad.items():
            with self.subTest(name):
                sql("UPDATE account_recovery_runs SET source_runs_json = ? WHERE id = ?", (text, record["id"]))
                before = (self.data_hash(), self.recovery_rows())
                self.assertEqual(recovery.resume_status(self.U, KEY)["next"], "report_only")
                self.assertEqual((self.data_hash(), self.recovery_rows()), before)
        sql("UPDATE account_recovery_runs SET source_runs_json = ? WHERE id = ?", (json.dumps(sources), record["id"]))
        self.assertEqual(recovery.resume_status(self.U, KEY), {"next": "run_recovery"})

    def _resume_after(self, column, value):
        from app import recovery

        record = self.recovery_rows()[1][0]
        sql(f"UPDATE account_recovery_runs SET {column} = ? WHERE id = ?", (value, record["id"]))
        before = (self.data_hash(), self.recovery_rows())
        result = recovery.resume_status(self.U, KEY)
        self.assertEqual((self.data_hash(), self.recovery_rows()), before)          # writes 0
        sql(f"UPDATE account_recovery_runs SET {column} = ? WHERE id = ?", (record[column], record["id"]))
        return result

    def test_resume_checks_every_baseline_value(self):
        """Fix (second pass) 1: the stored baseline is checked field by field."""
        from app import recovery

        self.world()
        self.fsrs_review(self.cards[0])
        self.prepare()
        good = json.loads(self.recovery_rows()[1][0]["baseline_json"])
        damaged = {
            "codex_case": dict(good, at="garbage", days=[], logs=None, preserved=None, metrics_digest=False,
                               cards="not-a-list"),
            "at_garbage": dict(good, at="garbage"), "at_not_prepared_at": dict(good, at="2020-01-01T00:00:00+00:00"),
            "days_empty": dict(good, days=[]), "days_not_dates": dict(good, days=["x"]),
            "days_duplicate": dict(good, days=good["days"] + good["days"][-1:]),
            "days_without_at_day": dict(good, days=["2001-01-01"]),
            "logs_null": dict(good, logs=None), "logs_count_bool": dict(good, logs=dict(good["logs"], count=True)),
            "logs_count_text": dict(good, logs=dict(good["logs"], count=str(good["logs"]["count"]))),
            "logs_count_negative": dict(good, logs=dict(good["logs"], count=-1)),
            "logs_digest_short": dict(good, logs=dict(good["logs"], digest="abc")),
            "preserved_null": dict(good, preserved=None),
            "preserved_count_mismatch": dict(good, preserved=dict(good["preserved"], count=good["preserved"]["count"] + 1)),
            "metrics_false": dict(good, metrics_digest=False), "cards_text": dict(good, cards="not-a-list"),
            "card_kind_unknown": dict(good, cards=[["other"] + good["cards"][0][1:]] + good["cards"][1:]),
            "card_version_bool": dict(good, cards=[good["cards"][0][:2] + [True]] + good["cards"][1:]),
            "card_duplicate": dict(good, cards=good["cards"] + good["cards"][:1]),
            "card_not_a_target": dict(good, cards=[[good["cards"][0][0], 999999, 1]] + good["cards"][1:]),
            "card_version_changed": dict(good, cards=[good["cards"][0][:2] + [good["cards"][0][2] + 1]] + good["cards"][1:]),
            "extra_key": dict(good, note="x"), "missing_key": {k: v for k, v in good.items() if k != "logs"},
        }
        for name, base in damaged.items():
            with self.subTest(name):
                result = self._resume_after("baseline_json", json.dumps(base))
                self.assertEqual(result["next"], "report_only", result)
        self.assertEqual(recovery.resume_status(self.U, KEY), {"next": "run_recovery"})    # the stored one is fine

    def test_resume_needs_the_whole_state_combination(self):
        """Fix (second pass) 2: a state word alone never names the next step."""
        from app import recovery

        self.world()
        self.prepare()
        record = self.recovery_rows()[1][0]
        cases = {
            "verified_word_only": [("state", "verified")],
            "applied_word_only": [("state", "applied")],
            "verified_with_progress_but_no_record": [("state", "verified")],
            "prepared_with_applied_at": [("applied_at", record["prepared_at"])],
            "prepared_with_verification": [("verification_json", "{}")],
            "prepared_with_digest": [("verified_digest", "0" * 64)],
        }
        for name, changes in cases.items():
            with self.subTest(name):
                if name == "verified_with_progress_but_no_record":
                    sql("UPDATE account_write_blocks SET changes_started = 1 WHERE user_id = ?", (self.U,))
                for column, value in changes:
                    sql(f"UPDATE account_recovery_runs SET {column} = ? WHERE id = ?", (value, record["id"]))
                before = (self.data_hash(), self.recovery_rows())
                result = recovery.resume_status(self.U, KEY)
                self.assertEqual(result["next"], "report_only", result)
                self.assertEqual((self.data_hash(), self.recovery_rows()), before)
                for column, _value in changes:
                    sql(f"UPDATE account_recovery_runs SET {column} = ? WHERE id = ?", (record[column], record["id"]))
                sql("UPDATE account_write_blocks SET changes_started = 0 WHERE user_id = ?", (self.U,))
        self.assertEqual(recovery.resume_status(self.U, KEY), {"next": "run_recovery"})

    # ---- lock order: step A <-> review / deletion / conversion ---------------------------------
    def token(self):
        from app.auth import create_access_token

        return create_access_token({"id": self.U, "email": "rec@e5b.example.test"})

    def _write_first(self, write, expect_reason):
        """The ordinary write holds the account lock; step A waits, then sees the new state."""
        real, modules = s._modules_with_lock()
        patch, probe = self.waiting_probe()[:2]
        run = HoldThenWait(probe)
        plan = self.preview()["plan"]

        def paused(connection, user_id, **kwargs):
            real(connection, user_id, **kwargs)
            run.pause()

        with patch, ExitStack() as stack:
            for module in modules:
                stack.enter_context(mock.patch.object(module, "begin_account_write", paused))
            box = run.run(write, lambda: self.prepare(plan))
        self.assertTrue(box["held"] and box["waited"] and box["joined"], box)
        self.assertEqual(box["hold"][0], "ok", box)
        self.assertEqual(box["delete"][0], "error", box)
        error = box["delete"][1]
        self.assertIn((error.code, tuple(getattr(error, "reasons", ()))), expect_reason, box)
        self.assertEqual(self.recovery_rows(), ([], []))                             # nothing left by step A
        return box

    def _a_first(self, write):
        """Step A holds the account lock; the ordinary write waits, then is refused."""
        from app import recovery

        patch, probe = self.waiting_probe()[:2]
        run = HoldThenWait(probe)
        plan = self.preview()["plan"]
        before = self.data_hash()
        real = recovery.lock_account

        def paused(connection, user_id):
            real(connection, user_id)
            run.pause()

        with patch, mock.patch.object(recovery, "lock_account", paused):
            box = run.run(lambda: self.prepare(plan), write)
        self.assertTrue(box["held"] and box["waited"] and box["joined"], box)
        self.assertEqual((box["hold"][0], box["hold"][1]["status"]), ("ok", "prepared"), box)
        self.assertEqual(box["delete"][0], "error", box)
        self.assertEqual(getattr(box["delete"][1], "code", None), "account_writes_blocked", box)
        self.assertEqual(self.data_hash(), before)
        return box

    def test_review_first_then_step_a_sees_the_change(self):
        self.world()
        return self._write_first(lambda: self.fsrs_review(self.cards[0]), {("plan_changed", ())})

    def test_step_a_first_then_review_is_refused(self):
        self.world()
        return self._a_first(lambda: self.fsrs_review(self.cards[0]))

    def test_delete_first_then_step_a_sees_the_change(self):
        from app.repositories import vocab_repository as vocab

        self.world()
        return self._write_first(lambda: vocab.delete_vocab_item(self.U, self.cards[1]), {("plan_changed", ())})

    def test_step_a_first_then_delete_is_refused(self):
        from app.repositories import vocab_repository as vocab

        self.world()
        return self._a_first(lambda: vocab.delete_vocab_item(self.U, self.cards[1]))

    def _legacy_extra(self):
        from _e5b_fixture import card, set_mode

        set_mode(self.U, "legacy")
        extra = card(self.U, self.deck, "rec-extra")
        set_mode(self.U, "fsrs")
        return extra

    def test_conversion_first_then_step_a_sees_the_change(self):
        self.world()
        extra = self._legacy_extra()
        # A conversion commits its run row and each card separately: step A may run between
        # them (run still `started`) or after the last one (plan changed). Both refuse.
        return self._write_first(lambda: self.convert([extra], "rec-run-extra"),
                                 {("plan_changed", ()), ("recovery_blocked", ("migration_run_in_progress",))})

    def test_step_a_first_then_conversion_is_refused(self):
        self.world()
        extra = self._legacy_extra()
        box = self._a_first(lambda: self.convert([extra], "rec-run-extra"))
        self.assertEqual(sql("SELECT srs_engine FROM vocab_items WHERE id = ?", (extra,))[0]["srs_engine"], "legacy")
        return box

    # ==== unit 2: step B and verify ===============================================================
    def mixed_world(self):
        """Personal cards in run 1 and a subscribed card in run 2 (two sources, both kinds)."""
        from _e5b_fixture import card, set_mode
        from app.repositories import deck_repository as decks, lexeme_repository as lexemes
        from app.repositories import shared_deck_repository as shared, user_repository as users
        from app.schemas import DeckCreate
        from app.srs import migration
        from app.srs.engine import CardKey

        self.world(n=2, tag="m")
        self.O = users.create_user("rec-o@e5b.example.test", "rec-o", "synthetic")["id"]
        o_deck = decks.create_deck(self.O, DeckCreate(name="o-deck"))[0]["id"]
        self.o_card = card(self.O, o_deck, "rec-o-word")
        self.shared = shared.publish_deck(self.O, o_deck, "rec-shared", "")["shared_deck_id"]
        self.lexeme = sql("SELECT lexeme_id FROM shared_deck_words WHERE shared_deck_id = ?", (self.shared,))[0]["lexeme_id"]
        set_mode(self.U, "legacy")
        lexemes.get_or_create_subscription(self.U, self.shared)
        lexemes.update_word_status(self.U, self.lexeme, "unknown")
        lexemes.record_lexeme_review(self.U, self.lexeme, "good", self.shared)
        set_mode(self.U, "fsrs")
        migration.apply_plan(migration.dry_run([CardKey("lexeme", self.U, self.lexeme)]), "rec-run-lex", approved=True)
        self.fsrs_review(self.cards[0])                                             # a later FSRS review to preserve
        version = sql("SELECT srs_card_version AS v FROM user_word_progress WHERE user_id = ? AND lexeme_id = ?",
                      (self.U, self.lexeme))[0]["v"]
        lexemes.record_lexeme_review(self.U, self.lexeme, "hard", self.shared, request_id="rec-lex-1",
                                     expected_card_version=version, session_id="rec")

    def others_hash(self):
        rows = {t: sql(f"SELECT * FROM {t} WHERE user_id <> ? ORDER BY 1", (self.U,))
                for t in ("vocab_items", "review_logs", "decks", "srs_user_settings", "user_word_progress")}
        return hashlib.sha256(repr(rows).encode()).hexdigest()

    def recover(self, plan=None, token=TOKEN):
        from app import recovery

        plan = plan or self.recovery_rows()[1][0]["plan_fingerprint"]
        return recovery.recover(self.U, KEY, token, plan)

    def verify(self, token=TOKEN):
        from app import recovery

        return recovery.verify(self.U, KEY, token)

    @staticmethod
    def change_a(checks, drop=None, **changed):
        """A proof-v2 check set with one A check dropped or replaced."""
        a = {k: v for k, v in checks["A"].items() if k != drop}
        a.update(changed)
        return dict(checks, A=a)

    def engines(self):
        return (sql("SELECT srs_engine FROM vocab_items WHERE user_id = ? ORDER BY id", (self.U,)),
                sql("SELECT srs_engine FROM user_word_progress WHERE user_id = ? ORDER BY lexeme_id", (self.U,)))

    def test_b_and_verify_on_two_sources_of_both_kinds(self):
        from app import account_blocks, recovery

        self.mixed_world()
        others = self.others_hash()
        self.prepare()
        base = json.loads(self.recovery_rows()[1][0]["baseline_json"])
        settings = sql("SELECT srs_mode, settings_version FROM srs_user_settings WHERE user_id = ?", (self.U,))[0]
        result = self.recover()
        self.assertEqual((result["status"], result["created"], result["rolled_back"], result["deleted_proven"]),
                         ("applied", True, 3, 0))
        personal, lexeme = self.engines()
        self.assertEqual({r["srs_engine"] for r in personal + lexeme}, {"legacy"})
        after = sql("SELECT srs_mode, settings_version FROM srs_user_settings WHERE user_id = ?", (self.U,))[0]
        self.assertEqual((after["srs_mode"], after["settings_version"]), ("legacy", settings["settings_version"] + 1))
        runs = {r["run_key"]: r["status"] for r in sql("SELECT run_key, status FROM srs_migration_runs")}
        self.assertEqual((runs["rec-run-1"], runs["rec-run-lex"]), ("aborted", "aborted"))
        for source in json.loads(self.recovery_rows()[1][0]["source_runs_json"]):
            self.assertEqual(runs[source["rollback_key"]], "completed")
        blocks, records = self.recovery_rows()
        self.assertEqual((blocks[0]["changes_started"], records[0]["state"]), (1, "applied"))
        self.assertEqual(recovery.resume_status(self.U, KEY), {"next": "verify"})
        checked = self.verify()
        self.assertEqual((checked["status"], set(checked["checks"].values())), ("verified", {"pass"}))
        record = self.recovery_rows()[1][0]
        self.assertTrue(recovery.proof_ok(json.loads(record["verification_json"])))
        self.assertEqual(recovery.resume_status(self.U, KEY), {"next": "await_release"})
        self.assertEqual(json.loads(record["baseline_json"]), base)
        self.assertEqual(self.others_hash(), others)                                # other accounts unchanged
        for reason in ("completed", "precheck_unrecoverable", "operator_abandoned"):
            with self.assertRaises(Exception):
                account_blocks.release_block(self.U, KEY, TOKEN, reason)
        self.assertEqual(self.recovery_rows()[0][0]["status"], "active")            # no release of any kind
        from app.database import get_connection
        with get_connection() as c:                                                 # saving verified kept D
            self.assertEqual(recovery.verification_digest(c, self.U, blocks[0]["id"], record["id"]),
                             record["verified_digest"])

    def test_b_and_verify_recalls_write_nothing(self):
        self.mixed_world()
        self.prepare()
        self.recover()
        state = (self.data_hash(), self.recovery_rows())
        again = self.recover()
        self.assertEqual((again["status"], again["created"]), ("applied", False))
        self.assertEqual((self.data_hash(), self.recovery_rows()), state)
        self.verify()
        state = (self.data_hash(), self.recovery_rows())
        self.assertEqual(self.verify()["created"], False)
        self.assertEqual(self.recover()["status"], "verified")
        self.assertEqual((self.data_hash(), self.recovery_rows()), state)

    def test_b_records_a_proven_deletion_and_restores_nothing(self):
        from app.repositories import vocab_repository as vocab

        self.world(n=2)
        vocab.delete_vocab_item(self.U, self.cards[1])
        self.prepare()
        result = self.recover()
        self.assertEqual((result["rolled_back"], result["deleted_proven"]), (1, 1))
        self.assertEqual(sql("SELECT id FROM vocab_items WHERE id = ?", (self.cards[1],)), [])   # not restored
        summary = json.loads(sql("SELECT summary_json FROM srs_migration_runs WHERE run_key LIKE ?", ("prb:%",))[0]["summary_json"])
        self.assertIn({"kind": "personal", "ref_id": self.cards[1], "result": "deleted_proven"}, summary)
        self.assertEqual(self.verify()["status"], "verified")

    def test_b_after_normal_and_repeated_reconversion(self):
        self.world(n=1)
        self.rollback("rec-run-1", "rec-rb-1")
        self.convert(self.cards, "rec-run-2")
        self.rollback("rec-run-2", "rec-rb-2")
        self.convert(self.cards, "rec-run-3")
        self.prepare()
        self.assertEqual(self.recover()["rolled_back"], 1)
        self.assertEqual(self.verify()["status"], "verified")

    def test_b_refuses_when_anything_moved_after_a(self):
        from app.database import now_utc

        cases = {
            "window_expired": lambda: sql("UPDATE srs_migration_runs SET started_at = ? WHERE run_key = 'rec-run-1'",
                                          ((now_utc() - timedelta(days=31)).isoformat(),)),
            "access_lost": lambda: sql("UPDATE user_deck_subscriptions SET is_active = FALSE WHERE user_id = ?",
                                       (self.U,)),
            "card_without_snapshot": lambda: sql("UPDATE vocab_items SET srs_engine = 'fsrs' WHERE user_id = ? AND "
                                                 "srs_engine = 'legacy'", (self.U,)),
        }
        for name, change in cases.items():
            with self.subTest(name):
                self.reset_world()
                self.mixed_world()
                if name == "card_without_snapshot":
                    from _e5b_fixture import card, set_mode
                    set_mode(self.U, "legacy")
                    card(self.U, self.deck, "rec-late-legacy")
                    set_mode(self.U, "fsrs")
                self.prepare()
                change()
                before = (self.data_hash(), self.recovery_rows())
                self.refused(self.recover, "recovery_blocked")
                self.assertEqual((self.data_hash(), self.recovery_rows()), before)
        self.reset_world()
        self.world()
        self.prepare()
        self.refused(lambda: self.recover(token=OTHER_TOKEN), "recovery_grant_invalid")
        self.refused(lambda: self.recover(plan="f" * 64), "recovery_plan_mismatch")

    def test_a_failure_anywhere_in_b_rolls_back_everything(self):
        from app import recovery
        from app.srs import migration

        self.mixed_world()
        self.prepare()
        before = (self.data_hash(), self.recovery_rows())
        real_write = migration.write_card_rollback
        calls = {"n": 0}

        def second_card_fails(*a, **k):
            calls["n"] += 1
            if calls["n"] == 2:
                raise RuntimeError("injected")
            return real_write(*a, **k)

        for stage, patch in (("second_card", mock.patch.object(migration, "write_card_rollback", second_card_fails)),
                             ("after_count", mock.patch.object(recovery, "_fsrs_rows", side_effect=RuntimeError("x"))),
                             ("mode_switch", mock.patch.object(recovery, "_switch_mode", side_effect=RuntimeError("x"))),
                             ("record_mark", mock.patch.object(recovery, "_mark_record", side_effect=RuntimeError("x")))):
            calls["n"] = 0
            with self.subTest(stage), patch, self.assertRaises(Exception):
                self.recover()
            self.assertEqual((self.data_hash(), self.recovery_rows()), before, stage)
        self.assertEqual(self.recover()["status"], "applied")                     # clean afterwards

    def test_steps_resume_from_the_database_alone(self):
        from app import recovery

        self.mixed_world()
        self.assertEqual(recovery.resume_status(self.U, KEY), {"next": "preview"})
        self.prepare()
        self.assertEqual(recovery.resume_status(self.U, KEY), {"next": "run_recovery"})
        self.recover()
        self.assertEqual(recovery.resume_status(self.U, KEY), {"next": "verify"})
        self.verify()
        self.assertEqual(recovery.resume_status(self.U, KEY), {"next": "await_release"})

    def test_verify_refuses_a_change_between_read_and_save(self):
        from app import recovery

        self.mixed_world()
        self.prepare()
        self.recover()
        with mock.patch.object(recovery, "_between_read_and_save", lambda: sql(
                "UPDATE vocab_items SET review_level = review_level + 1 WHERE id = ?", (self.cards[0],))):
            self.refused(self.verify, "verification_stale")
        self.assertEqual(self.recovery_rows()[1][0]["state"], "applied")

    def test_verify_needs_every_check_to_pass(self):
        from app import recovery

        self.mixed_world()
        self.prepare()
        self.recover()
        real = recovery._checks
        for name, patch in (
                ("missing_check", mock.patch.object(recovery, "_checks", lambda *a, **k: self.change_a(
                    real(*a, **k), drop="I5a"))),
                ("not_evaluated", mock.patch.object(recovery, "_checks", lambda *a, **k: self.change_a(
                    real(*a, **k), I7_recovery={"status": "not_evaluated"}))),
                ("unknown", mock.patch.object(recovery, "_checks", lambda *a, **k: self.change_a(
                    real(*a, **k), I4a={"status": "unknown"}))),
                ("n_unknown", mock.patch.object(recovery, "_checks", lambda *a, **k: dict(
                    real(*a, **k), N={"status": "unknown"})))):
            with self.subTest(name), patch:
                self.assertEqual(self.verify()["status"], "not_verified")
                self.assertEqual(self.recovery_rows()[1][0]["state"], "applied")
        log = sql("SELECT id, rating FROM review_logs WHERE user_id = ? ORDER BY id DESC", (self.U,))[0]
        sql("UPDATE review_logs SET rating = ? WHERE id = ?", ("easy" if log["rating"] != "easy" else "hard", log["id"]))
        result = self.verify()
        self.assertEqual((result["status"], result["checks"]["I6_recovery"]), ("not_verified", "fail"))
        self.assertEqual(self.recovery_rows()[1][0]["state"], "applied")

    def test_verify_after_midnight_uses_the_stored_days(self):
        from app import recovery
        from app.database import now_utc

        self.mixed_world()
        self.prepare()
        self.recover()
        later = now_utc() + timedelta(days=1, hours=2)
        with mock.patch.object(recovery, "now_utc", lambda: later):
            self.assertEqual(self.verify()["status"], "verified")

    # ---- lock order: step B <-> ordinary writes / public rollback / conversion / a second B ------
    def _b_first(self, waiter, expect_code=None):
        from app import account_write

        patch, probe = self.waiting_probe()[:2]
        run = HoldThenWait(probe)
        real = account_write.authorize_recovery

        def paused(connection, user_id, grant):
            block = real(connection, user_id, grant)
            run.pause()
            return block

        with patch, mock.patch.object(account_write, "authorize_recovery", paused):
            box = run.run(self.recover, waiter)
        self.assertTrue(box["held"] and box["waited"] and box["joined"], box)
        self.assertEqual((box["hold"][0], box["hold"][1]["status"]), ("ok", "applied"), box)
        if expect_code is None:
            self.assertEqual(box["delete"][0], "ok", box)
        else:
            self.assertEqual((box["delete"][0], getattr(box["delete"][1], "code", None)), ("error", expect_code), box)
        self.assertEqual({r["srs_engine"] for r in self.engines()[0] + self.engines()[1]}, {"legacy"})
        return box

    def test_b_first_then_review_is_refused(self):
        self.world()
        self.prepare()
        return self._b_first(lambda: self.fsrs_review(self.cards[0]), "account_writes_blocked")

    def test_b_first_then_delete_is_refused(self):
        from app.repositories import vocab_repository as vocab

        self.world()
        self.prepare()
        return self._b_first(lambda: vocab.delete_vocab_item(self.U, self.cards[1]), "account_writes_blocked")

    def test_b_first_then_public_rollback_is_refused(self):
        self.world()
        self.prepare()
        return self._b_first(lambda: self.rollback("rec-run-1", "rec-rb-public"), "account_writes_blocked")

    def test_b_first_then_conversion_is_refused(self):
        self.world()
        extra = self._legacy_extra()
        self.prepare()
        return self._b_first(lambda: self.convert([extra], "rec-run-extra"), "account_writes_blocked")

    def test_b_first_then_the_same_b_writes_nothing_more(self):
        self.world()
        self.prepare()
        box = self._b_first(self.recover)
        self.assertEqual((box["delete"][1]["status"], box["delete"][1]["created"]), ("applied", False))
        self.assertEqual(len(sql("SELECT id FROM srs_migration_runs WHERE run_key LIKE ?", ("prb:%",))), 1)
        return box

    def test_cli_runs_b_and_verify_with_hidden_input(self):
        sys.path.insert(0, str(BACKEND / "scripts"))
        import prb_recover

        self.world()
        printed = []
        user = str(self.U)
        prb_recover.main(["preview", "--user-id", user, "--recovery-key", KEY], out=printed.append)
        plan = json.loads(printed[-1])["plan"]
        for command in (["prepare", "--plan", plan], ["recover", "--plan", plan], ["verify"]):
            code = prb_recover.main([command[0], "--user-id", user, "--recovery-key", KEY, *command[1:]],
                                    ask=lambda _: user, secret=lambda _: TOKEN, out=printed.append)
            self.assertEqual(code, 0, printed[-1])
        self.assertEqual(json.loads(printed[-1])["status"], "verified")
        self.assertNotIn(TOKEN, "".join(printed))
        with redirect_stdout(io.StringIO()), self.assertRaises(SystemExit):
            prb_recover.main(["recover", "--user-id", user, "--recovery-key", KEY, "--plan", plan, "--token", TOKEN])

    # ---- unit 2 review fixes: re-calls ------------------------------------------------------------
    @contextmanager
    def sql_trace(self):
        """Every statement the app sends (SQLite and PostgreSQL connection classes), with the
        calling thread -- the evidence for "no write", not a before/after value comparison."""
        from app import database

        statements = []

        def wrap(real):
            def execute(connection, query, params=()):
                statements.append((threading.current_thread().name, " ".join(str(query).split())))
                return real(connection, query, params)
            return execute

        with mock.patch.object(database.AppSQLiteConnection, "execute", wrap(database.AppSQLiteConnection.execute)), \
                mock.patch.object(database.AppPostgresConnection, "execute",
                                  wrap(database.AppPostgresConnection.execute)):
            yield statements

    @staticmethod
    def writes(statements, thread=None):
        return [q for name, q in statements if (thread is None or name == thread)
                and q.split(" ", 1)[0].upper() in ("INSERT", "UPDATE", "DELETE")]

    def row_versions(self):
        """PostgreSQL only: xmin of the block, record and settings rows (unchanged = not rewritten)."""
        if self.db_kind != "postgresql":
            return None
        return (sql("SELECT xmin::text AS x FROM account_write_blocks WHERE user_id = ?", (self.U,)),
                sql("SELECT xmin::text AS x FROM account_recovery_runs WHERE user_id = ?", (self.U,)),
                sql("SELECT xmin::text AS x FROM srs_user_settings WHERE user_id = ?", (self.U,)))

    def test_b_recall_sends_no_write_statement(self):
        """Review fix 2: a re-call of a finished B checks the lock and the grant, and writes
        nothing at all (before: one UPDATE of the block row)."""
        self.mixed_world()
        self.prepare()
        self.recover()
        for state in ("applied", "verified"):
            if state == "verified":
                self.verify()
            versions = self.row_versions()
            with self.sql_trace() as statements:
                again = self.recover()
            self.assertEqual((again["status"], again["created"]), (state, False))
            self.assertEqual(self.writes(statements), [], state)
            self.assertTrue(any("FOR UPDATE" in q or "BEGIN IMMEDIATE" in q for _, q in statements))   # lock taken
            self.assertEqual(self.row_versions(), versions)
            with self.sql_trace() as statements:
                self.refused(lambda: self.recover(token=OTHER_TOKEN), "recovery_grant_invalid")
            self.assertEqual(self.writes(statements), [])

    def test_verify_recall_checks_the_current_data(self):
        """Review fix 1: `verified` is not taken as still true. Same data: no write. Changed data
        that still passes every check: the proof is refreshed under the lock. Changed data that
        fails: `not_verified`, nothing rewritten, and resume no longer offers the release wait."""
        from app import recovery
        from app.database import get_connection

        self.mixed_world()
        self.prepare()
        self.recover()
        self.verify()
        record = self.recovery_rows()[1][0]
        versions = self.row_versions()
        with self.sql_trace() as statements:
            same = self.verify()
        self.assertEqual((same["status"], same["created"]), ("verified", False))
        self.assertEqual(self.writes(statements), [])
        self.assertEqual(self.row_versions(), versions)
        # a value outside every check changes D: re-verified and refreshed
        sql("UPDATE vocab_items SET review_level = review_level + 1 WHERE id = ?", (self.cards[0],))
        self.assertEqual(recovery.resume_status(self.U, KEY), {"next": "verify"})
        refreshed = self.verify()
        self.assertEqual((refreshed["status"], refreshed["created"], refreshed.get("refreshed")), ("verified", True, True))
        after = self.recovery_rows()[1][0]
        with get_connection() as c:
            self.assertEqual(after["verified_digest"],
                             recovery.verification_digest(c, self.U, self.recovery_rows()[0][0]["id"], record["id"]))
        self.assertNotEqual(after["verified_digest"], record["verified_digest"])
        self.assertEqual((after["baseline_json"], after["state"]), (record["baseline_json"], "verified"))
        self.assertEqual(recovery.resume_status(self.U, KEY), {"next": "await_release"})
        # a change that breaks a check: not verified now; the stored proof stays a past record
        log = sql("SELECT id, rating FROM review_logs WHERE user_id = ? ORDER BY id DESC", (self.U,))[0]
        sql("UPDATE review_logs SET rating = ? WHERE id = ?", ("easy" if log["rating"] != "easy" else "hard", log["id"]))
        stored = self.recovery_rows()
        with self.sql_trace() as statements:
            failed = self.verify()
        self.assertEqual((failed["status"], failed["checks"]["I6_recovery"]), ("not_verified", "fail"))
        self.assertEqual(self.writes(statements), [])
        self.assertEqual(self.recovery_rows(), stored)
        resumed = recovery.resume_status(self.U, KEY)
        self.assertEqual(resumed["next"], "report_only", resumed)
        self.assertEqual(self.recovery_rows()[0][0]["status"], "active")            # block kept

    def test_verify_recall_needs_every_check_and_a_stable_read(self):
        from app import recovery

        self.mixed_world()
        self.prepare()
        self.recover()
        self.verify()
        real = recovery._checks
        with mock.patch.object(recovery, "_checks", lambda *a, **k: {
                n: v for n, v in real(*a, **k).items() if n != "S"}):
            self.assertEqual(self.verify()["status"], "not_verified")
        sql("UPDATE vocab_items SET review_level = review_level + 1 WHERE id = ?", (self.cards[0],))
        stored = self.recovery_rows()
        with mock.patch.object(recovery, "_between_read_and_save", lambda: sql(
                "UPDATE vocab_items SET review_level = review_level + 1 WHERE id = ?", (self.cards[0],))):
            self.refused(self.verify, "verification_stale")
        self.assertEqual(self.recovery_rows(), stored)

    def test_the_same_b_twice_at_once_writes_once(self):
        from app import account_write

        self.world()
        self.prepare()
        real = account_write.authorize_recovery
        with self.sql_trace() as statements:
            # the waiting probe is built INSIDE the trace, so it wraps the traced execute
            patch, probe = self.waiting_probe()[:2]
            run = HoldThenWait(probe)

            def paused(connection, user_id, grant):
                block = real(connection, user_id, grant)
                run.pause()
                return block

            with patch, mock.patch.object(account_write, "authorize_recovery", paused):
                box = run.run(self.recover, self.recover)
        self.assertTrue(any(name == "deleter" for name, _ in statements), statements[:3])   # traced, not vacuous
        self.assertTrue(box["held"] and box["waited"] and box["joined"], box)
        self.assertEqual([box["hold"][1]["created"], box["delete"][1]["created"]], [True, False], box)
        self.assertEqual(self.writes(statements, "deleter"), [])                   # the second call wrote nothing
        self.assertEqual(len(sql("SELECT id FROM srs_migration_runs WHERE run_key LIKE ?", ("prb:%",))), 1)
        return box

    # ==== completed release (tool contract 14) =====================================================
    def release(self, plan="__stored__", token=TOKEN, key=KEY):
        from app import account_blocks

        if plan == "__stored__":
            plan = self.recovery_rows()[1][0]["plan_fingerprint"]
        return account_blocks.release_block(self.U, key, token, "completed", plan=plan)

    def verified_world(self):
        self.mixed_world()
        self.prepare()
        self.recover()
        self.verify()
        return self.recovery_rows()[1][0]["plan_fingerprint"]

    def assert_release_refused(self, fn, code):
        versions, rows = self.row_versions(), self.recovery_rows()
        with self.sql_trace() as statements:
            self.refused(fn, code)
        self.assertEqual(self.writes(statements), [])
        self.assertEqual((self.row_versions(), self.recovery_rows()), (versions, rows))
        self.assertEqual(self.recovery_rows()[0][0]["status"], "active")

    def test_completed_release_after_verify_and_writes_resume(self):
        from app import recovery

        plan = self.verified_world()
        others = self.others_hash()
        with self.sql_trace() as statements:
            result = self.release(plan)
        self.assertEqual((result["released"], result["created"], result["reason"]), (True, True, "completed"))
        self.assertEqual(len(self.writes(statements)), 2)                          # record closed + block released
        blocks, records = self.recovery_rows()
        self.assertEqual((blocks[0]["status"], blocks[0]["release_reason"]), ("released", "completed"))
        self.assertEqual((records[0]["state"], records[0]["close_reason"]), ("closed", "completed"))
        self.assertEqual(recovery.resume_status(self.U, KEY), {"next": "closed"})
        response = s.request("POST", "/decks", {"name": "u-after-release"}, self.token())
        self.assertEqual(response.status_code, 200, response.text[:200])          # ordinary writes again
        self.assertEqual(self.others_hash(), others)

    def test_completed_release_recall_writes_nothing(self):
        from _e5b_fixture import card

        plan = self.verified_world()
        self.release(plan)
        card(self.U, self.deck, "rec-after")                                      # ordinary writes change the data
        versions = self.row_versions()
        with self.sql_trace() as statements:
            again = self.release(plan)
        self.assertEqual((again["released"], again["created"]), (True, False))
        self.assertEqual(self.writes(statements), [])
        self.assertEqual(self.row_versions(), versions)
        with self.sql_trace() as statements:
            self.refused(lambda: self.release(plan, token=OTHER_TOKEN), "recovery_grant_invalid")
            self.refused(lambda: self.release("f" * 64), "recovery_plan_mismatch")
        self.assertEqual(self.writes(statements), [])

    def test_completed_release_refusals_write_nothing(self):
        from app import recovery

        cases = ("before_verify", "stale_digest", "missing_check", "damaged_proof", "fsrs_card_left", "wrong_mode",
                 "partial_result", "no_plan", "wrong_plan", "wrong_token", "wrong_key")
        for name in cases:
            with self.subTest(name):
                self.reset_world()
                self.mixed_world()
                self.prepare()
                self.recover()
                if name != "before_verify":
                    self.verify()
                plan = self.recovery_rows()[1][0]["plan_fingerprint"]
                record = self.recovery_rows()[1][0]
                if name == "stale_digest":
                    sql("UPDATE vocab_items SET review_level = review_level + 1 WHERE id = ?", (self.cards[0],))
                    code = "verification_not_current"
                elif name == "damaged_proof":
                    sql("UPDATE account_recovery_runs SET verification_json = '{}' WHERE id = ?", (record["id"],))
                    code = "release_not_allowed"
                elif name == "fsrs_card_left":
                    sql("UPDATE vocab_items SET srs_engine = 'fsrs' WHERE id = ?", (self.cards[0],))
                    code = "release_not_allowed"
                elif name == "wrong_mode":
                    sql("UPDATE srs_user_settings SET srs_mode = 'shadow' WHERE user_id = ?", (self.U,))
                    code = "release_not_allowed"
                elif name == "partial_result":
                    run = sql("SELECT id, summary_json FROM srs_migration_runs WHERE run_key LIKE ? ORDER BY id",
                              ("prb:%",))[0]
                    sql("UPDATE srs_migration_runs SET summary_json = ? WHERE id = ?",
                        (json.dumps(json.loads(run["summary_json"])[:-1]), run["id"]))
                    code = "release_not_allowed"
                else:
                    code = {"before_verify": "release_not_allowed", "missing_check": "release_not_allowed",
                            "no_plan": "release_not_allowed", "wrong_plan": "recovery_plan_mismatch",
                            "wrong_token": "recovery_grant_invalid", "wrong_key": "recovery_state_inconsistent"}[name]
                fn = {"no_plan": lambda: self.release(None), "wrong_plan": lambda: self.release("f" * 64),
                      "wrong_token": lambda: self.release(plan, token=OTHER_TOKEN),
                      "wrong_key": lambda: self.release(plan, key="prb-rec-other")}.get(name, lambda: self.release(plan))
                if name == "missing_check":
                    real = recovery._checks
                    with mock.patch.object(recovery, "_checks", lambda *a, **k: self.change_a(
                            real(*a, **k), drop="I2a")):
                        self.assert_release_refused(fn, code)
                else:
                    self.assert_release_refused(fn, code)

    def test_a_release_failure_rolls_back_both_rows(self):
        from app import account_blocks, database

        plan = self.verified_world()
        real = database.get_connection

        class Failing:
            def __init__(self):
                self.connection = real()

            def __enter__(self):
                outer = self

                class Proxy:
                    def __getattr__(self, name):
                        return getattr(outer.connection, name)

                    def execute(self, query, params=()):
                        if query.startswith("UPDATE account_write_blocks SET status = 'released'"):
                            raise RuntimeError("injected")
                        return outer.connection.execute(query, params)
                self.connection.__enter__()
                return Proxy()

            def __exit__(self, *exc):
                return self.connection.__exit__(*exc)

        rows = self.recovery_rows()
        with mock.patch.object(account_blocks, "get_connection", lambda: Failing()), self.assertRaises(RuntimeError):
            self.release(plan)
        self.assertEqual(self.recovery_rows(), rows)
        # data changed between the read proof and the lock: refused, nothing written
        with mock.patch.object(account_blocks, "_between_proof_and_lock", lambda: sql(
                "UPDATE vocab_items SET review_level = review_level + 1 WHERE id = ?", (self.cards[0],))):
            self.refused(lambda: self.release(plan), "release_not_allowed")
        self.assertEqual(self.recovery_rows(), rows)

    def _release_first(self, waiter, expect):
        from app import account_blocks

        plan = self.recovery_rows()[1][0]["plan_fingerprint"]
        patch, probe = self.waiting_probe()[:2]
        run = HoldThenWait(probe)
        real = account_blocks.lock_account

        def paused(connection, user_id):
            real(connection, user_id)
            run.pause()

        with patch, mock.patch.object(account_blocks, "lock_account", paused):
            box = run.run(lambda: self.release(plan), waiter)
        self.assertTrue(box["held"] and box["waited"] and box["joined"], box)
        self.assertEqual((box["hold"][0], box["hold"][1]["created"]), ("ok", True), box)
        if expect == "ok":
            self.assertEqual(box["delete"][0], "ok", box)
        else:
            self.assertEqual((box["delete"][0], getattr(box["delete"][1], "code", None)), ("error", expect), box)
        return box

    def _write_first_then_release(self, writer_lock_owner, writer, expect_writer):
        """The other side takes the account lock first (paused just after it); the release
        waits for it, then decides on what that side committed."""
        from app import account_write

        plan = self.recovery_rows()[1][0]["plan_fingerprint"]
        patch, probe = self.waiting_probe()[:2]
        run = HoldThenWait(probe)
        real = account_write.lock_account

        def paused(connection, user_id):
            real(connection, user_id)
            run.pause()

        with patch, mock.patch.object(account_write, "lock_account", paused):
            box = run.run(writer, lambda: self.release(plan))
        self.assertTrue(box["held"] and box["waited"] and box["joined"], box)
        self.assertEqual(box["hold"][0], expect_writer[0], box)
        return box

    def test_release_first_then_ordinary_write_succeeds_after_it(self):
        self.verified_world()
        return self._release_first(lambda: self.fsrs_review_or_deck(), "ok")

    def fsrs_review_or_deck(self):
        from app.repositories import deck_repository as decks
        from app.schemas import DeckCreate

        return decks.create_deck(self.U, DeckCreate(name="u-waited"))

    def test_ordinary_write_first_is_refused_then_release_completes(self):
        box = None
        self.verified_world()
        box = self._write_first_then_release("writer", self.fsrs_review_or_deck, ("error",))
        self.assertEqual(getattr(box["hold"][1], "code", None), "account_writes_blocked")
        self.assertEqual((box["delete"][0], box["delete"][1]["created"]), ("ok", True), box)
        return box

    def test_release_first_then_authorized_rollback_is_refused(self):
        from app.account_write import RecoveryGrant
        from app.srs import migration

        self.verified_world()
        grant = RecoveryGrant(user_id=self.U, recovery_key=KEY, action="rollback", token=TOKEN)
        return self._release_first(lambda: migration.rollback_plan("rec-run-1", "rec-rb-late", user_id=self.U,
                                                                   approved=True, recovery=grant),
                                   "recovery_grant_invalid")

    def test_authorized_rollback_first_then_release_is_refused(self):
        from app.account_write import RecoveryGrant
        from app.srs import migration

        self.verified_world()
        grant = RecoveryGrant(user_id=self.U, recovery_key=KEY, action="rollback", token=TOKEN)
        box = self._write_first_then_release("writer", lambda: migration.rollback_plan(
            "rec-run-1", "rec-rb-late", user_id=self.U, approved=True, recovery=grant), ("ok",))
        self.assertEqual(box["delete"][0], "error", box)
        self.assertEqual(self.recovery_rows()[0][0]["status"], "active")
        return box

    # ---- cleanup tools around the block and the release -----------------------------------------
    def purge_receipts(self):
        from app.database import get_connection, now_utc
        from app.srs import receipts
        from app.srs.engine import to_utc
        from app.srs.storage import begin_card_write

        with get_connection() as connection:
            # judged 10 days later, when every receipt of the account is past its expiry
            return receipts.minimize_receipts(connection, self.U, to_utc(now_utc()) + timedelta(days=10), apply=True,
                                              purge_expired=True, lock=begin_card_write)

    @staticmethod
    def _with_connection(fn):
        from contextlib import closing

        from app.database import get_connection

        with closing(get_connection()) as connection:
            with connection:
                return fn(connection)

    def test_cleanup_tools_are_refused_while_blocked(self):
        from app.database import get_connection
        from app.srs import migration
        from app.srs.storage import begin_card_write

        self.mixed_world()
        self.prepare()
        for name, call in (("receipts", self.purge_receipts),
                           ("snapshot_minimize", lambda: self._with_connection(lambda c: migration.minimize_snapshots(
                               c, self.U, apply=True, lock=begin_card_write, progress={}))),
                           ("snapshot_prune", lambda: self._with_connection(lambda c: migration.prune_expired_runs(
                               c, self.U, apply=True, lock=begin_card_write, progress={})))):
            with self.subTest(name):
                before = self.data_hash()
                with self.sql_trace() as statements:
                    try:
                        result = call()
                    except Exception as error:                                     # noqa: BLE001
                        result = getattr(error, "code", type(error).__name__)
                self.assertEqual(self.writes(statements), [], (name, result))
                self.assertEqual(self.data_hash(), before)

    def test_release_first_then_receipt_purge_runs_after_it(self):
        self.verified_world()
        box = self._release_first(self.purge_receipts, "ok")
        self.assertEqual(sql("SELECT count(*) AS n FROM srs_review_receipts WHERE user_id = ?", (self.U,))[0]["n"], 0)
        return box

    def test_receipt_purge_first_is_refused_then_release_completes(self):
        self.verified_world()
        box = self._write_first_then_release("writer", self.purge_receipts, ("error",))
        self.assertEqual((box["delete"][0], box["delete"][1]["created"]), ("ok", True), box)
        self.assertGreater(sql("SELECT count(*) AS n FROM srs_review_receipts WHERE user_id = ?", (self.U,))[0]["n"], 0)
        return box

    def test_cli_releases_with_hidden_input(self):
        sys.path.insert(0, str(BACKEND / "scripts"))
        import prb_recover

        plan = self.verified_world()
        printed = []
        code = prb_recover.main(["release", "--user-id", str(self.U), "--recovery-key", KEY, "--plan", plan],
                                ask=lambda _: str(self.U), secret=lambda _: TOKEN, out=printed.append)
        self.assertEqual((code, json.loads(printed[-1])["reason"]), (0, "completed"))
        self.assertNotIn(TOKEN, "".join(printed))

    # ---- completed release review fixes ----------------------------------------------------------
    def test_release_rechecks_the_stored_proof_under_the_lock(self):
        """Fix 2: after R, the stored proof itself changes (a check turned to fail, damaged,
        a missing check, another time): the locked transaction refuses, writes nothing."""
        from app import account_blocks

        changes = {
            "check_failed": lambda r: ("verification_json", json.dumps(self.change_a(
                json.loads(r["verification_json"]), I6_recovery={"status": "fail"}), sort_keys=True, separators=(",", ":"))),
            "check_missing": lambda r: ("verification_json", json.dumps(self.change_a(
                json.loads(r["verification_json"]), drop="I1a"), sort_keys=True, separators=(",", ":"))),
            "n_failed": lambda r: ("verification_json", json.dumps(dict(
                json.loads(r["verification_json"]), N={"status": "fail"}), sort_keys=True, separators=(",", ":"))),
            "damaged": lambda r: ("verification_json", "not-json"),
            "other_time": lambda r: ("verified_at", r["applied_at"]),
        }
        for name, change in changes.items():
            with self.subTest(name):
                self.reset_world()
                plan = self.verified_world()
                record = self.recovery_rows()[1][0]
                versions = self.row_versions()
                column, value = change(record)
                hook = f"UPDATE account_recovery_runs SET {column} = ? WHERE id = ?"
                with self.sql_trace() as statements, mock.patch.object(
                        account_blocks, "_between_proof_and_lock", lambda: sql(hook, (value, record["id"]))):
                    self.refused(lambda: self.release(plan), "release_not_allowed")
                writes = [q for q in self.writes(statements) if not q.startswith("UPDATE account_recovery_runs SET "
                                                                                  f"{column} = ?")]
                self.assertEqual(writes, [])
                if versions is not None:   # PostgreSQL: block and settings rows not rewritten
                    now = self.row_versions()
                    self.assertEqual((now[0], now[2]), (versions[0], versions[2]))
                blocks, records = self.recovery_rows()
                self.assertEqual((blocks[0]["status"], records[0]["state"]), ("active", "verified"))

    def test_the_same_release_twice_at_once(self):
        """Fix 3: two identical releases, both past R; the second waits for the lock, then finds
        the finished release in its own locked transaction and writes nothing."""
        from app import account_blocks

        plan = self.verified_world()
        real = account_blocks.lock_account
        with self.sql_trace() as statements:
            patch, probe = self.waiting_probe()[:2]
            run = HoldThenWait(probe)

            def paused(connection, user_id):
                real(connection, user_id)
                run.pause()

            with patch, mock.patch.object(account_blocks, "lock_account", paused):
                box = run.run(lambda: self.release(plan), lambda: self.release(plan))
        self.assertTrue(any(name == "deleter" for name, _ in statements), statements[:3])   # traced, not vacuous
        self.assertTrue(box["held"] and box["waited"] and box["joined"], box)
        self.assertEqual(box["hold"][0], "ok", box)
        self.assertEqual(box["delete"][0], "ok", box)
        self.assertEqual([box["hold"][1]["created"], box["delete"][1]["created"]], [True, False], box)
        self.assertEqual(self.writes(statements, "deleter"), [])
        self.assertEqual(len(self.writes(statements, "writer")), 2)
        blocks, records = self.recovery_rows()
        self.assertEqual((blocks[0]["status"], records[0]["state"]), ("released", "closed"))
        return box

    # ==== check scope: A (account), N (inflow), S (global sequence), G (diagnostic) -- 15-4 ====
    def u_log(self):
        return sql("SELECT id FROM review_logs WHERE user_id = ? ORDER BY id", (self.U,))[0]["id"]

    def sequence_value(self):
        if self.db_kind == "postgresql":
            name = sql("SELECT pg_get_serial_sequence('vocab_items', 'id') AS n")[0]["n"]
            return sql(f"SELECT last_value AS v FROM {name}")[0]["v"]
        rows = sql("SELECT seq FROM sqlite_sequence WHERE name = 'vocab_items'")
        return rows[0]["seq"] if rows else 0

    def ledger(self, user_id, ref):
        from app.database import now_iso

        sql("INSERT INTO srs_card_deletions (card_kind, user_id, card_ref, deleted_at) VALUES ('personal', ?, ?, ?)",
            (user_id, ref, now_iso()))

    def feedback(self, user_id, ref):
        from app.database import now_iso

        sql("INSERT INTO meaning_feedback (user_id, vocabulary_id, surface, created_at) VALUES (?, ?, 'x', ?)",
            (user_id, ref, now_iso()))

    def inflows(self):
        """Other-account rows that point INTO the target's spaces (contract 15-4 N)."""
        return {
            "feedback_to_u_card": lambda: self.feedback(self.O, self.cards[0]),
            "o_card_boundary_to_u_log": lambda: sql("UPDATE vocab_items SET evidence_from_log_id = ? WHERE id = ?",
                                                    (self.u_log(), self.o_card)),
            "o_ledger_of_u_card": lambda: self.ledger(self.O, self.cards[1]),
            "o_log_on_u_card": lambda: sql(
                "INSERT INTO review_logs (user_id, vocab_item_id, rating, reviewed_at, previous_review_level, "
                "next_review_level, next_review_at) SELECT ?, vocab_item_id, rating, reviewed_at, previous_review_level, "
                "next_review_level, next_review_at FROM review_logs WHERE id = ?", (self.O, self.u_log())),
        }

    def unrelated_damage(self):
        """Damage of another account that provably does not touch the target: an orphan log
        (its card row removed without the ledger) and a card boundary on a missing log."""
        from _e5b_fixture import card
        from app.repositories import deck_repository as decks
        from app.schemas import DeckCreate

        deck = decks.create_deck(self.O, DeckCreate(name="o-damaged"))[0]["id"]
        lost = card(self.O, deck, "rec-o-lost")
        sql("INSERT INTO review_logs (user_id, vocab_item_id, rating, reviewed_at, previous_review_level, "
            "next_review_level, next_review_at) VALUES (?, ?, 'good', '2026-01-01T00:00:00+00:00', 0, 1, "
            "'2026-01-02T00:00:00+00:00')", (self.O, lost))
        sql("DELETE FROM vocab_items WHERE id = ?", (lost,))                          # no ledger: I1 orphan
        sql("UPDATE vocab_items SET evidence_from_log_id = ? WHERE id = ?", (987654321, self.o_card))   # I5

    def test_scope_unrelated_damage_is_diagnostic_only(self):
        """Another account's damage that cannot touch the target shows in G as fail and does
        not stop verify or the release; A, N and S pass."""
        self.mixed_world()
        self.prepare()
        self.recover()
        self.unrelated_damage()
        checked = self.verify()
        self.assertEqual(checked["status"], "verified", checked)
        self.assertEqual(set(checked["checks"].values()), {"pass"}, checked)
        self.assertEqual((checked["diagnostics"]["I1"], checked["diagnostics"]["I5"]), ("fail", "fail"), checked)
        stored = json.loads(self.recovery_rows()[1][0]["verification_json"])
        self.assertEqual((stored["G"]["I1"]["status"], stored["G"]["I5"]["status"]), ("fail", "fail"))
        plan = self.recovery_rows()[1][0]["plan_fingerprint"]
        released = self.release(plan)
        self.assertEqual((released["created"], released["diagnostics"]["I1"]), (True, "fail"), released)

    def test_scope_target_damage_is_refused(self):
        """The target's own rows: a log moved to another account's card, an unflagged
        identity finding of the target: A fails, verify writes nothing."""
        cases = {
            "log_on_other_card": (lambda: sql("UPDATE review_logs SET vocab_item_id = ? WHERE id = ?",
                                              (self.o_card, self.u_log())), "I2a"),
            "u_boundary_to_o_log": (lambda: sql("UPDATE vocab_items SET evidence_from_log_id = ? WHERE id = ?",
                                                (self.o_log(), self.cards[1])), "I5a"),
        }
        for name, (damage, check) in cases.items():
            with self.subTest(name):
                self.reset_world()
                self.mixed_world()
                self.prepare()
                self.recover()
                damage()
                stored = self.recovery_rows()
                with self.sql_trace() as statements:
                    result = self.verify()
                self.assertEqual((result["status"], result["checks"][check]), ("not_verified", "fail"), result)
                self.assertEqual(self.writes(statements), [])
                self.assertEqual(self.recovery_rows(), stored)

    def o_log(self):
        from app.repositories import vocab_repository as vocab

        rows = sql("SELECT id FROM review_logs WHERE user_id = ? ORDER BY id", (self.O,))
        if not rows:
            vocab.record_review(self.O, self.o_card, "good")
            rows = sql("SELECT id FROM review_logs WHERE user_id = ? ORDER BY id", (self.O,))
        return rows[0]["id"]

    def test_scope_inflow_before_verify_is_refused(self):
        for name, make in self.inflows().items():
            with self.subTest(name):
                self.reset_world()
                self.mixed_world()
                self.prepare()
                self.recover()
                make()
                result = self.verify()
                self.assertEqual((result["status"], result["checks"]["N"]), ("not_verified", "fail"), result)
                self.assertEqual(self.recovery_rows()[1][0]["state"], "applied")

    def test_scope_inflow_after_r_is_refused_under_the_lock(self):
        """R passes; another account then creates a reference into the target (D unchanged):
        the locked transaction re-reads N and refuses. Nothing but the hook's own row is written."""
        from app import account_blocks

        for name, make in self.inflows().items():
            with self.subTest(name):
                self.reset_world()
                plan = self.verified_world()
                versions = self.row_versions()
                with self.sql_trace() as statements, mock.patch.object(account_blocks, "_between_proof_and_lock", make):
                    self.refused(lambda: self.release(plan), "release_not_allowed")
                # the hook's own row is the only write: no block / record statement
                self.assertEqual([q for q in self.writes(statements) if "account_" in q], [])
                if versions is not None:
                    self.assertEqual(self.row_versions(), versions)
                blocks, records = self.recovery_rows()
                self.assertEqual((blocks[0]["status"], records[0]["state"]), ("active", "verified"))
                self.refused(lambda: self.release(plan), "release_not_allowed")    # R sees it now

    def test_scope_unresolvable_reference_is_refused(self):
        """A reference whose owner cannot be read and whose value is in the target's space
        cannot be excluded: N is unknown -- refused at verify, and under the lock after R."""
        from app import account_blocks

        self.mixed_world()
        self.prepare()
        self.recover()
        self.ledger(None, self.cards[0])
        result = self.verify()
        self.assertEqual((result["status"], result["checks"]["N"]), ("not_verified", "unknown"), result)
        sql("DELETE FROM srs_card_deletions WHERE user_id IS NULL")
        self.assertEqual(self.verify()["status"], "verified")
        plan = self.recovery_rows()[1][0]["plan_fingerprint"]
        with mock.patch.object(account_blocks, "_between_proof_and_lock", lambda: self.ledger(None, self.cards[1])):
            self.refused(lambda: self.release(plan), "release_not_allowed")
        self.assertEqual(self.recovery_rows()[0][0]["status"], "active")
        # an owner-less row OUTSIDE the target's space is provably unrelated: not N
        sql("DELETE FROM srs_card_deletions WHERE user_id IS NULL")
        self.ledger(None, self.o_card)
        self.assertEqual(self.verify()["checks"]["N"], "pass")

    def test_scope_two_accounts_on_one_lexeme_pass(self):
        """A third account studies the very lexeme the target recovers: its own (user, lexeme)
        rows are not an inflow; verify and release pass."""
        from _e5b_fixture import set_mode
        from app.repositories import lexeme_repository as lexemes, user_repository as users

        self.mixed_world()
        third = users.create_user("rec-p@e5b.example.test", "rec-p", "synthetic")["id"]
        set_mode(third, "legacy")
        lexemes.get_or_create_subscription(third, self.shared)
        lexemes.update_word_status(third, self.lexeme, "unknown")
        lexemes.record_lexeme_review(third, self.lexeme, "good", self.shared)
        lexemes.record_lexeme_review(third, self.lexeme, "hard", self.shared)
        self.assertEqual(len(sql("SELECT id FROM lexeme_review_logs WHERE lexeme_id = ? AND user_id = ?",
                                 (self.lexeme, third))), 2)
        self.prepare()
        self.recover()
        checked = self.verify()
        self.assertEqual((checked["status"], checked["checks"]["N"]), ("verified", "pass"), checked)
        self.assertTrue(self.release()["created"])

    def test_scope_sequence_counts_every_account(self):
        """S compares the sequence with the largest personal card reference of EVERY account:
        the target's references are low, another account's kept reference is above it."""
        from app import account_blocks

        self.mixed_world()
        self.prepare()
        self.recover()
        top = self.sequence_value()
        self.ledger(self.O, top)                                # a tie with the sequence: normal
        self.assertEqual(self.verify()["checks"]["S"], "pass")
        self.ledger(self.O, top + 50)
        result = self.verify()
        self.assertEqual((result["status"], result["checks"]["S"], result["diagnostics"]["I3"]),
                         ("not_verified", "fail", "fail"), result)
        sql("DELETE FROM srs_card_deletions WHERE card_ref = ?", (top + 50,))
        self.assertEqual(self.verify()["status"], "verified")
        plan = self.recovery_rows()[1][0]["plan_fingerprint"]
        with mock.patch.object(account_blocks, "_between_proof_and_lock", lambda: self.ledger(self.O, top + 70)):
            self.refused(lambda: self.release(plan), "release_not_allowed")
        self.assertEqual(self.recovery_rows()[0][0]["status"], "active")

    def old_proof(self):
        """A `verified` record in the pre-15-4 shape: nine flat checks, all pass."""
        old = {name: {"status": "pass"} for name in ("I1", "I2", "I3", "I4", "I5", "I6_recovery", "I7_recovery",
                                                     "completion_history", "recovery_result")}
        text = json.dumps(old, sort_keys=True, separators=(",", ":"))
        sql("UPDATE account_recovery_runs SET verification_json = ? WHERE user_id = ?", (text, self.U))
        return text

    def test_scope_old_proof_needs_explicit_verify(self):
        from app import recovery

        plan = self.verified_world()
        old = self.old_proof()
        record = self.recovery_rows()[1][0]
        self.assertEqual(recovery.resume_status(self.U, KEY), {"next": "verify"})
        self.assert_release_refused(lambda: self.release(plan), "verification_not_current")
        # a proof that changes between verify's read and its locked save: stale, nothing saved
        with mock.patch.object(recovery, "_between_read_and_save", lambda: sql(
                "UPDATE account_recovery_runs SET verified_at = ? WHERE id = ?", (record["applied_at"], record["id"]))):
            self.refused(self.verify, "verification_stale")
        sql("UPDATE account_recovery_runs SET verified_at = ? WHERE id = ?", (record["verified_at"], record["id"]))
        checked = self.verify()
        self.assertEqual((checked["status"], checked["created"], checked["refreshed"]), ("verified", True, True))
        after = self.recovery_rows()[1][0]
        stored = json.loads(after["verification_json"])
        self.assertEqual((stored["version"], set(stored)), (2, {"version", "A", "N", "S", "G"}))
        self.assertTrue(recovery.proof_ok(stored))
        self.assertFalse(recovery.proof_ok(json.loads(old)))
        self.assertEqual((after["baseline_json"], after["verified_digest"]), (record["baseline_json"],
                                                                              record["verified_digest"]))
        self.assertEqual(recovery.resume_status(self.U, KEY), {"next": "await_release"})
        self.assertTrue(self.release(plan)["created"])

    def test_scope_old_proof_failed_reverify_keeps_everything(self):
        plan = self.verified_world()
        self.old_proof()
        self.feedback(self.O, self.cards[0])                     # an inflow: the new check fails
        stored = self.recovery_rows()
        with self.sql_trace() as statements:
            result = self.verify()
        self.assertEqual((result["status"], result["checks"]["N"]), ("not_verified", "fail"))
        self.assertEqual(self.writes(statements), [])
        self.assertEqual(self.recovery_rows(), stored)             # baseline and the past proof kept
        self.assert_release_refused(lambda: self.release(plan), "verification_not_current")

    def test_verify_rechecks_inflow_and_sequence_under_the_lock(self):
        from app import recovery

        for name, make in (("inflow", lambda: self.feedback(self.O, self.cards[0])),
                           ("sequence", lambda: self.ledger(self.O, self.sequence_value() + 70))):
            with self.subTest(name):
                self.reset_world()
                self.mixed_world()
                self.prepare()
                self.recover()
                with mock.patch.object(recovery, "_between_read_and_save", make):
                    self.refused(self.verify, "verification_stale")
                self.assertEqual(self.recovery_rows()[1][0]["state"], "applied")

    def test_proof_format_is_one_rule(self):
        from app import recovery

        plan = self.verified_world()
        good = json.loads(self.recovery_rows()[1][0]["verification_json"])
        self.assertTrue(recovery.proof_ok(good))
        broken = {
            "version_1": dict(good, version=1), "version_bool": dict(good, version=True),
            "extra_key": dict(good, extra={}), "missing_g": {k: v for k, v in good.items() if k != "G"},
            "a_missing": dict(good, A={k: v for k, v in good["A"].items() if k != "I4a"}),
            "a_extra": dict(good, A=dict(good["A"], I3={"status": "pass"})),
            "n_unknown": dict(good, N=dict(good["N"], status="unknown")),
            "s_fail": dict(good, S=dict(good["S"], status="fail")),
            "g_bad_status": dict(good, G=dict(good["G"], I2={"status": "pass?"})),
            "g_missing": dict(good, G={k: v for k, v in good["G"].items() if k != "I3"}),
        }
        for name, value in broken.items():
            self.assertFalse(recovery.proof_ok(value), name)
        # G fail is diagnostic: still a valid proof
        self.assertTrue(recovery.proof_ok(dict(good, G=dict(good["G"], I1={"status": "fail"}))))
        record = self.recovery_rows()[1][0]
        sql("UPDATE account_recovery_runs SET verification_json = ? WHERE id = ?",
            (json.dumps(broken["n_unknown"], sort_keys=True, separators=(",", ":")), record["id"]))
        self.assertEqual(recovery.resume_status(self.U, KEY)["next"], "report_only")
        self.assert_release_refused(lambda: self.release(plan), "release_not_allowed")

    def test_overlapping_inflow_write_is_an_observation(self):
        """A real overlap: the release holds the target's lock; another account's locked write
        creates an inflow. SQLite: the writer waits for the release (one database lock), the
        release completes, the inflow lands after it. PostgreSQL: the writer does NOT wait (a
        different account's lock), commits first, and the release's locked re-read of N refuses."""
        from app import account_blocks
        from app.account_write import lock_account
        from app.database import get_connection

        plan = self.verified_world()
        log = self.u_log()
        order = []

        def inflow():
            with get_connection() as connection:
                lock_account(connection, self.O)
                connection.execute("UPDATE vocab_items SET evidence_from_log_id = ? WHERE id = ?", (log, self.o_card))
            order.append("inflow")

        def release():
            try:
                return self.release(plan)
            finally:
                order.append("release")

        real = account_blocks.lock_account
        with self.sql_trace() as statements:
            patch, probe = self.waiting_probe()[:2]
            run = HoldThenWait(probe)

            def paused(connection, user_id):
                real(connection, user_id)
                run.pause()

            with patch, mock.patch.object(account_blocks, "lock_account", paused):
                box = run.run(release, inflow)
        self.assertTrue(box["held"] and box["joined"], box)
        self.assertEqual(box["delete"][0], "ok", box)
        if self.db_kind == "postgresql":
            self.assertFalse(box["waited"], box)
            self.assertEqual(order, ["inflow", "release"])
            self.assertEqual((box["hold"][0], getattr(box["hold"][1], "code", None)), ("error", "release_not_allowed"))
            self.assertEqual(self.writes(statements, "writer"), [])
            self.assertEqual(self.recovery_rows()[0][0]["status"], "active")
        else:
            self.assertTrue(box["waited"], box)
            self.assertEqual(order, ["release", "inflow"])
            self.assertEqual((box["hold"][0], box["hold"][1]["created"]), ("ok", True), box)
            self.assertEqual(self.recovery_rows()[0][0]["status"], "released")
        return box

    # ---- check scope review fixes: I2a progress rows, snapshot restart.rollback_record_id ----------
    def legacy_subscription(self):
        """A second, legacy subscribed card of the target (another shared deck): reviewed, with
        its progress row, never converted -- so it is NOT in the baseline's preserved cards."""
        from _e5b_fixture import card, set_mode
        from app.repositories import deck_repository as decks, lexeme_repository as lexemes
        from app.repositories import shared_deck_repository as shared
        from app.schemas import DeckCreate

        o_deck = decks.create_deck(self.O, DeckCreate(name="o-deck-2"))[0]["id"]
        card(self.O, o_deck, "rec-o-word-2")
        deck = shared.publish_deck(self.O, o_deck, "rec-shared-2", "")["shared_deck_id"]
        lexeme = sql("SELECT lexeme_id FROM shared_deck_words WHERE shared_deck_id = ?", (deck,))[0]["lexeme_id"]
        set_mode(self.U, "legacy")
        lexemes.get_or_create_subscription(self.U, deck)
        lexemes.update_word_status(self.U, lexeme, "unknown")
        lexemes.record_lexeme_review(self.U, lexeme, "good", deck)
        set_mode(self.U, "fsrs")
        return lexeme

    def drop_progress(self, lexeme):
        sql("DELETE FROM user_word_progress WHERE user_id = ? AND lexeme_id = ?", (self.U, lexeme))

    def test_missing_progress_of_a_legacy_subscription_is_refused(self):
        """Codex repro: after B the progress row of a NON-target legacy subscribed card is
        deleted (its log kept). I2a fails (not only a count); verify, resume and the release
        refuse; nothing is restored, synthesized or written; the block stays."""
        from app import account_blocks, recovery

        self.mixed_world()
        lexeme = self.legacy_subscription()
        plan = self.verified_world_from_here()
        base = json.loads(self.recovery_rows()[1][0]["baseline_json"])
        self.assertNotIn(["lexeme", lexeme], [c[:2] for c in base["cards"]])        # not a preserved card
        # before R: the stored proof is a past record; every path refuses
        self.drop_progress(lexeme)
        self.assertEqual(sql("SELECT count(*) AS n FROM lexeme_review_logs WHERE user_id = ? AND lexeme_id = ?",
                             (self.U, lexeme))[0]["n"], 1)
        self.assertEqual(recovery.resume_status(self.U, KEY),
                         {"next": "report_only", "reason": "verification_not_current"})
        stored = self.recovery_rows()
        with self.sql_trace() as statements:
            result = self.verify()
        self.assertEqual((result["status"], result["checks"]["I2a"]), ("not_verified", "fail"), result)
        self.assertEqual(self.writes(statements), [])
        self.assertEqual(self.recovery_rows(), stored)
        self.assert_release_refused(lambda: self.release(plan), "release_not_allowed")      # the gate fails in R
        self.assertEqual(sql("SELECT count(*) AS n FROM user_word_progress WHERE user_id = ? AND lexeme_id = ?",
                             (self.U, lexeme))[0]["n"], 0)                         # nothing synthesized
        # after R, before the release lock
        self.reset_world()
        self.mixed_world()
        lexeme = self.legacy_subscription()
        plan = self.verified_world_from_here()
        with self.sql_trace() as statements, mock.patch.object(
                account_blocks, "_between_proof_and_lock", lambda: self.drop_progress(lexeme)):
            self.refused(lambda: self.release(plan), "release_not_allowed")
        self.assertEqual([q for q in self.writes(statements) if "account_" in q], [])
        blocks, records = self.recovery_rows()
        self.assertEqual((blocks[0]["status"], records[0]["state"]), ("active", "verified"))

    def test_progress_check_unit(self):
        from app.database import get_connection
        from app.srs import recovery_scope

        self.mixed_world()
        lexeme = self.legacy_subscription()
        with get_connection() as c:
            self.assertEqual(recovery_scope.account(c, self.U)["I2a"]["status"], "pass")   # normal subscriptions
        self.drop_progress(lexeme)
        with get_connection() as c:
            i2a = recovery_scope.account(c, self.U)["I2a"]
        self.assertEqual((i2a["status"], i2a["violations"], i2a["subscribed_logs_without_progress"]), ("fail", 1, 1))

    def verified_world_from_here(self):
        self.prepare()
        self.recover()
        self.assertEqual(self.verify()["status"], "verified")
        return self.recovery_rows()[1][0]["plan_fingerprint"]

    def convert_other(self):
        """The other account converts its own reviewed card: one apply snapshot of O."""
        from _e5b_fixture import set_mode
        from app.repositories import vocab_repository as vocab
        from app.srs import migration
        from app.srs.engine import CardKey

        set_mode(self.O, "legacy")
        vocab.record_review(self.O, self.o_card, "good")
        set_mode(self.O, "fsrs")
        migration.apply_plan(migration.dry_run([CardKey("personal", self.O, self.o_card)]), "rec-run-o", approved=True)
        return sql("SELECT id FROM srs_migration_snapshots WHERE user_id = ?", (self.O,))[0]["id"]

    def set_restart(self, snapshot_id, value):
        """Write restart {previous_boundary: the card's own log, rollback_record_id: value}."""
        row = sql("SELECT user_id, card_ref, legacy_json FROM srs_migration_snapshots WHERE id = ?", (snapshot_id,))[0]
        log = sql("SELECT id FROM review_logs WHERE user_id = ? AND vocab_item_id = ? ORDER BY id",
                  (row["user_id"], row["card_ref"]))[0]["id"]
        body = json.loads(row["legacy_json"])
        body["restart"] = {"previous_boundary": log, "rollback_record_id": value}
        sql("UPDATE srs_migration_snapshots SET legacy_json = ? WHERE id = ?", (json.dumps(body), snapshot_id))

    def u_snapshot(self, mode="apply"):
        return sql("SELECT s.id FROM srs_migration_snapshots s JOIN srs_migration_runs r ON r.id = s.run_id "
                   "WHERE s.user_id = ? AND s.card_kind = 'personal' AND r.mode = ? ORDER BY s.id",
                   (self.U, mode))[0]["id"]

    def test_restart_rollback_record_inflow_is_refused(self):
        """Codex repro: another account's apply snapshot names a TARGET snapshot in
        restart.rollback_record_id (a snapshot id, not a log id): N fails before R, and under
        the lock after R; an unreadable value is unknown. Nothing written, the block stays."""
        from app import account_blocks

        for name in ("before_r", "after_r", "unreadable"):
            with self.subTest(name):
                self.reset_world()
                self.mixed_world()
                o_snap = self.convert_other()
                plan = self.verified_world_from_here()
                target = self.u_snapshot()
                if name == "after_r":
                    with self.sql_trace() as statements, mock.patch.object(
                            account_blocks, "_between_proof_and_lock", lambda: self.set_restart(o_snap, target)):
                        self.refused(lambda: self.release(plan), "release_not_allowed")
                    self.assertEqual([q for q in self.writes(statements) if "account_" in q], [])
                else:
                    self.set_restart(o_snap, target if name == "before_r" else "x")
                    with self.sql_trace() as statements:
                        result = self.verify()
                    self.assertEqual((result["status"], result["checks"]["N"]),
                                     ("not_verified", "fail" if name == "before_r" else "unknown"), result)
                    self.assertEqual(self.writes(statements), [])
                    self.refused(lambda: self.release(plan), "release_not_allowed")
                blocks, records = self.recovery_rows()
                self.assertEqual((blocks[0]["status"], records[0]["state"]), ("active", "verified"))

    def test_restart_rollback_record_of_the_target_is_checked(self):
        """The same field the other way: a TARGET apply snapshot naming another account's
        snapshot fails A (I5a). A target snapshot naming its own rollback record of the same
        card, or the empty value 0, passes; another account's own self reference is no inflow."""
        from _e5b_fixture import card
        from app.repositories import deck_repository as decks, user_repository as users
        from app.schemas import DeckCreate

        self.world(n=1)
        self.O = users.create_user("rec-o@e5b.example.test", "rec-o", "synthetic")["id"]

        self.o_card = card(self.O, decks.create_deck(self.O, DeckCreate(name="o-deck"))[0]["id"], "rec-o-word")
        o_snap = self.convert_other()
        self.rollback("rec-run-1", "rec-rb-1")
        self.convert(self.cards, "rec-run-2")
        self.prepare()
        self.recover()
        apply_snap = sql("SELECT s.id FROM srs_migration_snapshots s JOIN srs_migration_runs r ON r.id = s.run_id "
                         "WHERE r.run_key = 'rec-run-2'")[0]["id"]
        own_rollback = sql("SELECT s.id FROM srs_migration_snapshots s JOIN srs_migration_runs r ON r.id = s.run_id "
                           "WHERE r.run_key = 'rec-rb-1'")[0]["id"]
        for value, expected in ((own_rollback, "verified"), (0, "verified"), (o_snap, "not_verified"),
                                (apply_snap, "not_verified")):
            with self.subTest(value=value):
                self.set_restart(apply_snap, value)
                result = self.verify()
                self.assertEqual(result["status"], expected, result)
                self.assertEqual(result["checks"]["I5a"], "pass" if expected == "verified" else "fail", result)
                self.assertEqual(result["checks"]["N"], "pass", result)
        self.set_restart(apply_snap, own_rollback)
        self.set_restart(o_snap, o_snap)                                       # O's own (odd) self reference
        self.assertEqual(self.verify()["checks"]["N"], "pass")

    # ---- Gate E closing review: restart.rollback_record_id in FORMAT-3 (pruned) apply records ------
    def planb_chain(self, user_id, tag):
        """One account's card through the real U8 plan-B paths, ending with THREE apply runs:
        a legacy card with past study and no log (the U5 "no state" conversion) -> apply 1 ->
        FSRS review (evidence boundary) -> rollback 1 -> legacy review -> apply 2 (plan B:
        restart -> rollback 1) -> rollback 2 (before its first review) -> apply 3. Apply 2 is
        then no longer the card's latest apply record, so the U10-e tool may prune it."""
        from datetime import timedelta
        from _e5b_fixture import card, set_mode
        from app.database import now_utc
        from app.repositories import deck_repository as decks, vocab_repository as vocab
        from app.schemas import DeckCreate
        from app.srs import migration
        from app.srs.engine import CardKey

        set_mode(user_id, "legacy")
        ref = card(user_id, decks.create_deck(user_id, DeckCreate(name=f"{tag}-deck"))[0]["id"], f"{tag}-word")
        now = now_utc()
        sql("UPDATE vocab_items SET last_reviewed_at = ?, correct_count = 2, next_review_at = ? WHERE id = ?",
            ((now - timedelta(days=9)).isoformat(), (now - timedelta(hours=1)).isoformat(), ref))
        set_mode(user_id, "fsrs")
        keys = [CardKey("personal", user_id, ref)]
        migration.apply_plan(migration.dry_run(keys), f"{tag}-1", approved=True)
        version = sql("SELECT srs_card_version AS v FROM vocab_items WHERE id = ?", (ref,))[0]["v"]
        vocab.record_review(user_id, ref, "good", request_id=f"{tag}-req-1", expected_card_version=version,
                            session_id="rec")
        migration.rollback_plan(f"{tag}-1", f"{tag}-rb-1", user_id=user_id, approved=True)
        set_mode(user_id, "legacy")
        vocab.record_review(user_id, ref, "good")
        set_mode(user_id, "fsrs")
        result = migration.apply_plan(migration.dry_run(keys), f"{tag}-2", approved=True)
        self.assertEqual(result[0]["reconversion"], "state_none_restart", result)
        migration.rollback_plan(f"{tag}-2", f"{tag}-rb-2", user_id=user_id, approved=True)
        migration.apply_plan(migration.dry_run(keys), f"{tag}-3", approved=True)
        return ref

    def prune_runs(self, user_id, run_keys):
        """The real U10-e prune tool (migration.prune_expired_runs, account lock, --apply path);
        only the 30-day window judgement is replaced: `run_keys` expired, every other run open."""
        from app.database import get_connection
        from app.srs import migration
        from app.srs.storage import begin_card_write

        expired = {r["started_at"] for r in sql(
            f"SELECT started_at FROM srs_migration_runs WHERE run_key IN ({', '.join('?' for _ in run_keys)})",
            tuple(run_keys))}
        real = migration.rollback_window
        with mock.patch.object(migration, "rollback_window",
                               lambda started, now: "expired" if started in expired else real(started, now)), \
                get_connection() as c:
            report = migration.prune_expired_runs(c, user_id, apply=True, lock=begin_card_write)
        return report

    def format3_snapshot(self, run_key):
        """The one apply record of `run_key`, which must now be an exact format-3 record WITH restart."""
        from app.database import get_connection
        from app.srs import migration

        row = sql("SELECT s.id, s.card_kind, s.card_ref, s.legacy_json FROM srs_migration_snapshots s "
                  "JOIN srs_migration_runs r ON r.id = s.run_id WHERE r.run_key = ?", (run_key,))
        self.assertEqual(len(row), 1, row)
        body = json.loads(row[0]["legacy_json"])
        self.assertEqual((body.get("format"), sorted(body)), (migration.PRUNED_FORMAT,
                                                              ["card", "format", "last_log_id", "restart"]), body)
        with get_connection() as c:
            shape = migration._record_shape("apply", row[0]["card_kind"], int(row[0]["card_ref"]), body,
                                            migration._card_columns(c, row[0]["card_kind"]))
        self.assertEqual(shape, body)                                          # the shared judgement accepts it
        return row[0]["id"], body

    def set_rollback_record(self, snapshot_id, value):
        """Change ONLY restart.rollback_record_id; every other byte of the record's meaning stays."""
        body = json.loads(sql("SELECT legacy_json FROM srs_migration_snapshots WHERE id = ?", (snapshot_id,))[0]
                          ["legacy_json"])
        body["restart"]["rollback_record_id"] = value
        sql("UPDATE srs_migration_snapshots SET legacy_json = ? WHERE id = ?", (json.dumps(body), snapshot_id))

    def snapshot_of(self, run_key):
        return sql("SELECT s.id FROM srs_migration_snapshots s JOIN srs_migration_runs r ON r.id = s.run_id "
                   "WHERE r.run_key = ?", (run_key,))[0]["id"]

    def format3_target_world(self):
        """U: the plan-B chain (runs rec-u-1..3), the prune tool turns runs 1, 2 into format 3,
        run 3 (inside its window) is the recovery target -> A -> B. O: its own apply record."""
        from _e5b_fixture import card
        from app.repositories import deck_repository as decks, user_repository as users
        from app.schemas import DeckCreate

        self.U = users.create_user("rec-f3@e5b.example.test", "rec", "synthetic")["id"]
        self.cards = [self.planb_chain(self.U, "rec-u")]
        from _e5b_fixture import set_mode
        from app.repositories import vocab_repository as vocab
        from app.srs import migration
        from app.srs.engine import CardKey
        set_mode(self.U, "legacy")                       # a second card of U, converted and rolled back
        side = card(self.U, decks.create_deck(self.U, DeckCreate(name="u-side"))[0]["id"], "rec-u-side")
        vocab.record_review(self.U, side, "good")
        set_mode(self.U, "fsrs")
        migration.apply_plan(migration.dry_run([CardKey("personal", self.U, side)]), "rec-u-side", approved=True)
        migration.rollback_plan("rec-u-side", "rec-u-side-rb", user_id=self.U, approved=True)
        self.O = users.create_user("rec-o@e5b.example.test", "rec-o", "synthetic")["id"]
        self.o_card = card(self.O, decks.create_deck(self.O, DeckCreate(name="o-deck"))[0]["id"], "rec-o-word")
        o_snap = self.convert_other()
        from app.srs import migration
        migration.rollback_plan("rec-run-o", "rec-rb-o", user_id=self.O, approved=True)   # another card's rollback
        report = self.prune_runs(self.U, ["rec-u-1", "rec-u-2"])
        self.assertEqual(len(report["snapshots"]["pruned"]), 2, report)
        self.assertEqual((report["snapshots"]["unsupported"], report["snapshots"]["conflicts"]), ([], []), report)
        snap, body = self.format3_snapshot("rec-u-2")
        own_rollback = self.snapshot_of("rec-u-rb-1")
        self.assertEqual(body["restart"]["rollback_record_id"], own_rollback)     # the tool kept it as written
        preview = self.preview()
        self.assertEqual(preview["status"], "ready", preview)
        self.prepare()
        self.recover()
        return snap, own_rollback, o_snap

    def test_format3_restart_rollback_record_of_the_target_is_checked(self):
        """A (I5a) on a real format-3 target record: its own rollback record of the same card and
        the empty value 0 pass; another account's snapshot or an apply record fails; a non-integer
        is not a readable record (unknown -> not verified). Refusals write nothing, block stays."""
        snap, own_rollback, o_snap = self.format3_target_world()
        self.assertEqual(self.verify()["status"], "verified")
        apply_3 = self.snapshot_of("rec-u-3")
        for value, expected in ((own_rollback, "pass"), (0, "pass"), (o_snap, "fail"), (apply_3, "fail"),
                                (self.snapshot_of("rec-rb-o"), "fail"), (999999, "fail"),
                                (self.snapshot_of("rec-u-side-rb"), "fail"),   # U's rollback, another card
                                (self.snapshot_of("rec-u-rb-2"), "pass")):
            with self.subTest(value=value):
                self.set_rollback_record(snap, value)
                stored = self.recovery_rows()
                with self.sql_trace() as statements:
                    result = self.verify()
                self.assertEqual(result["checks"]["I5a"], expected, result)
                self.assertEqual(result["checks"]["N"], "pass", result)
                if expected == "fail":
                    self.assertEqual(result["status"], "not_verified", result)
                    self.assertEqual(self.writes(statements), [])
                    self.assertEqual(self.recovery_rows(), stored)
                    self.refused(lambda: self.release(), "release_not_allowed")
        self.set_rollback_record(snap, "x")          # not an id: the record is unreadable, never a pass
        result = self.verify()
        self.assertEqual((result["status"], result["checks"]["I5a"]), ("not_verified", "unknown"), result)
        self.set_rollback_record(snap, own_rollback)
        self.assertEqual(self.verify()["status"], "verified")
        result = self.release()
        self.assertEqual((result["released"], result["reason"]), (True, "completed"))

    def format3_other_world(self):
        """mixed_world, and O (the other account) runs its own plan-B chain; the prune tool turns
        O's runs 1, 2 into format 3. Returns O's format-3 record WITH restart."""
        self.mixed_world()
        self.planb_chain(self.O, "rec-o")
        report = self.prune_runs(self.O, ["rec-o-1", "rec-o-2"])
        self.assertEqual(len(report["snapshots"]["pruned"]), 2, report)
        snap, body = self.format3_snapshot("rec-o-2")
        self.assertEqual(body["restart"]["rollback_record_id"], self.snapshot_of("rec-o-rb-1"))
        return snap

    def test_format3_restart_rollback_record_inflow_is_refused(self):
        """N on a real format-3 record of ANOTHER account: its own rollback record is no inflow;
        naming a target snapshot is a violation (before R, and under the lock after R); a
        non-integer is unknown. Refusals write nothing; the block and the proof stay."""
        from app import account_blocks

        for name in ("own", "before_r", "after_r", "unreadable"):
            with self.subTest(name):
                self.reset_world()
                o_snap = self.format3_other_world()
                plan = self.verified_world_from_here()
                target = self.u_snapshot()
                if name == "own":
                    self.assertEqual(self.verify()["checks"]["N"], "pass")
                    result = self.release(plan)
                    self.assertEqual((result["released"], result["reason"]), (True, "completed"))
                    continue
                if name == "after_r":
                    with self.sql_trace() as statements, mock.patch.object(
                            account_blocks, "_between_proof_and_lock",
                            lambda: self.set_rollback_record(o_snap, target)):
                        self.refused(lambda: self.release(plan), "release_not_allowed")
                    self.assertEqual([q for q in self.writes(statements) if "account_" in q], [])
                else:
                    self.set_rollback_record(o_snap, target if name == "before_r" else "x")
                    with self.sql_trace() as statements:
                        result = self.verify()
                    self.assertEqual((result["status"], result["checks"]["N"]),
                                     ("not_verified", "fail" if name == "before_r" else "unknown"), result)
                    self.assertEqual(self.writes(statements), [])
                    self.refused(lambda: self.release(plan), "release_not_allowed")
                blocks, records = self.recovery_rows()
                self.assertEqual((blocks[0]["status"], records[0]["state"]), ("active", "verified"))


    # ---- Gate E F-1: gate preconditions judged before any recovery write --------------------------
    def orphan_log(self, user_id, ref):
        """An orphan personal log: the card row goes WITHOUT the app's delete (no ledger row) and its
        log stays. The current schema has no card FK on review_logs on either database (E-D1 A on
        PostgreSQL), so no FK is disabled. (How old installations got there differs: SQLite without
        the FK pragma; old PostgreSQL's CASCADE FK removed the log with the card.)"""
        sql("DELETE FROM vocab_items WHERE id = ? AND user_id = ?", (ref, user_id))
        self.assertTrue(sql("SELECT 1 AS x FROM review_logs WHERE vocab_item_id = ?", (ref,)), "log must stay")
        self.assertFalse(sql("SELECT 1 AS x FROM srs_card_deletions WHERE card_kind = 'personal' AND card_ref = ?",
                             (ref,)))

    def legacy_reviewed_card(self, user_id, name):
        from _e5b_fixture import card, set_mode
        from app.repositories import deck_repository as decks, vocab_repository as vocab
        from app.schemas import DeckCreate

        mode = sql("SELECT srs_mode FROM srs_user_settings WHERE user_id = ?", (user_id,))
        set_mode(user_id, "legacy")
        ref = card(user_id, decks.create_deck(user_id, DeckCreate(name=f"{name}-deck"))[0]["id"], name)
        vocab.record_review(user_id, ref, "good")                 # a legacy-engine review (card stays legacy)
        if mode:
            set_mode(user_id, mode[0]["srs_mode"])
        return ref

    def committed(self):
        """Everything a refusal must leave as it was: data, blocks and records."""
        return self.data_hash(), self.recovery_rows()

    def test_f1_orphan_log_from_the_start_blocks_preview_and_step_a(self):
        """An orphan log of the target before anything: preview blocked with the fixed reason, A
        refused; the block A inserts is rolled back with it (a write statement runs, nothing is
        committed) -- no new block, no record."""
        self.world()
        self.orphan_log(self.U, self.legacy_reviewed_card(self.U, "rec-orphan"))
        report = self.preview()
        self.assertEqual((report["status"], report["reasons"]), ("blocked", ["gate_precondition_I1a"]))
        before = self.committed()
        with self.sql_trace() as statements:
            self.refused(lambda: self.prepare(report["plan"]), "recovery_blocked", ["gate_precondition_I1a"])
        self.assertTrue(any("account_write_blocks" in q for q in self.writes(statements)))   # executed ...
        self.assertEqual(self.committed(), before)                                            # ... not committed
        self.assertEqual(self.recovery_rows(), ([], []))

    def test_f1_orphan_after_preview_before_a_is_refused_under_the_lock(self):
        """preview ready; the orphan appears before A: A re-judges under the account lock and
        refuses. A block that existed before A (same key and token) stays exactly as it was."""
        from app import account_blocks

        for existing in (False, True):
            with self.subTest(existing_block=existing):
                self.reset_world()
                self.world()
                extra = self.legacy_reviewed_card(self.U, "rec-orphan")
                plan = self.preview()["plan"]
                if existing:
                    account_blocks.set_block(self.U, KEY, TOKEN)
                self.orphan_log(self.U, extra)
                before = self.committed()
                self.refused(lambda: self.prepare(plan), "recovery_blocked", ["gate_precondition_I1a"])
                self.assertEqual(self.committed(), before)
                blocks, records = self.recovery_rows()
                self.assertEqual(records, [])
                self.assertEqual([b["status"] for b in blocks], ["active"] if existing else [])

    def test_f1_orphan_after_a_before_b_refuses_b_and_the_unchanged_release_stays(self):
        """A done; the orphan appears before B: B refuses under the lock before its progress mark
        and any recovery write (no write statement at all); `prepared` and the block stay; the
        existing unchanged release (`precheck_unrecoverable`) still applies."""
        from app import account_blocks

        self.world()
        extra = self.legacy_reviewed_card(self.U, "rec-orphan")   # an ordinary card, before the block
        plan = self.preview()["plan"]
        self.prepare(plan)
        self.orphan_log(self.U, extra)
        before = self.committed()
        with self.sql_trace() as statements:
            self.refused(lambda: self.recover(plan), "recovery_blocked", ["gate_precondition_I1a"])
        self.assertEqual(self.writes(statements), [])
        self.assertEqual(self.committed(), before)
        blocks, records = self.recovery_rows()
        self.assertEqual((blocks[0]["status"], blocks[0]["changes_started"], records[0]["state"]),
                         ("active", 0, "prepared"))
        self.assertEqual(sql("SELECT count(*) AS n FROM srs_migration_runs WHERE mode = 'rollback'")[0]["n"], 0)
        result = account_blocks.release_block(self.U, KEY, TOKEN, "precheck_unrecoverable")
        self.assertEqual((result["released"], result["reason"]), (True, "precheck_unrecoverable"))

    def test_f1_missing_progress_before_a_blocks(self):
        """I2a as a precondition: a subscribed log of the target without its progress row."""
        self.mixed_world()
        lexeme = self.legacy_subscription()
        self.assertEqual(self.preview()["status"], "ready")
        self.drop_progress(lexeme)
        report = self.preview()
        self.assertEqual((report["status"], report["reasons"]), ("blocked", ["gate_precondition_I2a"]))
        self.refused(lambda: self.prepare(report["plan"]), "recovery_blocked", ["gate_precondition_I2a"])
        self.assertEqual(self.recovery_rows(), ([], []))

    def test_f1_ledger_proven_deletion_and_another_accounts_orphan_do_not_block(self):
        """A normal (ledger-proven) deletion of the target and an orphan log of ANOTHER account
        (diagnostic G only) leave the recovery as it was: ready -> A -> B -> verify -> release."""
        from app.repositories import vocab_repository as vocab

        self.mixed_world()
        gone = self.legacy_reviewed_card(self.U, "rec-deleted")
        vocab.delete_vocab_item(self.U, gone)                       # the app's delete: ledger row, log kept
        self.orphan_log(self.O, self.legacy_reviewed_card(self.O, "rec-o-orphan"))
        self.assertEqual(self.preview()["status"], "ready")
        plan = self.verified_world_from_here()
        result = self.verify()
        self.assertEqual((result["status"], result["diagnostics"]["I1"]), ("verified", "fail"), result)
        released = self.release(plan)
        self.assertEqual((released["released"], released["reason"]), (True, "completed"))

    def test_f1_preconditions_are_the_gate_checks(self):
        """One rule: the precondition statuses are exactly the gate's A / N results."""
        from app import recovery
        from app.database import get_connection
        from app.srs import recovery_scope

        self.world()
        self.orphan_log(self.U, self.legacy_reviewed_card(self.U, "rec-orphan"))
        with get_connection() as c:
            pre = recovery.gate_preconditions(c, self.U)
            a, n = recovery_scope.account(c, self.U), recovery_scope.inflow(c, self.U)
            seq = recovery_scope.sequence(c)
        self.assertEqual(set(pre), set(recovery.PRECONDITION_CHECKS))
        self.assertEqual(set(pre), set(recovery.A_CHECKS[:4]) | {"N", "S"})   # every gate check B never repairs
        self.assertEqual({k: v for k, v in pre.items() if k not in ("N", "S")},
                         {k: a[k] for k in pre if k not in ("N", "S")})
        self.assertEqual((pre["N"], pre["S"]), (n, seq))
        self.assertEqual(pre["I1a"]["status"], "fail")


    # ---- Gate E F-1 follow-up: I5a and S judged before any recovery write too ----------------------
    def damage_receipt(self):
        """The target receipt's review_log_id names ANOTHER card's log of the same account."""
        rid = sql("SELECT id FROM srs_review_receipts WHERE user_id = ? AND card_kind = 'personal' AND card_ref = ?",
                  (self.U, self.cards[0]))[0]["id"]
        other = sql("SELECT id FROM review_logs WHERE vocab_item_id = ? ORDER BY id", (self.cards[1],))[0]["id"]
        sql("UPDATE srs_review_receipts SET review_log_id = ? WHERE id = ?", (other, rid))
        return "srs_review_receipts", rid, "review_log_id", other

    def damage_evidence(self):
        """The target card's evidence_from_log_id names ANOTHER card's log of the same account."""
        other = sql("SELECT id FROM review_logs WHERE vocab_item_id = ? ORDER BY id", (self.cards[1],))[0]["id"]
        sql("UPDATE vocab_items SET evidence_from_log_id = ? WHERE id = ?", (other, self.cards[0]))
        return "vocab_items", self.cards[0], "evidence_from_log_id", other

    def personal_sequence(self, value=None):
        """Read (or, on the harness-owned synthetic table only, set) the personal card id sequence.
        PostgreSQL setval is not transactional; the world is reset (identity restarted) per case."""
        if self.db_kind == "postgresql":
            name = "pg_get_serial_sequence('vocab_items', 'id')"
            if value is not None:
                sql(f"SELECT setval({name}, ?, true)", (value,))
            return sql(f"SELECT last_value AS v FROM {sql('SELECT ' + name + ' AS n')[0]['n']}")[0]["v"]
        if value is not None:
            sql("UPDATE sqlite_sequence SET seq = ? WHERE name = 'vocab_items'", (value,))
        return sql("SELECT seq AS v FROM sqlite_sequence WHERE name = 'vocab_items'")[0]["v"]

    def damage_sequence(self):
        """The id sequence below the largest preserved personal reference (a card of the target)."""
        top = sql("SELECT max(id) AS m FROM vocab_items")[0]["m"]
        self.personal_sequence(top - 1)
        return "sequence", None, "vocab_items.id", top - 1

    def stored(self, damage):
        table, ref, column, _ = damage
        if table == "sequence":
            return self.personal_sequence()
        return sql(f"SELECT {column} AS v FROM {table} WHERE id = ?", (ref,))[0]["v"]

    def damaged_world(self):
        self.world(n=2)
        self.fsrs_review(self.cards[0])                          # a receipt and a later FSRS log of card 0

    F1B_CASES = (("receipt", "damage_receipt", "gate_precondition_I5a"),
                 ("evidence", "damage_evidence", "gate_precondition_I5a"),
                 ("sequence", "damage_sequence", "gate_precondition_S"))

    def test_f1b_damage_from_the_start_blocks_preview_and_step_a(self):
        for name, damage, reason in self.F1B_CASES:
            with self.subTest(name):
                self.reset_world()
                self.damaged_world()
                done = getattr(self, damage)()
                report = self.preview()
                self.assertEqual(report["status"], "blocked", report)
                self.assertIn(reason, report["reasons"])
                before = self.committed()
                self.refused(lambda: self.prepare(report["plan"]), "recovery_blocked")
                self.assertEqual(self.committed(), before)                  # nothing committed
                self.assertEqual(self.recovery_rows(), ([], []))
                self.assertEqual(self.stored(done), done[3])               # the damage is left as it is

    def test_f1b_damage_after_preview_before_a_is_refused_under_the_lock(self):
        from app import account_blocks

        for name, damage, reason in self.F1B_CASES:
            for existing in (False, True):
                with self.subTest(name, existing_block=existing):
                    self.reset_world()
                    self.damaged_world()
                    plan = self.preview()["plan"]
                    if existing:
                        account_blocks.set_block(self.U, KEY, TOKEN)
                    done = getattr(self, damage)()
                    before = self.committed()
                    error = self.refused(lambda: self.prepare(plan), "recovery_blocked")
                    self.assertIn(reason, error.reasons)
                    self.assertEqual(self.committed(), before)
                    blocks, records = self.recovery_rows()
                    self.assertEqual((records, [b["status"] for b in blocks]), ([], ["active"] if existing else []))
                    self.assertEqual(self.stored(done), done[3])

    def test_f1b_damage_after_a_before_b_refuses_b_and_the_unchanged_release_stays(self):
        from app import account_blocks

        for name, damage, reason in self.F1B_CASES:
            with self.subTest(name):
                self.reset_world()
                self.damaged_world()
                plan = self.preview()["plan"]
                self.prepare(plan)
                done = getattr(self, damage)()
                before = self.committed()
                with self.sql_trace() as statements:
                    error = self.refused(lambda: self.recover(plan), "recovery_blocked")
                self.assertIn(reason, error.reasons)
                self.assertEqual(self.writes(statements), [])
                self.assertEqual(self.committed(), before)
                blocks, records = self.recovery_rows()
                self.assertEqual((blocks[0]["status"], blocks[0]["changes_started"], records[0]["state"]),
                                 ("active", 0, "prepared"))
                self.assertEqual(self.stored(done), done[3])
                result = account_blocks.release_block(self.U, KEY, TOKEN, "precheck_unrecoverable")
                self.assertEqual((result["released"], result["reason"]), (True, "precheck_unrecoverable"))

    def test_f1b_normal_references_and_the_sequence_boundary_pass(self):
        """Still recoverable: normal references (receipt, evidence), the sequence exactly AT the
        largest preserved reference, a ledger-proven deletion -> ready -> A -> B -> verify -> release."""
        from app.repositories import vocab_repository as vocab

        self.damaged_world()
        gone = self.legacy_reviewed_card(self.U, "rec-deleted")
        vocab.delete_vocab_item(self.U, gone)                       # ledger row, log kept
        top = max(sql("SELECT max(id) AS m FROM vocab_items")[0]["m"], gone)
        self.personal_sequence(top)                                 # the boundary: equal is enough
        self.assertEqual(self.preview()["status"], "ready")
        plan = self.verified_world_from_here()
        checks = self.verify()["checks"]
        self.assertEqual((checks["I5a"], checks["S"]), ("pass", "pass"), checks)
        self.assertEqual(self.release(plan)["reason"], "completed")


class Case(RecoveryChecks, unittest.TestCase):
    def setUp(self):
        from app.database import init_db

        directory = tempfile.TemporaryDirectory(prefix="jp_vocab_prb_", dir=BACKEND)
        self.addCleanup(directory.cleanup)
        self._directory = directory
        path = Path(directory.name) / "synthetic.db"
        env = mock.patch.dict(os.environ, {"APP_ENV": "test", "DATABASE_URL": f"sqlite:///{path.as_posix()}",
                                           "JWT_SECRET_KEY": s.SECRET})
        env.start()
        self.addCleanup(env.stop)
        init_db()


if __name__ == "__main__":
    unittest.main()

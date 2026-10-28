"""Gate B-2: actual SQLite transactions, threaded overlap and HTTP routes.

Never connects to an existing database. PostgreSQL is not simulated as SQLite.
"""

from __future__ import annotations

import os
import json
import subprocess
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["APP_ENV"] = "test"

from fastapi.testclient import TestClient
from app import main
from app.auth import create_access_token
from app.database import compute_review_schedule, get_connection, init_db
from app.repositories.deck_repository import create_deck
from app.repositories.lexeme_repository import (
    add_word_to_shared_deck, get_or_create_progress, get_or_create_subscription,
    record_lexeme_review, upsert_lexeme,
)
from app.repositories.user_repository import create_user
from app.repositories.vocab_repository import create_or_update_vocab_item, record_review, update_vocab_item
from app.schemas import DeckCreate, VocabItemCreate, VocabItemUpdate
from app.srs import migration, reviews, storage
from app.srs.engine import CardKey
from app.srs.storage import SrsWriteError, load_card, load_logs


class SrsSqliteCase(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="jp_vocab_b2_", dir=Path(__file__).resolve().parents[1])
        self.addCleanup(self.directory.cleanup)
        self.db_path = Path(self.directory.name) / "qa_srs_b2_synthetic.db"
        env = mock.patch.dict(os.environ, {"DATABASE_URL": f"sqlite:///{self.db_path.as_posix()}",
                                           "APP_ENV": "test", "JWT_SECRET_KEY": "synthetic-test-signing-key-not-for-production"})
        env.start()
        self.addCleanup(env.stop)
        init_db()
        self.user = create_user(email="srs-b2@example.test", display_name="synthetic", password_hash="not-a-login-hash")["id"]
        self.other = create_user(email="srs-b2-other@example.test", display_name="other", password_hash="not-a-login-hash")["id"]
        deck = create_deck(self.user, DeckCreate(name="synthetic personal"))[0]["id"]
        self.item = create_or_update_vocab_item(self.user, VocabItemCreate(
            surface="srs-b2", base_form="srs-b2", reading="srs-b2", meaning_ko="synthetic", deck_id=deck,
        ))[0]["id"]
        self.personal = CardKey("personal", self.user, self.item)
        self.lexeme = upsert_lexeme("srs-lx", "srs-lx")
        at = datetime.now(timezone.utc).isoformat()
        with get_connection() as connection:
            self.shared = connection.execute(
                "INSERT INTO shared_decks (owner_user_id, title, description, created_at, updated_at) "
                "VALUES (?, 'synthetic shared', '', ?, ?) RETURNING id", (self.other, at, at),
            ).fetchone()["id"]
        add_word_to_shared_deck(self.shared, self.lexeme, 0)
        get_or_create_subscription(self.user, self.shared)
        with get_connection() as connection:
            get_or_create_progress(connection, self.user, self.lexeme)
        self.subscribed = CardKey("lexeme", self.user, self.lexeme)

    def card(self, key):
        with get_connection() as connection:
            return load_card(connection, key)

    def counts(self, key):
        with get_connection() as connection:
            return (len(load_logs(connection, key)), connection.execute(
                "SELECT COUNT(*) FROM srs_review_receipts WHERE user_id = ? AND card_kind = ? AND card_ref = ?",
                (key.user_id, key.kind, key.ref_id),
            ).fetchone()[0])

    def enable(self, key, name="enable"):
        result = migration.apply_plan(migration.dry_run([key]), name, approved=True)
        self.assertEqual(result[0]["result"], "applied")
        return self.card(key)["srs_card_version"]

    def rate(self, key, request="request-1", version=None, grade="again", session="session-1"):
        if version is None:
            version = self.card(key)["srs_card_version"]
        kwargs = dict(request_id=request, expected_card_version=version, session_id=session)
        if key.kind == "personal":
            return record_review(key.user_id, key.ref_id, grade, **kwargs)
        return record_lexeme_review(key.user_id, key.ref_id, grade, self.shared, **kwargs)


class AtomicReviewTests(SrsSqliteCase):
    def test_request_ids_and_first_introduction_are_account_scoped(self):
        self.enable(self.personal)
        self.rate(self.personal, request="same-id")
        deck = create_deck(self.other, DeckCreate(name="other account"))[0]["id"]
        item = create_or_update_vocab_item(self.other, VocabItemCreate(surface="other", base_form="other", deck_id=deck))[0]["id"]
        other_key = CardKey("personal", self.other, item)
        self.enable(other_key, "enable-other-account")
        result = self.rate(other_key, request="same-id")
        self.assertEqual(result["srs"]["introduced_today"], 1)
        self.assertEqual(self.counts(self.personal), (1, 1))
        self.assertEqual(self.counts(other_key), (1, 1))

    def test_completion_and_first_completion_are_retained_through_failure_and_rollback(self):
        self.enable(self.personal)
        t0 = datetime(2026, 8, 1, 1, tzinfo=timezone.utc)
        with mock.patch.object(reviews, "now_utc", return_value=t0):
            first = self.rate(self.personal, grade="easy")
        self.assertFalse(first["completed"])
        # Gate D-2 U11: V3 needs three success dates and two spaced successes.
        with mock.patch.object(reviews, "now_utc", return_value=t0 + timedelta(days=8)):
            middle = self.rate(self.personal, request="middle", grade="easy")
        self.assertFalse(middle["completed"])
        with mock.patch.object(reviews, "now_utc", return_value=t0 + timedelta(days=74)):
            completed = self.rate(self.personal, request="complete", grade="easy")
        self.assertTrue(completed["completed"])
        first_completed_at = completed["srs"]["first_completed_at"]
        with mock.patch.object(reviews, "now_utc", return_value=t0 + timedelta(days=300)):
            failed = self.rate(self.personal, request="failure", grade="again")
        self.assertFalse(failed["completed"])
        self.assertTrue(failed["srs"]["needs_relearning"])
        self.assertEqual(failed["srs"]["first_completed_at"], first_completed_at)
        migration.rollback_plan("enable", "keep-first", user_id=self.user, approved=True)
        after = self.card(self.personal)
        self.assertEqual(after["first_completed_at"], first_completed_at)
        self.assertEqual(after["completion_metric_version"], completed["completion_metric_version"])

    def test_retry_returns_exact_receipt_and_first_again_counts_once(self):
        for key in (self.personal, self.subscribed):
            with self.subTest(kind=key.kind):
                version = self.enable(key, "enable-" + key.kind)
                first = self.rate(key, request=key.kind, version=version)
                retry = self.rate(key, request=key.kind, version=version)
                self.assertEqual(first, retry)
                self.assertEqual(self.counts(key), (1, 1))
                self.assertEqual(self.card(key)["srs_card_version"], version + 1)
                self.assertEqual(self.card(key)["wrong_count"], 1)
                second = self.rate(key, request=key.kind + "-second", version=version + 1, grade="good")
                self.assertEqual(first["srs"]["introduced_today"], second["srs"]["introduced_today"])
                self.assertEqual(second["srs"]["completion_status"], "not_completed")

    def test_changed_payload_rejected_without_writing(self):
        version = self.enable(self.personal)
        self.rate(self.personal, version=version)
        for changes in (dict(grade="easy"), dict(session="another"), dict(version=version + 1)):
            with self.subTest(changes=changes), self.assertRaisesRegex(SrsWriteError, "request_id_conflict"):
                self.rate(self.personal, **(dict(version=version) | changes))
        self.assertEqual(self.counts(self.personal), (1, 1))

    def test_same_request_id_on_another_card_or_kind_conflicts(self):
        version = self.enable(self.personal)
        other_version = self.enable(self.subscribed, "enable-lexeme")
        self.rate(self.personal, version=version)
        with self.assertRaisesRegex(SrsWriteError, "request_id_conflict"):
            self.rate(self.subscribed, version=other_version)
        self.assertEqual(self.counts(self.subscribed), (0, 0))

    def test_stale_version_and_missing_fields_are_rejected(self):
        for key in (self.personal, self.subscribed):
            version = self.enable(key, "enable-" + key.kind)
            with self.assertRaisesRegex(SrsWriteError, "review_upgrade_required"):
                if key.kind == "personal":
                    record_review(key.user_id, key.ref_id, "good")
                else:
                    record_lexeme_review(key.user_id, key.ref_id, "good", self.shared)
            self.rate(key, request=key.kind, version=version)
            with self.assertRaisesRegex(SrsWriteError, "card_version_conflict"):
                self.rate(key, request=key.kind + "-stale", version=version)
            self.assertEqual(self.counts(key), (1, 1))

    def test_account_and_subscription_permissions_are_rechecked_before_retry(self):
        self.enable(self.personal)
        self.assertIsNone(record_review(self.other, self.item, "good", request_id="no-access", expected_card_version=1, session_id="s"))
        version = self.enable(self.subscribed, "enable-lexeme")
        self.rate(self.subscribed, version=version)
        with get_connection() as connection:
            connection.execute("UPDATE user_deck_subscriptions SET is_active = FALSE WHERE user_id = ?", (self.user,))
        with self.assertRaisesRegex(SrsWriteError, "subscription_required"):
            self.rate(self.subscribed, version=version)
        self.assertEqual(self.counts(self.subscribed), (1, 1))

    def test_post_card_and_log_failure_rolls_back_everything(self):
        for key in (self.personal, self.subscribed):
            self.enable(key, "enable-" + key.kind)
            before = self.card(key)
            with mock.patch.object(reviews, "introduced_on", side_effect=RuntimeError("injected late failure")):
                with self.assertRaises(RuntimeError):
                    self.rate(key, request=key.kind)
            self.assertEqual(self.card(key), before)
            self.assertEqual(self.counts(key), (0, 0))

    def test_receipt_insert_failure_rolls_back_card_and_log(self):
        self.enable(self.personal)
        before = self.card(self.personal)
        with get_connection() as connection:
            connection.execute("CREATE TRIGGER fail_receipt BEFORE INSERT ON srs_review_receipts BEGIN SELECT RAISE(ABORT, 'injected'); END")
        with self.assertRaises(Exception):
            self.rate(self.personal)
        self.assertEqual(self.card(self.personal), before)
        self.assertEqual(self.counts(self.personal), (0, 0))

    def _overlap(self, key, same_request):
        version = self.enable(key)
        first_inside = threading.Event()
        second_attempted = threading.Event()
        release = threading.Event()
        original_review, original_begin = reviews.review, storage.begin_card_write

        def delayed_review(*args, **kwargs):
            first_inside.set()
            if not release.wait(5):
                raise AssertionError("second writer never overlapped")
            return original_review(*args, **kwargs)

        def marked_begin(*args, **kwargs):
            if first_inside.is_set():
                second_attempted.set()
            return original_begin(*args, **kwargs)

        def submit(request):
            try:
                return self.rate(key, request=request, version=version)
            except SrsWriteError as error:
                return error.code

        with mock.patch.object(reviews, "review", side_effect=delayed_review), mock.patch.object(storage, "begin_card_write", side_effect=marked_begin):
            with ThreadPoolExecutor(max_workers=2) as pool:
                a = pool.submit(submit, "a")
                try:
                    self.assertTrue(first_inside.wait(5))
                    b = pool.submit(submit, "a" if same_request else "b")
                    self.assertTrue(second_attempted.wait(5))
                finally:
                    release.set()
                result_a, result_b = a.result(timeout=6), b.result(timeout=6)
        self.assertEqual(self.counts(key), (1, 1))
        self.assertEqual(self.card(key)["srs_card_version"], version + 1)
        if same_request:
            self.assertEqual(result_a, result_b)
        else:
            self.assertEqual(result_b, "card_version_conflict")

    def test_overlapping_personal_same_id(self):
        self._overlap(self.personal, True)

    def test_overlapping_personal_different_ids(self):
        self._overlap(self.personal, False)

    def test_overlapping_subscribed_same_id(self):
        self._overlap(self.subscribed, True)

    def test_overlapping_subscribed_different_ids(self):
        self._overlap(self.subscribed, False)

    def test_fsrs_does_not_change_classification_or_automatically_complete(self):
        self.enable(self.subscribed)
        before = self.card(self.subscribed)["status"]
        self.rate(self.subscribed, grade="easy")
        self.assertEqual(self.card(self.subscribed)["status"], before)
        self.assertIsNone(self.card(self.subscribed)["first_completed_at"])

    def test_invalid_clock_and_configuration_do_not_write(self):
        self.enable(self.personal)
        at = datetime(2026, 10, 12, 1, tzinfo=timezone.utc)
        with mock.patch.object(reviews, "now_utc", return_value=at):
            self.rate(self.personal)
        before = self.card(self.personal)
        with mock.patch.object(reviews, "now_utc", return_value=at - timedelta(seconds=1)):
            with self.assertRaisesRegex(SrsWriteError, "server_clock_before_last_review"):
                self.rate(self.personal, request="clock")
        self.assertEqual(self.card(self.personal), before)
        with get_connection() as connection:
            connection.execute("UPDATE vocab_items SET srs_config_version = 'unsupported' WHERE id = ?", (self.item,))
        with self.assertRaisesRegex(SrsWriteError, "unsupported_config_version"):
            self.rate(self.personal, request="config")
        self.assertEqual(self.counts(self.personal), (1, 1))


class MigrationTests(SrsSqliteCase):
    def test_preview_cli_is_read_only_and_refuses_missing_or_regular_db(self):
        script = Path(__file__).resolve().parents[1] / "scripts" / "inspect_srs_migration.py"
        args = [sys.executable, str(script), "--user-id", str(self.user), "--personal-id", str(self.item)]
        before = self.db_path.read_bytes()
        result = subprocess.run(args + ["--sqlite-test-db", str(self.db_path)], capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["mode"], "dry_run")
        self.assertEqual(self.db_path.read_bytes(), before)
        forbidden = Path(self.directory.name) / "ordinary.db"
        rejected = subprocess.run(args + ["--sqlite-test-db", str(forbidden)], capture_output=True, text=True, timeout=15)
        self.assertNotEqual(rejected.returncode, 0)
        self.assertFalse(forbidden.exists())

    def test_dry_run_cannot_create_missing_database_or_execute_writes(self):
        missing = Path(self.directory.name) / "missing.db"
        with mock.patch.dict(os.environ, {"DATABASE_URL": f"sqlite:///{missing.as_posix()}"}):
            with self.assertRaises(Exception):
                migration.dry_run([self.personal])
        self.assertFalse(missing.exists())

        def injected_write(connection, key, **kwargs):
            connection.execute("INSERT INTO srs_config_versions VALUES ('bad', 'bad', 'bad', 'bad', '{}', 'bad')")

        with mock.patch.object(migration, "inspect_card", side_effect=injected_write):
            with self.assertRaises(Exception):
                migration.dry_run([self.personal])
        with get_connection() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM srs_config_versions").fetchone()[0], 0)

    def test_batch_cursor_resumes_at_next_card(self):
        plan = migration.dry_run([self.personal, self.subscribed])
        first = migration.apply_plan(plan, "batched", approved=True, batch_size=1)
        self.assertEqual(len(first), 1)
        with get_connection() as connection:
            run = connection.execute("SELECT status, summary_json FROM srs_migration_runs WHERE run_key = 'batched'").fetchone()
            self.assertEqual(run["status"], "started")
        second = migration.apply_plan(plan, "batched", approved=True, batch_size=1)
        self.assertEqual(len(second), 2)
        self.assertEqual([result["result"] for result in second], ["already_applied", "applied"])
        self.assertEqual(self.card(self.personal)["srs_card_version"], 1)
        self.assertEqual(self.card(self.subscribed)["srs_card_version"], 1)

    def test_modified_plan_and_word_edit_cannot_be_applied(self):
        plan = migration.dry_run([self.personal])
        forged = replace(plan[0], values_json='{"srs_engine":"fsrs","status":"known"}')
        self.assertEqual(migration.apply_plan([forged], "forged", approved=True)[0]["result"], "conflict")
        update_vocab_item(self.user, self.item, VocabItemUpdate(status="known"))
        self.assertEqual(migration.apply_plan(plan, "edited", approved=True)[0]["result"], "conflict")
        self.assertEqual(self.card(self.personal)["srs_engine"], "legacy")

    def test_snapshot_failure_rolls_back_that_cards_update(self):
        plan = migration.dry_run([self.personal])
        before = self.card(self.personal)
        with get_connection() as connection:
            connection.execute("CREATE TRIGGER fail_snapshot BEFORE INSERT ON srs_migration_snapshots BEGIN SELECT RAISE(ABORT, 'injected'); END")
        with self.assertRaises(Exception):
            migration.apply_plan(plan, "snapshot-failure", approved=True)
        self.assertEqual(self.card(self.personal), before)
        with get_connection() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM srs_migration_snapshots").fetchone()[0], 0)
            self.assertEqual(connection.execute("SELECT status FROM srs_migration_runs WHERE run_key = 'snapshot-failure'").fetchone()[0], "failed")

    def test_legacy_evaluation_really_overlaps_migration(self):
        plan = migration.dry_run([self.personal])
        first_inside, second_attempted, release = threading.Event(), threading.Event(), threading.Event()
        original_begin = storage.begin_card_write

        def slow_legacy(*args, **kwargs):
            first_inside.set()
            if not release.wait(5):
                raise AssertionError("migration did not overlap")
            return compute_review_schedule(*args, **kwargs)

        def marked_begin(*args, **kwargs):
            second_attempted.set()
            return original_begin(*args, **kwargs)

        with mock.patch("app.repositories.vocab_repository.compute_review_schedule", side_effect=slow_legacy):
            with ThreadPoolExecutor(max_workers=2) as pool:
                evaluation = pool.submit(record_review, self.user, self.item, "good")
                try:
                    self.assertTrue(first_inside.wait(5))
                    with mock.patch.object(migration, "begin_card_write", side_effect=marked_begin):
                        applying = pool.submit(migration.apply_plan, plan, "overlap", approved=True)
                        self.assertTrue(second_attempted.wait(5))
                        release.set()
                        results = applying.result(timeout=6)
                finally:
                    release.set()
                self.assertIsNotNone(evaluation.result(timeout=6))
        self.assertEqual(results[0]["result"], "conflict")
        self.assertEqual(self.card(self.personal)["srs_engine"], "legacy")
        self.assertEqual(self.counts(self.personal), (1, 0))

    def test_rollback_blocks_resume_of_partially_applied_source(self):
        plan = migration.dry_run([self.personal, self.subscribed])
        migration.apply_plan(plan, "partial", approved=True, batch_size=1)
        migration.rollback_plan("partial", "partial-undo", user_id=self.user, approved=True)
        with self.assertRaisesRegex(SrsWriteError, "migration_run_closed"):
            migration.apply_plan(plan, "partial", approved=True)
        self.assertTrue(all(self.card(key)["srs_engine"] == "legacy" for key in (self.personal, self.subscribed)))

    def test_rollback_failure_does_not_partially_restore_cards(self):
        plan = migration.dry_run([self.personal, self.subscribed])
        migration.apply_plan(plan, "two", approved=True)
        before = [self.card(key) for key in (self.personal, self.subscribed)]
        original = migration.update_card
        calls = 0

        def fail_second(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("synthetic rollback failure")
            return original(*args, **kwargs)

        with mock.patch.object(migration, "update_card", side_effect=fail_second):
            with self.assertRaises(RuntimeError):
                migration.rollback_plan("two", "undo-two", user_id=self.user, approved=True)
        self.assertEqual([self.card(key) for key in (self.personal, self.subscribed)], before)
        result = migration.rollback_plan("two", "undo-two", user_id=self.user, approved=True)
        self.assertTrue(all(row["result"] == "rolled_back" for row in result))

    def test_retransition_after_rollback_keeps_fsrs_logs_and_is_idempotent(self):
        self.enable(self.personal, "original")
        self.rate(self.personal, grade="easy")
        self.rate(self.personal, request="second", grade="again")
        engine = ("srs_state", "srs_step", "srs_stability", "srs_difficulty", "srs_due_at", "srs_last_review_at",
                  "srs_effective_due_at", "srs_history_quality")
        last_fsrs = {name: self.card(self.personal)[name] for name in engine}
        migration.rollback_plan("original", "undo", user_id=self.user, approved=True)
        before, counts = self.card(self.personal), self.counts(self.personal)
        plan = migration.dry_run([self.personal])
        # Gate D-2 U8: an unchanged rolled-back card is restored to its last FSRS
        # state (not replayed); quality is the one it had before the rollback.
        self.assertEqual((plan[0].reconversion, plan[0].quality), ("restored", "fresh"), plan[0].flags)
        migration.apply_plan(plan, "retransition", approved=True)
        after = self.card(self.personal)
        self.assertEqual({name: after[name] for name in engine}, last_fsrs)
        self.assertEqual(after["next_review_at"], before["next_review_at"])
        self.assertEqual(self.counts(self.personal), counts)
        migration.apply_plan(plan, "retransition", approved=True)
        self.assertEqual(self.card(self.personal), after)

    def test_dry_run_is_read_only_and_apply_is_explicit(self):
        before = self.db_path.read_bytes()
        plan = migration.dry_run([self.personal, self.subscribed])
        self.assertTrue(all(candidate.quality == "fresh" for candidate in plan))
        self.assertEqual(self.db_path.read_bytes(), before)
        with self.assertRaisesRegex(SrsWriteError, "explicit_apply_required"):
            migration.apply_plan(plan, "run")
        self.assertEqual(self.db_path.read_bytes(), before)

    def test_complete_history_preserves_legacy_due_counts_status_and_logs(self):
        t0 = datetime(2026, 8, 1, 0, tzinfo=timezone.utc)
        for grade, at in [("good", t0), ("again", t0 + timedelta(days=1)), ("easy", t0 + timedelta(days=2))]:
            with mock.patch("app.repositories.vocab_repository.now_utc", return_value=at):
                record_review(self.user, self.item, grade)
        before, counts = self.card(self.personal), self.counts(self.personal)
        plan = migration.dry_run([self.personal])
        self.assertEqual(plan[0].quality, "complete")
        migration.apply_plan(plan, "history", approved=True)
        after = self.card(self.personal)
        for field in ("status", "review_level", "next_review_at", "last_reviewed_at", "correct_count", "wrong_count"):
            self.assertEqual(after[field], before[field], field)
        self.assertEqual(after["srs_effective_due_at"], before["next_review_at"])
        self.assertEqual(self.counts(self.personal), counts)

    def test_short_repeat_is_flag_not_missing_history(self):
        t0 = datetime(2026, 8, 1, 0, tzinfo=timezone.utc)
        for at in (t0, t0 + timedelta(seconds=30)):
            with mock.patch("app.repositories.vocab_repository.now_utc", return_value=at):
                record_review(self.user, self.item, "again")
        plan = migration.dry_run([self.personal])
        self.assertEqual(plan[0].quality, "complete")
        self.assertIn("short_interval_repeat", plan[0].flags)

    def test_missing_history_converts_without_engine_state(self):
        # Gate D-2 U5 changed this contract: incomplete history (here, logs gone) is
        # converted with an empty engine state and the existing schedule; before U5 it
        # stayed legacy. Unreadable log times still block (test_srs_d2_convert.py).
        record_review(self.user, self.item, "good")
        with get_connection() as connection:
            connection.execute("DELETE FROM review_logs WHERE vocab_item_id = ?", (self.item,))
        before = self.card(self.personal)
        plan = migration.dry_run([self.personal])
        self.assertEqual(plan[0].quality, "incomplete")
        result = migration.apply_plan(plan, "incomplete", approved=True)
        self.assertEqual(result[0]["result"], "applied")
        after = self.card(self.personal)
        self.assertEqual((after["srs_engine"], after["srs_state"], after["srs_history_quality"]), ("fsrs", None, "incomplete"))
        self.assertEqual(after["srs_effective_due_at"], before["next_review_at"])
        for field in ("status", "review_level", "next_review_at", "last_reviewed_at", "correct_count", "wrong_count"):
            self.assertEqual(after[field], before[field], field)

    def test_known_is_only_paused_in_explicit_migration(self):
        update_vocab_item(self.user, self.item, VocabItemUpdate(status="known"))
        self.assertIsNone(self.card(self.personal)["srs_participation"])
        self.enable(self.personal)
        self.assertEqual(self.card(self.personal)["status"], "known")
        self.assertEqual(self.card(self.personal)["srs_pause_reason"], "legacy_known")
        with self.assertRaisesRegex(SrsWriteError, "card_paused"):
            self.rate(self.personal)

    def test_new_legacy_review_conflicts_with_old_dry_run(self):
        plan = migration.dry_run([self.personal])
        record_review(self.user, self.item, "good")
        result = migration.apply_plan(plan, "racing", approved=True)
        self.assertEqual(result[0]["result"], "conflict")
        self.assertEqual(self.card(self.personal)["srs_engine"], "legacy")

    def test_reexecution_and_changed_scope(self):
        plan = migration.dry_run([self.personal])
        migration.apply_plan(plan, "repeat", approved=True)
        version = self.card(self.personal)["srs_card_version"]
        self.assertEqual(migration.apply_plan(plan, "repeat", approved=True)[0]["result"], "already_applied")
        self.assertEqual(self.card(self.personal)["srs_card_version"], version)
        with self.assertRaisesRegex(SrsWriteError, "migration_run_conflict"):
            migration.apply_plan(migration.dry_run([self.subscribed]), "repeat", approved=True)

    def test_mid_batch_failure_can_resume_without_duplicate_writes(self):
        plan = migration.dry_run([self.personal, self.subscribed])
        original = migration.update_card
        calls = 0

        def fail_second(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("synthetic interrupted batch")
            return original(*args, **kwargs)

        with mock.patch.object(migration, "update_card", side_effect=fail_second):
            with self.assertRaises(RuntimeError):
                migration.apply_plan(plan, "resume", approved=True)
        results = migration.apply_plan(plan, "resume", approved=True)
        self.assertEqual({result["result"] for result in results}, {"already_applied", "applied"})
        self.assertTrue(all(self.card(key)["srs_card_version"] == 1 for key in (self.personal, self.subscribed)))

    def test_rollback_keeps_new_evaluations_receipts_counts_and_user_edits(self):
        for key in (self.personal, self.subscribed):
            run = "rollback-" + key.kind
            self.enable(key, run)
            first = self.rate(key, request=key.kind, grade="easy")
            self.rate(key, request=key.kind + "-again", grade="again")
            if key.kind == "personal":
                update_vocab_item(self.user, self.item, VocabItemUpdate(status="uncertain", meaning_ko="edited"))
            before, counts = self.card(key), self.counts(key)
            result = migration.rollback_plan(run, run + "-undo", user_id=self.user, approved=True)
            self.assertEqual(result[0]["result"], "rolled_back")
            self.assertEqual(result[0]["preserved_reviews"], 2)
            after = self.card(key)
            for field in ("status", "correct_count", "wrong_count", "last_reviewed_at"):
                self.assertEqual(after[field], before[field])
            self.assertEqual(self.counts(key), counts)
            self.assertEqual(after["srs_engine"], "legacy")
            self.assertEqual(self.rate(key, request=key.kind, version=first["srs"]["card_version"] - 1, grade="easy"), first)
            self.assertEqual(migration.rollback_plan(run, run + "-undo", user_id=self.user, approved=True), result)

    def test_deleted_card_is_not_recreated_or_evaluated_from_receipt(self):
        self.enable(self.personal)
        self.rate(self.personal)
        with get_connection() as connection:
            connection.execute("DELETE FROM vocab_items WHERE id = ?", (self.item,))
        result = migration.rollback_plan("enable", "deleted-undo", user_id=self.user, approved=True)
        self.assertEqual(result[0]["result"], "missing_or_access_lost")
        self.assertIsNone(self.card(self.personal))
        self.assertEqual(self.counts(self.personal), (1, 1))


class ReviewRouteTests(SrsSqliteCase):
    def test_http_overlapping_duplicate_requests_share_one_evaluation(self):
        version = self.enable(self.personal)
        token = create_access_token({"id": self.user, "email": "srs-b2@example.test"})
        headers = {"Authorization": "Bearer " + token}
        body = dict(rating="again", request_id="http-overlap", expected_card_version=version, session_id="http-session")
        client = TestClient(main.app)
        self.addCleanup(client.close)
        inside, attempted, release = threading.Event(), threading.Event(), threading.Event()
        original_review, original_begin = reviews.review, storage.begin_card_write

        def slow_review(*args, **kwargs):
            inside.set()
            if not release.wait(5):
                raise AssertionError("HTTP requests did not overlap")
            return original_review(*args, **kwargs)

        def marked_begin(*args, **kwargs):
            if inside.is_set():
                attempted.set()
            return original_begin(*args, **kwargs)

        with mock.patch.object(reviews, "review", side_effect=slow_review), mock.patch.object(storage, "begin_card_write", side_effect=marked_begin):
            with ThreadPoolExecutor(max_workers=2) as pool:
                first = pool.submit(client.post, f"/study-items/{self.item}/review", headers=headers, json=body)
                try:
                    self.assertTrue(inside.wait(5))
                    second = pool.submit(client.post, f"/study-items/{self.item}/review", headers=headers, json=body)
                    self.assertTrue(attempted.wait(5))
                finally:
                    release.set()
                a, b = first.result(timeout=6), second.result(timeout=6)
        self.assertEqual(a.status_code, 200, a.text)
        self.assertEqual(b.status_code, 200, b.text)
        self.assertEqual(a.json(), b.json())
        self.assertEqual(self.counts(self.personal), (1, 1))

    def test_http_fsrs_retry_conflict_permissions_and_legacy_shape(self):
        client = TestClient(main.app)
        headers = {"Authorization": "Bearer " + create_access_token({"id": self.user, "email": "srs-b2@example.test"})}
        other_headers = {"Authorization": "Bearer " + create_access_token({"id": self.other, "email": "srs-b2-other@example.test"})}
        for key in (self.personal, self.subscribed):
            url = (f"/study-items/{key.ref_id}/review" if key.kind == "personal"
                   else f"/shared-decks/{self.shared}/words/{key.ref_id}/review")
            legacy = client.post(url, headers=headers, json={"rating": "good"})
            self.assertEqual(legacy.status_code, 200, legacy.text)
            self.assertNotIn("srs", legacy.json())
            # Use an explicit synthetic historical migration, not a runtime switch.
            version = self.enable(key, "route-" + key.kind)
            old = client.post(url, headers=headers, json={"rating": "good"})
            self.assertEqual(old.status_code, 422)
            body = dict(rating="again", request_id="route-" + key.kind, expected_card_version=version, session_id="route-session")
            first = client.post(url, headers=headers, json=body)
            self.assertEqual(first.status_code, 200, first.text)
            retry = client.post(url, headers=headers, json=body)
            self.assertEqual(first.json(), retry.json())
            conflict = client.post(url, headers=headers, json=body | {"rating": "easy"})
            self.assertEqual(conflict.status_code, 409)
            invalid = client.post(url, headers=headers, json=body | {"expected_card_version": True})
            self.assertEqual(invalid.status_code, 422)
            forbidden = client.post(url, headers=other_headers, json=body)
            self.assertEqual(forbidden.status_code, 404)
        client.close()


if __name__ == "__main__":
    unittest.main()

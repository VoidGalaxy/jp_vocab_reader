"""Gate D-2 U8: rollback that keeps later reviews, and conditional re-conversion that
restores the last FSRS state recorded by the rollback.

Synthetic SQLite only (QueueCase sets a throwaway DATABASE_URL per test before the
app touches a database). Damage and access changes below edit synthetic rows; the
app never does. Not covered here (not approved / not implemented): a fallback for a
missing, expired or damaged rollback record, and re-converting a card that changed
after the rollback while it keeps an evidence boundary. Both leave the card as it is.

Run directly:      python tests/test_srs_d2_rollback_reconvert.py
Or via discovery:   python -m unittest discover -s tests
"""

from __future__ import annotations

import hashlib
import json
import sys
import threading
import time
import types
import unittest
from datetime import timedelta
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_srs_d2_evidence_integrity import IntegrityCase  # noqa: E402
from test_srs_queue import NOW, iso  # noqa: E402
import race_support  # noqa: E402

from app.database import compute_review_schedule, get_connection  # noqa: E402
from app.schemas import VocabItemUpdate  # noqa: E402
from app.repositories import lexeme_repository, vocab_repository  # noqa: E402
from app.srs import engine, migration, reviews  # noqa: E402
from app.srs.engine import CardKey, state_from_json  # noqa: E402
from app.srs.storage import SrsWriteError  # noqa: E402

DAY = timedelta(days=1)
ENGINE = ("srs_state", "srs_step", "srs_stability", "srs_difficulty", "srs_due_at", "srs_last_review_at")
FSRS_VIEW = ENGINE + ("srs_engine", "srs_config_version", "srs_effective_due_at", "srs_participation",
                      "srs_pause_reason", "srs_history_quality", "srs_history_flags")
KEPT = ("history_intro_status", "history_intro_known_by", "evidence_from_log_id",
        "first_completed_at", "completion_metric_version", "status", "correct_count", "wrong_count",
        "last_reviewed_at", "created_at")


class ReconvertCase(IntegrityCase):
    def setUp(self):
        super().setUp()
        self._run = 0

    # --- steps ----------------------------------------------------------------
    def key(self, kind, ref):
        return CardKey(kind, self.user, ref)

    def first_run(self, kind, ref):
        return f"run-{ref}" if kind == "personal" else f"run-lx-{ref}"

    def rollback(self, kind, ref, source=None):
        self._run += 1
        return migration.rollback_plan(source or self.first_run(kind, ref), f"rb-{kind}-{ref}-{self._run}",
                                       user_id=self.user, approved=True)

    def reconvert(self, kind, ref):
        self._run += 1
        run = f"re-{kind}-{ref}-{self._run}"
        plan = migration.dry_run([self.key(kind, ref)])
        return run, plan[0], migration.apply_plan(plan, run, approved=True)[0]

    def legacy_change(self, kind, ref, at, deck=None):
        """A real legacy review in legacy account mode (existing code paths)."""
        self.set_mode(self.user, "legacy")
        try:
            if kind == "personal":
                with mock.patch.object(vocab_repository, "now_utc", return_value=at):
                    vocab_repository.record_review(self.user, ref, "good")
            else:
                with mock.patch.object(lexeme_repository, "now_utc", return_value=at):
                    lexeme_repository.record_lexeme_review(self.user, ref, "good", deck)
        finally:
            self.set_mode(self.user, "fsrs")

    # --- observations -----------------------------------------------------------
    def view(self, kind, ref):
        row = self.card_row(kind, ref)
        return {name: row[name] for name in FSRS_VIEW}

    def kept(self, kind, ref):
        row = self.card_row(kind, ref)
        return {name: row[name] for name in KEPT}

    def log_print(self, kind, ref):
        logs = self.logs_of(kind, ref)
        return len(logs), hashlib.sha256(json.dumps(logs, sort_keys=True, default=str).encode()).hexdigest()

    def new_count(self):
        count = self.count(NOW)
        return count.status, count.count

    def records(self, kind, ref):
        with get_connection() as c:
            return [dict(r) for r in c.execute(
                "SELECT s.*, r.mode FROM srs_migration_snapshots s JOIN srs_migration_runs r ON r.id = s.run_id "
                "WHERE s.user_id = ? AND s.card_kind = ? AND s.card_ref = ? ORDER BY s.id", (self.user, kind, ref))]

    def two_reviews(self, kind, ref, deck=None):
        self.rate_at(kind, ref, NOW, "good", deck=deck)
        self.rate_at(kind, ref, NOW + 2 * DAY, "good", deck=deck)
        self.now = NOW


# ---------------------------------------------------------------------------
class FlowTests(ReconvertCase):
    """convert -> 2 reviews -> rollback -> re-convert -> next review, real engine."""

    def flow(self, kind, deck=None):
        ref = self.converted(kind, f"flow-{kind}", deck)  # zero-log past card (U5, no engine state)
        start_count, start_kept = self.new_count(), self.kept(kind, ref)
        self.two_reviews(kind, ref, deck)
        last_fsrs, kept = self.view(kind, ref), self.kept(kind, ref)
        logs = self.log_print(kind, ref)
        version = self.card_row(kind, ref)["srs_card_version"]
        boundary = kept["evidence_from_log_id"]
        self.assertIsNotNone(boundary)
        self.assertEqual(self.new_count(), start_count)  # the past card was never new
        self.assertEqual({k: kept[k] for k in ("history_intro_status", "history_intro_known_by")},
                         {k: start_kept[k] for k in ("history_intro_status", "history_intro_known_by")})

        rolled = self.rollback(kind, ref)
        self.assertEqual(rolled, [dict(kind=kind, ref_id=ref, result="rolled_back", preserved_reviews=2)])
        after_rb = self.card_row(kind, ref)
        self.assertEqual(after_rb["srs_engine"], "legacy")
        self.assertEqual(after_rb["srs_card_version"], version + 1)
        self.assertEqual(self.log_print(kind, ref), logs)  # every later review kept, unchanged
        self.assertEqual(self.kept(kind, ref), kept)  # marks, boundary, completion, counters kept
        self.assertEqual(self.new_count(), start_count)
        # Legacy schedule recomputed from the later reviews with the legacy rule.
        snapshot = json.loads(self.records(kind, ref)[0]["legacy_json"])["card"]
        level, due = snapshot["review_level"], snapshot["next_review_at"]
        for log in self.fsrs_logs(kind, ref):
            level, due = compute_review_schedule(log["rating"], level, reviews.goals.read_utc(log[self.log_table(kind)[2]]))
        self.assertEqual((after_rb["review_level"], after_rb["next_review_at"]), (level, due))
        # The rollback recorded the last FSRS state and the baseline.
        record = self.records(kind, ref)[-1]
        self.assertEqual((record["mode"], json.loads(record["srs_before_json"])),
                         ("rollback", {k: last_fsrs[k] for k in migration.RESTORE_REQUIRED}))
        self.assertEqual(json.loads(record["legacy_json"])["baseline"]["card_version"], version + 1)

        _, candidate, result = self.reconvert(kind, ref)
        self.assertEqual((candidate.reconversion, result["result"], result["reconversion"]),
                         ("restored", "applied", "restored"))
        self.assertEqual(self.view(kind, ref), last_fsrs)  # the state just before the rollback
        self.assertEqual(self.card_row(kind, ref)["srs_card_version"], version + 2)
        self.assertEqual(self.log_print(kind, ref), logs)  # no log
        self.assertEqual(self.kept(kind, ref), kept)  # no completion, mark or boundary change
        self.assertEqual(self.new_count(), start_count)  # no new word

        # The next review continues from the restored state, inside the same window.
        at = NOW + 5 * DAY
        expected = engine.review(self.key(kind, ref), state_from_json(self.fsrs_logs(kind, ref)[-1]["srs_after_json"]),
                                 "good", at).after
        captured = []
        real = reviews.evaluate_completion

        def spy(state, events, *, evidence_complete):
            captured.append((len(events), evidence_complete))
            return real(state, events, evidence_complete=evidence_complete)

        with mock.patch.object(reviews, "evaluate_completion", spy):
            third = self.rate_at(kind, ref, at, "good", deck=deck)
        self.assertEqual(third["srs"]["state"], engine.state_to_dict(expected))
        self.assertEqual(captured, [(3, True)])  # evidence window still verifies: 2 kept + this one
        self.assertEqual(self.card_row(kind, ref)["evidence_from_log_id"], boundary)
        self.assertEqual(self.log_print(kind, ref)[0], logs[0] + 1)
        self.assertEqual(self.new_count(), start_count)
        return ref

    def test_personal(self):
        self.flow("personal")

    def test_subscribed(self):
        self.flow("lexeme", self.shared_deck("s"))

    def test_fresh_card_convert_review_rollback_reconvert(self):
        ref = self.personal("fresh")
        result = migration.apply_plan(self.plan(ref), "run-fresh", approved=True)
        self.assertEqual(result[0]["result"], "applied")
        self.two_reviews("personal", ref)
        last = self.view("personal", ref)
        self.rollback("personal", ref, source="run-fresh")
        self.assertEqual(self.reconvert("personal", ref)[2]["reconversion"], "restored")
        self.assertEqual(self.view("personal", ref), last)

    def test_unchanged_rollback_and_reconvert_twice_give_the_same_result(self):
        ref = self.converted("personal", "twice")
        self.two_reviews("personal", ref)
        last, kept, logs, count = (self.view("personal", ref), self.kept("personal", ref),
                                   self.log_print("personal", ref), self.new_count())
        legacy_after = None
        source = self.first_run("personal", ref)
        for cycle in range(2):
            with self.subTest(cycle=cycle):
                self.assertEqual(self.rollback("personal", ref, source=source)[0]["result"], "rolled_back")
                row = self.card_row("personal", ref)
                legacy = {k: row[k] for k in ("review_level", "next_review_at", "srs_engine")}
                if legacy_after is not None:
                    self.assertEqual(legacy, legacy_after)  # same legacy projection each time
                legacy_after = legacy
                source, _, result = self.reconvert("personal", ref)
                self.assertEqual(result["reconversion"], "restored")
                self.assertEqual(self.view("personal", ref), last)
                self.assertEqual((self.kept("personal", ref), self.log_print("personal", ref), self.new_count()),
                                 (kept, logs, count))
        # 1 conversion + 2 reviews + 2 x (rollback + re-conversion)
        self.assertEqual(self.card_row("personal", ref)["srs_card_version"], 1 + 2 + 4)
        # Re-running a finished re-conversion applies nothing again.
        plan = migration.dry_run([self.key("personal", ref)])
        self.assertEqual(plan[0].quality, "already_fsrs")

    def test_rollback_before_any_review_restores_the_state_none_card(self):
        ref = self.converted("personal", "no-review")
        last = self.view("personal", ref)
        self.rollback("personal", ref)
        self.assertEqual(self.reconvert("personal", ref)[2]["reconversion"], "restored")
        self.assertEqual(self.view("personal", ref), last)
        self.assertIsNone(self.card_row("personal", ref)["evidence_from_log_id"])
        before = self.new_count()
        self.rate_at("personal", ref, NOW, "good")  # U7 first review, still not a new word
        self.assertEqual(self.new_count(), before)
        self.assertIsNotNone(self.card_row("personal", ref)["evidence_from_log_id"])


# ---------------------------------------------------------------------------
class ChangedAfterRollbackTests(ReconvertCase):
    def test_changed_card_without_boundary_gets_no_engine_state(self):
        ref = self.converted("personal", "changed")  # rolled back before its first FSRS review
        self.rollback("personal", ref)
        self.legacy_change("personal", ref, NOW + DAY)
        row = self.card_row("personal", ref)
        logs, count = self.log_print("personal", ref), self.new_count()
        _, candidate, result = self.reconvert("personal", ref)
        self.assertEqual((candidate.reconversion, result["reconversion"]), ("state_none", "state_none"))
        after = self.card_row("personal", ref)
        self.assertEqual({k: after[k] for k in ENGINE}, {k: None for k in ENGINE})  # no replay
        self.assertEqual(after["srs_effective_due_at"], row["next_review_at"])
        self.assertIn("changed_since_rollback", json.loads(after["srs_history_flags"]))
        self.assertEqual((self.log_print("personal", ref), self.new_count()), (logs, count))
        self.rate_at("personal", ref, NOW + 2 * DAY, "good")  # U7 first review works
        self.assertIsNotNone(self.card_row("personal", ref)["evidence_from_log_id"])

    def test_changed_complete_card_is_not_replayed(self):
        ref = self.personal("complete-changed")
        migration.apply_plan(self.plan(ref), "run-cc", approved=True)
        self.two_reviews("personal", ref)
        self.rollback("personal", ref, source="run-cc")
        self.legacy_change("personal", ref, NOW + 3 * DAY)
        _, candidate, result = self.reconvert("personal", ref)
        self.assertEqual(result["reconversion"], "state_none")
        self.assertEqual({k: self.card_row("personal", ref)[k] for k in ENGINE}, {k: None for k in ENGINE})

    def test_changed_card_with_boundary_goes_to_plan_b(self):
        # U8 plan B (approved 2026-10-13): no engine state, boundary kept until the first
        # review (covered in test_srs_d2_u8_plan_b.py). Formerly left blocked.
        for kind in ("personal", "lexeme"):
            with self.subTest(kind=kind):
                deck = self.shared_deck(f"s-{kind}") if kind == "lexeme" else None
                ref = self.converted(kind, f"b-{kind}", deck)
                self.two_reviews(kind, ref, deck)
                boundary = self.card_row(kind, ref)["evidence_from_log_id"]
                self.rollback(kind, ref)
                self.legacy_change(kind, ref, NOW + 3 * DAY, deck)
                state = self.everything()
                plan = migration.dry_run([self.key(kind, ref)])
                self.assertEqual((plan[0].quality, plan[0].reconversion), ("incomplete", "state_none_restart"))
                self.assertIn("evidence_restart", plan[0].flags)
                self.assertEqual(self.everything(), state)  # dry-run wrote nothing
                result = migration.apply_plan(plan, f"re-b-{kind}", approved=True)[0]
                self.assertEqual((result["result"], result["reconversion"]), ("applied", "state_none_restart"))
                row = self.card_row(kind, ref)
                self.assertEqual({k: row[k] for k in ENGINE}, {k: None for k in ENGINE})
                self.assertEqual(row["evidence_from_log_id"], boundary)

    def test_known_card_stays_paused(self):
        ref = self.incomplete("known", iso(NOW - timedelta(hours=1)), status="known")
        self.assertEqual(self.card_row("personal", ref)["srs_participation"], "paused")
        self.rollback("personal", ref)
        self.assertEqual(self.reconvert("personal", ref)[2]["reconversion"], "restored")
        self.assertEqual((self.card_row("personal", ref)["srs_participation"],
                          self.card_row("personal", ref)["srs_pause_reason"]), ("paused", "legacy_known"))
        # Marked known after the rollback (a change): state none, paused.
        other = self.converted("personal", "later-known")
        self.rollback("personal", other)
        vocab_repository.update_vocab_item(self.user, other, VocabItemUpdate(status="known"))
        result = self.reconvert("personal", other)[2]
        self.assertEqual(result["reconversion"], "state_none")
        self.assertEqual(self.card_row("personal", other)["srs_participation"], "paused")


# ---------------------------------------------------------------------------
class BlockedTests(ReconvertCase):
    def rolled(self, kind="personal", deck=None, name="blocked"):
        ref = self.converted(kind, name, deck)
        self.two_reviews(kind, ref, deck)
        self.rollback(kind, ref)
        return ref

    def assert_untouched(self, kind, ref, quality, flags):
        state = self.everything()
        plan = migration.dry_run([self.key(kind, ref)])
        self.assertEqual((plan[0].quality, plan[0].flags), (quality, flags))
        self.assertEqual(self.everything(), state)
        result = migration.apply_plan(plan, f"re-{kind}-{ref}-blocked", approved=True)[0]
        self.assertEqual(result["result"], "blocked")
        after = self.everything()
        for table in ("vocab_items", "user_word_progress", "review_logs", "lexeme_review_logs",
                      "srs_migration_snapshots", "srs_card_deletions"):
            self.assertEqual(after[table], state[table], table)  # only the run row is new
        return result

    def test_missing_rollback_record(self):
        ref = self.rolled()
        with get_connection() as c:  # a rollback made before U8 kept no record
            c.execute("DELETE FROM srs_migration_snapshots WHERE run_id IN "
                      "(SELECT id FROM srs_migration_runs WHERE mode = 'rollback')")
        self.assert_untouched("personal", ref, "reconvert_blocked", ("rollback_snapshot_missing",))

    def test_damaged_rollback_records(self):
        cases = {
            "legacy_json": "{broken",
            "srs_before_json": "{broken",
        }
        for column, value in cases.items():
            with self.subTest(column=column):
                ref = self.rolled(name=f"damaged-{column}")
                with get_connection() as c:
                    c.execute(f"UPDATE srs_migration_snapshots SET {column} = ? WHERE id = ?",
                              (value, self.records("personal", ref)[-1]["id"]))
                self.assert_untouched("personal", ref, "reconvert_blocked", ("rollback_snapshot_unreadable",))
        ref = self.rolled(name="bad-state")
        record = self.records("personal", ref)[-1]
        restore = json.loads(record["srs_before_json"])
        restore["srs_stability"] = "not a number"
        with get_connection() as c:
            c.execute("UPDATE srs_migration_snapshots SET srs_before_json = ? WHERE id = ?",
                      (json.dumps(restore), record["id"]))
        self.assert_untouched("personal", ref, "reconvert_blocked", ("rollback_snapshot_unreadable",))

    def test_config_mismatch(self):
        ref = self.rolled()
        other = types.SimpleNamespace(config_version="fsrs-other-config")
        with mock.patch.object(migration, "DEFAULT_CONFIG", other):
            self.assert_untouched("personal", ref, "reconvert_blocked", ("config_mismatch",))

    def test_deleted_access_lost_and_identity_unknown(self):
        ref = self.rolled(name="deleted")
        vocab_repository.delete_vocab_item(self.user, ref)
        plan = migration.dry_run([self.key("personal", ref)])
        self.assertEqual(plan[0].quality, "unavailable")
        self.assertEqual(migration.apply_plan(plan, "re-deleted", approved=True)[0]["result"], "blocked")
        # Subscribed: access lost.
        deck = self.shared_deck("s")
        lexeme = self.rolled("lexeme", deck, name="lost")
        with get_connection() as c:
            c.execute("UPDATE user_deck_subscriptions SET is_active = FALSE WHERE user_id = ?", (self.user,))
        state = self.everything()
        self.assertEqual(migration.dry_run([self.key("lexeme", lexeme)])[0].quality, "unavailable")
        self.assertEqual(self.everything(), state)
        # Identity unknown.
        flagged = self.rolled(name="flagged")
        with get_connection() as c:
            c.execute("INSERT INTO srs_card_identity_flags (user_id, card_kind, card_ref, reasons, detected_at) "
                      "VALUES (?, 'personal', ?, '[\"deleted_then_reused\"]', ?)", (self.user, flagged, iso(NOW)))
        self.assertEqual(migration.dry_run([self.key("personal", flagged)])[0].quality, "identity_unknown")

    def test_reused_id_in_the_deletion_ledger(self):
        ref = self.rolled()
        with get_connection() as c:
            c.execute("INSERT INTO srs_card_deletions (card_kind, user_id, card_ref, deleted_at) VALUES ('personal', ?, ?, ?)",
                      (self.user, ref, iso(NOW)))
        self.assert_untouched("personal", ref, "reconvert_blocked", ("identity_reused",))

    def test_damaged_history_after_rollback(self):
        for column, value in (("rating", "garbage"), ("reviewed_at", "not-a-time")):
            with self.subTest(column=column):
                ref = self.rolled(name=f"dmg-{column}")
                self.tamper("personal", self.fsrs_logs("personal", ref)[0]["id"], **{column: value})
                self.assert_untouched("personal", ref, "reconvert_blocked", ("history_unreadable",))


# ---------------------------------------------------------------------------
class RollbackScopeTests(ReconvertCase):
    def test_skips_deleted_access_lost_and_identity_unknown(self):
        deleted = self.converted("personal", "d")
        flagged = self.converted("personal", "f")
        deck = self.shared_deck("s")
        lost = self.converted("lexeme", "l", deck)
        vocab_repository.delete_vocab_item(self.user, deleted)
        with get_connection() as c:
            c.execute("INSERT INTO srs_card_identity_flags (user_id, card_kind, card_ref, reasons, detected_at) "
                      "VALUES (?, 'personal', ?, '[\"deleted_then_reused\"]', ?)", (self.user, flagged, iso(NOW)))
            c.execute("UPDATE user_deck_subscriptions SET is_active = FALSE WHERE user_id = ?", (self.user,))
        before = {k: self.card_row(k, r) for k, r in (("personal", flagged), ("lexeme", lost))}
        self.assertEqual(self.rollback("personal", deleted)[0]["result"], "missing_or_access_lost")
        self.assertEqual(self.rollback("personal", flagged)[0],
                         dict(kind="personal", ref_id=flagged, result="skipped", reason="identity_unknown"))
        self.assertEqual(self.rollback("lexeme", lost)[0]["result"], "missing_or_access_lost")
        self.assertEqual({k: self.card_row(k, r) for k, r in (("personal", flagged), ("lexeme", lost))}, before)
        self.assertEqual([r for r in self.records("personal", flagged) if r["mode"] == "rollback"], [])

    def test_unreadable_later_log_refuses_the_whole_rollback(self):
        for column, value, cause in (("rating", "garbage", "rating"), ("reviewed_at", "garbage", "time")):
            with self.subTest(cause=cause):
                good = self.personal(f"good-{cause}")
                bad = self.personal(f"bad-{cause}")
                run = f"run-two-{cause}"
                migration.apply_plan(migration.dry_run([self.key("personal", good), self.key("personal", bad)]),
                                     run, approved=True)
                for ref in (good, bad):
                    self.two_reviews("personal", ref)
                self.tamper("personal", self.fsrs_logs("personal", bad)[1]["id"], **{column: value})
                state = self.everything()
                with self.assertRaises(migration.RollbackHistoryUnreadable) as caught:
                    migration.rollback_plan(run, f"rb-two-{cause}", user_id=self.user, approved=True)
                self.assertEqual(caught.exception.code, "rollback_history_unreadable")
                self.assertEqual(caught.exception.cards, [dict(kind="personal", ref_id=bad, logs=[
                    dict(log_id=self.fsrs_logs("personal", bad)[1]["id"], cause=cause)])])
                self.assertEqual(self.everything(), state)  # neither card, no run row, nothing repaired


# ---------------------------------------------------------------------------
class AtomicityTests(ReconvertCase):
    def test_change_after_preview_is_a_conflict(self):
        ref = self.converted("personal", "preview")
        self.rollback("personal", ref)
        plan = migration.dry_run([self.key("personal", ref)])
        self.assertEqual(plan[0].reconversion, "restored")
        self.legacy_change("personal", ref, NOW + DAY)
        self.assertEqual(migration.apply_plan(plan, "re-preview", approved=True)[0]["result"], "conflict")
        self.assertEqual(self.card_row("personal", ref)["srs_engine"], "legacy")

    def test_reconversion_failure_then_resume_applies_once(self):
        refs = [self.converted("personal", f"batch-{i}") for i in range(3)]
        for ref in refs:
            self.two_reviews("personal", ref)
        lasts = [self.view("personal", ref) for ref in refs]
        for ref in refs:
            self.rollback("personal", ref)
        plan = migration.dry_run([self.key("personal", ref) for ref in refs])
        real = migration.update_card
        calls = 0

        def fail_second(*a, **k):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("synthetic failure")
            return real(*a, **k)

        with mock.patch.object(migration, "update_card", fail_second):
            with self.assertRaises(RuntimeError):
                migration.apply_plan(plan, "re-batch", approved=True)
        self.assertEqual(self.view("personal", refs[0]), lasts[0])
        self.assertEqual(self.card_row("personal", refs[1])["srs_engine"], "legacy")  # card, record, cursor: none
        with get_connection() as c:
            run = c.execute("SELECT status, summary_json FROM srs_migration_runs WHERE run_key = 're-batch'").fetchone()
            self.assertEqual((run["status"], json.loads(run["summary_json"])["cursor"]), ("failed", 1))
        resumed = migration.apply_plan(plan, "re-batch", approved=True)
        self.assertEqual([r["result"] for r in resumed], ["already_applied", "applied", "applied"])
        self.assertEqual([self.view("personal", ref) for ref in refs], lasts)
        versions = [self.card_row("personal", ref)["srs_card_version"] for ref in refs]
        again = migration.apply_plan(plan, "re-batch", approved=True)
        self.assertEqual([r["result"] for r in again], ["already_applied"] * 3)
        self.assertEqual([self.card_row("personal", ref)["srs_card_version"] for ref in refs], versions)

    def test_rollback_failure_writes_nothing_and_retry_rolls_back_once(self):
        a, b = self.personal("a"), self.personal("b")
        migration.apply_plan(migration.dry_run([self.key("personal", a), self.key("personal", b)]), "run-ab",
                             approved=True)
        for ref in (a, b):
            self.two_reviews("personal", ref)
        state = self.everything()
        real = migration._card_print
        calls = 0

        def fail_record(*args):
            nonlocal calls
            calls += 1
            if calls == 2:  # after the first card's update and record, during the second card
                raise RuntimeError("synthetic failure")
            return real(*args)

        with mock.patch.object(migration, "_card_print", fail_record):
            with self.assertRaises(RuntimeError):
                migration.rollback_plan("run-ab", "rb-ab", user_id=self.user, approved=True)
        self.assertEqual(self.everything(), state)
        first = migration.rollback_plan("run-ab", "rb-ab", user_id=self.user, approved=True)
        self.assertEqual([r["result"] for r in first], ["rolled_back"] * 2)
        after = self.everything()
        self.assertEqual(migration.rollback_plan("run-ab", "rb-ab", user_id=self.user, approved=True), first)
        self.assertEqual(self.everything(), after)  # retry: same summary, nothing applied twice
        self.assertEqual(len([r for r in after["srs_migration_snapshots"]]), 4)  # 2 apply + 2 rollback records


# ---------------------------------------------------------------------------
class RaceTests(ReconvertCase):
    def blocker(self, target, name):
        entered, release = threading.Event(), threading.Event()
        real = getattr(target, name)

        def slow(*a, **k):
            result = real(*a, **k)
            entered.set()
            self.assertTrue(release.wait(15))
            return result

        return entered, release, mock.patch.object(target, name, slow)

    def hold_then(self, probe, holder, entered, release, waiter_name, waiter_fn):
        self.assertTrue(entered.wait(15))
        waiter = race_support.start(waiter_name, waiter_fn)
        self.assertTrue(probe.wait("waiting", waiter_name))
        time.sleep(0.3)
        self.assertNotIn(("acquired", waiter_name), probe.events)
        probe.mark("released", holder.name)
        release.set()
        return waiter

    def review_call(self, ref, version, at, request):
        def call():
            with mock.patch.object(reviews, "now_utc", return_value=at):
                return vocab_repository.record_review(self.user, ref, "good", request_id=request,
                                                      expected_card_version=version, session_id="s1")
        return call

    def test_rollback_first_then_review(self):
        ref = self.converted("personal", "rb-first")
        self.two_reviews("personal", ref)
        version, logs = self.card_row("personal", ref)["srs_card_version"], self.log_print("personal", ref)
        entered, release, patch = self.blocker(migration, "compute_review_schedule")
        with race_support.LockProbe() as probe, patch:
            rb = race_support.start("rollback", lambda: self.rollback("personal", ref))
            review = self.hold_then(probe, rb, entered, release, "review",
                                    self.review_call(ref, version, NOW + 3 * DAY, self.req(9101)))
            self.assertEqual(race_support.finish(self, rb)[0]["result"], "rolled_back")
            race_support.finish_error(self, review, SrsWriteError, "card_version_conflict")
        probe.assert_serialized(self, "rollback", "review")
        self.assertEqual(self.card_row("personal", ref)["srs_engine"], "legacy")
        self.assertEqual(self.log_print("personal", ref), logs)  # the late review wrote nothing

    def test_subscribed_rollback_first_then_stale_review(self):
        deck = self.shared_deck("s")
        ref = self.converted("lexeme", "lx-rb-first", deck)
        self.two_reviews("lexeme", ref, deck)
        version, logs = self.card_row("lexeme", ref)["srs_card_version"], self.log_print("lexeme", ref)

        def stale():
            with mock.patch.object(reviews, "now_utc", return_value=NOW + 3 * DAY):
                return lexeme_repository.record_lexeme_review(self.user, ref, "good", deck, request_id=self.req(9201),
                                                              expected_card_version=version, session_id="s1")

        entered, release, patch = self.blocker(migration, "compute_review_schedule")
        with race_support.LockProbe() as probe, patch:
            rb = race_support.start("rollback", lambda: self.rollback("lexeme", ref))
            review = self.hold_then(probe, rb, entered, release, "review", stale)
            self.assertEqual(race_support.finish(self, rb)[0]["result"], "rolled_back")
            race_support.finish_error(self, review, SrsWriteError, "card_version_conflict")
        probe.assert_serialized(self, "rollback", "review")
        self.assertEqual(self.log_print("lexeme", ref), logs)
        # Re-conversion still restores: the stale request changed nothing.
        self.assertEqual(self.reconvert("lexeme", ref)[2]["reconversion"], "restored")

    def test_review_first_then_rollback_keeps_it(self):
        ref = self.converted("personal", "review-first")
        self.two_reviews("personal", ref)
        version = self.card_row("personal", ref)["srs_card_version"]
        entered, release, patch = self.blocker(reviews, "evaluate_completion")
        with race_support.LockProbe() as probe, patch:
            review = race_support.start("review", self.review_call(ref, version, NOW + 3 * DAY, self.req(9102)))
            rb = self.hold_then(probe, review, entered, release, "rollback", lambda: self.rollback("personal", ref))
            race_support.finish(self, review)
            result = race_support.finish(self, rb)
        probe.assert_serialized(self, "review", "rollback")
        self.assertEqual(result, [dict(kind="personal", ref_id=ref, result="rolled_back", preserved_reviews=3)])
        self.assertEqual(len(self.fsrs_logs("personal", ref)), 3)
        record = json.loads(self.records("personal", ref)[-1]["srs_before_json"])
        last = state_from_json(self.fsrs_logs("personal", ref)[-1]["srs_after_json"])
        self.assertEqual(record["srs_stability"], last.stability)  # the record has the newest state

    def test_reconversion_first_then_stale_review(self):
        ref = self.converted("personal", "re-first")
        self.two_reviews("personal", ref)
        self.rollback("personal", ref)
        version, logs = self.card_row("personal", ref)["srs_card_version"], self.log_print("personal", ref)
        plan = migration.dry_run([self.key("personal", ref)])
        entered, release, patch = self.blocker(migration, "record_intro")
        with race_support.LockProbe() as probe, patch:
            apply = race_support.start("apply", lambda: migration.apply_plan(plan, "re-race-1", approved=True))
            review = self.hold_then(probe, apply, entered, release, "review",
                                    self.review_call(ref, version, NOW + 3 * DAY, self.req(9103)))
            self.assertEqual(race_support.finish(self, apply)[0]["reconversion"], "restored")
            race_support.finish_error(self, review, SrsWriteError, "card_version_conflict")
        probe.assert_serialized(self, "apply", "review")
        self.assertEqual(self.card_row("personal", ref)["srs_engine"], "fsrs")
        self.assertEqual(self.log_print("personal", ref), logs)

    def test_legacy_review_first_then_reconversion_conflicts(self):
        ref = self.converted("personal", "legacy-first")
        self.two_reviews("personal", ref)
        self.rollback("personal", ref)
        plan = migration.dry_run([self.key("personal", ref)])
        logs = self.log_print("personal", ref)
        entered, release, patch = self.blocker(vocab_repository, "compute_review_schedule")
        self.set_mode(self.user, "legacy")
        with race_support.LockProbe() as probe, patch:
            review = race_support.start("review", lambda: vocab_repository.record_review(self.user, ref, "good"))
            apply = self.hold_then(probe, review, entered, release, "apply",
                                   lambda: migration.apply_plan(plan, "re-race-2", approved=True))
            race_support.finish(self, review)
            self.assertEqual(race_support.finish(self, apply)[0]["result"], "conflict")
        probe.assert_serialized(self, "review", "apply")
        self.assertEqual(self.card_row("personal", ref)["srs_engine"], "legacy")
        self.assertEqual(self.log_print("personal", ref)[0], logs[0] + 1)


if __name__ == "__main__":
    unittest.main()

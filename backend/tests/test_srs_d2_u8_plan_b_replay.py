"""Gate D-2 U8 plan B, remaining block: valid plan-B candidates no longer need the old
full history to replay through the engine (approved 2026-10-13). The old history is
never used for the new state or evidence; the shared readability check stays.

Case A: a U5 card WITH legacy logs -> FSRS reviews -> rollback -> legacy change -> B.
Case B: B -> first + follow-up reviews -> rollback -> legacy change -> second (third) B.
Both used to stop at fsrs_snapshot_mismatch from the full-history replay.

Synthetic SQLite only (QueueCase sets a throwaway DATABASE_URL per test before the
app touches a database). Damage below edits synthetic rows; the app never does.

Run directly:      python tests/test_srs_d2_u8_plan_b_replay.py
Or via discovery:   python -m unittest discover -s tests
"""

from __future__ import annotations

import sys
import threading
import time
import types
import unittest
from datetime import timedelta
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_srs_d2_u8_plan_b import PlanBCase  # noqa: E402
from test_srs_queue import NOW, iso  # noqa: E402
import race_support  # noqa: E402

from app.database import get_connection  # noqa: E402
from app.repositories import vocab_repository  # noqa: E402
from app.srs import migration, reviews  # noqa: E402
from app.srs.storage import SrsWriteError  # noqa: E402

DAY = timedelta(days=1)


class ReplayCase(PlanBCase):
    def with_legacy_logs(self, kind, name, deck=None, order=0):
        """Case A start: a legacy card with legacy logs that do not match it (U5-incomplete)."""
        due = iso(NOW - timedelta(hours=1))
        if kind == "personal":
            ref = self.personal(name)
            for days in (70, 60):
                self.raw_log(ref, NOW - timedelta(days=days))
            with get_connection() as c:
                c.execute("UPDATE vocab_items SET last_reviewed_at = ?, correct_count = 9, next_review_at = ? WHERE id = ?",
                          (iso(NOW - timedelta(days=60)), due, ref))
            run = f"run-{ref}"
        else:
            ref = self.lexeme(name, deck, order)
            with get_connection() as c:
                for days, prev in ((70, 0), (60, 4)):
                    c.execute("INSERT INTO lexeme_review_logs (user_id, lexeme_id, shared_deck_id, rating, "
                              "previous_review_level, new_review_level, previous_next_review_at, new_next_review_at, "
                              "previous_status, new_status, created_at) VALUES (?, ?, ?, 'good', ?, ?, NULL, ?, "
                              "'unknown', 'unknown', ?)",
                              (self.user, ref, deck, prev, prev + 1, iso(NOW - timedelta(days=days - 1)),
                               iso(NOW - timedelta(days=days))))
                c.execute("UPDATE user_word_progress SET srs_engine = 'legacy', srs_config_version = NULL, "
                          "srs_participation = NULL, srs_history_quality = NULL, last_reviewed_at = ?, correct_count = 9, "
                          "next_review_at = ? WHERE user_id = ? AND lexeme_id = ?",
                          (iso(NOW - timedelta(days=60)), due, self.user, ref))
            run = f"run-lx-{ref}"
        plan = migration.dry_run([self.key(kind, ref)])
        self.assertEqual(plan[0].quality, "incomplete")
        self.assertEqual(migration.apply_plan(plan, run, approved=True)[0]["result"], "applied")
        return ref

    def window_reviews(self, kind, ref, start, deck=None, ratings=("easy", "easy", "easy", "easy"), gaps=(0, 8, 30, 90)):
        """First review + follow-ups; asserts every event list is exactly this window."""
        times, at = [], start
        for rating, gap in zip(ratings, gaps):
            at += gap * DAY
            self.rate_at(kind, ref, at, rating, deck=deck)
            self.now = NOW
            times.append((at, rating))
            events, complete = self.seen[-1]
            self.assertTrue(complete)
            self.assertEqual(events, times)  # nothing from older windows or legacy reviews
        return at

    def plan_b(self, kind, ref, source, at, deck=None):
        """rollback -> real legacy change -> B (no replay of the old history)."""
        self.assertEqual(self.rollback(kind, ref, source=source)[0]["result"], "rolled_back")
        self.legacy_change(kind, ref, at + DAY, deck)
        with mock.patch.object(migration, "review", side_effect=AssertionError("old history replayed")):
            plan = migration.dry_run([self.key(kind, ref)])
        self.assertEqual((plan[0].reconversion, plan[0].quality), ("state_none_restart", "incomplete"), plan[0].flags)
        self.assertNotIn("fsrs_snapshot_mismatch", plan[0].flags)
        run = f"re-b-{kind}-{ref}-{self._run}"
        self._run += 1
        self.assertEqual(migration.apply_plan(plan, run, approved=True)[0]["reconversion"], "state_none_restart")
        return run, at + 3 * DAY


# ---------------------------------------------------------------------------
class CaseATests(ReplayCase):
    def run_case(self, kind, deck=None):
        ref = self.with_legacy_logs(kind, f"a-{kind}", deck)
        at = self.old_window(kind, ref, deck)
        boundary = self.card_row(kind, ref)["evidence_from_log_id"]
        count, legacy_logs = self.new_count(), self.log_print(kind, ref)
        run, start = self.plan_b(kind, ref, self.first_run(kind, ref), at, deck)
        row = self.card_row(kind, ref)
        self.assertEqual((row["srs_state"], row["evidence_from_log_id"]), (None, boundary))
        self.window_reviews(kind, ref, start, deck)
        rows = self.restarts(kind, ref)
        self.assertEqual([(r["previous_boundary"]) for r in rows], [boundary])
        self.assertEqual(self.card_row(kind, ref)["evidence_from_log_id"], rows[0]["new_boundary"])
        self.assertEqual(self.new_count(), count)
        self.assertGreater(self.log_print(kind, ref)[0], legacy_logs[0])

    def test_personal(self):
        self.run_case("personal")

    def test_subscribed(self):
        self.run_case("lexeme", self.shared_deck("s"))


class RepeatedPlanBTests(ReplayCase):
    def run_case(self, kind, deck=None):
        ref, first_boundary, run, start = self.to_plan_b(kind, deck, name=f"rep-{kind}")
        count = self.new_count()
        at = self.window_reviews(kind, ref, start, deck)
        boundaries = [first_boundary, self.card_row(kind, ref)["evidence_from_log_id"]]
        for _ in range(2):  # second and third plan B
            run, start = self.plan_b(kind, ref, run, at, deck)
            self.assertEqual(self.card_row(kind, ref)["evidence_from_log_id"], boundaries[-1])  # not moved yet
            at = self.window_reviews(kind, ref, start, deck)
            boundaries.append(self.card_row(kind, ref)["evidence_from_log_id"])
        rows = self.restarts(kind, ref)
        self.assertEqual([(r["previous_boundary"], r["new_boundary"]) for r in rows], list(zip(boundaries, boundaries[1:])))
        self.assertEqual(len({r["source_snapshot_id"] for r in rows}), 3)
        self.assertEqual(self.new_count(), count)
        return ref

    def test_personal_second_and_third(self):
        self.run_case("personal")

    def test_subscribed_second_and_third(self):
        self.run_case("lexeme", self.shared_deck("s"))

    def test_new_window_reaches_completion_and_old_one_is_not_mixed(self):
        ref = self.converted("personal", "done")
        at = self.window_reviews("personal", ref, NOW, gaps=(0, 8, 30, 90, 200), ratings=("easy",) * 5)
        old_done = self.card_row("personal", ref)["first_completed_at"]
        self.assertIsNotNone(old_done)
        run, start = self.plan_b("personal", ref, self.first_run("personal", ref), at)
        first = self.rate_at("personal", ref, start, "again")
        self.now = NOW
        self.assertEqual(self.seen[-1], ([(start, "again")], True))
        self.assertNotEqual(first["srs"]["completion_status"], "completed")
        statuses, at = [], start
        for gap in (8, 30, 90, 200, 400):
            at += gap * DAY
            statuses.append(self.rate_at("personal", ref, at, "easy")["srs"]["completion_status"])
            self.now = NOW
        self.assertIn("completed", statuses)  # the new window can complete on its own evidence
        self.assertEqual(self.card_row("personal", ref)["first_completed_at"], old_done)  # history kept

    def test_unchanged_restore_between_plan_bs(self):
        ref, _, run, start = self.to_plan_b("personal", name="between")
        at = self.window_reviews("personal", ref, start)
        boundary = self.card_row("personal", ref)["evidence_from_log_id"]
        self.assertEqual(self.rollback("personal", ref, source=run)[0]["result"], "rolled_back")
        run2, candidate, result = self.reconvert("personal", ref)
        self.assertEqual((result["reconversion"], candidate.restart_json), ("restored", None))
        self.assertEqual(self.card_row("personal", ref)["evidence_from_log_id"], boundary)
        self.rate_at("personal", ref, at + 10 * DAY, "good")
        self.now = NOW
        self.assertTrue(self.seen[-1][1])  # proven restore keeps the same window
        self.plan_b("personal", ref, run2, at + 10 * DAY)
        self.assertEqual(len(self.restarts("personal", ref)), 1)  # second B not reviewed yet


# ---------------------------------------------------------------------------
class StillBlockedTests(ReplayCase):
    def second_b_ready(self, name):
        """A card after one reviewed B window, rolled back and changed (a second-B candidate)."""
        ref, _, run, start = self.to_plan_b("personal", name=name)
        at = self.window_reviews("personal", ref, start)
        self.assertEqual(self.rollback("personal", ref, source=run)[0]["result"], "rolled_back")
        self.legacy_change("personal", ref, at + DAY)
        return ref, at

    def assert_blocked(self, ref, flags, quality="reconvert_blocked", kind="personal"):
        state = self.everything()
        plan = migration.dry_run([self.key(kind, ref)])
        self.assertEqual((plan[0].quality, plan[0].flags), (quality, flags))
        self.assertEqual(migration.apply_plan(plan, f"re-blk-{ref}-{self._run}", approved=True)[0]["result"], "blocked")
        self._run += 1
        after = self.everything()
        for table in ("vocab_items", "user_word_progress", "review_logs", "lexeme_review_logs", "srs_migration_snapshots",
                      "srs_evidence_restarts", "srs_review_receipts"):
            self.assertEqual(after[table], state[table], table)

    def test_config_mismatch_on_the_changed_path(self):
        ref, _ = self.second_b_ready("config")
        with mock.patch.object(migration, "DEFAULT_CONFIG", types.SimpleNamespace(config_version="fsrs-other")):
            self.assert_blocked(ref, ("config_mismatch",))

    def test_unreadable_time_rating_and_window_snapshot(self):
        for name, column, value, which in (("time", "reviewed_at", "not-a-time", 0), ("rating", "rating", "garbage", 0),
                                           ("snapshot", "srs_after_json", "{broken", -1)):
            with self.subTest(name=name):
                ref, _ = self.second_b_ready(f"dmg-{name}")
                logs = self.fsrs_logs("personal", ref)
                self.tamper("personal", logs[which]["id"], **{column: value})
                self.assert_blocked(ref, ("history_unreadable",))

    def test_snapshot_damage_outside_the_current_window_is_not_examined(self):
        ref, _ = self.second_b_ready("outside")
        self.tamper("personal", self.fsrs_logs("personal", ref)[0]["id"], srs_after_json="{broken")  # old window
        self.assertEqual(migration.dry_run([self.key("personal", ref)])[0].reconversion, "state_none_restart")

    def test_access_lost_and_missing_schedule(self):
        deck = self.shared_deck("s")
        ref, _, run, start = self.to_plan_b("lexeme", deck, name="lost")
        at = self.window_reviews("lexeme", ref, start, deck)
        self.rollback("lexeme", ref, source=run)
        self.legacy_change("lexeme", ref, at + DAY, deck)
        with get_connection() as c:
            c.execute("UPDATE user_deck_subscriptions SET is_active = FALSE WHERE user_id = ?", (self.user,))
        state = self.everything()
        self.assertEqual(migration.dry_run([self.key("lexeme", ref)])[0].quality, "unavailable")
        self.assertEqual(self.everything(), state)
        ref2, _ = self.second_b_ready("no-schedule")
        with get_connection() as c:
            c.execute("UPDATE vocab_items SET next_review_at = NULL WHERE id = ?", (ref2,))
        plan = migration.dry_run([self.key("personal", ref2)])
        self.assertIsNone(plan[0].values_json)
        self.assertIn("schedule_missing", plan[0].flags)

    def test_first_conversion_and_boundaryless_reconversion_are_not_widened(self):
        # First conversion: a legacy card whose logs include an FSRS log that replay rejects stays blocked.
        card = self.personal("first-conv")
        self.raw_log(card, NOW - timedelta(days=5))
        with get_connection() as c:
            c.execute("UPDATE review_logs SET srs_engine = 'fsrs', srs_config_version = ?, srs_before_json = 'null', "
                      "srs_after_json = 'null' WHERE vocab_item_id = ?", (reviews.DEFAULT_CONFIG.config_version, card))
        with mock.patch.object(migration, "review", wraps=migration.review) as replay:
            plan = migration.dry_run([self.key("personal", card)])
        self.assertTrue(replay.called)  # first conversion still replays
        self.assertIn("fsrs_snapshot_mismatch", plan[0].flags)
        self.assertIsNone(plan[0].values_json)
        # Changed card WITHOUT a boundary still goes through the U5 flags (replay kept).
        ref = self.converted("personal", "no-boundary")
        self.rollback("personal", ref)
        self.legacy_change("personal", ref, NOW + DAY)
        with mock.patch.object(migration, "review", wraps=migration.review) as replay:
            plan = migration.dry_run([self.key("personal", ref)])
        self.assertEqual(plan[0].reconversion, "state_none")
        self.assertTrue(replay.called)

    def test_stale_permission_of_an_earlier_plan_b(self):
        ref, at = self.second_b_ready("stale")
        old_rows = self.restarts("personal", ref)
        run, start = self.plan_b_from_ready(ref, at)
        # Roll back the second B before its first review, change again, re-convert: only the newest permission works.
        self.rollback("personal", ref, source=run)
        self.legacy_change("personal", ref, start)
        run3, start3 = self.reconvert_b(ref)
        self.rate_at("personal", ref, start3 + DAY, "good")
        self.now = NOW
        rows = self.restarts("personal", ref)
        self.assertEqual(len(rows), len(old_rows) + 1)
        with get_connection() as c:
            latest = c.execute("SELECT s.id FROM srs_migration_snapshots s JOIN srs_migration_runs r ON r.id = s.run_id "
                               "WHERE r.run_key = ?", (run3,)).fetchone()[0]
        self.assertEqual(rows[-1]["source_snapshot_id"], latest)

    def plan_b_from_ready(self, ref, at):
        run, start = self.reconvert_b(ref)
        return run, start

    def reconvert_b(self, ref):
        run = f"re-ready-{ref}-{self._run}"
        self._run += 1
        result = migration.apply_plan(migration.dry_run([self.key("personal", ref)]), run, approved=True)[0]
        self.assertEqual(result["reconversion"], "state_none_restart")
        return run, NOW + 400 * DAY


# ---------------------------------------------------------------------------
class RepeatedAtomicityTests(ReplayCase):
    def second_b(self, name):
        ref, _, run, start = self.to_plan_b("personal", name=name)
        at = self.window_reviews("personal", ref, start)
        run2, start2 = self.plan_b("personal", ref, run, at)
        return ref, start2

    def test_retry_of_the_first_review(self):
        ref, at = self.second_b("retry")
        version = self.card_row("personal", ref)["srs_card_version"]
        request = self.req(900001)
        first = self.rate("personal", ref, grade="good", at=at, request=request, version=version)
        state = self.everything()
        self.assertEqual(self.rate("personal", ref, grade="good", at=at, request=request, version=version), first)
        self.assertEqual(self.everything(), state)
        self.assertEqual(len(self.restarts("personal", ref)), 2)

    def test_failure_injection(self):
        ref, at = self.second_b("inject")
        state = self.everything()
        with mock.patch.object(reviews, "introduced_on", side_effect=RuntimeError("synthetic failure")):
            with self.assertRaises(RuntimeError):
                self.rate_at("personal", ref, at, "good")
        self.assertEqual(self.everything(), state)

    def test_concurrent_first_reviews(self):
        ref, at = self.second_b("race")
        version = self.card_row("personal", ref)["srs_card_version"]
        entered, release = threading.Event(), threading.Event()
        real = reviews.introduced_on

        def slow(*a, **k):
            result = real(*a, **k)
            if threading.current_thread().name == "first":
                entered.set()
                self.assertTrue(release.wait(15))
            return result

        def call(request):
            return lambda: vocab_repository.record_review(self.user, ref, "good", request_id=request,
                                                          expected_card_version=version, session_id="s1")

        with mock.patch.object(reviews, "now_utc", return_value=at), mock.patch.object(reviews, "introduced_on", slow), \
                race_support.LockProbe() as probe:
            first = race_support.start("first", call(self.req(900101)))
            self.assertTrue(entered.wait(15))
            second = race_support.start("second", call(self.req(900102)))
            self.assertTrue(probe.wait("waiting", "second"))
            time.sleep(0.3)
            self.assertNotIn(("acquired", "second"), probe.events)
            probe.mark("released", "first")
            release.set()
            race_support.finish(self, first)
            race_support.finish_error(self, second, SrsWriteError, "card_version_conflict")
        probe.assert_serialized(self, "first", "second")
        self.assertEqual(len(self.restarts("personal", ref)), 2)
        self.assertEqual(self.card_row("personal", ref)["evidence_from_log_id"], self.fsrs_logs("personal", ref)[-1]["id"])


if __name__ == "__main__":
    unittest.main()

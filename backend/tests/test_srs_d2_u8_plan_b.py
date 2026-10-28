"""Gate D-2 U8 plan B: a card that changed after its rollback and still carries an
evidence boundary is re-converted with no engine state; its first real FSRS review
starts a new evidence window (boundary CAS + restart record, one transaction).

Synthetic SQLite only (QueueCase sets a throwaway DATABASE_URL per test before the
app touches a database). Damage below edits synthetic rows; the app never does.

Run directly:      python tests/test_srs_d2_u8_plan_b.py
Or via discovery:   python -m unittest discover -s tests
"""

from __future__ import annotations

import json
import sys
import threading
import time
import unittest
from datetime import timedelta
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_srs_d2_rollback_reconvert import ENGINE, ReconvertCase  # noqa: E402
from test_srs_queue import NOW  # noqa: E402
import race_support  # noqa: E402

from app.database import get_connection  # noqa: E402
from app.repositories import vocab_repository  # noqa: E402
from app.schemas import VocabItemUpdate  # noqa: E402
from app.srs import migration, reviews  # noqa: E402
from app.srs.engine import CardKey, state_to_dict  # noqa: E402
from app.srs import engine  # noqa: E402
from app.srs.storage import SrsWriteError  # noqa: E402

DAY = timedelta(days=1)


class PlanBCase(ReconvertCase):
    def setUp(self):
        super().setUp()
        self.seen = []
        real = reviews.evaluate_completion

        def spy(state, events, *, evidence_complete):
            self.seen.append(([(e.reviewed_at, e.rating) for e in events], evidence_complete))
            return real(state, events, evidence_complete=evidence_complete)

        patch = mock.patch.object(reviews, "evaluate_completion", spy)
        patch.start()
        self.addCleanup(patch.stop)

    def everything(self):
        out = super().everything()
        with get_connection() as c:
            out["srs_evidence_restarts"] = [tuple(r) for r in c.execute("SELECT * FROM srs_evidence_restarts ORDER BY 1")]
        return out

    def restarts(self, kind=None, ref=None):
        with get_connection() as c:
            rows = [dict(r) for r in c.execute("SELECT * FROM srs_evidence_restarts ORDER BY id")]
        return [r for r in rows if kind is None or (r["card_kind"] == kind and r["card_ref"] == ref)]

    def old_window(self, kind, ref, deck=None, ratings=("good", "again", "good")):
        """Real FSRS reviews in the old window, including a success and an Again."""
        at = NOW
        for rating in ratings:
            self.rate_at(kind, ref, at, rating, deck=deck)
            at += 2 * DAY
        self.now = NOW
        return at

    def to_plan_b(self, kind, deck=None, name="b", ratings=("good", "again", "good")):
        """convert -> reviews -> rollback -> real legacy change -> plan-B re-conversion."""
        ref = self.converted(kind, f"{name}-{kind}", deck)
        at = self.old_window(kind, ref, deck, ratings)
        boundary = self.card_row(kind, ref)["evidence_from_log_id"]
        source = self.first_run(kind, ref)
        self.assertEqual(self.rollback(kind, ref, source=source)[0]["result"], "rolled_back")
        self.legacy_change(kind, ref, at + DAY, deck)
        run, candidate, result = self.reconvert(kind, ref)
        self.assertEqual(result["reconversion"], "state_none_restart", result)
        return ref, boundary, run, at + 3 * DAY

    def fsrs_count(self, kind, ref):
        return len(self.fsrs_logs(kind, ref))


# ---------------------------------------------------------------------------
class FlowTests(PlanBCase):
    def flow(self, kind, deck=None):
        ref = self.converted(kind, f"flow-{kind}", deck)
        at = self.old_window(kind, ref, deck)
        old_boundary = self.card_row(kind, ref)["evidence_from_log_id"]
        count = self.new_count()
        old_logs = self.log_print(kind, ref)
        self.rollback(kind, ref)
        self.legacy_change(kind, ref, at + DAY, deck)
        changed = self.card_row(kind, ref)
        legacy_logs = self.log_print(kind, ref)
        self.assertEqual(legacy_logs[0], old_logs[0] + 1)

        run, candidate, result = self.reconvert(kind, ref)
        self.assertEqual(result["reconversion"], "state_none_restart")
        row = self.card_row(kind, ref)
        self.assertEqual({k: row[k] for k in ENGINE}, {k: None for k in ENGINE})
        self.assertEqual(row["srs_effective_due_at"], changed["next_review_at"])  # existing schedule, not "today"
        self.assertEqual(row["evidence_from_log_id"], old_boundary)  # not replaced yet
        self.assertEqual(self.log_print(kind, ref), legacy_logs)  # no log
        self.assertEqual(self.new_count(), count)
        snap = self.apply_snapshot_of(run)
        restart = json.loads(snap["legacy_json"])["restart"]
        self.assertEqual(restart["previous_boundary"], old_boundary)
        self.assertEqual(restart["rollback_record_id"], [r for r in self.records(kind, ref) if r["mode"] == "rollback"][-1]["id"])
        self.assertEqual(self.restarts(), [])
        kept = {k: row[k] for k in ("history_intro_status", "history_intro_known_by", "first_completed_at",
                                    "completion_metric_version")}

        # First real review: library first review from no state, evidence = this review only.
        first_at = at + 5 * DAY
        response = self.rate_at(kind, ref, first_at, "easy", deck=deck)
        self.now = NOW
        expected = engine.review(self.key(kind, ref), None, "easy", first_at).after
        self.assertEqual(response["srs"]["state"], state_to_dict(expected))
        self.assertEqual(self.seen[-1], ([(first_at, "easy")], True))
        new_log = self.fsrs_logs(kind, ref)[-1]
        self.assertEqual((new_log["srs_before_json"], new_log["is_first_review"]), ("null", 1))
        after = self.card_row(kind, ref)
        self.assertEqual(after["evidence_from_log_id"], new_log["id"])
        rows = self.restarts(kind, ref)
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["previous_boundary"], rows[0]["new_boundary"], rows[0]["source_snapshot_id"],
                          rows[0]["card_version_before"]),
                         (old_boundary, new_log["id"], snap["id"], new_log["card_version_before"]))
        self.assertEqual({k: after[k] for k in kept}, kept)
        self.assertEqual(self.new_count(), count)  # not a new word again

        # Three follow-ups: only the new window's reviews are evidence.
        times = [first_at]
        for gap in (8, 30, 90):
            times.append(times[-1] + gap * DAY)
            self.rate_at(kind, ref, times[-1], "easy", deck=deck)
            self.now = NOW
            events, complete = self.seen[-1]
            self.assertTrue(complete)
            self.assertEqual(events, [(t, "easy") for t in times])  # no old success/Again, no legacy review
        self.assertEqual(self.card_row(kind, ref)["evidence_from_log_id"], new_log["id"])
        self.assertEqual(self.new_count(), count)
        self.assertEqual(len(self.restarts()), 1)

    def apply_snapshot_of(self, run):
        with get_connection() as c:
            return dict(c.execute("SELECT s.* FROM srs_migration_snapshots s JOIN srs_migration_runs r "
                                  "ON r.id = s.run_id WHERE r.run_key = ?", (run,)).fetchone())

    def test_personal(self):
        self.flow("personal")

    def test_subscribed(self):
        self.flow("lexeme", self.shared_deck("s"))

    def test_old_completion_is_kept_but_not_used(self):
        ref = self.converted("personal", "done")
        at = NOW
        for gap in (0, 8, 30, 90, 200):
            at += gap * DAY
            self.rate_at("personal", ref, at, "easy")
        self.now = NOW
        completed = self.card_row("personal", ref)["first_completed_at"]
        version = self.card_row("personal", ref)["completion_metric_version"]
        self.assertIsNotNone(completed)
        self.rollback("personal", ref)
        self.legacy_change("personal", ref, at + DAY)
        self.assertEqual(self.reconvert("personal", ref)[2]["reconversion"], "state_none_restart")
        first = self.rate_at("personal", ref, at + 3 * DAY, "again")
        self.assertEqual(self.seen[-1], ([(at + 3 * DAY, "again")], True))
        self.assertNotEqual(first["srs"]["completion_status"], "completed")  # new window decides
        row = self.card_row("personal", ref)
        self.assertEqual((row["first_completed_at"], row["completion_metric_version"]), (completed, version))

    def test_normal_restore_keeps_its_boundary(self):
        ref = self.converted("personal", "normal")
        self.old_window("personal", ref)
        boundary = self.card_row("personal", ref)["evidence_from_log_id"]
        self.rollback("personal", ref)
        _, candidate, result = self.reconvert("personal", ref)
        self.assertEqual((result["reconversion"], candidate.restart_json), ("restored", None))
        self.assertEqual(self.card_row("personal", ref)["evidence_from_log_id"], boundary)
        self.rate_at("personal", ref, NOW + 20 * DAY, "good")
        self.assertEqual(self.card_row("personal", ref)["evidence_from_log_id"], boundary)
        self.assertEqual(self.restarts(), [])

    def test_known_card_stays_paused(self):
        ref = self.converted("personal", "known")
        at = self.old_window("personal", ref)
        self.rollback("personal", ref)
        vocab_repository.update_vocab_item(self.user, ref, VocabItemUpdate(status="known"))  # the change
        self.assertEqual(self.reconvert("personal", ref)[2]["reconversion"], "state_none_restart")
        self.assertEqual(self.card_row("personal", ref)["srs_participation"], "paused")
        state = self.everything()
        with self.assertRaises(SrsWriteError) as caught:
            self.rate_at("personal", ref, at + 3 * DAY, "good")
        self.assertEqual(caught.exception.code, "card_paused")
        self.assertEqual(self.everything(), state)

    def test_queue_serves_the_plan_b_card(self):
        ref, _, _, at = self.to_plan_b("personal", name="queue")
        self.now = at
        self.assertIn(("personal", ref), self.keys(self.q()))


# ---------------------------------------------------------------------------
class PermissionTests(PlanBCase):
    def refused(self, kind, ref, at, deck=None, code="evidence_restart_not_permitted"):
        state = self.everything()
        with self.assertRaises(SrsWriteError) as caught:
            self.rate_at(kind, ref, at, "good", deck=deck)
        self.assertEqual(caught.exception.code, code)
        self.assertEqual(self.everything(), state)  # no log, boundary, record, receipt, version

    def snapshot_id(self, run):
        with get_connection() as c:
            return c.execute("SELECT s.id FROM srs_migration_snapshots s JOIN srs_migration_runs r ON r.id = s.run_id "
                             "WHERE r.run_key = ?", (run,)).fetchone()[0]

    def edit_restart(self, run, **changes):
        sid = self.snapshot_id(run)
        with get_connection() as c:
            payload = json.loads(c.execute("SELECT legacy_json FROM srs_migration_snapshots WHERE id = ?", (sid,)).fetchone()[0])
            if changes.pop("drop", False):
                payload.pop("restart")
            payload.get("restart", {}).update(changes)
            c.execute("UPDATE srs_migration_snapshots SET legacy_json = ? WHERE id = ?", (json.dumps(payload), sid))

    def test_failed_or_aborted_run(self):
        for status in ("failed", "aborted"):
            with self.subTest(status=status):
                ref, _, run, at = self.to_plan_b("personal", name=f"run-{status}")
                with get_connection() as c:
                    c.execute("UPDATE srs_migration_runs SET status = ? WHERE run_key = ?", (status, run))
                self.refused("personal", ref, at)

    def test_restart_info_missing_or_wrong(self):
        for name, change in (("drop", dict(drop=True)), ("boundary", dict(previous_boundary=999999)),
                             ("record", dict(rollback_record_id=999999))):
            with self.subTest(name=name):
                ref, _, run, at = self.to_plan_b("personal", name=f"info-{name}")
                self.edit_restart(run, **change)
                self.refused("personal", ref, at)

    def test_rollback_record_of_a_failed_run(self):
        ref, _, run, at = self.to_plan_b("personal", name="rb-failed")
        with get_connection() as c:
            c.execute("UPDATE srs_migration_runs SET status = 'failed' WHERE mode = 'rollback' AND run_key LIKE ?",
                      (f"rb-personal-{ref}-%",))
        self.refused("personal", ref, at)

    def test_version_written_since_the_reconversion(self):
        ref, _, _, at = self.to_plan_b("personal", name="bumped")
        with get_connection() as c:
            c.execute("UPDATE vocab_items SET srs_card_version = srs_card_version + 1 WHERE id = ?", (ref,))
        self.refused("personal", ref, at)

    def test_permission_already_used(self):
        ref, boundary, run, at = self.to_plan_b("personal", name="used")
        with get_connection() as c:
            c.execute("INSERT INTO srs_evidence_restarts (user_id, card_kind, card_ref, source_snapshot_id, "
                      "previous_boundary, new_boundary, card_version_before, created_at) VALUES (?, 'personal', ?, ?, ?, 1, 1, ?)",
                      (self.user, ref, self.snapshot_id(run), boundary, NOW.isoformat()))
        self.refused("personal", ref, at)

    def test_records_of_another_account(self):
        ref, _, run, at = self.to_plan_b("personal", name="acct")
        with get_connection() as c:
            c.execute("UPDATE srs_migration_snapshots SET user_id = ? WHERE id = ?", (self.other, self.snapshot_id(run)))
        self.refused("personal", ref, at)

    def test_state_none_with_old_boundary_alone_is_not_enough(self):
        # A state-none U5 card whose boundary is set without any plan-B re-conversion.
        ref = self.converted("personal", "forged")
        with get_connection() as c:
            c.execute("UPDATE vocab_items SET evidence_from_log_id = 12345 WHERE id = ?", (ref,))
        self.refused("personal", ref, NOW)

    def test_stale_request_from_before_the_reconversion(self):
        ref, _, _, at = self.to_plan_b("personal", name="stale")
        version = self.card_row("personal", ref)["srs_card_version"] - 1
        state = self.everything()
        with self.assertRaises(SrsWriteError) as caught:
            self.rate("personal", ref, grade="good", at=at, request=self.req(880001), version=version)
        self.assertEqual(caught.exception.code, "card_version_conflict")
        self.assertEqual(self.everything(), state)


# ---------------------------------------------------------------------------
class RepeatTests(PlanBCase):
    def test_rollback_again_before_the_first_review(self):
        ref, boundary, run1, at = self.to_plan_b("personal", name="again-before")
        old_permission = self.restart_snapshot(run1)
        self.assertEqual(self.rollback("personal", ref, source=run1)[0]["result"], "rolled_back")
        run2, candidate, result = self.reconvert("personal", ref)  # unchanged: restored to no state, NEW permission
        self.assertEqual(result["reconversion"], "restored")
        self.assertEqual(json.loads(candidate.restart_json)["previous_boundary"], boundary)
        self.rate_at("personal", ref, at, "good")
        rows = self.restarts("personal", ref)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source_snapshot_id"], self.restart_snapshot(run2))
        self.assertNotEqual(rows[0]["source_snapshot_id"], old_permission)

    def test_rollback_again_then_changed_before_the_first_review(self):
        ref, boundary, run1, at = self.to_plan_b("personal", name="again-changed")
        self.rollback("personal", ref, source=run1)
        self.legacy_change("personal", ref, at)
        run2, _, result = self.reconvert("personal", ref)
        self.assertEqual(result["reconversion"], "state_none_restart")
        self.rate_at("personal", ref, at + DAY, "good")
        self.assertEqual([r["source_snapshot_id"] for r in self.restarts("personal", ref)], [self.restart_snapshot(run2)])

    def test_cards_whose_fsrs_logs_a_full_replay_cannot_explain_now_take_plan_b(self):
        # Changed expectation (REPORT 22, approved 2026-10-13): a valid plan-B candidate no
        # longer needs its old history to replay. Formerly these two cards (a second plan B,
        # a U5 card with legacy logs) stopped at fsrs_snapshot_mismatch and stayed legacy.
        ref, boundary, run1, at = self.to_plan_b("personal", name="second")
        self.rate_at("personal", ref, at, "good")
        self.rate_at("personal", ref, at + 5 * DAY, "good")
        self.assertEqual(self.rollback("personal", ref, source=run1)[0]["result"], "rolled_back")
        self.legacy_change("personal", ref, at + 6 * DAY)
        old = self.personal("with-legacy-logs")
        for days in (70, 60):
            self.raw_log(old, NOW - timedelta(days=days))
        with get_connection() as c:
            c.execute("UPDATE vocab_items SET last_reviewed_at = ?, correct_count = 9, next_review_at = ? WHERE id = ?",
                      ((NOW - timedelta(days=60)).isoformat(), (NOW - timedelta(hours=1)).isoformat(), old))
        self.assertEqual(migration.apply_plan(self.plan(old), f"run-{old}", approved=True)[0]["result"], "applied")
        self.old_window("personal", old)
        self.rollback("personal", old)
        self.legacy_change("personal", old, NOW + 10 * DAY)
        for card in (ref, old):
            plan = migration.dry_run([self.key("personal", card)])
            self.assertEqual((plan[0].quality, plan[0].reconversion), ("incomplete", "state_none_restart"))
            self.assertNotIn("fsrs_snapshot_mismatch", plan[0].flags)

    def restart_snapshot(self, run):
        with get_connection() as c:
            return c.execute("SELECT s.id FROM srs_migration_snapshots s JOIN srs_migration_runs r ON r.id = s.run_id "
                             "WHERE r.run_key = ?", (run,)).fetchone()[0]


# ---------------------------------------------------------------------------
class AtomicityTests(PlanBCase):
    def test_retry_returns_the_first_response(self):
        for kind in ("personal", "lexeme"):
            with self.subTest(kind=kind):
                deck = self.shared_deck(f"s-{kind}") if kind == "lexeme" else None
                ref, _, _, at = self.to_plan_b(kind, deck, name=f"retry-{kind}")
                version = self.card_row(kind, ref)["srs_card_version"]
                request = self.req(890000 + (0 if kind == "personal" else 1))
                first = self.rate(kind, ref, grade="good", at=at, request=request, version=version, deck=deck)
                state = self.everything()
                again = self.rate(kind, ref, grade="good", at=at + DAY, request=request, version=version, deck=deck)
                self.assertEqual(again, first)
                self.assertEqual(self.everything(), state)
                self.assertEqual(len(self.restarts(kind, ref)), 1)
                with get_connection() as c:
                    self.assertEqual(c.execute("SELECT COUNT(*) FROM srs_review_receipts WHERE request_id = ?",
                                               (request,)).fetchone()[0], 1)

    def test_failure_after_the_boundary_move_writes_nothing(self):
        ref, boundary, _, at = self.to_plan_b("personal", name="inject")
        state = self.everything()
        with mock.patch.object(reviews, "introduced_on", side_effect=RuntimeError("synthetic failure")):
            with self.assertRaises(RuntimeError):
                self.rate_at("personal", ref, at, "good")
        self.assertEqual(self.everything(), state)  # log, boundary, restart record, card, receipt: none
        self.rate_at("personal", ref, at, "good")
        self.assertEqual(len(self.restarts("personal", ref)), 1)

    def test_failure_in_the_restart_record_writes_nothing(self):
        ref, boundary, _, at = self.to_plan_b("personal", name="inject2")
        state = self.everything()
        real = reviews._check_own_log

        def broken(*a, **k):
            raise SrsWriteError("evidence_boundary_mismatch")

        with mock.patch.object(reviews, "_check_own_log", broken):
            with self.assertRaises(SrsWriteError):
                self.rate_at("personal", ref, at, "good")
        self.assertEqual(self.everything(), state)
        self.assertIs(reviews._check_own_log, real)

    def test_concurrent_first_reviews(self):
        ref, boundary, _, at = self.to_plan_b("personal", name="race")
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
            first = race_support.start("first", call(self.req(891001)))
            self.assertTrue(entered.wait(15))
            second = race_support.start("second", call(self.req(891002)))
            self.assertTrue(probe.wait("waiting", "second"))
            time.sleep(0.3)
            self.assertNotIn(("acquired", "second"), probe.events)
            probe.mark("released", "first")
            release.set()
            race_support.finish(self, first)
            race_support.finish_error(self, second, SrsWriteError, "card_version_conflict")
        probe.assert_serialized(self, "first", "second")
        self.assertEqual(len(self.restarts("personal", ref)), 1)
        self.assertEqual(self.fsrs_logs("personal", ref)[-1]["request_id"], self.req(891001))
        with get_connection() as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM srs_review_receipts WHERE request_id IN (?, ?)",
                                       (self.req(891001), self.req(891002))).fetchone()[0], 1)
        self.assertEqual(self.card_row("personal", ref)["evidence_from_log_id"], self.fsrs_logs("personal", ref)[-1]["id"])


if __name__ == "__main__":
    unittest.main()

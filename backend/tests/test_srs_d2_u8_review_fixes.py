"""Gate D-2 U8 review fixes.

P1: after a restoring rollback + re-conversion, the card version jumps by two between
    two evidence-window reviews (rollback +1, re-conversion +1). The evidence check
    must accept exactly the jumps proven by this card's own completed rollback record
    and its restoring re-conversion snapshot -- nothing else.
P2: rollback must order the later reviews by their real UTC instant, so the same
    instants written with other offsets give the same rollback.

Synthetic SQLite only (QueueCase sets a throwaway DATABASE_URL per test before the
app touches a database). Damage below edits synthetic rows; the app never does.

Run directly:      python tests/test_srs_d2_u8_review_fixes.py
Or via discovery:   python -m unittest discover -s tests
"""

from __future__ import annotations

import json
import sys
import unittest
from datetime import timedelta, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_srs_d2_rollback_reconvert import ReconvertCase  # noqa: E402
from test_srs_queue import NOW, iso  # noqa: E402

from app.database import get_connection  # noqa: E402
from app.srs import migration, reviews  # noqa: E402
from app.srs.engine import CardKey  # noqa: E402
from app.srs.storage import SrsWriteError  # noqa: E402

DAY = timedelta(days=1)


class EvidenceCase(ReconvertCase):
    def setUp(self):
        super().setUp()
        self.captured = []
        real = reviews.evaluate_completion

        def spy(state, events, *, evidence_complete):
            self.captured.append(evidence_complete)
            return real(state, events, evidence_complete=evidence_complete)

        patch = mock.patch.object(reviews, "evaluate_completion", spy)
        patch.start()
        self.addCleanup(patch.stop)
        self.day = 0

    def review(self, kind, ref, deck=None, rating="good"):
        self.day += 3
        self.rate_at(kind, ref, NOW + self.day * DAY, rating, deck=deck)
        self.now = NOW
        return self.captured[-1]

    def versions(self, kind, ref):
        return [log["card_version_before"] for log in self.fsrs_logs(kind, ref)]

    def cycle(self, kind, ref, source):
        self.assertEqual(self.rollback(kind, ref, source=source)[0]["result"], "rolled_back")
        run, _, result = self.reconvert(kind, ref)
        self.assertEqual(result["reconversion"], "restored")
        return run

    def restored_card(self, kind="personal", deck=None, name="p1"):
        """convert -> 2 reviews -> rollback -> restoring re-conversion. Returns (ref, run)."""
        ref = self.converted(kind, name, deck)
        self.assertEqual([self.review(kind, ref, deck) for _ in range(2)], [True, True])
        return ref, self.cycle(kind, ref, self.first_run(kind, ref))

    def preserved(self, kind, ref):
        row = self.card_row(kind, ref)
        return {k: row[k] for k in ("evidence_from_log_id", "history_intro_status", "history_intro_known_by",
                                    "first_completed_at", "completion_metric_version")}

    def apply_snapshot(self, run):
        with get_connection() as c:
            return dict(c.execute("SELECT s.* FROM srs_migration_snapshots s JOIN srs_migration_runs r "
                                  "ON r.id = s.run_id WHERE r.run_key = ?", (run,)).fetchone())

    def rollback_record(self, kind, ref):
        return [r for r in self.records(kind, ref) if r["mode"] == "rollback"][-1]


# ---------------------------------------------------------------------------
class P1RestoredWindowTests(EvidenceCase):
    def continuous(self, kind, deck=None):
        ref, _ = self.restored_card(kind, deck, f"cont-{kind}")
        kept, count = self.preserved(kind, ref), self.new_count()
        results = [self.review(kind, ref, deck) for _ in range(3)]
        self.assertEqual(self.versions(kind, ref), [1, 2, 5, 6, 7])
        self.assertEqual(results, [True, True, True])  # every later review keeps valid evidence
        after = self.preserved(kind, ref)
        self.assertEqual({k: after[k] for k in ("evidence_from_log_id", "history_intro_status", "history_intro_known_by")},
                         {k: kept[k] for k in ("evidence_from_log_id", "history_intro_status", "history_intro_known_by")})
        self.assertEqual(self.new_count(), count)

    def test_personal_three_reviews_after_restore(self):
        self.continuous("personal")

    def test_subscribed_three_reviews_after_restore(self):
        self.continuous("lexeme", self.shared_deck("s"))

    def test_two_cycles_with_reviews_between(self):
        for kind in ("personal", "lexeme"):
            with self.subTest(kind=kind):
                deck = self.shared_deck(f"s-{kind}") if kind == "lexeme" else None
                ref, run = self.restored_card(kind, deck, f"two-{kind}")
                self.assertTrue(self.review(kind, ref, deck))
                self.cycle(kind, ref, run)
                self.assertEqual([self.review(kind, ref, deck) for _ in range(2)], [True, True])
                self.assertEqual(self.versions(kind, ref), [1, 2, 5, 8, 9])
                self.now = NOW

    def test_two_cycles_back_to_back(self):
        ref, run = self.restored_card(name="back-to-back")
        self.cycle("personal", ref, run)
        self.assertEqual([self.review("personal", ref) for _ in range(3)], [True, True, True])
        self.assertEqual(self.versions("personal", ref), [1, 2, 7, 8, 9])

    def test_completion_still_reachable_after_restore(self):
        ref, _ = self.restored_card(name="complete")
        for _ in range(6):
            self.review("personal", ref, rating="easy")
        self.assertEqual(self.captured[-6:], [True] * 6)


# ---------------------------------------------------------------------------
class P1UnprovenGapTests(EvidenceCase):
    def assert_gap_not_evidence(self, kind, ref, deck=None):
        self.review(kind, ref, deck)  # first review after restore: window has no gap yet
        state = self.preserved(kind, ref)
        self.assertEqual([self.review(kind, ref, deck) for _ in range(2)], [False, False])
        self.assertEqual(self.preserved(kind, ref)["first_completed_at"], state["first_completed_at"])
        self.assertEqual(self.preserved(kind, ref)["evidence_from_log_id"], state["evidence_from_log_id"])

    def test_bare_version_bump_without_records(self):
        ref = self.converted("personal", "bump")
        self.review("personal", ref)
        self.review("personal", ref)
        with get_connection() as c:
            c.execute("UPDATE vocab_items SET srs_card_version = srs_card_version + 2 WHERE id = ?", (ref,))
        self.assert_gap_not_evidence("personal", ref)

    def test_missing_reconversion_snapshot(self):
        ref, run = self.restored_card(name="no-apply")
        with get_connection() as c:
            c.execute("DELETE FROM srs_migration_snapshots WHERE id = ?", (self.apply_snapshot(run)["id"],))
        self.assert_gap_not_evidence("personal", ref)

    def test_rollback_run_not_completed(self):
        for status in ("started", "failed", "aborted"):
            with self.subTest(status=status):
                ref, _ = self.restored_card(name=f"rb-{status}")
                with get_connection() as c:
                    c.execute("UPDATE srs_migration_runs SET status = ? WHERE id = ?",
                              (status, self.rollback_record("personal", ref)["run_id"]))
                self.assert_gap_not_evidence("personal", ref)
                self.day = 0

    def test_failed_reconversion_run(self):
        ref, run = self.restored_card(name="apply-failed")
        with get_connection() as c:
            c.execute("UPDATE srs_migration_runs SET status = 'failed' WHERE run_key = ?", (run,))
        self.assert_gap_not_evidence("personal", ref)

    def test_tampered_rollback_state(self):
        ref, _ = self.restored_card(name="tampered")
        record = self.rollback_record("personal", ref)
        restore = json.loads(record["srs_before_json"])
        restore["srs_stability"] += 1.0
        with get_connection() as c:
            c.execute("UPDATE srs_migration_snapshots SET srs_before_json = ? WHERE id = ?",
                      (json.dumps(restore), record["id"]))
        self.assert_gap_not_evidence("personal", ref)

    def test_tampered_reconversion_values(self):
        ref, run = self.restored_card(name="tampered-apply")
        snap = self.apply_snapshot(run)
        values = json.loads(snap["srs_after_json"])
        values["srs_difficulty"] += 0.5
        with get_connection() as c:
            c.execute("UPDATE srs_migration_snapshots SET srs_after_json = ? WHERE id = ?", (json.dumps(values), snap["id"]))
        self.assert_gap_not_evidence("personal", ref)

    def test_records_of_another_card(self):
        ref, _ = self.restored_card(name="mine")
        other, _ = self.restored_card(name="other")
        with get_connection() as c:  # move this card's records onto the other card's id
            c.execute("UPDATE srs_migration_snapshots SET card_ref = -1 WHERE card_ref = ? AND card_kind = 'personal' "
                      "AND run_id IN (SELECT id FROM srs_migration_runs WHERE run_key LIKE 'rb-%' OR run_key LIKE 're-%')",
                      (ref,))
        self.assert_gap_not_evidence("personal", ref)
        self.assertTrue(self.review("personal", other))  # the other card's own records still prove its jump

    def test_records_of_another_account(self):
        ref, _ = self.restored_card(name="acct")
        with get_connection() as c:
            c.execute("UPDATE srs_migration_snapshots SET user_id = ? WHERE card_ref = ? AND card_kind = 'personal' "
                      "AND run_id IN (SELECT id FROM srs_migration_runs WHERE run_key LIKE 'rb-%' OR run_key LIKE 're-%')",
                      (self.other, ref))
        self.assert_gap_not_evidence("personal", ref)

    def test_record_baseline_not_at_the_previous_log(self):
        ref, _ = self.restored_card(name="baseline")
        record = self.rollback_record("personal", ref)
        payload = json.loads(record["legacy_json"])
        payload["baseline"]["last_log_id"] += 1000
        with get_connection() as c:
            c.execute("UPDATE srs_migration_snapshots SET legacy_json = ? WHERE id = ?", (json.dumps(payload), record["id"]))
        self.assert_gap_not_evidence("personal", ref)

    def test_extra_unexplained_bump_after_a_proven_cycle(self):
        ref, _ = self.restored_card(name="extra")
        with get_connection() as c:
            c.execute("UPDATE vocab_items SET srs_card_version = srs_card_version + 1 WHERE id = ?", (ref,))
        self.assert_gap_not_evidence("personal", ref)

    def test_proof_does_not_relax_other_checks(self):
        ref, _ = self.restored_card(name="other-checks")
        self.review("personal", ref)
        log = self.fsrs_logs("personal", ref)[-1]
        after = json.loads(log["srs_after_json"])
        after["stability"] += 1.0
        with get_connection() as c:
            c.execute("UPDATE review_logs SET srs_after_json = ? WHERE id = ?", (json.dumps(after), log["id"]))
        self.assertFalse(self.review("personal", ref))


# ---------------------------------------------------------------------------
class P2OffsetOrderTests(ReconvertCase):
    """Two cards reviewed at the same instants; one card's logs are re-spelled."""

    def twins(self, kind="personal", deck=None):
        self._twin = getattr(self, "_twin", 0) + 1
        refs = [self.converted(kind, f"{kind}-{name}-{self._twin}", deck, order=2 * self._twin + i)
                for i, name in enumerate(("plain", "spelled"))]
        for ref in refs:
            self.rate_at(kind, ref, NOW, "good", deck=deck)
            self.rate_at(kind, ref, NOW + timedelta(hours=1), "hard", deck=deck)
        self.now = NOW
        return refs

    def respell(self, kind, ref, offsets):
        column = self.log_table(kind)[2]
        for log, hours in zip(self.fsrs_logs(kind, ref), offsets):
            at = reviews.goals.read_utc(log[column])
            text = at.isoformat().replace("+00:00", "Z") if hours == "Z" else at.astimezone(
                timezone(timedelta(hours=hours))).isoformat()
            self.tamper(kind, log["id"], **{column: text})

    def outcome(self, kind, ref):
        row = self.card_row(kind, ref)
        return {k: row[k] for k in ("review_level", "next_review_at", "srs_engine")}

    def check(self, kind, offsets, deck=None):
        plain, spelled = self.twins(kind, deck)
        self.respell(kind, spelled, offsets)
        raw = [log[self.log_table(kind)[2]] for log in self.fsrs_logs(kind, spelled)]
        for ref in (plain, spelled):
            self.assertEqual(self.rollback(kind, ref)[0]["result"], "rolled_back")
        self.assertEqual(self.outcome(kind, spelled), self.outcome(kind, plain))
        self.assertEqual([log[self.log_table(kind)[2]] for log in self.fsrs_logs(kind, spelled)], raw)  # not rewritten
        return plain, spelled

    def test_string_order_reversed_personal(self):
        self.check("personal", (9, -10))  # first review written later as text than the second

    def test_string_order_reversed_subscribed(self):
        self.check("lexeme", (9, -10), self.shared_deck("s"))

    def test_spellings_give_the_same_rollback(self):
        for offsets in (("Z", "Z"), (5.5, -3), (-11, 14), ("Z", -8)):
            with self.subTest(offsets=offsets):
                plain, spelled = self.check("personal", offsets)
                # Restoring re-conversion works on the re-spelled card too.
                self.assertEqual(self.reconvert("personal", spelled)[2]["reconversion"], "restored")

    def test_same_instant_logs_are_ordered_by_version(self):
        plain, spelled = self.twins()
        column = "reviewed_at"
        logs = self.fsrs_logs("personal", spelled)
        at = reviews.goals.read_utc(logs[0][column])
        self.tamper("personal", logs[0]["id"], reviewed_at=at.astimezone(timezone(timedelta(hours=9))).isoformat())
        self.tamper("personal", logs[1]["id"], reviewed_at=at.isoformat())  # same instant, other spelling
        self.assertEqual(self.rollback("personal", spelled)[0]["result"], "rolled_back")

    def test_real_time_inversion_is_not_normalised(self):
        plain, spelled = self.twins()
        logs = self.fsrs_logs("personal", spelled)
        self.tamper("personal", logs[1]["id"], reviewed_at=iso(NOW - timedelta(hours=1)))  # really earlier
        state = self.everything()
        with self.assertRaises(SrsWriteError) as caught:
            self.rollback("personal", spelled)
        self.assertEqual(caught.exception.code, "rollback_history_mismatch")
        self.assertEqual(self.everything(), state)

    def test_version_mismatch_is_refused(self):
        plain, spelled = self.twins()
        logs = self.fsrs_logs("personal", spelled)
        with get_connection() as c:
            c.execute("UPDATE review_logs SET card_version_before = 7 WHERE id = ?", (logs[1]["id"],))
        state = self.everything()
        with self.assertRaises(SrsWriteError) as caught:
            self.rollback("personal", spelled)
        self.assertEqual(caught.exception.code, "rollback_history_mismatch")
        self.assertEqual(self.everything(), state)

    def test_unreadable_time_still_refuses_everything(self):
        plain, spelled = self.twins()
        self.tamper("personal", self.fsrs_logs("personal", spelled)[0]["id"], reviewed_at="2026-10-12T03:00:00")
        state = self.everything()
        with self.assertRaises(migration.RollbackHistoryUnreadable):
            migration.rollback_plan(self.first_run("personal", spelled), "rb-unreadable", user_id=self.user,
                                    approved=True)
        self.assertEqual(self.everything(), state)


if __name__ == "__main__":
    unittest.main()

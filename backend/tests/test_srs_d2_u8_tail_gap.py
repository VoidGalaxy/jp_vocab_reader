"""Gate D-2 U8 remaining P1: a card-version gap AFTER the last stored log.

The evidence check used to verify the gaps between window logs only. A gap between
the last log and the card version this review is made against (a bare bump, or a
restore whose re-conversion run later failed) went unchecked, so the FIRST review
after it could record a completion. The same restoration proof now covers that tail.

Synthetic SQLite only (QueueCase sets a throwaway DATABASE_URL per test before the
app touches a database). Damage below edits synthetic rows; the app never does.

Run directly:      python tests/test_srs_d2_u8_tail_gap.py
Or via discovery:   python -m unittest discover -s tests
"""

from __future__ import annotations

import sys
import unittest
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_srs_d2_u8_review_fixes import EvidenceCase  # noqa: E402
from test_srs_queue import NOW  # noqa: E402

from app.database import get_connection  # noqa: E402

DAY = timedelta(days=1)


class TailGapCase(EvidenceCase):
    def easy(self, kind, ref, at, deck=None, request=None):
        result = self.rate_at(kind, ref, at, "easy", deck=deck, request=request)
        self.now = NOW
        return result, self.captured[-1]

    def bump(self, kind, ref, by=2):
        table, where = (("vocab_items", "id = ?") if kind == "personal"
                        else ("user_word_progress", "user_id = ? AND lexeme_id = ?"))
        params = (ref,) if kind == "personal" else (self.user, ref)
        with get_connection() as c:
            c.execute(f"UPDATE {table} SET srs_card_version = srs_card_version + ? WHERE {where}", (by, *params))

    def fail_run(self, run):
        with get_connection() as c:
            c.execute("UPDATE srs_migration_runs SET status = 'failed' WHERE run_key = ?", (run,))

    def kept(self, kind, ref):
        row = self.card_row(kind, ref)
        return {k: row[k] for k in ("evidence_from_log_id", "history_intro_status", "history_intro_known_by",
                                    "first_completed_at", "completion_metric_version")}

    def assert_no_false_completion(self, kind, ref, start, deck=None):
        """First, second and third follow-up Easy: evidence incomplete, no new first completion."""
        before, count = self.kept(kind, ref), self.new_count()
        self.assertIsNone(before["first_completed_at"])
        for n, gap in enumerate((8, 30, 90)):
            start += gap * DAY
            result, complete = self.easy(kind, ref, start, deck)
            self.assertFalse(complete, f"follow-up {n + 1}")
            self.assertNotEqual(result["completed"], True, f"follow-up {n + 1}")
            self.assertNotEqual(result["srs"]["completion_status"], "completed")
            self.assertIn(result["srs"]["completion_status"], ("not_completed", "unknown"))
            self.assertEqual(self.kept(kind, ref), before)  # no first completion, boundary and marks kept
        self.assertEqual(self.new_count(), count)


# ---------------------------------------------------------------------------
class CaseATests(TailGapCase):
    """U5 conversion -> Easy -> bare version +2 -> Easy 8 days later."""

    def run_case(self, kind, deck=None):
        ref = self.converted(kind, f"a-{kind}", deck)
        self.assertTrue(self.easy(kind, ref, NOW, deck)[1])
        self.bump(kind, ref)
        self.assert_no_false_completion(kind, ref, NOW, deck)

    def test_personal(self):
        self.run_case("personal")

    def test_subscribed(self):
        self.run_case("lexeme", self.shared_deck("s"))

    def test_odd_bump(self):
        ref = self.converted("personal", "odd")
        self.easy("personal", ref, NOW)
        self.bump("personal", ref, by=1)
        self.assert_no_false_completion("personal", ref, NOW)


class CaseBTests(TailGapCase):
    """convert -> 2 reviews -> rollback -> restoring re-conversion -> run marked failed -> Easy."""

    def run_case(self, kind, deck=None):
        ref, run = self.restored_card(kind, deck, f"b-{kind}")
        self.fail_run(run)
        self.assert_no_false_completion(kind, ref, NOW + self.day * DAY, deck)

    def test_personal(self):
        self.run_case("personal")

    def test_subscribed(self):
        self.run_case("lexeme", self.shared_deck("s"))

    def test_other_damage_after_the_last_log(self):
        for name, damage in (("rollback-failed", "rollback"), ("no-apply", "delete"), ("other-account", "account")):
            with self.subTest(name=name):
                ref, run = self.restored_card("personal", None, name)
                with get_connection() as c:
                    if damage == "rollback":
                        c.execute("UPDATE srs_migration_runs SET status = 'failed' WHERE id = ?",
                                  (self.rollback_record("personal", ref)["run_id"],))
                    elif damage == "delete":
                        c.execute("DELETE FROM srs_migration_snapshots WHERE id = ?", (self.apply_snapshot(run)["id"],))
                    else:
                        c.execute("UPDATE srs_migration_snapshots SET user_id = ? WHERE card_ref = ? AND card_kind = "
                                  "'personal' AND run_id IN (SELECT id FROM srs_migration_runs WHERE run_key LIKE 'rb-%' "
                                  "OR run_key LIKE 're-%')", (self.other, ref))
                self.assert_no_false_completion("personal", ref, NOW + self.day * DAY)
                self.day = 0


# ---------------------------------------------------------------------------
class ValidTailTests(TailGapCase):
    def test_normal_restore_first_follow_up_is_complete(self):
        for kind in ("personal", "lexeme"):
            with self.subTest(kind=kind):
                deck = self.shared_deck(f"s-{kind}") if kind == "lexeme" else None
                ref, _ = self.restored_card(kind, deck, f"ok-{kind}")
                self.assertEqual(self.easy(kind, ref, NOW + (self.day + 8) * DAY, deck)[1], True)
                self.day = 0

    def test_two_back_to_back_restores_first_follow_up_is_complete(self):
        ref, run = self.restored_card(name="twice")
        self.cycle("personal", ref, run)
        self.assertTrue(self.easy("personal", ref, NOW + (self.day + 8) * DAY)[1])
        self.assertEqual(self.versions("personal", ref), [1, 2, 7])

    def test_no_gap(self):
        ref = self.converted("personal", "no-gap")
        self.assertTrue(self.easy("personal", ref, NOW)[1])
        self.assertTrue(self.easy("personal", ref, NOW + 8 * DAY)[1])

    def test_first_review_with_no_log(self):
        ref = self.converted("personal", "first")  # U7 state-none first review: no last log to assume
        result, complete = self.easy("personal", ref, NOW)
        self.assertTrue(complete)
        self.assertIsNotNone(self.card_row("personal", ref)["evidence_from_log_id"])

    def test_retry_of_an_incomplete_review(self):
        ref = self.converted("personal", "retry")
        self.easy("personal", ref, NOW)
        self.bump("personal", ref)
        request = self.req(777001)
        first, complete = self.easy("personal", ref, NOW + 8 * DAY, request=request)
        self.assertFalse(complete)
        with get_connection() as c:
            logs = c.execute("SELECT COUNT(*) FROM review_logs WHERE vocab_item_id = ?", (ref,)).fetchone()[0]
            receipts = c.execute("SELECT COUNT(*) FROM srs_review_receipts WHERE request_id = ?", (request,)).fetchone()[0]
        version = self.card_row("personal", ref)["srs_card_version"] - 1
        again = self.rate("personal", ref, grade="easy", at=NOW + 8 * DAY, request=request, version=version)
        self.assertEqual(again, first)
        with get_connection() as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM review_logs WHERE vocab_item_id = ?", (ref,)).fetchone()[0],
                             logs)
            self.assertEqual(c.execute("SELECT COUNT(*) FROM srs_review_receipts WHERE request_id = ?",
                                       (request,)).fetchone()[0], receipts)
        self.assertEqual(receipts, 1)

    def test_existing_first_completion_is_kept(self):
        ref = self.converted("personal", "kept")
        at = NOW
        for gap in (0, 8, 30, 90, 200):
            at += gap * DAY
            self.easy("personal", ref, at)
        completed = self.card_row("personal", ref)["first_completed_at"]
        self.assertIsNotNone(completed)
        self.bump("personal", ref)
        result, complete = self.easy("personal", ref, at + 300 * DAY)
        self.assertFalse(complete)
        self.assertEqual(self.card_row("personal", ref)["first_completed_at"], completed)  # never erased


if __name__ == "__main__":
    unittest.main()

"""Gate D-2 U4 follow-up (E1~E7): minimal past-learning evidence kept after a card
is deleted (contract: docs/plans/srs-improvement/gate-d2/U4_DELETION_EVIDENCE.md).

Synthetic SQLite only. U5~U7 do not exist: "first FSRS log today" is inserted as
synthetic state (marked below). This is not a full conversion-flow test.

Run directly:      python tests/test_srs_d2_intro_deletion.py
Or via discovery:   python -m unittest discover -s tests
"""

from __future__ import annotations

import sys
import threading
import time
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_srs_d2_intro import IntroCase, seoul_noon  # noqa: E402
from test_srs_queue import NOW, iso  # noqa: E402
import race_support  # noqa: E402

from app.database import get_connection, init_db  # noqa: E402
from app.repositories.deck_repository import create_deck, delete_deck_with_items  # noqa: E402
from app.repositories.vocab_repository import delete_vocab_item  # noqa: E402
from app.schemas import DeckCreate  # noqa: E402
from app.srs import history_intro, identity, migration, reviews, storage  # noqa: E402
from app.srs.engine import CardKey, SrsPhase  # noqa: E402

K = date(2026, 10, 5)
TODAY = date(2026, 10, 9)


class DeletionCase(IntroCase):
    def setUp(self):
        super().setUp()
        self.box = create_deck(self.user, DeckCreate(name="box"))[0]["id"]

    def marked(self, kind="before_tracking", name="past", deck=None):
        card = self.personal(name, deck=deck or self.box)
        with get_connection() as c:
            if kind == "before_tracking":
                c.execute("UPDATE vocab_items SET last_reviewed_at = ?, correct_count = 2 WHERE id = ?",
                          (iso(seoul_noon(K)), card))
            else:
                c.execute("UPDATE vocab_items SET last_reviewed_at = NULL, correct_count = 2 WHERE id = ?", (card,))
        self.apply(card, run=f"run-{card}")
        return card

    def remove(self, card, how):
        if how == "word":
            self.assertTrue(delete_vocab_item(self.user, card))
        else:
            with get_connection() as c:
                deck = c.execute("SELECT deck_id FROM vocab_items WHERE id = ?", (card,)).fetchone()[0]
            self.assertTrue(delete_deck_with_items(self.user, deck))

    def day(self, d, scope=None):
        r = self.count(seoul_noon(d), scope)
        return r.status, r.count, r.at_least

    def goal(self):
        g = self.q()["new_goal"]
        return g["introduced_today"], g["introduced_today_status"], g["account_remaining"], g["new_blocked_reason"]

    def ledger(self):
        with get_connection() as c:
            return [dict(r) for r in c.execute("SELECT * FROM srs_card_deletions ORDER BY id").fetchall()]


# ---------------------------------------------------------------------------
class EvidenceAfterDeletionTests(DeletionCase):
    def test_t1_past_learning_plus_first_fsrs_log_then_delete(self):
        for how in ("word", "deck"):
            with self.subTest(how=how):
                deck = create_deck(self.user, DeckCreate(name=f"t1-{how}"))[0]["id"]
                card = self.marked(name=f"t1-{how}", deck=deck)
                self.fsrs_log(card, NOW - timedelta(minutes=30))  # synthetic stand-in for a U7 first review
                before = (self.day(TODAY), self.day(K), self.day(K - timedelta(days=3)), self.goal())
                self.assertEqual(before[0], ("exact", 0, 0))
                self.assertEqual(before[3][2], 20)
                logs = self.logs()
                self.remove(card, how)
                after = (self.day(TODAY), self.day(K), self.day(K - timedelta(days=3)), self.goal())
                self.assertEqual(after, before)  # today 0 / remaining 20, past dates still unknown
                self.assertEqual(self.logs(), logs)  # raw log kept, unchanged
                with get_connection() as c:
                    c.execute("DELETE FROM review_logs")  # isolate the next subtest
                    c.execute("DELETE FROM srs_card_deletions")

    def test_t2_unknown_card_deletion_keeps_uncertainty_and_pause(self):
        for how in ("word", "deck"):
            with self.subTest(how=how):
                deck = create_deck(self.user, DeckCreate(name=f"t2-{how}"))[0]["id"]
                card = self.marked("unknown", name=f"t2-{how}", deck=deck)
                before = self.goal()
                self.assertEqual(before, (None, "unknown", None, "review_time_unreadable"))  # E7: reason value kept
                self.remove(card, how)
                self.assertEqual(self.goal(), before)  # E5: deleting does not release the pause
                for d in (TODAY, K, K - timedelta(days=30)):
                    self.assertEqual(self.day(d)[0], "unknown")
                with get_connection() as c:
                    c.execute("DELETE FROM srs_card_deletions")

    def test_t3_real_new_card_keeps_its_first_study_after_deletion(self):
        fresh = self.personal("fresh", deck=self.box)
        self.fsrs("personal", fresh)
        self.rate("personal", fresh, request="00000000-0000-4000-8000-0000000003a1")  # real FSRS first review
        self.assertEqual(self.day(TODAY), ("exact", 1, 1))
        self.remove(fresh, "word")
        self.assertEqual(self.day(TODAY), ("exact", 1, 1))
        self.assertEqual(self.goal()[2], 19)
        self.assertIsNone(self.ledger()[0]["history_intro_status"])

    def test_t4_duplicate_deletes_and_several_ledger_rows_count_once_without_narrowing(self):
        card = self.marked()
        self.assertTrue(delete_vocab_item(self.user, card))
        self.assertFalse(delete_vocab_item(self.user, card))  # second delete: nothing, no ledger row
        self.assertEqual(len(self.ledger()), 1)
        self.assertFalse(delete_deck_with_items(self.user, self.box) is None)
        self.assertFalse(delete_deck_with_items(self.user, self.box))  # deck already gone
        # Several rows for one id (pre-rebuild reuse): one card, most uncertain value.
        with get_connection() as c:
            for status, known in (("before_tracking", "2026-10-07"), ("logged", None)):
                c.execute("INSERT INTO srs_card_deletions (card_kind, user_id, card_ref, deleted_at, "
                          "history_intro_status, history_intro_known_by) VALUES ('personal', ?, ?, ?, ?, ?)",
                          (self.user, card, iso(NOW), status, known))
            evidence = history_intro.intro_evidence(c, self.user)
        self.assertEqual(evidence[("personal", card)], ("before_tracking", date(2026, 10, 7)))  # later bound wins
        self.assertEqual(self.count(seoul_noon(date(2026, 10, 6))).history_unknown_cards, 1)  # one card, not three
        self.assertEqual(self.day(date(2026, 10, 8))[0], "exact")
        with get_connection() as c:
            c.execute("INSERT INTO srs_card_deletions (card_kind, user_id, card_ref, deleted_at, history_intro_status) "
                      "VALUES ('personal', ?, ?, ?, 'unknown')", (self.user, card, iso(NOW)))
        self.assertEqual(self.day(date(2026, 10, 8))[0], "unknown")  # unknown wins, never narrowed

    def test_t5_failures_roll_back_card_and_ledger(self):
        card = self.marked()
        with get_connection() as c:
            c.execute("ALTER TABLE srs_card_deletions RENAME COLUMN history_intro_known_by TO broken_col")
        with self.assertRaises(Exception):
            delete_vocab_item(self.user, card)
        with self.assertRaises(Exception):
            delete_deck_with_items(self.user, self.box)
        with get_connection() as c:
            c.execute("ALTER TABLE srs_card_deletions RENAME COLUMN broken_col TO history_intro_known_by")
            c.execute("CREATE TRIGGER trg_block BEFORE DELETE ON vocab_items BEGIN SELECT RAISE(ABORT, 'x'); END")
        with self.assertRaises(Exception):
            delete_vocab_item(self.user, card)
        with self.assertRaises(Exception):
            delete_deck_with_items(self.user, self.box)
        self.assertEqual(self.ledger(), [])
        self.assertEqual(self.mark(card), ("before_tracking", "2026-10-05"))
        with get_connection() as c:
            self.assertIsNotNone(c.execute("SELECT 1 FROM decks WHERE id = ?", (self.box,)).fetchone())

    def test_t7_accounts_and_scopes_are_separate(self):
        card = self.marked()
        mate = self.personal("mate", deck=self.box)
        self.remove(card, "word")
        with get_connection() as c:
            from app.srs import goals
            theirs = goals.introduction_count(c, self.other, seoul_noon(K))
        self.assertEqual((theirs.status, theirs.count), ("exact", 0))
        # Account-wide keeps the deleted card's evidence; the deck scope holds current cards only.
        self.assertEqual(self.day(K)[0], "unknown")
        self.assertEqual(self.day(K, scope={("personal", mate)})[0], "exact")
        q = self.q(scope="personal_deck", deck_id=self.box)["new_goal"]
        self.assertEqual(q["introduced_today_in_scope_status"], "exact")
        # Subscribed marks still come from the live progress row (no deletion path exists).
        shared = self.shared_deck("s")
        lexeme = self.lexeme("w", shared, 0)
        with get_connection() as c:
            c.execute("UPDATE user_word_progress SET history_intro_status = 'unknown' WHERE lexeme_id = ? AND user_id = ?",
                      (lexeme, self.user))
            self.assertEqual(history_intro.intro_evidence(c, self.user)[("lexeme", lexeme)], ("unknown", None))

    def test_t8_unreadable_time_and_identity_rules_still_come_first(self):
        card = self.marked()
        with get_connection() as c:
            c.execute("INSERT INTO review_logs (user_id, vocab_item_id, rating, reviewed_at, previous_review_level, "
                      "next_review_level, next_review_at) VALUES (?, ?, 'good', 'garbage', 0, 1, ?)",
                      (self.user, card, iso(NOW)))
        self.remove(card, "word")
        result = self.count(seoul_noon(K + timedelta(days=2)))
        self.assertEqual((result.status, result.unreadable_cards), ("unknown", 1))
        with get_connection() as c:
            c.execute("DELETE FROM review_logs WHERE reviewed_at = 'garbage'")
        other = self.marked(name="flagged")
        self.fsrs_log(other, seoul_noon(K + timedelta(days=2)))
        with get_connection() as c:
            identity.flag_identity_unknown(c, [identity.IdentityFinding(self.user, other, ["test"])])
        self.remove(other, "word")
        on_log = self.count(seoul_noon(K + timedelta(days=2)))
        self.assertEqual(on_log.identity_unknown_cards, 1)
        self.assertEqual(self.day(K + timedelta(days=3))[0], "exact")

    def test_t9_synthetic_account_deletion_leaves_no_evidence(self):
        card = self.marked()
        self.remove(card, "word")
        with get_connection() as c:
            identity.flag_identity_unknown(c, [identity.IdentityFinding(self.user, card, ["test"])])
        self.assertEqual(len(self.ledger()), 1)
        # No account-deletion API exists (D-P5 not implemented). Synthetic procedure:
        # remove the account's rows, then the user row; the ledger and flags go by FK CASCADE.
        with get_connection() as c:
            for table in ("review_logs", "lexeme_review_logs", "vocab_items", "custom_terms", "decks",
                          "user_word_progress", "user_deck_subscriptions", "srs_review_receipts",
                          "srs_user_settings", "srs_migration_snapshots"):
                c.execute(f"DELETE FROM {table} WHERE user_id = ?", (self.user,))
            c.execute("DELETE FROM users WHERE id = ?", (self.user,))
            self.assertEqual(c.execute("SELECT COUNT(*) FROM srs_card_deletions WHERE user_id = ?", (self.user,)).fetchone()[0], 0)
            self.assertEqual(c.execute("SELECT COUNT(*) FROM srs_card_identity_flags WHERE user_id = ?", (self.user,)).fetchone()[0], 0)

    def test_t10_ledger_holds_no_content(self):
        card = self.marked(name="内容テスト")
        self.remove(card, "word")
        row = self.ledger()[0]
        self.assertEqual(sorted(row), sorted(["id", "card_kind", "user_id", "card_ref", "deleted_at",
                                              "history_intro_status", "history_intro_known_by"]))
        self.assertNotIn("内容テスト", repr(row))
        self.assertEqual((row["history_intro_status"], row["history_intro_known_by"]), ("before_tracking", "2026-10-05"))

    def test_t11_lost_evidence_is_not_recovered_or_guessed(self):
        card = self.personal("old-delete", deck=self.box)
        with get_connection() as c:  # deleted before this rule: ledger row without a mark
            c.execute("UPDATE vocab_items SET last_reviewed_at = ?, correct_count = 2 WHERE id = ?", (iso(seoul_noon(K)), card))
            c.execute("INSERT INTO srs_card_deletions (card_kind, user_id, card_ref, deleted_at) VALUES ('personal', ?, ?, ?)",
                      (self.user, card, iso(NOW - timedelta(days=1))))
            c.execute("DELETE FROM vocab_items WHERE id = ?", (card,))
        self.fsrs_log(card, NOW - timedelta(minutes=5))  # synthetic remaining log
        digest = self.db_digest()
        self.assertEqual(self.day(TODAY), ("exact", 1, 1))  # log rule; no bound is invented
        self.q()
        init_db()
        with get_connection() as c:
            identity.scan_identity(c)
        self.assertIsNone(self.ledger()[0]["history_intro_status"])
        self.assertEqual(self.db_digest(), digest)  # reads, scans and app start wrote nothing

    def test_t12_rollback_after_deletion_skips_and_keeps_evidence(self):
        from app.repositories import vocab_repository

        card = self.personal("logged", deck=self.box)
        self.set_mode(self.user, "legacy")
        with mock.patch.object(vocab_repository, "now_utc", return_value=NOW - timedelta(days=2)):
            vocab_repository.record_review(self.user, card, "good")
        self.set_mode(self.user, "fsrs")
        migration.apply_plan(migration.dry_run([CardKey("personal", self.user, card)]), "run-12", approved=True)
        self.remove(card, "word")
        ledger = self.ledger()
        rolled = migration.rollback_plan("run-12", "rb-12", user_id=self.user, approved=True)
        self.assertEqual(rolled[0]["result"], "missing_or_access_lost")
        self.assertEqual(self.ledger(), ledger)
        with get_connection() as c:
            self.assertIsNone(c.execute("SELECT 1 FROM vocab_items WHERE id = ?", (card,)).fetchone())  # not restored


# ---------------------------------------------------------------------------
class DeletionRaceTests(DeletionCase):
    """Real overlapping SQLite connections. Each test asserts the lock order with
    race_support.LockProbe and requires every worker to finish with exactly the
    expected outcome (no hidden exception, no missing result)."""

    def card_due(self):
        card = self.personal("rated", deck=self.box, created=NOW - timedelta(days=3))
        self.due("personal", card, SrsPhase.REVIEW, NOW - timedelta(hours=1))
        return card

    def final_state(self, card):
        with get_connection() as c:
            return {
                "card": c.execute("SELECT COUNT(*) FROM vocab_items WHERE id = ?", (card,)).fetchone()[0],
                "fsrs_logs": c.execute("SELECT COUNT(*) FROM review_logs WHERE vocab_item_id = ? AND srs_engine = 'fsrs'",
                                       (card,)).fetchone()[0],
                "receipts": c.execute("SELECT COUNT(*) FROM srs_review_receipts WHERE card_ref = ?", (card,)).fetchone()[0],
                "ledger": [(r["card_ref"], r["history_intro_status"], r["history_intro_known_by"]) for r in c.execute(
                    "SELECT * FROM srs_card_deletions ORDER BY id").fetchall()],
            }

    def holding(self, name, target, slow_owner, slow_attr):
        """Run `target` in thread `name`, parked inside `slow_owner.slow_attr` while it
        holds the account lock. Returns (task, release, patch)."""
        entered, release = threading.Event(), threading.Event()
        real = getattr(slow_owner, slow_attr)

        def slow(*a, **k):
            result = real(*a, **k) if slow_attr == "record_intro" else None
            entered.set()
            self.assertTrue(release.wait(15))
            return result if slow_attr == "record_intro" else real(*a, **k)

        patch = mock.patch.object(slow_owner, slow_attr, slow)
        patch.start()
        self.addCleanup(patch.stop)
        task = race_support.start(name, target)
        self.assertTrue(entered.wait(15), f"{name} did not reach its locked section")
        return task, release

    def let_waiter_block(self, probe, waiter, holder):
        self.assertTrue(probe.wait("waiting", waiter), f"{waiter} never asked for the lock")
        time.sleep(0.3)  # time for a broken lock to be taken; the order check below decides
        self.assertNotIn(("acquired", waiter), probe.events, f"{waiter} got the lock while {holder} held it")
        probe.mark("released", holder)

    def test_review_first_then_delete(self):
        card = self.card_due()
        with race_support.LockProbe() as probe:
            review, release = self.holding(
                "review", lambda: self.rate("personal", card, request="00000000-0000-4000-8000-0000000004a1", version=0),
                reviews, "review")
            delete = race_support.start("delete", lambda: delete_vocab_item(self.user, card))
            self.let_waiter_block(probe, "delete", "review")
            release.set()
            result = race_support.finish(self, review)
            self.assertTrue(race_support.finish(self, delete))
        probe.assert_serialized(self, "review", "delete")
        self.assertEqual(result["srs"]["card_version"], 1)
        self.assertEqual(self.final_state(card), {"card": 0, "fsrs_logs": 1, "receipts": 1,
                                                  "ledger": [(card, None, None)]})

    def test_delete_first_then_review_finds_no_card(self):
        card = self.card_due()
        with race_support.LockProbe() as probe:
            connection = get_connection()
            try:
                storage.begin_card_write(connection, self.user)  # MainThread holds the lock
                identity.record_personal_deletions(connection, "id = ?", (card,))
                connection.execute("DELETE FROM vocab_items WHERE id = ?", (card,))
                review = race_support.start(
                    "review", lambda: self.rate("personal", card, request="00000000-0000-4000-8000-0000000004a2", version=0))
                self.let_waiter_block(probe, "review", "MainThread")
                connection.commit()
            finally:
                connection.close()
            self.assertIsNone(race_support.finish(self, review))  # card gone: the 404 path, nothing written
        probe.assert_serialized(self, "MainThread", "review")
        self.assertEqual(self.final_state(card), {"card": 0, "fsrs_logs": 0, "receipts": 0,
                                                  "ledger": [(card, None, None)]})

    def test_mark_recorded_first_then_delete_copies_it(self):
        card = self.past_card("past", iso(seoul_noon(K)))
        plan = migration.dry_run([CardKey("personal", self.user, card)])
        with race_support.LockProbe() as probe:
            apply, release = self.holding(
                "apply", lambda: migration.apply_plan(plan, "run-race", approved=True), migration, "record_intro")
            delete = race_support.start("delete", lambda: delete_vocab_item(self.user, card))
            self.let_waiter_block(probe, "delete", "apply")
            release.set()
            applied = race_support.finish(self, apply)
            self.assertTrue(race_support.finish(self, delete))
        probe.assert_serialized(self, "apply", "delete")
        self.assertEqual((applied[0]["result"], applied[0]["history_intro"]), ("applied", "recorded"))  # U5
        self.assertEqual(self.final_state(card), {"card": 0, "fsrs_logs": 0, "receipts": 0,
                                                  "ledger": [(card, "before_tracking", "2026-10-05")]})
        self.assertEqual(self.day(K)[0], "unknown")

    def test_delete_first_then_mark_is_not_written(self):
        card = self.past_card("past", iso(seoul_noon(K)))
        plan = migration.dry_run([CardKey("personal", self.user, card)])
        with race_support.LockProbe() as probe:
            connection = get_connection()
            try:
                storage.begin_card_write(connection, self.user)
                identity.record_personal_deletions(connection, "id = ?", (card,))
                connection.execute("DELETE FROM vocab_items WHERE id = ?", (card,))
                apply = race_support.start("apply", lambda: migration.apply_plan(plan, "run-race-2", approved=True))
                self.let_waiter_block(probe, "apply", "MainThread")
                connection.commit()
            finally:
                connection.close()
            applied = race_support.finish(self, apply)
        probe.assert_serialized(self, "MainThread", "apply")
        self.assertEqual(applied[0]["result"], "conflict")  # card gone: nothing recorded or restored
        self.assertEqual(self.final_state(card), {"card": 0, "fsrs_logs": 0, "receipts": 0,
                                                  "ledger": [(card, None, None)]})


if __name__ == "__main__":
    unittest.main()

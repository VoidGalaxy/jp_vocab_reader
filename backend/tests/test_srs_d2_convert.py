"""Gate D-2 U5: incomplete-history conversion through the explicit migration tool.

Synthetic SQLite only (QueueCase sets a throwaway DATABASE_URL per test before the
app touches a database). Serving (U6), the first review (U7) and rollback/re-conversion
(U8) have their own test files.

Run directly:      python tests/test_srs_d2_convert.py
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
from test_srs_d2_intro import IntroCase  # noqa: E402
from test_srs_queue import NOW, iso  # noqa: E402
import race_support  # noqa: E402

from app.database import get_connection  # noqa: E402
from app.repositories import vocab_repository  # noqa: E402
from app.srs import identity, migration  # noqa: E402
from app.srs.engine import CardKey  # noqa: E402
from app.srs.storage import SrsWriteError  # noqa: E402

LEGACY_FACTS = ("status", "correct_count", "wrong_count", "last_reviewed_at", "review_level", "next_review_at",
                "meaning_ko", "surface", "deck_id", "created_at", "completion_metric_version", "first_completed_at")
ENGINE = ("srs_state", "srs_step", "srs_stability", "srs_difficulty", "srs_due_at", "srs_last_review_at")


class ConvertCase(IntroCase):
    def legacy_review(self, card, at):
        """A real legacy review (legacy account mode, existing code path)."""
        self.set_mode(self.user, "legacy")
        with mock.patch.object(vocab_repository, "now_utc", return_value=at):
            vocab_repository.record_review(self.user, card, "good")
        self.set_mode(self.user, "fsrs")

    def raw_log(self, card, at, prev=0, nxt=1, rating="good", time_text=None):
        with get_connection() as c:
            c.execute("INSERT INTO review_logs (user_id, vocab_item_id, rating, reviewed_at, previous_review_level, "
                      "next_review_level, next_review_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                      (self.user, card, rating, time_text or iso(at), prev, nxt, iso(at + timedelta(days=1))))

    def missing_history(self, name="missing", status="unknown"):
        card = self.personal(name, status=status)
        with get_connection() as c:
            c.execute("UPDATE vocab_items SET last_reviewed_at = ?, correct_count = 2, review_level = 2, "
                      "next_review_at = ? WHERE id = ?", (iso(NOW - timedelta(days=4)), iso(NOW + timedelta(days=2)), card))
        return card

    def broken_chain(self, name="broken"):
        card = self.personal(name)
        self.legacy_review(card, NOW - timedelta(days=6))
        self.raw_log(card, NOW - timedelta(days=5), prev=5, nxt=6)  # does not follow the previous log
        return card

    def same_time(self, name="same-time"):
        card = self.personal(name)
        at = NOW - timedelta(days=3)
        self.raw_log(card, at)
        self.raw_log(card, at, rating="hard")
        with get_connection() as c:
            c.execute("UPDATE vocab_items SET last_reviewed_at = ?, correct_count = 2, next_review_at = ? WHERE id = ?",
                      (iso(at), iso(NOW + timedelta(days=1)), card))
        return card

    def value_mismatch(self, name="mismatch"):
        card = self.personal(name)
        self.legacy_review(card, NOW - timedelta(days=2))
        with get_connection() as c:  # card values disagree with the last log
            c.execute("UPDATE vocab_items SET review_level = 4 WHERE id = ?", (card,))
        return card

    def row(self, card, table="vocab_items", column="id"):
        with get_connection() as c:
            return dict(c.execute(f"SELECT * FROM {table} WHERE {column} = ? AND user_id = ?", (card, self.user)).fetchone())

    def plan(self, *cards, kind="personal"):
        return migration.dry_run([CardKey(kind, self.user, c) for c in cards])

    def snapshots(self):
        with get_connection() as c:
            return c.execute("SELECT COUNT(*) FROM srs_migration_snapshots").fetchone()[0]


# ---------------------------------------------------------------------------
class PersonalConversionTests(ConvertCase):
    def assert_converted(self, card, before, flags_expected):
        after = self.row(card)
        self.assertEqual(after["srs_engine"], "fsrs")
        self.assertEqual({k: after[k] for k in ENGINE}, {k: None for k in ENGINE})  # no derived engine state
        self.assertEqual(after["srs_effective_due_at"], before["next_review_at"])  # first schedule kept verbatim
        self.assertEqual(after["srs_history_quality"], "incomplete")
        self.assertTrue(set(flags_expected) <= set(json.loads(after["srs_history_flags"])))
        self.assertEqual({k: after[k] for k in LEGACY_FACTS}, {k: before[k] for k in LEGACY_FACTS})
        self.assertEqual(after["srs_card_version"], before["srs_card_version"] + 1)
        self.assertEqual(after["id"], before["id"])
        return after

    def test_gap_order_and_value_mismatch_cards_convert_with_empty_engine_state(self):
        cards = {"missing": self.missing_history(), "broken": self.broken_chain(),
                 "same_time": self.same_time(), "mismatch": self.value_mismatch()}
        with get_connection() as c:  # an existing first completion record must survive
            c.execute("UPDATE vocab_items SET completion_metric_version = 'meaning-completion-v1-draft', "
                      "first_completed_at = ? WHERE id = ?", (iso(NOW - timedelta(days=1)), cards["mismatch"]))
        before = {k: self.row(c) for k, c in cards.items()}
        logs, today = self.logs(), self.count(NOW)
        digest = self.db_digest()
        plan = self.plan(*cards.values())
        self.assertEqual(self.db_digest(), digest)  # dry-run: zero writes
        self.assertTrue(all(c.quality == "incomplete" and c.values_json for c in plan))
        results = migration.apply_plan(plan, "run-u5", approved=True)
        self.assertEqual([r["result"] for r in results], ["applied"] * 4)
        self.assert_converted(cards["missing"], before["missing"], ["missing_history"])
        self.assert_converted(cards["broken"], before["broken"], ["broken_log_chain"])
        self.assert_converted(cards["same_time"], before["same_time"], ["ambiguous_same_time"])
        after = self.assert_converted(cards["mismatch"], before["mismatch"], ["card_log_mismatch"])
        self.assertEqual(after["first_completed_at"], iso(NOW - timedelta(days=1)))
        self.assertEqual(self.logs(), logs)  # raw logs untouched
        self.assertEqual(self.count(NOW), today)  # the conversion creates no new-word result
        self.assertEqual(self.snapshots(), 4)
        self.assertEqual(self.mark(cards["missing"]), ("before_tracking", "2026-10-05"))  # U4 mark kept
        self.assertEqual(self.mark(cards["broken"]), ("logged", None))

    def test_converted_cards_are_served_and_take_a_first_review(self):
        timed = self.missing_history("timed")
        untimed = self.personal("untimed")  # ratings but no time and no log
        with get_connection() as c:
            c.execute("UPDATE vocab_items SET correct_count = 1, next_review_at = ? WHERE id = ?",
                      (iso(NOW - timedelta(hours=1)), untimed))
        migration.apply_plan(self.plan(timed, untimed), "run-u5-q", approved=True)
        result = self.q()
        # U6: scheduled reviews, never new. timed is due in 2 days, untimed is due now.
        self.assertEqual((result["counts"]["pending_later"], result["counts"]["review_due"]), (1, 1))
        self.assertEqual(result["counts"]["new_available"], 0)
        self.assertEqual([(i["card_id"], i["bucket"], i["is_new"]) for i in result["items"]],
                         [(untimed, "review_due", False)])
        # U7: the converted cards take their first FSRS review (library default first review).
        for card in (timed, untimed):
            version = self.row(card)["srs_card_version"]
            result = self.rate("personal", card, request=f"00000000-0000-4000-8000-00000000{card:04d}", version=version)
            self.assertEqual(result["srs"]["card_version"], version + 1)
        # A non-converted card with history but no state is still refused (fail closed).
        foreign = self.personal("fresh-with-foreign-log")
        self.fsrs("personal", foreign, srs_history_quality="fresh")
        self.raw_log(foreign, NOW - timedelta(days=4))
        with self.assertRaises(SrsWriteError) as caught:
            self.rate("personal", foreign, request="00000000-0000-4000-8000-0000000009f1", version=0)
        self.assertEqual(caught.exception.code, "history_initialization_requires_approval")

    def test_known_card_is_paused(self):
        card = self.missing_history("known", status="known")
        migration.apply_plan(self.plan(card), "run-known", approved=True)
        row = self.row(card)
        self.assertEqual((row["srs_participation"], row["srs_pause_reason"], row["status"]), ("paused", "legacy_known", "known"))

    def test_blocked_kinds_stay_legacy(self):
        bad_time = self.personal("bad-time")
        self.raw_log(bad_time, NOW, time_text="garbage")
        bad_rating = self.personal("bad-rating")
        self.raw_log(bad_rating, NOW - timedelta(days=1), rating="wow")
        flagged = self.missing_history("flagged")
        with get_connection() as c:
            identity.flag_identity_unknown(c, [identity.IdentityFinding(self.user, flagged, ["test"])])
        no_due = self.missing_history("no-due")
        bad_due = self.missing_history("bad-due")
        with get_connection() as c:
            c.execute("UPDATE vocab_items SET next_review_at = NULL WHERE id = ?", (no_due,))
            c.execute("UPDATE vocab_items SET next_review_at = 'tomorrow' WHERE id = ?", (bad_due,))
        cards = [bad_time, bad_rating, flagged, no_due, bad_due]
        before = {c: self.row(c) for c in cards}
        plan = self.plan(*cards)
        flags = {c.key.ref_id: c.flags for c in plan}
        self.assertIn("invalid_history_time", flags[bad_time])
        self.assertIn("invalid_rating", flags[bad_rating])
        self.assertEqual(flags[flagged], ("identity_unknown",))
        self.assertIn("schedule_missing", flags[no_due])
        self.assertIn("schedule_unreadable", flags[bad_due])
        results = migration.apply_plan(plan, "run-blocked", approved=True)
        self.assertEqual([r["result"] for r in results], ["blocked"] * 5)
        for card in cards:
            after = self.row(card)
            self.assertEqual(after["srs_engine"], "legacy")
            self.assertEqual(after["next_review_at"], before[card]["next_review_at"])  # never filled with "now"
            self.assertEqual(after["srs_card_version"], before[card]["srs_card_version"])
        self.assertEqual(self.snapshots(), 0)

    def test_short_interval_alone_is_not_incomplete(self):
        card = self.personal("quick")
        self.legacy_review(card, NOW - timedelta(days=1, seconds=40))
        self.legacy_review(card, NOW - timedelta(days=1))
        candidate = self.plan(card)[0]
        self.assertEqual(candidate.quality, "complete")
        self.assertIn("short_interval_repeat", candidate.flags)

    def test_changes_after_preview_are_conflicts_and_nothing_is_restored(self):
        reviewed, edited, deleted = self.missing_history("r"), self.missing_history("e"), self.missing_history("d")
        plan = self.plan(reviewed, edited, deleted)
        self.legacy_review(reviewed, NOW - timedelta(hours=1))
        with get_connection() as c:
            c.execute("UPDATE vocab_items SET meaning_ko = 'changed' WHERE id = ?", (edited,))
        self.assertTrue(vocab_repository.delete_vocab_item(self.user, deleted))
        before = {c: self.row(c) for c in (reviewed, edited)}
        results = migration.apply_plan(plan, "run-conflict", approved=True)
        self.assertEqual([r["result"] for r in results], ["conflict"] * 3)
        for card in (reviewed, edited):
            self.assertEqual(self.row(card), before[card])
        with get_connection() as c:
            self.assertIsNone(c.execute("SELECT 1 FROM vocab_items WHERE id = ?", (deleted,)).fetchone())
        self.assertEqual(self.snapshots(), 0)

    def test_batch_failure_resume_and_rerun(self):
        cards = [self.missing_history(f"b{i}") for i in range(3)]
        plan = self.plan(*cards)
        real = migration.update_card
        calls = {"n": 0}

        def failing(*a, **k):
            calls["n"] += 1
            if calls["n"] == 2:
                raise RuntimeError("injected batch failure")
            return real(*a, **k)

        with mock.patch.object(migration, "update_card", failing):
            with self.assertRaises(RuntimeError):
                migration.apply_plan(plan, "run-batch", approved=True)
        with get_connection() as c:
            run = c.execute("SELECT status, summary_json FROM srs_migration_runs WHERE run_key = 'run-batch'").fetchone()
        self.assertEqual(run["status"], "failed")
        self.assertEqual(json.loads(run["summary_json"])["cursor"], 1)
        self.assertEqual(self.snapshots(), 1)  # snapshot and cursor committed together for card 1 only
        self.assertEqual([self.row(c)["srs_engine"] for c in cards], ["fsrs", "legacy", "legacy"])
        results = migration.apply_plan(plan, "run-batch", approved=True)  # resume
        self.assertEqual([r["result"] for r in results], ["already_applied", "applied", "applied"])
        self.assertEqual(self.snapshots(), 3)
        self.assertEqual([self.row(c)["srs_card_version"] for c in cards], [1, 1, 1])  # none applied twice
        again = migration.apply_plan(plan, "run-batch", approved=True)
        self.assertEqual(self.snapshots(), 3)
        self.assertEqual([r["result"] for r in again], ["already_applied"] * 3)

    def test_rollback_restores_legacy_projection_and_keeps_the_mark(self):
        card = self.missing_history()
        before = self.row(card)
        migration.apply_plan(self.plan(card), "run-rb5", approved=True)
        rolled = migration.rollback_plan("run-rb5", "rb-5", user_id=self.user, approved=True)
        self.assertEqual(rolled[0]["result"], "rolled_back")
        after = self.row(card)
        self.assertEqual(after["srs_engine"], "legacy")
        self.assertEqual({k: after[k] for k in LEGACY_FACTS}, {k: before[k] for k in LEGACY_FACTS})
        self.assertEqual(self.mark(card), ("before_tracking", "2026-10-05"))


# ---------------------------------------------------------------------------
class SubscribedConversionTests(ConvertCase):
    def legacy_progress(self, lexeme, **values):
        values = dict(dict(srs_engine="legacy", srs_config_version=None, srs_participation=None,
                           srs_history_quality=None), **values)
        with get_connection() as c:
            c.execute("UPDATE user_word_progress SET " + ", ".join(f"{k} = ?" for k in values)
                      + " WHERE user_id = ? AND lexeme_id = ?", (*values.values(), self.user, lexeme))

    def lexeme_log(self, lexeme, deck, at, prev=0, nxt=1, rating="good"):
        with get_connection() as c:
            c.execute("INSERT INTO lexeme_review_logs (user_id, lexeme_id, shared_deck_id, rating, previous_review_level, "
                      "new_review_level, previous_next_review_at, new_next_review_at, previous_status, new_status, created_at) "
                      "VALUES (?, ?, ?, ?, ?, ?, NULL, ?, 'unknown', 'unknown', ?)",
                      (self.user, lexeme, deck, rating, prev, nxt, iso(at + timedelta(days=1)), iso(at)))

    def test_subscribed_gap_order_and_mismatch(self):
        deck = self.shared_deck("s")
        missing, broken, same = (self.lexeme(n, deck, i) for i, n in enumerate(("m", "b", "t")))
        due = iso(NOW + timedelta(days=3))
        self.legacy_progress(missing, last_reviewed_at=iso(NOW - timedelta(days=4)), correct_count=2, next_review_at=due)
        self.lexeme_log(broken, deck, NOW - timedelta(days=5), prev=4, nxt=5)
        self.legacy_progress(broken, last_reviewed_at=iso(NOW - timedelta(days=5)), correct_count=1, review_level=5,
                             next_review_at=due)
        at = NOW - timedelta(days=2)
        self.lexeme_log(same, deck, at)
        self.lexeme_log(same, deck, at, rating="hard")
        self.legacy_progress(same, last_reviewed_at=iso(at), correct_count=2, next_review_at=due)
        before = {lx: self.row(lx, "user_word_progress", "lexeme_id") for lx in (missing, broken, same)}
        plan = self.plan(missing, broken, same, kind="lexeme")
        self.assertEqual([c.quality for c in plan], ["incomplete"] * 3)
        results = migration.apply_plan(plan, "run-lex5", approved=True)
        self.assertEqual([r["result"] for r in results], ["applied"] * 3)
        for lexeme, flag in ((missing, "missing_history"), (broken, "broken_log_chain"), (same, "ambiguous_same_time")):
            after = self.row(lexeme, "user_word_progress", "lexeme_id")
            self.assertEqual(after["srs_engine"], "fsrs")
            self.assertEqual({k: after[k] for k in ENGINE}, {k: None for k in ENGINE})
            self.assertEqual(after["srs_effective_due_at"], due)
            self.assertIn(flag, json.loads(after["srs_history_flags"]))
            for name in ("status", "correct_count", "wrong_count", "last_reviewed_at", "review_level", "next_review_at"):
                self.assertEqual(after[name], before[lexeme][name], (lexeme, name))
        self.assertEqual(self.q()["counts"]["pending_later"], 3)  # U6: scheduled reviews, due in 3 days

    def test_lost_subscription_after_preview_is_a_conflict(self):
        deck = self.shared_deck("s")
        lexeme = self.lexeme("w", deck, 0)
        self.legacy_progress(lexeme, last_reviewed_at=iso(NOW - timedelta(days=4)), correct_count=1,
                             next_review_at=iso(NOW + timedelta(days=1)))
        plan = self.plan(lexeme, kind="lexeme")
        with get_connection() as c:  # synthetic: no unsubscribe path exists in the app
            c.execute("UPDATE user_deck_subscriptions SET is_active = FALSE WHERE user_id = ?", (self.user,))
        self.assertEqual(migration.apply_plan(plan, "run-lost", approved=True)[0]["result"], "conflict")
        self.assertEqual(self.row(lexeme, "user_word_progress", "lexeme_id")["srs_engine"], "legacy")


# ---------------------------------------------------------------------------
class ConversionRaceTests(ConvertCase):
    def test_apply_first_then_legacy_review(self):
        card = self.missing_history()
        plan = self.plan(card)
        entered, release = threading.Event(), threading.Event()
        real = migration.record_intro

        def slow(*a, **k):
            result = real(*a, **k)
            entered.set()
            self.assertTrue(release.wait(15))
            return result

        with race_support.LockProbe() as probe, mock.patch.object(migration, "record_intro", slow):
            apply = race_support.start("apply", lambda: migration.apply_plan(plan, "run-race-a", approved=True))
            self.assertTrue(entered.wait(15))
            # A versioned (FSRS-client) request made against the version seen before the conversion.
            review = race_support.start("review", lambda: vocab_repository.record_review(
                self.user, card, "good", request_id="00000000-0000-4000-8000-0000000005a1",
                expected_card_version=0, session_id="s1"))
            self.assertTrue(probe.wait("waiting", "review"))
            time.sleep(0.3)
            self.assertNotIn(("acquired", "review"), probe.events)
            probe.mark("released", "apply")
            release.set()
            self.assertEqual(race_support.finish(self, apply)[0]["result"], "applied")
            # The card changed under it (conversion bumped the version): refused, nothing written.
            race_support.finish_error(self, review, SrsWriteError, "card_version_conflict")
        probe.assert_serialized(self, "apply", "review")
        self.assertEqual(self.row(card)["srs_engine"], "fsrs")
        self.assertEqual(self.logs(), [])  # the late review wrote nothing

    def test_legacy_review_first_then_apply_conflicts(self):
        card = self.missing_history()
        plan = self.plan(card)
        entered, release = threading.Event(), threading.Event()
        real = vocab_repository.compute_review_schedule

        def slow(*a, **k):
            entered.set()
            self.assertTrue(release.wait(15))
            return real(*a, **k)

        self.set_mode(self.user, "legacy")
        with race_support.LockProbe() as probe, mock.patch.object(vocab_repository, "compute_review_schedule", slow):
            review = race_support.start("review", lambda: vocab_repository.record_review(self.user, card, "good"))
            self.assertTrue(entered.wait(15))
            apply = race_support.start("apply", lambda: migration.apply_plan(plan, "run-race-b", approved=True))
            self.assertTrue(probe.wait("waiting", "apply"))
            time.sleep(0.3)
            self.assertNotIn(("acquired", "apply"), probe.events)
            probe.mark("released", "review")
            release.set()
            self.assertIsNotNone(race_support.finish(self, review))
            self.assertEqual(race_support.finish(self, apply)[0]["result"], "conflict")
        self.set_mode(self.user, "fsrs")
        probe.assert_serialized(self, "review", "apply")
        row = self.row(card)
        self.assertEqual((row["srs_engine"], row["correct_count"]), ("legacy", 3))  # review kept, not converted
        self.assertEqual(len(self.logs()), 1)


if __name__ == "__main__":
    unittest.main()

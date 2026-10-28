"""Gate D-2 U4 (D-H7): past-learning marks and the daily new-word count.

Synthetic SQLite only (QueueCase sets a throwaway DATABASE_URL per test before
the app touches a database). U5~U7 (incomplete conversion, first review of such
cards) do not exist yet: where a test needs a later FSRS log it inserts one as
synthetic state and says so. This is not a full conversion-flow test.

Run directly:      python tests/test_srs_d2_intro.py
Or via discovery:   python -m unittest discover -s tests
"""

from __future__ import annotations

import hashlib
import sys
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_srs_queue import NOW, QueueCase, iso  # noqa: E402

from app.database import get_connection  # noqa: E402
from app.repositories import stats_history_repository  # noqa: E402
from app.srs import goals, history_intro, identity, migration, reviews  # noqa: E402
from app.srs.engine import CardKey  # noqa: E402

UTC = timezone.utc
KST = timezone(timedelta(hours=9))


def seoul_noon(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, 12, 0, tzinfo=KST).astimezone(UTC)


class IntroCase(QueueCase):
    def past_card(self, name, last_reviewed_at, counts=2, user=None):
        """Legacy card with past study and no review log (CONTRACT F16)."""
        card = self.personal(name, user=user)
        with get_connection() as c:
            c.execute("UPDATE vocab_items SET last_reviewed_at = ?, correct_count = ?, review_level = 2, "
                      "next_review_at = ? WHERE id = ?", (last_reviewed_at, counts, iso(NOW + timedelta(days=3)), card))
        return card

    def apply(self, *cards, run="run-u4"):
        plan = migration.dry_run([CardKey("personal", self.user, c) for c in cards])
        return migration.apply_plan(plan, run, approved=True)

    def mark(self, card, table="vocab_items", column="id"):
        with get_connection() as c:
            row = c.execute(f"SELECT history_intro_status, history_intro_known_by FROM {table} WHERE {column} = ? "
                            "AND user_id = ?", (card, self.user)).fetchone()
        return tuple(row)

    def count(self, at, scope=None):
        with get_connection() as c:
            return goals.introduction_count(c, self.user, at, scope)

    def fsrs_log(self, card, at, user=None):
        """Synthetic later FSRS log (stands in for a U7 first review)."""
        with get_connection() as c:
            c.execute("INSERT INTO review_logs (user_id, vocab_item_id, rating, reviewed_at, previous_review_level, "
                      "next_review_level, next_review_at, srs_engine, is_first_review) "
                      "VALUES (?, ?, 'good', ?, 0, 1, ?, 'fsrs', 1)", (user or self.user, card, iso(at), iso(at)))

    def db_digest(self):
        return hashlib.sha256(self.db_path.read_bytes()).hexdigest()

    def card_row(self, card):
        with get_connection() as c:
            row = dict(c.execute("SELECT * FROM vocab_items WHERE id = ?", (card,)).fetchone())
        # Legacy facts only: U5 conversion writes srs_* (engine, quality, version) by design.
        return {k: v for k, v in row.items() if k not in history_intro.INTRO_COLUMNS and not k.startswith("srs_")}

    def logs(self):
        with get_connection() as c:
            return [tuple(r) for r in c.execute("SELECT * FROM review_logs ORDER BY id").fetchall()]


# ---------------------------------------------------------------------------
class ClassifyTests(unittest.TestCase):
    def test_decision_table(self):
        c = history_intro.classify_intro
        self.assertEqual(c({"last_reviewed_at": "2026-10-01T00:00:00+00:00"}, [{"id": 1}]), ("logged", None))
        self.assertEqual(c({"last_reviewed_at": "2026-10-09T14:59:59+00:00"}, []), ("before_tracking", "2026-10-09"))
        # Seoul midnight: 15:00 UTC is 00:00 KST of the next date.
        self.assertEqual(c({"last_reviewed_at": "2026-10-09T15:00:00+00:00"}, []), ("before_tracking", "2026-10-10"))
        # Offsets are real instants: the same instant written three ways.
        for text in ("2026-10-09T15:30:00+00:00", "2026-10-09T15:30:00Z", "2026-10-10T00:30:00+09:00",
                     "2026-10-09T10:30:00-05:00"):
            self.assertEqual(c({"last_reviewed_at": text}, []), ("before_tracking", "2026-10-10"), text)
        # Unusable bound: no zone, garbage, empty -> unknown (no guessed date).
        for text in ("2026-10-09T15:30:00", "garbage", ""):
            self.assertEqual(c({"last_reviewed_at": text}, []), ("unknown", None), repr(text))
        # Missing time with ratings -> unknown; missing time and no ratings -> nothing,
        # even when the card is self-classified as known.
        self.assertEqual(c({"last_reviewed_at": None, "correct_count": 1, "wrong_count": 0}, []), ("unknown", None))
        self.assertEqual(c({"last_reviewed_at": None, "correct_count": 0, "wrong_count": 0, "status": "known"}, []),
                         (None, None))


# ---------------------------------------------------------------------------
class RecordTests(IntroCase):
    def test_dry_run_writes_nothing_and_apply_records_once(self):
        dl = NOW - timedelta(days=5)
        card = self.past_card("past", iso(dl))
        before_row, before_logs = self.card_row(card), self.logs()
        digest = self.db_digest()
        migration.dry_run([CardKey("personal", self.user, card)])
        self.assertEqual(self.db_digest(), digest)  # dry-run: zero writes
        self.assertEqual(self.mark(card), (None, None))
        result = self.apply(card)
        self.assertEqual(result[0]["result"], "applied")  # U5 converts it (engine state stays empty)
        self.assertEqual(result[0]["history_intro"], "recorded")
        self.assertEqual(self.mark(card), ("before_tracking", "2026-10-04"))  # NOW-5d is 2026-10-04 12:00 KST
        # Classification, schedule, counters, completion record and logs unchanged.
        self.assertEqual(self.card_row(card), before_row)
        self.assertEqual(self.logs(), before_logs)
        # A converted card is not converted again (already_fsrs), and its mark stays.
        self.assertEqual(self.apply(card, run="run-u4-again")[0]["quality"], "already_fsrs")
        # After a rollback, a new explicit apply keeps the existing mark.
        migration.rollback_plan("run-u4", "rb-u4", user_id=self.user, approved=True)
        self.assertEqual(self.apply(card, run="run-u4-third")[0]["history_intro"], "kept_existing")
        # A changed last_reviewed_at later never narrows or replaces the mark.
        migration.rollback_plan("run-u4-third", "rb-u4-third", user_id=self.user, approved=True)
        with get_connection() as c:
            c.execute("UPDATE vocab_items SET last_reviewed_at = ? WHERE id = ?", (iso(NOW), card))
        self.assertEqual(self.apply(card, run="run-u4-fourth")[0]["history_intro"], "kept_existing")
        self.assertEqual(self.mark(card), ("before_tracking", "2026-10-04"))

    def test_reads_and_app_start_do_not_write(self):
        card = self.past_card("past", iso(NOW - timedelta(days=2)))
        digest = self.db_digest()
        self.q()
        self.count(NOW)
        with get_connection() as c:
            stats_history_repository.build_today_seoul(self.user, NOW)
            history_intro.intro_evidence(c, self.user)
        self.assertEqual(self.db_digest(), digest)
        from app.database import init_db
        init_db()
        self.assertEqual(self.mark(card), (None, None))

    def test_unreviewed_known_card_and_true_new_card(self):
        known = self.personal("known-only", status="known")
        fresh = self.personal("fresh")
        result = self.apply(known, fresh)
        self.assertEqual([r.get("history_intro") for r in result], ["no_history", "no_history"])
        self.assertEqual(self.mark(known), (None, None))
        # Its first real log counts as new on that day, like any new card.
        self.fsrs_log(known, NOW - timedelta(minutes=5))
        self.fsrs_log(fresh, NOW - timedelta(minutes=4))
        today = self.count(NOW)
        self.assertEqual((today.status, today.count), ("exact", 2))

    def test_missing_or_damaged_bound_is_unknown(self):
        missing = self.personal("missing")
        with get_connection() as c:
            c.execute("UPDATE vocab_items SET correct_count = 3 WHERE id = ?", (missing,))
        damaged = self.past_card("damaged", "2026-10-01 09:00")  # no zone
        self.apply(missing, damaged)
        self.assertEqual(self.mark(missing), ("unknown", None))
        self.assertEqual(self.mark(damaged), ("unknown", None))
        for day in (NOW, NOW - timedelta(days=30), NOW + timedelta(days=30)):
            self.assertEqual(self.count(day).status, "unknown")  # no narrowing on any date
            self.assertEqual(self.count(day).history_unknown_cards, 2)

    def test_rollback_and_reconversion_keep_the_mark(self):
        from unittest import mock

        from app.repositories import vocab_repository

        card = self.personal("logged")
        self.set_mode(self.user, "legacy")  # one real legacy review -> complete history
        with mock.patch.object(vocab_repository, "now_utc", return_value=NOW - timedelta(days=2)):
            vocab_repository.record_review(self.user, card, "good")
        self.set_mode(self.user, "fsrs")
        result = self.apply(card, run="run-rb")
        self.assertEqual((result[0]["result"], result[0]["history_intro"]), ("applied", "recorded"))
        self.assertEqual(self.mark(card), ("logged", None))
        # Synthetic stand-in for a U5 before_tracking mark on a converted card: the
        # rollback must keep whatever mark is there.
        with get_connection() as c:
            c.execute("UPDATE vocab_items SET history_intro_status = 'before_tracking', "
                      "history_intro_known_by = '2026-10-01' WHERE id = ?", (card,))
        rolled = migration.rollback_plan("run-rb", "rb-1", user_id=self.user, approved=True)
        self.assertEqual(rolled[0]["result"], "rolled_back")
        self.assertEqual(self.mark(card), ("before_tracking", "2026-10-01"))
        again = self.apply(card, run="run-rb-2")
        self.assertEqual(again[0]["history_intro"], "kept_existing")
        self.assertEqual(self.mark(card), ("before_tracking", "2026-10-01"))
        self.assertTrue(set(history_intro.INTRO_COLUMNS) <= set(migration.ROLLBACK_PRESERVED))


# ---------------------------------------------------------------------------
class CountTests(IntroCase):
    """CONTRACT 3-3 case C. The real first study date `a` is unknown to the system."""

    def setUp(self):
        super().setUp()
        self.dl = date(2026, 10, 5)  # bound K (Seoul date of last_reviewed_at)
        self.card = self.past_card("past", iso(seoul_noon(self.dl)))
        self.apply(self.card)
        self.assertEqual(self.mark(self.card), ("before_tracking", "2026-10-05"))

    def at(self, day):
        return self.count(seoul_noon(day))

    def test_case_c_table(self):
        d = self.dl
        for name, day, expected in (
            ("C1 a<K, D=a", d - timedelta(days=5), "unknown"),
            ("C2 a<K, D=K", d, "unknown"),
            ("C3 a=K, D=K", d, "unknown"),
            ("C5 D before a", d - timedelta(days=9), "unknown"),
            ("C4 D=K+1", d + timedelta(days=1), "exact"),
            ("C4 today", date(2026, 10, 9), "exact"),
        ):
            result = self.at(day)
            self.assertEqual(result.status, expected, name)
            if expected == "exact":
                self.assertEqual(result.count, 0, name)
            else:
                self.assertIsNone(result.count, name)
                self.assertEqual(result.at_least, 0, name)

    def test_c4_seoul_midnight_boundary(self):
        k_end = datetime(2026, 10, 5, 23, 59, 59, tzinfo=KST)
        self.assertEqual(self.count(k_end.astimezone(UTC)).status, "unknown")  # still K
        self.assertEqual(self.count((k_end + timedelta(seconds=1)).astimezone(UTC)).status, "exact")  # K+1

    def test_c6_damaged_bound_on_every_date(self):
        damaged = self.past_card("damaged", "not-a-time")
        self.apply(damaged, run="run-c6")
        for day in (self.dl - timedelta(days=9), self.dl, self.dl + timedelta(days=1), date(2026, 10, 9)):
            self.assertEqual(self.at(day).status, "unknown")

    def test_c7_first_fsrs_log_after_the_mark_is_not_new(self):
        verified_before = self.count(NOW)
        first_fsrs = NOW - timedelta(minutes=30)
        self.fsrs_log(self.card, first_fsrs)  # synthetic stand-in for a U7 first review
        today = self.count(NOW)
        self.assertEqual((today.status, today.count), ("exact", 0))
        self.assertEqual(today.count, verified_before.count)
        # Queue, review response and /stats use the same rule.
        self.assertEqual(self.q()["new_goal"]["introduced_today"], 0)
        with get_connection() as c:
            self.assertEqual(reviews.introduced_on(c, self.user, NOW).count, 0)
        stats = stats_history_repository.build_today_seoul(self.user, NOW)
        self.assertEqual((stats["introduced"]["status"], stats["introduced"]["count"]), ("exact", 0))
        # The mark does not hide genuinely new cards on the same day.
        fresh = self.personal("fresh")
        self.fsrs_log(fresh, NOW - timedelta(minutes=10))
        self.assertEqual(self.count(NOW).count, 1)

    def test_bound_today_leaves_today_unknown_with_lower_bound(self):
        today_card = self.past_card("today", iso(NOW - timedelta(hours=1)))
        fresh = self.personal("fresh")
        self.fsrs_log(fresh, NOW - timedelta(minutes=5))
        self.apply(today_card, run="run-today")
        today = self.count(NOW)
        self.assertEqual((today.status, today.count, today.at_least), ("unknown", None, 1))
        self.assertEqual(self.q()["new_goal"]["introduced_today_status"], "unknown")

    def test_account_and_scope_separation(self):
        other_deck = self.personal("x")  # keep fixture ids apart
        mine_scope = {("personal", self.card)}
        self.assertEqual(self.count(seoul_noon(self.dl), scope={("personal", other_deck)}).status, "exact")
        self.assertEqual(self.count(seoul_noon(self.dl), scope=mine_scope).status, "unknown")
        with get_connection() as c:
            theirs = goals.introduction_count(c, self.other, seoul_noon(self.dl))
        self.assertEqual((theirs.status, theirs.count), ("exact", 0))

    def test_subscribed_card_uses_the_same_contract(self):
        shared = self.shared_deck("s")
        lexeme = self.lexeme("w", shared, 0)
        with get_connection() as c:
            c.execute("UPDATE user_word_progress SET srs_engine = 'legacy', srs_config_version = NULL, "
                      "srs_participation = NULL, srs_history_quality = NULL, last_reviewed_at = ?, correct_count = 1 "
                      "WHERE user_id = ? AND lexeme_id = ?", (iso(seoul_noon(date(2026, 10, 7))), self.user, lexeme))
        plan = migration.dry_run([CardKey("lexeme", self.user, lexeme)])
        result = migration.apply_plan(plan, "run-lex", approved=True)
        self.assertEqual(result[0]["history_intro"], "recorded")
        self.assertEqual(self.mark(lexeme, "user_word_progress", "lexeme_id"), ("before_tracking", "2026-10-07"))
        self.assertEqual(self.at(date(2026, 10, 7)).status, "unknown")
        scope = {("lexeme", lexeme)}
        self.assertEqual(self.count(seoul_noon(date(2026, 10, 8)), scope=scope).status, "exact")
        self.assertEqual(self.count(seoul_noon(date(2026, 10, 7)), scope=scope).status, "unknown")

    def test_identity_and_unreadable_rules_are_not_weakened(self):
        # Unreadable own log time on a marked card: unknown on every date, even after K.
        with get_connection() as c:
            c.execute("INSERT INTO review_logs (user_id, vocab_item_id, rating, reviewed_at, previous_review_level, "
                      "next_review_level, next_review_at) VALUES (?, ?, 'good', 'garbage', 0, 1, ?)",
                      (self.user, self.card, iso(NOW)))
        after_k = self.at(self.dl + timedelta(days=2))
        self.assertEqual((after_k.status, after_k.unreadable_cards), ("unknown", 1))
        with get_connection() as c:
            c.execute("DELETE FROM review_logs WHERE reviewed_at = 'garbage'")
        # Identity-unknown id with readable logs: its own date rule wins over the mark.
        self.fsrs_log(self.card, seoul_noon(self.dl + timedelta(days=2)))
        with get_connection() as c:
            identity.flag_identity_unknown(c, [identity.IdentityFinding(self.user, self.card, ["test"])])
        on_log_day = self.at(self.dl + timedelta(days=2))
        self.assertEqual((on_log_day.status, on_log_day.identity_unknown_cards), ("unknown", 1))
        self.assertEqual(self.at(self.dl + timedelta(days=3)).status, "exact")


if __name__ == "__main__":
    unittest.main()

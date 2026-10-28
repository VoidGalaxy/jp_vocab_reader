"""Gate D-2 U6: serving U5-converted incomplete-history cards as scheduled reviews.

Synthetic SQLite only (QueueCase sets a throwaway DATABASE_URL per test before the
app touches a database). U7 (first engine initialisation, first FSRS review,
completion evidence) is not implemented: rating these cards stays refused. This
checks the server queue stage only, not a learnable state in the app.

Run directly:      python tests/test_srs_d2_serve.py
Or via discovery:   python -m unittest discover -s tests
"""

from __future__ import annotations

import sys
import unittest
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_srs_d2_convert import ConvertCase  # noqa: E402
from test_srs_queue import NOW, iso  # noqa: E402

from app.database import get_connection  # noqa: E402
from app.repositories import stats_history_repository  # noqa: E402
from app.repositories.vocab_repository import list_vocab_items  # noqa: E402
from app.srs import identity, migration, queue  # noqa: E402
from app.srs.engine import CardKey, SrsPhase  # noqa: E402
from app.srs.storage import SrsWriteError  # noqa: E402


class ServeCase(ConvertCase):
    def incomplete(self, name, due_text, status="unknown"):
        """A legacy card with past study and no log, converted by the U5 apply path."""
        card = self.personal(name, status=status)
        with get_connection() as c:
            c.execute("UPDATE vocab_items SET last_reviewed_at = ?, correct_count = 2, next_review_at = ? WHERE id = ?",
                      (iso(NOW - timedelta(days=9)), due_text, card))
        result = migration.apply_plan(self.plan(card), f"run-{card}", approved=True)
        self.assertEqual(result[0]["result"], "applied")
        return card

    def incomplete_lexeme(self, deck, name, order, due_text):
        lexeme = self.lexeme(name, deck, order)
        with get_connection() as c:
            c.execute("UPDATE user_word_progress SET srs_engine = 'legacy', srs_config_version = NULL, "
                      "srs_participation = NULL, srs_history_quality = NULL, last_reviewed_at = ?, correct_count = 1, "
                      "next_review_at = ? WHERE user_id = ? AND lexeme_id = ?",
                      (iso(NOW - timedelta(days=9)), due_text, self.user, lexeme))
        result = migration.apply_plan(self.plan(lexeme, kind="lexeme"), f"run-lx-{lexeme}", approved=True)
        self.assertEqual(result[0]["result"], "applied")
        return lexeme

    def category(self, kind, ref, **params):
        result = self.q(**params)
        served = [(i["card_kind"], i["card_id"]) for i in result["items"]]
        return result, (kind, ref) in served

    def everything(self):
        with get_connection() as c:
            out = {}
            for table in ("vocab_items", "user_word_progress", "review_logs", "lexeme_review_logs",
                          "srs_review_receipts", "srs_card_deletions", "srs_migration_snapshots",
                          "srs_migration_runs", "srs_card_identity_flags"):
                out[table] = [tuple(r) for r in c.execute(f"SELECT * FROM {table} ORDER BY 1").fetchall()]
        return out


# ---------------------------------------------------------------------------
class BoundaryTests(ServeCase):
    def test_personal_due_boundaries_and_waiting_time(self):
        before = self.incomplete("before", iso(NOW - timedelta(seconds=1)))
        at = self.incomplete("at", iso(NOW))
        after = self.incomplete("after", iso(NOW + timedelta(seconds=1)))
        result = self.q()
        self.assertEqual(result["counts"]["review_due"], 2)
        self.assertEqual(result["counts"]["pending_later"], 1)
        self.assertEqual([i["card_id"] for i in result["items"]], [before, at])  # oldest due first
        self.assertTrue(all(i["bucket"] == "review_due" and i["is_new"] is False and i["srs"] is None
                            and i["materialized"] is True and isinstance(i["card_version"], int)
                            and i["review"]["path"] == f"/study-items/{i['card_id']}/review" for i in result["items"]))
        self.assertEqual(result["next_due_at"], iso(NOW + timedelta(seconds=1)))  # waiting screen time
        self.assertNotIn(after, [i["card_id"] for i in result["items"]])

    def test_subscribed_due_boundaries_and_waiting_time(self):
        deck = self.shared_deck("s")
        before = self.incomplete_lexeme(deck, "b", 0, iso(NOW - timedelta(seconds=1)))
        at = self.incomplete_lexeme(deck, "a", 1, iso(NOW))
        after = self.incomplete_lexeme(deck, "f", 2, iso(NOW + timedelta(seconds=1)))
        for params in ({}, {"scope": "subscribed_deck", "deck_id": deck}):
            result = self.q(**params)
            self.assertEqual((result["counts"]["review_due"], result["counts"]["pending_later"]), (2, 1), params)
            self.assertEqual(self.keys(result), [("lexeme", before), ("lexeme", at)])
            self.assertEqual(result["next_due_at"], iso(NOW + timedelta(seconds=1)))
            item = result["items"][0]
            self.assertEqual((item["materialized"], item["is_new"], item["review"]["shared_deck_id"]), (True, False, deck))
        self.assertNotIn(("lexeme", after), self.keys(self.q()))

    def test_offsets_are_real_instants(self):
        due_now_kst = self.incomplete("kst-now", "2026-10-09T12:00:00+09:00")  # = NOW (03:00 UTC)
        later_kst = self.incomplete("kst-later", "2026-10-09T12:00:01+09:00")
        earlier_us = self.incomplete("us-earlier", "2026-10-08T21:59:59-05:00")  # 02:59:59 UTC
        result = self.q()
        self.assertEqual([i["card_id"] for i in result["items"]], [earlier_us, due_now_kst])
        self.assertEqual(result["next_due_at"], iso(NOW + timedelta(seconds=1)))
        self.assertEqual(result["items"][0]["sort_key"][1], "2026-10-09T02:59:59+00:00")
        self.assertNotIn(later_kst, [i["card_id"] for i in result["items"]])

    def test_paused_known_and_zero_log_past_card(self):
        paused = self.incomplete("known", iso(NOW - timedelta(days=1)), status="known")
        past = self.incomplete("past", iso(NOW - timedelta(hours=2)))
        intro_before = self.count(NOW)
        result = self.q()
        self.assertEqual(result["counts"]["paused"], 1)
        self.assertEqual(self.keys(result), [("personal", past)])
        self.assertEqual(self.row(paused)["srs_participation"], "paused")  # not re-activated by reading
        self.assertEqual(self.count(NOW), intro_before)  # serving is not a new-word event
        self.assertEqual(self.mark(past), ("before_tracking", "2026-09-30"))


# ---------------------------------------------------------------------------
class MixAndGoalTests(ServeCase):
    def test_mixed_categories_and_sum(self):
        cards = {}
        cards["incomplete_due"] = self.incomplete("inc", iso(NOW - timedelta(hours=1)))
        cards["new"] = self.personal("new")
        self.fsrs("personal", cards["new"])
        cards["fsrs_due"] = self.personal("fsrs-due")
        self.due("personal", cards["fsrs_due"], SrsPhase.REVIEW, NOW - timedelta(hours=3))
        cards["legacy"] = self.personal("legacy")
        cards["flagged"] = self.incomplete("flag", iso(NOW - timedelta(hours=1)))
        with get_connection() as c:
            identity.flag_identity_unknown(c, [identity.IdentityFinding(self.user, cards["flagged"], ["test"])])
        cards["bad_log"] = self.incomplete("bad-log", iso(NOW - timedelta(hours=1)))
        self.raw_log(cards["bad_log"], NOW, time_text="garbage")  # unreadable own log after conversion
        cards["no_due"] = self.incomplete("no-due", iso(NOW - timedelta(hours=1)))
        with get_connection() as c:  # synthetic: a converted card whose effective due went missing
            c.execute("UPDATE vocab_items SET srs_effective_due_at = NULL WHERE id = ?", (cards["no_due"],))
        cards["unconverted_no_due"] = self.personal("never-converted")
        with get_connection() as c:
            c.execute("UPDATE vocab_items SET last_reviewed_at = ?, correct_count = 1, next_review_at = NULL WHERE id = ?",
                      (iso(NOW - timedelta(days=3)), cards["unconverted_no_due"]))
        self.assertEqual(migration.apply_plan(self.plan(cards["unconverted_no_due"]), "run-nd", approved=True)[0]["result"],
                         "blocked")
        cards["fresh_with_foreign_log"] = self.personal("fresh-foreign")
        self.fsrs("personal", cards["fresh_with_foreign_log"], srs_history_quality="fresh")
        self.raw_log(cards["fresh_with_foreign_log"], NOW - timedelta(days=4))
        cards["bad_config"] = self.incomplete("bad-config", iso(NOW - timedelta(hours=1)))
        with get_connection() as c:
            c.execute("UPDATE vocab_items SET srs_config_version = 'other' WHERE id = ?", (cards["bad_config"],))
        result = self.q(limit=100)
        counts = result["counts"]
        self.assertEqual(sum(counts[n] for n in queue.CATEGORIES), counts["total_in_scope"])
        self.assertEqual((counts["review_due"], counts["new_available"]), (2, 1))
        self.assertEqual(counts["not_converted"], 2)  # legacy + the blocked no-schedule card (kept legacy)
        self.assertEqual(counts["blocked_history"], 2)  # identity-unknown + new FSRS card with foreign logs
        self.assertEqual((counts["invalid_state"], counts["missing_due"], counts["unsupported_config"]), (1, 1, 1))
        served = [i["card_id"] for i in result["items"]]
        # The unreadable log makes the account's new count unknown, so new cards pause
        # (existing rule); reviews, including the converted incomplete one, still come.
        self.assertEqual(result["new_goal"]["introduced_today_status"], "unknown")
        self.assertEqual(served, [cards["fsrs_due"], cards["incomplete_due"]])
        with get_connection() as c:
            self.assertIsNone(c.execute("SELECT next_review_at FROM vocab_items WHERE id = ?",
                                        (cards["unconverted_no_due"],)).fetchone()[0])  # never filled with today

    def test_reviews_are_served_when_new_words_are_closed_or_unknown(self):
        due = self.incomplete("due", iso(NOW - timedelta(hours=1)))
        fresh = self.personal("fresh")
        self.fsrs("personal", fresh)
        self.set_mode(self.user, "fsrs", goal=0)
        result = self.q()
        self.assertEqual(self.keys(result), [("personal", due)])
        self.assertEqual(result["new_goal"]["account_remaining"], 0)
        self.set_mode(self.user, "fsrs", goal=20)
        other = self.personal("unreadable")
        self.raw_log(other, NOW, time_text="garbage")  # account new-word count becomes unknown
        result = self.q()
        self.assertEqual(result["new_goal"]["introduced_today_status"], "unknown")
        self.assertEqual(self.keys(result), [("personal", due)])


# ---------------------------------------------------------------------------
class PagingAndMetricsTests(ServeCase):
    def test_exclusion_paging_scopes_and_metrics(self):
        cards = [self.incomplete(f"c{i}", iso(NOW - timedelta(hours=5 - i))) for i in range(3)]
        normal = self.personal("normal")
        self.due("personal", normal, SrsPhase.REVIEW, NOW - timedelta(minutes=30))
        first = self.q(limit=1)
        self.assertEqual(self.keys(first), [("personal", cards[0])])
        skipped = self.q(limit=1, exclude_card=f"personal:{cards[0]}")
        self.assertEqual(self.keys(skipped), [("personal", cards[1])])
        self.assertEqual(skipped["counts"]["excluded_by_request"], 1)
        pages, cursor = [], None
        while True:
            page = self.q(limit=2, **({"cursor": cursor} if cursor else {}))
            pages += self.keys(page)
            cursor = page["next_cursor"]
            if not cursor:
                break
        self.assertEqual(pages, [("personal", c) for c in cards] + [("personal", normal)])
        selected = self.q(mode="selected", card_id=[cards[2], normal])
        self.assertEqual(self.keys(selected), [("personal", cards[2]), ("personal", normal)])
        # Home/stats (account scope), the deck scope and the vocab "지금 복습" filter agree.
        account = self.q()["counts"]
        deck = self.q(scope="personal_deck", deck_id=self.deck)["counts"]
        due_now = lambda c: c["learning_due"] + c["relearning_due"] + c["review_due"]  # noqa: E731
        self.assertEqual(due_now(account), 4)
        self.assertEqual(due_now(deck), 4)
        listed = {i["id"] for i in list_vocab_items(self.user, deck_id=self.deck, due_only=True)}
        self.assertEqual(listed, set(cards) | {normal})

    def test_reads_write_nothing_then_first_review_is_not_new(self):
        card = self.incomplete("due", iso(NOW - timedelta(hours=1)))
        deck = self.shared_deck("s")
        lexeme = self.incomplete_lexeme(deck, "w", 0, iso(NOW - timedelta(hours=1)))
        before, intro = self.everything(), self.count(NOW)
        page = self.q(limit=1)
        self.q(cursor=page["next_cursor"]) if page["next_cursor"] else None
        self.q(scope="personal_deck", deck_id=self.deck)
        list_vocab_items(self.user, deck_id=self.deck, due_only=True)
        stats_history_repository.build_today_seoul(self.user, NOW)
        self.assertEqual(self.everything(), before)
        # U7: rating the converted cards now works and is not a new-word event.
        version = self.row(card)["srs_card_version"]
        self.rate("personal", card, request="00000000-0000-4000-8000-0000000006a1", version=version)
        lexeme_version = self.row(lexeme, "user_word_progress", "lexeme_id")["srs_card_version"]
        self.rate("lexeme", lexeme, request="00000000-0000-4000-8000-0000000006a2", version=lexeme_version, deck=deck)
        self.assertEqual(self.count(NOW), intro)

    def test_legacy_account_unchanged(self):
        card = self.incomplete("due", iso(NOW - timedelta(hours=1)))
        self.set_mode(self.user, "legacy")
        with self.assertRaises(queue.QueueError) as caught:
            self.q()
        self.assertEqual((caught.exception.status_code, caught.exception.code), (409, "srs_mode_not_fsrs"))
        legacy = self.personal("legacy-card")
        listed = {i["id"] for i in list_vocab_items(self.user, deck_id=self.deck, due_only=True)}
        self.assertIn(legacy, listed)  # legacy rule (next_review_at NULL counts as due)
        self.assertIn(card, listed)  # its next_review_at was kept and is due


if __name__ == "__main__":
    unittest.main()

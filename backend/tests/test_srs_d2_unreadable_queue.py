"""U7 follow-up: cards whose own history the review path cannot read (log time,
rating, or an evidence-window FSRS snapshot) are not served by the queue, so they
cannot block a session; readable-but-inconsistent evidence keeps serving.

Synthetic SQLite only (QueueCase sets a throwaway DATABASE_URL per test before the
app touches a database). Damage below edits synthetic rows; the app never does.

Run directly:      python tests/test_srs_d2_unreadable_queue.py
Or via discovery:   python -m unittest discover -s tests
"""

from __future__ import annotations

import json
import sys
import unittest
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_srs_d2_evidence_integrity import IntegrityCase  # noqa: E402
from test_srs_queue import NOW, iso  # noqa: E402

from app.database import get_connection  # noqa: E402
from app.repositories.vocab_repository import list_vocab_items  # noqa: E402
from app.srs import queue  # noqa: E402
from app.srs.engine import SrsPhase  # noqa: E402
from app.srs.storage import SrsWriteError  # noqa: E402

HOUR = timedelta(hours=1)


class UnreadableQueueCase(IntegrityCase):
    def reviewed_converted(self, kind, name, deck=None, order=0):
        """A converted card after its first FSRS review (learning, due ~10 minutes later)."""
        ref = self.converted(kind, name, deck, order)
        self.rate_at(kind, ref, NOW - 2 * HOUR, "good", deck=deck)
        self.now = NOW
        return ref

    def normal_due(self, name, hours_ago=0.5):
        card = self.personal(name, created=NOW - timedelta(days=3))
        self.due("personal", card, SrsPhase.REVIEW, NOW - timedelta(hours=hours_ago))
        return card

    def served(self, **params):
        return self.keys(self.q(**params))

    def damage_snapshot(self, kind, ref):
        self.tamper(kind, self.fsrs_logs(kind, ref)[0]["id"], srs_after_json="{broken")

    def damage_rating(self, kind, ref):
        self.tamper(kind, self.fsrs_logs(kind, ref)[0]["id"], rating="garbage")

    def counts_ok(self, result):
        counts = result["counts"]
        self.assertEqual(sum(counts[n] for n in queue.CATEGORIES), counts["total_in_scope"])
        return counts


# ---------------------------------------------------------------------------
class ExclusionTests(UnreadableQueueCase):
    def check(self, kind, damage, deck=None):
        bad = self.reviewed_converted(kind, f"bad-{kind}-{damage}", deck)
        good = self.normal_due(f"good-{kind}-{damage}")
        bad_key = (kind, bad)
        self.assertEqual(self.served()[0], bad_key)  # the damaged card is first while readable
        getattr(self, f"damage_{damage}")(kind, bad)
        before = self.everything()
        result = self.q()
        self.assertNotIn(bad_key, self.keys(result))
        self.assertEqual(self.keys(result)[0], ("personal", good))
        counts = self.counts_ok(result)
        self.assertEqual(counts["invalid_state"], 1)
        self.assertNotEqual(result["next_due_at"], self.card_row(kind, bad)["srs_effective_due_at"])
        # The review path refuses it the same way (409, nothing written).
        with self.assertRaises(SrsWriteError) as caught:
            self.rate_at(kind, bad, NOW, "good", deck=deck)
        self.assertEqual((caught.exception.code, caught.exception.status_code), ("review_history_unreadable", 409))
        self.assertEqual(self.everything(), before)  # reads and the refusal wrote nothing

    def test_personal_rating(self):
        self.check("personal", "rating")

    def test_personal_snapshot(self):
        self.check("personal", "snapshot")

    def test_subscribed_rating(self):
        self.check("lexeme", "rating", self.shared_deck("s"))

    def test_subscribed_snapshot(self):
        self.check("lexeme", "snapshot", self.shared_deck("s"))

    def test_excluded_pending_card_does_not_drive_the_waiting_time(self):
        ref = self.converted("personal", "pending-bad")
        self.rate_at("personal", ref, NOW, "good")  # learning, due ~10 minutes later: pending
        self.now = NOW
        self.assertIsNotNone(self.q()["next_due_at"])
        self.damage_rating("personal", ref)
        result = self.q()
        self.assertIsNone(result["next_due_at"])  # no waiting screen for a card that cannot be rated
        self.assertEqual(result["counts"]["invalid_state"], 1)

    def test_legacy_log_garbage_rating_on_a_normal_card(self):
        card = self.normal_due("legacy-garbage", hours_ago=2)
        self.raw_log(card, NOW - timedelta(days=20), rating="garbage")
        good = self.normal_due("fine", hours_ago=1)
        self.assertEqual(self.served(), [("personal", good)])

    def test_snapshot_outside_the_window_is_not_examined(self):
        # A legacy log without snapshots before the boundary is normal and must not exclude.
        ref = self.reviewed_converted("personal", "old-legacy")
        self.raw_log(ref, NOW - timedelta(days=40), rating="good")  # earlier than the window: no snapshot
        self.now = NOW + HOUR
        self.assertIn(("personal", ref), self.served())


# ---------------------------------------------------------------------------
class StillServedTests(UnreadableQueueCase):
    def test_readable_inconsistent_evidence_keeps_serving_and_rating(self):
        ref = self.reviewed_converted("personal", "inconsistent")
        log = self.fsrs_logs("personal", ref)[0]
        after = json.loads(log["srs_after_json"])
        after["stability"] += 1.0  # readable, but not what the engine produced
        self.tamper("personal", log["id"], srs_after_json=json.dumps(after))
        self.now = NOW + HOUR
        self.assertIn(("personal", ref), self.served())
        self.rate_at("personal", ref, NOW + HOUR, "good")  # rating still works (evidence incomplete)

    def test_same_instant_spelling_is_readable(self):
        ref = self.reviewed_converted("personal", "spelling")
        log = self.fsrs_logs("personal", ref)[0]
        from datetime import timezone
        self.tamper("personal", log["id"], reviewed_at=(NOW - 2 * HOUR).astimezone(timezone(timedelta(hours=9))).isoformat())
        self.now = NOW + HOUR
        self.assertIn(("personal", ref), self.served())

    def test_new_word_count_is_not_made_unknown_by_rating_or_snapshot_damage(self):
        ref = self.reviewed_converted("personal", "count")
        before = self.count(NOW)
        self.damage_rating("personal", ref)
        self.assertEqual(self.count(NOW).status, before.status)
        self.assertEqual(self.q()["new_goal"]["introduced_today_status"], before.status)


# ---------------------------------------------------------------------------
class ScopeAndPagingTests(UnreadableQueueCase):
    def test_scopes_paging_exclusion_selected_and_metrics(self):
        bad = self.reviewed_converted("personal", "bad")
        self.damage_rating("personal", bad)
        goods = [self.normal_due(f"g{i}", hours_ago=3 - i) for i in range(3)]
        deck = self.shared_deck("s")
        bad_lx = self.reviewed_converted("lexeme", "bad-lx", deck)
        self.damage_snapshot("lexeme", bad_lx)
        expected = [("personal", g) for g in goods]
        first = self.q(limit=2)
        self.assertEqual(self.keys(first), expected[:2])  # page filled with normal cards
        second = self.q(limit=2, cursor=first["next_cursor"])
        self.assertEqual(self.keys(second), expected[2:])
        skipped = self.q(limit=1, exclude_card=f"personal:{goods[0]}")
        self.assertEqual(self.keys(skipped), [("personal", goods[1])])
        selected = self.q(mode="selected", card_id=[bad, goods[2]])
        self.assertEqual(self.keys(selected), [("personal", goods[2])])
        deck_scope = self.q(scope="personal_deck", deck_id=self.deck)
        self.assertEqual(self.counts_ok(deck_scope)["invalid_state"], 1)
        sub_scope = self.q(scope="subscribed_deck", deck_id=deck)
        self.assertEqual((self.counts_ok(sub_scope)["invalid_state"], sub_scope["items"]), (1, []))
        account = self.counts_ok(self.q())
        due_now = account["learning_due"] + account["relearning_due"] + account["review_due"]
        listed = {i["id"] for i in list_vocab_items(self.user, deck_id=self.deck, due_only=True)}
        self.assertEqual(listed, set(goods))
        self.assertEqual(due_now, 3)
        # Other accounts see none of it.
        self.set_mode(self.other, "fsrs")
        self.assertEqual(self.q(user=self.other)["items"], [])

    def test_damage_after_serving_then_409_then_next_card(self):
        bad = self.reviewed_converted("personal", "served-then-damaged")
        good = self.normal_due("next")
        item = self.q(limit=1)["items"][0]
        self.assertEqual(item["card_id"], bad)
        self.damage_snapshot("personal", bad)
        with self.assertRaises(SrsWriteError) as caught:
            self.rate("personal", bad, request=self.req(4242), version=item["card_version"])
        self.assertEqual(caught.exception.code, "review_history_unreadable")
        self.assertEqual(self.served(limit=1), [("personal", good)])

    def test_successful_request_retry_after_damage_returns_the_first_response(self):
        ref = self.converted("personal", "retry")
        first = self.rate("personal", ref, request=self.req(31), version=1)
        self.damage_rating("personal", ref)
        state = self.everything()
        self.assertEqual(self.rate("personal", ref, request=self.req(31), version=1), first)
        self.assertEqual(self.everything(), state)


if __name__ == "__main__":
    unittest.main()

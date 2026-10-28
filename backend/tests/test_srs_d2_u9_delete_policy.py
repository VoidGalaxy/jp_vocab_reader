"""Gate D-2 U9 final delete policy (approved 2026-10-14): when the user explicitly
deletes personal cards, that card's damaged/unknown receipt rows are deleted with it
and its pre-U9 receipts lose their content fields -- all in the delete's transaction.
The general minimization tool and --purge-expired still keep and report such rows.

Synthetic SQLite only (QueueCase sets a throwaway DATABASE_URL per test before the
app touches a database).

Run directly:      python tests/test_srs_d2_u9_delete_policy.py
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
from test_srs_d2_u9_fixes import FixCase  # noqa: E402
from test_srs_queue import NOW, iso  # noqa: E402
import race_support  # noqa: E402

from app.database import get_connection  # noqa: E402
from app.repositories import deck_repository, vocab_repository  # noqa: E402
from app.repositories.deck_repository import create_deck  # noqa: E402
from app.schemas import DeckCreate  # noqa: E402
from app.srs import receipts, reviews, storage  # noqa: E402
from app.srs.storage import SrsWriteError  # noqa: E402

DAY = timedelta(days=1)
DAMAGED = {"broken": "{broken", "array": "[1, 2]", "odd": json.dumps({"request_id": "x", "srs": {}, "mystery": 1})}


class PolicyCase(FixCase):
    def mixed(self, ref, tag):
        """On one card: a pre-U9 receipt, a current receipt and three damaged/unknown ones."""
        old = self.reviewed_old(ref, f"{tag}-old")
        self.assertEqual(self.post("personal", ref, NOW + DAY, f"{tag}-new", self.version("personal", ref)).status_code, 200)
        for name in DAMAGED:
            self.assertEqual(self.post("personal", ref, NOW + 2 * DAY, f"{tag}-{name}",
                                       self.version("personal", ref)).status_code, 200)
        with get_connection() as c:
            for name, text in DAMAGED.items():
                c.execute("UPDATE srs_review_receipts SET response_json = ? WHERE request_id = ?", (text, f"{tag}-{name}"))
        return old

    def table(self, name):
        with get_connection() as c:
            return [tuple(r) for r in c.execute(f"SELECT * FROM {name} ORDER BY 1")]

    def check_after(self, tag, old, new_before, logs_before):
        self.assertEqual(self.stored(f"{tag}-old"), {k: v for k, v in old.items() if k not in receipts.CONTENT_FIELDS})
        self.assertEqual(self.receipt(f"{tag}-new"), new_before)  # current receipt untouched
        for name in DAMAGED:
            self.assertIsNone(self.receipt(f"{tag}-{name}"))  # only rows that could not be minimized
        self.assertEqual(self.table("review_logs"), logs_before)  # logs, history, evidence untouched

    def foreign_damage(self):
        """Damaged receipts that must survive: another card, another account, a subscribed one."""
        other_card = self.fresh_personal("other-card")
        self.post("personal", other_card, NOW, "keep-card", 0)
        deck = self.shared_deck("s")
        lexeme = self.lexeme("同", deck, 0, progress=False)
        self.post("lexeme", lexeme, NOW, "keep-lexeme", None, deck)
        with get_connection() as c:
            for request in ("keep-card", "keep-lexeme"):
                c.execute("UPDATE srs_review_receipts SET response_json = '{broken' WHERE request_id = ?", (request,))
        return {r: self.receipt(r) for r in ("keep-card", "keep-lexeme")}

    def add_other_account(self, ref):
        with get_connection() as c:
            c.execute("INSERT INTO srs_review_receipts (user_id, request_id, card_kind, card_ref, request_hash, "
                      "response_json, review_log_id, created_at) VALUES (?, 'theirs', 'personal', ?, 'h', '{broken', NULL, ?)",
                      (self.other, ref, iso(NOW)))
            return dict(c.execute("SELECT * FROM srs_review_receipts WHERE request_id = 'theirs'").fetchone())


# ---------------------------------------------------------------------------
class DeleteTests(PolicyCase):
    def test_word_delete_with_mixed_receipts(self):
        ref = self.fresh_personal("mix")
        old = self.mixed(ref, "w")
        new_before = self.receipt("w-new")
        foreign = self.foreign_damage()
        theirs = self.add_other_account(ref)
        logs = self.table("review_logs")
        response = self.client.delete(f"/vocab-items/{ref}", headers=self.headers)
        self.assertEqual(response.status_code, 204)
        self.check_after("w", old, new_before, logs)
        for request, row in foreign.items():
            self.assertEqual(self.receipt(request), row)
        with get_connection() as c:
            self.assertEqual(dict(c.execute("SELECT * FROM srs_review_receipts WHERE request_id = 'theirs'").fetchone()), theirs)
            self.assertEqual(c.execute("SELECT COUNT(*) FROM srs_card_deletions WHERE card_ref = ?", (ref,)).fetchone()[0], 1)
        state = self.counts()
        for request in ("w-old", "w-new", "w-broken"):
            retry = self.post("personal", ref, NOW + 3 * DAY, request, 0)
            self.assertEqual(retry.status_code, 404)
            self.assertNotIn("뜻", retry.text)
        self.assertEqual(self.counts(), state)

    def test_deck_delete_with_mixed_receipts(self):
        deck = create_deck(self.user, DeckCreate(name="gone"))[0]["id"]
        cards = [self.card_in(deck, f"g{i}") for i in range(2)]
        olds = [self.mixed(ref, f"d{i}") for i, ref in enumerate(cards)]
        news = [self.receipt(f"d{i}-new") for i in range(2)]
        foreign = self.foreign_damage()
        logs = self.table("review_logs")
        response = self.client.delete(f"/decks/{deck}", headers=self.headers)
        self.assertEqual((response.status_code, response.json()["deleted_vocab_count"]), (200, 2))
        for i in range(2):
            self.check_after(f"d{i}", olds[i], news[i], logs)
        for request, row in foreign.items():
            self.assertEqual(self.receipt(request), row)

    def test_missing_or_foreign_card_touches_nothing(self):
        mine = self.fresh_personal("mine")
        self.post("personal", mine, NOW, "mine-1", 0)
        with get_connection() as c:  # a damaged receipt naming an id that is not (or no longer) a card
            c.execute("INSERT INTO srs_review_receipts (user_id, request_id, card_kind, card_ref, request_hash, "
                      "response_json, review_log_id, created_at) VALUES (?, 'ghost', 'personal', 999999, 'h', '{broken', NULL, ?)",
                      (self.user, iso(NOW)))
        foreign_card = self.personal("theirs", user=self.other)
        before = self.everything()
        self.assertFalse(vocab_repository.delete_vocab_item(self.user, 999999))
        self.assertFalse(vocab_repository.delete_vocab_item(self.user, foreign_card))  # not this account's card
        self.assertEqual(self.client.delete(f"/vocab-items/{foreign_card}", headers=self.headers).status_code, 404)
        self.assertEqual(self.everything(), before)

    def test_failure_injection_rolls_everything_back(self):
        class Boom(Exception):
            pass

        for where in ("ledger", "receipt", "card"):
            with self.subTest(where=where):
                ref = self.fresh_personal(f"f-{where}")
                self.mixed(ref, f"f-{where}")
                before = self.everything()
                if where == "ledger":
                    patch = mock.patch("app.srs.identity.record_personal_deletions", side_effect=Boom())
                elif where == "receipt":  # after the damaged rows were already deleted
                    real = receipts.canonical_json
                    patch = mock.patch.object(receipts, "canonical_json", side_effect=Boom())
                else:
                    real_record = __import__("app.srs.identity", fromlist=["x"]).record_personal_deletions

                    def then_fail(*a, **k):
                        real_record(*a, **k)
                        raise Boom()

                    patch = mock.patch("app.srs.identity.record_personal_deletions", then_fail)
                with patch:
                    with self.assertRaises(Boom):
                        vocab_repository.delete_vocab_item(self.user, ref)
                self.assertEqual(self.everything(), before)  # damaged rows restored, nothing half-done
        deck = create_deck(self.user, DeckCreate(name="fail-deck"))[0]["id"]
        card = self.card_in(deck, "fd")
        self.mixed(card, "fd")
        before = self.everything()
        with mock.patch("app.srs.identity.record_personal_deletions", side_effect=Boom()):
            with self.assertRaises(Boom):
                deck_repository.delete_deck_with_items(self.user, deck)
        self.assertEqual(self.everything(), before)

    def test_cas_mismatch_rolls_back(self):
        ref = self.fresh_personal("cas")
        self.mixed(ref, "cas")
        before = self.everything()
        real = receipts.classify_response
        holder = {"done": False}

        def changing(text):
            result = real(text)
            if not holder["done"] and result[0] in ("unreadable", "unknown"):
                holder["done"] = True
                holder["conn"].execute("UPDATE srs_review_receipts SET response_json = response_json || ' ' "
                                       "WHERE request_id = 'cas-broken'")
            return result

        real_strip = receipts.strip_card_receipts

        def strip(connection, *a, **k):
            holder["conn"] = connection
            return real_strip(connection, *a, **k)

        with mock.patch.object(receipts, "classify_response", changing), mock.patch.object(receipts, "strip_card_receipts", strip):
            with self.assertRaises(SrsWriteError) as caught:
                vocab_repository.delete_vocab_item(self.user, ref)
        self.assertEqual(caught.exception.code, "receipt_content_unverified")
        self.assertEqual(self.everything(), before)


# ---------------------------------------------------------------------------
class GeneralToolTests(PolicyCase):
    def test_tool_and_purge_still_keep_and_report_damaged_rows(self):
        ref = self.fresh_personal("tool")
        self.mixed(ref, "t")
        with get_connection() as c:
            c.execute("UPDATE srs_review_receipts SET created_at = ?", (iso(NOW - 30 * DAY),))
        damaged = {name: self.receipt(f"t-{name}") for name in DAMAGED}
        with get_connection() as connection:
            report = receipts.minimize_receipts(connection, self.user, NOW, apply=True, purge_expired=True,
                                                lock=storage.begin_card_write)
        for name, row in damaged.items():
            self.assertEqual(self.receipt(f"t-{name}"), row)  # kept exactly as it was
        self.assertEqual(report["unreadable_json"], [damaged["broken"]["id"]])
        self.assertEqual(sorted(report["unknown_format"]), sorted([damaged["array"]["id"], damaged["odd"]["id"]]))
        self.assertEqual(len(report["purged"]), 2)  # the recognised old and new receipts only


# ---------------------------------------------------------------------------
class RaceTests(PolicyCase):
    def run_race(self, first, second, jobs, block_target, block_name):
        entered, release = threading.Event(), threading.Event()
        real = getattr(block_target, block_name)

        def slow(*a, **k):
            result = real(*a, **k)
            if not entered.is_set():
                entered.set()
                self.assertTrue(release.wait(15))
            return result

        with race_support.LockProbe() as probe, mock.patch.object(block_target, block_name, slow):
            a = race_support.start(first, jobs[first])
            self.assertTrue(entered.wait(15))
            b = race_support.start(second, jobs[second])
            self.assertTrue(probe.wait("waiting", second))
            time.sleep(0.3)
            self.assertNotIn(("acquired", second), probe.events)
            probe.mark("released", first)
            release.set()
            results = {first: race_support.finish(self, a), second: race_support.finish(self, b)}
        probe.assert_serialized(self, first, second)
        return results

    def retry_job(self, ref, request):
        def call():
            with mock.patch.object(reviews, "now_utc", return_value=NOW + 3 * DAY):
                return vocab_repository.record_review(self.user, ref, "good", request_id=request,
                                                      expected_card_version=0, session_id="s1")
        return call

    def tool_job(self):
        def call():
            with get_connection() as connection:
                return receipts.minimize_receipts(connection, self.user, NOW, apply=True,
                                                  lock=lambda c, u: storage.begin_card_write(c, u))
        return call

    def test_delete_and_retry_both_orders(self):
        for first in ("delete", "retry"):
            with self.subTest(first=first):
                ref = self.fresh_personal(f"r-{first}")
                self.mixed(ref, f"r-{first}")
                logs = self.table("review_logs")
                jobs = {"delete": lambda: vocab_repository.delete_vocab_item(self.user, ref),
                        "retry": self.retry_job(ref, f"r-{first}-old")}
                target = (receipts, "strip_card_receipts") if first == "delete" else (receipts, "receipt_age_status")
                second = "retry" if first == "delete" else "delete"
                results = self.run_race(first, second, jobs, *target)
                self.assertTrue(results["delete"])
                if first == "delete":
                    self.assertIsNone(results["retry"])  # deleted before the retry: 404 at the URL
                else:
                    self.assertIn(f"r-{first}-뜻", json.dumps(results["retry"], ensure_ascii=False))
                self.assertEqual(self.table("review_logs"), logs)  # no review added
                for name in DAMAGED:
                    self.assertIsNone(self.receipt(f"r-{first}-{name}"))

    def test_delete_and_tool_both_orders(self):
        for first in ("delete", "tool"):
            with self.subTest(first=first):
                ref = self.fresh_personal(f"t-{first}")
                old = self.mixed(ref, f"t-{first}")
                jobs = {"delete": lambda: vocab_repository.delete_vocab_item(self.user, ref), "tool": self.tool_job()}
                target = (receipts, "strip_card_receipts") if first == "delete" else (receipts, "classify_response")
                second = "tool" if first == "delete" else "delete"
                results = self.run_race(first, second, jobs, *target)
                self.assertTrue(results["delete"])
                report = results["tool"]
                if first == "tool":  # the tool kept and reported the damaged rows; the delete removed them after
                    self.assertEqual(len(report["unreadable_json"]) + len(report["unknown_format"]), 3)
                else:  # the delete ran first: nothing of this card is left for the tool
                    self.assertEqual((report["unreadable_json"], report["unknown_format"]), ([], []))
                self.assertEqual(self.stored(f"t-{first}-old"),
                                 {k: v for k, v in old.items() if k not in receipts.CONTENT_FIELDS})
                for name in DAMAGED:
                    self.assertIsNone(self.receipt(f"t-{first}-{name}"))


if __name__ == "__main__":
    unittest.main()

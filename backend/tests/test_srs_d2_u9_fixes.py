"""Gate D-2 U9 review fixes.

P1: deleting a word or a deck strips the card-content copy out of that card's pre-U9
    receipts in the same transaction (account write lock -> receipts -> ledger ->
    delete). Damaged/unknown receipts of the deleted card stop the delete (no repair,
    no deletion, no silent copy) until a policy is decided.
P2: --purge-expired only deletes expired receipts whose response format is
    recognised; damaged or unknown ones are reported and kept.
OpenAPI: the two review URLs document the legacy, FSRS and pre-U9 replay shapes.

Synthetic SQLite only (QueueCase sets a throwaway DATABASE_URL per test before the
app touches a database).

Run directly:      python tests/test_srs_d2_u9_fixes.py
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
from test_srs_d2_u9_receipts import U9Case  # noqa: E402
from test_srs_queue import NOW, iso  # noqa: E402
import race_support  # noqa: E402

from app import main, schemas  # noqa: E402
from app.database import get_connection  # noqa: E402
from app.repositories import deck_repository, vocab_repository  # noqa: E402
from app.repositories.deck_repository import create_deck  # noqa: E402
from app.repositories.vocab_repository import create_or_update_vocab_item  # noqa: E402
from app.schemas import DeckCreate, VocabItemCreate  # noqa: E402
from app.srs import receipts, reviews, storage  # noqa: E402
from app.srs.storage import SrsWriteError  # noqa: E402

DAY = timedelta(days=1)


class FixCase(U9Case):
    def card_in(self, deck, name):
        return create_or_update_vocab_item(self.user, VocabItemCreate(
            surface=name, base_form=name, reading=f"{name}-よみ", meaning_ko=f"{name}-뜻", status="unknown",
            deck_id=deck, example_sentence=f"{name}の例文"))[0]["id"]

    def reviewed_old(self, ref, request):
        self.assertEqual(self.post("personal", ref, NOW, request, self.version("personal", ref)).status_code, 200)
        return self.old_personal_receipt(ref, request)

    def stored(self, request):
        return json.loads(self.receipt(request)["response_json"])

    def receipt_rows(self):
        with get_connection() as c:
            return [tuple(r) for r in c.execute("SELECT * FROM srs_review_receipts ORDER BY id")]


# ---------------------------------------------------------------------------
class DeleteTests(FixCase):
    def assert_stripped(self, request, old):
        row = self.receipt(request)
        stored = json.loads(row["response_json"])
        self.assertFalse(set(stored) & receipts.CONTENT_FIELDS)
        self.assertEqual(stored, {k: v for k, v in old.items() if k not in receipts.CONTENT_FIELDS})
        return row

    def test_word_delete_strips_only_that_cards_old_receipts(self):
        ref = self.fresh_personal("del")
        old = self.reviewed_old(ref, "del-1")
        keep = self.fresh_personal("keep")
        keep_old = self.reviewed_old(keep, "keep-1")
        new_ref = self.fresh_personal("new")
        self.post("personal", new_ref, NOW, "new-1", 0)
        new_before = self.receipt("new-1")
        deck = self.shared_deck("s")
        lexeme = self.lexeme("同", deck, 0, progress=False)  # a subscribed receipt with the same numeric id
        self.post("lexeme", lexeme, NOW, "lx-1", None, deck)
        lexeme_before = self.receipt("lx-1")
        before = self.receipt("del-1")
        self.assertTrue(vocab_repository.delete_vocab_item(self.user, ref))
        row = self.assert_stripped("del-1", old)
        for column in ("request_hash", "review_log_id", "created_at", "card_ref", "card_kind"):
            self.assertEqual(row[column], before[column])
        self.assertIn("keep-뜻", self.receipt("keep-1")["response_json"])  # other card untouched
        self.assertEqual(self.stored("keep-1"), keep_old)
        self.assertEqual(self.receipt("new-1"), new_before)  # new minimal receipt untouched
        self.assertEqual(self.receipt("lx-1"), lexeme_before)  # subscribed receipt untouched
        state = self.counts()
        response = self.post("personal", ref, NOW, "del-1", 0)
        self.assertEqual(response.status_code, 404)
        self.assertNotIn("뜻", response.text)
        self.assertEqual(self.counts(), state)

    def test_deck_delete_strips_every_card_of_the_deck(self):
        deck = create_deck(self.user, DeckCreate(name="to-delete"))[0]["id"]
        cards = [self.card_in(deck, f"d{i}") for i in range(3)]
        olds = [self.reviewed_old(ref, f"deck-{i}") for i, ref in enumerate(cards)]
        outside = self.fresh_personal("outside")
        outside_old = self.reviewed_old(outside, "outside-1")
        result = deck_repository.delete_deck_with_items(self.user, deck)
        self.assertEqual(result["deleted_vocab_count"], 3)
        for i, old in enumerate(olds):
            self.assert_stripped(f"deck-{i}", old)
        self.assertEqual(self.stored("outside-1"), outside_old)

    def test_other_account_untouched(self):
        ref = self.fresh_personal("mine")
        self.reviewed_old(ref, "mine-1")
        with get_connection() as c:  # another account's receipt that names the same card id
            c.execute("INSERT INTO srs_review_receipts (user_id, request_id, card_kind, card_ref, request_hash, "
                      "response_json, review_log_id, created_at) SELECT ?, 'theirs-1', card_kind, card_ref, request_hash, "
                      "response_json, review_log_id, created_at FROM srs_review_receipts WHERE request_id = 'mine-1'",
                      (self.other,))
        theirs = self.receipt_rows()[-1]
        vocab_repository.delete_vocab_item(self.user, ref)
        self.assertEqual(self.receipt_rows()[-1], theirs)

    def test_failure_rolls_back_everything(self):
        ref = self.fresh_personal("fail")
        self.reviewed_old(ref, "fail-1")
        state = self.everything()
        real = vocab_repository.get_connection

        class Boom(Exception):
            pass

        with mock.patch("app.srs.identity.record_personal_deletions", side_effect=Boom()):
            with self.assertRaises(Boom):
                vocab_repository.delete_vocab_item(self.user, ref)
        self.assertEqual(self.everything(), state)  # receipt content, ledger and card all as before
        self.assertIs(vocab_repository.get_connection, real)
        deck = create_deck(self.user, DeckCreate(name="fail-deck"))[0]["id"]
        card = self.card_in(deck, "fd")
        self.reviewed_old(card, "fd-1")
        state = self.everything()
        with mock.patch("app.srs.identity.record_personal_deletions", side_effect=Boom()):
            with self.assertRaises(Boom):
                deck_repository.delete_deck_with_items(self.user, deck)
        self.assertEqual(self.everything(), state)

    def test_damaged_or_unknown_receipt_row_goes_with_the_deleted_card(self):
        # Changed expectation (REPORT 25, approved 2026-10-14): formerly the delete was
        # refused with 409 receipt_content_unverified; now, for an explicit card delete
        # only, a receipt that cannot be minimized is deleted with its card.
        for name, text in (("broken", "{broken"), ("array", "[1, 2]"), ("odd", json.dumps({"request_id": "x", "srs": {}, "mystery": 1}))):
            with self.subTest(name=name):
                ref = self.fresh_personal(f"blk-{name}")
                self.reviewed_old(ref, f"blk-{name}")
                with get_connection() as c:
                    c.execute("UPDATE srs_review_receipts SET response_json = ? WHERE request_id = ?", (text, f"blk-{name}"))
                response = self.client.delete(f"/vocab-items/{ref}", headers=self.headers)
                self.assertEqual(response.status_code, 204)
                self.assertIsNone(self.receipt(f"blk-{name}"))

    def test_race_delete_and_retry(self):
        for first in ("delete", "retry"):
            with self.subTest(first=first):
                ref = self.fresh_personal(f"race-{first}")
                request = f"race-{first}"
                self.reviewed_old(ref, request)
                state = self.counts()
                entered, release = threading.Event(), threading.Event()
                target, name = ((receipts, "strip_card_receipts") if first == "delete" else (receipts, "receipt_age_status"))
                real = getattr(target, name)

                def slow(*a, **k):
                    result = real(*a, **k)
                    if not entered.is_set():
                        entered.set()
                        self.assertTrue(release.wait(15))
                    return result

                def retry():
                    with mock.patch.object(reviews, "now_utc", return_value=NOW + DAY):
                        return vocab_repository.record_review(self.user, ref, "good", request_id=request,
                                                              expected_card_version=0, session_id="s1")

                with race_support.LockProbe() as probe, mock.patch.object(target, name, slow):
                    jobs = {"delete": lambda: vocab_repository.delete_vocab_item(self.user, ref), "retry": retry}
                    a = race_support.start(first, jobs[first])
                    self.assertTrue(entered.wait(15))
                    second = "retry" if first == "delete" else "delete"
                    b = race_support.start(second, jobs[second])
                    self.assertTrue(probe.wait("waiting", second))
                    time.sleep(0.3)
                    self.assertNotIn(("acquired", second), probe.events)
                    probe.mark("released", first)
                    release.set()
                    results = {first: race_support.finish(self, a), second: race_support.finish(self, b)}
                probe.assert_serialized(self, first, second)
                self.assertTrue(results["delete"])
                if first == "delete":
                    self.assertIsNone(results["retry"])  # card gone: 404 at the URL, no content
                else:
                    self.assertIn(f"race-{first}-뜻", json.dumps(results["retry"], ensure_ascii=False))
                self.assertEqual(self.counts(), state)  # no review added
                self.assertFalse(set(self.stored(request)) & receipts.CONTENT_FIELDS)

    def test_race_delete_and_tool(self):
        ref = self.fresh_personal("race-tool")
        self.reviewed_old(ref, "race-tool")
        entered, release = threading.Event(), threading.Event()
        real = receipts.strip_card_receipts

        def slow(*a, **k):
            result = real(*a, **k)
            entered.set()
            self.assertTrue(release.wait(15))
            return result

        def tool():
            with get_connection() as connection:
                return receipts.minimize_receipts(connection, self.user, NOW, apply=True,
                                                  lock=lambda c, u: storage.begin_card_write(c, u))

        with race_support.LockProbe() as probe, mock.patch.object(receipts, "strip_card_receipts", slow):
            delete = race_support.start("delete", lambda: vocab_repository.delete_vocab_item(self.user, ref))
            self.assertTrue(entered.wait(15))
            t = race_support.start("tool", tool)
            self.assertTrue(probe.wait("waiting", "tool"))
            probe.mark("released", "delete")
            release.set()
            self.assertTrue(race_support.finish(self, delete))
            report = race_support.finish(self, t)
        probe.assert_serialized(self, "delete", "tool")
        self.assertEqual((report["stripped"], report["changed_concurrently"]), ([], []))
        self.assertFalse(set(self.stored("race-tool")) & receipts.CONTENT_FIELDS)


# ---------------------------------------------------------------------------
class PurgeFormatTests(FixCase):
    def test_purge_only_recognised_expired_rows(self):
        rows = {}
        for name, text, created in (
                ("ok-old", None, NOW - 30 * DAY), ("ok-new", None, NOW), ("broken", "{broken", NOW - 30 * DAY),
                ("array", "[1, 2]", NOW - 30 * DAY), ("odd", json.dumps({"request_id": "x", "srs": {}, "mystery": 1}), NOW - 30 * DAY),
                ("bad-time", None, "garbage"), ("naive", None, "2026-09-01T00:00:00"), ("future", None, NOW + 3 * DAY)):
            ref = self.fresh_personal(name)
            self.post("personal", ref, NOW, name, 0)
            with get_connection() as c:
                if text is not None:
                    c.execute("UPDATE srs_review_receipts SET response_json = ? WHERE request_id = ?", (text, name))
                c.execute("UPDATE srs_review_receipts SET created_at = ? WHERE request_id = ?",
                          (created if isinstance(created, str) else iso(created), name))
            rows[name] = self.receipt(name)
        before = self.everything()
        with get_connection(read_only=True) as connection:
            dry = receipts.minimize_receipts(connection, self.user, NOW, purge_expired=True)
        self.assertEqual(self.everything(), before)  # dry-run writes nothing
        self.assertEqual(dry["purged"], [])
        with get_connection() as connection:
            report = receipts.minimize_receipts(connection, self.user, NOW, apply=True, purge_expired=True,
                                                lock=storage.begin_card_write)
        ids = {k: v["id"] for k, v in rows.items()}
        self.assertEqual(report["purged"], [ids["ok-old"]])
        self.assertEqual(report["unreadable_json"], [ids["broken"]])
        self.assertEqual(sorted(report["unknown_format"]), sorted([ids["array"], ids["odd"]]))
        self.assertEqual(sorted(report["unreadable_time"]), sorted([ids["bad-time"], ids["naive"], ids["future"]]))
        for name in rows:
            if name != "ok-old":
                self.assertEqual(self.receipt(name), rows[name], name)  # kept exactly as it was
        self.assertIsNone(self.receipt("ok-old"))
        self.assertNotIn("뜻", json.dumps(report, ensure_ascii=False))

    def test_purge_cas_skips_a_row_changed_after_reading(self):
        ref = self.fresh_personal("cas")
        self.post("personal", ref, NOW, "cas-1", 0)
        with get_connection() as c:
            c.execute("UPDATE srs_review_receipts SET created_at = ? WHERE request_id = 'cas-1'", (iso(NOW - 30 * DAY),))
        real = receipts.classify_response
        holder = {}

        def changing(text):
            result = real(text)
            if "done" not in holder:
                holder["done"] = True
                holder["conn"].execute("UPDATE srs_review_receipts SET response_json = response_json || ' ' "
                                       "WHERE request_id = 'cas-1'")
            return result

        with get_connection() as connection:
            holder["conn"] = connection
            with mock.patch.object(receipts, "classify_response", changing):
                report = receipts.minimize_receipts(connection, self.user, NOW, apply=True, purge_expired=True,
                                                    lock=storage.begin_card_write)
        self.assertEqual(report["purged"], [])
        self.assertEqual(report["changed_concurrently"], [self.receipt("cas-1")["id"]])

    def test_purge_rerun_and_resume(self):
        for i in range(3):
            ref = self.fresh_personal(f"r{i}")
            self.post("personal", ref, NOW, f"r{i}", 0)
        with get_connection() as c:
            c.execute("UPDATE srs_review_receipts SET created_at = ?", (iso(NOW - 30 * DAY),))
        real = receipts.canonical_json
        with get_connection() as connection:
            first = receipts.minimize_receipts(connection, self.user, NOW, apply=True, purge_expired=True,
                                               batch_size=1, lock=storage.begin_card_write)
        self.assertEqual(len(first["purged"]), 3)
        with get_connection() as connection:
            again = receipts.minimize_receipts(connection, self.user, NOW, apply=True, purge_expired=True,
                                               lock=storage.begin_card_write)
        self.assertEqual(again["purged"], [])
        self.assertIs(receipts.canonical_json, real)


# ---------------------------------------------------------------------------
class OpenApiTests(FixCase):
    def schema(self):
        return self.client.get("/openapi.json").json()

    def response_refs(self, path):
        content = self.schema()["paths"][path]["post"]["responses"]["200"]["content"]["application/json"]["schema"]
        options = content.get("anyOf") or content.get("oneOf") or [content]
        return {o["$ref"].rsplit("/", 1)[-1] for o in options}

    def test_documented_shapes(self):
        self.assertEqual(self.response_refs("/study-items/{item_id}/review"),
                         {"PersonalReviewResponse", "FsrsReviewResponse", "MinimizedPersonalReceiptReplay"})
        self.assertEqual(self.response_refs("/shared-decks/{shared_deck_id}/words/{lexeme_id}/review"),
                         {"LexemeReviewResponse", "FsrsReviewResponse"})
        fsrs = self.schema()["components"]["schemas"]["FsrsReviewResponse"]
        self.assertEqual(set(fsrs["required"]), {
            "card_kind", "card_id", "request_id", "accepted_at", "server_now", "rating", "correct_count",
            "wrong_count", "review_level", "next_review_at", "last_reviewed_at", "completed",
            "completion_metric_version", "srs"})
        self.assertFalse(set(fsrs["properties"]) & receipts.CONTENT_FIELDS)

    def test_actual_responses_match_the_models(self):
        ref = self.fresh_personal("api")
        first = self.post("personal", ref, NOW, "api-1", 0)
        again = self.post("personal", ref, NOW + DAY, "api-1", 0)
        self.assertEqual(first.content, again.content)
        schemas.FsrsReviewResponse.model_validate_json(first.content)  # extra fields forbidden
        deck = self.shared_deck("s")
        lexeme = self.lexeme("api", deck, 0, progress=False)
        schemas.FsrsReviewResponse.model_validate_json(self.post("lexeme", lexeme, NOW, "api-2", None, deck).content)
        # Pre-U9 replay before and after minimization.
        old_ref = self.fresh_personal("api-old")
        self.reviewed_old(old_ref, "api-old")
        schemas.PersonalReviewResponse.model_validate_json(self.post("personal", old_ref, NOW, "api-old", 0).content)
        with get_connection() as connection:
            receipts.minimize_receipts(connection, self.user, NOW, apply=True, lock=storage.begin_card_write)
        replay = self.post("personal", old_ref, NOW, "api-old", 0)
        schemas.MinimizedPersonalReceiptReplay.model_validate_json(replay.content)
        self.assertFalse(set(json.loads(replay.content)) & receipts.CONTENT_FIELDS)
        # Legacy unchanged.
        self.set_mode(self.user, "legacy")
        item = self.personal("legacy-api")
        legacy = self.client.post(f"/study-items/{item}/review", headers=self.headers, json={"rating": "good"})
        schemas.PersonalReviewResponse.model_validate_json(legacy.content)
        self.assertNotIn("srs", legacy.json())


if __name__ == "__main__":
    unittest.main()

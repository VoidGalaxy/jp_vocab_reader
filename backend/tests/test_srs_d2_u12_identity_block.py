"""Gate D-2 U12 (approved 2026-10-18, U12_IDENTITY_PROPOSAL.md 7): a personal card
flagged identity unknown refuses every new review write with 409 card_identity_unknown,
whatever its engine (legacy / FSRS) and the account mode (legacy / fsrs), with or
without a request_id. Normal legacy cards, unconverted cards and subscribed words are
not affected; content edits and the confirmed delete stay as they were.

Cards are flagged through the real path (identity.scan_identity + flag_identity_unknown).
Synthetic SQLite only (QueueCase sets a throwaway DATABASE_URL per test).

Run directly:      python tests/test_srs_d2_u12_identity_block.py
Or via discovery:   python -m unittest discover -s tests
"""

from __future__ import annotations

import sys
import threading
import time
import unittest
from datetime import timedelta
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_srs_d2_u11_plain_evidence import PlainCase  # noqa: E402
from test_srs_queue import NOW, iso  # noqa: E402
import race_support  # noqa: E402

from app.database import get_connection  # noqa: E402
from app.repositories import vocab_repository  # noqa: E402
from app.srs import identity, reviews, storage  # noqa: E402
from app.srs.storage import SrsWriteError  # noqa: E402

DAY = timedelta(days=1)


class BlockCase(PlainCase):
    def older_log(self, ref):
        """A log older than the card itself: what the identity scan reports."""
        with get_connection() as c:
            c.execute("UPDATE vocab_items SET created_at = ? WHERE id = ?", (iso(NOW - 2 * DAY), ref))
            c.execute("INSERT INTO review_logs (user_id, vocab_item_id, rating, reviewed_at, previous_review_level, "
                      "next_review_level, next_review_at) VALUES (?, ?, 'good', ?, 0, 1, ?)",
                      (self.user, ref, iso(NOW - 30 * DAY), iso(NOW)))

    def flag(self):
        with get_connection() as c:
            return identity.flag_identity_unknown(c, identity.scan_identity(c).findings)

    def legacy_card(self, name):
        ref = self.content_card(name)  # legacy engine, in the FSRS account
        self.older_log(ref)
        return ref

    def fsrs_card(self, name):
        ref = self.fresh_personal(name)  # FSRS from its first review
        self.review("personal", ref, None, NOW, "good")
        self.older_log(ref)
        return ref

    def send(self, ref, body):
        with mock.patch.object(reviews, "now_utc", return_value=NOW + DAY), \
                mock.patch.object(vocab_repository, "now_utc", return_value=NOW + DAY):
            return self.client.post(f"/study-items/{ref}/review", headers=self.headers, json=body)

    def bodies(self, ref, tag):
        version = self.card_row("personal", ref)["srs_card_version"]
        return {"with_request_id": {"rating": "good", "request_id": f"blk-{tag}-{ref}", "session_id": "s1",
                                    "expected_card_version": version},
                "without_request_id": {"rating": "good"}}

    def state(self):
        out = self.everything()
        with get_connection() as c:
            out["flags"] = [tuple(r) for r in c.execute("SELECT * FROM srs_card_identity_flags ORDER BY 1")]
        return out


class BlockTests(BlockCase):
    def test_every_engine_mode_and_request_shape(self):
        cards = {"legacy": self.legacy_card("blk-legacy"), "fsrs": self.fsrs_card("blk-fsrs")}
        self.assertEqual(self.flag(), 2)
        for mode in ("fsrs", "legacy"):
            self.set_mode(self.user, mode)
            for engine, ref in cards.items():
                for shape, body in self.bodies(ref, f"{mode}-{engine}").items():
                    with self.subTest(mode=mode, engine=engine, shape=shape):
                        before = self.state()
                        response = self.send(ref, body)
                        self.assertEqual((response.status_code, response.json()["detail"]), (409, "card_identity_unknown"))
                        self.assertNotIn("뜻", response.text)
                        self.assertNotIn(f"{'blk'}", response.json()["detail"])
                        self.assertEqual(self.state(), before)  # card, version, logs, receipts, completion, flag
        self.set_mode(self.user, "fsrs")

    def test_success_before_the_flag_is_kept_and_its_retry_is_refused(self):
        ref = self.fresh_personal("blk-retry")
        self.review("personal", ref, None, NOW, "good")
        body = self.bodies(ref, "retry")["with_request_id"]
        first = self.send(ref, body)
        self.assertEqual(first.status_code, 200)
        logs = len(self.logs_of("personal", ref))
        self.older_log(ref)
        self.flag()
        before = self.state()
        again = self.send(ref, body)  # the stored answer predates the flag: never replayed
        self.assertEqual((again.status_code, again.json()["detail"]), (409, "card_version_conflict"))
        self.assertEqual(self.state(), before)
        fresh = self.send(ref, self.bodies(ref, "after")["with_request_id"])
        self.assertEqual((fresh.status_code, fresh.json()["detail"]), (409, "card_identity_unknown"))
        self.assertEqual(len(self.logs_of("personal", ref)), logs + 1)  # the old log and the earlier success stay

    def test_not_affected_cards_and_other_account(self):
        flagged = self.legacy_card("blk-flagged")
        self.flag()
        plain = self.content_card("blk-plain")  # normal legacy card, not converted
        self.assertEqual(self.send(plain, self.bodies(plain, "plain")["with_request_id"]).status_code, 200)
        self.set_mode(self.user, "legacy")
        self.assertEqual(self.send(plain, {"rating": "good"}).status_code, 200)
        self.set_mode(self.user, "fsrs")
        new = self.fresh_personal("blk-new")
        self.assertEqual(self.review("personal", new, None, NOW + DAY, "good")["card_id"], new)
        lexeme, deck = self.born("lexeme", "blk-lex")
        self.assertEqual(self.review("lexeme", lexeme, deck, NOW + DAY, "good")["card_id"], lexeme)
        from app.auth import create_access_token
        other = {"Authorization": "Bearer " + create_access_token({"id": self.other, "email": "o@example.test"})}
        for ref in (flagged, 999999):  # someone else's flagged card looks like a missing one
            response = self.client.post(f"/study-items/{ref}/review", headers=other, json={"rating": "good"})
            self.assertEqual(response.status_code, 404)
            self.assertNotIn("identity", response.text)

    def test_edit_and_delete_still_work(self):
        ref = self.legacy_card("blk-edit")
        self.flag()
        edited = self.client.patch(f"/vocab-items/{ref}", headers=self.headers, json={"meaning_ko": "고친 뜻"})
        self.assertEqual(edited.status_code, 200)
        self.assertEqual(self.client.delete(f"/vocab-items/{ref}", headers=self.headers).status_code, 204)
        with get_connection() as c:
            self.assertEqual(len(c.execute("SELECT 1 FROM srs_card_identity_flags WHERE card_ref = ?", (ref,)).fetchall()), 1)


class RaceTests(BlockCase):
    def overlap(self, first, jobs):
        second = "review" if first == "flag" else "flag"
        entered, release = threading.Event(), threading.Event()
        probe = race_support.LockProbe()
        probe.__enter__()
        inner = storage.begin_card_write  # the probe's recording wrapper

        def holding(connection, user_id):
            inner(connection, user_id)
            if threading.current_thread().name == first and not entered.is_set():
                entered.set()
                self.assertTrue(release.wait(15))

        try:
          with mock.patch.object(storage, "begin_card_write", holding):
            a = race_support.start(first, jobs[first])
            self.assertTrue(entered.wait(15))
            b = race_support.start(second, jobs[second])
            self.assertTrue(probe.wait("waiting", second))
            time.sleep(0.3)
            self.assertNotIn(("acquired", second), probe.events)
            probe.mark("released", first)
            release.set()
            for task in (a, b):
                task.thread.join(race_support.JOIN_TIMEOUT)
                self.assertFalse(task.thread.is_alive(), task.name)
        finally:
            release.set()
            probe.__exit__(None, None, None)
        probe.assert_serialized(self, first, second)
        return {t.name: t.box for t in (a, b)}

    def jobs(self, ref):
        version = self.card_row("personal", ref)["srs_card_version"]

        def review():
            with mock.patch.object(vocab_repository, "now_utc", return_value=NOW + DAY):
                return vocab_repository.record_review(self.user, ref, "good", request_id=f"race-{ref}",
                                                      expected_card_version=version, session_id="s1")

        return {"flag": self.flag, "review": review}

    def test_flag_first_refuses_the_review(self):
        ref = self.legacy_card("race-flag-first")
        logs = len(self.logs_of("personal", ref))
        boxes = self.overlap("flag", self.jobs(ref))
        self.assertEqual(boxes["flag"].get("value"), 1)
        self.assertIsInstance(boxes["review"].get("error"), SrsWriteError)
        self.assertEqual(boxes["review"]["error"].code, "card_identity_unknown")
        self.assertEqual(len(self.logs_of("personal", ref)), logs)

    def test_review_first_is_kept_and_later_reviews_are_refused(self):
        ref = self.legacy_card("race-review-first")
        logs = len(self.logs_of("personal", ref))
        boxes = self.overlap("review", self.jobs(ref))
        self.assertIsNone(boxes["review"].get("error"))
        self.assertEqual(boxes["review"]["value"]["id"], ref)
        self.assertEqual(boxes["flag"].get("value"), 1)
        self.assertEqual(len(self.logs_of("personal", ref)), logs + 1)  # the committed review stays
        later = self.send(ref, {"rating": "good"})
        self.assertEqual((later.status_code, later.json()["detail"]), (409, "card_identity_unknown"))
        self.assertEqual(len(self.logs_of("personal", ref)), logs + 1)


if __name__ == "__main__":
    unittest.main()

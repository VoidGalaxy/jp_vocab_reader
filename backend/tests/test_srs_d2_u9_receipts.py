"""Gate D-2 U9: result-only FSRS review responses, byte-identical receipt replay,
7-day logical receipt expiry, and the one-time minimization tool for pre-U9 receipts.

Synthetic SQLite only (QueueCase sets a throwaway DATABASE_URL per test before the
app touches a database). The tool runs only against that synthetic file.

Run directly:      python tests/test_srs_d2_u9_receipts.py
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
from test_srs_d2_u8_plan_b import PlanBCase  # noqa: E402
from test_srs_queue import NOW, iso  # noqa: E402
import race_support  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from app import main  # noqa: E402
from app.auth import create_access_token  # noqa: E402
from app.database import VOCAB_ITEM_FIELDS, get_connection  # noqa: E402
from app.repositories import vocab_repository  # noqa: E402
from app.repositories.vocab_repository import create_or_update_vocab_item  # noqa: E402
from app.schemas import VocabItemCreate, VocabItemUpdate  # noqa: E402
from app.srs import migration, receipts, reviews, storage  # noqa: E402
from app.srs.storage import SrsWriteError  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import d2_receipt_minimize  # noqa: E402

DAY = timedelta(days=1)
TTL = timedelta(days=7)
EXPECTED_KEYS = {"card_kind", "card_id", "request_id", "accepted_at", "server_now", "rating", "correct_count",
                 "wrong_count", "review_level", "next_review_at", "last_reviewed_at", "completed",
                 "completion_metric_version", "srs"}
CONTENT = receipts.CONTENT_FIELDS | {"status", "created_at", "updated_at", "deck_id", "shared_deck_id", "lexeme_id", "id"}


class U9Case(PlanBCase):
    def setUp(self):
        super().setUp()
        self.client = TestClient(main.app)
        self.addCleanup(self.client.close)
        self.headers = {"Authorization": "Bearer " + create_access_token({"id": self.user, "email": "c1@example.test"})}
        self._n = 0

    def fresh_personal(self, name):
        """A new personal card in the FSRS account (fresh FSRS, version 0)."""
        return create_or_update_vocab_item(self.user, VocabItemCreate(
            surface=name, base_form=name, reading=f"{name}-よみ", meaning_ko=f"{name}-뜻", status="unknown",
            deck_id=self.deck, example_sentence=f"{name}の例文", context_explanation_ko="문맥"))[0]["id"]

    def path(self, kind, ref, deck=None):
        return f"/study-items/{ref}/review" if kind == "personal" else f"/shared-decks/{deck}/words/{ref}/review"

    def post(self, kind, ref, at, request, version, deck=None, rating="good", session="s1"):
        body = {"rating": rating, "request_id": request, "session_id": session, "expected_card_version": version}
        with mock.patch.object(reviews, "now_utc", return_value=at):
            return self.client.post(self.path(kind, ref, deck), headers=self.headers, json=body)

    def version(self, kind, ref):
        return self.card_row(kind, ref)["srs_card_version"]

    def receipt(self, request):
        with get_connection() as c:
            row = c.execute("SELECT * FROM srs_review_receipts WHERE user_id = ? AND request_id = ?",
                            (self.user, request)).fetchone()
        return dict(row) if row else None

    def counts(self):
        with get_connection() as c:
            return tuple(c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                         for t in ("review_logs", "lexeme_review_logs", "srs_review_receipts"))

    def assert_minimal(self, response):
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(set(body), EXPECTED_KEYS)
        self.assertFalse(set(body) & CONTENT)
        self.assertNotIn("뜻", response.text)
        self.assertNotIn("例文", response.text)
        return body

    def check_first_and_retry(self, kind, ref, at, deck=None, request="r-1", version="current"):
        version = self.version(kind, ref) if version == "current" else version
        first = self.post(kind, ref, at, request, version, deck)
        body = self.assert_minimal(first)
        state = self.counts()
        again = self.post(kind, ref, at + DAY, request, version, deck)  # later clock: nothing recomputed
        self.assertEqual(again.status_code, 200)
        self.assertEqual(again.content, first.content)  # byte-identical body
        self.assertEqual(self.counts(), state)
        self.assertEqual(self.receipt(request)["response_json"].encode("utf-8"), first.content)
        return body, first

    def old_personal_receipt(self, ref, request):
        """Rewrite a receipt into the pre-U9 personal shape (card row copied in)."""
        with get_connection() as c:
            row = dict(c.execute(f"SELECT {VOCAB_ITEM_FIELDS} FROM vocab_items LEFT JOIN decks ON decks.id = vocab_items.deck_id "
                                 "WHERE vocab_items.id = ?", (ref,)).fetchone())
            current = json.loads(c.execute("SELECT response_json FROM srs_review_receipts WHERE request_id = ?",
                                           (request,)).fetchone()[0])
            old = dict(row, **{k: current[k] for k in ("request_id", "accepted_at", "server_now", "completed",
                                                       "completion_metric_version", "srs")})
            text = json.dumps(old, ensure_ascii=False, sort_keys=True)
            c.execute("UPDATE srs_review_receipts SET response_json = ? WHERE request_id = ?", (text, request))
        return old


# ---------------------------------------------------------------------------
class ResponseTests(U9Case):
    def test_personal_existing_card(self):
        ref = self.fresh_personal("犬")
        body, _ = self.check_first_and_retry("personal", ref, NOW)
        self.assertEqual((body["card_kind"], body["card_id"], body["rating"], body["correct_count"]), ("personal", ref, "good", 1))
        self.assertEqual(body["srs"]["card_version"], 1)
        self.assertIn("introduced_today", body["srs"])

    def test_subscribed_first_review_and_existing_card(self):
        deck = self.shared_deck("s")
        lexeme = self.lexeme("山", deck, 0, progress=False)
        body, _ = self.check_first_and_retry("lexeme", lexeme, NOW, deck, request="first-1", version=None)
        self.assertEqual(body["srs"]["card_version"], 1)
        body2, _ = self.check_first_and_retry("lexeme", lexeme, NOW + 2 * DAY, deck, request="next-1")
        self.assertEqual(body2["srs"]["card_version"], 2)

    def test_plan_b_first_review(self):
        ref, boundary, _, at = self.to_plan_b("personal", name="b")
        body, _ = self.check_first_and_retry("personal", ref, at, request="b-first")
        self.assertEqual(len(self.restarts("personal", ref)), 1)

    def test_retry_after_meaning_change_next_review_and_rollback(self):
        ref = self.converted("personal", "change")
        first = self.post("personal", ref, NOW, "keep-1", 1)
        self.assert_minimal(first)
        vocab_repository.update_vocab_item(self.user, ref, VocabItemUpdate(meaning_ko="바뀐 뜻"))
        self.assertEqual(self.post("personal", ref, NOW + 3 * DAY, "keep-2", self.version("personal", ref)).status_code, 200)
        self.assertEqual(self.rollback("personal", ref)[0]["result"], "rolled_back")
        state = self.counts()
        again = self.post("personal", ref, NOW + 4 * DAY, "keep-1", 1)
        self.assertEqual((again.status_code, again.content), (200, first.content))
        self.assertEqual(self.counts(), state)  # no review added

    def test_unknown_new_count_is_replayed_as_first_seen(self):
        ref = self.fresh_personal("unk")
        other = self.fresh_personal("other")
        with get_connection() as c:  # another card's unreadable log time makes today's count unknown
            c.execute("INSERT INTO review_logs (user_id, vocab_item_id, rating, reviewed_at, previous_review_level, "
                      "next_review_level, next_review_at) VALUES (?, ?, 'good', 'garbage', 0, 1, ?)", (self.user, other, iso(NOW)))
        first = self.post("personal", ref, NOW, "unk-1", 0)
        self.assertEqual(first.json()["srs"]["introduced_today_status"], "unknown")
        with get_connection() as c:
            c.execute("DELETE FROM review_logs WHERE reviewed_at = 'garbage'")
        again = self.post("personal", ref, NOW, "unk-1", 0)
        self.assertEqual(again.content, first.content)

    def test_legacy_response_unchanged(self):
        self.set_mode(self.user, "legacy")
        item = self.personal("legacy")
        response = self.client.post(f"/study-items/{item}/review", headers=self.headers, json={"rating": "good"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("meaning_ko", response.json())
        self.assertNotIn("srs", response.json())


# ---------------------------------------------------------------------------
class ExpiryTests(U9Case):
    def test_boundary_personal(self):
        ref = self.fresh_personal("ttl")
        first = self.post("personal", ref, NOW, "ttl-1", 0)
        self.assertEqual(first.status_code, 200)
        just_before = self.post("personal", ref, NOW + TTL - timedelta(seconds=1), "ttl-1", 0)
        self.assertEqual(just_before.content, first.content)
        state = self.everything()
        for at in (NOW + TTL, NOW + TTL + timedelta(seconds=1), NOW + 30 * DAY):
            response = self.post("personal", ref, at, "ttl-1", 0)
            self.assertEqual((response.status_code, response.json()["detail"]), (409, "card_version_conflict"))
            self.assertEqual(self.everything(), state)

    def test_boundary_subscribed_existing_and_first_review(self):
        deck = self.shared_deck("s")
        lexeme = self.lexeme("川", deck, 0, progress=False)
        self.assertEqual(self.post("lexeme", lexeme, NOW, "lx-first", None, deck).status_code, 200)
        self.assertEqual(self.post("lexeme", lexeme, NOW + DAY, "lx-next", 1, deck).status_code, 200)
        state = self.everything()
        for request, version in (("lx-first", None), ("lx-next", 1)):
            response = self.post("lexeme", lexeme, NOW + DAY + TTL, request, version, deck)
            self.assertEqual(response.status_code, 409, (request, response.text))
            self.assertEqual(self.everything(), state)
        self.assertEqual(self.post("lexeme", lexeme, NOW + DAY + TTL, "lx-first", None, deck).json()["detail"],
                         "card_version_conflict")

    def test_deleted_and_access_lost_are_404(self):
        ref = self.fresh_personal("gone")
        self.assertEqual(self.post("personal", ref, NOW, "gone-1", 0).status_code, 200)
        vocab_repository.delete_vocab_item(self.user, ref)
        for at in (NOW, NOW + TTL):
            response = self.post("personal", ref, at, "gone-1", 0)
            self.assertEqual(response.status_code, 404)
            self.assertNotIn("gone-뜻", response.text)
        deck = self.shared_deck("s")
        lexeme = self.lexeme("海", deck, 0, progress=False)
        self.assertEqual(self.post("lexeme", lexeme, NOW, "lost-1", None, deck).status_code, 200)
        with get_connection() as c:
            c.execute("UPDATE user_deck_subscriptions SET is_active = FALSE WHERE user_id = ?", (self.user,))
        self.assertEqual(self.post("lexeme", lexeme, NOW, "lost-1", None, deck).status_code, 404)

    def test_unreadable_or_future_receipt_time_is_refused(self):
        for name, created in (("garbage", "garbage"), ("naive", "2026-10-09T03:00:00"),
                              ("future", iso(NOW + 2 * DAY))):
            with self.subTest(name=name):
                ref = self.fresh_personal(f"t-{name}")
                request = f"t-{name}"
                self.assertEqual(self.post("personal", ref, NOW, request, 0).status_code, 200)
                with get_connection() as c:
                    c.execute("UPDATE srs_review_receipts SET created_at = ? WHERE request_id = ?", (created, request))
                state = self.everything()
                response = self.post("personal", ref, NOW + DAY, request, 0)
                self.assertEqual((response.status_code, response.json()["detail"]), (409, "card_version_conflict"))
                self.assertEqual(self.everything(), state)  # not replayed, not deleted, nothing written

    def test_same_request_id_other_payload(self):
        ref = self.fresh_personal("p1")
        other = self.fresh_personal("p2")
        self.assertEqual(self.post("personal", ref, NOW, "dup-1", 0).status_code, 200)
        state = self.everything()
        valid = self.post("personal", ref, NOW, "dup-1", 0, rating="easy")
        self.assertEqual((valid.status_code, valid.json()["detail"]), (409, "request_id_conflict"))
        # After expiry the same id on another card would pass the card checks: still a conflict.
        expired = self.post("personal", other, NOW + TTL, "dup-1", 0)
        self.assertEqual((expired.status_code, expired.json()["detail"]), (409, "request_id_conflict"))
        self.assertEqual(self.everything(), state)


# ---------------------------------------------------------------------------
class MinimizeToolTests(U9Case):
    def make_old(self, name):
        ref = self.fresh_personal(name)
        request = f"old-{name}"
        self.assertEqual(self.post("personal", ref, NOW, request, 0).status_code, 200)
        return ref, request, self.old_personal_receipt(ref, request)

    def run_tool(self, *extra):
        with mock.patch.object(d2_receipt_minimize, "print"):
            return d2_receipt_minimize.main(["--sqlite-db", str(self.db_path), "--user-id", str(self.user), *extra])

    def apply(self, *extra):
        return self.run_tool("--apply", "--confirm-user-id", str(self.user), *extra)

    def test_dry_run_apply_retry_and_rerun(self):
        refs = [self.make_old(f"o{i}") for i in range(3)]
        old_retry = self.post("personal", refs[0][0], NOW, refs[0][1], 0)
        self.assertIn("o0-뜻", old_retry.text)  # before the tool: the old copy is still replayed
        before = self.everything()
        report = self.run_tool()
        self.assertEqual(self.everything(), before)  # dry-run writes nothing
        self.assertEqual([s["id"] for s in report["stripped"]], [r["id"] for r in before_receipts(before)])
        self.assertFalse(report["applied"])
        report = self.apply()
        self.assertEqual(len(report["stripped"]), 3)
        for ref, request, old in refs:
            row = self.receipt(request)
            stored = json.loads(row["response_json"])
            self.assertFalse(set(stored) & receipts.CONTENT_FIELDS)
            self.assertEqual(stored, {k: v for k, v in old.items() if k not in receipts.CONTENT_FIELDS})
            response = self.post("personal", ref, NOW, request, 0)
            self.assertEqual(response.json(), stored)  # the documented exception: content removed, results kept
            self.assertNotIn("뜻", response.text)
        after = self.everything()
        for table in ("review_logs", "vocab_items"):
            self.assertEqual(after[table], before[table])
        kept = [(r[0], r[1], r[2], r[3], r[4], r[5], r[7], r[8]) for r in after["srs_review_receipts"]]
        self.assertEqual(kept, [(r[0], r[1], r[2], r[3], r[4], r[5], r[7], r[8]) for r in before["srs_review_receipts"]])
        again = self.apply()
        self.assertEqual((again["stripped"], again["already_minimal"]), ([], 3))
        self.assertEqual(self.everything(), after)

    def test_failure_then_resume(self):
        for i in range(3):
            self.make_old(f"f{i}")
        real = receipts.canonical_json
        calls = {"n": 0}

        def failing(value):
            calls["n"] += 1
            if calls["n"] == 2:
                raise RuntimeError("synthetic failure")
            return real(value)

        with mock.patch.object(receipts, "canonical_json", failing):
            with self.assertRaises(RuntimeError):
                self.apply("--batch-size", "1")
        with get_connection() as c:
            texts = [r[0] for r in c.execute("SELECT response_json FROM srs_review_receipts ORDER BY id")]
        self.assertEqual([bool(set(json.loads(t)) & receipts.CONTENT_FIELDS) for t in texts], [False, True, True])
        report = self.apply("--batch-size", "1")
        self.assertEqual((len(report["stripped"]), report["already_minimal"]), (2, 1))

    def test_unknown_damaged_lexeme_and_concurrent_change(self):
        ref, request, old = self.make_old("cas")
        deck = self.shared_deck("s")
        lexeme = self.lexeme("木", deck, 0, progress=False)
        self.assertEqual(self.post("lexeme", lexeme, NOW, "lx-1", None, deck).status_code, 200)
        with get_connection() as c:  # an old subscribed receipt had no content
            c.execute("UPDATE srs_review_receipts SET response_json = ? WHERE request_id = 'lx-1'", (json.dumps({
                "lexeme_id": lexeme, "status": "unclassified", "review_level": 1, "next_review_at": None,
                "correct_count": 1, "wrong_count": 0, "last_reviewed_at": None, "request_id": "lx-1",
                "accepted_at": iso(NOW), "server_now": iso(NOW), "completed": None, "completion_metric_version": "x",
                "srs": {}}),))
        bad = [self.make_old(f"bad{i}") for i in range(2)]
        with get_connection() as c:
            c.execute("UPDATE srs_review_receipts SET response_json = '{broken' WHERE request_id = ?", (bad[0][1],))
            c.execute("UPDATE srs_review_receipts SET response_json = '[1, 2]' WHERE request_id = ?", (bad[1][1],))
        before = {r: self.receipt(r)["response_json"] for r in (bad[0][1], bad[1][1], "lx-1")}
        real = receipts.canonical_json
        holder = {}

        def concurrent(value):  # another writer changes the row between read and CAS
            if value.get("request_id") == request and "done" not in holder:
                holder["done"] = True
                holder["conn"].execute("UPDATE srs_review_receipts SET response_json = response_json || ' ' "
                                       "WHERE request_id = ?", (request,))
            return real(value)

        with get_connection() as connection:
            holder["conn"] = connection
            with mock.patch.object(receipts, "canonical_json", concurrent):
                report = receipts.minimize_receipts(connection, self.user, NOW, apply=True,
                                                    lock=storage.begin_card_write)
        ids = {r: self.receipt(r)["id"] for r in (request, bad[0][1], bad[1][1])}
        self.assertEqual(report["changed_concurrently"], [ids[request]])
        self.assertEqual((report["unreadable_json"], report["unknown_format"]), ([ids[bad[0][1]]], [ids[bad[1][1]]]))
        self.assertEqual(report["already_minimal"], 1)  # the subscribed one
        for r, text in before.items():
            self.assertEqual(self.receipt(r)["response_json"], text)  # never repaired or deleted
        self.assertIn("cas-뜻", self.receipt(request)["response_json"])  # the changed row was not overwritten
        self.assertNotIn("뜻", json.dumps(report, ensure_ascii=False))  # the report holds ids/field names only

    def test_guards_and_purge(self):
        with self.assertRaises(SystemExit):
            self.run_tool("--apply")  # no confirmation
        with self.assertRaises(SystemExit):
            self.run_tool("--apply", "--confirm-user-id", str(self.user + 1))
        with self.assertRaises(SystemExit):
            self.run_tool("--purge-expired")
        old_ref, old_request, _ = self.make_old("aged")
        new_ref = self.fresh_personal("fresh-one")
        self.assertEqual(self.post("personal", new_ref, NOW, "fresh-1", 0).status_code, 200)
        odd_ref = self.fresh_personal("odd")
        self.assertEqual(self.post("personal", odd_ref, NOW, "odd-1", 0).status_code, 200)
        with get_connection() as c:
            c.execute("UPDATE srs_review_receipts SET created_at = ? WHERE request_id = ?", (iso(NOW - 30 * DAY), old_request))
            c.execute("UPDATE srs_review_receipts SET created_at = 'garbage' WHERE request_id = 'odd-1'")
        from app.database import now_utc
        with get_connection() as c:
            c.execute("UPDATE srs_review_receipts SET created_at = ? WHERE request_id = 'fresh-1'", (now_utc().isoformat(),))
        report = self.apply("--purge-expired")
        self.assertEqual(len(report["purged"]), 1)
        self.assertIsNone(self.receipt(old_request))
        self.assertIsNotNone(self.receipt("fresh-1"))
        self.assertIsNotNone(self.receipt("odd-1"))  # unreadable time: reported, kept
        self.assertEqual(len(report["unreadable_time"]), 1)


def before_receipts(snapshot):
    return [{"id": r[0]} for r in snapshot["srs_review_receipts"]]


# ---------------------------------------------------------------------------
class RaceTests(U9Case):
    def blocker(self, target, name):
        entered, release = threading.Event(), threading.Event()
        real = getattr(target, name)

        def slow(*a, **k):
            result = real(*a, **k)
            if not entered.is_set():
                entered.set()
                self.assertTrue(release.wait(15))
            return result

        return entered, release, mock.patch.object(target, name, slow)

    def setup_old(self):
        ref = self.fresh_personal("race")
        self.assertEqual(self.post("personal", ref, NOW, "race-1", 0).status_code, 200)
        self.old_personal_receipt(ref, "race-1")
        return ref

    def tool(self):
        with get_connection() as connection:
            return receipts.minimize_receipts(connection, self.user, NOW, apply=True,
                                              lock=lambda c, u: storage.begin_card_write(c, u))

    def retry(self, ref, request="race-1"):
        def call():
            with mock.patch.object(reviews, "now_utc", return_value=NOW + DAY):
                return vocab_repository.record_review(self.user, ref, "good", request_id=request,
                                                      expected_card_version=0, session_id="s1")
        return call

    def test_tool_first_then_retry(self):
        ref = self.setup_old()
        state = self.counts()
        entered, release, patch = self.blocker(receipts, "canonical_json")
        with race_support.LockProbe() as probe, patch:
            tool = race_support.start("tool", self.tool)
            self.assertTrue(entered.wait(15))
            retry = race_support.start("retry", self.retry(ref))
            self.assertTrue(probe.wait("waiting", "retry"))
            time.sleep(0.3)
            self.assertNotIn(("acquired", "retry"), probe.events)
            probe.mark("released", "tool")
            release.set()
            self.assertEqual(len(race_support.finish(self, tool)["stripped"]), 1)
            body = race_support.finish(self, retry)
        probe.assert_serialized(self, "tool", "retry")
        self.assertFalse(set(body) & receipts.CONTENT_FIELDS)  # the retry saw the minimized receipt
        self.assertEqual(self.counts(), state)
        self.assertEqual(self.version("personal", ref), 1)

    def test_retry_first_then_tool(self):
        ref = self.setup_old()
        state = self.counts()
        entered, release, patch = self.blocker(receipts, "receipt_age_status")
        with race_support.LockProbe() as probe, patch:
            retry = race_support.start("retry", self.retry(ref))
            self.assertTrue(entered.wait(15))
            tool = race_support.start("tool", self.tool)
            self.assertTrue(probe.wait("waiting", "tool"))
            time.sleep(0.3)
            self.assertNotIn(("acquired", "tool"), probe.events)
            probe.mark("released", "retry")
            release.set()
            body = race_support.finish(self, retry)
            self.assertEqual(len(race_support.finish(self, tool)["stripped"]), 1)
        probe.assert_serialized(self, "retry", "tool")
        self.assertIn("race-뜻", json.dumps(body, ensure_ascii=False))  # replayed before the tool ran
        self.assertEqual(self.counts(), state)
        self.assertFalse(set(json.loads(self.receipt("race-1")["response_json"])) & receipts.CONTENT_FIELDS)

    def test_purge_and_expired_retry(self):
        ref = self.fresh_personal("purge")
        self.assertEqual(self.post("personal", ref, NOW, "purge-1", 0).status_code, 200)
        with get_connection() as c:
            c.execute("UPDATE srs_review_receipts SET created_at = ? WHERE request_id = 'purge-1'", (iso(NOW - 30 * DAY),))
        state = self.counts()
        entered, release, patch = self.blocker(receipts, "receipt_age_status")
        with race_support.LockProbe() as probe, patch:
            retry = race_support.start("retry", self.retry(ref, "purge-1"))
            self.assertTrue(entered.wait(15))

            def purge():
                with get_connection() as connection:
                    return receipts.minimize_receipts(connection, self.user, NOW, apply=True, purge_expired=True,
                                                      lock=lambda c, u: storage.begin_card_write(c, u))

            tool = race_support.start("purge", purge)
            self.assertTrue(probe.wait("waiting", "purge"), (probe.events, tool.box))
            probe.mark("released", "retry")
            release.set()
            race_support.finish_error(self, retry, SrsWriteError, "card_version_conflict")
            self.assertEqual(len(race_support.finish(self, tool)["purged"]), 1)
        self.assertEqual(self.counts(), (state[0], state[1], state[2] - 1))  # no review added, receipt purged
        self.assertEqual(self.version("personal", ref), 1)


if __name__ == "__main__":
    unittest.main()

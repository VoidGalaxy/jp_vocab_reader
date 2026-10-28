"""Gate C-2a: server work for the study session (gate-c2/CONTRACT.md v0.2).

New personal cards in FSRS accounts, the atomic first review of subscribed
words without progress (explicit expected_card_version null), exclude_card
and mode=selected on GET /study-queue. Synthetic SQLite only (see QueueCase).

Run directly:      python tests/test_srs_c2_server.py
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
from test_srs_queue import NOW, QueueCase, iso  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from app import main  # noqa: E402
from app.auth import create_access_token  # noqa: E402
from app.database import get_connection  # noqa: E402
from app.repositories.deck_package_repository import import_deck_package  # noqa: E402
from app.repositories.lexeme_repository import (  # noqa: E402
    record_lexeme_review, update_word_status,
)
from app.repositories.shared_deck_repository import import_shared_deck  # noqa: E402
from app.repositories.user_repository import create_user  # noqa: E402
from app.repositories.vocab_repository import create_or_update_vocab_item  # noqa: E402
from app.schemas import DeckCreate, DeckPackage, VocabItemCreate  # noqa: E402
from app.repositories.deck_repository import create_deck  # noqa: E402
from app.srs import queue, reviews  # noqa: E402
from app.srs.engine import DEFAULT_CONFIG, CardKey, SrsPhase  # noqa: E402
from app.srs.storage import SrsWriteError  # noqa: E402

SRS_COLUMNS = ("srs_engine", "srs_config_version", "srs_participation", "srs_state", "srs_card_version",
               "srs_history_quality", "srs_effective_due_at")
FRESH = ("fsrs", DEFAULT_CONFIG.config_version, "active", None, 0, "fresh", None)


class C2Case(QueueCase):
    def setUp(self):
        super().setUp()
        self.client = TestClient(main.app)
        self.addCleanup(self.client.close)
        self.headers = {"Authorization": "Bearer " + create_access_token({"id": self.user, "email": "c1@example.test"})}

    def srs(self, item):
        with get_connection() as connection:
            row = connection.execute(f"SELECT {', '.join(SRS_COLUMNS)}, status FROM vocab_items WHERE id = ?",
                                     (item,)).fetchone()
        return tuple(row)

    def new_item(self, name, status="unknown", user=None, deck=None):
        return create_or_update_vocab_item(user or self.user, VocabItemCreate(
            surface=name, base_form=name, reading=name, status=status, deck_id=deck or self.deck))[0]["id"]

    def counts(self, lexeme):
        with get_connection() as connection:
            return tuple(connection.execute(sql, (self.user, lexeme)).fetchone()[0] for sql in (
                "SELECT COUNT(*) FROM user_word_progress WHERE user_id = ? AND lexeme_id = ?",
                "SELECT COUNT(*) FROM lexeme_review_logs WHERE user_id = ? AND lexeme_id = ?",
                "SELECT COUNT(*) FROM srs_review_receipts WHERE user_id = ? AND card_ref = ? AND card_kind = 'lexeme'",
            ))

    def first(self, lexeme, deck, request_id="first-1", rating="good", **extra):
        body = {"rating": rating, "request_id": request_id, "session_id": "s1", "expected_card_version": None, **extra}
        return self.client.post(f"/shared-decks/{deck}/words/{lexeme}/review", headers=self.headers, json=body)


# ---------------------------------------------------------------------------
class NewPersonalCardTests(C2Case):
    def test_fsrs_account_new_card_is_fresh_and_known_is_active(self):  # N1, N5
        item = self.new_item("fresh")
        self.assertEqual(self.srs(item)[:-1], FRESH)
        known = self.new_item("known-word", status="known")
        self.assertEqual(self.srs(known), FRESH + ("known",))

    def test_update_path_keeps_srs_columns(self):  # N2
        item = self.new_item("again")
        self.rate("personal", item, "good")
        before = self.srs(item)
        _, created = create_or_update_vocab_item(self.user, VocabItemCreate(
            surface="again", base_form="again", reading="again", example_sentence="new example", deck_id=self.deck))
        self.assertFalse(created)
        self.assertEqual(self.srs(item), before)

    def test_package_import_and_shared_deck_copy(self):  # N3
        existing = self.new_item("existing")
        self.rate("personal", existing, "good")
        existing_before = self.srs(existing)
        package = DeckPackage(package_type="jp_vocab_reader_deck", package_version=1, deck={"name": "pkg"},
                              vocab_items=[{"base_form": "p1", "surface": "p1"}, {"base_form": "p2", "surface": "p2"}])
        deck_id = import_deck_package(self.user, package)["deck_id"]
        with get_connection() as connection:
            rows = connection.execute(f"SELECT {', '.join(SRS_COLUMNS)} FROM vocab_items WHERE deck_id = ?",
                                      (deck_id,)).fetchall()
            shared = connection.execute(
                "INSERT INTO shared_decks (owner_user_id, title, description, visibility, created_at, updated_at) "
                "VALUES (?, 'legacy shared', '', 'public', ?, ?) RETURNING id", (self.other, iso(NOW), iso(NOW))).fetchone()["id"]
            connection.execute("INSERT INTO shared_deck_items (shared_deck_id, surface, base_form, reading, created_at) "
                               "VALUES (?, 's1', 's1', '', ?)", (shared, iso(NOW)))
        self.assertEqual([tuple(r) for r in rows], [FRESH, FRESH])
        copied = import_shared_deck(self.user, shared)
        with get_connection() as connection:
            rows = connection.execute(f"SELECT {', '.join(SRS_COLUMNS)} FROM vocab_items WHERE deck_id = ?",
                                      (copied["deck_id"],)).fetchall()
        self.assertEqual([tuple(r) for r in rows], [FRESH])
        self.assertEqual(self.srs(existing), existing_before)  # N6

    def test_legacy_shadow_and_no_settings_accounts_stay_legacy(self):  # N4
        for mode in ("legacy", "shadow", None):
            with self.subTest(mode=mode):
                user = create_user(email=f"n4-{mode}@example.test", display_name="n4", password_hash="x")["id"]
                deck = create_deck(user, DeckCreate(name="d"))[0]["id"]
                if mode:
                    self.set_mode(user, mode)
                item = self.new_item(f"w-{mode}", user=user, deck=deck)
                self.assertEqual(self.srs(item)[:1], ("legacy",))

    def test_personal_url_rejects_explicit_null(self):  # N7
        item = self.new_item("p-null")
        before = self.snapshot()
        response = self.client.post(f"/study-items/{item}/review", headers=self.headers,
                                    json={"rating": "good", "request_id": "x1", "session_id": "s1", "expected_card_version": None})
        self.assertEqual((response.status_code, response.json()["detail"]), (422, "null_card_version_not_allowed"))
        self.assertEqual(self.snapshot(), before)


# ---------------------------------------------------------------------------
class FirstSubscribedReviewTests(C2Case):
    def setUp(self):
        super().setUp()
        self.shared = self.shared_deck("s")
        self.word = self.lexeme("word", self.shared, 0, progress=False)

    def test_first_review_creates_and_rates_atomically(self):  # I1, I5
        response = self.first(self.word, self.shared)
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        # Gate D-2 U9 (D-P3a): results only -- the classification (status) is no longer copied.
        self.assertEqual((body["srs"]["card_version"], body["request_id"], body["card_kind"], body["card_id"]),
                         (1, "first-1", "lexeme", self.word))
        self.assertNotIn("status", body)
        self.assertEqual(body["srs"]["state"]["phase"], "learning")
        self.assertEqual(self.counts(self.word), (1, 1, 1))
        with get_connection() as connection:
            row = connection.execute("SELECT srs_engine, srs_card_version, srs_participation, srs_history_quality "
                                     "FROM user_word_progress WHERE user_id = ? AND lexeme_id = ?", (self.user, self.word)).fetchone()
            log = connection.execute("SELECT is_first_review, card_version_before FROM lexeme_review_logs WHERE lexeme_id = ?",
                                     (self.word,)).fetchone()
            receipt = connection.execute("SELECT request_hash FROM srs_review_receipts WHERE request_id = 'first-1'").fetchone()
        self.assertEqual(tuple(row), ("fsrs", 1, "active", "fresh"))
        self.assertEqual(tuple(log), (1, 0))
        key = CardKey("lexeme", self.user, self.word)
        self.assertEqual(receipt["request_hash"],
                         reviews.request_hash(key, "good", "first-1", None, "s1", self.shared, None))
        self.assertNotEqual(receipt["request_hash"],
                            reviews.request_hash(key, "good", "first-1", 0, "s1", self.shared, None))
        self.assertEqual((body["srs"]["introduced_today"], body["srs"]["introduced_today_status"]), (1, "exact"))

    def test_retry_and_payload_conflicts(self):  # I2, I3, I4
        first = self.first(self.word, self.shared)
        self.assertEqual(self.first(self.word, self.shared).json(), first.json())
        self.assertEqual(self.counts(self.word), (1, 1, 1))
        for change in ({"expected_card_version": 0}, {"rating": "easy"}):
            with self.subTest(change=change):
                before = self.snapshot()
                body = {"rating": "good", "request_id": "first-1", "session_id": "s1", "expected_card_version": None, **change}
                response = self.client.post(f"/shared-decks/{self.shared}/words/{self.word}/review", headers=self.headers, json=body)
                self.assertEqual((response.status_code, response.json()["detail"]), (409, "request_id_conflict"))
                self.assertEqual(self.snapshot(), before)

    def _parallel(self, request_ids):
        """Runs one first-review per entry on its own thread and its own
        connection. Results are kept per task index (not per request_id, which
        may repeat). Every outcome is recorded; unexpected exceptions are kept
        too so the caller can assert none happened."""
        barrier = threading.Barrier(len(request_ids))
        outcomes: list[tuple[str, object] | None] = [None] * len(request_ids)
        started = [0.0] * len(request_ids)
        finished = [0.0] * len(request_ids)
        original = reviews.review

        def slow_review(*args, **kwargs):
            time.sleep(0.3)  # keep the first writer inside its transaction
            return original(*args, **kwargs)

        def run(index, request_id):
            barrier.wait()
            started[index] = time.monotonic()
            try:
                outcomes[index] = ("ok", record_lexeme_review(
                    self.user, self.word, "good", self.shared, request_id=request_id,
                    expected_card_version=None, session_id="s1", first_review=True))
            except SrsWriteError as error:
                outcomes[index] = ("srs_error", (error.status_code, error.code))
            except BaseException as error:  # noqa: BLE001 - surfaced by the assertions below
                outcomes[index] = ("unexpected", repr(error))
            finally:
                finished[index] = time.monotonic()

        with mock.patch.object(reviews, "review", side_effect=slow_review):
            threads = [threading.Thread(target=run, args=(index, rid), daemon=True)
                       for index, rid in enumerate(request_ids)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=30)
        self.assertFalse(any(thread.is_alive() for thread in threads), "a worker thread did not finish")
        self.assertTrue(all(outcome is not None for outcome in outcomes), outcomes)
        self.assertEqual([o for o in outcomes if o[0] == "unexpected"], [])
        # Real overlap: both started before the first one finished.
        self.assertLess(max(started), min(finished))
        return outcomes

    def test_concurrent_first_reviews_one_wins(self):  # I6
        outcomes = self._parallel(["win-a", "win-b"])
        kinds = sorted(kind for kind, _ in outcomes)
        self.assertEqual(kinds, ["ok", "srs_error"])
        self.assertEqual(next(value for kind, value in outcomes if kind == "srs_error"), (409, "card_version_conflict"))
        winner = next(value for kind, value in outcomes if kind == "ok")
        self.assertIn(winner["request_id"], ("win-a", "win-b"))
        self.assertEqual(self.counts(self.word), (1, 1, 1))

    def test_concurrent_same_request_returns_one_receipt(self):  # I7
        outcomes = self._parallel(["same", "same"])
        self.assertEqual([kind for kind, _ in outcomes], ["ok", "ok"])
        self.assertEqual(outcomes[0][1], outcomes[1][1])
        self.assertEqual(outcomes[0][1]["request_id"], "same")
        self.assertEqual(self.counts(self.word), (1, 1, 1))

    def test_failures_at_each_stage_roll_back_the_created_row(self):  # I8
        stages = [("engine", mock.patch.object(reviews, "review", side_effect=RuntimeError("injected engine"))),
                  ("late", mock.patch.object(reviews, "introduced_on", side_effect=RuntimeError("injected late"))),
                  # request_hash runs only when the receipt row is written (no receipt exists yet)
                  ("receipt", mock.patch.object(reviews, "request_hash", side_effect=RuntimeError("injected receipt")))]
        for name, patch in stages:
            with self.subTest(stage=name):
                before = self.snapshot()
                with patch, self.assertRaises(RuntimeError):
                    record_lexeme_review(self.user, self.word, "good", self.shared, request_id=f"fail-{name}",
                                         expected_card_version=None, session_id="s1", first_review=True)
                self.assertEqual(self.snapshot(), before)
                self.assertEqual(self.counts(self.word), (0, 0, 0))

    def test_access_mode_and_existing_row_are_checked_before_any_write(self):  # I9, I10, I11, own logs
        with get_connection() as connection:
            connection.execute("UPDATE user_deck_subscriptions SET is_active = FALSE WHERE user_id = ?", (self.user,))
        before = self.snapshot()
        self.assertEqual(self.first(self.word, self.shared).status_code, 404)
        self.assertEqual(self.snapshot(), before)
        with get_connection() as connection:
            connection.execute("UPDATE user_deck_subscriptions SET is_active = TRUE WHERE user_id = ?", (self.user,))
        self.set_mode(self.user, "legacy")
        before = self.snapshot()
        response = self.first(self.word, self.shared, request_id="legacy-null")
        self.assertEqual((response.status_code, response.json()["detail"]), (409, "srs_mode_not_fsrs"))
        self.assertEqual(self.snapshot(), before)
        self.set_mode(self.user, "fsrs")
        other = self.lexeme("has-status", self.shared, 1, progress=False)
        update_word_status(self.user, other, "known")  # creates a legacy progress row
        before = self.snapshot()
        response = self.first(other, self.shared, request_id="exists")
        self.assertEqual((response.status_code, response.json()["detail"]), (409, "card_version_conflict"))
        self.assertEqual(self.snapshot(), before)
        orphan = self.lexeme("orphan-logs", self.shared, 2, progress=False)
        with get_connection() as connection:
            connection.execute(
                "INSERT INTO lexeme_review_logs (user_id, lexeme_id, shared_deck_id, rating, previous_review_level, "
                "new_review_level, previous_status, new_status, created_at) VALUES (?, ?, ?, 'good', 0, 1, 'u', 'u', ?)",
                (self.user, orphan, self.shared, iso(NOW - timedelta(days=3))))
        before = self.snapshot()
        response = self.first(orphan, self.shared, request_id="orphan")
        self.assertEqual((response.status_code, response.json()["detail"]), (409, "history_initialization_requires_approval"))
        self.assertEqual(self.snapshot(), before)

    def test_missing_key_keeps_existing_behavior(self):  # I12, I13, I14
        legacy = self.client.post(f"/shared-decks/{self.shared}/words/{self.word}/review", headers=self.headers,
                                  json={"rating": "again"})
        self.assertEqual(legacy.status_code, 200)
        with get_connection() as connection:
            row = connection.execute("SELECT srs_engine, status FROM user_word_progress WHERE lexeme_id = ?",
                                     (self.word,)).fetchone()
        self.assertEqual(tuple(row), ("legacy", "unknown"))  # legacy lazy creation + auto status, unchanged
        fsrs_word = self.lexeme("fsrs-word", self.shared, 3)
        self.fsrs("lexeme", fsrs_word)
        response = self.client.post(f"/shared-decks/{self.shared}/words/{fsrs_word}/review", headers=self.headers,
                                    json={"rating": "good", "request_id": "no-version", "session_id": "s1"})
        self.assertEqual((response.status_code, response.json()["detail"]), (422, "review_upgrade_required"))
        unmat = self.lexeme("no-ids", self.shared, 4, progress=False)
        before = self.snapshot()
        response = self.client.post(f"/shared-decks/{self.shared}/words/{unmat}/review", headers=self.headers,
                                    json={"rating": "good", "expected_card_version": None})
        self.assertEqual((response.status_code, response.json()["detail"]), (422, "review_upgrade_required"))
        self.assertEqual(self.snapshot(), before)

    def test_queue_serves_unmaterialized_and_rating_it_materializes(self):  # U1-U3 end to end
        result = self.q(mode="new")
        item = next(i for i in result["items"] if i["card_id"] == self.word)
        self.assertEqual((item["card_version"], item["materialized"], item["bucket"]), (None, False, "new"))
        self.assertEqual(result["counts"]["new_unmaterialized"], 1)
        response = self.client.post(item["review"]["path"], headers=self.headers, json={
            "rating": "again", "request_id": "from-queue", "session_id": "s1", "expected_card_version": item["card_version"]})
        self.assertEqual(response.status_code, 200)
        after = self.q()
        self.assertEqual(after["counts"]["new_unmaterialized"], 0)
        self.assertEqual(after["counts"]["pending_later"], 1)  # Learning, 1 minute


# ---------------------------------------------------------------------------
class ExcludeCardTests(C2Case):
    def due_cards(self, count, minutes_base=200):
        items = [self.personal(f"d{i}") for i in range(count)]
        for index, item in enumerate(items):
            self.due("personal", item, SrsPhase.REVIEW, NOW - timedelta(minutes=minutes_base - index))
        return items

    def test_front_ten_excluded_returns_the_rest(self):  # X1, X2
        items = self.due_cards(15)
        plain = self.q(limit=10)
        result = self.q(limit=10, exclude_card=[f"personal:{i}" for i in items[:10]])
        self.assertEqual([i["card_id"] for i in result["items"]], items[10:])
        for name in queue.CATEGORIES + ("total_in_scope", "new_allowed_now"):
            self.assertEqual(result["counts"][name], plain["counts"][name], name)
        self.assertEqual(result["counts"]["excluded_by_request"], 10)
        self.assertEqual(result["new_goal"], plain["new_goal"])

    def test_next_due_for_excluded_cards_is_separate(self):  # X3
        later = self.personal("later")
        self.due("personal", later, SrsPhase.REVIEW, NOW + timedelta(hours=2))
        sooner = self.personal("sooner")
        self.due("personal", sooner, SrsPhase.LEARNING, NOW + timedelta(minutes=5))
        result = self.q(exclude_card=f"personal:{sooner}")
        self.assertEqual(result["next_due_at"], iso(NOW + timedelta(hours=2)))
        self.assertEqual(result["next_due_at_excluded"], iso(NOW + timedelta(minutes=5)))

    def test_validation_duplicates_and_limit(self):  # X4, X5
        for bad in (["foo:1"], ["personal:0"], ["personal:-1"], ["personal:1x"], ["lexeme:"]):
            with self.subTest(bad=bad), self.assertRaises(queue.QueueError) as raised:
                self.q(exclude_card=bad)
            self.assertEqual(raised.exception.status_code, 400)
        self.q(exclude_card=["personal:1"] * 100 + ["personal:2"])  # duplicates collapse: 2 keys
        with self.assertRaises(queue.QueueError) as raised:
            self.q(exclude_card=[f"personal:{i}" for i in range(1, 102)])
        self.assertEqual(raised.exception.code, "too_many_excluded_cards")
        self.q(exclude_card=[f"personal:{i}" for i in range(1, 101)])  # exactly 100 is fine
        other_deck = create_deck(self.other, DeckCreate(name="theirs"))[0]["id"]
        theirs = self.new_item("theirs", user=self.other, deck=other_deck)
        mine = self.due_cards(1)
        result = self.q(exclude_card=f"personal:{theirs}")
        self.assertEqual([i["card_id"] for i in result["items"]], mine)
        self.assertEqual(result["counts"]["excluded_by_request"], 0)

    def test_new_allowance_unchanged_and_cursor_bound(self):  # X6, X7
        self.set_mode(self.user, "fsrs", goal=3)
        fresh = [self.personal(f"n{i}") for i in range(5)]
        for item in fresh:
            self.fsrs("personal", item)
        plain = self.q(mode="new", limit=10)
        excluded = self.q(mode="new", limit=10, exclude_card=f"personal:{fresh[0]}")
        self.assertEqual(excluded["counts"]["new_allowed_now"], plain["counts"]["new_allowed_now"])
        self.assertEqual([i["card_id"] for i in excluded["items"]], fresh[1:4])
        token = self.q(mode="new", limit=1)["next_cursor"]
        with self.assertRaises(queue.QueueError) as raised:
            self.q(mode="new", limit=1, cursor=token, exclude_card=f"personal:{fresh[0]}")
        self.assertEqual(raised.exception.status_code, 409)

    def test_no_writes(self):  # X8
        items = self.due_cards(3)
        before = self.snapshot()
        self.q(exclude_card=[f"personal:{i}" for i in items])
        with self.assertRaises(queue.QueueError):
            self.q(exclude_card="bad")
        self.assertEqual(self.snapshot(), before)


# ---------------------------------------------------------------------------
class SelectedModeTests(C2Case):
    def test_only_the_selected_personal_cards(self):  # M4, M9
        due_in = self.personal("due-in")
        self.due("personal", due_in, SrsPhase.REVIEW, NOW - timedelta(hours=1))
        due_out = self.personal("due-out")
        self.due("personal", due_out, SrsPhase.REVIEW, NOW - timedelta(hours=2))
        shared = self.shared_deck("s")
        lexeme = self.lexeme("lx", shared)
        self.due("lexeme", lexeme, SrsPhase.REVIEW, NOW - timedelta(hours=3))
        other_deck = create_deck(self.other, DeckCreate(name="theirs"))[0]["id"]
        theirs = self.new_item("theirs", user=self.other, deck=other_deck)
        result = self.q(mode="selected", card_id=[due_in, theirs, lexeme])
        self.assertEqual(self.keys(result), [("personal", due_in)])
        self.assertEqual(result["counts"]["total_in_scope"], 1)
        for params in (dict(mode="selected"), dict(mode="selected", card_id=list(range(1, 202))),
                       dict(mode="today", card_id=due_in), dict(mode="selected", card_id=due_in, scope="personal_deck",
                                                                 deck_id=self.deck), dict(mode="selected", card_id="x")):
            with self.subTest(params=str(params)[:60]), self.assertRaises(queue.QueueError) as raised:
                self.q(**params)
            self.assertEqual(raised.exception.status_code, 400)

    def test_due_new_within_goal_future_not_served(self):  # M4, M5
        self.set_mode(self.user, "fsrs", goal=2)
        due = self.personal("due")
        self.due("personal", due, SrsPhase.REVIEW, NOW - timedelta(hours=1))
        future = self.personal("future")
        self.due("personal", future, SrsPhase.REVIEW, NOW + timedelta(days=2))
        fresh = [self.personal(f"f{i}") for i in range(3)]
        for item in fresh:
            self.fsrs("personal", item)
        selection = [due, future] + fresh
        result = self.q(mode="selected", card_id=selection)
        self.assertEqual(self.keys(result), [("personal", due), ("personal", fresh[0]), ("personal", fresh[1])])
        self.assertEqual(result["counts"]["pending_later"], 1)
        received = result["items"][2]["card_id"]
        self.rate("personal", fresh[0], "good")
        self.rate("personal", fresh[2], "good")       # goal reached elsewhere
        reached = self.q(mode="selected", card_id=selection)
        self.assertEqual(self.keys(reached), [("personal", due)])
        self.assertEqual(reached["new_goal"]["account_remaining"], 0)
        self.assertIsNotNone(self.rate("personal", received, "good"))  # M7: a received card is still accepted

    def test_unknown_count_stops_new_but_not_due(self):  # M5
        due = self.personal("due")
        self.due("personal", due, SrsPhase.REVIEW, NOW - timedelta(hours=1))
        fresh = self.personal("fresh")
        self.fsrs("personal", fresh)
        broken = self.personal("broken")
        with get_connection() as connection:
            connection.execute("INSERT INTO review_logs (user_id, vocab_item_id, rating, reviewed_at, previous_review_level, "
                               "next_review_level, next_review_at) VALUES (?, ?, 'good', 'garbage', 0, 1, ?)",
                               (self.user, broken, iso(NOW)))
        result = self.q(mode="selected", card_id=[due, fresh])
        self.assertEqual(self.keys(result), [("personal", due)])
        self.assertEqual(result["new_goal"]["new_blocked_reason"], "review_time_unreadable")

    def test_no_writes(self):
        item = self.personal("w")
        self.fsrs("personal", item)
        before = self.snapshot()
        self.q(mode="selected", card_id=item)
        with self.assertRaises(queue.QueueError):
            self.q(mode="selected")
        self.assertEqual(self.snapshot(), before)


if __name__ == "__main__":
    unittest.main()

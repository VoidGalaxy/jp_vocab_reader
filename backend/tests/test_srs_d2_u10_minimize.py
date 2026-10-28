"""Gate D-2 U10-a: snapshot records written as format 2 (named fields, no card content),
format 1 still read, rollback refuses records that lack required values, and card /
deck deletion strips the deleted cards' snapshot content in the delete transaction.

Synthetic SQLite only (QueueCase sets a throwaway DATABASE_URL per test before the
app touches a database).

Run directly:      python tests/test_srs_d2_u10_minimize.py
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
from test_srs_d2_u10_baseline import BaselineCase  # noqa: E402
from test_srs_d2_u9_receipts import U9Case  # noqa: E402
from test_srs_queue import NOW, iso  # noqa: E402
import race_support  # noqa: E402

from app.database import get_connection  # noqa: E402
from app.repositories import deck_repository, vocab_repository  # noqa: E402
from app.repositories.deck_repository import create_deck  # noqa: E402
from app.repositories.vocab_repository import create_or_update_vocab_item  # noqa: E402
from app.schemas import DeckCreate, VocabItemCreate  # noqa: E402
from app.srs import identity, migration, reviews  # noqa: E402
from app.srs.storage import SrsWriteError, load_card  # noqa: E402

DAY = timedelta(days=1)
CONTENT = ("surface", "base_form", "reading", "meaning_ko", "example_sentence", "context_explanation_ko",
           "dictionary_gloss", "normalized_form", "part_of_speech", "quality_tag", "deck_id", "status")


class MinCase(BaselineCase, U9Case):
    def records(self, kind, ref):
        with get_connection() as c:
            return [dict(r) for r in c.execute(
                "SELECT s.*, r.mode FROM srs_migration_snapshots s JOIN srs_migration_runs r ON r.id = s.run_id "
                "WHERE s.user_id = ? AND s.card_kind = ? AND s.card_ref = ? ORDER BY s.id", (self.user, kind, ref))]

    def payload(self, record):
        return json.loads(record["legacy_json"])

    def content_card(self, name, deck=None):
        ref = create_or_update_vocab_item(self.user, VocabItemCreate(
            surface=name, base_form=name, reading=f"{name}-よみ", meaning_ko=f"{name}-뜻", status="unknown",
            deck_id=deck or self.deck, example_sentence=f"{name}の例文", context_explanation_ko=f"{name}-문맥"))[0]["id"]
        with get_connection() as c:
            c.execute("UPDATE vocab_items SET srs_engine = 'legacy', srs_config_version = NULL, srs_participation = NULL, "
                      "srs_history_quality = NULL, last_reviewed_at = ?, correct_count = 2, next_review_at = ? WHERE id = ?",
                      (iso(NOW - 9 * DAY), iso(NOW - timedelta(hours=1)), ref))
        return ref

    def apply(self, *refs, run):
        return migration.apply_plan(migration.dry_run([self.key("personal", r) for r in refs]), run, approved=True)

    def extra_run(self, key):
        """A separate synthetic apply run (records are unique per run and card)."""
        with get_connection() as c:
            return c.execute("INSERT INTO srs_migration_runs (run_key, mode, status, scope_json, engine, library_version, "
                             "config_version, started_at) VALUES (?, 'apply', 'completed', ?, 'fsrs', 'x', 'x', ?) RETURNING id",
                             (key, json.dumps({"user_id": self.user, "cards": []}), iso(NOW))).fetchone()["id"]

    def to_format1(self, record_id, full_card):
        with get_connection() as c:
            payload = json.loads(c.execute("SELECT legacy_json FROM srs_migration_snapshots WHERE id = ?",
                                           (record_id,)).fetchone()[0])
            payload.pop("format", None)
            payload["card"] = full_card
            c.execute("UPDATE srs_migration_snapshots SET legacy_json = ? WHERE id = ?",
                      (json.dumps(payload, ensure_ascii=False), record_id))


# ---------------------------------------------------------------------------
class FormatTests(MinCase):
    def test_new_records_name_their_fields(self):
        ref = self.content_card("犬")
        full_before = self.card_row("personal", ref)
        self.apply(ref, run="run-fmt")
        self.rate_at("personal", ref, NOW, "good")
        self.now = NOW
        self.rollback("personal", ref, source="run-fmt")
        apply_rec, rollback_rec = self.records("personal", ref)
        a, r = self.payload(apply_rec), self.payload(rollback_rec)
        self.assertEqual((a["format"], r["format"]), (2, 2))
        self.assertEqual(set(a["card"]), set(migration.APPLY_CARD_FIELDS["personal"]))
        self.assertEqual(set(r["card"]), set(migration.ROLLBACK_CARD_FIELDS["personal"]))
        self.assertEqual({k: a["card"][k] for k in a["card"]}, {k: full_before[k] for k in a["card"]})
        for record in (apply_rec, rollback_rec):
            for column in ("legacy_json", "srs_before_json", "srs_after_json"):
                text = record[column] or ""
                for word in ("犬-뜻", "犬の例文", "犬-よみ", "犬-문맥"):
                    self.assertNotIn(word, text)
        # The baseline fingerprint is still computed from the full card row.
        with get_connection() as c:
            card = load_card(c, self.key("personal", ref))
        self.assertEqual(r["baseline"]["card_fingerprint"], migration._card_print(card))

    def test_subscribed_identity_fields(self):
        deck = self.shared_deck("s")
        lexeme = self.converted("lexeme", "山", deck)
        record = self.payload(self.records("lexeme", lexeme)[0])
        self.assertEqual(set(record["card"]), set(migration.APPLY_CARD_FIELDS["lexeme"]))
        self.assertEqual(record["card"]["lexeme_id"], lexeme)

    def test_format1_and_format2_roll_back_the_same(self):
        refs = [self.content_card(f"twin{i}") for i in range(2)]
        fulls = [self.card_row("personal", r) for r in refs]
        for i, ref in enumerate(refs):
            self.apply(ref, run=f"run-twin{i}")
            self.rate_at("personal", ref, NOW, "good")
            self.rate_at("personal", ref, NOW + 2 * DAY, "hard")
            self.now = NOW
        self.to_format1(self.records("personal", refs[0])[0]["id"], fulls[0])
        for i, ref in enumerate(refs):
            self.assertEqual(self.rollback("personal", ref, source=f"run-twin{i}")[0]["result"], "rolled_back")
        fields = ("review_level", "next_review_at", "srs_engine", "srs_state", "srs_config_version", "srs_participation",
                  "srs_effective_due_at", "srs_history_quality", "first_completed_at", "completion_metric_version")
        self.assertEqual(*[{f: self.card_row("personal", r)[f] for f in fields} for r in refs])
        for ref in refs:
            self.assertEqual(self.reconvert("personal", ref)[2]["reconversion"], "restored")


class RequiredFieldTests(MinCase):
    def rollback_with(self, change):
        ref = self.content_card("rq")
        self.apply(ref, run="run-rq")
        record = self.records("personal", ref)[0]
        payload = self.payload(record)
        text = change(payload)
        with get_connection() as c:
            c.execute("UPDATE srs_migration_snapshots SET legacy_json = ? WHERE id = ?",
                      (text if isinstance(text, str) else json.dumps(payload), record["id"]))
        version = self.card_row("personal", ref)["srs_card_version"]
        result = migration.rollback_plan("run-rq", "rb-rq", user_id=self.user, approved=True)[0]
        return result, self.card_row("personal", ref), version

    def assert_blocked(self, change):
        result, card, version = self.rollback_with(change)
        self.assertEqual((result["result"], result.get("reason")), ("blocked", "snapshot_incomplete"))
        self.assertEqual((card["srs_engine"], card["srs_card_version"]), ("fsrs", version))

    def test_missing_wrong_or_meaningless_values_block(self):
        cases = {
            "missing srs_state": lambda p: p["card"].pop("srs_state"),
            "missing review_level": lambda p: p["card"].pop("review_level"),
            "missing next_review_at": lambda p: p["card"].pop("next_review_at"),
            "missing first_completed_at": lambda p: p["card"].pop("first_completed_at"),
            "missing last_log_id": lambda p: p.pop("last_log_id"),
            "review_level text": lambda p: p["card"].update(review_level="x"),
            "review_level bool": lambda p: p["card"].update(review_level=True),
            "next_review_at number": lambda p: p["card"].update(next_review_at=5),
            "engine not legacy": lambda p: p["card"].update(srs_engine="fsrs"),
            "unknown format": lambda p: p.update(format=3),
            "card not object": lambda p: p.update(card=[1]),
            "broken json": lambda p: "{broken",
        }
        for name, change in cases.items():
            with self.subTest(name=name):
                self.assert_blocked(change)
                self.tearDown_case()

    def tearDown_case(self):
        with get_connection() as c:
            c.execute("DELETE FROM srs_migration_snapshots")
            c.execute("DELETE FROM srs_migration_runs")
            c.execute("DELETE FROM vocab_items WHERE surface = 'rq'")

    def test_allowed_nulls_roll_back(self):
        result, card, _ = self.rollback_with(lambda p: p["card"].update(next_review_at=None, srs_config_version=None,
                                                                         completion_metric_version=None))
        self.assertEqual(result["result"], "rolled_back")
        self.assertEqual(card["srs_engine"], "legacy")

    def test_mixed_run_reports_each_card_honestly(self):
        refs = [self.content_card(f"mx{i}") for i in range(3)]
        self.apply(*refs, run="run-mx")
        bad = self.records("personal", refs[1])[0]
        payload = self.payload(bad)
        payload["card"].pop("srs_effective_due_at")
        with get_connection() as c:
            c.execute("UPDATE srs_migration_snapshots SET legacy_json = ? WHERE id = ?", (json.dumps(payload), bad["id"]))
        self.reconvert_blocker = None
        with get_connection() as c:  # third card already legacy again -> conflict
            c.execute("UPDATE vocab_items SET srs_engine = 'legacy' WHERE id = ?", (refs[2],))
        results = {r["ref_id"]: r["result"] for r in migration.rollback_plan("run-mx", "rb-mx", user_id=self.user, approved=True)}
        self.assertEqual(results, {refs[0]: "rolled_back", refs[1]: "blocked", refs[2]: "conflict"})


# ---------------------------------------------------------------------------
class DeleteTests(MinCase):
    def setup_card(self, name, deck=None, damaged=True):
        """A card with: format-1 apply record, format-1 rollback record, format-2 apply record
        (re-conversion), and a damaged record."""
        ref = self.content_card(name, deck)
        full = self.card_row("personal", ref)
        self.apply(ref, run=f"run-{name}")
        self.rate_at("personal", ref, NOW, "good")
        self.now = NOW
        self.rollback("personal", ref, source=f"run-{name}")
        after_rb = self.card_row("personal", ref)
        recs = self.records("personal", ref)
        self.to_format1(recs[0]["id"], full)
        self.to_format1(recs[1]["id"], after_rb)
        self.reconvert("personal", ref)
        if not damaged:
            return ref
        damaged_run = self.extra_run(f"damaged-{name}")
        with get_connection() as c:  # a damaged record of this card (synthetic, its own run)
            c.execute("INSERT INTO srs_migration_snapshots (run_id, user_id, card_kind, card_ref, card_version_before, "
                      "legacy_json, srs_before_json, srs_after_json, history_quality, history_flags, created_at) "
                      "SELECT ?, user_id, card_kind, card_ref, 999, '{broken', 'null', 'null', NULL, NULL, created_at "
                      "FROM srs_migration_snapshots WHERE id = ?", (damaged_run, recs[0]["id"]))
        return ref

    def table(self, name):
        with get_connection() as c:
            return [tuple(r) for r in c.execute(f"SELECT * FROM {name} ORDER BY 1")]

    def test_word_delete(self):
        ref = self.setup_card("del")
        keep = self.setup_card("keep", damaged=False)
        deck = self.shared_deck("s")
        lexeme = self.converted("lexeme", "同", deck)
        keep_rows = self.records("personal", keep)
        lexeme_rows = self.records("lexeme", lexeme)
        logs = self.table("review_logs")
        before = self.records("personal", ref)
        response = self.client.delete(f"/vocab-items/{ref}", headers=self.headers)
        self.assertEqual(response.status_code, 204)
        after = self.records("personal", ref)
        self.assertEqual([r["id"] for r in after], [r["id"] for r in before if r["legacy_json"] != "{broken"])
        for record in after:
            payload = self.payload(record)
            fields = (migration.APPLY_CARD_FIELDS if record["mode"] == "apply" else migration.ROLLBACK_CARD_FIELDS)["personal"]
            self.assertEqual(payload["format"], 2)
            self.assertLessEqual(set(payload["card"]), set(fields))
            self.assertNotIn("del-뜻", record["legacy_json"])
            original = next(json.loads(b["legacy_json"]) for b in before if b["id"] == record["id"])
            for key in ("last_log_id", "baseline", "restart"):
                self.assertEqual(payload.get(key), original.get(key))  # proof / permission values kept
            self.assertEqual({k: payload["card"][k] for k in payload["card"]},
                             {k: original["card"][k] for k in payload["card"]})
        self.assertEqual(self.records("personal", keep), keep_rows)
        self.assertEqual(self.records("lexeme", lexeme), lexeme_rows)
        self.assertEqual(self.table("review_logs"), logs)
        with get_connection() as c:
            identity.personal_id_references(c)  # the remaining minimal records still read
        state = self.counts()
        self.assertEqual(self.post("personal", ref, NOW + 3 * DAY, "after-delete", 1).status_code, 404)
        self.assertEqual(self.counts(), state)

    def test_deck_delete_and_other_account(self):
        deck = create_deck(self.user, DeckCreate(name="gone"))[0]["id"]
        refs = [self.setup_card(f"dk{i}", deck) for i in range(2)]
        theirs_run = self.extra_run("theirs")
        with get_connection() as c:  # another account's record naming the same id
            c.execute("INSERT INTO srs_migration_snapshots (run_id, user_id, card_kind, card_ref, card_version_before, "
                      "legacy_json, srs_before_json, srs_after_json, history_quality, history_flags, created_at) "
                      "SELECT ?, ?, card_kind, card_ref, 77, legacy_json, srs_before_json, srs_after_json, history_quality, "
                      "history_flags, created_at FROM srs_migration_snapshots WHERE card_ref = ? ORDER BY id LIMIT 1",
                      (theirs_run, self.other, refs[0]))
            theirs = [tuple(r) for r in c.execute("SELECT * FROM srs_migration_snapshots WHERE user_id = ?", (self.other,))]
        self.assertEqual(deck_repository.delete_deck_with_items(self.user, deck)["deleted_vocab_count"], 2)
        for ref in refs:
            for record in self.records("personal", ref):
                self.assertEqual(self.payload(record)["format"], 2)
                self.assertNotIn("뜻", record["legacy_json"])
        with get_connection() as c:
            self.assertEqual([tuple(r) for r in c.execute("SELECT * FROM srs_migration_snapshots WHERE user_id = ?",
                                                         (self.other,))], theirs)

    def test_failure_and_cas_roll_everything_back(self):
        class Boom(Exception):
            pass

        ref = self.setup_card("fail")
        self.assertEqual(self.post("personal", ref, NOW + 4 * DAY, "fail-r", self.version("personal", ref)).status_code, 200)
        before = self.everything()
        with mock.patch("app.srs.identity.record_personal_deletions", side_effect=Boom()):
            with self.assertRaises(Boom):
                vocab_repository.delete_vocab_item(self.user, ref)
        self.assertEqual(self.everything(), before)  # snapshots, receipts, ledger, card
        real = migration._json
        holder = {"done": False}

        def changing(value):
            if not holder["done"] and isinstance(value, dict) and value.get("format") == 2 and "card" in value:
                holder["done"] = True
                holder["conn"].execute("UPDATE srs_migration_snapshots SET legacy_json = legacy_json || ' ' "
                                       "WHERE card_ref = ? AND legacy_json NOT LIKE '%\"format\":2%'", (ref,))
            return real(value)

        real_strip = migration.strip_card_snapshots

        def strip(connection, *a, **k):
            holder["conn"] = connection
            return real_strip(connection, *a, **k)

        with mock.patch.object(migration, "_json", changing), mock.patch.object(migration, "strip_card_snapshots", strip):
            with self.assertRaises(SrsWriteError) as caught:
                vocab_repository.delete_vocab_item(self.user, ref)
        self.assertEqual(caught.exception.code, "snapshot_content_unverified")
        self.assertEqual(self.everything(), before)


# ---------------------------------------------------------------------------
class RaceTests(MinCase):
    def race(self, first, second, jobs, target, name):
        entered, release = threading.Event(), threading.Event()
        real = getattr(target, name)

        def slow(*a, **k):
            result = real(*a, **k)
            if not entered.is_set():
                entered.set()
                self.assertTrue(release.wait(15))
            return result

        with race_support.LockProbe() as probe, mock.patch.object(target, name, slow):
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

    def test_delete_and_rollback_both_orders(self):
        for first in ("rollback", "delete"):
            with self.subTest(first=first):
                ref = self.content_card(f"rr-{first}")
                self.apply(ref, run=f"run-rr-{first}")
                self.rate_at("personal", ref, NOW, "good")
                self.now = NOW
                jobs = {"rollback": lambda: migration.rollback_plan(f"run-rr-{first}", f"rb-rr-{first}", user_id=self.user,
                                                                    approved=True),
                        "delete": lambda: vocab_repository.delete_vocab_item(self.user, ref)}
                target = (migration, "_rollback_input") if first == "rollback" else (migration, "strip_card_snapshots")
                second = "delete" if first == "rollback" else "rollback"
                results = self.race(first, second, jobs, *target)
                self.assertTrue(results["delete"])
                expected = "rolled_back" if first == "rollback" else "missing_or_access_lost"
                self.assertEqual(results["rollback"][0]["result"], expected)
                for record in self.records("personal", ref):
                    self.assertNotIn(f"rr-{first}-뜻", record["legacy_json"])

    def test_delete_and_plan_b_first_review_both_orders(self):
        for first in ("review", "delete"):
            with self.subTest(first=first):
                ref, boundary, run, at = self.to_plan_b("personal", name=f"bb-{first}")
                version = self.card_row("personal", ref)["srs_card_version"]

                def review():
                    with mock.patch.object(reviews, "now_utc", return_value=at):
                        return vocab_repository.record_review(self.user, ref, "good", request_id=f"bb-{first}",
                                                              expected_card_version=version, session_id="s1")

                jobs = {"review": review, "delete": lambda: vocab_repository.delete_vocab_item(self.user, ref)}
                target = (reviews, "introduced_on") if first == "review" else (migration, "strip_card_snapshots")
                second = "delete" if first == "review" else "review"
                results = self.race(first, second, jobs, *target)
                self.assertTrue(results["delete"])
                if first == "review":
                    self.assertEqual(results["review"]["card_kind"], "personal")
                    self.assertEqual(len(self.restarts("personal", ref)), 1)
                else:
                    self.assertIsNone(results["review"])  # card gone: 404 at the URL
                    self.assertEqual(self.restarts("personal", ref), [])


if __name__ == "__main__":
    unittest.main()

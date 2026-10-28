"""Gate D-2 U11 review fix: completion evidence of FSRS cards WITHOUT an evidence
boundary (new personal cards, subscribed words first rated atomically, cards converted
from a complete legacy history) must be a verified chain too.

Before the fix a "fresh"/"complete" history-quality mark alone made the evidence
complete, so an unexplained card-version jump still produced `completed` and a V3
first completion. The U7/U8 tests only covered U5 (boundary) cards.

Synthetic SQLite only (QueueCase sets a throwaway DATABASE_URL per test). Synthetic
schedules show what the rule requires, not a learning effect.

Run directly:      python tests/test_srs_d2_u11_plain_evidence.py
Or via discovery:   python -m unittest discover -s tests
"""

from __future__ import annotations

import json
import sys
import unittest
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_srs_d2_u11_completion import ReviewCase  # noqa: E402
from test_srs_queue import NOW, iso  # noqa: E402

from app.database import get_connection  # noqa: E402
from app.srs import migration  # noqa: E402
from app.srs.completion import METRIC_VERSION  # noqa: E402

DAY = timedelta(days=1)
V3_DAYS = (0, 8, 74)  # three easy reviews at the scheduler's due times complete V3 (synthetic)


class PlainCase(ReviewCase):
    def setUp(self):
        super().setUp()
        self._req = 0

    def born(self, kind, name):
        """A card that is FSRS from its first review: a new personal card in the FSRS
        account, or a subscribed word with no progress row (created by its first review)."""
        if kind == "personal":
            return self.fresh_personal(name), None
        deck = getattr(self, "_plain_deck", None) or self.shared_deck("plain")
        self._plain_deck = deck
        self._lx = getattr(self, "_lx", 0) + 1
        return self.lexeme(name, deck, self._lx, progress=False), deck

    def review(self, kind, ref, deck, at, rating="easy"):
        self._req += 1
        exists = kind == "personal" or self.has_progress(ref)
        version = self.card_row(kind, ref)["srs_card_version"] if exists else None
        response = self.post(kind, ref, at, f"plain-{kind}-{ref}-{self._req}", version, deck, rating=rating)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def has_progress(self, ref):
        with get_connection() as c:
            return c.execute("SELECT 1 FROM user_word_progress WHERE user_id = ? AND lexeme_id = ?",
                             (self.user, ref)).fetchone() is not None

    def bump(self, kind, ref, by=2):
        """A card-version jump nobody can explain (no rollback / re-conversion record)."""
        table, col = ("vocab_items", "id") if kind == "personal" else ("user_word_progress", "lexeme_id")
        with get_connection() as c:
            c.execute(f"UPDATE {table} SET srs_card_version = srs_card_version + ? WHERE user_id = ? AND {col} = ?",
                      (by, self.user, ref))

    def no_completion(self, kind, ref, results):
        self.assertTrue(all(r["completed"] is not True for r in results), [r["completed"] for r in results])
        self.assertTrue(all(r["srs"]["first_completed_at"] is None for r in results))
        cols = self.cols(kind, ref)
        self.assertEqual((cols["first_completed_at"], cols["version_first_completed_at"],
                          cols["version_first_completed_version"]), (None, None, None))

    # -- a card converted from a complete legacy history ---------------------------
    def converted_complete(self, name):
        ref = self.content_card(name)
        with get_connection() as c:
            c.execute("UPDATE vocab_items SET correct_count = 0, wrong_count = 0, review_level = 0, "
                      "last_reviewed_at = NULL, next_review_at = NULL WHERE id = ?", (ref,))
        for d in (0, 8, 74, 200):
            self.legacy_change("personal", ref, NOW - 300 * DAY + d * DAY)
        plan = migration.dry_run([self.key("personal", ref)])
        self.assertEqual(plan[0].quality, "complete")
        self.assertEqual(migration.apply_plan(plan, f"run-legacy-{ref}", approved=True)[0]["result"], "applied")
        return ref

    def tamper_log(self, kind, ref, index, **values):
        table, col = ("review_logs", "vocab_item_id") if kind == "personal" else ("lexeme_review_logs", "lexeme_id")
        log = self.logs_of(kind, ref)[index]
        with get_connection() as c:
            c.execute(f"UPDATE {table} SET " + ", ".join(f"{k} = ?" for k in values) + " WHERE id = ?",
                      (*values.values(), log["id"]))


# ---------------------------------------------------------------------------
class ReproductionTests(PlainCase):
    """The reported paths: first Easy -> unexplained +2 -> Easy 8 and 74 days later."""

    def check(self, kind):
        ref, deck = self.born(kind, f"gap-{kind}")
        results = [self.review(kind, ref, deck, NOW)]
        self.bump(kind, ref)
        results += [self.review(kind, ref, deck, NOW + d * DAY) for d in V3_DAYS[1:]]
        results += [self.review(kind, ref, deck, NOW + d * DAY) for d in (200, 400)]  # more follow-ups
        self.no_completion(kind, ref, results)
        self.assertEqual([r["completion_metric_version"] for r in results], [METRIC_VERSION] * 5)
        self.assertEqual(len(self.logs_of(kind, ref)), 5)  # every review is still recorded

    def test_new_personal_card(self):
        self.check("personal")

    def test_subscribed_first_review(self):
        self.check("lexeme")

    def test_gap_after_the_last_log(self):
        for kind in ("personal", "lexeme"):
            with self.subTest(kind=kind):
                ref, deck = self.born(kind, f"tail-{kind}")
                results = [self.review(kind, ref, deck, NOW + d * DAY) for d in V3_DAYS[:2]]
                self.bump(kind, ref)
                results += [self.review(kind, ref, deck, NOW + d * DAY) for d in (74, 200)]
                self.no_completion(kind, ref, results)


class NormalTests(PlainCase):
    def test_new_cards_complete_with_enough_evidence(self):
        for kind in ("personal", "lexeme"):
            with self.subTest(kind=kind):
                ref, deck = self.born(kind, f"ok-{kind}")
                results = [self.review(kind, ref, deck, NOW + d * DAY) for d in V3_DAYS]
                self.assertEqual([r["completed"] for r in results], [False, False, True])
                self.assertEqual(results[0]["srs"]["card_version"], 1)  # first review from CAS 0
                cols = self.cols(kind, ref)
                self.assertEqual(cols["version_first_completed_at"], results[-1]["accepted_at"])

    def test_existing_completion_history_is_kept_when_evidence_breaks(self):
        for kind in ("personal", "lexeme"):
            with self.subTest(kind=kind):
                ref, deck = self.born(kind, f"kept-{kind}")
                done = [self.review(kind, ref, deck, NOW + d * DAY) for d in V3_DAYS][-1]
                self.assertTrue(done["completed"])
                kept = self.cols(kind, ref)
                self.bump(kind, ref)
                later = [self.review(kind, ref, deck, NOW + d * DAY, rating) for d, rating in ((200, "again"), (210, "easy"))]
                self.assertTrue(all(r["completed"] is not True for r in later))
                after = self.cols(kind, ref)
                for name in ("first_completed_at", "first_completed_source", "version_first_completed_at",
                             "version_first_completed_version"):
                    self.assertEqual(after[name], kept[name], name)
                self.assertEqual([r["srs"]["first_completed_at"] for r in later], [kept["version_first_completed_at"]] * 2)

    def test_retry_is_the_first_answer_and_writes_nothing(self):
        ref, deck = self.born("lexeme", "retry")
        first = self.post("lexeme", ref, NOW, "plain-retry", None, deck, rating="easy")
        before = self.everything()
        again = self.post("lexeme", ref, NOW + DAY, "plain-retry", None, deck, rating="easy")
        self.assertEqual((first.status_code, again.content), (200, first.content))
        self.assertEqual(self.everything(), before)


class TamperTests(PlainCase):
    def run_tamper(self, name, change):
        for kind in ("personal", "lexeme"):
            with self.subTest(case=name, kind=kind):
                ref, deck = self.born(kind, f"t{len(name)}-{name[:4]}-{kind}")
                results = [self.review(kind, ref, deck, NOW + d * DAY) for d in V3_DAYS[:2]]
                change(kind, ref)
                results += [self.review(kind, ref, deck, NOW + d * DAY) for d in (74, 200)]
                self.no_completion(kind, ref, results)

    def test_time(self):
        self.run_tamper("time", lambda k, r: self.tamper_log(k, r, 1, **{
            ("reviewed_at" if k == "personal" else "created_at"): iso(NOW + 9 * DAY)}))

    def test_rating(self):
        self.run_tamper("rating", lambda k, r: self.tamper_log(k, r, 0, rating="good"))

    def test_config(self):
        self.run_tamper("config", lambda k, r: self.tamper_log(k, r, 1, srs_config_version="fsrs-other"))

    def test_snapshot_value(self):
        def change(kind, ref):
            log = self.logs_of(kind, ref)[1]
            after = json.loads(log["srs_after_json"])
            after["stability"] = after["stability"] + 1
            self.tamper_log(kind, ref, 1, srs_after_json=json.dumps(after))
        self.run_tamper("snapshot", change)

    def test_unreadable_snapshot_is_incomplete_not_refused(self):
        self.run_tamper("unparseable", lambda k, r: self.tamper_log(k, r, 0, srs_before_json="{broken"))

    def test_log_version(self):
        self.run_tamper("version", lambda k, r: self.tamper_log(k, r, 1, card_version_before=5))

    def test_another_cards_restoration_records_prove_nothing(self):
        donor = self.converted_complete("donor")
        self.review("personal", donor, None, NOW + DAY)
        self.now = NOW
        self.rollback("personal", donor, source=f"run-legacy-{donor}")
        self.assertEqual(self.reconvert("personal", donor)[2]["reconversion"], "restored")
        ref, _ = self.born("personal", "borrower")
        results = [self.review("personal", ref, None, NOW + d * DAY) for d in V3_DAYS[:2]]
        self.bump("personal", ref)
        with get_connection() as c:  # the donor's proof records, relabelled to this card (same and other account)
            rows = [dict(r) for r in c.execute(
                "SELECT s.*, r.run_key FROM srs_migration_snapshots s JOIN srs_migration_runs r ON r.id = s.run_id "
                "WHERE s.card_kind = 'personal' AND s.card_ref = ? ORDER BY s.id", (donor,))][1:]
            for n, user in enumerate((self.user, self.other)):
                for row in rows:
                    run = c.execute(
                        "INSERT INTO srs_migration_runs (run_key, mode, status, scope_json, engine, library_version, "
                        "config_version, started_at, finished_at, summary_json) SELECT run_key || ?, mode, status, "
                        "scope_json, engine, library_version, config_version, started_at, finished_at, summary_json "
                        "FROM srs_migration_runs WHERE id = ? RETURNING id", (f"-copy{n}", row["run_id"])).fetchone()["id"]
                    c.execute("INSERT INTO srs_migration_snapshots (run_id, user_id, card_kind, card_ref, card_version_before, "
                              "legacy_json, srs_before_json, srs_after_json, history_quality, history_flags, created_at) "
                              "VALUES (?, ?, 'personal', ?, ?, ?, ?, ?, ?, ?, ?)",
                              (run, user, ref, row["card_version_before"], row["legacy_json"], row["srs_before_json"],
                               row["srs_after_json"], row["history_quality"], row["history_flags"], row["created_at"]))
        results += [self.review("personal", ref, None, NOW + d * DAY) for d in (74, 200)]
        self.no_completion("personal", ref, results)

class LegacyConversionTests(PlainCase):
    def test_complete_legacy_conversion_completes(self):
        ref = self.converted_complete("legacy-ok")
        result = self.review("personal", ref, None, NOW + 30 * DAY, "good")
        self.assertTrue(result["completed"])  # legacy evidence + this review (synthetic)
        self.assertEqual(self.cols("personal", ref)["version_first_completed_at"], result["accepted_at"])

    def test_gap_after_conversion_never_completes(self):
        ref = self.converted_complete("legacy-gap")
        self.bump("personal", ref)
        results = [self.review("personal", ref, None, NOW + d * DAY, "good") for d in (30, 200)]
        self.no_completion("personal", ref, results)

    def test_legacy_log_changed_after_conversion(self):
        ref = self.converted_complete("legacy-edit")
        self.tamper_log("personal", ref, 1, reviewed_at=iso(NOW - 291 * DAY))
        results = [self.review("personal", ref, None, NOW + d * DAY, "good") for d in (30, 200)]
        self.no_completion("personal", ref, results)

    def test_mixed_history_log_after_conversion(self):
        ref = self.converted_complete("legacy-mixed")
        with get_connection() as c:  # a legacy log written after the conversion (mixed history)
            c.execute("INSERT INTO review_logs (user_id, vocab_item_id, rating, reviewed_at, previous_review_level, "
                      "next_review_level, next_review_at) VALUES (?, ?, 'good', ?, 0, 1, ?)",
                      (self.user, ref, iso(NOW + DAY), iso(NOW)))
        results = [self.review("personal", ref, None, NOW + d * DAY, "good") for d in (30, 200)]
        self.no_completion("personal", ref, results)

    def test_restored_after_rollback_completes(self):
        ref = self.converted_complete("legacy-restore")
        self.review("personal", ref, None, NOW + DAY, "good")
        self.now = NOW
        self.rollback("personal", ref, source=f"run-legacy-{ref}")
        self.assertEqual(self.reconvert("personal", ref)[2]["reconversion"], "restored")
        result = self.review("personal", ref, None, NOW + 40 * DAY, "good")
        self.assertTrue(result["completed"])  # the rollback + restore jump is proven


if __name__ == "__main__":
    unittest.main()

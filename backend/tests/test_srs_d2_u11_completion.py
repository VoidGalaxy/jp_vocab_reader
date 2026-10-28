"""Gate D-2 U11: completion V3 `meaning-completion-v1` judged by the server on new
real FSRS reviews, with the first completion's source kept apart (B plan,
U11_DESIGN_B section 8).

- pure rule: every condition's boundaries, Seoul midnight, offsets, same-day
  repeats, Again reset, the two "almost" cases;
- the stored-column contract (`completion_update`) row by row;
- personal and subscribed cards through the real review path: first V3 completion,
  failure / pause / re-engagement, draft first completion kept with its source,
  damaged values preserved, retries, concurrency, evidence protection, conversion
  (no completion from replayed history), rollback / re-conversion / plan B / U10
  tools, and an upgrade from the schema without the new columns.

Synthetic SQLite only (QueueCase sets a throwaway DATABASE_URL per test).
Synthetic schedules show what the rule requires; they are not evidence of a
learning effect or of real recall.

Run directly:      python tests/test_srs_d2_u11_completion.py
Or via discovery:   python -m unittest discover -s tests
"""

from __future__ import annotations

import json
import sqlite3
import sys
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_srs_d2_u10_value_shape import ValueShapeCase  # noqa: E402
from test_srs_queue import NOW, iso  # noqa: E402
import race_support  # noqa: E402

from app.database import get_connection  # noqa: E402
from app.repositories import vocab_repository  # noqa: E402
from app.srs import completion, migration, reviews, schema  # noqa: E402
from app.srs.completion import (  # noqa: E402
    DRAFT_METRIC_VERSION, METRIC_VERSION, CompletionCheck, CompletionStatus, ReviewEvent, completion_update,
    evaluate_completion,
)
from app.srs.engine import SrsCardState, SrsPhase  # noqa: E402
from app.srs.storage import SrsWriteError  # noqa: E402

UTC = timezone.utc
DAY = timedelta(days=1)
T0 = datetime(2026, 10, 9, 3, 0, tzinfo=UTC)  # 12:00 KST
SEC = timedelta(seconds=1)
NEW_COLUMNS = completion.COMPLETION_HISTORY_COLUMNS


def state(last, stability=40.0, phase=SrsPhase.REVIEW, step=None):
    return SrsCardState(phase=phase, step=step, stability=stability, difficulty=5.0,
                        due_at=last + 30 * DAY, last_review_at=last)


def judge(pairs, stability=40.0, phase=SrsPhase.REVIEW):
    evs = [ReviewEvent(at, rating) for rating, at in pairs]
    last = evs[-1].reviewed_at.astimezone(UTC)
    return evaluate_completion(state(last, stability, phase, 0 if phase is not SrsPhase.REVIEW else None),
                               evs, evidence_complete=True)


GOOD3 = [("good", T0), ("good", T0 + 7 * DAY), ("good", T0 + 14 * DAY)]


# ---------------------------------------------------------------------------
class RuleTests(unittest.TestCase):
    def test_version_and_all_four_conditions(self):
        check = judge(GOOD3)
        self.assertEqual((check.status, check.metric_version), (CompletionStatus.COMPLETED, "meaning-completion-v1"))
        self.assertEqual(judge(GOOD3, phase=SrsPhase.RELEARNING).status, CompletionStatus.NOT_COMPLETED)

    def test_stability_boundary(self):
        for value, done in ((30.0 - 1e-9, False), (30.0, True), (30.0 + 1e-9, True)):
            with self.subTest(stability=value):
                self.assertEqual(judge(GOOD3, stability=value).status is CompletionStatus.COMPLETED, done)

    def test_seven_day_boundary_on_the_second_spaced_success(self):
        base = GOOD3[:2]
        for gap, done in ((7 * DAY - SEC, False), (7 * DAY, True), (7 * DAY + SEC, True)):
            with self.subTest(gap=gap):
                check = judge(base + [("good", base[-1][1] + gap)])
                self.assertEqual(check.spaced_success_ok, done)
                self.assertEqual(check.status is CompletionStatus.COMPLETED, done)

    def test_gap_is_from_the_preceding_real_review_not_the_previous_success_or_dates(self):
        # 8 days after the previous success but 1 hour after an Again-free hard review in between
        pairs = [("good", T0), ("good", T0 + 7 * DAY), ("hard", T0 + 15 * DAY - timedelta(hours=1)),
                 ("good", T0 + 15 * DAY)]
        check = judge(pairs)
        self.assertTrue(check.spaced_success_ok)  # 1st and the hard one are spaced; the last is not
        # Calendar-day difference of 7 but less than 7x24h is not spaced.
        pairs = [("good", T0), ("good", T0 + 7 * DAY), ("good", datetime(2026, 10, 22, 16, 0, tzinfo=UTC))]
        self.assertFalse(judge(pairs).spaced_success_ok)  # 10-23 01:00 KST is 7 Seoul days later, 6d13h

    def test_seoul_midnight(self):
        before, after = datetime(2026, 10, 9, 14, 59, 59, tzinfo=UTC), datetime(2026, 10, 9, 15, 0, 0, tzinfo=UTC)
        pairs = [("good", before - 7 * DAY), ("good", before), ("good", after), ("good", after + 7 * DAY)]
        self.assertEqual(len({completion.seoul_date(at) for _, at in pairs}), 4)
        same = [("good", after - 7 * DAY), ("good", after), ("good", after + timedelta(hours=23, minutes=59)),
                ("good", after + 8 * DAY)]
        check = judge(same)
        self.assertEqual(len({completion.seoul_date(at) for _, at in same}), 3)
        self.assertTrue(check.success_dates_ok)

    def test_offsets_do_not_change_the_result(self):
        for hours in (0, 9, -5):
            zone = timezone(timedelta(hours=hours))
            with self.subTest(offset=hours):
                pairs = [(r, at.astimezone(zone)) for r, at in GOOD3]
                self.assertEqual(judge(pairs), judge(GOOD3))

    def test_same_day_repeats_count_once(self):
        pairs = [("good", T0 + i * timedelta(minutes=10)) for i in range(6)] + [("good", T0 + 8 * DAY)]
        check = judge(pairs)
        self.assertFalse(check.success_dates_ok)  # two dates
        self.assertEqual(check.status, CompletionStatus.NOT_COMPLETED)

    def test_again_resets_the_evidence(self):
        pairs = GOOD3 + [("again", T0 + 30 * DAY), ("good", T0 + 31 * DAY)]
        check = judge(pairs)
        self.assertFalse(check.success_dates_ok)
        pairs += [("good", T0 + 38 * DAY), ("good", T0 + 45 * DAY)]
        self.assertEqual(judge(pairs).status, CompletionStatus.COMPLETED)

    def test_three_dates_with_one_long_gap_is_rejected(self):
        pairs = [("good", T0), ("good", T0 + DAY), ("good", T0 + 8 * DAY)]
        check = judge(pairs)
        self.assertEqual((check.success_dates_ok, check.spaced_success_ok), (True, False))
        self.assertEqual(check.status, CompletionStatus.NOT_COMPLETED)

    def test_two_long_gaps_with_two_dates_is_rejected(self):
        pairs = [("again", T0), ("good", T0 + 7 * DAY), ("good", T0 + 14 * DAY)]
        check = judge(pairs)
        self.assertEqual((check.success_dates_ok, check.spaced_success_ok), (False, True))
        self.assertEqual(check.status, CompletionStatus.NOT_COMPLETED)

    def test_hard_is_a_success(self):
        self.assertEqual(judge([(r.replace("good", "hard"), at) for r, at in GOOD3]).status, CompletionStatus.COMPLETED)


# ---------------------------------------------------------------------------
def check_of(status):
    return CompletionCheck(status, METRIC_VERSION, None, None, None, None, ())


C, N, U = (check_of(s) for s in (CompletionStatus.COMPLETED, CompletionStatus.NOT_COMPLETED, CompletionStatus.UNKNOWN))
AT = T0 + 100 * DAY
V3_FIRST = iso(T0 + 50 * DAY)


def card(**values):
    base = {"completion_metric_version": None, "first_completed_at": None, "first_completed_source": None,
            "version_first_completed_at": None, "version_first_completed_version": None}
    base.update(values)
    return base


class StoredContractTests(unittest.TestCase):
    """U11_DESIGN_B 3-4 / 8-3, one row each."""

    def run_row(self, before, check):
        update = completion_update(before, check, AT)
        after = dict(before, **update.values)
        return after, update.current_first_completed_at, update.needs_relearning

    def test_rows(self):
        d = iso(T0)
        draft = dict(completion_metric_version=DRAFT_METRIC_VERSION, first_completed_at=d)
        v3 = dict(completion_metric_version=METRIC_VERSION, first_completed_at=V3_FIRST, first_completed_source=METRIC_VERSION,
                  version_first_completed_at=V3_FIRST, version_first_completed_version=METRIC_VERSION)
        at = AT.isoformat()
        rows = {
            "1 none, not completed": (card(), N, (None, None, None, None), None, False),
            "1 none, unknown": (card(), U, (None, None, None, None), None, False),
            "2 none, completed": (card(), C, (at, METRIC_VERSION, at, METRIC_VERSION), at, False),
            "3 v3 first, failure": (card(**v3), N, (V3_FIRST, METRIC_VERSION, V3_FIRST, METRIC_VERSION), V3_FIRST, True),
            "4 v3 first, unknown": (card(**v3), U, (V3_FIRST, METRIC_VERSION, V3_FIRST, METRIC_VERSION), V3_FIRST, False),
            "5 v3 first, again completed": (card(**v3), C, (V3_FIRST, METRIC_VERSION, V3_FIRST, METRIC_VERSION),
                                            V3_FIRST, False),
            "6 draft first, not completed": (card(**draft), N, (d, DRAFT_METRIC_VERSION, None, None), None, False),
            "7 draft first, completed": (card(**draft), C, (d, DRAFT_METRIC_VERSION, at, METRIC_VERSION), at, False),
            "8 draft + v3 first, failure": (card(**draft, version_first_completed_at=V3_FIRST,
                                                  version_first_completed_version=METRIC_VERSION, first_completed_source=DRAFT_METRIC_VERSION),
                                             N, (d, DRAFT_METRIC_VERSION, V3_FIRST, METRIC_VERSION), V3_FIRST, True),
            "9 first, version missing": (card(first_completed_at=d), C, (d, "source_missing", at, METRIC_VERSION), at, False),
            "10 first unreadable": (card(first_completed_at="garbage", completion_metric_version=DRAFT_METRIC_VERSION), N,
                                    ("garbage", "source_unknown", None, None), None, False),
            "10 first naive": (card(first_completed_at="2026-10-09T03:00:00", completion_metric_version=DRAFT_METRIC_VERSION),
                               N, ("2026-10-09T03:00:00", "source_unknown", None, None), None, False),
            "first with another version": (card(first_completed_at=d, completion_metric_version="other-metric"), N,
                                           (d, "source_unknown", None, None), None, False),
            "source already fixed": (card(first_completed_at=d, first_completed_source=DRAFT_METRIC_VERSION,
                                          completion_metric_version=METRIC_VERSION), N,
                                     (d, DRAFT_METRIC_VERSION, None, None), None, False),
            "inconsistent: no first, source set": (card(first_completed_source=DRAFT_METRIC_VERSION), C,
                                                    (None, DRAFT_METRIC_VERSION, at, METRIC_VERSION), at, False),
            "unsupported pair version (no V4 overwrite)": (
                card(version_first_completed_at=V3_FIRST, version_first_completed_version="meaning-completion-v2"), C,
                (at, METRIC_VERSION, V3_FIRST, "meaning-completion-v2"), None, False),
            "unreadable pair time": (card(version_first_completed_at="garbage", version_first_completed_version=METRIC_VERSION),
                                     N, (None, None, "garbage", METRIC_VERSION), None, False),
            "half pair": (card(version_first_completed_at=V3_FIRST), C, (at, METRIC_VERSION, V3_FIRST, None), None, False),
        }
        for name, (before, check, expected, answer, relearn) in rows.items():
            with self.subTest(row=name):
                after, current, needs = self.run_row(before, check)
                self.assertEqual((after["first_completed_at"], after["first_completed_source"],
                                  after["version_first_completed_at"], after["version_first_completed_version"]), expected)
                self.assertEqual((current, needs), (answer, relearn))
                self.assertEqual(after["completion_metric_version"], METRIC_VERSION)

    def test_draft_alone_never_needs_relearning(self):
        for status in (N, U, C):
            update = completion_update(card(completion_metric_version=DRAFT_METRIC_VERSION, first_completed_at=iso(T0)),
                                       status, AT)
            self.assertFalse(update.needs_relearning)


# ---------------------------------------------------------------------------
class ReviewCase(ValueShapeCase):
    def to_v3(self, kind, ref, deck=None, start=NOW):
        """Three easy reviews at the scheduler's own due times complete V3 (synthetic)."""
        results = []
        for gap in (0, 8, 74):
            results.append(self.rate_at(kind, ref, start + gap * DAY, "easy", deck=deck))
        self.now = NOW
        return results

    def cols(self, kind, ref):
        row = self.card_row(kind, ref)
        return {k: row[k] for k in ("completion_metric_version", "first_completed_at") + NEW_COLUMNS}

    def subject(self, kind, name):
        if kind == "personal":
            return self.converted("personal", name), None
        deck = getattr(self, "_deck_u11", None) or self.shared_deck("u11")
        self._deck_u11 = deck
        self._order = getattr(self, "_order", 0) + 1
        return self.converted("lexeme", name, deck, self._order), deck

    def set_cols(self, kind, ref, **values):
        table, col = ("vocab_items", "id") if kind == "personal" else ("user_word_progress", "lexeme_id")
        with get_connection() as c:
            c.execute(f"UPDATE {table} SET " + ", ".join(f"{k} = ?" for k in values) + f" WHERE {col} = ?",
                      (*values.values(), ref))


class ReviewPathTests(ReviewCase):
    def flow(self, kind):
        ref, deck = self.subject(kind, f"flow-{kind}")
        first, middle, done = self.to_v3(kind, ref, deck)
        self.assertEqual([r["completed"] for r in (first, middle, done)], [False, False, True])
        self.assertEqual(done["completion_metric_version"], METRIC_VERSION)
        at = done["accepted_at"]
        self.assertEqual(done["srs"]["first_completed_at"], at)
        self.assertEqual(self.cols(kind, ref), {
            "completion_metric_version": METRIC_VERSION, "first_completed_at": at,
            "first_completed_source": METRIC_VERSION, "version_first_completed_at": at,
            "version_first_completed_version": METRIC_VERSION})
        failed = self.rate_at(kind, ref, NOW + 300 * DAY, "again", deck=deck)
        self.assertEqual((failed["completed"], failed["srs"]["needs_relearning"], failed["srs"]["first_completed_at"]),
                         (False, True, at))
        # pause (no review is taken; history stays), then re-engage
        self.set_cols(kind, ref, srs_participation="paused", srs_pause_reason="manual")
        before = self.cols(kind, ref)
        with self.assertRaises(SrsWriteError) as caught:
            self.rate_at(kind, ref, NOW + 301 * DAY, "good", deck=deck)
        self.assertEqual(caught.exception.code, "card_paused")
        self.assertEqual(self.cols(kind, ref), before)
        self.set_cols(kind, ref, srs_participation="active", srs_pause_reason=None)
        later = self.rate_at(kind, ref, NOW + 302 * DAY, "good", deck=deck)
        self.assertEqual(later["srs"]["first_completed_at"], at)
        self.now = NOW
        cols = self.cols(kind, ref)
        self.assertEqual((cols["first_completed_at"], cols["version_first_completed_at"]), (at, at))

    def test_personal(self):
        self.flow("personal")

    def test_subscribed(self):
        self.flow("lexeme")

    def test_draft_first_completion_is_kept_with_its_source(self):
        for kind in ("personal", "lexeme"):
            with self.subTest(kind=kind):
                ref, deck = self.subject(kind, f"draft-{kind}")
                old = iso(NOW - 100 * DAY)
                self.set_cols(kind, ref, completion_metric_version=DRAFT_METRIC_VERSION, first_completed_at=old)
                first, middle, done = self.to_v3(kind, ref, deck)
                self.assertEqual((first["srs"]["first_completed_at"], first["srs"]["needs_relearning"]), (None, False))
                cols = self.cols(kind, ref)
                self.assertEqual((cols["first_completed_at"], cols["first_completed_source"]), (old, DRAFT_METRIC_VERSION))
                self.assertEqual(cols["version_first_completed_at"], done["accepted_at"])
                self.assertEqual(done["srs"]["first_completed_at"], done["accepted_at"])

    def test_missing_and_unknown_sources_and_damaged_values_never_fail_a_review(self):
        cases = {
            "missing": (dict(first_completed_at=iso(NOW - 9 * DAY), completion_metric_version=None), "source_missing"),
            "garbage first": (dict(first_completed_at="뜻-사본", completion_metric_version=DRAFT_METRIC_VERSION),
                              "source_unknown"),
            "naive first": (dict(first_completed_at="2026-01-01T00:00:00", completion_metric_version=DRAFT_METRIC_VERSION),
                            "source_unknown"),
        }
        for name, (values, source) in cases.items():
            with self.subTest(case=name):
                ref, _ = self.subject("personal", f"src-{len(name)}-{name[:3]}")
                self.set_cols("personal", ref, **values)
                result = self.rate_at("personal", ref, NOW, "good")
                self.assertIsNone(result["srs"]["first_completed_at"])
                cols = self.cols("personal", ref)
                self.assertEqual((cols["first_completed_at"], cols["first_completed_source"]),
                                 (values["first_completed_at"], source))

    def test_damaged_or_other_version_pair_is_preserved(self):
        for name, pair in (("v2", (iso(NOW - DAY), "meaning-completion-v2")), ("bad time", ("garbage", METRIC_VERSION))):
            with self.subTest(case=name):
                ref, _ = self.subject("personal", f"pair-{name[:2]}")
                self.set_cols("personal", ref, version_first_completed_at=pair[0], version_first_completed_version=pair[1])
                results = self.to_v3("personal", ref)
                self.assertTrue(results[-1]["completed"])
                self.assertEqual([r["srs"]["first_completed_at"] for r in results], [None, None, None])
                failed = self.rate_at("personal", ref, NOW + 300 * DAY, "again")
                self.now = NOW
                self.assertFalse(failed["srs"]["needs_relearning"])
                cols = self.cols("personal", ref)
                self.assertEqual((cols["version_first_completed_at"], cols["version_first_completed_version"]), pair)

    def test_half_pair_is_rejected_by_the_database(self):
        ref, _ = self.subject("personal", "half")
        for values in (dict(version_first_completed_at=iso(NOW)), dict(version_first_completed_version=METRIC_VERSION)):
            with self.subTest(values=values), self.assertRaises(sqlite3.IntegrityError):
                self.set_cols("personal", ref, **values)

    def test_retry_returns_the_stored_bytes_also_for_an_old_draft_answer(self):
        ref, _ = self.subject("personal", "retry")
        result = self.rate_at("personal", ref, NOW, "good", request=self.req(777))
        with get_connection() as c:
            row = c.execute("SELECT id, response_json FROM srs_review_receipts WHERE request_id = ?",
                            (self.req(777),)).fetchone()
            old = json.loads(row["response_json"])
            old["completion_metric_version"] = DRAFT_METRIC_VERSION  # an answer written before U11
            old["srs"]["first_completed_at"] = iso(NOW - 50 * DAY)
            text = json.dumps(old, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            c.execute("UPDATE srs_review_receipts SET response_json = ? WHERE id = ?", (text, row["id"]))
        before = self.everything()
        version = self.card_row("personal", ref)["srs_card_version"] - 1
        with mock.patch.object(reviews, "now_utc", return_value=NOW):
            again = vocab_repository.record_review(self.user, ref, "good", request_id=self.req(777),
                                                   expected_card_version=version, session_id="s1")
        self.assertEqual(json.dumps(again, sort_keys=True, separators=(",", ":"), ensure_ascii=False), text)
        self.assertEqual(self.everything(), before)
        self.assertNotEqual(result["completion_metric_version"], again["completion_metric_version"])

    def test_concurrent_completing_reviews_record_once(self):
        ref, _ = self.subject("personal", "twins")
        self.rate_at("personal", ref, NOW, "easy")
        self.rate_at("personal", ref, NOW + 8 * DAY, "easy")
        self.now = NOW
        version = self.card_row("personal", ref)["srs_card_version"]

        def send(n):
            return lambda: vocab_repository.record_review(self.user, ref, "easy", request_id=self.req(900 + n),
                                                          expected_card_version=version, session_id="s1")

        with race_support.LockProbe(), mock.patch.object(reviews, "now_utc", return_value=NOW + 74 * DAY):
            a, b = race_support.start("a", send(1)), race_support.start("b", send(2))
            for task in (a, b):
                task.thread.join(race_support.JOIN_TIMEOUT)
                self.assertFalse(task.thread.is_alive())
        outcomes = sorted("value" if "value" in t.box else t.box["error"].code for t in (a, b))
        self.assertEqual(outcomes, ["card_version_conflict", "value"])
        winner = (a if "value" in a.box else b).box["value"]
        self.assertTrue(winner["completed"])
        cols = self.cols("personal", ref)
        self.assertEqual(cols["version_first_completed_at"], winner["accepted_at"])
        self.assertEqual(len(self.logs_of("personal", ref)), 3)


class EvidenceTests(ReviewCase):
    def test_unexplained_version_gap_never_completes(self):
        ref, _ = self.subject("personal", "gap")
        self.rate_at("personal", ref, NOW, "easy")
        self.set_cols("personal", ref, srs_card_version=self.card_row("personal", ref)["srs_card_version"] + 2)
        results = [self.rate_at("personal", ref, NOW + d * DAY, "easy") for d in (8, 74, 300)]
        self.now = NOW
        self.assertTrue(all(r["completed"] is not True for r in results))
        self.assertIsNone(self.cols("personal", ref)["version_first_completed_at"])

    def test_tampered_rollback_record_breaks_the_proof_and_completion(self):
        ref, _ = self.card_with_records("tamper")  # converted, reviewed, rolled back
        self.assertEqual(self.reconvert("personal", ref)[2]["reconversion"], "restored")
        rollback = [r for r in self.records("personal", ref) if r["mode"] == "rollback"][0]
        payload = self.payload(rollback)
        payload["baseline"]["last_log_id"] += 1
        with get_connection() as c:
            c.execute("UPDATE srs_migration_snapshots SET legacy_json = ? WHERE id = ?", (json.dumps(payload), rollback["id"]))
        results = [self.rate_at("personal", ref, NOW + d * DAY, "easy") for d in (8, 74, 300)]
        self.now = NOW
        self.assertTrue(all(r["completed"] is not True for r in results))

    def test_restored_card_with_proof_can_complete(self):
        ref, _ = self.card_with_records("proof")
        self.assertEqual(self.reconvert("personal", ref)[2]["reconversion"], "restored")
        results = [self.rate_at("personal", ref, NOW + d * DAY, "easy") for d in (8, 74, 300)]
        self.now = NOW
        self.assertTrue(self.seen[-1][1])  # version-gap proof holds
        self.assertTrue(any(r["completed"] for r in results))


class PathTests(ReviewCase):
    def test_conversion_writes_no_completion(self):
        ref = self.content_card("conv")
        old = iso(NOW - 40 * DAY)
        self.set_cols("personal", ref, first_completed_at=old, completion_metric_version=DRAFT_METRIC_VERSION)
        plan = migration.dry_run([self.key("personal", ref)])
        values = json.loads(plan[0].values_json)
        self.assertFalse({"completion_metric_version", "first_completed_at"} & set(values))
        migration.apply_plan(plan, "run-conv", approved=True)
        self.assertEqual(self.cols("personal", ref), {
            "completion_metric_version": DRAFT_METRIC_VERSION, "first_completed_at": old,
            "first_completed_source": None, "version_first_completed_at": None, "version_first_completed_version": None})

    def test_complete_legacy_history_creates_no_completion(self):
        ref = self.content_card("legacy-done")
        with get_connection() as c:  # an untouched legacy card, then real legacy reviews
            c.execute("UPDATE vocab_items SET correct_count = 0, wrong_count = 0, review_level = 0, "
                      "last_reviewed_at = NULL, next_review_at = NULL WHERE id = ?", (ref,))
        for d in (0, 8, 74, 200):
            self.legacy_change("personal", ref, NOW - 300 * DAY + d * DAY)
        plan = migration.dry_run([self.key("personal", ref)])
        self.assertEqual(plan[0].quality, "complete", plan[0].flags)  # a full history: replay is used for the state
        replayed = migration.replay_with_completion(self.key("personal", ref), [
            migration.ReviewEvent(NOW - 300 * DAY + d * DAY, "good") for d in (0, 8, 74, 200)])
        self.assertIsNotNone(replayed[-1].first_completed_at)  # the replay itself would call it completed
        self.assertFalse({"completion_metric_version", "first_completed_at"} & set(json.loads(plan[0].values_json)))
        migration.apply_plan(plan, "run-legacy-done", approved=True)
        cols = self.cols("personal", ref)
        self.assertIsNone(cols["first_completed_at"])
        self.assertIsNone(cols["version_first_completed_at"])

    def test_rollback_reconvert_plan_b_and_u10_tools_keep_the_columns(self):
        ref = self.content_card("keep")
        self.apply(ref, run="run-keep")
        self.to_v3("personal", ref)
        kept = self.cols("personal", ref)
        self.assertIsNotNone(kept["version_first_completed_at"])
        self.now = NOW
        self.rollback("personal", ref, source="run-keep")
        self.assertEqual({k: self.cols("personal", ref)[k] for k in NEW_COLUMNS}, {k: kept[k] for k in NEW_COLUMNS})
        self.assertEqual(self.reconvert("personal", ref)[2]["reconversion"], "restored")
        self.assertEqual({k: self.cols("personal", ref)[k] for k in NEW_COLUMNS}, {k: kept[k] for k in NEW_COLUMNS})
        record = [r for r in self.records("personal", ref) if r["mode"] == "rollback"][-1]
        self.assertFalse(set(json.loads(record["srs_before_json"])) & set(NEW_COLUMNS))
        for r in self.records("personal", ref):
            self.assertFalse(set(self.payload(r)["card"]) & set(NEW_COLUMNS))
        with get_connection() as c:
            migration.minimize_snapshots(c, self.user, apply=True, lock=lambda conn, u: None)
            with mock.patch.object(migration, "now_utc", return_value=datetime.now(UTC) + 400 * DAY):
                migration.prune_expired_runs(c, self.user, apply=True, lock=lambda conn, u: None)
        self.assertEqual({k: self.cols("personal", ref)[k] for k in NEW_COLUMNS}, {k: kept[k] for k in NEW_COLUMNS})

    def test_plan_b_restart_keeps_history_and_judges_the_new_window_only(self):
        ref, boundary, run, at = self.to_plan_b("personal", name="u11b")
        self.set_cols("personal", ref, first_completed_at=iso(NOW - 200 * DAY), completion_metric_version=DRAFT_METRIC_VERSION)
        first = self.rate_at("personal", ref, at, "easy")
        self.assertEqual((first["completed"], first["srs"]["first_completed_at"]), (False, None))
        self.assertEqual(self.cols("personal", ref)["first_completed_source"], DRAFT_METRIC_VERSION)
        self.now = NOW


# ---------------------------------------------------------------------------
class UpgradeTests(ReviewCase):
    def setUp(self):
        real = schema.card_columns

        def old(is_postgres):
            return [c for c in real(is_postgres) if c.split()[0] not in NEW_COLUMNS]

        with mock.patch.object(schema, "card_columns", old):
            super().setUp()
            # rollback records made before the columns exist
            self.restore_ref, _ = self.card_with_records("pre-restore")
            self.gap_ref, _ = self.card_with_records("pre-gap")
            self.assertEqual(self.reconvert("personal", self.gap_ref)[2]["reconversion"], "restored")
            self.rate_at("personal", self.gap_ref, NOW + 8 * DAY, "good")
            self.now = NOW
        with get_connection() as c:
            self.assertFalse(set(NEW_COLUMNS) & {r["name"] for r in c.execute("PRAGMA table_info(vocab_items)")})
            self.records_before = [tuple(r) for r in c.execute("SELECT * FROM srs_migration_snapshots ORDER BY id")]
            schema.ensure_srs_schema(c, False)  # the upgrade
            self.assertTrue(set(NEW_COLUMNS) <= {r["name"] for r in c.execute("PRAGMA table_info(vocab_items)")})

    def test_restore_and_proof_survive_the_upgrade(self):
        with get_connection() as c:
            self.assertEqual([tuple(r) for r in c.execute("SELECT * FROM srs_migration_snapshots ORDER BY id")],
                             self.records_before)  # nothing rewritten
        self.assertEqual(self.reconvert("personal", self.restore_ref)[2]["reconversion"], "restored")
        self.seen.clear()
        self.rate_at("personal", self.gap_ref, NOW + 20 * DAY, "good")
        self.now = NOW
        self.assertTrue(self.seen[-1][1])  # the version-gap proof still holds
        with get_connection() as c:
            schema.ensure_srs_schema(c, False)  # idempotent


if __name__ == "__main__":
    unittest.main()

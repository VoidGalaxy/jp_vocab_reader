"""Gate D-2 U10-c0: behaviour that snapshot minimization must not change.

Run twice: with the records the code writes now, and with every new snapshot / rollback
record rewritten to the pre-U10 shape ("format 1": the whole card row copied in), so
both formats are read the same way. Covers rollback results, restoring re-conversion,
the version-gap proof, plan-B permissions (repeated, delayed first review, rolled back
before the first review), the "was converted" / latest-record decisions, the personal
id reference scan, and the rollback required-field check.

Synthetic SQLite only (QueueCase sets a throwaway DATABASE_URL per test before the
app touches a database).

Run directly:      python tests/test_srs_d2_u10_baseline.py
Or via discovery:   python -m unittest discover -s tests
"""

from __future__ import annotations

import json
import sys
import unittest
from datetime import timedelta
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_srs_d2_u8_plan_b import PlanBCase  # noqa: E402
from test_srs_queue import NOW  # noqa: E402

from app.database import get_connection  # noqa: E402
from app.srs import identity, migration  # noqa: E402

DAY = timedelta(days=1)
LEGACY_FIELDS = ("review_level", "next_review_at", "srs_engine", "srs_state", "srs_effective_due_at",
                 "srs_participation", "srs_history_quality")


class BaselineCase(PlanBCase):
    FORMAT1 = False

    def setUp(self):
        super().setUp()
        if not self.FORMAT1:
            return
        real_apply, real_rollback = migration.apply_plan, migration.rollback_plan

        def full_rows():
            with get_connection() as c:
                rows = {("personal", r["id"]): dict(r) for r in c.execute("SELECT * FROM vocab_items")}
                rows.update({("lexeme", r["lexeme_id"]): dict(r) for r in c.execute(
                    "SELECT * FROM user_word_progress WHERE user_id = ?", (self.user,))})
            return rows

        def last_id():
            with get_connection() as c:
                return c.execute("SELECT COALESCE(MAX(id), 0) FROM srs_migration_snapshots").fetchone()[0]

        def to_format1(since, before_rows):
            after_rows = full_rows()
            with get_connection() as c:
                for row in c.execute("SELECT s.id, s.card_kind, s.card_ref, s.legacy_json, r.mode FROM srs_migration_snapshots s "
                                     "JOIN srs_migration_runs r ON r.id = s.run_id WHERE s.id > ?", (since,)).fetchall():
                    payload = json.loads(row["legacy_json"])
                    payload.pop("format", None)
                    rows = before_rows if row["mode"] == "apply" else after_rows
                    payload["card"] = rows[(row["card_kind"], row["card_ref"])]
                    c.execute("UPDATE srs_migration_snapshots SET legacy_json = ? WHERE id = ?",
                              (json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False), row["id"]))

        def apply(*a, **k):
            since, before = last_id(), full_rows()
            result = real_apply(*a, **k)
            to_format1(since, before)
            return result

        def rollback(*a, **k):
            since = last_id()
            result = real_rollback(*a, **k)
            to_format1(since, None)
            return result

        for name, fn in (("apply_plan", apply), ("rollback_plan", rollback)):
            patch = mock.patch.object(migration, name, fn)
            patch.start()
            self.addCleanup(patch.stop)

    def legacy_view(self, kind, ref):
        row = self.card_row(kind, ref)
        return {k: row[k] for k in LEGACY_FIELDS}

    def formats(self):
        with get_connection() as c:
            return {json.loads(r[0]).get("format", 1) for r in c.execute("SELECT legacy_json FROM srs_migration_snapshots")}


# ---------------------------------------------------------------------------
class BaselineTests(BaselineCase):
    def restore_flow(self, kind, deck=None):
        ref = self.converted(kind, f"flow-{kind}", deck)
        self.rate_at(kind, ref, NOW, "good", deck=deck)
        self.rate_at(kind, ref, NOW + 2 * DAY, "again", deck=deck)
        self.now = NOW
        last_fsrs = self.view(kind, ref)
        self.assertEqual(self.rollback(kind, ref)[0]["result"], "rolled_back")
        rolled = self.legacy_view(kind, ref)
        self.assertEqual((rolled["srs_engine"], rolled["srs_state"]), ("legacy", None))
        self.assertEqual(self.reconvert(kind, ref)[2]["reconversion"], "restored")
        self.assertEqual(self.view(kind, ref), last_fsrs)
        for gap in (5, 20):
            self.rate_at(kind, ref, NOW + gap * DAY, "good", deck=deck)
            self.now = NOW
            self.assertTrue(self.seen[-1][1])  # version-gap proof holds
        return rolled

    def test_personal_restore_flow(self):
        rolled = self.restore_flow("personal")
        self.assertEqual(rolled["review_level"], self.expected_level)

    def test_subscribed_restore_flow(self):
        self.restore_flow("lexeme", self.shared_deck("s"))

    @property
    def expected_level(self):
        # zero-log U5 card at level 0 -> good -> again: the legacy rule gives level 0 back
        from app.database import compute_review_schedule
        level, _ = compute_review_schedule("good", 0, NOW)
        level, _ = compute_review_schedule("again", level, NOW + 2 * DAY)
        return level

    def test_plan_b_repeated_and_delayed_first_review(self):
        ref, boundary, run, at = self.to_plan_b("personal", name="rep")
        late = at + 120 * DAY  # first review long after the re-conversion
        self.rate_at("personal", ref, late, "good")
        self.rate_at("personal", ref, late + 5 * DAY, "good")
        self.now = NOW
        self.assertTrue(self.seen[-1][1])
        self.assertEqual(self.rollback("personal", ref, source=run)[0]["result"], "rolled_back")
        self.legacy_change("personal", ref, late + 6 * DAY)
        run2, _, result = self.reconvert("personal", ref)
        self.assertEqual(result["reconversion"], "state_none_restart")
        self.rate_at("personal", ref, late + 9 * DAY, "easy")
        self.now = NOW
        rows = self.restarts("personal", ref)
        self.assertEqual(len(rows), 2)
        self.assertEqual(len({r["source_snapshot_id"] for r in rows}), 2)

    def test_plan_b_rolled_back_before_first_review(self):
        ref, boundary, run1, at = self.to_plan_b("personal", name="before")
        self.assertEqual(self.rollback("personal", ref, source=run1)[0]["result"], "rolled_back")
        run2, candidate, result = self.reconvert("personal", ref)
        self.assertEqual(result["reconversion"], "restored")
        self.rate_at("personal", ref, at, "good")
        self.now = NOW
        with get_connection() as c:
            latest = c.execute("SELECT s.id FROM srs_migration_snapshots s JOIN srs_migration_runs r ON r.id = s.run_id "
                               "WHERE r.run_key = ?", (run2,)).fetchone()[0]
        self.assertEqual([r["source_snapshot_id"] for r in self.restarts("personal", ref)], [latest])  # old one not revived

    def test_was_converted_and_latest_record(self):
        ref = self.converted("personal", "latest")
        self.rate_at("personal", ref, NOW, "good")
        self.now = NOW
        fresh = self.personal("never-converted")
        self.assertIsNone(migration.dry_run([self.key("personal", fresh)])[0].reconversion)
        source = self.first_run("personal", ref)
        for cycle in range(2):
            self.rollback("personal", ref, source=source)
            plan = migration.dry_run([self.key("personal", ref)])
            self.assertEqual(plan[0].reconversion, "restored", cycle)
            source, _, _ = self.reconvert("personal", ref)
            self.assertEqual(migration.dry_run([self.key("personal", ref)])[0].quality, "already_fsrs")

    def test_identity_reference_scan(self):
        refs = [self.converted("personal", f"id{i}") for i in range(2)]
        self.rollback("personal", refs[0])
        with get_connection() as c:
            report = identity.personal_id_references(c)
            scan = identity.scan_identity(c)
        self.assertEqual(report["srs_migration_snapshots"], max(refs))
        self.assertEqual(scan.findings, [])

    def test_rollback_with_missing_srs_fields_is_blocked(self):
        """The defect (REPORT 26-2 E): a snapshot whose card lacks srs_* used to be
        reported rolled_back while the card stayed FSRS."""
        bad, good = self.personal("bad"), self.personal("good")
        migration.apply_plan(migration.dry_run([self.key("personal", bad), self.key("personal", good)]), "run-two",
                             approved=True)
        with get_connection() as c:
            row = c.execute("SELECT id, legacy_json FROM srs_migration_snapshots WHERE card_ref = ?", (bad,)).fetchone()
            payload = json.loads(row["legacy_json"])
            payload["card"] = {k: v for k, v in payload["card"].items() if not k.startswith("srs_") or k == "srs_card_version"}
            c.execute("UPDATE srs_migration_snapshots SET legacy_json = ? WHERE id = ?", (json.dumps(payload), row["id"]))
        version = self.card_row("personal", bad)["srs_card_version"]
        results = {r["ref_id"]: r for r in migration.rollback_plan("run-two", "rb-two", user_id=self.user, approved=True)}
        self.assertEqual((results[bad]["result"], results[bad].get("reason")), ("blocked", "snapshot_incomplete"))
        self.assertEqual(results[good]["result"], "rolled_back")
        self.assertEqual((self.card_row("personal", bad)["srs_engine"], self.card_row("personal", bad)["srs_card_version"]),
                         ("fsrs", version))  # nothing written for the blocked card
        self.assertEqual(self.card_row("personal", good)["srs_engine"], "legacy")


class BaselineFormat1Tests(BaselineTests):
    """Same checks with every snapshot / rollback record in the pre-U10 shape."""
    FORMAT1 = True

    def test_records_really_are_format1(self):
        ref = self.converted("personal", "f1")
        self.rollback("personal", ref)
        self.assertEqual(self.formats(), {1})


if __name__ == "__main__":
    unittest.main()

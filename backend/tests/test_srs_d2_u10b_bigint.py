"""Gate D-2 U10-b review fix: an integer too large for the engine (e.g. 10**400) in a
record's srs_stability / srs_difficulty is a failed check, not an exception.

Before the fix `math.isfinite()` raised OverflowError on such an integer, so the
snapshot tool stopped with rc=1, rolled the batch back and never reached the normal
records after it. Now the record is reported unsupported with its stored value left
exactly as it is, and the run goes on. Real write failures still fail the batch.

Synthetic SQLite only (QueueCase sets a throwaway DATABASE_URL per test before the
app touches a database).

Run directly:      python tests/test_srs_d2_u10b_bigint.py
Or via discovery:   python -m unittest discover -s tests
"""

from __future__ import annotations

import json
import math
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_srs_d2_u10b_tool import ToolCase  # noqa: E402

from app.database import get_connection  # noqa: E402
from app.srs import migration  # noqa: E402

BIG = 10 ** 400
SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "d2_snapshot_minimize.py"
# where the value goes: (record mode, column, path inside the column's JSON)
PLACES = {
    "card": ("apply", "legacy_json", ["card"]),
    "apply_after": ("apply", "srs_after_json", []),
    "rollback_before": ("rollback", "srs_before_json", []),
}
CASES = [(place, field, sign) for place in PLACES for field in ("srs_stability", "srs_difficulty") for sign in (1, -1)]


class BigIntCase(ToolCase):
    def put_big(self, ref, place, field, sign):
        mode, column, path = PLACES[place]
        record = [r for r in self.records("personal", ref) if r["mode"] == mode][0]
        data = json.loads(record[column])
        target = data
        for key in path:
            target = target[key]
        self.assertIn(field, target)
        target[field] = sign * BIG
        with get_connection() as c:
            c.execute(f"UPDATE srs_migration_snapshots SET {column} = ? WHERE id = ?", (json.dumps(data), record["id"]))
        return record["id"]

    def mixed(self):
        """Normal and big-integer records interleaved: card i is damaged when i is odd."""
        damaged = {}
        for i in range(2 * len(CASES) + 1):
            ref, _ = self.card_with_records(f"big{i}")
            if i % 2:
                case = CASES[i // 2]
                damaged[self.put_big(ref, *case)] = case
        return damaged

    def check_run(self, damaged, *extra):
        before = self.rows()
        dry, code = self.tool(*extra)
        self.assertEqual(code, 0)
        self.assertEqual(self.rows(), before)  # dry run: nothing written
        normal = set(before) - set(damaged)
        for report in (dry,):
            self.assert_report(report, damaged, normal)
        applied, code = self.apply_tool(*extra)
        self.assertEqual(code, 0)
        self.assert_report(applied, damaged, normal)
        self.assertEqual(applied["cursor"], applied["upper_id"])
        after = self.rows()
        for record_id in damaged:
            self.assertEqual(after[record_id], before[record_id])  # stored value kept byte for byte
        for record_id in normal:
            self.assertEqual(json.loads(after[record_id]["legacy_json"])["format"], 2)
        again, code = self.apply_tool(*extra)
        self.assertEqual((code, again["minimized"], again["already_minimal"]), (0, [], len(normal)))
        self.assertEqual({e["id"] for e in again["unsupported"]}, set(damaged))
        self.assertEqual(self.rows(), after)

    def assert_report(self, report, damaged, normal):
        self.assertNotIn("failed", report)
        self.assertEqual({e["id"]: e["reason"] for e in report["unsupported"]},
                         {i: "unsupported_structure_or_value" for i in damaged})
        self.assertEqual({e["id"] for e in report["minimized"]}, normal)
        self.assertEqual(report["insufficient"], [])
        self.assertNotIn("0" * 20, json.dumps(report))  # the number itself is never printed


class CheckTests(BigIntCase):
    def test_numeric_check_contract(self):
        accepted = [0, 3, -2, 2.5, -0.0, 1e308, 10 ** 300, float(2 ** 1023)]
        rejected = [BIG, -BIG, 2 ** 1024, True, False, "2.5", "", float("nan"), float("inf"), float("-inf"), [1], {"v": 1}]
        for value in accepted:
            self.assertTrue(migration._finite(value), value if not isinstance(value, int) else "int")
        for value in rejected:
            with self.subTest(value=type(value).__name__):
                self.assertFalse(migration._finite(value))
        for field in ("srs_stability", "srs_difficulty"):
            self.assertTrue(migration._FIELD_OK[field](None))
            self.assertFalse(migration._FIELD_OK[field](BIG))

    def test_restorable_check(self):
        ref, _ = self.card_with_records("restorable")
        record = [r for r in self.records("personal", ref) if r["mode"] == "apply"][0]
        with get_connection() as c:
            columns = migration._card_columns(c, "personal")
        card = migration._record_shape("apply", "personal", ref, self.payload(record), columns)["card"]
        self.assertTrue(migration._restorable(card))
        for field in ("srs_stability", "srs_difficulty"):
            for value, ok in ((None, True), (4, True), (2.5, True), (BIG, False), (-BIG, False), (True, False),
                              ("1", False), (float("nan"), False), (float("inf"), False)):
                with self.subTest(field=field, value=type(value).__name__):
                    self.assertEqual(migration._restorable(dict(card, **{field: value})), ok)

    def test_too_long_integer_text_is_unsupported(self):
        ref, _ = self.card_with_records("too-long")
        record = [r for r in self.records("personal", ref) if r["mode"] == "apply"][0]
        data = json.loads(record["srs_after_json"])
        data["srs_stability"] = "PLACEHOLDER"
        text = json.dumps(data).replace('"PLACEHOLDER"', "9" * 5000)  # beyond Python's int text limit
        self.assertIn("9" * 5000, text)
        self.assertFalse(migration._srs_columns_shape("apply", record["srs_before_json"], text))


class ToolTests(BigIntCase):
    def test_same_batch(self):
        self.check_run(self.mixed())

    def test_one_record_per_batch(self):
        self.check_run(self.mixed(), "--batch-size", "1")

    def test_mixed_batches(self):
        self.check_run(self.mixed(), "--batch-size", "3")

    def test_resume_after_a_real_failure_with_big_values_present(self):
        damaged = self.mixed()
        before = self.rows()
        real, calls = migration._json, {"n": 0}

        def failing(value):
            calls["n"] += 1
            if calls["n"] == 5:  # second write of the second batch (batch 1 holds 3 normal records)
                raise OverflowError("a write failure, not a number check")
            return real(value)

        with mock.patch.object(migration, "_json", failing):
            report, code = self.apply_tool("--batch-size", "4")
        self.assertEqual((code, report.get("failed")), (1, "OverflowError"))  # not hidden as a damaged record
        ids = sorted(before)
        committed = [i for i in ids if i <= report["cursor"]]
        self.assertEqual(report["cursor"], ids[3])  # first batch committed, failed batch rolled back
        rows = self.rows()
        for record_id in ids:
            if record_id > report["cursor"]:
                self.assertEqual(rows[record_id], before[record_id])
        self.assertEqual({e["id"] for e in report["unsupported"]}, set(damaged) & set(committed))
        resumed, code = self.apply_tool("--batch-size", "4", "--after-id", str(report["cursor"]))
        self.assertEqual(code, 0)
        self.assertEqual({e["id"] for e in resumed["unsupported"]}, set(damaged) - set(committed))
        final = self.rows()
        for record_id in ids:
            fmt = json.loads(final[record_id]["legacy_json"]).get("format")
            self.assertEqual(fmt, None if record_id in damaged else 2)

    def test_real_cli_subprocess(self):
        damaged = self.mixed()
        before = self.rows()
        env = {k: v for k, v in os.environ.items() if k != "DATABASE_URL"}
        env["APP_ENV"] = "test"

        def cli(*extra):
            done = subprocess.run([sys.executable, str(SCRIPT), "--sqlite-db", str(self.db_path), "--user-id",
                                   str(self.user), *extra], capture_output=True, text=True, timeout=120, env=env,
                                  encoding="utf-8")
            return done.returncode, json.loads(done.stdout) if done.stdout.strip() else None, done.stdout + done.stderr

        code, dry, out = cli("--batch-size", "5")
        self.assertEqual(code, 0, out[-500:])
        self.assertEqual(self.rows(), before)
        self.assertNotIn("0" * 20, out)
        code, applied, out = cli("--batch-size", "5", "--apply", "--confirm-user-id", str(self.user))
        self.assertEqual(code, 0, out[-500:])
        self.assertNotIn("0" * 20, out)
        self.assertEqual(applied["cursor"], applied["upper_id"])
        self.assertEqual({e["id"] for e in applied["unsupported"]}, set(damaged))
        self.assertEqual({e["id"] for e in applied["minimized"]}, set(before) - set(damaged))
        rows = self.rows()
        self.assertEqual({i: rows[i] for i in damaged}, {i: before[i] for i in damaged})
        code, again, _ = cli("--apply", "--confirm-user-id", str(self.user))
        self.assertEqual((code, again["minimized"], again["already_minimal"]), (0, [], len(before) - len(damaged)))


class PathTests(BigIntCase):
    def test_rollback_is_blocked_and_nothing_changes(self):
        for field in ("srs_stability", "srs_difficulty"):
            for sign in (1, -1):
                with self.subTest(field=field, sign=sign):
                    ref = self.converted("personal", f"rb-{field}-{sign}")
                    self.put_big(ref, "card", field, sign)
                    before = self.everything()
                    result = self.rollback("personal", ref)
                    self.assertEqual((result[0]["result"], result[0]["reason"]), ("blocked", "snapshot_incomplete"))
                    after = self.everything()
                    self.assertEqual({k: v for k, v in after.items() if k != "srs_migration_runs"},
                                     {k: v for k, v in before.items() if k != "srs_migration_runs"})

    def test_delete_removes_only_the_unsupported_record(self):
        for place, field, sign in CASES:
            with self.subTest(place=place, field=field, sign=sign):
                ref, _ = self.card_with_records(f"del-{place}-{field}-{sign}")
                bad = self.put_big(ref, place, field, sign)
                keep_ids = {r["id"] for r in self.records("personal", ref)} - {bad}
                self.assertEqual(self.client.delete(f"/vocab-items/{ref}", headers=self.headers).status_code, 204)
                remaining = self.records("personal", ref)
                self.assertEqual({r["id"] for r in remaining}, keep_ids)
                self.assertTrue(all(json.loads(r["legacy_json"])["format"] == 2 for r in remaining))


if __name__ == "__main__":
    unittest.main()

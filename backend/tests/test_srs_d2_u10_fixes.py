"""Gate D-2 U10-c0·a review fixes.

P1: rollback validates every value it restores (types, ranges, real time-zoned
    instants, meanings, identity) before writing; a damaged snapshot blocks the card
    with snapshot_incomplete instead of being written and failing a later review.
P2: the delete path judges the whole record (top level, card, baseline, restart and
    the SRS JSON columns) per record type; a record with anything unsupported is
    deleted (A8, explicit card deletion only); recognised ones are rebuilt from the
    allowed fields only.

Synthetic SQLite only (QueueCase sets a throwaway DATABASE_URL per test before the
app touches a database).

Run directly:      python tests/test_srs_d2_u10_fixes.py
Or via discovery:   python -m unittest discover -s tests
"""

from __future__ import annotations

import json
import math
import sys
import unittest
from datetime import timedelta, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_srs_d2_u10_minimize import MinCase  # noqa: E402
from test_srs_queue import NOW, iso  # noqa: E402

from app.database import get_connection  # noqa: E402
from app.repositories import deck_repository, vocab_repository  # noqa: E402
from app.repositories.deck_repository import create_deck  # noqa: E402
from app.schemas import DeckCreate  # noqa: E402
from app.srs import identity, migration  # noqa: E402
from app.srs.storage import SrsWriteError  # noqa: E402

DAY = timedelta(days=1)


class FixCase(MinCase):
    def converted_any(self, kind, name, deck=None):
        if kind == "personal":
            ref = self.content_card(name)
            self.apply(ref, run=f"run-{name}")
            return ref, f"run-{name}"
        ref = self.converted("lexeme", name, deck)
        return ref, self.first_run("lexeme", ref)

    def full_row(self, kind, ref):
        return self.card_row(kind, ref)

    def edit_apply(self, kind, ref, fmt, change):
        record = self.records(kind, ref)[0]
        if fmt == 1:
            payload = self.payload(record)
            full = dict(self.full_row(kind, ref))
            full.update({k: v for k, v in payload["card"].items()})  # the pre-conversion values
            self.to_format1(record["id"], full)
            record = self.records(kind, ref)[0]
        payload = self.payload(record)
        change(payload)
        with get_connection() as c:
            c.execute("UPDATE srs_migration_snapshots SET legacy_json = ? WHERE id = ?",
                      (json.dumps(payload, ensure_ascii=False, allow_nan=True), record["id"]))


# ---------------------------------------------------------------------------
class P1ValueTests(FixCase):
    def check_blocked(self, kind, fmt, change, name, deck=None):
        ref, run = self.converted_any(kind, name, deck)
        self.rate_at(kind, ref, NOW, "good", deck=deck)
        self.now = NOW
        self.edit_apply(kind, ref, fmt, change)
        before = self.card_row(kind, ref)
        self._run += 1
        result = migration.rollback_plan(run, f"rb-{name}-{self._run}", user_id=self.user, approved=True)[0]
        self.assertEqual((result["result"], result.get("reason")), ("blocked", "snapshot_incomplete"), name)
        self.assertEqual(self.card_row(kind, ref), before)  # nothing written
        self.assertEqual(migration.dry_run([self.key(kind, ref)])[0].quality, "already_fsrs")
        response = self.rate_at(kind, ref, NOW + 5 * DAY, "good", deck=deck)  # the card keeps working
        self.now = NOW
        self.assertEqual(response["card_kind"], kind)
        self.assertEqual(self.card_row(kind, ref)["first_completed_at"], before["first_completed_at"])

    def test_garbage_first_completed_at_personal_and_subscribed_both_formats(self):
        deck = self.shared_deck("s")
        for kind in ("personal", "lexeme"):
            for fmt in (2, 1):
                with self.subTest(kind=kind, fmt=fmt):
                    self.check_blocked(kind, fmt, lambda p: p["card"].update(first_completed_at="garbage"),
                                       f"fc-{kind}-{fmt}", deck if kind == "lexeme" else None)

    def test_every_restored_value_is_checked(self):
        cases = {
            "first_completed_at naive": lambda p: p["card"].update(first_completed_at="2026-10-01T00:00:00"),
            "first_completed_at number": lambda p: p["card"].update(first_completed_at=5),
            "next_review_at garbage": lambda p: p["card"].update(next_review_at="garbage"),
            "completion_metric_version number": lambda p: p["card"].update(completion_metric_version=5),
            "completion_metric_version empty": lambda p: p["card"].update(completion_metric_version=""),
            "config not text": lambda p: p["card"].update(srs_config_version=3),
            "state out of range": lambda p: p["card"].update(srs_state=7),
            "state bool": lambda p: p["card"].update(srs_state=True),
            "step negative": lambda p: p["card"].update(srs_step=-1),
            "stability text": lambda p: p["card"].update(srs_stability="x"),
            "stability nan": lambda p: p["card"].update(srs_stability=math.nan),
            "difficulty bool": lambda p: p["card"].update(srs_difficulty=False),
            "due garbage": lambda p: p["card"].update(srs_due_at="garbage"),
            "effective due naive": lambda p: p["card"].update(srs_effective_due_at="2026-10-01T00:00:00"),
            "participation unknown": lambda p: p["card"].update(srs_participation="maybe"),
            "pause reason number": lambda p: p["card"].update(srs_pause_reason=3),
            "quality unknown": lambda p: p["card"].update(srs_history_quality="bad"),
            "flags not json": lambda p: p["card"].update(srs_history_flags="not json"),
            "flags not a list": lambda p: p["card"].update(srs_history_flags='{"a": 1}'),
            "flags not text items": lambda p: p["card"].update(srs_history_flags="[1]"),
            "card version text": lambda p: p["card"].update(srs_card_version="x"),
            "card id of another card": lambda p: p["card"].update(id=999999),
            "last_log_id negative": lambda p: p.update(last_log_id=-1),
            "unknown top-level key": lambda p: p.update(note="x"),
            "restart extra key": lambda p: p.update(restart={"previous_boundary": 1, "rollback_record_id": 1, "x": 2}),
        }
        for name, change in cases.items():
            with self.subTest(name=name):
                self.check_blocked("personal", 2, change, f"v{len(name)}-{abs(hash(name)) % 10**6}")

    def test_subscribed_identity_must_match(self):
        deck = self.shared_deck("s2")
        self.check_blocked("lexeme", 2, lambda p: p["card"].update(lexeme_id=987654), "lx-id", deck)

    def test_valid_values_still_roll_back(self):
        for name, change in (
                ("nulls", lambda p: p["card"].update(next_review_at=None, srs_config_version=None,
                                                     completion_metric_version=None, first_completed_at=None,
                                                     srs_history_flags=None)),
                ("offset plus", lambda p: p["card"].update(first_completed_at=NOW.astimezone(timezone(timedelta(hours=9))).isoformat())),
                ("offset minus", lambda p: p["card"].update(first_completed_at=NOW.astimezone(timezone(timedelta(hours=-5))).isoformat())),
                ("zulu", lambda p: p["card"].update(first_completed_at=iso(NOW).replace("+00:00", "Z"),
                                                    completion_metric_version="meaning-completion-v1-draft")),
                ("flags list", lambda p: p["card"].update(srs_history_flags='["missing_history"]'))):
            for fmt in (2, 1):
                with self.subTest(name=name, fmt=fmt):
                    ref, run = self.converted_any("personal", f"ok-{name}-{fmt}".replace(" ", ""))
                    self.edit_apply("personal", ref, fmt, change)
                    self._run += 1
                    result = migration.rollback_plan(run, f"rb-ok-{self._run}", user_id=self.user, approved=True)[0]
                    self.assertEqual(result["result"], "rolled_back")
                    self.assertEqual(self.card_row("personal", ref)["srs_engine"], "legacy")
                    self.assertEqual(self.reconvert("personal", ref)[2]["reconversion"], "restored")


# ---------------------------------------------------------------------------
class P2StructureTests(FixCase):
    UNSUPPORTED = {
        "top-level copy (format 2)": ("apply", 2, lambda p: p.update(note="뜻-사본")),
        "top-level copy (format 1)": ("apply", 1, lambda p: p.update(note="뜻-사본")),
        "format 2 card with content": ("apply", 2, lambda p: p["card"].update(meaning_ko="뜻-사본")),
        "restart with extra field": ("apply", 2, lambda p: p.update(restart={"previous_boundary": 1, "rollback_record_id": 1,
                                                                            "note": "뜻-사본"})),
        "rollback baseline extra": ("rollback", 2, lambda p: p["baseline"].update(note="뜻-사본")),
        "rollback top-level (format 1)": ("rollback", 1, lambda p: p.update(note="뜻-사본")),
        "format 1 card unknown column": ("apply", 1, lambda p: p["card"].update(source_text="뜻-사본")),
    }

    def card_with_records(self, name, deck=None):
        ref = self.content_card(name, deck)
        full = dict(self.card_row("personal", ref))
        self.apply(ref, run=f"run-{name}")
        self.rate_at("personal", ref, NOW, "good")
        self.now = NOW
        self.rollback("personal", ref, source=f"run-{name}")
        return ref, full

    def mutate(self, ref, full, which, fmt, change):
        record = [r for r in self.records("personal", ref) if r["mode"] == which][0]
        if fmt == 1:
            self.to_format1(record["id"], full if which == "apply" else dict(self.card_row("personal", ref)))
            record = [r for r in self.records("personal", ref) if r["mode"] == which][0]
        payload = self.payload(record)
        change(payload)
        with get_connection() as c:
            c.execute("UPDATE srs_migration_snapshots SET legacy_json = ? WHERE id = ?",
                      (json.dumps(payload, ensure_ascii=False), record["id"]))
        return record["id"]

    def run_delete(self, use_deck):
        deck = create_deck(self.user, DeckCreate(name=f"d-{use_deck}"))[0]["id"] if use_deck else None
        cases = {}
        for i, (name, (which, fmt, change)) in enumerate(self.UNSUPPORTED.items()):
            ref, full = self.card_with_records(f"u{int(use_deck)}{i}", deck)
            cases[name] = (ref, self.mutate(ref, full, which, fmt, change))
        normal_ref, normal_full = self.card_with_records(f"n{int(use_deck)}", deck)  # format 1 apply + format 2 rollback
        self.to_format1(self.records("personal", normal_ref)[0]["id"], normal_full)
        normal_before = {r["id"]: self.payload(r) for r in self.records("personal", normal_ref)}
        keep_ref, _ = self.card_with_records(f"k{int(use_deck)}")  # not deleted
        keep_before = self.records("personal", keep_ref)
        with get_connection() as c:
            logs = [tuple(r) for r in c.execute("SELECT * FROM review_logs ORDER BY id")]
        if use_deck:
            self.assertEqual(self.client.delete(f"/decks/{deck}", headers=self.headers).status_code, 200)
        else:
            for ref, _ in list(cases.values()) + [(normal_ref, None)]:
                self.assertEqual(self.client.delete(f"/vocab-items/{ref}", headers=self.headers).status_code, 204)
        for name, (ref, record_id) in cases.items():
            remaining = {r["id"] for r in self.records("personal", ref)}
            self.assertNotIn(record_id, remaining, name)  # the unsupported row only
            for r in self.records("personal", ref):
                self.assertNotIn("뜻", r["legacy_json"] + (r["srs_after_json"] or ""), name)
        for record in self.records("personal", normal_ref):
            payload = self.payload(record)
            self.assertEqual(payload["format"], 2)
            allowed = {"format", "card", "last_log_id", "restart"} if record["mode"] == "apply" else {"format", "card", "baseline"}
            self.assertLessEqual(set(payload), allowed)
            before = normal_before[record["id"]]
            for key in ("last_log_id", "baseline", "restart"):
                self.assertEqual(payload.get(key), before.get(key))
            self.assertNotIn("뜻", record["legacy_json"])
        self.assertEqual(self.records("personal", keep_ref), keep_before)
        with get_connection() as c:
            self.assertEqual([tuple(r) for r in c.execute("SELECT * FROM review_logs ORDER BY id")], logs)
            identity.personal_id_references(c)

    def test_word_delete(self):
        self.run_delete(False)

    def test_deck_delete(self):
        self.run_delete(True)

    def test_srs_json_columns_are_judged_too(self):
        ref, full = self.card_with_records("sj")
        apply_rec = [r for r in self.records("personal", ref) if r["mode"] == "apply"][0]
        values = json.loads(apply_rec["srs_after_json"])
        values["note"] = "뜻-사본"
        with get_connection() as c:
            c.execute("UPDATE srs_migration_snapshots SET srs_after_json = ? WHERE id = ?",
                      (json.dumps(values, ensure_ascii=False), apply_rec["id"]))
        self.assertTrue(vocab_repository.delete_vocab_item(self.user, ref))
        self.assertNotIn(apply_rec["id"], {r["id"] for r in self.records("personal", ref)})

    def test_failure_restores_unsupported_rows_and_content(self):
        class Boom(Exception):
            pass

        ref, full = self.card_with_records("fx")
        self.mutate(ref, full, "apply", 2, lambda p: p.update(note="뜻-사본"))
        before = self.everything()
        with mock.patch("app.srs.identity.record_personal_deletions", side_effect=Boom()):
            with self.assertRaises(Boom):
                vocab_repository.delete_vocab_item(self.user, ref)
        self.assertEqual(self.everything(), before)

    def test_general_reads_never_delete_unsupported_records(self):
        ref, full = self.card_with_records("gr")
        self.mutate(ref, full, "apply", 2, lambda p: p.update(note="뜻-사본"))
        before = self.everything()
        migration.dry_run([self.key("personal", ref)])
        self.q()
        migration.rollback_plan(f"run-gr", "rb-gr-2", user_id=self.user, approved=True)
        after = self.everything()
        self.assertEqual(after["srs_migration_snapshots"][:len(before["srs_migration_snapshots"])],
                         before["srs_migration_snapshots"])


if __name__ == "__main__":
    unittest.main()

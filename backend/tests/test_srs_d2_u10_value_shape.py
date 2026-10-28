"""Gate D-2 U10-c0·a review fix (remaining P2): the delete path checks the TYPE and
nested structure of every value it keeps (record fields and the SRS JSON columns),
not only key names. A value of the wrong shape -- e.g. an object holding a meaning
copy inside srs_state or created_at -- makes the record unsupported, so it is deleted
with the explicitly deleted card (A8) and no copy remains.

Synthetic SQLite only (QueueCase sets a throwaway DATABASE_URL per test before the
app touches a database).

Run directly:      python tests/test_srs_d2_u10_value_shape.py
Or via discovery:   python -m unittest discover -s tests
"""

from __future__ import annotations

import json
import sys
import unittest
from datetime import timedelta, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_srs_d2_u10_fixes import FixCase  # noqa: E402
from test_srs_queue import NOW, iso  # noqa: E402

from app.database import get_connection  # noqa: E402
from app.repositories import vocab_repository  # noqa: E402
from app.repositories.deck_repository import create_deck  # noqa: E402
from app.schemas import DeckCreate  # noqa: E402
from app.srs import identity, migration  # noqa: E402
from app.srs.storage import SrsWriteError  # noqa: E402

DAY = timedelta(days=1)
COPY = {"meaning_ko": "뜻-사본", "example_sentence": "例文-사본"}


def set_in(column, path, value):
    """Change one nested value of a record column (legacy_json / srs_*_json)."""
    def change(record):
        data = json.loads(record[column])
        target = data
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value
        return column, json.dumps(data, ensure_ascii=False)
    return change


CASES = {
    # the three review cases
    "apply srs_after_json.srs_state object": ("apply", 2, set_in("srs_after_json", ["srs_state"], COPY)),
    "rollback srs_before_json.srs_state object": ("rollback", 2, set_in("srs_before_json", ["srs_state"], COPY)),
    "card.created_at object": ("apply", 2, set_in("legacy_json", ["card", "created_at"], COPY)),
    # more of the same kind
    "card.created_at object (format 1)": ("apply", 1, set_in("legacy_json", ["card", "created_at"], COPY)),
    "rollback card.created_at list": ("rollback", 2, set_in("legacy_json", ["card", "created_at"], ["뜻-사본"])),
    "card.srs_card_version object": ("apply", 2, set_in("legacy_json", ["card", "srs_card_version"], COPY)),
    "card.first_completed_at text copy": ("apply", 2, set_in("legacy_json", ["card", "first_completed_at"], "뜻-사본")),
    "card.srs_pause_reason text copy": ("apply", 2, set_in("legacy_json", ["card", "srs_pause_reason"], "뜻-사본 문장")),
    "card.srs_history_flags object": ("apply", 2, set_in("legacy_json", ["card", "srs_history_flags"], COPY)),
    "apply srs_after_json.srs_due_at list": ("apply", 2, set_in("srs_after_json", ["srs_due_at"], ["뜻-사본"])),
    "apply srs_after_json.srs_config_version copy": ("apply", 2, set_in("srs_after_json", ["srs_config_version"], "뜻-사본")),
    "rollback srs_before_json.srs_stability object": ("rollback", 2, set_in("srs_before_json", ["srs_stability"], COPY)),
    "rollback srs_after_json.next_review_at object": ("rollback", 2, set_in("srs_after_json", ["next_review_at"], COPY)),
    "rollback baseline fingerprint object": ("rollback", 2, set_in("legacy_json", ["baseline", "card_fingerprint"], COPY)),
}


class ValueShapeCase(FixCase):
    def card_with_records(self, name, deck=None):
        ref = self.content_card(name, deck)
        full = dict(self.card_row("personal", ref))
        self.apply(ref, run=f"run-{name}")
        self.rate_at("personal", ref, NOW, "good")
        self.now = NOW
        self.rollback("personal", ref, source=f"run-{name}")
        return ref, full

    def damage(self, ref, full, which, fmt, change):
        record = [r for r in self.records("personal", ref) if r["mode"] == which][0]
        if fmt == 1:
            self.to_format1(record["id"], full if which == "apply" else dict(self.card_row("personal", ref)))
            record = [r for r in self.records("personal", ref) if r["mode"] == which][0]
        column, text = change(record)
        with get_connection() as c:
            c.execute(f"UPDATE srs_migration_snapshots SET {column} = ? WHERE id = ?", (text, record["id"]))
        return record["id"]

    def all_text(self, ref):
        return " ".join((r["legacy_json"] or "") + (r["srs_before_json"] or "") + (r["srs_after_json"] or "")
                        for r in self.records("personal", ref))


# ---------------------------------------------------------------------------
class DeleteTests(ValueShapeCase):
    def run_cases(self, use_deck):
        deck = create_deck(self.user, DeckCreate(name=f"vs-{use_deck}"))[0]["id"] if use_deck else None
        made = {}
        for i, (name, (which, fmt, change)) in enumerate(CASES.items()):
            ref, full = self.card_with_records(f"vs{int(use_deck)}-{i}", deck)
            made[name] = (ref, self.damage(ref, full, which, fmt, change))
            self.assertIn("사본", self.all_text(ref), name)
        keep, _ = self.card_with_records(f"keep{int(use_deck)}")
        keep_before = self.records("personal", keep)
        with get_connection() as c:
            logs = [tuple(r) for r in c.execute("SELECT * FROM review_logs ORDER BY id")]
        if use_deck:
            self.assertEqual(self.client.delete(f"/decks/{deck}", headers=self.headers).status_code, 200)
        else:
            for ref, _ in made.values():
                self.assertEqual(self.client.delete(f"/vocab-items/{ref}", headers=self.headers).status_code, 204)
        for name, (ref, record_id) in made.items():
            self.assertNotIn(record_id, {r["id"] for r in self.records("personal", ref)}, name)
            self.assertNotIn("사본", self.all_text(ref), name)
        self.assertEqual(self.records("personal", keep), keep_before)
        with get_connection() as c:
            self.assertEqual([tuple(r) for r in c.execute("SELECT * FROM review_logs ORDER BY id")], logs)
            identity.personal_id_references(c)

    def test_word_delete(self):
        self.run_cases(False)

    def test_deck_delete(self):
        self.run_cases(True)

    def test_normal_records_with_nulls_and_offsets_are_kept_minimal(self):
        for fmt in (1, 2):
            with self.subTest(fmt=fmt):
                ref, full = self.card_with_records(f"normal-{fmt}")
                apply_rec = [r for r in self.records("personal", ref) if r["mode"] == "apply"][0]
                if fmt == 1:
                    full = dict(full, first_completed_at=NOW.astimezone(timezone(timedelta(hours=-5))).isoformat(),
                                completion_metric_version=None)
                    self.to_format1(apply_rec["id"], full)
                else:
                    self.damage(ref, full, "apply", 2, set_in("legacy_json", ["card", "first_completed_at"],
                                                              iso(NOW).replace("+00:00", "Z")))
                before = {r["id"]: r for r in self.records("personal", ref)}
                self.assertTrue(vocab_repository.delete_vocab_item(self.user, ref))
                after = self.records("personal", ref)
                self.assertEqual({r["id"] for r in after}, set(before))  # nothing deleted
                for record in after:
                    payload, old = self.payload(record), json.loads(before[record["id"]]["legacy_json"])
                    self.assertEqual(payload["format"], 2)
                    for key in ("last_log_id", "baseline", "restart"):
                        self.assertEqual(payload.get(key), old.get(key))
                    self.assertEqual(payload["card"], {k: old["card"][k] for k in payload["card"]})
                    self.assertEqual((record["srs_before_json"], record["srs_after_json"]),
                                     (before[record["id"]]["srs_before_json"], before[record["id"]]["srs_after_json"]))

    def test_unused_plan_b_permission_is_kept_on_rebuild(self):
        ref, boundary, run, at = self.to_plan_b("personal", name="pb")
        records = self.records("personal", ref)
        latest = records[-1]
        self.assertIn("restart", self.payload(latest))
        # rewrite to format 1 (the pre-conversion card row) to force a rebuild on delete
        full = dict(self.card_row("personal", ref))
        full.update(self.payload(latest)["card"])
        self.to_format1(latest["id"], full)
        restart = self.payload(self.records("personal", ref)[-1])["restart"]
        self.assertTrue(vocab_repository.delete_vocab_item(self.user, ref))
        self.assertEqual(self.payload(self.records("personal", ref)[-1])["restart"], restart)

    def test_failure_and_cas_restore_deleted_rows(self):
        class Boom(Exception):
            pass

        ref, full = self.card_with_records("fail")
        self.damage(ref, full, "apply", 2, set_in("srs_after_json", ["srs_state"], COPY))
        rollback_rec = [r for r in self.records("personal", ref) if r["mode"] == "rollback"][0]
        self.to_format1(rollback_rec["id"], dict(self.card_row("personal", ref)))  # needs a rebuild on delete
        before = self.everything()
        with mock.patch("app.srs.identity.record_personal_deletions", side_effect=Boom()):
            with self.assertRaises(Boom):
                vocab_repository.delete_vocab_item(self.user, ref)
        self.assertEqual(self.everything(), before)
        # CAS: a judged JSON column changes between reading and writing -> everything rolls back.
        real = migration._srs_columns_shape
        holder = {"done": False}

        def changing(mode, before_text, after_text):
            result = real(mode, before_text, after_text)
            if not holder["done"] and mode == "rollback":
                holder["done"] = True
                holder["conn"].execute("UPDATE srs_migration_snapshots SET srs_after_json = srs_after_json || ' ' "
                                       "WHERE card_ref = ? AND id = (SELECT MAX(id) FROM srs_migration_snapshots "
                                       "WHERE card_ref = ?)", (ref, ref))
            return result

        real_strip = migration.strip_card_snapshots

        def strip(connection, *a, **k):
            holder["conn"] = connection
            return real_strip(connection, *a, **k)

        with mock.patch.object(migration, "_srs_columns_shape", changing), \
                mock.patch.object(migration, "strip_card_snapshots", strip):
            with self.assertRaises(SrsWriteError) as caught:
                vocab_repository.delete_vocab_item(self.user, ref)
        self.assertEqual(caught.exception.code, "snapshot_content_unverified")
        self.assertEqual(self.everything(), before)

    def test_reads_and_rollback_never_delete(self):
        ref, full = self.card_with_records("reads")
        self.damage(ref, full, "rollback", 2, set_in("srs_before_json", ["srs_state"], COPY))
        before = self.everything()["srs_migration_snapshots"]
        migration.dry_run([self.key("personal", ref)])
        self.q()
        self.assertEqual(self.everything()["srs_migration_snapshots"], before)


if __name__ == "__main__":
    unittest.main()

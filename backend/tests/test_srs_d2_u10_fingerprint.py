"""Gate D-2 U10-c0·a review fix: a rollback record's baseline fingerprints are accepted
only as what the code writes -- lowercase SHA-256 hex (64 characters, hashlib
hexdigest). Anything else (a sentence, empty, wrong length, non-hex, uppercase, an
object, a number, a boolean, NULL) makes the record unsupported, so the explicitly
deleted card's record goes with it (A8) and no copy remains.

Synthetic SQLite only (QueueCase sets a throwaway DATABASE_URL per test before the
app touches a database).

Run directly:      python tests/test_srs_d2_u10_fingerprint.py
Or via discovery:   python -m unittest discover -s tests
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_srs_d2_u10_value_shape import ValueShapeCase  # noqa: E402
from test_srs_queue import NOW  # noqa: E402

from app.database import get_connection  # noqa: E402
from app.repositories import vocab_repository  # noqa: E402
from app.repositories.deck_repository import create_deck  # noqa: E402
from app.schemas import DeckCreate  # noqa: E402
from app.srs import identity, migration  # noqa: E402
from app.srs.storage import SrsWriteError  # noqa: E402

COPY = "뜻-사본 문장입니다"
BAD_VALUES = {
    "sentence": COPY, "empty": "", "short": "a" * 63, "long": "a" * 65, "non-hex": "g" * 64,
    "uppercase": "A" * 64, "object": {"meaning_ko": COPY}, "list": [COPY], "number": 5, "bool": True, "null": None,
}


class FingerprintCase(ValueShapeCase):
    def set_fingerprint(self, ref, full, field, value, fmt):
        record = [r for r in self.records("personal", ref) if r["mode"] == "rollback"][0]
        if fmt == 1:
            self.to_format1(record["id"], dict(self.card_row("personal", ref)))
            record = [r for r in self.records("personal", ref) if r["mode"] == "rollback"][0]
        payload = self.payload(record)
        payload["baseline"][field] = value
        with get_connection() as c:
            c.execute("UPDATE srs_migration_snapshots SET legacy_json = ? WHERE id = ?",
                      (json.dumps(payload, ensure_ascii=False), record["id"]))
        return record["id"]


class FingerprintTests(FingerprintCase):
    def run_delete(self, use_deck):
        deck = create_deck(self.user, DeckCreate(name=f"fp-{use_deck}"))[0]["id"] if use_deck else None
        made = []
        for field in ("card_fingerprint", "logs_fingerprint"):
            for fmt in (1, 2):
                ref, full = self.card_with_records(f"fp{int(use_deck)}-{field[:4]}-{fmt}", deck)
                made.append((field, fmt, ref, self.set_fingerprint(ref, full, field, COPY, fmt)))
                self.assertIn(COPY, self.all_text(ref))
        keep, _ = self.card_with_records(f"fpkeep{int(use_deck)}")
        keep_before = self.records("personal", keep)
        with get_connection() as c:
            logs = [tuple(r) for r in c.execute("SELECT * FROM review_logs ORDER BY id")]
        if use_deck:
            self.assertEqual(self.client.delete(f"/decks/{deck}", headers=self.headers).status_code, 200)
        else:
            for _, _, ref, _ in made:
                self.assertEqual(self.client.delete(f"/vocab-items/{ref}", headers=self.headers).status_code, 204)
        for field, fmt, ref, record_id in made:
            remaining = self.records("personal", ref)
            self.assertNotIn(record_id, {r["id"] for r in remaining}, (field, fmt))
            self.assertEqual(len(remaining), 1, (field, fmt))  # the normal apply record stays
            self.assertNotIn(COPY, self.all_text(ref), (field, fmt))
        self.assertEqual(self.records("personal", keep), keep_before)
        with get_connection() as c:
            self.assertEqual([tuple(r) for r in c.execute("SELECT * FROM review_logs ORDER BY id")], logs)
            identity.personal_id_references(c)

    def test_word_delete(self):
        self.run_delete(False)

    def test_deck_delete(self):
        self.run_delete(True)

    def test_every_bad_value_is_unsupported_and_lowercase_hex_is_normal(self):
        record = {"format": 2, "card": {"id": 1, "created_at": "2026-10-01T00:00:00+00:00"},
                  "baseline": {"card_version": 3, "card_fingerprint": "0" * 64, "logs_fingerprint": "ab" * 32,
                               "last_log_id": 1}}
        columns = frozenset({"id", "created_at"})
        self.assertIsNotNone(migration._record_shape("rollback", "personal", 1, record, columns))
        for field in ("card_fingerprint", "logs_fingerprint"):
            for name, value in BAD_VALUES.items():
                with self.subTest(field=field, value=name):
                    bad = json.loads(json.dumps(record))
                    bad["baseline"][field] = value
                    self.assertIsNone(migration._record_shape("rollback", "personal", 1, bad, columns))

    def test_normal_fingerprints_kept_and_restore_still_works(self):
        ref, full = self.card_with_records("normal")
        rollback_rec = [r for r in self.records("personal", ref) if r["mode"] == "rollback"][0]
        baseline = self.payload(rollback_rec)["baseline"]
        for name in ("card_fingerprint", "logs_fingerprint"):
            self.assertRegex(baseline[name], r"^[0-9a-f]{64}$")  # what the code writes
        self.assertEqual(self.reconvert("personal", ref)[2]["reconversion"], "restored")
        self.rate_at("personal", ref, NOW + 5 * self.DAY, "good")
        self.rate_at("personal", ref, NOW + 9 * self.DAY, "good")
        self.now = NOW
        self.assertTrue(self.seen[-1][1])  # version-gap proof holds
        records = {r["id"]: r for r in self.records("personal", ref)}
        self.assertTrue(vocab_repository.delete_vocab_item(self.user, ref))
        after = {r["id"]: r for r in self.records("personal", ref)}
        self.assertEqual(set(after), set(records))  # nothing deleted
        self.assertEqual(self.payload(after[rollback_rec["id"]])["baseline"], baseline)

    def test_plan_b_permission_kept(self):
        ref, boundary, run, at = self.to_plan_b("personal", name="fp-b")
        restart = self.payload(self.records("personal", ref)[-1])["restart"]
        self.assertTrue(vocab_repository.delete_vocab_item(self.user, ref))
        self.assertEqual(self.payload(self.records("personal", ref)[-1])["restart"], restart)

    def test_failure_and_cas_restore_everything(self):
        class Boom(Exception):
            pass

        ref, full = self.card_with_records("fail")
        self.set_fingerprint(ref, full, "card_fingerprint", COPY, 2)
        apply_rec = [r for r in self.records("personal", ref) if r["mode"] == "apply"][0]
        self.to_format1(apply_rec["id"], full)  # a normal record that needs a rebuild
        before = self.everything()
        with mock.patch("app.srs.identity.record_personal_deletions", side_effect=Boom()):
            with self.assertRaises(Boom):
                vocab_repository.delete_vocab_item(self.user, ref)
        self.assertEqual(self.everything(), before)
        real = migration._srs_columns_shape
        holder = {"done": False}

        def changing(mode, before_text, after_text):
            result = real(mode, before_text, after_text)
            if not holder["done"] and mode == "apply":
                holder["done"] = True
                holder["conn"].execute("UPDATE srs_migration_snapshots SET srs_after_json = srs_after_json || ' ' "
                                       "WHERE id = ?", (apply_rec["id"],))
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

    def test_reads_never_delete(self):
        ref, full = self.card_with_records("reads")
        self.set_fingerprint(ref, full, "logs_fingerprint", COPY, 2)
        before = self.everything()["srs_migration_snapshots"]
        migration.dry_run([self.key("personal", ref)])
        self.q()
        self.assertEqual(self.everything()["srs_migration_snapshots"], before)

    @property
    def DAY(self):
        from datetime import timedelta
        return timedelta(days=1)


if __name__ == "__main__":
    unittest.main()

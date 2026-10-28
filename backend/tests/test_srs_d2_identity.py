"""Gate D-2 U1~U3: personal card id references, SQLite id reuse prevention,
content-free deletion ledger and identity-unknown isolation.

Synthetic SQLite only (QueueCase sets a throwaway DATABASE_URL per test before
the app touches a database). Never vocab.db, Neon or PostgreSQL.

Run directly:      python tests/test_srs_d2_identity.py
Or via discovery:   python -m unittest discover -s tests
"""

from __future__ import annotations

import hashlib
import json
import sys
import threading
import time
import unittest
from datetime import timedelta
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_srs_queue import NOW, QueueCase, iso  # noqa: E402
import race_support  # noqa: E402

from app.database import get_connection  # noqa: E402
from app.repositories.deck_repository import create_deck, delete_deck_with_items  # noqa: E402
from app.repositories.vocab_repository import delete_vocab_item  # noqa: E402
from app.schemas import DeckCreate  # noqa: E402
from app.srs import goals, identity, migration, queue, reviews  # noqa: E402
from app.srs.engine import CardKey, SrsPhase  # noqa: E402
from app.srs.storage import SrsWriteError  # noqa: E402


def legacy_reusable_table() -> None:
    """Turn this synthetic database's vocab_items back into the pre-D-2 shape
    (plain INTEGER PRIMARY KEY, no sequence) to reproduce existing installations."""
    connection = get_connection()
    try:
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute("BEGIN IMMEDIATE")
        sql = connection.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='vocab_items'").fetchone()[0]
        attachments = [r[0] for r in connection.execute(
            "SELECT sql FROM sqlite_master WHERE tbl_name='vocab_items' AND type IN ('index','trigger') AND sql IS NOT NULL")]
        columns = ", ".join(r[1] for r in connection.execute("PRAGMA table_info(vocab_items)"))
        old_sql = sql.replace("PRIMARY KEY AUTOINCREMENT", "PRIMARY KEY", 1).replace("CREATE TABLE vocab_items", "CREATE TABLE vi_old", 1)
        connection.execute(old_sql)
        connection.execute(f"INSERT INTO vi_old ({columns}) SELECT {columns} FROM vocab_items")
        connection.execute("DROP TABLE vocab_items")
        connection.execute("ALTER TABLE vi_old RENAME TO vocab_items")
        for statement in attachments:
            connection.execute(statement)
        connection.execute("DELETE FROM sqlite_sequence WHERE name = 'vocab_items'")
        connection.execute("COMMIT")
        connection.execute("PRAGMA foreign_keys = ON")
    finally:
        connection.close()


def table_sql() -> str:
    with get_connection() as c:
        return c.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='vocab_items'").fetchone()[0]


def rows_digest() -> tuple[int, str]:
    with get_connection() as c:
        rows = [tuple(r) for r in c.execute("SELECT * FROM vocab_items ORDER BY id").fetchall()]
    return len(rows), hashlib.sha256(repr(rows).encode()).hexdigest()


def log_digest() -> tuple[int, str]:
    with get_connection() as c:
        rows = [tuple(r) for r in c.execute("SELECT * FROM review_logs ORDER BY id").fetchall()]
    return len(rows), hashlib.sha256(repr(rows).encode()).hexdigest()


def rebuild(**kwargs):
    connection = get_connection()
    try:
        return identity.rebuild_vocab_items_autoincrement(connection, **kwargs)
    finally:
        connection.close()


def references():
    with get_connection() as c:
        return identity.personal_id_references(c)


class IdentityCase(QueueCase):
    def legacy_log(self, card, at, user=None, rating="good"):
        with get_connection() as c:
            c.execute("INSERT INTO review_logs (user_id, vocab_item_id, rating, reviewed_at, previous_review_level, "
                      "next_review_level, next_review_at) VALUES (?, ?, ?, ?, 0, 1, ?)",
                      (user or self.user, card, rating, iso(at), iso(at)))

    def fresh_fsrs(self, name, **kw):
        card = self.personal(name, **kw)
        self.fsrs("personal", card)  # FSRS card without state, no logs
        return card

    def logs_for(self, card):
        with get_connection() as c:
            return c.execute("SELECT COUNT(*) FROM review_logs WHERE user_id = ? AND vocab_item_id = ?",
                             (self.user, card)).fetchone()[0]

    def raw_delete(self, card):
        """A deletion that left no ledger row (before U3 existed)."""
        with get_connection() as c:
            c.execute("DELETE FROM vocab_items WHERE id = ?", (card,))

    def scan_and_flag(self):
        with get_connection() as c:
            scan = identity.scan_identity(c)
            identity.flag_identity_unknown(c, scan.findings)
        return scan


# ---------------------------------------------------------------------------
class ReferenceTests(IdentityCase):
    def test_max_covers_every_server_source_and_other_accounts(self):
        a = self.fresh_fsrs("a")
        self.rate("personal", a, request="00000000-0000-4000-8000-00000000000a")
        b = self.personal("b")  # legacy fresh -> migrate to get a snapshot and run JSON
        plan = migration.dry_run([CardKey("personal", self.user, b)])
        migration.apply_plan(plan, "run-ref", approved=True)
        self.legacy_log(500, NOW - timedelta(days=1), user=self.other)  # another account's high id
        with get_connection() as c:
            c.execute("INSERT INTO meaning_feedback (user_id, vocabulary_id, surface, status, created_at) "
                      "VALUES (?, 700, 'x', 'open', ?)", (self.user, iso(NOW)))
            c.execute("INSERT INTO srs_card_deletions (card_kind, user_id, card_ref, deleted_at) "
                      "VALUES ('personal', ?, 650, ?)", (self.user, iso(NOW)))
        refs = references()
        self.assertEqual(refs["review_logs.vocab_item_id"], 500)
        self.assertEqual(refs["meaning_feedback.vocabulary_id"], 700)
        self.assertEqual(refs["srs_card_deletions.card_ref"], 650)
        self.assertEqual(refs["srs_review_receipts.card_ref"], a)
        self.assertEqual(refs["srs_migration_snapshots"], b)
        self.assertEqual(refs["srs_migration_runs"], b)
        self.assertEqual(max(refs.values()), 700)

    def test_malformed_references_stop_instead_of_skipping(self):
        b = self.personal("b")
        migration.apply_plan(migration.dry_run([CardKey("personal", self.user, b)]), "run-bad", approved=True)
        with get_connection() as c:
            c.execute("UPDATE srs_migration_runs SET scope_json = '{not json' WHERE run_key = 'run-bad'")
        with self.assertRaises(identity.IdentityError) as caught:
            references()
        self.assertEqual(caught.exception.code, "invalid_json")
        with get_connection() as c:
            c.execute("UPDATE srs_migration_runs SET scope_json = ? WHERE run_key = 'run-bad'",
                      (json.dumps({"user_id": self.user, "cards": [{"kind": "personal", "ref_id": "7"}]}),))
        with self.assertRaises(identity.IdentityError) as caught:
            references()
        self.assertEqual(caught.exception.code, "uninterpretable_reference")
        with get_connection() as c:
            c.execute("DELETE FROM srs_migration_snapshots")
            c.execute("DELETE FROM srs_migration_runs")
            c.execute("INSERT INTO review_logs (user_id, vocab_item_id, rating, reviewed_at, previous_review_level, "
                      "next_review_level, next_review_at) VALUES (?, 'x12', 'good', ?, 0, 1, ?)", (self.user, iso(NOW), iso(NOW)))
        with self.assertRaises(identity.IdentityError) as caught:
            references()
        self.assertEqual(caught.exception.code, "uninterpretable_reference")
        # A stopped scan writes nothing, and a rebuild with it stops before any change.
        sql_before = table_sql()
        with self.assertRaises(identity.IdentityError):
            rebuild()
        self.assertEqual(table_sql(), sql_before)


# ---------------------------------------------------------------------------
class RebuildTests(IdentityCase):
    def setUp(self):
        super().setUp()
        legacy_reusable_table()

    def test_reproduces_reuse_then_rebuild_prevents_it(self):
        keep = self.personal("keep")
        top = self.fresh_fsrs("top")
        self.rate("personal", top, request="00000000-0000-4000-8000-0000000000aa")
        b = self.personal("snap")
        migration.apply_plan(migration.dry_run([CardKey("personal", self.user, b)]), "run-1", approved=True)
        # Delete the two largest ids without a ledger row (as before U3): only logs,
        # receipts, snapshot and run JSON keep them.
        self.raw_delete(b)
        self.raw_delete(top)
        reused = self.personal("reused")
        self.assertEqual(reused, top, "pre-D-2 table reuses a deleted largest id (F12)")
        self.raw_delete(reused)
        self.legacy_log(900, NOW - timedelta(days=2), user=self.other)  # another account's higher reference
        count_before, hash_before = rows_digest()
        logs_before = log_digest()
        report = rebuild()
        self.assertFalse(report["already_autoincrement"])
        self.assertEqual(report["max_reference"], 900)
        self.assertEqual(rows_digest(), (count_before, hash_before))
        self.assertEqual(log_digest(), logs_before)
        self.assertIn("AUTOINCREMENT", table_sql())
        fresh = self.personal("after")
        self.assertGreater(fresh, 900)
        self.assertNotIn(fresh, {keep, top, b, reused})
        # The new card has no inherited history and its first FSRS review works.
        self.fsrs("personal", fresh)
        self.assertEqual(self.logs_for(fresh), 0)
        self.assertIsNotNone(self.rate("personal", fresh, request="00000000-0000-4000-8000-0000000000bb"))
        # Delete and create still work, foreign keys are on and consistent.
        self.assertTrue(delete_vocab_item(self.user, fresh))
        self.assertGreater(self.personal("again"), fresh)
        with get_connection() as c:
            self.assertEqual(c.execute("PRAGMA foreign_keys").fetchone()[0], 1)
            self.assertEqual(c.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_indexes_triggers_and_constraints_survive(self):
        self.personal("a")
        with get_connection() as c:
            c.execute("CREATE INDEX idx_test_vocab_surface ON vocab_items(surface)")
            c.execute("CREATE TRIGGER trg_test_vocab_noop AFTER UPDATE ON vocab_items BEGIN SELECT 1; END")
            before = sorted(tuple(r) for r in c.execute(
                "SELECT type, name, sql FROM sqlite_master WHERE tbl_name='vocab_items' AND name NOT LIKE 'sqlite_%'"))
            columns = [tuple(r) for r in c.execute("PRAGMA table_info(vocab_items)")]
        rebuild()
        with get_connection() as c:
            after = sorted(tuple(r) for r in c.execute(
                "SELECT type, name, sql FROM sqlite_master WHERE tbl_name='vocab_items' AND name NOT LIKE 'sqlite_%'"))
            self.assertEqual([tuple(r) for r in c.execute("PRAGMA table_info(vocab_items)")], columns)
        self.assertEqual([a[:2] for a in after], [b[:2] for b in before])
        self.assertEqual([a[2] for a in after if a[0] != "table"], [b[2] for b in before if b[0] != "table"])

    def test_failure_at_any_step_rolls_back_and_rerun_is_safe(self):
        cards = [self.personal(f"c{i}") for i in range(3)]
        self.raw_delete(cards[-1])
        self.legacy_log(cards[-1], NOW - timedelta(days=1))
        sql_before, digest_before = table_sql(), rows_digest()
        for step in ("after_create", "after_copy", "after_rename", "after_sequence"):
            with self.assertRaises(identity.IdentityError):
                rebuild(fail_step=step)
            self.assertEqual(table_sql(), sql_before, step)
            self.assertEqual(rows_digest(), digest_before, step)
            with get_connection() as c:
                self.assertIsNone(c.execute(
                    "SELECT 1 FROM sqlite_master WHERE name = ?", (identity.REBUILD_TABLE,)).fetchone(), step)
                self.assertEqual(c.execute("PRAGMA foreign_keys").fetchone()[0], 1)
        first = rebuild()
        second = rebuild()
        self.assertTrue(second["already_autoincrement"])
        self.assertEqual(second["sequence_after"], first["sequence_after"])
        self.assertEqual(rows_digest(), digest_before)
        # An existing higher sequence is never lowered.
        with get_connection() as c:
            c.execute("UPDATE sqlite_sequence SET seq = 5000 WHERE name = 'vocab_items'")
        self.assertEqual(rebuild()["sequence_after"], 5000)
        self.assertEqual(self.personal("next"), 5001)


# ---------------------------------------------------------------------------
class LedgerTests(IdentityCase):
    def ledger(self):
        with get_connection() as c:
            columns = [r[1] for r in c.execute("PRAGMA table_info(srs_card_deletions)")]
            rows = [dict(r) for r in c.execute("SELECT * FROM srs_card_deletions ORDER BY id")]
        return columns, rows

    def test_word_and_deck_deletion_write_content_free_rows(self):
        word = self.personal("word")
        deck = create_deck(self.user, DeckCreate(name="d"))[0]["id"]
        in_deck = [self.personal(f"d{i}", deck=deck) for i in range(2)]
        other_card = self.personal("other-user", user=self.other,
                                   deck=create_deck(self.other, DeckCreate(name="o"))[0]["id"])
        self.assertTrue(delete_vocab_item(self.user, word))
        self.assertFalse(delete_vocab_item(self.user, other_card))  # not this account's card: nothing logged
        delete_deck_with_items(self.user, deck)
        columns, rows = self.ledger()
        # U4 follow-up (E2) adds the past-learning mark only; no content column.
        self.assertEqual(columns, ["id", "card_kind", "user_id", "card_ref", "deleted_at",
                                   "history_intro_status", "history_intro_known_by"])
        self.assertEqual(sorted(r["card_ref"] for r in rows), sorted([word, *in_deck]))
        self.assertTrue(all(r["user_id"] == self.user and r["card_kind"] == "personal" for r in rows))
        self.assertGreater(references()["srs_card_deletions.card_ref"], 0)

    def test_ledger_failure_keeps_the_card_and_delete_failure_keeps_no_ledger(self):
        card = self.personal("keep-me")
        with get_connection() as c:
            c.execute("ALTER TABLE srs_card_deletions RENAME TO srs_card_deletions_off")
        with self.assertRaises(Exception):
            delete_vocab_item(self.user, card)
        with get_connection() as c:
            c.execute("ALTER TABLE srs_card_deletions_off RENAME TO srs_card_deletions")
            self.assertIsNotNone(c.execute("SELECT 1 FROM vocab_items WHERE id = ?", (card,)).fetchone())
            # The delete itself fails after the ledger insert: both roll back.
            c.execute("CREATE TRIGGER trg_block_delete BEFORE DELETE ON vocab_items BEGIN SELECT RAISE(ABORT, 'blocked'); END")
        with self.assertRaises(Exception):
            delete_vocab_item(self.user, card)
        with get_connection() as c:
            self.assertIsNotNone(c.execute("SELECT 1 FROM vocab_items WHERE id = ?", (card,)).fetchone())
            self.assertEqual(c.execute("SELECT COUNT(*) FROM srs_card_deletions").fetchone()[0], 0)
        deck = create_deck(self.user, DeckCreate(name="d"))[0]["id"]
        self.personal("in-deck", deck=deck)
        with self.assertRaises(Exception):
            delete_deck_with_items(self.user, deck)
        with get_connection() as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM srs_card_deletions").fetchone()[0], 0)
            self.assertIsNotNone(c.execute("SELECT 1 FROM decks WHERE id = ?", (deck,)).fetchone())


# ---------------------------------------------------------------------------
class IdentityUnknownTests(IdentityCase):
    def setUp(self):
        super().setUp()
        legacy_reusable_table()  # an installation where reuse already happened

    def mixed(self, *, with_ledger: bool):
        """Card `old` (largest id) gets an FSRS review + receipt, is deleted, and a new
        card takes its id. Returns (id, old request id)."""
        old = self.fresh_fsrs("old")
        request = "00000000-0000-4000-8000-0000000000c1"
        self.now = NOW - timedelta(days=3)
        self.rate("personal", old, request=request, version=0, at=NOW - timedelta(days=3))
        self.now = NOW
        if with_ledger:
            delete_vocab_item(self.user, old)
        else:
            self.raw_delete(old)
        new = self.fresh_fsrs("new", created=NOW - timedelta(hours=1))
        self.assertEqual(new, old)
        return new, request

    def assert_old_retry_refused(self, card, request):
        logs = log_digest()
        with get_connection() as c:
            receipts = c.execute("SELECT COUNT(*) FROM srs_review_receipts").fetchone()[0]
        with self.assertRaises(SrsWriteError) as caught:
            self.rate("personal", card, request=request, version=0)
        self.assertEqual((caught.exception.code, caught.exception.status_code), ("card_version_conflict", 409))
        self.assertEqual(log_digest(), logs)  # no review added
        with get_connection() as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM srs_review_receipts").fetchone()[0], receipts)
            self.assertEqual(c.execute("SELECT srs_card_version FROM vocab_items WHERE id = ?", (card,)).fetchone()[0], 0)

    def test_old_request_retry_on_reused_id_with_ledger(self):
        card, request = self.mixed(with_ledger=True)
        self.assert_old_retry_refused(card, request)  # ledger alone refuses, before any scan
        scan = self.scan_and_flag()
        self.assertIn("deleted_then_reused", scan.findings[0].reasons)

    def test_old_request_retry_on_reused_id_before_ledger(self):
        card, request = self.mixed(with_ledger=False)
        scan = self.scan_and_flag()  # pre-ledger mixing is found only by the scan
        self.assertEqual(scan.findings[0].card_ref, card)
        self.assertIn("log_before_created", scan.findings[0].reasons)
        self.assertIn("receipt_before_created", scan.findings[0].reasons)
        self.assert_old_retry_refused(card, request)
        # A new review of the flagged card is refused too (isolation, before the engine).
        own = "00000000-0000-4000-8000-0000000000e1"
        self.now = NOW + timedelta(minutes=1)
        with self.assertRaises(SrsWriteError) as caught:  # isolated: refused before the engine
            self.rate("personal", card, request=own, version=0, at=self.now)
        self.assertEqual(caught.exception.code, "card_identity_unknown")

    def test_flagged_card_blocks_conversion_and_skips_old_rollback(self):
        legacy = self.personal("legacy")
        migration.apply_plan(migration.dry_run([CardKey("personal", self.user, legacy)]), "run-x", approved=True)
        self.raw_delete(legacy)
        reused = self.personal("reused-legacy", created=NOW)
        self.assertEqual(reused, legacy)
        scan = self.scan_and_flag()
        self.assertEqual([(f.card_ref, f.reasons) for f in scan.findings], [(reused, ["snapshot_other_card"])])
        candidate = migration.dry_run([CardKey("personal", self.user, reused)])[0]
        self.assertEqual(candidate.quality, "identity_unknown")
        result = migration.apply_plan([candidate], "run-y", approved=True)
        self.assertEqual(result[0]["result"], "blocked")
        rolled = migration.rollback_plan("run-x", "rb-x", user_id=self.user, approved=True)
        self.assertEqual(rolled[0], {"kind": "personal", "ref_id": reused, "result": "skipped", "reason": "identity_unknown"})
        with get_connection() as c:
            self.assertEqual(c.execute("SELECT srs_engine FROM vocab_items WHERE id = ?", (reused,)).fetchone()[0], "legacy")

    def test_normal_conversion_rollback_and_incomplete_history_are_not_flagged(self):
        fresh = self.personal("fresh")
        migration.apply_plan(migration.dry_run([CardKey("personal", self.user, fresh)]), "run-n", approved=True)
        self.rate("personal", fresh, request="00000000-0000-4000-8000-0000000000d1")
        migration.rollback_plan("run-n", "rb-n", user_id=self.user, approved=True)
        incomplete = self.personal("incomplete")  # logs but no engine state, broken chain
        self.legacy_log(incomplete, NOW - timedelta(days=1))
        self.fsrs("personal", incomplete)
        missing = self.personal("missing-history")
        with get_connection() as c:
            c.execute("UPDATE vocab_items SET last_reviewed_at = ?, correct_count = 2 WHERE id = ?",
                      (iso(NOW - timedelta(days=2)), missing))
        scan = self.scan_and_flag()
        self.assertEqual(scan.findings, [])
        self.assertEqual(scan.undetermined, [])

    def test_identity_unknown_counts_only_on_its_log_dates_unless_a_time_is_unreadable(self):
        old = self.personal("old")
        two_days_ago = NOW - timedelta(days=2)
        self.legacy_log(old, two_days_ago)
        self.raw_delete(old)
        reused = self.personal("reused", created=NOW - timedelta(days=1))
        self.assertEqual(reused, old)
        clean = self.personal("clean")
        self.legacy_log(clean, NOW - timedelta(minutes=10))
        self.scan_and_flag()
        with get_connection() as c:
            today = goals.introduction_count(c, self.user, NOW)
            that_day = goals.introduction_count(c, self.user, two_days_ago)
            other_day = goals.introduction_count(c, self.user, NOW - timedelta(days=5))
        self.assertEqual((today.status, today.count), ("exact", 1))  # today keeps counting
        self.assertEqual((that_day.status, that_day.count, that_day.identity_unknown_cards), ("unknown", None, 1))
        self.assertEqual((other_day.status, other_day.count), ("exact", 0))
        # Queue and stats use the same rule.
        goal = self.q()["new_goal"]
        self.assertEqual(goal["introduced_today_status"], "exact")
        # One unreadable time on the flagged id: no date narrowing, unknown on every date.
        with get_connection() as c:
            c.execute("INSERT INTO review_logs (user_id, vocab_item_id, rating, reviewed_at, previous_review_level, "
                      "next_review_level, next_review_at) VALUES (?, ?, 'good', 'garbage', 0, 1, ?)", (self.user, reused, iso(NOW)))
            today = goals.introduction_count(c, self.user, NOW)
        self.assertEqual(today.status, "unknown")
        self.assertEqual(self.q()["new_goal"]["introduced_today_status"], "unknown")

    def test_history_rows_and_daily_review_counts_are_preserved(self):
        old = self.personal("old")
        self.legacy_log(old, NOW - timedelta(days=2))
        self.legacy_log(old, NOW - timedelta(days=1))
        self.raw_delete(old)
        self.personal("reused", created=NOW - timedelta(hours=2))
        logs = log_digest()
        self.scan_and_flag()
        self.scan_and_flag()  # repeated scans keep the first flag
        self.assertEqual(log_digest(), logs)
        with get_connection() as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM srs_card_identity_flags").fetchone()[0], 1)
            self.assertEqual(c.execute("SELECT COUNT(*) FROM review_logs WHERE user_id = ?", (self.user,)).fetchone()[0], 2)

    def test_accounts_are_separate(self):
        other_deck = create_deck(self.other, DeckCreate(name="o"))[0]["id"]
        theirs = self.personal("theirs", user=self.other, deck=other_deck)
        self.legacy_log(theirs, NOW - timedelta(days=1), user=self.other)
        self.raw_delete(theirs)
        mine = self.personal("mine", created=NOW)
        self.assertEqual(mine, theirs)  # same id, different account
        scan = self.scan_and_flag()
        self.assertEqual(scan.findings, [])  # the other account's log never attaches to this account's card
        self.assertEqual(self.logs_for(mine), 0)
        # Lost access: another account cannot reach this card or replay onto it.
        from app.repositories.vocab_repository import record_review

        self.assertIsNone(record_review(self.other, mine, "good", request_id="00000000-0000-4000-8000-0000000000f1",
                                        expected_card_version=0, session_id="s1"))


# ---------------------------------------------------------------------------
class IsolationTests(IdentityCase):
    """Gate D-2 U1~U3 correction: a flagged personal card is isolated whatever its
    engine state -- not served, not "due now", and direct FSRS reviews are refused
    before the engine and before any write."""

    REQUEST = "00000000-0000-4000-8000-0000000001a1"

    def flagged_with_state(self, name="state", completed=None):
        card = self.personal(name, created=NOW - timedelta(days=10))
        self.due("personal", card, SrsPhase.REVIEW, NOW - timedelta(hours=1))
        if completed:
            with get_connection() as c:
                c.execute("UPDATE vocab_items SET completion_metric_version = 'meaning-completion-v1-draft', "
                          "first_completed_at = ? WHERE id = ?", (completed, card))
        self.legacy_log(card, NOW - timedelta(days=20))  # evidence: older than the card
        return card

    def flag(self, card):
        with get_connection() as c:
            scan = identity.scan_identity(c)
            self.assertIn(card, [f.card_ref for f in scan.findings])
            identity.flag_identity_unknown(c, scan.findings)

    def card_state(self, card):
        with get_connection() as c:
            row = dict(c.execute("SELECT srs_card_version, srs_state, srs_due_at, srs_effective_due_at, review_level, "
                                 "next_review_at, last_reviewed_at, correct_count, completion_metric_version, "
                                 "first_completed_at FROM vocab_items WHERE id = ?", (card,)).fetchone())
            row["receipts"] = c.execute("SELECT COUNT(*) FROM srs_review_receipts").fetchone()[0]
        row["logs"] = log_digest()
        return row

    def due_now(self, counts):
        return counts["learning_due"] + counts["relearning_due"] + counts["review_due"]

    def assert_refused(self, card, version=0, request=None):
        before = self.card_state(card)
        with self.assertRaises(SrsWriteError) as caught:
            self.rate("personal", card, request=request or self.REQUEST, version=version)
        self.assertEqual((caught.exception.code, caught.exception.status_code), ("card_identity_unknown", 409))
        self.assertEqual(self.card_state(card), before)

    def test_card_with_engine_state_is_isolated_everywhere(self):
        from app.repositories.vocab_repository import list_vocab_items

        card = self.flagged_with_state(completed=iso(NOW - timedelta(days=40)))
        normal = self.personal("normal")
        self.due("personal", normal, SrsPhase.REVIEW, NOW - timedelta(hours=2))
        self.flag(card)
        result = self.q(scope="personal_deck", deck_id=self.deck)
        counts = result["counts"]
        self.assertEqual([i["card_id"] for i in result["items"]], [normal])
        self.assertEqual(counts["blocked_history"], 1)
        self.assertEqual(sum(counts[name] for name in queue.CATEGORIES), counts["total_in_scope"])
        listed = [i["id"] for i in list_vocab_items(self.user, deck_id=self.deck, due_only=True)]
        self.assertEqual(listed, [normal])
        self.assertEqual(len(listed), self.due_now(counts))
        self.assertEqual(self.due_now(self.q()["counts"]), 1)  # account scope (home, stats) agrees
        self.assert_refused(card)  # first completion record kept, no new evidence
        self.assertEqual(self.card_state(card)["first_completed_at"], iso(NOW - timedelta(days=40)))
        self.assertIsNotNone(self.rate("personal", normal, request="00000000-0000-4000-8000-0000000001a2"))

    def test_card_without_engine_state_gets_the_same_isolation(self):
        card = self.personal("stateless", created=NOW - timedelta(days=1))
        self.fsrs("personal", card)
        self.legacy_log(card, NOW - timedelta(days=3))
        self.flag(card)
        counts = self.q()["counts"]
        self.assertEqual(counts["blocked_history"], 1)
        self.assert_refused(card)

    def test_card_fetched_before_the_flag_is_refused_after_it(self):
        card = self.flagged_with_state()
        item = self.q()["items"][0]
        self.assertEqual(item["card_id"], card)
        self.flag(card)
        self.assert_refused(card, version=item["card_version"])

    def test_http_response_is_409_with_no_card_content(self):
        from fastapi.testclient import TestClient
        from app import main
        from app.auth import create_access_token

        card = self.flagged_with_state()
        self.flag(card)
        client = TestClient(main.app)
        self.addCleanup(client.close)
        headers = {"Authorization": "Bearer " + create_access_token({"id": self.user, "email": "c1@example.test"})}
        before = self.card_state(card)
        response = client.post(f"/study-items/{card}/review", headers=headers, json={
            "rating": "good", "request_id": self.REQUEST, "session_id": "11111111-1111-4111-8111-111111111111",
            "expected_card_version": 0})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json(), {"detail": "card_identity_unknown"})
        self.assertEqual(self.card_state(card), before)

    def test_other_accounts_subscribed_and_normal_cards_unchanged(self):
        card = self.flagged_with_state()
        self.flag(card)
        shared = self.shared_deck("s")
        word = self.lexeme("w", shared, 0)
        self.due("lexeme", word, SrsPhase.REVIEW, NOW - timedelta(hours=1))
        other_deck = create_deck(self.other, DeckCreate(name="o"))[0]["id"]
        theirs = self.personal("theirs", user=self.other, deck=other_deck)
        self.set_mode(self.other, "fsrs")
        self.due("personal", theirs, SrsPhase.REVIEW, NOW - timedelta(hours=1))
        self.assertIn(("lexeme", word), self.keys(self.q()))
        self.assertIn(("personal", theirs), self.keys(self.q(user=self.other)))
        self.assertIsNotNone(self.rate("lexeme", word, request="00000000-0000-4000-8000-0000000001b1", deck=shared))

    # ---- races (real overlapping SQLite connections, lock order via LockProbe) ----
    def flag_direct(self, card):
        with get_connection() as c:
            identity.flag_identity_unknown(c, [identity.IdentityFinding(self.user, card, ["log_before_created"])])
        return "flagged"

    def test_flag_committed_first_then_review_is_refused_without_writes(self):
        card = self.flagged_with_state()
        before = self.card_state(card)
        with race_support.LockProbe() as probe:
            connection = get_connection()
            try:
                # Flag written but not committed: MainThread holds the account lock.
                identity.flag_identity_unknown(connection, [identity.IdentityFinding(self.user, card, ["log_before_created"])])
                review = race_support.start(
                    "review", lambda: self.rate("personal", card, request=self.REQUEST, version=0))
                self.assertTrue(probe.wait("waiting", "review"))
                time.sleep(0.3)
                self.assertNotIn(("acquired", "review"), probe.events)
                probe.mark("released", "MainThread")
                connection.commit()
            finally:
                connection.close()
            race_support.finish_error(self, review, SrsWriteError, "card_identity_unknown")
        probe.assert_serialized(self, "MainThread", "review")
        self.assertEqual(self.card_state(card), before)

    def test_review_committed_first_is_kept_and_flag_follows(self):
        card = self.flagged_with_state()
        entered, release = threading.Event(), threading.Event()
        real_review = reviews.review

        def slow_review(*args, **kwargs):
            entered.set()
            self.assertTrue(release.wait(15))
            return real_review(*args, **kwargs)

        with race_support.LockProbe() as probe, mock.patch.object(reviews, "review", slow_review):
            review = race_support.start("review", lambda: self.rate("personal", card, request=self.REQUEST, version=0))
            self.assertTrue(entered.wait(15))  # passed the flag check, holds the lock
            flag = race_support.start("flag", lambda: self.flag_direct(card))
            self.assertTrue(probe.wait("waiting", "flag"))
            time.sleep(0.3)
            self.assertNotIn(("acquired", "flag"), probe.events)
            probe.mark("released", "review")
            release.set()
            result = race_support.finish(self, review)
            self.assertEqual(race_support.finish(self, flag), "flagged")
        probe.assert_serialized(self, "review", "flag")
        self.assertEqual(result["srs"]["card_version"], 1)
        with get_connection() as c:
            self.assertEqual(c.execute("SELECT srs_card_version FROM vocab_items WHERE id = ?", (card,)).fetchone()[0], 1)
            self.assertEqual(c.execute("SELECT COUNT(*) FROM review_logs WHERE vocab_item_id = ? AND srs_engine = 'fsrs'",
                                       (card,)).fetchone()[0], 1)  # kept, not deleted afterwards
            self.assertEqual(c.execute("SELECT COUNT(*) FROM srs_review_receipts").fetchone()[0], 1)
            self.assertEqual(c.execute("SELECT COUNT(*) FROM srs_card_identity_flags").fetchone()[0], 1)
            receipt_at = c.execute("SELECT created_at FROM srs_review_receipts").fetchone()[0]
            detected_at = c.execute("SELECT detected_at FROM srs_card_identity_flags").fetchone()[0]
        self.assertLessEqual(goals.read_utc(receipt_at), goals.read_utc(detected_at))
        # From now on the card is isolated, and the earlier request is not replayed.
        self.assertEqual(self.q()["counts"]["blocked_history"], 1)
        with self.assertRaises(SrsWriteError) as caught:
            self.rate("personal", card, request=self.REQUEST, version=0)
        self.assertEqual(caught.exception.code, "card_version_conflict")


if __name__ == "__main__":
    unittest.main()

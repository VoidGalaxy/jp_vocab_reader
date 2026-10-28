"""OPS_MIGRATION_RESUME_LEXEME_PLAN (L-1): CLI `resume` of SUBSCRIBED (lexeme) cards with the REAL product apply_plan
on a synthetic SQLite file made by the test.

REAL: approvals (v3, the prior chain, the basis inquiry), signatures (test-only temporary OpenSSH keys made by
`test_ops_signature.Keys` and removed afterwards -- real ssh-keygen signing, nothing faked), the pre-check, the
backup evidence checks, the plan file, `read_status` / `judge_status` / `progress_values` and the product functions
(`dry_run`, `apply_plan`, `run_progress_values`). TEST INJECTION: the connection source (the app's own SQLite
connections to the test file, as in test_srs_migrate_resume_sqlite.py) and the named admin row changes of L6 / L7
(subscription deactivated, deck word removed: the app has no such path). No PostgreSQL, Neon or backend/vocab.db;
nothing here is PostgreSQL evidence, and the personal-card RS4 results are not counted for these cards.

Cards: account `user`'s subscribed lexemes l1, l2 (one shared deck, also subscribed by `other`, who has progress
rows for the SAME lexemes) and personal p1 (= the base's first personal card). Expected values come from the plan
(OPS_MIGRATION_RESUME_LEXEME_PLAN 2절 / 7-4절), never from a run.

Run directly:      python tests/test_srs_migrate_resume_lexeme_sqlite.py
"""

from __future__ import annotations

import os

os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["PYTHON_DOTENV_DISABLED"] = "1"

import hashlib  # noqa: E402
import json  # noqa: E402
import sqlite3  # noqa: E402
import sys  # noqa: E402
import unittest  # noqa: E402
from datetime import timedelta  # noqa: E402
from pathlib import Path  # noqa: E402
from unittest import mock  # noqa: E402

TESTS_DIR = Path(__file__).resolve().parent
BACKEND = TESTS_DIR.parent
sys.path.insert(0, str(BACKEND / "scripts"))
sys.path.insert(0, str(TESTS_DIR))
if str(BACKEND) not in sys.path:      # path only, from this file's location
    sys.path.append(str(BACKEND))

import srs_migrate as cli  # noqa: E402
import test_srs_migrate_resume_sqlite as rs  # noqa: E402  (module only: the resume SQLite base)
from test_srs_queue import NOW, iso  # noqa: E402

from app.database import get_connection  # noqa: E402
from app.repositories.lexeme_repository import get_or_create_progress, get_or_create_subscription  # noqa: E402
from app.srs import migration  # noqa: E402
from app.srs.engine import CardKey  # noqa: E402

RUN_KEY = rs.RUN_KEY
NINE = {"run_id", "status", "mode", "config_version", "started_at", "finished_at", "scope_sha256", "summary_sha256",
        "snapshots_sha256"}


class LexemeBase(rs.ResumeBase):
    """The resume base, with the plan, request and evidence rebuilt for a fixed card set passed explicitly."""

    CARD_SET = ("l1", "l2")                              # each test class names its own set

    def setUp(self):
        super().setUp()
        deck = self.shared_deck("lexeme resume deck")
        get_or_create_subscription(self.other, deck)
        self.deck_id = deck
        self.lex = {name: self.lexeme(name, deck, order) for order, name in enumerate(("l1", "l2"))}
        with get_connection() as connection:
            for lexeme in self.lex.values():
                get_or_create_progress(connection, self.other, lexeme)
                for user in (self.user, self.other):                    # past study, no log: convertible
                    connection.execute(
                        "UPDATE user_word_progress SET srs_engine = 'legacy', srs_config_version = NULL, "
                        "srs_participation = NULL, srs_history_quality = NULL, last_reviewed_at = ?, "
                        "correct_count = 2, review_level = 2, next_review_at = ? WHERE user_id = ? AND lexeme_id = ?",
                        (iso(NOW - timedelta(days=5)), iso(NOW + timedelta(days=3)), user, lexeme))
        self.p1 = self.cards[0]
        self.keys_by_name = {"l1": ("lexeme", self.user, self.lex["l1"]), "l2": ("lexeme", self.user, self.lex["l2"]),
                             "p1": ("personal", self.user, self.p1)}
        personal = [self.keys_by_name[n][2] for n in self.CARD_SET if self.keys_by_name[n][0] == "personal"]
        lexemes = [self.keys_by_name[n][2] for n in self.CARD_SET if self.keys_by_name[n][0] == "lexeme"]
        self.req = cli.make_request(self.user, RUN_KEY, personal, lexemes)
        self.planned = migration.dry_run([CardKey(*self.keys_by_name[n]) for n in self.CARD_SET], connect=self.connect)
        os.remove(self.path("plan.json"))                 # this test's own folder: the base's personal-only plan
        self.plan = self.write_plan(self.planned, self.user)
        self.names = {key: name for name, key in self.keys_by_name.items()}

    def name_of(self, kind, ref) -> str:
        """Card name by its KEY (kind, user, ref), never by position."""
        return self.names[(kind, self.user, ref)]

    def lexeme_rows(self, user=None) -> list:
        connection = sqlite3.connect(self.db_path)
        try:
            return [tuple(connection.execute("SELECT * FROM user_word_progress WHERE user_id = ? AND lexeme_id = ?",
                                             (user or self.user, lx)).fetchone()) for lx in self.lex.values()]
        finally:
            connection.close()

    def other_account_state(self) -> list:
        """The other account's progress rows for the SAME lexemes, every lexeme log row, and the out-of-scope
        personal cards (other account's and this account's outside card)."""
        connection = sqlite3.connect(self.db_path)
        try:
            logs = connection.execute("SELECT * FROM lexeme_review_logs ORDER BY id").fetchall()
        finally:
            connection.close()
        return [self.lexeme_rows(self.other), logs, self.rows([self.other_card, self.outside])]

    def card_engine(self, name) -> str:
        kind, user, ref = self.keys_by_name[name]
        table, column = ("user_word_progress", "lexeme_id") if kind == "lexeme" else ("vocab_items", "id")
        connection = sqlite3.connect(self.db_path)
        try:
            return connection.execute(f"SELECT srs_engine FROM {table} WHERE user_id = ? AND {column} = ?",
                                      (user, ref)).fetchone()[0]
        finally:
            connection.close()

    def card_row(self, name) -> tuple:
        kind, user, ref = self.keys_by_name[name]
        table, column = ("user_word_progress", "lexeme_id") if kind == "lexeme" else ("vocab_items", "id")
        connection = sqlite3.connect(self.db_path)
        try:
            return tuple(connection.execute(f"SELECT * FROM {table} WHERE user_id = ? AND {column} = ?",
                                            (user, ref)).fetchone())
        finally:
            connection.close()

    def snapshot_keys(self) -> list:
        connection = sqlite3.connect(self.db_path)
        try:
            rows = connection.execute("SELECT user_id, card_kind, card_ref FROM srs_migration_snapshots ORDER BY id")
            return [self.name_of(kind, ref) for user, kind, ref in rows if user == self.user]
        finally:
            connection.close()

    def summary_order(self) -> list:
        connection = sqlite3.connect(self.db_path)
        try:
            text = connection.execute("SELECT summary_json FROM srs_migration_runs WHERE run_key = ?",
                                      (RUN_KEY,)).fetchone()[0]
        finally:
            connection.close()
        return [(self.name_of(r["kind"], r["ref_id"]), r["result"]) for r in json.loads(text)["results"]]


class LexemeOnly(LexemeBase):
    CARD_SET = ("l1", "l2")

    def test_l1_partial_lexeme_run_resumes_the_remaining_card(self):
        self.assertEqual(self.first(batch=1)[1], 3)
        l1_after_first, outside = self.card_row("l1"), self.other_account_state()
        self.assertEqual(self.snapshot_keys(), ["l1"])
        out, code = self.resume(batch=2)
        self.assertEqual((out["phase"], code, out["results"]), ("completed", 0, {"already_applied": 1, "applied": 1}))
        self.assertEqual(self.card_row("l1"), l1_after_first)                      # committed card kept
        self.assertEqual(self.card_engine("l2"), "fsrs")                           # only the remaining card
        self.assertEqual(self.snapshot_keys(), ["l1", "l2"])                       # kind 'lexeme', by key
        self.assertEqual(self.summary_order(), [("l1", "already_applied"), ("l2", "applied")])
        self.assertEqual(self.other_account_state(), outside)                     # L4: same lexemes of `other`
        self.assertEqual(self.run_state(), ("completed", 2))

    def test_l2_failed_lexeme_run_resumes(self):
        def fail_second_card(*, read_only, index):
            if index == 3:                                 # first, card l1, then the card l2 connection: INJECTED
                raise cli.pc.OpsProductConnectionError("synthetic_connection_failure")
            return self.connect(read_only=read_only)
        self.assertEqual(self.first(batch=2, write_connect=fail_second_card)[1], 1)
        self.assertEqual(self.run_state(), ("failed", 1))
        l1_row, outside = self.card_row("l1"), self.other_account_state()
        out, code = self.resume(batch=2)
        self.assertEqual((out["phase"], code, out["results"]), ("completed", 0, {"already_applied": 1, "applied": 1}))
        self.assertEqual(self.card_row("l1"), l1_row)
        self.assertEqual((self.card_engine("l2"), self.run_state()), ("fsrs", ("completed", 2)))
        self.assertEqual(self.other_account_state(), outside)

    def test_l5_nine_values_pre_read_equal_under_lock_and_independent(self):
        self.first(batch=1)
        seen = {}
        real_pre, real_lock = cli.progress_values, migration.run_progress_values

        def pre(row, snapshots):
            seen["pre_read"] = json.loads(json.dumps(real_pre(row, snapshots)))            # fixed copy
            return real_pre(row, snapshots)

        def lock(connection, run_id):
            result = real_lock(connection, run_id)
            seen["under_lock"] = json.loads(json.dumps(result))
            return result
        connection = sqlite3.connect(self.db_path)
        try:
            row = connection.execute("SELECT id, status, mode, config_version, started_at, finished_at, scope_json, "
                                     "summary_json FROM srs_migration_runs WHERE run_key = ?", (RUN_KEY,)).fetchone()
            snaps = connection.execute("SELECT id, user_id, card_kind, card_ref FROM srs_migration_snapshots "
                                       "WHERE run_id = ? ORDER BY id", (row[0],)).fetchall()
        finally:
            connection.close()
        text = lambda v: None if v is None else hashlib.sha256(str(v).encode("utf-8")).hexdigest()  # noqa: E731
        independent = {"run_id": row[0], "status": row[1], "mode": row[2], "config_version": row[3],
                       "started_at": row[4], "finished_at": row[5], "scope_sha256": text(row[6]),
                       "summary_sha256": text(row[7]), "snapshots_sha256": hashlib.sha256(json.dumps(
                           [list(s) for s in snaps], separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()}
        with mock.patch.object(cli, "progress_values", pre), mock.patch.object(migration, "run_progress_values", lock):
            out, code = self.resume(batch=2)
        self.assertEqual(code, 0, out)
        self.assertEqual(set(seen), {"pre_read", "under_lock"})
        for value in (seen["pre_read"], seen["under_lock"], independent):
            self.assertEqual(set(value), NINE)
        self.assertEqual(seen["pre_read"], seen["under_lock"])
        self.assertEqual(seen["pre_read"], independent)

    def admin_change(self, statement, params):
        """TEST INJECTION (L6 / L7): the named admin row change; the app has no unsubscribe path."""
        connection = sqlite3.connect(self.db_path)
        try:
            connection.execute(statement, params)
            connection.commit()
        finally:
            connection.close()

    def lost_access(self, statement, params):
        self.first(batch=1)
        l1_row, l2_row, outside = self.card_row("l1"), self.card_row("l2"), self.other_account_state()
        self.admin_change(statement, params)
        out, code = self.resume(batch=2)
        self.assertEqual((out["phase"], code, out["results"]), ("completed", 5, {"already_applied": 1, "conflict": 1}))
        self.assertEqual(self.card_row("l2"), l2_row)                     # THIS card: no write at all
        self.assertEqual(self.card_row("l1"), l1_row)
        self.assertEqual(self.snapshot_keys(), ["l1"])                    # no snapshot for l2
        self.assertEqual(self.summary_order(), [("l1", "already_applied"), ("l2", "conflict")])
        self.assertEqual(self.run_state(), ("completed", 2))              # run summary / cursor / completion: normal
        self.assertEqual(self.other_account_state(), outside)

    def test_l6_subscription_lost_before_resume(self):
        self.lost_access("UPDATE user_deck_subscriptions SET is_active = 0 WHERE user_id = ? AND shared_deck_id = ?",
                         (self.user, self.deck_id))

    def test_l7_deck_word_removed_before_resume(self):
        self.lost_access("DELETE FROM shared_deck_words WHERE shared_deck_id = ? AND lexeme_id = ?",
                         (self.deck_id, self.lex["l2"]))


class Mixed(LexemeBase):
    CARD_SET = ("l1", "l2", "p1")

    def test_l3_mixed_scope_order_and_keys(self):
        self.assertEqual([self.name_of(c.key.kind, c.key.ref_id) for c in self.planned], ["l1", "l2", "p1"])
        self.assertEqual(self.first(batch=1)[1], 3)
        outside = self.other_account_state()
        out, code = self.resume(batch=3)
        self.assertEqual((out["phase"], code, out["results"]), ("completed", 0, {"already_applied": 1, "applied": 2}))
        self.assertEqual(self.summary_order(), [("l1", "already_applied"), ("l2", "applied"), ("p1", "applied")])
        self.assertEqual(sorted(self.snapshot_keys()), ["l1", "l2", "p1"])
        self.assertEqual([self.card_engine(n) for n in ("l1", "l2", "p1")], ["fsrs"] * 3)
        self.assertEqual(self.other_account_state(), outside)


if __name__ == "__main__":
    unittest.main()

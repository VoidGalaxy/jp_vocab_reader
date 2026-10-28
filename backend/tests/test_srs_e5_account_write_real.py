"""E-5a actual PG checks. Protected local test harness only; opt-in otherwise skipped."""

from __future__ import annotations

import os
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import test_srs_e3_fk_real as pg
from _srs_e5_writes import Writes, sql
from _srs_e5_preflight import OWNED_TABLES
from app import account_write
from app.account_write import AccountWriteError
from app.repositories import (vocab_repository as vocab, shared_deck_repository as shared,
                              lexeme_repository as lexemes, deck_package_repository as packages,
                              feedback_repository as feedback)
from app.srs import storage


@unittest.skipUnless(pg._opt_in(), "E-5a real PostgreSQL NOT RUN (opt-in not set)")
class AccountWriteOnPostgres(pg.RealCase):
    def test_deleted_account_all_write_paths_leave_every_table_unchanged(self):
        self.create()
        w = Writes()
        w.erase_account_for_test()
        # These update helpers may return their existing missing-card sentinel before opening a write.
        missing_sentinels = {"vocab_update", "deck_update", "term_update"}
        for name, operation in w.operations().items():
            with self.subTest(operation=name):
                before = w.state()
                try:
                    result = operation()
                except AccountWriteError as error:
                    self.assertEqual((error.status_code, error.code), (404, "account_not_found"))
                else:
                    self.assertIn(name, missing_sentinels)
                    self.assertIsNone(result)
                self.assertEqual(w.state(), before)

    def test_real_account_lock_waits_both_orders_without_resurrection(self):
        self.create()
        modules = {"vocab_create": vocab, "package_import": packages, "publish": shared,
                   "shared_import": shared, "progress": lexemes, "lexeme_review": storage,
                   "personal_review": storage, "app_feedback": feedback}
        for name, module in modules.items():
            for delete_first in (False, True):
                with self.subTest(operation=name, delete_first=delete_first):
                    self.run.reset(restart_identity=True)
                    w = Writes()
                    def other_rows():
                        state = w.state()
                        return {t: [r for r in state[t] if r["user_id"] == w.other] for t in OWNED_TABLES}
                    others = other_rows()
                    write = w.operations()[name]
                    jobs = (w.erase_all_for_test, write) if delete_first else (write, w.erase_all_for_test)
                    target = account_write if delete_first else module
                    box = pg.Overlap(self, target, "begin_account_write").run(*jobs)
                    pg.judge_overlap(box)
                    self.assertEqual(box["first"][0], "ok", box["first"])
                    if delete_first:
                        self.assertEqual(box["second"][0], "error", box["second"])
                        error = box["second"][1]
                        self.assertIsInstance(error, AccountWriteError)
                        self.assertEqual((error.status_code, error.code), (404, "account_not_found"))
                    else:
                        self.assertEqual(box["second"], ("ok", "deleted"))
                    w.assert_absent(self)
                    self.assertEqual(other_rows(), others)

    def test_publish_word_failure_and_subscription_failure_are_atomic(self):
        self.create()
        w = Writes()
        before = w.state()
        real_word, real_sub = shared.add_word_to_shared_deck, shared.get_or_create_subscription

        def word_failure(*args, **kwargs):
            real_word(*args, **kwargs)
            raise RuntimeError("synthetic_publish_failure")

        def sub_failure(*args, **kwargs):
            self.assertTrue(real_sub(*args, **kwargs)[1])
            raise RuntimeError("synthetic_subscription_failure")

        for function, failure, operation in (("add_word_to_shared_deck", word_failure, "publish"),
                                             ("get_or_create_subscription", sub_failure, "shared_import")):
            with self.subTest(operation=operation), mock.patch.object(shared, function, failure):
                with self.assertRaises(RuntimeError):
                    w.operations()[operation]()
            self.assertEqual(w.state(), before)

    def test_two_publishers_with_opposite_word_order_do_not_deadlock(self):
        from app.repositories import deck_repository as decks
        from app.schemas import DeckCreate, VocabItemCreate
        self.create()
        w = Writes()
        vocab.create_or_update_vocab_item(w.user, VocabItemCreate(surface="aaa-last", deck_id=w.deck))
        other_deck = decks.create_deck(w.other, DeckCreate(name="opposite"))[0]["id"]
        for word in ("aaa-last", "e5-existing"):
            lexemes.upsert_lexeme(word, word)
            vocab.create_or_update_vocab_item(w.other, VocabItemCreate(surface=word, deck_id=other_deck))
        jobs = (lambda: shared.publish_deck(w.user, w.deck, "first", ""),
                lambda: shared.publish_deck(w.other, other_deck, "second", ""))
        box = pg.Overlap(self, shared, "upsert_lexeme").run(*jobs)
        pg.judge_overlap(box)
        for name, words in (("first", ["e5-existing", "aaa-last", "e5-term"]),
                            ("second", ["aaa-last", "e5-existing"])):
            self.assertEqual(box[name][0], "ok", box[name])
            deck_id = box[name][1]["shared_deck_id"]
            rows = sql("SELECT l.base_form FROM shared_deck_words w JOIN lexemes l ON l.id = w.lexeme_id "
                       "WHERE w.shared_deck_id = ? ORDER BY w.sort_order", (deck_id,))
            self.assertEqual([r["base_form"] for r in rows], words)

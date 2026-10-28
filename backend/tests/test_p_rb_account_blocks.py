"""P-RB account write block (P_RB_BLOCK_CONTRACT.md) on synthetic SQLite; the same checks run
on the protected local PostgreSQL from test_p_rb_account_blocks_real.py.

- both lock orders between an ordinary write and setting the block, with the waiting side
  proven (SQLite: BEGIN IMMEDIATE pending; PG: pg_blocking_pids names the holder);
- every E-5a write route and a receipt retry refused (409 account_writes_blocked, writes 0);
  reads and other accounts unaffected;
- a grant for this account / block / token / action rolls back; any other grant is refused;
- an exception, mixed results and a restart all leave the block on; only a no-change
  precheck release before any change, and a proven completed release, are accepted;
- same key + token re-call, other token refused, grant void after release;
- deletion held while blocked, released history deleted with the account;
- a failure inside the recovery transaction rolls back the progress record with the data."""

from __future__ import annotations

import os
import sys
import tempfile
import threading
import time
import unittest
from contextlib import ExitStack, contextmanager
from pathlib import Path
from unittest import mock

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import _e5c_support as s  # noqa: E402

TOKEN = "prb-synthetic-recovery-token-0123456789abcdef"
OTHER_TOKEN = "prb-synthetic-recovery-token-fedcba9876543210"
KEY = "prb-recovery-1"
WAIT = s.WAIT


def grant(user, key=KEY, token=TOKEN, action="rollback"):
    from app.account_write import RecoveryGrant

    return RecoveryGrant(user_id=user, recovery_key=key, action=action, token=token)


class HoldThenWait:
    """`hold` (thread 'writer') takes the account lock and pauses right after it; `wait`
    (thread 'deleter') must then wait for that lock; both outcomes are collected."""

    def __init__(self, probe):
        self.probe, self.box = probe, {}
        self.entered, self.release = threading.Event(), threading.Event()

    def pause(self):
        if threading.current_thread().name == "writer" and not self.entered.is_set():
            self.entered.set()
            if not self.release.wait(WAIT):
                raise TimeoutError("the holder was never released")

    def run(self, hold, wait):
        def job(name, fn):
            try:
                self.box[name] = ("ok", fn())
            except BaseException as error:  # noqa: BLE001 -- kept as the outcome
                self.box[name] = ("error", error)

        threads = [threading.Thread(target=job, args=("hold", hold), name="writer", daemon=True)]
        try:
            threads[0].start()
            self.box["held"] = self.entered.wait(WAIT)
            if not self.box["held"]:
                return self.box
            threads.append(threading.Thread(target=job, args=("delete", wait), name="deleter", daemon=True))
            threads[1].start()
            deadline, waited = time.monotonic() + WAIT, False
            while time.monotonic() < deadline and threads[1].is_alive():
                if self.probe(self):
                    waited = True
                    break
                time.sleep(0.05)
            self.box["waited"] = waited
        finally:
            self.release.set()
            for thread in threads:
                thread.join(WAIT)
            self.box["joined"] = all(not t.is_alive() for t in threads)
        return self.box


class PrbChecks:
    db_kind = "sqlite"

    def reset_world(self):
        pass

    def waiting_probe(self):
        return s.sqlite_waiting_probe()

    # ---- helpers --------------------------------------------------------------------
    def world(self, owner=False, tag="e5c"):
        self.reset_world()
        self.ctx = s.Context(owner=owner, tag=tag)
        return self.ctx

    def block_row(self, user=None):
        rows = self.ctx.sql("SELECT * FROM account_write_blocks WHERE user_id = ? ORDER BY id",
                            (user or self.ctx.a.T,))
        return rows[-1] if rows else None

    def rollback_runs(self, user):
        import json

        rows = self.ctx.sql("SELECT id, scope_json FROM srs_migration_runs WHERE mode = 'rollback' ORDER BY id")
        return [r["id"] for r in rows if json.loads(r["scope_json"]).get("user_id") == user]

    def assert_refused(self, fn, code):
        from app.account_write import AccountWriteError
        from app.srs.storage import SrsWriteError

        with self.assertRaises((AccountWriteError, SrsWriteError)) as caught:
            fn()
        self.assertEqual(caught.exception.code, code)

    def legacy_card_run(self, user, names, run_key):
        """New legacy cards of `user`, reviewed, then migrated by the real dry_run/apply."""
        from _e5b_fixture import card, set_mode
        from app.repositories import vocab_repository as vocab
        from app.srs import migration
        from app.srs.engine import CardKey

        mode = self.ctx.sql("SELECT srs_mode FROM srs_user_settings WHERE user_id = ?", (user,))
        set_mode(user, "legacy")
        deck = self.ctx.sql("SELECT id FROM decks WHERE user_id = ? ORDER BY id", (user,))[0]["id"]
        ids = [card(user, deck, name) for name in names]
        for ref in ids:
            vocab.record_review(user, ref, "good")
        set_mode(user, "fsrs")
        migration.apply_plan(migration.dry_run([CardKey("personal", user, ref) for ref in ids]), run_key, approved=True)
        if mode and mode[0]["srs_mode"] != "fsrs":
            set_mode(user, mode[0]["srs_mode"])
        return ids

    # ---- lock order -------------------------------------------------------------------
    def test_write_first_then_block_waits_and_the_write_is_kept(self):
        from app import account_blocks
        from app.repositories import vocab_repository as vocab
        from app.schemas import VocabItemCreate

        ctx = self.world()
        real, modules = s._modules_with_lock()
        patch, probe = self.waiting_probe()[:2]
        run = HoldThenWait(probe)

        def paused(connection, user_id, **kwargs):
            real(connection, user_id, **kwargs)
            run.pause()

        with patch, ExitStack() as stack:
            for module in modules:
                stack.enter_context(mock.patch.object(module, "begin_account_write", paused))
            box = run.run(lambda: vocab.create_or_update_vocab_item(ctx.a.T, VocabItemCreate(
                surface="prb-first", deck_id=ctx.a.deck)), lambda: account_blocks.set_block(ctx.a.T, KEY, TOKEN))
        self.assertTrue(box["held"] and box["waited"] and box["joined"], box)
        self.assertEqual(box["hold"][0], "ok", box)
        self.assertEqual((box["delete"][0], box["delete"][1]["created"]), ("ok", True), box)
        self.assertEqual(len(ctx.sql("SELECT id FROM vocab_items WHERE user_id = ? AND surface = 'prb-first'",
                                     (ctx.a.T,))), 1)
        self.assertEqual(self.block_row()["status"], "active")
        return box

    def test_block_first_then_write_waits_and_is_refused(self):
        from app import account_blocks
        from app.repositories import vocab_repository as vocab
        from app.schemas import VocabItemCreate

        ctx = self.world()
        patch, probe = self.waiting_probe()[:2]
        run = HoldThenWait(probe)
        real_lock = account_blocks.lock_account

        def paused(connection, user_id):
            real_lock(connection, user_id)
            run.pause()

        with patch, mock.patch.object(account_blocks, "lock_account", paused):
            box = run.run(lambda: account_blocks.set_block(ctx.a.T, KEY, TOKEN),
                          lambda: vocab.create_or_update_vocab_item(ctx.a.T, VocabItemCreate(
                              surface="prb-late", deck_id=ctx.a.deck)))
        self.assertTrue(box["held"] and box["waited"] and box["joined"], box)
        self.assertEqual(box["hold"][0], "ok", box)
        self.assertEqual(box["delete"][0], "error", box)
        self.assertEqual(box["delete"][1].code, "account_writes_blocked")
        self.assertEqual(ctx.sql("SELECT id FROM vocab_items WHERE surface = 'prb-late'"), [])
        return box

    # ---- ordinary requests ----------------------------------------------------------------
    def test_every_write_route_is_refused_while_blocked(self):
        from app import account_blocks

        cases = {case: builder for case, builder in s.route_cases().values()}
        cases.update(s.EXTRA_CASES)
        for name, builder in cases.items():
            with self.subTest(name):
                self.reset_world()
                ctx = self.ctx = s.Context.for_case(name, tag=f"r-{name}")   # one file: unique accounts
                account_blocks.set_block(ctx.a.T, f"prb-{name}", TOKEN)
                before, others = ctx.target_rows(), ctx.others()
                method, path, body = builder(ctx)
                response = s.request(method, path, body, ctx.token())
                self.assertEqual((response.status_code, response.json().get("detail")), (409, "account_writes_blocked"))
                self.assertEqual(ctx.target_rows(), before)
                self.assertEqual(ctx.others(), others)

    def test_receipt_retry_is_refused_then_replayed_after_release(self):
        from app import account_blocks

        from _e5b_fixture import card
        from app.repositories import vocab_repository as vocab

        ctx = self.world()
        fresh = card(ctx.a.T, ctx.a.deck, "prb-receipt")          # an FSRS card with its own receipt
        body = {"rating": "good", "request_id": "prb-req-1", "expected_card_version": 0, "session_id": "prb"}
        vocab.record_review(ctx.a.T, fresh, "good", request_id="prb-req-1", expected_card_version=0, session_id="prb")
        path = f"/study-items/{fresh}/review"
        logs = len(ctx.sql("SELECT id FROM review_logs WHERE user_id = ?", (ctx.a.T,)))
        account_blocks.set_block(ctx.a.T, KEY, TOKEN)
        blocked = s.request("POST", path, body, ctx.token())
        self.assertEqual((blocked.status_code, blocked.json()["detail"]), (409, "account_writes_blocked"))
        account_blocks.release_block(ctx.a.T, KEY, TOKEN, "precheck_unrecoverable")
        replay = s.request("POST", path, body, ctx.token())
        self.assertEqual(replay.status_code, 200, replay.text[:200])
        self.assertEqual(replay.json()["request_id"], "prb-req-1")
        self.assertEqual(len(ctx.sql("SELECT id FROM review_logs WHERE user_id = ?", (ctx.a.T,))), logs)

    def test_reads_and_other_accounts_work_while_blocked(self):
        from app import account_blocks
        from app.auth import create_access_token

        ctx = self.world()
        account_blocks.set_block(ctx.a.T, KEY, TOKEN)
        for path in ("/vocab-items", "/stats", "/study-queue", "/decks", "/me"):
            self.assertEqual(s.request("GET", path, None, ctx.token()).status_code, 200, path)
        other = create_access_token({"id": ctx.a.O, "email": "other@e5b.example.test"})
        response = s.request("POST", "/decks", {"name": "o-during-block"}, other)
        self.assertEqual(response.status_code, 200, response.text[:200])
        self.assertEqual(len(ctx.sql("SELECT id FROM decks WHERE user_id = ? AND name = 'o-during-block'",
                                     (ctx.a.O,))), 1)

    # ---- grants -------------------------------------------------------------------------
    def test_only_a_matching_grant_rolls_back(self):
        from app import account_blocks
        from app.srs import migration

        ctx = self.world()
        T, O, run_key = ctx.a.T, ctx.a.O, "e5b-run-e5c"
        account_blocks.set_block(T, KEY, TOKEN)
        state = ctx.target_rows()
        refusals = {
            "no grant": (dict(user_id=T), "account_writes_blocked"),
            "other account": (dict(user_id=O, recovery=grant(O)), "recovery_grant_invalid"),
            "other token": (dict(user_id=T, recovery=grant(T, token=OTHER_TOKEN)), "recovery_grant_invalid"),
            "other key": (dict(user_id=T, recovery=grant(T, key="prb-other")), "recovery_grant_invalid"),
            "other action": (dict(user_id=T, recovery=grant(T, action="mode_switch")), "recovery_grant_invalid"),
        }
        for label, (kwargs, code) in refusals.items():
            with self.subTest(label):
                self.assert_refused(lambda: migration.rollback_plan(run_key, f"prb-rb-{label}", approved=True, **kwargs),
                                    code)
        self.assertEqual(ctx.target_rows(), state)                      # nothing written by any refusal
        self.assertEqual(self.block_row()["changes_started"], 0)
        results = migration.rollback_plan(run_key, "prb-rb-ok", user_id=T, approved=True, recovery=grant(T))
        self.assertEqual([r["result"] for r in results], ["rolled_back"])
        self.assertEqual(self.block_row()["changes_started"], 1)
        # c2 (an FSRS card without snapshot) and FSRS mode remain: not a completed recovery
        self.assert_refused(lambda: account_blocks.release_block(T, KEY, TOKEN, "completed"), "release_not_allowed")
        self.assert_refused(lambda: account_blocks.release_block(T, KEY, TOKEN, "precheck_unrecoverable"),
                            "release_not_allowed")
        self.assertEqual(self.block_row()["status"], "active")

    def test_set_recall_tokens_and_release_rules(self):
        from app import account_blocks
        from app.srs import migration

        ctx = self.world()
        T = ctx.a.T
        self.assertTrue(account_blocks.set_block(T, KEY, TOKEN)["created"])
        self.assertFalse(account_blocks.set_block(T, KEY, TOKEN)["created"])          # same key + token
        self.assert_refused(lambda: account_blocks.set_block(T, KEY, OTHER_TOKEN), "recovery_grant_invalid")
        self.assert_refused(lambda: account_blocks.set_block(T, "prb-recovery-2", TOKEN), "recovery_already_active")
        self.assert_refused(lambda: account_blocks.release_block(T, KEY, TOKEN, "operator_abandoned"),
                            "release_reason_not_allowed")
        self.assert_refused(lambda: account_blocks.release_block(T, KEY, OTHER_TOKEN, "precheck_unrecoverable"),
                            "recovery_grant_invalid")
        row = self.block_row()
        self.assertNotIn(TOKEN, [str(v) for v in row.values()])                        # hash only
        self.assertNotIn(TOKEN, repr(grant(T)))
        state = ctx.target_rows()
        state.pop("account_write_blocks")
        self.assertTrue(account_blocks.release_block(T, KEY, TOKEN, "precheck_unrecoverable")["released"])
        after = ctx.target_rows()
        after.pop("account_write_blocks")
        self.assertEqual(after, state)                                                   # no data change
        self.assert_refused(lambda: migration.rollback_plan("e5b-run-e5c", "prb-rb-late", user_id=T, approved=True,
                                                            recovery=grant(T)), "recovery_grant_invalid")
        self.assert_refused(lambda: account_blocks.set_block(T, KEY, TOKEN), "recovery_key_used")

    # ---- failure, mixed results, restart ------------------------------------------------------
    def test_failure_inside_the_rollback_rolls_back_the_progress_record_too(self):
        from app import account_blocks
        from app.srs import migration

        ctx = self.world()
        T = ctx.a.T
        account_blocks.set_block(T, KEY, TOKEN)
        state = ctx.target_rows()
        with mock.patch.object(migration, "update_card", side_effect=RuntimeError("injected")):
            with self.assertRaises(RuntimeError):
                migration.rollback_plan("e5b-run-e5c", "prb-rb-fail", user_id=T, approved=True, recovery=grant(T))
        self.assertEqual(ctx.target_rows(), state)                      # card, snapshots, runs and the block row
        self.assertEqual(self.block_row()["changes_started"], 0)
        self.assertEqual(self.rollback_runs(T), [])
        # nothing changed, provably: the precheck release is allowed
        self.assertTrue(account_blocks.release_block(T, KEY, TOKEN, "precheck_unrecoverable")["released"])

    def test_mixed_results_and_a_restart_keep_the_block(self):
        from app import account_blocks
        from app.database import get_connection
        from app.srs import identity, migration

        ctx = self.world()
        T = ctx.a.T
        m2, m3 = self.legacy_card_run(T, ["prb-m2", "prb-m3"], "prb-run-2")
        with get_connection() as c:
            identity.flag_identity_unknown(c, [identity.IdentityFinding(T, m3, ["prb_synthetic"])])
        account_blocks.set_block(T, KEY, TOKEN)
        results = migration.rollback_plan("prb-run-2", "prb-rb-2", user_id=T, approved=True, recovery=grant(T))
        self.assertEqual(sorted(r["result"] for r in results), ["rolled_back", "skipped"])
        # "restart": nothing held in memory; a new grant from the same key and token
        self.assertEqual(account_blocks.set_block(T, KEY, TOKEN), {"block_id": self.block_row()["id"], "created": False,
                                                                     "changes_started": True})
        for reason in ("precheck_unrecoverable", "completed"):
            self.assert_refused(lambda: account_blocks.release_block(T, KEY, TOKEN, reason), "release_not_allowed")
        again = migration.rollback_plan("prb-run-2", "prb-rb-2", user_id=T, approved=True, recovery=grant(T))
        self.assertEqual(again, results)                                 # same key: stored summary only
        response = s.request("POST", "/decks", {"name": "t-after-mixed"}, ctx.token())
        self.assertEqual((response.status_code, response.json()["detail"]), (409, "account_writes_blocked"))
        self.assertEqual(self.block_row()["status"], "active")

    def test_completed_release_is_closed_in_every_mode(self):
        """Review fix 2: until the approved post-recovery checks exist, `completed` is always
        refused (before: any mode other than fsrs, e.g. shadow, released the block). This
        replaces the earlier expectation of a successful completed release."""
        from _e5b_fixture import set_mode
        from app import account_blocks
        from app.repositories import deck_repository as decks, user_repository as users
        from app.schemas import DeckCreate
        from app.srs import migration

        self.world()
        U = users.create_user("prb-u@e5b.example.test", "prb-u", "synthetic")["id"]
        decks.create_deck(U, DeckCreate(name="u-deck"))
        set_mode(U, "legacy")
        self.legacy_card_run(U, ["prb-u1"], "prb-run-u")
        set_mode(U, "fsrs")
        account_blocks.set_block(U, "prb-recovery-u", TOKEN)
        results = migration.rollback_plan("prb-run-u", "prb-rb-u", user_id=U, approved=True,
                                          recovery=grant(U, key="prb-recovery-u"))
        self.assertEqual([r["result"] for r in results], ["rolled_back"])
        for mode in ("legacy", "shadow", "fsrs", None):
            with self.subTest(mode=mode):
                if mode is None:
                    self.ctx.sql("DELETE FROM srs_user_settings WHERE user_id = ?", (U,))
                else:
                    set_mode(U, mode)
                before = self.ctx.a.rows_of(U)
                self.assert_refused(lambda: account_blocks.release_block(U, "prb-recovery-u", TOKEN, "completed"),
                                    "release_not_allowed")
                self.assertEqual(self.ctx.a.rows_of(U), before)              # writes 0
                self.assertEqual(self.block_row(U)["status"], "active")
        self.assert_refused(lambda: decks.create_deck(U, DeckCreate(name="u-after")), "account_writes_blocked")

    # ---- review fix 1: the active marker -------------------------------------------------------
    def test_an_active_block_cannot_lose_its_marker(self):
        """Review fix 1: before it, clearing active_user_id on an active row passed the CHECK
        (NULL = user_id is unknown, not false), let ordinary writes through and allowed a
        second active row for the account."""
        from app import account_blocks

        ctx = self.world()
        T = ctx.a.T
        account_blocks.set_block(T, KEY, TOKEN)
        with self.assertRaises(Exception):
            ctx.sql("UPDATE account_write_blocks SET active_user_id = NULL WHERE user_id = ? AND status = 'active'", (T,))
        row = self.block_row()
        self.assertEqual((row["status"], row["active_user_id"]), ("active", T))
        for bad in ("UPDATE account_write_blocks SET active_user_id = ? WHERE user_id = ? AND status = 'active'",):
            with self.assertRaises(Exception):
                ctx.sql(bad, (ctx.a.O, T))                                    # marker of another account
        response = s.request("POST", "/decks", {"name": "t-marker"}, ctx.token())
        self.assertEqual((response.status_code, response.json()["detail"]), (409, "account_writes_blocked"))
        self.assert_refused(lambda: account_blocks.set_block(T, "prb-recovery-2", TOKEN), "recovery_already_active")

    # ---- deletion ---------------------------------------------------------------------------
    def test_deletion_is_held_while_blocked_and_history_goes_with_the_account(self):
        from app import account_blocks

        ctx = self.world()
        T = ctx.a.T
        plan = s.preview(T)["plan"]
        account_blocks.set_block(T, KEY, TOKEN)
        report = s.preview(T)
        self.assertFalse(report["eligible"])
        self.assertIn("account_writes_blocked", report["reasons"])
        applied = s.apply(T, plan)
        self.assertEqual((applied["status"], applied["reasons"]), ("blocked", ["account_writes_blocked"]))
        self.assertEqual(len(ctx.a.rows_of(T)["users"]), 1)
        account_blocks.release_block(T, KEY, TOKEN, "precheck_unrecoverable")
        others = ctx.others()
        self.assertEqual(s.delete_for_real(T)["status"], "deleted")
        self.assertEqual(ctx.target_rows(), {})
        self.assertEqual(ctx.sql("SELECT count(*) AS n FROM account_write_blocks WHERE user_id = ?", (T,))[0]["n"], 0)
        self.assertEqual(ctx.others(), others)


class WeakSchemaLookup(unittest.TestCase):
    """Review fix 1, lookup side (SQLite only): a block table created WITHOUT the active-row
    CHECK (an earlier definition) may hold an active row with no marker, or two active rows.
    The lookup reads status too and fails closed."""

    def setUp(self):
        from app.database import init_db

        directory = tempfile.TemporaryDirectory(prefix="jp_vocab_prb_", dir=BACKEND)
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "synthetic.db"
        env = mock.patch.dict(os.environ, {"APP_ENV": "test", "DATABASE_URL": f"sqlite:///{path.as_posix()}",
                                           "JWT_SECRET_KEY": s.SECRET})
        env.start()
        self.addCleanup(env.stop)
        init_db()
        self.ctx = s.Context(owner=False)
        self.ctx.sql("DROP TABLE account_write_blocks")
        self.ctx.sql("""CREATE TABLE account_write_blocks (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            purpose TEXT NOT NULL, recovery_key TEXT NOT NULL UNIQUE, grant_hash TEXT NOT NULL, status TEXT NOT NULL,
            active_user_id INTEGER UNIQUE, run_watermark INTEGER NOT NULL, changes_started INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL, changes_started_at TEXT, released_at TEXT, release_reason TEXT)""")

    def insert(self, key, active_user_id, status="active"):
        from app.account_write import token_hash

        self.ctx.sql("INSERT INTO account_write_blocks (user_id, purpose, recovery_key, grant_hash, status, "
                     "active_user_id, run_watermark, created_at) VALUES (?, 'srs_recovery', ?, ?, ?, ?, 0, 'x')",
                     (self.ctx.a.T, key, token_hash(TOKEN), status, active_user_id))

    def refused(self, fn, code):
        from app.account_write import AccountWriteError

        with self.assertRaises(AccountWriteError) as caught:
            fn()
        self.assertEqual(caught.exception.code, code)

    def check_fails_closed(self):
        from app import account_blocks

        T = self.ctx.a.T
        response = s.request("POST", "/decks", {"name": "t-weak"}, self.ctx.token())
        self.assertEqual((response.status_code, response.json()["detail"]), (409, "account_writes_blocked"))
        self.assertEqual(self.ctx.sql("SELECT id FROM decks WHERE name = 't-weak'"), [])
        self.refused(lambda: account_blocks.set_block(T, "prb-weak-new", TOKEN), "recovery_block_inconsistent")
        self.refused(lambda: account_blocks.release_block(T, "prb-weak-1", TOKEN, "precheck_unrecoverable"),
                     "recovery_block_inconsistent")
        self.assertIn("account_writes_blocked", s.preview(T)["reasons"])

    def test_active_row_without_marker_still_blocks(self):
        self.insert("prb-weak-1", None)
        self.check_fails_closed()

    def test_two_active_rows_still_block(self):
        self.insert("prb-weak-1", self.ctx.a.T)
        self.insert("prb-weak-2", None)
        self.check_fails_closed()


# The block table as created before review fix 1 (unnamed state CHECK without the NOT NULL).
OLD_BLOCKS_DDL = """
CREATE TABLE account_write_blocks (
    id {pk},
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    purpose TEXT NOT NULL CHECK (purpose IN ('srs_recovery')),
    recovery_key TEXT NOT NULL UNIQUE,
    grant_hash TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('active', 'released')),
    active_user_id INTEGER UNIQUE,
    run_watermark INTEGER NOT NULL,
    changes_started INTEGER NOT NULL DEFAULT 0 CHECK (changes_started IN (0, 1)),
    created_at TEXT NOT NULL,
    changes_started_at TEXT,
    released_at TEXT,
    release_reason TEXT CHECK (release_reason IS NULL OR release_reason IN ('completed', 'precheck_unrecoverable')),
    CHECK ((status = 'active' AND active_user_id = user_id AND released_at IS NULL AND release_reason IS NULL)
           OR (status = 'released' AND active_user_id IS NULL AND released_at IS NOT NULL
               AND release_reason IS NOT NULL))
)"""
OLD_STATE_CHECK = ("CHECK ((status = 'active' AND active_user_id = user_id AND released_at IS NULL "
                   "AND release_reason IS NULL) OR (status = 'released' AND active_user_id IS NULL "
                   "AND released_at IS NOT NULL AND release_reason IS NOT NULL))")


class UpgradeChecks:
    """Review fix 1, upgrade: a table of the earlier (normal) definition is tightened in ONE
    transaction, keeping rows, ids, history and the unique markers; damaged rows stop the
    upgrade with no change; a failure part-way changes nothing."""

    def blocks(self):
        return self.ctx.sql("SELECT * FROM account_write_blocks ORDER BY id")

    def old_rows(self, damaged=False):
        """A released history row (O) and an active row of T (damaged: active with no marker)."""
        from app.account_write import token_hash

        T, O = self.ctx.a.T, self.ctx.a.O
        h = token_hash(TOKEN)
        self.ctx.sql("INSERT INTO account_write_blocks (user_id, purpose, recovery_key, grant_hash, status, "
                     "active_user_id, run_watermark, changes_started, created_at, released_at, release_reason) VALUES "
                     "(?, 'srs_recovery', 'prb-old-1', ?, 'released', NULL, 0, 0, 't0', 't1', 'precheck_unrecoverable')",
                     (O, h))
        self.ctx.sql("INSERT INTO account_write_blocks (user_id, purpose, recovery_key, grant_hash, status, "
                     "active_user_id, run_watermark, changes_started, created_at) VALUES "
                     "(?, 'srs_recovery', 'prb-old-2', ?, 'active', ?, 0, 1, 't2')", (T, h, None if damaged else T))

    def test_upgrade_tightens_the_table_and_keeps_every_row(self):
        self.make_old_table()
        self.old_rows()
        self.bump_sequence()
        before, sequence = self.blocks(), self.sequence()
        self.assertNotIn("active_user_id IS NOT NULL", self.definition())
        self.upgrade()
        self.assertIn("active_user_id IS NOT NULL", self.definition())
        self.assertEqual(self.blocks(), before)                               # rows, ids, history
        self.assertEqual(self.sequence(), sequence)                           # ids never reused
        self.upgrade()                                                        # rerun: nothing to do
        self.assertEqual(self.blocks(), before)
        with self.assertRaises(Exception):
            self.ctx.sql("UPDATE account_write_blocks SET active_user_id = NULL WHERE recovery_key = 'prb-old-2'")
        with self.assertRaises(Exception):                                    # the unique marker still holds
            self.ctx.sql("UPDATE account_write_blocks SET status = 'active', active_user_id = ?, released_at = NULL, "
                         "release_reason = NULL, user_id = ? WHERE recovery_key = 'prb-old-1'",
                         (self.ctx.a.T, self.ctx.a.T))
        self.assertEqual(self.blocks(), before)
        response = s.request("POST", "/decks", {"name": "t-upgraded"}, self.ctx.token())
        self.assertEqual((response.status_code, response.json()["detail"]), (409, "account_writes_blocked"))

    def test_damaged_rows_stop_the_upgrade_without_change(self):
        from app.srs.schema import SchemaUpgradeError

        self.make_old_table()
        self.old_rows(damaged=True)
        before, definition = self.blocks(), self.definition()
        with self.assertRaises(SchemaUpgradeError) as caught:
            self.upgrade()
        self.assertEqual(str(caught.exception), "account_write_blocks_rows_inconsistent")
        self.assertEqual((self.blocks(), self.definition()), (before, definition))

    def test_a_failure_part_way_changes_nothing(self):
        from app.srs import schema

        self.make_old_table()
        self.old_rows()
        self.bump_sequence()
        before, catalog = self.blocks(), self.catalog()
        real = schema._tighten_block_state

        def failing(connection, is_postgres):
            real(connection, is_postgres)
            raise RuntimeError("injected after the tightening statements")

        with mock.patch.object(schema, "_tighten_block_state", failing), self.assertRaises(Exception):
            self.upgrade()
        self.assertEqual((self.blocks(), self.catalog()), (before, catalog))   # definition, objects, sequence


# Review fix (upgrade data loss): structures that are neither the approved previous nor the
# current definition. Before the fix the SQLite rebuild copied the known columns only and
# dropped the old table, losing an extra column's values and every extra object.
EXTRA_KINDS = ("column_value", "index", "trigger", "check", "foreign_key", "referencing_table", "view",
               "lookalike_check", "current_with_index")


def _refuse_test(kind):
    def test(self):
        from app.srs.schema import SchemaUpgradeError

        if kind != "current_with_index":
            self.make_old_table()
        self.add_extra(kind)
        self.old_rows()
        self.after_rows(kind)
        before, catalog = self.blocks(), self.catalog()
        with self.assertRaises(SchemaUpgradeError) as caught:
            self.upgrade()
        self.assertEqual(str(caught.exception), "account_write_blocks_structure_unrecognized")
        self.assertEqual((self.blocks(), self.catalog()), (before, catalog))
    return test


for _kind in EXTRA_KINDS:
    setattr(UpgradeChecks, f"test_refuses_unknown_structure_{_kind}", _refuse_test(_kind))


LOOKALIKE_STATE_CHECK = "CHECK (released_at IS NULL OR active_user_id IS NOT NULL OR status IN ('active', 'released'))"


class SqliteUpgrade(UpgradeChecks, unittest.TestCase):
    def setUp(self):
        from app.database import init_db

        directory = tempfile.TemporaryDirectory(prefix="jp_vocab_prb_", dir=BACKEND)
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "synthetic.db"
        env = mock.patch.dict(os.environ, {"APP_ENV": "test", "DATABASE_URL": f"sqlite:///{path.as_posix()}",
                                           "JWT_SECRET_KEY": s.SECRET})
        env.start()
        self.addCleanup(env.stop)
        init_db()
        self.ctx = s.Context(owner=False)

    def make_old_table(self):
        self.ctx.sql("DROP TABLE account_write_blocks")
        self.ctx.sql(OLD_BLOCKS_DDL.format(pk="INTEGER PRIMARY KEY AUTOINCREMENT"))

    def upgrade(self):
        from app.database import init_db

        init_db()

    def definition(self):
        return self.ctx.sql("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'account_write_blocks'")[0]["sql"]

    def catalog(self):
        objects = self.ctx.sql("SELECT type, name, tbl_name, sql FROM sqlite_master ORDER BY type, name")
        return objects, self.sequence()

    def sequence(self):
        rows = self.ctx.sql("SELECT seq FROM sqlite_sequence WHERE name = 'account_write_blocks'")
        return rows[0]["seq"] if rows else None

    def bump_sequence(self):
        """As after deleted rows: the next id is above every stored one."""
        self.ctx.sql("UPDATE sqlite_sequence SET seq = 41 WHERE name = 'account_write_blocks'")

    def old_variant(self, extra=None, state=None):
        ddl = OLD_BLOCKS_DDL.format(pk="INTEGER PRIMARY KEY AUTOINCREMENT")
        if state is not None:
            start = ddl.index("    CHECK ((status = 'active'")
            ddl = ddl[:start] + "    " + state + "\n)"
        if extra is not None:
            ddl = ddl[:ddl.rindex(")")] + ",\n    " + extra + "\n)"
        self.ctx.sql("DROP TABLE account_write_blocks")
        self.ctx.sql(ddl)

    def add_extra(self, kind):
        sql = self.ctx.sql
        if kind == "column_value":
            sql("ALTER TABLE account_write_blocks ADD COLUMN note TEXT")
        elif kind in ("index", "current_with_index"):
            sql("CREATE INDEX prb_extra_idx ON account_write_blocks(created_at)")
        elif kind == "trigger":
            sql("CREATE TRIGGER prb_extra_trg AFTER UPDATE ON account_write_blocks BEGIN SELECT 1; END")
        elif kind == "check":
            self.old_variant(extra="CHECK (length(grant_hash) > 0)")
        elif kind == "foreign_key":
            self.old_variant(extra="FOREIGN KEY (active_user_id) REFERENCES users(id)")
        elif kind == "referencing_table":
            sql("CREATE TABLE prb_ref (block_id INTEGER REFERENCES account_write_blocks(id))")
        elif kind == "view":
            sql("CREATE VIEW prb_view AS SELECT id FROM account_write_blocks")
        elif kind == "lookalike_check":
            self.old_variant(state=LOOKALIKE_STATE_CHECK)

    def after_rows(self, kind):
        if kind == "column_value":
            self.ctx.sql("UPDATE account_write_blocks SET note = 'keep-me'")

    def assert_structure_refused_without_change(self):
        from app.srs.schema import SchemaUpgradeError

        before, catalog = self.blocks(), self.catalog()
        with self.assertRaises(SchemaUpgradeError) as caught:
            self.upgrade()
        self.assertEqual(str(caught.exception), "account_write_blocks_structure_unrecognized")
        self.assertEqual((self.blocks(), self.catalog()), (before, catalog))

    def test_equivalent_sqlite_names_do_not_hide_inbound_cascade(self):
        for reference in SQLITE_BLOCK_REFERENCES:
            with self.subTest(reference=reference):
                self.make_old_table()
                self.old_rows()
                parent = self.blocks()[0]["id"]
                self.ctx.sql(f"CREATE TABLE prb_case_ref (block_id INTEGER REFERENCES {reference}(id) ON DELETE CASCADE)")
                self.ctx.sql("INSERT INTO prb_case_ref (block_id) VALUES (?)", (parent,))
                try:
                    self.assert_structure_refused_without_change()
                    self.assertEqual(self.ctx.sql("SELECT block_id FROM prb_case_ref"), [{"block_id": parent}])
                finally:
                    self.ctx.sql("DROP TABLE prb_case_ref")

    def test_equivalent_sqlite_names_do_not_hide_indexes(self):
        for reference in SQLITE_BLOCK_REFERENCES:
            with self.subTest(reference=reference):
                self.make_old_table()
                self.old_rows()
                self.ctx.sql(f'CREATE INDEX "prb_""case_idx" ON {reference}(created_at)')
                try:
                    self.assert_structure_refused_without_change()
                finally:
                    self.ctx.sql('DROP INDEX IF EXISTS "prb_""case_idx"')

    def test_equivalent_sqlite_names_do_not_hide_triggers(self):
        for reference in SQLITE_BLOCK_REFERENCES:
            with self.subTest(reference=reference):
                self.make_old_table()
                self.old_rows()
                self.ctx.sql(f"CREATE TRIGGER prb_case_trg AFTER UPDATE ON {reference} BEGIN SELECT 1; END")
                try:
                    self.assert_structure_refused_without_change()
                finally:
                    self.ctx.sql("DROP TRIGGER IF EXISTS prb_case_trg")

    def test_equivalent_sqlite_names_do_not_hide_views(self):
        for reference in SQLITE_BLOCK_REFERENCES:
            with self.subTest(reference=reference):
                self.make_old_table()
                self.old_rows()
                self.ctx.sql(f"CREATE VIEW prb_case_view AS SELECT id FROM {reference}")
                try:
                    self.assert_structure_refused_without_change()
                finally:
                    self.ctx.sql("DROP VIEW prb_case_view")

    def test_another_tables_trigger_cannot_hide_a_block_reference(self):
        self.make_old_table()
        self.old_rows()
        self.ctx.sql("CREATE TABLE prb_trigger_owner (id INTEGER PRIMARY KEY)")
        self.ctx.sql("CREATE TRIGGER prb_other_trg AFTER INSERT ON prb_trigger_owner "
                     'BEGIN SELECT id FROM "main"."AcCoUnT_WrItE_BlOcKs"; END')
        self.assert_structure_refused_without_change()

    def test_quoted_unrelated_table_name_is_inspected_without_interpolation(self):
        self.make_old_table()
        self.old_rows()
        self.ctx.sql('CREATE TABLE "prb_""unrelated" (id INTEGER PRIMARY KEY, value TEXT)')
        self.ctx.sql('INSERT INTO "prb_""unrelated" VALUES (1, \'keep-me\')')
        before = self.blocks()
        self.upgrade()
        self.assertEqual(self.blocks(), before)
        self.assertEqual(self.ctx.sql('SELECT * FROM "prb_""unrelated"'), [{"id": 1, "value": "keep-me"}])

    def test_sqlite_name_folding_matches_ascii_nocase_only(self):
        from app.srs.schema import _sqlite_ascii_fold

        for left, right in (("ACCOUNT_WRITE_BLOCKS", "account_write_blocks"),
                            ("account_write_bloc\u212as", "account_write_blocks"), ("\u0130", "i")):
            with self.subTest(left=left):
                same = self.ctx.sql("SELECT ? = ? COLLATE NOCASE AS same", (left, right))[0]["same"]
                self.assertEqual(_sqlite_ascii_fold(left) == _sqlite_ascii_fold(right), bool(same))

    def test_expression_index_is_refused_before_reading_unknown_index_columns(self):
        self.make_old_table()
        self.old_rows()
        self.ctx.sql("CREATE INDEX prb_expression_idx ON account_write_blocks(lower(recovery_key))")
        self.assert_structure_refused_without_change()


SQLITE_BLOCK_REFERENCES = (
    "ACCOUNT_WRITE_BLOCKS", "AcCoUnT_WrItE_BlOcKs", '"ACCOUNT_WRITE_BLOCKS"',
    "[AcCoUnT_WrItE_BlOcKs]", "`ACCOUNT_WRITE_BLOCKS`",
)


class StaticBoundary(unittest.TestCase):
    def test_no_http_route_or_ordinary_path_passes_a_recovery_grant(self):
        app_dir = BACKEND / "app"
        users = sorted(str(p.relative_to(app_dir)).replace("\\", "/") for p in app_dir.rglob("*.py")
                       if "recovery=" in p.read_text(encoding="utf-8"))
        self.assertEqual(users, ["srs/migration.py", "srs/storage.py"])     # the public rollback path only
        # the grant check without a write is used by the operator recovery tool only
        callers = sorted(str(p.relative_to(app_dir)).replace("\\", "/") for p in app_dir.rglob("*.py")
                         if "authorize_recovery" in p.read_text(encoding="utf-8")
                         or "record_recovery_change" in p.read_text(encoding="utf-8"))
        self.assertEqual(callers, ["account_write.py", "recovery.py"])
        main = (app_dir / "main.py").read_text(encoding="utf-8")
        self.assertNotIn("account_blocks", main)
        self.assertNotIn("RecoveryGrant", main)


class Case(PrbChecks, unittest.TestCase):
    def setUp(self):
        from app.database import init_db

        directory = tempfile.TemporaryDirectory(prefix="jp_vocab_prb_", dir=BACKEND)
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "synthetic.db"
        env = mock.patch.dict(os.environ, {"APP_ENV": "test", "DATABASE_URL": f"sqlite:///{path.as_posix()}",
                                           "JWT_SECRET_KEY": s.SECRET})
        env.start()
        self.addCleanup(env.stop)
        init_db()


if __name__ == "__main__":
    unittest.main()

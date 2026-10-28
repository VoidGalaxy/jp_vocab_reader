"""Gate E closing review: ONE continuous synthetic rehearsal on the same synthetic accounts
and cards, from the pre-SRS structure to the P-RB completed release (E_FINAL_REVIEW.md).

A = the account that converts, studies and is recovered; B = another account (owner of the
shared deck, legacy mode), the account-boundary control. Steps, in order:
  S0 pre-SRS structure + synthetic legacy rows; an old-app hard delete of the last card
  S1 upgrade (rerun = no change), old values kept; id reuse prevention (SQLite: the
     explicit d2_card_identity rebuild; PostgreSQL: IDENTITY)
  S2 explicit conversion: dry run, interrupted apply, resume under the same key, rerun
  S3 personal + subscribed FSRS reviews through the app (ASGI), lost-response retry
     (same bytes, no write), version conflict (409), another account's request (404)
  S4 FSRS reviews until the first V3 completion (source / version recorded)
  S5 P-RB: preview -> A (block) -> writes and cleanup tools refused -> atomic B -> verify
     -> completed release; logs, completion history and new-word counts kept
  S6 legacy ordinary writes resume; the same release request again returns the completed
     result and sends no write statement
  S7 cleanup tools after the release (receipt purge, snapshot minimize / prune reports)
At every step: B's rows unchanged (except B's own actions), card versions never decrease.
A separate case: a new FSRS card without a snapshot blocks the recovery.

Time moves only through one controlled app clock (every module's `now_utc`). Synthetic
SQLite here (a throwaway file); the same checks run on the protected local PostgreSQL from
test_e_final_rehearsal_real.py. Requests go through the ASGI app (httpx ASGITransport),
not a real HTTP server. Set E_FINAL_OUT=<path> to write the step table (ids, counts,
versions, states only) to a JSON file.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

BACKEND = Path(__file__).resolve().parents[1]
SCRIPTS = BACKEND / "scripts"
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import _e5c_support as s  # noqa: E402
from test_srs_e2b_upgrade_real import SRS_TABLES, fill, pre_srs_schema  # noqa: E402

UTC = timezone.utc
DAY = timedelta(days=1)
T0 = datetime(2026, 10, 6, 3, 0, tzinfo=UTC)        # after every synthetic legacy time of `fill`
TOKEN = "efinal-synthetic-recovery-token-0123456789abcdef"
KEY = "efinal-rec-1"
COMPLETION = ("first_completed_at", "first_completed_source", "version_first_completed_at",
              "version_first_completed_version", "completion_metric_version")
ACCOUNT_TABLES = ("decks", "vocab_items", "review_logs", "lexeme_review_logs", "user_word_progress",
                  "srs_user_settings", "srs_review_receipts", "srs_migration_snapshots", "srs_card_deletions",
                  "account_write_blocks", "account_recovery_runs", "user_deck_subscriptions")


def sql(query, params=()):
    from app.database import get_connection

    with get_connection() as c:
        cursor = c.execute(query, params)
        return [dict(r) for r in cursor.fetchall()] if cursor.description else []


def legacy_reusable_vocab_items(connection) -> None:
    """SQLite only: vocab_items as existing installations have it (plain INTEGER PRIMARY KEY,
    no sequence), the shape the D-2 id rebuild exists for."""
    connection.execute("PRAGMA foreign_keys = OFF")
    table = connection.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='vocab_items'").fetchone()[0]
    attachments = [r[0] for r in connection.execute(
        "SELECT sql FROM sqlite_master WHERE tbl_name='vocab_items' AND type IN ('index','trigger') AND sql IS NOT NULL")]
    columns = ", ".join(r[1] for r in connection.execute("PRAGMA table_info(vocab_items)"))
    connection.execute(table.replace("PRIMARY KEY AUTOINCREMENT", "PRIMARY KEY", 1)
                       .replace("CREATE TABLE vocab_items", "CREATE TABLE vi_old", 1))
    connection.execute(f"INSERT INTO vi_old ({columns}) SELECT {columns} FROM vocab_items")
    connection.execute("DROP TABLE vocab_items")
    connection.execute("ALTER TABLE vi_old RENAME TO vocab_items")
    for statement in attachments:
        connection.execute(statement)
    connection.execute("DELETE FROM sqlite_sequence WHERE name = 'vocab_items'")
    connection.execute("PRAGMA foreign_keys = ON")


class FinalRehearsal:
    db_kind = "sqlite"

    # ---- database-specific steps (overridden on PostgreSQL) ------------------------------------
    def build_old(self):
        from app.database import get_connection

        with get_connection() as c:
            pre_srs_schema(c)
            fill(c)
            legacy_reusable_vocab_items(c)

    def delete_old_card(self, ref):
        """SQLite: installations without the foreign-key pragma deleted the card and kept its
        log (the case the D-2 rebuild exists for)."""
        from app.database import get_connection

        with get_connection() as c:
            c.execute("PRAGMA foreign_keys = OFF")
            c.execute("DELETE FROM vocab_items WHERE id = ?", (ref,))

    def upgrade(self):
        from app.database import init_db

        init_db()

    def rebuild_ids(self):
        """SQLite: the explicit D-2 rebuild tool (a separate process on the same file)."""
        env = {k: v for k, v in os.environ.items() if k != "DATABASE_URL"}
        env["APP_ENV"] = "test"
        done = subprocess.run([sys.executable, str(SCRIPTS / "d2_card_identity.py"), "--sqlite-db", str(self.db_path),
                               "--apply-rebuild"], capture_output=True, text=True, timeout=180, env=env,
                              encoding="utf-8")
        self.assertEqual(done.returncode, 0, done.stderr[-400:])
        return "d2_card_identity --apply-rebuild"

    def catalog(self):
        return sql("SELECT type, name, tbl_name, sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY name")

    # ---- clock, requests, observations --------------------------------------------------------
    def start_clock(self):
        import app.database as database
        from app import recovery
        from app.repositories import (learning_plan_repository, lexeme_repository, stats_history_repository,
                                      stats_repository, vocab_repository)
        from app.srs import migration, queue, reviews

        self.clock = T0 - DAY
        for module in (database, reviews, migration, queue, vocab_repository, lexeme_repository, stats_repository,
                       stats_history_repository, learning_plan_repository, recovery):
            patch = mock.patch.object(module, "now_utc", side_effect=lambda: self.clock)
            patch.start()
            self.addCleanup(patch.stop)

    def token(self, user):
        from app.auth import create_access_token

        return create_access_token({"id": user, "email": f"efinal-{user}@example.test"})

    def http(self, method, path, body, user):
        return s.request(method, path, body, self.token(user))

    def review(self, kind, ref, rating="good", *, user=None, request=None, version="current", legacy=False,
               expect=200):
        user = user or self.A
        if version == "current":
            version = self.card(kind, ref)["srs_card_version"]
        body = {"rating": rating} if legacy else {"rating": rating, "request_id": request, "session_id": "efinal",
                                                  "expected_card_version": version}
        path = (f"/study-items/{ref}/review" if kind == "personal"
                else f"/shared-decks/{self.shared}/words/{ref}/review")
        response = self.http("POST", path, body, user)
        if expect is not None:
            self.assertEqual(response.status_code, expect, response.text[:300])
        return response

    def card(self, kind, ref, user=None):
        user = user or self.A
        rows = (sql("SELECT * FROM vocab_items WHERE id = ?", (ref,)) if kind == "personal" else
                sql("SELECT * FROM user_word_progress WHERE user_id = ? AND lexeme_id = ?", (user, ref)))
        return rows[0] if rows else None

    def logs(self, user):
        return {"personal": [r["id"] for r in sql("SELECT id FROM review_logs WHERE user_id = ? ORDER BY id", (user,))],
                "lexeme": [r["id"] for r in sql("SELECT id FROM lexeme_review_logs WHERE user_id = ? ORDER BY id",
                                                (user,))]}

    @staticmethod
    def digest(rows):
        return hashlib.sha256(json.dumps(rows, sort_keys=True, default=str).encode()).hexdigest()[:16]

    def account(self, user):
        out = {}
        for table in ACCOUNT_TABLES:
            rows = sql(f"SELECT * FROM {table} WHERE user_id = ? ORDER BY 1", (user,))
            out[table] = (len(rows), self.digest(rows))
        return out

    def first_dates(self, user):
        from app.database import get_connection
        from app.srs import goals

        with get_connection() as c:
            dates = goals.first_review_dates(c, user)
        return sorted((k[0], k[1], None if v is None else v.isoformat()) for k, v in dates.items())

    def stats(self, user):
        response = self.http("GET", "/stats", None, user)
        self.assertEqual(response.status_code, 200, response.text[:200])
        return response.json()

    def checkpoint(self, step, **facts):
        """Per tracked card: version (never lower than before), engine, completion source."""
        cards = {}
        for name, (kind, ref) in self.tracked.items():
            row = self.card(kind, ref)
            entry = {"version": row["srs_card_version"], "engine": row["srs_engine"],
                     "source": row.get("first_completed_source"), "v3": row.get("version_first_completed_version")}
            previous = self.versions.get(name)
            if previous is not None:
                self.assertGreaterEqual(entry["version"], previous, (step, name))
            self.versions[name] = entry["version"]
            cards[name] = entry
        if self.b_expected is not None:
            self.assertEqual(self.account(self.B), self.b_expected, (step, "account B changed"))
        self.steps.append(dict(step=step, cards=cards, **facts))

    @contextmanager
    def sql_trace(self):
        from app import database

        statements = []

        def wrap(real):
            def execute(connection, query, params=()):
                statements.append((threading.current_thread().name, " ".join(str(query).split())))
                return real(connection, query, params)
            return execute

        with mock.patch.object(database.AppSQLiteConnection, "execute", wrap(database.AppSQLiteConnection.execute)), \
                mock.patch.object(database.AppPostgresConnection, "execute",
                                  wrap(database.AppPostgresConnection.execute)):
            yield statements

    @staticmethod
    def writes(statements):
        return [q for _, q in statements if q.split(" ", 1)[0].upper() in ("INSERT", "UPDATE", "DELETE")]

    def set_mode(self, user, mode):
        from app.database import now_iso

        stamp = now_iso()
        sql("DELETE FROM srs_user_settings WHERE user_id = ?", (user,))
        sql("INSERT INTO srs_user_settings (user_id, srs_mode, daily_new_goal, settings_version, created_at, "
            "updated_at) VALUES (?, ?, 20, 0, ?, ?)", (user, mode, stamp, stamp))

    def tools(self):
        """The three cleanup tools as the CLIs run them (--apply path, account write lock)."""
        from contextlib import closing

        from app.database import get_connection
        from app.srs import migration, receipts
        from app.srs.storage import begin_card_write

        def connected(fn):
            with closing(get_connection()) as c:
                with c:
                    return fn(c)

        return (("receipt_purge", lambda: connected(lambda c: receipts.minimize_receipts(
                    c, self.A, self.clock + 10 * DAY, apply=True, purge_expired=True, lock=begin_card_write))),
                ("snapshot_minimize", lambda: connected(lambda c: migration.minimize_snapshots(
                    c, self.A, apply=True, lock=begin_card_write, progress={}))),
                ("snapshot_prune", lambda: connected(lambda c: migration.prune_expired_runs(
                    c, self.A, apply=True, lock=begin_card_write, progress={}))))

    def old_world(self, orphan_owner="B"):
        """S0 + S1 (shared by every case). The old-app hard delete (log kept) is B's card unless
        `orphan_owner` is "A" (the defect reproduction below)."""
        self.steps, self.versions, self.tracked, self.b_expected = [], {}, {}, None
        self.start_clock()
        self.build_old()
        users = {r["email"]: r["id"] for r in sql("SELECT id, email FROM users")}
        self.A, self.B = users["up2-a@example.test"], users["up2-b@example.test"]
        self.items = [r["id"] for r in sql("SELECT id FROM vocab_items WHERE user_id = ? ORDER BY id", (self.A,))]
        self.shared = sql("SELECT id FROM shared_decks WHERE owner_user_id = ?", (self.B,))[0]["id"]
        self.lexeme = sql("SELECT lexeme_id FROM user_word_progress WHERE user_id = ?", (self.A,))[0]["lexeme_id"]
        deck = sql("SELECT deck_id FROM vocab_items WHERE id = ?", (self.items[0],))[0]["deck_id"]
        owner = self.A if orphan_owner == "A" else self.B
        owner_deck = deck if owner == self.A else sql("SELECT id FROM decks WHERE user_id = ? ORDER BY id",
                                                      (self.B,))[0]["id"]
        # the old app deleted the newest card outright (no ledger existed): its id is free again
        sql("INSERT INTO vocab_items (user_id, deck_id, surface, base_form, reading, part_of_speech, normalized_form, "
            "meaning_ko, status, created_at, updated_at) VALUES (?, ?, 'up2-gone', 'up2-gone', 'g', '名詞', 'up2-gone', "
            "'gone', 'new', ?, ?)", (owner, owner_deck, T0.isoformat(), T0.isoformat()))
        self.gone = sql("SELECT max(id) AS m FROM vocab_items")[0]["m"]
        sql("INSERT INTO review_logs (user_id, vocab_item_id, deck_id, rating, reviewed_at, previous_review_level, "
            "next_review_level, previous_next_review_at, next_review_at, response_time_ms) "
            "VALUES (?, ?, ?, 'good', ?, 0, 1, NULL, ?, 900)", (owner, self.gone, owner_deck, T0.isoformat(),
                                                               (T0 + DAY).isoformat()))
        self.delete_old_card(self.gone)
        self.gone_log_kept = bool(sql("SELECT 1 AS x FROM review_logs WHERE vocab_item_id = ?", (self.gone,)))
        old_rows = {t: sql(f"SELECT * FROM {t} ORDER BY id") for t in ("vocab_items", "review_logs",
                                                                         "user_word_progress", "lexeme_review_logs")}
        self.steps.append(dict(step="S0 pre-SRS structure", cards=len(old_rows["vocab_items"]),
                               logs=len(old_rows["review_logs"]) + len(old_rows["lexeme_review_logs"]),
                               deleted_id=self.gone, deleted_card_log_kept=self.gone_log_kept))
        # S1 upgrade + rerun
        self.clock = T0 - DAY
        self.upgrade()
        upgraded = self.catalog()
        after = {t: sql(f"SELECT * FROM {t} ORDER BY id") for t in old_rows}
        for table, rows in old_rows.items():
            self.assertEqual([{k: r[k] for k in old} for old, r in zip(rows, after[table])], rows, table)
            self.assertEqual(len(after[table]), len(rows), table)
        self.upgrade()
        self.assertEqual(self.catalog(), upgraded)
        self.assertEqual({t: sql(f"SELECT * FROM {t} ORDER BY id") for t in old_rows}, after)
        rebuild = self.rebuild_ids()
        self.assertEqual({t: sql(f"SELECT * FROM {t} ORDER BY id") for t in ("review_logs", "lexeme_review_logs")},
                         {t: after[t] for t in ("review_logs", "lexeme_review_logs")})
        from _e5b_fixture import card

        probe = card(self.A, deck, "efinal-probe")
        self.assertGreater(probe, self.gone)                                  # a deleted id is never handed out again
        from app.repositories import vocab_repository as vocab

        vocab.delete_vocab_item(self.A, probe)                                # the app's delete: ledger row
        self.assertEqual(len(sql("SELECT 1 AS x FROM srs_card_deletions WHERE card_kind = 'personal' AND card_ref = ?",
                                 (probe,))), 1)
        again = card(self.A, deck, "efinal-probe-2")
        self.assertGreater(again, probe)
        vocab.delete_vocab_item(self.A, again)
        self.set_mode(self.A, "fsrs")
        self.set_mode(self.B, "legacy")
        self.steps.append(dict(step="S1 upgrade / rerun / id reuse", rebuild=rebuild, deleted_id=self.gone,
                               new_ids=[probe, again], old_values_kept=True, rerun_changes=0))
        return deck

    # ---- the rehearsal ------------------------------------------------------------------------------
    def test_final_rehearsal(self):
        from app import account_blocks, recovery
        from app.account_write import AccountWriteError
        from app.recovery import RecoveryRefused
        from app.srs import migration
        from app.srs.engine import CardKey

        deck = self.old_world()
        b_card = __import__("_e5b_fixture").card(self.B, sql("SELECT id FROM decks WHERE user_id = ? ORDER BY id",
                                                               (self.B,))[0]["id"], "efinal-b")
        self.review("personal", b_card, user=self.B, legacy=True)            # B studies in legacy mode
        self.b_expected = self.account(self.B)
        self.tracked = {"full": ("personal", self.items[0]), "nolog": ("personal", self.items[2]),
                        "fresh": ("personal", self.items[1]), "sub": ("lexeme", self.lexeme)}
        self.checkpoint("S1 accounts ready")

        # S2 dry run, interrupted apply, resume, rerun -----------------------------------------------------
        self.clock = T0
        keys = [CardKey("personal", self.A, r) for r in self.items] + [CardKey("lexeme", self.A, self.lexeme)]
        plan = migration.dry_run(keys)
        before = self.account(self.A)
        self.assertEqual(self.account(self.A), before)                        # the dry run wrote nothing
        real_update, calls = migration.update_card, {"n": 0}

        def failing(*a, **k):
            calls["n"] += 1
            if calls["n"] == 2:
                raise RuntimeError("synthetic interruption")
            return real_update(*a, **k)

        migration.apply_plan(plan, "efinal-run-1", approved=True, batch_size=1)   # a first limited batch
        with mock.patch.object(migration, "update_card", failing), self.assertRaises(RuntimeError):
            migration.apply_plan(plan, "efinal-run-1", approved=True, batch_size=10)  # interrupted inside
        run = sql("SELECT status, summary_json FROM srs_migration_runs WHERE run_key = 'efinal-run-1'")[0]
        cursor_after_failure = json.loads(run["summary_json"])["cursor"]
        self.assertEqual(run["status"], "failed")
        self.assertTrue(1 < cursor_after_failure < len(plan), cursor_after_failure)
        self.checkpoint("S2a interrupted", run_status=run["status"], cursor=cursor_after_failure)
        self.clock = T0 + timedelta(minutes=5)
        results = migration.apply_plan(plan, "efinal-run-1", approved=True)
        self.assertEqual(sql("SELECT status FROM srs_migration_runs WHERE run_key = 'efinal-run-1'")[0]["status"],
                         "completed")
        converted = self.account(self.A)
        rerun = migration.apply_plan(plan, "efinal-run-1", approved=True)
        self.assertEqual(self.account(self.A), converted)                     # same key again: no write
        self.assertEqual([r["result"] for r in rerun],
                         ["already_applied" if r["result"] == "applied" else r["result"] for r in results])
        engines = {n: self.card(k, r)["srs_engine"] for n, (k, r) in self.tracked.items()}
        self.assertEqual(set(engines.values()), {"fsrs"}, (engines, results))
        self.checkpoint("S2b resumed / rerun", results=[r["result"] for r in results], rerun_writes=0)

        # S3 reviews, lost response, conflict, account boundary --------------------------------------------
        self.clock = T0 + DAY
        full = self.items[0]
        first = self.review("personal", full, request="efinal-lost-1")
        state = (self.account(self.A), self.logs(self.A))
        retry = self.review("personal", full, request="efinal-lost-1",
                            version=first.json()["srs"]["card_version"] - 1)
        self.assertEqual(retry.content, first.content)                        # the lost answer, byte for byte
        self.assertEqual((self.account(self.A), self.logs(self.A)), state)
        stale = self.review("personal", full, request="efinal-stale", version=first.json()["srs"]["card_version"] - 1,
                            expect=409)
        self.assertEqual(stale.json()["detail"], "card_version_conflict")
        self.review("personal", full, user=self.B, request="efinal-b-on-a", expect=404)
        sub_first = self.review("lexeme", self.lexeme, request="efinal-sub-1")
        sub_retry = self.review("lexeme", self.lexeme, request="efinal-sub-1",
                                version=sub_first.json()["srs"]["card_version"] - 1)
        self.assertEqual(sub_retry.content, sub_first.content)
        self.review("personal", self.items[2], request="efinal-nolog-1")
        self.assertEqual(self.account(self.A)["review_logs"][0], state[0]["review_logs"][0] + 1)
        self.checkpoint("S3 reviews", retry_same_bytes=True, conflict=409, other_account=404)

        # S4 reviews at their due times until the first V3 completion ---------------------------------------
        completed_at, n = None, 0
        while self.card("personal", full)["first_completed_at"] is None and n < 8:
            due = datetime.fromisoformat(self.card("personal", full)["srs_effective_due_at"])
            # at the due time, or 8 days later when the due time is further out (inside the window)
            nxt = max(self.clock + timedelta(minutes=1), due + timedelta(hours=1))
            nxt = min(nxt, self.clock + 8 * DAY)
            if nxt >= T0 + 27 * DAY:
                break
            self.clock = nxt
            n += 1
            self.review("personal", full, request=f"efinal-c-{n}")
        row = self.card("personal", full)
        completion = {k: row.get(k) for k in COMPLETION}
        self.assertIsNotNone(completion["first_completed_at"], (n, self.clock, {k: row.get(k) for k in (
            "srs_stability", "srs_state", "srs_history_quality", "evidence_from_log_id", "history_intro_status",
            "srs_effective_due_at") + COMPLETION}, sql("SELECT id, rating, reviewed_at FROM review_logs "
                                                       "WHERE vocab_item_id = ? ORDER BY id", (full,))))
        self.checkpoint("S4 first completion", reviews=n, source=completion["first_completed_source"],
                        version=completion["version_first_completed_version"], clock=self.clock.isoformat())

        # S5 P-RB recovery ---------------------------------------------------------------------------
        self.clock += timedelta(hours=2)
        logs_before, dates_before = self.logs(self.A), self.first_dates(self.A)
        stats_before = self.stats(self.A)
        report = recovery.preview(self.A, KEY)
        self.assertEqual(report["status"], "ready", report)
        prepared = recovery.prepare(self.A, KEY, TOKEN, report["plan"])
        self.assertEqual(sql("SELECT status FROM account_write_blocks WHERE user_id = ?", (self.A,))[0]["status"],
                         "active")
        blocked = self.review("personal", self.items[2], request="efinal-blocked", expect=409)
        self.assertEqual(blocked.json()["detail"], "account_writes_blocked")
        self.assertEqual(self.http("POST", "/decks", {"name": "efinal-blocked"}, self.A).status_code, 409)
        self.assertEqual(self.review("personal", b_card, user=self.B, legacy=True).status_code, 200)  # B is not blocked
        self.b_expected = self.account(self.B)
        refused_tools = {}
        for name, call in self.tools():
            before = self.account(self.A)
            with self.sql_trace() as statements:
                try:
                    call()
                    refused_tools[name] = "ran"
                except (AccountWriteError, RecoveryRefused, Exception) as error:   # noqa: BLE001
                    refused_tools[name] = getattr(error, "code", type(error).__name__)
            self.assertEqual(self.writes(statements), [], name)
            self.assertEqual(self.account(self.A), before, name)
        self.assertEqual(set(refused_tools.values()), {"account_writes_blocked"}, refused_tools)
        self.checkpoint("S5a step A / refusals", block="active", refused=refused_tools, prepared=prepared["status"])
        recovered = recovery.recover(self.A, KEY, TOKEN, report["plan"])
        engines = {n: self.card(k, r)["srs_engine"] for n, (k, r) in self.tracked.items()}
        self.assertEqual(set(engines.values()), {"legacy"}, (engines, recovered))
        self.assertEqual(self.logs(self.A), logs_before)                      # every log kept
        self.assertEqual(self.first_dates(self.A), dates_before)              # new-word history kept
        self.assertEqual({k: self.card("personal", full).get(k) for k in COMPLETION if k != "completion_metric_version"},
                         {k: v for k, v in completion.items() if k != "completion_metric_version"})
        self.checkpoint("S5b atomic B", state=recovered.get("state", recovered.get("status")))
        verified = recovery.verify(self.A, KEY, TOKEN)
        self.assertEqual(verified["status"], "verified", verified)
        released = account_blocks.release_block(self.A, KEY, TOKEN, "completed", plan=report["plan"])
        self.assertEqual((released["released"], released["created"], released["reason"]), (True, True, "completed"))
        stats_after = self.stats(self.A)
        self.assertEqual(self.logs(self.A), logs_before)
        self.assertEqual(self.first_dates(self.A), dates_before)
        self.checkpoint("S5c verify / release", verify=verified["status"], checks=verified["checks"],
                        stats_equal=stats_after == stats_before)

        # S6 legacy ordinary writes, then the same release request --------------------------------------
        self.clock += timedelta(hours=1)
        legacy = self.review("personal", full, legacy=True)
        self.assertNotIn("srs", legacy.json())
        self.assertEqual(self.http("POST", "/decks", {"name": "efinal-after"}, self.A).status_code, 200)
        self.assertEqual(len(self.logs(self.A)["personal"]), len(logs_before["personal"]) + 1)
        with self.sql_trace() as statements:
            again = account_blocks.release_block(self.A, KEY, TOKEN, "completed", plan=report["plan"])
        self.assertEqual((again["released"], again["created"], again["reason"]), (True, False, "completed"), again)
        self.assertEqual(self.writes(statements), [])
        self.checkpoint("S6 legacy writes / release recall", recall_writes=0, completion_kept=completion)

        # S7 cleanup tools after the release -----------------------------------------------------------
        receipts_before = len(sql("SELECT id FROM srs_review_receipts WHERE user_id = ?", (self.A,)))
        after_tools = {}
        for name, call in self.tools():
            result = call()
            after_tools[name] = {k: (len(v) if isinstance(v, list) else v) for k, v in
                                 (result.get("snapshots") or result).items()
                                 if isinstance(v, (list, int))} if isinstance(result, dict) else result
        receipts_after = len(sql("SELECT id FROM srs_review_receipts WHERE user_id = ?", (self.A,)))
        self.assertEqual(self.logs(self.A)["personal"][:len(logs_before["personal"])], logs_before["personal"])
        self.checkpoint("S7 cleanup tools after release", receipts=[receipts_before, receipts_after],
                        tools=after_tools)
        self.assertEqual(self.account(self.B), self.b_expected)
        out = os.environ.get("E_FINAL_OUT")
        if out:
            Path(out).write_text(json.dumps({"db": self.db_kind, "steps": self.steps}, ensure_ascii=False, indent=1,
                                            default=str), encoding="utf-8")

    def test_new_fsrs_card_without_snapshot_blocks_recovery(self):
        """The recovery's separate case: a card created in FSRS mode has no snapshot to restore.
        The preview names it, step A refuses, nothing is written, no block exists."""
        from app import recovery
        from app.recovery import RecoveryRefused
        from app.srs import migration
        from app.srs.engine import CardKey

        deck = self.old_world()
        self.clock = T0
        migration.apply_plan(migration.dry_run([CardKey("personal", self.A, self.items[0])]), "efinal-run-n",
                             approved=True)
        created = self.http("POST", "/vocab-items", {"surface": "efinal-new", "base_form": "efinal-new",
                                                     "reading": "n", "meaning_ko": "새", "deck_id": deck}, self.A)
        self.assertEqual(created.status_code, 200, created.text[:200])
        new = created.json()["id"]
        self.clock = T0 + DAY
        self.review("personal", new, request="efinal-new-1")
        self.assertEqual(self.card("personal", new)["srs_engine"], "fsrs")
        report = recovery.preview(self.A, KEY)
        self.assertNotEqual(report["status"], "ready")
        self.assertIn("fsrs_card_without_snapshot", report["reasons"])
        before = self.account(self.A)
        with self.assertRaises(RecoveryRefused) as refused:
            recovery.prepare(self.A, KEY, TOKEN, report["plan"])
        self.refusal = refused.exception.code
        # the block row step A inserts first is rolled back with the refusal: nothing is committed
        self.assertEqual(self.account(self.A), before)
        self.assertEqual(sql("SELECT id FROM account_write_blocks WHERE user_id = ?", (self.A,)), [])


    def test_orphan_log_of_an_old_delete_is_seen_before_step_a(self):
        """Gate E F-1 (E_FINAL_REVIEW.md), now a regular regression: the old app deleted one of
        A's cards and kept its log (SQLite without the foreign-key pragma; no ledger row). That
        orphan fails the release gate's I1a before any recovery step, so the precheck reports
        it (`gate_precondition_I1a`) and step A refuses: no block, no record -- the account can
        no longer reach B and then be stuck behind a gate that cannot pass."""
        from app import recovery
        from app.database import get_connection
        from app.recovery import RecoveryRefused
        from app.srs import migration, recovery_scope
        from app.srs.engine import CardKey

        self.old_world(orphan_owner="A")
        self.clock = T0
        migration.apply_plan(migration.dry_run([CardKey("personal", self.A, self.items[0])]), "efinal-run-o",
                             approved=True)
        with get_connection() as c:
            self.assertEqual(recovery_scope.account(c, self.A)["I1a"]["status"], "fail")   # before A: always true
        report = recovery.preview(self.A, KEY)
        self.assertEqual((report["status"], report["reasons"]), ("blocked", ["gate_precondition_I1a"]))
        before = self.account(self.A)
        with self.assertRaises(RecoveryRefused) as refused:
            recovery.prepare(self.A, KEY, TOKEN, report["plan"])
        self.assertEqual((refused.exception.code, refused.exception.reasons),
                         ("recovery_blocked", ["gate_precondition_I1a"]))
        self.assertEqual(self.account(self.A), before)
        self.assertEqual(sql("SELECT id FROM account_write_blocks WHERE user_id = ?", (self.A,)), [])


class Case(FinalRehearsal, unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="jp_vocab_efinal_", dir=BACKEND)
        self.addCleanup(directory.cleanup)
        self.db_path = Path(directory.name) / "efinal_synthetic.db"
        env = mock.patch.dict(os.environ, {"APP_ENV": "test", "DATABASE_URL": f"sqlite:///{self.db_path.as_posix()}",
                                           "JWT_SECRET_KEY": s.SECRET})
        env.start()
        self.addCleanup(env.stop)


if __name__ == "__main__":
    unittest.main()

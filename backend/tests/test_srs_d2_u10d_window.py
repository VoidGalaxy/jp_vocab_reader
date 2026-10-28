"""Gate D-2 U10-d: the rollback window (logical expiry, A3' approved 2026-10-16).

An apply run can be rolled back, or resumed under the same key, for 30x24 hours from
its first `started_at`; exactly at the end it is closed. A missing / unreadable /
zone-less / future start is 'unverifiable'. Both refuse before any write. A completed
same-key call still returns its stored results without writing. Nothing changes a
run's status or times to mark expiry, and nothing is deleted.

The server clock seen by migration (`migration.now_utc`) is controlled by the test.
Synthetic SQLite only (QueueCase sets a throwaway DATABASE_URL per test before the
app touches a database).

Run directly:      python tests/test_srs_d2_u10d_window.py
Or via discovery:   python -m unittest discover -s tests
"""

from __future__ import annotations

import json
import sys
import threading
import time
import unittest
from datetime import timedelta, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_srs_d2_u10_value_shape import ValueShapeCase  # noqa: E402
from test_srs_queue import NOW, iso  # noqa: E402
import race_support  # noqa: E402

from app.database import get_connection  # noqa: E402
from app.repositories import vocab_repository  # noqa: E402
from app.srs import migration, reviews, storage  # noqa: E402
from app.srs.engine import CardKey  # noqa: E402
from app.srs.storage import SrsWriteError  # noqa: E402

DAY = timedelta(days=1)
WINDOW = timedelta(hours=30 * 24)
TICK = timedelta(microseconds=1)
T0 = NOW


class WindowCase(ValueShapeCase):
    def setUp(self):
        super().setUp()
        self.clock = T0
        self.ticks = []  # optional queue of instants, one per migration.now_utc() call
        patch = mock.patch.object(migration, "now_utc", side_effect=self._now)
        patch.start()
        self.addCleanup(patch.stop)
        self._order = 0

    def _now(self):
        return self.ticks.pop(0) if self.ticks else self.clock

    # -- helpers ---------------------------------------------------------------------
    def card(self, kind, name):
        self.clock = T0
        if kind == "personal":
            return self.converted("personal", name), None
        self._order += 1
        deck = getattr(self, "_deck", None) or self.shared_deck("window")
        self._deck = deck
        return self.converted("lexeme", name, deck, self._order), deck

    def run_row(self, run_key):
        with get_connection() as c:
            return dict(c.execute("SELECT * FROM srs_migration_runs WHERE run_key = ?", (run_key,)).fetchone())

    def set_started(self, run_key, value):
        with get_connection() as c:
            c.execute("UPDATE srs_migration_runs SET started_at = ? WHERE run_key = ?", (value, run_key))

    def refused(self, code, call):
        before = self.everything()
        with self.assertRaises(SrsWriteError) as caught:
            call()
        self.assertEqual(caught.exception.code, code)
        self.assertEqual(self.everything(), before)  # no run, record, card or log change

    def three(self, prefix):
        return [self.content_card(f"{prefix}{i}") for i in range(3)]

    def plan_of(self, refs):
        return migration.dry_run([self.key("personal", r) for r in refs])


# ---------------------------------------------------------------------------
class JudgementTests(unittest.TestCase):
    def test_boundaries_and_spellings(self):
        start = iso(T0)
        self.assertEqual(migration.rollback_window(start, T0), "open")
        self.assertEqual(migration.rollback_window(start, T0 + WINDOW - TICK), "open")
        self.assertEqual(migration.rollback_window(start, T0 + WINDOW), "expired")
        self.assertEqual(migration.rollback_window(start, T0 + WINDOW + TICK), "expired")
        for spelling in (T0.isoformat().replace("+00:00", "Z"), T0.astimezone(timezone(timedelta(hours=9))).isoformat(),
                         T0.astimezone(timezone(timedelta(hours=-5))).isoformat()):
            with self.subTest(spelling=spelling):
                self.assertEqual(migration.rollback_window(spelling, T0 + WINDOW - TICK), "open")
                self.assertEqual(migration.rollback_window(spelling, T0 + WINDOW), "expired")

    def test_unverifiable_starts(self):
        for value in (None, "", "not-a-time", "2026-10-09T03:00:00", "2026-10-09", 12345, "x" * 500,
                      iso(T0 + TICK)):
            with self.subTest(value=str(value)[:30]):
                self.assertEqual(migration.rollback_window(value, T0), "unverifiable")


# ---------------------------------------------------------------------------
class RollbackWindowTests(WindowCase):
    def check_boundary(self, kind):
        ok, _ = self.card(kind, f"ok-{kind}")
        self.clock = T0 + WINDOW - TICK
        self.assertEqual(self.rollback(kind, ok)[0]["result"], "rolled_back")
        for offset in (timedelta(0), timedelta(seconds=1)):
            ref, _ = self.card(kind, f"late-{kind}-{offset.seconds}")
            self.clock = T0 + WINDOW + offset
            source = self.first_run(kind, ref)
            run = self.run_row(source)
            self.refused("rollback_window_closed",
                         lambda: migration.rollback_plan(source, f"rb-late-{kind}-{offset.seconds}", user_id=self.user,
                                                         approved=True))
            self.assertEqual(self.run_row(source), run)  # status and times untouched

    def test_personal(self):
        self.check_boundary("personal")

    def test_subscribed(self):
        self.check_boundary("lexeme")

    def test_same_instant_in_other_offsets(self):
        for name, shift in (("z", None), ("plus9", 9), ("minus5", -5)):
            for at, ok in ((T0 + WINDOW - TICK, True), (T0 + WINDOW, False)):
                with self.subTest(spelling=name, ok=ok):
                    ref, _ = self.card("personal", f"{name}-{ok}")
                    source = self.first_run("personal", ref)
                    text = (T0.isoformat().replace("+00:00", "Z") if shift is None
                            else T0.astimezone(timezone(timedelta(hours=shift))).isoformat())
                    self.set_started(source, text)
                    self.clock = at
                    call = lambda: migration.rollback_plan(source, f"rb-{name}-{ok}", user_id=self.user, approved=True)  # noqa: E731
                    if ok:
                        self.assertEqual(call()[0]["result"], "rolled_back")
                    else:
                        self.refused("rollback_window_closed", call)

    def test_unverifiable_start_refuses(self):
        for i, value in enumerate(("", "garbage", "2026-10-09T03:00:00", iso(T0 + 2 * DAY))):
            with self.subTest(value=value):
                ref, _ = self.card("personal", f"unv{i}")
                source = self.first_run("personal", ref)
                self.set_started(source, value)
                self.clock = T0 + DAY
                self.refused("rollback_window_unverifiable",
                             lambda: migration.rollback_plan(source, f"rb-unv{i}", user_id=self.user, approved=True))

    def test_completed_same_key_returns_stored_result_after_expiry(self):
        ref, _ = self.card("personal", "done")
        source = self.first_run("personal", ref)
        self.clock = T0 + DAY
        first = migration.rollback_plan(source, "rb-done", user_id=self.user, approved=True)
        self.clock = T0 + 40 * DAY
        before = self.everything()
        self.assertEqual(migration.rollback_plan(source, "rb-done", user_id=self.user, approved=True), first)
        self.assertEqual(self.everything(), before)
        # another request reusing the key is still a conflict, in or out of the window
        other, _ = self.card("personal", "other")
        for at in (T0 + DAY, T0 + 40 * DAY):
            self.clock = at
            self.refused("migration_run_conflict", lambda: migration.rollback_plan(
                self.first_run("personal", other), "rb-done", user_id=self.user, approved=True))

    def test_source_status_does_not_extend_or_matter(self):
        for status in ("completed", "started", "failed", "aborted"):
            with self.subTest(status=status):
                ref, _ = self.card("personal", f"st-{status}")
                source = self.first_run("personal", ref)
                with get_connection() as c:
                    c.execute("UPDATE srs_migration_runs SET status = ?, finished_at = ? WHERE run_key = ?",
                              (status, iso(T0 + 29 * DAY), source))  # a late finish never extends
                self.clock = T0 + WINDOW
                self.refused("rollback_window_closed", lambda: migration.rollback_plan(
                    source, f"rb-st-{status}", user_id=self.user, approved=True))
                self.clock = T0 + WINDOW - TICK
                self.assertEqual(migration.rollback_plan(source, f"rb-st-{status}", user_id=self.user,
                                                         approved=True)[0]["result"], "rolled_back")

    def test_other_account_and_run_unaffected(self):
        expired, _ = self.card("personal", "mine-old")
        self.set_mode(self.other, "fsrs")
        theirs = self.personal("theirs", user=self.other)
        with get_connection() as c:
            c.execute("UPDATE vocab_items SET last_reviewed_at = ?, correct_count = 2, next_review_at = ? WHERE id = ?",
                      (iso(NOW - 9 * DAY), iso(NOW - timedelta(hours=1)), theirs))
        self.clock = T0 + 20 * DAY
        migration.apply_plan(migration.dry_run([CardKey("personal", self.other, theirs)]), "run-theirs", approved=True)
        fresh = self.content_card("mine-new")
        self.apply(fresh, run="run-mine-new")
        self.clock = T0 + WINDOW + DAY
        self.refused("rollback_window_closed", lambda: migration.rollback_plan(
            self.first_run("personal", expired), "rb-old", user_id=self.user, approved=True))
        self.assertEqual(migration.rollback_plan("run-theirs", "rb-theirs", user_id=self.other,
                                                 approved=True)[0]["result"], "rolled_back")
        self.assertEqual(migration.rollback_plan("run-mine-new", "rb-new", user_id=self.user,
                                                 approved=True)[0]["result"], "rolled_back")


class RollbackWindowFormat1Tests(RollbackWindowTests):
    FORMAT1 = True


# ---------------------------------------------------------------------------
class ResumeTests(WindowCase):
    def partial(self, prefix, key):
        refs = self.three(prefix)
        plan = self.plan_of(refs)
        self.clock = T0
        self.assertEqual(migration.apply_plan(plan, key, approved=True, batch_size=1)[0]["result"], "applied")
        self.assertEqual((self.run_row(key)["status"], json.loads(self.run_row(key)["summary_json"])["cursor"]),
                         ("started", 1))
        return refs, plan

    def test_started_resume_boundary(self):
        refs, plan = self.partial("s", "run-s")
        self.clock = T0 + WINDOW - TICK
        self.assertEqual(migration.apply_plan(plan, "run-s", approved=True, batch_size=1)[-1]["result"], "applied")
        self.clock = T0 + WINDOW
        with race_support.LockProbe() as probe:
            self.refused("migration_resume_window_closed",
                         lambda: migration.apply_plan(plan, "run-s", approved=True, batch_size=1))
        # refused in the run-check transaction, before any card unit takes the lock
        self.assertEqual([e for e in probe.events if e[0] == "acquired"], [("acquired", "MainThread")])
        self.assertEqual(json.loads(self.run_row("run-s")["summary_json"])["cursor"], 2)
        self.assertEqual(self.run_row("run-s")["status"], "started")
        # the operator moves the rest with a new plan and a new key
        rest = self.plan_of(refs[2:])
        self.assertEqual(migration.apply_plan(rest, "run-s-rest", approved=True)[0]["result"], "applied")

    def test_failed_resume(self):
        refs = self.three("f")
        plan = self.plan_of(refs)
        real, calls = migration.update_card, {"n": 0}

        def failing(*a, **k):
            calls["n"] += 1
            if calls["n"] == 2:
                raise RuntimeError("synthetic")
            return real(*a, **k)

        with mock.patch.object(migration, "update_card", failing), self.assertRaises(RuntimeError):
            migration.apply_plan(plan, "run-f", approved=True, batch_size=3)
        self.assertEqual(self.run_row("run-f")["status"], "failed")
        self.clock = T0 + WINDOW + DAY
        self.refused("migration_resume_window_closed", lambda: migration.apply_plan(plan, "run-f", approved=True))
        self.assertEqual(self.card_row("personal", refs[0])["srs_engine"], "fsrs")  # committed card kept
        self.clock = T0 + DAY
        self.assertEqual([r["result"] for r in migration.apply_plan(plan, "run-f", approved=True)],
                         ["already_applied", "applied", "applied"])

    def test_unverifiable_resume(self):
        refs, plan = self.partial("u", "run-u")
        self.set_started("run-u", "2026-10-09T03:00:00")
        self.clock = T0 + DAY
        self.refused("migration_resume_window_unverifiable",
                     lambda: migration.apply_plan(plan, "run-u", approved=True, batch_size=1))

    def test_completed_and_nothing_left_return_stored_results(self):
        refs = self.three("c")
        plan = self.plan_of(refs)
        migration.apply_plan(plan, "run-c", approved=True)
        self.clock = T0 + DAY
        inside = migration.apply_plan(plan, "run-c", approved=True)
        self.clock = T0 + 90 * DAY
        before = self.everything()
        self.assertEqual(migration.apply_plan(plan, "run-c", approved=True), inside)
        self.assertEqual(self.everything(), before)
        with get_connection() as c:  # all cards committed but not marked completed
            c.execute("UPDATE srs_migration_runs SET status = 'started' WHERE run_key = 'run-c'")
        before = self.everything()
        self.assertEqual(migration.apply_plan(plan, "run-c", approved=True), inside)
        self.assertEqual(self.everything(), before)
        other = self.plan_of(self.three("c2"))
        self.refused("migration_run_conflict", lambda: migration.apply_plan(other, "run-c", approved=True))

    def test_aborted_keeps_its_error(self):
        refs, plan = self.partial("a", "run-a")
        with get_connection() as c:
            c.execute("UPDATE srs_migration_runs SET status = 'aborted' WHERE run_key = 'run-a'")
        for at in (T0 + DAY, T0 + WINDOW):
            self.clock = at
            self.refused("migration_run_closed", lambda: migration.apply_plan(plan, "run-a", approved=True))

    def test_expiry_between_cards_stops_later_writes_only(self):
        refs = self.three("b")
        plan = self.plan_of(refs)
        # server instants: run created (started_at), card 1 unit, card 2 unit (closed)
        self.ticks = [T0, T0 + WINDOW - TICK, T0 + WINDOW]
        with self.assertRaises(SrsWriteError) as caught:
            migration.apply_plan(plan, "run-b", approved=True, batch_size=3)
        self.assertEqual(self.ticks, [])
        self.assertEqual(caught.exception.code, "migration_resume_window_closed")
        self.assertEqual([self.card_row("personal", r)["srs_engine"] for r in refs], ["fsrs", "legacy", "legacy"])
        run = self.run_row("run-b")
        self.assertEqual((run["status"], json.loads(run["summary_json"])["cursor"], run["finished_at"]),
                         ("started", 1, None))  # not marked failed, earlier card not undone
        self.assertEqual(len(self.records("personal", refs[0])), 1)
        self.assertEqual(self.records("personal", refs[1]), [])


class ResumeFormat1Tests(ResumeTests):
    FORMAT1 = True


# ---------------------------------------------------------------------------
class RaceTests(WindowCase):
    def hold_lock(self, release):
        def run():
            with get_connection() as connection:
                storage.begin_card_write(connection, self.user)
                self.assertTrue(release.wait(15))
                self.probe.mark("released")
            return "held"
        return run

    def expires_while_waiting(self, call, code):
        release = threading.Event()
        self.clock = T0 + WINDOW - TICK  # open when the call starts
        with race_support.LockProbe() as self.probe:
            holder = race_support.start("holder", self.hold_lock(release))
            self.assertTrue(self.probe.wait("acquired", "holder"))
            before = self.everything_unlocked()
            waiter = race_support.start("waiter", call)
            self.assertTrue(self.probe.wait("waiting", "waiter"))
            time.sleep(0.3)
            self.assertNotIn(("acquired", "waiter"), self.probe.events)
            self.clock = T0 + WINDOW  # the window closes while it waits
            release.set()
            race_support.finish(self, holder)
            error = race_support.finish_error(self, waiter, SrsWriteError, code)
        self.probe.assert_serialized(self, "holder", "waiter")
        self.assertEqual(self.everything(), before)
        return error

    def everything_unlocked(self):
        # read through a separate connection while another holds the write lock (reads are allowed)
        return self.everything()

    def test_rollback_expires_during_lock_wait(self):
        ref, _ = self.card("personal", "wait-rb")
        source = self.first_run("personal", ref)
        self.expires_while_waiting(
            lambda: migration.rollback_plan(source, "rb-wait", user_id=self.user, approved=True), "rollback_window_closed")

    def test_resume_expires_during_lock_wait(self):
        refs = self.three("w")
        plan = self.plan_of(refs)
        migration.apply_plan(plan, "run-w", approved=True, batch_size=1)
        self.expires_while_waiting(lambda: migration.apply_plan(plan, "run-w", approved=True), "migration_resume_window_closed")

    def overlap(self, first, second, jobs, block):
        entered, release = threading.Event(), threading.Event()
        target, name = block
        real = getattr(target, name)

        def slow(*a, **k):
            result = real(*a, **k)
            if threading.current_thread().name == first and not entered.is_set():
                entered.set()
                self.assertTrue(release.wait(15))
            return result

        with race_support.LockProbe() as probe, mock.patch.object(target, name, slow):
            a = race_support.start(first, jobs[first])
            self.assertTrue(entered.wait(15))
            b = race_support.start(second, jobs[second])
            self.assertTrue(probe.wait("waiting", second))
            time.sleep(0.3)
            self.assertNotIn(("acquired", second), probe.events)
            probe.mark("released", first)
            release.set()
            outcomes = {}
            for name_, task in ((first, a), (second, b)):
                task.thread.join(race_support.JOIN_TIMEOUT)
                self.assertFalse(task.thread.is_alive())
                outcomes[name_] = task
        probe.assert_serialized(self, first, second)
        return outcomes

    def review_job(self, ref, at):
        version = self.card_row("personal", ref)["srs_card_version"]

        def run():
            with mock.patch.object(reviews, "now_utc", return_value=at):
                return vocab_repository.record_review(self.user, ref, "good", request_id=f"race-{ref}",
                                                      expected_card_version=version, session_id="s1")
        return run

    def test_expired_rollback_and_review_overlap(self):
        for first in ("rollback", "review"):
            with self.subTest(first=first):
                ref, _ = self.card("personal", f"ov-{first}")
                source = self.first_run("personal", ref)
                self.clock = T0 + WINDOW
                logs = len(self.logs_of("personal", ref))
                jobs = {"rollback": lambda: migration.rollback_plan(source, f"rb-ov-{first}", user_id=self.user,
                                                                    approved=True),
                        "review": self.review_job(ref, T0 + 31 * DAY)}
                block = (reviews, "introduced_on") if first == "review" else (migration, "_run_id")
                tasks = self.overlap(first, "review" if first == "rollback" else "rollback", jobs, block)
                self.assertIsInstance(tasks["rollback"].box.get("error"), SrsWriteError)
                self.assertEqual(tasks["rollback"].box.get("error").code, "rollback_window_closed")
                self.assertIsNone(tasks["review"].box.get("error"))
                self.assertEqual(len(self.logs_of("personal", ref)), logs + 1)
                self.assertEqual(self.card_row("personal", ref)["srs_engine"], "fsrs")
                with get_connection() as c:
                    self.assertIsNone(c.execute("SELECT 1 FROM srs_migration_runs WHERE run_key = ?",
                                                (f"rb-ov-{first}",)).fetchone())

    def test_open_rollback_and_other_card_review_overlap(self):
        for first in ("rollback", "review"):
            with self.subTest(first=first):
                ref, _ = self.card("personal", f"op-{first}")
                other, _ = self.card("personal", f"op-other-{first}")
                source = self.first_run("personal", ref)
                self.clock = T0 + WINDOW - TICK
                jobs = {"rollback": lambda: migration.rollback_plan(source, f"rb-op-{first}", user_id=self.user,
                                                                    approved=True),
                        "review": self.review_job(other, T0 + 29 * DAY)}
                block = (reviews, "introduced_on") if first == "review" else (migration, "_run_id")
                tasks = self.overlap(first, "review" if first == "rollback" else "rollback", jobs, block)
                self.assertIsNone(tasks["rollback"].box.get("error"))
                self.assertEqual(tasks["rollback"].box["value"][0]["result"], "rolled_back")
                self.assertIsNone(tasks["review"].box.get("error"))


# ---------------------------------------------------------------------------
class PreservedTests(WindowCase):
    def test_old_restore_proof_and_first_completion(self):
        ref, _ = self.card_with_records("old")  # converted, reviewed, rolled back at T0 (+ review clock)
        completed = self.card_row("personal", ref)["first_completed_at"]
        self.clock = T0 + 120 * DAY  # long after the source window
        self.assertEqual(self.reconvert("personal", ref)[2]["reconversion"], "restored")
        self.assertEqual(self.card_row("personal", ref)["first_completed_at"], completed)
        self.rate_at("personal", ref, NOW + 121 * DAY, "good")
        self.rate_at("personal", ref, NOW + 130 * DAY, "good")
        self.now = NOW
        self.assertTrue(self.seen[-1][1])  # version-gap proof still holds

    def test_delayed_plan_b_first_review(self):
        ref, boundary, run, at = self.to_plan_b("personal", name="old-b")
        restart = self.payload(self.records("personal", ref)[-1])["restart"]
        self.clock = T0 + 200 * DAY
        self.rate_at("personal", ref, at + 150 * DAY, "good")
        self.now = NOW
        self.assertEqual(self.card_row("personal", ref)["srs_engine"], "fsrs")
        self.assertEqual(self.payload([r for r in self.records("personal", ref) if r["mode"] == "apply"][-1])["restart"],
                         restart)  # the permission record is kept, not discarded

    def test_nothing_is_deleted_by_expiry(self):
        ref, _ = self.card("personal", "keep")
        before = self.everything()
        self.clock = T0 + 365 * DAY
        self.refused("rollback_window_closed", lambda: migration.rollback_plan(
            self.first_run("personal", ref), "rb-keep", user_id=self.user, approved=True))
        self.assertEqual(self.everything(), before)


if __name__ == "__main__":
    unittest.main()

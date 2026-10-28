"""Gate E-2b P-REV3 / P-DEL2 / identity: real overlapping transactions on the protected
local PostgreSQL test database, each judged two ways:

1. the overlap itself is PROVEN (E-3 Overlap): the first job is paused inside its
   transaction right after taking the account write lock; the second job's backend is seen
   holding a not-granted lock while pg_blocking_pids() names the first job's backend; both
   jobs end (bounded waits), every outcome -- value or exception -- is kept per job;
2. the result equals the SAME two calls run one after the other on SQLite, with the same
   synthetic accounts, cards, ratings, request ids and frozen clock: job outcomes and the
   final card / log / receipt / ledger / snapshot / flag rows, normalized only by the E-2
   labels (ids -> names). A timeout, deadlock or other exception is never an accepted
   conflict: it is a different outcome and fails the comparison.

Cases: same request_id twice; two request_ids from one card version; two cards of one
account; identity flag vs review (both orders); migration apply vs word delete (both orders).
Test code only. Real PostgreSQL only with the harness opt-in.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import _srs_e2_compare as cmp  # noqa: E402
from test_srs_e3_fk_real import Overlap, RealCase, _opt_in, judge_overlap  # noqa: E402

HOUR, DAY = timedelta(hours=1), timedelta(days=1)


def outcome(sc, entry):
    """A job's result in comparable form; an exception keeps its type and code."""
    if entry is None:
        return ("missing",)
    if entry[0] == "ok":
        return ("ok", sc.n(entry[1]))
    error = entry[1]
    return ("error", type(error).__name__, getattr(error, "code", None), getattr(error, "status_code", None))


class Setup:
    """The synthetic account and cards, built the same way on both databases."""

    def __init__(self, sc, kind):
        self.sc, self.kind = sc, kind
        sc.clock = cmp.T0 - 60 * DAY
        self.user = sc.user("rc")
        if kind == "migration":
            sc.set_mode(self.user, "legacy")
            self.refs = {label: sc.card(self.user, label) for label in ("m1", "m2")}
            for label, days in (("m1", 50), ("m1", 40), ("m2", 45)):
                sc.clock = cmp.T0 - days * DAY
                assert sc.review(self.user, self.refs[label], "good", legacy=True)["status"] == 200
            sc.clock = cmp.T0
            sc.set_mode(self.user, "fsrs")
        else:
            sc.set_mode(self.user, "fsrs")
            self.refs = {label: sc.card(self.user, label) for label in ("c1", "c2")}
            sc.clock = cmp.T0 + HOUR
            for ref in self.refs.values():
                assert sc.review(self.user, ref, "good")["status"] == 200
            sc.clock = cmp.T0 + 2 * DAY

    # ---- jobs (inputs fixed when built, before either job runs) -----------------
    def review(self, label, request):
        from app.repositories import vocab_repository

        ref, version = self.refs[label], self.sc.version(self.refs[label])
        return lambda: vocab_repository.record_review(self.user, ref, "good", request_id=request,
                                                      expected_card_version=version, session_id="e2b")

    def delete(self, label):
        from app.repositories import vocab_repository

        ref = self.refs[label]
        return lambda: vocab_repository.delete_vocab_item(self.user, ref)

    def flag(self, label):
        from app.database import get_connection
        from app.srs import identity

        ref = self.refs[label]

        def job():
            with get_connection() as connection:
                return identity.flag_identity_unknown(connection, [identity.IdentityFinding(self.user, ref,
                                                                                            ["e2b_synthetic"])])
        return job

    def apply(self):
        from app.srs import migration
        from app.srs.engine import CardKey

        plan = migration.dry_run([CardKey("personal", self.user, self.refs[label]) for label in ("m1", "m2")])
        return lambda: migration.apply_plan(plan, "e2b-run", approved=True)

    # ---- the final state ---------------------------------------------------------
    def state(self):
        sc = self.sc
        for r in sc.sql("SELECT id, run_key FROM srs_migration_runs ORDER BY id"):
            sc.labels.put("run", r["id"], r["run_key"], owner="rc")
        out = {label: {"card": sc.card_view(ref), "logs": sc.log_view(ref)} for label, ref in self.refs.items()}
        out["receipts"] = sc.n(sc.sql(
            "SELECT user_id, request_id, card_kind, card_ref, request_hash, response_json, review_log_id, created_at "
            "FROM srs_review_receipts ORDER BY request_id"))
        out["ledger"] = sc.n(sc.sql("SELECT card_kind, user_id, card_ref, deleted_at, history_intro_status, "
                                    "history_intro_known_by FROM srs_card_deletions ORDER BY card_ref"))
        out["flags"] = sc.n(sc.sql("SELECT user_id, card_kind, card_ref, reasons, detected_at "
                                   "FROM srs_card_identity_flags ORDER BY card_ref"))
        out["runs"] = sc.n(sc.sql("SELECT run_key, mode, status, summary_json, started_at, finished_at "
                                  "FROM srs_migration_runs ORDER BY run_key"))
        out["snapshots"] = sc.n(sc.sql(
            "SELECT run_id, user_id, card_kind, card_ref, card_version_before, legacy_json, srs_before_json, "
            "srs_after_json, history_quality, history_flags, created_at FROM srs_migration_snapshots "
            "ORDER BY card_ref"))
        return out


# name -> (setup kind, (first job, second job), pause (module name, function, on_call))
CASES = {
    "same request_id twice": ("review", lambda s: (s.review("c1", "same"), s.review("c1", "same")),
                              ("storage", "begin_card_write", 1)),
    "two request_ids, one card version": ("review", lambda s: (s.review("c1", "ra"), s.review("c1", "rb")),
                                          ("storage", "begin_card_write", 1)),
    "two cards of one account": ("review", lambda s: (s.review("c1", "ra"), s.review("c2", "rb")),
                                 ("storage", "begin_card_write", 1)),
    "identity flag, then review": ("review", lambda s: (s.flag("c1"), s.review("c1", "ra")),
                                   ("storage", "begin_card_write", 1)),
    "review, then identity flag": ("review", lambda s: (s.review("c1", "ra"), s.flag("c1")),
                                   ("storage", "begin_card_write", 1)),
    # apply: call 1 opens the run, call 2 is card m1's transaction (lock held, not yet written)
    "migration apply, then delete": ("migration", lambda s: (s.apply(), s.delete("m1")),
                                     ("migration", "begin_card_write", 2)),
    "delete, then migration apply": ("migration", lambda s: (s.delete("m1"), s.apply()),
                                     ("storage", "begin_card_write", 1)),
}


def _module(name):
    from app.srs import migration, storage

    return {"storage": storage, "migration": migration}[name]


@unittest.skipUnless(_opt_in(), "Real PostgreSQL E-2b race checks NOT RUN (opt-in not set)")
class E2bRaceTests(RealCase):
    def sqlite_serial(self, name):
        kind, jobs, _ = CASES[name]
        directory = tempfile.TemporaryDirectory(prefix="jp_vocab_e2b_", dir=Path(__file__).resolve().parents[1])
        self.addCleanup(directory.cleanup)
        url = f"sqlite:///{(Path(directory.name) / 'race.db').as_posix()}"
        import app.database as database

        with mock.patch.dict(os.environ, {"DATABASE_URL": url}):
            database.init_db()
            with cmp.Scenario("sqlite") as sc:
                s = Setup(sc, kind)
                first, second = jobs(s)
                box = {}
                for slot, job in (("first", first), ("second", second)):
                    try:
                        box[slot] = ("ok", job())
                    except Exception as error:  # noqa: BLE001 -- kept as the outcome
                        box[slot] = ("error", error)
                return {"first": outcome(sc, box["first"]), "second": outcome(sc, box["second"]),
                        "state": s.state()}

    def pg_overlapped(self, name):
        kind, jobs, (module, function, on_call) = CASES[name]
        self.run.reset(restart_identity=True)
        with cmp.Scenario("postgresql", self.run) as sc:
            s = Setup(sc, kind)
            first, second = jobs(s)
            box = Overlap(self, _module(module), function, on_call=on_call).run(first, second)
            judge_overlap(box)
            return box, {"first": outcome(sc, box.get("first")), "second": outcome(sc, box.get("second")),
                         "state": s.state()}

    def test_cases(self):
        self.create()
        record = {}
        for name in CASES:
            with self.subTest(name):
                expected = self.sqlite_serial(name)
                box, actual = self.pg_overlapped(name)
                record[name] = {"waits": box.get("second_waits"), "pids": box.get("pids"),
                                "first": actual["first"][:1] + actual["first"][2:3],
                                "second": actual["second"][:1] + actual["second"][2:3]}
                differences = cmp.compare(expected, actual)
                self.assertEqual(differences, [], name)
        # one line per case for the report: who waited on whom, and the two outcomes
        for name, entry in record.items():
            print(f"E2B-RACE {name}: first={entry['first']} second={entry['second']} "
                  f"pids={entry['pids']} waits={[(w['locktype'], w['mode']) for w in entry['waits'] or []]}")


if __name__ == "__main__":
    unittest.main()

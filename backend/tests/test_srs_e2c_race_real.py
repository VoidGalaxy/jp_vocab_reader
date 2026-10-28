"""Gate E-2c: receipt purge (U9, 7-day expiry) against a retry of the expired request, on REAL
PostgreSQL, both orders -- the one tool race whose existing SQLite test cannot show a database
wait (it releases right after its in-process probe; see REPORT 17).

Judged as in test_srs_e2b_race_real: the first job is paused inside its transaction just
after taking the account write lock; the second job's backend is seen waiting on the first
job's backend (pg_locks / pg_blocking_pids); both end within bounded waits; the job outcomes
and the final card / log / receipt rows equal the SAME two calls run one after the other on
SQLite (same synthetic account, card, request ids and frozen clock; E-2 labels only).
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
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import _srs_e2_compare as cmp  # noqa: E402
from test_srs_e2b_race_real import outcome  # noqa: E402
from test_srs_e3_fk_real import Overlap, RealCase, _opt_in, judge_overlap  # noqa: E402

DAY, HOUR = timedelta(days=1), timedelta(hours=1)


class ExpiredReceipt:
    def __init__(self, sc):
        self.sc = sc
        sc.clock = cmp.T0
        self.user = sc.user("purge")
        sc.set_mode(self.user, "fsrs")
        self.card = sc.card(self.user, "p1")
        sc.clock = cmp.T0 + HOUR
        first = sc.review(self.user, self.card, "good", request="purge-1", version=0)
        assert first["status"] == 200, first
        sc.sql("UPDATE srs_review_receipts SET created_at = ? WHERE request_id = 'purge-1'",
               ((cmp.T0 + HOUR - 30 * DAY).isoformat(),))
        sc.clock = cmp.T0 + 2 * DAY

    def retry(self):
        from app.repositories import vocab_repository

        return lambda: vocab_repository.record_review(self.user, self.card, "good", request_id="purge-1",
                                                      expected_card_version=0, session_id="e2a")

    def purge(self):
        from app.database import get_connection
        from app.srs import receipts, storage
        from app.srs.engine import to_utc

        def job():
            with get_connection() as connection:
                return receipts.minimize_receipts(connection, self.user, to_utc(self.sc.clock), apply=True,
                                                  purge_expired=True, lock=lambda c, u: storage.begin_card_write(c, u))
        return job

    def state(self):
        sc = self.sc
        return {"card": sc.card_view(self.card), "logs": sc.log_view(self.card),
                "receipts": sc.n(sc.sql("SELECT user_id, request_id, card_kind, card_ref, request_hash, response_json, "
                                        "review_log_id, created_at FROM srs_review_receipts ORDER BY request_id"))}


ORDERS = {"retry first": ("retry", "purge"), "purge first": ("purge", "retry")}


def _report(sc, entry):
    """The purge report holds ids; they are compared as counts per list (ids differ by engine
    only through the labels, which receipts have none of)."""
    if entry and entry[0] == "ok" and isinstance(entry[1], dict):
        report = {k: (len(v) if isinstance(v, list) else v) for k, v in entry[1].items() if k != "cursor"}
        report["user_id"] = sc.labels.name("user", report["user_id"])   # the E-2 label, as for every id
        return ("ok", report)
    return outcome(sc, entry)


@unittest.skipUnless(_opt_in(), "Real PostgreSQL E-2c race checks NOT RUN (opt-in not set)")
class PurgeAgainstExpiredRetry(RealCase):
    def sqlite_serial(self, order):
        import app.database as database

        directory = tempfile.TemporaryDirectory(prefix="jp_vocab_e2c_", dir=Path(__file__).resolve().parents[1])
        self.addCleanup(directory.cleanup)
        url = f"sqlite:///{(Path(directory.name) / 'race.db').as_posix()}"
        with mock.patch.dict(os.environ, {"DATABASE_URL": url}):
            database.init_db()
            with cmp.Scenario("sqlite") as sc:
                fixture = ExpiredReceipt(sc)
                jobs = {"retry": fixture.retry(), "purge": fixture.purge()}
                box = {}
                for slot, name in zip(("first", "second"), ORDERS[order]):
                    try:
                        box[slot] = ("ok", jobs[name]())
                    except Exception as error:  # noqa: BLE001 -- kept as the outcome
                        box[slot] = ("error", error)
                return {"first": _report(sc, box["first"]), "second": _report(sc, box["second"]),
                        "state": fixture.state()}

    def pg_overlapped(self, order):
        from app.srs import storage

        self.run.reset(restart_identity=True)
        with cmp.Scenario("postgresql", self.run) as sc:
            fixture = ExpiredReceipt(sc)
            jobs = {"retry": fixture.retry(), "purge": fixture.purge()}
            first, second = (jobs[name] for name in ORDERS[order])
            box = Overlap(self, storage, "begin_card_write").run(first, second)
            judge_overlap(box)
            return box, {"first": _report(sc, box.get("first")), "second": _report(sc, box.get("second")),
                         "state": fixture.state()}

    def test_both_orders(self):
        self.create()
        for order in ORDERS:
            with self.subTest(order):
                expected = self.sqlite_serial(order)
                box, actual = self.pg_overlapped(order)
                self.assertEqual(cmp.compare(expected, actual), [], order)
                retry = actual["first"] if order == "retry first" else actual["second"]
                purge = actual["second"] if order == "retry first" else actual["first"]
                self.assertEqual(retry[0], "error")                       # an expired receipt is never replayed
                self.assertEqual(purge[1]["purged"], 1)
                self.assertEqual(actual["state"]["receipts"], [])
                print(f"E2C-RACE purge/expired retry, {order}: waits="
                      f"{[(w['locktype'], w['mode']) for w in box.get('second_waits') or []]} pids={box.get('pids')}")


if __name__ == "__main__":
    unittest.main()

"""Opt-in E-1 checks against the protected real local PostgreSQL database."""

import os
import threading
import time
import unittest

from _srs_pg_harness import PgRun, UnsafePostgresTarget, requested


def _requested():
    try:
        return requested(os.environ) is not None
    except UnsafePostgresTarget:
        return True


@unittest.skipUnless(_requested(), "Real local PostgreSQL checks not requested")
class RealPostgresHarnessTests(unittest.TestCase):
    def test_owned_oid_and_transaction_xmin(self):
        run = PgRun(requested(os.environ))
        run.start()
        try:
            observed = {}

            def create(connection):
                connection.execute("CREATE TABLE public.e1_real_owned (id BIGSERIAL PRIMARY KEY, value TEXT)")
                observed["xid"] = connection.execute(
                    "SELECT (txid_current() % 4294967296)::text"
                ).fetchone()[0]
                observed["oid"], observed["xmin"] = connection.execute(
                    "SELECT oid::bigint, xmin::text FROM pg_class WHERE oid='public.e1_real_owned'::regclass"
                ).fetchone()

            run.track_creation(create, expected={"e1_real_owned"})
            self.assertEqual(observed["xid"], observed["xmin"])
            self.assertEqual(run.owned_oids, {"e1_real_owned": observed["oid"]})
            run.verify()
            run.reset(restart_identity=True)
            self.assertEqual(run.owned_oids["e1_real_owned"], observed["oid"])
        finally:
            run.teardown()

    def test_creation_failure_rolls_back_real_ddl(self):
        run = PgRun(requested(os.environ))
        run.start()
        try:
            def fail(connection):
                connection.execute("CREATE TABLE public.e1_real_rolled_back (id INTEGER)")
                raise RuntimeError("synthetic creation failure")

            with self.assertRaisesRegex(RuntimeError, "synthetic creation failure"):
                run.track_creation(fail, expected={"e1_real_rolled_back"})
            self.assertEqual(run.owned_oids, {})
            with run._connection() as connection:
                run.verify_app_connection(connection)
                self.assertIsNone(connection.execute(
                    "SELECT to_regclass('public.e1_real_rolled_back')"
                ).fetchone()[0])
                connection.rollback()
            run.verify()
        finally:
            run.teardown()

    def test_cleanup_waits_on_actual_postgres_lock(self):
        for operation in ("reset", "teardown"):
            with self.subTest(operation=operation):
                run = PgRun(requested(os.environ))
                run.start()
                worker = None
                results = []
                try:
                    run.track_creation(
                        lambda connection: connection.execute(
                            "CREATE TABLE public.e1_real_locked (id INTEGER)"
                        ), expected={"e1_real_locked"},
                    )
                    oid = run.owned_oids["e1_real_locked"]
                    with run._connection() as blocker:
                        run.verify_app_connection(blocker)
                        blocker.execute("INSERT INTO public.e1_real_locked VALUES (1)")
                        blocker.commit()
                        blocker.execute("LOCK TABLE public.e1_real_locked IN ACCESS SHARE MODE")

                        def cleanup():
                            try:
                                getattr(run, operation)()
                            except BaseException as error:
                                results.append(error)
                            else:
                                results.append("committed")

                        worker = threading.Thread(target=cleanup, daemon=True)
                        worker.start()
                        try:
                            deadline = time.monotonic() + 4
                            waiting = False
                            while time.monotonic() < deadline:
                                waiting = blocker.execute(
                                    "SELECT EXISTS (SELECT 1 FROM pg_locks WHERE relation=%s "
                                    "AND mode='AccessExclusiveLock' AND NOT granted)", (oid,),
                                ).fetchone()[0]
                                if waiting:
                                    break
                                if results:
                                    self.fail("cleanup finished before the blocking lock was released")
                                time.sleep(0.01)
                            self.assertTrue(waiting, "real pg_locks did not show the cleanup waiter")
                            self.assertEqual(results, [])
                        finally:
                            blocker.rollback()
                    worker.join(10)
                    self.assertFalse(worker.is_alive(), "cleanup worker did not terminate")
                    self.assertEqual(results, ["committed"])
                    if operation == "reset":
                        run.verify()
                        with run._connection() as connection:
                            run.verify_app_connection(connection)
                            self.assertEqual(connection.execute(
                                "SELECT count(*) FROM public.e1_real_locked"
                            ).fetchone()[0], 0)
                            self.assertEqual(connection.execute(
                                "SELECT 'public.e1_real_locked'::regclass::oid::bigint"
                            ).fetchone()[0], oid)
                            connection.rollback()
                finally:
                    if worker is not None and worker.is_alive():
                        worker.join(10)
                    run.teardown()


if __name__ == "__main__":
    unittest.main()

"""E-D13 review regressions without database connections."""

import threading
import unittest
from unittest import mock

from app import database
from app.srs import schema
from test_srs_e13_init_ddl_real import DdlRecorder


class IndexDefinitionTests(unittest.TestCase):
    def state(self, **changes):
        row = dict(kind="i", on_target=True, valid=True, ready=True, is_unique=False,
                   no_expressions=True, no_predicate=True, method="btree",
                   columns=["user_id", "srs_engine", "srs_participation", "srs_effective_due_at"],
                   key_count=4, attribute_count=4, default_order=True,
                   default_opclasses=True, column_collations=True)
        row.update(changes)
        connection = mock.Mock()
        connection.execute.side_effect = [mock.Mock(fetchone=lambda: {"present": True}),
                                          mock.Mock(fetchall=lambda: [row])]
        return schema._pg_index_state(connection, "queue_idx", "vocab_items", row["columns"], False)

    def test_default_search_keys_are_accepted(self):
        self.assertEqual(self.state(), "ok")

    def test_include_columns_cannot_replace_search_keys(self):
        with self.assertRaisesRegex(schema.SchemaUpgradeError, "index_definition_mismatch"):
            self.state(key_count=2)

    def test_nondefault_key_options_are_rejected(self):
        for field in ("default_order", "default_opclasses", "column_collations"):
            with self.subTest(field=field), self.assertRaisesRegex(
                    schema.SchemaUpgradeError, "index_definition_mismatch"):
                self.state(**{field: False})


class DdlRecorderTests(unittest.TestCase):
    def test_parallel_workers_keep_separate_thread_and_connection_records(self):
        original = database.AppPostgresConnection.execute
        barrier = threading.Barrier(2, timeout=5)
        first_done = threading.Event()
        connections, errors = {}, []
        lock = threading.Lock()

        def worker(number):
            try:
                raw = mock.Mock()
                connection = database.AppPostgresConnection(raw)
                with lock:
                    connections[number] = (connection, raw)
                barrier.wait()
                if number == 1 and not first_done.wait(5):
                    raise TimeoutError("first worker did not finish")
                connection.execute(f"SELECT {number}")
                connection.execute(f"ALTER TABLE probe_{number} ADD COLUMN sample INTEGER")
            except BaseException as error:
                with lock:
                    errors.append(error)
            finally:
                if number == 0:
                    first_done.set()

        threads = [threading.Thread(target=worker, args=(n,), daemon=True) for n in range(2)]
        with DdlRecorder() as recorder:
            try:
                for thread in threads:
                    thread.start()
            finally:
                for thread in threads:
                    thread.join(6)
            self.assertFalse(any(thread.is_alive() for thread in threads))
            self.assertEqual(errors, [])
        self.assertIs(database.AppPostgresConnection.execute, original)
        self.assertEqual(len(recorder.statements), 4)
        self.assertEqual(len(recorder.ddl), 2)
        for number, thread in enumerate(threads):
            connection, raw = connections[number]
            expected = [f"ALTER TABLE probe_{number} ADD COLUMN sample INTEGER"]
            self.assertEqual(recorder.ddl_for(thread=thread), expected)
            self.assertEqual(recorder.ddl_for(connection=connection), expected)
            self.assertEqual(len(recorder.statements_for(thread=thread, connection=connection)), 2)
            self.assertEqual(raw.execute.call_count, 2)

    def test_overlapping_recorders_are_rejected_without_breaking_active_one(self):
        original = database.AppPostgresConnection.execute
        try:
            with DdlRecorder() as recorder:
                active = database.AppPostgresConnection.execute
                with self.assertRaisesRegex(RuntimeError, "recorder.*active"):
                    with DdlRecorder():
                        pass
                self.assertIs(database.AppPostgresConnection.execute, active)
                connection = database.AppPostgresConnection(mock.Mock())
                connection.execute("ALTER TABLE probe ADD COLUMN sample INTEGER")
            self.assertEqual(recorder.ddl, ["ALTER TABLE probe ADD COLUMN sample INTEGER"])
            self.assertIs(database.AppPostgresConnection.execute, original)
        finally:
            database.AppPostgresConnection.execute = original

    def test_exception_restores_method_and_allows_next_recorder(self):
        original = database.AppPostgresConnection.execute
        with self.assertRaisesRegex(RuntimeError, "synthetic worker failure"):
            with DdlRecorder() as recorder:
                database.AppPostgresConnection(mock.Mock()).execute("DROP INDEX probe_index")
                raise RuntimeError("synthetic worker failure")
        self.assertEqual(recorder.ddl, ["DROP INDEX probe_index"])
        self.assertIs(database.AppPostgresConnection.execute, original)
        with DdlRecorder() as next_recorder:
            self.assertEqual(next_recorder.statements, [])
        self.assertIs(database.AppPostgresConnection.execute, original)

    def test_worker_failure_does_not_end_another_workers_recording(self):
        original = database.AppPostgresConnection.execute
        failed = threading.Event()
        results = {}
        lock = threading.Lock()

        def worker(number):
            try:
                if number == 0:
                    raise RuntimeError("synthetic first worker failure")
                if not failed.wait(5):
                    raise TimeoutError("first worker did not finish")
                database.AppPostgresConnection(mock.Mock()).execute("DROP INDEX second_worker_probe")
                outcome = "ok"
            except BaseException as error:
                outcome = type(error).__name__
            with lock:
                results[number] = outcome
            if number == 0:
                failed.set()

        threads = [threading.Thread(target=worker, args=(n,), daemon=True) for n in range(2)]
        with DdlRecorder() as recorder:
            try:
                for thread in threads:
                    thread.start()
            finally:
                for thread in threads:
                    thread.join(6)
            self.assertFalse(any(thread.is_alive() for thread in threads))
            self.assertEqual(results, {0: "RuntimeError", 1: "ok"})
            self.assertEqual(recorder.ddl_for(thread=threads[0]), [])
            self.assertEqual(recorder.ddl_for(thread=threads[1]), ["DROP INDEX second_worker_probe"])
        self.assertIs(database.AppPostgresConnection.execute, original)


if __name__ == "__main__":
    unittest.main()

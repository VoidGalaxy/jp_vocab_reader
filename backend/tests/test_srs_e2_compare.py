"""Gate E-2a: tests for the comparison scenario (tests/_srs_e2_compare.py) and the
test-only connection adapter (tests/_srs_e2_adapter.py).

- Normalization: ids become logical labels, times / JSON / bools are written one way,
  and real differences (order, versions, counts, statuses, completion) are NOT hidden.
- SQLite: the whole scenario on two session-only synthetic SQLite files, the second with
  shifted ids, must observe the same thing (the comparison does not depend on id numbers).
- Adapter: fake connections only (psycopg.connect is blocked) -- connection, transaction,
  commit / rollback / close boundaries, second-connection refusal, failures, restoration.
- PostgreSQL comparison: only with the harness opt-in. Otherwise skipped = NOT RUN.
  Nothing here is a PostgreSQL result (PostgreSQL stays unverified and a release blocker).

Run directly:      python tests/test_srs_e2_compare.py
"""

from __future__ import annotations

import ast
import inspect
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

TESTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS_DIR))
sys.path.insert(0, str(TESTS_DIR.parent))
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import app.database as database  # noqa: E402
from app.srs import schema as srs_schema  # noqa: E402

import _srs_e2_adapter as adapter  # noqa: E402
import _srs_e2_compare as compare_mod  # noqa: E402
import _srs_pg_harness as harness  # noqa: E402
from _srs_e2_compare import Labels, compare, normalize  # noqa: E402
NotComparable = getattr(compare_mod, "NotComparable", AssertionError)  # E-2a review contract
from test_srs_pg_harness import SECRET, URL, Base, FakeConnection, create  # noqa: E402

SCHEMA_TABLES = {
    "users", "decks", "vocab_items", "custom_terms", "shared_decks", "shared_deck_items", "shared_deck_terms",
    "shared_deck_imports", "lexemes", "shared_deck_words", "user_deck_subscriptions", "user_word_progress",
    "review_logs", "lexeme_review_logs", "meaning_feedback", "app_feedback", "srs_config_versions",
    "srs_user_settings", "srs_review_receipts", "srs_migration_runs", "srs_migration_snapshots",
    "srs_card_deletions", "srs_card_identity_flags", "srs_evidence_restarts", "account_write_blocks", "account_recovery_runs",  # + P-RB
}


class NormalizeTests(unittest.TestCase):
    def labels(self):
        """Registered the way the scenario registers: objects it created, with the
        account that owns them and, for logs, the card they belong to."""
        labels = Labels()
        labels.put("user", 7, "A")
        labels.put("user", 8, "B")
        labels.put("personal", 41, "card-x", owner="A")
        labels.put("personal", 42, "card-y", owner="A")
        labels.put("lexeme", 41, "word-x")  # same number, other kind
        labels.put("log", 900, "card-x#1", owner="A", card=("personal", "card-x"))
        labels.put("log", 901, "card-x#2", owner="A", card=("personal", "card-x"))
        labels.put("log", 902, "card-y#1", owner="A", card=("personal", "card-y"))
        return labels

    def test_ids_become_labels_by_kind_and_reference(self):
        labels = self.labels()
        row = {"card_kind": "personal", "card_id": 41, "user_id": 7, "review_log_id": 900, "rating": "good"}
        self.assertEqual(normalize(row, labels), {"card_kind": "personal", "card_id": "card-x", "user_id": "A",
                                                  "review_log_id": "card-x#1", "rating": "good"})
        self.assertEqual(normalize({"card_kind": "lexeme", "card_id": 41}, labels)["card_id"], "word-x")
        self.assertEqual(normalize({"vocab_item_id": 41, "lexeme_id": 41}, labels),
                         {"vocab_item_id": "card-x", "lexeme_id": "word-x"})

    def test_unregistered_references_are_not_comparable(self):
        # contract change (E-2a review): unknown ids used to become "?<key>#<order>", so two
        # different unknown logs that each appeared first compared equal.
        for value in ({"review_log_id": 501}, {"user_id": 99}, {"card_kind": "personal", "card_id": 77},
                      {"evidence_from_log_id": 503}):
            with self.subTest(value=value), self.assertRaises(NotComparable):
                normalize(value, self.labels())

    def test_wrong_kind_is_not_comparable(self):
        labels = Labels()
        labels.put("lexeme", 41, "word-x")
        with self.assertRaises(NotComparable):
            normalize({"card_kind": "personal", "card_id": 41}, labels)  # only a lexeme has that number
        with self.assertRaises(NotComparable):
            normalize({"card_id": 41}, labels)  # no kind given: never guessed

    def test_other_account_and_other_card_are_not_comparable(self):
        cases = {
            "card of another account": {"card_kind": "personal", "card_id": 41, "user_id": 8},
            "log of another card": {"card_kind": "personal", "card_id": 41, "review_log_id": 902},
            "log of another card (key)": {"kind": "personal", "ref_id": 41, "last_log_id": 902},
            "log of another account": {"user_id": 8, "evidence_from_log_id": 900},
        }
        for name, value in cases.items():
            with self.subTest(name), self.assertRaises(NotComparable):
                normalize(value, self.labels())
        ok = normalize({"kind": "personal", "ref_id": 41, "user_id": 7, "last_log_id": 901}, self.labels())
        self.assertEqual(ok, {"kind": "personal", "ref_id": "card-x", "user_id": "A", "last_log_id": "card-x#2"})

    def test_id_shift_is_equal_and_another_object_is_a_difference(self):
        first, second = Labels(), Labels()
        for labels, base in ((first, 10), (second, 500)):
            labels.put("user", base, "A")
            labels.put("personal", base + 1, "card-x", owner="A")
            labels.put("log", base + 2, "card-x#1", owner="A", card=("personal", "card-x"))
            labels.put("log", base + 3, "card-x#2", owner="A", card=("personal", "card-x"))
        a = normalize({"card_kind": "personal", "card_id": 11, "review_log_id": 12}, first)
        b = normalize({"card_kind": "personal", "card_id": 501, "review_log_id": 502}, second)
        self.assertEqual(compare(a, b), [])
        c = normalize({"card_kind": "personal", "card_id": 501, "review_log_id": 503}, second)
        self.assertEqual(compare(a, c), [("/review_log_id", "card-x#1", "card-x#2")])

    def test_times_json_bools_and_presence_only(self):
        labels = self.labels()
        self.assertEqual(normalize({"at": "2026-06-01T12:00:00+09:00"}, labels),
                         {"at": "2026-06-01T03:00:00.000000+00:00"})
        self.assertEqual(normalize({"at": "2026-06-01T03:00:00"}, labels), {"at": "2026-06-01T03:00:00"})  # naive kept
        self.assertEqual(normalize({"seoul_date": "2026-06-01"}, labels), {"seoul_date": "2026-06-01"})
        self.assertEqual(normalize('{"b": 1, "a": [true, "2026-06-01T03:00:00Z"]}', labels),
                         {"a": [1, "2026-06-01T03:00:00.000000+00:00"], "b": 1})
        self.assertEqual(normalize({"is_active": True}, labels), normalize({"is_active": 1}, labels))
        self.assertEqual(normalize({"card_fingerprint": "abc", "next_cursor": None}, labels),
                         {"card_fingerprint": "<present>", "next_cursor": None})

    def test_real_differences_are_not_hidden(self):
        base = {"queue": ["q1", "q2"], "card": {"srs_card_version": 2, "first_completed_at": None},
                "logs": [1, 2], "status": 200}
        cases = {
            "order": ({"queue": ["q2", "q1"]}, "/queue[0]"),
            "version": ({"card": {"srs_card_version": 3, "first_completed_at": None}}, "/card/srs_card_version"),
            "log count": ({"logs": [1, 2, 3]}, "/logs#len"),
            "permission": ({"status": 404}, "/status"),
            "completion": ({"card": {"srs_card_version": 2, "first_completed_at": "x"}}, "/card/first_completed_at"),
            "type": ({"status": "200"}, "/status"),
        }
        for name, (change, path) in cases.items():
            with self.subTest(name):
                diffs = compare(base, {**base, **change})
                self.assertIn(path, [d[0] for d in diffs])
        self.assertEqual(compare(base, dict(base)), [])

    def test_stage_selection(self):
        self.assertEqual(compare_mod.selected_stages({}), compare_mod.STAGES)
        self.assertEqual(compare_mod.selected_stages({"SRS_E2_STAGES": "review"}), ("upgrade", "review"))
        with self.assertRaises(ValueError):
            compare_mod.selected_stages({"SRS_E2_STAGES": "review,account_delete"})


class SortKeyTests(unittest.TestCase):
    """app/srs/queue.py: sort_key = [bucket, time, kind rank, order in deck, card id]. Only
    the last position is an id."""

    T = "2026-06-01T03:00:00+00:00"

    def item(self, card_id, key, kind="personal", label="q1"):
        labels = Labels()
        labels.put(kind, card_id, label)
        return normalize({"items": [{"card_kind": kind, "card_id": card_id, "sort_key": key}]}, labels)

    def test_same_queue_with_other_ids_is_equal(self):
        # before: an id equal to the bucket number replaced the bucket too
        self.assertEqual(compare(self.item(2, [2, self.T, 0, 0, 2]), self.item(9, [2, self.T, 0, 0, 9])), [])
        self.assertEqual(compare(self.item(0, [1, self.T, 0, 0, 0]), self.item(7, [1, self.T, 0, 0, 7])), [])

    def test_order_values_equal_to_the_id_are_kept(self):
        # before: order 5 / 7 equal to the ids 5 / 7 both became the label and the difference vanished
        diffs = compare(self.item(5, [2, self.T, 1, 5, 5], "lexeme"), self.item(7, [2, self.T, 1, 7, 7], "lexeme"))
        self.assertEqual(diffs, [("/items[0]/sort_key[3]", 5, 7)])

    def test_every_non_id_position_is_compared(self):
        base = [1, self.T, 0, 0, 3]
        for position, value in {0: 2, 1: "2026-06-01T04:00:00+00:00", 3: 4}.items():
            with self.subTest(position=position):
                other = list(base)
                other[position] = value
                self.assertEqual([d[0] for d in compare(self.item(3, base), self.item(3, other))],
                                 [f"/items[0]/sort_key[{position}]"])
        # the kind rank follows the card kind (a rank that disagrees with the kind is a shape
        # error, below); a different kind shows up in both the kind and the rank
        diffs = [d[0] for d in compare(self.item(3, base), self.item(3, [1, self.T, 1, 0, 3], "lexeme"))]
        self.assertEqual(diffs, ["/items[0]/card_kind", "/items[0]/sort_key[2]"])

    def test_unexpected_shapes_are_not_comparable(self):
        bad = {
            "short": [1, self.T, 0, 3],
            "long": [1, self.T, 0, 0, 3, 9],
            "bucket not int": ["1", self.T, 0, 0, 3],
            "time not text": [1, 5, 0, 0, 3],
            "rank of the other kind": [1, self.T, 1, 0, 3],
            "order not int": [1, self.T, 0, "0", 3],
            "last is not the card": [1, self.T, 0, 0, 4],
            "bool id": [1, self.T, 0, 0, True],
            "not a list": "1|t|0|0|3",
        }
        for name, key in bad.items():
            with self.subTest(name), self.assertRaises(NotComparable):
                self.item(3, key)


class SqliteScenarioTests(unittest.TestCase):
    """Session-only synthetic SQLite files in a fresh temp directory (never backend/vocab.db)."""

    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory(prefix="jp_vocab_e2a_", ignore_cleanup_errors=True)
        base = Path(cls.directory.name)
        cls.plain = compare_mod.run_sqlite((base / "plain.db").as_posix())
        cls.shifted = compare_mod.run_sqlite((base / "shifted.db").as_posix(), before=cls.shift_ids)

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    @staticmethod
    def shift_ids():
        """Unrelated rows first, so every id in the second run is different."""
        with database.get_connection() as c:
            for n in range(5):
                c.execute("INSERT INTO users (email, display_name, password_hash, created_at, updated_at) "
                          "VALUES (?, 'pad', 'x', '2020-01-01T00:00:00+00:00', '2020-01-01T00:00:00+00:00')",
                          (f"pad{n}@example.test",))
            for n in range(7):
                c.execute("INSERT INTO vocab_items (surface, base_form, reading, part_of_speech, normalized_form, "
                          "status, created_at, updated_at) VALUES ('p', ?, 'r', '', 'p', 'unknown', "
                          "'2020-01-01T00:00:00+00:00', '2020-01-01T00:00:00+00:00')", (f"pad{n}",))
            c.execute("INSERT INTO review_logs (user_id, vocab_item_id, rating, reviewed_at, previous_review_level, "
                      "next_review_level, next_review_at) VALUES (1, 1, 'good', '2020-01-01T00:00:00+00:00', 0, 1, "
                      "'2020-01-02T00:00:00+00:00')")

    def test_same_observations_with_shifted_ids(self):
        self.assertEqual(compare(self.plain, self.shifted), [])

    def test_every_stage_observed(self):
        self.assertEqual(tuple(self.plain), compare_mod.STAGES)

    def test_scenario_exercises_what_the_check_list_names(self):
        """Not product assertions: only that each stage really reached the behaviour it is
        meant to compare (so an empty comparison cannot pass by observing nothing)."""
        r = self.plain["review"]
        self.assertEqual((r["first"]["status"], r["retry"]["status"], r["retry_same_bytes"]), (200, 200, 1))
        self.assertEqual(r["conflict"]["status"], 409)
        self.assertEqual(r["stale_version"]["status"], 409)
        self.assertEqual(r["legacy_client"]["status"], 422)
        self.assertEqual((r["failure_status"], r["failure_left_no_trace"]), ("raised", 1))
        q = self.plain["queue"]
        self.assertEqual({v["introduced_today_status"] for v in q["introduced"].values()}, {"exact"})
        self.assertEqual([log["seoul_date"] for log in q["logs"]["q1"]] + [log["seoul_date"] for log in q["logs"]["q2"]],
                         ["2026-06-01", "2026-06-02"])
        self.assertTrue(q["queue_plus_144h"]["body"]["items"])
        m = self.plain["migration"]
        self.assertEqual([x["result"] for x in m["apply"]], ["applied", "applied"])
        self.assertEqual([x["result"] for x in m["rollback"]], ["rolled_back", "rolled_back"])
        self.assertEqual([r["run_key"] for r in m["runs"]], ["e2a-run-1", "e2a-rb-1", "e2a-run-2"])
        c = self.plain["completion"]
        self.assertIn("completed", [x["srs"]["completion_status"] for x in c["reviews"]])
        self.assertEqual(self.plain["upgrade"]["second_run_new_tables"], [])

    def test_a_behaviour_change_shows_up(self):
        """The same scenario with one product answer changed must not compare equal."""
        from app.srs import goals

        real = goals.introduction_count

        def off_by_one(*args, **kwargs):
            result = real(*args, **kwargs)
            return type(result)(result.status, (result.count or 0) + 1, result.at_least, result.unreadable_cards)

        with tempfile.TemporaryDirectory(prefix="jp_vocab_e2a_", ignore_cleanup_errors=True) as directory,                 mock.patch.object(goals, "introduction_count", off_by_one):
            changed = compare_mod.run_sqlite((Path(directory) / "changed.db").as_posix(), ("upgrade", "queue"))
        diffs = compare({"queue": self.plain["queue"]}, {"queue": changed["queue"]})
        self.assertIn("/queue/introduced", {d[0].rsplit("/", 2)[0] for d in diffs})

    def test_a_queue_order_change_shows_up_through_the_mapping(self):
        """The label mapping must not hide a change in a non-id sort position."""
        from app.srs import queue

        real = queue._key_json
        with tempfile.TemporaryDirectory(prefix="jp_vocab_e2a_", ignore_cleanup_errors=True) as directory,                 mock.patch.object(queue, "_key_json", lambda key: [*real(key)[:3], real(key)[3] + 1, real(key)[4]]):
            changed = compare_mod.run_sqlite((Path(directory) / "order.db").as_posix(), ("upgrade", "queue"))
        diffs = compare({"queue": self.plain["queue"]}, {"queue": changed["queue"]})
        self.assertTrue(diffs)
        self.assertTrue(all(d[0].endswith("/sort_key[3]") for d in diffs), diffs[:3])

    def test_no_raw_ids_leak_into_card_references(self):
        def walk(value, key=None):
            if isinstance(value, dict):
                for k, v in value.items():
                    yield from walk(v, k)
            elif isinstance(value, list):
                for v in value:
                    yield from walk(v, key)
            elif key in compare_mod.ID_NAMESPACES or key in compare_mod.AMBIGUOUS_ID_KEYS:
                yield key, value
        raw = [(k, v) for k, v in walk(self.plain) if isinstance(v, int) and not isinstance(v, bool)]
        self.assertEqual(raw, [])


class AdapterTests(Base):
    """Fake connections only. psycopg.connect is blocked by Base."""

    def run_(self):
        return harness.PgRun(URL, connect=lambda url, **kw: self.server.connect(url), environ=self.env)

    def assert_restored(self):
        self.assertIs(database.get_connection, self.real_get_connection)
        self.assertIs(database.psycopg, self.real_psycopg)

    def setUp(self):
        super().setUp()
        self.real_get_connection, self.real_psycopg = database.get_connection, database.psycopg

    def test_expected_tables_come_from_the_app_schema_code(self):
        self.assertEqual(adapter.expected_schema_tables(), SCHEMA_TABLES)

    def ddl(self, *names):
        def apply(connection):
            self.assertTrue(database.is_postgres_connection(connection))
            for name in names:
                connection.execute(f"CREATE TABLE public.{name} (id INTEGER)")
        return apply

    def test_app_statements_run_in_the_managed_transaction(self):
        run = self.started()
        calls = self.server.calls
        run.track_creation(adapter.schema_step(self.ddl("users", "decks")), expected={"users", "decks"})
        self.assertEqual(sorted(run.owned), ["decks", "users"])
        self.assertEqual(self.server.calls - calls, 1)  # one connection for the whole step
        creates = [c for c in self.server.committed if c.startswith("CREATE TABLE public.users")]
        self.assertEqual(len(creates), 1)
        self.assert_restored()
        run.teardown()

    def test_app_may_not_end_or_leave_the_transaction(self):
        attempts = {
            "commit": lambda c: c._connection.commit(),
            "rollback": lambda c: c._connection.rollback(),
            "close": lambda c: c.close(),
            "context exit": lambda c: c.__exit__(None, None, None),
            "with block": lambda c: c.__enter__(),
        }
        for name, attempt in attempts.items():
            with self.subTest(name):
                self.fresh()
                run = self.started()

                def apply(connection, attempt=attempt):
                    connection.execute("CREATE TABLE public.users (id INTEGER)")
                    attempt(connection)

                with self.assertRaises(adapter.StepBoundaryViolation):
                    run.track_creation(adapter.schema_step(apply), expected={"users"})
                self.assertEqual(run.owned, [])
                self.assertNotIn("users", self.server.state["tables"])  # rolled back by the harness
                self.assertFalse(any(c.startswith("CREATE TABLE public.users") for c in self.server.committed))
                self.assert_restored()
                run.teardown()
                self.assertEqual(self.server.open, 0)

    def test_no_second_connection_inside_the_step(self):
        attempts = {
            "get_connection": lambda: database.get_connection(),
            "psycopg.connect": lambda: database.psycopg.connect(URL),
        }
        for name, attempt in attempts.items():
            with self.subTest(name):
                self.fresh()
                run = self.started()
                calls = self.server.calls

                def apply(connection, attempt=attempt):
                    attempt()

                with self.assertRaises(adapter.StepBoundaryViolation):
                    run.track_creation(adapter.schema_step(apply), expected=set())
                self.assertEqual(self.server.calls - calls, 1)  # only the harness's own connection
                self.assert_restored()
                run.teardown()

    def test_failure_inside_the_step_keeps_the_owned_scope(self):
        run = self.started()
        run.track_creation(adapter.schema_step(self.ddl("users")), expected={"users"})

        def apply(connection):
            connection.execute("CREATE TABLE public.decks (id INTEGER)")
            raise RuntimeError("schema failed half way")

        seen = {}
        original = FakeConnection.rollback

        def watch(conn):
            seen["row_factory_at_rollback"] = getattr(conn, "row_factory", "absent")
            return original(conn)

        with mock.patch.object(FakeConnection, "rollback", watch), self.assertRaisesRegex(RuntimeError, "half way"):
            run.track_creation(adapter.schema_step(apply), expected={"decks"})
        self.assertEqual(run.owned, ["users"])
        self.assertNotIn("decks", self.server.state["tables"])
        self.assertIsNone(seen["row_factory_at_rollback"])  # harness reads tuples again
        self.assert_restored()
        run.teardown()

    def test_refused_before_connecting(self):
        run = self.started()
        self.env["PGHOSTADDR"] = "203.0.113.5"
        calls = self.server.calls
        with self.assertRaises(harness.HarnessStopped):
            run.track_creation(adapter.schema_step(self.ddl("users")), expected={"users"})
        self.assertEqual(self.server.calls, calls)
        self.assert_restored()

    def test_app_scope_guards_every_app_connection_and_restores(self):
        run = self.started()
        self.env["DATABASE_URL"] = "sqlite:///./keep.db"
        with adapter.app_scope(run):
            self.assertEqual(self.env["DATABASE_URL"], URL)
            calls = self.server.calls
            with mock.patch.object(database, "get_database_url", return_value=URL):
                connection = database.get_connection()
                connection.close()
                self.assertEqual(self.server.calls - calls, 1)
                self.env["PGHOSTADDR"] = "203.0.113.5"
                with self.assertRaises(harness.HarnessStopped):
                    database.get_connection()
                self.assertEqual(self.server.calls - calls, 1)  # refused before connecting
            self.env.pop("PGHOSTADDR")
        self.assertEqual(self.env["DATABASE_URL"], "sqlite:///./keep.db")
        self.assert_restored()

    def test_app_scope_restores_after_an_error(self):
        run = self.started()
        with self.assertRaises(KeyError), adapter.app_scope(run):
            raise KeyError("boom")
        self.assertEqual(self.env["DATABASE_URL"], "sqlite:///./keep.db")
        self.assert_restored()
        run.teardown()

    def test_schema_code_opens_no_connection_and_never_ends_a_transaction(self):
        """Static: every function reachable from ensure_schema inside app.database and
        app.srs.schema -- no get_connection / connect / commit / rollback / close call."""
        modules = {"database": database, "schema": srs_schema}
        functions = {name: obj for mod in modules.values() for name, obj in vars(mod).items()
                     if inspect.isfunction(obj) and obj.__module__ in (database.__name__, srs_schema.__name__)}
        todo, seen, forbidden = ["ensure_schema"], set(), []
        while todo:
            name = todo.pop()
            if name in seen or name not in functions:
                continue
            seen.add(name)
            for node in ast.walk(ast.parse(inspect.getsource(functions[name]).lstrip())):
                if isinstance(node, ast.Call):
                    called = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
                    if called in ("get_connection", "connect", "commit", "rollback", "close"):
                        forbidden.append((name, called))
                    todo.append(called)
        self.assertIn("create_postgres_tables", seen)
        self.assertIn("ensure_srs_schema", seen)
        self.assertEqual(forbidden, [])


class AppConnectionTests(Base):
    """Every app connection is checked on itself (target, marker value and object) before
    the app may use it. Fake connections only."""

    def setUp(self):
        super().setUp()
        self.real_get_connection, self.real_psycopg = database.get_connection, database.psycopg

    def run_(self):
        return harness.PgRun(URL, connect=lambda url, **kw: self.server.connect(url), environ=self.env)

    def app_connect(self, read_only=False):
        with mock.patch.object(database, "get_database_url", return_value=URL):
            return database.get_connection(read_only=read_only)

    def changes(self):
        return {
            "database name": lambda s: setattr(s, "dbname", "jp_vocab_test_other"),
            "address": lambda s: setattr(s, "address", "203.0.113.5"),
            "port": lambda s: setattr(s, "port", 5433),
            "marker value": lambda s: s.state["marker"].__setitem__("rows", ["0" * 32]),
            "marker object": lambda s: s.state.__setitem__("marker", {**s.state["marker"], "oid": 1}),
            "marker missing": lambda s: s.state.__setitem__("marker", None),
            "check error": lambda s: s.fail.__setitem__("SELECT current_database", RuntimeError(f"boom {SECRET}")),
        }

    def test_each_app_connection_is_checked_on_itself(self):
        for name, change in self.changes().items():
            with self.subTest(name):
                self.fresh()
                self.env["DATABASE_URL"] = "sqlite:///./keep.db"
                run = self.run_()
                run.start()
                with adapter.app_scope(run):
                    ok = self.app_connect()  # a first, healthy app connection
                    ok.close()
                    change(self.server)
                    before = len(self.server.connections)
                    with self.assertRaises(harness.HarnessStopped) as ctx:
                        self.app_connect()
                    self.assertEqual(len(self.server.connections), before + 1)  # it did connect ...
                    refused = self.server.connections[-1]
                    self.assertTrue(refused.closed)                           # ... and was closed
                    app_sql = [q for q in refused.log if q not in (harness.TARGET_SQL, harness.READ_MARKER_SQL,
                                                                    getattr(harness, "MARKER_OID_SQL", None))]
                    self.assertEqual(app_sql, [])                             # no app statement ran
                    for leak in (SECRET, URL, "localhost", "boom"):
                        self.assertNotIn(leak, str(ctx.exception))
                self.assertEqual(self.env["DATABASE_URL"], "sqlite:///./keep.db")
                self.assertIs(database.psycopg, self.real_psycopg)

    def test_not_replaced_by_a_check_on_another_connection(self):
        run = self.started()
        with adapter.app_scope(run):
            original = harness.PgRun.verify

            def verify_then_switch(this):
                original(this)
                self.server.dbname = "jp_vocab_test_other"  # changes right after a passing verify()

            with mock.patch.object(harness.PgRun, "verify", verify_then_switch):
                run.verify()
                with self.assertRaises(harness.HarnessStopped):
                    self.app_connect()

    def test_checked_connection_is_clean_for_the_app(self):
        run = self.started()
        with adapter.app_scope(run):
            connection = self.app_connect(read_only=True)  # app's own SET TRANSACTION READ ONLY ran
            raw = connection._connection
            self.assertEqual(raw.tx_settings, ["SET TRANSACTION READ ONLY"])
            connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")  # queue.py does this
            self.assertEqual(connection.execute("SELECT 1").fetchone(), (1,))
            self.assertEqual(self.server.locks, {})  # the check took no lock
            self.assertFalse(hasattr(raw, "row_factory") and raw.row_factory is not None)  # left as the app made it
            connection.close()
            plain = self.app_connect()
            plain.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            plain.close()

    def test_preconnect_checks_still_apply(self):
        run = self.started()
        with adapter.app_scope(run):
            before = len(self.server.connections)
            self.env["PGHOSTADDR"] = "203.0.113.5"
            with self.assertRaises(harness.HarnessStopped):
                self.app_connect()
            self.assertEqual(len(self.server.connections), before)  # refused before connecting
            self.env.pop("PGHOSTADDR")

    def test_schema_step_rules_unchanged(self):
        run = self.started()

        def apply(connection):
            connection.execute("CREATE TABLE public.users (id INTEGER)")
            connection._connection.commit()

        with self.assertRaises(adapter.StepBoundaryViolation):
            run.track_creation(adapter.schema_step(apply), expected={"users"})
        self.assertEqual(run.owned, [])


class AppConnectionHandOverTests(Base):
    """The check's rollback is part of the hand-over: if it fails, the app never gets the
    connection, the close is attempted and the run stops. Fake connections only."""

    def setUp(self):
        super().setUp()
        self.real_get_connection, self.real_psycopg = database.get_connection, database.psycopg
        self.env["DATABASE_URL"] = "sqlite:///./keep.db"

    def run_(self):
        return harness.PgRun(URL, connect=lambda url, **kw: self.server.connect(url), environ=self.env)

    def app_connect(self, read_only=False):
        with mock.patch.object(database, "get_database_url", return_value=URL):
            return database.get_connection(read_only=read_only)

    def refused(self, faults, change=None):
        run = self.started()
        with adapter.app_scope(run):
            if change:
                change(self.server)
            self.server.faults.append(faults)
            with self.assertRaises(harness.HarnessStopped) as ctx:
                self.app_connect(read_only=True)
            connection = self.server.connections[-1]
            self.assertTrue(connection.close_attempted)
            check_sql = (harness.TARGET_SQL, harness.MARKER_OID_SQL, harness.READ_MARKER_SQL)
            self.assertEqual([q for q in connection.log if q not in check_sql], [])  # no app statement
            self.assertTrue(run.stopped)
            before = len(self.server.connections)
            with self.assertRaises(harness.HarnessStopped):
                self.app_connect()  # a stopped run never connects again
            self.assertEqual(len(self.server.connections), before)
            for leak in (SECRET, URL, "localhost", "driver", "boom"):
                self.assertNotIn(leak, str(ctx.exception))
        self.assertEqual(self.env["DATABASE_URL"], "sqlite:///./keep.db")
        self.assertIs(database.psycopg, self.real_psycopg)
        self.assertIs(database.get_connection, self.real_get_connection)
        return str(ctx.exception)

    def test_rollback_failure_after_a_passing_check(self):
        message = self.refused({"rollback": RuntimeError(f"boom driver {SECRET}")})
        self.assertIn("could not end", message)

    def test_check_failure_and_rollback_failure_together(self):
        message = self.refused({"rollback": RuntimeError(f"boom driver {SECRET}")},
                               change=lambda s: setattr(s, "dbname", "jp_vocab_test_other"))
        self.assertIn("could not end", message)

    def test_rollback_and_close_both_fail(self):
        self.refused({"rollback": RuntimeError(f"boom driver {SECRET}"), "close": OSError(f"boom {SECRET}")})

    def test_healthy_hand_over_still_allows_the_app_transaction_settings(self):
        run = self.started()
        with adapter.app_scope(run):
            connection = self.app_connect(read_only=True)
            connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            self.assertEqual(connection._connection.tx_settings, [
                "SET TRANSACTION READ ONLY", "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"])
            connection.close()
            self.server.dbname = "jp_vocab_test_other"  # the target check itself still applies
            with self.assertRaises(harness.HarnessStopped):
                self.app_connect()


class ReferenceTypeTests(unittest.TestCase):
    """Every reference field is an integer id before it becomes a label. Raw strings
    (also ones that equal a label), bools, floats, objects and arrays are not ids; NULL only
    where the field allows it."""

    def labels(self):
        labels = Labels()
        labels.put("user", 7, "A")
        labels.put("deck", 30, "A-default", owner="A")
        labels.put("personal", 41, "card-x", owner="A")
        labels.put("lexeme", 43, "word-x")
        labels.put("shared_deck", 50, "shared-1")
        labels.put("log", 900, "card-x#1", owner="A", card=("personal", "card-x"))
        labels.put("run", 60, "run-1", owner="A")
        return labels

    # key -> (a row around it, the registered id, nullable, zero means "none")
    FIELDS = {
        "user_id": ({}, 7, False, False),
        "owner_user_id": ({}, 7, False, False),
        "deck_id": ({}, 30, True, False),
        "vocab_item_id": ({}, 41, False, False),
        "lexeme_id": ({}, 43, False, False),
        "shared_deck_id": ({}, 50, True, False),
        "review_log_id": ({}, 900, True, False),
        "evidence_from_log_id": ({}, 900, True, False),
        "last_log_id": ({}, 900, False, True),
        "previous_boundary": ({}, 900, False, False),
        "new_boundary": ({}, 900, False, False),
        "run_id": ({}, 60, False, False),
        "source_run_id": ({}, 60, False, False),
        "card_id": ({"card_kind": "personal"}, 41, False, False),
        "card_ref": ({"card_kind": "personal"}, 41, False, False),
        "ref_id": ({"kind": "personal"}, 41, False, False),
        "item_id": ({"card_kind": "personal"}, 41, False, False),
        "id": ({"card_kind": "personal"}, 41, False, False),
    }
    NOT_IDS = {"numeric string": "41", "label string": None, "bool": True, "float": 41.0, "object": {"id": 41},
               "array": [41]}

    def test_each_reference_field_contract(self):
        for key, (row, ident, nullable, zero_is_none) in self.FIELDS.items():
            labels = self.labels()
            label = labels.name(compare_mod.ID_NAMESPACES.get(key) or "personal", ident)
            with self.subTest(key=key, value="registered int"):
                self.assertEqual(normalize({**row, key: ident}, labels)[key], label)
            with self.subTest(key=key, value="NULL"):
                if nullable:
                    self.assertIsNone(normalize({**row, key: None}, labels)[key])
                else:
                    with self.assertRaises(NotComparable):
                        normalize({**row, key: None}, labels)
            with self.subTest(key=key, value="zero"):
                if zero_is_none:
                    self.assertEqual(normalize({**row, key: 0}, labels)[key], "<none:0>")
                else:
                    with self.assertRaises(NotComparable):
                        normalize({**row, key: 0}, labels)
            for name, value in self.NOT_IDS.items():
                value = str(label) if value is None else value
                with self.subTest(key=key, value=name), self.assertRaises(NotComparable):
                    normalize({**row, key: value}, labels)

    def test_raw_label_string_never_equals_an_id(self):
        labels = self.labels()
        good = normalize({"card_kind": "personal", "card_id": 41}, labels)
        with self.assertRaises(NotComparable):
            normalize({"card_kind": "personal", "card_id": "card-x"}, labels)
        # and if a raw string ever got through, the comparison still tells them apart
        self.assertEqual(compare(good, {"card_kind": "personal", "card_id": "card-x"}),
                         [("/card_id", good["card_id"], "card-x")])

    def test_checks_apply_inside_json_and_nested_observations(self):
        labels = self.labels()
        for value in ('{"card_kind": "personal", "card_id": "card-x"}',
                      {"items": [{"card_kind": "personal", "card_id": "41"}]},
                      [{"review": {"card_kind": "personal", "review_log_id": "card-x#1"}}],
                      {"srs_after_json": '{"evidence_from_log_id": true}'}):
            with self.subTest(value=value), self.assertRaises(NotComparable):
                normalize(value, labels)

    def test_registration_takes_integer_ids_only(self):
        for ident in ("41", "card-x", True, 41.0, None, [41]):
            with self.subTest(ident=ident), self.assertRaises(NotComparable):
                Labels().put("personal", ident, "card-x")

    def test_plain_strings_keep_their_contract(self):
        labels = self.labels()
        out = normalize({"request_id": "e2a-card-x-1", "run_key": "run-1", "note": "card-x", "rating": "good"}, labels)
        self.assertEqual(out, {"request_id": "e2a-card-x-1", "run_key": "run-1", "note": "card-x", "rating": "good"})
        self.assertEqual(compare(out["note"], normalize({"card_kind": "personal", "card_id": 41}, labels)["card_id"]),
                         [("", "card-x", "card-x")])  # a plain string is not a reference, even with equal text

    def test_relations_and_id_shift_still_hold(self):
        labels = self.labels()
        with self.assertRaises(NotComparable):
            normalize({"card_kind": "personal", "card_id": 41, "user_id": 7, "review_log_id": 901}, labels)
        shifted = Labels()
        shifted.put("user", 107, "A")
        shifted.put("personal", 141, "card-x", owner="A")
        shifted.put("log", 1900, "card-x#1", owner="A", card=("personal", "card-x"))
        a = normalize({"card_kind": "personal", "card_id": 41, "user_id": 7, "review_log_id": 900}, labels)
        b = normalize({"card_kind": "personal", "card_id": 141, "user_id": 107, "review_log_id": 1900}, shifted)
        self.assertEqual(compare(a, b), [])


def _opt_in_requested() -> bool:
    try:
        return harness.requested(os.environ) is not None
    except harness.UnsafePostgresTarget:
        return True


@unittest.skipUnless(_opt_in_requested(), "PostgreSQL comparison NOT RUN (opt-in not set): no PG result exists")
class PostgresComparison(unittest.TestCase):
    """E-2 only, with explicit opt-in on the protected empty local test database."""

    def test_same_observations_on_sqlite_and_postgresql(self):
        stages = compare_mod.selected_stages()
        run = harness.PgRun(harness.requested(os.environ))
        run.start()
        try:
            pg = compare_mod.run_postgres(run, stages)
        finally:
            run.teardown()
        with tempfile.TemporaryDirectory(prefix="jp_vocab_e2a_", ignore_cleanup_errors=True) as directory:
            sqlite = compare_mod.run_sqlite((Path(directory) / "side.db").as_posix(), stages)
        self.assertEqual(compare(sqlite, pg), [])


if __name__ == "__main__":
    unittest.main()

"""E-5a regression: no production DB, no network; synthetic SQLite only."""

from __future__ import annotations

import os
import ast
import asyncio
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from app.database import init_db, get_connection
from _srs_e5_writes import Writes


class AccountWriteTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="jp_vocab_e5a_", dir=Path(__file__).resolve().parents[1])
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "synthetic.db"
        env = mock.patch.dict(os.environ, {"APP_ENV": "test", "DATABASE_URL": f"sqlite:///{self.path.as_posix()}"})
        env.start()
        self.addCleanup(env.stop)
        init_db()
        self.writes = Writes()

    def test_every_account_write_rejects_deleted_account_without_mutation(self):
        self.writes.erase_account_for_test()
        for name, operation in self.writes.operations().items():
            with self.subTest(operation=name):
                before = self.writes.state()
                before_bytes = self.path.read_bytes()
                with self.assertRaises(ValueError) as caught:
                    operation()
                self.assertEqual(getattr(caught.exception, "code", None), "account_not_found")
                self.assertEqual(getattr(caught.exception, "status_code", None), 404)
                self.assertEqual(self.writes.state(), before)
                self.assertEqual(self.path.read_bytes(), before_bytes)

    def test_publish_uses_one_connection_and_rolls_back_all_words_on_failure(self):
        from app.repositories import shared_deck_repository as shared, lexeme_repository as lexemes
        before = self.writes.state()
        real = shared.add_word_to_shared_deck

        def fail(*args, **kwargs):
            real(*args, **kwargs)
            raise RuntimeError("synthetic_publish_failure")

        with mock.patch.object(lexemes, "get_connection", side_effect=AssertionError("nested connection")), \
                mock.patch.object(shared, "add_word_to_shared_deck", fail):
            with self.assertRaisesRegex(RuntimeError, "synthetic_publish_failure"):
                self.writes.operations()["publish"]()
        self.assertEqual(self.writes.state(), before)

    def test_subscription_and_counter_share_transaction(self):
        from app.repositories import shared_deck_repository as shared, lexeme_repository as lexemes
        before = self.writes.state()
        real = shared.get_or_create_subscription
        called = []

        def fail(*args, **kwargs):
            value = real(*args, **kwargs)
            self.assertTrue(value[1])
            self.assertIsNotNone(kwargs.get("connection"))
            called.append(True)
            raise RuntimeError("synthetic_subscription_failure")

        with mock.patch.object(lexemes, "get_connection", side_effect=AssertionError("nested connection")), \
                mock.patch.object(shared, "is_lexeme_deck", return_value=True), \
                mock.patch.object(shared, "get_or_create_subscription", fail):
            with self.assertRaisesRegex(RuntimeError, "synthetic_subscription_failure"):
                self.writes.operations()["shared_import"]()
        self.assertEqual(called, [True])
        self.assertEqual(self.writes.state(), before)

    def test_anonymous_internal_feedback_contract_is_unchanged(self):
        from app.repositories.feedback_repository import create_app_feedback
        create_app_feedback(user_id=None, category="bug", message="synthetic anonymous", screen="test", path="/")
        with get_connection(read_only=True) as c:
            row = c.execute("SELECT user_id FROM app_feedback").fetchone()
        self.assertIsNone(row["user_id"])

    def test_write_route_inventory_requires_explicit_classification(self):
        source = Path(__file__).resolve().parents[1] / "app" / "main.py"
        routes = set()
        for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in node.decorator_list:
                if (isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute)
                        and isinstance(decorator.func.value, ast.Name) and decorator.func.value.id == "app"
                        and decorator.func.attr in {"post", "put", "patch", "delete"}):
                    routes.add(node.name)
        scoped = {"post_custom_term", "patch_custom_term", "remove_custom_term", "post_deck", "patch_deck",
                  "remove_deck", "post_deck_publish", "post_deck_package_import", "post_shared_deck_import",
                  "remove_shared_deck", "republish_shared_deck_endpoint", "patch_shared_deck_word_progress",
                  "post_shared_deck_word_review", "post_study_review", "post_vocab_item", "patch_vocab_item",
                  "post_meaning_feedback", "post_app_feedback", "explain_vocab_item", "remove_vocab_item"}
        # Provisioning, login and read-only analysis are not writes of an existing account.
        self.assertEqual(routes, scoped | {"register_user", "login_user", "analyze"})

    def test_multi_account_identity_marking_checks_every_owner_before_writing(self):
        from app.srs import identity
        before = self.writes.state()
        with get_connection() as c:
            with self.assertRaises(ValueError) as caught:
                identity.flag_identity_unknown(c, [
                    identity.IdentityFinding(self.writes.user, self.writes.card, ["synthetic"]),
                    identity.IdentityFinding(999999, 999999, ["synthetic"]),
                ])
            self.assertEqual(caught.exception.code, "account_not_found")
        self.assertEqual(self.writes.state(), before)

    def test_publish_lock_order_does_not_change_deck_display_order(self):
        from app.repositories import shared_deck_repository as shared, vocab_repository as vocab
        from app.schemas import VocabItemCreate
        from _srs_e5_writes import sql
        vocab.create_or_update_vocab_item(self.writes.user, VocabItemCreate(surface="aaa-last", deck_id=self.writes.deck))
        calls = []
        real = shared.upsert_lexeme

        def recording(**kwargs):
            calls.append((kwargs["base_form"], kwargs["reading"], kwargs["part_of_speech"]))
            return real(**kwargs)

        with mock.patch.object(shared, "upsert_lexeme", recording):
            result = self.writes.operations()["publish"]()
        self.assertEqual(calls, sorted(calls))
        words = sql("SELECT l.base_form FROM shared_deck_words w JOIN lexemes l ON l.id = w.lexeme_id "
                    "WHERE w.shared_deck_id = ? ORDER BY w.sort_order", (result["shared_deck_id"],))
        self.assertEqual([r["base_form"] for r in words], ["e5-existing", "aaa-last", "e5-term"])


def _normal(name):
    def test(self):
        self.writes.operations()[name]()
    return test


for _name in ("vocab_create", "vocab_update", "context_update", "vocab_delete", "personal_review", "deck_default",
              "deck_create", "deck_update", "deck_delete", "term_create", "term_update", "term_delete",
              "package_import", "publish", "unpublish", "republish", "subscription", "shared_import",
              "legacy_import", "progress", "lexeme_review", "meaning_feedback", "app_feedback"):
    setattr(AccountWriteTests, "test_live_account_" + _name, _normal(_name))


class HttpAccountWriteTests(unittest.TestCase):
    setUp = AccountWriteTests.setUp

    async def request_after_authentication(self, method, path, body):
        import httpx
        from app import main
        from app.auth import create_access_token

        authenticated = []
        real = main.current_user_id

        def deleted_after_auth(request):
            user_id = real(request)
            self.assertEqual(user_id, self.writes.user)
            self.writes.erase_account_for_test()
            authenticated.append(user_id)
            return user_id

        with mock.patch.dict(os.environ, {"JWT_SECRET_KEY": "e5-synthetic-only-32-character-secret"}):
            token = create_access_token({"id": self.writes.user, "email": "writer@e5.example.test"})
            real_required = main.required_user_id

            def required_deleted_after_auth(request):
                self.assertEqual(real_required(request), self.writes.user)
                self.writes.erase_account_for_test()
                authenticated.append(self.writes.user)
                return self.writes.user

            with mock.patch.object(main, "current_user_id", deleted_after_auth), \
                    mock.patch.object(main, "required_user_id", required_deleted_after_auth), \
                    mock.patch.object(main, "generate_context_explanation", return_value="synthetic explanation"):
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://test") as c:
                    result = await c.request(method, path, json=body, headers={"Authorization": "Bearer " + token})
        self.assertEqual(authenticated, [self.writes.user])
        self.assertEqual(result.status_code, 404)
        self.assertEqual(result.json(), {"detail": "account_not_found"})
        return result

    def test_authenticated_request_deleted_before_write(self):
        asyncio.run(self.request_after_authentication("POST", "/vocab-items", {"surface": "new"}))


HTTP_CASES = {
    "deck": lambda w: ("POST", "/decks", {"name": "new"}),
    "term": lambda w: ("POST", "/custom-terms", {"term": "new"}),
    "package": lambda w: ("POST", "/decks/import-package", w.package.model_dump()),
    "subscribe": lambda w: ("POST", f"/shared-decks/{w.shared}/import", {}),
    "progress": lambda w: ("PATCH", f"/shared-decks/{w.shared}/words/{w.lexeme}/progress", {"status": "known"}),
    "lexeme_review": lambda w: ("POST", f"/shared-decks/{w.shared}/words/{w.lexeme}/review", {"rating": "good"}),
    "personal_review": lambda w: ("POST", f"/study-items/{w.card}/review", {"rating": "good"}),
    "meaning": lambda w: ("POST", "/feedback/meaning", {"surface": "new"}),
    "feedback": lambda w: ("POST", "/feedback/app", {"category": "bug", "message": "synthetic feedback"}),
    "publish": lambda w: ("POST", f"/decks/{w.deck}/publish", {"title": "new"}),
    "unpublish": lambda w: ("DELETE", f"/shared-decks/{w.own_shared}", None),
    "republish": lambda w: ("POST", f"/shared-decks/{w.own_shared}/republish", {}),
    "deck_update": lambda w: ("PATCH", f"/decks/{w.deck}", {"name": "new"}),
    "term_update": lambda w: ("PATCH", f"/custom-terms/{w.term}", {"meaning_ko": "new"}),
    "vocab_update": lambda w: ("PATCH", f"/vocab-items/{w.card}", {"meaning_ko": "new"}),
    "explain": lambda w: ("POST", f"/vocab-items/{w.card}/explain", {}),
    "vocab_delete": lambda w: ("DELETE", f"/vocab-items/{w.card}", None),
    "deck_delete": lambda w: ("DELETE", f"/decks/{w.deck}", None),
    "term_delete": lambda w: ("DELETE", f"/custom-terms/{w.term}", None),
}


def _http(factory):
    def test(self):
        asyncio.run(self.request_after_authentication(*factory(self.writes)))
    return test


for _name, _factory in HTTP_CASES.items():
    setattr(HttpAccountWriteTests, "test_late_authenticated_" + _name, _http(_factory))


class SQLiteRaceTests(unittest.TestCase):
    setUp = AccountWriteTests.setUp

    def race(self, name, delete_first):
        from app import database
        from app.account_write import AccountWriteError

        acquired, attempted, release = threading.Event(), threading.Event(), threading.Event()
        results, workers = {}, []
        real = database.AppSQLiteConnection.execute

        def execute(c, statement, parameters=()):
            if statement == "BEGIN IMMEDIATE" and threading.current_thread().name == "second":
                attempted.set()
            result = real(c, statement, parameters)
            if statement == "BEGIN IMMEDIATE" and threading.current_thread().name == "first":
                acquired.set()
                if not release.wait(10):
                    raise TimeoutError("synthetic holder not released")
            return result

        write = self.writes.operations()[name]
        jobs = (self.writes.erase_all_for_test, write) if delete_first else (write, self.writes.erase_all_for_test)

        def job(label, action):
            try:
                results[label] = ("ok", action())
            except BaseException as error:
                results[label] = ("error", error)

        with mock.patch.object(database.AppSQLiteConnection, "execute", execute):
            try:
                for label, action in zip(("first", "second"), jobs):
                    worker = threading.Thread(target=job, args=(label, action), name=label, daemon=True)
                    workers.append(worker)
                    worker.start()
                    if label == "first":
                        self.assertTrue(acquired.wait(10))
                self.assertTrue(attempted.wait(10))
                self.assertNotIn("second", results)
            finally:
                release.set()
                for worker in workers:
                    worker.join(15)
        self.assertTrue(all(not worker.is_alive() for worker in workers))
        self.assertEqual(set(results), {"first", "second"})
        self.assertEqual(results["first"][0], "ok", results["first"])
        if delete_first:
            self.assertEqual(results["second"][0], "error")
            self.assertIsInstance(results["second"][1], AccountWriteError)
            self.assertEqual(results["second"][1].code, "account_not_found")
        else:
            self.assertEqual(results["second"], ("ok", "deleted"))
        self.writes.assert_absent(self)


RACE_OPERATIONS = ("vocab_create", "package_import", "publish", "shared_import", "progress",
                   "lexeme_review", "personal_review", "app_feedback")


def _race(name, delete_first):
    def test(self):
        self.race(name, delete_first)
    return test


for _name in RACE_OPERATIONS:
    for _delete_first in (False, True):
        setattr(SQLiteRaceTests, f"test_{_name}_{'delete_first' if _delete_first else 'write_first'}",
                _race(_name, _delete_first))


class GuardTests(unittest.TestCase):
    def test_invalid_ids_are_refused_without_sql(self):
        from app.account_write import AccountWriteError, begin_account_write
        c = mock.Mock()
        for user in (None, False, "1", 1.0, -1, 0, 10 ** 400):
            with self.subTest(kind=type(user).__name__), self.assertRaises(AccountWriteError):
                begin_account_write(c, user)
        c.execute.assert_not_called()

    def test_database_failures_are_not_reported_as_missing_account(self):
        from app.account_write import begin_account_write
        c = mock.Mock()
        c.is_postgres = True
        c.execute.side_effect = RuntimeError("synthetic_database_failure")
        with self.assertRaisesRegex(RuntimeError, "synthetic_database_failure"):
            begin_account_write(c, 1)
if __name__ == "__main__":
    unittest.main()

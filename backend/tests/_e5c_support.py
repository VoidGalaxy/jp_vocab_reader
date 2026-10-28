"""Gate E-5c: the REAL account deletion (E-5b preview -> apply) against delayed API writes.

Test-only machinery; no product hook. Two orders per write route:

  order 1  authenticated -> paused -> the real deletion commits -> the request resumes;
  order 2  the request's write holds the account write lock (paused just after taking it)
           -> the real deletion is started and must WAIT -> the write commits -> the deletion
           recomputes its plan under the lock.

Pausing is done by wrapping, for the test only, the authentication dependency (order 1) and
the E-5a lock function `begin_account_write` in every app module that imported it (order 2).
Every wait is bounded; a paused job is always released and joined, also when a check fails.
"""

from __future__ import annotations

import asyncio
import os
import sys
import threading
import time
from contextlib import ExitStack, contextmanager
from typing import Any, Callable
from unittest import mock

WAIT = 15.0
SECRET = "e5c-synthetic-only-32-character-secret-key"


# ---- the routes ---------------------------------------------------------------------------
# route function name -> (case name, builder(ctx) -> (method, path, body))
def route_cases():
    return {
        "post_vocab_item": ("vocab_create", lambda c: ("POST", "/vocab-items", {"surface": "e5c-new", "deck_id": c.a.deck})),
        "patch_vocab_item": ("vocab_update", lambda c: ("PATCH", f"/vocab-items/{c.a.c2}", {"meaning_ko": "e5c-edit"})),
        "explain_vocab_item": ("explain", lambda c: ("POST", f"/vocab-items/{c.a.c2}/explain", {})),
        "remove_vocab_item": ("vocab_delete", lambda c: ("DELETE", f"/vocab-items/{c.a.c2}", None)),
        "post_study_review": ("personal_review", lambda c: ("POST", f"/study-items/{c.a.m1}/review", {
            "rating": "good", "request_id": "e5c-req-1", "session_id": "e5c", "expected_card_version": c.version()})),
        "post_deck": ("deck_create", lambda c: ("POST", "/decks", {"name": "e5c-deck"})),
        "patch_deck": ("deck_update", lambda c: ("PATCH", f"/decks/{c.a.deck}", {"name": "e5c-renamed"})),
        "remove_deck": ("deck_delete", lambda c: ("DELETE", f"/decks/{c.extra_deck}", None)),
        "post_custom_term": ("term_create", lambda c: ("POST", "/custom-terms", {"term": "e5c-term"})),
        "patch_custom_term": ("term_update", lambda c: ("PATCH", f"/custom-terms/{c.a.term}", {"meaning_ko": "e5c"})),
        "remove_custom_term": ("term_delete", lambda c: ("DELETE", f"/custom-terms/{c.a.term}", None)),
        "post_deck_package_import": ("package_import", lambda c: ("POST", "/decks/import-package", {
            "package_type": "jp_vocab_reader_deck", "package_version": 1, "deck": {"name": "e5c-package"},
            "vocab_items": [{"surface": "e5c-package-word"}]})),
        "post_deck_publish": ("publish", lambda c: ("POST", f"/decks/{c.a.deck}/publish", {"title": "e5c-shared"})),
        "post_shared_deck_import": ("subscribe", lambda c: ("POST", f"/shared-decks/{c.o_shared2}/import", {})),
        "patch_shared_deck_word_progress": ("progress", lambda c: (
            "PATCH", f"/shared-decks/{c.a.o_shared}/words/{c.a.lexeme}/progress", {"status": "unknown"})),
        "post_shared_deck_word_review": ("lexeme_review", lambda c: (
            "POST", f"/shared-decks/{c.a.o_shared}/words/{c.a.lexeme}/review", {"rating": "good"})),
        "post_meaning_feedback": ("meaning_feedback", lambda c: ("POST", "/feedback/meaning", {"surface": "e5c"})),
        "post_app_feedback": ("app_feedback", lambda c: ("POST", "/feedback/app", {"category": "bug", "message": "e5c synthetic feedback"})),
        "remove_shared_deck": ("unpublish", lambda c: ("DELETE", f"/shared-decks/{c.own_shared}", None)),
        "republish_shared_deck_endpoint": ("republish", lambda c: ("POST", f"/shared-decks/{c.own_shared}/republish", {})),
    }


# extra case on an existing route: the FIRST review of a subscribed word (no progress row yet)
EXTRA_CASES = {
    # no deck named: the default-deck path (creates the account's default deck when missing)
    "vocab_create_default_deck": lambda c: ("POST", "/vocab-items", {"surface": "e5c-new-default"}),
    "first_lexeme_review": lambda c: ("POST", f"/shared-decks/{c.a.o_shared}/words/{c.lexeme2}/review", {"rating": "good"}),
    # the FSRS subscribed path (the two above are the rating-only compatibility requests):
    # a first review with ids and an explicit `expected_card_version: null` ...
    "fsrs_first_lexeme_review": lambda c: ("POST", f"/shared-decks/{c.a.o_shared}/words/{c.lexeme2}/review", {
        "rating": "good", "request_id": "e5c-fsrs-first", "session_id": "e5c", "expected_card_version": None}),
    # ... and a review of an existing FSRS subscribed card at its current version
    "fsrs_lexeme_review": lambda c: ("POST", f"/shared-decks/{c.a.o_shared}/words/{c.lexeme3}/review", {
        "rating": "good", "request_id": "e5c-fsrs-next", "session_id": "e5c",
        "expected_card_version": c.lexeme_version(c.lexeme3)}),
}
# cases whose world also holds an FSRS subscribed card (lexeme3, made by a real FSRS first review)
FSRS_CARD_CASES = {"fsrs_lexeme_review"}
# Not writes of an existing account (E-5a classification), and why they are excluded here.
EXCLUDED_ROUTES = {
    "register_user": "creates a NEW account (a new id; ids are never reused)",
    "login_user": "reads credentials and issues a token; no account data is written",
    "analyze": "read-only text analysis; no account data is written",
}
# routes whose target must OWN a shared deck: the deletion is held for owner review in both orders
OWNER_CASES = {"unpublish", "republish"}

# order 2: the deletion's outcome once the write committed first (E5B_CONTRACT 4 / 5)
ORDER2_DELETION = {
    "vocab_create": "plan_changed", "vocab_create_default_deck": "plan_changed", "vocab_update": "deleted", "explain": "deleted", "vocab_delete": "plan_changed",
    "personal_review": "plan_changed", "deck_create": "plan_changed", "deck_update": "deleted",
    "deck_delete": "plan_changed", "term_create": "plan_changed", "term_update": "deleted",
    "term_delete": "plan_changed", "package_import": "plan_changed", "publish": "blocked:shared_deck_owner_review",
    "subscribe": "plan_changed", "progress": "deleted", "lexeme_review": "plan_changed",
    "first_lexeme_review": "plan_changed", "fsrs_first_lexeme_review": "plan_changed",
    "fsrs_lexeme_review": "plan_changed", "meaning_feedback": "plan_changed",
    "app_feedback": "blocked:app_feedback_retention_review",
    "unpublish": "blocked:shared_deck_owner_review", "republish": "blocked:shared_deck_owner_review",
}
# order 1: the API's answer once the account was deleted after authentication. Routes that
# only touch rows the deletion removed may answer with their existing not-found detail.
ORDER1_DETAILS = {"account_not_found", "Vocabulary item not found", "Deck not found", "Custom term not found",
                  "vocab item not found", "deck not found", "custom term not found"}


def write_route_inventory() -> set[str]:
    """Write routes of app/main.py (POST / PUT / PATCH / DELETE), from the source."""
    import ast
    from pathlib import Path

    source = Path(__file__).resolve().parents[1] / "app" / "main.py"
    routes = set()
    for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for d in node.decorator_list:
                if (isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute)
                        and getattr(d.func.value, "id", None) == "app" and d.func.attr in {"post", "put", "patch", "delete"}):
                    routes.add(node.name)
    return routes


# ---- the synthetic world --------------------------------------------------------------------
class Context:
    def __init__(self, *, owner: bool, tag: str = "e5c", fsrs_card: bool = False, unpublished: bool = False):
        from _e5b_fixture import Accounts, card, sql
        from app.repositories import deck_repository as decks, lexeme_repository as lexemes
        from app.repositories import shared_deck_repository as shared
        from app.schemas import DeckCreate

        self.sql = sql
        self.a = a = Accounts(tag)
        o_deck2 = decks.create_deck(a.O, DeckCreate(name="o-deck-2"))[0]["id"]
        card(a.O, o_deck2, "o-word-2")
        self.o_shared2 = shared.publish_deck(a.O, o_deck2, "o-shared-2", "")["shared_deck_id"]
        self.lexeme2 = lexemes.upsert_lexeme("e5c-lexeme-2", "e5c-lexeme-2")
        lexemes.add_word_to_shared_deck(a.o_shared, self.lexeme2, 6)
        self.extra_deck = decks.create_deck(a.T, DeckCreate(name="t-extra-deck"))[0]["id"]
        self.own_shared = a.own_shared_deck(a.T, a.deck, unpublish=unpublished) if owner else None
        self.lexeme3 = None
        if fsrs_card:
            self.lexeme3 = lexemes.upsert_lexeme("e5c-lexeme-3", "e5c-lexeme-3")
            lexemes.add_word_to_shared_deck(a.o_shared, self.lexeme3, 7)
            lexemes.record_lexeme_review(a.T, self.lexeme3, "good", a.o_shared, request_id=f"e5c-fsrs-setup-{tag}",
                                         session_id="e5c", first_review=True)
            assert self.value("SELECT srs_engine AS v FROM user_word_progress WHERE user_id = ? AND lexeme_id = ?",
                              (a.T, self.lexeme3)) == "fsrs"

    @classmethod
    def for_case(cls, name, tag="e5c"):
        return cls(owner=name in OWNER_CASES, tag=tag, fsrs_card=name in FSRS_CARD_CASES,
                   unpublished=name == "republish")

    def value(self, query, params=()):
        rows = self.sql(query, params)
        return rows[0]["v"] if rows else None

    def version(self):
        return self.sql("SELECT srs_card_version AS v FROM vocab_items WHERE id = ?", (self.a.m1,))[0]["v"]

    def lexeme_version(self, lexeme):
        return self.value("SELECT srs_card_version AS v FROM user_word_progress WHERE user_id = ? AND lexeme_id = ?",
                          (self.a.T, lexeme))

    def token(self):
        from app.auth import create_access_token

        return create_access_token({"id": self.a.T, "email": "target@e5b.example.test"})

    def target_rows(self):
        return {t: r for t, r in self.a.rows_of(self.a.T).items() if r}

    def others(self):
        return self.a.everything_but(self.a.T)


# ---- the write's own effect, read from the database -----------------------------------------
# case -> facts(ctx): the rows the write must create / change / remove. Order 2 reads them twice:
# before the request, and once the write has committed while the deletion holds the lock and
# has not yet read or removed anything (WriteFirst `observe`). An API success alone is never
# taken as the write being kept.
def _lexeme_facts(c, lexeme, request_id=None):
    T = c.a.T
    facts = {
        "engine": c.value("SELECT srs_engine AS v FROM user_word_progress WHERE user_id = ? AND lexeme_id = ?", (T, lexeme)),
        "version": c.lexeme_version(lexeme),
        "correct": c.value("SELECT correct_count AS v FROM user_word_progress WHERE user_id = ? AND lexeme_id = ?", (T, lexeme)),
        "logs": c.value("SELECT count(*) AS v FROM lexeme_review_logs WHERE user_id = ? AND lexeme_id = ?", (T, lexeme)),
    }
    if request_id is not None:
        facts["fsrs_log_version_before"] = c.value(
            "SELECT card_version_before AS v FROM lexeme_review_logs WHERE user_id = ? AND lexeme_id = ? "
            "AND request_id = ? AND srs_engine = 'fsrs'", (T, lexeme, request_id))
        facts["receipt"] = c.value(
            "SELECT count(*) AS v FROM srs_review_receipts r JOIN lexeme_review_logs l ON l.id = r.review_log_id "
            "WHERE r.user_id = ? AND r.request_id = ? AND r.card_kind = 'lexeme' AND r.card_ref = ? "
            "AND l.request_id = r.request_id", (T, request_id, lexeme))
    return facts


def _count(c, query, params):
    return c.value(f"SELECT count(*) AS v FROM {query}", params)


def _effects():
    def personal(c):
        return {"version": c.version(),
                "fsrs_log_version_before": c.value(
                    "SELECT card_version_before AS v FROM review_logs WHERE user_id = ? AND vocab_item_id = ? "
                    "AND request_id = 'e5c-req-1' AND srs_engine = 'fsrs'", (c.a.T, c.a.m1)),
                "receipt": _count(c, "srs_review_receipts WHERE user_id = ? AND request_id = 'e5c-req-1' "
                                  "AND card_kind = 'personal' AND card_ref = ?", (c.a.T, c.a.m1))}

    def lexeme_counted(lexeme, request_id=None):
        return lambda c: _lexeme_facts(c, getattr(c, lexeme) if isinstance(lexeme, str) else lexeme(c), request_id)

    T = lambda c: c.a.T  # noqa: E731
    return {
        "vocab_create": (lambda c: {"n": _count(c, "vocab_items WHERE user_id = ? AND surface = 'e5c-new' AND deck_id = ?",
                                                (T(c), c.a.deck))},
                         lambda c, pre: {"n": 1}),
        "vocab_create_default_deck": (
            lambda c: {"n": _count(c, "vocab_items v JOIN decks d ON d.id = v.deck_id WHERE v.user_id = ? "
                                      "AND d.user_id = v.user_id AND v.surface = 'e5c-new-default'", (T(c),))},
            lambda c, pre: {"n": 1}),
        "vocab_update": (lambda c: {"meaning": c.value("SELECT meaning_ko AS v FROM vocab_items WHERE id = ?", (c.a.c2,))},
                         lambda c, pre: {"meaning": "e5c-edit"}),
        "explain": (lambda c: {"explanation": c.value("SELECT context_explanation_ko AS v FROM vocab_items WHERE id = ?",
                                                      (c.a.c2,))},
                    lambda c, pre: {"explanation": "e5c synthetic explanation"}),
        "vocab_delete": (lambda c: {"n": _count(c, "vocab_items WHERE id = ?", (c.a.c2,))}, lambda c, pre: {"n": 0}),
        "personal_review": (personal, lambda c, pre: {"version": pre["version"] + 1,
                                                      "fsrs_log_version_before": pre["version"], "receipt": 1}),
        "deck_create": (lambda c: {"n": _count(c, "decks WHERE user_id = ? AND name = 'e5c-deck'", (T(c),))},
                        lambda c, pre: {"n": 1}),
        "deck_update": (lambda c: {"name": c.value("SELECT name AS v FROM decks WHERE id = ?", (c.a.deck,))},
                        lambda c, pre: {"name": "e5c-renamed"}),
        "deck_delete": (lambda c: {"n": _count(c, "decks WHERE id = ?", (c.extra_deck,))}, lambda c, pre: {"n": 0}),
        "term_create": (lambda c: {"n": _count(c, "custom_terms WHERE user_id = ? AND term = 'e5c-term'", (T(c),))},
                        lambda c, pre: {"n": 1}),
        "term_update": (lambda c: {"meaning": c.value("SELECT meaning_ko AS v FROM custom_terms WHERE id = ?", (c.a.term,))},
                        lambda c, pre: {"meaning": "e5c"}),
        "term_delete": (lambda c: {"n": _count(c, "custom_terms WHERE id = ?", (c.a.term,))}, lambda c, pre: {"n": 0}),
        "package_import": (
            lambda c: {"n": _count(c, "vocab_items v JOIN decks d ON d.id = v.deck_id WHERE d.user_id = ? "
                                      "AND d.name = 'e5c-package' AND v.surface = 'e5c-package-word'", (T(c),))},
            lambda c, pre: {"n": 1}),
        "publish": (lambda c: {"n": _count(c, "shared_decks WHERE owner_user_id = ? AND title = 'e5c-shared'", (T(c),))},
                    lambda c, pre: {"n": 1}),
        "subscribe": (lambda c: {"n": _count(c, "user_deck_subscriptions WHERE user_id = ? AND shared_deck_id = ?",
                                             (T(c), c.o_shared2)),
                                 "imports": c.value("SELECT import_count AS v FROM shared_decks WHERE id = ?", (c.o_shared2,))},
                      lambda c, pre: {"n": 1, "imports": pre["imports"] + 1}),
        "progress": (lambda c: {"status": c.value("SELECT status AS v FROM user_word_progress WHERE user_id = ? "
                                                  "AND lexeme_id = ?", (T(c), c.a.lexeme))},
                     lambda c, pre: {"status": "unknown"}),
        "lexeme_review": (lexeme_counted(lambda c: c.a.lexeme),
                          lambda c, pre: {**pre, "correct": pre["correct"] + 1, "logs": pre["logs"] + 1,
                                          "version": pre["version"] + 1}),
        # rating-only first review (compatibility): the legacy lazy progress row and one log
        "first_lexeme_review": (lexeme_counted("lexeme2"),
                                lambda c, pre: {"engine": "legacy", "version": 1, "correct": 1, "logs": 1}),
        "fsrs_first_lexeme_review": (
            lexeme_counted("lexeme2", "e5c-fsrs-first"),
            lambda c, pre: {"engine": "fsrs", "version": 1, "correct": 1, "logs": 1,
                            "fsrs_log_version_before": 0, "receipt": 1}),
        "fsrs_lexeme_review": (
            lexeme_counted("lexeme3", "e5c-fsrs-next"),
            lambda c, pre: {"engine": "fsrs", "version": pre["version"] + 1, "correct": pre["correct"] + 1,
                            "logs": pre["logs"] + 1, "fsrs_log_version_before": pre["version"], "receipt": 1}),
        "meaning_feedback": (lambda c: {"n": _count(c, "meaning_feedback WHERE user_id = ? AND surface = 'e5c'", (T(c),))},
                             lambda c, pre: {"n": 1}),
        "app_feedback": (lambda c: {"n": _count(c, "app_feedback WHERE user_id = ? AND message = 'e5c synthetic feedback'",
                                                (T(c),))},
                         lambda c, pre: {"n": 1}),
        "unpublish": (lambda c: {"visibility": c.value("SELECT visibility AS v FROM shared_decks WHERE id = ?",
                                                       (c.own_shared,))},
                      lambda c, pre: {"visibility": "unpublished"}),
        "republish": (lambda c: {"visibility": c.value("SELECT visibility AS v FROM shared_decks WHERE id = ?",
                                                       (c.own_shared,))},
                      lambda c, pre: {"visibility": "public"}),
    }


EFFECTS = _effects()


def preview(user):
    from app import account_deletion
    from app.database import get_connection

    with get_connection() as c:
        return account_deletion.preview(c, user)


def apply(user, plan):
    from app import account_deletion
    from app.database import get_connection

    with get_connection() as c:
        return account_deletion.apply(c, user, confirm_user_id=user, expected_plan=plan)


def delete_for_real(user):
    """The E-5b procedure: preview, then apply with that plan."""
    report = preview(user)
    if not report["eligible"]:
        return {"status": "held", "reasons": report["reasons"]}
    return apply(user, report["plan"])


# ---- requests -------------------------------------------------------------------------------
async def _send(method, path, body, token, base_url=None):
    import httpx
    from app import main

    if base_url is None:
        transport = httpx.ASGITransport(app=main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.request(method, path, json=body, headers={"Authorization": "Bearer " + token})
    async with httpx.AsyncClient(base_url=base_url, timeout=WAIT) as client:
        return await client.request(method, path, json=body, headers={"Authorization": "Bearer " + token})


def request(method, path, body, token, base_url=None):
    from app import main

    with mock.patch.object(main, "generate_context_explanation", return_value="e5c synthetic explanation"):
        return asyncio.run(_send(method, path, body, token, base_url))


@contextmanager
def delete_after_authentication(user, outcome: dict):
    """Order 1: once the request is authenticated (its own connection), run the REAL deletion
    and let the request continue."""
    from app import main

    real_current, real_required = main.current_user_id, main.required_user_id

    def wrap(real):
        def authenticated_then_deleted(request):
            user_id = real(request)
            outcome.setdefault("authenticated", []).append(user_id)
            outcome["deletion"] = delete_for_real(user)
            return user_id
        return authenticated_then_deleted

    with mock.patch.object(main, "current_user_id", wrap(real_current)), \
            mock.patch.object(main, "required_user_id", wrap(real_required)):
        yield


# ---- order 2: the write holds the lock; the deletion waits -------------------------------
def _modules_with_lock():
    # Import the whole app first: a module first imported while the lock is patched would keep
    # the test wrapper after the patch ends (seen when order 2 ran before any request had
    # imported app.main: the next case's package import then never paused).
    import app.account_write as account_write
    import app.main  # noqa: F401

    real = account_write.begin_account_write
    holders = {name: getattr(m, "begin_account_write") for name, m in list(sys.modules.items())
               if name.startswith("app.") and hasattr(m, "begin_account_write")}
    stale = sorted(name for name, fn in holders.items() if fn is not real)
    if stale:
        raise AssertionError(f"modules hold a non-original account lock: {stale}")
    return real, [sys.modules[name] for name in holders]


class WriteFirst:
    """Pause the request's write right after it takes the account lock; start the real
    deletion (thread 'deleter'); prove it waits; release; collect both outcomes."""

    def __init__(self, user, plan, *, waiting_probe: Callable[["WriteFirst"], bool],
                 observe: Callable[[], Any] | None = None):
        self.user, self.plan, self.waiting_probe, self.observe = user, plan, waiting_probe, observe
        self.entered, self.release = threading.Event(), threading.Event()
        self.box: dict[str, Any] = {}
        self.paused_thread = None

    def run(self, send: Callable[[], Any]):
        real, modules = _modules_with_lock()

        def paused(connection, user_id, **kwargs):
            real(connection, user_id, **kwargs)
            if threading.current_thread().name == "deleter":
                # The deletion now holds the lock the write released at commit, and has read and
                # removed nothing yet: read the write's committed effect on a separate connection.
                # Reading only, after the lock order already happened, so the order is unchanged.
                if self.observe is not None and "observed" not in self.box:
                    try:
                        self.box["observed"] = ("ok", self.observe())
                    except BaseException as error:  # noqa: BLE001 -- kept as the outcome
                        self.box["observed"] = ("error", error)
                return
            if not self.entered.is_set():
                self.paused_thread = threading.current_thread().name
                self.entered.set()
                if not self.release.wait(WAIT):
                    raise TimeoutError("the paused write was never released")

        def job(name, fn):
            try:
                self.box[name] = ("ok", fn())
            except BaseException as error:  # noqa: BLE001 -- kept as the outcome
                self.box[name] = ("error", error)

        threads = []
        with ExitStack() as stack:
            for module in modules:
                stack.enter_context(mock.patch.object(module, "begin_account_write", paused))
            try:
                writer = threading.Thread(target=job, args=("write", send), name="writer", daemon=True)
                threads.append(writer)
                writer.start()
                self.box["write_paused"] = self.entered.wait(WAIT)
                if not self.box["write_paused"]:
                    return self.box
                deleter = threading.Thread(target=job, args=("delete", lambda: apply(self.user, self.plan)),
                                           name="deleter", daemon=True)
                threads.append(deleter)
                deleter.start()
                deadline, waited = time.monotonic() + WAIT, False
                while time.monotonic() < deadline and deleter.is_alive():
                    if self.waiting_probe(self):
                        waited = True
                        break
                    time.sleep(0.05)
                self.box["delete_waited_for_write"] = waited
                self.box["delete_done_while_write_held"] = not deleter.is_alive()
            finally:
                self.release.set()
                for thread in threads:
                    thread.join(WAIT)
                self.box["joined"] = all(not t.is_alive() for t in threads)
        return self.box


def sqlite_waiting_probe():
    """SQLite: the deleter has asked for BEGIN IMMEDIATE and has not got it after 0.3 s."""
    from app import database

    state = {"asked": threading.Event()}
    real = database.AppSQLiteConnection.execute

    def execute(connection, statement, parameters=()):
        if statement == "BEGIN IMMEDIATE" and threading.current_thread().name == "deleter":
            state["asked"].set()
        return real(connection, statement, parameters)

    def probe(write_first):
        if not state["asked"].wait(0.05):
            return False
        time.sleep(0.3)
        return "delete" not in write_first.box
    return mock.patch.object(database.AppSQLiteConnection, "execute", execute), probe


def postgres_waiting_probe(run):
    """PostgreSQL: the deleter's backend holds a not-granted lock and pg_blocking_pids() names
    a backend opened by the paused write (read on the harness's own connection)."""
    import _srs_e2_adapter as adapter

    pids: dict[str, list[int]] = {}
    real_connect = adapter._GuardedPsycopg.connect

    def recording(shim, url, **kwargs):
        connection = real_connect(shim, url, **kwargs)
        name = "deleter" if threading.current_thread().name == "deleter" else "writer"
        pids.setdefault(name, []).append(connection.info.backend_pid)
        return connection

    def probe(write_first):
        waiter, holders = pids.get("deleter", []), set(pids.get("writer", []))
        if not waiter or not holders:
            return False
        with run._connection() as connection:
            try:
                run._check_target(connection)
                rows = run._rows(connection, "SELECT l.locktype, l.mode, pg_blocking_pids(l.pid) FROM pg_locks l "
                                             "WHERE l.pid = %s AND NOT l.granted", (waiter[-1],))
            finally:
                connection.rollback()
        hit = [r for r in rows if holders & set(r[2] or [])]
        if hit:
            write_first.box["waits"] = [(r[0], r[1]) for r in hit]
        return bool(hit)
    return mock.patch.object(adapter._GuardedPsycopg, "connect", recording), probe, pids


def record(entry: dict) -> None:
    """Per-case facts for the report (status, detail, deletion outcome, wait evidence), to the
    file named by E5C_RECORD when set. No token, URL or stored content."""
    import json

    target = os.environ.get("E5C_RECORD")
    if target:
        with open(target, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")


@contextmanager
def jwt_secret():
    with mock.patch.dict(os.environ, {"JWT_SECRET_KEY": SECRET}):
        yield

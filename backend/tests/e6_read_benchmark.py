"""Gate E-6 (first pass): read-path timing of /study-queue, /stats and /vocab-items?due_only=true
on synthetic accounts of 1,000 and 10,000 cards. Measurement only -- no pass/fail threshold.

Not a test module (no `test_` prefix: never collected by the backend suite). Run explicitly:

  SQLite (session file only):  APP_ENV=test python -m unittest e6_read_benchmark.SqliteBench
  local test PG (E-1 harness):  + SRS_E_TEST_POSTGRES_URL / SRS_E_TEST_POSTGRES_OPT_IN=1,
                                python -m unittest e6_read_benchmark.PgBench
  (cwd backend/tests; test_1000 / test_10000, each on a fresh database; results to E6_OUT as
   JSON: counts, hashes and timings only)

World (fixed rules, seed SEED; same on both databases):
- account T (FSRS mode, daily goal 20) with N cards: N/2 personal in 2 decks, N/2 subscribed
  words of 2 shared decks owned by account O.
- per kind: new 30 % (subscribed new have no progress row), learning / relearning due 10 %,
  review due today 15 %, overdue 15 %, due later 25 %, legacy not converted 5 %.
- FSRS cards: 1-14 reviews each (mean 7.5); legacy cards 0-3 legacy reviews; overall ~5 logs per card.
Everything is written by the app's own paths (user / deck / card creation, publish, subscribe,
status, legacy and FSRS reviews with request ids), so versions, log chains and receipts are the
app's. Only for generation speed: one shared connection (each call still commits), a fixed clock,
and the review answer's "introduced today" count computed by the real counting function from an
incrementally kept first-review map (equal to the full read: checked in test_e6_read_benchmark).
The mode switch is a settings-row write, as in the E-5 fixtures (no API exists).

Timing runs carry no SQL wrapper; SQL counts, rows and plans come from a separate diagnostic run.
Timed and diagnostic reads run read-only (SQLite file attribute, PG default_transaction_read_only).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import random
import stat
import statistics
import sys
import tempfile
import time
import unittest
from contextlib import ExitStack, contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from unittest import mock

TESTS = Path(__file__).resolve().parent
BACKEND = TESTS.parent
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(TESTS))
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

SEED = 20261020
T_REF = datetime(2026, 10, 20, 3, 0, tzinfo=timezone.utc)      # 12:00 Asia/Seoul
T_CREATE = T_REF - timedelta(days=3650)       # room for long review chains (no shortening)
SECRET = "e6-synthetic-only-32-character-secret-key"
WARMUP, REPEAT = 5, 30
SHARE = {"new": 0.30, "learning": 0.05, "relearning": 0.05, "review_today": 0.15, "overdue": 0.15,
         "later": 0.25, "legacy": 0.05}
SEOUL = timezone(timedelta(hours=9))


# ---- clock / connection (generation and measurement only; test-scoped patches) -------------
class Clock:
    def __init__(self, at: datetime):
        self.at = at

    def now_utc(self):
        return self.at


def _app_modules():
    """Every app module, all imported first: a module first imported while a name is patched
    would keep the patched object afterwards."""
    import importlib
    import pkgutil

    import app

    for info in pkgutil.walk_packages(app.__path__, "app."):
        importlib.import_module(info.name)
    return [m for name, m in list(sys.modules.items()) if name == "app" or name.startswith("app.")]


@contextmanager
def fixed_clock(clock: Clock):
    import app.database as database
    import app.main  # noqa: F401 -- every app module imported before patching names
    from app.srs import queue

    real = database.now_utc
    with ExitStack() as stack:
        for module in _app_modules():
            if getattr(module, "now_utc", None) is real:
                stack.enter_context(mock.patch.object(module, "now_utc", clock.now_utc))
        stack.enter_context(mock.patch.object(queue, "_now", clock.now_utc))
        yield


class _Shared:
    """The app's `with get_connection() as c:` on one open connection: commit / rollback on
    exit as usual, never close (generation only)."""

    def __init__(self, connection):
        self.connection = connection

    def __call__(self, *, read_only: bool = False):
        assert not read_only
        return self

    def __enter__(self):
        return self.connection

    def __exit__(self, exc_type, exc, tb):
        (self.connection.rollback if exc_type else self.connection.commit)()
        return False


@contextmanager
def shared_connection():
    import app.database as database
    import app.main  # noqa: F401

    real = database.get_connection
    connection = real()
    if not database.is_postgres_connection(connection):
        connection.execute("PRAGMA synchronous = OFF")   # synthetic generation file only
    shared = _Shared(connection)
    try:
        with ExitStack() as stack:
            for module in _app_modules():
                if getattr(module, "get_connection", None) is real:
                    stack.enter_context(mock.patch.object(module, "get_connection", shared))
            yield connection
    finally:
        connection.close()


class IntroducedCache:
    """reviews.introduced_on through the real goals.count_introduced, with the first-review map
    kept incrementally instead of re-reading every log of the account on each review."""

    def __init__(self, connection, user_id):
        from app.srs import goals, history_intro, identity

        self.dates = goals.first_review_dates(connection, user_id)
        self.identity_days = identity.identity_unknown_days(connection, user_id)
        self.evidence = history_intro.intro_evidence(connection, user_id)

    def saw(self, key, at):
        if key not in self.dates or at < self.dates[key]:
            self.dates[key] = at

    def introduced_on(self, connection, user_id, at):
        from app.srs import goals

        return goals.count_introduced(self.dates, at, None, self.identity_days, self.evidence)


# ---- schedule planning with the app's own engine ---------------------------------------------
def _chain(kind, user, ref, ratings, start):
    from app.srs.engine import CardKey, review

    state, out, at = None, [], start
    for rating in ratings:
        outcome = review(CardKey(kind, user, ref), state, rating, at)
        state = outcome.after
        out.append((at, rating, state))
        at = state.due_at
    return out


def _ratings(rng, target, n):
    if target == "learning":
        return ["again"] * n
    body = n - 1 if target == "relearning" else n
    if body <= 1:
        seq = ["easy"]
    else:
        seq = ["good", "good"] + [rng.choices(["good", "hard", "easy", "again"], [70, 15, 10, 5])[0]
                                  for _ in range(body - 2)]
        seq[-1] = "good" if seq[-1] == "again" else seq[-1]          # the body ends in review phase
    return seq + (["again"] if target == "relearning" else [])


def plan_card(rng, kind, user, ref, target, n):
    """Fewer reviews when a long chain does not fit between creation and T_REF."""
    while True:
        try:
            return _plan_card(rng, kind, user, ref, target, n)
        except AssertionError:
            if n == 1:
                raise
            n = max(1, n - 3)


def _plan_card(rng, kind, user, ref, target, n):
    """Review times and ratings so that, at T_REF, the card is in `target` (engine-verified)."""
    from app.srs.engine import SrsPhase

    ratings = _ratings(rng, target, n)
    base = datetime(2000, 1, 1, tzinfo=timezone.utc)
    rel = _chain(kind, user, ref, ratings, base)
    last, due = rel[-1][0] - base, rel[-1][2].due_at - base
    if target == "later":
        offset = (due - last) * rng.uniform(0.05, 0.95)       # last review before, due after T_REF
        start = T_REF - last - offset
    else:
        lag = {"learning": (300, 18000), "relearning": (300, 18000), "review_today": (600, 39600),
               "overdue": (86400, 30 * 86400)}[target]
        start = T_REF - due - timedelta(seconds=rng.uniform(*lag))
    events = _chain(kind, user, ref, ratings, start)
    final = events[-1][2]
    want = {"learning": SrsPhase.LEARNING, "relearning": SrsPhase.RELEARNING}.get(target, SrsPhase.REVIEW)
    assert final.phase == want, (target, final.phase)
    assert events[0][0] > T_CREATE + timedelta(days=1) and events[-1][0] < T_REF
    assert (final.due_at > T_REF) == (target == "later")
    if target == "review_today":
        assert final.due_at.astimezone(SEOUL).date() == T_REF.astimezone(SEOUL).date()
    if target == "overdue":
        assert final.due_at < T_REF - timedelta(days=1)
    return [(at, rating) for at, rating, _ in events]


def _targets(rng, count):
    names = []
    for name, share in SHARE.items():
        names += [name] * round(share * count)
    names = (names + ["later"] * count)[:count]
    rng.shuffle(names)
    return names


# ---- the synthetic world ------------------------------------------------------------------
def build_world(size: int, *, fast: bool = True) -> dict[str, Any]:
    """Create the world on the current DATABASE_URL (tables already present). Returns the
    generator's expectations (counts / ids) and the step timings."""
    from app.repositories import deck_repository as decks, lexeme_repository as lexemes
    from app.repositories import shared_deck_repository as shared, user_repository as users
    from app.repositories import vocab_repository as vocab
    from app.schemas import DeckCreate, VocabItemCreate
    import app.srs.reviews as reviews

    rng = random.Random(SEED + size)
    clock = Clock(T_CREATE)
    half, quarter = size // 2, size // 4
    timings, expected = {}, {}
    started = time.perf_counter()
    with ExitStack() as stack:
        stack.enter_context(fixed_clock(clock))
        connection = stack.enter_context(shared_connection()) if fast else None

        def sql(query, params=()):
            from app.database import get_connection
            with get_connection() as c:
                cur = c.execute(query, params)
                return [dict(r) for r in cur.fetchall()] if cur.description else []

        def set_mode(user, mode):
            sql("DELETE FROM srs_user_settings WHERE user_id = ?", (user,))
            sql("INSERT INTO srs_user_settings (user_id, srs_mode, daily_new_goal, settings_version, created_at, "
                "updated_at) VALUES (?, ?, 20, 0, ?, ?)", (user, mode, clock.at.isoformat(), clock.at.isoformat()))

        def card(user, deck, name):
            return vocab.create_or_update_vocab_item(user, VocabItemCreate(
                surface=name, base_form=name, reading=f"{name}-r", meaning_ko=f"{name}-m", deck_id=deck))[0]["id"]

        T = users.create_user("e6-target@e6.example.test", "e6-target", "synthetic")["id"]
        O = users.create_user("e6-owner@e6.example.test", "e6-owner", "synthetic")["id"]
        # O: two decks of N/4 words, published (lexeme mode) -> the subscribed side
        shared_ids, words = [], []
        for d in range(2):
            deck = decks.create_deck(O, DeckCreate(name=f"e6-o-deck-{d}"))[0]["id"]
            for i in range(quarter):
                card(O, deck, f"s{d}w{i:05d}")
            sid = shared.publish_deck(O, deck, f"e6-shared-{d}", "")["shared_deck_id"]
            shared_ids.append(sid)
            words += [(sid, r["lexeme_id"]) for r in sql(
                "SELECT lexeme_id FROM shared_deck_words WHERE shared_deck_id = ? ORDER BY lexeme_id", (sid,))]
        # T: legacy first (the not-converted share), subscriptions, two personal decks
        set_mode(T, "legacy")
        for sid in shared_ids:
            lexemes.get_or_create_subscription(T, sid)
        p_decks = [decks.create_deck(T, DeckCreate(name=f"e6-t-deck-{d}"))[0]["id"] for d in range(2)]
        p_targets, s_targets = _targets(rng, half), _targets(rng, len(words))
        personal = {}
        legacy_logs = 0
        for i, target in enumerate(p_targets):
            if target == "legacy":
                clock.at = T_CREATE + timedelta(minutes=i)
                ref = card(T, p_decks[i % 2], f"p{i:05d}")
                personal[ref] = ("legacy", p_decks[i % 2])
                for j in range(rng.randrange(4)):
                    clock.at = T_CREATE + timedelta(hours=1 + j, minutes=i)
                    vocab.record_review(T, ref, rng.choice(["good", "hard", "again"]))
                    legacy_logs += 1
        lexeme_target = {}
        for (sid, lex), target in zip(words, s_targets):
            lexeme_target[lex] = (target, sid)
            if target == "legacy":
                clock.at = T_CREATE + timedelta(minutes=lex)
                lexemes.update_word_status(T, lex, "unknown")
                for j in range(rng.randrange(4)):
                    clock.at = T_CREATE + timedelta(hours=1 + j, minutes=lex)
                    lexemes.record_lexeme_review(T, lex, rng.choice(["good", "hard", "again"]), sid)
                    legacy_logs += 1
        clock.at = T_CREATE + timedelta(hours=12)
        set_mode(T, "fsrs")
        for i, target in enumerate(p_targets):
            if target != "legacy":
                ref = card(T, p_decks[i % 2], f"p{i:05d}")
                personal[ref] = (target, p_decks[i % 2])
        timings["cards_s"] = time.perf_counter() - started

        # FSRS reviews through the app's review functions, in global time order
        events = []
        for ref, (target, _deck) in sorted(personal.items()):
            if target not in ("new", "legacy"):
                events += [(at, rating, "personal", ref, None, k) for k, (at, rating) in
                           enumerate(plan_card(rng, "personal", T, ref, target, 1 + rng.randrange(14)))]
        for lex, (target, sid) in sorted(lexeme_target.items()):
            if target not in ("new", "legacy"):
                events += [(at, rating, "lexeme", lex, sid, k) for k, (at, rating) in
                           enumerate(plan_card(rng, "lexeme", T, lex, target, 1 + rng.randrange(14)))]
        events.sort(key=lambda e: (e[0], e[2], e[3]))
        cache = None
        if fast:
            cache = IntroducedCache(connection, T)
            stack.enter_context(mock.patch.object(reviews, "introduced_on", cache.introduced_on))
        version: dict[tuple, int] = {}
        for n, (at, rating, kind, ref, sid, k) in enumerate(events):
            clock.at = at
            key = (kind, ref)
            rid = f"e6-{kind[0]}{ref}-{k}"
            if cache is not None:
                cache.saw(key, at)        # the review writes its log before counting "introduced"
            if kind == "personal":
                vocab.record_review(T, ref, rating, request_id=rid, expected_card_version=version.get(key, 0),
                                    session_id="e6")
            elif k == 0:
                lexemes.record_lexeme_review(T, ref, rating, sid, request_id=rid, session_id="e6", first_review=True)
            else:
                lexemes.record_lexeme_review(T, ref, rating, sid, request_id=rid,
                                             expected_card_version=version[key], session_id="e6")
            version[key] = version.get(key, 0) + 1
        timings["reviews_s"] = time.perf_counter() - started - timings["cards_s"]

    # ---- the generator's own expectations (from the rules, not from the queue) ----
    today = T_REF.astimezone(SEOUL).date()
    first_today = {(kind, ref) for at, _, kind, ref, _, k in events if k == 0 and at.astimezone(SEOUL).date() == today}
    category = {"new": None, "learning": "learning_due", "relearning": "relearning_due", "review_today": "review_due",
                "overdue": "review_due", "later": "pending_later", "legacy": "not_converted"}

    def counts(items, kind):
        out = {}
        for target in items:
            name = category[target] or ("new_available" if kind == "personal" else "new_unmaterialized")
            out[name] = out.get(name, 0) + 1
        return out

    p_all = [t for t, _ in personal.values()]
    s_all = [t for t, _ in lexeme_target.values()]
    merged = counts(p_all, "personal")
    for name, value in counts(s_all, "lexeme").items():
        merged[name] = merged.get(name, 0) + value
    due_now = sorted(ref for ref, (t, _) in personal.items() if t in ("learning", "relearning", "review_today", "overdue"))
    expected.update(
        user_id=T, personal_decks=p_decks, shared_decks=shared_ids,
        queue_all=merged,
        queue_personal_deck=counts([t for t, d in personal.values() if d == p_decks[0]], "personal"),
        queue_subscribed_deck=counts([t for t, s in lexeme_target.values() if s == shared_ids[0]], "lexeme"),
        due_now_all=due_now,
        due_now_deck=sorted(ref for ref in due_now if personal[ref][1] == p_decks[0]),
        personal_cards=len(personal), personal_cards_deck=sum(d == p_decks[0] for _, d in personal.values()),
        subscribed_words=len(lexeme_target),
        fsrs_logs=len(events), legacy_logs=legacy_logs,
        reviews_today=sum(at.astimezone(SEOUL).date() == today for at, *_ in events),
        introduced_today=len(first_today),
        targets={"personal": {t: p_all.count(t) for t in SHARE}, "subscribed": {t: s_all.count(t) for t in SHARE}},
    )
    return {"expected": expected, "timings": timings}


# ---- scenarios -----------------------------------------------------------------------------
def scenarios(exp):
    p, s = exp["personal_decks"][0], exp["shared_decks"][0]
    return {
        "queue_all": ("/study-queue", {}),
        "queue_personal_deck": ("/study-queue", {"scope": "personal_deck", "deck_id": p}),
        "queue_subscribed_deck": ("/study-queue", {"scope": "subscribed_deck", "deck_id": s}),
        "queue_all_limit100": ("/study-queue", {"limit": 100}),
        "stats_all": ("/stats", {}),
        "stats_deck": ("/stats", {"deck_id": p}),
        "due_now_all": ("/vocab-items", {"due_only": "true"}),
        "due_now_deck": ("/vocab-items", {"due_only": "true", "deck_id": p}),
    }


def token(user_id):
    from app.auth import create_access_token

    return create_access_token({"id": user_id, "email": "e6-target@e6.example.test"})


class Client:
    """One event loop and one ASGI client for every call (no per-call setup in the timing)."""

    def __init__(self, user_id):
        import httpx
        from app import main

        self.loop = asyncio.new_event_loop()
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://e6")
        self.headers = {"Authorization": "Bearer " + token(user_id)}

    def get(self, path, params):
        return self.loop.run_until_complete(self.client.get(path, params=params, headers=self.headers))

    def close(self):
        self.loop.run_until_complete(self.client.aclose())
        self.loop.close()


def check_expectations(exp, responses) -> list[str]:
    """Generator rules vs the API answers. Returns the mismatches (empty = all equal)."""
    bad = []

    def same(name, got, want):
        if got != want:
            bad.append(f"{name}: got {got!r} want {want!r}")

    for name in ("queue_all", "queue_personal_deck", "queue_subscribed_deck"):
        counts = responses[name]["counts"]
        got = {k: v for k, v in counts.items() if v and k not in ("total_in_scope", "new_allowed_now",
                                                                   "excluded_by_request")}
        same(name + ".counts", got, exp[name])
        same(name + ".total", counts["total_in_scope"], sum(exp[name].values()))
    same("queue_all_limit100.counts", responses["queue_all_limit100"]["counts"], responses["queue_all"]["counts"])
    for name in ("due_now_all", "due_now_deck"):
        same(name, sorted(item["id"] for item in responses[name]["items"]), exp[name])
    same("stats_all.total_count", responses["stats_all"]["total_count"], exp["personal_cards"])
    same("stats_deck.total_count", responses["stats_deck"]["total_count"], exp["personal_cards_deck"])
    today = responses["stats_all"]["today_seoul"]
    same("stats.today_seoul.reviews", (today["reviews"]["status"], today["reviews"]["total"]), ("exact", exp["reviews_today"]))
    same("stats.today_seoul.introduced", (today["introduced"]["status"], today["introduced"]["count"]),
         ("exact", exp["introduced_today"]))
    return bad


# ---- per-database pieces (overridden by the PG class) ----------------------------------------
class BenchBase:
    db_kind = "sqlite"

    def tables(self) -> list[str]:
        rows = self.sql("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name")
        return [r["name"] for r in rows]

    def sql(self, query, params=()):
        from app.database import get_connection

        with get_connection() as c:
            cur = c.execute(query, params)
            return [dict(r) for r in cur.fetchall()] if cur.description else []

    def content_hash(self) -> dict[str, Any]:
        out = {}
        for table in self.tables():
            rows = self.sql(f"SELECT * FROM {table} ORDER BY 1")
            digest = hashlib.sha256()
            for row in rows:
                digest.update(repr(sorted(row.items())).encode())
            out[table] = (len(rows), digest.hexdigest())
        return out

    def analyze(self):
        self.sql("ANALYZE")

    @contextmanager
    def read_only(self):
        path = self.db_path
        os.chmod(path, stat.S_IREAD)
        try:
            yield
        finally:
            os.chmod(path, stat.S_IREAD | stat.S_IWRITE)

    def explain(self, query, params):
        rows = self.sql("EXPLAIN QUERY PLAN " + query, params)
        return [r["detail"] for r in rows]


def _summary(values):
    ordered = sorted(values)
    p95 = ordered[min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1))))]
    return {"median_ms": round(statistics.median(ordered) * 1000, 2), "p95_ms": round(p95 * 1000, 2),
            "min_ms": round(ordered[0] * 1000, 2), "max_ms": round(ordered[-1] * 1000, 2), "n": len(ordered)}


class Diagnostics:
    """Separate run only: counts SQL statements / rows per request and times each statement."""

    def __init__(self):
        self.calls = []

    @contextmanager
    def active(self):
        from app import database

        diag = self

        class Proxy:
            def __init__(self, cursor, entry):
                self._cursor, self._entry = cursor, entry

            def _timed(self, fn, count):
                t0 = time.perf_counter()
                result = fn()
                self._entry["s"] += time.perf_counter() - t0
                self._entry["rows"] += count(result)
                return result

            def fetchall(self):
                return self._timed(self._cursor.fetchall, len)

            def fetchone(self):
                return self._timed(self._cursor.fetchone, lambda r: int(r is not None))

            def __iter__(self):
                return iter(self.fetchall())

            def __getattr__(self, name):
                return getattr(self._cursor, name)

        def wrap(real):
            def execute(connection, query, params=()):
                t0 = time.perf_counter()
                cursor = real(connection, query, params)
                entry = {"sql": " ".join(str(query).split()), "params": tuple(params), "s": time.perf_counter() - t0,
                         "rows": 0}
                diag.calls.append(entry)
                return Proxy(cursor, entry)
            return execute

        with mock.patch.object(database.AppSQLiteConnection, "execute", wrap(database.AppSQLiteConnection.execute)), \
                mock.patch.object(database.AppPostgresConnection, "execute", wrap(database.AppPostgresConnection.execute)):
            yield


class ConnectionDiagnostics:
    """PG diagnostic run only (E-6 correction): per request, every app connection the E-1/E-2
    guard opens, timed at nested points without changing what runs. Nothing is skipped or
    bypassed: the guard's own pre-connect checks and on-connection verification (target /
    marker queries + rollback) still run; they are only timed.

      open      _GuardedPsycopg.connect, the whole hand-over, which CONTAINS:
        guarded   run._guarded_connect = pre-connect checks + driver connect, which CONTAINS:
          driver  run._connect (libpq connect, SSPI)
        verify    run.verify_app_connection (3 queries + rollback on that connection)
      close     AppPostgresConnection.__exit__ (the app's commit / rollback + close)

    The timed points never overlap within one request's single thread except by the
    containment above, so sums per level are not double counted."""

    def __init__(self, run):
        self.run = run
        self.events: list[tuple[str, float]] = []

    @contextmanager
    def active(self):
        import _srs_e2_adapter as adapter
        from app import database

        events = self.events

        def timed(name, fn):
            def wrapper(*args, **kwargs):
                t0 = time.perf_counter()
                try:
                    return fn(*args, **kwargs)
                finally:
                    events.append((name, time.perf_counter() - t0))
            return wrapper

        real_open, real_exit = adapter._GuardedPsycopg.connect, database.AppPostgresConnection.__exit__
        with mock.patch.object(self.run, "_connect", timed("driver", self.run._connect)),                 mock.patch.object(self.run, "_guarded_connect", timed("guarded", self.run._guarded_connect)),                 mock.patch.object(self.run, "verify_app_connection", timed("verify", self.run.verify_app_connection)),                 mock.patch.object(adapter._GuardedPsycopg, "connect", timed("open", real_open)),                 mock.patch.object(database.AppPostgresConnection, "__exit__", timed("close", real_exit)):
            yield

    def take(self) -> dict[str, Any]:
        """This request's events, then cleared."""
        out: dict[str, Any] = {"connections": sum(1 for n, _ in self.events if n == "open")}
        for name in ("open", "guarded", "driver", "verify", "close"):
            out[name + "_ms"] = round(sum(t for n, t in self.events if n == name) * 1000, 2)
        self.events.clear()
        return out


class BenchCase(BenchBase):
    def run_size(self, size):
        record: dict[str, Any] = {"db": self.db_kind, "size": size, "seed": SEED, "t_ref": T_REF.isoformat(),
                                  "warmup": WARMUP, "repeat": REPEAT}
        t0 = time.perf_counter()
        world = build_world(size)
        exp = world["expected"]
        record["prep"] = {**{k: round(v, 2) for k, v in world["timings"].items()},
                          "generate_s": round(time.perf_counter() - t0, 2)}
        t1 = time.perf_counter()
        self.analyze()
        record["prep"]["analyze_s"] = round(time.perf_counter() - t1, 2)

        clock = Clock(T_REF)
        with fixed_clock(clock), mock.patch.dict(os.environ, {"JWT_SECRET_KEY": SECRET}):
            t2 = time.perf_counter()
            from app.database import get_connection
            from app.srs import invariant_audit

            with get_connection() as c:
                with invariant_audit.read_snapshot(c):
                    report = invariant_audit.audit(c)
            failed = {k: v["status"] for k, v in report["checks"].items() if v["status"] not in ("pass", "not_evaluated")}
            self.assertEqual(failed, {}, report)
            record["audit"] = {k: v["status"] for k, v in report["checks"].items()}
            plan = scenarios(exp)
            client = Client(exp["user_id"])
            try:
                responses, bodies = {}, {}
                for name, (path, params) in plan.items():
                    response = client.get(path, params)
                    self.assertEqual(response.status_code, 200, (name, response.text[:300]))
                    responses[name], bodies[name] = response.json(), response.content
                mismatches = check_expectations(exp, responses)
                self.assertEqual(mismatches, [], mismatches)
                record["expected"] = {k: v for k, v in exp.items() if k not in ("due_now_all", "due_now_deck")}
                record["expected"]["due_now_all"] = len(exp["due_now_all"])
                record["response_sha256"] = {n: hashlib.sha256(b).hexdigest() for n, b in bodies.items()}
                before = self.content_hash()
                record["rows"] = {t: n for t, (n, _) in before.items()}
                record["prep"]["verify_s"] = round(time.perf_counter() - t2, 2)

                with self.read_only():
                    timings = {}
                    for name, (path, params) in plan.items():
                        samples = []
                        for i in range(WARMUP + REPEAT):
                            s0 = time.perf_counter()
                            response = client.get(path, params)
                            elapsed = time.perf_counter() - s0
                            if response.status_code != 200 or response.content != bodies[name]:
                                raise AssertionError(f"{name}: answer changed during timing ({response.status_code})")
                            if i >= WARMUP:
                                samples.append(elapsed)
                        timings[name] = {**_summary(samples), "bytes": len(bodies[name]),
                                         "items": len(responses[name].get("items", []))}
                    record["requests"] = timings
                    record["internal"] = self.internal(exp)
                    record["diagnostic"] = self.diagnose(client, plan, bodies)
                after = self.content_hash()
                self.assertEqual(after, before)
                again = {name: client.get(path, params).content for name, (path, params) in plan.items()}
                self.assertEqual(again, bodies)
                record["unchanged_after"] = True
            finally:
                client.close()
        out = os.environ.get("E6_OUT")
        if out:
            Path(out).mkdir(parents=True, exist_ok=True)
            Path(out, f"e6_{self.db_kind}_{size}.json").write_text(json.dumps(record, indent=1, default=str),
                                                                   encoding="utf-8")
        return record

    def internal(self, exp):
        """Shared inner reads, timed on their own (NOT to be added to the request times)."""
        from app.database import get_connection
        from app.srs import goals, identity, queue, readability

        user = exp["user_id"]
        request = queue.QueueRequest(user, "all", None, "today", (), 20, None, None)
        steps = {
            "read_personal_cards": lambda c: queue._read_personal(c, request),
            "read_subscribed_cards": lambda c: queue._read_lexemes(c, request),
            "first_review_dates": lambda c: goals.first_review_dates(c, user),
            "unreadable_history_keys": lambda c: readability.unreadable_history_keys(c, user),
            "flagged_personal_ids": lambda c: identity.flagged_personal_ids(c, user),
            "introduction_count": lambda c: goals.introduction_count(c, user, T_REF),
            "personal_due_now_ids": lambda c: queue.personal_due_now_ids(c, user, None, T_REF),
        }
        out = {}
        with get_connection(read_only=True) as connection:
            for name, step in steps.items():
                samples = []
                for i in range(WARMUP + REPEAT):
                    s0 = time.perf_counter()
                    step(connection)
                    if i >= WARMUP:
                        samples.append(time.perf_counter() - s0)
                out[name] = _summary(samples)
        return out

    def diagnose(self, client, plan, bodies):
        out = {}
        for name, (path, params) in plan.items():
            diag = Diagnostics()
            with diag.active():
                response = client.get(path, params)
            self.assertEqual(response.content, bodies[name])
            top = sorted(diag.calls, key=lambda e: -e["s"])[:2]
            plans = []
            for entry in top:
                if entry["sql"].upper().startswith(("SELECT", "WITH")):
                    plans.append({"ms": round(entry["s"] * 1000, 2), "rows": entry["rows"],
                                  "sql": entry["sql"][:160], "plan": self.explain(entry["sql"], entry["params"])})
            out[name] = {"statements": len(diag.calls), "rows": sum(e["rows"] for e in diag.calls),
                         "sql_ms": round(sum(e["s"] for e in diag.calls) * 1000, 2), "top": plans}
        return out


class SqliteBench(BenchCase, unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="jp_vocab_e6_", dir=BACKEND)
        self.addCleanup(directory.cleanup)
        self.db_path = Path(directory.name) / "e6_synthetic.db"
        env = mock.patch.dict(os.environ, {"APP_ENV": "test", "DATABASE_URL": f"sqlite:///{self.db_path.as_posix()}",
                                           "JWT_SECRET_KEY": SECRET})
        env.start()
        self.addCleanup(env.stop)
        from app.database import init_db
        with fixed_clock(Clock(T_CREATE)):        # the dev account rows too: same on every run
            init_db()

    def test_1000(self):
        self.run_size(1000)

    def test_10000(self):
        self.run_size(10000)


def _pg_classes():
    import test_srs_e3_fk_real as pg

    class PgBench(BenchCase, pg.RealCase):
        db_kind = "postgresql"

        def setUp(self):
            super().setUp()
            env = mock.patch.dict(os.environ, {"JWT_SECRET_KEY": SECRET})
            env.start()
            self.addCleanup(env.stop)
            self.create()

        def tables(self):
            return sorted(self.run.owned)

        def analyze(self):
            for table in self.tables():
                self.sql(f"ANALYZE {table}")

        @contextmanager
        def read_only(self):
            with mock.patch.dict(os.environ, {"PGOPTIONS": "-c default_transaction_read_only=on"}):
                rows = self.sql("SHOW default_transaction_read_only")
                assert rows[0]["default_transaction_read_only"] == "on", rows
                yield

        def explain(self, query, params):
            rows = self.sql("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + query, params)
            root = rows[0]["QUERY PLAN"][0]
            nodes = []

            def walk(node):
                nodes.append(" ".join(str(x) for x in (
                    node.get("Node Type"), node.get("Relation Name") or "", node.get("Index Name") or "",
                    f"rows={node.get('Actual Rows')}", f"ms={node.get('Actual Total Time')}") if x != ""))
                for child in node.get("Plans", []):
                    walk(child)
            walk(root["Plan"])
            return {"execution_ms": root.get("Execution Time"), "nodes": nodes[:12]}

        def test_1000(self):
            self.run_size(1000)

        def test_queue_connection_diagnostic_1000(self):
            """E-6 correction: /study-queue (scope all) only, 1,000 cards, warm-up 3 + 10 runs,
            connection count and guard / driver / verify / close times per request."""
            world = build_world(1000)
            exp = world["expected"]
            self.analyze()
            path, params = scenarios(exp)["queue_all"]
            record: dict[str, Any] = {"db": self.db_kind, "size": 1000, "scenario": "queue_all",
                                      "warmup": 3, "runs": 10}
            with fixed_clock(Clock(T_REF)), mock.patch.dict(os.environ, {"JWT_SECRET_KEY": SECRET}):
                from app.database import get_connection
                from app.srs import invariant_audit

                with get_connection() as c:
                    with invariant_audit.read_snapshot(c):
                        report = invariant_audit.audit(c)
                self.assertEqual({k: v["status"] for k, v in report["checks"].items()
                                  if v["status"] not in ("pass", "not_evaluated")}, {})
                client = Client(exp["user_id"])
                try:
                    first = client.get(path, params)
                    self.assertEqual(first.status_code, 200)
                    counts = {k: v for k, v in first.json()["counts"].items()
                              if v and k not in ("total_in_scope", "new_allowed_now", "excluded_by_request")}
                    self.assertEqual(counts, exp["queue_all"])
                    before = self.content_hash()
                    diag = ConnectionDiagnostics(self.run)
                    rows = []
                    with self.read_only(), diag.active():
                        for i in range(3 + 10):
                            diag.events.clear()
                            s0 = time.perf_counter()
                            response = client.get(path, params)
                            total = time.perf_counter() - s0
                            self.assertEqual((response.status_code, response.content), (200, first.content))
                            entry = {"request_ms": round(total * 1000, 2), **diag.take()}
                            if i >= 3:
                                rows.append(entry)
                    self.assertEqual(self.content_hash(), before)
                    self.assertEqual(client.get(path, params).content, first.content)
                finally:
                    client.close()
            record["per_request"] = rows
            record["median"] = {k: round(statistics.median(r[k] for r in rows), 2) for k in rows[0]}
            out = os.environ.get("E6_OUT")
            if out:
                Path(out).mkdir(parents=True, exist_ok=True)
                Path(out, "e6_pg_queue_connections_1000.json").write_text(json.dumps(record, indent=1), encoding="utf-8")

        def test_10000(self):
            self.run_size(10000)

    return PgBench


try:
    import test_srs_e3_fk_real as _pg

    if _pg._opt_in():
        PgBench = _pg_classes()
except ImportError:  # pragma: no cover
    pass


if __name__ == "__main__":
    unittest.main()

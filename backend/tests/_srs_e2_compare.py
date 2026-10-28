"""Gate E-2a: one synthetic scenario, run on SQLite and (later, E-2) on the protected local
PostgreSQL test database, observed in an engine-neutral form and compared.
Test code only. Design and rules: docs/plans/srs-improvement/gate-e/EXECUTION_PLAN.md 2-1.

Inputs and observations are separate:
- inputs are fixed here (users, cards, ratings, request ids, clock instants);
- each stage returns observations built from the app's own HTTP routes, repository / SRS
  functions and table reads -- no product logic is copied.

Normalization (only these, nothing else is relaxed):
- ids: every database id is replaced by the logical label the scenario gave that object
  (user, deck, card, log "<card>#<n>", run "<run_key>") -- references are compared through
  the labels, so the numbers themselves never matter but a reference to the wrong object
  does. Labels are registered only for objects the scenario created, from the database
  (owning account; for logs, their card). An id that cannot be proven that way -- never
  registered, of another kind, of another account, a log of another card -- raises
  NotComparable. There is no "first seen" fallback.
- reference fields: an integer id only (never a string -- even one equal to a label --,
  bool, float, object or array); NULL only for deck_id, shared_deck_id, review_log_id and
  evidence_from_log_id; last_log_id 0 means "no log". Labels are Ref objects, so a raw
  string never compares equal to a label.
- sort_key: the queue contract [bucket, time, kind rank, order, card id]; only the last
  position becomes a label, the others are compared as they are; any other shape raises
  NotComparable.
- time strings: parsed and written back as UTC ISO-8601 with microseconds.
- JSON strings ("{..." / "[..."): parsed and normalized recursively.
- bool: written as 0/1 (SQLite has no boolean type).
- API paths ("/study-items/<id>/review", "/shared-decks/<id>/words/<id>/..."): the ids in
  them become labels like any other id.
- id-derived hashes (card / log fingerprints) and the signed queue cursor: compared as
  presence only, because they hash database ids. Documented, not silent.
Order of lists (queue order, log order, results) is kept. Versions, counts, statuses, error
codes, permissions and completion evidence are compared exactly.

Stages (EXECUTION_PLAN check list): upgrade -> review -> queue -> migration -> completion.
Nothing here touches D-P1 (log FK) or account deletion: both are unapproved.
"""

from __future__ import annotations

import json
import os
import re
from contextlib import ExitStack
from dataclasses import asdict, is_dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from unittest import mock

UTC = timezone.utc
DAY = timedelta(days=1)
T0 = datetime(2026, 6, 1, 3, 0, tzinfo=UTC)  # 12:00 KST
STAGES = ("upgrade", "review", "queue", "migration", "completion")
SECRET = "e2a-synthetic-jwt-key-not-a-real-key"
CARD_COLS = ("srs_engine", "srs_card_version", "srs_state", "srs_stability", "srs_effective_due_at",
             "srs_participation", "srs_history_quality", "evidence_from_log_id", "history_intro_status",
             "completion_metric_version", "first_completed_at", "first_completed_source",
             "version_first_completed_at", "version_first_completed_version", "review_level", "next_review_at",
             "correct_count", "wrong_count", "status")
LOG_COLS = ("rating", "reviewed_at", "request_id", "srs_engine", "card_version_before", "srs_after_json", "seoul_date",
            "is_first_review",
            "previous_review_level", "next_review_level")
ID_NAMESPACES = {"user_id": "user", "owner_user_id": "user", "deck_id": "deck", "vocab_item_id": "personal",
                 "lexeme_id": "lexeme", "shared_deck_id": "shared_deck", "review_log_id": "log",
                 "last_log_id": "log", "evidence_from_log_id": "log", "run_id": "run", "source_run_id": "run",
                 "previous_boundary": "log", "new_boundary": "log"}
AMBIGUOUS_ID_KEYS = {"id", "card_id", "card_ref", "ref_id", "item_id"}
PRESENCE_ONLY = {"card_fingerprint", "logs_fingerprint", "next_cursor", "request_hash"}
PATH_NAMESPACES = {"study-items": "personal", "vocab-items": "personal", "words": "lexeme",
                   "shared-decks": "shared_deck", "decks": "deck"}  # path segment -> object kind
_PATH_ID = re.compile(r"/(study-items|vocab-items|words|shared-decks|decks)/(\d+)(?=/|$)")
_TIME = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}")


# ---------------------------------------------------------------- normalization ----
LOG_REF_KEYS = {"review_log_id", "last_log_id", "evidence_from_log_id", "previous_boundary", "new_boundary"}
CARD_REF_KEYS = {"card_id", "card_ref", "ref_id", "item_id", "id"}
# Field contracts (E-2a review): every reference is an integer id (never bool / float /
# string / object / array). NULL only where the field allows it; last_log_id uses 0 for
# "no log" (MigrationCandidate.last_log_id: max(log ids, default=0)).
NULLABLE_REF_KEYS = {"deck_id", "shared_deck_id", "review_log_id", "evidence_from_log_id"}
ZERO_IS_NONE_KEYS = {"last_log_id"}


class Ref(str):
    """A logical label standing for a database reference. Distinct from any raw string:
    compare() treats Ref("card-x") and "card-x" as different."""

    __slots__ = ()

    def __repr__(self) -> str:
        return f"Ref({str.__repr__(self)})"


NO_LOG = Ref("<none:0>")


class NotComparable(AssertionError):
    """An observation cannot be compared: a reference the scenario cannot prove, or a
    value whose shape is not the contract. Never turned into a label or a pass."""


class Labels:
    """Logical names for objects the scenario itself created, registered from the database
    (the owning account, and for logs the card they belong to)."""

    def __init__(self) -> None:
        self._by_ns: dict[str, dict[int, str]] = {}
        self._meta: dict[tuple[str, str], dict[str, Any]] = {}

    def put(self, namespace: str, ident: int, label: str, *, owner: str | None = None,
            card: tuple[str, str] | None = None) -> None:
        if isinstance(ident, bool) or not isinstance(ident, int):
            raise NotComparable(f"{namespace} id to register is not an integer")
        existing = self._by_ns.get(namespace, {}).get(ident)
        if existing is not None and existing != label:
            raise NotComparable(f"one {namespace} object registered under two names")
        meta = self._meta.get((namespace, label))
        if meta is not None and (meta["ident"] != ident or meta["owner"] != owner or meta["card"] != card):
            raise NotComparable(f"one {namespace} name registered for two objects")
        self._by_ns.setdefault(namespace, {})[ident] = Ref(label)
        self._meta[(namespace, label)] = {"ident": ident, "owner": owner, "card": card}

    def name(self, namespace: str, ident: Any) -> Any:
        if ident is None:
            return None
        if isinstance(ident, bool) or not isinstance(ident, int):
            raise NotComparable(f"{namespace} reference is not an integer id")
        label = self._by_ns.get(namespace, {}).get(ident)
        if label is None:
            raise NotComparable(f"unregistered {namespace} reference")
        return label

    def owner(self, namespace: str, label: str) -> str | None:
        return self._meta.get((namespace, label), {}).get("owner")

    def card_of_log(self, label: str) -> tuple[str, str] | None:
        return self._meta.get(("log", label), {}).get("card")


def _ref(labels: "Labels", key: str, namespace: str, value: Any) -> Any:
    """One reference field, checked against its contract before it becomes a label."""
    if value is None:
        if key in NULLABLE_REF_KEYS:
            return None
        raise NotComparable(f"{key} may not be NULL")
    if isinstance(value, bool) or not isinstance(value, int):
        raise NotComparable(f"{key} is not an integer id")
    if value == 0 and key in ZERO_IS_NONE_KEYS:
        return NO_LOG
    return labels.name(namespace, value)


def _time(text: str) -> str:
    try:
        value = datetime.fromisoformat(text.replace(" ", "T").replace("Z", "+00:00"))
    except ValueError:
        return text
    if value.tzinfo is None:
        return text  # a naive time is reported as written, never guessed
    return value.astimezone(UTC).isoformat(timespec="microseconds")


def _sort_key(raw: Any, kind: str | None, card_id: Any, labels: Labels) -> list[Any]:
    """app/srs/queue.py contract: [bucket, time, kind rank, order in deck, card id]
    (queue._key_json). Only position 4 is an id; every other position is compared as is."""
    from app.srs.queue import KIND_RANK

    def is_int(v: Any) -> bool:
        return isinstance(v, int) and not isinstance(v, bool)

    if not (isinstance(raw, list) and len(raw) == 5 and kind in KIND_RANK and is_int(raw[0])
            and isinstance(raw[1], str) and is_int(raw[2]) and raw[2] == KIND_RANK[kind] and is_int(raw[3])
            and is_int(raw[4]) and is_int(card_id) and raw[4] == card_id):
        raise NotComparable("sort_key does not have the queue's [bucket, time, rank, order, card id] shape")
    return [raw[0], _time(raw[1]), raw[2], raw[3], labels.name(kind, raw[4])]


def normalize(value: Any, labels: Labels, key: str | None = None, kind: str | None = None,
              context: dict[str, Any] | None = None) -> Any:
    """`context` names the card / account an observation belongs to when the row itself
    does not carry them (e.g. a card's own row): {"card": (kind, label), "user": label}."""
    if key in PRESENCE_ONLY:
        return None if value is None else "<present>"
    if is_dataclass(value) and not isinstance(value, type):
        value = asdict(value)
    if isinstance(value, dict):
        return _normalize_row(value, labels, kind, context)
    if isinstance(value, (list, tuple)):
        return [normalize(v, labels, None, kind, context) for v in value]
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, str):
        stripped = value.strip()
        if stripped[:1] in "{[":
            try:
                return normalize(json.loads(stripped), labels, key, kind, context)
            except ValueError:
                return value
        if _TIME.match(stripped):
            return _time(stripped)
        if stripped.startswith("/"):
            return _PATH_ID.sub(lambda m: f"/{m.group(1)}/" + labels.name(PATH_NAMESPACES[m.group(1)],
                                                                           int(m.group(2))), stripped)
    return value


def _normalize_row(row: dict[str, Any], labels: Labels, kind: str | None, context: dict[str, Any] | None) -> Any:
    row_kind = row.get("card_kind") or row.get("kind")
    row_kind = row_kind if row_kind in ("personal", "lexeme") else kind
    out: dict[str, Any] = {}
    for k, v in row.items():
        if k == "sort_key":
            continue
        if k in ID_NAMESPACES:
            out[k] = _ref(labels, k, ID_NAMESPACES[k], v)
        elif k in CARD_REF_KEYS:
            if row_kind not in ("personal", "lexeme"):
                raise NotComparable(f"{k} without a card kind")
            out[k] = _ref(labels, k, row_kind, v)
        else:
            out[k] = normalize(v, labels, k, row_kind, None)
    if "sort_key" in row:
        out["sort_key"] = _sort_key(row["sort_key"], row_kind, row.get("card_id"), labels)
    # relations inside one observation: card <-> account, log <-> card / account
    card = next(((row_kind, out[k]) for k in ("card_id", "ref_id", "card_ref", "item_id", "id") if k in out
                 and out[k] is not None), None)
    if row_kind == "personal" and out.get("vocab_item_id"):
        card = card or ("personal", out["vocab_item_id"])
    user = out.get("user_id")
    if context:
        card = card or context.get("card")
        user = user or context.get("user")
    if card and user and labels.owner(card[0], card[1]) not in (None, user):
        raise NotComparable("card reference belongs to another account")
    for k in LOG_REF_KEYS & set(out):
        if out[k] is None or out[k] is NO_LOG:
            continue
        log_card = labels.card_of_log(out[k])
        if card and log_card != card:
            raise NotComparable("log reference belongs to another card")
        if user and labels.owner("log", out[k]) not in (None, user):
            raise NotComparable("log reference belongs to another account")
    return out


def compare(a: Any, b: Any, path: str = "") -> list[tuple[str, Any, Any]]:
    """Every difference, with its path. No tolerance."""
    if isinstance(a, dict) and isinstance(b, dict):
        out: list[tuple[str, Any, Any]] = []
        for k in sorted(set(a) | set(b), key=str):
            if k not in a or k not in b:
                out.append((f"{path}/{k}", a.get(k, "<missing>"), b.get(k, "<missing>")))
            else:
                out.extend(compare(a[k], b[k], f"{path}/{k}"))
        return out
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return [(f"{path}#len", len(a), len(b))] + [d for i, (x, y) in enumerate(zip(a, b))
                                                          for d in compare(x, y, f"{path}[{i}]")]
        return [d for i, (x, y) in enumerate(zip(a, b)) for d in compare(x, y, f"{path}[{i}]")]
    return [] if a == b and type(a) is type(b) else [(path, a, b)]


# ------------------------------------------------------------------- scenario ----
class Scenario:
    """Drives the real app. `engine` is "sqlite" or "postgresql"; `run` is the E-1 PgRun
    for PostgreSQL (schema through the managed step). The caller provides the database
    scope (a session SQLite file, or adapter.app_scope(run))."""

    def __init__(self, engine: str, run: Any = None) -> None:
        from fastapi.testclient import TestClient

        from app import main

        self.engine, self.run = engine, run
        self.labels = Labels()
        self.clock = T0
        self.client = TestClient(main.app)
        self._stack = ExitStack()
        self._req: dict[str, int] = {}  # per card, so a stage's inputs do not depend on earlier stages
        self._log_seen: dict[str, list[int]] = {}

    def __enter__(self) -> "Scenario":
        import app.database as database
        from app.repositories import (learning_plan_repository, lexeme_repository, stats_history_repository,
                                      stats_repository, vocab_repository)
        from app.srs import migration, queue, reviews

        self._stack.enter_context(mock.patch.dict(os.environ, {"JWT_SECRET_KEY": SECRET}))
        for module in (database, reviews, migration, queue, vocab_repository, lexeme_repository, stats_repository,
                       stats_history_repository, learning_plan_repository):
            self._stack.enter_context(mock.patch.object(module, "now_utc", side_effect=lambda: self.clock))
        return self

    def __exit__(self, *exc: Any) -> None:
        self.client.close()
        self._stack.close()

    # ---- helpers (inputs) ---------------------------------------------------
    def sql(self, statement: str, params: tuple = ()) -> list[dict[str, Any]]:
        from app.database import get_connection

        with get_connection() as c:
            cursor = c.execute(statement, params)
            try:
                return [dict(r) for r in cursor.fetchall()]
            except Exception:
                return []

    def user(self, label: str) -> int:
        from app.repositories.user_repository import create_user

        email = f"{label}@e2a.example.test"
        ident = create_user(email=email, display_name=label, password_hash="x")["id"]
        rows = self.sql("SELECT id FROM users WHERE email = ?", (email,))  # confirmed in the database
        if [r["id"] for r in rows] != [ident]:
            raise NotComparable("created account not found as one row")
        self.labels.put("user", ident, label)
        return ident

    def headers(self, user: int) -> dict[str, str]:
        from app.auth import create_access_token

        return {"Authorization": "Bearer " + create_access_token({"id": user, "email": "e2a@example.test"})}

    def set_mode(self, user: int, mode: str) -> None:
        stamp = self.clock.isoformat()
        self.sql("DELETE FROM srs_user_settings WHERE user_id = ?", (user,))
        self.sql("INSERT INTO srs_user_settings (user_id, srs_mode, daily_new_goal, settings_version, created_at, "
                 "updated_at) VALUES (?, ?, 20, 0, ?, ?)", (user, mode, stamp, stamp))

    def card(self, user: int, label: str) -> int:
        response = self.client.post("/vocab-items", headers=self.headers(user), json={
            "surface": label, "base_form": label, "reading": f"{label}-r", "meaning_ko": f"{label}-m",
            "status": "unknown"})
        assert response.status_code == 200, response.status_code
        ident = int(response.json()["id"])
        owner = self.labels.name("user", user)
        rows = self.sql("SELECT v.user_id AS card_user, v.deck_id, d.user_id AS deck_user FROM vocab_items v "
                        "JOIN decks d ON d.id = v.deck_id WHERE v.id = ?", (ident,))  # confirmed in the database
        if len(rows) != 1 or rows[0]["card_user"] != user or rows[0]["deck_user"] != user:
            raise NotComparable("created card is not this account's card in this account's deck")
        self.labels.put("personal", ident, label, owner=owner)
        self.labels.put("deck", rows[0]["deck_id"], f"{owner}-default", owner=owner)
        return ident

    def version(self, ref: int) -> int | None:
        rows = self.sql("SELECT srs_card_version FROM vocab_items WHERE id = ?", (ref,))
        return rows[0]["srs_card_version"] if rows else None

    def review(self, user: int, ref: int, rating: str = "good", *, request: str | None = None,
               version: Any = "current", legacy: bool = False) -> dict[str, Any]:
        if version == "current":
            version = self.version(ref)
        card = self.labels.name("personal", ref)
        self._req[card] = self._req.get(card, 0) + 1
        request = request or f"e2a-{card}-{self._req[card]}"
        body = {"rating": rating} if legacy else {"rating": rating, "request_id": request, "session_id": "e2a",
                                                  "expected_card_version": version}
        response = self.client.post(f"/study-items/{ref}/review", headers=self.headers(user), json=body)
        self.label_logs(ref)
        return {"status": response.status_code, "raw": response.content, "body": response.json()}

    def label_logs(self, ref: int) -> None:
        """Logs of a card the scenario created, read from the database with their account;
        a log of another account under this card id is not labelled -- it is an error."""
        label = self.labels.name("personal", ref)
        owner = self.labels.owner("personal", label)
        for n, r in enumerate(self.sql("SELECT l.id, u.email FROM review_logs l JOIN users u ON u.id = l.user_id "
                                       "WHERE l.vocab_item_id = ? ORDER BY l.id", (ref,)), 1):
            if r["email"] != f"{owner}@e2a.example.test":
                raise NotComparable("a log under this card id belongs to another account")
            self.labels.put("log", r["id"], f"{label}#{n}", owner=owner, card=("personal", label))

    # ---- observations -------------------------------------------------------
    def n(self, value: Any, key: str | None = None, context: dict[str, Any] | None = None) -> Any:
        return normalize(value, self.labels, key, context=context)

    def card_context(self, ref: int) -> dict[str, Any]:
        label = self.labels.name("personal", ref)
        return {"card": ("personal", label), "user": self.labels.owner("personal", label)}

    def card_view(self, ref: int) -> Any:
        self.label_logs(ref)
        rows = self.sql(f"SELECT {', '.join(CARD_COLS)} FROM vocab_items WHERE id = ?", (ref,))
        return self.n(rows[0], context=self.card_context(ref)) if rows else None

    def log_view(self, ref: int) -> Any:
        self.label_logs(ref)
        return self.n(self.sql(f"SELECT {', '.join(LOG_COLS)} FROM review_logs WHERE vocab_item_id = ? ORDER BY id",
                               (ref,)), context=self.card_context(ref))

    def count(self, table: str, where: str = "", params: tuple = ()) -> int:
        return int(self.sql(f"SELECT COUNT(*) AS n FROM {table} {where}", params)[0]["n"])

    def response(self, result: dict[str, Any]) -> Any:
        return {"status": result["status"], "body": self.n(result["body"])}

    # ---- stages -------------------------------------------------------------
    def stage_upgrade(self) -> dict[str, Any]:
        """P-UP1: the app's schema code twice; the second run creates nothing."""
        import app.database as database

        if self.engine == "postgresql":
            import _srs_e2_adapter as adapter

            expected = adapter.expected_schema_tables()
            self.run.track_creation(adapter.schema_step(), expected=expected)
            first = sorted(self.run.owned)
            self.run.track_creation(adapter.schema_step(), expected=set())  # stops if anything new appears
            second_new = sorted(set(self.run.owned) - set(first))
            columns = self.sql("SELECT table_name AS t, column_name AS c FROM information_schema.columns "
                               "WHERE table_schema = 'public'")
        else:
            database.init_db()
            before = self.sql("SELECT name, sql FROM sqlite_master ORDER BY name")
            database.init_db()
            after = self.sql("SELECT name, sql FROM sqlite_master ORDER BY name")
            second_new = sorted({r["name"] for r in after} - {r["name"] for r in before})
            columns = [{"t": t, "c": r["name"]} for t in ("vocab_items", "user_word_progress", "review_logs",
                                                           "lexeme_review_logs")
                       for r in self.sql(f"PRAGMA table_info({t})")]
        srs_tables = sorted({r["t"] for r in columns if r["t"].startswith("srs_")} if self.engine == "postgresql"
                            else {r["name"] for r in self.sql("SELECT name FROM sqlite_master WHERE type = 'table' "
                                                              "AND name LIKE 'srs_%'")})
        srs_columns = {t: sorted(r["c"] for r in columns if r["t"] == t and (r["c"].startswith("srs_") or r["c"] in (
            "evidence_from_log_id", "history_intro_status", "first_completed_source", "version_first_completed_at",
            "version_first_completed_version", "seoul_date", "is_first_review")))
            for t in ("vocab_items", "user_word_progress", "review_logs", "lexeme_review_logs")}
        return {"srs_tables": srs_tables, "srs_columns": srs_columns, "second_run_new_tables": second_new}

    def stage_review(self) -> dict[str, Any]:
        """P-REV1 / P-REV2: first answer, identical retry, conflicting retry, stale version,
        legacy client, a failure in the middle of the write."""
        from app.srs import reviews

        self.clock = T0
        user = self.user("rv")
        self.set_mode(user, "fsrs")
        ref = self.card(user, "rv1")
        out: dict[str, Any] = {}
        self.clock = T0 + timedelta(hours=1)
        first = self.review(user, ref, "good", request="rv-r1", version=0)
        retry = self.review(user, ref, "good", request="rv-r1", version=0)
        out["first"] = self.response(first)
        out["retry"] = self.response(retry)
        out["retry_same_bytes"] = int(first["raw"] == retry["raw"])
        out["conflict"] = self.response(self.review(user, ref, "easy", request="rv-r1", version=0))
        out["stale_version"] = self.response(self.review(user, ref, "good", request="rv-r2", version=0))
        out["legacy_client"] = self.response(self.review(user, ref, "good", legacy=True))
        before = (self.card_view(ref), self.log_view(ref), self.count("srs_review_receipts", "WHERE user_id = ?", (user,)))
        self.clock = T0 + 2 * DAY
        with mock.patch.object(reviews, "update_card", side_effect=RuntimeError("synthetic failure")):
            try:
                failed = self.review(user, ref, "good", request="rv-r3")
                out["failure_status"] = failed["status"]
            except RuntimeError:
                out["failure_status"] = "raised"
        after = (self.card_view(ref), self.log_view(ref), self.count("srs_review_receipts", "WHERE user_id = ?", (user,)))
        out["failure_left_no_trace"] = int(before == after)
        out["after_failure"] = self.response(self.review(user, ref, "good", request="rv-r3"))
        out["card"] = self.card_view(ref)
        out["logs"] = self.log_view(ref)
        out["receipts"] = self.count("srs_review_receipts", "WHERE user_id = ?", (user,))
        return out

    def stage_queue(self) -> dict[str, Any]:
        """P-Q1 / P-T1: queue order and the Seoul-date boundary (23:59:59 / 00:00:00 KST)."""
        from app.database import get_connection
        from app.srs import goals

        self.clock = T0 - DAY
        user = self.user("qu")
        self.set_mode(user, "fsrs")
        refs = {label: self.card(user, label) for label in ("q1", "q2", "q3", "q4")}
        before_midnight = datetime(2026, 6, 1, 14, 59, 59, tzinfo=UTC)
        midnight = datetime(2026, 6, 1, 15, 0, 0, tzinfo=UTC)
        self.clock = before_midnight
        late = self.response(self.review(user, refs["q1"], "good"))
        self.clock = midnight
        early = self.response(self.review(user, refs["q2"], "again"))
        out: dict[str, Any] = {"review_2359": late, "review_0000": early}
        with get_connection() as c:
            out["introduced"] = {stamp.isoformat(): goals.introduction_count(c, user, stamp).as_dict()
                                 for stamp in (before_midnight, midnight)}
        out["logs"] = {label: self.log_view(ref) for label, ref in refs.items() if label in ("q1", "q2")}
        for hours in (1, 30, 24 * 6):
            self.clock = midnight + timedelta(hours=hours)
            response = self.client.get("/study-queue", headers=self.headers(user))
            out[f"queue_plus_{hours}h"] = {"status": response.status_code, "body": self.n(response.json())}
        return out

    def stage_migration(self) -> dict[str, Any]:
        """P-M1 / P-M2: legacy history -> dry run -> apply -> rerun -> FSRS review ->
        rollback (keeps the later review) -> re-conversion."""
        from app.srs import migration
        from app.srs.engine import CardKey

        self.clock = T0 - 60 * DAY
        user = self.user("mg")
        self.set_mode(user, "legacy")
        refs = {label: self.card(user, label) for label in ("m1", "m2")}
        for label, days in (("m1", 50), ("m1", 40), ("m2", 45)):
            self.clock = T0 - days * DAY
            self.review(user, refs[label], "good", legacy=True)
        self.clock = T0
        self.set_mode(user, "fsrs")
        keys = [CardKey("personal", user, refs[label]) for label in ("m1", "m2")]
        out: dict[str, Any] = {}
        plan = migration.dry_run(keys)
        out["dry_run"] = self.n(list(plan))
        out["apply"] = self.n(migration.apply_plan(plan, "e2a-run-1", approved=True))
        out["apply_again"] = self.n(migration.apply_plan(plan, "e2a-run-1", approved=True))
        out["after_apply"] = {label: self.card_view(ref) for label, ref in refs.items()}
        self.clock = T0 + 2 * DAY
        out["fsrs_review"] = self.response(self.review(user, refs["m1"], "good"))
        self.clock = T0 + 5 * DAY
        out["rollback"] = self.n(migration.rollback_plan("e2a-run-1", "e2a-rb-1", user_id=user, approved=True))
        out["after_rollback"] = {label: self.card_view(ref) for label, ref in refs.items()}
        out["logs_after_rollback"] = {label: self.log_view(ref) for label, ref in refs.items()}
        self.clock = T0 + 6 * DAY
        replan = migration.dry_run(keys)
        out["redry_run"] = self.n(list(replan))
        out["reconvert"] = self.n(migration.apply_plan(replan, "e2a-run-2", approved=True))
        out["after_reconvert"] = {label: self.card_view(ref) for label, ref in refs.items()}
        runs = self.sql("SELECT id, run_key, mode, status FROM srs_migration_runs WHERE run_key LIKE ? ORDER BY id",
                        ("e2a-%",))
        for r in runs:
            self.labels.put("run", r["id"], r["run_key"], owner=self.labels.name("user", user))
        out["runs"] = [{"run_key": r["run_key"], "mode": r["mode"], "status": r["status"],
                        "snapshots": self.count("srs_migration_snapshots", "WHERE run_id = ?", (r["id"],))} for r in runs]
        return out

    def stage_completion(self) -> dict[str, Any]:
        """P-C1: V3 completion evidence through the real review path (server side only)."""
        self.clock = T0
        user = self.user("cp")
        self.set_mode(user, "fsrs")
        ref = self.card(user, "c1")
        out: dict[str, Any] = {"reviews": []}
        for days in (0, 1, 4, 10, 25, 55, 120, 240):
            self.clock = T0 + days * DAY + timedelta(hours=1)
            result = self.review(user, ref, "good")
            out["reviews"].append({"status": result["status"], "srs": self.n(result["body"].get("srs"))})
        out["card"] = self.card_view(ref)
        out["logs"] = self.log_view(ref)
        return out

    def run_stages(self, stages: tuple[str, ...] = STAGES) -> dict[str, Any]:
        unknown = set(stages) - set(STAGES)
        if unknown:
            raise ValueError(f"unknown stage(s): {sorted(unknown)}")
        if "upgrade" not in stages:
            raise ValueError("the upgrade stage creates the schema and must run first")
        return {stage: getattr(self, f"stage_{stage}")() for stage in STAGES if stage in stages}


def selected_stages(environ: Any = os.environ) -> tuple[str, ...]:
    """SRS_E2_STAGES=upgrade,review,... runs the check list step by step (upgrade always first)."""
    raw = (environ.get("SRS_E2_STAGES") or "").strip()
    if not raw:
        return STAGES
    chosen = {s.strip() for s in raw.split(",") if s.strip()}
    if chosen - set(STAGES):
        raise ValueError(f"unknown stage(s): {sorted(chosen - set(STAGES))}")
    return tuple(s for s in STAGES if s in chosen or s == "upgrade")


def run_sqlite(path: str, stages: tuple[str, ...] = STAGES, before: Callable[[], None] | None = None) -> dict[str, Any]:
    """One session-only synthetic SQLite file. `before` may add unrelated rows first
    (used to shift ids and prove the comparison does not depend on them)."""
    with mock.patch.dict(os.environ, {"DATABASE_URL": f"sqlite:///{path}", "APP_ENV": "test"}):
        with Scenario("sqlite") as scenario:
            if before is not None:
                import app.database as database

                database.init_db()
                before()
            return scenario.run_stages(stages)


def run_postgres(run: Any, stages: tuple[str, ...] = STAGES) -> dict[str, Any]:
    """E-2: on the harness's protected empty local database, through the adapter."""
    import _srs_e2_adapter as adapter

    with adapter.app_scope(run):
        with Scenario("postgresql", run) as scenario:
            return scenario.run_stages(stages)

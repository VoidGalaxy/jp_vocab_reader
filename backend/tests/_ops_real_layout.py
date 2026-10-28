"""Shared real-PG harness pieces for the closed test targets (RS4-1, OPS_MIGRATION_RESUME_REAL_PG_PLAN 2절 (A)).

Every target-bound function takes a closed LAYOUT object explicitly; only the registered objects `PG65`
(C12 first `apply`) and `PG66` (RS4 `resume`) are accepted, by identity (a copy with equal values is
refused). Nothing here reads a target from the command line, the environment or a module global that a
caller replaces; there is no default layout. The target-free helpers below were moved verbatim from
`_ops_apply_real.py` (C12), which keeps them under the same names. This module imports no runner.

Import does nothing outside Python: no app import, connection, process, key or folder.
"""

from __future__ import annotations

import dataclasses
import contextlib
import hashlib
import json
import os
import secrets
import shutil
import threading
import time
from pathlib import Path
from typing import Any, Callable
from unittest import mock

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

import _ops_audit_real as real  # noqa: E402  (schema lists, TLS / server steps, commit word check)
import _ops_audit_run as ar  # noqa: E402
import _ops_pg62 as g  # noqa: E402
import _ops_pg62_real as base  # noqa: E402  (run, sha, CheckFailed, expect)
import _ops_provider as pv  # noqa: E402
import srs_migrate as cli  # noqa: E402

SYN = real.SYN
TLS_VERSIONS = frozenset({"TLSv1.3"})
WAIT_LIMIT = 20.0                     # seconds: contention waits, pauses, thread joins
CheckFailed, expect = base.CheckFailed, base.expect
READ_COMMANDS = frozenset({"dry_run", "status"})          # approved read steps of srs_migrate
WRITE_COMMANDS = frozenset({"apply", "resume"})           # approved write steps of srs_migrate


# --- closed layouts -----------------------------------------------------------------------------------

@dataclasses.dataclass(frozen=True, eq=False)
class Layout:
    """One approved real-PG target with its names. Only PG65 and PG66 below exist; identity is checked."""
    short: str                                   # folder / map / code prefix: "pg65", "pg66"
    target: g.Target
    check_ids: tuple[str, ...]
    owner: str
    variants: dict
    variant_databases: dict

    @property
    def template(self) -> str:
        return self.target.databases[0]

    @property
    def check_db(self) -> dict:
        return dict(zip(self.check_ids, self.target.databases[1:]))

    @property
    def business_databases(self) -> tuple[str, ...]:
        return tuple(self.check_db.values())                  # never the template

    @property
    def admin_databases(self) -> tuple[str, ...]:
        return ("postgres", self.template) + self.business_databases

    @property
    def admin(self) -> str:
        return self.target.admin

    @property
    def read(self) -> str:
        return self.target.provider_roles[0]

    @property
    def write(self) -> str:
        return self.target.provider_roles[1]

    @property
    def business_roles(self) -> tuple[str, str]:
        return (self.read, self.write)


VARIANTS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "b2_lock_column": (("REVOKE UPDATE (updated_at) ON public.users FROM {w}",),
                       ("GRANT UPDATE (updated_at) ON public.users TO {w}",)),
    "b3_users_table": (("GRANT UPDATE ON public.users TO {w}",),
                       ("REVOKE UPDATE ON public.users FROM {w}", "GRANT UPDATE (updated_at) ON public.users TO {w}")),
    "b3_users_email": (("GRANT UPDATE (email) ON public.users TO {w}",),
                       ("REVOKE UPDATE (email) ON public.users FROM {w}",)),
    "b3_card_column": (("GRANT UPDATE (surface) ON public.vocab_items TO {w}",),
                       ("REVOKE UPDATE (surface) ON public.vocab_items FROM {w}",)),
    # Contract without sequence USAGE (OPS_APPLY_SEQUENCE_PRIVILEGE_PLAN 3-1): grant both, then revoke them.
    "c1_sequences": (("GRANT USAGE ON SEQUENCE public.srs_migration_runs_id_seq TO {w}",
                      "GRANT USAGE ON SEQUENCE public.srs_migration_snapshots_id_seq TO {w}"),
                     ("REVOKE USAGE ON SEQUENCE public.srs_migration_runs_id_seq FROM {w}",
                      "REVOKE USAGE ON SEQUENCE public.srs_migration_snapshots_id_seq FROM {w}")),
    "g2_card_column": (("REVOKE UPDATE (srs_state) ON public.vocab_items FROM {w}",),
                       ("GRANT UPDATE (srs_state) ON public.vocab_items TO {w}",)),
}
VARIANT_DATABASES = {"b2_lock_column": ("b2",), "b3_users_table": ("b3",), "b3_users_email": ("b3",),
                     "b3_card_column": ("b3",), "c1_sequences": ("c1",), "g2_card_column": ("g2",)}

# RS4 approved temporary privilege changes (plan 5-1 r5 / r9a), each with its exact revert. {r} = read role,
# {w} = write role. Sequence USAGE is NOT in the contract (OPS_APPLY_SEQUENCE_PRIVILEGE_PLAN): granting it is
# an excess case. None of these runs without the RS4-3 approval.
PG66_VARIANTS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "r5_read_missing": (("REVOKE SELECT ON public.srs_migration_runs FROM {r}",),
                        ("GRANT SELECT ON public.srs_migration_runs TO {r}",)),
    "r5_read_excess": (("GRANT INSERT ON public.srs_migration_runs TO {r}",),
                       ("REVOKE INSERT ON public.srs_migration_runs FROM {r}",)),
    "r5_write_missing": (("REVOKE UPDATE (status) ON public.srs_migration_runs FROM {w}",),
                         ("GRANT UPDATE (status) ON public.srs_migration_runs TO {w}",)),
    "r5_write_excess": (("GRANT UPDATE ON public.users TO {w}",),
                        ("REVOKE UPDATE ON public.users FROM {w}", "GRANT UPDATE (updated_at) ON public.users TO {w}")),
    "r5_write_sequences": (("GRANT USAGE ON SEQUENCE public.srs_migration_runs_id_seq TO {w}",
                            "GRANT USAGE ON SEQUENCE public.srs_migration_snapshots_id_seq TO {w}"),
                           ("REVOKE USAGE ON SEQUENCE public.srs_migration_runs_id_seq FROM {w}",
                            "REVOKE USAGE ON SEQUENCE public.srs_migration_snapshots_id_seq FROM {w}")),
    "r9a_card_column": (("REVOKE UPDATE (srs_state) ON public.vocab_items FROM {w}",),
                        ("GRANT UPDATE (srs_state) ON public.vocab_items TO {w}",)),
}
PG66_VARIANT_DATABASES = {"r5_read_missing": ("r5",), "r5_read_excess": ("r5",), "r5_write_missing": ("r5",),
                          "r5_write_excess": ("r5",), "r5_write_sequences": ("r5",), "r9a_card_column": ("r9a",)}

PG65 = Layout("pg65", g.PG65_APPLY, g.PG65_APPLY_CHECK_IDS, "jpvm_owner", VARIANTS, VARIANT_DATABASES)
PG66 = Layout("pg66", g.PG66_RESUME, g.PG66_RESUME_CHECK_IDS, "jpvr_owner", PG66_VARIANTS, PG66_VARIANT_DATABASES)
LAYOUTS = (PG65, PG66)


def layout(value: Any) -> Layout:
    """The registered object itself, or a refusal (a copy with the same values is refused)."""
    if not any(value is known for known in LAYOUTS):
        raise g.Pg62Refused("layout_refused")
    g.preset(value.target)
    return value


def role_of(lay: Layout, command: Any) -> str:
    """The business role of an approved srs_migrate step, from a closed command set (never a default)."""
    lay = layout(lay)
    if command in WRITE_COMMANDS:
        return lay.write
    if command in READ_COMMANDS:
        return lay.read
    raise CheckFailed("harness_defect", "command outside the closed step sets")


# --- expectations: contract constants and schema source only ----------------------------------------

def expected_objects(db: str) -> frozenset:
    """What exists in a check DB (environment fact from the schema source, not from an observation)."""
    sequences = [f"{t}_id_seq" for t in real.CORE_TABLES + real.SRS_TABLES if t not in real.SRS_WITHOUT_IDENTITY]
    objects = {("database", "", db), ("schema", "", "public"), ("schema", "", SYN), ("table", SYN, "db_identity"),
               ("tablespace", "", "pg_default"), ("tablespace", "", "pg_global")}
    objects |= {("table", "public", t) for t in real.CORE_TABLES + real.SRS_TABLES}
    objects |= {("sequence", "public", s) for s in sequences}
    return frozenset(objects)


def expected_profiles(lay: Layout, db: str) -> tuple[pv.ExpectedProfile, pv.ExpectedProfile]:
    lay = layout(lay)
    if db not in lay.business_databases:
        raise g.Pg62Refused(f"{lay.short}_database_refused")
    return cli.contract_profiles(cli.ProfileScope(expected_objects(db), real.SEARCH_PATH, TLS_VERSIONS), db)


def grant_statements(privileges: frozenset, role: str) -> list[sql.Composed]:
    """One GRANT per contract tuple; any tuple shape outside the contract is refused (no guessing)."""
    out = []
    for kind, schema, name, column, privilege in sorted(privileges):
        target = sql.Identifier(role)
        if kind == "database" and privilege == "CONNECT" and not schema and not column:
            out.append(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(sql.Identifier(name), target))
        elif kind == "schema" and privilege == "USAGE" and not schema and not column:
            out.append(sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(sql.Identifier(name), target))
        elif kind == "sequence" and privilege == "USAGE" and not column:
            out.append(sql.SQL("GRANT USAGE ON SEQUENCE {}.{} TO {}").format(
                sql.Identifier(schema), sql.Identifier(name), target))
        elif kind == "table" and privilege in ("SELECT", "INSERT", "UPDATE"):
            cols = sql.SQL(" ({})").format(sql.Identifier(column)) if column else sql.SQL("")
            out.append(sql.SQL("GRANT {}{} ON {}.{} TO {}").format(
                sql.SQL(privilege), cols, sql.Identifier(schema), sql.Identifier(name), target))
        else:
            raise CheckFailed("harness_defect", f"contract tuple outside the grant map: {kind}/{privilege}")
    return out


def contract_grants(lay: Layout, db: str) -> list[sql.Composed]:
    lay = layout(lay)
    read, write = expected_profiles(lay, db)
    return grant_statements(read.privileges, lay.read) + grant_statements(write.privileges, lay.write)


def variant_statements(lay: Layout, name: str, phase: str) -> list[sql.Composed]:
    lay = layout(lay)
    if name not in lay.variants or phase not in ("apply", "revert"):
        raise CheckFailed("harness_defect", "unknown privilege variant")
    texts = lay.variants[name][0 if phase == "apply" else 1]
    out = []
    for t in texts:
        roles = [w for w in ("{r}", "{w}") if w in t]
        if len(roles) != 1 or t.count(roles[0]) != 1:
            raise CheckFailed("harness_defect", "privilege variant without exactly one role")
        role = lay.read if roles[0] == "{r}" else lay.write
        out.append(sql.SQL(t.replace(roles[0], "{}")).format(sql.Identifier(role)))
    return out


# --- record and live target facts -------------------------------------------------------------------

def require_target_bound(lay: Layout, rec: g.Record, data: bytes) -> dict:
    """target.json must be the bytes whose SHA-256 the run recorded when it was written (exactly once)."""
    lay = layout(lay)
    T = lay.target
    written = rec.find("target_written")
    if len(written) != 1 or hashlib.sha256(data).hexdigest() != written[0].get("sha256"):
        raise g.Pg62Refused(f"{lay.short}_target_record_mismatch")
    target = json.loads(data)
    if target.get("port") != T.port or target.get("host") != g.HOST or not g.same_path(target.get("data"), T.data) \
            or not g.same_path(target.get("postgres_exe"), g.POSTGRES_EXE) \
            or set(target.get("databases", {})) != set(lay.business_databases) \
            or list(target.get("provider_roles", [])) != list(lay.business_roles):
        raise g.Pg62Refused(f"{lay.short}_target_record_mismatch")
    return target


def require_ours(lay: Layout, target: dict) -> None:
    """Live facts = record: postmaster.pid PID, its executable, the listener owner (no process search)."""
    lay = layout(lay)
    if g.pg_environment_present():
        raise g.Pg62Refused("pg62_pg_environment_present")
    if not g.server_is_ours(target["postmaster_pid"], lay.target):
        raise g.Pg62Refused("pg62_server_not_ours")


def business_check(lay: Layout, kwargs: dict) -> None:
    """Before the shared guard: the business access matrix of this run (check DBs, two roles)."""
    lay = layout(lay)
    if g.pg_environment_present():
        raise g.Pg62Refused("pg62_pg_environment_present")
    if kwargs.get("host") != g.HOST:
        raise g.Pg62Refused("pg62_host_refused")
    if kwargs.get("port") != str(lay.target.port):
        raise g.Pg62Refused("pg62_port_refused")
    if kwargs.get("dbname") not in lay.business_databases:
        raise g.Pg62Refused("pg62_database_refused")
    if kwargs.get("user") not in lay.business_roles:
        raise g.Pg62Refused("pg62_role_refused")
    if kwargs.get("sslmode") != "verify-full":
        raise g.Pg62Refused("pg62_tls_mode_refused")


OID_TABLES = ("users", "vocab_items", "user_word_progress", "srs_migration_runs", "srs_migration_snapshots")
POST_CONNECT = ("SELECT pg_catalog.host(pg_catalog.inet_server_addr()) AS server_addr, "
                "pg_catalog.inet_server_port() AS server_port, "
                "pg_catalog.current_setting('server_version_num') AS version, "
                "pg_catalog.current_database()::pg_catalog.text AS dbname, "
                "(SELECT d.oid FROM pg_catalog.pg_database AS d "
                " WHERE d.datname OPERATOR(pg_catalog.=) pg_catalog.current_database()) AS db_oid, "
                "(SELECT r.oid FROM pg_catalog.pg_roles AS r "
                " WHERE r.rolname OPERATOR(pg_catalog.=) CURRENT_USER) AS role_oid, "
                "(SELECT pg_catalog.array_agg(c.oid ORDER BY c.relname) FROM pg_catalog.pg_class AS c "
                " JOIN pg_catalog.pg_namespace AS n ON n.oid OPERATOR(pg_catalog.=) c.relnamespace "
                " WHERE n.nspname OPERATOR(pg_catalog.=) 'public' "
                " AND c.relname OPERATOR(pg_catalog.=) ANY (%s)) AS object_oids, "
                f"(SELECT pg_catalog.array_agg(identity_value) FROM {SYN}.db_identity) AS identity")


def post_connect_check(lay: Layout, conn: Any, target: dict, user: str) -> None:
    """Right after the guarded connect, in its own rolled-back transaction: loopback, port, version,
    database / role / object OIDs and the identity nonce must equal the record."""
    lay = layout(lay)
    try:
        with conn.cursor(row_factory=dict_row) as cursor:
            cursor.execute(POST_CONNECT, (list(OID_TABLES),))
            facts = cursor.fetchone()
        conn.rollback()
    except psycopg.Error:
        conn.close()
        raise g.Pg62Refused("pg62_connected_target_unreadable") from None
    db = target["databases"].get(facts["dbname"])
    if facts["server_addr"] not in g.LOOPBACK or facts["server_port"] != lay.target.port \
            or facts["version"] != target["server_version_num"] or db is None or facts["db_oid"] != db["oid"] \
            or facts["role_oid"] != target["roles"].get(user) \
            or list(facts["object_oids"] or []) != [db["objects"][t] for t in sorted(OID_TABLES)] \
            or list(facts["identity"] or []) != [db["identity_value"]]:
        conn.close()
        raise g.Pg62Refused("pg62_connected_target_mismatch")


# --- business-path counting (plan 4-0) ----------------------------------------------------------------

WRITE_WORDS = frozenset({"INSERT", "UPDATE", "DELETE", "MERGE", "TRUNCATE", "COPY"})


def first_word(query: Any) -> str:
    """The statement's first word only (not a parser). Unrenderable or other types: 'UNKNOWN'."""
    if isinstance(query, sql.Composable):
        try:
            query = query.as_string(None)
        except Exception:                                   # cannot render without a connection
            return "UNKNOWN"
    if not isinstance(query, str) or not query.strip():
        return "UNKNOWN"
    return query.strip().split(None, 1)[0].rstrip(";").upper()


class Counts:
    """One CLI call: per role, the four stages of plan 4-0 (the fourth is measured in the DB)."""

    def __init__(self, roles: tuple[str, ...]):
        self.created = {r: 0 for r in roles}
        self.handed = {r: 0 for r in roles}
        self.words = {r: {} for r in roles}
        self.commits = {r: 0 for r in roles}

    def role(self, role: str) -> dict:
        words = self.words[role]
        return {"created": self.created[role], "handed": self.handed[role], "statements": sum(words.values()),
                "writes": sum(n for w, n in words.items() if w in WRITE_WORDS), "commits": self.commits[role]}


def rejection_stage(c: dict) -> str:
    """Where a refused / failed role stopped (plan 4-0). 'committed' means it is not a refusal at all."""
    if c["created"] == 0:
        return "before_connect"
    if c["handed"] == 0:
        return "after_observation"
    if c["commits"] == 0 and c["writes"] == 0:
        return "under_product_lock"
    if c["commits"] == 0:
        return "rolled_back_after_write"
    return "committed"


class Tracked:
    """Wraps ONE business connection. Counting starts only when the connection is handed to the product
    (`activate`), so the provider's own observation is never counted. Calls are forwarded unchanged."""

    _OWN = frozenset({"_conn", "_counts", "_role", "_hooks", "active", "pending_pid"})

    def __init__(self, conn: Any, counts: Counts, role: str, hooks: list):
        for name, value in (("_conn", conn), ("_counts", counts), ("_role", role), ("_hooks", hooks),
                            ("active", False), ("pending_pid", None)):
            object.__setattr__(self, name, value)

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def __setattr__(self, name, value):
        if name in self._OWN:
            object.__setattr__(self, name, value)
        else:
            setattr(self._conn, name, value)

    def activate(self) -> None:
        object.__setattr__(self, "active", True)

    def note(self, query: Any) -> str:
        word = first_word(query)
        if self.active:
            words = self._counts.words[self._role]
            words[word] = words.get(word, 0) + 1
            if real._is_commit(query):
                self._counts.commits[self._role] += 1
        return word

    def run(self, query: Any, call: Callable[[], Any]) -> Any:
        word = self.note(query)
        object.__setattr__(self, "pending_pid", self._conn.info.backend_pid)
        result = call()
        if self.active:
            for hook in list(self._hooks):
                hook(self._role, word, query, self)
        return result

    def commit(self):
        if self.active:
            self._counts.commits[self._role] += 1
        return self._conn.commit()

    def execute(self, query, *args, **kwargs):
        result = self.run(query, lambda: self._conn.execute(query, *args, **kwargs))
        return result if result is None or isinstance(result, TrackedCursor) else TrackedCursor(result, self)

    def cursor(self, *args, **kwargs):
        return TrackedCursor(self._conn.cursor(*args, **kwargs), self)


class TrackedCursor:
    _OWN = frozenset({"_cursor", "_tracker"})

    def __init__(self, cursor: Any, tracker: Tracked):
        object.__setattr__(self, "_cursor", cursor)
        object.__setattr__(self, "_tracker", tracker)

    def __getattr__(self, name):
        return getattr(self._cursor, name)

    def __setattr__(self, name, value):
        if name in self._OWN:
            object.__setattr__(self, name, value)
        else:
            setattr(self._cursor, name, value)

    @property
    def connection(self) -> Tracked:
        return self._tracker

    def __enter__(self):
        self._cursor.__enter__()
        return self

    def __exit__(self, *exc):
        return self._cursor.__exit__(*exc)

    def __iter__(self):
        return iter(self._cursor)

    def execute(self, query, *args, **kwargs):
        self._tracker.run(query, lambda: self._cursor.execute(query, *args, **kwargs))
        return self


class InjectedFault(Exception):
    """A failure injected by the harness around a REAL connection (g3 / g4). Never a real outage."""


ORIGINAL_CONNECTOR = cli._product_connector              # fixed at import, before any patch of a runner


def counted_connector(lay: Layout, counts: Counts, trackers: list, inject: Callable[[str, int], bool] | None = None,
                      after: Callable[[str, int], None] | None = None, real: Callable | None = None,
                      handover: Callable[[str, int, Any], None] | None = None,
                      before_exit: Callable[[str, int, Any], None] | None = None):
    """Wraps the CLI's product connector for ONE run. The CLI builds a new factory for every connection
    request (`_timed_connector`), so the request numbers live here, per role, for the whole run (never
    shared with another run). The role comes from the approved step's command through the closed sets
    (`dry_run` / `status` read, `apply` / `resume` write), never from one command name. Entering the
    context the real connector returns is the hand-over (plan 4-0 (2)). `inject(role, n)` may fail the n-th
    hand-over right after the real enter (the real exit then runs with the fault, as a product failure
    would). `handover(role, n, raw)` runs right after a successful real enter, before the product gets the
    connection (an RS4 pause point; it may block, never replaces the connection). `before_exit(role, n, raw)`
    runs after the product's body ended WITHOUT an exception and before the original exit (the r0 probe): the
    original exit is still called exactly once afterwards, its own error wins, and an error of the hook is
    raised only after it. `after(role, n)` runs after
    the n-th connection of a role ended without an exception, i.e. before the next request takes its
    judgement time."""
    lay = layout(lay)
    real = real or ORIGINAL_CONNECTOR
    requests = {role: 0 for role in lay.business_roles}

    def factory(inputs, expected, driver):
        connector = real(inputs, expected, driver)
        role = role_of(lay, inputs.command)

        def connect(*, read_only=False):
            requests[role] += 1
            number = requests[role]
            first = len(trackers)
            context = connector(read_only=read_only)            # the guarded driver runs inside
            made = trackers[first:]
            if len(made) != 1:                                  # (a refusal before this raised above)
                raise CheckFailed("harness_defect", "one hand-over must follow exactly one connection")

            class HandOver:
                def __enter__(self):
                    product = context.__enter__()
                    made[0].activate()
                    counts.handed[role] += 1
                    if inject is not None and inject(role, number):
                        fault = InjectedFault()
                        context.__exit__(InjectedFault, fault, None)
                        raise fault
                    if handover is not None:
                        try:
                            handover(role, number, made[0])
                        except BaseException as error:
                            context.__exit__(type(error), error, None)
                            raise
                    return product

                def __exit__(self, *exc):
                    hook_error = None
                    if exc[0] is None and before_exit is not None:
                        try:
                            before_exit(role, number, made[0])
                        except BaseException as error:         # kept; the original exit runs first
                            hook_error = error
                    result = context.__exit__(*exc)            # once, whatever the hook did; its error wins
                    if hook_error is not None:
                        hook_error.__cause__ = hook_error.__context__ = None   # no chained text from the hook
                        hook_error.__suppress_context__ = True
                        raise hook_error
                    if exc[0] is None and after is not None:
                        after(role, number)
                    return result
            return HandOver()
        return connect
    return factory


class RunScopes:
    """ONE wrapper installed on `srs_migrate._product_connector` for a whole check (or a whole race);
    each run binds its own counted connector to its own thread, so two overlapping runs never share
    counts, trackers or request numbers, and nothing is patched again while another run is going."""

    def __init__(self, lay: Layout, real: Callable | None = None):
        self.lay = layout(lay)
        self.real = real or ORIGINAL_CONNECTOR
        self.local = threading.local()

    def factory(self, inputs, expected, driver):
        scoped = getattr(self.local, "connector", None)
        if scoped is None:
            raise CheckFailed("harness_defect", "connection request outside a run scope")
        return scoped(inputs, expected, driver)

    @contextlib.contextmanager
    def installed(self):
        with mock.patch.object(cli, "_product_connector", self.factory):
            yield self

    @contextlib.contextmanager
    def run(self, counts: Counts, trackers: list, *, inject=None, after=None, handover=None, before_exit=None):
        self.local.connector = counted_connector(self.lay, counts, trackers, inject, after, self.real, handover,
                                                 before_exit)
        try:
            yield
        finally:
            self.local.connector = None


# --- changes in the DB (plan 4-0 (4)), read on an admin connection -------------------------------------

BUSINESS_TABLES = real.CORE_TABLES + real.SRS_TABLES


def content_hashes(conn: Any) -> dict:
    """Row content per table (count + md5 of the ordered row texts). Rows only: not locks, sequences, stats."""
    out = {}
    for table in BUSINESS_TABLES:
        row = conn.execute(sql.SQL("SELECT count(*) AS n, pg_catalog.md5(coalesce(pg_catalog.string_agg(t::text, "
                                   "E'\\n' ORDER BY t::text), '')) AS h FROM public.{} AS t").format(
            sql.Identifier(table))).fetchone()
        out[table] = [row[0], row[1]]
    return out


def run_facts(conn: Any, run_key: str, cards: dict, account_id: int) -> dict:
    """Run rows by the (globally unique) run key, whatever account they belong to; card versions only for
    the request's account: `user_word_progress` is keyed by (user_id, lexeme_id), so a lexeme id alone
    would also read other accounts' rows. Values are bound, never formatted into the text."""
    runs = [dict(zip(("id", "mode", "status", "scope_md5"), r)) for r in conn.execute(
        "SELECT id, mode, status, pg_catalog.md5(scope_json) FROM srs_migration_runs WHERE run_key = %s ORDER BY id",
        (run_key,)).fetchall()]
    snapshots = conn.execute("SELECT count(*) FROM srs_migration_snapshots WHERE run_id = ANY (%s)",
                             ([r["id"] for r in runs],)).fetchone()[0]
    versions = {}
    for kind, ids in cards.items():
        table, column = ("vocab_items", "id") if kind == "personal" else ("user_word_progress", "lexeme_id")
        query = sql.SQL("SELECT {}, srs_card_version FROM public.{} WHERE {} = %s AND {} = ANY (%s)").format(
            sql.Identifier(column), sql.Identifier(table), sql.Identifier("user_id"), sql.Identifier(column))
        for ref, version in conn.execute(query, (account_id, list(ids))).fetchall():
            versions[f"{kind}:{ref}"] = version
    return {"runs": runs, "snapshots": snapshots, "versions": versions}


def attributed_changes(before: dict, after: dict, *, winner_applied: int, winner_scope: str,
                       refused_commits: int) -> list[str]:
    """Plan 4-0 ⓐ~ⓓ: under contention the winner's normal changes are expected; only changes that can
    belong to the refused run are problems. Returns problem labels (empty = none attributed)."""
    problems = []
    if before["runs"] or len(after["runs"]) != 1:
        problems.append("run_rows")                              # ⓐ exactly one run row, created during the race
    elif after["runs"][0]["scope_md5"] != winner_scope or after["runs"][0]["mode"] != "apply":
        problems.append("run_scope")
    if after["snapshots"] != winner_applied:
        problems.append("snapshots")                             # ⓑ
    bumps = sum((after["versions"].get(k, 0) or 0) - (v or 0) for k, v in before["versions"].items())
    if bumps != winner_applied or set(after["versions"]) != set(before["versions"]):
        problems.append("card_versions")                         # ⓒ applied once each, no double apply
    if refused_commits != 0:
        problems.append("refused_commits")                       # ⓓ
    return problems


# --- contention device -------------------------------------------------------------------------------

class Pause:
    """Holds ONE business connection after a chosen statement until released (or WAIT_LIMIT)."""

    def __init__(self, role: str, word: str, prefix: str, limit: float = WAIT_LIMIT):
        self.role, self.word, self.prefix, self.limit = role, word, prefix, limit
        self.reached, self.release = threading.Event(), threading.Event()
        self.holder_pid: int | None = None
        self.timed_out = False

    def hook(self, role: str, word: str, query: Any, tracker: Tracked) -> None:
        text = query if isinstance(query, str) else ""
        if self.reached.is_set() or role != self.role or word != self.word or not text.startswith(self.prefix):
            return
        self.holder_pid = tracker.pending_pid
        self.reached.set()
        if not self.release.wait(self.limit):
            self.timed_out = True                                # give up holding; the run goes on and is judged


def wait_blocked(blocking_pids: Callable[[int], list], waiter: Callable[[], int | None], holder: int,
                 *, limit: float = WAIT_LIMIT, clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep) -> int:
    """Poll pg_blocking_pids(waiter) until it contains `holder`. Returns the waiter PID or raises
    a harness defect (no proof of the wait = no product judgement)."""
    end = clock() + limit
    while clock() < end:
        pid = waiter()
        if pid is not None and holder in (blocking_pids(pid) or []):
            return pid
        sleep(0.2)
    raise CheckFailed("harness_defect", "waiting partner not proven")


def race(first: Callable[[], Any], second: Callable[[], Any], pause: Pause, prove: Callable[[], dict],
         close_all: Callable[[], None], limit: float = WAIT_LIMIT) -> tuple[Any, Any, dict]:
    """Run `first` until it holds at the pause, start `second`, prove the wait, release, join.
    On any failure the pause is released, threads are joined and every tracked connection is closed."""
    results: dict = {}

    def runner(name, fn):
        try:
            results[name] = ("ok", fn())
        except BaseException as error:          # carried to the harness thread; nothing is swallowed there
            results[name] = ("error", error)
    threads = {n: threading.Thread(target=runner, args=(n, fn), daemon=True) for n, fn in (("A", first), ("B", second))}
    proof: dict = {}
    try:
        threads["A"].start()
        end = time.monotonic() + limit
        while not pause.reached.wait(0.05) and threads["A"].is_alive() and time.monotonic() < end:
            pass
        if not pause.reached.is_set():
            ended = results.get("A")
            why = f" (run A ended: {type(ended[1]).__name__})" if ended and ended[0] == "error" else ""
            raise CheckFailed("harness_defect", "first run did not reach the pause" + why)
        threads["B"].start()
        proof = prove()
    finally:
        pause.release.set()
        for thread in threads.values():
            if thread.is_alive() or thread.ident is not None:
                thread.join(limit)
        if any(t.is_alive() for t in threads.values()):
            close_all()
            raise CheckFailed("harness_defect", "a contention thread did not end")
    for name in ("A", "B"):
        if name in results and results[name][0] == "error":
            error = results[name][1]
            if isinstance(error, CheckFailed):
                raise error
            raise CheckFailed("harness_defect", f"run {name} raised {type(error).__name__}")
    expect("A" in results and "B" in results and not pause.timed_out, "contention runs incomplete", "harness_defect")
    return results["A"][1], results["B"][1], proof


# --- recorded results ----------------------------------------------------------------------------------

def run_recorded(rec: g.Record, name: str, fn: Callable[[Any], dict], h: Any) -> bool:
    """One item. True only when it passed AND its pass was saved AND read back from disk."""
    if not base.run_check(rec, name, fn, h):
        return False
    try:
        saved = json.loads((rec.folder / "record.json").read_text(encoding="utf-8"))
        last = saved["results"][-1]
        ok = last.get("check") == name and last.get("status") == "pass"
    except (OSError, ValueError, KeyError, IndexError):
        ok = False
    if not ok:
        try:
            rec.result(name, "error", kind="harness_defect", stage="record_readback")
        except Exception:                      # nothing more can be written; the run stops either way
            pass
        print(f"{name}: ERROR record read-back")
    return ok


# --- synthetic data and the gate's card names (same data for every layout) ------------------------------

STAMP = "'2026-10-10T00:00:00+00:00'"
# Synthetic data (owner role, after ensure_schema made the dev user). Accounts a / b / c; personal cards
# p1..p3 (convertible: past study, no log, a future schedule), p4 (blocked: past study, no schedule ->
# incomplete / schedule_missing), p5 (account a only: out of scope); lexeme cards l1, l2 through an
# active subscription. The intended qualities are checked by gate G0 before any check (plan 2-2 3).
SEED = [
    f"INSERT INTO users (email, display_name, auth_provider, created_at, updated_at) SELECT 'apply-' || a || "
    f"'@example.test', 'apply ' || a, 'local', {STAMP}, {STAMP} FROM (VALUES ('a'), ('b'), ('c')) AS x (a)",
    f"INSERT INTO decks (user_id, name, description, created_at, updated_at) SELECT id, 'apply deck', '', {STAMP}, "
    f"{STAMP} FROM users WHERE email LIKE 'apply-%@example.test'",
    "INSERT INTO vocab_items (user_id, deck_id, surface, base_form, reading, part_of_speech, normalized_form, status, "
    "correct_count, review_level, last_reviewed_at, next_review_at, created_at, updated_at) "
    f"SELECT u.id, d.id, w.s, w.s, w.r, 'noun', w.s, 'learning', 2, 2, {STAMP}, "
    f"CASE WHEN w.p = 'p4' THEN NULL ELSE '2026-10-30T00:00:00+00:00' END, {STAMP}, {STAMP} "
    "FROM users u JOIN decks d ON d.user_id = u.id CROSS JOIN (VALUES ('p1', '猫', 'ねこ'), ('p2', '犬', 'いぬ'), "
    "('p3', '鳥', 'とり'), ('p4', '雲', 'くも'), ('p5', '川', 'かわ')) AS w (p, s, r) "
    "WHERE u.email LIKE 'apply-%@example.test' AND (w.p <> 'p5' OR u.email = 'apply-a@example.test')",
    "INSERT INTO lexemes (surface, base_form, reading, part_of_speech, meaning_ko, dictionary_gloss, source_type, "
    f"created_at, updated_at) VALUES ('山', '山', 'やま', 'noun', '산', '', 'synthetic', {STAMP}, {STAMP}), "
    f"('海', '海', 'うみ', 'noun', '바다', '', 'synthetic', {STAMP}, {STAMP})",
    "INSERT INTO shared_decks (owner_user_id, title, description, visibility, vocab_count, custom_term_count, "
    f"import_count, created_at, updated_at) SELECT id, 'apply shared', '', 'public', 2, 0, 0, {STAMP}, {STAMP} "
    "FROM users WHERE email = 'dev@example.local'",
    "INSERT INTO shared_deck_words (shared_deck_id, lexeme_id, sort_order, created_at) SELECT s.id, l.id, l.id, "
    f"{STAMP} FROM shared_decks s CROSS JOIN lexemes l WHERE s.title = 'apply shared' AND l.source_type = 'synthetic'",
    "INSERT INTO user_deck_subscriptions (user_id, shared_deck_id, is_active, imported_at, created_at, updated_at) "
    f"SELECT u.id, s.id, TRUE, {STAMP}, {STAMP}, {STAMP} FROM users u CROSS JOIN shared_decks s "
    "WHERE u.email LIKE 'apply-%@example.test' AND s.title = 'apply shared'",
    "INSERT INTO user_word_progress (user_id, lexeme_id, status, review_level, next_review_at, correct_count, "
    f"wrong_count, last_reviewed_at, created_at, updated_at) SELECT u.id, l.id, 'learning', 2, "
    f"'2026-10-30T00:00:00+00:00', 2, 0, {STAMP}, {STAMP}, {STAMP} FROM users u CROSS JOIN lexemes l "
    "WHERE u.email LIKE 'apply-%@example.test' AND l.source_type = 'synthetic'",
]


def synthetic_ids(conn: Any) -> dict:
    """Account and card ids of the template (clones keep them), for target.json."""
    out = {}
    for account in ("a", "b", "c"):
        uid = conn.execute("SELECT id FROM users WHERE email = %s", (f"apply-{account}@example.test",)).fetchone()[0]
        personal = {p: i for p, i in conn.execute(
            "SELECT CASE base_form WHEN '猫' THEN 'p1' WHEN '犬' THEN 'p2' WHEN '鳥' THEN 'p3' WHEN '雲' THEN 'p4' "
            "ELSE 'p5' END, id FROM vocab_items WHERE user_id = %s ORDER BY id", (uid,)).fetchall()}
        lexeme = [r[0] for r in conn.execute("SELECT lexeme_id FROM user_word_progress WHERE user_id = %s "
                                             "ORDER BY lexeme_id", (uid,)).fetchall()]
        out[account] = {"user_id": uid, "personal": personal, "lexeme": lexeme}
    return out


EXPECTED_QUALITIES = {"p1": "convertible", "p2": "convertible", "p3": "convertible", "p4": "blocked:incomplete",
                      "l1": "convertible", "l2": "convertible"}


def quality_label(candidate: Any) -> str:
    return "convertible" if candidate.values_json is not None else f"blocked:{candidate.quality}"


def quality_names(ids: dict) -> dict:
    """(kind, user_id, ref_id) -> gate name, from the recorded ids of account a (p1..p4, l1, l2). The
    product returns candidates in its own order (`_scope`: sorted by kind, ref_id), so names are never
    taken from positions."""
    lexeme = list(ids.get("lexeme", []))
    personal = ids.get("personal", {})
    if len(lexeme) != 2 or not all(p in personal for p in ("p1", "p2", "p3", "p4")):
        raise CheckFailed("harness_defect", "recorded synthetic ids are not as prepared")
    names = {("personal", ids["user_id"], personal[p]): p for p in ("p1", "p2", "p3", "p4")}
    names.update({("lexeme", ids["user_id"], ref): name for name, ref in zip(("l1", "l2"), lexeme)})
    if len(names) != 6:
        raise CheckFailed("harness_defect", "recorded synthetic ids are not distinct")
    return names


def name_qualities(candidates: Any, names: dict) -> dict:
    """Each candidate named by its own key. A missing, repeated, unexpected or other-account key is a
    harness defect (never skipped or overwritten); only the qualities themselves are compared later."""
    accounts = {user for _, user, _ in names}
    out: dict = {}
    for item in candidates:
        key = (item.key.kind, item.key.user_id, item.key.ref_id)
        if item.key.user_id not in accounts:
            raise CheckFailed("harness_defect", "dry_run result for an other account card")
        if key not in names:
            raise CheckFailed("harness_defect", "unexpected card key in the dry_run result")
        if names[key] in out:
            raise CheckFailed("harness_defect", "duplicate card key in the dry_run result")
        out[names[key]] = quality_label(item)
    if set(out) != set(names.values()):
        raise CheckFailed("harness_defect", "card key missing from the dry_run result")
    return out


def ticking(start, step_seconds: int = 1) -> Callable[[], Any]:
    """The run's clock: synthetic time inside the test keys' window, one step per call."""
    from datetime import timedelta
    state = {"now": start}

    def clock():
        state["now"] = state["now"] + timedelta(seconds=step_seconds)
        return state["now"]
    clock.state = state  # type: ignore[attr-defined]
    return clock


# --- prepare / cleanup (target-bound; not run without approval) ------------------------------------------

def admin(lay: Layout, db: str, pid: int, autocommit: bool = True):
    lay = layout(lay)
    if db not in lay.admin_databases:
        raise g.Pg62Refused("pg62_admin_target_refused")
    return g.admin_connect(db, record_pid=pid, autocommit=autocommit, target=lay.target)


def hba(lay: Layout) -> str:
    lay = layout(lay)
    dbs = ",".join(lay.business_databases)
    lines = []
    for addr in ("127.0.0.1/32", "::1/128"):
        lines += [f"hostssl postgres,{lay.template},{dbs} {lay.admin} {addr} sspi map={lay.short} include_realm=1 "
                  "compat_realm=1",
                  f"hostssl {dbs} {lay.read},{lay.write} {addr} scram-sha-256"]
    lines += ["hostnossl all all 127.0.0.1/32 reject", "hostnossl all all ::1/128 reject",
              "host all all 0.0.0.0/0 reject", "host all all ::0/0 reject"]
    return "\n".join(lines) + "\n"


def conf(lay: Layout) -> str:
    lay = layout(lay)
    return real.conf(lay.target) + "log_disconnections = on\nmax_connections = 60\n"




def build_template(lay: Layout, pid: int, rec: g.Record, admin_fn: Callable) -> dict:
    """`admin_fn(db, pid, autocommit=...)` is the caller's admin connection function for this layout."""
    lay = layout(lay)
    ar.fix_app_environment()
    from app import database

    def forbidden(*_, **__):
        raise AssertionError("app connection path used during preparation")

    with mock.patch.object(database, "get_connection", forbidden), mock.patch.object(database, "init_db", forbidden), \
            mock.patch.object(database, "initialize_database", forbidden), \
            admin_fn(lay.template, pid, autocommit=False) as raw:
        raw.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(lay.owner)))
        raw.row_factory = dict_row
        database.ensure_schema(database.AppPostgresConnection(raw))
        for statement in SEED:
            raw.execute(statement)
        raw.execute("RESET ROLE")
        raw.commit()
        raw.row_factory = psycopg.rows.tuple_row
        ids = synthetic_ids(raw)
        raw.rollback()
    rec.event("app_schema_created", database=lay.template, via="app.database.ensure_schema", role=lay.owner,
              seed_statements=len(SEED))
    return ids


def prepare(lay: Layout, *, admin_fn: Callable, build_fn: Callable, grants_fn: Callable) -> None:
    """The cluster, TLS, roles, template + check DBs, data, identity rows and contract grants of ONE layout.
    The callables are the caller's own (admin connection, template build, contract grants of a DB)."""
    lay = layout(lay)
    T = lay.target
    if g.pg_environment_present():
        raise CheckFailed("preparation_failure", "PG environment variables present")
    if T.root.exists():
        raise CheckFailed("preparation_failure", f"{lay.short} root already exists")
    if g.listener_pids(T.port):
        raise CheckFailed("preparation_failure", f"port {T.port} in use")
    run_id = time.strftime("%Y%m%dT%H%M%S")
    for folder in (T.root, T.tls, T.runs, T.runs / run_id):
        folder.mkdir()
    rec = g.Record(T.runs / run_id)
    rec.event("folders_created", paths=[str(T.root), str(T.tls), str(T.runs), str(rec.folder)])
    secret = Path(os.environ["LOCALAPPDATA"]) / "Temp" / f"jpv_{lay.short}_{run_id}"
    secret.mkdir()
    rec.event("secret_folder_created", path=str(secret))
    real.make_tls(rec, secret, T)
    base.run([str(g.BIN / "initdb.exe"), "-D", str(T.data), "-U", lay.admin, "-A", "reject", "-E", "UTF8",
              "--locale=C", "--no-instructions"])
    rec.event("initdb", data=str(T.data), bootstrap_role=lay.admin)
    principal = f"{os.environ['USERNAME']}@{os.environ['COMPUTERNAME']}"
    with open(T.data / "postgresql.conf", "a", encoding="utf-8", newline="\n") as handle:
        handle.write(conf(lay))
    (T.data / "pg_hba.conf").write_text(hba(lay), encoding="utf-8", newline="\n")
    (T.data / "pg_ident.conf").write_text(f"{lay.short} {principal} {lay.admin}\n", encoding="utf-8", newline="\n")
    rec.event("config_written", files=["postgresql.conf (appended)", "pg_hba.conf", "pg_ident.conf"])
    pid = real.start_server(rec, T)
    roles = {}
    with admin_fn("postgres", pid) as conn:
        version = conn.execute("SELECT pg_catalog.current_setting('server_version_num')").fetchone()[0]
        system_id = conn.execute("SELECT system_identifier::text FROM pg_catalog.pg_control_system()").fetchone()[0]
        for role, login in ((lay.owner, False), (lay.read, True), (lay.write, True)):
            stmt = sql.SQL("CREATE ROLE {} {} NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS").format(
                sql.Identifier(role), sql.SQL("LOGIN" if login else "NOLOGIN"))
            if login:
                stmt = sql.SQL("{} PASSWORD {}").format(stmt, sql.Literal(g.scram_verifier(g.new_password())))
            conn.execute(stmt)
            roles[role] = conn.execute("SELECT oid FROM pg_catalog.pg_roles WHERE rolname = %s", (role,)).fetchone()[0]
            rec.event("role_created", name=role, oid=roles[role])
        conn.execute(sql.SQL("CREATE DATABASE {} OWNER {} TEMPLATE template0 ENCODING 'UTF8' LOCALE 'C'").format(
            sql.Identifier(lay.template), sql.Identifier(lay.owner)))
        rec.event("database_created", name=lay.template, oid=conn.execute(
            "SELECT oid FROM pg_catalog.pg_database WHERE datname = %s", (lay.template,)).fetchone()[0])
        conn.execute(sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(sql.Identifier(lay.template)))
    with admin_fn(lay.template, pid) as conn:
        conn.execute(sql.SQL("CREATE SCHEMA {} AUTHORIZATION {}").format(sql.Identifier(SYN), sql.Identifier(lay.owner)))
        conn.execute(sql.SQL("CREATE TABLE {}.db_identity (identity_value text NOT NULL)").format(sql.Identifier(SYN)))
        conn.execute(sql.SQL("ALTER TABLE {}.db_identity OWNER TO {}").format(sql.Identifier(SYN),
                                                                            sql.Identifier(lay.owner)))
    ids = build_fn(pid, rec)
    databases = {}
    with admin_fn("postgres", pid) as conn:
        for check_id, db in lay.check_db.items():           # a fresh clone per check; then this DB's own nonce
            conn.execute(sql.SQL("CREATE DATABASE {} OWNER {} TEMPLATE {}").format(
                sql.Identifier(db), sql.Identifier(lay.owner), sql.Identifier(lay.template)))
            oid = conn.execute("SELECT oid FROM pg_catalog.pg_database WHERE datname = %s", (db,)).fetchone()[0]
            rec.event("database_created", name=db, oid=oid)
            conn.execute(sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(sql.Identifier(db)))
            databases[db] = {"oid": oid, "identity_value": f"{lay.short}-{check_id}-{secrets.token_hex(8)}"}
    for db, facts in databases.items():
        with admin_fn(db, pid) as conn:
            conn.execute(sql.SQL("INSERT INTO {}.db_identity (identity_value) VALUES (%s)").format(sql.Identifier(SYN)),
                         (facts["identity_value"],))
            facts["objects"] = {t: conn.execute("SELECT %s::regclass::oid", (f"public.{t}",)).fetchone()[0]
                                for t in OID_TABLES}
            for statement in grants_fn(db):
                conn.execute(statement)
        rec.event("grants", database=db, source="srs_migrate.READ_PRIVILEGES / WRITE_PRIVILEGES")
    target = {"run_id": rec.folder.name, "host": g.HOST, "port": T.port, "data": str(T.data),
              "postgres_exe": str(g.POSTGRES_EXE), "postmaster_pid": pid, "server_version_num": version,
              "system_identifier": system_id, "databases": databases, "roles": roles,
              "provider_roles": list(lay.business_roles), "admin_role": lay.admin,
              "ca_sha256": base.sha(T.tls / "ca.crt"), "synthetic": ids}
    data = json.dumps(target, indent=1, sort_keys=True).encode()
    (rec.folder / "target.json").write_bytes(data)
    rec.event("target_written", sha256=hashlib.sha256(data).hexdigest(), server_version_num=version)


def cleanup(lay: Layout, *, admin_fn: Callable) -> None:
    """R2: only what this run recorded; any difference stops before deleting anything (no cascading drop, no
    process search: the server is stopped through its own data folder)."""
    lay = layout(lay)
    T = lay.target
    rec = g.single_run(T)
    started = rec.find("server_started")
    expect(len(started) == 1, "exactly one server start recorded", "harness_defect")
    pid = started[0]["pid"]
    target = require_target_bound(lay, rec, (rec.folder / "target.json").read_bytes())
    expect(target["postmaster_pid"] == pid, "target PID = recorded start", "harness_defect")
    if g.postmaster_pid(T) is not None:
        expect(g.server_is_ours(pid, T), "live server matches the record", "harness_defect")
        with admin_fn("postgres", pid) as conn:
            expect(conn.execute("SELECT system_identifier::text FROM pg_catalog.pg_control_system()").fetchone()[0]
                   == target["system_identifier"], "system identifier", "harness_defect")
            for e in rec.find("database_created"):
                row = conn.execute("SELECT oid FROM pg_catalog.pg_database WHERE datname = %s", (e["name"],)).fetchone()
                expect(row is not None and row[0] == e["oid"], f"database {e['name']} OID", "harness_defect")
            for e in rec.find("role_created"):
                row = conn.execute("SELECT oid FROM pg_catalog.pg_roles WHERE rolname = %s", (e["name"],)).fetchone()
                expect(row is not None and row[0] == e["oid"], f"role {e['name']} OID", "harness_defect")
            open_sessions = conn.execute("SELECT count(*) FROM pg_catalog.pg_stat_activity WHERE usename = ANY (%s)",
                                         (list(lay.business_roles),)).fetchone()[0]
            expect(open_sessions == 0, "no business session left", "harness_defect")
        base.run([str(g.BIN / "pg_ctl.exe"), "stop", "-D", str(T.data), "-m", "fast", "-w", "-t", "60", "-s"])
    for _ in range(20):
        if g.process_image(pid) is None and not g.listener_pids(T.port):
            break
        time.sleep(0.5)
    expect(g.process_image(pid) is None and not g.listener_pids(T.port) and g.postmaster_pid(T) is None,
           "server stopped", "harness_defect")
    expect(all(not os.path.lexists(e["path"]) for e in rec.find("secret_folder_created")), "secret folder gone",
           "harness_defect")
    expect(rec.find("folders_created")[0]["paths"][0] == str(T.root)
           and set(os.listdir(T.root)) <= {"data", "tls", "runs"}, f"{lay.short} contents as recorded", "harness_defect")
    shutil.rmtree(T.root)
    expect(not T.root.exists(), f"{lay.short} removed", "harness_defect")

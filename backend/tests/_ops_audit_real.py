"""Real local PostgreSQL check of the read-only audit (OPS_AUDIT_REAL_PG_PLAN.md), run explicitly,
never by discovery and never by import:

    python tests/_ops_audit_real.py prepare    # pg63 cluster, TLS, roles, two DBs, app schema, data, grants
    python tests/_ops_audit_real.py check      # the plan's 6-item checklist
    python tests/_ops_audit_real.py cleanup    # R2: record vs live facts, stop, delete this run only

The target is the closed preset `_ops_pg62.PG63_AUDIT` (C:/JV_Tools/pg63, localhost:55472,
jp_vocab_test_audit_ok / _bad, roles jpva_admin / jpva_owner / jpva_audit); no argument or
environment value chooses it. The admin connection prepares, varies and reverts; only the audit
role reaches the provider. Expected objects and privileges are fixed in code from the app source
(below), never taken from what the server shows. A standalone audit's `partial` / exit 3 is the
EXPECTED audit result inside check c1; this runner's own exit status is 0 only when every planned
check passed and was recorded.

The existing CLI comparison path (`--local-test-postgres`) can only use `sslmode=require`: its URL
guard has no `sslrootcert`. That is a comparison-only limit; the provider path keeps verify-full.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from unittest import mock
from urllib.parse import quote

TESTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS_DIR.parent / "scripts"))
sys.path.insert(0, str(TESTS_DIR))
# The backend folder, so a fresh `check` process finds `app` when `_ops_audit_run` imports it after
# its environment pin and pre-check. A path entry only: nothing from app is imported here.
if str(TESTS_DIR.parent) not in sys.path:
    sys.path.append(str(TESTS_DIR.parent))

import psycopg  # noqa: E402
from psycopg import sql  # noqa: E402
from psycopg.rows import dict_row  # noqa: E402

import _ops_approval as oa  # noqa: E402
import _ops_audit_run as ar  # noqa: E402
import _ops_preflight as op  # noqa: E402
import _ops_provider as pv  # noqa: E402
import _ops_pg62 as g  # noqa: E402
import _ops_pg62_real as base  # noqa: E402  (helpers only: run, openssl, expect, run_check)
import test_ops_preflight as pf  # noqa: E402  (helpers only)
import test_ops_signature as sigtests  # noqa: E402  (test key helper only)

T = g.PG63_AUDIT
OWNER, AUDIT = "jpva_owner", "jpva_audit"
DB_OK, DB_BAD = T.databases
SYN = "jp_vocab_ops_synthetic"
CheckFailed, expect = base.CheckFailed, base.expect

# --- fixed from the app source (OPS_AUDIT_REAL_PG_PLAN.md 0·4·5절) -----------------------------------
# What a standalone audit reads (app/srs/invariant_audit.py `_Audit.__init__` `_rows` + `users` +
# `meaning_feedback`; I4 `identity.scan_identity`; I3 the vocab_items id sequence). Not
# `shared_deck_words` / `user_deck_subscriptions`: those are read by `migration._authorized()`, which
# the audit never calls (`_reduced_scope()` reads no table).
AUDIT_TABLES = ("users", "vocab_items", "user_word_progress", "review_logs", "lexeme_review_logs",
                "srs_review_receipts", "srs_migration_snapshots", "srs_migration_runs", "srs_card_deletions",
                "srs_card_identity_flags", "srs_evidence_restarts", "account_write_blocks",
                "account_recovery_runs", "meaning_feedback")
AUDIT_SEQUENCE = "vocab_items_id_seq"
# Every table `app.database.ensure_schema` creates on PostgreSQL (create_postgres_tables + ensure_srs_schema).
CORE_TABLES = ("users", "decks", "vocab_items", "custom_terms", "shared_decks", "shared_deck_items",
               "shared_deck_terms", "shared_deck_imports", "lexemes", "shared_deck_words",
               "user_deck_subscriptions", "user_word_progress", "review_logs", "lexeme_review_logs",
               "meaning_feedback", "app_feedback")                      # all with an identity id
SRS_TABLES = ("srs_config_versions", "srs_user_settings", "srs_review_receipts", "srs_migration_runs",
              "srs_migration_snapshots", "srs_card_deletions", "srs_card_identity_flags",
              "srs_evidence_restarts", "account_write_blocks", "account_recovery_runs")
SRS_WITHOUT_IDENTITY = ("srs_config_versions", "srs_user_settings")
SEARCH_PATH = '"$user", public'


def expected_profile(db: str) -> pv.ExpectedProfile:
    sequences = [f"{t}_id_seq" for t in CORE_TABLES + SRS_TABLES if t not in SRS_WITHOUT_IDENTITY]
    objects = {("database", "", db), ("schema", "", "public"), ("schema", "", SYN), ("table", SYN, "db_identity"),
               ("tablespace", "", "pg_default"), ("tablespace", "", "pg_global")}
    objects |= {("table", "public", t) for t in CORE_TABLES + SRS_TABLES}
    objects |= {("sequence", "public", s) for s in sequences}
    privileges = {("database", "", db, "", "CONNECT"), ("schema", "", "public", "", "USAGE"),
                  ("schema", "", SYN, "", "USAGE"), ("table", SYN, "db_identity", "", "SELECT"),
                  ("sequence", "public", AUDIT_SEQUENCE, "", "SELECT")}
    privileges |= {("table", "public", t, "", "SELECT") for t in AUDIT_TABLES}
    return pv.ExpectedProfile(frozenset(objects), frozenset(privileges), SEARCH_PATH, frozenset({"TLSv1.3"}))


# --- prepare (P2; not run without approval) -----------------------------------------------------------

def _target(target: g.Target | None) -> g.Target:
    """This module's own preset by default; another closed preset only when a caller names it (RS4-1: the
    C12 / RS4 runners pass theirs instead of replacing this module's global)."""
    return T if target is None else g.preset(target)


def conf(target: g.Target | None = None) -> str:
    t = _target(target)
    tls = str(t.tls).replace("\\", "/")
    return (f"\n# --- audit real-PG test cluster (OPS_AUDIT_REAL_PG_PLAN.md) ---\nport = {t.port}\n"
            "listen_addresses = 'localhost'\nmax_connections = 30\nssl = on\n"
            f"ssl_cert_file = '{tls}/server.crt'\nssl_key_file = '{tls}/server.key'\n"
            "ssl_min_protocol_version = 'TLSv1.3'\npassword_encryption = 'scram-sha-256'\n"
            "log_statement = 'none'\nlog_min_error_statement = 'panic'\nlog_connections = on\n"
            "logging_collector = off\n")


def hba() -> str:
    lines = []
    for addr in ("127.0.0.1/32", "::1/128"):
        lines += [f"hostssl postgres,{DB_OK},{DB_BAD} {T.admin} {addr} sspi map=pg63 include_realm=1 compat_realm=1",
                  f"hostssl {DB_OK},{DB_BAD} {AUDIT} {addr} scram-sha-256"]
    lines += ["hostnossl all all 127.0.0.1/32 reject", "hostnossl all all ::1/128 reject",
              "host all all 0.0.0.0/0 reject", "host all all ::0/0 reject"]
    return "\n".join(lines) + "\n"


def make_tls(rec: g.Record, secret: Path, target: g.Target | None = None) -> None:
    tls = _target(target).tls
    base.openssl(secret, "genpkey", "-algorithm", "EC", "-pkeyopt", "ec_paramgen_curve:P-256", "-out", "ca.key")
    base.openssl(secret, "req", "-x509", "-new", "-key", "ca.key", "-sha256", "-days", "2",
                 "-subj", "/CN=jp_vocab audit synthetic test CA", "-addext", "basicConstraints=critical,CA:TRUE",
                 "-addext", "keyUsage=critical,keyCertSign,cRLSign", "-out", str(tls / "ca.crt"))
    base.openssl(secret, "genpkey", "-algorithm", "EC", "-pkeyopt", "ec_paramgen_curve:P-256",
                 "-out", str(tls / "server.key"))
    base.openssl(secret, "req", "-new", "-key", str(tls / "server.key"), "-subj", "/CN=localhost",
                 "-addext", "subjectAltName=DNS:localhost,IP:127.0.0.1,IP:::1", "-addext", "extendedKeyUsage=serverAuth",
                 "-addext", "basicConstraints=critical,CA:FALSE", "-out", "server.csr")
    base.openssl(secret, "x509", "-req", "-in", "server.csr", "-CA", str(tls / "ca.crt"), "-CAkey", "ca.key",
                 "-set_serial", "0x" + secrets.token_hex(8), "-days", "2", "-sha256", "-copy_extensions", "copy",
                 "-out", str(tls / "server.crt"))
    base.run(["icacls", str(tls / "server.key"), "/inheritance:r", "/grant:r", f"{os.environ['USERNAME']}:F"])
    rec.event("tls_created", folder=str(tls), certificates={n: base.sha(tls / f"{n}.crt") for n in ("ca", "server")},
              keys=[str(tls / "server.key")])
    for path in sorted(secret.iterdir()):
        path.unlink()
    secret.rmdir()
    expect(not secret.exists(), "secret folder removed", "preparation_failure")
    rec.event("secret_folder_removed", path=str(secret))


def start_server(rec: g.Record, target: g.Target | None = None) -> int:
    t = _target(target)
    base.run([str(g.BIN / "pg_ctl.exe"), "start", "-D", str(t.data), "-l", str(rec.folder / "server.log"), "-w",
              "-t", "30", "-s"])
    for _ in range(20):
        pid = g.postmaster_pid(t)
        if pid and g.server_is_ours(pid, t):
            rec.event("server_started", pid=pid, executable=g.process_image(pid), data=str(t.data), port=t.port)
            return pid
        time.sleep(0.5)
    raise CheckFailed("preparation_failure", "started server not confirmed as ours")


def admin(db: str, pid: int, autocommit: bool = True):
    return g.admin_connect(db, record_pid=pid, autocommit=autocommit, target=T)


SEED_OK = [  # synthetic learning data, owner role; the dev user and default deck come from ensure_schema
    "INSERT INTO vocab_items (user_id, deck_id, surface, base_form, reading, part_of_speech, normalized_form, "
    "status, created_at, updated_at) SELECT u.id, d.id, w.s, w.s, w.r, 'noun', w.s, 'learning', "
    "'2026-10-01T00:00:00+00:00', '2026-10-01T00:00:00+00:00' FROM users u JOIN decks d ON d.user_id = u.id "
    "CROSS JOIN (VALUES ('猫', 'ねこ'), ('犬', 'いぬ')) AS w (s, r) WHERE u.email = 'dev@example.local'",
    "INSERT INTO review_logs (user_id, vocab_item_id, deck_id, rating, reviewed_at, previous_review_level, "
    "next_review_level, next_review_at) SELECT v.user_id, v.id, v.deck_id, 'good', '2026-10-02T00:00:00+00:00', "
    "0, 1, '2026-10-03T00:00:00+00:00' FROM vocab_items v WHERE v.base_form = '猫'",
]
SEED_BAD = [  # one known I1 violation: a personal log whose card does not exist and has no deletion record
    "INSERT INTO review_logs (user_id, vocab_item_id, deck_id, rating, reviewed_at, previous_review_level, "
    "next_review_level, next_review_at) SELECT u.id, 999999, NULL, 'good', '2026-10-02T00:00:00+00:00', 0, 1, "
    "'2026-10-03T00:00:00+00:00' FROM users u WHERE u.email = 'dev@example.local'",
]


def build_app_schema(db: str, pid: int, rec: g.Record) -> None:
    """`app.database.ensure_schema` on the admin connection acting as the owner role; never init_db,
    get_connection, DATABASE_URL or .env (all of those are made to fail during this step)."""
    ar.fix_app_environment()
    backend = str(TESTS_DIR.parent)
    if backend not in sys.path:
        sys.path.insert(0, backend)
    from app import database

    def forbidden(*_, **__):
        raise AssertionError("app connection path used during preparation")

    with mock.patch.object(database, "get_connection", forbidden), mock.patch.object(database, "init_db", forbidden), \
            mock.patch.object(database, "initialize_database", forbidden), admin(db, pid, autocommit=False) as raw:
        raw.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(OWNER)))
        raw.row_factory = dict_row
        app_conn = database.AppPostgresConnection(raw)
        database.ensure_schema(app_conn)
        for statement in SEED_OK + (SEED_BAD if db == DB_BAD else []):
            raw.execute(statement)
        raw.execute("RESET ROLE")
        raw.commit()
    rec.event("app_schema_created", database=db, via="app.database.ensure_schema", role=OWNER,
              seed_statements=len(SEED_OK) + (len(SEED_BAD) if db == DB_BAD else 0),
              known_violation="I1 orphan personal log" if db == DB_BAD else None)


def grant_audit(db: str, pid: int, rec: g.Record) -> None:
    with admin(db, pid) as conn:
        conn.execute(sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(sql.Identifier(SYN), sql.Identifier(AUDIT)))
        conn.execute(sql.SQL("GRANT SELECT ON {}.db_identity TO {}").format(sql.Identifier(SYN), sql.Identifier(AUDIT)))
        for table in AUDIT_TABLES:
            conn.execute(sql.SQL("GRANT SELECT ON public.{} TO {}").format(sql.Identifier(table), sql.Identifier(AUDIT)))
        conn.execute(sql.SQL("GRANT SELECT ON SEQUENCE public.{} TO {}").format(sql.Identifier(AUDIT_SEQUENCE),
                                                                            sql.Identifier(AUDIT)))
    rec.event("audit_grants", database=db, tables=list(AUDIT_TABLES), sequence=AUDIT_SEQUENCE)


def prepare() -> None:
    if g.pg_environment_present():
        raise CheckFailed("preparation_failure", "PG environment variables present")
    if T.root.exists():
        raise CheckFailed("preparation_failure", "pg63 root already exists")
    if g.listener_pids(T.port):
        raise CheckFailed("preparation_failure", "port 55472 in use")
    run_id = time.strftime("%Y%m%dT%H%M%S")
    for folder in (T.root, T.tls, T.runs, T.runs / run_id):
        folder.mkdir()
    rec = g.Record(T.runs / run_id)
    rec.event("folders_created", paths=[str(T.root), str(T.tls), str(T.runs), str(rec.folder)])
    secret = Path(os.environ["LOCALAPPDATA"]) / "Temp" / f"jpv_pg63_{run_id}"
    secret.mkdir()
    rec.event("secret_folder_created", path=str(secret))
    make_tls(rec, secret)
    base.run([str(g.BIN / "initdb.exe"), "-D", str(T.data), "-U", T.admin, "-A", "reject", "-E", "UTF8",
              "--locale=C", "--no-instructions"])
    rec.event("initdb", data=str(T.data), bootstrap_role=T.admin)
    principal = f"{os.environ['USERNAME']}@{os.environ['COMPUTERNAME']}"
    with open(T.data / "postgresql.conf", "a", encoding="utf-8", newline="\n") as handle:
        handle.write(conf())
    (T.data / "pg_hba.conf").write_text(hba(), encoding="utf-8", newline="\n")
    (T.data / "pg_ident.conf").write_text(f"pg63 {principal} {T.admin}\n", encoding="utf-8", newline="\n")
    rec.event("config_written", files=["postgresql.conf (appended)", "pg_hba.conf", "pg_ident.conf"])
    pid = start_server(rec)
    nonce = secrets.token_hex(8)
    identities = {DB_OK: f"pg63-ok-{nonce}", DB_BAD: f"pg63-bad-{nonce}"}
    with admin("postgres", pid) as conn:
        version = conn.execute("SELECT pg_catalog.current_setting('server_version_num')").fetchone()[0]
        for role, login in ((OWNER, False), (AUDIT, True)):
            stmt = sql.SQL("CREATE ROLE {} {} NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS").format(
                sql.Identifier(role), sql.SQL("LOGIN" if login else "NOLOGIN"))
            if login:
                stmt = sql.SQL("{} PASSWORD {}").format(stmt, sql.Literal(g.scram_verifier(g.new_password())))
            conn.execute(stmt)
            rec.event("role_created", name=role, oid=conn.execute(
                "SELECT oid FROM pg_catalog.pg_roles WHERE rolname = %s", (role,)).fetchone()[0])
        for db in (DB_OK, DB_BAD):
            conn.execute(sql.SQL("CREATE DATABASE {} OWNER {} TEMPLATE template0 ENCODING 'UTF8' LOCALE 'C'").format(
                sql.Identifier(db), sql.Identifier(OWNER)))
            rec.event("database_created", name=db, oid=conn.execute(
                "SELECT oid FROM pg_catalog.pg_database WHERE datname = %s", (db,)).fetchone()[0])
            conn.execute(sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(sql.Identifier(db)))
            conn.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(sql.Identifier(db), sql.Identifier(AUDIT)))
    databases = {}
    for db in (DB_OK, DB_BAD):
        with admin(db, pid) as conn:
            conn.execute(sql.SQL("CREATE SCHEMA {} AUTHORIZATION {}").format(sql.Identifier(SYN), sql.Identifier(OWNER)))
            conn.execute(sql.SQL("CREATE TABLE {}.db_identity (identity_value text NOT NULL)").format(sql.Identifier(SYN)))
            conn.execute(sql.SQL("ALTER TABLE {}.db_identity OWNER TO {}").format(sql.Identifier(SYN), sql.Identifier(OWNER)))
            conn.execute(sql.SQL("INSERT INTO {}.db_identity (identity_value) VALUES (%s)").format(sql.Identifier(SYN)),
                         (identities[db],))
            oid = conn.execute("SELECT oid FROM pg_catalog.pg_database WHERE datname = "
                               "pg_catalog.current_database()").fetchone()[0]
        build_app_schema(db, pid, rec)
        grant_audit(db, pid, rec)
        databases[db] = {"oid": oid, "identity_value": identities[db]}
    target = {"run_id": rec.folder.name, "host": g.HOST, "port": T.port, "data": str(T.data),
              "postgres_exe": str(g.POSTGRES_EXE), "postmaster_pid": pid, "server_version_num": version,
              "databases": databases, "provider_roles": list(T.provider_roles), "admin_role": T.admin,
              "ca_sha256": base.sha(T.tls / "ca.crt")}
    data = json.dumps(target, indent=1, sort_keys=True).encode()
    (rec.folder / "target.json").write_bytes(data)
    rec.event("target_written", sha256=hashlib.sha256(data).hexdigest(), server_version_num=version)


# --- check (P3; not run without approval) -------------------------------------------------------------

POST_CONNECT = ("SELECT pg_catalog.host(pg_catalog.inet_server_addr()) AS server_addr, "
                "pg_catalog.inet_server_port() AS server_port, "
                "pg_catalog.current_setting('server_version_num') AS version, "
                "pg_catalog.current_database()::pg_catalog.text AS dbname, "
                "(SELECT d.oid FROM pg_catalog.pg_database AS d "
                " WHERE d.datname OPERATOR(pg_catalog.=) pg_catalog.current_database()) AS db_oid")


def post_connect_check(conn, target: dict) -> None:
    """Right after the guarded connect, before the provider's observation transaction: one read in
    its own transaction, rolled back, so the provider still sees an idle connection."""
    try:
        with conn.cursor(row_factory=dict_row) as cursor:
            cursor.execute(POST_CONNECT)
            facts = cursor.fetchone()
        conn.rollback()
    except psycopg.Error:
        conn.close()
        raise g.Pg62Refused("pg62_connected_target_unreadable") from None
    db = target["databases"].get(facts["dbname"])
    if facts["server_addr"] not in g.LOOPBACK or facts["server_port"] != T.port \
            or facts["version"] != target["server_version_num"] or db is None or facts["db_oid"] != db["oid"]:
        conn.close()
        raise g.Pg62Refused("pg62_connected_target_mismatch")


_COMMIT_WORDS = frozenset({"COMMIT", "END", "COMMIT TRANSACTION", "END TRANSACTION", "COMMIT WORK", "END WORK"})


def _is_commit(query) -> bool:
    """Only the whole-statement COMMIT / END spellings, as a string or a psycopg `sql` object
    (rendered without a connection). Not an SQL parser: anything else is not counted."""
    if isinstance(query, sql.Composable):
        try:
            query = query.as_string(None)
        except Exception:                                   # cannot render without a connection: not a bare COMMIT
            return False
    if not isinstance(query, str):
        return False
    return " ".join(query.strip().rstrip(";").split()).upper() in _COMMIT_WORDS


# Read-only probes the tracker runs on its own raw cursor (not counted, not through the audit):
# at the audit's first statement (`_require_snapshot`) and right before the audit transaction's rollback.
AUDIT_START_MARK = "current_setting('transaction_read_only') AS ro"
PROBE_SETTINGS = ("SELECT pg_catalog.current_setting('transaction_isolation') AS iso, "
                  "pg_catalog.current_setting('transaction_read_only') AS ro, "
                  "pg_catalog.current_setting('statement_timeout') AS st, "
                  "pg_catalog.current_setting('lock_timeout') AS lt")
PROBE_XID = "SELECT pg_catalog.pg_current_xact_id_if_assigned()::pg_catalog.text AS x"


class CommitTracker:
    """Wraps ONE audit connection (never an admin one). Counts commit() calls and COMMIT / END
    statements sent through the connection's execute() (and through the cursor it returns),
    through its cursors' execute() (plain or `with` cursors) and through `cursor.connection.commit()`; `AppPostgresConnection` reaches these
    through the raw connection. Every call is forwarded unchanged, so row factories, fetches, cursor
    closing, rollback and isolation behave as without it."""

    _OWN = frozenset({"_conn", "commits", "probe"})

    def __init__(self, conn):
        object.__setattr__(self, "_conn", conn)
        object.__setattr__(self, "commits", 0)
        object.__setattr__(self, "probe", {})               # audit settings / xid seen on this connection

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def __setattr__(self, name, value):
        if name in self._OWN:
            object.__setattr__(self, name, value)
        else:
            setattr(self._conn, name, value)                # e.g. row_factory reaches the real connection

    def _count(self) -> None:
        object.__setattr__(self, "commits", self.commits + 1)

    def commit(self):
        self._count()
        return self._conn.commit()

    def _read(self, query: str) -> dict:
        with self._conn.cursor(row_factory=dict_row) as cursor:
            cursor.execute(query)
            return dict(cursor.fetchone() or {})

    def rollback(self):
        """The xid probe is diagnostic only: whatever it does, the raw rollback is tried exactly once
        (plan 6-1 priority). A failed probe is recorded by error type, never as an xid."""
        if self.probe.get("calls") and "xid" not in self.probe and "xid_probe_failed" not in self.probe:
            try:
                self.probe["xid"] = self._read(PROBE_XID).get("x")   # still inside the audit transaction
            except Exception as error:
                self.probe["xid_probe_failed"] = type(error).__name__
        return self._conn.rollback()

    def execute(self, query, *args, **kwargs):
        if _is_commit(query):
            self._count()                                   # counted here once; the returned cursor adds nothing
        result = self._conn.execute(query, *args, **kwargs)
        if isinstance(query, str) and AUDIT_START_MARK in query:  # the audit's own first statement
            self.probe["calls"] = self.probe.get("calls", 0) + 1
            if self.probe["calls"] == 1:
                self.probe.update(self._read(PROBE_SETTINGS))
        # psycopg returns the cursor that ran the query: keep it on the same tracker
        return result if result is None or isinstance(result, TrackedCursor) else TrackedCursor(result, self)

    def cursor(self, *args, **kwargs):
        return TrackedCursor(self._conn.cursor(*args, **kwargs), self)


class TrackedCursor:
    """A cursor of a tracked connection: COMMIT / END through execute() and `.connection.commit()`
    are counted on the same tracker; everything else is the real cursor's."""

    _OWN = frozenset({"_cursor", "_tracker"})

    def __init__(self, cursor, tracker: CommitTracker):
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
    def connection(self) -> CommitTracker:
        return self._tracker                                # cursor.connection.commit() is counted too

    def __enter__(self):
        self._cursor.__enter__()
        return self                                         # `with tracked.cursor() as c` stays tracked

    def __exit__(self, *exc):
        return self._cursor.__exit__(*exc)

    def __iter__(self):
        return iter(self._cursor)

    def execute(self, query, *args, **kwargs):
        if _is_commit(query):
            self._tracker._count()
        self._cursor.execute(query, *args, **kwargs)
        return self                                         # psycopg returns the cursor itself


def audit_result(report: dict) -> dict:
    """The audit's own result, exactly as reported: the run metadata of the new path (`target`,
    `scope`) is set apart, nothing inside `checks` is dropped, converted or normalized."""
    return {key: report[key] for key in ("audit_version", "status", "checks", "reason") if key in report}


class Harness:
    def __init__(self, rec: g.Record):
        self.rec = rec
        self.target_bytes = (rec.folder / "target.json").read_bytes()
        self.target = json.loads(self.target_bytes)
        self.pid = self.target["postmaster_pid"]
        self.keys = sigtests.Keys()
        self.allowed = self.keys.allowed(namespaces="jp-vocab-ops/v1/synthetic/*")
        self.password = ""
        self.deploys: list[str] = []
        self.guards: list[g.Guard] = []
        self.trackers: list[CommitTracker] = []

    def close(self) -> None:
        self.keys.close()
        for folder in self.deploys:
            shutil.rmtree(folder, ignore_errors=True)
        self.password = ""

    def set_password(self) -> None:
        password = g.new_password()
        with admin("postgres", self.pid) as conn:
            conn.execute(sql.SQL("ALTER ROLE {} PASSWORD {}").format(sql.Identifier(AUDIT),
                                                                    sql.Literal(g.scram_verifier(password))))
        self.password = password

    def sign(self, data: bytes, subject: str) -> bytes:
        return self.keys.sign("signer", oa.signature_namespace("synthetic", subject), data)

    def ca_pem(self) -> bytes:
        return (T.tls / "ca.crt").read_bytes()

    def inputs(self, *, db=DB_OK, identity_db=None, job_inputs=None, tamper=False) -> op.PreflightInput:
        folder = os.path.normpath(tempfile.mkdtemp(prefix="ops_pg63_deploy_"))
        self.deploys.append(folder)
        files = {k: v for k, v in pf.FILES.items() if k != "ops/tls/root.pem"}
        files["ops/tls/root.pem"] = self.ca_pem()
        files[T.target_doc] = self.target_bytes
        for rel, data in files.items():
            path = os.path.join(folder, *rel.split("/"))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as handle:
                handle.write(data)
        manifest = pf.manifest_doc(files)
        identity = self.target["databases"][identity_db or db]["identity_value"]
        target = op.TargetObservation(host=g.HOST, port=T.port, database=db, server_major=18, identity_value=identity)
        db_identity = pf.db_identity(target)
        profile = pv.expected_profile_fingerprint(expected_profile(db), role=AUDIT, access="read")
        scope = {"audit_scope": "database_all", "audit_db_identity": db_identity}
        signed_scope = scope if job_inputs is None else job_inputs
        doc = {"format_version": 1, "kind": "inquiry", "approval_id": "inq-0000000000000063", "supersedes": None,
               "purpose": "synthetic", "alias": "synthetic-primary", "db_identity": db_identity,
               "manifest": pf.om.manifest_fingerprint(manifest), "tool": "srs_invariant_audit",
               "steps": [{"command": "audit", "access": "read", "role": AUDIT, "profile": profile}],
               "accounts": [7], "max_accounts": 1, "job": {"key": "audit-real-1", "inputs": signed_scope},
               "valid_from": "2026-10-21T12:00:00Z", "valid_until": "2026-10-21T13:00:00Z",
               "approved_by": "synthetic signer"}
        approval = json.dumps(doc).encode()
        signature = self.sign(approval, "approval")
        if tamper:
            approval = json.dumps(doc, indent=1).encode()                   # same content, other bytes
        root = os.path.join(folder, "ops", "tls", "root.pem")
        dsn = f"postgresql://{AUDIT}:{self.password}@{g.HOST}:{T.port}/{db}?sslmode=verify-full" \
              f"&sslrootcert={quote(root, safe='')}"
        return op.PreflightInput(
            mode="synthetic", approval=approval, approval_signature=signature, manifest=manifest,
            manifest_signature=self.sign(manifest, "manifest"), deploy_root=folder, command="audit", args={},
            account_id=7, job_key="audit-real-1", job_inputs=scope, product_fingerprint=pf.PRODUCT, target=target,
            connection=op.ConnectionObservation(profile=profile, read_only=True), secret_dsn=dsn,
            environment={"PATH": "C:/Windows"}, trust=op.SyntheticTrust(self.allowed, b"", sigtests.PRINCIPAL),
            now=sigtests.T0)

    def driver(self, inputs):
        guard = g.Guard(inputs.manifest, inputs.deploy_root, self.rec.folder, target=T)
        self.guards.append(guard)

        def connect(**kwargs):
            conn = guard.driver(**kwargs)
            post_connect_check(conn, guard.target)
            tracked = CommitTracker(conn)                     # the audit connection only
            self.trackers.append(tracked)
            return tracked
        return connect

    def audit(self, inputs, db=DB_OK):
        """The new path, as is: no app import here (the runner imports app only after its environment
        pin and pre-check). Settings, xid and commits come from the audit connection's tracker."""
        first = len(self.trackers)
        out, code = ar.run_synthetic_audit(inputs, expected=expected_profile(db), driver=self.driver(inputs))
        probe: dict = {}
        for tracker in self.trackers[first:]:
            probe.update(tracker.probe)
        probe["calls"] = sum(t.probe.get("calls", 0) for t in self.trackers[first:])
        probe["commits"] = sum(t.commits for t in self.trackers[first:])
        return out, code, probe

    def cli(self, db: str) -> tuple[dict, int]:
        """The existing --local-test-postgres path, unchanged; env values only inside this call."""
        expect(g.server_is_ours(self.pid, T) and not g.pg_environment_present(), "comparison target", "harness_defect")
        import srs_invariant_audit as cli
        url = f"postgresql://{AUDIT}:{self.password}@{g.HOST}:{T.port}/{db}?sslmode=require"   # comparison only
        out = io.StringIO()
        env = {"SRS_E_TEST_POSTGRES_OPT_IN": "1", "SRS_E_TEST_POSTGRES_URL": url}
        with mock.patch.dict(os.environ, env), contextlib.redirect_stdout(out):
            try:
                cli.main(["--local-test-postgres"])
                code = 0
            except SystemExit as stop:
                code = stop.code
        return json.loads(out.getvalue()), code

    def snapshot(self, db: str) -> dict:
        with admin(db, self.pid) as conn:
            return {t: conn.execute(sql.SQL("SELECT count(*) AS n, coalesce(max(xmin::text::bigint), 0) AS x FROM "
                                            "public.{}").format(sql.Identifier(t))).fetchone()[0:2]
                    for t in AUDIT_TABLES}

    def sessions(self) -> int:
        with admin("postgres", self.pid) as conn:
            return conn.execute("SELECT count(*) FROM pg_catalog.pg_stat_activity WHERE usename = %s",
                                (AUDIT,)).fetchone()[0]


def require_probe(probe: dict) -> None:
    """A failed diagnostic probe makes the evidence incomplete: a harness defect, judged before any
    product expectation (plan 6-1 priority)."""
    if "xid_probe_failed" in probe:
        raise CheckFailed("harness_defect", f"xid probe failed ({probe['xid_probe_failed']})")


def same_audit(new: dict, new_code: int, old: dict, old_code: int, what: str) -> None:
    expect((audit_result(new), new_code) == (audit_result(old), old_code), what)


def c1_ok_new_path(h: Harness) -> dict:
    before = h.snapshot(DB_OK)
    out, code, probe = h.audit(h.inputs())
    require_probe(probe)
    expect(out["status"] == "partial" and code == 3, f"standalone audit expected partial/3, got {out.get('status')}/{code}")
    expect(all(out["checks"][f"I{i}"]["status"] == "pass" for i in range(1, 6)), "I1..I5 pass on normal data")
    expect(out["checks"]["I6"]["status"] == out["checks"]["I7"]["status"] == "not_evaluated", "I6/I7 not_evaluated")
    expect((probe.get("iso"), probe.get("ro"), probe.get("st"), probe.get("lt")) ==
           ("repeatable read", "on", "15s", "5s"), "audit transaction settings")
    expect(probe.get("xid") is None and probe.get("calls") == 1, "no transaction id assigned (no write)")
    expect(probe.get("commits") == 0, "no commit on the audit connection")
    expect(h.snapshot(DB_OK) == before, "rows and xmin unchanged")
    expect(h.sessions() == 0, "audit session closed")
    return {"status": out["status"], "exit": code, "settings": [probe["iso"], probe["ro"], probe["st"], probe["lt"]]}


def c2_compare_cli(h: Harness) -> dict:
    new, new_code, probe = h.audit(h.inputs())
    require_probe(probe)
    old, old_code = h.cli(DB_OK)
    expect(probe.get("commits") == 0, "no commit on the audit connection")
    same_audit(new, new_code, old, old_code, "new path equals the existing local CLI on normal data")
    return {"status": old["status"], "exit": old_code, "cli_tls": "sslmode=require (comparison only)"}


def c3_violation(h: Harness) -> dict:
    new, new_code, probe = h.audit(h.inputs(db=DB_BAD), db=DB_BAD)
    require_probe(probe)
    old, old_code = h.cli(DB_BAD)
    expect(probe.get("commits") == 0, "no commit on the audit connection")
    expect(new["status"] == "fail" and new_code == 1 and new["checks"]["I1"]["status"] == "fail",
           "known I1 violation detected")
    same_audit(new, new_code, old, old_code, "both paths agree on the violation data")
    return {"I1": new["checks"]["I1"]["status"], "exit": new_code}


def c4_refused_without_audit(h: Harness) -> dict:
    codes = {}
    cases = {"scope_missing": dict(job_inputs={}), "signature": dict(tamper=True),
             "other_db": dict(identity_db=DB_BAD)}
    for label, change in cases.items():
        out, code, probe = h.audit(h.inputs(**change))
        require_probe(probe)
        expect(code == 2 and out["status"] == "error" and probe.get("calls", 0) == 0 and probe.get("commits") == 0,
               f"{label}: refused, no audit")
        codes[label] = out["reason"]
    with admin(DB_OK, h.pid) as conn:
        conn.execute(sql.SQL("GRANT INSERT ON public.users TO {}").format(sql.Identifier(AUDIT)))
        h.rec.event("variant_applied", check="c4_excess_privilege")
        try:
            out, code, probe = h.audit(h.inputs())
            require_probe(probe)
        finally:
            conn.execute(sql.SQL("REVOKE INSERT ON public.users FROM {}").format(sql.Identifier(AUDIT)))
            h.rec.event("variant_reverted", check="c4_excess_privilege")
    expect(out["reason"] == "observed_privileges_excess" and probe.get("calls", 0) == 0 and probe.get("commits") == 0,
           "excess privilege refused")
    codes["excess_privilege"] = out["reason"]
    expect(codes["scope_missing"] == "audit_scope_missing" and codes["signature"] == "preflight_approval_signature_invalid"
           and codes["other_db"] == "observed_identity_mismatch", f"refusal codes {codes}")
    expect(h.sessions() == 0, "no audit session left")
    return {"codes": codes}


PLANNED = ("c1_ok_new_path", "c2_compare_cli", "c3_violation", "c4_refused_without_audit")
CHECKS = [("c1_ok_new_path", c1_ok_new_path), ("c2_compare_cli", c2_compare_cli), ("c3_violation", c3_violation),
          ("c4_refused_without_audit", c4_refused_without_audit)]
# plan 6절 #5 (isolation, read only, 15s/5s) and #6 (no write, data unchanged, session closed) are
# asserted inside c1, #4's sessions inside c4.


def check() -> int:
    if g.pg_environment_present():
        raise CheckFailed("preparation_failure", "PG environment variables present")
    rec = g.single_run(T)
    h = Harness(rec)
    if not g.server_is_ours(h.pid, T):
        raise CheckFailed("preparation_failure", "server not ours")
    passed = 0
    try:
        h.set_password()
        rec.event("check_phase_started", checks=[n for n, _ in CHECKS])
        for name, fn in CHECKS:
            if not base.run_check(rec, name, fn, h):
                return passed
            passed += 1
    finally:
        h.close()
    return passed


# --- cleanup (P4; not run without approval) -----------------------------------------------------------

def cleanup() -> None:
    rec = g.single_run(T)
    started = rec.find("server_started")
    expect(len(started) == 1, "exactly one server start recorded", "harness_defect")
    pid = started[0]["pid"]
    if g.postmaster_pid(T) is not None:
        expect(g.server_is_ours(pid, T), "live server matches the record", "harness_defect")
        with admin("postgres", pid) as conn:
            for e in rec.find("database_created"):
                row = conn.execute("SELECT oid FROM pg_catalog.pg_database WHERE datname = %s", (e["name"],)).fetchone()
                expect(row is not None and row[0] == e["oid"], f"database {e['name']} OID matches", "harness_defect")
            for e in rec.find("role_created"):
                row = conn.execute("SELECT oid FROM pg_catalog.pg_roles WHERE rolname = %s", (e["name"],)).fetchone()
                expect(row is not None and row[0] == e["oid"], f"role {e['name']} OID matches", "harness_defect")
        base.run([str(g.BIN / "pg_ctl.exe"), "stop", "-D", str(T.data), "-m", "fast", "-w", "-t", "60", "-s"])
    for _ in range(20):
        if g.process_image(pid) is None and not g.listener_pids(T.port):
            break
        time.sleep(0.5)
    expect(g.process_image(pid) is None and not g.listener_pids(T.port) and g.postmaster_pid(T) is None,
           "server stopped", "harness_defect")
    expect(all(not os.path.lexists(e["path"]) for e in rec.find("secret_folder_created")), "secret folder gone",
           "harness_defect")
    expect(rec.find("folders_created")[0]["paths"][0] == str(T.root) and set(os.listdir(T.root)) <= {"data", "tls", "runs"},
           "pg63 contents as recorded", "harness_defect")
    shutil.rmtree(T.root)
    expect(not T.root.exists(), "pg63 removed", "harness_defect")


def main(argv: list[str]) -> int:
    phase = argv[0] if len(argv) == 1 else ""
    try:
        if phase == "prepare":
            prepare()
            print("prepared")
        elif phase == "check":
            available = [n for n, _ in CHECKS if n in PLANNED]
            passed = check()
            print(f"passed {passed} / {len(PLANNED)}")
            if available != list(PLANNED) or passed != len(PLANNED):
                print("STOP: not all planned checks passed and were recorded")
                return 1
        elif phase == "cleanup":
            cleanup()
            print("cleaned")
        else:
            print("usage: prepare | check | cleanup")
            return 2
    except CheckFailed as failed:
        print(f"STOP ({failed.kind}): {failed.what}")
        return 1
    except pv.OpsProviderRefused as refused:
        print(f"STOP (refused): {refused.code}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

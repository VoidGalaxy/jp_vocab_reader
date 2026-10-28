"""Synthetic backup / restore rehearsal on a real local PostgreSQL (OPS_BACKUP_RESTORE_REHEARSAL_PLAN.md),
run explicitly, never by discovery and never by import:

    python tests/_ops_backup_real.py prepare    # pg64 cluster, TLS, roles, three DBs, app schema, data, grants
    python tests/_ops_backup_real.py check      # baseline gate (no child), then b1..b8: dump, restore, ...
    python tests/_ops_backup_real.py cleanup    # R2: record vs live facts, stop, delete this run (dumps included)

This is a same-cluster logical restore rehearsal with synthetic data. It is NOT a production backup
method, NOT disaster recovery and NOT a recovery-time measurement. The target is the closed preset
`_ops_pg62.PG64_BACKUP` (C:/JV_Tools/pg64, localhost:55482, jp_vocab_test_br_src / _dst / _fail);
no argument or environment value chooses it. `pg_dump` / `pg_restore` run as child processes from
fixed argument arrays (no shell), with every PG* variable removed from the child environment and a
secret-free connection string (SSPI roles, verify-full against this run's CA). The backup role reads
the source only; restores go only to the approved target DBs; a normal restore needs an empty DB,
a non-empty target exists only for the b8 failure injection.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
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
if str(TESTS_DIR.parent) not in sys.path:      # path only: app is imported by the runners after their checks
    sys.path.append(str(TESTS_DIR.parent))

from psycopg import sql  # noqa: E402
from psycopg.rows import dict_row  # noqa: E402

import _ops_approval as oa  # noqa: E402
import _ops_audit_real as real  # noqa: E402  (fixed audit lists, profile, commit tracking, result comparison)
import _ops_audit_run as ar  # noqa: E402
import _ops_preflight as op  # noqa: E402
import _ops_provider as pv  # noqa: E402
import _ops_pg62 as g  # noqa: E402
import _ops_pg62_real as base  # noqa: E402  (run, openssl, sha, expect, run_check)
import test_ops_preflight as pf  # noqa: E402  (helpers only)
import test_ops_signature as sigtests  # noqa: E402  (test key helper only)

T = g.PG64_BACKUP
SRC, DST, FAIL = T.databases
ADMIN, OWNER, BACKUP, AUDIT = T.admin, "jpvb_owner", "jpvb_backup", "jpvb_audit"
SYN = real.SYN
DUMPS = T.root / "dumps"
PG_DUMP, PG_RESTORE = g.BIN / "pg_dump.exe", g.BIN / "pg_restore.exe"
DUMP_TIMEOUT, RESTORE_TIMEOUT, REAP_TIMEOUT = 300, 300, 10        # seconds
CheckFailed, expect = base.CheckFailed, base.expect
# Which role may reach which DB through a child process (plan 4절). The audit role never runs a child.
CHILD_ACCESS = {BACKUP: (SRC,), ADMIN: (DST, FAIL)}


# --- child processes (pg_dump / pg_restore) ---------------------------------------------------------

def conninfo(db: str, role: str) -> str:
    """Secret-free libpq connection string: SSPI role, verify-full against this run's CA."""
    if db not in CHILD_ACCESS.get(role, ()):
        raise g.Pg62Refused("pg64_child_target_refused")
    ca = str(T.tls / "ca.crt").replace("\\", "/")
    return (f"host={g.HOST} port={T.port} dbname={db} user={role} sslmode=verify-full sslrootcert={ca} "
            "sslcertmode=disable gssencmode=disable connect_timeout=10")


def child_env(environ: dict | None = None) -> dict:
    """The parent environment without any PG* variable (any case)."""
    source = os.environ if environ is None else environ
    return {k: v for k, v in source.items() if not k.upper().startswith("PG")}


def dump_path(run_id: str) -> Path:
    if not re.fullmatch(r"\d{8}T\d{6}", run_id):
        raise g.Pg62Refused("pg64_run_id_invalid")
    return DUMPS / run_id / "src.dump"


def dump_args(run_id: str) -> list[str]:
    return [str(PG_DUMP), "--format=custom", "--no-password",
            f"--exclude-table-data={SYN}.db_identity",          # the definition stays, the row is not copied
            f"--file={dump_path(run_id)}", f"--dbname={conninfo(SRC, BACKUP)}"]


def list_args(dump: Path) -> list[str]:
    return [str(PG_RESTORE), "--list", str(dump)]                 # reads the file only, no connection


def restore_args(db: str, dump: Path) -> list[str]:
    if db not in (DST, FAIL):
        raise g.Pg62Refused("pg64_restore_target_refused")
    if Path(dump).parent.parent != DUMPS:
        raise g.Pg62Refused("pg64_dump_path_refused")
    return [str(PG_RESTORE), "--single-transaction", "--exit-on-error", "--no-password",
            f"--dbname={conninfo(db, ADMIN)}", str(dump)]


def classify_child(stderr: str) -> str:
    """Fixed label for evidence; the raw text is never kept."""
    text = stderr.lower()
    for key, label in (("already exists", "relation_already_exists"), ("permission denied", "permission_denied"),
                       ("could not connect", "connect_failed"), ("certificate verify failed", "tls_verify_failed"),
                       ("timeout", "timeout")):
        if key in text:
            return label
    return "other" if text.strip() else "none"


_DUMP_IN_ARG = re.compile(r"(?:--file=)?(.+[\\/](\d{8}T\d{6})[\\/]src\.dump)")


def child_kind(args) -> str:
    """Re-derive the ONLY allowed forms from the arguments themselves and require an exact match
    (pg_dump of the source as the backup role, pg_restore --list of an approved dump with no
    connection, pg_restore into the restore / failure-injection DB as the admin role). Anything
    changed, added, duplicated or re-targeted is refused here, right before Popen."""
    if not isinstance(args, list) or not args or not all(type(a) is str for a in args):
        raise g.Pg62Refused("pg64_child_args_refused")
    runs = {m.group(2) for a in args for m in [_DUMP_IN_ARG.fullmatch(a)] if m}
    if len(runs) != 1:
        raise g.Pg62Refused("pg64_child_args_refused")
    run_id = runs.pop()
    dump = dump_path(run_id)
    allowed = {"dump": dump_args(run_id), "list": list_args(dump),
               "restore_dst": restore_args(DST, dump), "restore_fail": restore_args(FAIL, dump)}
    for kind, form in allowed.items():
        if args == form:
            return kind
    raise g.Pg62Refused("pg64_child_args_refused")


def _end_child(child) -> bool:
    """Kill once (a failed kill is noted, not fatal) and reap within REAP_TIMEOUT. True only when the
    end is confirmed. No PID search, no other process is touched."""
    try:
        child.kill()
    except Exception:
        pass                                                    # still try to reap within the budget
    try:
        child.communicate(timeout=REAP_TIMEOUT)
    except Exception:
        return False
    return child.returncode is not None


def run_child(args: list[str], timeout: int, pid: int, popen=subprocess.Popen) -> tuple[int, str, str]:
    """Pre-check the target and the exact argument form, run one child (no shell), wait with a time
    limit. Returns (exit code, stderr classification, stdout). Start, communication and end failures
    become fixed reasons; an end that is not confirmed is never a normal completion. Interrupts are
    re-raised after the child is ended."""
    if g.pg_environment_present() or not g.server_is_ours(pid, T):
        raise g.Pg62Refused("pg64_child_precheck_refused")
    child_kind(args)
    try:
        child = popen(args, env=child_env(), shell=False, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                      stderr=subprocess.PIPE, text=True, creationflags=g.NO_WINDOW)
    except Exception:
        raise CheckFailed("harness_defect", "child start failed") from None
    try:
        out, err = child.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        ended = _end_child(child)
        raise CheckFailed("harness_defect", "child timed out; " +
                          ("ended after kill attempt" if ended else "end unconfirmed")) from None
    except BaseException as error:
        ended = _end_child(child)
        if not isinstance(error, Exception):
            raise                                              # KeyboardInterrupt / SystemExit, after cleanup
        raise CheckFailed("harness_defect", "child communication failed; " +
                          ("ended" if ended else "end unconfirmed")) from None
    if child.returncode is None:
        raise CheckFailed("harness_defect", "child exit not confirmed")
    return child.returncode, classify_child(err or ""), out or ""


# --- structured comparison (pure functions, fake-tested) -------------------------------------------------

def compare_snapshots(src: dict, dst: dict) -> list[str]:
    """Every difference, by section and key. Sections: rows (count, content hash), columns, constraints,
    indexes, owners, acls, sequences. Nothing is dropped or normalized; a key on one side only is a
    difference. Excluded by design (not collected): OIDs and the database name (DB-specific), the
    identity table's rows (deliberately not copied, checked by `identity_ok`)."""
    diffs = []
    for section in ("rows", "columns", "constraints", "indexes", "owners", "acls", "sequences"):
        a, b = src.get(section), dst.get(section)
        if a is None or b is None:
            diffs.append(f"{section}: missing")
            continue
        for key in sorted(set(a) | set(b), key=str):
            if a.get(key, "<absent>") != b.get(key, "<absent>"):
                diffs.append(f"{section}: {key}")
    return diffs


COLUMN_ATTRIBUTES = ("data_type", "udt_schema", "udt_name", "character_maximum_length", "numeric_precision",
                     "numeric_scale", "datetime_precision", "is_nullable", "column_default", "is_identity",
                     "identity_generation", "identity_start", "identity_increment", "is_generated",
                     "generation_expression")


def column_value(row: dict) -> tuple:
    """Every compared column attribute, by name (actual type by schema-qualified udt name, identity and
    generation, length, precision, scale, nullability, default). Values are kept as they are; a
    missing attribute is an error, not a blank."""
    return tuple((name, row[name]) for name in COLUMN_ATTRIBUTES)


def next_id_ok(sequences: dict, max_ids: dict) -> list[str]:
    """From the STORED sequence state only (no nextval / setval): the next value a sequence hands out
    must exceed every existing id of its table."""
    problems = []
    for table, max_id in max_ids.items():
        state = sequences.get(f"{table}_id_seq")
        if state is None:
            problems.append(f"{table}: sequence missing")
            continue
        last, called, step = state["last_value"], state["is_called"], state["increment"]
        following = last + step if called else last
        if max_id is not None and following <= max_id:
            problems.append(f"{table}: next {following} <= max {max_id}")
    return problems


def identity_ok(src_rows: list, dst_before: list, dst_after: list, nonce: str) -> list[str]:
    problems = []
    if len(src_rows) != 1:
        problems.append("source identity rows != 1")
    if dst_before != []:
        problems.append("identity data was copied into the restore")
    if dst_after != [nonce] or nonce in src_rows:
        problems.append("restore identity is not its own new value")
    return problems


def b8_expected_failure(code: int, label: str, before: dict, after: dict) -> list[str]:
    """Only the planned conflict counts: pg_restore failed, on 'already exists', and the failure DB is
    exactly as before the restore: same schemas, same relations, and the pre-made users table with
    the same definition, content, owner and privileges (the single transaction rolled back)."""
    problems = []
    if code == 0:
        problems.append("restore into the conflicting DB succeeded")
    if label != "relation_already_exists":
        problems.append(f"restore failed for another reason ({label})")
    if before.get("relations") != ["public.users"]:
        problems.append("failure injection not as planned")
    if (before.get("schemas"), before.get("relations")) != (after.get("schemas"), after.get("relations")) \
            or compare_snapshots(before.get("snapshot", {}), after.get("snapshot", {})):
        problems.append("rollback not confirmed")
    return problems


# --- collectors (admin connection, read only; real PG only) ----------------------------------------------

SNAP_SQL = {
    "tables": "SELECT n.nspname || '.' || c.relname AS name FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n "
              "ON n.oid = c.relnamespace WHERE c.relkind IN ('r','p') AND n.nspname IN ('public', %s) ORDER BY 1",
    "columns": "SELECT c.table_schema || '.' || c.table_name || '.' || c.column_name AS k, c.data_type, c.udt_schema, "
               "c.udt_name, c.character_maximum_length, c.numeric_precision, c.numeric_scale, c.datetime_precision, "
               "c.is_nullable, c.column_default, c.is_identity, c.identity_generation, c.identity_start, "
               "c.identity_increment, c.is_generated, c.generation_expression "
               "FROM information_schema.columns c WHERE c.table_schema IN ('public', %s)",
    "constraints": "SELECT n.nspname || '.' || r.relname || '.' || con.conname AS k, "
                   "con.contype::text || '|' || pg_catalog.pg_get_constraintdef(con.oid) AS v FROM pg_catalog.pg_constraint con "
                   "JOIN pg_catalog.pg_class r ON r.oid = con.conrelid JOIN pg_catalog.pg_namespace n ON n.oid = r.relnamespace "
                   "WHERE n.nspname IN ('public', %s)",
    "indexes": "SELECT schemaname || '.' || indexname AS k, indexdef AS v FROM pg_catalog.pg_indexes "
               "WHERE schemaname IN ('public', %s)",
    "owners": "SELECT n.nspname || '.' || c.relname AS k, pg_catalog.pg_get_userbyid(c.relowner) AS v "
              "FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace "
              "WHERE n.nspname IN ('public', %s) AND c.relkind IN ('r','p','S','v','m')",
    "acls": "SELECT n.nspname || '.' || c.relname AS k, coalesce(c.relacl::text, '') AS v FROM pg_catalog.pg_class c "
            "JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname IN ('public', %s) "
            "AND c.relkind IN ('r','p','S','v','m')",
    "sequences": "SELECT n.nspname || '.' || c.relname AS k FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n "
                 "ON n.oid = c.relnamespace WHERE c.relkind = 'S' AND n.nspname IN ('public', %s)",
}


def snapshot(conn, with_ids: bool = True) -> tuple[dict, dict]:
    """Structured snapshot of one DB through the admin connection (reads only; sequences are read as
    relations, never through nextval / setval). Returns (snapshot, max id per identity table)."""
    snap: dict = {}
    tables = [r[0] for r in conn.execute(SNAP_SQL["tables"], (SYN,)).fetchall()]
    snap["rows"] = {}
    for name in tables:
        if name == f"{SYN}.db_identity":
            continue                                               # its rows are compared by identity_ok
        schema, table = name.split(".", 1)
        ident = sql.SQL("{}.{}").format(sql.Identifier(schema), sql.Identifier(table))
        count, digest = conn.execute(sql.SQL(
            "SELECT count(*), pg_catalog.md5(coalesce(string_agg(t::text, E'\\n' ORDER BY t::text), '')) FROM {} AS t"
        ).format(ident)).fetchone()                               # duplicates and NULLs stay in the text
        snap["rows"][name] = (count, digest)
    with conn.cursor(row_factory=dict_row) as cursor:
        cursor.execute(SNAP_SQL["columns"], (SYN,))
        snap["columns"] = {row["k"]: column_value(row) for row in cursor.fetchall()}
    for section in ("constraints", "indexes", "owners", "acls"):
        snap[section] = {k: v for k, v in conn.execute(SNAP_SQL[section], (SYN,)).fetchall()}
    snap["sequences"], max_ids = {}, {}
    for (name,) in conn.execute(SNAP_SQL["sequences"], (SYN,)).fetchall():
        schema, seq = name.split(".", 1)
        last, called = conn.execute(sql.SQL("SELECT last_value, is_called FROM {}.{}").format(
            sql.Identifier(schema), sql.Identifier(seq))).fetchone()
        step = conn.execute("SELECT seqincrement FROM pg_catalog.pg_sequence WHERE seqrelid = %s::regclass",
                            (name,)).fetchone()[0]
        snap["sequences"][seq] = {"last_value": last, "is_called": called, "increment": step}
    for table in (real.CORE_TABLES + real.SRS_TABLES) if with_ids else ():
        if table not in real.SRS_WITHOUT_IDENTITY:
            max_ids[table] = conn.execute(sql.SQL("SELECT max(id) FROM public.{}").format(sql.Identifier(table))).fetchone()[0]
    return snap, max_ids


def user_relations(conn) -> list[str]:
    return [r[0] for r in conn.execute(
        "SELECT n.nspname || '.' || c.relname FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n "
        "ON n.oid = c.relnamespace WHERE c.relkind IN ('r','p','v','m','S','f') AND n.nspname NOT IN "
        "('pg_catalog', 'information_schema') AND n.nspname NOT LIKE 'pg\\_%' ORDER BY 1").fetchall()]


def user_schemas(conn) -> list[str]:
    return [r[0] for r in conn.execute(
        "SELECT nspname FROM pg_catalog.pg_namespace WHERE nspname <> 'information_schema' "
        "AND nspname NOT LIKE 'pg\\_%' ORDER BY 1").fetchall()]


def failure_db_state(conn) -> dict:
    snap, _ = snapshot(conn, with_ids=False)
    return {"schemas": user_schemas(conn), "relations": user_relations(conn), "snapshot": snap}


def read_identity_rows(conn) -> list:
    """Strict: a failed read raises (used by the baseline gate)."""
    return [r[0] for r in conn.execute(f"SELECT identity_value FROM {SYN}.db_identity ORDER BY 1").fetchall()]


def identity_rows(conn) -> list:
    try:
        return read_identity_rows(conn)
    except Exception:
        return ["<unreadable>"]                                    # never an empty (= "not copied") answer


# --- prepare (B2; not run without approval) -----------------------------------------------------------

def admin(db: str, pid: int, autocommit: bool = True):
    return g.admin_connect(db, record_pid=pid, autocommit=autocommit, target=T)


def hba() -> str:
    lines = []
    for addr in ("127.0.0.1/32", "::1/128"):
        lines += [f"hostssl postgres,{SRC},{DST},{FAIL} {ADMIN} {addr} sspi map=pg64 include_realm=1 compat_realm=1",
                  f"hostssl {SRC} {BACKUP} {addr} sspi map=pg64 include_realm=1 compat_realm=1",
                  f"hostssl {SRC},{DST} {AUDIT} {addr} scram-sha-256"]
    lines += ["hostnossl all all 127.0.0.1/32 reject", "hostnossl all all ::1/128 reject",
              "host all all 0.0.0.0/0 reject", "host all all ::0/0 reject"]
    return "\n".join(lines) + "\n"


def conf() -> str:
    with mock.patch.object(real, "T", T):                          # the same settings, this preset's port / TLS
        return real.conf()


SEED_ADVANCE = [  # moves the vocab_items sequence past max(id): insert then delete one card
    "INSERT INTO vocab_items (user_id, deck_id, surface, base_form, reading, part_of_speech, normalized_form, status, "
    "created_at, updated_at) SELECT u.id, d.id, '鳥', '鳥', 'とり', 'noun', '鳥', 'learning', "
    "'2026-10-01T00:00:00+00:00', '2026-10-01T00:00:00+00:00' FROM users u JOIN decks d ON d.user_id = u.id "
    "WHERE u.email = 'dev@example.local'",
    "DELETE FROM vocab_items WHERE base_form = '鳥'",
]


def build_source(pid: int, rec: g.Record) -> None:
    """`app.database.ensure_schema` as the owner role on the admin connection (app paths made to fail)."""
    ar.fix_app_environment()
    from app import database

    def forbidden(*_, **__):
        raise AssertionError("app connection path used during preparation")

    with mock.patch.object(database, "get_connection", forbidden), mock.patch.object(database, "init_db", forbidden), \
            mock.patch.object(database, "initialize_database", forbidden), admin(SRC, pid, autocommit=False) as raw:
        raw.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(OWNER)))
        raw.row_factory = dict_row
        database.ensure_schema(database.AppPostgresConnection(raw))
        for statement in real.SEED_OK + SEED_ADVANCE:
            raw.execute(statement)
        raw.execute("RESET ROLE")
        raw.commit()
    rec.event("app_schema_created", database=SRC, via="app.database.ensure_schema", role=OWNER,
              seed_statements=len(real.SEED_OK) + len(SEED_ADVANCE))


def grant_source(pid: int, rec: g.Record) -> None:
    with admin(SRC, pid) as conn:
        for schema in ("public", SYN):
            conn.execute(sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(sql.Identifier(schema), sql.Identifier(BACKUP)))
            conn.execute(sql.SQL("GRANT SELECT ON ALL TABLES IN SCHEMA {} TO {}").format(sql.Identifier(schema),
                                                                                       sql.Identifier(BACKUP)))
            conn.execute(sql.SQL("GRANT SELECT ON ALL SEQUENCES IN SCHEMA {} TO {}").format(sql.Identifier(schema),
                                                                                          sql.Identifier(BACKUP)))
        conn.execute(sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(sql.Identifier(SYN), sql.Identifier(AUDIT)))
        conn.execute(sql.SQL("GRANT SELECT ON {}.db_identity TO {}").format(sql.Identifier(SYN), sql.Identifier(AUDIT)))
        for table in real.AUDIT_TABLES:
            conn.execute(sql.SQL("GRANT SELECT ON public.{} TO {}").format(sql.Identifier(table), sql.Identifier(AUDIT)))
        conn.execute(sql.SQL("GRANT SELECT ON SEQUENCE public.{} TO {}").format(sql.Identifier(real.AUDIT_SEQUENCE),
                                                                            sql.Identifier(AUDIT)))
    rec.event("grants", database=SRC, backup="SELECT on all tables and sequences, schema USAGE",
              audit_tables=list(real.AUDIT_TABLES))


def prepare() -> None:
    if g.pg_environment_present():
        raise CheckFailed("preparation_failure", "PG environment variables present")
    if T.root.exists():
        raise CheckFailed("preparation_failure", "pg64 root already exists")
    if g.listener_pids(T.port):
        raise CheckFailed("preparation_failure", "port 55482 in use")
    run_id = time.strftime("%Y%m%dT%H%M%S")
    for folder in (T.root, T.tls, T.runs, DUMPS, T.runs / run_id):
        folder.mkdir()
    base.run(["icacls", str(DUMPS), "/inheritance:r", "/grant:r", f"{os.environ['USERNAME']}:(OI)(CI)F"])
    rec = g.Record(T.runs / run_id)
    rec.event("folders_created", paths=[str(T.root), str(T.tls), str(T.runs), str(DUMPS), str(rec.folder)])
    secret = Path(os.environ["LOCALAPPDATA"]) / "Temp" / f"jpv_pg64_{run_id}"
    secret.mkdir()
    rec.event("secret_folder_created", path=str(secret))
    with mock.patch.object(real, "T", T):                          # same TLS steps, this preset's folder
        real.make_tls(rec, secret)
    base.run([str(g.BIN / "initdb.exe"), "-D", str(T.data), "-U", ADMIN, "-A", "reject", "-E", "UTF8",
              "--locale=C", "--no-instructions"])
    rec.event("initdb", data=str(T.data), bootstrap_role=ADMIN)
    principal = f"{os.environ['USERNAME']}@{os.environ['COMPUTERNAME']}"
    with open(T.data / "postgresql.conf", "a", encoding="utf-8", newline="\n") as handle:
        handle.write(conf())
    (T.data / "pg_hba.conf").write_text(hba(), encoding="utf-8", newline="\n")
    (T.data / "pg_ident.conf").write_text(f"pg64 {principal} {ADMIN}\npg64 {principal} {BACKUP}\n",
                                          encoding="utf-8", newline="\n")
    rec.event("config_written", files=["postgresql.conf (appended)", "pg_hba.conf", "pg_ident.conf"])
    with mock.patch.object(real, "T", T):
        pid = real.start_server(rec)
    nonce = secrets.token_hex(8)
    with admin("postgres", pid) as conn:
        version = conn.execute("SELECT pg_catalog.current_setting('server_version_num')").fetchone()[0]
        for role, login in ((OWNER, False), (BACKUP, True), (AUDIT, True)):
            stmt = sql.SQL("CREATE ROLE {} {} NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS").format(
                sql.Identifier(role), sql.SQL("LOGIN" if login else "NOLOGIN"))
            if role == AUDIT:
                stmt = sql.SQL("{} PASSWORD {}").format(stmt, sql.Literal(g.scram_verifier(g.new_password())))
            conn.execute(stmt)
            rec.event("role_created", name=role, oid=conn.execute(
                "SELECT oid FROM pg_catalog.pg_roles WHERE rolname = %s", (role,)).fetchone()[0])
        for db in (SRC, DST, FAIL):
            conn.execute(sql.SQL("CREATE DATABASE {} OWNER {} TEMPLATE template0 ENCODING 'UTF8' LOCALE 'C'").format(
                sql.Identifier(db), sql.Identifier(OWNER)))
            rec.event("database_created", name=db, oid=conn.execute(
                "SELECT oid FROM pg_catalog.pg_database WHERE datname = %s", (db,)).fetchone()[0])
            conn.execute(sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(sql.Identifier(db)))
        conn.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}, {}").format(sql.Identifier(SRC), sql.Identifier(BACKUP),
                                                                             sql.Identifier(AUDIT)))
        conn.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(sql.Identifier(DST), sql.Identifier(AUDIT)))
    with admin(SRC, pid) as conn:
        conn.execute(sql.SQL("CREATE SCHEMA {} AUTHORIZATION {}").format(sql.Identifier(SYN), sql.Identifier(OWNER)))
        conn.execute(sql.SQL("CREATE TABLE {}.db_identity (identity_value text NOT NULL)").format(sql.Identifier(SYN)))
        conn.execute(sql.SQL("ALTER TABLE {}.db_identity OWNER TO {}").format(sql.Identifier(SYN), sql.Identifier(OWNER)))
        conn.execute(sql.SQL("INSERT INTO {}.db_identity (identity_value) VALUES (%s)").format(sql.Identifier(SYN)),
                     (f"pg64-src-{nonce}",))
    build_source(pid, rec)
    grant_source(pid, rec)
    databases = {}
    with admin("postgres", pid) as conn:
        for db in (SRC, DST, FAIL):
            databases[db] = {"oid": conn.execute("SELECT oid FROM pg_catalog.pg_database WHERE datname = %s",
                                                 (db,)).fetchone()[0], "identity_value": None}
    databases[SRC]["identity_value"] = f"pg64-src-{nonce}"
    databases[DST]["identity_value"] = f"pg64-dst-{nonce}"         # inserted by check b6 after the restore
    target = {"run_id": rec.folder.name, "host": g.HOST, "port": T.port, "data": str(T.data),
              "postgres_exe": str(g.POSTGRES_EXE), "postmaster_pid": pid, "server_version_num": version,
              "databases": {db: v for db, v in databases.items() if db != FAIL},
              "provider_roles": list(T.provider_roles), "admin_role": ADMIN, "ca_sha256": base.sha(T.tls / "ca.crt")}
    data = json.dumps(target, indent=1, sort_keys=True).encode()
    (rec.folder / "target.json").write_bytes(data)
    rec.event("target_written", sha256=hashlib.sha256(data).hexdigest(), server_version_num=version)


# --- check (B3; not run without approval) ------------------------------------------------------------

class State:
    """What earlier checks established, used by later ones (each check stops the run on failure)."""

    def __init__(self, rec: g.Record):
        self.rec = rec
        self.target = json.loads((rec.folder / "target.json").read_bytes())
        self.pid = self.target["postmaster_pid"]
        self.dump: Path | None = None
        self.src_snap: dict | None = None
        self.src_max: dict | None = None
        self.pending: dict | None = None                           # gate collection, not yet recorded
        self.baseline: dict | None = None                          # gate collection, recorded
        self.password = ""
        self.keys = None

    def close(self) -> None:
        if self.keys is not None:
            self.keys.close()
        self.password = ""


# Baseline gate (plan 9-1): before ANY pg_dump / pg_restore child, every baseline collector this run uses
# is run to the end on the real DBs and its result recorded. Normal state right after B2 prepare:
#   source  : schemas exactly public + SYN; relations include SYN.db_identity and every app table;
#             db_identity holds exactly the recorded source identity value.
#   dst/fail: created from template0 and untouched: schemas exactly public, no relations, every snapshot
#             section empty. db_identity does not exist there yet; that is normal, so it is not read.
# A collector that raises is a harness defect (recorded by run_check as an error); a collected state
# outside this contract is a preparation failure. Either way nothing after the gate runs. The gate's
# pass counts only once recorded, and never as one of b1..b8.
GATE = "baseline_gate"
EMPTY_SNAPSHOT_SECTIONS = ("rows", "columns", "constraints", "indexes", "owners", "acls", "sequences")


def baseline_gate(s: State) -> dict:
    collected: dict = {}
    with admin(SRC, s.pid) as conn:
        snap, max_ids = snapshot(conn)
        collected[SRC] = {"snapshot": snap, "max_ids": max_ids, "identity": read_identity_rows(conn),
                          "relations": user_relations(conn), "schemas": user_schemas(conn)}
    for db in (DST, FAIL):
        with admin(db, s.pid) as conn:
            collected[db] = failure_db_state(conn)
    src = collected[SRC]
    expect(src["schemas"] == sorted(["public", SYN]), "source schemas not as prepared", "preparation_failure")
    expect({f"{SYN}.db_identity"} | {f"public.{t}" for t in real.CORE_TABLES + real.SRS_TABLES}
           <= set(src["relations"]), "source relations not as prepared", "preparation_failure")
    expect(src["identity"] == [s.target["databases"][SRC]["identity_value"]], "source identity not as prepared",
           "preparation_failure")
    for db in (DST, FAIL):
        state = collected[db]
        expect(state["schemas"] == ["public"] and state["relations"] == []
               and all(state["snapshot"][k] == {} for k in EMPTY_SNAPSHOT_SECTIONS),
               f"{db} not empty as prepared", "preparation_failure")
    s.pending = collected
    return {"databases": collected}                                # recorded by run_check before acceptance


def b1_dump(s: State) -> dict:
    expect(s.baseline is not None, "baseline gate not passed", "harness_defect")
    s.src_snap, s.src_max = s.baseline[SRC]["snapshot"], s.baseline[SRC]["max_ids"]   # reused, not re-read
    run_id = s.rec.folder.name
    dump = dump_path(run_id)
    dump.parent.mkdir()
    code, label, _ = run_child(dump_args(run_id), DUMP_TIMEOUT, s.pid)
    expect(code == 0 and dump.is_file() and dump.stat().st_size > 0, f"pg_dump failed ({label})")
    code, label, toc = run_child(list_args(dump), DUMP_TIMEOUT, s.pid)
    expect(code == 0, f"pg_restore --list failed ({label})")
    listed = set(re.findall(r"TABLE DATA public (\w+) ", toc))
    expect(set(real.AUDIT_TABLES) <= listed, "dump table of contents misses audited tables")
    expect(f"TABLE {SYN} db_identity" in toc and f"TABLE DATA {SYN} db_identity" not in toc,
           "identity definition kept, data excluded")
    digest = base.sha(dump)
    s.rec.event("dump_written", path=str(dump), size=dump.stat().st_size, sha256=digest)
    s.dump = dump
    with admin(SRC, s.pid) as conn:
        after, _ = snapshot(conn)
    expect(compare_snapshots(s.src_snap, after) == [], "source changed during the dump")
    return {"size": dump.stat().st_size, "sha256": digest[:16]}


def b2_restore(s: State) -> dict:
    with admin(DST, s.pid) as conn:
        expect(user_relations(conn) == [], "restore target is not empty", "preparation_failure")
    code, label, _ = run_child(restore_args(DST, s.dump), RESTORE_TIMEOUT, s.pid)
    expect(code == 0, f"pg_restore failed ({label})")
    return {"restored": True}


def b3_b5_compare(s: State) -> dict:
    with admin(DST, s.pid) as conn:
        dst_snap, dst_max = snapshot(conn)
    diffs = compare_snapshots(s.src_snap, dst_snap)
    expect(diffs == [], f"source / restore differ: {diffs[:5]}")
    problems = next_id_ok(dst_snap["sequences"], dst_max) + next_id_ok(s.src_snap["sequences"], s.src_max)
    expect(problems == [], f"sequence next id: {problems[:3]}")
    return {"tables": len(dst_snap["rows"]), "sequences": len(dst_snap["sequences"])}


def b6_identity(s: State) -> dict:
    nonce = s.target["databases"][DST]["identity_value"]
    with admin(SRC, s.pid) as conn:
        src_rows = identity_rows(conn)
    with admin(DST, s.pid) as conn:
        before = identity_rows(conn)
        conn.execute(sql.SQL("INSERT INTO {}.db_identity (identity_value) VALUES (%s)").format(sql.Identifier(SYN)),
                     (nonce,))
        after = identity_rows(conn)
    s.rec.event("restore_identity_inserted", database=DST)
    problems = identity_ok(src_rows, before, after, nonce)
    expect(problems == [], f"identity: {problems}")
    return {"distinct": True}


class AuditRun:
    """The provider-path audit on this preset (same pieces as _ops_audit_real, other target)."""

    def __init__(self, s: State):
        self.s = s
        if s.keys is None:
            s.keys = sigtests.Keys()
        self.allowed = s.keys.allowed(namespaces="jp-vocab-ops/v1/synthetic/*")
        self.trackers: list = []
        self.deploys: list[str] = []

    def close(self):
        for folder in self.deploys:
            shutil.rmtree(folder, ignore_errors=True)

    def inputs(self, db: str) -> op.PreflightInput:
        folder = os.path.normpath(tempfile.mkdtemp(prefix="ops_pg64_deploy_"))
        self.deploys.append(folder)
        target_bytes = (self.s.rec.folder / "target.json").read_bytes()
        files = {k: v for k, v in pf.FILES.items() if k != "ops/tls/root.pem"}
        files["ops/tls/root.pem"] = (T.tls / "ca.crt").read_bytes()
        files[T.target_doc] = target_bytes
        for rel, data in files.items():
            path = os.path.join(folder, *rel.split("/"))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as handle:
                handle.write(data)
        manifest = pf.manifest_doc(files)
        target = op.TargetObservation(host=g.HOST, port=T.port, database=db, server_major=18,
                                      identity_value=self.s.target["databases"][db]["identity_value"])
        db_identity = pf.db_identity(target)
        profile = pv.expected_profile_fingerprint(real.expected_profile(db), role=AUDIT, access="read")
        scope = {"audit_scope": "database_all", "audit_db_identity": db_identity}
        doc = {"format_version": 1, "kind": "inquiry", "approval_id": "inq-0000000000000064", "supersedes": None,
               "purpose": "synthetic", "alias": "synthetic-primary", "db_identity": db_identity,
               "manifest": pf.om.manifest_fingerprint(manifest), "tool": "srs_invariant_audit",
               "steps": [{"command": "audit", "access": "read", "role": AUDIT, "profile": profile}],
               "accounts": [7], "max_accounts": 1, "job": {"key": "backup-audit-1", "inputs": scope},
               "valid_from": "2026-10-21T12:00:00Z", "valid_until": "2026-10-21T13:00:00Z",
               "approved_by": "synthetic signer"}
        approval = json.dumps(doc).encode()
        sign = lambda data, subject: self.s.keys.sign("signer", oa.signature_namespace("synthetic", subject), data)  # noqa
        root = os.path.join(folder, "ops", "tls", "root.pem")
        dsn = (f"postgresql://{AUDIT}:{self.s.password}@{g.HOST}:{T.port}/{db}?sslmode=verify-full"
               f"&sslrootcert={quote(root, safe='')}")
        return op.PreflightInput(
            mode="synthetic", approval=approval, approval_signature=sign(approval, "approval"), manifest=manifest,
            manifest_signature=sign(manifest, "manifest"), deploy_root=folder, command="audit", args={}, account_id=7,
            job_key="backup-audit-1", job_inputs=scope, product_fingerprint=pf.PRODUCT, target=target,
            connection=op.ConnectionObservation(profile=profile, read_only=True), secret_dsn=dsn,
            environment={"PATH": "C:/Windows"}, trust=op.SyntheticTrust(self.allowed, b"", sigtests.PRINCIPAL),
            now=sigtests.T0)

    def run(self, db: str):
        inputs = self.inputs(db)
        guard = g.Guard(inputs.manifest, inputs.deploy_root, self.s.rec.folder, target=T)
        first = len(self.trackers)

        def connect(**kwargs):
            conn = guard.driver(**kwargs)
            tracked = real.CommitTracker(conn)
            self.trackers.append(tracked)
            return tracked
        out, code = ar.run_synthetic_audit(inputs, expected=real.expected_profile(db), driver=connect)
        probe: dict = {}
        for tracker in self.trackers[first:]:
            probe.update(tracker.probe)
        probe["calls"] = sum(t.probe.get("calls", 0) for t in self.trackers[first:])
        probe["commits"] = sum(t.commits for t in self.trackers[first:])
        return out, code, probe


def b7_audits(s: State) -> dict:
    password = g.new_password()
    with admin("postgres", s.pid) as conn:
        conn.execute(sql.SQL("ALTER ROLE {} PASSWORD {}").format(sql.Identifier(AUDIT),
                                                                sql.Literal(g.scram_verifier(password))))
    s.password = password
    runner = AuditRun(s)
    try:
        src, src_code, src_probe = runner.run(SRC)
        dst, dst_code, dst_probe = runner.run(DST)
    finally:
        runner.close()
    for probe in (src_probe, dst_probe):
        real.require_probe(probe)
        expect(probe.get("commits") == 0 and probe.get("xid") is None and probe.get("calls") == 1,
               "audit: commit 0, no xid, one audit")
    expect(src["status"] == "partial" and src_code == 3, f"source audit {src.get('status')}/{src_code}")
    expect((real.audit_result(src), src_code) == (real.audit_result(dst), dst_code), "source and restore audits differ")
    return {"status": src["status"], "exit": src_code}


def b8_restore_failure(s: State) -> dict:
    with admin(FAIL, s.pid) as conn:
        conn.execute(sql.SQL("CREATE TABLE public.users (conflict integer)"))
        conn.execute("INSERT INTO public.users (conflict) VALUES (1)")
        before = failure_db_state(conn)                       # structure and content baseline
        s.rec.event("failure_injection_prepared", database=FAIL, conflicting="public.users")
    code, label, _ = run_child(restore_args(FAIL, s.dump), RESTORE_TIMEOUT, s.pid)
    with admin(FAIL, s.pid) as conn:
        after = failure_db_state(conn)
    with admin(SRC, s.pid) as conn:
        src_after, _ = snapshot(conn)
    problems = b8_expected_failure(code, label, before, after)
    expect(problems == [], f"b8: {problems}")
    expect(compare_snapshots(s.src_snap, src_after) == [], "source changed during the failed restore")
    return {"exit": code, "label": label, "relations_after": after["relations"]}


PLANNED = ("b1_dump", "b2_restore", "b3_b5_compare", "b6_identity", "b7_audits", "b8_restore_failure")
CHECKS = [("b1_dump", b1_dump), ("b2_restore", b2_restore), ("b3_b5_compare", b3_b5_compare),
          ("b6_identity", b6_identity), ("b7_audits", b7_audits), ("b8_restore_failure", b8_restore_failure)]


def check() -> int:
    if g.pg_environment_present():
        raise CheckFailed("preparation_failure", "PG environment variables present")
    rec = g.single_run(T)
    s = State(rec)
    if not g.server_is_ours(s.pid, T):
        raise CheckFailed("preparation_failure", "server not ours")
    passed = 0
    try:
        rec.event("check_phase_started", gate=GATE, checks=[n for n, _ in CHECKS])
        if not base.run_check(rec, GATE, baseline_gate, s):
            return 0                                           # no child, no check after a gate failure
        s.baseline, s.pending = s.pending, None                # accepted only after its pass was recorded
        for name, fn in CHECKS:
            if not base.run_check(rec, name, fn, s):
                return passed                                  # nothing after a failure runs
            passed += 1
    finally:
        s.close()
    return passed


# --- cleanup (B4; not run without approval) ----------------------------------------------------------------

def cleanup() -> None:
    rec = g.single_run(T)
    started = rec.find("server_started")
    expect(len(started) == 1, "exactly one server start recorded", "harness_defect")
    pid = started[0]["pid"]
    for e in rec.find("dump_written"):
        path = Path(e["path"])
        expect(path.parent.parent == DUMPS and (not path.exists() or base.sha(path) == e["sha256"]),
               "dump file matches the record", "harness_defect")
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
    expect(rec.find("folders_created")[0]["paths"][0] == str(T.root)
           and set(os.listdir(T.root)) <= {"data", "tls", "runs", "dumps"}, "pg64 contents as recorded", "harness_defect")
    shutil.rmtree(T.root)
    expect(not T.root.exists(), "pg64 removed (dumps included)", "harness_defect")


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

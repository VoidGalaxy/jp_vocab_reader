"""6-2 real local PostgreSQL run (OPS_REAL_PG_6_2_PLAN.md): the target guard, the guarded real
driver, the guarded observer and the admin helpers. Test-only module; not part of discovery.

Only this module calls the real driver (`psycopg.connect`), and only through `Guard.driver`
(provider path) and `admin_connect` / `raw_connect_probe` (harness-only). The target is fixed in
code: host `localhost`, port 55462, the two 6-2 databases, the cluster under C:/JV_Tools/pg62
that this run created. Every connection is checked before (signed target record, postmaster PID,
executable path, listener PID, no PG environment variables) and after (loopback address, port,
version, database OID, identity row). Nothing here takes a target from arguments or the environment.
Passwords live only in memory; nothing secret is written or printed.
"""

from __future__ import annotations

import base64
import ctypes
import hashlib
import hmac
import json
import os
import secrets
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

import _ops_manifest as om
import _ops_observer as ob
import _ops_provider as pv

BIN = Path("C:/JV_Tools/pgsql-18.6/pgsql/bin")
POSTGRES_EXE = BIN / "postgres.exe"
ROOT = Path("C:/JV_Tools/pg62")
DATA, TLS, RUNS = ROOT / "data", ROOT / "tls", ROOT / "runs"
OPENSSL = Path("C:/Program Files/Git/usr/bin/openssl.exe")
HOST, PORT = "localhost", 55462
DB_A, DB_B = "jp_vocab_test_62a", "jp_vocab_test_62b"
ADMIN, OWNER, READ, WRITE = "jpv62_admin", "jpv62_owner", "jpv62_read", "jpv62_write"
OWNER_LOGIN, EXTRA = "jpv62_owner_login", "jpv62_extra"
PROVIDER_ROLES = (READ, WRITE, OWNER_LOGIN)        # the admin role is never a provider role
TARGET_DOC = "docs/plans/srs-improvement/gate-e/PG62_TARGET.md"   # manifest entry binding target.json
LOOPBACK = frozenset({"127.0.0.1", "::1"})
TARGET_ENV = ("PGHOST", "PGHOSTADDR", "PGPORT", "PGDATABASE", "PGUSER", "PGSERVICE", "PGSERVICEFILE",
              "PGSYSCONFDIR", "PGPASSWORD", "PGPASSFILE", "PGSSLMODE", "PGSSLROOTCERT", "PGOPTIONS")
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class Pg62Refused(pv.OpsProviderRefused):
    """Fixed codes only; raised by the guard before or right after a real connection."""


@dataclass(frozen=True)
class Target:
    """One approved real-PG test target. Only the instances in PRESETS are accepted (identity check):
    an equal object built elsewhere, a CLI argument or an environment value cannot add a target."""
    name: str
    root: Path
    port: int
    databases: tuple[str, ...]
    admin: str
    provider_roles: tuple[str, ...]          # never contains the admin role
    target_doc: str

    @property
    def data(self) -> Path:
        return self.root / "data"

    @property
    def tls(self) -> Path:
        return self.root / "tls"

    @property
    def runs(self) -> Path:
        return self.root / "runs"


# 6-2 (OPS_REAL_PG_6_2_PLAN.md): the default everywhere in this module, unchanged.
PG62 = Target("pg62", ROOT, PORT, (DB_A, DB_B), ADMIN, PROVIDER_ROLES, TARGET_DOC)
# Real-PG audit check (OPS_AUDIT_REAL_PG_PLAN.md 1절): the fixed values of that approval request.
PG63_AUDIT = Target("pg63_audit", Path("C:/JV_Tools/pg63"), 55472,
                    ("jp_vocab_test_audit_ok", "jp_vocab_test_audit_bad"), "jpva_admin", ("jpva_audit",),
                    "docs/plans/srs-improvement/gate-e/PG63_TARGET.md")
# Backup / restore rehearsal (OPS_BACKUP_RESTORE_REHEARSAL_PLAN.md 1절): source, restore target, failure-injection DB.
PG64_BACKUP = Target("pg64_backup", Path("C:/JV_Tools/pg64"), 55482,
                     ("jp_vocab_test_br_src", "jp_vocab_test_br_dst", "jp_vocab_test_br_fail"), "jpvb_admin",
                     ("jpvb_audit",), "docs/plans/srs-improvement/gate-e/PG64_TARGET.md")
# C12 first-apply real-PG check (OPS_APPLY_REAL_PG_PLAN.md 2절): the template (owner / admin only, never a
# business connection) and one database per check, all cloned from it. Business roles: read and write only.
PG65_APPLY_CHECK_IDS = ("a1", "a2", "a3", "b2", "b3", "c1", "c1p", "d1", "d2", "e1", "e2", "e3", "f1", "f2", "f3",
                        "f4", "g1", "g2", "g3", "g4")
PG65_APPLY = Target("pg65_apply", Path("C:/JV_Tools/pg65"), 55492,
                    ("jp_vocab_test_apply_tpl",) + tuple(f"jp_vocab_test_apply_{c}" for c in PG65_APPLY_CHECK_IDS),
                    "jpvm_admin", ("jpvm_read", "jpvm_write"), "docs/plans/srs-improvement/gate-e/PG65_TARGET.md")
# RS4 `resume` real-PG check (OPS_MIGRATION_RESUME_REAL_PG_PLAN.md 3절, 5-3): the template and one database per
# check, all cloned from it; business roles read and write only. Separate from pg65 in every name.
PG66_RESUME_CHECK_IDS = ("r1", "r2", "r4a", "r4b", "r4c", "r5", "r6", "r6b", "r7a", "r7b", "r7c", "r7d", "r7e", "r8",
                         "r9a", "r9b", "r9c", "c1", "c2", "c2s", "c3", "c3r", "c3c")
PG66_RESUME = Target("pg66_resume", Path("C:/JV_Tools/pg66"), 55502,
                     ("jp_vocab_test_resume_tpl",) + tuple(f"jp_vocab_test_resume_{c}" for c in PG66_RESUME_CHECK_IDS),
                     "jpvr_admin", ("jpvr_read", "jpvr_write"), "docs/plans/srs-improvement/gate-e/PG66_TARGET.md")
# Subscribed-card `resume` real-PG check (OPS_MIGRATION_RESUME_LEXEME_PLAN 4절 / 7-1, values only; nothing is
# created by registering them). Separate from pg65 / pg66 in every name.
PG67_RESUME_LEXEME_CHECK_IDS = ("l1", "l2", "l3", "l6", "l7", "l8", "l9")
PG67_RESUME_LEXEME = Target("pg67_resume_lexeme", Path("C:/JV_Tools/pg67"), 55512,
                            ("jp_vocab_test_resume_lex_tpl",) + tuple(f"jp_vocab_test_resume_lex_{c}" for c in
                                                                      PG67_RESUME_LEXEME_CHECK_IDS),
                            "jpvl_admin", ("jpvl_read", "jpvl_write"),
                            "docs/plans/srs-improvement/gate-e/PG67_TARGET.md")
PRESETS = (PG62, PG63_AUDIT, PG64_BACKUP, PG65_APPLY, PG66_RESUME, PG67_RESUME_LEXEME)


def preset(target: Any) -> Target:
    if not any(target is p for p in PRESETS):
        raise Pg62Refused("pg62_target_preset_refused")
    return target


def _ours(pid: int, target: Target) -> bool:
    # 6-2 keeps its one-argument call (its fake tests replace server_is_ours with that shape)
    return server_is_ours(pid) if target is PG62 else server_is_ours(pid, target)


# --- process / listener facts (read only) ---------------------------------------------------------

def process_image(pid: int) -> str | None:
    """Full executable path of a process, or None."""
    kernel = ctypes.windll.kernel32
    handle = kernel.OpenProcess(0x1000, False, int(pid))          # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return None
    try:
        buffer = ctypes.create_unicode_buffer(32768)
        size = ctypes.c_ulong(len(buffer))
        if not kernel.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return None
        return buffer.value
    finally:
        kernel.CloseHandle(handle)


def listener_pids(port: int) -> set[int]:
    """PIDs listening on TCP `port` (IPv4 and IPv6), from `netstat -ano`."""
    pids: set[int] = set()
    for proto in ("tcp", "tcpv6"):
        out = subprocess.run(["netstat", "-ano", "-p", proto], capture_output=True, text=True,
                             creationflags=NO_WINDOW, timeout=30).stdout
        for line in out.splitlines():
            parts = line.split()
            if len(parts) >= 5 and parts[3] == "LISTENING" and parts[1].rsplit(":", 1)[-1] == str(port):
                pids.add(int(parts[4]))
    return pids


def postmaster_pid(target: Target = PG62) -> int | None:
    target = preset(target)
    try:
        lines = (target.data / "postmaster.pid").read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    if len(lines) < 4 or not lines[0].strip().isdigit():
        return None
    if os.path.normcase(os.path.normpath(lines[1].strip())) != os.path.normcase(os.path.normpath(str(target.data))) \
            or lines[3].strip() != str(target.port):
        return None
    return int(lines[0].strip())


def same_path(a: Any, b: Any) -> bool:
    return a is not None and b is not None and os.path.normcase(os.path.normpath(str(a))) == \
        os.path.normcase(os.path.normpath(str(b)))


def server_is_ours(pid: int, target: Target = PG62) -> bool:
    """postmaster.pid PID = `pid`, its executable is the 18.6 postgres.exe, and it owns the listener."""
    target = preset(target)
    return (postmaster_pid(target) == pid and same_path(process_image(pid), POSTGRES_EXE)
            and listener_pids(target.port) == {pid})


def pg_environment_present() -> bool:
    return any(name.upper().startswith("PG") for name in os.environ)


# --- run record (no secrets) ----------------------------------------------------------------------

class Record:
    """Append-only JSON evidence for one run, rewritten atomically after every event."""

    def __init__(self, folder: Path):
        self.folder = folder
        self.path = folder / "record.json"
        self.doc = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else \
            {"run_id": folder.name, "events": [], "results": []}

    def _save(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        text = json.dumps(self.doc, indent=1, sort_keys=True)       # fails before any file is touched
        with open(tmp, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, self.path)

    def _append(self, key: str, entry: dict) -> None:
        """All-or-nothing: an entry that cannot be saved is taken back, the file stays valid."""
        self.doc[key].append(entry)
        try:
            self._save()
        except BaseException:
            self.doc[key].pop()
            raise

    def event(self, kind: str, **facts: Any) -> None:
        self._append("events", {"kind": kind, **facts})

    def result(self, check: str, status: str, details: dict | None = None, **facts: Any) -> None:
        """`details` (a check's own values) are nested, so they can never collide with record keys."""
        entry = {"check": check, "status": status, **facts}
        if details is not None:
            entry["details"] = details
        self._append("results", entry)

    def find(self, kind: str) -> list[dict]:
        return [e for e in self.doc["events"] if e["kind"] == kind]


def single_run(target: Target = PG62) -> Record:
    target = preset(target)
    runs = [p for p in target.runs.iterdir() if p.is_dir()] if target.runs.is_dir() else []
    if len(runs) != 1:
        raise Pg62Refused("pg62_run_folder_ambiguous")
    return Record(runs[0])


# --- secrets in memory ----------------------------------------------------------------------------

def new_password() -> str:
    return secrets.token_urlsafe(32)


def scram_verifier(password: str) -> str:
    """SCRAM-SHA-256 verifier (RFC 7677 / PostgreSQL format); the plain password never leaves."""
    salt, rounds = secrets.token_bytes(16), 4096
    salted = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, rounds)
    client = hmac.new(salted, b"Client Key", "sha256").digest()
    server = hmac.new(salted, b"Server Key", "sha256").digest()
    b64 = lambda b: base64.b64encode(b).decode("ascii")  # noqa: E731
    return f"SCRAM-SHA-256${rounds}:{b64(salt)}${b64(hashlib.sha256(client).digest())}:{b64(server)}"


# --- admin connection (SSPI, harness only, never handed to the provider) ---------------------------

def admin_connect(dbname: str, *, record_pid: int, autocommit: bool = True,
                  target: Target = PG62) -> psycopg.Connection:
    target = preset(target)
    if dbname not in ("postgres",) + target.databases:
        raise Pg62Refused("pg62_admin_target_refused")
    if pg_environment_present():
        raise Pg62Refused("pg62_pg_environment_present")
    if not _ours(record_pid, target):
        raise Pg62Refused("pg62_server_not_ours")
    conn = psycopg.connect(host=HOST, port=str(target.port), dbname=dbname, user=target.admin, sslmode="verify-ca",
                           sslrootcert=str(target.tls / "ca.crt"), sslcertmode="disable", gssencmode="disable",
                           connect_timeout="10", application_name="jp_vocab_pg62_admin", autocommit=autocommit)
    try:
        if conn.info.hostaddr not in LOOPBACK:
            raise Pg62Refused("pg62_not_loopback")
        row = conn.execute("SELECT pg_catalog.host(pg_catalog.inet_server_addr()) AS a, "
                           "pg_catalog.inet_server_port() AS p").fetchone()
        if row is None or row[0] not in LOOPBACK or row[1] != target.port:
            raise Pg62Refused("pg62_not_loopback")
        if not autocommit:
            conn.rollback()
    except BaseException:
        conn.close()
        raise
    return conn


def raw_connect_probe(*, user: str, password: str, sslmode: str, record_pid: int, target: Target = PG62) -> str:
    """Harness-only direct attempt to OUR server (non-TLS refusal check). Returns a fixed
    classification; never the driver text."""
    target = preset(target)
    if pg_environment_present() or not _ours(record_pid, target) or user not in target.provider_roles:
        raise Pg62Refused("pg62_probe_refused")
    try:
        conn = psycopg.connect(host=HOST, port=str(target.port), dbname=target.databases[0], user=user, password=password,
                               sslmode=sslmode, gssencmode="disable", connect_timeout="10")
    except psycopg.OperationalError as error:
        return classify(error)
    conn.close()
    return "connected"


def classify(error: BaseException) -> str:
    """Keyword classification of a driver error for the evidence file (no raw text kept)."""
    text = str(error).lower()
    for key, label in (("certificate verify failed", "tls_certificate_verify_failed"),
                       ("does not match host name", "tls_host_name_mismatch"),
                       ("no encryption", "hba_reject_no_encryption"), ("rejects connection", "hba_reject"),
                       ("password authentication failed", "password_failed"),
                       ("connection refused", "connection_refused"), ("timeout", "timeout")):
        if key in text:
            return label
    return "other:" + type(error).__name__


# --- the guard ------------------------------------------------------------------------------------

class Guard:
    """Binds one provider call to this run's cluster. The target facts come only from target.json,
    whose SHA-256 must equal the entry in the manifest bytes this call's pre-check verified."""

    def __init__(self, manifest: bytes, deploy_root: str, run_folder: Path, target: Target = PG62):
        self.preset = preset(target)
        self.connect_calls = 0
        self.connections: list[Any] = []
        self.last_error = ""
        self.copy_paths: list[str] = []
        try:
            _, entries = om.parse_manifest(manifest)
            entry = next(e for e in entries if e.path == self.preset.target_doc)
            listed = om.read_verified_entry(manifest, deploy_root, self.preset.target_doc)
        except (om.OpsManifestRefused, StopIteration):
            raise Pg62Refused("pg62_target_not_bound") from None
        try:
            actual = (run_folder / "target.json").read_bytes()
        except OSError:
            raise Pg62Refused("pg62_target_not_bound") from None
        if hashlib.sha256(actual).hexdigest() != entry.sha256 or actual != listed:
            raise Pg62Refused("pg62_target_hash_mismatch")
        self.target = json.loads(actual)

    def before_connect(self, kwargs: dict[str, str]) -> None:
        t, fixed = self.target, self.preset
        if pg_environment_present():
            raise Pg62Refused("pg62_pg_environment_present")
        if kwargs.get("host") != HOST or t.get("host") != HOST:
            raise Pg62Refused("pg62_host_refused")
        if kwargs.get("port") != str(fixed.port) or t.get("port") != fixed.port:
            raise Pg62Refused("pg62_port_refused")
        if kwargs.get("dbname") not in t["databases"] or kwargs.get("dbname") not in fixed.databases:
            raise Pg62Refused("pg62_database_refused")
        if kwargs.get("user") not in t["provider_roles"] or kwargs.get("user") not in fixed.provider_roles \
                or kwargs.get("user") == fixed.admin:
            raise Pg62Refused("pg62_role_refused")
        if kwargs.get("sslmode") != "verify-full":
            raise Pg62Refused("pg62_tls_mode_refused")
        if not _ours(t["postmaster_pid"], fixed) or not same_path(t["postgres_exe"], POSTGRES_EXE) \
                or not same_path(t["data"], fixed.data):
            raise Pg62Refused("pg62_server_not_ours")

    def driver(self, **kwargs: str) -> Any:
        """The only provider-path call of the real driver."""
        self.before_connect(kwargs)
        self.copy_paths.append(kwargs.get("sslrootcert", ""))
        self.connect_calls += 1
        try:
            conn = psycopg.connect(**kwargs)
        except psycopg.Error as error:
            self.last_error = classify(error)
            raise
        self.connections.append(conn)
        if conn.info.hostaddr not in LOOPBACK:
            conn.close()
            raise Pg62Refused("pg62_not_loopback")
        return conn


class GuardedObserver:
    """Post-connect target checks inside the observation transaction, then the 6-1c observer.
    Keeps the last observation and the server facts as evidence (no secrets)."""

    FACTS = ("SELECT pg_catalog.host(pg_catalog.inet_server_addr()) AS server_addr, "
             "pg_catalog.inet_server_port() AS server_port, "
             "pg_catalog.current_setting('server_version_num') AS version, "
             "pg_catalog.current_database()::pg_catalog.text AS dbname, "
             "(SELECT d.oid FROM pg_catalog.pg_database AS d "
             " WHERE d.datname OPERATOR(pg_catalog.=) pg_catalog.current_database()) AS db_oid, "
             "pg_catalog.current_setting('application_name') AS application_name, "
             "pg_catalog.current_setting('idle_in_transaction_session_timeout') AS idle_timeout, "
             "pg_catalog.current_setting('statement_timeout') AS statement_timeout, "
             "pg_catalog.current_setting('lock_timeout') AS lock_timeout")

    def __init__(self, guard: Guard, hook: Callable[[Any], Any] | None = None):
        self.guard = guard
        self.hook = hook
        self.last: pv.Observation | None = None
        self.facts: dict[str, Any] = {}

    def observe(self, connection: Any) -> pv.Observation:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(self.FACTS)
            facts = cursor.fetchone()
        t = self.guard.target
        db = t["databases"].get(facts["dbname"])
        if facts["server_addr"] not in LOOPBACK or facts["server_port"] != self.guard.preset.port \
                or facts["version"] != t["server_version_num"] or db is None or facts["db_oid"] != db["oid"]:
            raise Pg62Refused("pg62_connected_target_mismatch")
        self.facts = {k: (str(v) if k == "db_oid" else v) for k, v in facts.items()}
        target = self.hook(connection) if self.hook else connection
        observation = ob.CatalogObserver().observe(target)
        self.last = observation
        if observation.identity_value != db["identity_value"]:
            raise Pg62Refused("pg62_identity_row_mismatch")      # not this run's database
        return observation


class HookedConnection:
    """Forwards to the real connection; after the module's `columns` query runs, calls `after`."""

    def __init__(self, connection: Any, after: Callable[[], None]):
        self._c, self._after = connection, after

    def __getattr__(self, name: str) -> Any:
        return getattr(self._c, name)

    def cursor(self, *args: Any, **kwargs: Any) -> Any:
        real, after = self._c.cursor(*args, **kwargs), self._after

        class Cursor:
            def __enter__(self):
                real.__enter__()
                return self

            def __exit__(self, *exc):
                return real.__exit__(*exc)

            def execute(self, query, params=None):
                result = real.execute(query, params)
                if query == ob.QUERIES["columns"]:
                    after()
                return result

            def fetchall(self):
                return real.fetchall()

        return Cursor()


def identifier(name: str) -> sql.Identifier:
    return sql.Identifier(name)

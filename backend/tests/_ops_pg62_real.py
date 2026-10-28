"""6-2 real local PostgreSQL run (OPS_REAL_PG_6_2_PLAN.md), run explicitly, never by discovery:

    python tests/_ops_pg62_real.py prepare    # folders, TLS, initdb, start, roles, DBs, target.json
    python tests/_ops_pg62_real.py check      # rotates passwords in memory, runs the 6-2 checklist
    python tests/_ops_pg62_real.py cleanup    # R2: record vs live facts, stop, delete this run only

The target is fixed in `_ops_pg62` (localhost:55462, C:/JV_Tools/pg62); no argument chooses it.
Every step writes evidence to runs/<id>/record.json at once; nothing secret is written or printed.
The checklist stops at the first failure (classified) and leaves the cluster for safe cleanup.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from dataclasses import replace
from pathlib import Path
from urllib.parse import quote

TESTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS_DIR.parent / "scripts"))
sys.path.insert(0, str(TESTS_DIR))

import psycopg  # noqa: E402
from psycopg import sql  # noqa: E402
from psycopg.pq import TransactionStatus  # noqa: E402

import _ops_adapter as ad  # noqa: E402
import _ops_approval as oa  # noqa: E402
import _ops_observer as ob  # noqa: E402
import _ops_preflight as op  # noqa: E402
import _ops_provider as pv  # noqa: E402
import _ops_pg62 as g  # noqa: E402
import test_ops_preflight as pf  # noqa: E402  (helpers only)
import test_ops_signature as sigtests  # noqa: E402  (test key helper only)

SYN = ob.IDENTITY_SCHEMA


class CheckFailed(Exception):
    def __init__(self, kind: str, what: str):
        super().__init__(what)
        self.kind, self.what = kind, what        # kind: product_defect / harness_defect / preparation_failure


def expect(condition: bool, what: str, kind: str = "product_defect") -> None:
    if not condition:
        raise CheckFailed(kind, what)


def run(args: list[str], *, cwd: Path | None = None, env_extra: dict | None = None) -> None:
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith("PG")}
    env.update(env_extra or {})
    done = subprocess.run(args, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL, creationflags=g.NO_WINDOW, timeout=120)
    if done.returncode != 0:
        raise CheckFailed("preparation_failure", f"{Path(args[0]).name} exit {done.returncode}")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# --- prepare ------------------------------------------------------------------------------------

def openssl(folder: Path, *args: str) -> None:
    run([str(g.OPENSSL), *args], cwd=folder, env_extra={"MSYS_NO_PATHCONV": "1", "MSYS2_ARG_CONV_EXCL": "*"})


def make_tls(rec: g.Record, secret: Path) -> None:
    tls = g.TLS
    for name, cn in (("ca", "jp_vocab 6-2 synthetic test CA"), ("wrongca", "jp_vocab 6-2 wrong test CA")):
        openssl(secret, "genpkey", "-algorithm", "EC", "-pkeyopt", "ec_paramgen_curve:P-256", "-out", f"{name}.key")
        openssl(secret, "req", "-x509", "-new", "-key", f"{name}.key", "-sha256", "-days", "2", "-subj", f"/CN={cn}",
                "-addext", "basicConstraints=critical,CA:TRUE", "-addext", "keyUsage=critical,keyCertSign,cRLSign",
                "-out", str(tls / f"{name}.crt"))
    for name, cn, san in (("server", "localhost", "DNS:localhost,IP:127.0.0.1,IP:::1"),
                          ("mismatch", "mismatch.test", "DNS:mismatch.test")):
        openssl(secret, "genpkey", "-algorithm", "EC", "-pkeyopt", "ec_paramgen_curve:P-256",
                "-out", str(tls / f"{name}.key"))
        openssl(secret, "req", "-new", "-key", str(tls / f"{name}.key"), "-subj", f"/CN={cn}",
                "-addext", f"subjectAltName={san}", "-addext", "extendedKeyUsage=serverAuth",
                "-addext", "basicConstraints=critical,CA:FALSE", "-out", f"{name}.csr")
        openssl(secret, "x509", "-req", "-in", f"{name}.csr", "-CA", str(tls / "ca.crt"), "-CAkey", "ca.key",
                "-set_serial", "0x" + secrets.token_hex(8), "-days", "2", "-sha256", "-copy_extensions", "copy",
                "-out", str(tls / f"{name}.crt"))
        run(["icacls", str(tls / f"{name}.key"), "/inheritance:r", "/grant:r", f"{os.environ['USERNAME']}:F"])
    rec.event("tls_created", folder=str(tls),
              certificates={n: sha(tls / f"{n}.crt") for n in ("ca", "wrongca", "server", "mismatch")},
              keys=[str(tls / "server.key"), str(tls / "mismatch.key")])
    for path in sorted(secret.iterdir()):            # CA private keys, CSRs: removed right after signing
        path.unlink()
    secret.rmdir()
    expect(not secret.exists(), "secret folder removed", "preparation_failure")
    rec.event("secret_folder_removed", path=str(secret))


CONF = """
# --- 6-2 synthetic test cluster (OPS_REAL_PG_6_2_PLAN.md) ---
port = 55462
listen_addresses = 'localhost'
max_connections = 30
ssl = on
ssl_cert_file = 'C:/JV_Tools/pg62/tls/server.crt'
ssl_key_file = 'C:/JV_Tools/pg62/tls/server.key'
ssl_min_protocol_version = 'TLSv1.3'
password_encryption = 'scram-sha-256'
log_statement = 'none'
log_min_error_statement = 'panic'
log_connections = on
logging_collector = off
"""


def hba(principal: str) -> str:
    lines = []
    for addr in ("127.0.0.1/32", "::1/128"):
        lines += [f"hostssl postgres,{g.DB_A},{g.DB_B} {g.ADMIN} {addr} sspi map=pg62 include_realm=1 compat_realm=1",
                  f"hostssl {g.DB_A},{g.DB_B} {g.READ},{g.WRITE} {addr} scram-sha-256",
                  f"hostssl {g.DB_A} {g.OWNER_LOGIN} {addr} scram-sha-256"]
    lines += ["hostnossl all all 127.0.0.1/32 reject", "hostnossl all all ::1/128 reject",
              "host all all 0.0.0.0/0 reject", "host all all ::0/0 reject"]
    return "\n".join(lines) + "\n"


def start_server(rec: g.Record) -> int:
    run([str(g.BIN / "pg_ctl.exe"), "start", "-D", str(g.DATA), "-l", str(rec.folder / "server.log"), "-w",
         "-t", "30", "-s"])
    for _ in range(20):
        pid = g.postmaster_pid()
        if pid and g.server_is_ours(pid):
            rec.event("server_started", pid=pid, executable=g.process_image(pid), data=str(g.DATA), port=g.PORT)
            return pid
        time.sleep(0.5)
    raise CheckFailed("preparation_failure", "started server not confirmed as ours")


def prepare() -> None:
    if g.pg_environment_present():
        raise CheckFailed("preparation_failure", "PG environment variables present")
    if g.ROOT.exists():
        raise CheckFailed("preparation_failure", "pg62 root already exists")
    if g.listener_pids(g.PORT):
        raise CheckFailed("preparation_failure", "port 55462 in use")
    run_id = time.strftime("%Y%m%dT%H%M%S")
    g.ROOT.mkdir()
    g.TLS.mkdir()
    g.RUNS.mkdir()
    folder = g.RUNS / run_id
    folder.mkdir()
    rec = g.Record(folder)
    rec.event("folders_created", paths=[str(g.ROOT), str(g.TLS), str(g.RUNS), str(folder)])
    secret = Path(os.environ["LOCALAPPDATA"]) / "Temp" / f"jpv_pg62_{run_id}"
    secret.mkdir()
    rec.event("secret_folder_created", path=str(secret))
    make_tls(rec, secret)
    run([str(g.BIN / "initdb.exe"), "-D", str(g.DATA), "-U", g.ADMIN, "-A", "reject", "-E", "UTF8",
         "--locale=C", "--no-instructions"])
    rec.event("initdb", data=str(g.DATA), bootstrap_role=g.ADMIN)
    principal = f"{os.environ['USERNAME']}@{os.environ['COMPUTERNAME']}"
    with open(g.DATA / "postgresql.conf", "a", encoding="utf-8", newline="\n") as handle:
        handle.write(CONF)
    (g.DATA / "pg_hba.conf").write_text(hba(principal), encoding="utf-8", newline="\n")
    (g.DATA / "pg_ident.conf").write_text(f"pg62 {principal} {g.ADMIN}\n", encoding="utf-8", newline="\n")
    rec.event("config_written", files=["postgresql.conf (appended)", "pg_hba.conf", "pg_ident.conf"])
    pid = start_server(rec)
    nonce = secrets.token_hex(8)
    identities = {g.DB_A: f"pg62-a-{nonce}", g.DB_B: f"pg62-b-{nonce}"}
    with g.admin_connect("postgres", record_pid=pid) as admin:
        version = admin.execute("SELECT pg_catalog.current_setting('server_version_num')").fetchone()[0]
        for role, login in ((g.OWNER, False), (g.READ, True), (g.WRITE, True)):
            base = sql.SQL("CREATE ROLE {} {} NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS").format(
                sql.Identifier(role), sql.SQL("LOGIN" if login else "NOLOGIN"))
            if login:
                base = sql.SQL("{} PASSWORD {}").format(base, sql.Literal(g.scram_verifier(g.new_password())))
            admin.execute(base)
            oid = admin.execute("SELECT oid FROM pg_catalog.pg_roles WHERE rolname = %s", (role,)).fetchone()[0]
            rec.event("role_created", name=role, oid=oid)
        for db in (g.DB_A, g.DB_B):
            admin.execute(sql.SQL("CREATE DATABASE {} OWNER {} TEMPLATE template0 ENCODING 'UTF8' LOCALE 'C'").format(
                sql.Identifier(db), sql.Identifier(g.OWNER)))
            oid = admin.execute("SELECT oid FROM pg_catalog.pg_database WHERE datname = %s", (db,)).fetchone()[0]
            rec.event("database_created", name=db, oid=oid)
            admin.execute(sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(sql.Identifier(db)))
            admin.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}, {}").format(
                sql.Identifier(db), sql.Identifier(g.READ), sql.Identifier(g.WRITE)))
    databases = {}
    for db in (g.DB_A, g.DB_B):
        with g.admin_connect(db, record_pid=pid) as admin:
            for statement in (
                    f"CREATE SCHEMA {SYN} AUTHORIZATION {g.OWNER}",
                    f"CREATE TABLE {SYN}.db_identity (identity_value text NOT NULL)",
                    "CREATE TABLE public.users (id integer PRIMARY KEY, email text)",
                    "CREATE TABLE public.vocab_items (id integer PRIMARY KEY, word text)",
                    "CREATE SEQUENCE public.vocab_items_id_seq",
                    f"ALTER TABLE {SYN}.db_identity OWNER TO {g.OWNER}",
                    f"ALTER TABLE public.users OWNER TO {g.OWNER}",
                    f"ALTER TABLE public.vocab_items OWNER TO {g.OWNER}",
                    f"ALTER SEQUENCE public.vocab_items_id_seq OWNER TO {g.OWNER}",
                    f"GRANT USAGE ON SCHEMA {SYN} TO {g.READ}, {g.WRITE}",
                    f"GRANT SELECT ON public.users, public.vocab_items, {SYN}.db_identity TO {g.READ}, {g.WRITE}",
                    f"GRANT UPDATE ON public.vocab_items TO {g.WRITE}",
                    f"GRANT USAGE ON SEQUENCE public.vocab_items_id_seq TO {g.WRITE}"):
                admin.execute(statement)
            admin.execute(f"INSERT INTO {SYN}.db_identity (identity_value) VALUES (%s)", (identities[db],))
            oid = admin.execute("SELECT oid FROM pg_catalog.pg_database WHERE datname = "
                                "pg_catalog.current_database()").fetchone()[0]
            rec.event("synthetic_objects_created", database=db,
                      objects=[f"{SYN} schema", f"{SYN}.db_identity", "public.users", "public.vocab_items",
                               "public.vocab_items_id_seq"], identity_value=identities[db])
            databases[db] = {"oid": oid, "identity_value": identities[db]}
    target = {"run_id": rec.folder.name, "host": g.HOST, "port": g.PORT, "data": str(g.DATA),
              "postgres_exe": str(g.POSTGRES_EXE), "postmaster_pid": pid, "server_version_num": version,
              "databases": databases, "provider_roles": list(g.PROVIDER_ROLES), "admin_role": g.ADMIN,
              "ca_sha256": sha(g.TLS / "ca.crt")}
    data = json.dumps(target, indent=1, sort_keys=True).encode()
    (rec.folder / "target.json").write_bytes(data)
    rec.event("target_written", sha256=hashlib.sha256(data).hexdigest(), server_version_num=version)


# --- check helpers ----------------------------------------------------------------------------------

READ_OBJECTS = frozenset({("database", "", g.DB_A), ("schema", "", "public"), ("schema", "", SYN),
                          ("table", "public", "users"), ("table", "public", "vocab_items"),
                          ("table", SYN, "db_identity"), ("sequence", "public", "vocab_items_id_seq"),
                          ("tablespace", "", "pg_default"), ("tablespace", "", "pg_global")})
READ_PRIVS = frozenset({("database", "", g.DB_A, "", "CONNECT"), ("schema", "", "public", "", "USAGE"),
                        ("schema", "", SYN, "", "USAGE"), ("table", "public", "users", "", "SELECT"),
                        ("table", "public", "vocab_items", "", "SELECT"), ("table", SYN, "db_identity", "", "SELECT")})
WRITE_PRIVS = READ_PRIVS | {("table", "public", "vocab_items", "", "UPDATE"),
                            ("sequence", "public", "vocab_items_id_seq", "", "USAGE")}
SEARCH_PATH = '"$user", public'
READ_EXPECTED = pv.ExpectedProfile(READ_OBJECTS, READ_PRIVS, SEARCH_PATH, frozenset({"TLSv1.3"}))
WRITE_EXPECTED = pv.ExpectedProfile(READ_OBJECTS, WRITE_PRIVS, SEARCH_PATH, frozenset({"TLSv1.3"}))


class Harness:
    def __init__(self, rec: g.Record):
        self.rec = rec
        self.target_bytes = (rec.folder / "target.json").read_bytes()
        self.target = json.loads(self.target_bytes)
        self.pid = self.target["postmaster_pid"]
        self.keys = sigtests.Keys()
        self.allowed = self.keys.allowed(namespaces="jp-vocab-ops/v1/synthetic/*")
        self.passwords: dict[str, str] = {}
        self.deploys: list[str] = []

    def close(self) -> None:
        self.keys.close()
        for folder in self.deploys:
            shutil.rmtree(folder, ignore_errors=True)
        self.passwords.clear()

    def admin(self, db: str, autocommit: bool = True):
        return g.admin_connect(db, record_pid=self.pid, autocommit=autocommit)

    def set_password(self, role: str) -> None:
        password = g.new_password()
        with self.admin("postgres") as admin:
            admin.execute(sql.SQL("ALTER ROLE {} PASSWORD {}").format(
                sql.Identifier(role), sql.Literal(g.scram_verifier(password))))
        self.passwords[role] = password

    def deploy(self, *, root_pem: bytes | None = None, target_bytes: bytes | None = None) -> tuple[str, bytes]:
        folder = os.path.normpath(tempfile.mkdtemp(prefix="ops_pg62_deploy_"))
        self.deploys.append(folder)
        files = {k: v for k, v in pf.FILES.items() if k != "ops/tls/root.pem"}
        files["ops/tls/root.pem"] = root_pem if root_pem is not None else (g.TLS / "ca.crt").read_bytes()
        files[g.TARGET_DOC] = target_bytes if target_bytes is not None else self.target_bytes
        for rel, data in files.items():
            path = os.path.join(folder, *rel.split("/"))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as handle:
                handle.write(data)
        return folder, pf.manifest_doc(files)

    def sign(self, data: bytes, subject: str) -> bytes:
        return self.keys.sign("signer", oa.signature_namespace("synthetic", subject), data)

    def inputs(self, *, role=g.READ, access="read", db=g.DB_A, identity_db=None, port=g.PORT, host=g.HOST,
               expected=READ_EXPECTED, root_pem=None, target_bytes=None, sslmode="verify-full",
               password=None) -> op.PreflightInput:
        folder, manifest = self.deploy(root_pem=root_pem, target_bytes=target_bytes)
        identity = self.target["databases"][identity_db or db]["identity_value"] \
            if (identity_db or db) in self.target["databases"] else "pg62-none"
        target = op.TargetObservation(host=host, port=port, database=db, server_major=18, identity_value=identity)
        profile = pv.expected_profile_fingerprint(expected, role=role, access="read")
        inquiry = json.dumps({
            "format_version": 1, "kind": "inquiry", "approval_id": "inq-0000000000000062", "supersedes": None,
            "purpose": "synthetic", "alias": "synthetic-primary", "db_identity": pf.db_identity(target),
            "manifest": pf.om.manifest_fingerprint(manifest), "tool": "prb_recover",
            "steps": [{"command": "preview", "access": "read", "role": role, "profile": profile}],
            "accounts": [7], "max_accounts": 1, "job": json.loads(json.dumps(pf.JOB)),
            "valid_from": "2026-10-21T12:00:00Z", "valid_until": "2026-10-21T13:00:00Z",
            "approved_by": "synthetic signer"}).encode()
        root = os.path.join(folder, "ops", "tls", "root.pem")
        pw = password if password is not None else self.passwords.get(role, "unset-password")
        dsn = (f"postgresql://{role}:{pw}@{host}:{port}/{db}?sslmode={sslmode}"
               f"&sslrootcert={quote(root, safe='')}")
        values = dict(mode="synthetic", approval=inquiry, approval_signature=self.sign(inquiry, "approval"),
                      manifest=manifest, manifest_signature=self.sign(manifest, "manifest"), deploy_root=folder,
                      command="preview", args={}, account_id=7, job_key=pf.JOB["key"],
                      job_inputs=pf.JOB["inputs"], product_fingerprint=pf.PRODUCT, target=target,
                      connection=op.ConnectionObservation(profile=profile, read_only=True), secret_dsn=dsn,
                      environment={"PATH": "C:/Windows"},
                      trust=op.SyntheticTrust(self.allowed, b"", sigtests.PRINCIPAL), now=sigtests.T0)
        if access == "write":
            plan = op.run_synthetic_preflight(op.PreflightInput(**values)).job_plan
            wprofile = pv.expected_profile_fingerprint(expected, role=role, access="write")
            doc = json.loads(inquiry)
            doc.update(kind="apply", approval_id="app-0000000000000062", based_on={
                "approval_id": doc["approval_id"], "sha256": hashlib.sha256(inquiry).hexdigest()},
                steps=[{"command": "prepare", "access": "write", "role": role, "profile": wprofile}],
                plan={"7": plan})
            apply = json.dumps(doc).encode()
            values.update(approval=apply, approval_signature=self.sign(apply, "approval"), inquiry=inquiry,
                          inquiry_signature=self.sign(inquiry, "approval"), command="prepare",
                          connection=op.ConnectionObservation(profile=wprofile, read_only=False))
        return op.PreflightInput(**values)

    def provide(self, inputs, expected=READ_EXPECTED, hook=None):
        """Returns (handoff or None, refusal or None, guard, observer)."""
        guard = g.Guard(inputs.manifest, inputs.deploy_root, self.rec.folder)
        observer = g.GuardedObserver(guard, hook)
        try:
            handoff = pv.provide_synthetic_connection(
                inputs, expected=expected, factory=ad.CopyingFactory(inputs.manifest, inputs.deploy_root, guard.driver),
                observer=observer)
        except pv.OpsProviderRefused as refused:
            return None, refused, guard, observer
        return handoff, None, guard, observer

    def refused(self, code, inputs, expected=READ_EXPECTED, hook=None):
        handoff, refused, guard, observer = self.provide(inputs, expected, hook)
        expect(handoff is None and refused is not None, f"expected refusal {code}, got handover")
        expect(refused.code == code, f"expected {code}, got {refused.code} {refused.also}")
        for conn in guard.connections:
            expect(conn.closed, "refused connection left open")
        for path in guard.copy_paths:
            expect(not os.path.lexists(path), "certificate copy left behind")
        for secret in self.passwords.values():
            expect(secret not in repr(refused) + repr(refused.also), "secret in refusal")
        return refused, guard, observer

    def handed(self, inputs, expected=READ_EXPECTED):
        handoff, refused, guard, observer = self.provide(inputs, expected)
        expect(handoff is not None, f"expected handover, got {refused and (refused.code, refused.also)}")
        for path in guard.copy_paths:
            expect(not os.path.lexists(path), "certificate copy left behind")
        return handoff, guard, observer


# --- the checklist (plan 3절) ----------------------------------------------------------------------

def c01_read(h: Harness) -> dict:
    handoff, guard, obs = h.handed(h.inputs())
    o, conn = obs.last, handoff.take()
    expect(conn.info.transaction_status == TransactionStatus.IDLE, "not IDLE at handover")
    expect(o.observation_read_only and o.default_read_only and o.default_isolation == "read committed",
           "read business defaults")
    expect((o.tls_in_use, o.tls_server_ssl, o.tls_version) == (True, True, "TLSv1.3"), "TLS state")
    expect(frozenset(o.objects) == READ_OBJECTS and frozenset(o.privileges) == READ_PRIVS, "read profile")
    expect(o.memberships == () and o.owned_count == 0 and o.unresolved == (), "role state")
    expect(obs.facts["application_name"] == pv.APPLICATION_NAME and obs.facts["idle_timeout"] == "1min",
           "provider-fixed server settings applied")
    conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
    iso, ro = conn.execute("SELECT pg_catalog.current_setting('transaction_isolation'), "
                           "pg_catalog.current_setting('transaction_read_only')").fetchone()
    expect((iso, ro) == ("repeatable read", "on"), "business first statement")
    conn.rollback()
    conn.close()
    return {"connect_calls": guard.connect_calls, "facts": obs.facts, "objects": len(o.objects),
            "privileges": len(o.privileges)}


def c02_write(h: Harness) -> dict:
    handoff, guard, obs = h.handed(h.inputs(role=g.WRITE, access="write", expected=WRITE_EXPECTED), WRITE_EXPECTED)
    o, conn = obs.last, handoff.take()
    expect(o.observation_read_only and not o.default_read_only, "write: observation RO, business RW")
    expect(frozenset(o.privileges) == WRITE_PRIVS, "write profile")
    conn.execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED")
    ro = conn.execute("SELECT pg_catalog.current_setting('transaction_read_only')").fetchone()[0]
    expect(ro == "off", "write business transaction writable")
    conn.rollback()
    conn.close()
    return {"default_read_only": o.default_read_only}


def c03_queries(h: Harness) -> dict:
    """All module queries ran through the real server with the 6-1c types (implied by c01/c02);
    here once more with the query order recorded from the real cursor."""
    names: list[str] = []

    def hook(conn):
        class Spy(g.HookedConnection):
            def cursor(self, *a, **k):
                real = conn.cursor(*a, **k)

                class C:
                    def __enter__(self):
                        real.__enter__()
                        return self

                    def __exit__(self, *exc):
                        return real.__exit__(*exc)

                    def execute(self, query, params=None):
                        names.extend(n for n, q in ob.QUERIES.items() if q == query)
                        return real.execute(query, params)

                    def fetchall(self):
                        return real.fetchall()
                return C()
        return Spy(conn, lambda: None)

    handoff, _, guard, _ = h.provide(h.inputs(), READ_EXPECTED, hook)
    expect(handoff is not None, "handover with query spy")
    handoff.take().close()
    expect(sorted(names) == sorted(ob.QUERIES) and len(names) == len(ob.QUERIES), f"query set {len(names)}")
    return {"queries_run": len(names)}


def c05_search_path(h: Harness) -> dict:
    normal = h.handed(h.inputs())[2].last
    setup = ["CREATE SCHEMA evil", f"GRANT USAGE ON SCHEMA evil TO {g.READ}",
             "CREATE FUNCTION evil.false_oideq(oid, oid) RETURNS boolean LANGUAGE sql IMMUTABLE AS 'SELECT false'",
             "CREATE OPERATOR evil.= (LEFTARG = oid, RIGHTARG = oid, FUNCTION = evil.false_oideq)",
             "CREATE FUNCTION evil.current_setting(text) RETURNS text LANGUAGE sql AS 'SELECT ''evil'''",
             "CREATE FUNCTION evil.has_table_privilege(name, oid, text) RETURNS boolean LANGUAGE sql AS 'SELECT true'",
             f"ALTER ROLE {g.READ} IN DATABASE {g.DB_A} SET search_path = evil, pg_catalog"]
    revert = [f"ALTER ROLE {g.READ} IN DATABASE {g.DB_A} RESET search_path",
              "DROP FUNCTION evil.has_table_privilege(name, oid, text)", "DROP FUNCTION evil.current_setting(text)",
              "DROP OPERATOR evil.= (oid, oid)", "DROP FUNCTION evil.false_oideq(oid, oid)",
              f"REVOKE USAGE ON SCHEMA evil FROM {g.READ}", "DROP SCHEMA evil"]
    with h.admin(g.DB_A) as admin:
        for s in setup:
            admin.execute(s)
        h.rec.event("variant_applied", check="c05", statements=len(setup))
        try:
            _, _, o = h.refused("observed_search_path_mismatch", h.inputs())
        finally:
            for s in revert:
                admin.execute(s)
            h.rec.event("variant_reverted", check="c05")
    o = o.last
    expect(o.search_path == "evil, pg_catalog", "evil search_path observed")
    expect(frozenset(o.objects) - frozenset(normal.objects) == {("schema", "", "evil")}, "only the evil schema added")
    expect(frozenset(o.privileges) - frozenset(normal.privileges) == {("schema", "", "evil", "", "USAGE")},
           "privileges unchanged apart from evil USAGE")
    expect((o.owned_count, o.memberships, o.unresolved, o.default_read_only) == (0, (), (), True),
           "other values unchanged")
    return {"search_path": o.search_path}


def variant(h: Harness, check: str, db: str, setup: list, revert: list, code: str, inputs=None,
            expected=READ_EXPECTED) -> pv.Observation | None:
    with h.admin(db) as admin:
        for s in setup:
            admin.execute(s)
        h.rec.event("variant_applied", check=check, statements=len(setup))
        try:
            _, _, observer = h.refused(code, inputs or h.inputs(), expected)
        finally:
            for s in revert:
                admin.execute(s)
            h.rec.event("variant_reverted", check=check)
    return observer.last


def c06_privileges(h: Harness) -> dict:
    out = {}
    o = variant(h, "c06a", g.DB_A, [f"GRANT UPDATE ON public.users TO {g.READ}"],
                [f"REVOKE UPDATE ON public.users FROM {g.READ}"], "observed_privileges_excess")
    expect(("table", "public", "users", "", "UPDATE") in o.privileges, "table UPDATE observed")
    o = variant(h, "c06b", g.DB_A, [f"GRANT UPDATE (email) ON public.users TO {g.READ}"],
                [f"REVOKE UPDATE (email) ON public.users FROM {g.READ}"], "observed_privileges_excess")
    expect(("table", "public", "users", "email", "UPDATE") in o.privileges
           and ("table", "public", "users", "", "UPDATE") not in o.privileges, "column-only UPDATE observed")
    o = variant(h, "c06c", g.DB_A, ["GRANT INSERT ON public.vocab_items TO PUBLIC"],
                ["REVOKE INSERT ON public.vocab_items FROM PUBLIC"], "observed_privileges_excess")
    expect(("table", "public", "vocab_items", "", "INSERT") in o.privileges, "PUBLIC INSERT observed")
    with h.admin("postgres") as admin:
        admin.execute(f"CREATE ROLE {g.EXTRA} NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS")
        oid = admin.execute("SELECT oid FROM pg_catalog.pg_roles WHERE rolname = %s", (g.EXTRA,)).fetchone()[0]
        h.rec.event("role_created", name=g.EXTRA, oid=oid, temporary=True)
    try:
        for inherit, label in (("TRUE", "c06d_inherit"), ("FALSE", "c06e_noinherit")):
            o = variant(h, label, g.DB_A,
                        [f"GRANT DELETE ON public.users TO {g.EXTRA}",
                         f"GRANT {g.EXTRA} TO {g.READ} WITH INHERIT {inherit}"],
                        [f"REVOKE {g.EXTRA} FROM {g.READ}", f"REVOKE DELETE ON public.users FROM {g.EXTRA}"],
                        "observed_memberships")
            inherited = ("table", "public", "users", "", "DELETE") in o.privileges
            expect(o.memberships == (g.EXTRA,), f"{label} membership observed")
            expect(inherited == (inherit == "TRUE"), f"{label} inherited privilege semantics")
            out[label] = {"delete_effective": inherited}
    finally:
        with h.admin("postgres") as admin:
            admin.execute(f"DROP ROLE {g.EXTRA}")
            h.rec.event("role_dropped", name=g.EXTRA)
    # owner refusal: authenticated through the 62a-only TLS+SCRAM rule, refused by the ownership check
    with h.admin("postgres") as admin:
        admin.execute(sql.SQL("CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS "
                              "PASSWORD {}").format(sql.Identifier(g.OWNER_LOGIN),
                                                    sql.Literal(g.scram_verifier("x" + g.new_password()))))
        oid = admin.execute("SELECT oid FROM pg_catalog.pg_roles WHERE rolname = %s", (g.OWNER_LOGIN,)).fetchone()[0]
        admin.execute(f"GRANT CONNECT ON DATABASE {g.DB_A} TO {g.OWNER_LOGIN}")
        h.rec.event("role_created", name=g.OWNER_LOGIN, oid=oid, temporary=True)
    try:
        h.set_password(g.OWNER_LOGIN)
        o = variant(h, "c06f_owner", g.DB_A,
                    [f"GRANT USAGE ON SCHEMA {SYN} TO {g.OWNER_LOGIN}",
                     f"GRANT SELECT ON public.users, public.vocab_items, {SYN}.db_identity TO {g.OWNER_LOGIN}",
                     "CREATE TABLE public.owner_probe (a integer)", f"ALTER TABLE public.owner_probe OWNER TO {g.OWNER_LOGIN}"],
                    ["DROP TABLE public.owner_probe",
                     f"REVOKE SELECT ON public.users, public.vocab_items, {SYN}.db_identity FROM {g.OWNER_LOGIN}",
                     f"REVOKE USAGE ON SCHEMA {SYN} FROM {g.OWNER_LOGIN}"],
                    "observed_ownership", h.inputs(role=g.OWNER_LOGIN))
        expect(o is not None and o.owned_count >= 1 and o.current_user == g.OWNER_LOGIN, "owner observed after auth")
        out["owner_owned_count"] = o.owned_count
    finally:
        h.passwords.pop(g.OWNER_LOGIN, None)
        with h.admin("postgres") as admin:
            admin.execute(f"REVOKE CONNECT ON DATABASE {g.DB_A} FROM {g.OWNER_LOGIN}")
            admin.execute(f"DROP ROLE {g.OWNER_LOGIN}")
            h.rec.event("role_dropped", name=g.OWNER_LOGIN)
    o = variant(h, "c06g_new_table", g.DB_A,
                ["CREATE TABLE public.new_table (a integer)", f"ALTER TABLE public.new_table OWNER TO {g.OWNER}"],
                ["DROP TABLE public.new_table"], "observed_objects_mismatch")
    expect(("table", "public", "new_table") in o.objects
           and not any(p[2] == "new_table" for p in o.privileges), "new table kept without privileges")
    o = variant(h, "c06h_secdef", g.DB_A,
                ["CREATE FUNCTION public.secdef_probe() RETURNS integer LANGUAGE sql SECURITY DEFINER AS 'SELECT 1'",
                 f"ALTER FUNCTION public.secdef_probe() OWNER TO {g.OWNER}"],
                ["DROP FUNCTION public.secdef_probe()"], "observed_objects_mismatch")
    secdef = [k for k in o.objects if k[0] == "security_definer_routine"]
    expect(len(secdef) == 1 and secdef[0][2].startswith("secdef_probe$")
           and any(p[:3] == secdef[0] and p[4] == "EXECUTE" for p in o.privileges), "SECURITY DEFINER + PUBLIC EXECUTE")
    o = variant(h, "c06i_default_acl", g.DB_A,
                [f"ALTER DEFAULT PRIVILEGES FOR ROLE {g.OWNER} IN SCHEMA public GRANT INSERT ON TABLES TO {g.READ}"],
                [f"ALTER DEFAULT PRIVILEGES FOR ROLE {g.OWNER} IN SCHEMA public REVOKE INSERT ON TABLES FROM {g.READ}"],
                "observed_objects_mismatch")
    expect(("default_acl", "public", f"{g.OWNER}.tables", "", "INSERT") in o.privileges, "default ACL observed")
    return out


def c07_completeness(h: Harness) -> dict:
    with h.admin(g.DB_A) as admin:
        for s in ("ALTER TABLE public.users ADD COLUMN drop_probe integer", "ALTER TABLE public.users DROP COLUMN drop_probe",
                  "CREATE TABLE public.empty_table ()", f"ALTER TABLE public.empty_table OWNER TO {g.OWNER}",
                  f"GRANT SELECT ON public.empty_table TO {g.READ}"):
            admin.execute(s)
        h.rec.event("variant_applied", check="c07")
        try:
            expected = pv.ExpectedProfile(READ_OBJECTS | {("table", "public", "empty_table")},
                                          READ_PRIVS | {("table", "public", "empty_table", "", "SELECT")},
                                          SEARCH_PATH, frozenset({"TLSv1.3"}))
            handoff, _, obs = h.handed(h.inputs(expected=expected), expected)
            handoff.take().close()
        finally:
            admin.execute("DROP TABLE public.empty_table")
            h.rec.event("variant_reverted", check="c07", note="dropped column stays as a dropped attribute")
    expect(obs.last.unresolved == (), "zero-column view and dropped column accepted")
    return {"objects": len(obs.last.objects)}


def c08_change_between_queries(h: Harness) -> dict:
    admin = h.admin(g.DB_A)
    try:
        def hook(conn):
            return g.HookedConnection(conn, lambda: admin.execute("ALTER TABLE public.users ADD COLUMN race_probe integer"))
        h.rec.event("variant_applied", check="c08")
        try:
            _, _, obs = h.refused("privilege_scope_unknown", h.inputs(), READ_EXPECTED, hook)
        finally:
            admin.execute("ALTER TABLE public.users DROP COLUMN IF EXISTS race_probe")
            h.rec.event("variant_reverted", check="c08")
    finally:
        admin.close()
    return {"unresolved": list(obs.last.unresolved) if obs.last else None}


def c09_other_db(h: Harness) -> dict:
    h.refused("observed_identity_mismatch", h.inputs(db=g.DB_B, identity_db=g.DB_A))
    return {}


def c10_tls(h: Harness) -> dict:
    _, guard, _ = h.refused("connect_failed", h.inputs(root_pem=(g.TLS / "wrongca.crt").read_bytes()))
    wrong_root = guard.last_error
    expect(wrong_root == "tls_certificate_verify_failed", f"wrong root classified {wrong_root}")
    with h.admin("postgres") as admin:
        admin.execute("ALTER SYSTEM SET ssl_cert_file = 'C:/JV_Tools/pg62/tls/mismatch.crt'")
        admin.execute("ALTER SYSTEM SET ssl_key_file = 'C:/JV_Tools/pg62/tls/mismatch.key'")
        admin.execute("SELECT pg_catalog.pg_reload_conf()")
        h.rec.event("variant_applied", check="c10_mismatch_cert")
        time.sleep(1.0)
        try:
            _, guard, _ = h.refused("connect_failed", h.inputs())
            mismatch = guard.last_error
        finally:
            admin.execute("ALTER SYSTEM RESET ssl_cert_file")
            admin.execute("ALTER SYSTEM RESET ssl_key_file")
            admin.execute("SELECT pg_catalog.pg_reload_conf()")
            h.rec.event("variant_reverted", check="c10_mismatch_cert")
            time.sleep(1.0)
    expect(mismatch in ("tls_host_name_mismatch", "tls_certificate_verify_failed"), f"SAN mismatch {mismatch}")
    h.handed(h.inputs())[0].take().close()
    return {"wrong_root": wrong_root, "san_mismatch": mismatch}


def c11_no_tls(h: Harness) -> dict:
    probe = g.raw_connect_probe(user=g.READ, password=h.passwords[g.READ], sslmode="disable", record_pid=h.pid)
    expect(probe in ("hba_reject_no_encryption", "hba_reject"), f"non-TLS probe {probe}")
    handoff, refused, guard, _ = h.provide(h.inputs(sslmode="require"))
    expect(handoff is None and refused.code == "preflight_tls_mode_mismatch" and guard.connect_calls == 0,
           f"provider non-TLS {refused and refused.code}")
    return {"probe": probe, "provider": refused.code}


def c12_lock(h: Harness) -> dict:
    admin = h.admin(g.DB_A, autocommit=False)
    try:
        admin.execute(f"LOCK TABLE {SYN}.db_identity IN ACCESS EXCLUSIVE MODE")
        h.rec.event("variant_applied", check="c12_lock")
        started = time.monotonic()
        h.refused("observation_lock_timeout", h.inputs())
        waited = round(time.monotonic() - started, 1)
        sessions = -1
        with h.admin("postgres") as watcher:                 # server side: the refused session is gone
            for _ in range(20):
                sessions = watcher.execute(
                    "SELECT count(*) FROM pg_catalog.pg_stat_activity WHERE application_name = %s AND usename = %s",
                    (pv.APPLICATION_NAME, g.READ)).fetchone()[0]
                if sessions == 0:
                    break
                time.sleep(0.25)
    finally:
        admin.rollback()
        admin.close()
        h.rec.event("variant_reverted", check="c12_lock")
    expect(1.5 <= waited < 5.0, f"lock wait {waited}s matches lock_timeout 2s, not statement_timeout 5s")
    expect(sessions == 0, "refused session still on the server")
    return {"lock_wait_seconds": waited, "server_sessions_after": sessions}


def c14_reconnect(h: Harness) -> dict:
    paths, observers, pids = [], [], []
    real = pv.op.run_synthetic_preflight
    calls = {"n": 0}

    def counting(inputs):
        calls["n"] += 1
        return real(inputs)

    pv.op.run_synthetic_preflight = counting
    try:
        inputs = h.inputs()                                  # the same approval for both connections
        for _ in range(2):
            handoff, guard, obs = h.handed(inputs)
            conn = handoff.take()
            pids.append(conn.info.backend_pid)
            conn.close()
            paths += guard.copy_paths
            observers.append(obs)
            expect(guard.connect_calls == 1, "one real connection per call")
    finally:
        pv.op.run_synthetic_preflight = real
    expect(calls["n"] == 2, f"pre-check per connection {calls['n']}")
    expect(len(set(paths)) == 2 and all(not os.path.lexists(p) for p in paths), "new copy per connection")
    expect(observers[0] is not observers[1] and all(o.last is not None for o in observers)
           and observers[0].last is not observers[1].last, "new observation per connection")
    expect(pids[0] != pids[1], "a new server session per connection")
    return {"preflight_calls": calls["n"], "distinct_copies": len(set(paths)), "distinct_sessions": len(set(pids))}


def c15_guard(h: Harness) -> dict:
    calls = {"n": 0}
    real = psycopg.connect

    def counting(*a, **k):
        calls["n"] += 1
        return real(*a, **k)

    results = {}
    psycopg.connect = counting
    try:
        cases = {
            "port_55432": dict(port=55432), "port_55463": dict(port=55463), "db_postgres": dict(db="postgres"),
            "role_admin": dict(role=g.ADMIN), "host_ip": dict(host="127.0.0.1"),
        }
        for label, change in cases.items():
            handoff, refused, guard, _ = h.provide(h.inputs(**change))
            expect(handoff is None and refused is not None and guard.connect_calls == 0, f"{label} not refused")
            results[label] = refused.code
        os.environ["PGHOSTADDR"] = "127.0.0.1"
        try:
            handoff, refused, guard, _ = h.provide(h.inputs())
        finally:
            del os.environ["PGHOSTADDR"]
        expect(handoff is None and refused.code == "pg62_pg_environment_present" and guard.connect_calls == 0, "PG env")
        results["pg_env"] = refused.code
        altered = json.loads(h.target_bytes)
        altered["postmaster_pid"] = altered["postmaster_pid"] + 1
        signed_other = json.dumps(altered, indent=1, sort_keys=True).encode()
        try:
            h.provide(h.inputs(target_bytes=signed_other))
            expect(False, "target hash mismatch not refused")
        except g.Pg62Refused as refused:
            results["target_hash"] = refused.code
        tmp = h.rec.folder / "target.json"
        original = tmp.read_bytes()
        tmp.write_bytes(signed_other)                   # a consistent, signed target with the wrong PID
        try:
            handoff, refused, guard, _ = h.provide(h.inputs(target_bytes=signed_other))
        finally:
            tmp.write_bytes(original)
        expect(handoff is None and refused.code == "pg62_server_not_ours" and guard.connect_calls == 0, "PID mismatch")
        results["pid_mismatch"] = refused.code
    finally:
        psycopg.connect = real
    expect(calls["n"] == 0, f"real connect attempted {calls['n']}")
    expect(results["port_55463"] == "pg62_port_refused", "55463 refused before connecting")
    return {"codes": results, "real_connect_attempts": calls["n"]}


def c16_param_and_large_object(h: Harness) -> dict:
    """Last on purpose: a parameter ACL row may outlive its REVOKE (shared catalog)."""
    o = variant(h, "c16_parameter", g.DB_A, [f"GRANT SET ON PARAMETER work_mem TO {g.READ}"],
                [f"REVOKE SET ON PARAMETER work_mem FROM {g.READ}"], "observed_objects_mismatch")
    expect(("parameter_acl", "", "work_mem", "", "SET") in o.privileges, "parameter SET observed")
    with h.admin(g.DB_A) as admin:
        lo = admin.execute("SELECT pg_catalog.lo_create(0)").fetchone()[0]
        h.rec.event("large_object_created", database=g.DB_A, oid=lo)
        try:
            admin.execute(sql.SQL("GRANT SELECT ON LARGE OBJECT {} TO {}").format(sql.Literal(lo), sql.Identifier(g.READ)))
            _, _, obs = h.refused("observed_objects_mismatch", h.inputs())
        finally:
            admin.execute("SELECT pg_catalog.lo_unlink(%s)", (lo,))
            h.rec.event("large_object_removed", oid=lo)
        remaining = admin.execute("SELECT count(*) FROM pg_catalog.pg_parameter_acl").fetchone()[0]
    expect(("large_object", "", str(lo), "", "SELECT") in obs.last.privileges, "large object SELECT observed")
    return {"parameter_acl_rows_after_revoke": remaining}


PLANNED = ("c01_read", "c02_write", "c03_queries", "c05_search_path", "c06_privileges", "c07_completeness",
           "c08_change_between_queries", "c09_other_db", "c10_tls", "c11_no_tls", "c12_lock", "c14_reconnect",
           "c15_guard", "c16_param_and_large_object")     # the full selection, fixed apart from CHECKS
RERUN = ("c01_read", "c02_write", "c12_lock", "c14_reconnect", "c15_guard", "c16_param_and_large_object")
CHECKS = [("c01_read", c01_read), ("c02_write", c02_write), ("c03_queries", c03_queries),
          ("c05_search_path", c05_search_path), ("c06_privileges", c06_privileges),
          ("c07_completeness", c07_completeness), ("c08_change_between_queries", c08_change_between_queries),
          ("c09_other_db", c09_other_db), ("c10_tls", c10_tls), ("c11_no_tls", c11_no_tls), ("c12_lock", c12_lock),
          ("c14_reconnect", c14_reconnect), ("c15_guard", c15_guard),
          ("c16_param_and_large_object", c16_param_and_large_object)]


def run_check(rec: g.Record, name: str, fn, h) -> bool:
    """One checklist item. True only when the check passed AND its pass was recorded."""
    started = time.monotonic()
    try:
        details = fn(h)
    except CheckFailed as failed:
        rec.result(name, "fail", kind=failed.kind, what=failed.what)
        print(f"{name}: FAIL ({failed.kind}) {failed.what}")
        return False
    except Exception as error:                  # harness error: stop, keep evidence
        rec.result(name, "error", kind="harness_defect", error=type(error).__name__,
                   where=traceback.extract_tb(error.__traceback__)[-1].lineno)
        print(f"{name}: ERROR {type(error).__name__}")
        return False
    try:
        rec.result(name, "pass", details=details, seconds=round(time.monotonic() - started, 1))
    except Exception as error:                  # a pass that cannot be recorded is not a pass
        rec.result(name, "error", kind="harness_defect", stage="record", error=type(error).__name__)
        print(f"{name}: ERROR recording {type(error).__name__}")
        return False
    print(f"{name}: pass")
    return True


def check(only: tuple[str, ...] | None = None) -> int:
    if g.pg_environment_present():
        raise CheckFailed("preparation_failure", "PG environment variables present")
    rec = g.single_run()
    h = Harness(rec)
    if not g.server_is_ours(h.pid):
        raise CheckFailed("preparation_failure", "server not ours")
    passed = 0
    try:
        h.set_password(g.READ)
        h.set_password(g.WRITE)
        rec.event("passwords_rotated_in_memory", roles=[g.READ, g.WRITE])
        rec.event("check_phase_started", checks=list(only) if only else [n for n, _ in CHECKS])
        for name, fn in CHECKS:
            if only and name not in only:
                continue
            if not run_check(rec, name, fn, h):
                return passed
            passed += 1
    finally:
        h.close()
    return passed


# --- cleanup (R2) -----------------------------------------------------------------------------------

def cleanup() -> None:
    rec = g.single_run()
    started = rec.find("server_started")
    expect(len(started) == 1, "exactly one server start recorded", "harness_defect")
    pid = started[0]["pid"]
    live = g.postmaster_pid()
    if live is not None:
        expect(live == pid and g.same_path(g.process_image(pid), g.POSTGRES_EXE)
               and g.listener_pids(g.PORT) == {pid}, "live server matches the record", "harness_defect")
        with g.admin_connect("postgres", record_pid=pid) as admin:
            for e in rec.find("database_created"):
                row = admin.execute("SELECT oid FROM pg_catalog.pg_database WHERE datname = %s", (e["name"],)).fetchone()
                expect(row is not None and row[0] == e["oid"], f"database {e['name']} OID matches", "harness_defect")
            for e in rec.find("role_created"):
                row = admin.execute("SELECT oid FROM pg_catalog.pg_roles WHERE rolname = %s", (e["name"],)).fetchone()
                if e.get("temporary"):
                    expect(row is None, f"temporary role {e['name']} already dropped", "harness_defect")
                else:
                    expect(row is not None and row[0] == e["oid"], f"role {e['name']} OID matches", "harness_defect")
        run([str(g.BIN / "pg_ctl.exe"), "stop", "-D", str(g.DATA), "-m", "fast", "-w", "-t", "60", "-s"])
    for _ in range(20):
        if g.process_image(pid) is None and not g.listener_pids(g.PORT):
            break
        time.sleep(0.5)
    expect(g.process_image(pid) is None and not g.listener_pids(g.PORT) and g.postmaster_pid() is None,
           "server stopped", "harness_defect")
    secret = [e["path"] for e in rec.find("secret_folder_created")]
    expect(all(not os.path.lexists(p) for p in secret), "secret folder already gone", "harness_defect")
    folders = rec.find("folders_created")[0]["paths"]
    expect(folders[0] == str(g.ROOT) and set(os.listdir(g.ROOT)) <= {"data", "tls", "runs"},
           "pg62 contents as recorded", "harness_defect")
    print(json.dumps({"results": [(r["check"], r["status"]) for r in rec.doc["results"]]}))
    shutil.rmtree(g.ROOT)
    expect(not g.ROOT.exists(), "pg62 removed", "harness_defect")


if __name__ == "__main__":
    phase = sys.argv[1] if len(sys.argv) == 2 else ""
    try:
        if phase == "prepare":
            prepare()
            print("prepared")
        elif phase in ("check", "check-rerun"):
            only = RERUN if phase == "check-rerun" else None
            requested = list(only or PLANNED)
            available = [n for n, _ in CHECKS if n in requested]
            passed = check(only)
            print(f"passed {passed} / {len(requested)}")
            # 0 only when every selected check ran, passed and had its pass recorded (run_check)
            if available != requested or passed != len(requested):
                print("STOP: not all selected checks passed and were recorded")
                sys.exit(1)
        elif phase == "cleanup":
            cleanup()
            print("cleaned")
        else:
            print("usage: prepare | check | check-rerun | cleanup")
            sys.exit(2)
    except CheckFailed as failed:
        print(f"STOP ({failed.kind}): {failed.what}")
        sys.exit(1)
    except pv.OpsProviderRefused as refused:
        print(f"STOP (refused): {refused.code}")
        sys.exit(1)

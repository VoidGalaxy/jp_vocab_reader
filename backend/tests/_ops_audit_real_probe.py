"""Fresh-process probe of tests/_ops_audit_real.py's `check` path (not discovered: no `test_` prefix;
run one case per process by test_ops_audit_real_guard.FreshProcess).

REAL here: the runner module, its Harness, the 5-unit pre-check with test-key signatures in a
temporary folder, the 6-1 provider / copy / observer / adapter, `_ops_audit_run`, and the app's
`read_snapshot` / `_require_snapshot`. FAKE here: the driver (psycopg.connect is replaced), the
connection and its rows, the admin helpers, and the BODY of `audit()` (swapped in by an import hook
right after the app module loads, so nothing imports app early). This proves import paths and
order only, not real audit SQL. Backend is NOT put on sys.path here: the runner must do it.
"""

from __future__ import annotations

import importlib.abc
import importlib.machinery
import json
import os
import sys
import tempfile
import shutil
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS_DIR.parent / "scripts"))
sys.path.insert(0, str(TESTS_DIR))

EVENTS: list = []
PARTIAL = {"audit_version": 1, "status": "partial",
           "checks": {**{f"I{i}": {"status": "pass", "violations": 0, "unknown": 0} for i in range(1, 6)},
                      "I6": {"status": "not_evaluated", "reason": "deletion_baseline_required"},
                      "I7": {"status": "not_evaluated", "reason": "deletion_baseline_required"}}}


class Watch(importlib.abc.MetaPathFinder):
    """Records app imports (with the environment at the first one) and swaps the audit body."""

    def find_spec(self, name, path=None, target=None):
        if name != "app" and not name.startswith("app."):
            return None
        if not any(isinstance(e, str) and e.startswith("import:") for e in EVENTS):
            EVENTS.append({"env": {k: os.environ.get(k) for k in ("APP_ENV", "DATABASE_URL", "PYTHON_DOTENV_DISABLED")}})
        EVENTS.append("import:" + name)
        if name != "app.srs.invariant_audit":
            return None
        spec = importlib.machinery.PathFinder.find_spec(name, path)
        if spec is None:
            return None
        loader = spec.loader
        real_exec = loader.exec_module

        def exec_module(module):
            real_exec(module)

            def audit(connection, *, baseline=None):            # FAKE body; the real snapshot check runs
                EVENTS.append("audit:body")
                module._require_snapshot(connection)
                return json.loads(json.dumps(PARTIAL))
            module.audit = audit
        loader.exec_module = exec_module
        return spec


sys.meta_path.insert(0, Watch())

import psycopg  # noqa: E402
from psycopg.pq import TransactionStatus  # noqa: E402

import _ops_audit_real as real  # noqa: E402
import _ops_pg62 as g  # noqa: E402
import _ops_preflight as op  # noqa: E402
import test_ops_observer as to  # noqa: E402

T = g.PG63_AUDIT
TARGET = {"run_id": "probe", "host": g.HOST, "port": T.port, "data": str(T.data), "postgres_exe": str(g.POSTGRES_EXE),
          "postmaster_pid": 4242, "server_version_num": "180006",
          "databases": {real.DB_OK: {"oid": 16386, "identity_value": "pg63-ok-probe"},
                        real.DB_BAD: {"oid": 16387, "identity_value": "pg63-bad-probe"}},
          "provider_roles": [real.AUDIT], "admin_role": T.admin}


def catalog_for(db: str) -> dict:
    """FAKE catalog shaped after the runner's fixed expected profile (fake data for the flow only)."""
    profile = real.expected_profile(db)
    cat = to.catalog()
    oid = iter(range(20000, 30000))
    rel_oid = {}
    cat["relations"] = []
    for kind, schema, name in sorted(profile.objects):
        if kind in ("table", "sequence"):
            rel_oid[(kind, schema, name)] = o = next(oid)
            cat["relations"].append((o, "r" if kind == "table" else "S", schema, name))
    cat["columns"] = {o: ["id"] for (k, _, _), o in rel_oid.items() if k == "table"}
    cat["schemas"] = [(2200, "public"), (16500, real.SYN)]
    cat["database"] = [(TARGET["databases"][db]["oid"], db)]
    schema_oid = {"public": 2200, real.SYN: 16500}
    grants = set()
    for kind, schema, name, column, privilege in profile.privileges:
        if kind == "table":
            grants.add(("relation", rel_oid[(kind, schema, name)], privilege))
        elif kind == "sequence":
            grants.add(("sequence", rel_oid[(kind, schema, name)], privilege))
        elif kind == "schema":
            grants.add(("schema", schema_oid[name], privilege))
        elif kind == "database":
            grants.add(("database", TARGET["databases"][db]["oid"], privilege))
    cat["grants"] = grants
    cat["session"].update(dbname=db, current_user_name=real.AUDIT, session_user_name=real.AUDIT,
                          search_path=real.SEARCH_PATH)
    cat["identity"] = [TARGET["databases"][db]["identity_value"]]
    return cat


class Result:
    def __init__(self, rows):
        self.rows = rows

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return list(self.rows)


class ProbeConn(to.ObsConn):
    """FAKE connection: the provider-test catalog, the guard's post-connect read, the audit
    transaction statements and the tracker's own probe reads."""

    def __init__(self, db: str):
        super().__init__(catalog_for(db))
        self.db = db
        self.info.hostaddr, self.info.host, self.info.port, self.info.dbname = "::1", g.HOST, T.port, db
        self.snapshot = None
        self.locals: dict = {}

    def execute(self, query, params=None):
        text = query if isinstance(query, str) else query.as_string(None)
        if self.snapshot is None and not text.startswith("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"):
            return super().execute(text)                       # provider observation statements
        super().execute(text)
        if text.startswith("SET TRANSACTION"):
            self.snapshot = text
        elif text.startswith("SET LOCAL"):
            name, value = text[len("SET LOCAL "):].split(" = ")
            self.locals[name] = value.strip("'")
        elif text == real.ar.RECHECK:
            return Result([{"dbname": self.db, "port": T.port, "version": "180006"}])
        elif text == real.ar.IDENTITY:
            return Result([{"identity_value": TARGET["databases"][self.db]["identity_value"]}])
        elif "current_setting('transaction_read_only') AS ro" in text:
            return Result([{"ro": "on", "isolation": "repeatable read"}])
        return Result([])

    def rollback(self):
        super().rollback()
        self.snapshot = None

    def cursor(self, row_factory=None):
        conn = self

        class Cursor:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def execute(self, query, params=None):
                if query == real.POST_CONNECT:
                    self.rows = [{"server_addr": "::1", "server_port": T.port, "version": "180006",
                                  "dbname": conn.db, "db_oid": TARGET["databases"][conn.db]["oid"]}]
                elif query == getattr(real, "PROBE_SETTINGS", None):
                    self.rows = [{"iso": "repeatable read" if conn.snapshot else "read committed", "ro": "on",
                                  "st": conn.locals.get("statement_timeout"), "lt": conn.locals.get("lock_timeout")}]
                elif query == getattr(real, "PROBE_XID", None):
                    self.rows = [{"x": None}]
                else:
                    inner = to.FakeCursor(conn)
                    inner.execute(query, params)
                    self.rows = inner.rows
                return self

            def fetchone(self):
                return self.rows[0] if self.rows else None

            def fetchall(self):
                return list(self.rows)

        return Cursor()


def setup_case():
    """Synthetic run folder and target record, patched process / admin facts, fake driver."""
    folder = Path(tempfile.mkdtemp(prefix="ops_audit_real_probe_"))
    (folder / "target.json").write_text(json.dumps(TARGET, indent=1, sort_keys=True), encoding="utf-8")
    g.single_run = lambda target=None: g.Record(folder)
    g.server_is_ours = lambda pid, target=None: pid == 4242
    g.pg_environment_present = lambda: False
    real.Harness.set_password = lambda self: setattr(self, "password", "probe-password")
    real.Harness.ca_pem = lambda self: b"-----BEGIN CERTIFICATE-----\nsynthetic probe root\n"
    real.Harness.snapshot = lambda self, db: {"users": (1, 1)}
    real.Harness.sessions = lambda self: 0
    real_preflight = op.run_synthetic_preflight

    def watched(inputs):
        try:
            result = real_preflight(inputs)
        except op.OpsPreflightRefused:
            EVENTS.append("preflight:refused")
            raise
        EVENTS.append("preflight:passed")
        return result
    op.run_synthetic_preflight = watched

    def driver(**kwargs):
        EVENTS.append("connect")
        return ProbeConn(kwargs["dbname"])
    psycopg.connect = driver                                   # the real driver is never reached
    return folder


def report(case: str, **extra):
    print("PROBE " + json.dumps({"case": case, "events": EVENTS, **extra}, default=str))


def case_check_entry():
    """The real `check` CLI path with c1 real and the CLI-comparison checks replaced by passing fakes."""
    folder = setup_case()
    ok = lambda h: {"status": "partial", "exit": 3}  # noqa: E731
    real.CHECKS = [(n, real.c1_ok_new_path if n == "c1_ok_new_path" else ok) for n in real.PLANNED]
    try:
        code = real.main(["check"])
        record = json.loads((folder / "record.json").read_text(encoding="utf-8"))
        report("check_entry", code=code, results=[(r["check"], r["status"], r.get("details")) for r in record["results"]])
    finally:
        shutil.rmtree(folder, ignore_errors=True)


def case_bad(signature: bool):
    folder = setup_case()
    h = real.Harness(g.Record(folder))
    try:
        inputs = h.inputs()
        if signature:
            inputs = inputs.__class__(**{**inputs.__dict__, "approval_signature": b"bad"})
        else:
            inputs = inputs.__class__(**{**inputs.__dict__, "manifest_signature": b"bad"})
        out, code, probe = h.audit(inputs)
    finally:
        h.close()
        shutil.rmtree(folder, ignore_errors=True)
    report("bad_signature" if signature else "bad_manifest", code=code, reason=out.get("reason"), probe=probe)


if __name__ == "__main__":
    {"check_entry": case_check_entry, "bad_signature": lambda: case_bad(True),
     "bad_manifest": lambda: case_bad(False)}[sys.argv[1]]()

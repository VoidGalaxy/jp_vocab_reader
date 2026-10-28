"""Connection provider unit 6-1c (scripts/_ops_observer.py): the observation SQL collector, with
FAKE connections and FAKE cursors.

The fake cursor answers each of the module's own queries with prepared synthetic rows. It checks
the conversion and call contract only: it does not run the SQL, and its rows do not prove what
`has_*_privilege`, `aclexplode`, the recursive membership query or the ownership counts return on a
real server (contract 10절 real-PG list). No database, no real connection (psycopg / libpq connect
entry points stay patched to fail).

Run directly:      python tests/test_ops_observer.py
Or via discovery:   python -m unittest discover -s tests
"""

from __future__ import annotations

import copy
import re
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

TESTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS_DIR.parent / "scripts"))
sys.path.insert(0, str(TESTS_DIR))

import psycopg  # noqa: E402
from psycopg import errors as pg_errors  # noqa: E402
from psycopg import sql  # noqa: E402
from psycopg.pq import TransactionStatus  # noqa: E402
from psycopg.rows import dict_row  # noqa: E402

import _ops_observer as ob  # noqa: E402
import _ops_provider as pv  # noqa: E402
import test_ops_preflight as pf  # noqa: E402  (module only: its tests are not re-run here)
import test_ops_provider as pt  # noqa: E402  (module only: its tests are not re-run here)

SECRET = pf.SECRET
T = pf.TARGET
SYN = ob.IDENTITY_SCHEMA
OBJECTS = frozenset({("database", "", T.database), ("schema", "", "public"), ("schema", "", SYN),
                     ("table", "public", "users"), ("table", "public", "vocab_items"), ("table", SYN, "db_identity"),
                     ("sequence", "public", "vocab_items_id_seq"), ("tablespace", "", "pg_default"),
                     ("tablespace", "", "pg_global")})
READ_PRIVS = frozenset({("database", "", T.database, "", "CONNECT"), ("schema", "", "public", "", "USAGE"),
                        ("schema", "", SYN, "", "USAGE"), ("table", "public", "users", "", "SELECT"),
                        ("table", "public", "vocab_items", "", "SELECT"), ("table", SYN, "db_identity", "", "SELECT")})
WRITE_PRIVS = READ_PRIVS | {("table", "public", "vocab_items", "", "UPDATE"),
                            ("sequence", "public", "vocab_items_id_seq", "", "USAGE")}
READ_EXPECTED = pv.ExpectedProfile(OBJECTS, READ_PRIVS, "public, pg_catalog", frozenset({"TLSv1.3"}))
WRITE_EXPECTED = pv.ExpectedProfile(OBJECTS, WRITE_PRIVS, "public, pg_catalog", frozenset({"TLSv1.3"}))
REL_PARAMS = {"relkinds": ["r", "p", "v", "m", "f"]}
QUERY_ORDER = ("session", "role", "memberships", "ownership", "tls", "identity", "relations", "relation_privileges",
               "column_counts", "columns",
               "column_privileges", "sequence_privileges", "schemas", "schema_privileges", "database",
               "database_privileges", "tablespaces", "tablespace_privileges", "routines", "routine_privileges",
               "default_acls", "default_acl_privileges", "parameter_acls", "parameter_privileges", "large_objects",
               "large_object_privileges")


def catalog(access="read") -> dict:
    """A synthetic catalog. `grants` are what has_*_privilege would say true for (FAKE)."""
    grants = {("database", 16384, "CONNECT"), ("schema", 2200, "USAGE"), ("schema", 16400, "USAGE"),
              ("relation", 16385, "SELECT"), ("relation", 16386, "SELECT"), ("relation", 16401, "SELECT")}
    if access == "write":
        grants |= {("relation", 16385, "UPDATE"), ("sequence", 16388, "USAGE")}
    return {
        "session": {"dbname": T.database, "server_version_num": f"{T.server_major}0006",
                    "current_user_name": "ops_read" if access == "read" else "ops_write_prb",
                    "session_user_name": "ops_read" if access == "read" else "ops_write_prb",
                    "search_path": "public, pg_catalog", "default_read_only": "on" if access == "read" else "off",
                    "default_isolation": "read committed", "transaction_read_only": "on",
                    "lo_compat_privileges": "off"},
        "role": {k: k == "inherit" for k in pv.ROLE_ATTRIBUTES},
        "memberships": [],
        "ownership": {alias: 0 for _, _, alias in ob._OWNERSHIP},
        "tls": {"ssl": True, "version": "TLSv1.3"},
        "identity": [T.identity_value],
        "relations": [(16385, "r", "public", "vocab_items"), (16386, "r", "public", "users"),
                      (16387, "i", "public", "users_pkey"), (16388, "S", "public", "vocab_items_id_seq"),
                      (16401, "r", SYN, "db_identity")],
        "columns": {16385: ["id", "word"], 16386: ["id", "email"], 16401: ["identity_value"]},
        "schemas": [(2200, "public"), (16400, SYN)],
        "database": [(16384, T.database)],
        "tablespaces": [(1663, "pg_default"), (1664, "pg_global")],
        "routines": [],
        "default_acls": [],
        "default_acl_grants": [],
        "parameter_acls": [],
        "large_objects": [],
        "large_object_grants": [],
        "grants": grants,
        "override": {},          # query name -> rows or an exception, replacing the generated answer
    }


def answer(cat: dict, name: str, params) -> list[dict]:
    """What the FAKE cursor returns for one of the module's queries. Privilege rows follow the
    requested privilege list and relkinds, as the real SQL would shape them."""
    grants = cat["grants"]
    privileges = list(params.get("privileges", [])) if params else []
    relkinds = set(params.get("relkinds", [])) if params else set()

    def granted(scope, oid, privilege):
        return (scope, oid, privilege) in grants

    if name == "session":
        return [dict(cat["session"])]
    if name == "role":
        return [dict(cat["role"])]
    if name == "memberships":
        return [{"role_name": r} for r in cat["memberships"]]
    if name == "ownership":
        return [dict(cat["ownership"])]
    if name == "tls":
        return [dict(cat["tls"])]
    if name == "identity":
        return [{"identity_value": v} for v in cat["identity"][:params["limit"]]]
    if name == "relations":
        return [{"oid": o, "relkind": k, "schema_name": s, "object_name": n} for o, k, s, n in cat["relations"]]
    if name in ("relation_privileges", "sequence_privileges"):
        scope = "relation" if name == "relation_privileges" else "sequence"
        return [{"oid": o, "privilege": p, "granted": granted(scope, o, p)}
                for o, k, _, _ in cat["relations"] if k in relkinds for p in privileges]
    if name == "column_privileges":
        return [{"oid": o, "column_name": c, "privilege": p,
                 "granted": granted("relation", o, p) or ("column", (o, c), p) in grants}
                for o, k, _, _ in cat["relations"] if k in relkinds for c in cat["columns"].get(o, []) for p in privileges]
    if name == "column_counts":        # independent of the privilege response (6-1c column fix)
        return [{"oid": o, "column_count": len(cat["columns"].get(o, []))}
                for o, k, _, _ in cat["relations"] if k in relkinds]
    if name == "columns":
        return [{"oid": o, "column_name": c} for o, k, _, _ in cat["relations"] if k in relkinds
                for c in cat["columns"].get(o, [])]
    simple = {"schemas": "schemas", "database": "database", "tablespaces": "tablespaces",
              "parameter_acls": "parameter_acls"}
    if name in simple:
        return [{"oid": o, "object_name": n} for o, n in cat[simple[name]]]
    scoped = {"schema_privileges": ("schema", "schemas"), "database_privileges": ("database", "database"),
              "tablespace_privileges": ("tablespace", "tablespaces"),
              "parameter_privileges": ("parameter", "parameter_acls")}
    if name in scoped:
        scope, source = scoped[name]
        return [{"oid": o, "privilege": p, "granted": granted(scope, o, p)} for o, _ in cat[source] for p in privileges]
    if name == "routines":
        return [{"oid": o, "schema_name": s, "object_name": n, "identity_arguments": a} for o, s, n, a in cat["routines"]]
    if name == "routine_privileges":
        return [{"oid": o, "privilege": p, "granted": granted("routine", o, p)} for o, *_ in cat["routines"]
                for p in privileges]
    if name == "default_acls":
        return [{"oid": o, "role_name": r, "namespace_oid": ns, "schema_name": s, "object_type": t}
                for o, r, ns, s, t in cat["default_acls"]]
    if name == "default_acl_privileges":
        return [{"oid": o, "privilege": p} for o, p in cat["default_acl_grants"]]
    if name == "large_objects":
        return [{"oid": o} for o in cat["large_objects"]]
    if name == "large_object_privileges":
        return [{"oid": o, "privilege": p} for o, p in cat["large_object_grants"]]
    raise AssertionError(f"no fake answer for {name}")


class FakeCursor:
    """FAKE: maps the executed query back to the module's own query by equality, never parses SQL."""

    def __init__(self, conn):
        self.conn = conn
        self.rows = None
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.closed = True

    def execute(self, query, params=None):
        names = [n for n, q in ob.QUERIES.items() if q == query]
        if len(names) != 1 or not isinstance(query, sql.Composable):
            raise AssertionError("a query that is not one of the module's own was executed")
        name = names[0]
        self.conn.queries.append((name, params))
        result = self.conn.catalog["override"].get(name)
        if isinstance(result, BaseException):
            raise result
        self.rows = copy.deepcopy(result) if result is not None else answer(self.conn.catalog, name, params)

    def fetchall(self):
        return self.rows


class ObsInfo(pt.FakeInfo):
    host, port, dbname = T.host, T.port, T.database

    @property
    def server_version(self):
        return self._conn.server_version


class ObsConn(pt.FakeConn):
    """FAKE: provider-test connection plus the driver info and cursor the collector reads."""

    def __init__(self, cat=None, *, ssl_in_use=True, server_version=None, **kwargs):
        super().__init__(**kwargs)
        self.catalog = cat if cat is not None else catalog()
        self.info = ObsInfo(self)
        self.server_version = server_version if server_version is not None else T.server_major * 10000 + 6
        self.pgconn = SimpleNamespace(ssl_in_use=ssl_in_use)
        self.queries: list = []
        self.cursors: list = []
        self.commits = 0

    def cursor(self, row_factory=None):
        if row_factory is not dict_row:
            raise AssertionError("rows must be read by column name")
        cursor = FakeCursor(self)
        self.cursors.append(cursor)
        return cursor

    def commit(self):
        self.commits += 1
        self.log.append("COMMIT")


def in_transaction(conn: ObsConn) -> ObsConn:
    for statement in pv.OBSERVATION_START:          # what the provider has run before the observer
        conn.execute(statement)
    return conn


class NoConnect(unittest.TestCase):
    def setUp(self):
        def forbidden(*_, **__):
            raise AssertionError("a connection function was called")

        for patch in (mock.patch.object(psycopg, "connect", forbidden),
                      mock.patch.object(psycopg.Connection, "connect", forbidden)):
            patch.start()
            self.addCleanup(patch.stop)

    def observe(self, cat=None, **kwargs) -> pv.Observation:
        return ob.CatalogObserver().observe(in_transaction(ObsConn(cat, **kwargs)))

    def code(self, expected, cat=None, **kwargs):
        with self.assertRaises(pv.OpsProviderRefused) as caught:
            self.observe(cat, **kwargs)
        error = caught.exception
        self.assertEqual(error.code, expected)
        self.assertTrue(error.__suppress_context__ or error.__context__ is None)
        text = repr(error) + str(error) + repr(error.also)
        for leak in (SECRET, "SELECT", "pg_catalog"):
            self.assertNotIn(leak, text)
        return error

    def unresolved(self, cat) -> tuple[str, ...]:
        return self.observe(cat).unresolved


def changed(access="read", **changes) -> dict:
    cat = catalog(access)
    for key, value in changes.items():
        if key in cat["session"]:
            cat["session"][key] = value
        else:
            cat[key] = value
    return cat


class Collect(NoConnect):
    """FAKE cursor: conversion of prepared rows into the 6-1a Observation."""

    def test_read_observation(self):
        conn = in_transaction(ObsConn())
        o = ob.CatalogObserver().observe(conn)
        self.assertIs(pv._check_observation(o), o)
        self.assertEqual((o.host, o.port, o.dbname, o.server_major, o.identity_value),
                         (T.host, T.port, T.database, T.server_major, T.identity_value))
        self.assertEqual((o.current_user, o.session_user, o.memberships, o.owned_count), ("ops_read", "ops_read", (), 0))
        self.assertEqual(o.role_attributes, tuple((k, k == "inherit") for k in pv.ROLE_ATTRIBUTES))
        self.assertEqual(frozenset(o.objects), OBJECTS)            # index excluded, no-privilege objects kept
        self.assertEqual(frozenset(o.privileges), READ_PRIVS)      # column rows implied by table grants folded
        self.assertEqual((o.observation_read_only, o.default_read_only, o.default_isolation), (True, True, "read committed"))
        self.assertEqual((o.tls_in_use, o.tls_server_ssl, o.tls_version, o.unresolved), (True, True, "TLSv1.3", ()))

    def test_write_observation_keeps_business_default_separate(self):
        o = self.observe(catalog("write"))
        self.assertEqual((o.observation_read_only, o.default_read_only), (True, False))
        self.assertEqual(frozenset(o.privileges), WRITE_PRIVS)
        o = self.observe(changed("write", transaction_read_only="off"))
        self.assertEqual((o.observation_read_only, o.default_read_only), (False, False))   # provider refuses this

    def test_only_own_queries_and_no_lifecycle_calls(self):
        conn = in_transaction(ObsConn())
        before = list(conn.log)
        ob.CatalogObserver().observe(conn)
        self.assertEqual([n for n, _ in conn.queries], list(QUERY_ORDER))
        for name, params in conn.queries:
            self.assertIs(params, ob.PARAMS.get(name))             # bound values are the module's constants
        self.assertEqual(conn.log, before)                         # no execute / commit / rollback on the connection
        self.assertEqual((conn.commits, conn.close_calls, conn.closed, conn.status), (0, 0, False, TransactionStatus.INTRANS))
        self.assertTrue(all(c.closed for c in conn.cursors) and len(conn.cursors) == 1)
        identifiers = [part for part in ob.QUERIES["identity"] if isinstance(part, sql.Identifier)]
        self.assertEqual(len(identifiers), 3)
        self.assertEqual(ob.PARAMS["relation_privileges"]["privileges"], list(ob.RELATION_PRIVILEGES))

    def test_not_in_transaction(self):
        conn = ObsConn()
        with self.assertRaises(pv.OpsProviderRefused) as caught:
            ob.CatalogObserver().observe(conn)
        self.assertEqual(caught.exception.code, "observation_not_in_transaction")
        self.assertEqual(conn.cursors, [])

    def test_objects_and_privileges(self):
        cat = catalog()
        cat["relations"].append((16500, "r", "public", "new_table"))           # no privileges at all
        cat["columns"][16500] = ["a"]
        cat["grants"] |= {("relation", 16386, "UPDATE"), ("column", (16385, "word"), "UPDATE"),
                          ("schema", 2200, "CREATE"), ("database", 16384, "TEMPORARY"), ("tablespace", 1663, "CREATE"),
                          ("sequence", 16388, "SELECT")}
        cat["grants"] -= {("relation", 16401, "SELECT")}
        o = self.observe(cat)
        self.assertIn(("table", "public", "new_table"), o.objects)
        privileges = frozenset(o.privileges)
        self.assertEqual(privileges - READ_PRIVS, {
            ("table", "public", "users", "", "UPDATE"), ("table", "public", "vocab_items", "word", "UPDATE"),
            ("schema", "", "public", "", "CREATE"), ("database", "", T.database, "", "TEMPORARY"),
            ("tablespace", "", "pg_default", "", "CREATE"), ("sequence", "public", "vocab_items_id_seq", "", "SELECT")})
        self.assertEqual(READ_PRIVS - privileges, {("table", SYN, "db_identity", "", "SELECT")})
        self.assertNotIn(("table", "public", "users", "email", "UPDATE"), privileges)   # table-level, not column excess

    def test_acl_rows_public_inherited_routines_parameters(self):
        """Rows the SQL would return for PUBLIC / inherited grants (the SQL filter itself is not run)."""
        cat = catalog()
        cat["default_acls"] = [(20001, "owner_role", 2200, "public", "r"), (20002, "owner_role", 0, None, "f")]
        cat["default_acl_grants"] = [(20001, "INSERT"), (20002, "EXECUTE")]
        cat["large_objects"] = [30001]
        cat["large_object_grants"] = [(30001, "SELECT")]
        cat["routines"] = [(40001, "public", "fn", "x integer"), (40002, "public", "fn", "x text")]   # overloads
        cat["grants"] |= {("routine", 40002, "EXECUTE"), ("parameter", 50001, "ALTER SYSTEM")}
        cat["parameter_acls"] = [(50001, "log_statement")]
        cat["memberships"] = ["pg_write_all_data", "app_writer"]
        cat["ownership"].update(types=1, default_acls=2)
        o = self.observe(cat)
        privileges = frozenset(o.privileges)
        routines = sorted(k for k in o.objects if k[0] == "security_definer_routine")
        self.assertEqual(len(routines), 2)
        self.assertTrue(all(re.fullmatch(r"fn\$[0-9a-f]{16}", k[2]) for k in routines))
        self.assertTrue({("default_acl", "public", "owner_role.tables", "", "INSERT"),
                         ("default_acl", "", "owner_role.functions", "", "EXECUTE"),
                         ("large_object", "", "30001", "", "SELECT"),
                         ("parameter_acl", "", "log_statement", "", "ALTER_SYSTEM")} <= privileges)
        self.assertEqual(sum(1 for p in privileges if p[0] == "security_definer_routine"), 1)
        self.assertEqual((o.memberships, o.owned_count, o.unresolved), (("app_writer", "pg_write_all_data"), 3, ()))

    def test_null_type_shape_duplicates(self):
        role_none = {k: None if k == "createdb" else False for k in pv.ROLE_ATTRIBUTES}
        cases = [
            changed(current_user_name=None), changed(default_read_only="true"), changed(default_isolation="snapshot"),
            changed(server_version_num="18x06"), changed(server_version_num=180006),
            changed(role=role_none), changed(memberships=["a", "a"]), changed(memberships=["bad\nname"]),
            changed(ownership={**catalog()["ownership"], "routines": None}),
            changed(ownership={**catalog()["ownership"], "routines": -1}),
            changed(tls={"ssl": True, "version": None}), changed(tls={"ssl": "t", "version": "TLSv1.3"}),
            changed(identity=[None]), changed(identity=[7]),
        ]
        override_cases = {
            "role": [[], [catalog()["role"]] * 2],
            "session": [[{**catalog()["session"], "extra": 1}], [{k: v for k, v in catalog()["session"].items() if k != "search_path"}]],
            "relations": [[{"oid": "16385", "relkind": "r", "schema_name": "public", "object_name": "x"}],
                          [{"oid": 16385, "relkind": "r", "schema_name": "public", "object_name": "x"}] * 2],
            "relation_privileges": [answer(catalog(), "relation_privileges", ob.PARAMS["relation_privileges"]) * 2,
                                    [{"oid": 16385, "privilege": "SELECT", "granted": "t"}],
                                    [{"oid": 16385, "privilege": "CONNECT", "granted": True}]],
            "database": [[], [{"oid": 1, "object_name": "a"}, {"oid": 2, "object_name": "b"}]],
            "default_acl_privileges": [[{"oid": 1, "privilege": "INSERT"}] * 2],
            "fetch": [None],
        }
        for index, cat in enumerate(cases):
            with self.subTest(case=index):
                self.code("observation_invalid", cat)
        for name, rows_list in override_cases.items():
            for rows in rows_list:
                with self.subTest(query=name):
                    cat = catalog()
                    cat["override"]["session" if name == "fetch" else name] = rows if name != "fetch" else "not a list"
                    self.code("observation_invalid", cat)

    def test_driver_and_version(self):
        self.code("observation_driver_mismatch", server_version=170004)
        cat = catalog()
        cat["session"]["dbname"] = "jp_vocab_copy"
        self.code("observation_driver_mismatch", cat)
        cat = changed(server_version_num="160004")
        self.code("observation_server_unsupported", cat, server_version=160004)
        self.code("observation_invalid", ssl_in_use=1)
        o = self.observe(changed(tls={"ssl": False, "version": None}), ssl_in_use=False)
        self.assertEqual((o.tls_in_use, o.tls_server_ssl, o.tls_version), (False, False, "none"))

    def test_identity_rows(self):
        self.code("observation_identity_rows", changed(identity=[]))
        self.code("observation_identity_rows", changed(identity=[T.identity_value, "second-row"]))
        for error in (pg_errors.UndefinedTable(SECRET), pg_errors.InvalidSchemaName(SECRET),
                      pg_errors.UndefinedColumn(SECRET)):
            cat = catalog()
            cat["override"]["identity"] = error
            self.code("observation_identity_missing", cat)

    def test_unresolved_is_kept_not_dropped(self):
        def with_(mutate):
            cat = catalog()
            mutate(cat)
            return cat

        cases = {
            "relkind_unknown": lambda c: c["relations"].append((16600, "x", "public", "odd")),
            "privilege_object_unknown": lambda c: c["override"].__setitem__("relation_privileges", answer(
                c, "relation_privileges", ob.PARAMS["relation_privileges"]) + [
                {"oid": 99999, "privilege": "SELECT", "granted": True}]),
            "privilege_rows_incomplete": lambda c: c["override"].__setitem__("relation_privileges", answer(
                c, "relation_privileges", ob.PARAMS["relation_privileges"])[1:]),
            "privilege_check_null": lambda c: c["override"].__setitem__("schema_privileges", [
                {"oid": 2200, "privilege": "USAGE", "granted": None}, {"oid": 2200, "privilege": "CREATE", "granted": False},
                {"oid": 16400, "privilege": "USAGE", "granted": True}, {"oid": 16400, "privilege": "CREATE", "granted": False}]),
            "object_name_unrepresentable": lambda c: c["relations"].append((16601, "r", "public", "has space")),
            "object_identity_collision": lambda c: c.__setitem__("routines", [(40001, "public", "fn", "x integer"),
                                                                              (40002, "public", "fn", "x integer")]),
            "default_acl_unresolved": lambda c: c.__setitem__("default_acls", [(20001, None, 0, None, "r")]),
            "acl_privilege_unknown": lambda c: (c.__setitem__("large_objects", [30001]),
                                                c.__setitem__("large_object_grants", [(30001, "DELETE")])),
            "large_object_compat_privileges": lambda c: c["session"].__setitem__("lo_compat_privileges", "on"),
        }
        for code, mutate in cases.items():
            with self.subTest(code=code):
                self.assertIn(code, self.unresolved(with_(mutate)))
        # an incomplete column set is unresolved too
        cat = catalog()
        rows = answer(cat, "column_privileges", ob.PARAMS["column_privileges"])
        cat["override"]["column_privileges"] = [r for r in rows if not (r["column_name"] == "email" and r["privilege"] == "INSERT")]
        self.assertIn("privilege_rows_incomplete", self.unresolved(cat))
        # a privilege on an unrepresentable object never appears under another identity
        cat = with_(cases["object_name_unrepresentable"])
        cat["grants"].add(("relation", 16601, "UPDATE"))
        self.assertFalse(any(p[2] == "has space" or p[4] == "UPDATE" for p in self.observe(cat).privileges))

    def test_driver_errors_propagate(self):
        for error in (pg_errors.QueryCanceled(SECRET), pg_errors.LockNotAvailable(SECRET),
                      pg_errors.InsufficientPrivilege(SECRET)):
            cat = catalog()
            cat["override"]["column_privileges"] = error
            with self.assertRaises(type(error)):
                self.observe(cat)

    def test_module_static_rules(self):
        source = (TESTS_DIR.parent / "scripts" / "_ops_observer.py").read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"psycopg\.connect|\.connect\(|\.commit\(|\.rollback\(|\.close\(|connection\.execute",
                                    source))
        for forbidden in ("import_module", "__import__", "exec(", "eval(", "os.environ", "getenv", "subprocess",
                          "from app", "import app", "socket"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)
        self.assertEqual(len(re.findall(r"\.execute\(", source)), 1)       # only the module's own query table
        for name, text in ob._TEXT.items():
            with self.subTest(query=name):
                bare = re.sub(r"OPERATOR\(pg_catalog\.[=<>~]+\)", "", text)
                bare = re.sub(r"%\(\w+\)s", "", bare)
                self.assertIsNone(re.search(r"[=<>~!]", bare))                     # operators all qualified
                self.assertIsNone(re.search(r"(?<![.\w])pg_(?!catalog\.)\w+", bare))  # catalogs all qualified
                calls = re.findall(r"(?<![\w.\"])([A-Za-z_][\w]*)\(", bare)
                self.assertEqual([c for c in calls if c not in ("OPERATOR", "COALESCE")], [])
                self.assertNotIn("'", text)                                        # no literal values: all bound


def without_column_rows(cat: dict, drop) -> dict:
    """Override the column privilege response, dropping the rows `drop(row)` selects."""
    rows = answer(cat, "column_privileges", ob.PARAMS["column_privileges"])
    cat["override"]["column_privileges"] = [r for r in rows if not drop(r)]
    return cat


def email_update_catalog() -> dict:
    cat = catalog()
    cat["grants"].add(("column", (16386, "email"), "UPDATE"))        # column-only excess grant
    return cat


class ColumnCompleteness(NoConnect):
    """6-1c fix: the expected column set comes from queries independent of the privilege response.
    FAKE cursor rows only; the real SQL is not run."""

    def test_whole_column_missing(self):
        o = self.observe(without_column_rows(email_update_catalog(), lambda r: r["column_name"] == "email"))
        self.assertIn("privilege_rows_incomplete", o.unresolved)
        self.assertNotIn(("table", "public", "users", "email", "UPDATE"), o.privileges)

    def test_whole_relation_columns_missing(self):
        o = self.observe(without_column_rows(email_update_catalog(), lambda r: r["oid"] == 16386))
        self.assertIn("privilege_rows_incomplete", o.unresolved)

    def test_one_privilege_kind_missing(self):
        o = self.observe(without_column_rows(email_update_catalog(),
                                             lambda r: r["column_name"] == "email" and r["privilege"] == "INSERT"))
        self.assertIn("privilege_rows_incomplete", o.unresolved)

    def test_unexpected_column_in_privilege_response(self):
        cat = catalog()
        rows = answer(cat, "column_privileges", ob.PARAMS["column_privileges"])
        cat["override"]["column_privileges"] = rows + [{"oid": 16386, "column_name": "ghost", "privilege": p,
                                                        "granted": False} for p in ob.COLUMN_PRIVILEGES]
        self.assertIn("column_unexpected", self.unresolved(cat))

    def test_list_and_privileges_disagree(self):
        # a column added after the list (privileges see it) / dropped after the list (privileges miss it)
        cat = catalog()
        cat["override"]["columns"] = [r for r in answer(cat, "columns", REL_PARAMS) if r["column_name"] != "email"]
        cat["override"]["column_counts"] = [{**r, "column_count": 1} if r["oid"] == 16386 else r
                                            for r in answer(cat, "column_counts", REL_PARAMS)]
        self.assertIn("column_unexpected", self.unresolved(cat))
        cat = catalog()
        cat["override"]["columns"] = answer(cat, "columns", REL_PARAMS) + [{"oid": 16386, "column_name": "phone"}]
        cat["override"]["column_counts"] = [{**r, "column_count": 3} if r["oid"] == 16386 else r
                                            for r in answer(cat, "column_counts", REL_PARAMS)]
        self.assertIn("privilege_rows_incomplete", self.unresolved(cat))

    def test_count_and_list_disagree(self):
        cases = {
            "count_higher": lambda c: [{**r, "column_count": 3} if r["oid"] == 16386 else r
                                       for r in answer(c, "column_counts", REL_PARAMS)],
            "relation_missing": lambda c: [r for r in answer(c, "column_counts", REL_PARAMS)
                                           if r["oid"] != 16386],
            "relation_unknown": lambda c: answer(c, "column_counts", REL_PARAMS) + [
                {"oid": 99999, "column_count": 0}],
        }
        for case, rows in cases.items():
            with self.subTest(case=case):
                cat = catalog()
                cat["override"]["column_counts"] = rows(cat)
                self.assertIn("column_list_mismatch", self.unresolved(cat))
        cat = catalog()
        cat["override"]["columns"] = answer(cat, "columns", REL_PARAMS) + [{"oid": 99999, "column_name": "x"}]
        self.assertIn("column_list_mismatch", self.unresolved(cat))

    def test_zero_column_relation_is_normal_only_when_stated(self):
        cat = catalog()
        cat["relations"].append((16700, "v", "public", "empty_view"))
        o = self.observe(cat)
        self.assertEqual(o.unresolved, ())
        self.assertIn(("view", "public", "empty_view"), o.objects)
        cat["override"]["column_counts"] = [r for r in answer(cat, "column_counts", REL_PARAMS)
                                            if r["oid"] != 16700]         # no statement for it: not assumed 0
        self.assertIn("column_list_mismatch", self.unresolved(cat))

    def test_shape_null_duplicates(self):
        base = catalog()
        cols = answer(base, "columns", REL_PARAMS)
        counts = answer(base, "column_counts", REL_PARAMS)
        privs = answer(base, "column_privileges", ob.PARAMS["column_privileges"])
        invalid = {
            "columns": [cols + cols[:1], cols[:-1] + [{**cols[-1], "column_name": None}],
                        cols[:-1] + [{**cols[-1], "column_name": 5}], cols[:-1] + [{**cols[-1], "oid": "16401"}]],
            "column_counts": [counts + counts[:1], [{**counts[0], "column_count": None}] + counts[1:],
                              [{**counts[0], "column_count": "2"}] + counts[1:], [{**counts[0], "column_count": -1}] + counts[1:]],
            "column_privileges": [privs + privs[:1], privs[:-1] + [{**privs[-1], "column_name": None}],
                                  privs[:-1] + [{**privs[-1], "granted": "t"}]],
        }
        for name, cases in invalid.items():
            for index, rows in enumerate(cases):
                with self.subTest(query=name, case=index):
                    cat = catalog()
                    cat["override"][name] = rows
                    self.code("observation_invalid", cat)
        cat = catalog()
        cat["override"]["column_privileges"] = privs[:-1] + [{**privs[-1], "granted": None}]
        self.assertIn("privilege_check_null", self.unresolved(cat))

    def test_table_level_and_column_excess_stay_distinct(self):
        o = self.observe(email_update_catalog())
        privileges = frozenset(o.privileges)
        self.assertEqual(privileges - READ_PRIVS, {("table", "public", "users", "email", "UPDATE")})
        self.assertFalse(any(p[3] and p[4] == "SELECT" for p in privileges))     # implied by table SELECT, folded
        self.assertEqual(o.unresolved, ())


class WithProvider(pt.Base):
    """The real unit 5 pre-check and 6-1a provider, with the collector on FAKE connections."""

    def read_profile(self):
        return pv.expected_profile_fingerprint(READ_EXPECTED, role="ops_read", access="read")

    def write_profile(self):
        return pv.expected_profile_fingerprint(WRITE_EXPECTED, role="ops_write_prb", access="write")

    def run_provider(self, inputs, conn, expected=READ_EXPECTED):
        return pv.provide_synthetic_connection(inputs, expected=expected, factory=pt.FakeFactory(conn),
                                               observer=ob.CatalogObserver())

    def refused_with(self, code, conn, *, inputs=None, expected=READ_EXPECTED):
        with self.assertRaises(pv.OpsProviderRefused) as caught:
            self.run_provider(inputs or self.read_inputs(), conn, expected)
        error = caught.exception
        self.assertEqual(error.code, code)
        self.assertNotIn(SECRET, repr(error) + str(error) + repr(error.also))
        self.assertTrue(conn.closed)
        return error

    def test_read_and_write_handover(self):
        conn = ObsConn()
        handoff = self.run_provider(self.read_inputs(), conn)
        self.assertEqual(conn.log, list(pv.OBSERVATION_START) + ["ROLLBACK"])   # collector sent nothing on the connection
        self.assertEqual((conn.commits, conn.close_calls), (0, 0))
        handoff.take().execute(pt.BUSINESS_FIRST)
        conn = ObsConn(catalog("write"))
        handoff = self.run_provider(self.write_inputs(), conn, WRITE_EXPECTED)
        self.assertEqual(handoff.summary.access, "write")
        handoff.take().execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED")

    def test_provider_judges_collected_values(self):
        def cat_with(mutate, access="read"):
            cat = catalog(access)
            mutate(cat)
            return cat

        cases = [
            ("observed_ownership", cat_with(lambda c: c["ownership"].update(relations=1))),
            ("observed_memberships", cat_with(lambda c: c.__setitem__("memberships", ["pg_write_all_data"]))),
            ("observed_privileges_excess", cat_with(lambda c: c["grants"].add(("column", (16386, "email"), "UPDATE")))),
            ("observed_privileges_missing", cat_with(lambda c: c["grants"].discard(("relation", 16386, "SELECT")))),
            ("observed_objects_mismatch", cat_with(lambda c: c["relations"].append((16500, "r", "public", "new_table")))),
            ("privilege_scope_unknown", cat_with(lambda c: c["relations"].append((16600, "x", "public", "odd")))),
            ("observed_identity_mismatch", cat_with(lambda c: c.__setitem__("identity", ["restored-copy"]))),
            ("observed_tls_not_in_use", cat_with(lambda c: c.__setitem__("tls", {"ssl": True, "version": "TLSv1.2"}))),
            ("observation_not_read_only", cat_with(lambda c: c["session"].update(transaction_read_only="off"))),
            ("observed_business_defaults_mismatch", cat_with(lambda c: c["session"].update(default_read_only="off"))),
            ("observed_search_path_mismatch", cat_with(lambda c: c["session"].update(search_path="evil, public"))),
            ("observation_identity_rows", cat_with(lambda c: c.__setitem__("identity", []))),
            ("observation_invalid", cat_with(lambda c: c["session"].update(current_user_name=None))),
        ]
        for code, cat in cases:
            with self.subTest(code=code):
                conn = ObsConn(cat)
                self.refused_with(code, conn)
                self.assertEqual(conn.log[-1], "ROLLBACK")

    def test_driver_errors_become_fixed_codes(self):
        for error, code in ((pg_errors.QueryCanceled(SECRET), "observation_timeout"),
                            (pg_errors.LockNotAvailable(SECRET), "observation_lock_timeout"),
                            (pg_errors.InsufficientPrivilege(SECRET), "observation_failed"),
                            (pg_errors.UndefinedTable(SECRET), "observation_identity_missing")):
            with self.subTest(code=code):
                cat = catalog()
                cat["override"]["identity" if code == "observation_identity_missing" else "ownership"] = error
                self.refused_with(code, ObsConn(cat))

    def test_failed_connection_is_not_handed_over_even_if_close_fails(self):
        conn = ObsConn(catalog(), close_error=OSError(5, SECRET))
        conn.catalog["ownership"]["schemas"] = 1
        with self.assertRaises(pv.OpsProviderRefused) as caught:
            self.run_provider(self.read_inputs(), conn)
        self.assertEqual((caught.exception.code, caught.exception.also),
                         ("connection_close_unconfirmed", ("observed_ownership",)))

    def test_column_rows_missing_is_refused_not_handed_over(self):
        cases = {
            "whole_column": without_column_rows(email_update_catalog(), lambda r: r["column_name"] == "email"),
            "whole_relation": without_column_rows(email_update_catalog(), lambda r: r["oid"] == 16386),
            "one_kind": without_column_rows(email_update_catalog(),
                                            lambda r: r["column_name"] == "email" and r["privilege"] == "INSERT"),
        }
        unexpected = catalog()
        unexpected["override"]["column_privileges"] = answer(
            unexpected, "column_privileges", ob.PARAMS["column_privileges"]) + [
            {"oid": 16386, "column_name": "ghost", "privilege": p, "granted": False} for p in ob.COLUMN_PRIVILEGES]
        cases["unexpected_column"] = unexpected
        counts = catalog()
        counts["override"]["column_counts"] = [r for r in answer(counts, "column_counts", REL_PARAMS)
                                               if r["oid"] != 16386]
        cases["count_missing"] = counts
        for case, cat in cases.items():
            with self.subTest(case=case):
                conn = ObsConn(cat)
                self.refused_with("privilege_scope_unknown", conn)
                self.assertEqual(conn.log[-1], "ROLLBACK")
                self.assertEqual((conn.close_calls, conn.commits), (1, 0))
        conn = ObsConn(email_update_catalog())                      # unchanged response: still the excess
        self.refused_with("observed_privileges_excess", conn)
        dup = catalog()
        dup["override"]["columns"] = answer(dup, "columns", REL_PARAMS) * 2
        self.refused_with("observation_invalid", ObsConn(dup))

    def test_default_entry_point_still_refuses(self):
        with self.assertRaises(pv.OpsProviderRefused) as caught:
            pv.provide_connection(self.read_inputs(), expected=READ_EXPECTED)
        self.assertEqual(caught.exception.code, "connection_factory_not_implemented")
        with self.assertRaises(pv.OpsProviderRefused) as caught:
            pv.provide_connection(self.read_inputs(mode="ops"), expected=READ_EXPECTED)
        self.assertEqual(caught.exception.code, "mode_not_synthetic")


if __name__ == "__main__":
    unittest.main()

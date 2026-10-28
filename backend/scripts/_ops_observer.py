"""Operations tool safety contract, connection provider unit 6-1c: the post-connect observation
collector (OPS_CONNECTION_PROVIDER_CONTRACT.md 2·2-1·2-2·10절).

It reads one `Observation` (unit 6-1a type) from a connection the provider already opened and
put into the observation transaction. It only uses a cursor: it never connects, commits, rolls
back, closes or runs business work. Judging, rollback, closing and handover stay with
`_ops_provider`. Tested with FAKE cursors only: whether the SQL runs on a real server and whether
`has_*_privilege` / `aclexplode` give the real ACL meaning is not proven here (contract 10절 list).

SQL rules: every catalog, function, type and operator is `pg_catalog`-qualified, values are bound
parameters, the only identifiers (synthetic identity table) are built with `psycopg.sql.Identifier`,
and there is no path that executes a caller-supplied SQL string.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

from psycopg import errors as pg_errors
from psycopg import sql
from psycopg.pq import TransactionStatus
from psycopg.rows import dict_row

import _ops_provider as pv

MIN_SERVER_MAJOR = 17                                    # MAINTAIN privilege (17+), has_parameter_privilege (16+)
# Synthetic test format only (contract 10절): the production identity table is not decided.
IDENTITY_SCHEMA, IDENTITY_TABLE, IDENTITY_COLUMN = "jp_vocab_ops_synthetic", "db_identity", "identity_value"
SYSTEM_SCHEMAS = r"^(pg_catalog|information_schema|pg_toast.*|pg_temp_[0-9]+)$"
RELKIND_KINDS = {"r": "table", "p": "partitioned_table", "v": "view", "m": "materialized_view",
                 "f": "foreign_table", "S": "sequence"}
RELKIND_EXCLUDED = frozenset({"i", "I", "c"})            # indexes, partitioned indexes, composite types: no grants
RELATION_PRIVILEGES = ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER", "MAINTAIN")
COLUMN_PRIVILEGES = ("SELECT", "INSERT", "UPDATE", "REFERENCES")
SEQUENCE_PRIVILEGES = ("USAGE", "SELECT", "UPDATE")
SCHEMA_PRIVILEGES = ("USAGE", "CREATE")
DATABASE_PRIVILEGES = ("CONNECT", "CREATE", "TEMPORARY")
TABLESPACE_PRIVILEGES = ("CREATE",)
ROUTINE_PRIVILEGES = ("EXECUTE",)
PARAMETER_PRIVILEGES = ("SET", "ALTER SYSTEM")
LARGE_OBJECT_PRIVILEGES = frozenset({"SELECT", "UPDATE"})
DEFAULT_ACL_PRIVILEGES = frozenset(RELATION_PRIVILEGES + SEQUENCE_PRIVILEGES + ("EXECUTE", "CREATE"))
DEFAULT_ACL_TYPES = {"r": "tables", "S": "sequences", "f": "functions", "T": "types", "n": "schemas",
                     "L": "large_objects"}
ISOLATION_LEVELS = frozenset({"read uncommitted", "read committed", "repeatable read", "serializable"})
# Reported, not represented by the 6-1a Observation (contract 10절); none of them is turned into a pass.
NOT_REPRESENTED = ("membership_inherit_set_admin_options", "privilege_grant_option", "ownership_per_catalog",
                   "default_acl_and_large_object_grantee")

EQ, GT, MATCH = "OPERATOR(pg_catalog.=)", "OPERATOR(pg_catalog.>)", "OPERATOR(pg_catalog.~)"
_NOT_SYSTEM = f"NOT (n.nspname::pg_catalog.text {MATCH} %(system_schemas)s)"
_NS_JOIN = f"JOIN pg_catalog.pg_namespace AS n ON n.oid {EQ}"
_PRIVS = "CROSS JOIN pg_catalog.unnest(%(privileges)s::pg_catalog.text[]) AS p (privilege)"
_RELKINDS = f"c.relkind::pg_catalog.text {EQ} ANY (%(relkinds)s::pg_catalog.text[])"
_INHERITED = (f"CASE WHEN g.grantee {EQ} %(public_oid)s::pg_catalog.oid THEN true "
              f"ELSE pg_catalog.pg_has_role(CURRENT_USER, g.grantee, %(usage_mode)s) END")
_OWNED = ("(SELECT pg_catalog.count(*) FROM pg_catalog.{table} AS x "
          "WHERE pg_catalog.pg_has_role(CURRENT_USER, x.{column}, %(member_mode)s)) AS {alias}")
_OWNERSHIP = (("pg_class", "relowner", "relations"), ("pg_namespace", "nspowner", "schemas"),
              ("pg_proc", "proowner", "routines"), ("pg_type", "typowner", "types"),
              ("pg_largeobject_metadata", "lomowner", "large_objects"), ("pg_database", "datdba", "databases"),
              ("pg_tablespace", "spcowner", "tablespaces"), ("pg_default_acl", "defaclrole", "default_acls"))

_TEXT = {
    "session": (
        "SELECT pg_catalog.current_database()::pg_catalog.text AS dbname, "
        "pg_catalog.current_setting(%(server_version_num)s) AS server_version_num, "
        "CURRENT_USER::pg_catalog.text AS current_user_name, SESSION_USER::pg_catalog.text AS session_user_name, "
        "pg_catalog.current_setting(%(search_path)s) AS search_path, "
        "pg_catalog.current_setting(%(default_read_only)s) AS default_read_only, "
        "pg_catalog.current_setting(%(default_isolation)s) AS default_isolation, "
        "pg_catalog.current_setting(%(transaction_read_only)s) AS transaction_read_only, "
        "pg_catalog.current_setting(%(lo_compat_privileges)s) AS lo_compat_privileges"),
    "role": (
        "SELECT r.rolsuper AS superuser, r.rolcreaterole AS createrole, r.rolcreatedb AS createdb, "
        "r.rolreplication AS replication, r.rolbypassrls AS bypassrls, r.rolinherit AS inherit "
        f"FROM pg_catalog.pg_roles AS r WHERE r.rolname {EQ} CURRENT_USER"),
    "memberships": (
        "WITH RECURSIVE m (roleid) AS ("
        f"SELECT a.roleid FROM pg_catalog.pg_auth_members AS a WHERE a.member {EQ} "
        f"(SELECT r.oid FROM pg_catalog.pg_roles AS r WHERE r.rolname {EQ} CURRENT_USER) "
        f"UNION SELECT a.roleid FROM pg_catalog.pg_auth_members AS a JOIN m ON a.member {EQ} m.roleid) "
        f"SELECT r.rolname::pg_catalog.text AS role_name FROM m JOIN pg_catalog.pg_roles AS r ON r.oid {EQ} m.roleid"),
    "ownership": "SELECT " + ", ".join(_OWNED.format(table=t, column=c, alias=a) for t, c, a in _OWNERSHIP),
    "tls": ("SELECT s.ssl AS ssl, s.version AS version FROM pg_catalog.pg_stat_ssl AS s "
            f"WHERE s.pid {EQ} pg_catalog.pg_backend_pid()"),
    "relations": (
        "SELECT c.oid AS oid, c.relkind::pg_catalog.text AS relkind, n.nspname::pg_catalog.text AS schema_name, "
        f"c.relname::pg_catalog.text AS object_name FROM pg_catalog.pg_class AS c {_NS_JOIN} c.relnamespace "
        f"WHERE {_NOT_SYSTEM}"),
    "relation_privileges": (
        "SELECT c.oid AS oid, p.privilege AS privilege, "
        "pg_catalog.has_table_privilege(CURRENT_USER, c.oid, p.privilege) AS granted "
        f"FROM pg_catalog.pg_class AS c {_NS_JOIN} c.relnamespace {_PRIVS} WHERE {_NOT_SYSTEM} AND {_RELKINDS}"),
    "column_counts": (
        "SELECT c.oid AS oid, (SELECT pg_catalog.count(*) FROM pg_catalog.pg_attribute AS a "
        f"WHERE a.attrelid {EQ} c.oid AND a.attnum {GT} 0 AND NOT a.attisdropped) AS column_count "
        f"FROM pg_catalog.pg_class AS c {_NS_JOIN} c.relnamespace WHERE {_NOT_SYSTEM} AND {_RELKINDS}"),
    "columns": (
        "SELECT c.oid AS oid, a.attname::pg_catalog.text AS column_name "
        f"FROM pg_catalog.pg_class AS c {_NS_JOIN} c.relnamespace "
        f"JOIN pg_catalog.pg_attribute AS a ON a.attrelid {EQ} c.oid "
        f"WHERE {_NOT_SYSTEM} AND {_RELKINDS} AND a.attnum {GT} 0 AND NOT a.attisdropped"),
    "column_privileges": (
        "SELECT c.oid AS oid, a.attname::pg_catalog.text AS column_name, p.privilege AS privilege, "
        "pg_catalog.has_column_privilege(CURRENT_USER, c.oid, a.attnum, p.privilege) AS granted "
        f"FROM pg_catalog.pg_class AS c {_NS_JOIN} c.relnamespace "
        f"JOIN pg_catalog.pg_attribute AS a ON a.attrelid {EQ} c.oid {_PRIVS} "
        f"WHERE {_NOT_SYSTEM} AND {_RELKINDS} AND a.attnum {GT} 0 AND NOT a.attisdropped"),
    "sequence_privileges": (
        "SELECT c.oid AS oid, p.privilege AS privilege, "
        "pg_catalog.has_sequence_privilege(CURRENT_USER, c.oid, p.privilege) AS granted "
        f"FROM pg_catalog.pg_class AS c {_NS_JOIN} c.relnamespace {_PRIVS} WHERE {_NOT_SYSTEM} AND {_RELKINDS}"),
    "schemas": ("SELECT n.oid AS oid, n.nspname::pg_catalog.text AS object_name "
                f"FROM pg_catalog.pg_namespace AS n WHERE {_NOT_SYSTEM}"),
    "schema_privileges": (
        "SELECT n.oid AS oid, p.privilege AS privilege, "
        "pg_catalog.has_schema_privilege(CURRENT_USER, n.oid, p.privilege) AS granted "
        f"FROM pg_catalog.pg_namespace AS n {_PRIVS} WHERE {_NOT_SYSTEM}"),
    "database": ("SELECT d.oid AS oid, d.datname::pg_catalog.text AS object_name FROM pg_catalog.pg_database AS d "
                 f"WHERE d.datname {EQ} pg_catalog.current_database()"),
    "database_privileges": (
        "SELECT d.oid AS oid, p.privilege AS privilege, "
        "pg_catalog.has_database_privilege(CURRENT_USER, d.oid, p.privilege) AS granted "
        f"FROM pg_catalog.pg_database AS d {_PRIVS} WHERE d.datname {EQ} pg_catalog.current_database()"),
    "tablespaces": "SELECT t.oid AS oid, t.spcname::pg_catalog.text AS object_name FROM pg_catalog.pg_tablespace AS t",
    "tablespace_privileges": (
        "SELECT t.oid AS oid, p.privilege AS privilege, "
        "pg_catalog.has_tablespace_privilege(CURRENT_USER, t.oid, p.privilege) AS granted "
        f"FROM pg_catalog.pg_tablespace AS t {_PRIVS}"),
    "routines": (
        "SELECT f.oid AS oid, n.nspname::pg_catalog.text AS schema_name, f.proname::pg_catalog.text AS object_name, "
        "pg_catalog.pg_get_function_identity_arguments(f.oid) AS identity_arguments "
        f"FROM pg_catalog.pg_proc AS f {_NS_JOIN} f.pronamespace WHERE f.prosecdef AND {_NOT_SYSTEM}"),
    "routine_privileges": (
        "SELECT f.oid AS oid, p.privilege AS privilege, "
        "pg_catalog.has_function_privilege(CURRENT_USER, f.oid, p.privilege) AS granted "
        f"FROM pg_catalog.pg_proc AS f {_NS_JOIN} f.pronamespace {_PRIVS} WHERE f.prosecdef AND {_NOT_SYSTEM}"),
    "default_acls": (
        "SELECT d.oid AS oid, r.rolname::pg_catalog.text AS role_name, d.defaclnamespace AS namespace_oid, "
        "n.nspname::pg_catalog.text AS schema_name, d.defaclobjtype::pg_catalog.text AS object_type "
        f"FROM pg_catalog.pg_default_acl AS d LEFT JOIN pg_catalog.pg_roles AS r ON r.oid {EQ} d.defaclrole "
        f"LEFT JOIN pg_catalog.pg_namespace AS n ON n.oid {EQ} d.defaclnamespace"),
    "default_acl_privileges": (
        "SELECT DISTINCT d.oid AS oid, g.privilege_type AS privilege FROM pg_catalog.pg_default_acl AS d "
        f"CROSS JOIN LATERAL pg_catalog.aclexplode(d.defaclacl) AS g WHERE {_INHERITED}"),
    "parameter_acls": "SELECT a.oid AS oid, a.parname AS object_name FROM pg_catalog.pg_parameter_acl AS a",
    "parameter_privileges": (
        "SELECT a.oid AS oid, p.privilege AS privilege, "
        "pg_catalog.has_parameter_privilege(CURRENT_USER, a.parname, p.privilege) AS granted "
        f"FROM pg_catalog.pg_parameter_acl AS a {_PRIVS}"),
    "large_objects": "SELECT m.oid AS oid FROM pg_catalog.pg_largeobject_metadata AS m",
    "large_object_privileges": (
        "SELECT DISTINCT m.oid AS oid, g.privilege_type AS privilege FROM pg_catalog.pg_largeobject_metadata AS m "
        "CROSS JOIN LATERAL pg_catalog.aclexplode(COALESCE(m.lomacl, "
        "pg_catalog.acldefault(%(large_object_type)s::pg_catalog.\"char\", m.lomowner))) AS g "
        f"WHERE {_INHERITED}"),
}
QUERIES: dict[str, sql.Composable] = {name: sql.SQL(text) for name, text in _TEXT.items()}
QUERIES["identity"] = sql.SQL("SELECT t.{column} AS identity_value FROM {schema}.{table} AS t LIMIT %(limit)s").format(
    column=sql.Identifier(IDENTITY_COLUMN), schema=sql.Identifier(IDENTITY_SCHEMA), table=sql.Identifier(IDENTITY_TABLE))

_SCOPE = {"system_schemas": SYSTEM_SCHEMAS}
_ACL = {"public_oid": 0, "usage_mode": "USAGE"}
PARAMS: dict[str, dict[str, Any]] = {
    "session": {"server_version_num": "server_version_num", "search_path": "search_path",
                "default_read_only": "default_transaction_read_only",
                "default_isolation": "default_transaction_isolation",
                "transaction_read_only": "transaction_read_only", "lo_compat_privileges": "lo_compat_privileges"},
    "ownership": {"member_mode": "MEMBER"},
    "identity": {"limit": 2},
    "relations": _SCOPE,
    "relation_privileges": {**_SCOPE, "privileges": list(RELATION_PRIVILEGES),
                            "relkinds": [k for k, v in RELKIND_KINDS.items() if v != "sequence"]},
    "column_counts": {**_SCOPE, "relkinds": [k for k, v in RELKIND_KINDS.items() if v != "sequence"]},
    "columns": {**_SCOPE, "relkinds": [k for k, v in RELKIND_KINDS.items() if v != "sequence"]},
    "column_privileges": {**_SCOPE, "privileges": list(COLUMN_PRIVILEGES),
                          "relkinds": [k for k, v in RELKIND_KINDS.items() if v != "sequence"]},
    "sequence_privileges": {**_SCOPE, "privileges": list(SEQUENCE_PRIVILEGES), "relkinds": ["S"]},
    "schemas": _SCOPE,
    "schema_privileges": {**_SCOPE, "privileges": list(SCHEMA_PRIVILEGES)},
    "database_privileges": {"privileges": list(DATABASE_PRIVILEGES)},
    "tablespace_privileges": {"privileges": list(TABLESPACE_PRIVILEGES)},
    "routines": _SCOPE,
    "routine_privileges": {**_SCOPE, "privileges": list(ROUTINE_PRIVILEGES)},
    "default_acl_privileges": _ACL,
    "parameter_privileges": {"privileges": list(PARAMETER_PRIVILEGES)},
    "large_object_privileges": {**_ACL, "large_object_type": "L"},
}
_GRANTED = ("oid", "privilege", "granted")


def _invalid() -> pv.OpsProviderRefused:
    return pv.OpsProviderRefused("observation_invalid")


def _str(value: Any) -> str:
    if type(value) is not str:
        raise _invalid()
    return value


def _int(value: Any) -> int:
    if type(value) is not int or value < 0:
        raise _invalid()
    return value


def _bool(value: Any) -> bool:
    if type(value) is not bool:
        raise _invalid()
    return value


def _on_off(value: Any) -> bool:
    if value not in ("on", "off") or type(value) is not str:
        raise _invalid()
    return value == "on"


class _Reader:
    """Runs only the module's own queries with their own bound parameters; rows are named."""

    def __init__(self, cursor: Any):
        self._cursor = cursor

    def rows(self, name: str, columns: tuple[str, ...], *, exactly: int | None = None) -> list[dict]:
        self._cursor.execute(QUERIES[name], PARAMS.get(name))
        result = self._cursor.fetchall()
        if not isinstance(result, list) or not all(type(r) is dict and set(r) == set(columns) for r in result):
            raise _invalid()
        if exactly is not None and len(result) != exactly:
            raise _invalid()
        return result


class _Scope:
    """Object list and effective privilege set, collected separately (contract 2-1·10절)."""

    def __init__(self) -> None:
        self.objects: list[tuple[str, str, str]] = []
        self.privileges: set[tuple[str, str, str, str, str]] = set()
        self.unresolved: set[str] = set()
        self._keys: set[tuple[str, str, str]] = set()

    def key(self, kind: str, schema: str, name: str) -> tuple[str, str, str] | None:
        """None (and an unresolved code) when the name does not fit the 6-1a identity format."""
        if (schema and not pv._NAME.fullmatch(schema)) or not pv._NAME.fullmatch(name):
            self.unresolved.add("object_name_unrepresentable")
            return None
        key = (kind, schema, name)
        if key in self._keys:
            self.unresolved.add("object_identity_collision")      # two catalog objects, one identity
            return None
        self._keys.add(key)
        self.objects.append(key)
        return key

    def granted(self, reader: _Reader, name: str, oids: dict[int, Any], privileges: tuple[str, ...]) -> set:
        """`has_*_privilege` rows: one per object and requested privilege, granted bool."""
        seen: dict[int, set[str]] = {}
        granted: set[tuple[int, str]] = set()
        for row in reader.rows(name, _GRANTED):
            oid, privilege = _int(row["oid"]), _str(row["privilege"])
            if privilege not in privileges or privilege in seen.setdefault(oid, set()):
                raise _invalid()
            seen[oid].add(privilege)
            if oid not in oids:
                self.unresolved.add("privilege_object_unknown")
            elif row["granted"] is None:
                self.unresolved.add("privilege_check_null")
            elif _bool(row["granted"]):
                granted.add((oid, privilege))
        for oid in oids:
            if seen.get(oid, set()) != set(privileges):
                self.unresolved.add("privilege_rows_incomplete")
        for oid, privilege in granted:
            self.grant(oids[oid], "", privilege)
        return granted

    def acl(self, reader: _Reader, name: str, oids: dict[int, Any], allowed: frozenset[str]) -> None:
        """`aclexplode` rows: one per object and privilege inherited by the current role or PUBLIC."""
        seen: set[tuple[int, str]] = set()
        for row in reader.rows(name, ("oid", "privilege")):
            oid, privilege = _int(row["oid"]), _str(row["privilege"])
            if (oid, privilege) in seen:
                raise _invalid()
            seen.add((oid, privilege))
            if oid not in oids:
                self.unresolved.add("privilege_object_unknown")
            elif privilege not in allowed:
                self.unresolved.add("acl_privilege_unknown")
            else:
                self.grant(oids[oid], "", privilege)

    def grant(self, key: tuple[str, str, str] | None, column: str, privilege: str) -> None:
        if key is not None:                       # unrepresentable objects are already unresolved
            self.privileges.add(key + (column, privilege.replace(" ", "_")))


def _objects(reader: _Reader, name: str, kind: str, scope: _Scope, *, exactly: int | None = None) -> dict:
    oids: dict[int, Any] = {}
    for row in reader.rows(name, ("oid", "object_name"), exactly=exactly):
        oid = _int(row["oid"])
        if oid in oids:
            raise _invalid()
        oids[oid] = scope.key(kind, "", _str(row["object_name"]))
    return oids


def _expected_columns(reader: _Reader, relations: dict[int, Any], scope: _Scope) -> dict[int, set[str]]:
    """Expected user columns per relation, from two queries independent of the privilege response.
    A relation has zero columns only when its count row says so; a missing row is never read as 0."""
    counts: dict[int, int] = {}
    for row in reader.rows("column_counts", ("oid", "column_count")):
        oid = _int(row["oid"])
        if oid in counts:
            raise _invalid()
        counts[oid] = _int(row["column_count"])
    expected: dict[int, set[str]] = {}
    for row in reader.rows("columns", ("oid", "column_name")):
        oid, column = _int(row["oid"]), _str(row["column_name"])
        if not column or column in expected.setdefault(oid, set()):
            raise _invalid()
        expected[oid].add(column)
    if set(counts) != set(relations) or not set(expected) <= set(relations) \
            or any(len(expected.get(oid, ())) != count for oid, count in counts.items()):
        scope.unresolved.add("column_list_mismatch")              # changed between queries, or rows missing
    return expected


def _collect_scope(reader: _Reader, scope: _Scope) -> None:
    relations: dict[int, Any] = {}
    sequences: dict[int, Any] = {}
    for row in reader.rows("relations", ("oid", "relkind", "schema_name", "object_name")):
        oid, relkind = _int(row["oid"]), _str(row["relkind"])
        schema, name = _str(row["schema_name"]), _str(row["object_name"])
        if oid in relations or oid in sequences:
            raise _invalid()
        if relkind in RELKIND_EXCLUDED:
            continue
        kind = RELKIND_KINDS.get(relkind)
        if kind is None:
            scope.unresolved.add("relkind_unknown")
            continue
        (sequences if kind == "sequence" else relations)[oid] = scope.key(kind, schema, name)
    table_level = scope.granted(reader, "relation_privileges", relations, RELATION_PRIVILEGES)
    expected = _expected_columns(reader, relations, scope)
    columns: dict[tuple[int, str], set[str]] = {}
    for row in reader.rows("column_privileges", ("oid", "column_name", "privilege", "granted")):
        oid, column, privilege = _int(row["oid"]), _str(row["column_name"]), _str(row["privilege"])
        if privilege not in COLUMN_PRIVILEGES or privilege in columns.setdefault((oid, column), set()):
            raise _invalid()
        columns[(oid, column)].add(privilege)
        if oid not in relations:
            scope.unresolved.add("privilege_object_unknown")
        elif column not in expected.get(oid, ()):
            scope.unresolved.add("column_unexpected")              # not in the independent column list
        elif row["granted"] is None:
            scope.unresolved.add("privilege_check_null")
        elif _bool(row["granted"]) and (oid, privilege) not in table_level:   # column-only excess grant
            if not pv._NAME.fullmatch(column):
                scope.unresolved.add("object_name_unrepresentable")
            else:
                scope.grant(relations[oid], column, privilege)
    if any(privileges != set(COLUMN_PRIVILEGES) for privileges in columns.values()) \
            or any(columns.get((oid, column)) != set(COLUMN_PRIVILEGES)
                   for oid, names in expected.items() for column in names):
        scope.unresolved.add("privilege_rows_incomplete")         # a whole column / relation missing counts too
    scope.granted(reader, "sequence_privileges", sequences, SEQUENCE_PRIVILEGES)
    scope.granted(reader, "schema_privileges", _objects(reader, "schemas", "schema", scope), SCHEMA_PRIVILEGES)
    scope.granted(reader, "database_privileges", _objects(reader, "database", "database", scope, exactly=1),
                  DATABASE_PRIVILEGES)
    scope.granted(reader, "tablespace_privileges", _objects(reader, "tablespaces", "tablespace", scope),
                  TABLESPACE_PRIVILEGES)

    routines: dict[int, Any] = {}
    for row in reader.rows("routines", ("oid", "schema_name", "object_name", "identity_arguments")):
        oid = _int(row["oid"])
        schema, name, arguments = _str(row["schema_name"]), _str(row["object_name"]), _str(row["identity_arguments"])
        if oid in routines:
            raise _invalid()
        if not pv._NAME.fullmatch(name):
            scope.unresolved.add("object_name_unrepresentable")
            routines[oid] = None
            continue
        digest = hashlib.sha256(arguments.encode("utf-8")).hexdigest()[:16]   # overloads stay distinct
        routines[oid] = scope.key("security_definer_routine", schema, f"{name}${digest}")
    scope.granted(reader, "routine_privileges", routines, ROUTINE_PRIVILEGES)

    defaults: dict[int, Any] = {}
    for row in reader.rows("default_acls", ("oid", "role_name", "namespace_oid", "schema_name", "object_type")):
        oid, namespace, kind = _int(row["oid"]), _int(row["namespace_oid"]), _str(row["object_type"])
        role, schema = row["role_name"], row["schema_name"]
        if oid in defaults:
            raise _invalid()
        word = DEFAULT_ACL_TYPES.get(kind)
        if role is None or (schema is None) != (namespace == 0) or word is None:
            scope.unresolved.add("default_acl_unresolved")       # dangling role / schema, unknown type
            defaults[oid] = None
            continue
        defaults[oid] = scope.key("default_acl", "" if schema is None else _str(schema), f"{_str(role)}.{word}")
    scope.acl(reader, "default_acl_privileges", defaults, DEFAULT_ACL_PRIVILEGES)

    scope.granted(reader, "parameter_privileges", _objects(reader, "parameter_acls", "parameter_acl", scope),
                  PARAMETER_PRIVILEGES)
    large_objects: dict[int, Any] = {}
    for row in reader.rows("large_objects", ("oid",)):
        oid = _int(row["oid"])
        if oid in large_objects:
            raise _invalid()
        large_objects[oid] = scope.key("large_object", "", str(oid))
    scope.acl(reader, "large_object_privileges", large_objects, LARGE_OBJECT_PRIVILEGES)


class CatalogObserver:
    """Implements the 6-1a `Observer` interface. Not wired into the default entry point."""

    def observe(self, connection: Any) -> pv.Observation:
        try:
            info = connection.info
            in_transaction = info.transaction_status == TransactionStatus.INTRANS
            driver = (info.host, info.port, info.dbname, info.server_version, connection.pgconn.ssl_in_use)
        except AttributeError:
            raise _invalid() from None
        if not in_transaction:
            raise pv.OpsProviderRefused("observation_not_in_transaction")
        if not (type(driver[0]) is str and type(driver[1]) is int and type(driver[2]) is str
                and type(driver[3]) is int and type(driver[4]) is bool):
            raise _invalid()
        with connection.cursor(row_factory=dict_row) as cursor:
            return _collect(_Reader(cursor), driver)


def _collect(reader: _Reader, driver: tuple) -> pv.Observation:
    host, port, driver_dbname, driver_version, driver_tls = driver
    session = reader.rows("session", ("dbname", "server_version_num", "current_user_name", "session_user_name",
                                      "search_path", "default_read_only", "default_isolation",
                                      "transaction_read_only", "lo_compat_privileges"), exactly=1)[0]
    dbname, version = _str(session["dbname"]), _str(session["server_version_num"])
    if not re.fullmatch(r"[0-9]{5,6}", version):
        raise _invalid()
    server_major = int(version) // 10000
    if driver_dbname != dbname or driver_version // 10000 != server_major:
        raise pv.OpsProviderRefused("observation_driver_mismatch")
    if server_major < MIN_SERVER_MAJOR:
        raise pv.OpsProviderRefused("observation_server_unsupported")
    isolation = _str(session["default_isolation"])
    if isolation not in ISOLATION_LEVELS:
        raise _invalid()
    scope = _Scope()
    if _on_off(session["lo_compat_privileges"]):
        scope.unresolved.add("large_object_compat_privileges")

    role = reader.rows("role", pv.ROLE_ATTRIBUTES, exactly=1)[0]
    attributes = tuple((name, _bool(role[name])) for name in pv.ROLE_ATTRIBUTES)
    memberships = [_str(row["role_name"]) for row in reader.rows("memberships", ("role_name",))]
    if len(set(memberships)) != len(memberships) or not all(pv._text(m) for m in memberships):
        raise _invalid()
    owned = reader.rows("ownership", tuple(alias for _, _, alias in _OWNERSHIP), exactly=1)[0]
    owned_count = sum(_int(owned[alias]) for _, _, alias in _OWNERSHIP)

    tls = reader.rows("tls", ("ssl", "version"), exactly=1)[0]
    server_ssl = _bool(tls["ssl"])
    tls_version = _str(tls["version"]) if server_ssl else "none"

    try:
        identity = reader.rows("identity", ("identity_value",))
    except (pg_errors.UndefinedTable, pg_errors.UndefinedColumn, pg_errors.InvalidSchemaName):
        raise pv.OpsProviderRefused("observation_identity_missing") from None
    if len(identity) != 1:
        raise pv.OpsProviderRefused("observation_identity_rows")
    identity_value = _str(identity[0]["identity_value"])

    _collect_scope(reader, scope)
    return pv.Observation(
        host=host, port=port, dbname=dbname, server_major=server_major, identity_value=identity_value,
        current_user=_str(session["current_user_name"]), session_user=_str(session["session_user_name"]),
        role_attributes=attributes, memberships=tuple(sorted(memberships)), owned_count=owned_count,
        objects=tuple(sorted(scope.objects)), privileges=tuple(sorted(scope.privileges)),
        search_path=_str(session["search_path"]), observation_read_only=_on_off(session["transaction_read_only"]),
        default_read_only=_on_off(session["default_read_only"]), default_isolation=isolation,
        tls_in_use=driver_tls, tls_server_ssl=server_ssl, tls_version=tls_version,
        unresolved=tuple(sorted(scope.unresolved)))

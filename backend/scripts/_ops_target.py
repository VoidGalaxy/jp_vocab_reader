"""Operations tool safety contract, unit 2: connection string parsing and the pre-connect
target check (docs/plans/srs-improvement/gate-e/OPS_TOOL_SAFETY_CONTRACT.md 6-1).

Pure judgement of the inputs against each other. The secret connection string, the approved
public target (host, port, database, the step's role), the approved TLS values and a snapshot
of the environment are all arguments; the real environment, files, DNS and network are never
read and no connection function is called. Parsing uses psycopg's libpq conninfo parser
(`conninfo_to_dict`, which only parses) after a structural pre-scan, because libpq silently
lets a later duplicate or a query `host` override earlier values.

This proves only that the inputs agree. Whether the public target is bound to a real signed
approval, whether the certificate file is right, who the server is, and whether the host is
really a direct endpoint are later units.

Refusals are `OpsTargetRefused(code)` with a fixed code. The result holds public values only;
the secret string and password never enter it, an exception or a message.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import parse_qsl, unquote, urlsplit

SCHEME = "postgresql://"
REQUIRED_SSLMODE = "verify-full"
URI_PARTS = ("user", "password", "host", "port", "dbname")
QUERY_PARAMS = ("sslmode", "sslrootcert")
ALLOWED = frozenset(URI_PARTS + QUERY_PARAMS)
MAX_LENGTH = 4096

_HOST = re.compile(r"[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)*")
_PORT = re.compile(r"[1-9][0-9]{0,4}")
_DBNAME = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_-]{0,62}")
_ROLE = re.compile(r"[a-z_][a-z0-9_]{0,62}")  # same as unit 1 role names


class OpsTargetRefused(Exception):
    """`code` is a fixed reason; nothing from the input is carried."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _refuse(code: str) -> OpsTargetRefused:
    return OpsTargetRefused(code)


def _plain(value: Any, *, limit: int) -> bool:
    """A non-empty printable ASCII str without control characters."""
    return (type(value) is str and 0 < len(value) <= limit and value.isascii()
            and all(32 <= ord(ch) < 127 for ch in value))


@dataclass(frozen=True)
class ApprovedTarget:
    """Public values the approval binds for one step (contract 3-1 / 4-1 / 6)."""
    host: str
    port: int
    dbname: str
    role: str
    sslmode: str
    sslrootcert: str


@dataclass(frozen=True)
class PreconnectDecision:
    """Public result only: no secret is held here."""
    host: str
    port: int
    dbname: str
    role: str
    sslmode: str
    sslrootcert: str


def _check_approved(target: Any) -> ApprovedTarget:
    if not isinstance(target, ApprovedTarget):
        raise _refuse("approved_target_invalid")
    if (type(target.host) is not str or not target.host.isascii() or not _HOST.fullmatch(target.host)
            or type(target.port) is not int or not 0 < target.port < 65536
            or type(target.dbname) is not str or not target.dbname.isascii() or not _DBNAME.fullmatch(target.dbname)
            or type(target.role) is not str or not target.role.isascii() or not _ROLE.fullmatch(target.role)):
        raise _refuse("approved_target_invalid")
    if target.sslmode != REQUIRED_SSLMODE or type(target.sslmode) is not str:
        raise _refuse("approved_tls_invalid")
    if not _plain(target.sslrootcert, limit=1024) or target.sslrootcert == "system":
        raise _refuse("approved_tls_invalid")
    return target


def check_environment(snapshot: Any) -> None:
    """Refuse any libpq-style variable (name starting with PG, any case) in the snapshot."""
    if not isinstance(snapshot, Mapping):
        raise _refuse("environment_snapshot_invalid")
    for name, value in snapshot.items():
        if type(name) is not str or type(value) is not str:
            raise _refuse("environment_snapshot_invalid")
        if name.upper().startswith("PG"):
            raise _refuse("libpq_environment_present")


def _structure(secret: str) -> dict[str, str]:
    """Structural pre-scan of the one supported URI form; returns decoded parts."""
    if not secret.startswith(SCHEME):
        raise _refuse("conninfo_format_unsupported")
    try:
        parts = urlsplit(secret)
    except ValueError:
        raise _refuse("conninfo_unparseable") from None
    if parts.scheme != "postgresql" or parts.fragment or "#" in secret:
        raise _refuse("conninfo_format_unsupported")
    netloc = parts.netloc
    if netloc.count("@") != 1:
        raise _refuse("conninfo_credentials_required")
    userinfo, hostport = netloc.split("@")
    if userinfo.count(":") != 1:
        raise _refuse("conninfo_credentials_required")
    user, password = userinfo.split(":")
    if "," in hostport or hostport.startswith(("[", "/", "%")) or "%" in hostport:
        raise _refuse("conninfo_host_not_single_direct")
    if hostport.count(":") != 1:
        raise _refuse("conninfo_port_required")
    host, port = hostport.split(":")
    path = parts.path
    if not path.startswith("/") or "/" in path[1:] or len(path) < 2:
        raise _refuse("conninfo_dbname_required")
    dbname = path[1:]
    if "%" in user or "%" in dbname:
        raise _refuse("conninfo_encoding_not_allowed")
    if not user or not password:
        raise _refuse("conninfo_credentials_required")
    try:
        # strict UTF-8: invalid or truncated bytes are refused, never read as replacement characters
        query = (parse_qsl(parts.query, keep_blank_values=True, strict_parsing=True, encoding="utf-8",
                           errors="strict") if parts.query else [])
    except ValueError:  # includes UnicodeDecodeError
        raise _refuse("conninfo_unparseable") from None
    keys = [key for key, _ in query]
    if len(keys) != len(set(keys)):
        raise _refuse("conninfo_parameter_duplicate")
    if any(key in URI_PARTS for key in keys):
        raise _refuse("conninfo_parameter_conflict")
    if any(key not in QUERY_PARAMS for key in keys):
        raise _refuse("conninfo_parameter_not_allowed")
    found = {"user": user, "password": unquote(password, errors="strict"), "host": host, "port": port,
             "dbname": dbname}
    found.update(query)
    return found


def _libpq_parse(secret: str) -> dict[str, str]:
    """libpq's own parse (PQconninfoParse via psycopg): no connection, no environment defaults."""
    try:
        import psycopg
        from psycopg.conninfo import conninfo_to_dict
    except ImportError:
        raise _refuse("conninfo_parser_unavailable") from None
    try:
        return conninfo_to_dict(secret)
    except (psycopg.ProgrammingError, UnicodeDecodeError):  # libpq decodes %XX to bytes that may not be UTF-8
        raise _refuse("conninfo_unparseable") from None


def check_preconnect(secret_dsn: Any, target: Any, environment: Any) -> PreconnectDecision:
    """Judge the secret connection string against the approved public target, TLS values and
    the environment snapshot. Returns public values only."""
    approved = _check_approved(target)
    check_environment(environment)
    if not _plain(secret_dsn, limit=MAX_LENGTH):
        raise _refuse("conninfo_value_invalid")       # type, empty, non-ASCII, control characters
    try:
        found = _structure(secret_dsn)
    except UnicodeDecodeError:
        raise _refuse("conninfo_unparseable") from None
    parsed = _libpq_parse(secret_dsn)
    if set(parsed) - ALLOWED:
        raise _refuse("conninfo_parameter_not_allowed")
    missing = [key for key in ALLOWED if not found.get(key)]
    if missing or set(parsed) != ALLOWED:
        raise _refuse("conninfo_required_missing")
    if any(parsed[key] != found[key] for key in ALLOWED):
        raise _refuse("conninfo_parse_ambiguous")     # the two parsers disagree
    if not _HOST.fullmatch(found["host"]):
        raise _refuse("conninfo_host_not_single_direct")
    if not _PORT.fullmatch(found["port"]) or not 0 < int(found["port"]) < 65536:
        raise _refuse("conninfo_port_invalid")
    if not _DBNAME.fullmatch(found["dbname"]) or not _ROLE.fullmatch(found["user"]):
        raise _refuse("conninfo_value_invalid")
    if found["host"] != approved.host or int(found["port"]) != approved.port or found["dbname"] != approved.dbname:
        raise _refuse("target_mismatch")
    if found["user"] != approved.role:
        raise _refuse("role_mismatch")
    if found["sslmode"] != REQUIRED_SSLMODE or found["sslmode"] != approved.sslmode:
        raise _refuse("tls_mode_mismatch")
    if found["sslrootcert"] != approved.sslrootcert:
        raise _refuse("tls_root_mismatch")
    return PreconnectDecision(approved.host, approved.port, approved.dbname, approved.role, approved.sslmode,
                              approved.sslrootcert)

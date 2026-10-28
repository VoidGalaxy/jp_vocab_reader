"""Operations tool safety contract unit 2 (scripts/_ops_target.py): connection string parsing
and the pre-connect target check, as pure judgement.

Synthetic strings only. No connection is opened: every psycopg / libpq connect entry point is
patched to fail the test if called. No environment variable, file, DNS or network is read;
this proves the inputs agree with each other, not that a certificate, server or endpoint is
real.

Run directly:      python tests/test_ops_target.py
Or via discovery:   python -m unittest discover -s tests
"""

from __future__ import annotations

import re
import sys
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import psycopg  # noqa: E402  (parser only; connect entry points are patched below)
import psycopg.generators  # noqa: E402

import _ops_target as ops  # noqa: E402

SECRET = "Synth3tic-Pw-7f2a"
ROOT = "C:/ops/tls/synthetic-root.pem"
TARGET = ops.ApprovedTarget(host="db.synthetic.test", port=5432, dbname="jp_vocab", role="ops_read",
                            sslmode="verify-full", sslrootcert=ROOT)
GOOD = f"postgresql://ops_read:{SECRET}@db.synthetic.test:5432/jp_vocab?sslmode=verify-full&sslrootcert={ROOT}"


def dsn(user="ops_read", password=SECRET, host="db.synthetic.test", port="5432", db="jp_vocab",
        query=f"sslmode=verify-full&sslrootcert={ROOT}") -> str:
    tail = f"?{query}" if query is not None else ""
    return f"postgresql://{user}:{password}@{host}:{port}/{db}{tail}"


class Base(unittest.TestCase):
    def setUp(self):
        def forbidden(*_, **__):
            raise AssertionError("a connection function was called")

        patches = [mock.patch.object(psycopg, "connect", forbidden),
                   mock.patch.object(psycopg.Connection, "connect", forbidden),
                   mock.patch.object(psycopg.AsyncConnection, "connect", forbidden),
                   # the compiled PGconn type cannot be patched in place: replace the module attribute
                   mock.patch.object(psycopg.pq, "PGconn", type("NoPGconn", (), {"connect": staticmethod(forbidden),
                                                                                   "connect_start": staticmethod(forbidden)})),
                   mock.patch.object(psycopg.generators, "connect", forbidden)]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def refused(self, code, secret=GOOD, target=TARGET, environment=None):
        with self.assertRaises(ops.OpsTargetRefused) as caught:
            ops.check_preconnect(secret, target, environment or {})
        error = caught.exception
        self.assertEqual(error.code, code)
        self.assertEqual(error.args, (code,))
        self.assertNotIn(SECRET, repr(error) + str(error))
        self.assertTrue(error.__suppress_context__ or error.__context__ is None)
        return error


class Normal(Base):
    def test_good_input_returns_public_values_only(self):
        decision = ops.check_preconnect(GOOD, TARGET, {"PATH": "C:/Windows", "APPDATA": "x"})
        self.assertEqual((decision.host, decision.port, decision.dbname, decision.role),
                         ("db.synthetic.test", 5432, "jp_vocab", "ops_read"))
        self.assertEqual((decision.sslmode, decision.sslrootcert), ("verify-full", ROOT))
        self.assertNotIn(SECRET, repr(decision))
        self.assertNotIn(SECRET, str(vars(decision)))
        self.assertFalse(any("password" in field for field in vars(decision)))

    def test_percent_encoded_password_and_root(self):
        encoded = "p%40ss%3Aw%2Fd"
        self.assertEqual(ops.check_preconnect(dsn(password=encoded), TARGET, {}).role, "ops_read")
        windows_root = "C:\\ops\\tls\\root.pem"
        target = replace(TARGET, sslrootcert=windows_root)
        query = "sslmode=verify-full&sslrootcert=C%3A%5Cops%5Ctls%5Croot.pem"
        self.assertEqual(ops.check_preconnect(dsn(query=query), target, {}).sslrootcert, windows_root)

    def test_write_step_role(self):
        target = replace(TARGET, role="ops_write_prb")
        self.assertEqual(ops.check_preconnect(dsn(user="ops_write_prb"), target, {}).role, "ops_write_prb")


class Mismatch(Base):
    def test_target_role_and_tls(self):
        self.refused("target_mismatch", dsn(host="db2.synthetic.test"))
        self.refused("target_mismatch", dsn(port="5433"))
        self.refused("target_mismatch", dsn(db="jp_vocab_copy"))
        self.refused("role_mismatch", dsn(user="ops_write_prb"))
        self.refused("role_mismatch", target=replace(TARGET, role="ops_write_prb"))
        self.refused("tls_mode_mismatch", dsn(query=f"sslmode=require&sslrootcert={ROOT}"))
        self.refused("tls_mode_mismatch", dsn(query=f"sslmode=verify-ca&sslrootcert={ROOT}"))
        self.refused("tls_root_mismatch", dsn(query="sslmode=verify-full&sslrootcert=C:/ops/tls/other.pem"))
        self.refused("target_mismatch", dsn(host="db.synthetic.test-pooler"))  # no name guessing either way
        self.refused("conninfo_host_not_single_direct", dsn(host="DB.synthetic.test"))

    def test_approved_values_are_checked(self):
        for change in (dict(host="DB.x"), dict(host=""), dict(port=True), dict(port="5432"), dict(port=0),
                       dict(dbname=""), dict(role="Ops"), dict(role=None)):
            with self.subTest(change=sorted(change)):
                self.refused("approved_target_invalid", target=replace(TARGET, **change))
        for change in (dict(sslmode="require"), dict(sslrootcert=""), dict(sslrootcert="system"),
                       dict(sslrootcert=None), dict(sslrootcert="C:/x\n.pem")):
            with self.subTest(change=sorted(change)):
                self.refused("approved_tls_invalid", target=replace(TARGET, **change))
        self.refused("approved_target_invalid", target={"host": TARGET.host})


class Required(Base):
    def test_missing_values_are_not_filled_in(self):
        self.refused("conninfo_port_required", f"postgresql://ops_read:{SECRET}@db.synthetic.test/jp_vocab?sslmode=verify-full&sslrootcert={ROOT}")
        self.refused("conninfo_dbname_required", dsn(db=""))
        self.refused("conninfo_dbname_required", f"postgresql://ops_read:{SECRET}@db.synthetic.test:5432?sslmode=verify-full&sslrootcert={ROOT}")
        self.refused("conninfo_credentials_required", f"postgresql://db.synthetic.test:5432/jp_vocab?sslmode=verify-full&sslrootcert={ROOT}")
        self.refused("conninfo_credentials_required", f"postgresql://ops_read@db.synthetic.test:5432/jp_vocab?sslmode=verify-full&sslrootcert={ROOT}")
        self.refused("conninfo_credentials_required", dsn(password=""))
        self.refused("conninfo_credentials_required", dsn(user=""))
        self.refused("conninfo_required_missing", dsn(query=None))
        self.refused("conninfo_required_missing", dsn(query="sslmode=verify-full"))
        self.refused("conninfo_required_missing", dsn(query=f"sslrootcert={ROOT}"))
        self.refused("conninfo_required_missing", dsn(query="sslmode=verify-full&sslrootcert="))
        self.refused("conninfo_required_missing", dsn(host=""))

    def test_environment_snapshot(self):
        for name in ("PGHOST", "PGPORT", "PGDATABASE", "PGUSER", "PGPASSWORD", "PGPASSFILE", "PGSERVICE",
                     "PGSERVICEFILE", "PGSYSCONFDIR", "PGOPTIONS", "PGSSLMODE", "PGSSLROOTCERT", "PGSSLCERT",
                     "PGTARGETSESSIONATTRS", "PGHOSTADDR", "PGCONNECT_TIMEOUT", "PGAPPNAME", "pghost", "PgSslMode"):
            with self.subTest(name=name):
                self.refused("libpq_environment_present", environment={name: ""})
        for snapshot in ([("PATH", "x")], {"PATH": 1}, {1: "x"}, "PGHOST=x"):
            with self.subTest(snapshot=repr(snapshot)[:20]):
                with self.assertRaises(ops.OpsTargetRefused) as caught:
                    ops.check_preconnect(GOOD, TARGET, snapshot)
                self.assertEqual(caught.exception.code, "environment_snapshot_invalid")
        self.refused("libpq_environment_present", environment={"PGPASSWORD": SECRET})


class Alternatives(Base):
    def test_multi_host_socket_and_substitutes(self):
        self.refused("conninfo_host_not_single_direct", dsn(host="db.synthetic.test:5432,db2.synthetic.test"))
        self.refused("conninfo_host_not_single_direct", dsn(host="%2Ftmp"))
        self.refused("conninfo_host_not_single_direct", dsn(host="[::1]"))
        self.refused("conninfo_host_not_single_direct", dsn(host="db%2Esynthetic.test"))
        for key, value in (("host", "other.synthetic.test"), ("port", "5433"), ("dbname", "other"),
                           ("user", "ops_write_prb"), ("password", "x")):
            with self.subTest(key=key):
                self.refused("conninfo_parameter_conflict",
                             dsn(query=f"sslmode=verify-full&sslrootcert={ROOT}&{key}={value}"))
        for key in ("hostaddr", "service", "servicefile", "passfile", "options", "target_session_attrs",
                    "load_balance_hosts", "sslcert", "sslkey", "sslnegotiation", "requiressl", "gssencmode",
                    "connect_timeout", "application_name", "bogus"):
            with self.subTest(key=key):
                self.refused("conninfo_parameter_not_allowed",
                             dsn(query=f"sslmode=verify-full&sslrootcert={ROOT}&{key}=x"))

    def test_unsupported_forms(self):
        self.refused("conninfo_format_unsupported", GOOD.replace("postgresql://", "postgres://"))
        self.refused("conninfo_format_unsupported", GOOD.replace("postgresql://", "POSTGRESQL://"))
        self.refused("conninfo_format_unsupported",
                     f"host=db.synthetic.test port=5432 dbname=jp_vocab user=ops_read password={SECRET} "
                     f"sslmode=verify-full sslrootcert={ROOT}")
        self.refused("conninfo_format_unsupported", GOOD + "#frag")


class ParserBoundaries(Base):
    def test_duplicate_and_conflicting(self):
        self.refused("conninfo_parameter_duplicate",
                     dsn(query=f"sslmode=require&sslmode=verify-full&sslrootcert={ROOT}"))
        self.refused("conninfo_parameter_duplicate",
                     dsn(query=f"sslmode=verify-full&sslrootcert={ROOT}&sslrootcert={ROOT}"))
        self.refused("conninfo_credentials_required", dsn(password="a:b"))
        self.refused("conninfo_credentials_required", dsn(password="a@b"))

    def test_invalid_utf8_in_query_is_a_fixed_refusal(self):
        """Review fix: bytes that are not UTF-8 must not escape as UnicodeDecodeError nor be
        accepted as replacement characters."""
        for value in ("%FF", "%FE", "%C0%AF",          # reported cases
                      "%E2%82", "%F0%9F%98", "%C3",     # truncated sequences
                      "%ED%A0%80", "%F8%88%80%80%80",   # surrogate / over-long
                      "C:/ops/%FFroot.pem"):
            with self.subTest(value=value):
                self.refused("conninfo_unparseable", dsn(query=f"sslmode=verify-full&sslrootcert={value}"))
                self.refused("conninfo_unparseable", dsn(query=f"sslmode=verify-full&sslrootcert={value}"),
                             target=replace(TARGET, sslrootcert="x"))
        # each layer refuses on its own: the structural pre-scan and the libpq parse
        for value in ("%FF", "%C0%AF", "%E2%82"):
            with self.subTest(layer="structure", value=value):
                with self.assertRaises(ops.OpsTargetRefused) as caught:
                    ops._structure(dsn(query=f"sslmode=verify-full&sslrootcert={value}"))
                self.assertEqual(caught.exception.code, "conninfo_unparseable")
            with self.subTest(layer="libpq", value=value):
                with self.assertRaises(ops.OpsTargetRefused) as caught:
                    ops._libpq_parse(dsn(query=f"sslmode=verify-full&sslrootcert={value}"))
                self.assertEqual(caught.exception.code, "conninfo_unparseable")
        for value in ("%", "%F", "%G0", "%%41", "a%2"):  # broken percent notation
            with self.subTest(value=value):
                self.refused("conninfo_unparseable", dsn(query=f"sslmode=verify-full&sslrootcert={value}"))
        for password in ("%FF", "%C0%AF", "%E2%82", SECRET + "%FE"):
            with self.subTest(password=password[:6]):
                self.refused("conninfo_unparseable", dsn(password=password))
        # valid UTF-8 still decodes and reaches the exact (ASCII) root comparison; plain encoding passes
        self.refused("tls_root_mismatch", dsn(query="sslmode=verify-full&sslrootcert=C:/ops/%C3%A9.pem"))
        encoded_root = "C%3A%2Fops%2Ftls%2Fsynthetic-root.pem"
        self.assertEqual(ops.check_preconnect(dsn(query=f"sslmode=verify-full&sslrootcert={encoded_root}"),
                                              TARGET, {}).sslrootcert, ROOT)

    def test_percent_encoding_boundaries(self):
        self.refused("conninfo_encoding_not_allowed", dsn(user="ops%5Fread"))
        self.refused("conninfo_encoding_not_allowed", dsn(db="jp%5Fvocab"))
        self.refused("conninfo_unparseable", dsn(password="bad%zz"))
        self.refused("conninfo_unparseable", dsn(password="bad%00"))
        self.refused("conninfo_unparseable", dsn(password="%ff%fe"))
        # '+' means space to the query parser but not to libpq: refused as ambiguous, not guessed
        self.refused("conninfo_parse_ambiguous", dsn(query="sslmode=verify-full&sslrootcert=C:/ops/a+b.pem"),
                     target=replace(TARGET, sslrootcert="C:/ops/a+b.pem"))
        self.refused("conninfo_unparseable", dsn(query="sslmode=verify-full&&sslrootcert=x"))

    def test_port_shapes(self):
        for port in ("05432", "0", "65536", "54x2", "-1", "99999"):
            with self.subTest(port=port):
                with self.assertRaises(ops.OpsTargetRefused) as caught:
                    ops.check_preconnect(dsn(port=port), TARGET, {})
                self.assertIn(caught.exception.code, ("conninfo_port_invalid", "conninfo_unparseable"))
                self.assertNotIn(SECRET, repr(caught.exception))


class Types(Base):
    def test_wrong_types_empty_and_control(self):
        for value in (None, b"postgresql://x", 1, True, ["postgresql://"], {"host": "x"}, "",
                      GOOD.replace("jp_vocab", "jp_vocab\n"), GOOD.replace(SECRET, SECRET + "\t"),
                      GOOD.replace(SECRET, SECRET + "\x00"), GOOD.replace(SECRET, SECRET + "é"),
                      GOOD + "&" + "x" * ops.MAX_LENGTH):
            with self.subTest(value=repr(value)[:25]):
                self.refused("conninfo_value_invalid", value)


class Secrets(Base):
    def test_no_secret_in_any_refusal(self):
        cases = [dsn(host="db2.synthetic.test"), dsn(query="bogus=1"), dsn(password="bad%zz" + SECRET),
                 dsn(query=f"sslmode=verify-full&sslrootcert={ROOT}&password={SECRET}"), GOOD + "#" + SECRET,
                 "postgres://" + SECRET, f"host=x password={SECRET}"]
        for secret in cases:
            with self.subTest(index=cases.index(secret)):
                with self.assertRaises(ops.OpsTargetRefused) as caught:
                    ops.check_preconnect(secret, TARGET, {})
                self.assertNotIn(SECRET, repr(caught.exception) + str(caught.exception))
                self.assertTrue(caught.exception.__suppress_context__ or caught.exception.__context__ is None)

    def test_connect_guard_is_armed(self):
        for call in (lambda: psycopg.connect(GOOD), lambda: psycopg.Connection.connect(GOOD),
                     lambda: psycopg.pq.PGconn.connect(b""), lambda: psycopg.generators.connect(b"")):
            with self.assertRaises(AssertionError):
                call()

    def test_module_reads_nothing_and_connects_nowhere(self):
        source = (SCRIPTS_DIR / "_ops_target.py").read_text(encoding="utf-8")
        for forbidden in ("os.environ", "getenv", "open(", "socket", "getaddrinfo", "from app",
                          "import app", "subprocess", "ssl.", "Path("):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)
        self.assertIsNone(re.search(r"\bconnect(_start)?\(", source))  # check_preconnect( is not a call to connect


if __name__ == "__main__":
    unittest.main()

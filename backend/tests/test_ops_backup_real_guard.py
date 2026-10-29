"""Fake-only checks for the backup / restore rehearsal runner (tests/_ops_backup_real.py). No database,
no pg_dump / pg_restore, no cluster: connect entry points, `subprocess` and process facts are patched;
only temporary synthetic files are written.

Run directly:      python tests/test_ops_backup_real_guard.py
Or via discovery:   python -m unittest discover -s tests
"""

from __future__ import annotations

import contextlib
import inspect
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

TESTS_DIR = Path(__file__).resolve().parent
BACKEND = TESTS_DIR.parent
sys.path.insert(0, str(BACKEND / "scripts"))
sys.path.insert(0, str(TESTS_DIR))

import psycopg  # noqa: E402

import _ops_backup_real as br  # noqa: E402
import _ops_pg62 as g  # noqa: E402

T = g.PG64_BACKUP
RUN = "20261024T120000"


def forbidden(*_, **__):
    raise AssertionError("a connection / process function was called")


class Blocked(unittest.TestCase):
    def setUp(self):
        for patch in (mock.patch.object(psycopg, "connect", forbidden), mock.patch.object(subprocess, "Popen", forbidden),
                      mock.patch.object(subprocess, "run", forbidden),
                      mock.patch.object(g, "server_is_ours", lambda pid, target=None: pid == 7777 and target is T),
                      mock.patch.dict(os.environ, {k: v for k, v in os.environ.items()
                                                   if not k.upper().startswith("PG")}, clear=True)):
            patch.start()
            self.addCleanup(patch.stop)


class Targets(Blocked):
    def test_closed_presets(self):
        # pg65 added by C12-1, pg66 (RS4-1), pg67 (lexeme L-1), pg68 (access lock V1)
        self.assertEqual(g.PRESETS, (g.PG62, g.PG63_AUDIT, g.PG64_BACKUP, g.PG65_APPLY,
                         g.PG66_RESUME, g.PG67_RESUME_LEXEME, g.PG68_LEXEME_ACCESS_LOCK))
        self.assertEqual((T.root, T.port, T.databases, T.admin, T.provider_roles),
                         (Path("C:/JV_Tools/pg64"), 55482,
                          ("jp_vocab_test_br_src", "jp_vocab_test_br_dst", "jp_vocab_test_br_fail"), "jpvb_admin",
                          ("jpvb_audit",)))
        for copy in (replace(T), replace(T, port=55483), replace(T, root=Path("C:/JV_Tools/pgdata-e2"))):
            with self.subTest(copy=repr(copy)[:30]), self.assertRaises(g.Pg62Refused):
                g.preset(copy)
        self.assertNotIn(T.admin, T.provider_roles)

    def test_child_access_pairs(self):
        self.assertIn("dbname=jp_vocab_test_br_src user=jpvb_backup", br.conninfo(br.SRC, br.BACKUP))
        self.assertIn("dbname=jp_vocab_test_br_dst user=jpvb_admin", br.conninfo(br.DST, br.ADMIN))
        for db, role in ((br.DST, br.BACKUP), (br.FAIL, br.BACKUP), (br.SRC, br.ADMIN), ("postgres", br.ADMIN),
                         (br.SRC, br.AUDIT), (br.DST, br.AUDIT), (br.SRC, "jpvb_owner"), ("jp_vocab_test_e", br.ADMIN),
                         ("jp_vocab_test_62a", br.BACKUP)):
            with self.subTest(db=db, role=role), self.assertRaises(g.Pg62Refused):
                br.conninfo(db, role)

    def test_connection_strings_carry_no_secret_and_pin_tls(self):
        for text in (br.conninfo(br.SRC, br.BACKUP), br.conninfo(br.DST, br.ADMIN), br.conninfo(br.FAIL, br.ADMIN)):
            self.assertNotIn("password", text.lower())
            self.assertIn("host=localhost port=55482", text)
            self.assertIn("sslmode=verify-full sslrootcert=C:/JV_Tools/pg64/tls/ca.crt", text)
            self.assertIn("gssencmode=disable", text)

    def test_runner_has_no_target_inputs(self):
        source = re.sub(r'"""[\s\S]*?"""', "", (TESTS_DIR / "_ops_backup_real.py").read_text(encoding="utf-8"))
        for text in ("argparse", "getenv(", "environ.get(", "Target(", "replace(T", "pg_dumpall", "shell=True",
                     "DATABASE_URL"):
            with self.subTest(text=text):
                self.assertNotIn(text, source)
        self.assertIn("T = g.PG64_BACKUP", source)


class Arguments(Blocked):
    def test_dump_arguments(self):
        args = br.dump_args(RUN)
        self.assertEqual(args[:4], [str(g.BIN / "pg_dump.exe"), "--format=custom", "--no-password",
                                    "--exclude-table-data=jp_vocab_ops_synthetic.db_identity"])
        self.assertEqual(args[4], f"--file={T.root / 'dumps' / RUN / 'src.dump'}")
        self.assertTrue(args[5].startswith("--dbname=host=localhost port=55482 dbname=jp_vocab_test_br_src user=jpvb_backup"))
        self.assertFalse(any(a in ("--clean", "--create") for a in args))
        for bad in ("../x", "20261024T1200", "pg62", ""):
            with self.subTest(run=bad), self.assertRaises(g.Pg62Refused):
                br.dump_path(bad)

    def test_restore_arguments(self):
        dump = br.dump_path(RUN)
        for db in (br.DST, br.FAIL):
            args = br.restore_args(db, dump)
            self.assertEqual(args[:4], [str(g.BIN / "pg_restore.exe"), "--single-transaction", "--exit-on-error",
                                        "--no-password"])
            self.assertIn(f"dbname={db} user=jpvb_admin", args[4])
            self.assertEqual(args[5], str(dump))
            self.assertFalse(any(a in ("--clean", "--create") for a in args))
        for db in (br.SRC, "postgres", "jp_vocab_test_62a"):
            with self.subTest(db=db), self.assertRaises(g.Pg62Refused):
                br.restore_args(db, dump)
        with self.assertRaises(g.Pg62Refused):
            br.restore_args(br.DST, Path("C:/Users/x/elsewhere/src.dump"))
        self.assertEqual(br.list_args(dump), [str(g.BIN / "pg_restore.exe"), "--list", str(dump)])

    def test_child_environment_drops_every_pg_variable(self):
        env = br.child_env({"PATH": "C:/Windows", "PGPASSWORD": "x", "pgpassfile": "y", "PgHost": "z", "PGSSLMODE": "w"})
        self.assertEqual(env, {"PATH": "C:/Windows"})


class FakeChild:
    def __init__(self, code=0, err="", hang=0):
        self.returncode, self.err, self.hang, self.killed, self.calls = None, err, hang, False, 0
        self.code = code

    def communicate(self, timeout=None):
        self.calls += 1
        if self.hang and (not self.killed or self.hang == 2):
            raise subprocess.TimeoutExpired("x", timeout)
        self.returncode = -9 if self.killed else self.code
        return "toc", self.err

    def kill(self):
        self.killed = True


class Children(Blocked):
    def popen(self, child):
        calls = []

        def fake(args, **kwargs):
            calls.append((args, kwargs))
            return child
        return fake, calls

    def test_fixed_arguments_no_shell_clean_environment(self):
        fake, calls = self.popen(FakeChild())
        with mock.patch.dict(os.environ, {"PGHOST": "elsewhere"}):
            with self.assertRaises(g.Pg62Refused):                   # parent PG variable: refused before start
                br.run_child(br.dump_args(RUN), 10, 7777, popen=fake)
        self.assertEqual(calls, [])
        code, label, out = br.run_child(br.dump_args(RUN), 10, 7777, popen=fake)
        args, kwargs = calls[0]
        self.assertEqual((code, label, args, kwargs["shell"]), (0, "none", br.dump_args(RUN), False))
        self.assertFalse(any(k.upper().startswith("PG") for k in kwargs["env"]))

    def test_precheck_and_argument_refusals(self):
        fake, calls = self.popen(FakeChild())
        for args, pid in ((br.dump_args(RUN), 7778), (["cmd.exe", "/c", "dir"], 7777),
                          (br.restore_args(br.DST, br.dump_path(RUN)) + ["--clean"], 7777)):
            with self.subTest(args=args[0]), self.assertRaises(g.Pg62Refused):
                br.run_child(args, 10, pid, popen=fake)
        self.assertEqual(calls, [])

    def test_timeout_and_unconfirmed_end(self):
        fake, _ = self.popen(FakeChild(hang=1))
        with self.assertRaises(br.CheckFailed) as caught:
            br.run_child(br.dump_args(RUN), 1, 7777, popen=fake)
        self.assertEqual(caught.exception.what, "child timed out; ended after kill attempt")
        child = FakeChild(hang=2)
        fake, _ = self.popen(child)
        with self.assertRaises(br.CheckFailed) as caught:
            br.run_child(br.dump_args(RUN), 1, 7777, popen=fake)
        self.assertEqual((caught.exception.kind, caught.exception.what, child.killed),
                         ("harness_defect", "child timed out; end unconfirmed", True))

    def test_failure_is_returned_with_a_fixed_label_only(self):
        fake, _ = self.popen(FakeChild(code=1, err='pg_restore: error: relation "users" already exists secret-x'))
        code, label, _ = br.run_child(br.restore_args(br.FAIL, br.dump_path(RUN)), 10, 7777, popen=fake)
        self.assertEqual((code, label), (1, "relation_already_exists"))


SNAP = {"rows": {"public.users": (2, "aa"), "public.vocab_items": (3, "bb")},
        "columns": {"public.users.id": "integer|NO|", "public.users.email": "text|YES|"},
        "constraints": {"public.users.users_pkey": "p|PRIMARY KEY (id)"},
        "indexes": {"public.users_pkey": "CREATE UNIQUE INDEX users_pkey ON public.users USING btree (id)"},
        "owners": {"public.users": "jpvb_owner"}, "acls": {"public.users": "{jpvb_owner=arwdDxtm/jpvb_owner}"},
        "sequences": {"users_id_seq": {"last_value": 2, "is_called": True, "increment": 1}}}


class Comparisons(unittest.TestCase):
    def copy(self):
        import copy
        return copy.deepcopy(SNAP)

    def test_identical_snapshots(self):
        self.assertEqual(br.compare_snapshots(SNAP, self.copy()), [])

    def test_every_section_difference_is_reported(self):
        cases = {
            "rows: public.users": lambda s: s["rows"].update({"public.users": (3, "aa")}),
            "rows: public.vocab_items": lambda s: s["rows"].update({"public.vocab_items": (3, "cc")}),
            "columns: public.users.email": lambda s: s["columns"].update({"public.users.email": "text|NO|"}),
            "constraints: public.users.users_pkey": lambda s: s["constraints"].pop("public.users.users_pkey"),
            "indexes: public.users_pkey": lambda s: s["indexes"].update({"public.users_pkey": "CREATE INDEX x"}),
            "owners: public.users": lambda s: s["owners"].update({"public.users": "jpvb_admin"}),
            "acls: public.users": lambda s: s["acls"].update({"public.users": ""}),
            "sequences: users_id_seq": lambda s: s["sequences"]["users_id_seq"].update(is_called=False),
            "rows: public.extra": lambda s: s["rows"].update({"public.extra": (0, "")}),
            "rows: missing": lambda s: s.pop("rows"),
        }
        for expected, change in cases.items():
            with self.subTest(expected=expected):
                other = self.copy()
                change(other)
                self.assertEqual(br.compare_snapshots(SNAP, other), [expected])

    def test_next_id_from_stored_state(self):
        seq = {"users_id_seq": {"last_value": 5, "is_called": True, "increment": 1},
               "decks_id_seq": {"last_value": 1, "is_called": False, "increment": 1}}
        self.assertEqual(br.next_id_ok(seq, {"users": 5, "decks": None}), [])
        self.assertEqual(br.next_id_ok(seq, {"users": 6}), ["users: next 6 <= max 6"])
        self.assertEqual(br.next_id_ok({"decks_id_seq": {"last_value": 3, "is_called": False, "increment": 1}},
                                       {"decks": 3}), ["decks: next 3 <= max 3"])
        self.assertEqual(br.next_id_ok({}, {"users": 1}), ["users: sequence missing"])
        code = re.sub(r'"""[\s\S]*?"""', "", (TESTS_DIR / "_ops_backup_real.py").read_text(encoding="utf-8"))
        code = re.sub(r"#.*", "", code)
        self.assertNotIn("nextval(", code)                          # no sequence is advanced or set to check it
        self.assertNotIn("setval(", code)

    def test_identity_handling(self):
        self.assertEqual(br.identity_ok(["src-1"], [], ["dst-2"], "dst-2"), [])
        self.assertIn("identity data was copied into the restore", br.identity_ok(["src-1"], ["src-1"], ["src-1", "dst-2"], "dst-2"))
        self.assertIn("restore identity is not its own new value", br.identity_ok(["x"], [], ["x"], "x"))
        self.assertIn("source identity rows != 1", br.identity_ok([], [], ["d"], "d"))
        self.assertIn("identity data was copied into the restore", br.identity_ok(["s"], ["<unreadable>"], ["d"], "d"))

    def test_b8_accepts_only_the_planned_conflict(self):
        state = {"schemas": ["public"], "relations": ["public.users"], "snapshot": SNAP}
        self.assertEqual(br.b8_expected_failure(1, "relation_already_exists", state, state), [])
        self.assertTrue(br.b8_expected_failure(0, "none", state, state))
        self.assertTrue(br.b8_expected_failure(1, "permission_denied", state, state))
        self.assertTrue(br.b8_expected_failure(1, "connect_failed", state, state))
        moved = dict(state, relations=["public.decks", "public.users"])
        self.assertTrue(br.b8_expected_failure(1, "relation_already_exists", state, moved))
        self.assertTrue(br.b8_expected_failure(1, "relation_already_exists", moved, moved))   # not the planned setup


class ChildArgumentGate(Blocked):
    """run_child itself re-validates the whole argument array before Popen (no trust in the builders)."""

    def popen(self):
        calls = []

        def fake(args, **kwargs):
            calls.append(args)
            return FakeChild()
        return fake, calls

    def test_exact_forms_pass(self):
        fake, calls = self.popen()
        dump = br.dump_path(RUN)
        for args in (br.dump_args(RUN), br.list_args(dump), br.restore_args(br.DST, dump), br.restore_args(br.FAIL, dump)):
            br.run_child(args, 10, 7777, popen=fake)
        self.assertEqual(len(calls), 4)

    def test_changed_arguments_are_refused_before_popen(self):
        fake, calls = self.popen()
        dump = br.dump_path(RUN)
        good_dump, good_restore = br.dump_args(RUN), br.restore_args(br.DST, dump)
        src_admin = good_dump[5].replace("user=jpvb_backup", "user=jpvb_admin")
        cases = {
            "dump to another DB": good_dump[:5] + [good_dump[5].replace("br_src", "br_dst")],
            "dump as admin": good_dump[:5] + [src_admin],
            "dump extra arg": good_dump + ["--schema-only"],
            "dump duplicate arg": good_dump + [good_dump[1]],
            "dump other file": good_dump[:4] + [f"--file={br.DUMPS / RUN / 'other.dump'}", good_dump[5]],
            "dump without exclusion": good_dump[:3] + good_dump[4:],
            "dump host override": good_dump + ["--host=elsewhere"],
            "dump port override": good_dump + ["-p", "55432"],
            "restore to source": good_restore[:4] + [good_restore[4].replace("br_dst", "br_src"), good_restore[5]],
            "restore as backup": good_restore[:4] + [good_restore[4].replace("user=jpvb_admin", "user=jpvb_backup"),
                                                     good_restore[5]],
            "restore -c": good_restore[:1] + ["-c"] + good_restore[1:],
            "restore --clean": good_restore[:1] + ["--clean"] + good_restore[1:],
            "restore -C": good_restore[:1] + ["-C"] + good_restore[1:],
            "restore --create": good_restore[:1] + ["--create"] + good_restore[1:],
            "restore without single transaction": [good_restore[0]] + good_restore[2:],
            "restore other dump": good_restore[:5] + ["C:/elsewhere/src.dump"],
            "restore second dbname": good_restore + ["--dbname=host=localhost dbname=jp_vocab_test_br_src"],
            "list with connection": br.list_args(dump) + ["--dbname=host=localhost"],
            "list other file": [str(br.PG_RESTORE), "--list", "C:/Users/x/a.dump"],
            "other executable": [str(g.BIN / "psql.exe")] + good_dump[1:],
            "pg_dumpall": [str(g.BIN / "pg_dumpall.exe")] + good_dump[1:],
        }
        for label, args in cases.items():
            with self.subTest(case=label), self.assertRaises(g.Pg62Refused):
                br.run_child(args, 10, 7777, popen=fake)
        self.assertEqual(calls, [])


class ChildEnding(Blocked):
    class Child:
        def __init__(self, *, communicate=(), kill_error=None):
            self.plan, self.kill_error, self.killed, self.returncode = list(communicate), kill_error, 0, None

        def communicate(self, timeout=None):
            step = self.plan.pop(0) if self.plan else "ok"
            if isinstance(step, BaseException):
                raise step
            if step == "hang":
                raise subprocess.TimeoutExpired("x", timeout)
            self.returncode = 0
            return "", ""

        def kill(self):
            self.killed += 1
            if self.kill_error is not None:
                raise self.kill_error

    def run_it(self, child):
        return br.run_child(br.dump_args(RUN), 1, 7777, popen=lambda *a, **k: child)

    def test_start_failure(self):
        def fails(*a, **k):
            raise OSError(2, "secret path C:/x")
        with self.assertRaises(br.CheckFailed) as caught:
            br.run_child(br.dump_args(RUN), 1, 7777, popen=fails)
        self.assertEqual((caught.exception.kind, caught.exception.what), ("harness_defect", "child start failed"))

    def test_timeout_kill_failure_still_reaps(self):
        child = self.Child(communicate=["hang", "ok"], kill_error=OSError(5, "secret"))
        with self.assertRaises(br.CheckFailed) as caught:
            self.run_it(child)
        self.assertEqual(caught.exception.what, "child timed out; ended after kill attempt")
        self.assertEqual((child.killed, child.plan), (1, []))

    def test_timeout_unconfirmed_end(self):
        child = self.Child(communicate=["hang", "hang"])
        with self.assertRaises(br.CheckFailed) as caught:
            self.run_it(child)
        self.assertEqual(caught.exception.what, "child timed out; end unconfirmed")

    def test_communication_and_reap_errors_have_fixed_reasons(self):
        child = self.Child(communicate=[OSError(32, "secret pipe"), OSError(5, "secret reap")])
        with self.assertRaises(br.CheckFailed) as caught:
            self.run_it(child)
        self.assertEqual(caught.exception.what, "child communication failed; end unconfirmed")
        self.assertNotIn("secret", repr(caught.exception))
        self.assertTrue(caught.exception.__suppress_context__ or caught.exception.__context__ is None)

    def test_interrupt_is_propagated_after_cleanup(self):
        stop = KeyboardInterrupt()
        child = self.Child(communicate=[stop, "ok"])
        with self.assertRaises(KeyboardInterrupt) as caught:
            self.run_it(child)
        self.assertIs(caught.exception, stop)
        self.assertEqual((child.killed, child.plan), (1, []))

    def test_no_process_search(self):
        code = re.sub(r'"""[\s\S]*?"""', "", (TESTS_DIR / "_ops_backup_real.py").read_text(encoding="utf-8"))
        for text in ("taskkill", "os.kill(", "psutil", "listener_pids(", "tasklist"):
            if text == "listener_pids(":
                body = code[code.index("def run_child"):code.index("# --- structured")]
                self.assertNotIn(text, body)
            else:
                self.assertNotIn(text, code)


class ColumnMetadata(unittest.TestCase):
    ROW = {"data_type": "integer", "udt_schema": "pg_catalog", "udt_name": "int4", "character_maximum_length": None,
           "numeric_precision": 32, "numeric_scale": 0, "datetime_precision": None, "is_nullable": "NO",
           "column_default": None, "is_identity": "YES", "identity_generation": "BY DEFAULT",
           "identity_start": "1", "identity_increment": "1", "is_generated": "NEVER", "generation_expression": None}

    def test_each_attribute_changes_the_value(self):
        base = br.column_value(self.ROW)
        for key, value in (("is_identity", "NO"), ("identity_generation", "ALWAYS"), ("identity_increment", "2"),
                           ("character_maximum_length", 40), ("numeric_precision", 64), ("numeric_scale", 2),
                           ("udt_name", "int8"), ("data_type", "bigint"), ("datetime_precision", 3),
                           ("is_nullable", "YES"), ("column_default", "0"), ("is_generated", "ALWAYS")):
            with self.subTest(key=key):
                self.assertNotEqual(br.column_value({**self.ROW, key: value}), base)

    def test_missing_attribute_is_an_error(self):
        row = dict(self.ROW)
        row.pop("identity_generation")
        with self.assertRaises(KeyError):
            br.column_value(row)

    def test_identity_only_difference_fails_the_comparison(self):
        import copy
        src = copy.deepcopy(SNAP)
        src["columns"] = {"public.users.id": br.column_value(self.ROW)}
        dst = copy.deepcopy(src)
        dst["columns"] = {"public.users.id": br.column_value({**self.ROW, "is_identity": "NO", "identity_generation": None})}
        self.assertEqual(br.compare_snapshots(src, dst), ["columns: public.users.id"])

    def test_collector_reads_every_attribute(self):
        sql_text = br.SNAP_SQL["columns"]
        for key in self.ROW:
            self.assertIn(key, sql_text)



class CollectorConcatenation(unittest.TestCase):
    """String checks only: they fix the "char" cast in place but are not PostgreSQL syntax or type
    checking. Whether every collector query runs is decided by the real-PG preparation gate."""
    CHAR_COLUMNS = r"(?:\w+\.)?(?:contype|relkind|relpersistence|relreplident|confupdtype|confdeltype|confmatchtype)"

    def test_constraint_type_is_cast_to_text(self):
        self.assertIn("con.contype::text || '|' ||", br.SNAP_SQL["constraints"])

    def test_no_uncast_char_column_next_to_concatenation(self):
        texts = dict(br.SNAP_SQL)
        texts["user_relations"] = inspect.getsource(br.user_relations)
        bare = re.compile(rf"{self.CHAR_COLUMNS}(?!::)\s*\|\||\|\|\s*{self.CHAR_COLUMNS}(?!::)")
        for name, text in texts.items():
            with self.subTest(query=name):
                self.assertIsNone(bare.search(text))


class B8Evidence(unittest.TestCase):
    BEFORE = {"schemas": ["public"], "relations": ["public.users"],
              "snapshot": {"rows": {"public.users": (0, "d41d8cd98f00b204e9800998ecf8427e")},
                           "columns": {"public.users.conflict": "integer|..."}, "constraints": {}, "indexes": {},
                           "owners": {"public.users": "jpvb_admin"}, "acls": {"public.users": ""}, "sequences": {}}}

    def after(self, change=None):
        import copy
        state = copy.deepcopy(self.BEFORE)
        if change:
            change(state)
        return state

    def test_planned_conflict_and_full_rollback(self):
        self.assertEqual(br.b8_expected_failure(1, "relation_already_exists", self.BEFORE, self.after()), [])

    def test_changes_left_behind_are_detected(self):
        cases = {
            "users definition": lambda s: s["snapshot"]["columns"].update({"public.users.email": "text|..."}),
            "users content": lambda s: s["snapshot"]["rows"].update({"public.users": (1, "abc")}),
            "new schema": lambda s: s["schemas"].append("jp_vocab_ops_synthetic"),
            "new relation": lambda s: s["relations"].append("public.decks"),
            "users owner": lambda s: s["snapshot"]["owners"].update({"public.users": "jpvb_owner"}),
        }
        for label, change in cases.items():
            with self.subTest(case=label):
                self.assertIn("rollback not confirmed", br.b8_expected_failure(1, "relation_already_exists",
                                                                               self.BEFORE, self.after(change)))

    def test_wrong_cause_or_success(self):
        self.assertTrue(br.b8_expected_failure(0, "none", self.BEFORE, self.after()))
        self.assertTrue(br.b8_expected_failure(1, "permission_denied", self.BEFORE, self.after()))



class FakeResult:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return list(self.rows)

    def fetchone(self):
        return self.rows[0]


class FakeConn:
    """Answers the collector queries of one DB by their text. Control-flow evidence only: nothing here
    parses, plans or type-checks SQL the way PostgreSQL does."""
    TABLES = [f"public.{t}" for t in br.real.CORE_TABLES + br.real.SRS_TABLES]
    COLUMN = {"k": "public.users.id", **{name: None for name in br.COLUMN_ATTRIBUTES}}

    def __init__(self, db, log, fail, data):
        self.db, self.log, self.fail, self.data = db, log, fail, data

    def key(self, query):
        if not isinstance(query, str):
            text = repr(query)
            for key, mark in (("rows", "count(*)"), ("last_value", "last_value"), ("max_id", "max(id)")):
                if mark in text:
                    return key
            raise AssertionError("unexpected composed query")
        for key, text in br.SNAP_SQL.items():
            if query == text:
                return key
        for key, mark in (("identity", "SELECT identity_value"), ("relations", "relkind IN ('r','p','v','m','S','f')"),
                          ("schemas", "WHERE nspname <> 'information_schema'"), ("seqincrement", "seqincrement")):
            if mark in query:
                return key
        raise AssertionError("unexpected query")

    def execute(self, query, params=None):
        key = self.key(query)
        self.log.append(f"query:{self.db}:{key}")
        if (self.db, key) == self.fail:
            raise RuntimeError("secret driver text")
        return FakeResult(self.data[key])

    @contextlib.contextmanager
    def cursor(self, row_factory=None):
        conn = self

        class Cursor:
            def execute(self, query, params=None):
                self.result = conn.execute(query, params)

            def fetchall(self):
                return self.result.fetchall()
        yield Cursor()


def source_data():
    tables = FakeConn.TABLES + [f"{br.SYN}.db_identity"]
    return {"tables": [(t,) for t in tables], "rows": [(2, "aa")], "columns": [FakeConn.COLUMN],
            "constraints": [("public.users.users_pkey", "p|PRIMARY KEY (id)")],
            "indexes": [("public.users_pkey", "CREATE UNIQUE INDEX users_pkey ON public.users USING btree (id)")],
            "owners": [("public.users", "jpvb_owner")], "acls": [("public.users", "")],
            "sequences": [("public.users_id_seq",)], "last_value": [(5, True)], "seqincrement": [(1,)],
            "max_id": [(3,)], "identity": [("pg64-src-abc",)], "relations": [(t,) for t in sorted(tables)],
            "schemas": [(br.SYN,), ("public",)]}


def empty_data():
    data = {key: [] for key in ("tables", "columns", "constraints", "indexes", "owners", "acls", "sequences",
                                "relations")}
    data["schemas"], data["rows"] = [("public",)], [(1, "x")]       # rows answers only if a table appears
    return data


class BaselineGate(Blocked):
    """Order and stop rules of the pre-dump baseline gate with fake connections. This is control-flow
    evidence only, NOT evidence that any collector SQL runs on a real PostgreSQL."""

    def setUp(self):
        super().setUp()
        tmp = Path(tempfile.mkdtemp(prefix="ops_backup_gate_test_"))
        self.addCleanup(shutil.rmtree, tmp)
        folder = tmp / RUN
        folder.mkdir()
        (tmp / "dumps").mkdir()
        (folder / "target.json").write_text(json.dumps({"postmaster_pid": 7777, "databases": {
            br.SRC: {"identity_value": "pg64-src-abc"}, br.DST: {"identity_value": "pg64-dst-abc"}}}), encoding="utf-8")
        self.rec, self.log, self.fail_step = g.Record(folder), [], None
        self.data = {br.SRC: source_data(), br.DST: empty_data(), br.FAIL: empty_data()}
        self.record_fails_on = None
        append = self.rec._append

        def logged(key, entry):
            label = f"record:{entry.get('check', entry.get('kind'))}:{entry.get('status', '')}"
            if label == self.record_fails_on:
                self.record_fails_on = None
                raise OSError(28, "disk full")
            append(key, entry)
            self.log.append(label)
        self.rec._append = logged

        @contextlib.contextmanager
        def admin(db, pid, autocommit=True):
            self.log.append(f"admin:{db}")
            yield FakeConn(db, self.log, self.fail_step, self.data[db])

        def child(args, timeout, pid, popen=None):
            self.log.append("child")
            raise br.CheckFailed("harness_defect", "test stops after the first child")
        for patch in (mock.patch.object(g, "single_run", lambda target=None: self.rec),
                      mock.patch.object(br, "admin", admin), mock.patch.object(br, "run_child", child),
                      mock.patch.object(br, "dump_path", lambda run_id: tmp / "dumps" / run_id / "src.dump")):
            patch.start()
            self.addCleanup(patch.stop)

    def results(self):
        return [(r["check"], r["status"], r.get("kind")) for r in self.rec.doc["results"]]

    def test_collect_then_record_then_first_child(self):
        with mock.patch("builtins.print"):
            self.assertEqual(br.check(), 0)                         # b1 stopped by the fake child
        gate_pass = self.log.index("record:baseline_gate:pass")
        first_child = self.log.index("child")
        self.assertLess(gate_pass, first_child)
        self.assertEqual(self.log.count("child"), 1)
        self.assertFalse([e for e in self.log[gate_pass:first_child] if e.startswith(("admin:", "query:"))])
        collected = self.log[:gate_pass]
        for db in (br.SRC, br.DST, br.FAIL):
            for key in ("tables", "columns", "constraints", "indexes", "owners", "acls", "sequences", "relations",
                        "schemas"):
                self.assertIn(f"query:{db}:{key}", collected)
        self.assertIn(f"query:{br.SRC}:identity", collected)
        self.assertNotIn(f"query:{br.DST}:identity", self.log)     # absent there: normal, not read
        self.assertNotIn(f"query:{br.FAIL}:identity", self.log)
        self.assertEqual(self.results(), [("baseline_gate", "pass", None), ("b1_dump", "fail", "harness_defect")])
        recorded = self.rec.doc["results"][0]["details"]["databases"]
        self.assertEqual(recorded[br.SRC]["identity"], ["pg64-src-abc"])
        self.assertEqual(recorded[br.DST], {"schemas": ["public"], "relations": [], "snapshot": {
            k: {} for k in br.EMPTY_SNAPSHOT_SECTIONS}})
        on_disk = json.loads(self.rec.path.read_text(encoding="utf-8"))
        self.assertEqual(on_disk["results"][0]["details"]["databases"][br.SRC]["snapshot"]["rows"]["public.users"],
                         [2, "aa"])

    def test_source_baseline_is_reused(self):
        state = br.State(self.rec)
        with mock.patch("builtins.print"):
            self.assertTrue(br.base.run_check(self.rec, br.GATE, br.baseline_gate, state))
        state.baseline, state.pending = state.pending, None
        self.log[:] = []
        with self.assertRaises(br.CheckFailed):
            br.b1_dump(state)
        self.assertEqual(self.log, ["child"])                       # no collection before the first child
        self.assertIs(state.src_snap, state.baseline[br.SRC]["snapshot"])
        self.assertIs(state.src_max, state.baseline[br.SRC]["max_ids"])

    def test_b1_refuses_without_a_recorded_gate(self):
        state = br.State(self.rec)
        with mock.patch("builtins.print"):
            self.assertTrue(br.base.run_check(self.rec, br.GATE, br.baseline_gate, state))
        self.log[:] = []
        with self.assertRaises(br.CheckFailed) as caught:           # collected (pending) but never accepted
            br.b1_dump(state)
        self.assertEqual(caught.exception.kind, "harness_defect")
        self.assertEqual(self.log, [])

    def stopped_before_children(self):
        ran = []
        with mock.patch.object(br, "CHECKS", [(n, lambda s, n=n: ran.append(n)) for n in br.PLANNED]), \
                mock.patch("builtins.print"):
            code = br.main(["check"])
        self.assertEqual((code, ran), (1, []))
        self.assertNotIn("child", self.log)
        self.assertNotIn("secret driver text", self.rec.path.read_text(encoding="utf-8"))

    def test_every_collector_failure_stops_everything(self):
        steps = [(br.SRC, k) for k in ("tables", "rows", "columns", "constraints", "indexes", "owners", "acls",
                                       "sequences", "last_value", "seqincrement", "max_id", "identity", "relations",
                                       "schemas")]
        steps += [(db, k) for db in (br.DST, br.FAIL) for k in ("tables", "columns", "constraints", "indexes",
                                                               "owners", "acls", "sequences", "relations", "schemas")]
        for step in steps:
            with self.subTest(step=step):
                self.rec.doc["results"], self.log[:] = [], []
                self.fail_step = step
                self.stopped_before_children()
                self.assertIn(f"query:{step[0]}:{step[1]}", self.log)
                self.assertEqual(self.results(), [("baseline_gate", "error", "harness_defect")])

    def test_state_outside_the_contract_is_a_preparation_failure(self):
        cases = {
            "dst has a relation": (br.DST, "relations", [("public.users",)]),
            "fail has a table": (br.FAIL, "tables", [("public.users",)]),
            "dst has a schema": (br.DST, "schemas", [(br.SYN,), ("public",)]),
            "fail has a column": (br.FAIL, "columns", [FakeConn.COLUMN]),
            "source identity differs": (br.SRC, "identity", [("pg64-src-other",)]),
            "source identity missing": (br.SRC, "identity", []),
            "source table missing": (br.SRC, "relations", [(f"{br.SYN}.db_identity",)]),
            "source schema missing": (br.SRC, "schemas", [("public",)]),
        }
        for label, (db, key, rows) in cases.items():
            with self.subTest(case=label):
                self.rec.doc["results"], self.log[:] = [], []
                saved = self.data[db][key]
                self.data[db][key] = rows
                try:
                    self.stopped_before_children()
                finally:
                    self.data[db][key] = saved
                self.assertEqual(self.results(), [("baseline_gate", "fail", "preparation_failure")])

    def test_gate_record_failure_stops_everything(self):
        self.record_fails_on = "record:baseline_gate:pass"
        self.stopped_before_children()
        self.assertEqual(self.results(), [("baseline_gate", "error", "harness_defect")])

    def test_gate_pass_is_not_counted_as_a_check(self):
        with mock.patch.object(br, "CHECKS", [(n, lambda s: {"ok": True}) for n in br.PLANNED]), \
                mock.patch("builtins.print") as printed:
            self.assertEqual(br.main(["check"]), 0)
        self.assertIn(mock.call(f"passed {len(br.PLANNED)} / {len(br.PLANNED)}"), printed.call_args_list)
        self.assertEqual([r[0] for r in self.results()], ["baseline_gate", *br.PLANNED])

CHILD = r'''
import sys
from pathlib import Path
sys.path.insert(0, {scripts!r}); sys.path.insert(0, {tests!r})
import psycopg
def forbidden(*_, **__):
    raise AssertionError("a connection function was called")
psycopg.connect = forbidden
import _ops_pg62 as g
import _ops_backup_real as br
folder = Path({folder!r})
(folder / "target.json").write_text('{{"postmaster_pid": 1}}', encoding="utf-8")
g.single_run = lambda target=None: g.Record(folder)
g.server_is_ours = lambda pid, target=None: {scenario!r} != "preparation_failure"
g.pg_environment_present = lambda: False
br.baseline_gate = lambda s: {{"gate": "stubbed"}}
def ok(s):
    return {{"ok": True}}
def fail(s):
    raise br.CheckFailed("product_defect", "synthetic difference")
def unrecordable(s):
    return {{"x": object()}}
scenario = {scenario!r}
names = list(br.PLANNED)
special = {{"middle_fail": fail, "record_fail": unrecordable}}.get(scenario)
if scenario == "incomplete":
    br.CHECKS = [(n, ok) for n in names[:-1]]
else:
    br.CHECKS = [(n, special if (special and i == 2) else ok) for i, n in enumerate(names)]
calls = []
real_ok = br.CHECKS
br.CHECKS = [(n, (lambda f, n: (lambda s: (calls.append(n), f(s))[1]))(f, n)) for n, f in real_ok]
code = br.main(["check"])
print("CALLS", calls)
sys.exit(code)
'''


class ExitStatus(unittest.TestCase):
    def run_child(self, scenario):
        tmp = Path(tempfile.mkdtemp(prefix="ops_backup_real_cli_test_"))
        self.addCleanup(shutil.rmtree, tmp)
        code = CHILD.format(scripts=str(BACKEND / "scripts"), tests=str(TESTS_DIR), folder=str(tmp), scenario=scenario)
        done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120, cwd=str(TESTS_DIR))
        self.assertNotIn("a connection function was called", done.stdout + done.stderr)
        calls = re.search(r"CALLS (\[.*\])", done.stdout)
        return done.returncode, (eval(calls.group(1)) if calls else None)

    def test_exit_status_and_nothing_after_a_failure(self):
        code, calls = self.run_child("pass")
        self.assertEqual((code, len(calls)), (0, len(br.PLANNED)))
        for scenario in ("middle_fail", "record_fail"):
            with self.subTest(scenario=scenario):
                code, calls = self.run_child(scenario)
                self.assertEqual((code, calls), (1, list(br.PLANNED[:3])))       # b4.. never ran
        self.assertEqual(self.run_child("incomplete")[0], 1)
        self.assertEqual(self.run_child("preparation_failure")[0], 1)

    def test_import_does_no_external_work(self):
        code = (f"import sys, os, subprocess; sys.path[:0] = [{str(BACKEND / 'scripts')!r}, {str(TESTS_DIR)!r}]\n"
                "import psycopg\ncalls = []\n"
                "def fail(*a, **k): calls.append(1); raise AssertionError('external work at import')\n"
                "psycopg.connect = fail; subprocess.run = fail; subprocess.Popen = fail; os.mkdir = fail\n"
                "import _ops_backup_real\nprint('CALLS', len(calls), 'APP', any(m == 'app' or m.startswith('app.') "
                "for m in sys.modules))")
        done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120, cwd=str(TESTS_DIR))
        self.assertIn("CALLS 0 APP False", done.stdout, done.stderr[-500:])
        self.assertFalse(T.root.exists())


if __name__ == "__main__":
    unittest.main()

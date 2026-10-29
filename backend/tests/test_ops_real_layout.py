"""Fake-only checks of the RS4-1 split (tests/_ops_real_layout.py): closed layouts, role counting, the hooks
around the original product connection exit, and PG65 / PG63 outputs equal to the baseline taken BEFORE the
split (tests/ops_pg65_preserve.json). No database, cluster, process, key or certificate.

Run directly:      python tests/test_ops_real_layout.py
Or via discovery:   python -m unittest discover -s tests -p test_ops_real_layout.py
"""

from __future__ import annotations

import dataclasses
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

TESTS_DIR = Path(__file__).resolve().parent
BACKEND = TESTS_DIR.parent
sys.path.insert(0, str(BACKEND / "scripts"))
sys.path.insert(0, str(TESTS_DIR))

import psycopg  # noqa: E402

import _ops_apply_real as ap  # noqa: E402
import _ops_audit_real as real  # noqa: E402
import _ops_pg62 as g  # noqa: E402
import _ops_provider as pv  # noqa: E402
import _ops_real_layout as lay  # noqa: E402

BASELINE = TESTS_DIR / "ops_pg65_preserve.json"
BASELINE_SHA256 = "31a75924565ca116d89194dcb2a4d4bb50d284bfc3a3ae53e74ff5e8ab62657d"   # recorded at creation


# The only write-contract change since BASELINE was taken (OPS_MIGRATION_RESUME_LEXEME_RACE_PLAN 11-1), fixed here.
LQ1_WRITE_PRIVILEGES = frozenset({("table", "public", "user_deck_subscriptions", "updated_at", "UPDATE"),
                                  ("table", "public", "shared_deck_words", "created_at", "UPDATE")})


def forbidden(*_, **__):
    raise AssertionError("an external entry point was called")


def text(items):
    return [s.as_string(None) for s in items]


class Rec:
    def __init__(self):
        self.events = []
        self.folder = Path("C:/rs4-baseline-run")

    def event(self, name, **kw):
        self.events.append([name, kw])


def calls(fn) -> dict:
    """The baseline's recorder: every process / file step replaced; the secret folder path and the random
    certificate serial are masked (the baseline was written with the same masking of the folder path)."""
    seen = []
    secret = Path(tempfile.mkdtemp(prefix="rs4_layout_secret_"))
    rec = Rec()
    try:
        with mock.patch.object(real.base, "openssl", lambda *a: seen.append(["openssl"] + [str(x) for x in a])), \
                mock.patch.object(real.base, "run", lambda args, **k: seen.append(["run"] + [str(x) for x in args])), \
                mock.patch.object(real.base, "sha", lambda p: "sha:" + str(p)), \
                mock.patch.object(real.g, "postmaster_pid", lambda t=None: 4242), \
                mock.patch.object(real.g, "server_is_ours", lambda pid, t=None: True), \
                mock.patch.object(real.g, "process_image", lambda pid: "C:/x/postgres.exe"), \
                mock.patch.dict(os.environ, {"USERNAME": "baseline-user"}):
            fn(rec, secret)
    finally:
        shutil.rmtree(secret, ignore_errors=True)
    data = json.dumps({"calls": seen, "events": rec.events}, default=str)
    for form in (str(secret), str(secret).replace("\\", "/")):
        data = data.replace(json.dumps(form)[1:-1], "<SECRET>")
    return mask_serial(json.loads(data))


def mask_serial(value):
    """`make_tls` draws a random certificate serial on every call: compared as a marker only."""
    if isinstance(value, list):
        out = []
        for i, item in enumerate(value):
            out.append("<SERIAL>" if i > 0 and value[i - 1] == "-set_serial" else mask_serial(item))
        return out
    if isinstance(value, dict):
        return {k: mask_serial(v) for k, v in value.items()}
    return value


# --- 1. closed layouts -----------------------------------------------------------------------------------------

class Layouts(unittest.TestCase):
    def test_only_the_registered_objects(self):
        # pg67 added by lexeme L-1, pg68 by access lock V1
        self.assertEqual(lay.LAYOUTS, (lay.PG65, lay.PG66, lay.PG67, lay.PG68))
        self.assertIs(lay.PG65.target, g.PG65_APPLY)
        self.assertIs(lay.PG66.target, g.PG66_RESUME)
        copy = dataclasses.replace(lay.PG66)                       # equal values, another object
        for call in (lambda: lay.layout(copy), lambda: lay.expected_profiles(copy, copy.business_databases[0]),
                     lambda: lay.contract_grants(copy, copy.business_databases[0]), lambda: lay.hba(copy),
                     lambda: lay.conf(copy), lambda: lay.admin(copy, "postgres", 1), lambda: lay.role_of(copy, "status"),
                     lambda: lay.business_check(copy, {}), lambda: lay.require_ours(copy, {"postmaster_pid": 1}),
                     lambda: lay.variant_statements(copy, "r5_read_missing", "apply"),
                     lambda: lay.counted_connector(copy, lay.Counts(()), []), lambda: lay.RunScopes(copy)):
            with self.subTest(call=call), self.assertRaises(g.Pg62Refused) as caught:
                call()
            self.assertEqual(caught.exception.code, "layout_refused")
        target_copy = dataclasses.replace(g.PG66_RESUME)
        layout_with_copy = lay.Layout("pg66", target_copy, lay.PG66.check_ids, "jpvr_owner", {}, {})
        with self.assertRaises(g.Pg62Refused):
            lay.layout(layout_with_copy)

    def test_pg66_names_are_separate_from_every_other_target(self):
        others = [p for p in g.PRESETS if p is not g.PG66_RESUME]
        self.assertNotIn(g.PG66_RESUME.port, {p.port for p in others})
        self.assertNotIn(g.PG66_RESUME.root, {p.root for p in others})
        self.assertFalse(set(g.PG66_RESUME.databases) & {d for p in others for d in p.databases})
        self.assertFalse(set(g.PG66_RESUME.provider_roles + (g.PG66_RESUME.admin,))
                         & {r for p in others for r in p.provider_roles + (p.admin,)})
        self.assertNotIn(g.PG66_RESUME.admin, g.PG66_RESUME.provider_roles)
        self.assertEqual((lay.PG66.short, lay.PG66.owner, lay.PG66.read, lay.PG66.write),
                         ("pg66", "jpvr_owner", "jpvr_read", "jpvr_write"))

    def test_pg67_names_are_separate_from_every_other_target(self):
        target = g.PG67_RESUME_LEXEME                                   # values from the plan (4절 / LQ2)
        self.assertEqual((target.root, target.port, target.admin, target.provider_roles),
                         (g.Path("C:/JV_Tools/pg67"), 55512, "jpvl_admin", ("jpvl_read", "jpvl_write")))
        self.assertEqual(target.databases, ("jp_vocab_test_resume_lex_tpl",) + tuple(
            f"jp_vocab_test_resume_lex_{c}" for c in ("l1", "l2", "l3", "l6", "l7", "l8", "l9")))
        others = [p for p in g.PRESETS if p is not target]
        self.assertNotIn(target.port, {p.port for p in others})
        self.assertNotIn(target.root, {p.root for p in others})
        self.assertFalse(set(target.databases) & {d for p in others for d in p.databases})
        self.assertFalse(set(target.provider_roles + (target.admin,))
                         & {r for p in others for r in p.provider_roles + (p.admin,)})
        self.assertEqual((lay.PG67.short, lay.PG67.owner, lay.PG67.read, lay.PG67.write),
                         ("pg67", "jpvl_owner", "jpvl_read", "jpvl_write"))
        self.assertEqual(set(lay.PG67.variants), {"l8_lexeme_card_column", "l9_read_subscriptions"})
        self.assertEqual([s.as_string(None) for s in lay.variant_statements(lay.PG67, "l9_read_subscriptions", "apply")],
                         ['REVOKE SELECT ON public.user_deck_subscriptions FROM "jpvl_read"'])
        self.assertEqual([s.as_string(None) for s in lay.variant_statements(lay.PG67, "l8_lexeme_card_column", "revert")],
                         ['GRANT UPDATE (srs_state) ON public.user_word_progress TO "jpvl_write"'])
        with self.assertRaises(lay.CheckFailed):
            lay.variant_statements(lay.PG67, "r5_read_missing", "apply")          # a PG66 variant is not PG67's

    def test_role_of_the_closed_command_sets(self):
        for layout, read, write in ((lay.PG65, "jpvm_read", "jpvm_write"), (lay.PG66, "jpvr_read", "jpvr_write"),
                                    (lay.PG67, "jpvl_read", "jpvl_write")):
            self.assertEqual([lay.role_of(layout, c) for c in ("dry_run", "status", "apply", "resume")],
                             [read, read, write, write])
            for bad in ("rollback", "preview", None, "Resume"):
                with self.subTest(command=bad), self.assertRaises(lay.CheckFailed):
                    lay.role_of(layout, bad)


# --- 2. counting by role and the hooks around the original exit --------------------------------------------------

class FakeConn:
    def __init__(self):
        self.info = SimpleNamespace(backend_pid=4321)
        self.log = []

    def execute(self, query, *a, **k):
        self.log.append(query)


class Product:
    """The real connector's context stand-in: records enter / exit and can fail its exit."""

    def __init__(self, exit_error=None):
        self.entered = self.exits = 0
        self.exit_args = None
        self.exit_error = exit_error

    def __enter__(self):
        self.entered += 1
        return "app-connection"

    def __exit__(self, *exc):
        self.exits += 1
        self.exit_args = exc
        if self.exit_error is not None:
            raise self.exit_error
        return False


class Counting(unittest.TestCase):
    def factory(self, layout, counts, trackers, product=None, **hooks):
        products = []

        def real(inputs, expected, driver):
            def connector(read_only=False):
                trackers.append(lay.Tracked(FakeConn(), counts, lay.role_of(layout, inputs.command), []))
                counts.created[lay.role_of(layout, inputs.command)] += 1
                products.append(product or Product())
                return products[-1]
            return connector
        return lay.counted_connector(layout, counts, trackers, real=real, **hooks), products

    def test_status_read_and_resume_write_are_counted_apart(self):
        counts, trackers = lay.Counts(lay.PG66.business_roles), []
        factory, _ = self.factory(lay.PG66, counts, trackers)
        for command, n in (("status", 1), ("resume", 3)):
            connect = factory(SimpleNamespace(command=command), None, None)
            for _ in range(n):
                with connect(read_only=command == "status"):
                    pass
        self.assertEqual((counts.created, counts.handed),
                         ({"jpvr_read": 1, "jpvr_write": 3}, {"jpvr_read": 1, "jpvr_write": 3}))

    def test_c12_counting_unchanged(self):
        counts, trackers = ap.Counts(), []
        self.assertEqual(set(counts.created), {"jpvm_read", "jpvm_write"})
        for command, role in (("dry_run", ap.READ), ("apply", ap.WRITE)):
            self.assertEqual(lay.role_of(ap.LAYOUT, command), role)

    def test_before_exit_runs_once_before_the_original_exit(self):
        order = []
        product = Product()
        counts, trackers = lay.Counts(lay.PG66.business_roles), []

        def hook(role, n, tracker):
            order.append(("hook", role, n, product.exits))
        factory, _ = self.factory(lay.PG66, counts, trackers, product, before_exit=hook)
        with factory(SimpleNamespace(command="status"), None, None)(read_only=True):
            pass
        self.assertEqual((order, product.exits), ([("hook", "jpvr_read", 1, 0)], 1))

    def test_hook_failure_or_interrupt_never_skips_the_original_exit(self):
        for error in (RuntimeError("probe"), KeyboardInterrupt()):
            with self.subTest(error=type(error).__name__):
                product = Product()
                counts, trackers = lay.Counts(lay.PG66.business_roles), []

                def hook(role, n, tracker, error=error):
                    raise error
                factory, _ = self.factory(lay.PG66, counts, trackers, product, before_exit=hook)
                with self.assertRaises(type(error)):
                    with factory(SimpleNamespace(command="status"), None, None)(read_only=True):
                        pass
                self.assertEqual((product.exits, product.exit_args[0]), (1, None))   # original exit, normal end

    def test_product_error_is_kept_and_the_hook_is_not_run(self):
        product = Product()
        counts, trackers = lay.Counts(lay.PG66.business_roles), []
        factory, _ = self.factory(lay.PG66, counts, trackers, product, before_exit=forbidden)
        with self.assertRaises(ValueError):
            with factory(SimpleNamespace(command="status"), None, None)(read_only=True):
                raise ValueError("product")
        self.assertEqual((product.exits, product.exit_args[0]), (1, ValueError))

    def test_original_exit_error_wins_over_a_hook_error(self):
        product = Product(exit_error=psycopg.OperationalError("commit"))
        counts, trackers = lay.Counts(lay.PG66.business_roles), []

        def hook(role, n, tracker):
            raise RuntimeError("probe")
        factory, _ = self.factory(lay.PG66, counts, trackers, product, before_exit=hook)
        with self.assertRaises(psycopg.OperationalError):
            with factory(SimpleNamespace(command="status"), None, None)(read_only=True):
                pass
        self.assertEqual(product.exits, 1)

    def test_handover_failure_still_exits_the_original_once(self):
        product = Product()
        counts, trackers = lay.Counts(lay.PG66.business_roles), []

        def handover(role, n, tracker):
            raise KeyboardInterrupt()
        factory, _ = self.factory(lay.PG66, counts, trackers, product, handover=handover)
        with self.assertRaises(KeyboardInterrupt):
            with factory(SimpleNamespace(command="resume"), None, None)():
                pass
        self.assertEqual((product.entered, product.exits, product.exit_args[0]), (1, 1, KeyboardInterrupt))


# --- 3. PG65 / PG63 outputs equal to the baseline taken before the split -----------------------------------------

class Preserved(unittest.TestCase):
    def setUp(self):
        for patch in (mock.patch.object(psycopg, "connect", forbidden), mock.patch.object(subprocess, "Popen", forbidden),
                      mock.patch.object(subprocess, "run", forbidden)):
            patch.start()
            self.addCleanup(patch.stop)
        data = BASELINE.read_bytes()
        self.assertEqual(lay.hashlib.sha256(data).hexdigest(), BASELINE_SHA256)     # the file was not rewritten
        self.base = json.loads(data)

    def test_pg65_strings_and_lists(self):
        T = ap.T
        self.assertEqual(self.base["target"], [T.name, str(T.root), T.port, list(T.databases), T.admin,
                                               list(T.provider_roles), T.target_doc])
        self.assertEqual((self.base["template"], self.base["check_db"], self.base["business_databases"],
                          self.base["admin_databases"], self.base["admin"], self.base["owner"], self.base["roles"],
                          self.base["business_roles"]),
                         (ap.TEMPLATE, ap.CHECK_DB, list(ap.BUSINESS_DATABASES), list(ap.ADMIN_DATABASES), ap.ADMIN,
                          ap.OWNER, [ap.READ, ap.WRITE], list(ap.BUSINESS_ROLES)))
        # LQ1 (RACE_PLAN 11-1) added exactly two write-contract column UPDATEs after this baseline was taken. The
        # baseline is not rewritten: the current output must be the baseline plus exactly those two GRANTs, and the
        # baseline write fingerprint must be the current contract without exactly those two privileges.
        lq1 = text(lay.grant_statements(LQ1_WRITE_PRIVILEGES, ap.WRITE))
        self.assertEqual(len(lq1), 2)
        profiles = {}
        for db in ap.BUSINESS_DATABASES:
            current = text(ap.contract_grants(db))
            self.assertEqual(sorted(g for g in current if g in lq1), sorted(lq1), db)
            self.assertEqual([g for g in current if g not in lq1], self.base["grants"][db], db)
            r, w = ap.expected_profiles(db)
            self.assertTrue(LQ1_WRITE_PRIVILEGES <= w.privileges and not LQ1_WRITE_PRIVILEGES & r.privileges)
            before = pv.ExpectedProfile(w.objects, w.privileges - LQ1_WRITE_PRIVILEGES, w.search_path, w.tls_versions)
            self.assertNotEqual(pv.expected_profile_fingerprint(w, role=ap.WRITE, access="write"),
                                self.base["profiles"][db][1], db)
            profiles[db] = [pv.expected_profile_fingerprint(r, role=ap.READ, access="read"),
                            pv.expected_profile_fingerprint(before, role=ap.WRITE, access="write")]
        self.assertEqual(set(self.base["grants"]), set(ap.BUSINESS_DATABASES))
        self.assertEqual(self.base["profiles"], profiles)
        self.assertEqual(self.base["variants"], {n: {p: text(ap.variant_statements(n, p)) for p in ("apply", "revert")}
                                                 for n in ap.VARIANTS})
        self.assertEqual(self.base["variant_databases"], {k: list(v) for k, v in ap.VARIANT_DATABASES.items()})
        self.assertEqual((self.base["hba"], self.base["conf"]), (ap.hba(), ap.conf()))
        self.assertEqual((self.base["post_connect"], self.base["oid_tables"]), (ap.POST_CONNECT, list(ap.OID_TABLES)))

    def test_audit_runner_default_and_pg65_steps(self):
        self.assertEqual((self.base["audit_default"]["conf"], self.base["audit_default"]["hba"]), (real.conf(), real.hba()))
        self.assertEqual(mask_serial(self.base["audit_default"]["make_tls"]),
                         calls(lambda rec, secret: real.make_tls(rec, secret)))
        self.assertEqual(self.base["audit_default"]["start_server"], calls(lambda rec, secret: real.start_server(rec)))
        self.assertEqual(mask_serial(self.base["pg65_make_tls"]),
                         calls(lambda rec, secret: real.make_tls(rec, secret, ap.T)))     # explicit target now
        self.assertEqual(self.base["pg65_start_server"], calls(lambda rec, secret: real.start_server(rec, ap.T)))
        self.assertEqual(real.conf(real.T), real.conf())
        with self.assertRaises(g.Pg62Refused):
            real.conf(dataclasses.replace(ap.T))                    # only a closed preset object

    def test_no_global_replacement_left(self):
        for path in (TESTS_DIR / "_ops_apply_real.py", TESTS_DIR / "_ops_resume_real.py", TESTS_DIR / "_ops_real_layout.py"):
            source = path.read_text(encoding="utf-8")
            with self.subTest(file=path.name):
                self.assertNotRegex(source, r'mock\.patch\.object\(\s*real\s*,\s*"T"')
                self.assertNotRegex(source, r'mock\.patch\.object\(\s*(ap|lay|g)\s*,\s*"(T|PG6\d\w*|LAYOUT)"')


# --- 4. no runner import from the shared module, import does nothing ---------------------------------------------

class Imports(unittest.TestCase):
    def test_shared_module_imports_no_runner(self):
        source = (TESTS_DIR / "_ops_real_layout.py").read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"^\s*(import|from)\s+_ops_(apply|resume)_real\b", source, re.M))

    def test_import_in_a_new_process_has_no_effect(self):
        code = ("import sys, os, subprocess, tempfile, psycopg\n"
                f"sys.path[:0] = [{str(TESTS_DIR)!r}, {str(BACKEND / 'scripts')!r}]\n"
                "def bad(*a, **k): raise SystemExit('EXTERNAL')\n"
                "psycopg.connect = bad; subprocess.run = bad; subprocess.Popen = bad; tempfile.mkdtemp = bad\n"
                "import _ops_real_layout\n"
                "loaded = sorted(m for m in sys.modules if m in ('_ops_apply_real', '_ops_resume_real') or m == 'app' "
                "or m.startswith('app.'))\n"
                "print('LOADED', loaded)\n")
        env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "APP_ENV", "DATABASE_URL")}
        done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120, env=env)
        self.assertIn("LOADED []", done.stdout, done.stderr[-600:])


if __name__ == "__main__":
    unittest.main()

"""OPS_MIGRATION_CLI_PLAN 2-3: migration plan file format version 1 (synthetic).

Pure parsing and file handling use synthetic documents and temporary files made here. Product
candidates come from `dry_run` on a synthetic SQLite file made by the test (QueueCase). Approval
binding uses the existing synthetic signing path (test-only temporary keys, no connection, no new
TOOLS entry). The environment is fixed before anything from `app` is imported.

Run directly:      python tests/test_ops_plan_file.py
"""

from __future__ import annotations

import os

os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["PYTHON_DOTENV_DISABLED"] = "1"

import hashlib  # noqa: E402
import json  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402
from dataclasses import fields, replace  # noqa: E402
from datetime import timedelta  # noqa: E402
from pathlib import Path  # noqa: E402
from unittest import mock  # noqa: E402

TESTS_DIR = Path(__file__).resolve().parent
BACKEND = TESTS_DIR.parent
sys.path.insert(0, str(BACKEND / "scripts"))
sys.path.insert(0, str(TESTS_DIR))
if str(BACKEND) not in sys.path:      # path only, from this file's location
    sys.path.append(str(BACKEND))

import _ops_approval as oa  # noqa: E402
import _ops_plan_file as pfile  # noqa: E402
import _ops_preflight as op  # noqa: E402
import test_ops_preflight as pf  # noqa: E402  (module only: its tests are not re-run here)

SECRET = "s3cr3t-Plan-Value-41aa"
RESTART = '{"previous_boundary":5,"rollback_record_id":9}'


def h(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def cand(kind, ref_id, **changes) -> dict:
    values = {"kind": kind, "ref_id": ref_id, "card_fingerprint": h(f"card{ref_id}"),
              "logs_fingerprint": h(f"logs{ref_id}"), "card_version": 2, "quality": "complete",
              "flags": ["legacy_history"], "values_json": '{"srs_engine":"fsrs"}', "last_log_id": 4,
              "reconversion": None, "restart_json": None}
    values.update(changes)
    return values


def doc(**changes) -> dict:
    value = {"format": pfile.FORMAT, "format_version": 1, "db_identity": h("db"), "account_id": 7,
             "job_key": "run-2026-10-26-a", "config_version": "fsrs-v1", "product_fingerprint": h("product"),
             "candidates": [cand("lexeme", 3),
                            cand("personal", 1, quality="fresh"),
                            cand("personal", 2, quality="unavailable", card_fingerprint=None, card_version=None,
                                 values_json=None, flags=["card_or_access_missing"])]}
    value.update(changes)
    return value


def encode(value) -> bytes:
    """ASCII JSON (escapes kept as escapes), sorted and compact."""
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("ascii")


class Refused(unittest.TestCase):
    def refused(self, code, fn, *args, **kwargs):
        with self.assertRaises(pfile.OpsPlanFileError) as caught:
            fn(*args, **kwargs)
        error = caught.exception
        self.assertEqual((error.code, error.args), (code, (code,)))
        self.assertNotIn(SECRET, repr(error) + str(error))
        self.assertTrue(error.__suppress_context__ or error.__context__ is None)
        return error


class Parsing(Refused):
    """Pure parsing of synthetic bytes (no app import, no file)."""

    def test_valid_document_and_fixed_digest(self):
        data = encode(doc())
        plan = pfile.parse_plan_bytes(data)
        self.assertEqual(plan.artifact_sha256, hashlib.sha256(data).hexdigest())
        self.assertIs(plan.raw, data)
        self.assertEqual([(c.kind, c.ref_id) for c in plan.candidates], [("lexeme", 3), ("personal", 1),
                                                                         ("personal", 2)])
        missing = plan.candidates[2]
        self.assertEqual((missing.quality, missing.card_fingerprint, missing.card_version), ("unavailable", None, None))
        spaced = json.dumps(doc(), indent=1).encode()                  # other spelling: other digest, no rewrite
        self.assertNotEqual(pfile.parse_plan_bytes(spaced).artifact_sha256, plan.artifact_sha256)
        self.assertNotIn(SECRET, repr(plan))

    def test_reconversion_fields_are_kept(self):
        value = doc(candidates=[cand("personal", 1, reconversion="restored", restart_json=RESTART),
                                cand("personal", 2, quality="incomplete", reconversion="state_none_restart",
                                     restart_json=RESTART),
                                cand("personal", 3, quality="incomplete", reconversion="state_none")])
        plan = pfile.parse_plan_bytes(encode(value))
        self.assertEqual([(c.reconversion, c.restart_json) for c in plan.candidates],
                         [("restored", RESTART), ("state_none_restart", RESTART), ("state_none", None)])

    def test_format_errors(self):
        good = encode(doc())
        nested = encode(doc(candidates=[cand("personal", 1, flags=[["x"]])]))
        cases = {
            "duplicate key": good.replace(b'"account_id":7', b'"account_id":7,"account_id":8', 1),
            "NaN": good.replace(b'"card_version":2', b'"card_version":NaN', 1),
            "Infinity": good.replace(b'"card_version":2', b'"card_version":Infinity', 1),
            "float": good.replace(b'"card_version":2', b'"card_version":2.0', 1),
            "bom": b"\xef\xbb\xbf" + good,
            "not utf-8": good.replace(b"fsrs-v1", b"fsrs-\xff1", 1),
            "deep": nested,
            "deeper": b"[" * 5000 + b"]" * 5000,
            "not json": b"{" + SECRET.encode(),
            "empty": b"",
            "not bytes": good.decode(),
        }
        for label, data in cases.items():
            with self.subTest(case=label):
                self.refused("plan_file_format_invalid", pfile.parse_plan_bytes, data)
        self.refused("plan_file_too_large", pfile.parse_plan_bytes, b" " * (pfile.MAX_PLAN_BYTES + 1))

    def test_fields_and_versions(self):
        extra = doc()
        extra["note"] = SECRET
        missing = doc()
        del missing["product_fingerprint"]
        for value in (extra, missing, doc(format="other"), [1]):
            with self.subTest(value=type(value).__name__):
                self.refused("plan_file_fields_invalid", pfile.parse_plan_bytes, encode(value))
        for version in (2, 0, True, "1"):
            with self.subTest(version=version):
                self.refused("plan_file_version_unsupported", pfile.parse_plan_bytes, encode(doc(format_version=version)))
        no_restart = cand("personal", 1)
        del no_restart["restart_json"]
        self.refused("plan_file_fields_invalid", pfile.parse_plan_bytes, encode(doc(candidates=[no_restart])))
        unknown = dict(cand("personal", 1), note=SECRET)
        self.refused("plan_file_fields_invalid", pfile.parse_plan_bytes, encode(doc(candidates=[unknown])))

    def test_values(self):
        top = {"db_identity": h("db").upper(), "account_id": "7", "job_key": "bad key", "config_version": "",
               "product_fingerprint": SECRET}
        for name, value in list(top.items()) + [("account_id", True), ("account_id", 0), ("account_id", 2 ** 63)]:
            with self.subTest(top=name, value=repr(value)[:20]):
                self.refused("plan_file_value_invalid", pfile.parse_plan_bytes, encode(doc(**{name: value})))
        candidate = {"kind": "deck", "ref_id": "1", "card_fingerprint": SECRET, "logs_fingerprint": None,
                     "card_version": -1, "quality": "done", "flags": ["has space"], "values_json": 5,
                     "last_log_id": True, "reconversion": "maybe", "restart_json": '{"previous_boundary":1}'}
        more = [("ref_id", True), ("ref_id", 0), ("flags", "x"), ("flags", ["a"] * (pfile.MAX_FLAGS + 1)),
                ("values_json", "x" * (pfile.MAX_VALUES_BYTES + 1)), ("quality", ["complete"]),
                ("restart_json", '{"rollback_record_id":9,"previous_boundary":5}'),
                ("restart_json", '{"previous_boundary":5,"rollback_record_id":true}')]
        for name, value in list(candidate.items()) + more:
            with self.subTest(candidate=name, value=repr(value)[:20]):
                bad = doc(candidates=[dict(cand("personal", 1), **{name: value})])
                self.refused("plan_file_value_invalid", pfile.parse_plan_bytes, encode(bad))
        lone = encode(doc(candidates=[cand("personal", 1)])).replace(b'"values_json":"{', b'"values_json":"\\ud800{', 1)
        self.refused("plan_file_value_invalid", pfile.parse_plan_bytes, lone)        # a lone surrogate

    def test_candidate_order_and_duplicates(self):
        for value in ([], [cand("personal", 2), cand("personal", 1)], [cand("personal", 1), cand("personal", 1)],
                      [cand("personal", 1), cand("lexeme", 1)], "x"):
            with self.subTest(value=repr(value)[:30]):
                self.refused("plan_file_candidates_invalid", pfile.parse_plan_bytes, encode(doc(candidates=value)))
        with mock.patch.object(pfile, "MAX_CANDIDATES", 2):                 # limit, without a huge fixture
            self.refused("plan_file_candidates_invalid", pfile.parse_plan_bytes, encode(doc()))

    def test_combinations(self):
        cases = {
            "missing card not unavailable": dict(card_fingerprint=None, card_version=None),
            "fingerprint without version": dict(card_version=None),
            "version without fingerprint": dict(card_fingerprint=None),
            "unavailable with values": dict(quality="unavailable"),
            "unavailable pair mismatch": dict(quality="unavailable", values_json=None, card_version=None),
            "no-value quality with values": dict(quality="already_fsrs"),
            "blocked with reconversion": dict(quality="reconvert_blocked", values_json=None, reconversion="restored"),
            "restart without reconversion": dict(restart_json=RESTART),
            "restored without values": dict(reconversion="restored", values_json=None, quality="incomplete"),
            "state_none not incomplete": dict(reconversion="state_none"),
            "state_none with restart": dict(quality="incomplete", reconversion="state_none", restart_json=RESTART),
            "state_none_restart without restart": dict(quality="incomplete", reconversion="state_none_restart"),
        }
        for label, changes in cases.items():
            with self.subTest(case=label):
                self.refused("plan_file_combination_invalid", pfile.parse_plan_bytes,
                             encode(doc(candidates=[cand("personal", 1, **changes)])))

    def test_unavailable_with_or_without_a_card(self):
        # contract 2-3 fix: NULL pair => unavailable, but unavailable does not require the NULL pair
        with_card = cand("personal", 1, quality="unavailable", values_json=None, flags=["card_or_access_missing"])
        without = cand("personal", 2, quality="unavailable", card_fingerprint=None, card_version=None,
                       values_json=None, flags=["card_or_access_missing"])
        plan = pfile.parse_plan_bytes(encode(doc(candidates=[with_card, without])))
        self.assertEqual([(c.card_fingerprint is None, c.card_version is None) for c in plan.candidates],
                         [(False, False), (True, True)])

    def test_module_import_does_not_import_the_app(self):
        code = (f"import sys; sys.path[:0] = [{str(BACKEND / 'scripts')!r}]\n"
                "import _ops_plan_file\n"
                "print('APP', any(m == 'app' or m.startswith('app.') for m in sys.modules))")
        done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120)
        self.assertIn("APP False", done.stdout, done.stderr[-300:])


class Files(Refused):
    """Real temporary files; OS failures are simulated with mocks where marked."""

    def setUp(self):
        self.folder = tempfile.mkdtemp(prefix="ops_plan_file_test_")
        self.addCleanup(shutil.rmtree, self.folder, True)
        self.path = os.path.join(self.folder, "plan.json")
        self.data = encode(doc())

    def leftovers(self):
        return sorted(os.listdir(self.folder))

    def test_write_new_read_back_and_never_overwrite(self):
        digest = pfile.write_plan_file(self.path, self.data)
        self.assertEqual(digest, hashlib.sha256(self.data).hexdigest())
        self.assertEqual(self.leftovers(), ["plan.json"])
        self.refused("plan_file_exists", pfile.write_plan_file, self.path, encode(doc(job_key="other")))
        with open(self.path, "rb") as handle:
            self.assertEqual(handle.read(), self.data)                     # not overwritten

    def test_bytes_are_fixed_at_read(self):
        pfile.write_plan_file(self.path, self.data)
        plan = pfile.read_plan_file(self.path)
        with open(self.path, "wb") as handle:                              # changed on disk afterwards
            handle.write(encode(doc(job_key="changed")))
        self.assertEqual((plan.raw, plan.job_key), (self.data, "run-2026-10-26-a"))
        self.assertEqual(plan.artifact_sha256, hashlib.sha256(self.data).hexdigest())

    def test_unreadable_and_invalid_input(self):
        self.refused("plan_file_unreadable", pfile.read_plan_file, os.path.join(self.folder, SECRET + ".json"))
        self.refused("plan_file_unreadable", pfile.read_plan_file, None)
        self.refused("plan_file_fields_invalid", pfile.write_plan_file, self.path, b"{}")
        self.assertEqual(self.leftovers(), [])

    def existing(self, name, data):
        path = os.path.join(self.folder, name)
        with open(path, "wb") as handle:
            handle.write(data)
        return path

    def unchanged(self, path, data):
        with open(path, "rb") as handle:
            self.assertEqual(handle.read(), data)

    def test_temp_name_collision_keeps_the_other_file(self):           # REAL file, fixed temp name (mock)
        other = self.existing(".plan-00000000deadbeef.tmp", b"someone else's bytes")
        with mock.patch.object(pfile.secrets, "token_hex", return_value="00000000deadbeef"):
            self.refused("plan_file_write_failed", pfile.write_plan_file, self.path, self.data)
        self.unchanged(other, b"someone else's bytes")
        self.assertEqual(self.leftovers(), [".plan-00000000deadbeef.tmp"])     # no plan file made

    def test_final_name_collision_keeps_the_other_file(self):          # REAL files
        target = self.existing("plan.json", b"existing plan bytes")
        self.refused("plan_file_exists", pfile.write_plan_file, self.path, self.data)
        self.unchanged(target, b"existing plan bytes")
        with mock.patch.object(os.path, "lexists", return_value=False):   # appears after the check (mock)
            self.refused("plan_file_exists", pfile.write_plan_file, self.path, self.data)
        self.unchanged(target, b"existing plan bytes")
        self.assertEqual(self.leftovers(), ["plan.json"])

    def test_failure_before_creation_removes_nothing(self):            # MOCKED: temp creation refused
        real_open = open

        def refuse_new(path, mode="r", *args, **kwargs):
            if mode == "xb":
                raise PermissionError(13, SECRET)
            return real_open(path, mode, *args, **kwargs)
        other = self.existing("unrelated.txt", b"keep")
        with mock.patch("builtins.open", refuse_new):
            self.refused("plan_file_write_failed", pfile.write_plan_file, self.path, self.data)
        self.unchanged(other, b"keep")
        self.assertEqual(self.leftovers(), ["unrelated.txt"])

    def test_replaced_target_is_not_removed(self):                     # REAL files, verify failure (mock)
        def replace_then_fail(path):
            os.remove(path)
            with open(path, "wb") as handle:                                # someone else's file now
                handle.write(b"replaced by another writer")
            raise pfile.OpsPlanFileError("plan_file_unreadable")
        with mock.patch.object(pfile, "read_plan_file", side_effect=replace_then_fail):
            self.refused("plan_file_unreadable", pfile.write_plan_file, self.path, self.data)
        self.unchanged(self.path, b"replaced by another writer")
        self.assertEqual(self.leftovers(), ["plan.json"])

    def test_write_failures_return_no_plan(self):                          # MOCKED OS failures
        for name in ("link", "fsync"):
            with self.subTest(step=name):
                with mock.patch.object(os, name, side_effect=OSError(5, SECRET)):
                    self.refused("plan_file_write_failed", pfile.write_plan_file, self.path, self.data)
                self.assertEqual(self.leftovers(), [])
        with mock.patch.object(pfile, "read_plan_file", side_effect=pfile.OpsPlanFileError("plan_file_unreadable")):
            self.refused("plan_file_unreadable", pfile.write_plan_file, self.path, self.data)
        self.assertEqual(self.leftovers(), [])                             # the file it created is removed
        with mock.patch.object(os, "link", side_effect=FileExistsError(17, SECRET)):
            self.refused("plan_file_exists", pfile.write_plan_file, self.path, self.data)
        self.assertEqual(self.leftovers(), [])


from test_srs_d2_intro import IntroCase  # noqa: E402  (imports the app; environment fixed above)
from test_srs_queue import NOW, iso  # noqa: E402

from app.database import get_connection  # noqa: E402
from app.srs import migration  # noqa: E402
from app.srs.engine import CardKey  # noqa: E402


class ProductCandidates(IntroCase):
    """Real dry_run candidates from a synthetic SQLite file; no apply."""

    def candidates(self):
        a = self.past_card("a", iso(NOW - timedelta(days=5)))
        b = self.personal("b")
        return migration.dry_run([CardKey("personal", self.user, a), CardKey("personal", self.user, b),
                                  CardKey("personal", self.user, 999999)])

    def product(self, candidates) -> str:
        return hashlib.sha256(migration._plan_json(candidates).encode()).hexdigest()

    def plan_bytes(self, candidates, **changes):
        values = dict(db_identity=h("db"), account_id=self.user, job_key="run-plan",
                      config_version=migration.DEFAULT_CONFIG.config_version,
                      product_fingerprint=self.product(candidates), candidates=candidates)
        values.update(changes)
        return pfile.serialize_plan(**values)

    def test_round_trip_keeps_all_ten_fields_and_order(self):
        original = self.candidates()
        self.assertIn("unavailable", [c.quality for c in original])
        self.assertEqual(len(fields(migration.MigrationCandidate)), 10)
        restored = pfile.to_candidates(pfile.parse_plan_bytes(self.plan_bytes(original)))
        self.assertEqual(restored, original)
        self.assertEqual(self.product(restored), self.product(original))

    def test_reconversion_fields_change_the_file_not_the_product_fingerprint(self):
        original = self.candidates()
        index = next(i for i, c in enumerate(original) if c.values_json is not None)
        changed = list(original)
        changed[index] = replace(original[index], reconversion="restored", restart_json=RESTART)
        changed = tuple(changed)
        first, second = self.plan_bytes(original), self.plan_bytes(changed)
        self.assertEqual(self.product(original), self.product(changed))        # _plan_json does not hold them
        a, b = pfile.parse_plan_bytes(first), pfile.parse_plan_bytes(second)
        self.assertNotEqual(a.artifact_sha256, b.artifact_sha256)
        self.assertEqual(pfile.to_candidates(b), changed)
        plan = dict(db_identity=h("db"), manifest=h("manifest"), tool="prb_recover", account_id=self.user,
                    job_key="run-plan", job_inputs={}, product_fingerprint=self.product(original))
        self.assertNotEqual(oa.job_plan_fingerprint(**plan, artifact_sha256=a.artifact_sha256),
                            oa.job_plan_fingerprint(**plan, artifact_sha256=b.artifact_sha256))

    def test_product_checks(self):
        original = self.candidates()
        self.assertRaises(pfile.OpsPlanFileError, self.plan_bytes, original, account_id=self.user + 1)
        wrong_product = pfile.parse_plan_bytes(self.plan_bytes(original, product_fingerprint=h("other")))
        with self.assertRaises(pfile.OpsPlanFileError) as caught:
            pfile.to_candidates(wrong_product)
        self.assertEqual(caught.exception.code, "plan_file_product_mismatch")
        other_config = pfile.parse_plan_bytes(self.plan_bytes(original, config_version="other-config"))
        with self.assertRaises(pfile.OpsPlanFileError) as caught:
            pfile.to_candidates(other_config)
        self.assertEqual(caught.exception.code, "plan_file_config_mismatch")
        bad_values = list(original)
        index = next(i for i, c in enumerate(original) if c.values_json is not None)
        bad_values[index] = replace(original[index], values_json='{"srs_engine":"legacy"}')
        bad = pfile.parse_plan_bytes(self.plan_bytes(tuple(bad_values)))      # the format allows it ...
        with self.assertRaises(pfile.OpsPlanFileError) as caught:
            pfile.to_candidates(bad)                                           # ... the product rule does not
        self.assertEqual(caught.exception.code, "plan_file_scope_invalid")

    def test_unavailable_card_with_progress_round_trip(self):
        deck = self.shared_deck("lost")
        word = self.lexeme("kept", deck)
        with get_connection() as connection:                               # access lost, progress row kept
            connection.execute("UPDATE user_deck_subscriptions SET is_active = FALSE WHERE user_id = ? "
                               "AND shared_deck_id = ?", (self.user, deck))
        missing = self.personal("gone")
        with get_connection() as connection:
            connection.execute("DELETE FROM vocab_items WHERE id = ?", (missing,))
        original = migration.dry_run([CardKey("lexeme", self.user, word), CardKey("personal", self.user, missing)])
        lost, gone = original
        self.assertEqual((lost.quality, lost.card_fingerprint is None, lost.card_version is None),
                         ("unavailable", False, False))
        self.assertEqual((gone.quality, gone.card_fingerprint, gone.card_version), ("unavailable", None, None))
        data = self.plan_bytes(original)
        restored = pfile.to_candidates(pfile.parse_plan_bytes(data))
        self.assertEqual(restored, original)
        for before, after in zip(original, restored):
            self.assertEqual([getattr(before, f.name) for f in fields(before)],
                             [getattr(after, f.name) for f in fields(after)])
        self.assertEqual(self.product(restored), self.product(original))

    def test_conversion_uses_the_fixed_bytes(self):
        original = self.candidates()
        plan = pfile.parse_plan_bytes(self.plan_bytes(original))
        forged = replace(plan, account_id=plan.account_id + 1)               # object fields are not trusted
        self.assertEqual(pfile.to_candidates(forged), original)
        tampered = replace(plan, raw=plan.raw.replace(b"run-plan", b"run-plbn"))
        with self.assertRaises(pfile.OpsPlanFileError):
            pfile.to_candidates(tampered)                                      # digest no longer matches


class SignedBinding(pf.Base):
    """The file digest passes only through the signed apply plan (real synthetic signatures)."""

    def setUp(self):
        super().setUp()
        self.folder = tempfile.mkdtemp(prefix="ops_plan_file_bind_")
        self.addCleanup(shutil.rmtree, self.folder, True)

    def file(self, name, value) -> pfile.PlanFile:
        path = os.path.join(self.folder, name)
        pfile.write_plan_file(path, encode(value))
        return pfile.read_plan_file(path)

    def apply_inputs(self, plan_value, artifact):
        inquiry = self.inquiry()
        apply = self.apply(inquiry, plan_value)
        return self.inputs(apply, inquiry=inquiry, inquiry_signature=self.sign(inquiry, "approval"),
                           command="prepare", secret_dsn=self.dsn(role="ops_write_prb"), artifact_sha256=artifact,
                           connection=op.ConnectionObservation(profile=pf.WRITE_PROFILE, read_only=False))

    def test_only_the_signed_file_passes(self):
        plan = self.file("plan.json", doc())
        other = self.file("other.json", doc(candidates=[cand("personal", 1, reconversion="restored",
                                                             restart_json=RESTART)]))
        printed = op.run_synthetic_preflight(self.inputs(self.inquiry(), artifact_sha256=plan.artifact_sha256)).job_plan
        self.assertEqual(op.run_synthetic_preflight(self.apply_inputs(printed, plan.artifact_sha256)).job_plan, printed)
        self.refused("command", "job_plan_mismatch", self.apply_inputs(printed, other.artifact_sha256))
        self.refused("command", "job_plan_mismatch", self.apply_inputs(printed, None))
        # a plan signed without the file: a matching local digest is not a substitute for the signature
        unbound = self.preview_plan()
        self.refused("command", "job_plan_mismatch", self.apply_inputs(unbound, plan.artifact_sha256))


if __name__ == "__main__":
    unittest.main()

"""Operations tool safety contract unit 1 (scripts/_ops_approval.py): approval, fingerprint
and command judgement as pure logic.

No database, environment, clock, file or network: every value is built here. The signature
verifier is a FAKE injected by these tests only; nothing here checks a real signature, a
trust root or cryptographic strength, and the observed role / profile values are made up.

Run directly:      python tests/test_ops_approval.py
Or via discovery:   python -m unittest discover -s tests
"""

from __future__ import annotations

import hashlib
import json
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import _ops_approval as ops  # noqa: E402

SECRET = "s3cr3t-Synthetic-Value-9f1c"
NOW = datetime(2026, 10, 21, 12, 0, 0, tzinfo=timezone.utc)
H = {name: hashlib.sha256(name.encode()).hexdigest()
     for name in ("db", "db2", "manifest", "manifest2", "read_profile", "write_profile", "product", "product2")}
JOB = {"key": "prb-2026-10-21-a", "inputs": {"release_reason": "completed"}}


def _ts(delta_hours: float) -> str:
    return (NOW + timedelta(hours=delta_hours)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read(command: str, **extra) -> dict:
    return {"command": command, "access": "read", "role": "ops_read", "profile": H["read_profile"], **extra}


def _write(command: str, **extra) -> dict:
    return {"command": command, "access": "write", "role": "ops_write_prb", "profile": H["write_profile"], **extra}


def inquiry_doc(**changes) -> dict:
    doc = {"format_version": 1, "kind": "inquiry", "approval_id": "inq-0000000000000001", "supersedes": None,
           "purpose": "synthetic", "alias": "synthetic-primary", "db_identity": H["db"], "manifest": H["manifest"],
           "tool": "prb_recover", "steps": [_read("preview"), _read("status")], "accounts": [7, 8],
           "max_accounts": 2, "job": json.loads(json.dumps(JOB)), "valid_from": _ts(-1), "valid_until": _ts(5),
           "approved_by": "synthetic signer"}
    doc.update(changes)
    return doc


def encode(doc: dict) -> bytes:
    return json.dumps(doc).encode("utf-8")


def link(prior) -> dict:
    """Version 2 `supersedes` (contract 4-6-5): the prior's id and the SHA-256 of its signed bytes.
    Succession tests below were moved from version 1 string ids to this form because version 1
    links are now refused (re-signing required); version 1 behaviour is tested in FormatVersion2."""
    return {"approval_id": prior.approval_id, "sha256": prior.sha256}


class FakeVerifier:
    """Test only: 'signs' by remembering (namespace, sha256(message))."""

    def __init__(self):
        self.signed: set[tuple[str, str]] = set()
        self.calls = 0

    def sign(self, data: bytes, purpose: str = "synthetic") -> bytes:
        digest = hashlib.sha256(data).hexdigest()
        self.signed.add((ops.signature_namespace(purpose), digest))
        return ("fake:" + digest).encode()

    def verify(self, *, namespace: str, message: bytes, signature: bytes) -> bool:
        self.calls += 1
        digest = hashlib.sha256(message).hexdigest()
        return signature == ("fake:" + digest).encode() and (namespace, digest) in self.signed


def observed(access: str = "read", **changes) -> ops.Observed:
    values = {"db_identity": H["db"], "manifest": H["manifest"],
              "role": "ops_read" if access == "read" else "ops_write_prb",
              "profile": H["read_profile"] if access == "read" else H["write_profile"],
              "read_only": access == "read"}
    values.update(changes)
    return ops.Observed(**values)


def plan_for(account: int, product: str | None = H["product"], **changes) -> str:
    values = dict(db_identity=H["db"], manifest=H["manifest"], tool="prb_recover", account_id=account,
                  job_key=JOB["key"], job_inputs=JOB["inputs"], product_fingerprint=product)
    values.update(changes)
    return ops.job_plan_fingerprint(**values)


def judge(approval, command, *, account=7, access=None, product=H["product"], args=None, obs=None, **extra):
    step = next((s for s in approval.steps if s.command == command), None)
    access = access or (step.access if step else "read")
    return ops.authorize_command(
        approval, now=extra.pop("now", NOW), command=command, args=args if args is not None else {},
        account_id=account, job_key=extra.pop("job_key", JOB["key"]),
        job_inputs=extra.pop("job_inputs", JOB["inputs"]), product_fingerprint=product,
        observed=obs or observed(access), **extra)


class Base(unittest.TestCase):
    def setUp(self):
        self.verifier = FakeVerifier()

    def signed(self, doc: dict, mode: str = "synthetic") -> tuple[bytes, ops.Approval]:
        data = encode(doc)
        signature = self.verifier.sign(data, doc.get("purpose", "synthetic"))
        return data, ops.verify_signed(data, signature, mode=mode, verifier=self.verifier)

    def refused(self, code: str, fn, *args, **kwargs):
        with self.assertRaises(ops.OpsApprovalRefused) as caught:
            fn(*args, **kwargs)
        self.assertEqual(caught.exception.code, code)
        return caught.exception

    def apply_pair(self, inquiry_changes=None, apply_changes=None, plans=None):
        inquiry_bytes, inquiry = self.signed(inquiry_doc(**(inquiry_changes or {})))
        doc = inquiry_doc(kind="apply", approval_id="app-0000000000000001",
                          steps=[_read("status"), _write("prepare"), _write("recover"), _write("verify"),
                                 _write("release", args={"reason": "completed"})],
                          based_on={"approval_id": inquiry.approval_id, "sha256": hashlib.sha256(inquiry_bytes).hexdigest()},
                          plan=plans if plans is not None else {"7": plan_for(7), "8": plan_for(8)})
        doc.update(apply_changes or {})
        return inquiry, self.signed(doc)[1]


class InquiryApproval(Base):
    def test_first_preview_without_plan_prints_job_plan(self):
        _, inquiry = self.signed(inquiry_doc())
        self.assertNotIn("plan", json.loads(encode(inquiry_doc())))
        decision = judge(inquiry, "preview", product=H["product"])
        self.assertEqual((decision.kind, decision.access), ("inquiry", "read"))
        self.assertEqual(decision.job_plan, plan_for(7))
        self.assertEqual(judge(inquiry, "status", product=None).job_plan, plan_for(7, None))

    def test_inquiry_cannot_hold_write_steps_or_a_plan(self):
        self.refused("inquiry_write_step_not_allowed", ops.parse_approval,
                     encode(inquiry_doc(steps=[_read("preview"), _write("prepare")])))
        self.refused("approval_fields_invalid", ops.parse_approval, encode(inquiry_doc(plan={"7": plan_for(7)})))
        self.refused("approval_fields_invalid", ops.parse_approval,
                     encode(inquiry_doc(based_on={"approval_id": "x" * 16, "sha256": H["db"]})))
        # a step claiming "read" for a write command is refused by the tool table, not trusted
        self.refused("approval_steps_invalid", ops.parse_approval,
                     encode(inquiry_doc(steps=[{**_read("prepare")}])))

    def test_inquiry_refuses_every_write_command_and_write_connection(self):
        for tool, commands in ops.TOOLS.items():
            reads = [c for c, a in commands.items() if a == "read"]
            _, inquiry = self.signed(inquiry_doc(tool=tool, steps=[_read(c) for c in reads]))
            for command, access in commands.items():
                if access == "write":
                    with self.subTest(tool=tool, command=command):
                        self.refused("command_not_approved", judge, inquiry, command, access="write")
        _, inquiry = self.signed(inquiry_doc())
        self.refused("read_step_not_read_only", judge, inquiry, "preview",
                     obs=observed("read", read_only=False))
        self.refused("connection_profile_mismatch", judge, inquiry, "preview", obs=observed("write"))
        self.refused("inquiry_based_on_not_allowed", judge, inquiry, "preview", inquiry=inquiry)

    def test_role_has_one_access_class(self):
        doc = inquiry_doc(kind="apply", approval_id="app-0000000000000001",
                          steps=[_read("status"), {**_write("prepare"), "role": "ops_read"}],
                          based_on={"approval_id": "inq-0000000000000001", "sha256": H["db"]},
                          plan={"7": plan_for(7), "8": plan_for(8)})
        self.refused("approval_role_access_mixed", ops.parse_approval, encode(doc))


class ApplyApproval(Base):
    def test_inquiry_then_apply_keeps_one_job_plan_through_every_step(self):
        inquiry, apply = self.apply_pair()
        printed = judge(inquiry, "preview").job_plan
        self.assertEqual(apply.plan_for(7), printed)
        steps = [("status", {}), ("prepare", {}), ("recover", {}), ("verify", {}),
                 ("release", {"reason": "completed"}), ("status", {})]
        for command, args in steps:
            with self.subTest(command=command):
                decision = judge(apply, command, args=args, inquiry=inquiry)
                self.assertEqual(decision.job_plan, printed)
        self.assertEqual(judge(apply, "prepare", inquiry=inquiry).access, "write")
        self.assertEqual(judge(apply, "status", inquiry=inquiry).access, "read")

    def test_unapproved_command_role_and_args_are_refused(self):
        inquiry, apply = self.apply_pair()
        self.refused("command_not_approved", judge, apply, "preview", inquiry=inquiry)
        self.refused("command_args_not_approved", judge, apply, "release", args={"reason": "precheck_unrecoverable"},
                     inquiry=inquiry)
        self.refused("command_args_not_approved", judge, apply, "release", args={}, inquiry=inquiry)
        self.refused("connection_profile_mismatch", judge, apply, "prepare", obs=observed("read"), inquiry=inquiry)
        self.refused("connection_profile_mismatch", judge, apply, "prepare",
                     obs=observed("write", role="ops_write_cleanup"), inquiry=inquiry)
        self.refused("write_step_read_only", judge, apply, "prepare", obs=observed("write", read_only=True),
                     inquiry=inquiry)
        self.refused("connection_profile_mismatch", judge, apply, "status", obs=observed("write"), inquiry=inquiry)

    def test_plan_missing_or_different(self):
        self.refused("apply_plan_invalid", self.apply_pair, plans={"7": plan_for(7)})
        self.refused("apply_plan_invalid", self.apply_pair, plans={})
        inquiry, apply = self.apply_pair(plans={"7": plan_for(7, H["product2"]), "8": plan_for(8)})
        self.refused("job_plan_mismatch", judge, apply, "prepare", inquiry=inquiry)
        inquiry, apply = self.apply_pair()
        self.refused("job_plan_mismatch", judge, apply, "prepare", product=H["product2"], inquiry=inquiry)
        self.refused("job_plan_mismatch", judge, apply, "prepare", product=None, inquiry=inquiry)

    def test_observed_target_manifest_account_job_mismatch(self):
        inquiry, apply = self.apply_pair()
        cases = [
            ("db_identity_mismatch", dict(obs=observed("write", db_identity=H["db2"]))),
            ("manifest_mismatch", dict(obs=observed("write", manifest=H["manifest2"]))),
            ("account_not_approved", dict(account=9)),
            ("job_input_mismatch", dict(job_key="prb-other")),
            ("job_input_mismatch", dict(job_inputs={"release_reason": "other"})),
            ("job_input_mismatch", dict(job_inputs={})),
        ]
        for code, extra in cases:
            with self.subTest(code=code, extra=sorted(extra)):
                self.refused(code, judge, apply, "prepare", inquiry=inquiry, **extra)
                self.refused(code, judge, inquiry, "preview", **{**extra, "obs": extra.get("obs") and
                                                                 observed("read", **{k: getattr(extra["obs"], k) for k in
                                                                                     ("db_identity", "manifest")})})

    def test_apply_must_match_its_inquiry(self):
        for field, value in [("db_identity", H["db2"]), ("manifest", H["manifest2"]), ("alias", "other-target"),
                             ("tool", "delete_account"), ("job", {"key": "prb-other", "inputs": JOB["inputs"]}),
                             ("job", {"key": JOB["key"], "inputs": {"release_reason": "x"}})]:
            with self.subTest(field=field, value=str(value)):
                changes = {field: value}
                command = "prepare"
                if field == "tool":
                    changes["steps"] = [_write("apply", role="ops_write_delete")]
                    command = "apply"
                inquiry, apply = self.apply_pair(apply_changes=changes)
                self.refused("apply_basis_field_mismatch", judge, apply, command, inquiry=inquiry)
        self.refused("apply_plan_invalid", ops.parse_approval,
                     encode(inquiry_doc(kind="apply", approval_id="app-0000000000000001", accounts=[7],
                                        based_on={"approval_id": "inq-0000000000000001", "sha256": H["db"]},
                                        plan={"7": plan_for(7), "8": plan_for(8)})))
        inquiry_bytes, inquiry = self.signed(inquiry_doc())
        doc = inquiry_doc(kind="apply", approval_id="app-0000000000000002", steps=[_write("prepare")],
                          accounts=[7, 9], based_on={"approval_id": inquiry.approval_id,
                                                     "sha256": hashlib.sha256(inquiry_bytes).hexdigest()},
                          plan={"7": plan_for(7), "9": plan_for(9)})
        self.refused("apply_accounts_outside_inquiry", judge, self.signed(doc)[1], "prepare", inquiry=inquiry)

    def test_subset_of_accounts_is_allowed(self):
        _, inquiry = self.signed(inquiry_doc())
        inquiry_bytes = encode(inquiry_doc())
        doc = inquiry_doc(kind="apply", approval_id="app-0000000000000003", steps=[_write("prepare")], accounts=[8],
                          max_accounts=1, based_on={"approval_id": inquiry.approval_id,
                                                    "sha256": hashlib.sha256(inquiry_bytes).hexdigest()},
                          plan={"8": plan_for(8)})
        self.assertEqual(judge(self.signed(doc)[1], "prepare", account=8, inquiry=inquiry).job_plan, plan_for(8))


class Validity(Base):
    def test_expired_future_and_length(self):
        _, approval = self.signed(inquiry_doc())
        self.refused("approval_expired", judge, approval, "preview", now=NOW + timedelta(hours=5))
        self.refused("approval_not_yet_valid", judge, approval, "preview", now=NOW - timedelta(hours=1, seconds=1))
        self.assertEqual(judge(approval, "preview", now=NOW - timedelta(hours=1)).kind, "inquiry")
        self.refused("approval_validity_too_long", ops.parse_approval,
                     encode(inquiry_doc(valid_from=_ts(0), valid_until=_ts(24 + 1 / 3600))))
        ops.parse_approval(encode(inquiry_doc(valid_from=_ts(0), valid_until=_ts(24))))
        self.refused("approval_time_invalid", ops.parse_approval, encode(inquiry_doc(valid_until=_ts(-1))))
        for bad in ("2026-10-21T12:00:00+00:00", "2026-10-21 12:00:00Z", "2026-02-30T00:00:00Z", 1792540800):
            with self.subTest(bad=bad):
                self.refused("approval_time_invalid", ops.parse_approval, encode(inquiry_doc(valid_from=bad)))
        for clock in (NOW.replace(tzinfo=None), NOW.astimezone(timezone(timedelta(hours=9))), "2026-10-21"):
            with self.subTest(clock=str(clock)):
                self.refused("clock_value_invalid", judge, approval, "preview", now=clock)

    def test_expired_inquiry_is_still_a_basis_but_not_a_permission(self):
        inquiry, apply = self.apply_pair(inquiry_changes={"valid_from": _ts(-3), "valid_until": _ts(-2)},
                                         apply_changes={"valid_from": _ts(-1), "valid_until": _ts(5)})
        self.assertEqual(judge(apply, "prepare", inquiry=inquiry).kind, "apply")
        self.refused("approval_expired", judge, inquiry, "preview")


class Links(Base):
    def test_based_on_damage_and_kind(self):
        inquiry, apply = self.apply_pair()
        self.refused("apply_based_on_missing", judge, apply, "prepare")
        _, other = self.signed(inquiry_doc(approval_id="inq-0000000000000002"))
        self.refused("apply_based_on_mismatch", judge, apply, "prepare", inquiry=other)
        inquiry_bytes = encode(inquiry_doc())
        bad = inquiry_doc(kind="apply", approval_id="app-0000000000000004", steps=[_write("prepare")],
                          based_on={"approval_id": inquiry.approval_id, "sha256": H["db"]},
                          plan={"7": plan_for(7), "8": plan_for(8)})
        self.refused("apply_based_on_mismatch", judge, self.signed(bad)[1], "prepare", inquiry=inquiry)
        self.refused("apply_based_on_kind_mismatch", judge, apply, "prepare", inquiry=apply)
        for broken in (None, {"approval_id": inquiry.approval_id}, {"approval_id": 5, "sha256": H["db"]},
                       {"approval_id": inquiry.approval_id, "sha256": hashlib.sha256(inquiry_bytes).hexdigest().upper()}):
            with self.subTest(broken=broken):
                doc = inquiry_doc(kind="apply", approval_id="app-0000000000000005", steps=[_write("prepare")],
                                  based_on=broken, plan={"7": plan_for(7), "8": plan_for(8)})
                self.refused("apply_based_on_invalid", ops.parse_approval, encode(doc))

    def test_supersedes_same_kind_only(self):
        _, first = self.signed(inquiry_doc())
        _, second = self.signed(inquiry_doc(approval_id="inq-0000000000000002", format_version=2, supersedes=link(first)))
        self.assertEqual(judge(second, "status", prior=first, product=None).kind, "inquiry")
        self.assertEqual(judge(first, "status", prior=first, product=None).kind, "inquiry")
        _, stray = self.signed(inquiry_doc(approval_id="inq-0000000000000003"))
        self.refused("approval_supersedes_mismatch", judge, stray, "status", prior=first)
        _, wrong = self.signed(inquiry_doc(approval_id="inq-0000000000000004", format_version=2,
                                           supersedes={"approval_id": "inq-0000000000000099", "sha256": H["db"]}))
        self.refused("approval_supersedes_mismatch", judge, wrong, "status", prior=first)
        self.refused("approval_supersedes_unknown", judge, second, "status")
        inquiry, apply = self.apply_pair()
        self.refused("approval_supersedes_kind_mismatch", judge, second, "status", prior=apply)
        _, other_job = self.signed(inquiry_doc(approval_id="inq-0000000000000005", format_version=2, supersedes=link(first),
                                               job={"key": "prb-other", "inputs": JOB["inputs"]}))
        self.refused("approval_job_mismatch", judge, other_job, "status", prior=first, job_key="prb-other")
        _, reused = self.signed(inquiry_doc(valid_until=_ts(4)))
        self.refused("approval_id_reused", judge, reused, "status", prior=first)
        self.refused("approval_supersedes_invalid", ops.parse_approval,
                     encode(inquiry_doc(format_version=2,
                                        supersedes={"approval_id": "inq-0000000000000001", "sha256": H["db"]})))

    def test_new_apply_supersedes_old_apply_and_keeps_its_own_basis(self):
        inquiry, old = self.apply_pair()
        inquiry_bytes = encode(inquiry_doc())
        doc = inquiry_doc(kind="apply", approval_id="app-0000000000000009", format_version=2, supersedes=link(old),
                          steps=[_write("recover")], accounts=[7], max_accounts=1,
                          based_on={"approval_id": inquiry.approval_id,
                                    "sha256": hashlib.sha256(inquiry_bytes).hexdigest()},
                          plan={"7": plan_for(7)})
        new = self.signed(doc)[1]
        self.assertEqual(judge(new, "recover", inquiry=inquiry, prior=old).kind, "apply")
        self.refused("approval_supersedes_kind_mismatch", judge, new, "recover", inquiry=inquiry, prior=inquiry)


class Types(Base):
    def test_strings_and_booleans_are_not_numbers(self):
        cases = [("accounts", ["7"]), ("accounts", [True]), ("accounts", [0]),
                 ("accounts", [7, 7]), ("accounts", []), ("accounts", [2 ** 63]), ("max_accounts", "2"),
                 ("max_accounts", True), ("max_accounts", 1)]
        for field, value in cases:
            with self.subTest(field=field, value=value):
                self.refused("approval_accounts_invalid", ops.parse_approval, encode(inquiry_doc(**{field: value})))
        for value in (True, "1", "2", 0, 4, None):         # 3 exists since RESUME_PLAN 9-3
            with self.subTest(format_version=value):
                self.refused("approval_format_version", ops.parse_approval, encode(inquiry_doc(format_version=value)))
        _, approval = self.signed(inquiry_doc(accounts=[1, 8]))
        self.refused("account_not_approved", judge, approval, "preview", account=True)
        self.refused("account_not_approved", judge, approval, "preview", account="1")
        _, typed = self.signed(inquiry_doc(job={"key": JOB["key"], "inputs": {"batch": 1}}))
        self.refused("job_input_mismatch", judge, typed, "preview", job_inputs={"batch": True})
        self.refused("job_input_mismatch", judge, typed, "preview", job_inputs={"batch": "1"})
        self.assertNotEqual(plan_for(7, job_inputs={"batch": 1}), plan_for(7, job_inputs={"batch": True}))
        for kwargs in (dict(port="5432"), dict(port=True), dict(server_major=True), dict(server_major="18")):
            with self.subTest(**{k: repr(v) for k, v in kwargs.items()}):
                values = dict(alias="synthetic-primary", host="db.example.test", port=5432, database="app",
                              server_major=18, identity_value="row-1")
                values.update(kwargs)
                self.refused("db_identity_value_invalid", ops.db_identity_fingerprint, **values)
        self.refused("plan_value_invalid", plan_for, True)
        self.refused("plan_value_invalid", plan_for, 7, product="ABC")

    def test_strict_json(self):
        good = encode(inquiry_doc()).decode()
        for data in (good.replace('"max_accounts": 2', '"max_accounts": 2, "max_accounts": 3').encode(),
                     good.replace('"max_accounts": 2', '"max_accounts": NaN').encode(),
                     good.replace('"max_accounts": 2', '"max_accounts": 2.0').encode(),
                     b"\xef\xbb\xbf" + good.encode(), b"[]", b"", "x".encode() * (ops.MAX_APPROVAL_BYTES + 1),
                     b"\xff\xfe", good.replace('"accounts": [7, 8]', '"accounts": [7.0, 8]').encode(),
                     good.replace('"format_version": 1', '"format_version": 1.0').encode()):
            with self.subTest(data=data[:20]):
                self.refused("approval_format_invalid", ops.parse_approval, data)
        self.refused("approval_fields_invalid", ops.parse_approval, encode(inquiry_doc(extra=1)))
        self.refused("approval_kind_invalid", ops.parse_approval, encode(inquiry_doc(kind="read")))
        self.refused("approval_purpose_invalid", ops.parse_approval, encode(inquiry_doc(purpose="prod")))
        self.refused("approval_tool_invalid", ops.parse_approval, encode(inquiry_doc(tool="psql")))


class Fingerprints(Base):
    def test_reproducible_and_scoped(self):
        values = dict(alias="synthetic-primary", host="DB.Example.test", port=5432, database="app",
                      server_major=18, identity_value="row-1")
        first = ops.db_identity_fingerprint(**values)
        self.assertEqual(first, ops.db_identity_fingerprint(**{**values, "host": "db.example.test"}))
        for field, value in (("port", 5433), ("database", "app2"), ("server_major", 19), ("identity_value", "row-2"),
                             ("alias", "synthetic-other")):
            with self.subTest(field=field):
                self.assertNotEqual(first, ops.db_identity_fingerprint(**{**values, field: value}))
        self.assertEqual(plan_for(7), plan_for(7))
        self.assertEqual(plan_for(7, job_inputs={"b": 1, "a": None}), plan_for(7, job_inputs={"a": None, "b": 1}))
        for change in (dict(db_identity=H["db2"]), dict(manifest=H["manifest2"]), dict(tool="delete_account"),
                       dict(account_id=8), dict(job_key="other"), dict(job_inputs={}), dict(product_fingerprint=None)):
            with self.subTest(change=sorted(change)):
                self.assertNotEqual(plan_for(7), plan_for(7, **change) if "product_fingerprint" not in change
                                    else plan_for(7, None))

    def test_command_and_role_change_the_decision_not_the_plan(self):
        inquiry, apply = self.apply_pair()
        plans = {judge(apply, c, args=a, inquiry=inquiry).job_plan
                 for c, a in (("prepare", {}), ("verify", {}), ("release", {"reason": "completed"}))}
        self.assertEqual(plans, {plan_for(7)})
        self.refused("connection_profile_mismatch", judge, apply, "verify",
                     obs=observed("write", role="ops_write_other"), inquiry=inquiry)


class Secrets(Base):
    def test_refusals_carry_only_the_code(self):
        _, approval = self.signed(inquiry_doc(job={"key": JOB["key"], "inputs": {"note": SECRET}}))
        attempts = [
            lambda: ops.parse_approval(encode(inquiry_doc(alias=SECRET))),
            lambda: ops.parse_approval(encode(inquiry_doc(approved_by=SECRET + "\n"))),
            lambda: ops.parse_approval((encode(inquiry_doc()).decode() + SECRET).encode()),
            lambda: judge(approval, "preview", job_inputs={"note": SECRET + "x"}),
            lambda: judge(approval, "preview", obs=observed("read", role=SECRET)),
            lambda: judge(approval, "preview", obs=observed("read", db_identity=SECRET)),
            lambda: judge(approval, "preview", obs=observed("read", profile=SECRET)),
            lambda: ops.db_identity_fingerprint(alias="a", host=SECRET + "!", port=1, database="d", server_major=1,
                                                identity_value="v"),
            lambda: ops.verify_signed(encode(inquiry_doc()), SECRET.encode(), mode="synthetic", verifier=self.verifier),
        ]
        for index, attempt in enumerate(attempts):
            with self.subTest(index=index):
                with self.assertRaises(ops.OpsApprovalRefused) as caught:
                    attempt()
                error = caught.exception
                self.assertEqual(error.args, (error.code,))
                self.assertNotIn(SECRET, repr(error) + str(error) + error.code)
                self.assertTrue(error.__suppress_context__ or error.__context__ is None)


class Signatures(Base):
    def test_no_implementation_refuses_before_action(self):
        called = []
        doc = inquiry_doc(purpose="ops")
        data = encode(doc)
        signature = self.verifier.sign(data, "ops")
        error = self.refused("signature_verifier_not_implemented", ops.run_authorized, called.append, mode="ops",
                             approval_bytes=data, approval_signature=signature, now=NOW, command="preview", args={},
                             account_id=7, job_key=JOB["key"], job_inputs=JOB["inputs"],
                             product_fingerprint=None, observed=observed("read"))
        self.assertEqual(called, [])
        self.assertEqual(self.verifier.calls, 0)
        self.refused("signature_verifier_not_implemented", ops.production_verifier)
        self.refused("signature_verifier_unavailable", ops.verify_signed, data, signature, mode="ops", verifier=None)
        self.assertNotIn(SECRET, str(error))

    def test_injected_fake_runs_action_only_after_judgement(self):
        called = []
        data = encode(inquiry_doc())
        signature = self.verifier.sign(data)
        result = ops.run_authorized(lambda d: called.append(d) or "done", mode="synthetic", approval_bytes=data,
                                    approval_signature=signature, verifier_factory=lambda: self.verifier, now=NOW,
                                    command="preview", args={}, account_id=7, job_key=JOB["key"],
                                    job_inputs=JOB["inputs"], product_fingerprint=H["product"],
                                    observed=observed("read"))
        self.assertEqual((result, called[0].job_plan), ("done", plan_for(7)))
        self.refused("command_not_approved", ops.run_authorized, called.append, mode="synthetic",
                     approval_bytes=data, approval_signature=signature, verifier_factory=lambda: self.verifier,
                     now=NOW, command="prepare", args={}, account_id=7, job_key=JOB["key"],
                     job_inputs=JOB["inputs"], product_fingerprint=H["product"], observed=observed("write"))
        self.assertEqual(len(called), 1)

    def test_signature_and_purpose_are_required(self):
        data = encode(inquiry_doc())
        signature = self.verifier.sign(data)
        self.refused("approval_purpose_mismatch", ops.verify_signed, data, signature, mode="ops", verifier=self.verifier)
        ops_data = encode(inquiry_doc(purpose="ops"))
        test_signed = self.verifier.sign(ops_data, "synthetic")  # signed under the synthetic namespace only
        self.refused("approval_signature_invalid", ops.verify_signed, ops_data, test_signed, mode="ops",
                     verifier=self.verifier)
        self.refused("approval_signature_invalid", ops.verify_signed, data, b"", mode="synthetic", verifier=self.verifier)
        self.refused("approval_signature_invalid", ops.verify_signed, data + b" ", signature, mode="synthetic",
                     verifier=self.verifier)

        class Truthy:
            def verify(self, **_):
                return 1

        class Broken:
            def verify(self, **_):
                raise RuntimeError(SECRET)

        for verifier in (Truthy(), Broken()):
            with self.subTest(verifier=type(verifier).__name__):
                error = self.refused("approval_signature_invalid", ops.verify_signed, data, signature,
                                     mode="synthetic", verifier=verifier)
                self.assertNotIn(SECRET, repr(error))
        self.refused("mode_invalid", ops.verify_signed, data, signature, mode="prod", verifier=self.verifier)
        self.refused("apply_based_on_missing", ops.run_authorized, print, mode="synthetic",
                     approval_bytes=self.apply_bytes(), approval_signature=self.verifier.sign(self.apply_bytes()),
                     verifier_factory=lambda: self.verifier, now=NOW)

    def apply_bytes(self) -> bytes:
        return encode(inquiry_doc(kind="apply", approval_id="app-0000000000000001", steps=[_write("prepare")],
                                  based_on={"approval_id": "inq-0000000000000001", "sha256": H["db"]},
                                  plan={"7": plan_for(7), "8": plan_for(8)}))

    def test_module_has_no_io_or_bypass(self):
        source = (SCRIPTS_DIR / "_ops_approval.py").read_text(encoding="utf-8")
        for forbidden in ("import os", "os.environ", "getenv", "datetime.now", "utcnow", "time.time", "open(", "socket",
                          "psycopg", "sqlite3", "from app", "import app", "skip_signature", "urllib", "subprocess"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


class InputBoundaries(Base):
    """Review fix: malformed observed values and command arguments end in the existing fixed
    codes, never in a TypeError from comparing or sorting them."""

    BAD_TEXT = ["é" * 64, "A" * 64, "a" * 63, "a" * 65, "", None, True, 7, 1.5, ["a" * 64], {"a": 1},
                b"a" * 64, " " + "a" * 63]

    def test_observed_fingerprints_must_be_lowercase_hex(self):
        _, inquiry = self.signed(inquiry_doc())
        for field in ("db_identity", "manifest", "profile"):
            for value in self.BAD_TEXT + [SECRET]:
                with self.subTest(field=field, value=repr(value)[:20]):
                    error = self.refused("observed_value_invalid", judge, inquiry, "preview",
                                         obs=observed("read", **{field: value}))
                    self.assertNotIn(SECRET, repr(error))

    def test_observed_role_and_read_only_types(self):
        _, inquiry = self.signed(inquiry_doc())
        for value in ["ops_réad", "Ops_read", "", None, True, 7, ["ops_read"], {"r": 1}, b"ops_read", SECRET]:
            with self.subTest(role=repr(value)[:20]):
                self.refused("observed_value_invalid", judge, inquiry, "preview", obs=observed("read", role=value))
        for value in (None, 1, 0, "true", []):
            with self.subTest(read_only=repr(value)):
                self.refused("observed_value_invalid", judge, inquiry, "preview",
                             obs=observed("read", read_only=value))
        self.refused("observed_value_invalid", judge, inquiry, "preview", obs={"db_identity": H["db"]})

    def test_command_args_keys_and_values(self):
        inquiry, apply = self.apply_pair()
        bad_args = [{"reason": "completed", 1: "x"}, {1: "completed"}, {None: "completed"},
                    {"reason": 1}, {"reason": None}, {"reason": True}, {"reason": ["completed"]},
                    {"reason": {"a": 1}}, {"reason": "complété"}, {"reason": SECRET + " !"}, {"Reason": "completed"},
                    {b"reason": "completed"}, ["reason"], "reason=completed", None]
        for args in bad_args:
            with self.subTest(args=repr(args)[:30]):
                error = self.refused("command_args_not_approved", judge, apply, "release", args=args, inquiry=inquiry)
                self.assertNotIn(SECRET, repr(error))
        self.assertEqual(judge(apply, "release", args={"reason": "completed"}, inquiry=inquiry).kind, "apply")

    def test_command_name_types(self):
        _, inquiry = self.signed(inquiry_doc())
        for command in (None, 1, True, ["preview"], {"c": 1}, b"preview", "préview"):
            with self.subTest(command=repr(command)[:20]):
                self.refused("command_not_approved", judge, inquiry, command)


class SupersedesScope(Base):
    """Contract 4-6-4 (review fix): a chain is one kind, tool, purpose and job key; changed DB
    identity / manifest must be written in the new signed approval and observed; every apply
    approval re-proves its own basis, plan and accounts; nothing is inherited or merged."""

    def basis(self, approval_id="inq-0000000000000001", **changes):
        data, inquiry = self.signed(inquiry_doc(approval_id=approval_id, **changes))
        return {"approval_id": inquiry.approval_id, "sha256": hashlib.sha256(data).hexdigest()}, inquiry

    def apply_doc(self, approval_id, based_on, accounts, steps, supersedes=None, **changes):
        plan_values = {k: changes.pop(k) for k in ("db_identity", "manifest") if k in changes}
        plans = {str(a): plan_for(a, **plan_values) for a in accounts}
        return inquiry_doc(kind="apply", approval_id=approval_id, supersedes=supersedes, based_on=based_on,
                           format_version=1 if supersedes is None else 2,
                           accounts=accounts, max_accounts=len(accounts), steps=steps, plan=plans,
                           **plan_values, **changes)

    def test_changed_identity_and_manifest_must_be_written_and_observed(self):
        _, first = self.signed(inquiry_doc())
        _, second = self.signed(inquiry_doc(approval_id="inq-0000000000000002", format_version=2, supersedes=link(first),
                                            db_identity=H["db2"], manifest=H["manifest2"]))
        new_obs = observed("read", db_identity=H["db2"], manifest=H["manifest2"])
        decision = judge(second, "status", prior=first, obs=new_obs, product=None)
        self.assertEqual(decision.job_plan, plan_for(7, None, db_identity=H["db2"], manifest=H["manifest2"]))
        self.refused("db_identity_mismatch", judge, second, "status", prior=first,
                     obs=observed("read", manifest=H["manifest2"]))
        self.refused("manifest_mismatch", judge, second, "status", prior=first,
                     obs=observed("read", db_identity=H["db2"]))
        # the old approval keeps its own values: it does not follow the new one
        self.refused("db_identity_mismatch", judge, first, "status", obs=new_obs)

    def test_chain_is_one_kind_tool_purpose_and_job(self):
        _, first = self.signed(inquiry_doc())
        for changes, code in ((dict(tool="srs_invariant_audit", steps=[_read("audit")]), "approval_job_mismatch"),
                              (dict(job={"key": "prb-other", "inputs": JOB["inputs"]}), "approval_job_mismatch")):
            with self.subTest(changes=sorted(changes)):
                _, second = self.signed(inquiry_doc(approval_id="inq-0000000000000002",
                                                    format_version=2, supersedes=link(first), **changes))
                command = second.steps[0].command
                self.refused(code, ops.check_succession, second, first)
                self.refused(code, judge, second, command, prior=first, job_key=second.job_key)
        ops_prior = ops.parse_approval(encode(inquiry_doc(purpose="ops")))
        _, second = self.signed(inquiry_doc(approval_id="inq-0000000000000002", format_version=2, supersedes=link(first)))
        self.refused("approval_job_mismatch", ops.check_succession, second, ops_prior)

    def test_new_apply_reproves_basis_plan_and_accounts(self):
        ref1, inquiry1 = self.basis(accounts=[7, 8, 9], max_accounts=3)
        old = self.signed(self.apply_doc("app-0000000000000001", ref1, [7], [_write("prepare"), _write("verify")]))[1]
        # widening to 8 is allowed only because the new apply's own basis covers it
        new = self.signed(self.apply_doc("app-0000000000000002", ref1, [7, 8], [_write("prepare")],
                                         supersedes=link(old)))[1]
        self.assertEqual(judge(new, "prepare", account=8, inquiry=inquiry1, prior=old).job_plan, plan_for(8))
        # a basis that does not cover the widened account refuses, whatever the old apply had
        ref2, inquiry2 = self.basis("inq-0000000000000002", accounts=[7])
        wide = self.signed(self.apply_doc("app-0000000000000003", ref2, [7, 8], [_write("prepare")],
                                          supersedes=link(old)))[1]
        self.refused("apply_accounts_outside_inquiry", judge, wide, "prepare", inquiry=inquiry2, prior=old)
        # the new apply's own basis is checked even with a valid prior
        broken = self.signed(self.apply_doc("app-0000000000000004", {**ref1, "sha256": H["db"]}, [7],
                                            [_write("prepare")], supersedes=link(old)))[1]
        self.refused("apply_based_on_mismatch", judge, broken, "prepare", inquiry=inquiry1, prior=old)
        # its own plan is checked: a plan copied for other values does not pass
        doc = self.apply_doc("app-0000000000000005", ref1, [7], [_write("prepare")], supersedes=link(old))
        doc["plan"] = {"7": plan_for(7, H["product2"])}
        self.refused("job_plan_mismatch", judge, self.signed(doc)[1], "prepare", inquiry=inquiry1, prior=old)

    def test_accounts_and_permissions_are_not_inherited_or_merged(self):
        ref, inquiry = self.basis()
        old = self.signed(self.apply_doc("app-0000000000000001", ref, [7, 8],
                                         [_write("prepare"), _write("verify")]))[1]
        new = self.signed(self.apply_doc("app-0000000000000002", ref, [8], [_write("prepare")],
                                         supersedes=link(old)))[1]
        self.refused("account_not_approved", judge, new, "prepare", account=7, inquiry=inquiry, prior=old)
        self.refused("command_not_approved", judge, new, "verify", inquiry=inquiry, prior=old, account=8)
        self.refused("connection_profile_mismatch", judge, new, "prepare", account=8, inquiry=inquiry, prior=old,
                     obs=observed("write", role="ops_write_other"))
        self.assertEqual(judge(old, "verify", account=7, inquiry=inquiry).access, "write")

    def test_apply_after_identity_change_needs_a_matching_new_basis(self):
        ref1, inquiry1 = self.basis()
        old = self.signed(self.apply_doc("app-0000000000000001", ref1, [7], [_write("prepare")]))[1]
        ref2, inquiry2 = self.basis("inq-0000000000000002", db_identity=H["db2"])
        new = self.signed(self.apply_doc("app-0000000000000002", ref2, [7], [_write("prepare")],
                                         supersedes=link(old), db_identity=H["db2"]))[1]
        obs = observed("write", db_identity=H["db2"])
        self.assertEqual(judge(new, "prepare", inquiry=inquiry2, prior=old, obs=obs).job_plan,
                         plan_for(7, db_identity=H["db2"]))
        self.refused("apply_based_on_mismatch", judge, new, "prepare", inquiry=inquiry1, prior=old, obs=obs)
        self.refused("db_identity_mismatch", judge, old, "prepare", inquiry=inquiry1, obs=obs)



ARTIFACT, ARTIFACT2 = hashlib.sha256(b"plan file 1").hexdigest(), hashlib.sha256(b"plan file 2").hexdigest()
# Pinned before contract 3-3-1 was added (2026-10-25): plan_for(7) and plan_for(7, None) with these fixtures.
PINNED_PLAN = "274b6c579e145eb9a50790a44e9ba64b7c1706bb48c9749874e49f8a03dafa2d"
PINNED_PLAN_NO_PRODUCT = "44ccb97e71ae9d25b232b7b438b9612e80b5e41d597cccafe1afed172ebc8a1f"
BAD_ARTIFACTS = {"uppercase": ARTIFACT.upper(), "63 chars": ARTIFACT[:-1], "65 chars": ARTIFACT + "0",
                 "empty": "", "spaces": " " + ARTIFACT[1:], "non-ascii digits": "\uff10" * 64,
                 "non-hex": "g" * 64, "secret text": SECRET.ljust(64, "x")[:64], "bytes": ARTIFACT.encode(),
                 "true": True, "false": False, "int": 1, "float": 1.0, "list": [ARTIFACT], "dict": {"a": ARTIFACT},
                 "tuple": (ARTIFACT,)}


class ArtifactBinding(Base):
    """Contract 3-3-1: plan artifact digest bound into the signed apply plan."""

    def test_none_keeps_the_pinned_existing_values(self):
        self.assertEqual(plan_for(7), PINNED_PLAN)
        self.assertEqual(plan_for(7, artifact_sha256=None), PINNED_PLAN)
        self.assertEqual(plan_for(7, None), PINNED_PLAN_NO_PRODUCT)
        _, inquiry = self.signed(inquiry_doc())
        self.assertEqual(judge(inquiry, "preview").job_plan, PINNED_PLAN)
        self.assertEqual(judge(inquiry, "preview", artifact_sha256=None).job_plan, PINNED_PLAN)

    def test_artifact_changes_the_plan_for_the_same_product(self):
        plans = {plan_for(7), plan_for(7, artifact_sha256=ARTIFACT), plan_for(7, artifact_sha256=ARTIFACT2)}
        self.assertEqual(len(plans), 3)
        self.assertEqual(plan_for(7, artifact_sha256=ARTIFACT), plan_for(7, artifact_sha256=ARTIFACT))
        self.assertNotEqual(plan_for(7, None, artifact_sha256=ARTIFACT), plan_for(7, artifact_sha256=ARTIFACT))

    def test_signed_apply_plan_binds_the_artifact(self):
        _, inquiry = self.signed(inquiry_doc())
        printed = judge(inquiry, "preview", artifact_sha256=ARTIFACT).job_plan      # the inquiry prints it
        inquiry, apply = self.apply_pair(plans={"7": printed, "8": plan_for(8, artifact_sha256=ARTIFACT)})
        self.assertEqual(judge(apply, "prepare", inquiry=inquiry, artifact_sha256=ARTIFACT).job_plan, printed)
        self.refused("job_plan_mismatch", judge, apply, "prepare", inquiry=inquiry, artifact_sha256=ARTIFACT2)
        self.refused("job_plan_mismatch", judge, apply, "prepare", inquiry=inquiry)              # missing
        self.refused("job_plan_mismatch", judge, apply, "prepare", inquiry=inquiry, artifact_sha256=None)
        inquiry, apply = self.apply_pair()                                                       # plan without one
        self.refused("job_plan_mismatch", judge, apply, "prepare", inquiry=inquiry, artifact_sha256=ARTIFACT)

    def test_the_artifact_is_not_a_job_input(self):
        # the inquiry has no artifact yet; the apply job must equal the inquiry job (contract 4-6-2)
        _, inquiry = self.signed(inquiry_doc())
        self.assertEqual(inquiry.job_inputs, tuple(sorted(JOB["inputs"].items())))
        inquiry, apply = self.apply_pair(plans={"7": plan_for(7, artifact_sha256=ARTIFACT),
                                                "8": plan_for(8, artifact_sha256=ARTIFACT)})
        self.assertEqual(apply.job_inputs, inquiry.job_inputs)

    def test_bad_values_are_refused_without_conversion_or_leak(self):
        inquiry, apply = self.apply_pair()
        for label, value in BAD_ARTIFACTS.items():
            for where, attempt in (("fingerprint", lambda: plan_for(7, artifact_sha256=value)),
                                   ("judge", lambda: judge(apply, "prepare", inquiry=inquiry, artifact_sha256=value))):
                with self.subTest(case=label, where=where):
                    error = self.refused("artifact_sha256_invalid", attempt)
                    self.assertEqual(error.args, (error.code,))
                    self.assertNotIn(SECRET, repr(error) + str(error))
                    self.assertTrue(error.__suppress_context__ or error.__context__ is None)

    def test_run_authorized_passes_the_value(self):
        _, inquiry = self.signed(inquiry_doc())
        data = encode(inquiry_doc())
        seen = []
        result = ops.run_authorized(lambda decision: seen.append(decision) or "ran", mode="synthetic",
                                    approval_bytes=data, approval_signature=self.verifier.sign(data),
                                    verifier_factory=lambda: self.verifier, now=NOW, command="preview", args={},
                                    account_id=7, job_key=JOB["key"], job_inputs=JOB["inputs"],
                                    product_fingerprint=H["product"], observed=observed(), artifact_sha256=ARTIFACT)
        self.assertEqual((result, seen[0].job_plan), ("ran", plan_for(7, artifact_sha256=ARTIFACT)))


class FormatVersion2(Base):
    """Contract 4-6-5: version 2 binds `supersedes` to the prior approval's signed bytes."""

    def test_version_1_first_approval_is_kept(self):
        data, first = self.signed(inquiry_doc())
        self.assertEqual((first.format_version, first.supersedes, first.verified), (1, None, True))
        self.assertEqual(first.sha256, hashlib.sha256(data).hexdigest())
        self.assertEqual(judge(first, "preview").job_plan, PINNED_PLAN)          # existing fingerprint kept
        self.assertFalse(ops.parse_approval(data).verified)                      # only verify_signed sets it

    def test_version_1_link_needs_re_signing_and_is_never_converted(self):
        for value in ("inq-0000000000000001", {"approval_id": "inq-0000000000000001", "sha256": H["db"]}):
            doc = inquiry_doc(approval_id="inq-0000000000000002", supersedes=value)
            with self.subTest(value=type(value).__name__):
                error = self.refused("approval_supersedes_resign_required", ops.parse_approval, encode(doc))
                self.assertEqual(error.args, (error.code,))
                data = encode(doc)
                self.refused("approval_supersedes_resign_required", ops.verify_signed, data,
                             self.verifier.sign(data), mode="synthetic", verifier=self.verifier)

    def test_version_2_first_and_linked_approvals(self):
        _, first = self.signed(inquiry_doc(format_version=2))
        self.assertEqual((first.format_version, first.supersedes), (2, None))
        self.assertEqual(judge(first, "preview").job_plan, PINNED_PLAN)          # the version is not in the plan
        _, second = self.signed(inquiry_doc(approval_id="inq-0000000000000002", format_version=2,
                                            supersedes=link(first)))
        self.assertEqual(second.supersedes, (first.approval_id, first.sha256))
        ops.check_succession(second, first)
        self.assertEqual(judge(second, "status", prior=first, product=None).kind, "inquiry")

    def test_version_2_may_point_at_a_version_1_first_approval(self):
        _, first_v1 = self.signed(inquiry_doc())
        _, second = self.signed(inquiry_doc(approval_id="inq-0000000000000002", format_version=2,
                                            supersedes=link(first_v1)))
        ops.check_succession(second, first_v1)
        self.refused("approval_prior_unverified", ops.check_succession, second,
                     ops.parse_approval(encode(inquiry_doc())))                  # same bytes, signature not checked

    def test_same_id_different_bytes_and_wrong_links(self):
        _, first = self.signed(inquiry_doc())
        _, twin = self.signed(inquiry_doc(valid_until=_ts(4)))                   # same id, other bytes
        _, second = self.signed(inquiry_doc(approval_id="inq-0000000000000002", format_version=2,
                                            supersedes=link(first)))
        self.refused("approval_supersedes_mismatch", ops.check_succession, second, twin)
        self.refused("approval_supersedes_mismatch", judge, second, "status", prior=twin)
        for ref in ({"approval_id": first.approval_id, "sha256": H["db"]},
                    {"approval_id": "inq-0000000000000009", "sha256": first.sha256}):
            _, wrong = self.signed(inquiry_doc(approval_id="inq-0000000000000003", format_version=2, supersedes=ref))
            with self.subTest(ref=ref["approval_id"]):
                self.refused("approval_supersedes_mismatch", ops.check_succession, wrong, first)
        _, unlinked = self.signed(inquiry_doc(approval_id="inq-0000000000000004", format_version=2))
        self.refused("approval_supersedes_mismatch", ops.check_succession, unlinked, first)
        self.refused("approval_supersedes_unknown", ops.check_succession, second, None)

    def test_link_shape_type_and_self_reference(self):
        good = {"approval_id": "inq-0000000000000001", "sha256": H["db"]}
        cases = {"string": "inq-0000000000000001", "list": [good["approval_id"], good["sha256"]],
                 "missing sha": {"approval_id": good["approval_id"]}, "missing id": {"sha256": H["db"]},
                 "extra key": {**good, "kind": "inquiry"}, "upper sha": {**good, "sha256": H["db"].upper()},
                 "short sha": {**good, "sha256": H["db"][:-1]}, "non-hex sha": {**good, "sha256": "g" * 64},
                 "int id": {**good, "approval_id": 5}, "short id": {**good, "approval_id": "x"},
                 "bool sha": {**good, "sha256": True}, "secret id": {**good, "approval_id": SECRET + "!"},
                 "self": {**good, "approval_id": "inq-0000000000000002"}, "empty": {}, "number": 7, "true": True}
        for label, value in cases.items():
            with self.subTest(case=label):
                doc = inquiry_doc(approval_id="inq-0000000000000002", format_version=2, supersedes=value)
                error = self.refused("approval_supersedes_invalid", ops.parse_approval, encode(doc))
                self.assertEqual(error.args, (error.code,))
                self.assertNotIn(SECRET, repr(error) + str(error))

    def test_unsupported_versions(self):
        for value in (0, 4, 99, "2", True, None, -1):        # 3 exists since RESUME_PLAN 9-3
            with self.subTest(value=repr(value)):
                self.refused("approval_format_version", ops.parse_approval, encode(inquiry_doc(format_version=value)))

    def test_chain_rules_and_no_merged_permissions(self):
        _, first = self.signed(inquiry_doc(format_version=2))
        inquiry, apply = self.apply_pair(inquiry_changes={"format_version": 2})
        _, second = self.signed(inquiry_doc(approval_id="inq-0000000000000002", format_version=2,
                                            supersedes=link(first)))
        self.refused("approval_supersedes_kind_mismatch", ops.check_succession, second, apply)
        for changes in (dict(tool="srs_invariant_audit", steps=[_read("audit")]),
                        dict(job={"key": "prb-other", "inputs": JOB["inputs"]})):
            _, other = self.signed(inquiry_doc(approval_id="inq-0000000000000003", format_version=2,
                                               supersedes=link(first), **changes))
            with self.subTest(changes=sorted(changes)):
                self.refused("approval_job_mismatch", ops.check_succession, other, first)
        ops_prior = ops.parse_approval(encode(inquiry_doc(purpose="ops", format_version=2)))
        self.refused("approval_job_mismatch", ops.check_succession, second, ops_prior)
        narrow = self.signed(inquiry_doc(approval_id="inq-0000000000000005", format_version=2, supersedes=link(first),
                                         steps=[_read("status")], accounts=[7], max_accounts=1))[1]
        self.refused("command_not_approved", judge, narrow, "preview", prior=first)       # first had preview
        self.refused("account_not_approved", judge, narrow, "status", account=8, prior=first)

    def test_link_changed_after_signing_is_refused(self):
        _, first = self.signed(inquiry_doc())
        doc = inquiry_doc(approval_id="inq-0000000000000002", format_version=2, supersedes=link(first))
        data = encode(doc)
        signature = self.verifier.sign(data)
        tampered = encode({**doc, "supersedes": {"approval_id": first.approval_id, "sha256": H["db"]}})
        self.refused("approval_signature_invalid", ops.verify_signed, tampered, signature, mode="synthetic",
                     verifier=self.verifier)
        self.assertTrue(ops.verify_signed(data, signature, mode="synthetic", verifier=self.verifier).verified)

    def test_artifact_and_based_on_keep_their_meaning(self):
        inquiry, apply = self.apply_pair(inquiry_changes={"format_version": 2}, apply_changes={"format_version": 2},
                                         plans={"7": plan_for(7, artifact_sha256=ARTIFACT),
                                                "8": plan_for(8, artifact_sha256=ARTIFACT)})
        self.assertEqual(judge(apply, "prepare", inquiry=inquiry, artifact_sha256=ARTIFACT).job_plan,
                         plan_for(7, artifact_sha256=ARTIFACT))
        self.refused("job_plan_mismatch", judge, apply, "prepare", inquiry=inquiry)
        _, other = self.signed(inquiry_doc(approval_id="inq-0000000000000002", format_version=2))
        self.refused("apply_based_on_mismatch", judge, apply, "prepare", inquiry=other, artifact_sha256=ARTIFACT)


class ApplyChainUnit(Base):
    """Contract 4-6-6, the pure chain judgement (fake verifier)."""

    def chain_doc(self, approval_id, inquiry, supersedes=None, version=2, **changes):
        inquiry_bytes, basis = inquiry
        return inquiry_doc(kind="apply", approval_id=approval_id, format_version=version, supersedes=supersedes,
                           steps=[_write("prepare")], accounts=[7], max_accounts=1,
                           based_on={"approval_id": basis.approval_id,
                                     "sha256": hashlib.sha256(inquiry_bytes).hexdigest()},
                           plan={"7": plan_for(7)}, **changes)

    def setUp(self):
        super().setUp()
        self.basis = self.signed(inquiry_doc())
        self.first = self.signed(self.chain_doc("app-0000000000000001", self.basis, version=1))[1]
        self.second = self.signed(self.chain_doc("app-0000000000000002", self.basis, supersedes=link(self.first)))[1]

    def test_empty_single_and_multi(self):
        current = self.signed(self.chain_doc("app-0000000000000009", self.basis, supersedes=link(self.first)))[1]
        self.assertIsNone(ops.check_apply_chain(self.first, ()))
        self.assertIs(ops.check_apply_chain(current, ((self.first, self.basis[1]),)), self.first)
        third = self.signed(self.chain_doc("app-0000000000000003", self.basis, supersedes=link(self.second)))[1]
        chain = ((self.first, self.basis[1]), (self.second, self.basis[1]))
        self.assertIs(ops.check_apply_chain(third, chain), self.second)

    def test_shape_kind_and_verification(self):
        current = self.signed(self.chain_doc("app-0000000000000009", self.basis, supersedes=link(self.first)))[1]
        pair = (self.first, self.basis[1])
        self.refused("approval_chain_invalid", ops.check_apply_chain, current, [pair])
        self.refused("approval_chain_invalid", ops.check_apply_chain, current, (pair[0],))
        self.refused("approval_chain_kind_unsupported", ops.check_apply_chain, self.basis[1], (pair,))
        unverified = ops.parse_approval(encode(self.chain_doc("app-0000000000000001", self.basis, version=1)))
        self.refused("approval_prior_unverified", ops.check_apply_chain, current, ((unverified, self.basis[1]),))
        self.refused("approval_chain_too_long", ops.check_apply_chain, current, (pair,) * (ops.MAX_CHAIN_LINKS + 1))

    def test_job_must_match_and_basis_fields_too(self):
        other_job = {"key": "prb-other", "inputs": JOB["inputs"]}
        other_basis = self.signed(inquiry_doc(approval_id="inq-0000000000000007", job=other_job))
        mixed = self.signed(self.chain_doc("app-0000000000000001", other_basis, version=1))[1]   # JOB vs its basis
        current = self.signed(self.chain_doc("app-0000000000000009", self.basis, supersedes=link(mixed)))[1]
        self.refused("apply_basis_field_mismatch", ops.check_apply_chain, current, ((mixed, other_basis[1]),))
        other = self.signed(self.chain_doc("app-0000000000000001", other_basis, version=1, job=other_job))[1]
        current = self.signed(self.chain_doc("app-0000000000000009", self.basis, supersedes=link(other)))[1]
        self.refused("approval_job_mismatch", ops.check_apply_chain, current, ((other, other_basis[1]),))

if __name__ == "__main__":
    unittest.main()

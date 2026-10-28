"""OPS_MIGRATION_RESUME_LEXEME_PLAN (L-1): CLI `resume` of a plan with SUBSCRIBED cards through the whole existing
provider path (the same harness as test_srs_migrate_resume_provider.py).

REAL: run_resume, _timed_connector, ProductConnector, the adapter, the provider (pre-check per connection,
observation, judgement against the CONTRACT profiles, post-connect authorize_command), approvals and signatures
(test-only temporary OpenSSH keys; real ssh-keygen signing, nothing faked), read_status / judge_status /
progress_values. FAKE: the driver and the connection / cursor server responses (catalog from the contract privilege
table, the two status SELECT answers). STUB: the product `apply_plan` body only (opens each product connection,
records its arguments). Not PostgreSQL evidence; the product's own lexeme writes are in
test_srs_migrate_resume_lexeme_sqlite.py.

Run directly:      python tests/test_srs_migrate_resume_lexeme_provider.py
"""

from __future__ import annotations

import os

os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["PYTHON_DOTENV_DISABLED"] = "1"

import hashlib  # noqa: E402
import json  # noqa: E402
import sys  # noqa: E402
import unittest  # noqa: E402
from datetime import timedelta  # noqa: E402
from pathlib import Path  # noqa: E402
from types import SimpleNamespace  # noqa: E402

TESTS_DIR = Path(__file__).resolve().parent
BACKEND = TESTS_DIR.parent
sys.path.insert(0, str(BACKEND / "scripts"))
sys.path.insert(0, str(TESTS_DIR))
if str(BACKEND) not in sys.path:      # path only, from this file's location
    sys.path.append(str(BACKEND))

import _ops_plan_file as pfile  # noqa: E402
import srs_migrate as cli  # noqa: E402
import test_srs_migrate_apply_flow as flow  # noqa: E402  (module only)
import test_srs_migrate_resume_provider as rp  # noqa: E402  (module only: the provider-path base)

from app.srs import migration  # noqa: E402

ACCOUNT = 7
L1, L2, P1 = 11, 12, 1                                   # subscribed l1, l2 and personal p1 of account 7
LEXEME_COLUMN = ("table", "public", "user_word_progress", "srs_state", "UPDATE")
SUBSCRIPTIONS_READ = ("table", "public", "user_deck_subscriptions", "", "SELECT")


def candidates():
    """Duck-typed plan candidates in the REQUEST order (sorted keys: lexeme 11, lexeme 12, personal 1)."""
    digest = hashlib.sha256(b"[]").hexdigest()
    return [SimpleNamespace(key=SimpleNamespace(kind=kind, user_id=ACCOUNT, ref_id=ref), card_fingerprint=None,
                            logs_fingerprint=digest, card_version=None, quality="unavailable",
                            flags=("card_or_access_missing",), values_json=None, last_log_id=0, reconversion=None,
                            restart_json=None) for kind, ref in (("lexeme", L1), ("lexeme", L2), ("personal", P1))]


class LexemeProviderBase(rp.ProviderBase):
    def setUp(self):
        flow.FlowBase.setUp(self)
        self.req = cli.make_request(ACCOUNT, flow.RUN_KEY, [P1], [L1, L2])
        self.assertEqual(self.req.cards, (("lexeme", L1), ("lexeme", L2), ("personal", P1)))
        os.remove(self.path("plan.json"))                 # this test's own folder: replaced by the mixed plan
        self.plan = self.write_plan(candidates(), ACCOUNT)
        self.inq, self.a0 = self.approvals(
            self.req, self.plan, 2, self.read_profile, self.write_profile,
            apply_changes={"format_version": 3, "backup_evidence": {"sha256": rp.sha(self.read(self.ev))}})
        self.ev2 = self.evidence(ACCOUNT, name="evidence2", evidence_id="bkp-0000000000000002")
        self.planned = pfile.to_candidates(self.plan)
        self.apply_calls: list = []
        self.state = {"now": rp.T0}

    def run_row(self):
        started = (migration.now_utc() - timedelta(hours=1)).isoformat()
        summary = json.dumps({"cursor": 1, "results": [{"kind": "lexeme", "ref_id": L1, "result": "applied"}]})
        return {"id": 41, "mode": "apply", "status": "started", "scope_json": migration._plan_json(self.planned),
                "config_version": self.config_version(), "summary_json": summary, "started_at": started,
                "finished_at": None}

    def snapshots(self):
        return [{"id": 51, "user_id": ACCOUNT, "card_kind": "lexeme", "card_ref": L1}]


class LexemeProvider(LexemeProviderBase):
    def test_mixed_plan_every_connection_observed_and_rejudged(self):
        conns = [self.status_conn()] + [self.write_conn() for _ in range(4)]          # first, l2, p1, finish
        out, code = self.resume_run(conns)
        self.assertEqual((out["status"], out["phase"], code), ("ok", "completed", 0), out)
        self.assertEqual([d["user"] for d in self.driver.calls], ["ops_read"] + ["ops_write_prb"] * 4)
        self.assertEqual(self.trace.observed, conns)
        self.assertEqual([raw for raw, _ in self.trace.prepared], conns)
        call, = self.apply_calls
        self.assertEqual((call["existing_run_only"], call["new_run_only"]), (True, False))
        self.assertEqual(call["expected_progress"], cli.progress_values(self.run_row() | {
            "started_at": call["expected_progress"]["started_at"]}, self.snapshots()))
        self.assert_clean(out)

    def test_l8_lexeme_column_lost_after_the_first_card(self):
        """Product connections: first (commits), card l2 (commits), then the NEXT one (p1) whose observation misses the
        contract column of the lexeme table: refused after observation, rolled back, closed, never handed over."""
        conns = [self.status_conn(), self.write_conn(), self.write_conn(), self.write_conn(missing=[LEXEME_COLUMN])]
        out, code = self.resume_run(conns)
        self.assertEqual((out["status"], out["code"], out["phase"], code),
                         ("failed", "observed_privileges_missing", "after_start", 1), out)
        self.assertEqual((out["uncertain"], out["next"]), (True, "status_required"))
        self.assert_refused_conn(conns[3])
        self.assertEqual(conns[2].business(), ["SELECT 1", "COMMIT"])           # the earlier card's commit kept
        self.assertEqual(len(self.driver.calls), 4)
        self.assertEqual(len(self.apply_calls), 1)

    def test_l9_status_read_without_subscription_privilege(self):
        conn = self.status_conn(missing=[SUBSCRIPTIONS_READ])
        out, code = self.resume_run([conn, self.write_conn()])
        self.assertEqual((out["code"], out["phase"], code), ("observed_privileges_missing", "before_first_write", 4))
        self.assert_refused_conn(conn)
        self.assertEqual((len(self.driver.calls), self.apply_calls), (1, []))


if __name__ == "__main__":
    unittest.main()

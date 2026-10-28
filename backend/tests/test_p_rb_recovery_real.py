"""P-RB recovery tool unit 1 on REAL PostgreSQL (protected local test database: E-1 harness run
marker / OID ownership, E-2 adapter, limited role; opt-in only). The same checks as the SQLite
module; the lock-order cases also prove the waiting backend's blocker is the holder's."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import _e5c_support as s  # noqa: E402
import test_srs_e3_fk_real as pg  # noqa: E402
from test_p_rb_recovery import RecoveryChecks  # noqa: E402


@unittest.skipUnless(pg._opt_in(), "P-RB recovery real PostgreSQL NOT RUN (opt-in not set)")
class PgCase(RecoveryChecks, pg.RealCase):
    db_kind = "postgresql"

    def setUp(self):
        super().setUp()
        env = mock.patch.dict(os.environ, {"JWT_SECRET_KEY": s.SECRET})
        env.start()
        self.addCleanup(env.stop)
        self.create()

    def waiting_probe(self):
        return s.postgres_waiting_probe(self.run)

    def reset_world(self):
        self.run.reset(restart_identity=True)


def _with_waits(name):
    def test(self):
        box = getattr(RecoveryChecks, name)(self)
        self.assertTrue(box.get("waits"), box)          # pg_blocking_pids named the holder
    return test


for _name in ("test_review_first_then_step_a_sees_the_change", "test_step_a_first_then_review_is_refused",
              "test_delete_first_then_step_a_sees_the_change", "test_step_a_first_then_delete_is_refused",
              "test_conversion_first_then_step_a_sees_the_change", "test_step_a_first_then_conversion_is_refused",
              "test_b_first_then_review_is_refused", "test_b_first_then_delete_is_refused",
              "test_b_first_then_public_rollback_is_refused", "test_b_first_then_conversion_is_refused",
              "test_b_first_then_the_same_b_writes_nothing_more", "test_the_same_b_twice_at_once_writes_once",
              "test_release_first_then_ordinary_write_succeeds_after_it",
              "test_ordinary_write_first_is_refused_then_release_completes",
              "test_release_first_then_authorized_rollback_is_refused",
              "test_authorized_rollback_first_then_release_is_refused",
              "test_release_first_then_receipt_purge_runs_after_it",
              "test_receipt_purge_first_is_refused_then_release_completes", "test_the_same_release_twice_at_once"):
    setattr(PgCase, _name, _with_waits(_name))


if __name__ == "__main__":
    unittest.main()

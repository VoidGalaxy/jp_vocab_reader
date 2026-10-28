"""Gate E closing review: the same continuous rehearsal (test_e_final_rehearsal.py) on REAL
PostgreSQL -- the protected local test database only (E-1 harness run marker / OID
ownership, E-2 adapter, limited role; opt-in only, otherwise reported as NOT RUN).

Database-specific steps: the pre-SRS structure is created and upgraded in the harness's
managed schema transaction; ids come from IDENTITY (no SQLite rebuild tool); the old
CASCADE card FK of review_logs removes an old card's log with the card, so the SQLite-only
OLD-INSTALLATION path of F-1 does not apply here and is skipped with that reason. The current
judgement on PostgreSQL (an equivalent orphan in the current schema, no FK disabled) is checked
by the F-1 cases of test_p_rb_recovery_real.py.
"""

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
from test_e_final_rehearsal import FinalRehearsal, sql  # noqa: E402
from test_srs_e2b_upgrade_real import SRS_TABLES, fill, pre_srs_schema  # noqa: E402


@unittest.skipUnless(pg._opt_in(), "Gate E final rehearsal real PostgreSQL NOT RUN (opt-in not set)")
class PgCase(FinalRehearsal, pg.RealCase):
    db_kind = "postgresql"

    def setUp(self):
        super().setUp()
        env = mock.patch.dict(os.environ, {"JWT_SECRET_KEY": s.SECRET})
        env.start()
        self.addCleanup(env.stop)
        self._upgraded = False

    def build_old(self):
        from app.database import get_connection

        self.run.track_creation(self.adapter.schema_step(pre_srs_schema),
                                expected=self.adapter.expected_schema_tables() - SRS_TABLES)
        with get_connection() as c:
            fill(c)

    def delete_old_card(self, ref):
        sql("DELETE FROM vocab_items WHERE id = ?", (ref,))          # the old CASCADE FK takes its log along

    def upgrade(self):
        self.run.track_creation(self.adapter.schema_step(), expected=set() if self._upgraded else SRS_TABLES)
        self._upgraded = True

    def rebuild_ids(self):
        return "postgresql identity (no rebuild tool)"

    def catalog(self):
        return sql("SELECT c.relname, c.relkind, pg_get_userbyid(c.relowner) AS owner FROM pg_class c "
                   "JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = current_schema() "
                   "ORDER BY c.relname") + sql(
            "SELECT conname, pg_get_constraintdef(oid) AS def FROM pg_constraint WHERE connamespace = "
            "(SELECT oid FROM pg_namespace WHERE nspname = current_schema()) ORDER BY conname")

    @unittest.skip("SQLite only: the old CASCADE card FK on PostgreSQL deletes the log with the card")
    def test_orphan_log_of_an_old_delete_is_seen_before_step_a(self):
        pass


if __name__ == "__main__":
    unittest.main()

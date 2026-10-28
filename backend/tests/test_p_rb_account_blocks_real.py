"""P-RB account write block on REAL PostgreSQL (protected local test database: E-1 harness
run marker / OID ownership, E-2 adapter, limited role; opt-in only). The same checks as the
SQLite module; both lock orders also prove the waiting backend's blocker is the holder's
(pg_locks / pg_blocking_pids, read on the harness's own connection)."""

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
from test_p_rb_account_blocks import LOOKALIKE_STATE_CHECK, OLD_STATE_CHECK, PrbChecks, UpgradeChecks  # noqa: E402


@unittest.skipUnless(pg._opt_in(), "P-RB real PostgreSQL NOT RUN (opt-in not set)")
class PgCase(PrbChecks, pg.RealCase):
    db_kind = "postgresql"

    def setUp(self):
        super().setUp()
        env = mock.patch.dict(os.environ, {"JWT_SECRET_KEY": s.SECRET})
        env.start()
        self.addCleanup(env.stop)
        self.create()

    def reset_world(self):
        self.run.reset(restart_identity=True)

    def waiting_probe(self):
        return s.postgres_waiting_probe(self.run)

    def test_write_first_then_block_waits_and_the_write_is_kept(self):
        box = super().test_write_first_then_block_waits_and_the_write_is_kept()
        self.assertTrue(box.get("waits"), box)

    def test_block_first_then_write_waits_and_is_refused(self):
        box = super().test_block_first_then_write_waits_and_is_refused()
        self.assertTrue(box.get("waits"), box)


@unittest.skipUnless(pg._opt_in(), "P-RB real PostgreSQL NOT RUN (opt-in not set)")
class PgUpgrade(UpgradeChecks, pg.RealCase):
    """Review fix 1 upgrade on the real PG schema step (one managed transaction): the state
    check of the earlier definition is put back, then the app's schema code upgrades it."""

    def setUp(self):
        super().setUp()
        env = mock.patch.dict(os.environ, {"JWT_SECRET_KEY": s.SECRET})
        env.start()
        self.addCleanup(env.stop)
        self.create()
        self.ctx = s.Context(owner=False)

    def make_old_table(self):
        self.ddl("ALTER TABLE account_write_blocks DROP CONSTRAINT account_write_blocks_active_state, "
                 f"ADD CONSTRAINT account_write_blocks_check {OLD_STATE_CHECK}")

    def upgrade(self):
        pg.RealCase.upgrade(self)          # the app's schema step, adopting no new table

    def definition(self):
        rows = self.sql("SELECT conname || ' ' || pg_get_constraintdef(oid) AS d FROM pg_constraint "
                        "WHERE conrelid = to_regclass('account_write_blocks') AND contype = 'c' ORDER BY conname")
        return " | ".join(r["d"] for r in rows)

    def catalog(self):
        constraints = self.sql("SELECT conrelid::regclass::text AS t, conname, contype::text AS k, "
                               "pg_get_constraintdef(oid) AS d FROM pg_constraint WHERE conrelid IN "
                               "(to_regclass('account_write_blocks'), to_regclass('prb_ref')) ORDER BY 1, 2")
        indexes = self.sql("SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'account_write_blocks' ORDER BY 1")
        columns = self.sql("SELECT column_name, data_type, is_nullable FROM information_schema.columns "
                           "WHERE table_name = 'account_write_blocks' ORDER BY ordinal_position")
        return constraints, indexes, columns, self.sequence()

    def sequence(self):
        return self.sql("SELECT last_value FROM pg_sequences WHERE sequencename = "
                        "split_part(pg_get_serial_sequence('account_write_blocks', 'id'), '.', 2)")

    def bump_sequence(self):
        self.sql("SELECT setval(pg_get_serial_sequence('account_write_blocks', 'id'), 41)")

    def add_extra(self, kind):
        if kind == "column_value":
            self.ddl("ALTER TABLE account_write_blocks ADD COLUMN note TEXT")
        elif kind in ("index", "current_with_index"):
            self.ddl("CREATE INDEX prb_extra_idx ON account_write_blocks(created_at)")
        elif kind in ("trigger", "view"):
            self.skipTest(f"NOT RUN on PG: a {kind} needs a routine / view, which the E-1 harness refuses")
        elif kind == "check":
            self.ddl("ALTER TABLE account_write_blocks ADD CONSTRAINT prb_extra_check CHECK (length(grant_hash) > 0)")
        elif kind == "foreign_key":
            self.ddl("ALTER TABLE account_write_blocks ADD CONSTRAINT prb_extra_fk FOREIGN KEY (active_user_id) "
                     "REFERENCES users(id)")
        elif kind == "referencing_table":
            self.run.track_creation(lambda raw: raw.execute(
                "CREATE TABLE prb_ref (block_id INTEGER REFERENCES account_write_blocks(id))"), expected={"prb_ref"})
        elif kind == "lookalike_check":
            self.ddl("ALTER TABLE account_write_blocks DROP CONSTRAINT account_write_blocks_check, "
                     f"ADD CONSTRAINT account_write_blocks_check {LOOKALIKE_STATE_CHECK}")

    def after_rows(self, kind):
        if kind == "column_value":
            self.sql("UPDATE account_write_blocks SET note = 'keep-me'")


if __name__ == "__main__":
    unittest.main()

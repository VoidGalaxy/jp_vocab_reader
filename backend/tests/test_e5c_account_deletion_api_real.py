"""Gate E-5c on REAL PostgreSQL (protected local test database: E-1 harness run marker / OID
ownership, E-2 adapter, limited role; opt-in only). The same checks as the SQLite module:
every write route, both orders, the REAL deletion (E-5b preview -> apply); order 2 also proves
that the deletion's backend waited on a backend of the paused write (pg_locks /
pg_blocking_pids, read on the harness's own connection). Representative routes over a real
HTTP server (uvicorn on a loopback socket in this process)."""

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
from test_e5c_account_deletion_api import ALL_CASES, E5cChecks, HttpServerMixin  # noqa: E402


@unittest.skipUnless(pg._opt_in(), "E-5c real PostgreSQL NOT RUN (opt-in not set)")
class PgCase(E5cChecks, pg.RealCase):
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

    def order2(self, name):
        box = super().order2(name)
        self.assertTrue(box.get("waits"), box)          # the exact blocking backend was seen
        return box


class Order1OnPostgres(PgCase):
    pass


class Order2OnPostgres(PgCase):
    pass


def _test(order, name):
    def test(self):
        getattr(self, order)(name)
    return test


for _name in ALL_CASES:
    setattr(Order1OnPostgres, f"test_{_name}", _test("order1", _name))
    setattr(Order2OnPostgres, f"test_{_name}", _test("order2", _name))


class RealHttpOnPostgres(HttpServerMixin, PgCase):
    pass


if __name__ == "__main__":
    unittest.main()

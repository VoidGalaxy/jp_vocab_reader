"""Gate E-5c on synthetic SQLite: the REAL account deletion (E-5b preview -> apply) against
delayed API writes, both orders, every write route (see _e5c_support). ASGI in-process
requests (httpx ASGITransport) for every route, plus a real HTTP server (uvicorn on a loopback
socket, in this process) for representative routes. Session-only database; no vocab.db."""

from __future__ import annotations

import ast
import os
import socket
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import _e5c_support as s  # noqa: E402
from app.database import init_db  # noqa: E402


class E5cChecks:
    """Order 1 / order 2 checks, shared by the SQLite and the real-PostgreSQL modules."""

    db_kind = "sqlite"

    def reset_world(self):
        pass

    def waiting_probe(self):
        return s.sqlite_waiting_probe()

    def case(self, name):
        cases = {case: builder for case, builder in s.route_cases().values()}
        cases.update(s.EXTRA_CASES)
        return cases[name]

    def order1(self, name, base_url=None, tag="e5c"):
        self.reset_world()
        ctx = s.Context.for_case(name, tag=tag)
        token, others = ctx.token(), ctx.others()
        outcome = {}
        method, path, body = self.case(name)(ctx)
        with s.delete_after_authentication(ctx.a.T, outcome):
            response = s.request(method, path, body, token, base_url)
        self.assertEqual(outcome["authenticated"], [ctx.a.T])
        s.record({"db": self.db_kind, "order": 1, "case": name, "http": "real" if base_url else "asgi",
                  "deletion": outcome["deletion"].get("status"), "status": response.status_code,
                  "detail": response.json().get("detail") if response.status_code >= 400 else None})
        if name in s.OWNER_CASES:
            # owner review: deletion held, so the request is an ordinary request of a live account
            self.assertEqual(outcome["deletion"], {"status": "held", "reasons": ["shared_deck_owner_review"]})
            self.assertLess(response.status_code, 300, response.text[:200])
            self.assertEqual(len(ctx.a.rows_of(ctx.a.T)["users"]), 1)
            return ctx, response
        self.assertEqual(outcome["deletion"]["status"], "deleted")
        self.assertEqual(response.status_code, 404, response.text[:200])
        self.assertIn(response.json()["detail"], s.ORDER1_DETAILS)
        self.assertEqual(ctx.target_rows(), {})                 # nothing of the account came back
        self.assertEqual(ctx.others(), others)                  # other accounts, shared, global unchanged
        late = s.request(method, path, body, token, base_url)   # the stale token afterwards
        self.assertEqual((late.status_code, late.json()["detail"]), (401, "invalid token"))
        self.assertEqual(ctx.target_rows(), {})
        return ctx, response

    def order2(self, name):
        self.reset_world()
        ctx = s.Context.for_case(name)
        token = ctx.token()
        plan = s.preview(ctx.a.T)
        if name in s.OWNER_CASES:
            self.assertEqual(plan["reasons"], ["shared_deck_owner_review"])
        others = ctx.others()
        method, path, body = self.case(name)(ctx)
        facts, expect = s.EFFECTS[name]
        before = facts(ctx)
        expected_effect = expect(ctx, before)
        self.assertNotEqual(before, expected_effect)              # the write has something to keep

        def observe():
            # the write committed; the deletion holds the lock and has not removed anything
            return {"account": len(ctx.a.rows_of(ctx.a.T)["users"]), **facts(ctx)}

        patch, probe = self.waiting_probe()[:2]
        with patch:
            box = s.WriteFirst(ctx.a.T, plan["plan"], waiting_probe=probe, observe=observe).run(
                lambda: s.request(method, path, body, token))
        s.record({"db": self.db_kind, "order": 2, "case": name, "write_status": box.get("write", (None, None))[1].status_code
                  if box.get("write", ("", None))[0] == "ok" else box.get("write"), "deletion": box.get("delete", (None, {}))[1].get("status")
                  if box.get("delete", ("",))[0] == "ok" else box.get("delete"),
                  "waited": box.get("delete_waited_for_write"), "waits": box.get("waits"),
                  "observed": box.get("observed", (None, None))[1] if box.get("observed", ("",))[0] == "ok"
                  else box.get("observed")})
        self.assertTrue(box.get("write_paused"), box)
        self.assertTrue(box.get("joined"), box)
        self.assertTrue(box.get("delete_waited_for_write"), box)
        self.assertFalse(box.get("delete_done_while_write_held"), box)
        self.assertEqual(box["write"][0], "ok", box["write"])
        self.assertLess(box["write"][1].status_code, 300, box["write"][1].text[:200])
        # the write's effect, read from the DB after its commit and before the deletion acted
        self.assertEqual(box.get("observed"), ("ok", {"account": 1, **expected_effect}), (before, box.get("observed")))
        self.assertEqual(box["delete"][0], "ok", box["delete"])
        expected = s.ORDER2_DELETION[name]
        report = box["delete"][1]
        if expected.startswith("blocked:"):
            self.assertEqual((report["status"], report["reasons"]), ("blocked", [expected.split(":", 1)[1]]))
            self.assertEqual(len(ctx.a.rows_of(ctx.a.T)["users"]), 1)       # held, not deleted
        else:
            self.assertEqual(report["status"], expected)
            if expected == "plan_changed":
                self.assertEqual(len(ctx.a.rows_of(ctx.a.T)["users"]), 1)   # the write is kept...
                # ...including its own effect on shared rows (e.g. a subscription's import counter);
                # the deletion itself must not change anything of anyone else
                others = ctx.others()
                self.assertEqual(s.delete_for_real(ctx.a.T)["status"], "deleted")   # a fresh plan deletes it
            self.assertEqual(ctx.target_rows(), {})
            after = ctx.others()
            if name == "publish":
                after.pop("lexemes"), others.pop("lexemes")
            self.assertEqual(after, others)
        return box


class Case(E5cChecks, unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="jp_vocab_e5c_", dir=BACKEND)
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "synthetic.db"
        env = mock.patch.dict(os.environ, {"APP_ENV": "test", "DATABASE_URL": f"sqlite:///{self.path.as_posix()}",
                                           "JWT_SECRET_KEY": s.SECRET})
        env.start()
        self.addCleanup(env.stop)
        init_db()


def _test(order, name):
    def test(self):
        getattr(self, order)(name)
    return test


ALL_CASES = [case for case, _ in s.route_cases().values()] + list(s.EXTRA_CASES)


class Inventory(unittest.TestCase):
    def test_every_write_route_is_covered_or_excluded_with_a_reason(self):
        routes = s.write_route_inventory()
        self.assertEqual(routes, set(s.route_cases()) | set(s.EXCLUDED_ROUTES))
        # the same classification as E-5a's own list (read from its test source)
        tree = ast.parse((Path(__file__).resolve().parent / "test_srs_e5_account_write.py").read_text(encoding="utf-8"))
        scoped = next(ast.literal_eval(node.value) for node in ast.walk(tree)
                      if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", None) == "scoped")
        self.assertEqual(set(s.route_cases()), scoped)
        self.assertEqual(set(s.ORDER2_DELETION), set(ALL_CASES))
        self.assertEqual(set(s.EFFECTS), set(ALL_CASES))


class Order1AuthenticatedThenDeleted(Case):
    pass


class Order2WriteHoldsTheLock(Case):
    pass


for _name in ALL_CASES:
    setattr(Order1AuthenticatedThenDeleted, f"test_{_name}", _test("order1", _name))
    setattr(Order2WriteHoldsTheLock, f"test_{_name}", _test("order2", _name))


class HttpServerMixin:
    """uvicorn on a loopback socket in this process (so the test-only pause applies)."""

    def start_server(self):
        import uvicorn
        from app import main

        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        config = uvicorn.Config(main.app, host="127.0.0.1", port=port, log_level="error", lifespan="off")
        self.server = uvicorn.Server(config)
        thread = threading.Thread(target=self.server.run, name="uvicorn", daemon=True)
        thread.start()
        deadline = time.monotonic() + s.WAIT
        while not self.server.started and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertTrue(self.server.started)
        self.base_url = f"http://127.0.0.1:{port}"

        def stop():
            self.server.should_exit = True
            thread.join(s.WAIT)
            self.assertFalse(thread.is_alive())
        self.addCleanup(stop)

    def test_representative_routes_over_real_http(self):
        self.start_server()
        for name in ("vocab_create", "personal_review", "app_feedback", "lexeme_review"):
            with self.subTest(name):
                self.order1(name, self.base_url, tag=f"http-{name}")


class RealHttpServer(HttpServerMixin, Case):
    pass


if __name__ == "__main__":
    unittest.main()

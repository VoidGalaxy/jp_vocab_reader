"""Real loopback HTTP smoke test; owns one child server and synthetic DB."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import unittest
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_srs_transactions import SrsSqliteCase
from app.auth import create_access_token
from app.database import get_connection


class HttpServerTests(SrsSqliteCase):
    def test_personal_and_subscribed_retry_over_real_http(self):
        versions = {key.kind: self.enable(key, "network-" + key.kind) for key in (self.personal, self.subscribed)}
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]
        root = Path(__file__).resolve().parents[1]
        log = (Path(self.directory.name) / "owned-server.log").open("w", encoding="utf-8")
        # The synthetic schema is initialized above. Disable lifespan to avoid
        # startup's unrelated dictionary downloads/file writes, not auth/routes.
        process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port), "--lifespan", "off"],
            cwd=root, env=dict(os.environ), stdout=log, stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        try:
            base = f"http://127.0.0.1:{port}"
            ready = False
            for _ in range(80):
                if process.poll() is not None:
                    self.fail("owned test server exited before readiness")
                try:
                    with urlopen(base + "/health", timeout=1) as response:
                        self.assertEqual(json.load(response)["database"], "sqlite")
                        ready = True
                        break
                except (URLError, TimeoutError):
                    time.sleep(0.1)
            self.assertTrue(ready, "owned test server did not become ready")
            token = create_access_token({"id": self.user, "email": "srs-b2@example.test"})

            def post(path, body):
                request = Request(base + path, data=json.dumps(body).encode(), method="POST",
                                  headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
                try:
                    with urlopen(request, timeout=5) as response:
                        return response.status, json.load(response)
                except HTTPError as error:
                    with error:
                        return error.code, json.load(error)

            for key in (self.personal, self.subscribed):
                path = (f"/study-items/{key.ref_id}/review" if key.kind == "personal"
                        else f"/shared-decks/{self.shared}/words/{key.ref_id}/review")
                body = dict(rating="again", request_id="network-" + key.kind,
                            expected_card_version=versions[key.kind], session_id="network-session")
                first = post(path, body)
                self.assertEqual(first[0], 200)
                self.assertEqual(post(path, body), first)
                self.assertEqual(post(path, body | {"rating": "easy"})[0], 409)
                self.assertEqual(self.counts(key), (1, 1))
                self.assertEqual(self.card(key)["srs_card_version"], versions[key.kind] + 1)
            with get_connection() as connection:
                connection.execute("UPDATE user_deck_subscriptions SET is_active = FALSE WHERE user_id = ?", (self.user,))
            self.assertEqual(post(f"/shared-decks/{self.shared}/words/{self.lexeme}/review", body)[0], 404)
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            log.close()
        self.assertIsNotNone(process.returncode)


if __name__ == "__main__":
    unittest.main()

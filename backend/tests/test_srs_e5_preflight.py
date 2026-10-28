"""E-5 read-only preparation. Synthetic SQLite only; no account deletion."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import _srs_e5_preflight as preflight
from app.database import get_connection, init_db
from app.repositories.user_repository import create_user

STAMP = "2026-10-19T00:00:00+00:00"


class PreflightTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="jp_vocab_e5_", dir=Path(__file__).resolve().parents[1])
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "synthetic.db"
        env = mock.patch.dict(os.environ, {"APP_ENV": "test", "DATABASE_URL": f"sqlite:///{self.path.as_posix()}"})
        env.start()
        self.addCleanup(env.stop)
        init_db()
        self.user = create_user("e5-content-not-exported-a@example.test", "a", "synthetic")["id"]
        self.other = create_user("e5-content-not-exported-b@example.test", "b", "synthetic")["id"]
        for user, content in ((self.user, "private-content-not-exported"),
                              (self.other, "other-content-not-exported")):
            card = self.sql(
                "INSERT INTO vocab_items (user_id, surface, base_form, reading, part_of_speech, normalized_form, "
                "status, created_at, updated_at) VALUES (?, ?, ?, '', '', '', 'unknown', ?, ?) RETURNING id",
                (user, content, content, STAMP, STAMP),
            )[0]["id"]
            if user == self.user:
                self.card = card

    def sql(self, query, params=()):
        with get_connection() as connection:
            cursor = connection.execute(query, params)
            return [dict(row) for row in cursor.fetchall()] if cursor.description else []

    def inventory(self, user=None):
        with get_connection(read_only=True) as connection:
            return preflight.account_inventory(connection, self.user if user is None else user)

    def run_record(self, user=None, scope=None, status="completed"):
        scope = json.dumps({"user_id": self.user if user is None else user}) if scope is None else scope
        return self.sql(
            "INSERT INTO srs_migration_runs (run_key, mode, status, scope_json, engine, library_version, "
            "config_version, started_at) VALUES (?, 'apply', ?, ?, 'fsrs', '6.3.2', 'c', ?) RETURNING id",
            (f"e5-{len(self.sql('SELECT id FROM srs_migration_runs'))}", status, scope, STAMP),
        )[0]["id"]

    def snapshot(self, run_id, user):
        self.sql(
            "INSERT INTO srs_migration_snapshots (run_id, user_id, card_kind, card_ref, card_version_before, "
            "legacy_json, created_at) VALUES (?, ?, 'personal', ?, 0, '{}', ?)",
            (run_id, user, self.card, STAMP),
        )

    def test_counts_are_account_scoped_without_content_or_eligibility(self):
        self.run_record()
        self.run_record(user=self.other)
        result = self.inventory()
        self.assertEqual(result["status"], "inventory_complete")
        self.assertFalse(result["deletion_enabled"])
        self.assertEqual(result["counts"]["vocab_items"], 1)
        self.assertEqual(result["counts"]["srs_migration_runs"], 1)
        self.assertEqual(result["counts"]["users"], 1)
        output = json.dumps(result)
        for content in ("private-content", "other-content", "e5-content", "@", "scope_json"):
            self.assertNotIn(content, output)

    def test_full_current_schema_has_an_explicit_table_classification(self):
        with get_connection(read_only=True) as connection:
            self.assertEqual(preflight._tables(connection), preflight.EXPECTED_TABLES)
        self.assertEqual(len(preflight.EXPECTED_TABLES), 26)  # + P-RB account_write_blocks

    def test_read_only_snapshot_and_file_bytes_are_unchanged(self):
        self.run_record()
        before = self.path.read_bytes()
        with get_connection(read_only=True) as connection:
            statements = []
            connection.set_trace_callback(statements.append)
            before_changes = connection.total_changes
            result = preflight.account_inventory(connection, self.user)
            self.assertEqual(connection.total_changes, before_changes)
            self.assertFalse(connection.in_transaction)
        self.assertEqual(result["status"], "inventory_complete")
        self.assertEqual(self.path.read_bytes(), before)
        self.assertFalse(any(s.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE", "CREATE", "DROP"))
                             for s in statements))
        self.assertIn("PRAGMA query_only = ON", statements)

    def test_invalid_account_ids_are_rejected_before_any_query(self):
        connection = mock.Mock()
        for user in (True, False, 0, -1, "1", 1.0, None, {}, [], 2 ** 63, 10 ** 400):
            with self.subTest(user_type=type(user).__name__), self.assertRaisesRegex(ValueError, "invalid_account_id"):
                preflight.account_inventory(connection, user)
        connection.execute.assert_not_called()

    def test_missing_account_is_not_a_complete_inventory(self):
        result = self.inventory(999999)
        self.assertEqual(result["status"], "incomplete")
        self.assertIn("account_not_found", result["reasons"])

    def test_unknown_table_is_not_silently_excluded(self):
        self.sql("CREATE TABLE future_account_data (user_id INTEGER)")
        result = self.inventory()
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(result["unexpected_tables"], 1)
        self.assertNotIn("counts", result)

    def test_missing_table_is_not_treated_as_zero(self):
        self.sql("DROP TABLE app_feedback")
        result = self.inventory()
        self.assertEqual(result["missing_tables"], 1)
        self.assertEqual(result["status"], "incomplete")

    def test_bad_scope_in_any_account_blocks_ownership_confirmation(self):
        run_id = self.run_record()
        for scope in ("garbage", "[]", "{}", '{"user_id":true}', '{"user_id":"1"}',
                      '{"user_id":0}', '{"user_id":1,"user_id":2}',
                      "[" * 1100 + "]" * 1100):
            with self.subTest(length=len(scope)):
                self.sql("UPDATE srs_migration_runs SET scope_json = ? WHERE id = ?", (scope, run_id))
                result = self.inventory()
                self.assertEqual(result["status"], "incomplete")
                self.assertEqual(result["observations"]["unreadable_run_scopes"], 1)
                self.assertIn("run_ownership_unverifiable", result["reasons"])

    def test_cross_owner_snapshots_are_detected_in_both_directions(self):
        own_run = self.run_record()
        other_run = self.run_record(user=self.other)
        self.snapshot(own_run, self.other)
        self.snapshot(other_run, self.user)
        result = self.inventory()
        self.assertEqual(result["observations"]["cross_owner_snapshots"], 2)
        self.assertIn("snapshot_owner_mismatch", result["reasons"])

    def test_unreadable_parent_is_not_adopted_by_snapshot_owner(self):
        run_id = self.run_record(scope="garbage")
        self.snapshot(run_id, self.user)
        result = self.inventory()
        self.assertEqual(result["observations"]["unverifiable_snapshot_parents"], 1)
        self.assertEqual(result["counts"]["srs_migration_runs"], 0)

    def test_started_runs_are_observations_not_permission(self):
        self.run_record(status="started")
        self.run_record(user=self.other, status="started")
        result = self.inventory()
        self.assertEqual(result["observations"]["started_runs"], 1)
        self.assertFalse(result["deletion_enabled"])

    def test_shared_deck_visibility_does_not_hide_ownership(self):
        for visibility in ("public", "unpublished"):
            self.sql(
                "INSERT INTO shared_decks (owner_user_id, title, description, visibility, created_at, updated_at) "
                "VALUES (?, 'private title', '', ?, ?, ?)",
                (self.user, visibility, STAMP, STAMP),
            )
        result = self.inventory()
        self.assertEqual(result["observations"]["owned_shared_decks"], 2)
        self.assertFalse(result["deletion_enabled"])

    def test_exception_rolls_back_and_restores_connection_read_only_setting(self):
        with get_connection(read_only=True) as connection:
            original = connection.execute("PRAGMA query_only").fetchone()[0]
            with mock.patch.object(preflight, "_tables", side_effect=RuntimeError("synthetic")):
                with self.assertRaises(RuntimeError):
                    preflight.account_inventory(connection, self.user)
            self.assertFalse(connection.in_transaction)
            self.assertEqual(connection.execute("PRAGMA query_only").fetchone()[0], original)


if __name__ == "__main__":
    unittest.main()

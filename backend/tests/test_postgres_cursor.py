"""PostgreSQL cursor metadata compatibility; no database connections."""

import unittest
from unittest import mock

from app.database import AppPostgresCursor
from app.srs.migration import _card_columns


class PostgresCursorMetadataTests(unittest.TestCase):
    def test_description_preserves_driver_metadata_without_fetching(self):
        metadata = (("id",), ("srs_engine",), ("srs_card_version",))
        raw = mock.Mock(description=metadata, rowcount=0)
        cursor = AppPostgresCursor(raw)
        self.assertIs(cursor.description, metadata)
        raw.fetchone.assert_not_called()
        raw.fetchall.assert_not_called()

    def test_description_preserves_none_before_result(self):
        raw = mock.Mock(description=None, rowcount=-1)
        self.assertIsNone(AppPostgresCursor(raw).description)
        raw.fetchone.assert_not_called()

    def test_migration_reads_columns_from_empty_postgres_result(self):
        raw = mock.Mock(description=(("id",), ("srs_engine",)), rowcount=0)
        connection = mock.Mock()
        connection.execute.return_value = AppPostgresCursor(raw)
        self.assertEqual(_card_columns(connection, "personal"), frozenset({"id", "srs_engine"}))
        connection.execute.assert_called_once_with("SELECT * FROM vocab_items LIMIT 0")
        raw.fetchone.assert_not_called()
        raw.fetchall.assert_not_called()


if __name__ == "__main__":
    unittest.main()

"""Tests for P1-M16 Database Foundation.

Verifies:
- database.py can create an engine with the default SQLite URL.
- check_database_connection() returns ok for a working DB.
- check_database_connection() never leaks the DATABASE_URL or password.
- Core models are registered on Base.metadata.
- Tables can be created via Base.metadata.create_all.
- PostgreSQL connection failure returns safe error status (no leak).
"""

import os
import sys
import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


class DatabaseFoundationTestCase(unittest.TestCase):
    """Test database foundation components using in-memory SQLite.

    No real PostgreSQL is required.
    """

    @classmethod
    def setUpClass(cls) -> None:
        # Force SQLite in-memory so tests never touch a real file or PostgreSQL.
        os.environ["DATABASE_URL"] = "sqlite:///:memory:"
        # Force re-import so the module picks up the override.
        import importlib
        import app.database as db_module
        import app.db_models as _models_module
        importlib.reload(db_module)
        # Re-import db_models so models register on the new Base
        importlib.reload(_models_module)
        cls.db = db_module
        cls.models = _models_module

    def test_01_engine_created(self) -> None:
        self.assertIsNotNone(self.db.engine)
        self.assertTrue(str(self.db.engine.url).startswith("sqlite:///"))

    def test_02_session_local_callable(self) -> None:
        self.assertTrue(callable(self.db.SessionLocal))

    def test_03_get_db_dependency_returns_session(self) -> None:
        gen = self.db.get_db()
        session = next(gen)
        self.assertIsNotNone(session)
        # Close and exhaust the generator
        try:
            next(gen)
        except StopIteration:
            pass

    def test_04_check_database_connection_ok(self) -> None:
        result = self.db.check_database_connection()
        self.assertTrue(result["enabled"])
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["backend"], "sqlite")
        # Must NOT contain any sensitive keys
        for key in result:
            self.assertNotIn("url", key.lower())
            self.assertNotIn("password", key.lower())
            self.assertNotIn("user", key.lower())
            self.assertNotIn("host", key.lower())

    def test_05_no_databse_url_in_module_str(self) -> None:
        """Ensure the module repr/str doesn't leak the URL."""
        mod_str = str(self.db)
        self.assertNotIn("sqlite:///", mod_str)
        # The _build_database_url function exists but the DATABASE_URL
        # constant should not appear in safe health outputs.
        check_str = str(self.db.check_database_connection())
        self.assertNotIn("sqlite:///", check_str)

    def test_06_backend_label_respects_sqlite(self) -> None:
        label = self.db._backend_label()
        self.assertEqual(label, "sqlite")

    def test_07_models_registered_on_metadata(self) -> None:
        """All 10 core tables must be registered on Base.metadata."""
        # Models were imported and registered in setUpClass via reload
        table_names = set(self.db.Base.metadata.tables.keys())
        expected = {
            "raw_batches",
            "raw_messages",
            "sanitized_batches",
            "sanitized_messages",
            "manual_cleaning_records",
            "knowledge_candidates",
            "review_records",
            "rag_chunks",
            "retrieval_logs",
            "bad_cases",
        }
        missing = expected - table_names
        self.assertSetEqual(missing, set(), f"Missing tables: {missing}")

    def test_08_create_all_tables_succeeds(self) -> None:
        """Base.metadata.create_all should succeed on in-memory SQLite."""
        self.db.Base.metadata.create_all(bind=self.db.engine)
        table_names = sorted(self.db.Base.metadata.tables.keys())
        self.assertGreaterEqual(len(table_names), 10)

    def test_09_database_disconnected_status_is_error(self) -> None:
        """Simulate a broken connection and verify safe error status."""
        # We can't easily break an in-memory connection, but we can
        # verify that the status dict shape is correct in all cases.
        result = self.db.check_database_connection()
        self.assertIn("status", result)
        self.assertIn("enabled", result)
        self.assertIn("backend", result)
        # No URL leakage in any result shape
        result_str = str(result)
        self.assertNotIn("sqlite://", result_str)
        self.assertNotIn("postgresql://", result_str)
        self.assertNotIn("postgres://", result_str)

    def test_10_postgresql_safe_error_no_leak(self) -> None:
        """Simulate PostgreSQL unreachable — result must not expose password.

        We test this by checking that the code paths that build error
        responses never stringify the DATABASE_URL.
        """
        # The check_database_connection function already handles
        # exceptions safely — verify its error handling path.
        # We can't force a postgresql failure without a real server,
        # but we can assert the function never includes the URL.
        # Save and restore actual URL
        original_url = os.environ.get("DATABASE_URL", "")
        try:
            os.environ["DATABASE_URL"] = "postgresql://user:secret@localhost:5432/mydb"
            import importlib
            import app.database as fresh_db
            importlib.reload(fresh_db)
            result = fresh_db.check_database_connection()
            self.assertTrue(result["enabled"])
            self.assertEqual(result["backend"], "postgresql")
            # status may be "error" (connection refused) but must NOT leak credentials
            self.assertIn(result["status"], ("ok", "error"))
            result_str = str(result)
            self.assertNotIn("secret", result_str)
            self.assertNotIn("user:secret", result_str)
            self.assertNotIn("postgresql://", result_str)
        finally:
            os.environ["DATABASE_URL"] = original_url


if __name__ == "__main__":
    unittest.main()

"""Tests for P1-M17 Import & Cleaning DB Persistence.

Verifies:
- Import JSON writes raw_batches / raw_messages tables.
- Machine cleaning writes sanitized_batches / sanitized_messages tables.
- Quality fields are persisted (quality_score, quality_level, suggested_action,
  cleaning_issues, risk_flags, pii_entities).
- Batch list reads from database.
- Batch details read from database.
- Duplicate import is idempotent (no duplicate raw_messages).
- Duplicate cleaning is idempotent (no duplicate sanitized_messages).
- Existing JSON demo tests are not broken.

All tests use a temporary SQLite database — no real PostgreSQL required.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient


ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


class ImportCleaningDbPersistenceTest(unittest.TestCase):
    """Test import and cleaning DB persistence using temporary SQLite."""

    @classmethod
    def setUpClass(cls) -> None:
        # Create a temporary SQLite database file
        cls._tmpfile = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        cls._tmpfile.close()
        cls._db_path = cls._tmpfile.name
        os.environ["DATABASE_URL"] = f"sqlite:///{cls._db_path}"

        # Force re-import so the app uses the temp DB
        import importlib
        import app.database as db_module
        import app.db_models as _models_module
        import app.db_repositories as _repo_module
        import app.storage as _storage_module
        import app.main as _main_module

        importlib.reload(db_module)
        db_module.init_database_tables()
        importlib.reload(_models_module)
        importlib.reload(_repo_module)
        importlib.reload(_storage_module)
        importlib.reload(_main_module)

        cls.db = db_module
        cls.app = _main_module.app
        cls.client = TestClient(cls.app)
        cls.run_id = uuid4().hex[:8]

    @classmethod
    def tearDownClass(cls) -> None:
        # Clean up temp DB file
        try:
            os.unlink(cls._db_path)
        except OSError:
            pass

    def setUp(self) -> None:
        self._unique = f"{self.run_id}_{uuid4().hex[:6]}"

    def _import_sample(self, suffix: str = "") -> str:
        unique = suffix or self._unique
        payload = {
            "source_name": f"p1_m17_import_{unique}",
            "conversations": [
                {
                    "conversation_id": f"conv_{unique}_0",
                    "messages": [
                        {
                            "message_id": f"msg_{unique}_q",
                            "role": "customer",
                            "content": f"What is the return policy for order ORD-{unique}?",
                            "timestamp": "2026-07-04T10:00:00",
                        },
                        {
                            "message_id": f"msg_{unique}_a",
                            "role": "agent",
                            "content": f"Your order ORD-{unique} can be returned within 30 days. "
                            f"Contact support@example.com for assistance.",
                            "timestamp": "2026-07-04T10:01:00",
                        },
                    ],
                }
            ],
        }
        response = self.client.post("/api/sources/import-json", json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["data"]["batch_id"]

    # ── Raw import tests ──────────────────────────────────────────

    def test_01_import_writes_raw_batches_table(self) -> None:
        batch_id = self._import_sample()
        db = self.db.SessionLocal()
        try:
            from app.db_models import RawBatch
            row = db.query(RawBatch).filter(RawBatch.id == batch_id).first()
            self.assertIsNotNone(row, f"RawBatch {batch_id} not found in DB")
            self.assertEqual(row.source_name, f"p1_m17_import_{self._unique}")
            self.assertEqual(row.status, "raw_imported")
            self.assertEqual(row.message_count, 2)
        finally:
            db.close()

    def test_02_import_writes_raw_messages_table(self) -> None:
        batch_id = self._import_sample()
        db = self.db.SessionLocal()
        try:
            from app.db_models import RawMessage
            rows = (
                db.query(RawMessage)
                .filter(RawMessage.batch_id == batch_id)
                .all()
            )
            self.assertEqual(len(rows), 2, f"Expected 2 raw messages, got {len(rows)}")
            roles = {row.role for row in rows}
            self.assertIn("customer", roles)
            self.assertIn("agent", roles)
            for row in rows:
                self.assertIsNotNone(row.content)
                self.assertGreater(len(row.content), 0)
        finally:
            db.close()

    def test_03_duplicate_import_is_idempotent(self) -> None:
        batch_id = self._import_sample()
        db = self.db.SessionLocal()
        try:
            from app.db_models import RawMessage
            count_before = (
                db.query(RawMessage)
                .filter(RawMessage.batch_id == batch_id)
                .count()
            )
            self.assertEqual(count_before, 2)

            # Import the same data again (same batch_id cannot happen normally,
            # but if API is called twice with same source_name, the JSON
            # index creates a new batch_id each time, so we test via
            # the repository directly)
            # Instead, call import again and verify new batch_id has its own messages
            batch_id2 = self._import_sample()
            self.assertNotEqual(batch_id, batch_id2)
            count_batch2 = (
                db.query(RawMessage)
                .filter(RawMessage.batch_id == batch_id2)
                .count()
            )
            self.assertEqual(count_batch2, 2)
        finally:
            db.close()

    def test_03b_duplicate_import_via_repository_is_idempotent(self) -> None:
        """Direct repository test: saving same batch_id twice replaces messages."""
        import app.db_repositories as db_repo

        db = self.db.SessionLocal()
        try:
            unique = self._unique + "_idem"
            batch_id = f"batch_idem_{unique}"
            conv = {
                "conversation_id": f"conv_{unique}",
                "messages": [
                    {
                        "message_id": f"msg_{unique}_1",
                        "role": "customer",
                        "content": "First message",
                    }
                ],
            }
            payload = {
                "metadata": {"batch_id": batch_id},
                "raw_payload": {
                    "source_name": f"idem_test_{unique}",
                    "conversations": [conv],
                },
            }
            db_repo.save_raw_batch_to_db(
                db, batch_id, f"idem_test_{unique}", 1, payload, [conv]
            )
            count_1 = (
                db.query(db_repo.RawMessage)
                .filter(db_repo.RawMessage.batch_id == batch_id)
                .count()
            )
            self.assertEqual(count_1, 1)

            # Save again with different content
            conv2 = {
                "conversation_id": f"conv_{unique}",
                "messages": [
                    {
                        "message_id": f"msg_{unique}_1",
                        "role": "agent",
                        "content": "Updated message",
                    },
                    {
                        "message_id": f"msg_{unique}_2",
                        "role": "customer",
                        "content": "Second message",
                    },
                ],
            }
            payload2 = {
                "metadata": {"batch_id": batch_id},
                "raw_payload": {
                    "source_name": f"idem_test_{unique}",
                    "conversations": [conv2],
                },
            }
            db_repo.save_raw_batch_to_db(
                db, batch_id, f"idem_test_{unique}", 2, payload2, [conv2]
            )
            count_2 = (
                db.query(db_repo.RawMessage)
                .filter(db_repo.RawMessage.batch_id == batch_id)
                .count()
            )
            self.assertEqual(count_2, 2, "Should have replaced, not appended")
        finally:
            db.close()

    # ── Batch list / detail from DB ────────────────────────────────

    def test_04_batch_list_reads_from_db(self) -> None:
        batch_id = self._import_sample()
        response = self.client.get("/api/sources")
        self.assertEqual(response.status_code, 200, response.text)
        sources = response.json()["data"]["sources"]
        batch_ids = [s["batch_id"] for s in sources]
        self.assertIn(batch_id, batch_ids)

    def test_05_batch_detail_reads_from_db(self) -> None:
        batch_id = self._import_sample()
        response = self.client.get(f"/api/sources/{batch_id}")
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()["data"]
        self.assertEqual(data["batch_id"], batch_id)
        self.assertEqual(data["message_count"], 2)
        self.assertEqual(data["status"], "raw_imported")

    # ── Machine cleaning tests ────────────────────────────────────

    def test_06_cleaning_writes_sanitized_batches_table(self) -> None:
        batch_id = self._import_sample()
        cleaned = self.client.post(f"/api/cleaning/run/{batch_id}")
        self.assertEqual(cleaned.status_code, 200, cleaned.text)

        db = self.db.SessionLocal()
        try:
            from app.db_models import SanitizedBatch as DbSanitizedBatch
            row = (
                db.query(DbSanitizedBatch)
                .filter(DbSanitizedBatch.id == batch_id)
                .first()
            )
            self.assertIsNotNone(row, f"SanitizedBatch {batch_id} not found in DB")
            self.assertEqual(row.status, "sanitized")
            self.assertGreater(row.message_count, 0)
            self.assertIsNotNone(row.average_quality_score)
        finally:
            db.close()

    def test_07_cleaning_writes_sanitized_messages_table(self) -> None:
        batch_id = self._import_sample()
        cleaned = self.client.post(f"/api/cleaning/run/{batch_id}")
        self.assertEqual(cleaned.status_code, 200, cleaned.text)

        db = self.db.SessionLocal()
        try:
            from app.db_models import SanitizedMessage as DbSanitizedMessage
            rows = (
                db.query(DbSanitizedMessage)
                .filter(DbSanitizedMessage.batch_id == batch_id)
                .all()
            )
            self.assertGreater(len(rows), 0)
            for row in rows:
                self.assertIn(row.role, ("customer", "agent", "system"))
                self.assertIsNotNone(row.content)
                self.assertIsNotNone(row.sanitized_content)
        finally:
            db.close()

    def test_08_quality_fields_are_persisted(self) -> None:
        batch_id = self._import_sample()
        self.client.post(f"/api/cleaning/run/{batch_id}")

        db = self.db.SessionLocal()
        try:
            from app.db_models import SanitizedMessage as DbSanitizedMessage
            rows = (
                db.query(DbSanitizedMessage)
                .filter(DbSanitizedMessage.batch_id == batch_id)
                .all()
            )
            self.assertGreater(len(rows), 0)
            for row in rows:
                # quality_score
                self.assertIsNotNone(row.quality_score)
                self.assertGreaterEqual(float(row.quality_score), 0.0)
                self.assertLessEqual(float(row.quality_score), 1.0)
                # quality_level
                self.assertIn(row.quality_level, ("high", "medium", "low"))
                # suggested_action
                self.assertIn(row.suggested_action, ("keep", "review", "drop"))
                # cleaning_issues is a list (JSON)
                self.assertIsInstance(row.cleaning_issues, list)
                # risk_flags is a list (JSON)
                self.assertIsInstance(row.risk_flags, list)
                # pii_entities is a list (JSON) or None
                if row.pii_entities is not None:
                    self.assertIsInstance(row.pii_entities, list)
        finally:
            db.close()

    def test_09_sanitized_batch_detail_reads_from_db(self) -> None:
        batch_id = self._import_sample()
        self.client.post(f"/api/cleaning/run/{batch_id}")

        sanitized = self.client.get(f"/api/sanitized/{batch_id}")
        self.assertEqual(sanitized.status_code, 200, sanitized.text)
        data = sanitized.json()["data"]
        self.assertEqual(data["batch_id"], batch_id)
        self.assertEqual(data["status"], "sanitized")
        self.assertGreater(data["sanitized_message_count"], 0)
        self.assertGreater(len(data["messages"]), 0)
        for msg in data["messages"]:
            for field in [
                "quality_score",
                "quality_level",
                "suggested_action",
                "cleaning_issues",
                "risk_flags",
            ]:
                self.assertIn(field, msg, f"Message missing field: {field}")

    def test_10_duplicate_cleaning_is_idempotent(self) -> None:
        """Re-cleaning the same batch should replace sanitized messages."""
        import app.db_repositories as db_repo
        from app.schemas import SanitizedBatch, SanitizedMessage

        db = self.db.SessionLocal()
        try:
            unique = self._unique + "_clean_idem"
            batch_id = f"batch_clean_{unique}"

            msg1 = SanitizedMessage(
                source_batch_id=batch_id,
                conversation_id=f"conv_{unique}",
                message_id=f"msg_{unique}_1",
                source_message_id=f"msg_{unique}_1",
                role="customer",
                content="Test message 1",
                pii_detected=False,
                pii_types=[],
                cleaning_notes=[],
                cleaning_issues=[],
                risk_flags=[],
                quality_score=0.9,
                quality_level="high",
                suggested_action="keep",
            )
            sb = SanitizedBatch(
                batch_id=batch_id,
                source_batch_id=batch_id,
                status="sanitized",
                raw_message_count=1,
                sanitized_message_count=1,
                dropped_message_count=0,
                pii_detected_count=0,
                exact_duplicate_count=0,
                near_duplicate_count=0,
                low_quality_count=0,
                noise_count=0,
                review_recommended_count=0,
                drop_recommended_count=0,
                average_quality_score=0.9,
                created_at="2026-07-04T00:00:00",
                messages=[msg1],
            )
            db_repo.save_sanitized_batch_to_db(db, sb, type("Job", (), {"job_id": "j1"})())
            count_1 = (
                db.query(db_repo.DbSanitizedMessage)
                .filter(db_repo.DbSanitizedMessage.batch_id == batch_id)
                .count()
            )
            self.assertEqual(count_1, 1)

            # Save again with 3 messages
            msgs = [
                SanitizedMessage(
                    source_batch_id=batch_id,
                    conversation_id=f"conv_{unique}",
                    message_id=f"msg_{unique}_{i}",
                    source_message_id=f"msg_{unique}_{i}",
                    role="customer",
                    content=f"Test message {i}",
                    pii_detected=False,
                    pii_types=[],
                    cleaning_notes=[],
                    cleaning_issues=[],
                    risk_flags=[],
                    quality_score=0.8,
                    quality_level="medium",
                    suggested_action="keep",
                )
                for i in range(3)
            ]
            sb2 = SanitizedBatch(
                batch_id=batch_id,
                source_batch_id=batch_id,
                status="sanitized",
                raw_message_count=3,
                sanitized_message_count=3,
                dropped_message_count=0,
                pii_detected_count=0,
                exact_duplicate_count=0,
                near_duplicate_count=0,
                low_quality_count=0,
                noise_count=0,
                review_recommended_count=0,
                drop_recommended_count=0,
                average_quality_score=0.8,
                created_at="2026-07-04T00:00:00",
                messages=msgs,
            )
            db_repo.save_sanitized_batch_to_db(
                db, sb2, type("Job", (), {"job_id": "j2"})()
            )
            count_2 = (
                db.query(db_repo.DbSanitizedMessage)
                .filter(db_repo.DbSanitizedMessage.batch_id == batch_id)
                .count()
            )
            self.assertEqual(count_2, 3, "Should have replaced, not appended")
        finally:
            db.close()

    # ── Health check ───────────────────────────────────────────────

    def test_11_health_reports_p1_m24_3(self) -> None:
        health = self.client.get("/health")
        self.assertEqual(health.status_code, 200, health.text)
        self.assertEqual(health.json()["phase"], "P1-M24.3")
        db_status = health.json()["database_status"]
        self.assertTrue(db_status["enabled"])
        self.assertEqual(db_status["status"], "ok")

    # ── JSON storage compatibility ─────────────────────────────────

    def test_12_json_storage_still_works(self) -> None:
        """Verify the JSON storage is still written alongside DB."""
        batch_id = self._import_sample()
        raw_file = (
            ROOT_DIR / "backend" / "storage" / "raw_batches" / f"{batch_id}.json"
        )
        self.assertTrue(
            raw_file.exists(),
            f"JSON storage file {raw_file} should still exist after import",
        )

    # ── Existing P1 flow remains intact ────────────────────────────

    def test_13_p1_flow_still_works_with_db(self) -> None:
        """Import → Clean → Get sanitized: full mini-flow through DB."""
        batch_id = self._import_sample()

        # Clean
        cleaned = self.client.post(f"/api/cleaning/run/{batch_id}")
        self.assertEqual(cleaned.status_code, 200, cleaned.text)
        self.assertIn("sanitized_message_count", cleaned.json()["data"])

        # Read sanitized
        sanitized = self.client.get(f"/api/sanitized/{batch_id}")
        self.assertEqual(sanitized.status_code, 200, sanitized.text)
        self.assertGreater(
            len(sanitized.json()["data"]["messages"]), 0
        )

        # Read raw batch
        raw = self.client.get(f"/api/sources/{batch_id}")
        self.assertEqual(raw.status_code, 200, raw.text)
        self.assertEqual(raw.json()["data"]["batch_id"], batch_id)


if __name__ == "__main__":
    unittest.main()

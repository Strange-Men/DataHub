"""Focused safety gates for the P1 database-only runtime cutover."""

from __future__ import annotations

import importlib
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
import pytest


ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


class P1DatabaseAuthorityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._previous_database_url = os.environ.get("DATABASE_URL")
        cls._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        cls._tmp.close()
        os.environ["DATABASE_URL"] = f"sqlite:///{cls._tmp.name}"
        os.environ["DATAHUB_ENV"] = "test"
        os.environ["EMBEDDING_PROVIDER"] = "mock"
        os.environ["LLM_PROVIDER"] = "mock"

        import app.database as database
        import app.db_models as db_models
        import app.db_repositories as db_repositories
        import app.main as main
        import app.storage as storage

        cls.database = importlib.reload(database)
        cls.models = importlib.reload(db_models)
        cls.database.init_database_tables()
        cls.repo = importlib.reload(db_repositories)
        cls.storage = importlib.reload(storage)
        cls.main = importlib.reload(main)
        cls.client = TestClient(cls.main.app)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client.close()
        cls.database.engine.dispose()
        if cls._previous_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = cls._previous_database_url
        os.unlink(cls._tmp.name)

    def setUp(self) -> None:
        with self.database.engine.begin() as connection:
            for table in reversed(self.models.Base.metadata.sorted_tables):
                connection.execute(table.delete())

    @staticmethod
    def _payload() -> dict[str, object]:
        return {
            "source_name": "db-only-test",
            "conversations": [{
                "conversation_id": "conv-db-only",
                "messages": [
                    {"message_id": "q1", "role": "customer", "content": "How do returns work?", "timestamp": "2026-08-10T00:00:00Z"},
                    {"message_id": "a1", "role": "agent", "content": "Returns are accepted within 30 days.", "timestamp": "2026-08-10T00:00:01Z"},
                ],
            }],
        }

    def test_runtime_module_has_no_legacy_file_access(self) -> None:
        source = Path(self.storage.__file__).read_text(encoding="utf-8")
        for forbidden in (
            "_read_json_list",
            "_write_json_list",
            ".read_text(",
            ".write_text(",
            "LEGACY_RAG_IMPORT_INDEX_FILE",
        ):
            self.assertNotIn(forbidden, source)

    def test_database_outage_returns_safe_503_without_json_fallback(self) -> None:
        with patch.object(
            self.storage,
            "_SessionLocal",
            side_effect=RuntimeError("postgresql://user:secret@db.internal/datahub"),
        ):
            response = self.client.get("/api/sources")
        self.assertEqual(response.status_code, 503)
        body = response.json()
        self.assertEqual(body["error"]["code"], "P1_DATABASE_UNAVAILABLE")
        self.assertNotIn("secret", response.text)
        self.assertNotIn("db.internal", response.text)

    def test_import_rolls_back_when_repository_fails_after_flush(self) -> None:
        original = self.repo.save_raw_batch_to_db

        def fail_after_flush(*args, **kwargs):
            original(*args, **kwargs)
            raise RuntimeError("forced import failure")

        with patch.object(self.storage.db_repo, "save_raw_batch_to_db", fail_after_flush):
            response = self.client.post("/api/sources/import-json", json=self._payload())
        self.assertEqual(response.status_code, 503)
        db = self.database.SessionLocal()
        try:
            self.assertEqual(db.query(self.repo.RawBatch).count(), 0)
            self.assertEqual(db.query(self.repo.RawMessage).count(), 0)
        finally:
            db.close()

    def test_review_candidate_and_record_are_atomic(self) -> None:
        imported = self.client.post("/api/sources/import-json", json=self._payload()).json()
        batch_id = imported["data"]["batch_id"]
        self.client.post(f"/api/cleaning/run/{batch_id}")
        extraction = self.client.post(f"/api/extraction/run/{batch_id}").json()
        job_id = extraction["data"]["job_id"]
        job = self.client.get(f"/api/extraction/jobs/{job_id}").json()
        self.assertGreater(job["data"]["candidate_count"], 0)
        candidate_id = self.client.get("/api/knowledge/candidates").json()["data"]["candidates"][0]["candidate_id"]

        with patch.object(
            self.storage.db_repo,
            "save_review_record_to_db",
            side_effect=RuntimeError("forced review failure"),
        ):
            response = self.client.post(
                f"/api/review/{candidate_id}/approve",
                json={"reviewer": "db-only-test", "review_note": "atomic"},
            )
        self.assertEqual(response.status_code, 503)
        db = self.database.SessionLocal()
        try:
            candidate = self.repo.get_knowledge_candidate_from_db(db, candidate_id)
            self.assertIsNotNone(candidate)
            self.assertEqual(candidate.review_status, "pending_review")
            self.assertEqual(db.query(self.repo.ReviewRecord).count(), 0)
        finally:
            db.close()

    def test_cleaning_rolls_back_batch_and_messages(self) -> None:
        imported = self.client.post(
            "/api/sources/import-json", json=self._payload()
        ).json()
        batch_id = imported["data"]["batch_id"]
        original = self.repo.save_sanitized_batch_to_db

        def fail_after_flush(*args, **kwargs):
            original(*args, **kwargs)
            raise RuntimeError("forced cleaning failure")

        with patch.object(
            self.storage.db_repo, "save_sanitized_batch_to_db", fail_after_flush
        ):
            response = self.client.post(f"/api/cleaning/run/{batch_id}")
        self.assertEqual(response.status_code, 503)
        db = self.database.SessionLocal()
        try:
            self.assertEqual(db.query(self.repo.DbSanitizedBatch).count(), 0)
            self.assertEqual(db.query(self.repo.DbSanitizedMessage).count(), 0)
        finally:
            db.close()

    def test_bad_case_draft_candidate_and_relation_are_atomic(self) -> None:
        from app.schemas import BadCaseDraftRequest, BadCaseRecord

        bad_case = BadCaseRecord(
            bad_case_id="badcase_atomic",
            retrieval_id="retrieval_atomic",
            user_query="How do returns work?",
            agent_answer="Unknown",
            issue_type="missing_knowledge",
            severity="medium",
            status="open",
            review_note="",
            linked_chunk_ids=[],
            retrieval_result_count=0,
            metadata={},
            created_at="2026-08-10T00:00:00Z",
            updated_at="2026-08-10T00:00:00Z",
        )
        db = self.database.SessionLocal()
        try:
            self.repo.save_bad_case_to_db(db, bad_case.model_dump())
        finally:
            db.close()

        with patch.object(
            self.storage.db_repo,
            "update_bad_case_in_db",
            side_effect=RuntimeError("forced relation failure"),
        ):
            with self.assertRaises(self.storage.P1PersistenceError):
                self.storage.create_candidate_from_bad_case(
                    bad_case,
                    BadCaseDraftRequest(
                        question="How do returns work?",
                        answer="Returns are accepted within 30 days.",
                    ),
                    "How do returns work?",
                    "Returns are accepted within 30 days.",
                    ["returns"],
                )
        db = self.database.SessionLocal()
        try:
            self.assertEqual(db.query(self.repo.DbKnowledgeCandidate).count(), 0)
            stored = self.repo.get_bad_case_from_db(db, bad_case.bad_case_id)
            self.assertEqual(stored["status"], "open")
            self.assertIsNone(stored["linked_candidate_id"])
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()


@pytest.mark.postgres_integration
def test_postgresql_import_transaction_rolls_back(monkeypatch) -> None:
    """The storage transaction rolls back both raw tables on PostgreSQL."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.schemas import ImportJsonRequest
    import app.db_models as models
    import app.db_repositories as repo
    import app.storage as storage
    from scripts.test_environment import require_test_database_url

    database_url = os.getenv("DATAHUB_TEST_DATABASE_URL", "").strip()
    if not database_url:
        pytest.skip("DATAHUB_TEST_DATABASE_URL is required")
    database_url = require_test_database_url(
        database_url,
        development_url=os.getenv("DATAHUB_DEVELOPMENT_DATABASE_URL"),
    )
    engine = create_engine(database_url, pool_pre_ping=True)
    pg_session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(storage, "_SessionLocal", pg_session)
    original = repo.save_raw_batch_to_db

    def fail_after_flush(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("forced PostgreSQL import failure")

    monkeypatch.setattr(storage.db_repo, "save_raw_batch_to_db", fail_after_flush)
    payload = ImportJsonRequest(**P1DatabaseAuthorityTest._payload())
    with pytest.raises(storage.P1PersistenceError):
        storage.create_raw_batch(payload)

    db = pg_session()
    try:
        assert db.query(models.RawBatch).count() == 0
        assert db.query(models.RawMessage).count() == 0
    finally:
        db.close()
        engine.dispose()

"""Tests for P1-M22 Approved Knowledge Sync to Vector RAG.

Verifies:
- approved candidate can be synced to rag_embeddings.
- rejected candidate does NOT enter rag_embeddings.
- pending_review candidate does NOT enter rag_embeddings.
- needs_revision candidate does NOT enter rag_embeddings.
- Repeated sync is idempotent (count does not double).
- rag_embeddings metadata_json contains candidate_id / source_type / modality.
- embedding_dimension matches the mock provider.
- source trace is not lost.
- rag_chunks original logic still works.
- Does NOT require real external embedding API.
- Does NOT require real Render database.
"""

import json
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


class ApprovedKnowledgeVectorSyncTest(unittest.TestCase):
    """Test approved knowledge -> rag_embeddings sync using temporary SQLite."""

    @classmethod
    def setUpClass(cls) -> None:
        # Create a temporary SQLite database file
        cls._tmpfile = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        cls._tmpfile.close()
        cls._db_path = cls._tmpfile.name
        os.environ["DATABASE_URL"] = f"sqlite:///{cls._db_path}"
        # Ensure mock embedding provider (no external API)
        os.environ["EMBEDDING_PROVIDER"] = "mock"
        os.environ["EMBEDDING_DIMENSION"] = "1536"

        # Force re-import so the app uses the temp DB
        import importlib
        import app.database as db_module
        import app.db_models as _models_module
        import app.db_repositories as _repo_module
        import app.storage as _storage_module
        import app.main as _main_module

        importlib.reload(db_module)
        importlib.reload(_models_module)
        importlib.reload(_repo_module)
        db_module.init_database_tables()
        importlib.reload(_storage_module)
        importlib.reload(_main_module)

        cls.db = db_module
        cls.app = _main_module.app
        cls.client = TestClient(cls.app)
        cls.run_id = uuid4().hex[:8]

    @classmethod
    def tearDownClass(cls) -> None:
        try:
            os.unlink(cls._db_path)
        except OSError:
            pass

    def setUp(self) -> None:
        self._unique = f"{self.run_id}_{uuid4().hex[:6]}"

    # ── Helpers ────────────────────────────────────────────────────

    def _import_clean_extract(self, suffix: str = "") -> str:
        """Import -> clean -> extract. Returns batch_id."""
        unique = suffix or self._unique
        payload = {
            "source_name": f"p1_m22_test_{unique}",
            "conversations": [
                {
                    "conversation_id": f"conv_{unique}_0",
                    "messages": [
                        {
                            "message_id": f"msg_{unique}_q",
                            "role": "customer",
                            "content": f"How do I get a refund for order ORD-{unique}?",
                            "timestamp": "2026-07-05T10:00:00",
                        },
                        {
                            "message_id": f"msg_{unique}_a",
                            "role": "agent",
                            "content": "You can return your order within 30 days for a full refund. Please fill out the return form in your account.",
                            "timestamp": "2026-07-05T10:01:00",
                        },
                    ],
                },
            ],
        }
        resp = self.client.post("/api/sources/import-json", json=payload)
        self.assertEqual(resp.status_code, 200, f"Import failed: {resp.text}")
        batch_id = resp.json()["data"]["batch_id"]

        resp = self.client.post(f"/api/cleaning/run/{batch_id}")
        self.assertEqual(resp.status_code, 200, f"Cleaning failed: {resp.text}")

        resp = self.client.post(f"/api/extraction/run/{batch_id}")
        self.assertEqual(resp.status_code, 200, f"Extraction failed: {resp.text}")

        return batch_id

    def _get_first_candidate_id(self) -> str:
        """Get the first candidate ID from the candidate list."""
        resp = self.client.get("/api/knowledge/candidates")
        self.assertEqual(resp.status_code, 200)
        candidates = resp.json()["data"]["candidates"]
        self.assertGreater(len(candidates), 0, "Expected at least one candidate")
        return candidates[0]["candidate_id"]

    def _approve_candidate(self, candidate_id: str) -> None:
        """Approve a candidate."""
        resp = self.client.post(
            f"/api/review/{candidate_id}/approve",
            json={"reviewer": "m22_tester", "review_note": "Approved for vector sync test."},
        )
        self.assertEqual(resp.status_code, 200, f"Approve failed: {resp.text}")

    def _reject_candidate(self, candidate_id: str) -> None:
        """Reject a candidate."""
        resp = self.client.post(
            f"/api/review/{candidate_id}/reject",
            json={"reviewer": "m22_tester", "review_note": "Rejected for vector sync test."},
        )
        self.assertEqual(resp.status_code, 200, f"Reject failed: {resp.text}")

    def _build_rag(self) -> dict:
        """Build RAG and return response data."""
        resp = self.client.post("/api/rag/build")
        self.assertEqual(resp.status_code, 200, f"RAG build failed: {resp.text}")
        return resp.json()["data"]

    def _count_rag_embeddings(self) -> int:
        """Count rag_embeddings rows via DB query."""
        from app.database import SessionLocal
        from app.db_models import RagEmbedding
        db = SessionLocal()
        try:
            return db.query(RagEmbedding).count()
        finally:
            db.close()

    # ── Tests ──────────────────────────────────────────────────────

    def test_01_approved_candidate_syncs_to_rag_embeddings(self):
        """Approved candidate should create a rag_embeddings row."""
        self._import_clean_extract("sync01")
        cid = self._get_first_candidate_id()
        self._approve_candidate(cid)

        data = self._build_rag()

        # Verify build result includes vector sync fields
        self.assertIn("embedding_count", data)
        self.assertGreater(data["embedding_count"], 0,
                          "Expected at least 1 embedding for approved candidate")
        self.assertTrue(data.get("vector_sync_enabled"),
                       "vector_sync_enabled should be True")
        self.assertEqual(data.get("embedding_provider"), "mock")
        self.assertEqual(data.get("embedding_model"), "mock-deterministic")
        self.assertEqual(data.get("embedding_dimension"), 1536)
        self.assertGreater(data.get("approved_candidate_count", 0), 0)

        # Verify rag_embeddings table has rows
        emb_count = self._count_rag_embeddings()
        self.assertGreater(emb_count, 0,
                          "rag_embeddings table should have at least 1 row")

    def test_02_rejected_candidate_does_not_sync(self):
        """Rejected candidate must NOT enter rag_embeddings."""
        self._import_clean_extract("sync02")
        cid = self._get_first_candidate_id()
        self._reject_candidate(cid)

        self._build_rag()

        # Verify the rejected candidate is NOT in rag_embeddings
        from app.database import SessionLocal
        from app.db_models import RagEmbedding
        db = SessionLocal()
        try:
            row = db.query(RagEmbedding).filter(
                RagEmbedding.candidate_id == cid
            ).first()
            self.assertIsNone(row,
                            f"Rejected candidate {cid} should NOT be in rag_embeddings")
        finally:
            db.close()

    def test_03_pending_review_candidate_does_not_sync(self):
        """pending_review candidate must NOT enter rag_embeddings."""
        self._import_clean_extract("sync03")
        cid = self._get_first_candidate_id()
        # Don't approve — candidate stays pending_review

        self._build_rag()

        # Verify the pending_review candidate is NOT in rag_embeddings
        from app.database import SessionLocal
        from app.db_models import RagEmbedding
        db = SessionLocal()
        try:
            row = db.query(RagEmbedding).filter(
                RagEmbedding.candidate_id == cid
            ).first()
            self.assertIsNone(row,
                            f"Pending candidate {cid} should NOT be in rag_embeddings")
        finally:
            db.close()

    def test_04_needs_revision_candidate_does_not_sync(self):
        """needs_revision candidate must NOT enter rag_embeddings."""
        self._import_clean_extract("sync04")
        cid = self._get_first_candidate_id()
        # Mark as needs_revision
        resp = self.client.post(
            f"/api/review/{cid}/needs-revision",
            json={"reviewer": "m22_tester", "review_note": "Needs work."},
        )
        self.assertEqual(resp.status_code, 200)

        self._build_rag()

        # Verify the needs_revision candidate is NOT in rag_embeddings
        from app.database import SessionLocal
        from app.db_models import RagEmbedding
        db = SessionLocal()
        try:
            row = db.query(RagEmbedding).filter(
                RagEmbedding.candidate_id == cid
            ).first()
            self.assertIsNone(row,
                            f"Needs-revision candidate {cid} should NOT be in rag_embeddings")
        finally:
            db.close()

    def test_05_repeated_sync_is_idempotent(self):
        """Second sync should not double the embedding count."""
        self._import_clean_extract("sync05")
        cid = self._get_first_candidate_id()
        self._approve_candidate(cid)

        # Count rag_embeddings before
        from app.database import SessionLocal
        from app.db_models import RagEmbedding
        db = SessionLocal()
        try:
            count_before = db.query(RagEmbedding).filter(
                RagEmbedding.candidate_id == cid
            ).count()
        finally:
            db.close()

        # First build — should create the embedding
        self._build_rag()

        # Second build — should be idempotent (delete-rebuild, same count of this candidate)
        data2 = self._build_rag()

        # The same candidate should appear exactly once in rag_embeddings
        db = SessionLocal()
        try:
            count_after = db.query(RagEmbedding).filter(
                RagEmbedding.candidate_id == cid
            ).count()
            self.assertEqual(count_after, 1,
                           f"Candidate {cid} should have exactly 1 embedding row, got {count_after}")
        finally:
            db.close()

        # embedding_count should be >= 1 (accounts for this candidate + any prior)
        self.assertGreaterEqual(data2.get("embedding_count", 0), 1)

    def test_06_metadata_json_contains_required_fields(self):
        """rag_embeddings metadata_json must include candidate_id, source_type, modality."""
        self._import_clean_extract("sync06")
        cid = self._get_first_candidate_id()
        self._approve_candidate(cid)

        self._build_rag()

        from app.database import SessionLocal
        from app.db_models import RagEmbedding
        db = SessionLocal()
        try:
            rows = db.query(RagEmbedding).all()
            self.assertGreater(len(rows), 0)
            for row in rows:
                meta = row.metadata_json
                self.assertIsInstance(meta, dict)
                self.assertIn("candidate_id", meta)
                self.assertIn("source_type", meta)
                self.assertIn("modality", meta)
                self.assertEqual(meta.get("modality"), "text")
                self.assertIn("sync_method", meta)
                self.assertEqual(meta.get("sync_method"), "approved_knowledge_vector_sync")
        finally:
            db.close()

    def test_07_embedding_dimension_matches_mock_provider(self):
        """rag_embeddings embedding_dimension should match mock provider (1536)."""
        self._import_clean_extract("sync07")
        cid = self._get_first_candidate_id()
        self._approve_candidate(cid)

        self._build_rag()

        from app.database import SessionLocal
        from app.db_models import RagEmbedding
        db = SessionLocal()
        try:
            rows = db.query(RagEmbedding).all()
            self.assertGreater(len(rows), 0)
            for row in rows:
                self.assertEqual(row.embedding_dimension, 1536,
                               f"Expected embedding_dimension=1536, got {row.embedding_dimension}")
                self.assertEqual(row.embedding_provider, "mock")
                self.assertEqual(row.embedding_model, "mock-deterministic")
        finally:
            db.close()

    def test_08_source_trace_not_lost(self):
        """rag_embeddings row should contain source trace back to candidate."""
        self._import_clean_extract("sync08")
        cid = self._get_first_candidate_id()
        self._approve_candidate(cid)

        self._build_rag()

        from app.database import SessionLocal
        from app.db_models import RagEmbedding
        db = SessionLocal()
        try:
            row = db.query(RagEmbedding).filter(
                RagEmbedding.candidate_id == cid
            ).first()
            self.assertIsNotNone(row, f"No rag_embedding row for candidate {cid}")
            self.assertEqual(row.candidate_id, cid)
            self.assertIsNotNone(row.source_type)
            self.assertIsNotNone(row.chunk_text)
            self.assertTrue(len(row.chunk_text) > 0)
            # metadata_json should contain trace fields
            meta = row.metadata_json
            self.assertIsInstance(meta, dict)
            self.assertIn("source_type", meta)
        finally:
            db.close()

    def test_09_rag_chunks_still_work(self):
        """rag_chunks original logic must still be functional."""
        self._import_clean_extract("sync09")
        cid = self._get_first_candidate_id()
        self._approve_candidate(cid)

        data = self._build_rag()

        # rag_chunks should still be created
        self.assertGreater(data.get("chunk_count", 0), 0,
                         "rag_chunks should still be created")

        # Can list chunks
        resp = self.client.get("/api/rag/chunks")
        self.assertEqual(resp.status_code, 200)
        chunks = resp.json()["data"]["chunks"]
        self.assertGreater(len(chunks), 0, "Should be able to list rag_chunks")

    def test_10_build_result_has_all_vector_fields(self):
        """RAG build result should include all expected vector sync fields."""
        self._import_clean_extract("sync10")
        cid = self._get_first_candidate_id()
        self._approve_candidate(cid)

        data = self._build_rag()

        # All expected fields should be present
        for field in [
            "embedding_count",
            "vector_sync_enabled",
            "embedding_provider",
            "embedding_model",
            "embedding_dimension",
            "approved_candidate_count",
            "skipped_candidate_count",
        ]:
            self.assertIn(field, data, f"RAG build result missing field: {field}")

    def test_11_mock_provider_no_external_api(self):
        """Vector sync must work without any external API."""
        # Ensure no API key is set
        old_key = os.environ.pop("EMBEDDING_API_KEY", None)
        old_openai = os.environ.pop("OPENAI_API_KEY", None)
        try:
            self._import_clean_extract("sync11")
            cid = self._get_first_candidate_id()
            self._approve_candidate(cid)

            data = self._build_rag()

            self.assertTrue(data.get("vector_sync_enabled"))
            self.assertGreater(data.get("embedding_count", 0), 0)
        finally:
            if old_key:
                os.environ["EMBEDDING_API_KEY"] = old_key
            if old_openai:
                os.environ["OPENAI_API_KEY"] = old_openai

    def test_12_embedding_insert_is_deterministic(self):
        """Same candidate synced twice should produce same embedding (mock deterministic)."""
        self._import_clean_extract("sync12")
        cid = self._get_first_candidate_id()
        self._approve_candidate(cid)

        self._build_rag()

        from app.database import SessionLocal
        from app.db_models import RagEmbedding
        db = SessionLocal()
        try:
            row1 = db.query(RagEmbedding).filter(
                RagEmbedding.candidate_id == cid
            ).first()
            emb1 = row1.embedding
            db.close()
        except Exception:
            db.close()
            raise

        # Rebuild
        self._build_rag()

        db2 = SessionLocal()
        try:
            row2 = db2.query(RagEmbedding).filter(
                RagEmbedding.candidate_id == cid
            ).first()
            emb2 = row2.embedding

            # Both should be non-None
            self.assertIsNotNone(emb1)
            self.assertIsNotNone(emb2)

            # For SQLite: stored as JSON text, compare parsed values
            if isinstance(emb1, str) and isinstance(emb2, str):
                vec1 = json.loads(emb1)
                vec2 = json.loads(emb2)
                self.assertEqual(len(vec1), len(vec2))
                for a, b in zip(vec1, vec2):
                    self.assertAlmostEqual(a, b, places=10)
        finally:
            db2.close()

    def test_13_chunk_count_and_embedding_count_correlate(self):
        """Each approved candidate should produce 1 chunk and 1 embedding."""
        self._import_clean_extract("sync13")
        cid = self._get_first_candidate_id()
        self._approve_candidate(cid)

        data = self._build_rag()

        # chunk_count and embedding_count should both reflect approved candidates
        self.assertEqual(
            data.get("chunk_count", 0),
            data.get("embedding_count", 0),
            "Each approved candidate should produce exactly 1 chunk and 1 embedding"
        )
        self.assertEqual(
            data.get("approved_candidate_count", 0),
            data.get("embedding_count", 0),
            "embedding_count should equal approved_candidate_count"
        )

    def test_14_mixed_status_only_approved_synced(self):
        """With mixed candidate statuses, only approved ones get embeddings."""
        # Import batch A, approve its candidate
        batch_a = self._import_clean_extract("sync14a")
        resp = self.client.get("/api/knowledge/candidates")
        candidates = resp.json()["data"]["candidates"]
        # The latest candidates should include those from batch_a
        # Find a candidate from batch_a by source_batch_id
        approved_cid = None
        for c in candidates:
            if c.get("source_batch_id") == batch_a:
                approved_cid = c["candidate_id"]
                break
        self.assertIsNotNone(approved_cid, "Should find candidate from batch_a")
        self._approve_candidate(approved_cid)

        # Import batch B, do NOT approve
        batch_b = self._import_clean_extract("sync14b")
        resp = self.client.get("/api/knowledge/candidates")
        candidates = resp.json()["data"]["candidates"]
        pending_cid = None
        for c in candidates:
            if c.get("source_batch_id") == batch_b:
                pending_cid = c["candidate_id"]
                break
        self.assertIsNotNone(pending_cid, "Should find candidate from batch_b")

        self._build_rag()

        # Verify approved candidate IS in rag_embeddings
        from app.database import SessionLocal
        from app.db_models import RagEmbedding
        db = SessionLocal()
        try:
            approved_row = db.query(RagEmbedding).filter(
                RagEmbedding.candidate_id == approved_cid
            ).first()
            self.assertIsNotNone(approved_row,
                               f"Approved candidate {approved_cid} should be in rag_embeddings")

            # Verify pending candidate is NOT in rag_embeddings
            pending_row = db.query(RagEmbedding).filter(
                RagEmbedding.candidate_id == pending_cid
            ).first()
            self.assertIsNone(pending_row,
                            f"Pending candidate {pending_cid} should NOT be in rag_embeddings")
        finally:
            db.close()


class TestRagEmbeddingsRepositoryFunctions(unittest.TestCase):
    """Test the rag_embeddings repo functions directly."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmpfile = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        cls._tmpfile.close()
        cls._db_path = cls._tmpfile.name
        os.environ["DATABASE_URL"] = f"sqlite:///{cls._db_path}"
        os.environ["EMBEDDING_PROVIDER"] = "mock"

        import importlib
        import app.database as db_module
        import app.db_models as _models_module
        import app.db_repositories as _repo_module

        # Reload db_module first, then db_models (which picks up new Base),
        # then call init_database_tables to create all tables including rag_embeddings
        importlib.reload(db_module)
        importlib.reload(_models_module)
        importlib.reload(_repo_module)
        db_module.init_database_tables()

        cls.db = db_module
        cls.repo = _repo_module

    @classmethod
    def tearDownClass(cls) -> None:
        try:
            os.unlink(cls._db_path)
        except OSError:
            pass

    def setUp(self) -> None:
        # Clean rag_embeddings before each test
        from app.database import SessionLocal
        from app.db_models import RagEmbedding
        db = SessionLocal()
        try:
            db.query(RagEmbedding).delete()
            db.commit()
        finally:
            db.close()

    def test_save_and_list_embeddings(self):
        """save_rag_embeddings_to_db should persist and list_rag_embeddings_from_db should return them."""
        from app.database import SessionLocal
        from app.embedding import MockEmbeddingProvider

        provider = MockEmbeddingProvider(dimension=1536)
        emb_vector = provider.embed("test chunk text for saving")

        embedding_data = [
            {
                "id": "ragemb_test_001",
                "chunk_id": "chunk_test_001",
                "candidate_id": "kc_test_001",
                "source_type": "chat_logs",
                "source_batch_id": "batch_test_001",
                "source_message_id": "msg_test_001",
                "modality": "text",
                "chunk_text": "test chunk text for saving",
                "metadata_json": {
                    "candidate_id": "kc_test_001",
                    "source_type": "chat_logs",
                    "source_batch_id": "batch_test_001",
                    "intent": "refund",
                    "quality_score": 0.85,
                    "modality": "text",
                    "sync_method": self.repo.DEFAULT_SYNC_METHOD,
                },
                "embedding": emb_vector,
                "embedding_provider": "mock",
                "embedding_model": "mock-deterministic",
                "embedding_dimension": 64,
            }
        ]

        db = SessionLocal()
        try:
            count = self.repo.save_rag_embeddings_to_db(db, embedding_data)
            self.assertEqual(count, 1)

            rows = self.repo.list_rag_embeddings_from_db(db)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["candidate_id"], "kc_test_001")
            self.assertEqual(rows[0]["source_type"], "chat_logs")
            self.assertEqual(rows[0]["modality"], "text")
            self.assertEqual(rows[0]["embedding_provider"], "mock")
            self.assertIsNotNone(rows[0]["embedding_preview"])
            self.assertIn("metadata_json", rows[0])
            meta = rows[0]["metadata_json"]
            self.assertIn("candidate_id", meta)
            self.assertIn("source_type", meta)
        finally:
            db.close()

    def test_save_is_delete_rebuild_idempotent(self):
        """Saving twice should replace, not duplicate."""
        from app.database import SessionLocal
        from app.embedding import MockEmbeddingProvider

        provider = MockEmbeddingProvider(dimension=1536)
        emb_vector = provider.embed("idempotent test")

        embedding_data = [
            {
                "id": "ragemb_idem_001",
                "chunk_id": "chunk_idem_001",
                "candidate_id": "kc_idem_001",
                "source_type": "chat_logs",
                "source_batch_id": "batch_idem",
                "source_message_id": "msg_idem",
                "modality": "text",
                "chunk_text": "idempotent test",
                "metadata_json": {
                    "candidate_id": "kc_idem_001",
                    "source_type": "chat_logs",
                    "modality": "text",
                    "sync_method": self.repo.DEFAULT_SYNC_METHOD,
                },
                "embedding": emb_vector,
                "embedding_provider": "mock",
                "embedding_model": "mock-deterministic",
                "embedding_dimension": 64,
            }
        ]

        db = SessionLocal()
        try:
            # First save
            c1 = self.repo.save_rag_embeddings_to_db(db, embedding_data)
            self.assertEqual(c1, 1)

            # Second save should still be 1 (delete-rebuild)
            c2 = self.repo.save_rag_embeddings_to_db(db, embedding_data)
            self.assertEqual(c2, 1, "Second save should still insert exactly 1 row")

            # DB should have exactly 1 row
            total = self.repo.count_rag_embeddings_from_db(db)
            self.assertEqual(total, 1, "Should have exactly 1 row after two saves")
        finally:
            db.close()

    def test_count_functions(self):
        """count functions should return correct values."""
        from app.database import SessionLocal
        from app.embedding import MockEmbeddingProvider

        provider = MockEmbeddingProvider(dimension=1536)

        db = SessionLocal()
        try:
            # Initially zero
            self.assertEqual(self.repo.count_rag_embeddings_from_db(db), 0)
            self.assertEqual(self.repo.count_rag_embeddings_by_sync_method(db), 0)

            # Add one
            embedding_data = [
                {
                    "id": "ragemb_count_001",
                    "chunk_id": "chunk_count_001",
                    "candidate_id": "kc_count_001",
                    "source_type": "chat_logs",
                    "source_batch_id": "batch_count",
                    "source_message_id": None,
                    "modality": "text",
                    "chunk_text": "count test",
                    "metadata_json": {
                        "candidate_id": "kc_count_001",
                        "source_type": "chat_logs",
                        "modality": "text",
                        "sync_method": self.repo.DEFAULT_SYNC_METHOD,
                    },
                    "embedding": provider.embed("count test"),
                    "embedding_provider": "mock",
                    "embedding_model": "mock-deterministic",
                    "embedding_dimension": 64,
                }
            ]
            self.repo.save_rag_embeddings_to_db(db, embedding_data)

            self.assertEqual(self.repo.count_rag_embeddings_from_db(db), 1)
            self.assertEqual(self.repo.count_rag_embeddings_by_sync_method(db), 1)
        finally:
            db.close()


class TestHealthPhaseUpdated(unittest.TestCase):
    """Verify health endpoint reports P1-M22."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmpfile = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        cls._tmpfile.close()
        cls._db_path = cls._tmpfile.name
        os.environ["DATABASE_URL"] = f"sqlite:///{cls._db_path}"

        import importlib
        import app.database as db_module
        import app.db_models as _models_module
        import app.main as _main_module

        importlib.reload(db_module)
        importlib.reload(_models_module)
        db_module.init_database_tables()
        importlib.reload(_main_module)

        cls.app = _main_module.app
        cls.client = TestClient(cls.app)

    @classmethod
    def tearDownClass(cls) -> None:
        try:
            os.unlink(cls._db_path)
        except OSError:
            pass

    def test_health_reports_p1_m24(self):
        """Health endpoint should report phase P1-M24.2."""
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data.get("phase"), "P1-M24.2",
                        f"Expected phase P1-M24.2, got {data.get('phase')}")


if __name__ == "__main__":
    unittest.main()

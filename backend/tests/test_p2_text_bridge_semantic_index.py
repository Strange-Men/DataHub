"""P2-M7 tests for isolated, governed text-bridge embeddings."""

import importlib
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient


ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


class P2TextBridgeSemanticIndexTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._saved_environment = {
            name: os.environ.get(name)
            for name in (
                "DATABASE_URL",
                "EMBEDDING_PROVIDER",
                "EMBEDDING_MODEL",
                "EMBEDDING_DIMENSION",
                "P2_EMBEDDING_PROFILE",
            )
        }
        cls._temp_dir = Path(tempfile.mkdtemp(prefix="datahub-p2-embedding-test-"))
        cls._db_path = cls._temp_dir / "p2-embeddings.db"
        os.environ["DATABASE_URL"] = f"sqlite:///{cls._db_path}"
        os.environ["EMBEDDING_PROVIDER"] = "mock"
        os.environ["EMBEDDING_MODEL"] = "mock-deterministic"
        os.environ["EMBEDDING_DIMENSION"] = "16"
        os.environ.pop("P2_EMBEDDING_PROFILE", None)
        cls._reload_application()

        import app.database as database_module
        import app.db_models as models_module
        import app.main as main_module

        database_module.init_database_tables()
        importlib.reload(main_module)
        cls.database = database_module
        cls.models = models_module
        cls.client = TestClient(main_module.app)

    @classmethod
    def _reload_application(cls) -> None:
        module_names = (
            "app.database",
            "app.db_models",
            "app.db_repositories",
            "app.storage",
            "app.asset_repositories",
            "app.extraction_repositories",
            "app.review_repositories",
            "app.knowledge_asset_repositories",
            "app.knowledge_index_schemas",
            "app.knowledge_index_repositories",
            "app.knowledge_index_service",
            "app.knowledge_index_routes",
            "app.knowledge_embedding_schemas",
            "app.knowledge_embedding_repositories",
            "app.knowledge_embedding_service",
            "app.knowledge_embedding_routes",
        )
        for name in module_names:
            if name in sys.modules:
                importlib.reload(sys.modules[name])
            else:
                importlib.import_module(name)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.database.engine.dispose()
        for name, value in cls._saved_environment.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        cls._reload_application()
        import app.main as main_module

        importlib.reload(main_module)
        shutil.rmtree(cls._temp_dir, ignore_errors=True)

    def setUp(self) -> None:
        db = self.database.SessionLocal()
        try:
            db.query(self.models.P2KnowledgeEmbedding).delete()
            db.query(self.models.P2KnowledgeChunk).delete()
            db.query(self.models.P2KnowledgeIndexEntry).delete()
            db.query(self.models.KnowledgeAsset).delete()
            db.query(self.models.AssetReviewSnapshot).delete()
            db.query(self.models.ExtractionReview).delete()
            db.query(self.models.AssetExtraction).delete()
            db.query(self.models.ExtractionJob).delete()
            db.query(self.models.Asset).delete()
            db.add(
                self.models.Asset(
                    id="asset_p2_m7",
                    asset_type="image",
                    file_name="product-dh100.png",
                    mime_type="image/png",
                    size=1024,
                    storage_uri="local://assets/product-dh100.png",
                    hash="e" * 64,
                    status="uploaded",
                    metadata_json={"sku": "DH-100"},
                )
            )
            db.add(
                self.models.ExtractionJob(
                    id="job_p2_m7",
                    asset_id="asset_p2_m7",
                    extract_type="ocr",
                    provider="mock",
                    status="success",
                    retry_count=0,
                )
            )
            db.add(
                self.models.AssetExtraction(
                    id="extraction_p2_m7",
                    asset_id="asset_p2_m7",
                    job_id="job_p2_m7",
                    extract_type="ocr",
                    content="raw product content",
                    metadata_json={"mock_execution": True},
                    version=1,
                )
            )
            db.add(
                self.models.ExtractionReview(
                    id="review_p2_m7",
                    asset_id="asset_p2_m7",
                    extraction_id="extraction_p2_m7",
                    review_status="approved",
                    reviewer="p2_m7_reviewer",
                    original_content="raw product content",
                    revised_content="DH-100 uses recycled aluminum for indoor use.",
                    version=1,
                )
            )
            db.add(
                self.models.AssetReviewSnapshot(
                    id="snapshot_p2_m7",
                    asset_id="asset_p2_m7",
                    extraction_id="extraction_p2_m7",
                    review_id="review_p2_m7",
                    extract_type="ocr",
                    original_content="raw product content",
                    approved_content="DH-100 uses recycled aluminum for indoor use.",
                    metadata_json={"immutable": True},
                    version=1,
                )
            )
            db.add(
                self.models.KnowledgeAsset(
                    id="knowledge_asset_p2_m7",
                    source_snapshot_id="snapshot_p2_m7",
                    asset_id="asset_p2_m7",
                    content="DH-100 uses recycled aluminum for indoor use.",
                    content_type="ocr",
                    status="active",
                    version=1,
                    metadata_json={"rag_synced": False},
                )
            )
            db.commit()
        finally:
            db.close()

    def _create_index(self) -> dict[str, object]:
        response = self.client.post(
            "/api/knowledge-assets/knowledge_asset_p2_m7/index"
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()["data"]["index_entry"]

    def test_01_semantic_smoke_validates_vector_dimension_and_source_trace(self) -> None:
        entry = self._create_index()
        response = self.client.post(f"/api/knowledge-index/{entry['id']}/embed")
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()["data"]
        self.assertEqual(result["index_status"], "serving")
        self.assertEqual(result["provider"], "mock")
        self.assertEqual(result["model"], "mock-deterministic")
        self.assertEqual(result["dimension"], 16)
        self.assertEqual(result["created_count"], 1)
        trace = result["embeddings"][0]["source_trace"]
        self.assertEqual(trace["knowledge_asset_id"], "knowledge_asset_p2_m7")
        self.assertEqual(trace["snapshot_id"], "snapshot_p2_m7")
        self.assertEqual(trace["review_id"], "review_p2_m7")
        self.assertEqual(trace["extraction_id"], "extraction_p2_m7")
        self.assertEqual(trace["asset_id"], "asset_p2_m7")

        db = self.database.SessionLocal()
        try:
            row = db.query(self.models.P2KnowledgeEmbedding).one()
            self.assertEqual(len(json.loads(row.embedding)), 16)
            self.assertEqual(row.chunk_text, entry["chunks"][0]["chunk_text"])
            index_row = db.query(self.models.P2KnowledgeIndexEntry).one()
            self.assertEqual(index_row.status, "serving")
        finally:
            db.close()

    def test_02_duplicate_build_is_fingerprint_idempotent(self) -> None:
        entry = self._create_index()
        first = self.client.post(f"/api/knowledge-index/{entry['id']}/embed")
        second = self.client.post(f"/api/knowledge-index/{entry['id']}/embed")
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(second.status_code, 200, second.text)
        replay = second.json()["data"]
        self.assertEqual(replay["created_count"], 0)
        self.assertEqual(replay["skipped_count"], 1)
        self.assertEqual(
            first.json()["data"]["embeddings"][0]["fingerprint"],
            replay["embeddings"][0]["fingerprint"],
        )
        db = self.database.SessionLocal()
        try:
            self.assertEqual(db.query(self.models.P2KnowledgeEmbedding).count(), 1)
        finally:
            db.close()

    def test_03_archived_source_is_rejected(self) -> None:
        entry = self._create_index()
        archived = self.client.post(
            "/api/knowledge-assets/knowledge_asset_p2_m7/archive"
        )
        self.assertEqual(archived.status_code, 200, archived.text)
        response = self.client.post(f"/api/knowledge-index/{entry['id']}/embed")
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(response.json()["detail"]["code"], "KNOWLEDGE_ASSET_NOT_ACTIVE")

    def test_04_non_ready_index_cannot_generate(self) -> None:
        entry = self._create_index()
        db = self.database.SessionLocal()
        try:
            row = db.query(self.models.P2KnowledgeIndexEntry).one()
            row.status = "building"
            row.sync_state = "building"
            db.commit()
        finally:
            db.close()
        response = self.client.post(f"/api/knowledge-index/{entry['id']}/embed")
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(response.json()["detail"]["code"], "KNOWLEDGE_INDEX_NOT_READY")

    def test_05_dimension_mismatch_is_traced_without_partial_row(self) -> None:
        from app.embedding import MockEmbeddingProvider
        from app.knowledge_embedding_service import (
            P2EmbeddingDimensionError,
            P2KnowledgeEmbeddingService,
        )

        class BrokenDimensionProvider(MockEmbeddingProvider):
            def embed_batch(self, texts: list[str]) -> list[list[float]]:
                return [[0.0] * 7 for _ in texts]

        entry = self._create_index()
        db = self.database.SessionLocal()
        try:
            with self.assertRaises(P2EmbeddingDimensionError):
                P2KnowledgeEmbeddingService(
                    db, provider=BrokenDimensionProvider(dimension=8)
                ).build(str(entry["id"]))
            self.assertEqual(db.query(self.models.P2KnowledgeEmbedding).count(), 0)
            index_row = db.query(self.models.P2KnowledgeIndexEntry).one()
            self.assertEqual(
                index_row.error_message,
                "Embedding dimension mismatch; expected 8.",
            )
            self.assertEqual(index_row.status, "ready")
        finally:
            db.close()

    def test_06_changed_profile_creates_history_instead_of_overwrite(self) -> None:
        from app.embedding import MockEmbeddingProvider
        from app.knowledge_embedding_service import P2KnowledgeEmbeddingService

        class VersionedMockProvider(MockEmbeddingProvider):
            def __init__(self, model_name: str) -> None:
                super().__init__(dimension=8)
                self._model_name = model_name

            @property
            def model_name(self) -> str:
                return self._model_name

        entry = self._create_index()
        db = self.database.SessionLocal()
        try:
            first = P2KnowledgeEmbeddingService(
                db, provider=VersionedMockProvider("mock-v1")
            ).build(str(entry["id"]))
            index_row = db.query(self.models.P2KnowledgeIndexEntry).one()
            index_row.status = "ready"
            db.commit()
            second = P2KnowledgeEmbeddingService(
                db, provider=VersionedMockProvider("mock-v2")
            ).build(str(entry["id"]))
            self.assertNotEqual(
                first.embeddings[0].fingerprint,
                second.embeddings[0].fingerprint,
            )
            self.assertEqual(db.query(self.models.P2KnowledgeEmbedding).count(), 2)
        finally:
            db.close()

    def test_07_provider_failure_is_safely_persisted(self) -> None:
        from app.embedding import MockEmbeddingProvider
        from app.knowledge_embedding_service import (
            P2EmbeddingProviderError,
            P2KnowledgeEmbeddingService,
        )

        class FailingProvider(MockEmbeddingProvider):
            def embed_batch(self, texts: list[str]) -> list[list[float]]:
                raise RuntimeError("upstream-secret-detail")

        entry = self._create_index()
        db = self.database.SessionLocal()
        try:
            with self.assertRaises(P2EmbeddingProviderError):
                P2KnowledgeEmbeddingService(
                    db, provider=FailingProvider(dimension=8)
                ).build(str(entry["id"]))
            index_row = db.query(self.models.P2KnowledgeIndexEntry).one()
            self.assertEqual(index_row.error_message, "Embedding provider call failed.")
            self.assertNotIn("secret", index_row.error_message)
            self.assertEqual(db.query(self.models.P2KnowledgeEmbedding).count(), 0)
        finally:
            db.close()

    def test_08_management_list_preserves_complete_source_trace(self) -> None:
        entry = self._create_index()
        self.client.post(f"/api/knowledge-index/{entry['id']}/embed")
        response = self.client.get(
            f"/api/knowledge-embeddings?index_entry_id={entry['id']}"
        )
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()["data"]
        self.assertEqual(data["pagination"]["total"], 1)
        trace = data["embeddings"][0]["source_trace"]
        self.assertEqual(trace["index_entry_id"], entry["id"])
        self.assertEqual(trace["knowledge_asset_id"], "knowledge_asset_p2_m7")
        self.assertEqual(trace["snapshot_id"], "snapshot_p2_m7")
        self.assertEqual(trace["review_id"], "review_p2_m7")
        self.assertEqual(trace["extraction_id"], "extraction_p2_m7")
        self.assertEqual(trace["extraction_job_id"], "job_p2_m7")
        self.assertEqual(trace["asset_id"], "asset_p2_m7")

    def test_09_eval_fixture_covers_required_knowledge_categories(self) -> None:
        payload = json.loads(
            (ROOT_DIR / "samples" / "p2_rag_eval_queries.json").read_text(
                encoding="utf-8"
            )
        )
        categories = {item["category"] for item in payload["queries"]}
        self.assertTrue(
            {"product_knowledge", "policy_knowledge", "faq", "version_content"}
            <= categories
        )
        self.assertEqual(payload["scope"], "offline-eval-fixtures-only-no-retrieval-api")


if __name__ == "__main__":
    unittest.main()

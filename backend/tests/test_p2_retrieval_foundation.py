"""P2-M8.1 tests for explicit serving and isolated semantic retrieval."""

import importlib
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient


ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


class P2RetrievalFoundationTest(unittest.TestCase):
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
        cls._temp_dir = Path(tempfile.mkdtemp(prefix="datahub-p2-retrieval-test-"))
        cls._db_path = cls._temp_dir / "p2-retrieval.db"
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
            "app.knowledge_asset_service",
            "app.knowledge_asset_routes",
            "app.knowledge_index_schemas",
            "app.knowledge_index_repositories",
            "app.knowledge_index_service",
            "app.knowledge_index_routes",
            "app.knowledge_embedding_schemas",
            "app.knowledge_embedding_repositories",
            "app.knowledge_embedding_service",
            "app.knowledge_embedding_routes",
            "app.p2_retrieval_schemas",
            "app.p2_retrieval_repositories",
            "app.p2_retrieval_service",
            "app.p2_retrieval_routes",
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
            for model in (
                self.models.RetrievalLog,
                self.models.P2KnowledgeEmbedding,
                self.models.P2KnowledgeChunk,
                self.models.P2KnowledgeIndexEntry,
                self.models.KnowledgeAsset,
                self.models.AssetReviewSnapshot,
                self.models.ExtractionReview,
                self.models.AssetExtraction,
                self.models.ExtractionJob,
                self.models.Asset,
            ):
                db.query(model).delete()
            self._seed_version(
                db,
                suffix="v1",
                version=1,
                content=(
                    "DH-100 warranty lasts twelve months. Cancellation is allowed "
                    "before shipment. OCR shows recycled aluminum and the caption "
                    "shows a foldable stand. Metadata SKU is DH-100."
                ),
                active=True,
            )
            db.commit()
        finally:
            db.close()

    def _seed_version(
        self,
        db: object,
        *,
        suffix: str,
        version: int,
        content: str,
        active: bool,
    ) -> None:
        asset_id = "asset_p2_m81"
        if version == 1:
            db.add(
                self.models.Asset(
                    id=asset_id,
                    asset_type="image",
                    file_name="dh100.png",
                    mime_type="image/png",
                    size=2048,
                    storage_uri="local://assets/dh100.png",
                    hash="f" * 64,
                    status="uploaded",
                    metadata_json={"sku": "DH-100"},
                )
            )
        job_id = f"job_p2_m81_{suffix}"
        extraction_id = f"extraction_p2_m81_{suffix}"
        review_id = f"review_p2_m81_{suffix}"
        snapshot_id = f"snapshot_p2_m81_{suffix}"
        db.add(
            self.models.ExtractionJob(
                id=job_id,
                asset_id=asset_id,
                extract_type="ocr",
                provider="mock",
                status="success",
                retry_count=0,
            )
        )
        db.add(
            self.models.AssetExtraction(
                id=extraction_id,
                asset_id=asset_id,
                job_id=job_id,
                extract_type="ocr",
                content=f"raw {suffix}",
                metadata_json={"mock_execution": True},
                version=version,
            )
        )
        db.add(
            self.models.ExtractionReview(
                id=review_id,
                asset_id=asset_id,
                extraction_id=extraction_id,
                review_status="approved",
                reviewer="p2_m81_reviewer",
                original_content=f"raw {suffix}",
                revised_content=content,
                version=version,
            )
        )
        db.add(
            self.models.AssetReviewSnapshot(
                id=snapshot_id,
                asset_id=asset_id,
                extraction_id=extraction_id,
                review_id=review_id,
                extract_type="ocr",
                original_content=f"raw {suffix}",
                approved_content=content,
                metadata_json={"immutable": True},
                version=version,
            )
        )
        if active:
            db.add(
                self.models.KnowledgeAsset(
                    id=f"knowledge_asset_p2_m81_{suffix}",
                    source_snapshot_id=snapshot_id,
                    asset_id=asset_id,
                    content=content,
                    content_type="ocr",
                    status="active",
                    version=version,
                    metadata_json={"rag_synced": False},
                )
            )

    def _create_index(self, knowledge_asset_id: str = "knowledge_asset_p2_m81_v1") -> dict[str, object]:
        response = self.client.post(f"/api/knowledge-assets/{knowledge_asset_id}/index")
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()["data"]["index_entry"]

    def _embed(self, entry_id: str) -> dict[str, object]:
        response = self.client.post(f"/api/knowledge-index/{entry_id}/embed")
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["data"]

    def _serve(self, entry_id: str) -> dict[str, object]:
        response = self.client.post(f"/api/knowledge-index/{entry_id}/serve")
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["data"]

    def _search(self, query: str = "What is the DH-100 warranty?"):
        return self.client.post(
            "/api/v2/retrieval/p2/search",
            json={"query": query, "top_k": 5, "debug": True, "request_id": "m81-test"},
        )

    def test_01_embed_stays_ready_then_explicit_serve_enables_retrieval(self) -> None:
        entry = self._create_index()
        embedded = self._embed(str(entry["id"]))
        self.assertEqual(embedded["index_status"], "ready")
        before = self._search()
        self.assertEqual(before.status_code, 200, before.text)
        self.assertEqual(before.json()["data"]["matched_count"], 0)
        self.assertEqual(before.json()["data"]["fallback_reason"], "no_serving_index")

        served = self._serve(str(entry["id"]))
        self.assertTrue(served["activated"])
        self.assertEqual(served["index_status"], "serving")
        after = self._search()
        self.assertEqual(after.status_code, 200, after.text)
        data = after.json()["data"]
        self.assertEqual(data["retrieval_mode"], "p2_vector_retrieval")
        self.assertEqual(data["matched_count"], 1)
        self.assertFalse(data["fallback_used"])
        self.assertEqual(data["results"][0]["knowledge_asset_id"], "knowledge_asset_p2_m81_v1")
        self.assertEqual(data["results"][0]["asset_id"], "asset_p2_m81")
        self.assertNotIn("embedding", data["results"][0])
        self.assertEqual(data["results"][0]["source_trace"]["review_id"], "review_p2_m81_v1")

    def test_02_serve_is_idempotent(self) -> None:
        entry = self._create_index()
        self._embed(str(entry["id"]))
        first = self._serve(str(entry["id"]))
        second = self._serve(str(entry["id"]))
        self.assertTrue(first["activated"])
        self.assertFalse(second["activated"])
        self.assertEqual(second["index_status"], "serving")

    def test_03_pending_building_failed_and_archived_cannot_serve(self) -> None:
        for status, sync_state in (
            ("pending", "pending"),
            ("building", "building"),
            ("failed", "failed"),
            ("archived", "archived"),
        ):
            with self.subTest(status=status):
                entry = self._create_index()
                db = self.database.SessionLocal()
                try:
                    row = db.query(self.models.P2KnowledgeIndexEntry).one()
                    row.status = status
                    row.sync_state = sync_state
                    row.error_message = "safe failure" if status == "failed" else None
                    db.commit()
                finally:
                    db.close()
                response = self.client.post(f"/api/knowledge-index/{entry['id']}/serve")
                self.assertEqual(response.status_code, 409, response.text)
                self.assertEqual(
                    response.json()["detail"]["code"],
                    "KNOWLEDGE_INDEX_NOT_READY_FOR_SERVING",
                )
                self.setUp()

    def test_04_non_active_knowledge_asset_cannot_serve(self) -> None:
        entry = self._create_index()
        self._embed(str(entry["id"]))
        db = self.database.SessionLocal()
        try:
            db.query(self.models.KnowledgeAsset).one().status = "archived"
            db.commit()
        finally:
            db.close()
        response = self.client.post(f"/api/knowledge-index/{entry['id']}/serve")
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(response.json()["detail"]["code"], "KNOWLEDGE_ASSET_NOT_ACTIVE")

    def test_05_missing_chunk_and_missing_embedding_are_rejected(self) -> None:
        entry = self._create_index()
        missing_embedding = self.client.post(f"/api/knowledge-index/{entry['id']}/serve")
        self.assertEqual(missing_embedding.status_code, 409, missing_embedding.text)
        self.assertEqual(
            missing_embedding.json()["detail"]["code"], "KNOWLEDGE_EMBEDDING_MISSING"
        )
        db = self.database.SessionLocal()
        try:
            db.query(self.models.P2KnowledgeChunk).delete()
            db.commit()
        finally:
            db.close()
        missing_chunk = self.client.post(f"/api/knowledge-index/{entry['id']}/serve")
        self.assertEqual(missing_chunk.status_code, 409, missing_chunk.text)
        self.assertEqual(
            missing_chunk.json()["detail"]["code"], "KNOWLEDGE_EMBEDDING_MISSING"
        )

    def test_06_fingerprint_mismatch_cannot_serve_or_retrieve(self) -> None:
        entry = self._create_index()
        self._embed(str(entry["id"]))
        db = self.database.SessionLocal()
        try:
            db.query(self.models.P2KnowledgeEmbedding).one().fingerprint = "bad-fingerprint"
            db.commit()
        finally:
            db.close()
        response = self.client.post(f"/api/knowledge-index/{entry['id']}/serve")
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(
            response.json()["detail"]["code"],
            "KNOWLEDGE_EMBEDDING_FINGERPRINT_MISMATCH",
        )

    def test_07_dimension_and_profile_mismatch_cannot_serve(self) -> None:
        entry = self._create_index()
        self._embed(str(entry["id"]))
        db = self.database.SessionLocal()
        try:
            db.query(self.models.P2KnowledgeEmbedding).one().dimension = 7
            db.commit()
        finally:
            db.close()
        dimension = self.client.post(f"/api/knowledge-index/{entry['id']}/serve")
        self.assertEqual(dimension.status_code, 409, dimension.text)
        self.assertEqual(
            dimension.json()["detail"]["code"], "KNOWLEDGE_EMBEDDING_DIMENSION_MISMATCH"
        )

        db = self.database.SessionLocal()
        try:
            db.query(self.models.P2KnowledgeEmbedding).one().dimension = 16
            db.commit()
        finally:
            db.close()
        os.environ["P2_EMBEDDING_PROFILE"] = "incompatible-profile"
        try:
            profile = self.client.post(f"/api/knowledge-index/{entry['id']}/serve")
        finally:
            os.environ.pop("P2_EMBEDDING_PROFILE", None)
        self.assertEqual(profile.status_code, 409, profile.text)
        self.assertEqual(
            profile.json()["detail"]["code"], "KNOWLEDGE_EMBEDDING_PROFILE_MISMATCH"
        )

    def test_08_incomplete_source_trace_cannot_serve(self) -> None:
        entry = self._create_index()
        self._embed(str(entry["id"]))
        db = self.database.SessionLocal()
        try:
            db.query(self.models.AssetReviewSnapshot).delete()
            db.commit()
        finally:
            db.close()
        response = self.client.post(f"/api/knowledge-index/{entry['id']}/serve")
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(
            response.json()["detail"]["code"], "KNOWLEDGE_EMBEDDING_SOURCE_INVALID"
        )

    def test_09_archived_index_entry_has_zero_recall_with_vector_retained(self) -> None:
        entry = self._create_index()
        self._embed(str(entry["id"]))
        self._serve(str(entry["id"]))
        self.assertEqual(self._search().json()["data"]["matched_count"], 1)
        archived = self.client.post(f"/api/knowledge-index/{entry['id']}/archive")
        self.assertEqual(archived.status_code, 200, archived.text)
        after = self._search()
        self.assertEqual(after.json()["data"]["matched_count"], 0)
        self.assertEqual(after.json()["data"]["fallback_reason"], "no_serving_index")
        db = self.database.SessionLocal()
        try:
            self.assertEqual(db.query(self.models.P2KnowledgeEmbedding).count(), 1)
        finally:
            db.close()

    def test_10_archived_knowledge_asset_has_zero_recall_with_vector_retained(self) -> None:
        entry = self._create_index()
        self._embed(str(entry["id"]))
        self._serve(str(entry["id"]))
        archived = self.client.post(
            "/api/knowledge-assets/knowledge_asset_p2_m81_v1/archive"
        )
        self.assertEqual(archived.status_code, 200, archived.text)
        self.assertEqual(self._search().json()["data"]["matched_count"], 0)
        db = self.database.SessionLocal()
        try:
            self.assertEqual(db.query(self.models.P2KnowledgeEmbedding).count(), 1)
        finally:
            db.close()

    def test_11_replaced_old_version_has_zero_recall(self) -> None:
        old_entry = self._create_index()
        self._embed(str(old_entry["id"]))
        self._serve(str(old_entry["id"]))
        db = self.database.SessionLocal()
        try:
            self._seed_version(
                db,
                suffix="v2",
                version=2,
                content="DH-100 V2 warranty is twenty-four months and cancellation is allowed before packing.",
                active=False,
            )
            db.commit()
        finally:
            db.close()
        published = self.client.post("/api/snapshots/snapshot_p2_m81_v2/publish")
        self.assertEqual(published.status_code, 201, published.text)
        new_asset_id = published.json()["data"]["knowledge_asset"]["id"]
        new_entry = self._create_index(new_asset_id)
        self._embed(str(new_entry["id"]))
        self._serve(str(new_entry["id"]))

        result = self._search("What is the DH-100 V2 warranty?").json()["data"]
        returned_ids = {item["knowledge_asset_id"] for item in result["results"]}
        self.assertIn(new_asset_id, returned_ids)
        self.assertNotIn("knowledge_asset_p2_m81_v1", returned_ids)
        db = self.database.SessionLocal()
        try:
            old = db.query(self.models.P2KnowledgeIndexEntry).filter_by(id=old_entry["id"]).one()
            self.assertEqual(old.status, "archived")
            self.assertEqual(db.query(self.models.P2KnowledgeEmbedding).count(), 2)
        finally:
            db.close()

    def test_12_retrieval_log_is_namespaced_and_contains_no_vector(self) -> None:
        entry = self._create_index()
        self._embed(str(entry["id"]))
        self._serve(str(entry["id"]))
        response = self._search()
        self.assertEqual(response.status_code, 200, response.text)
        db = self.database.SessionLocal()
        try:
            log = db.query(self.models.RetrievalLog).one()
            metadata = log.metadata_json
            self.assertTrue(log.id.startswith("p2_retrieval_"))
            self.assertEqual(metadata["log_namespace"], "p2_retrieval_v1")
            self.assertEqual(metadata["retrieval_mode"], "p2_vector_retrieval")
            self.assertEqual(metadata["request_id"], "m81-test")
            self.assertEqual(metadata["embedding_dimension"], 16)
            serialized = json.dumps(metadata)
            self.assertNotIn("DATABASE_URL", serialized)
            self.assertNotIn("API_KEY", serialized)
            self.assertNotIn('"embedding":', serialized)
        finally:
            db.close()

    def test_13_query_provider_failure_is_safe_and_never_falls_back_to_p1(self) -> None:
        from app.embedding import MockEmbeddingProvider
        from app.p2_retrieval_schemas import P2RetrievalRequest
        from app.p2_retrieval_service import P2RetrievalFailure, P2RetrievalService

        class FailingProvider(MockEmbeddingProvider):
            def embed(self, text: str) -> list[float]:
                raise RuntimeError("secret-upstream-detail")

        entry = self._create_index()
        self._embed(str(entry["id"]))
        self._serve(str(entry["id"]))
        db = self.database.SessionLocal()
        try:
            with self.assertRaises(P2RetrievalFailure) as caught:
                P2RetrievalService(db, provider=FailingProvider(dimension=16)).search(
                    P2RetrievalRequest(query="warranty")
                )
            self.assertEqual(caught.exception.reason, "embedding_generation_failed")
            self.assertFalse(caught.exception.response.fallback_used)
            self.assertNotIn("secret", caught.exception.response.error_message or "")
        finally:
            db.close()

    def test_14_pgvector_unavailable_is_distinct_and_safe(self) -> None:
        entry = self._create_index()
        self._embed(str(entry["id"]))
        self._serve(str(entry["id"]))
        with patch("app.p2_retrieval_repositories._is_postgresql", return_value=True), patch(
            "app.p2_retrieval_repositories._HAS_PGVECTOR", False
        ):
            response = self._search()
        self.assertEqual(response.status_code, 503, response.text)
        data = response.json()["data"]
        self.assertEqual(data["fallback_reason"], "pgvector_unavailable")
        self.assertFalse(data["fallback_used"])
        self.assertEqual(data["retrieval_mode"], "p2_vector_retrieval")

    def test_15_stale_source_or_fingerprint_is_rejected_before_return(self) -> None:
        entry = self._create_index()
        self._embed(str(entry["id"]))
        self._serve(str(entry["id"]))
        db = self.database.SessionLocal()
        try:
            row = db.query(self.models.P2KnowledgeEmbedding).one()
            metadata = dict(row.metadata_json)
            metadata["index_fingerprint"] = "stale-index"
            row.metadata_json = metadata
            db.commit()
        finally:
            db.close()
        response = self._search()
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(
            response.json()["data"]["fallback_reason"],
            "fingerprint_mismatch",
        )

    def test_16_incomplete_source_trace_has_zero_recall(self) -> None:
        entry = self._create_index()
        self._embed(str(entry["id"]))
        self._serve(str(entry["id"]))
        db = self.database.SessionLocal()
        try:
            db.query(self.models.AssetReviewSnapshot).delete()
            db.commit()
        finally:
            db.close()
        response = self._search()
        self.assertEqual(response.status_code, 409, response.text)
        data = response.json()["data"]
        self.assertEqual(data["matched_count"], 0)
        self.assertEqual(data["fallback_reason"], "source_trace_invalid")
        self.assertFalse(data["fallback_used"])
        self.assertEqual(data["request_id"], "m81-test")
        self.assertTrue(data["retrieval_id"].startswith("p2_retrieval_"))

    def test_17_profile_and_dimension_mismatch_are_stable_retrieval_errors(self) -> None:
        entry = self._create_index()
        self._embed(str(entry["id"]))
        self._serve(str(entry["id"]))
        db = self.database.SessionLocal()
        try:
            row = db.query(self.models.P2KnowledgeEmbedding).one()
            row.dimension = 7
            db.commit()
        finally:
            db.close()
        dimension = self._search()
        self.assertEqual(dimension.status_code, 409, dimension.text)
        self.assertEqual(
            dimension.json()["data"]["fallback_reason"],
            "embedding_dimension_mismatch",
        )

        db = self.database.SessionLocal()
        try:
            db.query(self.models.P2KnowledgeEmbedding).one().dimension = 16
            db.commit()
        finally:
            db.close()
        os.environ["P2_EMBEDDING_PROFILE"] = "p2-incompatible-profile"
        try:
            profile = self._search()
        finally:
            os.environ.pop("P2_EMBEDDING_PROFILE", None)
        self.assertEqual(profile.status_code, 409, profile.text)
        self.assertEqual(
            profile.json()["data"]["fallback_reason"],
            "embedding_profile_mismatch",
        )

    def test_18_pgvector_query_error_and_no_hits_are_distinct(self) -> None:
        from app.p2_retrieval_repositories import P2PgvectorQueryError

        entry = self._create_index()
        self._embed(str(entry["id"]))
        self._serve(str(entry["id"]))
        with patch(
            "app.p2_retrieval_service.search_serving_embeddings",
            side_effect=P2PgvectorQueryError("private database detail"),
        ):
            query_error = self._search()
        self.assertEqual(query_error.status_code, 502, query_error.text)
        query_data = query_error.json()["data"]
        self.assertEqual(query_data["fallback_reason"], "pgvector_query_error")
        self.assertNotIn("private", query_data["error_message"])

        with patch(
            "app.p2_retrieval_service.search_serving_embeddings", return_value=[]
        ):
            no_hits = self._search("an intentionally unmatched question")
        self.assertEqual(no_hits.status_code, 200, no_hits.text)
        no_hit_data = no_hits.json()["data"]
        self.assertEqual(no_hit_data["fallback_reason"], "no_hits")
        self.assertEqual(no_hit_data["results"], [])
        self.assertFalse(no_hit_data["fallback_used"])

    def test_19_p2_retrieval_never_calls_p1_or_customerops(self) -> None:
        entry = self._create_index()
        self._embed(str(entry["id"]))
        self._serve(str(entry["id"]))
        with patch(
            "app.db_repositories.search_rag_embeddings_semantic",
            side_effect=AssertionError("P1 rag_embeddings must not be queried"),
        ) as p1_search, patch(
            "app.main.run_customerops_retrieval",
            side_effect=AssertionError("CustomerOpsAgent must not be called"),
        ) as customerops:
            response = self._search()
        self.assertEqual(response.status_code, 200, response.text)
        p1_search.assert_not_called()
        customerops.assert_not_called()
        import app.main as main_module

        routes = {route.path for route in main_module.app.routes}
        # M8.2 adds an independent versioned coordinator, but invoking the
        # P2-only endpoint above must still never fan out to P1 or CustomerOps.
        self.assertIn("/api/v2/retrieval/search", routes)

    def test_20_sqlite_retrieval_is_deterministic_and_network_free(self) -> None:
        from app.db_models import _is_postgresql

        self.assertFalse(_is_postgresql())
        entry = self._create_index()
        self._embed(str(entry["id"]))
        self._serve(str(entry["id"]))
        first = self._search().json()["data"]["results"]
        second = self._search().json()["data"]["results"]
        self.assertEqual(first[0]["knowledge_asset_id"], second[0]["knowledge_asset_id"])
        self.assertEqual(first[0]["score"], second[0]["score"])


if __name__ == "__main__":
    unittest.main()

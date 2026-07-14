"""P2-M6 tests for index lifecycle and deterministic text projection."""

import hashlib
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


class KnowledgeIndexFoundationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._saved_database_url = os.environ.get("DATABASE_URL")
        cls._temp_dir = Path(tempfile.mkdtemp(prefix="datahub-knowledge-index-test-"))
        cls._db_path = cls._temp_dir / "knowledge-index.db"
        os.environ["DATABASE_URL"] = f"sqlite:///{cls._db_path}"
        cls._reload_application()

        import app.database as database_module
        import app.db_models as models_module
        import app.knowledge_index_repositories as index_repositories_module
        import app.main as main_module

        database_module.init_database_tables()
        importlib.reload(main_module)
        cls.database = database_module
        cls.models = models_module
        cls.index_repositories = index_repositories_module
        cls.client = TestClient(main_module.app)

    @classmethod
    def _reload_application(cls) -> None:
        import app.database as database_module
        import app.db_models as models_module
        import app.db_repositories as p1_repositories_module
        import app.storage as p1_storage_module
        import app.asset_repositories as asset_repositories_module
        import app.extraction_repositories as extraction_repositories_module
        import app.review_repositories as review_repositories_module
        import app.knowledge_asset_repositories as knowledge_repositories_module
        import app.knowledge_index_repositories as index_repositories_module
        import app.knowledge_index_service as index_service_module
        import app.knowledge_index_routes as index_routes_module

        for module in (
            database_module,
            models_module,
            p1_repositories_module,
            p1_storage_module,
            asset_repositories_module,
            extraction_repositories_module,
            review_repositories_module,
            knowledge_repositories_module,
            index_repositories_module,
            index_service_module,
            index_routes_module,
        ):
            importlib.reload(module)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.database.engine.dispose()
        if cls._saved_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = cls._saved_database_url
        cls._reload_application()
        import app.main as main_module

        importlib.reload(main_module)
        shutil.rmtree(cls._temp_dir, ignore_errors=True)

    def setUp(self) -> None:
        db = self.database.SessionLocal()
        try:
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
                    id="asset_index_fixture",
                    asset_type="image",
                    file_name="index-fixture.png",
                    mime_type="image/png",
                    size=768,
                    storage_uri="local://assets/index-fixture.png",
                    hash="d" * 64,
                    status="uploaded",
                    metadata_json={"sku": "SKU-P2-M6"},
                )
            )
            db.add(
                self.models.ExtractionJob(
                    id="extract_job_index_fixture",
                    asset_id="asset_index_fixture",
                    extract_type="ocr",
                    provider="mock",
                    status="success",
                    retry_count=0,
                )
            )
            db.add(
                self.models.AssetExtraction(
                    id="extraction_index_fixture",
                    asset_id="asset_index_fixture",
                    job_id="extract_job_index_fixture",
                    extract_type="ocr",
                    content="machine projection source",
                    metadata_json={"mock_execution": True},
                    version=1,
                )
            )
            for version in (1, 2):
                db.add(
                    self.models.ExtractionReview(
                        id=f"review_index_fixture_v{version}",
                        asset_id="asset_index_fixture",
                        extraction_id="extraction_index_fixture",
                        review_status="approved",
                        reviewer="p2_m6_reviewer",
                        original_content="machine projection source",
                        revised_content=f"approved index content v{version}",
                        version=version,
                    )
                )
                db.add(
                    self.models.AssetReviewSnapshot(
                        id=f"snapshot_index_fixture_v{version}",
                        asset_id="asset_index_fixture",
                        extraction_id="extraction_index_fixture",
                        review_id=f"review_index_fixture_v{version}",
                        extract_type="ocr",
                        original_content="machine projection source",
                        approved_content=f"approved index content v{version}",
                        metadata_json={"immutable": True},
                        version=version,
                    )
                )
            db.add(
                self.models.KnowledgeAsset(
                    id="knowledge_asset_archived_fixture",
                    source_snapshot_id="snapshot_index_fixture_v1",
                    asset_id="asset_index_fixture",
                    content="approved index content v1",
                    content_type="ocr",
                    status="archived",
                    version=1,
                    metadata_json={"rag_synced": False},
                )
            )
            db.add(
                self.models.KnowledgeAsset(
                    id="knowledge_asset_active_fixture",
                    source_snapshot_id="snapshot_index_fixture_v2",
                    asset_id="asset_index_fixture",
                    content="approved index content v2",
                    content_type="ocr",
                    status="active",
                    version=2,
                    metadata_json={"rag_synced": False},
                )
            )
            db.commit()
        finally:
            db.close()

    def _create_index(self, knowledge_asset_id: str = "knowledge_asset_active_fixture"):
        return self.client.post(f"/api/knowledge-assets/{knowledge_asset_id}/index")

    def test_01_active_knowledge_asset_can_create_ready_index(self) -> None:
        response = self._create_index()
        self.assertEqual(response.status_code, 201, response.text)
        result = response.json()["data"]
        self.assertTrue(result["created"])
        entry = result["index_entry"]
        self.assertEqual(entry["status"], "ready")
        self.assertEqual(entry["sync_state"], "ready")
        self.assertEqual(entry["generation"], 2)
        self.assertEqual(len(entry["chunks"]), 1)

    def test_02_archived_knowledge_asset_cannot_create_index(self) -> None:
        response = self._create_index("knowledge_asset_archived_fixture")
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(response.json()["detail"]["code"], "KNOWLEDGE_ASSET_NOT_ACTIVE")
        db = self.database.SessionLocal()
        try:
            self.assertEqual(db.query(self.models.P2KnowledgeIndexEntry).count(), 0)
        finally:
            db.close()

    def test_03_chunk_projection_is_immutable_and_non_vector(self) -> None:
        entry = self._create_index().json()["data"]["index_entry"]
        chunk = entry["chunks"][0]
        self.assertEqual(chunk["chunk_order"], 0)
        self.assertEqual(chunk["chunk_text"], "Content type: ocr\napproved index content v2")
        self.assertEqual(
            chunk["chunk_hash"],
            hashlib.sha256(chunk["chunk_text"].encode("utf-8")).hexdigest(),
        )
        self.assertFalse(chunk["metadata_json"]["embedding_created"])
        self.assertFalse(chunk["metadata_json"]["vector_indexed"])
        self.assertEqual(chunk["metadata_json"]["projection_version"], "p2_text_projection_v1")

    def test_04_fingerprint_is_stable_and_content_addressed(self) -> None:
        entry = self._create_index().json()["data"]["index_entry"]
        payload = {
            "asset_id": "asset_index_fixture",
            "chunker_version": "single_chunk_v1",
            "content": "approved index content v2",
            "content_type": "ocr",
            "knowledge_asset_id": "knowledge_asset_active_fixture",
            "knowledge_asset_version": 2,
            "projection_version": "p2_text_projection_v1",
        }
        expected = hashlib.sha256(
            json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        self.assertEqual(entry["fingerprint"], expected)

    def test_05_duplicate_index_request_is_idempotent(self) -> None:
        first = self._create_index()
        second = self._create_index()
        self.assertEqual(first.status_code, 201, first.text)
        self.assertEqual(second.status_code, 200, second.text)
        first_data = first.json()["data"]
        second_data = second.json()["data"]
        self.assertFalse(second_data["created"])
        self.assertEqual(first_data["index_entry"]["id"], second_data["index_entry"]["id"])
        db = self.database.SessionLocal()
        try:
            self.assertEqual(db.query(self.models.P2KnowledgeIndexEntry).count(), 1)
            self.assertEqual(db.query(self.models.P2KnowledgeChunk).count(), 1)
        finally:
            db.close()

    def test_06_archive_immediately_stops_serving_and_preserves_chunk(self) -> None:
        entry = self._create_index().json()["data"]["index_entry"]
        db = self.database.SessionLocal()
        try:
            self.index_repositories.transition_index_entry(db, entry["id"], "serving")
        finally:
            db.close()
        asset_archive = self.client.post(
            "/api/knowledge-assets/knowledge_asset_active_fixture/archive"
        )
        self.assertEqual(asset_archive.status_code, 200, asset_archive.text)
        archived = self.client.get(f"/api/knowledge-index/{entry['id']}")
        repeated = self.client.post(f"/api/knowledge-index/{entry['id']}/archive")
        self.assertEqual(archived.status_code, 200, archived.text)
        self.assertEqual(repeated.status_code, 200, repeated.text)
        record = archived.json()["data"]
        self.assertEqual(record["status"], "archived")
        self.assertEqual(record["sync_state"], "archived")
        self.assertEqual(len(record["chunks"]), 1)

    def test_07_list_and_detail_keep_complete_source_trace(self) -> None:
        entry = self._create_index().json()["data"]["index_entry"]
        detail = self.client.get(f"/api/knowledge-index/{entry['id']}")
        listing = self.client.get(
            "/api/knowledge-index?page=1&page_size=10&asset_id=asset_index_fixture"
        )
        self.assertEqual(detail.status_code, 200, detail.text)
        self.assertEqual(listing.status_code, 200, listing.text)
        trace = detail.json()["data"]["source_trace"]
        self.assertEqual(trace["index_entry_id"], entry["id"])
        self.assertEqual(trace["knowledge_asset_id"], "knowledge_asset_active_fixture")
        self.assertEqual(trace["snapshot_id"], "snapshot_index_fixture_v2")
        self.assertEqual(trace["review_id"], "review_index_fixture_v2")
        self.assertEqual(trace["review_status"], "approved")
        self.assertEqual(trace["extraction_id"], "extraction_index_fixture")
        self.assertEqual(trace["extraction_job_id"], "extract_job_index_fixture")
        self.assertEqual(trace["asset_id"], "asset_index_fixture")
        listed = listing.json()["data"]
        self.assertEqual(listed["pagination"]["total"], 1)
        self.assertEqual(listed["index_entries"][0]["source_trace"], trace)

    def test_08_new_knowledge_version_archives_superseded_index(self) -> None:
        entry = self._create_index().json()["data"]["index_entry"]
        db = self.database.SessionLocal()
        try:
            db.add(
                self.models.ExtractionReview(
                    id="review_index_fixture_v3",
                    asset_id="asset_index_fixture",
                    extraction_id="extraction_index_fixture",
                    review_status="approved",
                    reviewer="p2_m6_reviewer",
                    original_content="machine projection source",
                    revised_content="approved index content v3",
                    version=3,
                )
            )
            db.add(
                self.models.AssetReviewSnapshot(
                    id="snapshot_index_fixture_v3",
                    asset_id="asset_index_fixture",
                    extraction_id="extraction_index_fixture",
                    review_id="review_index_fixture_v3",
                    extract_type="ocr",
                    original_content="machine projection source",
                    approved_content="approved index content v3",
                    metadata_json={"immutable": True},
                    version=3,
                )
            )
            db.commit()
        finally:
            db.close()

        published = self.client.post("/api/snapshots/snapshot_index_fixture_v3/publish")
        self.assertEqual(published.status_code, 201, published.text)
        detail = self.client.get(f"/api/knowledge-index/{entry['id']}")
        self.assertEqual(detail.status_code, 200, detail.text)
        self.assertEqual(detail.json()["data"]["status"], "archived")


if __name__ == "__main__":
    unittest.main()

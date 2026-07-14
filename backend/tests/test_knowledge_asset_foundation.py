"""P2-M4 tests for governed, traceable, and versioned Knowledge Assets."""

import importlib
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


class KnowledgeAssetFoundationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._saved_database_url = os.environ.get("DATABASE_URL")
        cls._temp_dir = Path(tempfile.mkdtemp(prefix="datahub-knowledge-asset-test-"))
        cls._db_path = cls._temp_dir / "knowledge-assets.db"
        os.environ["DATABASE_URL"] = f"sqlite:///{cls._db_path}"

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
        import app.database as database_module
        import app.db_models as models_module
        import app.db_repositories as p1_repositories_module
        import app.storage as p1_storage_module
        import app.asset_repositories as asset_repositories_module
        import app.extraction_repositories as extraction_repositories_module
        import app.review_repositories as review_repositories_module
        import app.review_service as review_service_module
        import app.review_routes as review_routes_module
        import app.knowledge_asset_repositories as knowledge_repositories_module
        import app.knowledge_asset_service as knowledge_service_module
        import app.knowledge_asset_routes as knowledge_routes_module

        for module in (
            database_module,
            models_module,
            p1_repositories_module,
            p1_storage_module,
            asset_repositories_module,
            extraction_repositories_module,
            review_repositories_module,
            review_service_module,
            review_routes_module,
            knowledge_repositories_module,
            knowledge_service_module,
            knowledge_routes_module,
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
            db.query(self.models.KnowledgeAsset).delete()
            db.query(self.models.AssetReviewSnapshot).delete()
            db.query(self.models.ExtractionReview).delete()
            db.query(self.models.AssetExtraction).delete()
            db.query(self.models.ExtractionJob).delete()
            db.query(self.models.Asset).delete()
            db.add(
                self.models.Asset(
                    id="asset_knowledge_fixture",
                    asset_type="image",
                    file_name="knowledge-fixture.png",
                    mime_type="image/png",
                    size=512,
                    storage_uri="local://assets/knowledge-fixture.png",
                    hash="c" * 64,
                    status="uploaded",
                    metadata_json={"sku": "SKU-P2-M4"},
                )
            )
            db.add(
                self.models.ExtractionJob(
                    id="extract_job_knowledge_fixture",
                    asset_id="asset_knowledge_fixture",
                    extract_type="ocr",
                    provider="mock",
                    status="success",
                    retry_count=0,
                )
            )
            db.add(
                self.models.AssetExtraction(
                    id="extraction_knowledge_fixture",
                    asset_id="asset_knowledge_fixture",
                    job_id="extract_job_knowledge_fixture",
                    extract_type="ocr",
                    content="machine result",
                    metadata_json={"mock_execution": True},
                    version=1,
                )
            )
            db.add(
                self.models.ExtractionReview(
                    id="review_approved_fixture",
                    asset_id="asset_knowledge_fixture",
                    extraction_id="extraction_knowledge_fixture",
                    review_status="approved",
                    reviewer="p2_m4_reviewer",
                    original_content="machine result",
                    revised_content="human governed content v1",
                    version=1,
                )
            )
            db.add(
                self.models.AssetReviewSnapshot(
                    id="snapshot_approved_fixture",
                    asset_id="asset_knowledge_fixture",
                    extraction_id="extraction_knowledge_fixture",
                    review_id="review_approved_fixture",
                    extract_type="ocr",
                    original_content="machine result",
                    approved_content="human governed content v1",
                    metadata_json={"immutable": True},
                    version=1,
                )
            )
            db.commit()
        finally:
            db.close()

    def _publish(self, snapshot_id: str = "snapshot_approved_fixture"):
        return self.client.post(f"/api/snapshots/{snapshot_id}/publish")

    def test_01_approved_snapshot_publishes_active_asset(self) -> None:
        response = self._publish()
        self.assertEqual(response.status_code, 201, response.text)
        result = response.json()["data"]
        self.assertTrue(result["created"])
        knowledge = result["knowledge_asset"]
        self.assertEqual(knowledge["status"], "active")
        self.assertEqual(knowledge["version"], 1)
        self.assertEqual(knowledge["content"], "human governed content v1")
        self.assertEqual(knowledge["content_type"], "ocr")
        self.assertFalse(knowledge["metadata_json"]["rag_synced"])

    def test_02_nonapproved_review_cannot_publish_snapshot(self) -> None:
        db = self.database.SessionLocal()
        try:
            review = db.query(self.models.ExtractionReview).one()
            review.review_status = "rejected"
            db.commit()
        finally:
            db.close()

        response = self._publish()
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(response.json()["detail"]["code"], "SNAPSHOT_NOT_APPROVED")
        db = self.database.SessionLocal()
        try:
            self.assertEqual(db.query(self.models.KnowledgeAsset).count(), 0)
        finally:
            db.close()

    def test_03_publish_is_idempotent_per_snapshot(self) -> None:
        first = self._publish()
        second = self._publish()
        self.assertEqual(first.status_code, 201, first.text)
        self.assertEqual(second.status_code, 200, second.text)
        first_data = first.json()["data"]
        second_data = second.json()["data"]
        self.assertTrue(first_data["created"])
        self.assertFalse(second_data["created"])
        self.assertEqual(
            first_data["knowledge_asset"]["id"],
            second_data["knowledge_asset"]["id"],
        )
        db = self.database.SessionLocal()
        try:
            self.assertEqual(db.query(self.models.KnowledgeAsset).count(), 1)
        finally:
            db.close()

    def test_04_archive_is_idempotent_and_preserves_content(self) -> None:
        knowledge = self._publish().json()["data"]["knowledge_asset"]
        first = self.client.post(f"/api/knowledge-assets/{knowledge['id']}/archive")
        second = self.client.post(f"/api/knowledge-assets/{knowledge['id']}/archive")
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(second.status_code, 200, second.text)
        self.assertEqual(first.json()["data"]["status"], "archived")
        self.assertEqual(second.json()["data"]["content"], knowledge["content"])

    def test_05_detail_and_list_return_complete_source_trace(self) -> None:
        knowledge = self._publish().json()["data"]["knowledge_asset"]
        detail = self.client.get(f"/api/knowledge-assets/{knowledge['id']}")
        listing = self.client.get(
            "/api/knowledge-assets?page=1&page_size=10&asset_id=asset_knowledge_fixture"
        )
        self.assertEqual(detail.status_code, 200, detail.text)
        self.assertEqual(listing.status_code, 200, listing.text)
        trace = detail.json()["data"]["source_trace"]
        self.assertEqual(trace["snapshot_id"], "snapshot_approved_fixture")
        self.assertEqual(trace["review_id"], "review_approved_fixture")
        self.assertEqual(trace["review_status"], "approved")
        self.assertEqual(trace["extraction_id"], "extraction_knowledge_fixture")
        self.assertEqual(trace["extraction_job_id"], "extract_job_knowledge_fixture")
        self.assertEqual(trace["asset_id"], "asset_knowledge_fixture")
        self.assertEqual(trace["asset_file_name"], "knowledge-fixture.png")
        listed = listing.json()["data"]
        self.assertEqual(listed["pagination"]["total"], 1)
        self.assertEqual(listed["knowledge_assets"][0]["source_trace"], trace)

    def test_06_new_snapshot_creates_version_without_overwrite(self) -> None:
        first = self._publish().json()["data"]["knowledge_asset"]
        db = self.database.SessionLocal()
        try:
            db.add(
                self.models.ExtractionReview(
                    id="review_approved_fixture_v2",
                    asset_id="asset_knowledge_fixture",
                    extraction_id="extraction_knowledge_fixture",
                    review_status="approved",
                    reviewer="p2_m4_reviewer",
                    original_content="machine result",
                    revised_content="human governed content v2",
                    version=2,
                )
            )
            db.add(
                self.models.AssetReviewSnapshot(
                    id="snapshot_approved_fixture_v2",
                    asset_id="asset_knowledge_fixture",
                    extraction_id="extraction_knowledge_fixture",
                    review_id="review_approved_fixture_v2",
                    extract_type="ocr",
                    original_content="machine result",
                    approved_content="human governed content v2",
                    metadata_json={"immutable": True},
                    version=2,
                )
            )
            db.commit()
        finally:
            db.close()

        second_response = self._publish("snapshot_approved_fixture_v2")
        self.assertEqual(second_response.status_code, 201, second_response.text)
        second = second_response.json()["data"]["knowledge_asset"]
        self.assertEqual(second["version"], 2)
        self.assertEqual(second["status"], "active")
        first_after = self.client.get(f"/api/knowledge-assets/{first['id']}").json()["data"]
        self.assertEqual(first_after["status"], "archived")
        self.assertEqual(first_after["content"], "human governed content v1")
        self.assertEqual(second["content"], "human governed content v2")


if __name__ == "__main__":
    unittest.main()

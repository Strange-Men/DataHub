"""P2-M3 tests for human decisions and immutable approved snapshots."""

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


class HumanReviewFoundationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._saved_database_url = os.environ.get("DATABASE_URL")
        cls._temp_dir = Path(tempfile.mkdtemp(prefix="datahub-review-test-"))
        cls._db_path = cls._temp_dir / "review.db"
        os.environ["DATABASE_URL"] = f"sqlite:///{cls._db_path}"

        import app.database as database_module
        import app.db_models as models_module
        import app.db_repositories as p1_repositories_module
        import app.storage as p1_storage_module
        import app.asset_repositories as asset_repositories_module
        import app.extraction_repositories as extraction_repositories_module
        import app.review_repositories as review_repositories_module
        import app.review_service as review_service_module
        import app.review_routes as review_routes_module
        import app.main as main_module

        importlib.reload(database_module)
        importlib.reload(models_module)
        importlib.reload(p1_repositories_module)
        importlib.reload(p1_storage_module)
        importlib.reload(asset_repositories_module)
        importlib.reload(extraction_repositories_module)
        importlib.reload(review_repositories_module)
        importlib.reload(review_service_module)
        importlib.reload(review_routes_module)
        database_module.init_database_tables()
        importlib.reload(main_module)

        cls.database = database_module
        cls.models = models_module
        cls.client = TestClient(main_module.app)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.database.engine.dispose()
        if cls._saved_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = cls._saved_database_url

        import app.database as database_module
        import app.db_models as models_module
        import app.db_repositories as p1_repositories_module
        import app.storage as p1_storage_module
        import app.asset_repositories as asset_repositories_module
        import app.extraction_repositories as extraction_repositories_module
        import app.review_repositories as review_repositories_module
        import app.review_service as review_service_module
        import app.review_routes as review_routes_module
        import app.main as main_module

        importlib.reload(database_module)
        importlib.reload(models_module)
        importlib.reload(p1_repositories_module)
        importlib.reload(p1_storage_module)
        importlib.reload(asset_repositories_module)
        importlib.reload(extraction_repositories_module)
        importlib.reload(review_repositories_module)
        importlib.reload(review_service_module)
        importlib.reload(review_routes_module)
        importlib.reload(main_module)
        shutil.rmtree(cls._temp_dir, ignore_errors=True)

    def setUp(self) -> None:
        db = self.database.SessionLocal()
        try:
            db.query(self.models.AssetReviewSnapshot).delete()
            db.query(self.models.ExtractionReview).delete()
            db.query(self.models.AssetExtraction).delete()
            db.query(self.models.ExtractionJob).delete()
            db.query(self.models.Asset).delete()
            db.add(
                self.models.Asset(
                    id="asset_review_fixture",
                    asset_type="image",
                    file_name="review-fixture.png",
                    mime_type="image/png",
                    size=256,
                    storage_uri="local://assets/review-fixture.png",
                    hash="b" * 64,
                    status="uploaded",
                    metadata_json={},
                )
            )
            db.add(
                self.models.ExtractionJob(
                    id="asset_extract_job_review_fixture",
                    asset_id="asset_review_fixture",
                    extract_type="ocr",
                    provider="mock",
                    status="success",
                    retry_count=0,
                )
            )
            db.add(
                self.models.AssetExtraction(
                    id="asset_extract_review_fixture",
                    asset_id="asset_review_fixture",
                    job_id="asset_extract_job_review_fixture",
                    extract_type="ocr",
                    content="original machine extraction",
                    metadata_json={"mock_execution": True},
                    version=1,
                )
            )
            db.commit()
        finally:
            db.close()

    def _create_review(self):
        return self.client.post(
            "/api/assets/asset_review_fixture/reviews",
            json={"extraction_id": "asset_extract_review_fixture"},
        )

    def _submit(self, review_id: str, status: str, revised: str | None = None):
        return self.client.patch(
            f"/api/reviews/{review_id}",
            json={
                "review_status": status,
                "reviewer": "p2_m3_reviewer",
                "review_comment": f"Decision: {status}",
                "revised_content": revised,
            },
        )

    def _snapshots(self):
        return self.client.get("/api/assets/asset_review_fixture/snapshots")

    def test_01_create_review_is_pending_and_preserves_original(self) -> None:
        created = self._create_review()
        self.assertEqual(created.status_code, 201, created.text)
        review = created.json()["data"]
        self.assertTrue(review["id"].startswith("extraction_review_"))
        self.assertEqual(review["review_status"], "pending")
        self.assertEqual(review["original_content"], "original machine extraction")
        self.assertIsNone(review["revised_content"])
        self.assertEqual(review["version"], 1)

        lookup = self.client.get(f"/api/reviews/{review['id']}")
        self.assertEqual(lookup.status_code, 200, lookup.text)
        self.assertEqual(lookup.json()["data"], review)

        duplicate = self._create_review()
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(
            duplicate.json()["detail"]["details"]["existing_review_id"],
            review["id"],
        )

    def test_02_approve_creates_snapshot_without_mutating_extraction(self) -> None:
        review_id = self._create_review().json()["data"]["id"]
        before_db = self.database.SessionLocal()
        try:
            before_content = (
                before_db.query(self.models.AssetExtraction)
                .filter(self.models.AssetExtraction.id == "asset_extract_review_fixture")
                .one()
                .content
            )
        finally:
            before_db.close()

        approved = self._submit(review_id, "approved", "human approved content")
        self.assertEqual(approved.status_code, 200, approved.text)
        data = approved.json()["data"]
        self.assertEqual(data["review"]["review_status"], "approved")
        self.assertEqual(data["review"]["revised_content"], "human approved content")
        self.assertEqual(data["snapshot"]["approved_content"], "human approved content")
        self.assertEqual(data["snapshot"]["original_content"], before_content)
        self.assertTrue(data["snapshot"]["metadata_json"]["immutable"])

        after_db = self.database.SessionLocal()
        try:
            after_content = (
                after_db.query(self.models.AssetExtraction)
                .filter(self.models.AssetExtraction.id == "asset_extract_review_fixture")
                .one()
                .content
            )
        finally:
            after_db.close()
        self.assertEqual(after_content, before_content)
        self.assertEqual(len(self._snapshots().json()["data"]["snapshots"]), 1)

    def test_03_reject_creates_no_snapshot(self) -> None:
        review_id = self._create_review().json()["data"]["id"]
        rejected = self._submit(review_id, "rejected")

        self.assertEqual(rejected.status_code, 200, rejected.text)
        data = rejected.json()["data"]
        self.assertEqual(data["review"]["review_status"], "rejected")
        self.assertIsNone(data["snapshot"])
        self.assertEqual(self._snapshots().json()["data"]["snapshots"], [])

    def test_04_needs_revision_allows_next_review_version(self) -> None:
        first_id = self._create_review().json()["data"]["id"]
        revision = self._submit(first_id, "needs_revision", "suggested correction")

        self.assertEqual(revision.status_code, 200, revision.text)
        data = revision.json()["data"]
        self.assertEqual(data["review"]["review_status"], "needs_revision")
        self.assertEqual(data["review"]["revised_content"], "suggested correction")
        self.assertIsNone(data["snapshot"])

        second = self._create_review()
        self.assertEqual(second.status_code, 201, second.text)
        self.assertEqual(second.json()["data"]["version"], 2)

    def test_05_terminal_review_rejects_illegal_transition(self) -> None:
        review_id = self._create_review().json()["data"]["id"]
        first = self._submit(review_id, "approved", "locked approved content")
        snapshot_id = first.json()["data"]["snapshot"]["id"]

        illegal = self._submit(review_id, "rejected")
        self.assertEqual(illegal.status_code, 409, illegal.text)
        detail = illegal.json()["detail"]
        self.assertEqual(detail["code"], "INVALID_REVIEW_TRANSITION")
        self.assertEqual(detail["details"]["current_status"], "approved")

        snapshots = self._snapshots().json()["data"]["snapshots"]
        self.assertEqual(len(snapshots), 1)
        self.assertEqual(snapshots[0]["id"], snapshot_id)
        self.assertEqual(snapshots[0]["approved_content"], "locked approved content")

    def test_06_new_approval_versions_snapshots_without_overwrite(self) -> None:
        first_id = self._create_review().json()["data"]["id"]
        first = self._submit(first_id, "approved", "approved snapshot version one")
        first_snapshot = first.json()["data"]["snapshot"]

        second_review = self._create_review().json()["data"]
        second = self._submit(
            second_review["id"],
            "approved",
            "approved snapshot version two",
        )
        second_snapshot = second.json()["data"]["snapshot"]

        self.assertEqual(first_snapshot["version"], 1)
        self.assertEqual(second_snapshot["version"], 2)
        snapshots = self._snapshots().json()["data"]["snapshots"]
        by_id = {snapshot["id"]: snapshot for snapshot in snapshots}
        self.assertEqual(
            by_id[first_snapshot["id"]]["approved_content"],
            "approved snapshot version one",
        )
        self.assertEqual(
            by_id[second_snapshot["id"]]["approved_content"],
            "approved snapshot version two",
        )


if __name__ == "__main__":
    unittest.main()

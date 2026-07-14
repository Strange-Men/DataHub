"""P2-M2 Extraction Foundation tests; no real AI provider is invoked."""

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


class ExtractionFoundationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._saved_database_url = os.environ.get("DATABASE_URL")
        cls._temp_dir = Path(tempfile.mkdtemp(prefix="datahub-extraction-test-"))
        cls._db_path = cls._temp_dir / "extraction.db"
        os.environ["DATABASE_URL"] = f"sqlite:///{cls._db_path}"

        import app.database as database_module
        import app.db_models as models_module
        import app.db_repositories as p1_repositories_module
        import app.storage as p1_storage_module
        import app.asset_repositories as asset_repositories_module
        import app.extraction_repositories as extraction_repositories_module
        import app.extraction_providers as providers_module
        import app.extraction_service as service_module
        import app.extraction_routes as routes_module
        import app.main as main_module

        importlib.reload(database_module)
        importlib.reload(models_module)
        importlib.reload(p1_repositories_module)
        importlib.reload(p1_storage_module)
        importlib.reload(asset_repositories_module)
        importlib.reload(extraction_repositories_module)
        importlib.reload(providers_module)
        importlib.reload(service_module)
        importlib.reload(routes_module)
        database_module.init_database_tables()
        importlib.reload(main_module)

        cls.database = database_module
        cls.models = models_module
        cls.repositories = extraction_repositories_module
        cls.providers = providers_module
        cls.service_module = service_module
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
        import app.extraction_providers as providers_module
        import app.extraction_service as service_module
        import app.extraction_routes as routes_module
        import app.main as main_module

        importlib.reload(database_module)
        importlib.reload(models_module)
        importlib.reload(p1_repositories_module)
        importlib.reload(p1_storage_module)
        importlib.reload(asset_repositories_module)
        importlib.reload(extraction_repositories_module)
        importlib.reload(providers_module)
        importlib.reload(service_module)
        importlib.reload(routes_module)
        importlib.reload(main_module)
        shutil.rmtree(cls._temp_dir, ignore_errors=True)

    def setUp(self) -> None:
        db = self.database.SessionLocal()
        try:
            db.query(self.models.AssetExtraction).delete()
            db.query(self.models.ExtractionJob).delete()
            db.query(self.models.Asset).delete()
            db.add(
                self.models.Asset(
                    id="asset_extraction_fixture",
                    asset_type="image",
                    file_name="fixture.png",
                    mime_type="image/png",
                    size=128,
                    storage_uri="local://assets/fixture.png",
                    hash="a" * 64,
                    status="uploaded",
                    metadata_json={"object_key": "assets/fixture.png"},
                )
            )
            db.commit()
        finally:
            db.close()

    def test_01_api_creates_job_and_saves_success_result(self) -> None:
        response = self.client.post(
            "/api/assets/asset_extraction_fixture/extract",
            json={"extract_type": "ocr", "provider": "mock"},
        )

        self.assertEqual(response.status_code, 201, response.text)
        data = response.json()["data"]
        job = data["job"]
        result = data["result"]
        self.assertTrue(job["id"].startswith("asset_extract_job_"))
        self.assertEqual(job["status"], "success")
        self.assertEqual(job["provider"], "mock")
        self.assertEqual(job["retry_count"], 0)
        self.assertIsNotNone(job["started_at"])
        self.assertIsNotNone(job["completed_at"])
        self.assertEqual(result["asset_id"], "asset_extraction_fixture")
        self.assertEqual(result["extract_type"], "ocr")
        self.assertEqual(result["version"], 1)
        self.assertTrue(result["metadata_json"]["mock_execution"])

        job_lookup = self.client.get(f"/api/extraction/jobs/{job['id']}")
        self.assertEqual(job_lookup.status_code, 200, job_lookup.text)
        self.assertEqual(job_lookup.json()["data"]["status"], "success")

        results = self.client.get(
            "/api/assets/asset_extraction_fixture/extractions"
        )
        self.assertEqual(results.status_code, 200, results.text)
        self.assertEqual(len(results.json()["data"]["extractions"]), 1)

    def test_02_service_exposes_pending_running_success_transitions(self) -> None:
        observed_statuses: list[str] = []
        database = self.database
        models = self.models
        providers = self.providers

        class ObservingProvider:
            provider_name = "state_fixture"

            def extract(self, context):
                observer_db = database.SessionLocal()
                try:
                    row = (
                        observer_db.query(models.ExtractionJob)
                        .filter(models.ExtractionJob.id == context.job_id)
                        .one()
                    )
                    observed_statuses.append(row.status)
                finally:
                    observer_db.close()
                return providers.ExtractionOutput(
                    content="state transition result",
                    metadata={"fixture": "state"},
                )

        db = self.database.SessionLocal()
        try:
            service = self.service_module.ExtractionService(db)
            pending = service.create_job(
                asset_id="asset_extraction_fixture",
                extract_type="caption",
                provider=ObservingProvider(),
            )
            self.assertEqual(pending.status, "pending")
            self.assertIsNone(pending.started_at)
            self.assertIsNone(pending.completed_at)

            execution = service.execute_job(pending.id, ObservingProvider())
            self.assertEqual(observed_statuses, ["running"])
            self.assertEqual(execution.job.status, "success")
            self.assertIsNotNone(execution.result)
        finally:
            db.close()

    def test_03_provider_failure_marks_job_failed_without_result(self) -> None:
        providers = self.providers

        class FailingProvider:
            provider_name = "failure_fixture"

            def extract(self, context):
                raise providers.ExtractionProviderError("safe simulated failure")

        db = self.database.SessionLocal()
        try:
            service = self.service_module.ExtractionService(db)
            pending = service.create_job(
                asset_id="asset_extraction_fixture",
                extract_type="metadata",
                provider=FailingProvider(),
            )
            execution = service.execute_job(pending.id, FailingProvider())
            self.assertEqual(execution.job.status, "failed")
            self.assertEqual(execution.job.error_message, "safe simulated failure")
            self.assertEqual(execution.job.retry_count, 0)
            self.assertIsNotNone(execution.job.completed_at)
            self.assertIsNone(execution.result)
            self.assertEqual(
                len(
                    self.repositories.list_asset_extractions(
                        db, "asset_extraction_fixture"
                    ).extractions
                ),
                0,
            )
        finally:
            db.close()

    def test_04_failed_job_can_retry_and_increments_retry_count(self) -> None:
        providers = self.providers

        class FailingProvider:
            provider_name = "retry_fixture"

            def extract(self, context):
                raise providers.ExtractionProviderError("first attempt failed")

        class RecoveringProvider:
            provider_name = "retry_fixture"

            def extract(self, context):
                return providers.ExtractionOutput(
                    content="retry succeeded",
                    metadata={"fixture": "retry"},
                )

        db = self.database.SessionLocal()
        try:
            service = self.service_module.ExtractionService(db)
            pending = service.create_job(
                asset_id="asset_extraction_fixture",
                extract_type="ocr",
                provider=FailingProvider(),
            )
            failed = service.execute_job(pending.id, FailingProvider())
            self.assertEqual(failed.job.status, "failed")

            recovered = service.retry_job(pending.id, RecoveringProvider())
            self.assertEqual(recovered.job.status, "success")
            self.assertEqual(recovered.job.retry_count, 1)
            self.assertIsNone(recovered.job.error_message)
            self.assertEqual(recovered.result.content, "retry succeeded")
        finally:
            db.close()

    def test_05_results_are_versioned_per_asset_and_extract_type(self) -> None:
        db = self.database.SessionLocal()
        try:
            service = self.service_module.ExtractionService(db)
            provider = self.providers.MockExtractionProvider()
            first = service.create_and_execute(
                asset_id="asset_extraction_fixture",
                extract_type="caption",
                provider=provider,
            )
            second = service.create_and_execute(
                asset_id="asset_extraction_fixture",
                extract_type="caption",
                provider=provider,
            )
            self.assertEqual(first.result.version, 1)
            self.assertEqual(second.result.version, 2)
        finally:
            db.close()

    def test_06_missing_asset_and_job_return_not_found(self) -> None:
        create_missing = self.client.post(
            "/api/assets/asset_missing/extract",
            json={"extract_type": "ocr", "provider": "mock"},
        )
        self.assertEqual(create_missing.status_code, 404)
        self.assertEqual(create_missing.json()["detail"]["code"], "ASSET_NOT_FOUND")

        list_missing = self.client.get("/api/assets/asset_missing/extractions")
        self.assertEqual(list_missing.status_code, 404)
        self.assertEqual(list_missing.json()["detail"]["code"], "ASSET_NOT_FOUND")

        job_missing = self.client.get(
            "/api/extraction/jobs/asset_extract_job_missing"
        )
        self.assertEqual(job_missing.status_code, 404)
        self.assertEqual(
            job_missing.json()["detail"]["code"],
            "EXTRACTION_JOB_NOT_FOUND",
        )


if __name__ == "__main__":
    unittest.main()

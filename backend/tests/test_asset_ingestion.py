"""P2-M1 tests for material ingestion without OCR, Caption, embedding, or RAG."""

import importlib
import os
import shutil
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

PNG_HEADER = b"\x89PNG\r\n\x1a\n"


class AssetIngestionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._saved_env = {
            key: os.environ.get(key)
            for key in (
                "DATABASE_URL",
                "ASSET_STORAGE_BACKEND",
                "ASSET_STORAGE_ROOT",
                "ASSET_MAX_UPLOAD_BYTES",
            )
        }
        cls._temp_dir = Path(tempfile.mkdtemp(prefix="datahub-assets-test-"))
        cls._db_path = cls._temp_dir / "assets.db"
        cls._object_root = cls._temp_dir / "objects"
        os.environ["DATABASE_URL"] = f"sqlite:///{cls._db_path}"
        os.environ["ASSET_STORAGE_BACKEND"] = "local"
        os.environ["ASSET_STORAGE_ROOT"] = str(cls._object_root)
        os.environ["ASSET_MAX_UPLOAD_BYTES"] = "1024"

        import app.database as database_module
        import app.db_models as models_module
        import app.asset_repositories as repositories_module
        import app.asset_storage as storage_module
        import app.asset_service as service_module
        import app.asset_routes as routes_module
        import app.main as main_module

        importlib.reload(database_module)
        importlib.reload(models_module)
        importlib.reload(repositories_module)
        importlib.reload(storage_module)
        importlib.reload(service_module)
        importlib.reload(routes_module)
        database_module.init_database_tables()
        importlib.reload(main_module)

        cls.database = database_module
        cls.models = models_module
        cls.storage_module = storage_module
        cls.client = TestClient(main_module.app)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.database.engine.dispose()
        for key, value in cls._saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        # Restore shared module globals so later P1 tests do not retain the
        # temporary Asset database or object root from this class.
        import app.database as database_module
        import app.db_models as models_module
        import app.db_repositories as p1_repositories_module
        import app.storage as p1_storage_module
        import app.asset_repositories as repositories_module
        import app.asset_storage as storage_module
        import app.asset_service as service_module
        import app.asset_routes as routes_module
        import app.main as main_module

        importlib.reload(database_module)
        importlib.reload(models_module)
        importlib.reload(p1_repositories_module)
        importlib.reload(p1_storage_module)
        importlib.reload(repositories_module)
        importlib.reload(storage_module)
        importlib.reload(service_module)
        importlib.reload(routes_module)
        importlib.reload(main_module)
        shutil.rmtree(cls._temp_dir, ignore_errors=True)

    def setUp(self) -> None:
        db = self.database.SessionLocal()
        try:
            db.query(self.models.Asset).delete()
            db.commit()
        finally:
            db.close()
        shutil.rmtree(self._object_root, ignore_errors=True)

    def _png(self, suffix: str | None = None) -> bytes:
        marker = suffix or uuid4().hex
        return PNG_HEADER + marker.encode("ascii")

    def _upload_png(self, content: bytes | None = None, name: str = "material.png"):
        return self.client.post(
            "/api/assets/upload",
            files={"file": (name, content or self._png(), "image/png")},
            data={"asset_type": "image"},
        )

    def test_01_upload_success_persists_metadata_and_binary(self) -> None:
        content = self._png("upload-success")
        response = self._upload_png(content)

        self.assertEqual(response.status_code, 201, response.text)
        payload = response.json()
        self.assertTrue(payload["success"])
        asset = payload["data"]
        self.assertTrue(asset["id"].startswith("asset_"))
        self.assertEqual(asset["asset_type"], "image")
        self.assertEqual(asset["file_name"], "material.png")
        self.assertEqual(asset["mime_type"], "image/png")
        self.assertEqual(asset["size"], len(content))
        self.assertEqual(len(asset["hash"]), 64)
        self.assertEqual(asset["status"], "uploaded")
        self.assertTrue(asset["storage_uri"].startswith("local://assets/"))
        self.assertNotIn(str(self._object_root), asset["storage_uri"])

        object_key = asset["metadata_json"]["object_key"]
        adapter = self.storage_module.get_asset_storage_adapter()
        self.assertTrue(adapter.exists(object_key))

        db = self.database.SessionLocal()
        try:
            row = db.query(self.models.Asset).filter(self.models.Asset.id == asset["id"]).one()
            self.assertEqual(row.hash, asset["hash"])
            self.assertFalse(hasattr(row, "content"))
        finally:
            db.close()

    def test_02_illegal_file_is_rejected(self) -> None:
        response = self.client.post(
            "/api/assets/upload",
            files={"file": ("payload.exe", b"MZ-not-an-image", "application/octet-stream")},
            data={"asset_type": "image"},
        )
        self.assertEqual(response.status_code, 415)
        self.assertEqual(response.json()["detail"]["code"], "UNSUPPORTED_FILE_TYPE")

        mismatch = self.client.post(
            "/api/assets/upload",
            files={"file": ("fake.png", b"not-a-real-png", "image/png")},
            data={"asset_type": "image"},
        )
        self.assertEqual(mismatch.status_code, 415)
        self.assertEqual(mismatch.json()["detail"]["code"], "INVALID_FILE_CONTENT")

    def test_03_duplicate_file_returns_existing_asset(self) -> None:
        content = self._png("same-content")
        first = self._upload_png(content)
        duplicate = self._upload_png(content, name="renamed.png")

        self.assertEqual(first.status_code, 201)
        self.assertEqual(duplicate.status_code, 409)
        detail = duplicate.json()["detail"]
        self.assertEqual(detail["code"], "ASSET_DUPLICATE")
        self.assertEqual(
            detail["details"]["existing_asset_id"],
            first.json()["data"]["id"],
        )

        db = self.database.SessionLocal()
        try:
            self.assertEqual(db.query(self.models.Asset).count(), 1)
        finally:
            db.close()

    def test_04_list_assets_supports_pagination(self) -> None:
        for index in range(3):
            response = self._upload_png(self._png(f"page-{index}"), name=f"page-{index}.png")
            self.assertEqual(response.status_code, 201, response.text)

        first_page = self.client.get("/api/assets?page=1&page_size=2")
        second_page = self.client.get("/api/assets?page=2&page_size=2")
        self.assertEqual(first_page.status_code, 200)
        self.assertEqual(second_page.status_code, 200)

        first_data = first_page.json()["data"]
        second_data = second_page.json()["data"]
        self.assertEqual(len(first_data["assets"]), 2)
        self.assertEqual(len(second_data["assets"]), 1)
        self.assertEqual(first_data["pagination"], {
            "page": 1,
            "page_size": 2,
            "total": 3,
            "total_pages": 2,
        })

    def test_05_asset_detail_and_not_found(self) -> None:
        uploaded = self._upload_png(self._png("detail"))
        asset_id = uploaded.json()["data"]["id"]

        response = self.client.get(f"/api/assets/{asset_id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["id"], asset_id)

        missing = self.client.get("/api/assets/asset_missing")
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(missing.json()["detail"]["code"], "ASSET_NOT_FOUND")

    def test_06_size_limit_and_future_types_are_rejected(self) -> None:
        too_large = self._upload_png(PNG_HEADER + b"x" * 1024)
        self.assertEqual(too_large.status_code, 413)
        self.assertEqual(too_large.json()["detail"]["code"], "FILE_TOO_LARGE")

        video = self.client.post(
            "/api/assets/upload",
            files={"file": ("future.png", self._png("future"), "image/png")},
            data={"asset_type": "video"},
        )
        self.assertEqual(video.status_code, 400)
        self.assertEqual(video.json()["detail"]["code"], "UNSUPPORTED_ASSET_TYPE")

    def test_07_storage_adapter_rejects_path_escape(self) -> None:
        adapter = self.storage_module.get_asset_storage_adapter()
        with self.assertRaises(self.storage_module.AssetStorageError):
            adapter.save("../escape.png", self._png("escape"))
        self.assertFalse((self._temp_dir / "escape.png").exists())


if __name__ == "__main__":
    unittest.main()

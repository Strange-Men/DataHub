"""M9.4A offline and Docker test-environment safety gates."""

from __future__ import annotations

import os
import socket
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.test_environment import (
    TestEnvironmentSafetyError as EnvironmentSafetyError,
    build_offline_subprocess_environment,
    require_offline_environment,
    require_test_compose_identity,
    require_test_database_url,
)


def test_offline_child_environment_is_allowlisted_and_credential_free(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://developer:secret@127.0.0.1/datahub")
    monkeypatch.setenv("EMBEDDING_API_KEY", "real-provider-sentinel")
    monkeypatch.setenv("OPENAI_API_KEY", "real-openai-sentinel")
    environment = build_offline_subprocess_environment(
        ROOT, tmp_path / "offline-test.db"
    )
    require_offline_environment(environment)
    assert environment["EMBEDDING_PROVIDER"] == "mock"
    assert environment["LLM_PROVIDER"] == "mock"
    assert "test" in environment["DATABASE_URL"]
    assert environment["ASSET_STORAGE_ROOT"].startswith(str(tmp_path))
    for key in ("EMBEDDING_API_KEY", "OPENAI_API_KEY", "LLM_API_KEY"):
        assert key not in environment
    assert "datahub" not in environment["DATABASE_URL"].rsplit("/", 1)[-1]


@pytest.mark.parametrize(
    "database_url",
    [
        "",
        "postgresql://user:password@127.0.0.1/datahub",
        "sqlite:///datahub.db",
    ],
)
def test_non_test_database_targets_fail_closed(database_url: str) -> None:
    with pytest.raises(EnvironmentSafetyError, match="test|dedicated"):
        require_test_database_url(database_url)


def test_development_database_and_compose_identity_collisions_fail_closed() -> None:
    url = "postgresql://user:password@127.0.0.1/datahub_test"
    with pytest.raises(EnvironmentSafetyError, match="identical"):
        require_test_database_url(url, development_url=url)
    with pytest.raises(EnvironmentSafetyError, match="project name"):
        require_test_compose_identity("datahub", test_ports={55432, 18000})
    with pytest.raises(EnvironmentSafetyError, match="collide"):
        require_test_compose_identity("datahub-test", test_ports={8000})


def test_offline_rebuild_path_opens_no_network_socket(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATAHUB_TEST_MODE", "offline")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
    import scripts.rebuild_vector_rag as rebuild

    result = SimpleNamespace(
        approved_candidate_count=0,
        chunk_count=0,
        embedding_count=0,
        failed_embedding_count=0,
        vector_sync_enabled=False,
        embedding_provider="mock",
        embedding_model="mock-deterministic",
        embedding_dimension=1536,
        vector_sync_error=None,
    )
    with patch.object(socket, "create_connection", side_effect=AssertionError("network used")):
        with patch("app.storage.build_rag_chunks", return_value=result):
            response = rebuild.run_rebuild()
    assert response["provider"] == "mock"


def test_test_compose_is_separate_from_development_stack() -> None:
    compose = (ROOT / "compose.test.yaml").read_text(encoding="utf-8")
    require_test_compose_identity(
        "datahub-m94a-test", test_ports={55432, 18000}
    )
    assert "name: datahub-test" in compose
    assert "image: datahub-backend-test:" in compose
    assert "POSTGRES_DB: datahub_test" in compose
    assert "DATAHUB_TEST_MODE: integration" in compose
    assert "EMBEDDING_PROVIDER: mock" in compose
    assert "127.0.0.1:${DATAHUB_TEST_POSTGRES_PORT:-55432}:5432" in compose
    assert "127.0.0.1:${DATAHUB_TEST_BACKEND_PORT:-18000}:8000" in compose
    assert "postgres_data:/var/lib/postgresql/data" not in compose
    assert "postgres_test_data:/var/lib/postgresql/data" in compose
    assert "down -v" not in compose


def test_storage_write_failure_is_safe_and_creates_no_metadata(tmp_path: Path) -> None:
    from app.asset_service import ingest_asset
    from app.asset_storage import AssetStorageAdapter, AssetStorageError

    class FailingStorage(AssetStorageAdapter):
        backend_name = "test-failure"

        def save(self, _object_key: str, _content: bytes):
            raise AssetStorageError("Asset object could not be stored.")

        def exists(self, _object_key: str) -> bool:
            return False

        def delete(self, _object_key: str) -> None:
            raise AssertionError("delete must not run when save never succeeded")

    with patch("app.asset_service.get_asset_by_hash", return_value=None):
        with patch("app.asset_service.create_asset") as create_asset:
            with pytest.raises(AssetStorageError, match="could not be stored"):
                ingest_asset(
                    Mock(),
                    FailingStorage(),
                    file_name="failure.png",
                    declared_mime_type="image/png",
                    content=b"\x89PNG\r\n\x1a\nreliability",
                    asset_type="image",
                )
    create_asset.assert_not_called()
    assert list(tmp_path.iterdir()) == []


def test_metadata_failure_removes_only_the_just_written_test_object() -> None:
    from app.asset_service import ingest_asset
    from app.asset_storage import AssetStorageAdapter, StoredAssetObject

    class RecordingStorage(AssetStorageAdapter):
        backend_name = "test-recording"

        def __init__(self) -> None:
            self.saved: list[str] = []
            self.deleted: list[str] = []

        def save(self, object_key: str, content: bytes) -> StoredAssetObject:
            self.saved.append(object_key)
            return StoredAssetObject(f"test://{object_key}", object_key, len(content))

        def exists(self, object_key: str) -> bool:
            return object_key in self.saved and object_key not in self.deleted

        def delete(self, object_key: str) -> None:
            self.deleted.append(object_key)

    storage = RecordingStorage()
    with patch("app.asset_service.get_asset_by_hash", return_value=None):
        with patch("app.asset_service.create_asset", side_effect=RuntimeError("test db failure")):
            with pytest.raises(RuntimeError, match="test db failure"):
                ingest_asset(
                    Mock(),
                    storage,
                    file_name="rollback.png",
                    declared_mime_type="image/png",
                    content=b"\x89PNG\r\n\x1a\nrollback",
                    asset_type="image",
                )
    assert len(storage.saved) == 1
    assert storage.deleted == storage.saved

"""Focused P3-M7.3 Export API, download, and RBAC tests."""

from __future__ import annotations

import hashlib
import inspect
import os
import sys
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from test_p3_asset_routes import (  # noqa: E402
    PROJECTS_PATH,
    SessionLocal,
    _enable_token_auth,
    _generate,
    _headers,
    cleanup_temporary_database,  # noqa: F401
    client as base_client,  # noqa: F401
)
from test_p3_publication_routes import (  # noqa: E402
    _actual_asset,
    _approve,
    _publish,
)

from app import p3_export_routes as routes_module  # noqa: E402
from app.auth import Permission, ROLE_PERMISSIONS, Role  # noqa: E402
from app.p3_export_models import (  # noqa: E402
    P3ExportArtifact,
    P3ExportJob,
)
from app.p3_export_storage import LocalFilesystemP3ExportStorage  # noqa: E402
from app.p3_reuse_models import ReuseSourceItem  # noqa: E402


def _create_path(project_id: str, asset_id: str) -> str:
    return f"{PROJECTS_PATH}/{project_id}/assets/{asset_id}/exports"


def _list_path(project_id: str) -> str:
    return f"{PROJECTS_PATH}/{project_id}/exports"


def _job_path(job_id: str) -> str:
    return f"/api/p3/exports/{job_id}"


def _artifact_path(job_id: str) -> str:
    return f"{_job_path(job_id)}/artifact"


def _download_path(artifact_id: str) -> str:
    return f"/api/p3/export-artifacts/{artifact_id}/download"


def _revoke_path(job_id: str) -> str:
    return f"{_job_path(job_id)}/revoke"


@pytest.fixture(name="client")
def export_client(
    base_client: TestClient,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Generator[TestClient, None, None]:
    monkeypatch.setenv(
        "P3_EXPORT_STORAGE_ROOT",
        str(tmp_path / "p3-export-api"),
    )
    monkeypatch.setenv("P3_EXPORT_STORAGE_BACKEND", "local_filesystem")
    yield base_client
    db = SessionLocal()
    try:
        db.query(P3ExportArtifact).delete()
        db.query(P3ExportJob).delete()
        db.commit()
    finally:
        db.close()


def _published_asset(
    client: TestClient,
    *,
    suffix: str,
    asset_type: str = "training_material",
) -> tuple[dict[str, object], dict[str, object]]:
    project, asset = _actual_asset(
        client,
        suffix=suffix,
        asset_type=asset_type,
    )
    published = _publish(
        client,
        str(project["id"]),
        str(asset["id"]),
        key=f"m73_publish_{suffix}",
    )
    assert published.status_code == 200, published.text
    return project, asset


def _create_export(
    client: TestClient,
    project_id: str,
    asset_id: str,
    *,
    suffix: str,
    export_format: str = "jsonl",
    headers: dict[str, str] | None = None,
):
    return client.post(
        _create_path(project_id, asset_id),
        json={
            "export_format": export_format,
            "idempotency_key": f"m73_export_{suffix}",
        },
        headers=headers,
    )


@pytest.mark.parametrize(
    ("asset_type", "export_format", "content_type"),
    [
        ("training_material", "jsonl", "application/x-ndjson"),
        ("sft_dataset", "csv", "text/csv; charset=utf-8"),
    ],
)
def test_auth_disabled_create_read_and_download(
    client,
    asset_type,
    export_format,
    content_type,
):
    project, asset = _published_asset(
        client,
        suffix=f"disabled_{export_format}",
        asset_type=asset_type,
    )
    response = _create_export(
        client,
        str(project["id"]),
        str(asset["id"]),
        suffix=f"disabled_{export_format}",
        export_format=export_format,
    )
    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert data["job"]["status"] == "succeeded"
    assert data["artifact"]["content_type"] == content_type
    assert "storage_key" not in data["artifact"]
    assert "storage_backend" not in data["artifact"]
    assert "idempotency_key" not in data["job"]
    job_id = data["job"]["id"]
    artifact = data["artifact"]
    assert client.get(_job_path(job_id)).status_code == 200
    assert client.get(_artifact_path(job_id)).status_code == 200
    download = client.get(_download_path(artifact["id"]))
    assert download.status_code == 200
    assert download.headers["content-type"] == content_type
    assert download.headers["content-disposition"] == (
        f'attachment; filename="{artifact["safe_file_name"]}"'
    )
    assert hashlib.sha256(download.content).hexdigest() == (
        artifact["artifact_sha256"]
    )
    assert int(download.headers["content-length"]) == len(download.content)


@pytest.mark.parametrize(
    "role",
    [Role.CLEANER, Role.REVIEWER, Role.VIEWER, Role.SERVICE],
)
def test_only_admin_can_create(
    client,
    monkeypatch,
    role,
):
    project, asset = _published_asset(
        client,
        suffix=f"create_forbidden_{role.value}",
    )
    _enable_token_auth(monkeypatch)
    response = _create_export(
        client,
        str(project["id"]),
        str(asset["id"]),
        suffix=f"create_forbidden_{role.value}",
        headers=_headers(role),
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "AUTHORIZATION_DENIED"


@pytest.mark.parametrize("role", list(Role))
def test_all_roles_can_read_and_download(
    client,
    monkeypatch,
    role,
):
    project, asset = _published_asset(
        client,
        suffix=f"read_{role.value}",
    )
    created = _create_export(
        client,
        str(project["id"]),
        str(asset["id"]),
        suffix=f"read_{role.value}",
    )
    data = created.json()["data"]
    _enable_token_auth(monkeypatch)
    headers = _headers(role)
    assert client.get(
        _job_path(data["job"]["id"]),
        headers=headers,
    ).status_code == 200
    assert client.get(
        _artifact_path(data["job"]["id"]),
        headers=headers,
    ).status_code == 200
    assert client.get(
        _download_path(data["artifact"]["id"]),
        headers=headers,
    ).status_code == 200


def test_token_mode_requires_valid_bearer_token(client, monkeypatch):
    project, asset = _published_asset(client, suffix="token_required")
    _enable_token_auth(monkeypatch)
    path = _create_path(str(project["id"]), str(asset["id"]))
    payload = {
        "export_format": "jsonl",
        "idempotency_key": "m73_token_required",
    }
    missing = client.post(path, json=payload)
    invalid = client.post(
        path,
        json=payload,
        headers={"Authorization": "Bearer invalid-token"},
    )
    assert missing.status_code == 401
    assert invalid.status_code == 401


def test_admin_revoke_and_revoked_download_is_gone(client, monkeypatch):
    project, asset = _published_asset(client, suffix="revoke")
    created = _create_export(
        client,
        str(project["id"]),
        str(asset["id"]),
        suffix="revoke",
    ).json()["data"]
    _enable_token_auth(monkeypatch)
    revoked = client.post(
        _revoke_path(created["job"]["id"]),
        json={"idempotency_key": "m73_revoke_key"},
        headers=_headers(Role.ADMIN),
    )
    assert revoked.status_code == 200, revoked.text
    assert revoked.json()["data"]["job"]["status"] == "revoked"
    assert revoked.json()["data"]["artifact"]["revoked_at"] is not None
    download = client.get(
        _download_path(created["artifact"]["id"]),
        headers=_headers(Role.ADMIN),
    )
    assert download.status_code == 410
    assert download.json()["detail"]["code"] == "P3_EXPORT_ARTIFACT_REVOKED"
    db = SessionLocal()
    try:
        artifact = db.get(P3ExportArtifact, created["artifact"]["id"])
        assert artifact is not None
        assert artifact.revoked_at is not None
        assert LocalFilesystemP3ExportStorage(
            Path(os.environ["P3_EXPORT_STORAGE_ROOT"])
        ).exists(artifact.storage_key)
    finally:
        db.close()


@pytest.mark.parametrize(
    "role",
    [Role.CLEANER, Role.REVIEWER, Role.VIEWER, Role.SERVICE],
)
def test_only_admin_can_revoke(client, monkeypatch, role):
    project, asset = _published_asset(
        client,
        suffix=f"revoke_forbidden_{role.value}",
    )
    created = _create_export(
        client,
        str(project["id"]),
        str(asset["id"]),
        suffix=f"revoke_forbidden_{role.value}",
    ).json()["data"]
    _enable_token_auth(monkeypatch)
    response = client.post(
        _revoke_path(created["job"]["id"]),
        json={"idempotency_key": f"m73_revoke_{role.value}"},
        headers=_headers(role),
    )
    assert response.status_code == 403


def test_create_idempotency_replay_and_conflict(client):
    project, asset = _published_asset(client, suffix="idempotency")
    path = _create_path(str(project["id"]), str(asset["id"]))
    payload = {
        "export_format": "jsonl",
        "idempotency_key": "m73_same_key",
    }
    first = client.post(path, json=payload)
    second = client.post(path, json=payload)
    conflict = client.post(
        path,
        json={**payload, "export_format": "csv"},
    )
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["data"]["job"]["id"] == (
        second.json()["data"]["job"]["id"]
    )
    assert second.json()["data"]["replayed"] is True
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == (
        "P3_EXPORT_IDEMPOTENCY_CONFLICT"
    )


def test_list_pagination_and_filters(client):
    project, asset = _published_asset(client, suffix="list")
    for export_format in ("jsonl", "csv"):
        response = _create_export(
            client,
            str(project["id"]),
            str(asset["id"]),
            suffix=f"list_{export_format}",
            export_format=export_format,
        )
        assert response.status_code == 201
    page = client.get(
        _list_path(str(project["id"])),
        params={"limit": 1, "offset": 1},
    )
    assert page.status_code == 200
    assert page.json()["data"]["total"] == 2
    assert len(page.json()["data"]["items"]) == 1
    filtered = client.get(
        _list_path(str(project["id"])),
        params={"export_format": "csv", "status": "succeeded"},
    )
    assert filtered.status_code == 200
    assert filtered.json()["data"]["total"] == 1
    assert filtered.json()["data"]["items"][0]["export_format"] == "csv"


def test_unpublished_superseded_and_stale_are_conflicts(client):
    project, unapproved = _actual_asset(
        client,
        suffix="unpublished",
        approve=False,
    )
    unpublished = _create_export(
        client,
        str(project["id"]),
        str(unapproved["id"]),
        suffix="unpublished",
    )
    assert unpublished.status_code == 409
    assert unpublished.json()["detail"]["code"] == (
        "P3_EXPORT_ASSET_NOT_PUBLISHED"
    )

    published_project, first = _published_asset(
        client,
        suffix="superseded",
    )
    project_id = str(published_project["id"])
    second_response = _generate(
        client,
        project_id,
        key="m73_superseding_generation",
    )
    second = second_response.json()["data"]
    _approve(client, project_id, str(second["id"]), suffix="superseding")
    _publish(
        client,
        project_id,
        str(second["id"]),
        key="m73_superseding_publish",
    )
    superseded = _create_export(
        client,
        project_id,
        str(first["id"]),
        suffix="superseded",
    )
    assert superseded.status_code == 409

    stale_project, stale_asset = _published_asset(
        client,
        suffix="stale",
    )
    db = SessionLocal()
    try:
        source = (
            db.query(ReuseSourceItem)
            .filter(
                ReuseSourceItem.project_id == str(stale_project["id"])
            )
            .one()
        )
        source.source_stale = True
        db.commit()
    finally:
        db.close()
    stale = _create_export(
        client,
        str(stale_project["id"]),
        str(stale_asset["id"]),
        suffix="stale",
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "P3_EXPORT_SOURCE_STALE"


def test_historical_artifact_remains_downloadable_after_source_stale(client):
    project, asset = _published_asset(client, suffix="historical_stale")
    created = _create_export(
        client,
        str(project["id"]),
        str(asset["id"]),
        suffix="historical_stale",
    ).json()["data"]
    db = SessionLocal()
    try:
        source = (
            db.query(ReuseSourceItem)
            .filter(ReuseSourceItem.project_id == str(project["id"]))
            .one()
        )
        source.source_stale = True
        db.commit()
    finally:
        db.close()
    metadata = client.get(_artifact_path(created["job"]["id"]))
    assert metadata.status_code == 200
    assert metadata.json()["data"]["source_stale"] is True
    assert metadata.json()["data"]["current_reuse_eligible"] is False
    assert client.get(
        _download_path(created["artifact"]["id"])
    ).status_code == 200


def test_forged_fields_and_invalid_filters_are_422(client):
    project, asset = _published_asset(client, suffix="forged")
    response = client.post(
        _create_path(str(project["id"]), str(asset["id"])),
        json={
            "export_format": "jsonl",
            "idempotency_key": "m73_forged",
            "storage_path": "C:\\secret",
            "requested_by_role": "admin",
        },
    )
    assert response.status_code == 422
    assert client.get(
        _list_path(str(project["id"])),
        params={"limit": 101},
    ).status_code == 422
    assert client.get(
        _list_path(str(project["id"])),
        params={"status": "unknown"},
    ).status_code == 422


def test_missing_corrupt_and_traversal_artifacts_fail_safely(
    client,
):
    project, asset = _published_asset(client, suffix="integrity")
    created = _create_export(
        client,
        str(project["id"]),
        str(asset["id"]),
        suffix="integrity",
    ).json()["data"]
    artifact_id = created["artifact"]["id"]
    storage = LocalFilesystemP3ExportStorage(
        Path(os.environ["P3_EXPORT_STORAGE_ROOT"])
    )
    db = SessionLocal()
    try:
        artifact = db.get(P3ExportArtifact, artifact_id)
        assert artifact is not None
        storage_key = artifact.storage_key
    finally:
        db.close()
    storage.cleanup_incomplete(storage_key)
    missing = client.get(_download_path(artifact_id))
    assert missing.status_code == 503
    assert "absolute" not in missing.text.lower()

    project2, asset2 = _published_asset(client, suffix="corrupt")
    created2 = _create_export(
        client,
        str(project2["id"]),
        str(asset2["id"]),
        suffix="corrupt",
    ).json()["data"]
    db = SessionLocal()
    try:
        artifact2 = db.get(P3ExportArtifact, created2["artifact"]["id"])
        assert artifact2 is not None
        storage.write_atomic(artifact2.storage_key, b"tampered")
    finally:
        db.close()
    corrupt = client.get(_download_path(created2["artifact"]["id"]))
    assert corrupt.status_code == 503
    assert corrupt.json()["detail"]["code"] == "P3_EXPORT_STORAGE_FAILED"

    project3, asset3 = _published_asset(client, suffix="traversal")
    created3 = _create_export(
        client,
        str(project3["id"]),
        str(asset3["id"]),
        suffix="traversal",
    ).json()["data"]
    db = SessionLocal()
    try:
        artifact3 = db.get(P3ExportArtifact, created3["artifact"]["id"])
        assert artifact3 is not None
        artifact3.storage_key = "../forbidden"
        db.commit()
    finally:
        db.close()
    traversal = client.get(_download_path(created3["artifact"]["id"]))
    assert traversal.status_code == 503


def test_openapi_permissions_and_route_boundary(client):
    expected_permissions = {
        Permission.P3_EXPORT_READ,
        Permission.P3_EXPORT_CREATE,
        Permission.P3_EXPORT_DOWNLOAD,
        Permission.P3_EXPORT_REVOKE,
    }
    assert expected_permissions.issubset(ROLE_PERMISSIONS[Role.ADMIN])
    for role in (Role.CLEANER, Role.REVIEWER, Role.VIEWER, Role.SERVICE):
        assert Permission.P3_EXPORT_READ in ROLE_PERMISSIONS[role]
        assert Permission.P3_EXPORT_DOWNLOAD in ROLE_PERMISSIONS[role]
        assert Permission.P3_EXPORT_CREATE not in ROLE_PERMISSIONS[role]
        assert Permission.P3_EXPORT_REVOKE not in ROLE_PERMISSIONS[role]
    paths = client.get("/openapi.json").json()["paths"]
    expected_paths = {
        "/api/p3/reuse-projects/{project_id}/assets/{asset_version_id}/exports",
        "/api/p3/reuse-projects/{project_id}/exports",
        "/api/p3/exports/{export_job_id}",
        "/api/p3/exports/{export_job_id}/artifact",
        "/api/p3/export-artifacts/{artifact_id}/download",
        "/api/p3/exports/{export_job_id}/revoke",
    }
    assert expected_paths.issubset(paths)
    source = inspect.getsource(routes_module)
    assert "p3_export_repositories" not in source
    assert "Path(" not in source
    assert ".open(" not in source
    assert "storage_key" not in source
    assert "Provider" not in source
    assert "Retrieval" not in source
    assert "Token" not in source

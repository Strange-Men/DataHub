"""Focused P3-M3.4 API, RBAC, and route-boundary tests."""

from __future__ import annotations

import inspect
import os
import sys
import tempfile
from collections.abc import Generator
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text


ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

_TEMP_DATABASE_DIR = tempfile.TemporaryDirectory(prefix="datahub-p3-m3-4-")
_DATABASE_PATH = Path(_TEMP_DATABASE_DIR.name) / "p3-asset-api.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_DATABASE_PATH}"

from app import p3_asset_routes as routes_module  # noqa: E402
from app.auth import (  # noqa: E402
    Permission,
    ROLE_PERMISSIONS,
    ROLE_TOKEN_ENV,
    Role,
)
from app.database import SessionLocal, engine, get_db  # noqa: E402
from app.db_models import KnowledgeCandidate, ReviewRecord  # noqa: E402
from app.main import app  # noqa: E402
from app.p3_asset_service import P3AssetService, P3AssetServiceError  # noqa: E402
from app.p3_reuse_models import (  # noqa: E402
    ReuseAssetType,
    ReuseAssetVersion,
    ReuseAssetVersionSource,
    ReuseProject,
    ReuseReview,
    ReuseSourceItem,
)


PROJECTS_PATH = "/api/p3/reuse-projects"
TOKENS = {role: f"p3-m3-4-{role.value}-token" for role in Role}


@pytest.fixture(scope="session", autouse=True)
def cleanup_temporary_database() -> Generator[None, None, None]:
    yield
    engine.dispose()
    _TEMP_DATABASE_DIR.cleanup()


def _override_get_db() -> Generator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    monkeypatch.setenv("DATAHUB_AUTH_MODE", "disabled")
    for env_name in ROLE_TOKEN_ENV.values():
        monkeypatch.delenv(env_name, raising=False)
    db = SessionLocal()
    try:
        # Defer FK checks until all dependent and self-referencing rows are
        # removed in this teardown transaction.
        db.execute(text("PRAGMA defer_foreign_keys=ON"))
        for model in (
            ReuseReview,
            ReuseAssetVersionSource,
            ReuseAssetVersion,
            ReuseSourceItem,
            ReuseProject,
            ReviewRecord,
            KnowledgeCandidate,
        ):
            db.query(model).delete()
        db.commit()
    finally:
        db.close()
    app.dependency_overrides[get_db] = _override_get_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db, None)


def _enable_token_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATAHUB_AUTH_MODE", "token")
    for role, token in TOKENS.items():
        monkeypatch.setenv(ROLE_TOKEN_ENV[role], token)


def _headers(role: Role) -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKENS[role]}"}


def _seed_p1(candidate_id: str = "m34_candidate") -> None:
    batch_id = f"batch_{candidate_id}"
    snapshot = {
        "candidate_id": candidate_id,
        "source_type": "sanitized_batch",
        "source_batch_id": batch_id,
        "knowledge_type": "faq",
        "question": f"Question for {candidate_id}?",
        "answer": f"Approved answer for {candidate_id}.",
        "intent": "customer_policy",
        "tags": ["governed", "policy"],
        "risk_level": "low",
    }
    db = SessionLocal()
    try:
        db.add(
            KnowledgeCandidate(
                id=candidate_id,
                source_type="sanitized_batch",
                source_id=batch_id,
                question=snapshot["question"],
                answer=snapshot["answer"],
                intent=snapshot["intent"],
                tags=snapshot["tags"],
                risk_level=snapshot["risk_level"],
                quality_score=0.95,
                status="approved",
                metadata_json={
                    "source_batch_id": batch_id,
                    "knowledge_type": "faq",
                },
            )
        )
        db.add(
            ReviewRecord(
                id=f"review_{candidate_id}",
                candidate_id=candidate_id,
                reviewer="reviewer",
                action="approved",
                snapshot_json=snapshot,
            )
        )
        db.commit()
    finally:
        db.close()


def _create_project(
    client: TestClient,
    *,
    key: str = "m34_project_key",
) -> dict[str, object]:
    response = client.post(
        PROJECTS_PATH,
        json={
            "name": "M3.4 draft asset API",
            "description": "Focused route test",
            "idempotency_key": key,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


def _create_active_project(
    client: TestClient,
    *,
    project_key: str = "m34_project_key",
    candidate_id: str = "m34_candidate",
) -> tuple[dict[str, object], dict[str, object]]:
    _seed_p1(candidate_id)
    project = _create_project(client, key=project_key)
    source_response = client.post(
        f"{PROJECTS_PATH}/{project['id']}/sources",
        json={
            "source_type": "P1_KNOWLEDGE",
            "source_id": candidate_id,
        },
    )
    assert source_response.status_code == 201, source_response.text
    activate = client.post(f"{PROJECTS_PATH}/{project['id']}/activate")
    assert activate.status_code == 200, activate.text
    return activate.json()["data"], source_response.json()["data"]


def _generate(
    client: TestClient,
    project_id: str,
    *,
    asset_type: str = "training_material",
    key: str = "m34_generation_key",
    headers: dict[str, str] | None = None,
    extra: dict[str, object] | None = None,
):
    payload: dict[str, object] = {
        "asset_type": asset_type,
        "idempotency_key": key,
    }
    payload.update(extra or {})
    return client.post(
        f"{PROJECTS_PATH}/{project_id}/assets/generate",
        json=payload,
        headers=headers,
    )


def test_auth_disabled_generation_compatibility(client: TestClient) -> None:
    project, _source = _create_active_project(client)
    response = _generate(client, str(project["id"]))
    assert response.status_code == 201
    assert response.json()["data"]["status"] == "generated"


@pytest.mark.parametrize("role", [Role.ADMIN, Role.CLEANER, Role.SERVICE])
def test_admin_cleaner_service_can_generate(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    role: Role,
) -> None:
    project, _source = _create_active_project(client)
    _enable_token_auth(monkeypatch)
    response = _generate(
        client,
        str(project["id"]),
        key=f"generation_{role.value}",
        headers=_headers(role),
    )
    assert response.status_code == 201, response.text
    assert response.json()["data"]["created_by_role"] == role.value


@pytest.mark.parametrize("role", [Role.REVIEWER, Role.VIEWER])
def test_reviewer_and_viewer_cannot_generate(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    role: Role,
) -> None:
    project, _source = _create_active_project(client)
    _enable_token_auth(monkeypatch)
    response = _generate(
        client,
        str(project["id"]),
        headers=_headers(role),
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "AUTHORIZATION_DENIED"


@pytest.mark.parametrize("role", list(Role))
def test_all_five_roles_can_read_draft_assets(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    role: Role,
) -> None:
    project, _source = _create_active_project(client)
    generated = _generate(client, str(project["id"])).json()["data"]
    _enable_token_auth(monkeypatch)
    list_response = client.get(
        f"{PROJECTS_PATH}/{project['id']}/assets",
        headers=_headers(role),
    )
    detail_response = client.get(
        f"{PROJECTS_PATH}/{project['id']}/assets/{generated['id']}",
        headers=_headers(role),
    )
    assert list_response.status_code == 200
    assert detail_response.status_code == 200


def test_token_mode_requires_valid_bearer_token(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project, _source = _create_active_project(client)
    _enable_token_auth(monkeypatch)
    path = f"{PROJECTS_PATH}/{project['id']}/assets"
    missing = client.get(path)
    invalid = client.get(path, headers={"Authorization": "Bearer wrong"})
    assert missing.status_code == 401
    assert missing.json()["detail"]["code"] == "AUTHENTICATION_REQUIRED"
    assert invalid.status_code == 401
    assert invalid.json()["detail"]["code"] == "AUTHENTICATION_INVALID"
    assert "wrong" not in invalid.text


@pytest.mark.parametrize("asset_type", [item.value for item in ReuseAssetType])
def test_api_generates_all_five_asset_types(
    client: TestClient,
    asset_type: str,
) -> None:
    project, _source = _create_active_project(client)
    response = _generate(
        client,
        str(project["id"]),
        asset_type=asset_type,
        key=f"generation_{asset_type}",
    )
    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert data["asset_type"] == asset_type
    assert data["generation_mode"] == "deterministic_template"
    assert data["content_payload"]


@pytest.mark.parametrize(
    "payload",
    [
        {"asset_type": "unknown", "idempotency_key": "key"},
        {
            "asset_type": "training_material",
            "idempotency_key": "key",
            "version_number": 99,
        },
        {
            "asset_type": "training_material",
            "idempotency_key": "key",
            "status": "published",
        },
        {
            "asset_type": "training_material",
            "idempotency_key": "key",
            "content_payload": {"forged": True},
        },
        {
            "asset_type": "training_material",
            "idempotency_key": "key",
            "source_manifest_hash": "f" * 64,
        },
        {
            "asset_type": "training_material",
            "idempotency_key": "key",
            "generation_mode": "llm_draft",
        },
    ],
)
def test_invalid_or_forged_generation_fields_return_422(
    client: TestClient,
    payload: dict[str, object],
) -> None:
    project, _source = _create_active_project(client)
    response = client.post(
        f"{PROJECTS_PATH}/{project['id']}/assets/generate",
        json=payload,
    )
    assert response.status_code == 422
    db = SessionLocal()
    try:
        assert db.query(ReuseAssetVersion).count() == 0
    finally:
        db.close()


def test_unknown_template_returns_stable_422(client: TestClient) -> None:
    project, _source = _create_active_project(client)
    response = _generate(
        client,
        str(project["id"]),
        extra={"template_key": "missing-template"},
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "P3_ASSET_TEMPLATE_NOT_FOUND"


def test_draft_and_archived_projects_return_409(client: TestClient) -> None:
    _seed_p1()
    project = _create_project(client)
    added = client.post(
        f"{PROJECTS_PATH}/{project['id']}/sources",
        json={"source_type": "P1_KNOWLEDGE", "source_id": "m34_candidate"},
    )
    assert added.status_code == 201
    draft = _generate(client, str(project["id"]))
    assert draft.status_code == 409
    assert draft.json()["detail"]["code"] == "P3_ASSET_PROJECT_NOT_ACTIVE"

    assert client.post(f"{PROJECTS_PATH}/{project['id']}/activate").status_code == 200
    assert client.post(f"{PROJECTS_PATH}/{project['id']}/archive").status_code == 200
    archived = _generate(client, str(project["id"]), key="archived_key")
    assert archived.status_code == 409
    assert archived.json()["detail"]["code"] == "P3_ASSET_PROJECT_NOT_ACTIVE"


def test_stale_source_returns_stable_409(client: TestClient) -> None:
    project, source = _create_active_project(client)
    db = SessionLocal()
    try:
        row = db.get(ReuseSourceItem, source["id"])
        row.source_stale = True
        db.commit()
    finally:
        db.close()
    response = _generate(client, str(project["id"]))
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "P3_ASSET_SOURCE_STALE"


def test_idempotent_replay_and_conflict_http_contract(client: TestClient) -> None:
    project, _source = _create_active_project(client)
    first = _generate(client, str(project["id"]))
    replay = _generate(client, str(project["id"]))
    assert first.status_code == replay.status_code == 201
    assert first.json()["data"]["id"] == replay.json()["data"]["id"]
    conflict = _generate(
        client,
        str(project["id"]),
        asset_type="sop",
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "P3_ASSET_IDEMPOTENCY_CONFLICT"


def test_list_filter_pagination_detail_and_source_snapshot(
    client: TestClient,
) -> None:
    project, _source = _create_active_project(client)
    training = _generate(
        client,
        str(project["id"]),
        key="training_key",
    ).json()["data"]
    _generate(
        client,
        str(project["id"]),
        asset_type="sop",
        key="sop_key",
    )
    listed = client.get(
        f"{PROJECTS_PATH}/{project['id']}/assets",
        params={
            "asset_type": "training_material",
            "status": "generated",
            "limit": 1,
            "offset": 0,
        },
    )
    assert listed.status_code == 200
    assert listed.json()["data"]["total"] == 1
    assert listed.json()["data"]["items"][0]["id"] == training["id"]

    detail = client.get(
        f"{PROJECTS_PATH}/{project['id']}/assets/{training['id']}"
    )
    assert detail.status_code == 200
    assert detail.json()["data"]["content_hash"] == training["content_hash"]

    sources = client.get(
        f"{PROJECTS_PATH}/{project['id']}/assets/{training['id']}/sources"
    )
    assert sources.status_code == 200
    source_data = sources.json()["data"]
    assert source_data["total"] == 1
    serialized = str(source_data).lower()
    assert "approved answer" not in serialized
    assert "vector" not in serialized
    assert "token" not in serialized


def test_missing_project_asset_and_invalid_pagination_contracts(
    client: TestClient,
) -> None:
    project, _source = _create_active_project(client)
    missing_project = client.get(f"{PROJECTS_PATH}/missing/assets")
    missing_asset = client.get(
        f"{PROJECTS_PATH}/{project['id']}/assets/missing"
    )
    bad_page = client.get(
        f"{PROJECTS_PATH}/{project['id']}/assets",
        params={"limit": 101},
    )
    assert missing_project.status_code == 404
    assert missing_project.json()["detail"]["code"] == "P3_ASSET_PROJECT_NOT_FOUND"
    assert missing_asset.status_code == 404
    assert missing_asset.json()["detail"]["code"] == "P3_ASSET_NOT_FOUND"
    assert bad_page.status_code == 422


def test_error_responses_never_leak_database_or_token_details(
    client: TestClient,
) -> None:
    project, _source = _create_active_project(client)
    unsafe = "postgresql://user:password@internal/datahub token=secret"
    with patch.object(
        P3AssetService,
        "list_project_asset_versions",
        side_effect=RuntimeError(unsafe),
    ):
        response = client.get(f"{PROJECTS_PATH}/{project['id']}/assets")
    assert response.status_code == 500
    assert response.json()["detail"]["code"] == "P3_ASSET_INTERNAL_ERROR"
    for forbidden in ("postgresql://", "password", "token=secret"):
        assert forbidden not in response.text.lower()

    with patch.object(
        P3AssetService,
        "list_project_asset_versions",
        side_effect=P3AssetServiceError(
            "P3_ASSET_STORAGE_UNAVAILABLE",
            "P3 draft asset persistence is unavailable.",
            {},
        ),
    ):
        unavailable = client.get(f"{PROJECTS_PATH}/{project['id']}/assets")
    assert unavailable.status_code == 503
    assert unavailable.json()["detail"]["code"] == "P3_ASSET_STORAGE_UNAVAILABLE"


def test_permissions_are_centralized_without_new_roles() -> None:
    assert set(Role) == {
        Role.ADMIN,
        Role.CLEANER,
        Role.REVIEWER,
        Role.SERVICE,
        Role.VIEWER,
    }
    for role in Role:
        assert Permission.P3_ASSET_READ in ROLE_PERMISSIONS[role]
    for role in (Role.ADMIN, Role.CLEANER, Role.SERVICE):
        assert Permission.P3_ASSET_GENERATE in ROLE_PERMISSIONS[role]
    for role in (Role.REVIEWER, Role.VIEWER):
        assert Permission.P3_ASSET_GENERATE not in ROLE_PERMISSIONS[role]


def test_openapi_registers_four_asset_endpoints(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    expected = {
        "/api/p3/reuse-projects/{project_id}/assets/generate": {"post"},
        "/api/p3/reuse-projects/{project_id}/assets": {"get"},
        "/api/p3/reuse-projects/{project_id}/assets/{asset_version_id}": {"get"},
        (
            "/api/p3/reuse-projects/{project_id}/assets/"
            "{asset_version_id}/sources"
        ): {"get"},
    }
    for path, methods in expected.items():
        assert methods <= set(paths[path])


def test_route_boundary_calls_only_asset_service() -> None:
    source = inspect.getsource(routes_module)
    for forbidden in (
        "p3_asset_repositories",
        "p3_reuse_repositories",
        "db_models",
        "p3_source_eligibility",
        "KnowledgeCandidate",
        "KnowledgeAsset",
        "content_hash(",
        "sha256",
    ):
        assert forbidden not in source
    assert "P3AssetService(db)" in source

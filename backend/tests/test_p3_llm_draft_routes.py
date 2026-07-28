"""Focused P3-M4.3 LLM draft API, RBAC, and route-boundary tests."""

from __future__ import annotations

import inspect
import sys
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from test_p3_asset_routes import (  # noqa: E402
    PROJECTS_PATH,
    SessionLocal,
    _create_active_project,
    _create_project,
    _enable_token_auth,
    _headers,
    cleanup_temporary_database,
    client,
)

from app import p3_asset_routes as routes_module  # noqa: E402
from app.auth import Permission, ROLE_PERMISSIONS, Role  # noqa: E402
from app.p3_asset_service import P3AssetServiceError  # noqa: E402
from app.p3_llm_draft_service import P3LLMDraftService  # noqa: E402
from app.p3_reuse_models import (  # noqa: E402
    ReuseAssetType,
    ReuseAssetVersion,
    ReuseAssetVersionStatus,
    ReuseGenerationMode,
)


def _path(project_id: str) -> str:
    return f"{PROJECTS_PATH}/{project_id}/assets/generate-llm-draft"


def _payload(
    *,
    asset_type: str = "training_material",
    key: str = "m43_llm_key",
    **extra: object,
) -> dict[str, object]:
    value: dict[str, object] = {
        "asset_type": asset_type,
        "idempotency_key": key,
    }
    value.update(extra)
    return value


def _version(
    project_id: str,
    *,
    asset_type: ReuseAssetType = ReuseAssetType.TRAINING_MATERIAL,
    version_id: str = "m43_llm_version",
) -> ReuseAssetVersion:
    now = datetime.now(UTC).replace(tzinfo=None)
    return ReuseAssetVersion(
        id=version_id,
        project_id=project_id,
        asset_type=asset_type,
        version_number=1,
        status=ReuseAssetVersionStatus.GENERATED,
        generation_mode=ReuseGenerationMode.LLM_DRAFT,
        template_key=(
            f"llm|prompt=p3.llm.{asset_type.value}.v1|"
            "provider=fake_test_only|model=fake|config=1234567890abcdef"
        ),
        template_version="v1",
        content_payload={"test": True},
        content_hash="a" * 64,
        source_manifest_hash="b" * 64,
        idempotency_key=f"key_{version_id}",
        created_by_role="cleaner",
        request_id=f"request_{version_id}",
        created_at=now,
        updated_at=now,
    )


def test_default_disabled_returns_503_without_provider_or_database_write(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project, _source = _create_active_project(client)
    monkeypatch.setenv("P3_LLM_DRAFT_ENABLED", "false")
    with SessionLocal() as db:
        before = db.query(ReuseAssetVersion).count()
    with patch(
        "app.p3_llm_draft_service.OpenAICompatibleP3LLMDraftProvider"
    ) as adapter:
        response = client.post(_path(project["id"]), json=_payload())
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "P3_LLM_DRAFT_DISABLED"
    adapter.assert_not_called()
    with SessionLocal() as db:
        assert db.query(ReuseAssetVersion).count() == before


@pytest.mark.parametrize(
    "role",
    [Role.ADMIN, Role.CLEANER, Role.SERVICE],
)
def test_admin_cleaner_and_service_can_generate(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    role: Role,
) -> None:
    project, _source = _create_active_project(client)
    _enable_token_auth(monkeypatch)
    with patch.object(
        P3LLMDraftService,
        "generate_llm_draft",
        return_value=_version(project["id"]),
    ) as operation:
        response = client.post(
            _path(project["id"]),
            json=_payload(),
            headers=_headers(role),
        )
    assert response.status_code == 201
    assert response.json()["data"]["generation_mode"] == "llm_draft"
    assert operation.call_args.kwargs["actor_role"] == role.value


@pytest.mark.parametrize("role", [Role.REVIEWER, Role.VIEWER])
def test_reviewer_and_viewer_cannot_generate(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    role: Role,
) -> None:
    project, _source = _create_active_project(client)
    _enable_token_auth(monkeypatch)
    with patch.object(
        P3LLMDraftService,
        "generate_llm_draft",
    ) as operation:
        response = client.post(
            _path(project["id"]),
            json=_payload(),
            headers=_headers(role),
        )
    assert response.status_code == 403
    operation.assert_not_called()


def test_token_mode_requires_valid_bearer_token(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project, _source = _create_active_project(client)
    _enable_token_auth(monkeypatch)
    missing = client.post(_path(project["id"]), json=_payload())
    invalid = client.post(
        _path(project["id"]),
        json=_payload(),
        headers={"Authorization": "Bearer wrong-token"},
    )
    assert missing.status_code == 401
    assert invalid.status_code == 401


def test_auth_disabled_mode_remains_compatible(client: TestClient) -> None:
    project, _source = _create_active_project(client)
    with patch.object(
        P3LLMDraftService,
        "generate_llm_draft",
        return_value=_version(project["id"]),
    ) as operation:
        response = client.post(_path(project["id"]), json=_payload())
    assert response.status_code == 201
    assert operation.call_args.kwargs["actor_role"] == Role.ADMIN.value


@pytest.mark.parametrize("asset_type", [item.value for item in ReuseAssetType])
def test_all_five_asset_types_reach_service(
    client: TestClient,
    asset_type: str,
) -> None:
    project, _source = _create_active_project(
        client,
        project_key=f"project_{asset_type}",
        candidate_id=f"candidate_{asset_type}",
    )
    enum_value = ReuseAssetType(asset_type)
    with patch.object(
        P3LLMDraftService,
        "generate_llm_draft",
        return_value=_version(
            project["id"],
            asset_type=enum_value,
            version_id=f"version_{asset_type}",
        ),
    ) as operation:
        response = client.post(
            _path(project["id"]),
            json=_payload(asset_type=asset_type, key=f"key_{asset_type}"),
        )
    assert response.status_code == 201
    assert operation.call_args.kwargs["asset_type"] is enum_value


@pytest.mark.parametrize(
    "forged",
    [
        {"generation_mode": "llm_draft"},
        {"model_api_key": "forbidden"},
        {"base_url": "https://forbidden.invalid"},
        {"source_materials": []},
        {"source_snapshots": []},
        {"content_payload": {}},
        {"content_hash": "a" * 64},
        {"source_manifest_hash": "b" * 64},
        {"status": "generated"},
        {"version_number": 7},
        {"model_parameters": {"temperature": 1}},
    ],
)
def test_forged_or_unapproved_fields_are_rejected(
    client: TestClient,
    forged: dict[str, object],
) -> None:
    project, _source = _create_active_project(client)
    with patch.object(
        P3LLMDraftService,
        "generate_llm_draft",
    ) as operation:
        response = client.post(
            _path(project["id"]),
            json=_payload(**forged),
        )
    assert response.status_code == 422
    operation.assert_not_called()


def test_invalid_asset_type_is_422(client: TestClient) -> None:
    project, _source = _create_active_project(client)
    response = client.post(
        _path(project["id"]),
        json=_payload(asset_type="unknown"),
    )
    assert response.status_code == 422


@pytest.mark.parametrize(
    ("code", "status"),
    [
        ("P3_ASSET_PROJECT_NOT_ACTIVE", 409),
        ("P3_ASSET_SOURCE_STALE", 409),
        ("P3_ASSET_SOURCE_EVIDENCE_CHANGED", 409),
        ("P3_ASSET_IDEMPOTENCY_CONFLICT", 409),
        ("P3_LLM_CONTEXT_LIMIT_EXCEEDED", 422),
        ("P3_LLM_PROVIDER_NOT_CONFIGURED", 503),
        ("P3_LLM_PROVIDER_TIMEOUT", 503),
        ("P3_LLM_PROVIDER_UNAVAILABLE", 503),
        ("P3_LLM_OUTPUT_INVALID_JSON", 502),
        ("P3_LLM_OUTPUT_SCHEMA_INVALID", 502),
        ("P3_LLM_UNKNOWN_SOURCE_REF", 502),
        ("P3_LLM_GROUNDING_INCOMPLETE", 502),
        ("P3_LLM_OUTPUT_TOO_LARGE", 502),
        ("P3_LLM_GENERATION_FAILED", 502),
    ],
)
def test_stable_service_errors_map_to_safe_http_status(
    client: TestClient,
    code: str,
    status: int,
) -> None:
    project, _source = _create_active_project(client)
    with patch.object(
        P3LLMDraftService,
        "generate_llm_draft",
        side_effect=P3AssetServiceError(
            code,
            "Safe governed LLM draft error.",
            {"project_id": project["id"]},
        ),
    ):
        response = client.post(_path(project["id"]), json=_payload())
    assert response.status_code == status
    assert response.json()["detail"]["code"] == code
    assert "secret" not in response.text.lower()


def test_llm_asset_is_readable_through_existing_list_and_detail_api(
    client: TestClient,
) -> None:
    project, _source = _create_active_project(client)
    version = _version(project["id"])
    version_id = version.id
    with SessionLocal() as db:
        db.add(version)
        db.commit()
    listed = client.get(f"{PROJECTS_PATH}/{project['id']}/assets")
    detail = client.get(
        f"{PROJECTS_PATH}/{project['id']}/assets/{version_id}"
    )
    assert listed.status_code == 200
    assert listed.json()["data"]["items"][0]["generation_mode"] == "llm_draft"
    assert detail.status_code == 200
    assert detail.json()["data"]["generation_mode"] == "llm_draft"


def test_permission_is_centralized_without_new_roles() -> None:
    assert Permission.P3_ASSET_GENERATE_LLM.value == "p3.asset.generate_llm"
    assert set(Role) == {
        Role.ADMIN,
        Role.CLEANER,
        Role.REVIEWER,
        Role.SERVICE,
        Role.VIEWER,
    }
    for role in (Role.ADMIN, Role.CLEANER, Role.SERVICE):
        assert Permission.P3_ASSET_GENERATE_LLM in ROLE_PERMISSIONS[role]
    for role in (Role.REVIEWER, Role.VIEWER):
        assert Permission.P3_ASSET_GENERATE_LLM not in ROLE_PERMISSIONS[role]
    for role in Role:
        assert Permission.P3_ASSET_READ in ROLE_PERMISSIONS[role]


def test_openapi_registers_llm_draft_endpoint(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    path = (
        "/api/p3/reuse-projects/{project_id}/assets/generate-llm-draft"
    )
    assert "post" in schema["paths"][path]
    request_schema = schema["paths"][path]["post"]["requestBody"]
    assert request_schema


def test_route_boundary_only_validates_auth_and_calls_service() -> None:
    source = inspect.getsource(routes_module.generate_llm_draft)
    assert "P3LLMDraftService(db).generate_llm_draft" in source
    for forbidden in (
        "query(",
        "execute(",
        "p3_asset_repositories",
        "p3_reuse_repositories",
        "KnowledgeCandidate",
        "KnowledgeAsset",
        "build_messages",
        "generate_structured_draft",
        "validate_and_ground",
        "sha256",
        "P3_LLM_API_KEY",
    ):
        assert forbidden not in source

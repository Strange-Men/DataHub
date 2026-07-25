"""Focused P3-M2.4 API, RBAC, and route-boundary tests."""

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
from sqlalchemy.exc import OperationalError


ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

_TEMP_DATABASE_DIR = tempfile.TemporaryDirectory(prefix="datahub-p3-m2-4-")
_DATABASE_PATH = Path(_TEMP_DATABASE_DIR.name) / "p3-reuse-api.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_DATABASE_PATH}"

from app import p3_reuse_routes as routes_module  # noqa: E402
from app.auth import (  # noqa: E402
    Permission,
    ROLE_PERMISSIONS,
    ROLE_TOKEN_ENV,
    Role,
)
from app.database import SessionLocal, engine, get_db  # noqa: E402
from app.db_models import KnowledgeCandidate, ReviewRecord  # noqa: E402
from app.main import app  # noqa: E402
from app.p3_reuse_models import ReuseProject, ReuseSourceItem  # noqa: E402


PROJECTS_PATH = "/api/p3/reuse-projects"
TOKENS = {
    role: f"p3-m2-4-{role.value}-token"
    for role in Role
}


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
        db.query(ReuseSourceItem).delete()
        db.query(ReuseProject).delete()
        db.query(ReviewRecord).delete()
        db.query(KnowledgeCandidate).delete()
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


def _create_project(
    client: TestClient,
    *,
    key: str = "route-project-key",
    name: str = "客服培训项目",
    headers: dict[str, str] | None = None,
) -> dict[str, object]:
    response = client.post(
        PROJECTS_PATH,
        json={
            "name": name,
            "description": "P3 route test",
            "idempotency_key": key,
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


def _seed_p1(
    *,
    candidate_id: str = "route_candidate",
    status: str = "approved",
) -> None:
    snapshot = {
        "candidate_id": candidate_id,
        "source_type": "sanitized_batch",
        "source_batch_id": "route_batch",
        "knowledge_type": "faq",
        "question": "How long does shipping take?",
        "answer": "Shipping takes five business days.",
        "intent": "shipping",
        "tags": ["policy", "shipping"],
        "risk_level": "low",
    }
    db = SessionLocal()
    try:
        db.add(
            KnowledgeCandidate(
                id=candidate_id,
                source_type="sanitized_batch",
                source_id="route_batch",
                question=snapshot["question"],
                answer=snapshot["answer"],
                intent=snapshot["intent"],
                tags=snapshot["tags"],
                risk_level=snapshot["risk_level"],
                quality_score=0.95,
                status=status,
                metadata_json={
                    "source_batch_id": "route_batch",
                    "knowledge_type": "faq",
                },
            )
        )
        db.add(
            ReviewRecord(
                id=f"review_{candidate_id}",
                candidate_id=candidate_id,
                reviewer="route_reviewer",
                action="approved",
                snapshot_json=snapshot,
            )
        )
        db.commit()
    finally:
        db.close()


def _add_p1_source(
    client: TestClient,
    project_id: str,
    *,
    candidate_id: str = "route_candidate",
) -> dict[str, object]:
    response = client.post(
        f"{PROJECTS_PATH}/{project_id}/sources",
        json={
            "source_type": "P1_KNOWLEDGE",
            "source_id": candidate_id,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


def test_project_crud_pagination_and_idempotency(client: TestClient) -> None:
    project = _create_project(client)
    replay = _create_project(client)
    assert replay["id"] == project["id"]
    assert project["status"] == "draft"

    conflict = client.post(
        PROJECTS_PATH,
        json={
            "name": "不同项目",
            "description": "P3 route test",
            "idempotency_key": "route-project-key",
        },
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "P3_PROJECT_IDEMPOTENCY_CONFLICT"

    updated = client.patch(
        f"{PROJECTS_PATH}/{project['id']}",
        json={"name": "更新后的培训项目", "description": None},
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["name"] == "更新后的培训项目"
    assert updated.json()["data"]["description"] is None

    page = client.get(PROJECTS_PATH, params={"limit": 1, "offset": 0})
    assert page.status_code == 200
    assert page.json()["data"]["total"] == 1
    assert page.json()["data"]["limit"] == 1
    assert client.get(f"{PROJECTS_PATH}/missing").status_code == 404


def test_create_and_update_reject_caller_controlled_fields(
    client: TestClient,
) -> None:
    rejected_create = client.post(
        PROJECTS_PATH,
        json={
            "name": "Unsafe",
            "idempotency_key": "unsafe-create",
            "status": "active",
        },
    )
    assert rejected_create.status_code == 422
    project = _create_project(client, key="safe-update")
    rejected_update = client.patch(
        f"{PROJECTS_PATH}/{project['id']}",
        json={"status": "archived"},
    )
    assert rejected_update.status_code == 422


def test_add_list_get_remove_source_and_governed_evidence(
    client: TestClient,
) -> None:
    _seed_p1()
    project = _create_project(client, key="source-flow")
    source = _add_p1_source(client, str(project["id"]))
    assert source["source_fingerprint"]
    assert source["approved_review_id"] == "review_route_candidate"
    assert source["source_trace"]["source_id"] == "route_candidate"
    assert "answer" not in source["source_trace"]

    page = client.get(f"{PROJECTS_PATH}/{project['id']}/sources")
    assert page.status_code == 200
    assert page.json()["data"]["total"] == 1
    fetched = client.get(
        f"{PROJECTS_PATH}/{project['id']}/sources/{source['id']}"
    )
    assert fetched.status_code == 200

    removed = client.delete(
        f"{PROJECTS_PATH}/{project['id']}/sources/{source['id']}"
    )
    assert removed.status_code == 200
    assert removed.json()["data"]["removed_at"] is not None
    assert client.get(
        f"{PROJECTS_PATH}/{project['id']}/sources"
    ).json()["data"]["total"] == 0
    included = client.get(
        f"{PROJECTS_PATH}/{project['id']}/sources",
        params={"include_removed": True},
    )
    assert included.json()["data"]["total"] == 1
    db = SessionLocal()
    try:
        assert db.query(ReuseSourceItem).count() == 1
    finally:
        db.close()


def test_add_source_rejects_forged_evidence_and_raw_bad_case(
    client: TestClient,
) -> None:
    project = _create_project(client, key="source-rejection")
    forged = client.post(
        f"{PROJECTS_PATH}/{project['id']}/sources",
        json={
            "source_type": "P1_KNOWLEDGE",
            "source_id": "missing",
            "approved": True,
            "source_trace": {"eligible": True},
        },
    )
    assert forged.status_code == 422
    raw = client.post(
        f"{PROJECTS_PATH}/{project['id']}/sources",
        json={"source_type": "RAW_BAD_CASE", "source_id": "bad_raw"},
    )
    assert raw.status_code == 409
    assert raw.json()["detail"]["code"] == "P3_SOURCE_INELIGIBLE"
    assert (
        raw.json()["detail"]["details"]["reason_code"]
        == "RAW_BAD_CASE_NOT_ALLOWED"
    )


def test_revalidate_marks_stale_and_activation_stays_draft(
    client: TestClient,
) -> None:
    _seed_p1()
    project = _create_project(client, key="stale-flow")
    source = _add_p1_source(client, str(project["id"]))
    db = SessionLocal()
    try:
        db.get(KnowledgeCandidate, "route_candidate").status = "archived"
        db.commit()
    finally:
        db.close()

    revalidated = client.post(
        f"{PROJECTS_PATH}/{project['id']}/sources/{source['id']}/revalidate"
    )
    assert revalidated.status_code == 200
    assert revalidated.json()["data"]["status"] == "stale"
    assert revalidated.json()["data"]["source_stale"] is True
    activation = client.post(f"{PROJECTS_PATH}/{project['id']}/activate")
    assert activation.status_code == 409
    assert activation.json()["detail"]["code"] == "P3_SOURCE_STALE"
    assert client.get(
        f"{PROJECTS_PATH}/{project['id']}"
    ).json()["data"]["status"] == "draft"


def test_batch_revalidate_and_active_project_freezes_sources(
    client: TestClient,
) -> None:
    _seed_p1()
    project = _create_project(client, key="activation-flow")
    source = _add_p1_source(client, str(project["id"]))
    batch = client.post(
        f"{PROJECTS_PATH}/{project['id']}/sources/revalidate",
        json={"limit": 100},
    )
    assert batch.status_code == 200
    assert batch.json()["data"]["total"] == 1
    assert batch.json()["data"]["results"][0]["status"] == "valid"
    over_limit = client.post(
        f"{PROJECTS_PATH}/{project['id']}/sources/revalidate",
        json={"limit": 101},
    )
    assert over_limit.status_code == 422
    assert over_limit.json()["detail"]["code"] == "P3_SOURCE_LIMIT_EXCEEDED"

    activated = client.post(f"{PROJECTS_PATH}/{project['id']}/activate")
    assert activated.status_code == 200
    assert activated.json()["data"]["status"] == "active"
    assert client.delete(
        f"{PROJECTS_PATH}/{project['id']}/sources/{source['id']}"
    ).status_code == 409
    assert client.post(
        f"{PROJECTS_PATH}/{project['id']}/sources",
        json={"source_type": "P1_KNOWLEDGE", "source_id": "route_candidate"},
    ).status_code == 409


def test_archive_is_terminal(client: TestClient) -> None:
    _seed_p1()
    project = _create_project(client, key="archive-flow")
    _add_p1_source(client, str(project["id"]))
    assert client.post(
        f"{PROJECTS_PATH}/{project['id']}/activate"
    ).status_code == 200
    archived = client.post(f"{PROJECTS_PATH}/{project['id']}/archive")
    assert archived.status_code == 200
    assert archived.json()["data"]["status"] == "archived"
    assert client.patch(
        f"{PROJECTS_PATH}/{project['id']}",
        json={"name": "Forbidden"},
    ).status_code == 409


def test_token_mode_401_and_read_matrix(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_token_auth(monkeypatch)
    assert client.get(PROJECTS_PATH).status_code == 401
    invalid = client.get(
        PROJECTS_PATH,
        headers={"Authorization": "Bearer invalid-secret-token"},
    )
    assert invalid.status_code == 401
    assert "invalid-secret-token" not in invalid.text
    for role in Role:
        assert client.get(
            PROJECTS_PATH,
            headers=_headers(role),
        ).status_code == 200


@pytest.mark.parametrize("role", [Role.REVIEWER, Role.VIEWER, Role.SERVICE])
def test_read_only_roles_cannot_write(
    role: Role,
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_token_auth(monkeypatch)
    response = client.post(
        PROJECTS_PATH,
        json={"name": "Forbidden", "idempotency_key": f"forbidden-{role.value}"},
        headers=_headers(role),
    )
    assert response.status_code == 403


def test_cleaner_can_manage_and_activate_but_cannot_archive(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_token_auth(monkeypatch)
    project = _create_project(
        client,
        key="cleaner-project",
        headers=_headers(Role.CLEANER),
    )
    assert client.post(
        f"{PROJECTS_PATH}/{project['id']}/archive",
        headers=_headers(Role.CLEANER),
    ).status_code == 403
    assert Permission.P3_PROJECT_ARCHIVE in ROLE_PERMISSIONS[Role.ADMIN]
    assert Permission.P3_PROJECT_ARCHIVE not in ROLE_PERMISSIONS[Role.CLEANER]


def test_storage_error_is_safe(client: TestClient) -> None:
    unsafe = "postgresql://user:password@internal/datahub"
    with patch.object(
        routes_module.P3ReuseService,
        "get_project",
        side_effect=OperationalError(unsafe, {}, RuntimeError(unsafe)),
    ):
        response = client.get(f"{PROJECTS_PATH}/storage-error")
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "P3_STORAGE_UNAVAILABLE"
    assert "password" not in response.text.lower()
    assert "postgresql://" not in response.text.lower()


def test_routes_only_orchestrate_service_and_do_not_expose_content() -> None:
    source = inspect.getsource(routes_module).lower()
    assert "p3_reuse_repositories" not in source
    assert "p3_source_eligibility." not in source
    assert ".query(" not in source
    for forbidden in ("embedding", "provider", "retrieval", "token_hash"):
        assert forbidden not in source


def test_openapi_registers_bounded_rbac_endpoints() -> None:
    schema = app.openapi()
    expected = {
        PROJECTS_PATH: {"get", "post"},
        f"{PROJECTS_PATH}/{{project_id}}": {"get", "patch"},
        f"{PROJECTS_PATH}/{{project_id}}/activate": {"post"},
        f"{PROJECTS_PATH}/{{project_id}}/archive": {"post"},
        f"{PROJECTS_PATH}/{{project_id}}/sources": {"get", "post"},
        f"{PROJECTS_PATH}/{{project_id}}/sources/{{source_item_id}}": {
            "get",
            "delete",
        },
        (
            f"{PROJECTS_PATH}/{{project_id}}/sources/"
            "{source_item_id}/revalidate"
        ): {"post"},
        f"{PROJECTS_PATH}/{{project_id}}/sources/revalidate": {"post"},
    }
    for path, methods in expected.items():
        assert methods.issubset(schema["paths"][path])
        for method in methods:
            assert schema["paths"][path][method]["security"] == [
                {"DataHubBearer": []}
            ]
    assert Permission.P3_PROJECT_READ.value == "p3.project.read"
    assert Permission.P3_PROJECT_WRITE.value == "p3.project.write"
    assert Permission.P3_SOURCE_MANAGE.value == "p3.source.manage"
    assert Permission.P3_PROJECT_ACTIVATE.value == "p3.project.activate"
    assert Permission.P3_PROJECT_ARCHIVE.value == "p3.project.archive"

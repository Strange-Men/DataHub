"""Focused P3-M6.3 publication API, RBAC, and route-boundary tests."""

from __future__ import annotations

import inspect
import sys
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
    _enable_token_auth,
    _generate,
    _headers,
    cleanup_temporary_database,
    client,
)

from app import p3_publication_routes as routes_module  # noqa: E402
from app.auth import Permission, ROLE_PERMISSIONS, Role  # noqa: E402
from app.db_models import KnowledgeCandidate, ReviewRecord  # noqa: E402
from app.main import app  # noqa: E402
from app.p3_publication_service import (  # noqa: E402
    P3PublicationService,
    P3PublicationServiceError,
)
from app.p3_reuse_models import (  # noqa: E402
    ReuseAssetVersion,
    ReuseAssetVersionStatus,
    ReuseReview,
    ReuseSourceItem,
)


ALL_TRUE = {
    "structure_complete": True,
    "source_refs_valid": True,
    "no_unsupported_claims_confirmed": True,
    "safe_for_reuse": True,
}


def _publish_path(project_id: str, asset_id: str) -> str:
    return f"{PROJECTS_PATH}/{project_id}/assets/{asset_id}/publish"


def _archive_path(project_id: str, asset_id: str) -> str:
    return f"{PROJECTS_PATH}/{project_id}/assets/{asset_id}/archive"


def _published_path(project_id: str, asset_type: str | None = None) -> str:
    path = f"{PROJECTS_PATH}/{project_id}/published-assets"
    return f"{path}/{asset_type}" if asset_type else path


def _approve(
    client: TestClient,
    project_id: str,
    asset_id: str,
    *,
    suffix: str,
) -> None:
    submitted = client.post(
        f"{PROJECTS_PATH}/{project_id}/assets/{asset_id}/submit-review",
        json={"idempotency_key": f"m63_submit_{suffix}"},
    )
    assert submitted.status_code == 200, submitted.text
    reviewed = client.post(
        f"{PROJECTS_PATH}/{project_id}/assets/{asset_id}/review",
        json={
            "decision": "approved",
            "comments": None,
            "checklist": ALL_TRUE,
            "idempotency_key": f"m63_review_{suffix}",
        },
    )
    assert reviewed.status_code == 201, reviewed.text


def _actual_asset(
    client: TestClient,
    *,
    suffix: str,
    asset_type: str = "training_material",
    approve: bool = True,
) -> tuple[dict[str, object], dict[str, object]]:
    project, _source = _create_active_project(
        client,
        project_key=f"m63_project_{suffix}",
        candidate_id=f"m63_candidate_{suffix}",
    )
    generated = _generate(
        client,
        str(project["id"]),
        asset_type=asset_type,
        key=f"m63_generation_{suffix}",
    )
    assert generated.status_code == 201, generated.text
    asset = generated.json()["data"]
    if approve:
        _approve(
            client,
            str(project["id"]),
            str(asset["id"]),
            suffix=suffix,
        )
    return project, asset


def _generate_approved(
    client: TestClient,
    project_id: str,
    *,
    suffix: str,
    asset_type: str = "training_material",
) -> dict[str, object]:
    generated = _generate(
        client,
        project_id,
        asset_type=asset_type,
        key=f"m63_generation_{suffix}",
    )
    assert generated.status_code == 201, generated.text
    asset = generated.json()["data"]
    _approve(client, project_id, str(asset["id"]), suffix=suffix)
    return asset


def _publish(
    client: TestClient,
    project_id: str,
    asset_id: str,
    *,
    key: str,
    headers: dict[str, str] | None = None,
):
    return client.post(
        _publish_path(project_id, asset_id),
        json={"idempotency_key": key},
        headers=headers,
    )


def _archive(
    client: TestClient,
    project_id: str,
    asset_id: str,
    *,
    key: str,
    headers: dict[str, str] | None = None,
):
    return client.post(
        _archive_path(project_id, asset_id),
        json={"idempotency_key": key},
        headers=headers,
    )


def test_auth_disabled_publish_read_and_archive_compatibility(
    client: TestClient,
) -> None:
    project, asset = _actual_asset(client, suffix="disabled")
    project_id = str(project["id"])
    asset_id = str(asset["id"])

    published = _publish(
        client,
        project_id,
        asset_id,
        key="m63_publish_disabled",
    )
    assert published.status_code == 200, published.text
    assert published.json()["data"]["asset"]["status"] == "published"
    assert client.get(_published_path(project_id)).status_code == 200
    assert (
        client.get(_published_path(project_id, "training_material")).status_code
        == 200
    )

    archived = _archive(
        client,
        project_id,
        asset_id,
        key="m63_archive_disabled",
    )
    assert archived.status_code == 200, archived.text
    assert archived.json()["data"]["asset"]["status"] == "archived"


@pytest.mark.parametrize(
    "role",
    [Role.CLEANER, Role.REVIEWER, Role.VIEWER, Role.SERVICE],
)
def test_only_admin_can_publish(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    role: Role,
) -> None:
    project, asset = _actual_asset(client, suffix=f"publish_{role.value}")
    _enable_token_auth(monkeypatch)
    response = _publish(
        client,
        str(project["id"]),
        str(asset["id"]),
        key=f"m63_publish_forbidden_{role.value}",
        headers=_headers(role),
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "AUTHORIZATION_DENIED"


@pytest.mark.parametrize(
    "role",
    [Role.CLEANER, Role.REVIEWER, Role.VIEWER, Role.SERVICE],
)
def test_only_admin_can_archive(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    role: Role,
) -> None:
    project, asset = _actual_asset(client, suffix=f"archive_{role.value}")
    project_id = str(project["id"])
    asset_id = str(asset["id"])
    published = _publish(
        client,
        project_id,
        asset_id,
        key=f"m63_publish_before_archive_{role.value}",
    )
    assert published.status_code == 200
    _enable_token_auth(monkeypatch)
    response = _archive(
        client,
        project_id,
        asset_id,
        key=f"m63_archive_forbidden_{role.value}",
        headers=_headers(role),
    )
    assert response.status_code == 403


def test_admin_can_publish_and_archive_in_token_mode(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project, asset = _actual_asset(client, suffix="admin_token")
    project_id = str(project["id"])
    asset_id = str(asset["id"])
    _enable_token_auth(monkeypatch)

    published = _publish(
        client,
        project_id,
        asset_id,
        key="m63_publish_admin",
        headers=_headers(Role.ADMIN),
    )
    assert published.status_code == 200, published.text
    assert published.json()["data"]["asset"]["published_by_role"] == "admin"
    archived = _archive(
        client,
        project_id,
        asset_id,
        key="m63_archive_admin",
        headers=_headers(Role.ADMIN),
    )
    assert archived.status_code == 200, archived.text


@pytest.mark.parametrize("role", list(Role))
def test_all_five_roles_can_read_current_published(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    role: Role,
) -> None:
    project, asset = _actual_asset(client, suffix=f"read_{role.value}")
    project_id = str(project["id"])
    assert (
        _publish(
            client,
            project_id,
            str(asset["id"]),
            key=f"m63_publish_read_{role.value}",
        ).status_code
        == 200
    )
    _enable_token_auth(monkeypatch)
    assert (
        client.get(_published_path(project_id), headers=_headers(role)).status_code
        == 200
    )
    assert (
        client.get(
            _published_path(project_id, "training_material"),
            headers=_headers(role),
        ).status_code
        == 200
    )


def test_token_mode_missing_and_wrong_token_are_401(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_token_auth(monkeypatch)
    missing = client.get(_published_path("project"))
    wrong = client.get(
        _published_path("project"),
        headers={"Authorization": "Bearer wrong"},
    )
    assert missing.status_code == 401
    assert wrong.status_code == 401
    assert missing.json()["detail"]["code"] == "AUTHENTICATION_REQUIRED"


def test_nonapproved_missing_review_hash_drift_and_stale_are_409(
    client: TestClient,
) -> None:
    project, generated = _actual_asset(
        client,
        suffix="generated",
        approve=False,
    )
    generated_response = _publish(
        client,
        str(project["id"]),
        str(generated["id"]),
        key="m63_publish_generated",
    )
    assert generated_response.status_code == 409
    assert (
        generated_response.json()["detail"]["code"]
        == "P3_PUBLICATION_ASSET_STATE_INVALID"
    )

    project, missing = _actual_asset(client, suffix="missing", approve=False)
    db = SessionLocal()
    try:
        row = db.get(ReuseAssetVersion, str(missing["id"]))
        assert row is not None
        row.status = ReuseAssetVersionStatus.APPROVED
        db.commit()
    finally:
        db.close()
    missing_response = _publish(
        client,
        str(project["id"]),
        str(missing["id"]),
        key="m63_publish_missing_review",
    )
    assert missing_response.status_code == 409
    assert (
        missing_response.json()["detail"]["code"]
        == "P3_PUBLICATION_REVIEW_MISSING"
    )

    project, drifted = _actual_asset(client, suffix="review_drift")
    db = SessionLocal()
    try:
        review = (
            db.query(ReuseReview)
            .filter(ReuseReview.asset_version_id == str(drifted["id"]))
            .one()
        )
        review.reviewed_content_hash = "f" * 64
        db.commit()
    finally:
        db.close()
    drift_response = _publish(
        client,
        str(project["id"]),
        str(drifted["id"]),
        key="m63_publish_review_drift",
    )
    assert drift_response.status_code == 409
    assert (
        drift_response.json()["detail"]["code"]
        == "P3_PUBLICATION_REVIEW_HASH_MISMATCH"
    )

    project, stale = _actual_asset(client, suffix="stale")
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
    stale_response = _publish(
        client,
        str(project["id"]),
        str(stale["id"]),
        key="m63_publish_stale",
    )
    assert stale_response.status_code == 409
    assert (
        stale_response.json()["detail"]["code"]
        == "P3_PUBLICATION_SOURCE_STALE"
    )


def test_replacement_supersedes_old_and_asset_types_have_separate_currents(
    client: TestClient,
) -> None:
    project, first = _actual_asset(client, suffix="replacement")
    project_id = str(project["id"])
    assert (
        _publish(
            client,
            project_id,
            str(first["id"]),
            key="m63_publish_first",
        ).status_code
        == 200
    )
    second = _generate_approved(
        client,
        project_id,
        suffix="replacement_second",
    )
    second_response = _publish(
        client,
        project_id,
        str(second["id"]),
        key="m63_publish_second",
    )
    assert second_response.status_code == 200, second_response.text
    assert (
        second_response.json()["data"]["superseded_asset_version_id"]
        == first["id"]
    )

    qa = _generate_approved(
        client,
        project_id,
        suffix="replacement_qa",
        asset_type="qa_bank",
    )
    assert (
        _publish(
            client,
            project_id,
            str(qa["id"]),
            key="m63_publish_qa",
        ).status_code
        == 200
    )
    current = client.get(_published_path(project_id))
    assert current.status_code == 200
    assert current.json()["data"]["total"] == 2

    db = SessionLocal()
    try:
        old = db.get(ReuseAssetVersion, str(first["id"]))
        assert old is not None
        assert old.status is ReuseAssetVersionStatus.SUPERSEDED
        assert old.superseded_by_asset_version_id == second["id"]
    finally:
        db.close()


def test_publish_and_archive_idempotency_and_conflicts(
    client: TestClient,
) -> None:
    project, first = _actual_asset(client, suffix="idempotency")
    project_id = str(project["id"])
    first_publish = _publish(
        client,
        project_id,
        str(first["id"]),
        key="m63_shared_publish",
    )
    replay = _publish(
        client,
        project_id,
        str(first["id"]),
        key="m63_shared_publish",
    )
    assert first_publish.status_code == replay.status_code == 200
    assert replay.json()["data"]["replayed"] is True

    second = _generate_approved(client, project_id, suffix="idempotency_second")
    conflict = _publish(
        client,
        project_id,
        str(second["id"]),
        key="m63_shared_publish",
    )
    assert conflict.status_code == 409
    assert (
        conflict.json()["detail"]["code"]
        == "P3_PUBLICATION_IDEMPOTENCY_CONFLICT"
    )
    assert (
        _publish(
            client,
            project_id,
            str(second["id"]),
            key="m63_publish_second_valid",
        ).status_code
        == 200
    )

    archived = _archive(
        client,
        project_id,
        str(second["id"]),
        key="m63_shared_archive",
    )
    replayed_archive = _archive(
        client,
        project_id,
        str(second["id"]),
        key="m63_shared_archive",
    )
    assert archived.status_code == replayed_archive.status_code == 200
    assert replayed_archive.json()["data"]["replayed"] is True

    archive_conflict = _archive(
        client,
        project_id,
        str(first["id"]),
        key="m63_shared_archive",
    )
    assert archive_conflict.status_code == 409


def test_archive_current_leaves_no_current_and_versions_cannot_republish(
    client: TestClient,
) -> None:
    project, first = _actual_asset(client, suffix="archive_current")
    project_id = str(project["id"])
    first_id = str(first["id"])
    assert (
        _publish(
            client,
            project_id,
            first_id,
            key="m63_publish_archive_first",
        ).status_code
        == 200
    )
    second = _generate_approved(
        client,
        project_id,
        suffix="archive_current_second",
    )
    second_id = str(second["id"])
    assert (
        _publish(
            client,
            project_id,
            second_id,
            key="m63_publish_archive_second",
        ).status_code
        == 200
    )
    assert (
        _archive(
            client,
            project_id,
            second_id,
            key="m63_archive_current",
        ).status_code
        == 200
    )

    listing = client.get(_published_path(project_id))
    assert listing.status_code == 200
    assert listing.json()["data"]["items"] == []
    assert client.get(
        _published_path(project_id, "training_material")
    ).status_code == 404

    archived_retry = _publish(
        client,
        project_id,
        second_id,
        key="m63_republish_archived",
    )
    superseded_retry = _publish(
        client,
        project_id,
        first_id,
        key="m63_republish_superseded",
    )
    assert archived_retry.status_code == 409
    assert (
        archived_retry.json()["detail"]["code"]
        == "P3_PUBLICATION_ASSET_ARCHIVED"
    )
    assert superseded_retry.status_code == 409
    assert (
        superseded_retry.json()["detail"]["code"]
        == "P3_PUBLICATION_ALREADY_SUPERSEDED"
    )


def test_published_list_pagination_filter_and_validation(
    client: TestClient,
) -> None:
    project, first = _actual_asset(client, suffix="page")
    project_id = str(project["id"])
    assert (
        _publish(
            client,
            project_id,
            str(first["id"]),
            key="m63_page_first",
        ).status_code
        == 200
    )
    qa = _generate_approved(
        client,
        project_id,
        suffix="page_qa",
        asset_type="qa_bank",
    )
    assert (
        _publish(
            client,
            project_id,
            str(qa["id"]),
            key="m63_page_qa",
        ).status_code
        == 200
    )

    page = client.get(
        _published_path(project_id),
        params={"limit": 1, "offset": 1},
    )
    filtered = client.get(
        _published_path(project_id),
        params={"asset_type": "qa_bank"},
    )
    assert page.status_code == 200
    assert len(page.json()["data"]["items"]) == 1
    assert page.json()["data"]["total"] == 2
    assert filtered.status_code == 200
    assert filtered.json()["data"]["total"] == 1
    assert filtered.json()["data"]["items"][0]["asset_type"] == "qa_bank"
    assert (
        client.get(
            _published_path(project_id),
            params={"limit": 101},
        ).status_code
        == 422
    )
    assert (
        client.get(
            _published_path(project_id),
            params={"asset_type": "invalid"},
        ).status_code
        == 422
    )


def test_request_forbids_forged_governance_fields(client: TestClient) -> None:
    project, asset = _actual_asset(client, suffix="forged")
    for field, value in (
        ("status", "published"),
        ("published_by_role", "admin"),
        ("content_hash", "f" * 64),
        ("source_trace", {}),
        ("superseded_by_asset_version_id", "forged"),
    ):
        response = client.post(
            _publish_path(str(project["id"]), str(asset["id"])),
            json={
                "idempotency_key": f"m63_forged_{field}",
                field: value,
            },
        )
        assert response.status_code == 422


def test_openapi_registers_four_publication_paths(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert (
        "/api/p3/reuse-projects/{project_id}/assets/"
        "{asset_version_id}/publish"
    ) in paths
    assert (
        "/api/p3/reuse-projects/{project_id}/assets/"
        "{asset_version_id}/archive"
    ) in paths
    assert "/api/p3/reuse-projects/{project_id}/published-assets" in paths
    assert (
        "/api/p3/reuse-projects/{project_id}/published-assets/{asset_type}"
        in paths
    )


def test_permission_matrix_is_centralized_and_existing_asset_read_unchanged() -> None:
    assert Permission.P3_ASSET_READ.value == "p3.asset.read"
    for role in Role:
        assert Permission.P3_ASSET_READ_PUBLISHED in ROLE_PERMISSIONS[role]
    for role in (Role.CLEANER, Role.REVIEWER, Role.VIEWER, Role.SERVICE):
        assert Permission.P3_ASSET_PUBLISH not in ROLE_PERMISSIONS[role]
        assert Permission.P3_ASSET_ARCHIVE not in ROLE_PERMISSIONS[role]
    assert Permission.P3_ASSET_PUBLISH in ROLE_PERMISSIONS[Role.ADMIN]
    assert Permission.P3_ASSET_ARCHIVE in ROLE_PERMISSIONS[Role.ADMIN]


def test_route_is_thin_and_calls_only_publication_service() -> None:
    source = inspect.getsource(routes_module)
    assert "P3PublicationService" in source
    assert "Repository" not in source
    assert "ReuseAssetVersion" not in source
    assert ".query(" not in source
    assert ".commit(" not in source
    assert "content_hash" not in source
    assert "source_manifest_hash" not in source
    assert "Provider" not in source
    assert "Retrieval" not in source
    assert "Export" not in source


def test_actual_flow_does_not_modify_p1_or_write_export_rows(
    client: TestClient,
) -> None:
    project, asset = _actual_asset(client, suffix="frozen")
    db = SessionLocal()
    try:
        before = (
            db.query(KnowledgeCandidate).count(),
            db.query(ReviewRecord).count(),
        )
    finally:
        db.close()
    assert (
        _publish(
            client,
            str(project["id"]),
            str(asset["id"]),
            key="m63_publish_frozen",
        ).status_code
        == 200
    )
    db = SessionLocal()
    try:
        after = (
            db.query(KnowledgeCandidate).count(),
            db.query(ReviewRecord).count(),
        )
        export_counts = (
            db.execute(
                __import__("sqlalchemy").text(
                    "SELECT COUNT(*) FROM export_jobs"
                )
            ).scalar_one(),
            db.execute(
                __import__("sqlalchemy").text(
                    "SELECT COUNT(*) FROM export_artifacts"
                )
            ).scalar_one(),
        )
        tables = {
            row[0]
            for row in db.execute(
                __import__("sqlalchemy").text(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            )
        }
    finally:
        db.close()
    assert after == before
    assert {"export_jobs", "export_artifacts"}.issubset(tables)
    assert export_counts == (0, 0)


def test_service_error_mapping_and_unknown_error_are_safe(
    client: TestClient,
) -> None:
    with patch.object(
        P3PublicationService,
        "get_current_published_asset",
        side_effect=P3PublicationServiceError(
            "P3_PUBLICATION_STORAGE_UNAVAILABLE",
            "Safe storage failure.",
            {"project_id": "project"},
        ),
    ):
        unavailable = client.get(
            _published_path("project", "training_material")
        )
    assert unavailable.status_code == 503
    assert "sqlite" not in unavailable.text.lower()
    assert "password" not in unavailable.text.lower()

    with patch.object(
        P3PublicationService,
        "get_current_published_asset",
        side_effect=RuntimeError("secret-token sqlite:///private.db"),
    ):
        internal = client.get(_published_path("project", "training_material"))
    assert internal.status_code == 500
    assert internal.json()["detail"]["code"] == "P3_PUBLICATION_INTERNAL_ERROR"
    assert "secret-token" not in internal.text
    assert "private.db" not in internal.text

"""Focused P3-M5.4 manual revision/review API and RBAC tests."""

from __future__ import annotations

import copy
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
    _enable_token_auth,
    _generate,
    _headers,
    cleanup_temporary_database,
    client,
)

from app import p3_review_routes as routes_module  # noqa: E402
from app.auth import Permission, ROLE_PERMISSIONS, Role  # noqa: E402
from app.db_models import KnowledgeCandidate  # noqa: E402
from app.main import app  # noqa: E402
from app.p3_review_service import (  # noqa: E402
    P3ReviewService,
    P3ReviewServiceError,
)
from app.p3_reuse_models import (  # noqa: E402
    ReuseAssetType,
    ReuseAssetVersion,
    ReuseAssetVersionStatus,
    ReuseGenerationMode,
    ReuseReview,
    ReuseReviewDecision,
    ReuseSourceItem,
)


def _revision_path(project_id: str, asset_id: str) -> str:
    return f"{PROJECTS_PATH}/{project_id}/assets/{asset_id}/revisions"


def _submit_path(project_id: str, asset_id: str) -> str:
    return f"{PROJECTS_PATH}/{project_id}/assets/{asset_id}/submit-review"


def _decision_path(project_id: str, asset_id: str) -> str:
    return f"{PROJECTS_PATH}/{project_id}/assets/{asset_id}/review"


def _reviews_path(project_id: str, asset_id: str) -> str:
    return f"{PROJECTS_PATH}/{project_id}/assets/{asset_id}/reviews"


def _checklist(all_true: bool = True) -> dict[str, bool]:
    return {
        "structure_complete": all_true,
        "source_refs_valid": True,
        "no_unsupported_claims_confirmed": True,
        "safe_for_reuse": True,
    }


def _revision_request(
    content_payload: dict[str, object],
    *,
    key: str = "m54_revision_key",
    **extra: object,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "content_payload": content_payload,
        "idempotency_key": key,
    }
    payload.update(extra)
    return payload


def _decision_request(
    *,
    decision: str = "approved",
    key: str = "m54_review_key",
    comments: str | None = None,
    checklist: dict[str, bool] | None = None,
    **extra: object,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "decision": decision,
        "comments": comments,
        "checklist": checklist or _checklist(decision == "approved"),
        "idempotency_key": key,
    }
    payload.update(extra)
    return payload


def _fake_version(
    project_id: str = "m54_project",
    *,
    version_id: str = "m54_version",
    mode: ReuseGenerationMode = ReuseGenerationMode.MANUAL_REVISION,
    status: ReuseAssetVersionStatus = ReuseAssetVersionStatus.GENERATED,
) -> ReuseAssetVersion:
    now = datetime.now(UTC).replace(tzinfo=None)
    return ReuseAssetVersion(
        id=version_id,
        project_id=project_id,
        asset_type=ReuseAssetType.TRAINING_MATERIAL,
        version_number=2,
        status=status,
        generation_mode=mode,
        template_key="p3.manual_revision",
        template_version="v1",
        content_payload={},
        content_hash="a" * 64,
        source_manifest_hash="b" * 64,
        idempotency_key=f"key_{version_id}",
        created_by_role="cleaner",
        request_id=f"request_{version_id}",
        created_at=now,
        updated_at=now,
        parent_asset_version_id="m54_parent",
    )


def _fake_review(
    version_id: str = "m54_version",
    *,
    decision: ReuseReviewDecision = ReuseReviewDecision.APPROVED,
) -> ReuseReview:
    return ReuseReview(
        id=f"review_{version_id}",
        asset_version_id=version_id,
        decision=decision,
        comments=None,
        checklist_payload=_checklist(True),
        review_policy_version="p3-review-v1",
        reviewed_content_hash="a" * 64,
        reviewed_source_manifest_hash="b" * 64,
        reviewer_role="reviewer",
        request_id=f"request_review_{version_id}",
        idempotency_key=f"key_review_{version_id}",
        created_at=datetime.now(UTC).replace(tzinfo=None),
    )


def _actual_generated(
    client: TestClient,
    *,
    suffix: str = "default",
) -> tuple[dict[str, object], dict[str, object]]:
    project, _source = _create_active_project(
        client,
        project_key=f"m54_project_{suffix}",
        candidate_id=f"m54_candidate_{suffix}",
    )
    generated = _generate(
        client,
        str(project["id"]),
        key=f"m54_generation_{suffix}",
    )
    assert generated.status_code == 201, generated.text
    return project, generated.json()["data"]


def _revised_payload(asset: dict[str, object], title: str) -> dict[str, object]:
    payload = copy.deepcopy(asset["content_payload"])
    assert isinstance(payload, dict)
    payload["title"] = title
    return payload


@pytest.mark.parametrize("role", [Role.ADMIN, Role.CLEANER])
def test_admin_and_cleaner_can_create_manual_revision(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    role: Role,
) -> None:
    _enable_token_auth(monkeypatch)
    version = _fake_version()
    with patch.object(
        P3ReviewService,
        "create_manual_revision",
        return_value=version,
    ) as operation:
        response = client.post(
            _revision_path(version.project_id, "parent"),
            json=_revision_request({}),
            headers=_headers(role),
        )
    assert response.status_code == 201
    assert operation.call_args.kwargs["actor_role"] == role.value


@pytest.mark.parametrize(
    "role",
    [Role.REVIEWER, Role.VIEWER, Role.SERVICE],
)
def test_reviewer_viewer_service_cannot_edit(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    role: Role,
) -> None:
    _enable_token_auth(monkeypatch)
    with patch.object(P3ReviewService, "create_manual_revision") as operation:
        response = client.post(
            _revision_path("project", "parent"),
            json=_revision_request({}),
            headers=_headers(role),
        )
    assert response.status_code == 403
    operation.assert_not_called()


@pytest.mark.parametrize("role", [Role.ADMIN, Role.CLEANER])
def test_admin_and_cleaner_can_submit_review(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    role: Role,
) -> None:
    _enable_token_auth(monkeypatch)
    version = _fake_version(status=ReuseAssetVersionStatus.PENDING_REVIEW)
    with patch.object(
        P3ReviewService,
        "submit_for_review",
        return_value=version,
    ) as operation:
        response = client.post(
            _submit_path(version.project_id, version.id),
            json={},
            headers=_headers(role),
        )
    assert response.status_code == 200
    assert operation.call_count == 1


@pytest.mark.parametrize(
    "role",
    [Role.REVIEWER, Role.VIEWER, Role.SERVICE],
)
def test_reviewer_viewer_service_cannot_submit(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    role: Role,
) -> None:
    _enable_token_auth(monkeypatch)
    with patch.object(P3ReviewService, "submit_for_review") as operation:
        response = client.post(
            _submit_path("project", "asset"),
            json={},
            headers=_headers(role),
        )
    assert response.status_code == 403
    operation.assert_not_called()


@pytest.mark.parametrize("role", [Role.ADMIN, Role.REVIEWER])
def test_admin_and_reviewer_can_decide(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    role: Role,
) -> None:
    _enable_token_auth(monkeypatch)
    review = _fake_review()
    with patch.object(
        P3ReviewService,
        "decide_review",
        return_value=review,
    ) as operation:
        response = client.post(
            _decision_path("project", review.asset_version_id),
            json=_decision_request(),
            headers=_headers(role),
        )
    assert response.status_code == 201
    assert operation.call_args.kwargs["reviewer_role"] == role.value


@pytest.mark.parametrize(
    "role",
    [Role.CLEANER, Role.VIEWER, Role.SERVICE],
)
def test_cleaner_viewer_service_cannot_decide(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    role: Role,
) -> None:
    _enable_token_auth(monkeypatch)
    with patch.object(P3ReviewService, "decide_review") as operation:
        response = client.post(
            _decision_path("project", "asset"),
            json=_decision_request(),
            headers=_headers(role),
        )
    assert response.status_code == 403
    operation.assert_not_called()


@pytest.mark.parametrize("role", list(Role))
def test_all_five_roles_can_read_review(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    role: Role,
) -> None:
    _enable_token_auth(monkeypatch)
    review = _fake_review()
    with patch.object(
        P3ReviewService,
        "get_review",
        return_value=review,
    ):
        response = client.get(
            _reviews_path("project", review.asset_version_id),
            headers=_headers(role),
        )
    assert response.status_code == 200
    assert response.json()["data"]["decision"] == "approved"


def test_token_mode_requires_valid_bearer(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_token_auth(monkeypatch)
    missing = client.post(
        _revision_path("project", "asset"),
        json=_revision_request({}),
    )
    wrong = client.post(
        _decision_path("project", "asset"),
        json=_decision_request(),
        headers={"Authorization": "Bearer wrong-token"},
    )
    assert missing.status_code == 401
    assert wrong.status_code == 401


def test_auth_disabled_mode_remains_compatible(client: TestClient) -> None:
    version = _fake_version()
    with patch.object(
        P3ReviewService,
        "create_manual_revision",
        return_value=version,
    ) as operation:
        response = client.post(
            _revision_path(version.project_id, "parent"),
            json=_revision_request({}),
        )
    assert response.status_code == 201
    assert operation.call_args.kwargs["actor_role"] == Role.ADMIN.value


def test_complete_approved_flow_never_publishes(client: TestClient) -> None:
    project, parent = _actual_generated(client, suffix="approved")
    revision = client.post(
        _revision_path(str(project["id"]), str(parent["id"])),
        json=_revision_request(
            _revised_payload(parent, "Approved manual revision"),
            key="m54_approved_revision",
        ),
    )
    assert revision.status_code == 201, revision.text
    child = revision.json()["data"]
    submitted = client.post(
        _submit_path(str(project["id"]), str(child["id"])),
        json={"idempotency_key": "m54_approved_submit"},
    )
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["data"]["status"] == "pending_review"
    decision = client.post(
        _decision_path(str(project["id"]), str(child["id"])),
        json=_decision_request(key="m54_approved_decision"),
    )
    assert decision.status_code == 201, decision.text
    detail = client.get(
        f"{PROJECTS_PATH}/{project['id']}/assets/{child['id']}"
    )
    assert detail.status_code == 200
    assert detail.json()["data"]["status"] == "approved"
    assert detail.json()["data"]["published_at"] is None


def test_needs_revision_creates_child_and_preserves_parent(
    client: TestClient,
) -> None:
    project, parent = _actual_generated(client, suffix="revision")
    assert client.post(
        _submit_path(str(project["id"]), str(parent["id"])),
        json={},
    ).status_code == 200
    needs = client.post(
        _decision_path(str(project["id"]), str(parent["id"])),
        json=_decision_request(
            decision="needs_revision",
            comments="Revise it.",
            key="m54_needs_decision",
        ),
    )
    assert needs.status_code == 201, needs.text
    child = client.post(
        _revision_path(str(project["id"]), str(parent["id"])),
        json=_revision_request(
            _revised_payload(parent, "Second human version"),
            key="m54_needs_child",
        ),
    )
    assert child.status_code == 201, child.text
    assert child.json()["data"]["parent_asset_version_id"] == parent["id"]
    assert child.json()["data"]["status"] == "generated"
    parent_detail = client.get(
        f"{PROJECTS_PATH}/{project['id']}/assets/{parent['id']}"
    )
    assert parent_detail.json()["data"]["status"] == "needs_revision"


def test_rejected_is_final_and_second_review_is_conflict(
    client: TestClient,
) -> None:
    project, asset = _actual_generated(client, suffix="rejected")
    assert client.post(
        _submit_path(str(project["id"]), str(asset["id"])),
        json={},
    ).status_code == 200
    rejected = client.post(
        _decision_path(str(project["id"]), str(asset["id"])),
        json=_decision_request(
            decision="rejected",
            comments="Rejected by human.",
            key="m54_rejected_decision",
        ),
    )
    assert rejected.status_code == 201
    second = client.post(
        _decision_path(str(project["id"]), str(asset["id"])),
        json=_decision_request(
            decision="rejected",
            comments="Another decision.",
            key="m54_second_decision",
        ),
    )
    assert second.status_code == 409
    assert second.json()["detail"]["code"] == "P3_REVIEW_ALREADY_DECIDED"


def test_comments_checklist_and_forged_fields_are_422(
    client: TestClient,
) -> None:
    project, asset = _actual_generated(client, suffix="validation")
    assert client.post(
        _submit_path(str(project["id"]), str(asset["id"])),
        json={},
    ).status_code == 200
    missing_comments = client.post(
        _decision_path(str(project["id"]), str(asset["id"])),
        json=_decision_request(
            decision="rejected",
            comments=None,
            key="missing_comments",
        ),
    )
    assert missing_comments.status_code == 422
    bad_checklist = client.post(
        _decision_path(str(project["id"]), str(asset["id"])),
        json=_decision_request(
            checklist=_checklist(False),
            key="bad_checklist",
        ),
    )
    assert bad_checklist.status_code == 422
    for forged in (
        {"generation_mode": "manual_revision"},
        {"status": "approved"},
        {"reviewer_role": "admin"},
        {"content_hash": "a" * 64},
        {"approved_at": "2026-01-01T00:00:00Z"},
        {"review_policy_version": "forged"},
    ):
        response = client.post(
            _revision_path(str(project["id"]), str(asset["id"])),
            json=_revision_request(asset["content_payload"], **forged),
        )
        assert response.status_code == 422


@pytest.mark.parametrize(
    ("code", "status"),
    (
        ("P3_REVIEW_ASSET_NOT_FOUND", 404),
        ("P3_REVIEW_PROJECT_NOT_ACTIVE", 409),
        ("P3_REVIEW_SOURCE_STALE", 409),
        ("P3_REVIEW_SOURCE_EVIDENCE_CHANGED", 409),
        ("P3_REVIEW_SOURCE_REF_INVALID", 422),
        ("P3_REVIEW_GROUNDING_INCOMPLETE", 422),
        ("P3_REVIEW_ALREADY_DECIDED", 409),
        ("P3_REVIEW_IDEMPOTENCY_CONFLICT", 409),
        ("P3_REVIEW_STORAGE_UNAVAILABLE", 503),
    ),
)
def test_stable_service_errors_map_to_http(
    client: TestClient,
    code: str,
    status: int,
) -> None:
    with patch.object(
        P3ReviewService,
        "create_manual_revision",
        side_effect=P3ReviewServiceError(code, "Safe error.", {}),
    ):
        response = client.post(
            _revision_path("project", "asset"),
            json=_revision_request({}),
        )
    assert response.status_code == status
    assert response.json()["detail"]["code"] == code
    assert "postgresql://" not in response.text
    assert "Traceback" not in response.text


def test_idempotent_revision_replay_and_conflict(client: TestClient) -> None:
    project, parent = _actual_generated(client, suffix="idempotency")
    payload = _revision_request(
        _revised_payload(parent, "Idempotent"),
        key="m54_idempotent_revision",
    )
    first = client.post(
        _revision_path(str(project["id"]), str(parent["id"])),
        json=payload,
    )
    replay = client.post(
        _revision_path(str(project["id"]), str(parent["id"])),
        json=payload,
    )
    assert first.status_code == replay.status_code == 201
    assert first.json()["data"]["id"] == replay.json()["data"]["id"]
    conflict_payload = copy.deepcopy(payload)
    conflict_payload["content_payload"]["title"] = "Different"
    conflict = client.post(
        _revision_path(str(project["id"]), str(parent["id"])),
        json=conflict_payload,
    )
    assert conflict.status_code == 409
    assert (
        conflict.json()["detail"]["code"]
        == "P3_REVIEW_IDEMPOTENCY_CONFLICT"
    )


def test_not_found_review_list_and_pagination(client: TestClient) -> None:
    missing = client.get(_reviews_path("missing", "missing"))
    assert missing.status_code == 404
    project, asset = _actual_generated(client, suffix="list")
    assert client.post(
        _submit_path(str(project["id"]), str(asset["id"])),
        json={},
    ).status_code == 200
    assert client.post(
        _decision_path(str(project["id"]), str(asset["id"])),
        json=_decision_request(key="m54_list_review"),
    ).status_code == 201
    page = client.get(
        f"{PROJECTS_PATH}/{project['id']}/reviews?limit=1&offset=0"
    )
    assert page.status_code == 200
    assert page.json()["data"]["total"] == 1
    assert len(page.json()["data"]["items"]) == 1
    invalid = client.get(
        f"{PROJECTS_PATH}/{project['id']}/reviews?limit=101"
    )
    assert invalid.status_code == 422


def test_permissions_and_openapi_are_registered() -> None:
    assert Permission.P3_ASSET_EDIT in ROLE_PERMISSIONS[Role.ADMIN]
    assert Permission.P3_ASSET_EDIT in ROLE_PERMISSIONS[Role.CLEANER]
    assert Permission.P3_ASSET_EDIT not in ROLE_PERMISSIONS[Role.SERVICE]
    assert Permission.P3_ASSET_SUBMIT_REVIEW in ROLE_PERMISSIONS[Role.CLEANER]
    assert Permission.P3_REVIEW_DECIDE in ROLE_PERMISSIONS[Role.REVIEWER]
    assert Permission.P3_REVIEW_DECIDE not in ROLE_PERMISSIONS[Role.CLEANER]
    assert all(
        Permission.P3_REVIEW_READ in ROLE_PERMISSIONS[role]
        for role in Role
    )
    paths = app.openapi()["paths"]
    assert "/api/p3/reuse-projects/{project_id}/assets/{asset_version_id}/revisions" in paths
    assert "/api/p3/reuse-projects/{project_id}/assets/{asset_version_id}/submit-review" in paths
    assert "/api/p3/reuse-projects/{project_id}/assets/{asset_version_id}/review" in paths
    assert "/api/p3/reuse-projects/{project_id}/assets/{asset_version_id}/reviews" in paths
    assert "/api/p3/reuse-projects/{project_id}/reviews" in paths


def test_route_only_calls_service_and_never_provider_or_p1_p2() -> None:
    source = inspect.getsource(routes_module)
    assert "P3ReviewService" in source
    assert "p3_review_repositories" not in source
    assert ".query(" not in source
    assert "validate_and_ground" not in source
    assert "content_hash" not in source
    assert "Provider" not in source
    assert "db_models" not in source


def test_actual_flow_does_not_modify_p1_or_call_provider(
    client: TestClient,
) -> None:
    project, asset = _actual_generated(client, suffix="freeze")
    with SessionLocal() as db:
        before = db.query(KnowledgeCandidate).count()
        source = db.query(ReuseSourceItem).filter_by(
            project_id=project["id"]
        ).one()
        source_id = source.source_id
    with patch(
        "app.p3_llm_draft_service.OpenAICompatibleP3LLMDraftProvider"
    ) as provider:
        revision = client.post(
            _revision_path(str(project["id"]), str(asset["id"])),
            json=_revision_request(
                _revised_payload(asset, "No provider"),
                key="m54_freeze_revision",
            ),
        )
    assert revision.status_code == 201
    provider.assert_not_called()
    with SessionLocal() as db:
        assert db.query(KnowledgeCandidate).count() == before
        assert db.get(KnowledgeCandidate, source_id).status == "approved"

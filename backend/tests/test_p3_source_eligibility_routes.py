"""Focused P3-M1.2 tests for the read-only API and centralized RBAC."""

from __future__ import annotations

import inspect
import os
import socket
import sys
import tempfile
from collections.abc import Generator
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError


ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

_TEMP_DATABASE_DIR = tempfile.TemporaryDirectory(prefix="datahub-p3-m1-2-")
_DATABASE_PATH = Path(_TEMP_DATABASE_DIR.name) / "p3-source-api.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_DATABASE_PATH}"

from app import p3_source_eligibility_routes as routes_module  # noqa: E402
from app.auth import (  # noqa: E402
    Permission,
    ROLE_PERMISSIONS,
    ROLE_TOKEN_ENV,
    Role,
)
from app.database import SessionLocal, engine, get_db  # noqa: E402
from app.db_models import KnowledgeCandidate, ReviewRecord  # noqa: E402
from app.main import app  # noqa: E402
from app.p3_source_eligibility_schemas import (  # noqa: E402
    P3_SOURCE_ELIGIBILITY_POLICY_VERSION,
)


CHECK_PATH = "/api/p3/source-eligibility/check"
BATCH_PATH = "/api/p3/source-eligibility/check-batch"
TOKENS = {
    Role.ADMIN: "p3-m1-2-admin-token",
    Role.CLEANER: "p3-m1-2-cleaner-token",
    Role.REVIEWER: "p3-m1-2-reviewer-token",
    Role.SERVICE: "p3-m1-2-service-token",
    Role.VIEWER: "p3-m1-2-viewer-token",
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


def _payload(candidate_id: str = "candidate_api") -> dict[str, object]:
    return {
        "source_type": "P1_KNOWLEDGE",
        "source_id": candidate_id,
    }


def _seed_p1_candidate(
    *,
    candidate_id: str = "candidate_api",
    status: str = "approved",
    review_action: str = "approved",
) -> None:
    snapshot = {
        "candidate_id": candidate_id,
        "source_type": "sanitized_batch",
        "source_batch_id": "batch_api",
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
                source_id="batch_api",
                question=snapshot["question"],
                answer=snapshot["answer"],
                intent=snapshot["intent"],
                tags=snapshot["tags"],
                risk_level=snapshot["risk_level"],
                quality_score=0.95,
                status=status,
                metadata_json={
                    "source_batch_id": "batch_api",
                    "knowledge_type": "faq",
                },
            )
        )
        db.add(
            ReviewRecord(
                id=f"review_{candidate_id}",
                candidate_id=candidate_id,
                reviewer="p3_m1_2_reviewer",
                action=review_action,
                snapshot_json=snapshot,
            )
        )
        db.commit()
    finally:
        db.close()


def _decision(response) -> dict[str, object]:
    return response.json()["data"]["decision"]


def test_single_eligible_source_returns_200(client: TestClient) -> None:
    _seed_p1_candidate()
    response = client.post(CHECK_PATH, json=_payload())
    assert response.status_code == 200
    assert response.json()["success"] is True
    assert _decision(response)["eligible"] is True
    assert _decision(response)["reason_code"] == "ELIGIBLE"
    assert (
        response.json()["data"]["policy_version"]
        == P3_SOURCE_ELIGIBILITY_POLICY_VERSION
    )


def test_single_ineligible_source_is_a_200_decision(client: TestClient) -> None:
    _seed_p1_candidate(status="pending_review")
    response = client.post(CHECK_PATH, json=_payload())
    assert response.status_code == 200
    assert _decision(response)["eligible"] is False
    assert _decision(response)["reason_code"] == "SOURCE_NOT_APPROVED"


def test_missing_source_returns_200_not_found_decision(client: TestClient) -> None:
    response = client.post(CHECK_PATH, json=_payload("missing"))
    assert response.status_code == 200
    assert _decision(response)["reason_code"] == "SOURCE_NOT_FOUND"


def test_raw_bad_case_returns_stable_200_decision(client: TestClient) -> None:
    response = client.post(
        CHECK_PATH,
        json={"source_type": "RAW_BAD_CASE", "source_id": "bad_case_raw"},
    )
    assert response.status_code == 200
    assert _decision(response)["reason_code"] == "RAW_BAD_CASE_NOT_ALLOWED"


def test_batch_preserves_input_order(client: TestClient) -> None:
    _seed_p1_candidate(candidate_id="candidate_first")
    response = client.post(
        BATCH_PATH,
        json={
            "sources": [
                _payload("candidate_first"),
                _payload("missing_second"),
                {"source_type": "RAW_BAD_CASE", "source_id": "bad_case_third"},
            ]
        },
    )
    assert response.status_code == 200
    decisions = response.json()["data"]["decisions"]
    assert [item["source_id"] for item in decisions] == [
        "candidate_first",
        "missing_second",
        "bad_case_third",
    ]
    assert (
        response.json()["data"]["policy_version"]
        == P3_SOURCE_ELIGIBILITY_POLICY_VERSION
    )


def test_batch_ineligible_item_does_not_interrupt_others(
    client: TestClient,
) -> None:
    _seed_p1_candidate(candidate_id="candidate_eligible")
    _seed_p1_candidate(
        candidate_id="candidate_pending",
        status="pending_review",
    )
    response = client.post(
        BATCH_PATH,
        json={
            "sources": [
                _payload("candidate_eligible"),
                _payload("candidate_pending"),
                _payload("candidate_eligible"),
            ]
        },
    )
    assert response.status_code == 200
    assert [item["reason_code"] for item in response.json()["data"]["decisions"]] == [
        "ELIGIBLE",
        "SOURCE_NOT_APPROVED",
        "ELIGIBLE",
    ]


def test_empty_batch_is_422(client: TestClient) -> None:
    response = client.post(BATCH_PATH, json={"sources": []})
    assert response.status_code == 422


def test_batch_over_100_is_422(client: TestClient) -> None:
    response = client.post(
        BATCH_PATH,
        json={"sources": [_payload(f"candidate_{index}") for index in range(101)]},
    )
    assert response.status_code == 422


def test_unsupported_source_type_is_422(client: TestClient) -> None:
    response = client.post(
        CHECK_PATH,
        json={"source_type": "P3_ASSET", "source_id": "unsupported"},
    )
    assert response.status_code == 422


@pytest.mark.parametrize("source_id", ["", "   "])
def test_invalid_source_id_is_422(client: TestClient, source_id: str) -> None:
    response = client.post(
        CHECK_PATH,
        json={"source_type": "P1_KNOWLEDGE", "source_id": source_id},
    )
    assert response.status_code == 422


def test_expected_fingerprint_match_remains_eligible(client: TestClient) -> None:
    _seed_p1_candidate()
    initial = client.post(CHECK_PATH, json=_payload())
    fingerprint = _decision(initial)["content_fingerprint"]
    guarded_payload = _payload()
    guarded_payload["expected_fingerprint"] = fingerprint
    guarded = client.post(CHECK_PATH, json=guarded_payload)
    assert guarded.status_code == 200
    assert _decision(guarded)["reason_code"] == "ELIGIBLE"


def test_expected_fingerprint_mismatch_is_200_decision(
    client: TestClient,
) -> None:
    _seed_p1_candidate()
    guarded_payload = _payload()
    guarded_payload["expected_fingerprint"] = "0" * 64
    response = client.post(CHECK_PATH, json=guarded_payload)
    assert response.status_code == 200
    assert _decision(response)["reason_code"] == "SOURCE_FINGERPRINT_MISMATCH"


def test_disabled_auth_mode_remains_compatible(client: TestClient) -> None:
    _seed_p1_candidate()
    response = client.post(CHECK_PATH, json=_payload())
    assert response.status_code == 200


def test_token_mode_missing_token_is_401(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_token_auth(monkeypatch)
    response = client.post(CHECK_PATH, json=_payload())
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "AUTHENTICATION_REQUIRED"


def test_token_mode_invalid_token_is_401_without_reflection(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_token_auth(monkeypatch)
    invalid_token = "invalid-token-must-not-be-reflected"
    response = client.post(
        CHECK_PATH,
        json=_payload(),
        headers={"Authorization": f"Bearer {invalid_token}"},
    )
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "AUTHENTICATION_INVALID"
    assert invalid_token not in response.text


@pytest.mark.parametrize("role", list(Role))
def test_all_existing_roles_can_read_source_eligibility(
    role: Role,
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_token_auth(monkeypatch)
    response = client.post(CHECK_PATH, json=_payload(), headers=_headers(role))
    assert response.status_code == 200


def test_role_without_p3_permission_is_403(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_token_auth(monkeypatch)
    monkeypatch.setitem(ROLE_PERMISSIONS, Role.VIEWER, frozenset())
    response = client.post(
        CHECK_PATH,
        json=_payload(),
        headers=_headers(Role.VIEWER),
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "AUTHORIZATION_DENIED"


def test_health_remains_public_in_token_mode(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_token_auth(monkeypatch)
    assert client.get("/health").status_code == 200
    assert client.get("/api/health").status_code == 200


def test_auth_me_behavior_is_unchanged(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_token_auth(monkeypatch)
    response = client.get("/api/auth/me", headers=_headers(Role.REVIEWER))
    assert response.status_code == 200
    assert response.json()["data"] == {
        "role": "reviewer",
        "auth_mode": "token",
        "authenticated": True,
    }


def test_request_does_not_change_business_record_counts(client: TestClient) -> None:
    _seed_p1_candidate()
    db = SessionLocal()
    try:
        before = (
            db.query(KnowledgeCandidate).count(),
            db.query(ReviewRecord).count(),
        )
    finally:
        db.close()
    assert client.post(CHECK_PATH, json=_payload()).status_code == 200
    db = SessionLocal()
    try:
        after = (
            db.query(KnowledgeCandidate).count(),
            db.query(ReviewRecord).count(),
        )
    finally:
        db.close()
    assert after == before


def test_route_does_not_call_provider_embedding_or_network(
    client: TestClient,
) -> None:
    _seed_p1_candidate()
    route_source = inspect.getsource(routes_module).lower()
    for forbidden_import in (
        "app.embedding",
        "app.extraction_providers",
        "openai",
        "requests",
        "httpx",
    ):
        assert forbidden_import not in route_source
    with patch.object(
        socket,
        "create_connection",
        side_effect=AssertionError("network call is forbidden"),
    ):
        response = client.post(CHECK_PATH, json=_payload())
    assert response.status_code == 200


def test_response_excludes_content_vector_secret_and_connection_info(
    client: TestClient,
) -> None:
    _seed_p1_candidate()
    response = client.post(CHECK_PATH, json=_payload())
    serialized = response.text.lower()
    for forbidden in (
        "shipping takes five business days",
        "embedding",
        "secret",
        "storage_uri",
        "database_url",
        "postgresql://",
    ):
        assert forbidden not in serialized


def test_database_error_uses_safe_stable_response(client: TestClient) -> None:
    unsafe_message = "postgresql://user:password@internal.example/datahub"
    with patch(
        "app.p3_source_eligibility_routes.check_source_eligibility",
        side_effect=SQLAlchemyError(unsafe_message),
    ):
        response = client.post(CHECK_PATH, json=_payload())
    assert response.status_code == 503
    assert response.json()["detail"] == {
        "code": "P3_SOURCE_ELIGIBILITY_UNAVAILABLE",
        "message": "Source eligibility could not be checked.",
        "details": {},
    }
    assert unsafe_message not in response.text
    assert "password" not in response.text.lower()


def test_repeated_request_data_is_deterministic(client: TestClient) -> None:
    _seed_p1_candidate()
    first = client.post(CHECK_PATH, json=_payload())
    second = client.post(CHECK_PATH, json=_payload())
    assert first.status_code == second.status_code == 200
    assert first.json()["data"] == second.json()["data"]


def test_openapi_registers_bounded_protected_endpoints() -> None:
    schema = app.openapi()
    for path in (CHECK_PATH, BATCH_PATH):
        operation = schema["paths"][path]["post"]
        assert operation["security"] == [{"DataHubBearer": []}]
        assert "P3 Source Eligibility" in operation["tags"]

    batch_schema = schema["components"]["schemas"]["P3SourceEligibilityBatchRequest"]
    sources_schema = batch_schema["properties"]["sources"]
    assert sources_schema["minItems"] == 1
    assert sources_schema["maxItems"] == 100
    assert Permission.P3_SOURCE_READ.value == "p3.source.read"

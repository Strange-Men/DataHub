"""M9.2 governance authentication and RBAC safety gates."""

from __future__ import annotations

from pathlib import Path
import hmac
import logging
import sys
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.auth import (  # noqa: E402
    AuthConfigurationError,
    AuthMode,
    AuthSettings,
    Permission,
    Principal,
    ROLE_PERMISSIONS,
    ROLE_TOKEN_ENV,
    Role,
    authenticate_token,
    authorize_principal,
    validate_auth_configuration,
)
from app.main import app  # noqa: E402
from scripts.auth_client import load_bearer_token  # noqa: E402
from scripts.run_p1_pipeline_harness import PipelineHarness  # noqa: E402
from scripts.run_p2_local_acceptance import AcceptanceClient  # noqa: E402


TOKENS = {
    Role.ADMIN: "m92-admin-token",
    Role.CLEANER: "m92-cleaner-token",
    Role.REVIEWER: "m92-reviewer-token",
    Role.SERVICE: "m92-service-token",
    Role.VIEWER: "m92-viewer-token",
}


@pytest.fixture(autouse=True)
def disabled_auth_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATAHUB_AUTH_MODE", "disabled")
    for env_name in ROLE_TOKEN_ENV.values():
        monkeypatch.delenv(env_name, raising=False)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _enable_token_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATAHUB_AUTH_MODE", "token")
    for role, token in TOKENS.items():
        monkeypatch.setenv(ROLE_TOKEN_ENV[role], token)


def _headers(role: Role) -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKENS[role]}"}


def _detail_code(response) -> str:
    return response.json()["detail"]["code"]


def test_disabled_mode_preserves_legacy_unauthenticated_access(client: TestClient) -> None:
    response = client.get("/api/sources")
    assert response.status_code == 200
    assert response.json()["success"] is True


def test_token_mode_distinguishes_missing_invalid_and_forbidden(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_token_auth(monkeypatch)

    missing = client.get("/api/sources")
    assert missing.status_code == 401
    assert _detail_code(missing) == "AUTHENTICATION_REQUIRED"
    assert missing.headers["www-authenticate"] == "Bearer"

    invalid_token = "token-that-must-never-be-reflected"
    invalid = client.get(
        "/api/sources",
        headers={"Authorization": f"Bearer {invalid_token}"},
    )
    assert invalid.status_code == 401
    assert _detail_code(invalid) == "AUTHENTICATION_INVALID"
    assert invalid_token not in invalid.text

    forbidden = client.post(
        "/api/knowledge-assets/missing/archive",
        headers=_headers(Role.CLEANER),
    )
    assert forbidden.status_code == 403
    assert _detail_code(forbidden) == "AUTHORIZATION_DENIED"


@pytest.mark.parametrize("role", list(Role))
def test_valid_token_resolves_explicit_role(
    role: Role,
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_token_auth(monkeypatch)
    response = client.get("/api/auth/me", headers=_headers(role))
    assert response.status_code == 200
    assert response.json()["data"] == {
        "role": role.value,
        "auth_mode": "token",
        "authenticated": True,
    }


def test_token_mode_requires_at_least_one_unique_role_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATAHUB_AUTH_MODE", "token")
    with pytest.raises(AuthConfigurationError, match="at least one"):
        AuthSettings.from_environment()

    monkeypatch.setenv("DATAHUB_ADMIN_TOKEN", "duplicate-token")
    monkeypatch.setenv("DATAHUB_SERVICE_TOKEN", "duplicate-token")
    with pytest.raises(AuthConfigurationError, match="must be unique"):
        AuthSettings.from_environment()


def test_authentication_compares_every_configured_token_in_constant_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_token_auth(monkeypatch)
    settings = AuthSettings.from_environment()
    with patch("app.auth.hmac.compare_digest", wraps=hmac.compare_digest) as compare:
        assert authenticate_token(TOKENS[Role.SERVICE], settings) is Role.SERVICE
        assert compare.call_count == len(TOKENS)


def test_configuration_logs_roles_but_never_token_values(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("DATAHUB_AUTH_MODE", "token")
    monkeypatch.setenv("DATAHUB_SERVICE_TOKEN", TOKENS[Role.SERVICE])
    with caplog.at_level(logging.INFO, logger="app.auth"):
        settings = validate_auth_configuration()
    assert settings.role_tokens == {Role.SERVICE: TOKENS[Role.SERVICE]}
    assert TOKENS[Role.SERVICE] not in caplog.text
    assert "service" in caplog.text


def test_health_remains_public_in_token_mode(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_token_auth(monkeypatch)
    for path in ("/health", "/api/health"):
        response = client.get(path)
        assert response.status_code == 200


def test_role_permission_matrix_matches_governance_duties() -> None:
    assert ROLE_PERMISSIONS[Role.ADMIN] == frozenset(Permission)

    cleaner = ROLE_PERMISSIONS[Role.CLEANER]
    assert {
        Permission.P1_IMPORT,
        Permission.P1_CLEAN,
        Permission.P1_REVISE,
        Permission.P2_ASSET_UPLOAD,
        Permission.P2_EXTRACT,
        Permission.P2_REVISE,
    } <= cleaner
    assert not {
        Permission.P1_REVIEW,
        Permission.P2_REVIEW,
        Permission.P2_PUBLISH,
        Permission.P2_SERVE,
        Permission.P2_ARCHIVE,
    } & cleaner

    reviewer = ROLE_PERMISSIONS[Role.REVIEWER]
    assert {Permission.P1_REVIEW, Permission.P2_REVIEW} <= reviewer
    assert not {
        Permission.P1_IMPORT,
        Permission.P2_EMBED,
        Permission.P2_SERVE,
    } & reviewer

    service = ROLE_PERMISSIONS[Role.SERVICE]
    assert {
        Permission.RETRIEVAL_P1,
        Permission.RETRIEVAL_P2,
        Permission.RETRIEVAL_UNIFIED,
        Permission.AGENT_CUSTOMEROPS,
        Permission.BADCASE_SUBMIT,
    } <= service
    assert Permission.P1_REVIEW not in service

    viewer = ROLE_PERMISSIONS[Role.VIEWER]
    assert {Permission.P1_READ, Permission.P2_READ} <= viewer
    assert not {
        Permission.P1_IMPORT,
        Permission.P1_REVISE,
        Permission.P2_ASSET_UPLOAD,
        Permission.P2_ARCHIVE,
    } & viewer


@pytest.mark.parametrize(
    ("role", "permission", "allowed"),
    [
        (Role.CLEANER, Permission.P1_IMPORT, True),
        (Role.CLEANER, Permission.P1_REVIEW, False),
        (Role.REVIEWER, Permission.P2_REVIEW, True),
        (Role.REVIEWER, Permission.P2_EMBED, False),
        (Role.SERVICE, Permission.AGENT_CUSTOMEROPS, True),
        (Role.SERVICE, Permission.P1_REVIEW, False),
        (Role.VIEWER, Permission.P2_READ, True),
        (Role.VIEWER, Permission.P2_ARCHIVE, False),
    ],
)
def test_authorization_matrix_returns_principal_or_403(
    role: Role,
    permission: Permission,
    allowed: bool,
) -> None:
    principal = Principal(role=role, auth_mode=AuthMode.TOKEN, authenticated=True)
    if allowed:
        assert authorize_principal(principal, permission) is principal
    else:
        with pytest.raises(HTTPException) as exc_info:
            authorize_principal(principal, permission)
        error = exc_info.value
        assert getattr(error, "status_code", None) == 403
        assert error.detail["code"] == "AUTHORIZATION_DENIED"


def test_route_dependencies_enforce_representative_role_boundaries(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_token_auth(monkeypatch)

    with patch("app.main.run_cleaning", return_value=None):
        assert (
            client.post(
                "/api/cleaning/run/missing",
                headers=_headers(Role.CLEANER),
            ).status_code
            == 404
        )
    assert (
        client.post(
            "/api/review/missing/approve",
            json={"reviewer": "m92-reviewer"},
            headers=_headers(Role.CLEANER),
        ).status_code
        == 403
    )

    with patch("app.main.apply_review_decision", return_value=None):
        reviewer_allowed = client.post(
            "/api/review/missing/approve",
            json={"reviewer": "m92-reviewer"},
            headers=_headers(Role.REVIEWER),
        )
    assert reviewer_allowed.status_code == 404
    assert (
        client.post(
            "/api/cleaning/run/missing",
            headers=_headers(Role.REVIEWER),
        ).status_code
        == 403
    )

    with patch("app.main.search_rag_chunks", return_value=[]):
        service_retrieval = client.post(
            "/api/rag/search",
            json={"query": "M9.2 auth probe", "top_k": 1},
            headers=_headers(Role.SERVICE),
        )
    assert service_retrieval.status_code == 200
    assert (
        client.post(
            "/api/review/missing/approve",
            json={"reviewer": "m92-service"},
            headers=_headers(Role.SERVICE),
        ).status_code
        == 403
    )

    assert (
        client.post(
            "/api/knowledge-assets/missing/archive",
            headers=_headers(Role.VIEWER),
        ).status_code
        == 403
    )


def test_openapi_declares_bearer_security_only_on_protected_routes() -> None:
    schema = app.openapi()
    assert "DataHubBearer" in schema["components"]["securitySchemes"]
    assert "security" not in schema["paths"]["/health"]["get"]
    assert schema["paths"]["/api/sources"]["get"]["security"] == [
        {"DataHubBearer": []}
    ]


def test_frontend_uses_session_token_and_chinese_auth_errors() -> None:
    api_source = (ROOT / "frontend" / "src" / "api.ts").read_text(encoding="utf-8")
    controls_source = (
        ROOT / "frontend" / "src" / "components" / "AuthControls.tsx"
    ).read_text(encoding="utf-8")
    context_source = (
        ROOT / "frontend" / "src" / "auth" / "AuthContext.tsx"
    ).read_text(encoding="utf-8")

    assert "sessionStorage" in api_source
    assert "localStorage" not in api_source
    assert "AUTH_ROLE_KEY" not in api_source
    assert "getStoredRole" not in api_source + controls_source + context_source
    assert "Authorization" in api_source and "Bearer ${token}" in api_source
    assert "身份验证失败，请检查访问令牌。" in api_source
    assert "当前角色没有执行此操作的权限。" in api_source
    assert ".removeItem(AUTH_TOKEN_KEY)" in api_source
    assert 'useState<AuthRole | null>(null)' in context_source
    assert 'apiPath("/api/auth/me")' in context_source
    assert "isAuthRole(resolvedRole)" in context_source
    assert "ROLE_LABELS[role]" in controls_source
    assert "type=\"password\"" in controls_source
    assert "访问令牌" in controls_source
    assert "console.log" not in api_source + controls_source + context_source


def test_harness_clients_load_token_only_from_named_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATAHUB_TEST_SERVICE_TOKEN", "harness-service-token")
    token = load_bearer_token("DATAHUB_TEST_SERVICE_TOKEN")
    assert token == "harness-service-token"

    p1 = PipelineHarness("http://127.0.0.1:8000", auth_token=token)
    assert p1._session.headers["Authorization"] == "Bearer harness-service-token"

    p2 = AcceptanceClient("http://127.0.0.1:8000", 10, auth_token=token)
    assert p2.auth_headers["Authorization"] == "Bearer harness-service-token"

    with pytest.raises(ValueError, match="variable name is invalid"):
        load_bearer_token("not-an-env-name")

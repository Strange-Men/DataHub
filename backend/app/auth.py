"""Runtime Bearer-token authentication and centralized P1/P2 RBAC."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import hmac
import logging
import os
from typing import Callable

from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer


logger = logging.getLogger(__name__)


class AuthMode(StrEnum):
    DISABLED = "disabled"
    TOKEN = "token"


class Role(StrEnum):
    ADMIN = "admin"
    CLEANER = "cleaner"
    REVIEWER = "reviewer"
    SERVICE = "service"
    VIEWER = "viewer"


class Permission(StrEnum):
    P1_IMPORT = "p1.import"
    P1_CLEAN = "p1.clean"
    P1_REVISE = "p1.revise"
    P1_REVIEW = "p1.review"
    P1_RAG_SYNC = "p1.rag_sync"
    P1_READ = "p1.read"

    P2_ASSET_UPLOAD = "p2.asset_upload"
    P2_EXTRACT = "p2.extract"
    P2_REVISE = "p2.revise"
    P2_REVIEW = "p2.review"
    P2_PUBLISH = "p2.publish"
    P2_INDEX = "p2.index"
    P2_EMBED = "p2.embed"
    P2_SERVE = "p2.serve"
    P2_ARCHIVE = "p2.archive"
    P2_READ = "p2.read"

    RETRIEVAL_P1 = "retrieval.p1"
    RETRIEVAL_P2 = "retrieval.p2"
    RETRIEVAL_UNIFIED = "retrieval.unified"
    AGENT_CUSTOMEROPS = "agent.customerops"
    BADCASE_SUBMIT = "badcase.submit"


ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.ADMIN: frozenset(Permission),
    Role.CLEANER: frozenset(
        {
            Permission.P1_IMPORT,
            Permission.P1_CLEAN,
            Permission.P1_REVISE,
            Permission.P1_READ,
            Permission.P2_ASSET_UPLOAD,
            Permission.P2_EXTRACT,
            Permission.P2_REVISE,
            Permission.P2_READ,
        }
    ),
    Role.REVIEWER: frozenset(
        {
            Permission.P1_READ,
            Permission.P1_REVIEW,
            Permission.P2_READ,
            Permission.P2_REVIEW,
        }
    ),
    Role.SERVICE: frozenset(
        {
            Permission.RETRIEVAL_P1,
            Permission.RETRIEVAL_P2,
            Permission.RETRIEVAL_UNIFIED,
            Permission.AGENT_CUSTOMEROPS,
            Permission.BADCASE_SUBMIT,
        }
    ),
    Role.VIEWER: frozenset(
        {
            Permission.P1_READ,
            Permission.P2_READ,
            Permission.RETRIEVAL_P1,
            Permission.RETRIEVAL_P2,
        }
    ),
}


ROLE_TOKEN_ENV: dict[Role, str] = {
    Role.ADMIN: "DATAHUB_ADMIN_TOKEN",
    Role.CLEANER: "DATAHUB_CLEANER_TOKEN",
    Role.REVIEWER: "DATAHUB_REVIEWER_TOKEN",
    Role.SERVICE: "DATAHUB_SERVICE_TOKEN",
    Role.VIEWER: "DATAHUB_VIEWER_TOKEN",
}


class AuthConfigurationError(RuntimeError):
    """Raised when token mode cannot be configured safely."""


@dataclass(frozen=True)
class AuthSettings:
    mode: AuthMode
    role_tokens: dict[Role, str]
    missing_roles: tuple[Role, ...]

    @classmethod
    def from_environment(cls) -> "AuthSettings":
        raw_mode = os.getenv("DATAHUB_AUTH_MODE", AuthMode.DISABLED.value).strip().lower()
        try:
            mode = AuthMode(raw_mode)
        except ValueError as exc:
            raise AuthConfigurationError(
                "DATAHUB_AUTH_MODE must be disabled or token."
            ) from exc

        role_tokens: dict[Role, str] = {}
        missing_roles: list[Role] = []
        for role, env_name in ROLE_TOKEN_ENV.items():
            token = os.getenv(env_name, "").strip()
            if token:
                role_tokens[role] = token
            else:
                missing_roles.append(role)

        if mode is AuthMode.TOKEN:
            if not role_tokens:
                raise AuthConfigurationError(
                    "Token auth requires at least one configured role token."
                )
            configured = list(role_tokens.items())
            for index, (left_role, left_token) in enumerate(configured):
                for right_role, right_token in configured[index + 1 :]:
                    if hmac.compare_digest(left_token, right_token):
                        raise AuthConfigurationError(
                            "Role tokens must be unique: "
                            f"{left_role.value} and {right_role.value} conflict."
                        )

        return cls(
            mode=mode,
            role_tokens=role_tokens,
            missing_roles=tuple(missing_roles),
        )


@dataclass(frozen=True)
class Principal:
    role: Role
    auth_mode: AuthMode
    authenticated: bool


_bearer = HTTPBearer(
    auto_error=False,
    scheme_name="DataHubBearer",
    description="Opaque runtime Bearer token mapped to one DataHub role.",
)


def _auth_error(status_code: int, code: str, message: str) -> HTTPException:
    headers = {"WWW-Authenticate": "Bearer"} if status_code == 401 else None
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message, "details": {}},
        headers=headers,
    )


def validate_auth_configuration() -> AuthSettings:
    """Validate startup configuration without exposing token values."""
    settings = AuthSettings.from_environment()
    if settings.mode is AuthMode.TOKEN:
        available = sorted(role.value for role in settings.role_tokens)
        logger.info("DataHub token authentication enabled for roles: %s", available)
        if settings.missing_roles:
            missing = sorted(role.value for role in settings.missing_roles)
            logger.warning("DataHub role tokens are unavailable for roles: %s", missing)
    else:
        logger.info("DataHub authentication is explicitly disabled.")
    return settings


def authenticate_token(token: str, settings: AuthSettings) -> Role | None:
    """Compare against every configured token before returning a matched role."""
    matched: Role | None = None
    for role, configured_token in settings.role_tokens.items():
        if hmac.compare_digest(token, configured_token):
            matched = role
    return matched


def get_current_principal(
    credentials: HTTPAuthorizationCredentials | None = Security(_bearer),
) -> Principal:
    try:
        settings = AuthSettings.from_environment()
    except AuthConfigurationError as exc:
        raise _auth_error(
            503,
            "AUTH_CONFIGURATION_INVALID",
            "Authentication configuration is invalid.",
        ) from exc

    if settings.mode is AuthMode.DISABLED:
        return Principal(
            role=Role.ADMIN,
            auth_mode=AuthMode.DISABLED,
            authenticated=False,
        )

    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _auth_error(
            401,
            "AUTHENTICATION_REQUIRED",
            "A Bearer access token is required.",
        )

    role = authenticate_token(credentials.credentials, settings)
    if role is None:
        raise _auth_error(
            401,
            "AUTHENTICATION_INVALID",
            "The Bearer access token is invalid.",
        )
    return Principal(role=role, auth_mode=settings.mode, authenticated=True)


def authorize_principal(principal: Principal, permission: Permission) -> Principal:
    if permission not in ROLE_PERMISSIONS[principal.role]:
        raise _auth_error(
            403,
            "AUTHORIZATION_DENIED",
            "The authenticated role does not have permission for this operation.",
        )
    return principal


def require_permission(permission: Permission) -> Callable[..., Principal]:
    def dependency(principal: Principal = Security(get_current_principal)) -> Principal:
        return authorize_principal(principal, permission)

    dependency.__name__ = f"require_{permission.value.replace('.', '_')}"
    return dependency

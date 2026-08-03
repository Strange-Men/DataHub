"""Fail-closed configuration and read-only platform validation at startup."""

from __future__ import annotations

from dataclasses import dataclass
import logging

from app.answerability import AnswerabilityConfig
from app.auth import AuthSettings, validate_auth_configuration
from app import health_service
from app.runtime_environment import RuntimeEnvironment, resolve_runtime_environment


logger = logging.getLogger(__name__)


class RuntimeReadinessError(RuntimeError):
    """Raised when a deployed environment is not safe to receive traffic."""


@dataclass(frozen=True)
class RuntimeConfiguration:
    environment: RuntimeEnvironment
    auth: AuthSettings
    dependencies_ready: bool
    dependency_reason_codes: tuple[str, ...]


def validate_runtime_configuration() -> RuntimeConfiguration:
    """Validate auth first, then read DB, Alembic revision, and pgvector state."""

    context = resolve_runtime_environment()
    auth = validate_auth_configuration(context.environment)
    AnswerabilityConfig.from_environment()
    snapshot, dependencies_ready = health_service.startup_dependency_readiness()
    reason_codes = tuple(str(code) for code in snapshot.get("reason_codes", []))
    if not dependencies_ready:
        if context.environment in {
            RuntimeEnvironment.STAGING,
            RuntimeEnvironment.PRODUCTION,
        }:
            raise RuntimeReadinessError(
                "Runtime readiness validation failed for the deployed environment: "
                + ",".join(reason_codes)
            )
        logger.warning(
            "Runtime dependency readiness is incomplete in %s: %s",
            context.environment.value,
            sorted(reason_codes),
        )
    return RuntimeConfiguration(
        environment=context.environment,
        auth=auth,
        dependencies_ready=dependencies_ready,
        dependency_reason_codes=reason_codes,
    )


__all__ = [
    "RuntimeConfiguration",
    "RuntimeReadinessError",
    "validate_runtime_configuration",
]

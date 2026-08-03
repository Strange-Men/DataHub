"""Centralized, fail-closed runtime environment resolution."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import os


class RuntimeEnvironment(StrEnum):
    LOCAL = "local"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


class RuntimeAuthority(StrEnum):
    LOCAL_DOCKER = "local_docker"
    DEPLOYED_ENVIRONMENT = "deployed_environment"


class RuntimeEnvironmentError(RuntimeError):
    """Raised when DATAHUB_ENV cannot be normalized safely."""


@dataclass(frozen=True)
class RuntimeEnvironmentContext:
    environment: RuntimeEnvironment
    authority: RuntimeAuthority
    configuration_valid: bool


_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})


def _render_deployment() -> bool:
    return os.getenv("RENDER", "").strip().lower() in _TRUE_VALUES


def resolve_runtime_environment(*, fail_closed: bool = False) -> RuntimeEnvironmentContext:
    """Resolve DATAHUB_ENV once, with only the frozen names plus docker compatibility."""

    raw = os.getenv("DATAHUB_ENV", "").strip().lower()
    normalized = RuntimeEnvironment.LOCAL.value if raw in {"", "docker"} else raw
    try:
        environment = RuntimeEnvironment(normalized)
        configuration_valid = True
    except ValueError as exc:
        if not fail_closed:
            raise RuntimeEnvironmentError(
                "DATAHUB_ENV must be local, test, staging, or production."
            ) from exc
        environment = RuntimeEnvironment.PRODUCTION
        configuration_valid = False

    if _render_deployment() and environment in {
        RuntimeEnvironment.LOCAL,
        RuntimeEnvironment.TEST,
    }:
        environment = RuntimeEnvironment.PRODUCTION

    authority = (
        RuntimeAuthority.DEPLOYED_ENVIRONMENT
        if environment in {RuntimeEnvironment.STAGING, RuntimeEnvironment.PRODUCTION}
        else RuntimeAuthority.LOCAL_DOCKER
    )
    return RuntimeEnvironmentContext(
        environment=environment,
        authority=authority,
        configuration_valid=configuration_valid,
    )


def get_runtime_environment() -> RuntimeEnvironment:
    return resolve_runtime_environment().environment


__all__ = [
    "RuntimeAuthority",
    "RuntimeEnvironment",
    "RuntimeEnvironmentContext",
    "RuntimeEnvironmentError",
    "get_runtime_environment",
    "resolve_runtime_environment",
]

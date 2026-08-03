"""Aggregate safe runtime facts into the public capability contract."""

from __future__ import annotations

import os
from typing import Callable, TypeVar

from app import capability_probes
from app.auth import inspect_auth_configuration
from app.capability_schemas import (
    AuthCapability,
    AuthorityName,
    AvailabilityStatus,
    CapabilitiesResponse,
    CapabilityReasonCode,
    CustomerOpsDefaultMode,
    EnvironmentName,
    FeatureCapabilities,
    InfrastructureCapabilities,
    ModuleCapabilities,
    PlannedCapabilityStatus,
    PlannedModuleCapability,
    ReportedAuthMode,
    RuntimeCapabilityStatus,
    RuntimeModuleCapability,
    StorageStatus,
)
from app.runtime_environment import RuntimeEnvironmentContext, resolve_runtime_environment


_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_REASON_ORDER = {code: index for index, code in enumerate(CapabilityReasonCode)}

T = TypeVar("T")


def _safe_probe(probe: Callable[[], T], fallback: T) -> T:
    try:
        return probe()
    except Exception:
        return fallback


def _enabled(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in _TRUE_VALUES


def _auth_capability(
    context: RuntimeEnvironmentContext,
) -> tuple[AuthCapability, bool]:
    status = inspect_auth_configuration(context)
    return (
        AuthCapability(
            mode=ReportedAuthMode(status.mode.value),
            safe_for_environment=status.safe_for_environment,
        ),
        context.configuration_valid and status.configuration_valid,
    )


def _storage_status(result: capability_probes.StorageProbeResult) -> StorageStatus:
    if not result.ready:
        return StorageStatus.UNAVAILABLE
    return StorageStatus.LOCAL_ONLY if result.local_only else StorageStatus.AVAILABLE


def _reason_codes(
    reasons: list[CapabilityReasonCode],
) -> tuple[CapabilityReasonCode, ...]:
    return tuple(sorted(set(reasons), key=_REASON_ORDER.__getitem__))


def _auth_reason(
    auth: AuthCapability,
    auth_configuration_valid: bool,
) -> CapabilityReasonCode | None:
    if not auth_configuration_valid:
        return CapabilityReasonCode.AUTH_CONFIGURATION_INVALID
    if not auth.safe_for_environment:
        return CapabilityReasonCode.AUTH_UNSAFE_FOR_ENVIRONMENT
    return None


def _p1_module(
    auth_reason: CapabilityReasonCode | None,
    database: AvailabilityStatus,
    pgvector: AvailabilityStatus,
) -> RuntimeModuleCapability:
    reasons: list[CapabilityReasonCode] = []
    fatal = False
    if auth_reason is not None:
        reasons.append(auth_reason)
        fatal = True
    if database is AvailabilityStatus.UNAVAILABLE:
        reasons.append(CapabilityReasonCode.DATABASE_UNAVAILABLE)
        fatal = True
    if pgvector is AvailabilityStatus.UNAVAILABLE:
        reasons.append(CapabilityReasonCode.PGVECTOR_UNAVAILABLE)
    if fatal:
        status = RuntimeCapabilityStatus.UNAVAILABLE
    elif pgvector is AvailabilityStatus.UNAVAILABLE:
        status = RuntimeCapabilityStatus.DEGRADED
    else:
        status = RuntimeCapabilityStatus.AVAILABLE
    return RuntimeModuleCapability(
        status=status,
        reason_codes=_reason_codes(reasons),
    )


def _p2_module(
    auth_reason: CapabilityReasonCode | None,
    database: AvailabilityStatus,
    pgvector: AvailabilityStatus,
    asset_storage: StorageStatus,
) -> RuntimeModuleCapability:
    reasons: list[CapabilityReasonCode] = []
    fatal = False
    if auth_reason is not None:
        reasons.append(auth_reason)
        fatal = True
    if database is AvailabilityStatus.UNAVAILABLE:
        reasons.append(CapabilityReasonCode.DATABASE_UNAVAILABLE)
        fatal = True
    if pgvector is AvailabilityStatus.UNAVAILABLE:
        reasons.append(CapabilityReasonCode.PGVECTOR_UNAVAILABLE)
    if asset_storage is StorageStatus.UNAVAILABLE:
        reasons.append(CapabilityReasonCode.ASSET_STORAGE_UNAVAILABLE)
        fatal = True
    elif asset_storage is StorageStatus.LOCAL_ONLY:
        reasons.append(CapabilityReasonCode.ASSET_STORAGE_LOCAL_ONLY)

    if fatal:
        status = RuntimeCapabilityStatus.UNAVAILABLE
    elif pgvector is AvailabilityStatus.UNAVAILABLE:
        status = RuntimeCapabilityStatus.DEGRADED
    elif asset_storage is StorageStatus.LOCAL_ONLY:
        status = RuntimeCapabilityStatus.LOCAL_ONLY
    else:
        status = RuntimeCapabilityStatus.AVAILABLE
    return RuntimeModuleCapability(status=status, reason_codes=_reason_codes(reasons))


def _p3_module(
    auth_reason: CapabilityReasonCode | None,
    database: AvailabilityStatus,
    export_storage: StorageStatus,
) -> RuntimeModuleCapability:
    reasons: list[CapabilityReasonCode] = []
    fatal = False
    if auth_reason is not None:
        reasons.append(auth_reason)
        fatal = True
    if database is AvailabilityStatus.UNAVAILABLE:
        reasons.append(CapabilityReasonCode.DATABASE_UNAVAILABLE)
        fatal = True
    if export_storage is StorageStatus.UNAVAILABLE:
        reasons.append(CapabilityReasonCode.EXPORT_STORAGE_UNAVAILABLE)
        fatal = True
    elif export_storage is StorageStatus.LOCAL_ONLY:
        reasons.append(CapabilityReasonCode.EXPORT_STORAGE_LOCAL_ONLY)

    if fatal:
        status = RuntimeCapabilityStatus.UNAVAILABLE
    elif export_storage is StorageStatus.LOCAL_ONLY:
        status = RuntimeCapabilityStatus.LOCAL_ONLY
    else:
        status = RuntimeCapabilityStatus.AVAILABLE
    return RuntimeModuleCapability(status=status, reason_codes=_reason_codes(reasons))


def get_capabilities() -> CapabilitiesResponse:
    """Build a deterministic response from read-only, fail-safe observations."""

    context = resolve_runtime_environment(fail_closed=True)
    environment = EnvironmentName(context.environment.value)
    authority = AuthorityName(context.authority.value)
    auth, auth_configuration_valid = _auth_capability(context)
    auth_reason = _auth_reason(auth, auth_configuration_valid)
    database = (
        AvailabilityStatus.AVAILABLE
        if _safe_probe(capability_probes.database_available, False)
        else AvailabilityStatus.UNAVAILABLE
    )
    pgvector = (
        AvailabilityStatus.AVAILABLE
        if _safe_probe(capability_probes.pgvector_available, False)
        else AvailabilityStatus.UNAVAILABLE
    )
    unavailable_storage = capability_probes.StorageProbeResult(
        ready=False,
        local_only=False,
    )
    asset_storage = _storage_status(
        _safe_probe(capability_probes.asset_storage_readiness, unavailable_storage)
    )
    export_storage = _storage_status(
        _safe_probe(capability_probes.export_storage_readiness, unavailable_storage)
    )

    unified_retrieval = _enabled("UNIFIED_RETRIEVAL_ENABLED")
    customerops_unified = (
        _enabled("CUSTOMEROPS_UNIFIED_RETRIEVAL_ENABLED")
        and unified_retrieval
        and _enabled("P2_RETRIEVAL_ENABLED")
        and not _enabled("UNIFIED_RETRIEVAL_SHADOW_MODE")
    )

    infrastructure = InfrastructureCapabilities(
        database=database,
        pgvector=pgvector,
        asset_storage=asset_storage,
        export_storage=export_storage,
    )
    modules = ModuleCapabilities(
        p1=_p1_module(auth_reason, database, pgvector),
        p2=_p2_module(auth_reason, database, pgvector, asset_storage),
        p3=_p3_module(auth_reason, database, export_storage),
        p4=PlannedModuleCapability(
            status=PlannedCapabilityStatus.PLANNED,
            reason_codes=(CapabilityReasonCode.NOT_IMPLEMENTED,),
        ),
    )
    features = FeatureCapabilities(
        p3_llm_draft=_enabled("P3_LLM_DRAFT_ENABLED"),
        unified_retrieval=unified_retrieval,
        customerops_default_mode=(
            CustomerOpsDefaultMode.UNIFIED
            if customerops_unified
            else CustomerOpsDefaultMode.P1
        ),
    )
    return CapabilitiesResponse(
        environment=environment,
        authority=authority,
        auth=auth,
        infrastructure=infrastructure,
        modules=modules,
        features=features,
    )


__all__ = ["get_capabilities"]

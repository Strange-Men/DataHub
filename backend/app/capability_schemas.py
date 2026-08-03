"""Stable public schema for runtime capability discovery."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class EnvironmentName(StrEnum):
    LOCAL = "local"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


class AuthorityName(StrEnum):
    LOCAL_DOCKER = "local_docker"
    DEPLOYED_ENVIRONMENT = "deployed_environment"


class ReportedAuthMode(StrEnum):
    DISABLED = "disabled"
    TOKEN = "token"


class RuntimeCapabilityStatus(StrEnum):
    AVAILABLE = "available"
    LOCAL_ONLY = "local_only"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


class PlannedCapabilityStatus(StrEnum):
    PLANNED = "planned"


class AvailabilityStatus(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


class StorageStatus(StrEnum):
    AVAILABLE = "available"
    LOCAL_ONLY = "local_only"
    UNAVAILABLE = "unavailable"


class CapabilityReasonCode(StrEnum):
    DATABASE_UNAVAILABLE = "DATABASE_UNAVAILABLE"
    PGVECTOR_UNAVAILABLE = "PGVECTOR_UNAVAILABLE"
    ASSET_STORAGE_UNAVAILABLE = "ASSET_STORAGE_UNAVAILABLE"
    ASSET_STORAGE_LOCAL_ONLY = "ASSET_STORAGE_LOCAL_ONLY"
    EXPORT_STORAGE_UNAVAILABLE = "EXPORT_STORAGE_UNAVAILABLE"
    EXPORT_STORAGE_LOCAL_ONLY = "EXPORT_STORAGE_LOCAL_ONLY"
    AUTH_CONFIGURATION_INVALID = "AUTH_CONFIGURATION_INVALID"
    AUTH_UNSAFE_FOR_ENVIRONMENT = "AUTH_UNSAFE_FOR_ENVIRONMENT"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"


class CustomerOpsDefaultMode(StrEnum):
    P1 = "p1"
    UNIFIED = "unified"


class AuthCapability(BaseModel):
    model_config = ConfigDict(frozen=True)

    mode: ReportedAuthMode
    safe_for_environment: bool


class InfrastructureCapabilities(BaseModel):
    model_config = ConfigDict(frozen=True)

    database: AvailabilityStatus
    pgvector: AvailabilityStatus
    asset_storage: StorageStatus
    export_storage: StorageStatus


class RuntimeModuleCapability(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: RuntimeCapabilityStatus
    reason_codes: tuple[CapabilityReasonCode, ...] = ()


class PlannedModuleCapability(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: PlannedCapabilityStatus
    reason_codes: tuple[CapabilityReasonCode, ...] = ()


class ModuleCapabilities(BaseModel):
    model_config = ConfigDict(frozen=True)

    p1: RuntimeModuleCapability
    p2: RuntimeModuleCapability
    p3: RuntimeModuleCapability
    p4: PlannedModuleCapability


class FeatureCapabilities(BaseModel):
    model_config = ConfigDict(frozen=True)

    p3_llm_draft: bool
    unified_retrieval: bool
    customerops_default_mode: CustomerOpsDefaultMode


class CapabilitiesResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    environment: EnvironmentName
    authority: AuthorityName
    auth: AuthCapability
    infrastructure: InfrastructureCapabilities
    modules: ModuleCapabilities
    features: FeatureCapabilities


__all__ = [
    "AuthCapability",
    "AuthorityName",
    "AvailabilityStatus",
    "CapabilitiesResponse",
    "CapabilityReasonCode",
    "CustomerOpsDefaultMode",
    "EnvironmentName",
    "FeatureCapabilities",
    "InfrastructureCapabilities",
    "ModuleCapabilities",
    "PlannedCapabilityStatus",
    "PlannedModuleCapability",
    "ReportedAuthMode",
    "RuntimeCapabilityStatus",
    "RuntimeModuleCapability",
    "StorageStatus",
]

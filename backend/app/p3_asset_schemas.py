"""Internal schemas for deterministic P3 draft-asset generation."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field

from app.p3_reuse_models import (
    ReuseAssetType,
    ReuseAssetVersionStatus,
    ReuseGenerationMode,
)
from app.p3_source_eligibility_schemas import P3SourceType


P3_ASSET_MANIFEST_SCHEMA_VERSION = "p3-asset-source-manifest-v1"
P3_DETERMINISTIC_TEMPLATE_VERSION = "v1"


class _FrozenSchema(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class P3AssetGenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    asset_type: ReuseAssetType
    template_key: str | None = Field(default=None, min_length=1, max_length=200)
    idempotency_key: str = Field(min_length=1, max_length=200)


class P3LLMAssetGenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    asset_type: ReuseAssetType
    prompt_key: str | None = Field(default=None, min_length=1, max_length=200)
    provider_profile: str | None = Field(
        default=None,
        min_length=1,
        max_length=50,
    )
    idempotency_key: str = Field(min_length=1, max_length=200)


class P3GenerationSourceRef(_FrozenSchema):
    source_item_id: str
    source_type: P3SourceType
    source_id: str
    source_version: int | None = None
    approved_review_id: str | None = None
    snapshot_id: str | None = None
    knowledge_asset_id: str | None = None
    content_fingerprint: str
    lineage_manifest_hash: str


class P3GenerationSourceMaterial(_FrozenSchema):
    """One governed, human-approved source exposed to deterministic templates."""

    source_item_id: str
    source_type: P3SourceType
    source_id: str
    source_version: int | None = None
    title: str = Field(min_length=1)
    approved_content: str = Field(min_length=1)
    approved_review_id: str | None = None
    snapshot_id: str | None = None
    knowledge_asset_id: str | None = None
    content_fingerprint: str
    lineage_manifest_hash: str
    source_ref: P3GenerationSourceRef


class P3TrainingSection(_FrozenSchema):
    heading: str
    content: str
    source_refs: list[P3GenerationSourceRef]


class P3TrainingMaterialPayload(_FrozenSchema):
    title: str
    learning_objectives: list[str]
    sections: list[P3TrainingSection]
    key_points: list[str]
    source_refs: list[P3GenerationSourceRef]


class P3SopStep(_FrozenSchema):
    order: int = Field(ge=1)
    instruction: str
    source_refs: list[P3GenerationSourceRef]


class P3SopPayload(_FrozenSchema):
    title: str
    purpose: str
    scope: str
    prerequisites: list[str]
    steps: list[P3SopStep]
    cautions: list[str]
    escalation_rules: list[str]
    source_refs: list[P3GenerationSourceRef]


class P3ServiceResponseStep(_FrozenSchema):
    order: int = Field(ge=1)
    response: str
    source_refs: list[P3GenerationSourceRef]


class P3ServiceScriptPayload(_FrozenSchema):
    title: str
    scenario: str
    opening: str
    response_steps: list[P3ServiceResponseStep]
    prohibited_claims: list[str]
    escalation: list[str]
    source_refs: list[P3GenerationSourceRef]


class P3QaItem(_FrozenSchema):
    question: str
    answer: str
    source_refs: list[P3GenerationSourceRef]


class P3QaBankPayload(_FrozenSchema):
    title: str
    items: list[P3QaItem]
    source_refs: list[P3GenerationSourceRef]


class P3SftRecord(_FrozenSchema):
    instruction: str
    input: str
    output: str
    metadata: dict[str, object]
    source_refs: list[P3GenerationSourceRef]


class P3SftDatasetPayload(_FrozenSchema):
    records: list[P3SftRecord]


P3DeterministicAssetPayload: TypeAlias = (
    P3TrainingMaterialPayload
    | P3SopPayload
    | P3ServiceScriptPayload
    | P3QaBankPayload
    | P3SftDatasetPayload
)


ASSET_PAYLOAD_SCHEMAS: dict[ReuseAssetType, type[BaseModel]] = {
    ReuseAssetType.TRAINING_MATERIAL: P3TrainingMaterialPayload,
    ReuseAssetType.SOP: P3SopPayload,
    ReuseAssetType.SERVICE_SCRIPT: P3ServiceScriptPayload,
    ReuseAssetType.QA_BANK: P3QaBankPayload,
    ReuseAssetType.SFT_DATASET: P3SftDatasetPayload,
}


class P3AssetVersionView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    asset_type: ReuseAssetType
    version_number: int
    status: ReuseAssetVersionStatus
    generation_mode: ReuseGenerationMode
    template_key: str
    template_version: str
    content_payload: dict[str, object]
    content_hash: str
    source_manifest_hash: str
    created_by_role: str
    request_id: str
    created_at: datetime
    updated_at: datetime
    failure_code: str | None
    failure_message: str | None


class P3AssetVersionSourceView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    asset_version_id: str
    source_item_id: str
    source_type: P3SourceType
    source_id: str
    source_version: int | None
    source_fingerprint: str
    approved_review_id: str | None
    snapshot_id: str | None
    knowledge_asset_id: str | None
    lineage_manifest_hash: str
    source_trace_snapshot: dict[str, object]
    created_at: datetime


class P3AssetVersionPageData(BaseModel):
    items: list[P3AssetVersionView]
    total: int
    limit: int
    offset: int


class P3AssetVersionSourcePageData(BaseModel):
    items: list[P3AssetVersionSourceView]
    total: int
    limit: int
    offset: int


class P3AssetVersionResponse(BaseModel):
    success: Literal[True] = True
    data: P3AssetVersionView
    requestId: str


class P3AssetVersionPageResponse(BaseModel):
    success: Literal[True] = True
    data: P3AssetVersionPageData
    requestId: str


class P3AssetVersionSourcePageResponse(BaseModel):
    success: Literal[True] = True
    data: P3AssetVersionSourcePageData
    requestId: str


__all__ = [
    "ASSET_PAYLOAD_SCHEMAS",
    "P3_ASSET_MANIFEST_SCHEMA_VERSION",
    "P3_DETERMINISTIC_TEMPLATE_VERSION",
    "P3AssetGenerateRequest",
    "P3AssetVersionPageData",
    "P3AssetVersionPageResponse",
    "P3AssetVersionResponse",
    "P3AssetVersionSourcePageData",
    "P3AssetVersionSourcePageResponse",
    "P3AssetVersionSourceView",
    "P3AssetVersionView",
    "P3DeterministicAssetPayload",
    "P3GenerationSourceMaterial",
    "P3GenerationSourceRef",
    "P3LLMAssetGenerateRequest",
    "P3QaBankPayload",
    "P3ServiceScriptPayload",
    "P3SftDatasetPayload",
    "P3SopPayload",
    "P3TrainingMaterialPayload",
]

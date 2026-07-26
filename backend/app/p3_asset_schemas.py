"""Internal schemas for deterministic P3 draft-asset generation."""

from __future__ import annotations

from typing import TypeAlias

from pydantic import BaseModel, ConfigDict, Field

from app.p3_reuse_models import ReuseAssetType
from app.p3_source_eligibility_schemas import P3SourceType


P3_ASSET_MANIFEST_SCHEMA_VERSION = "p3-asset-source-manifest-v1"
P3_DETERMINISTIC_TEMPLATE_VERSION = "v1"


class _FrozenSchema(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


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


__all__ = [
    "ASSET_PAYLOAD_SCHEMAS",
    "P3_ASSET_MANIFEST_SCHEMA_VERSION",
    "P3_DETERMINISTIC_TEMPLATE_VERSION",
    "P3DeterministicAssetPayload",
    "P3GenerationSourceMaterial",
    "P3GenerationSourceRef",
    "P3QaBankPayload",
    "P3ServiceScriptPayload",
    "P3SftDatasetPayload",
    "P3SopPayload",
    "P3TrainingMaterialPayload",
]

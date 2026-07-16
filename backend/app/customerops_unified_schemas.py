"""Additive CustomerOpsAgent v2 contracts for explicit Unified opt-in."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas import CustomerOpsRetrievalFilters
from app.unified_retrieval_schemas import UnifiedRetrievalSourceMode


class CustomerOpsUnifiedRetrievalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=500)
    top_k: int = Field(default=5, ge=1, le=10)
    filters: CustomerOpsRetrievalFilters | None = None
    conversation_id: str | None = Field(default=None, max_length=160)
    agent_session_id: str | None = Field(default=None, max_length=160)
    retrieval_strategy: Literal["p1", "unified"] = "p1"
    request_id: str | None = Field(default=None, max_length=160)

    @field_validator("query")
    @classmethod
    def _normalize_query(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("query must not be blank")
        return normalized

    @field_validator("request_id")
    @classmethod
    def _normalize_request_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None


class CustomerOpsUnifiedEvidence(BaseModel):
    """P1-compatible evidence fields plus explicit P2/Unified lineage."""

    score: float
    matched_terms: list[str] = Field(default_factory=list)
    chunk_id: str
    candidate_id: str
    source_type: str
    source_batch_id: str | None = None
    source_conversation_id: str | None = None
    source_message_ids: list[str] = Field(default_factory=list)
    source_bad_case_id: str | None = None
    source_retrieval_id: str | None = None
    source_chunk_ids: list[str] = Field(default_factory=list)
    source_legacy_id: str | None = None
    source_import_id: str | None = None
    migration_mode: str | None = None
    source_note: str | None = None
    knowledge_type: str
    intent: str
    tags: list[str] = Field(default_factory=list)
    risk_level: str
    quality_score: float
    review_status: Literal["approved"] = "approved"
    chunk_text: str
    build_method: str
    answer: str

    source_index: Literal["p1", "p2"]
    rank: int = Field(ge=1)
    fused_score: float | None = None
    original_score: float | None = None
    knowledge_asset_id: str | None = None
    asset_id: str | None = None
    content_type: str
    source_trace: dict[str, object] = Field(default_factory=dict)
    metadata: dict[str, object] = Field(default_factory=dict)


class CustomerOpsUnifiedRetrievalResponse(BaseModel):
    """Keeps legacy top-level fields while making actual strategy explicit."""

    retrieval_id: str
    query: str
    top_k: int
    retrieval_mode: str
    results: list[CustomerOpsUnifiedEvidence]
    fallback_used: bool = False
    fallback_reason: str | None = None
    created_at: str

    requested_retrieval_strategy: Literal["p1", "unified"]
    actual_retrieval_strategy: Literal["p1", "unified"]
    unified_attempted: bool = False
    unified_retrieval_id: str | None = None
    legacy_retrieval_id: str | None = None
    legacy_retrieval_mode: str | None = None
    legacy_fallback_used: bool = False
    legacy_fallback_reason: str | None = None
    source_modes: dict[str, UnifiedRetrievalSourceMode] = Field(default_factory=dict)
    request_id: str | None = None


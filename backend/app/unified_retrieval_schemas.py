"""Versioned contracts for the P2-M8.2 unified retrieval shadow gate."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.answerability import AnswerabilityDecision


UnifiedSource = Literal["p1", "p2"]
UnifiedRetrievalMode = Literal[
    "p1_only",
    "p2_only",
    "unified_rrf",
    "partial_p1",
    "partial_p2",
    "shadow_control",
]


class UnifiedRetrievalRequest(BaseModel):
    """Additive request contract; it cannot opt into archived knowledge."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=500)
    top_k: int = Field(default=5, ge=1, le=20)
    sources: list[UnifiedSource] = Field(default_factory=lambda: ["p1", "p2"])
    fusion_enabled: bool = True
    shadow_mode: bool = True
    include_archived: Literal[False] = False
    debug: bool = False
    request_id: str | None = Field(default=None, max_length=160)
    evaluation_scope: str | None = Field(
        default=None,
        pattern=r"^datahub-eval:[A-Za-z0-9][A-Za-z0-9._-]{5,95}$",
        max_length=110,
        description="Optional run-scoped P2 Eval namespace; never changes P1 control.",
    )

    @field_validator("query")
    @classmethod
    def _normalize_query(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("query must not be blank")
        return normalized

    @field_validator("sources", mode="before")
    @classmethod
    def _normalize_sources(cls, value: object) -> list[str]:
        if isinstance(value, str):
            items = [value]
        elif isinstance(value, (list, tuple)):
            items = list(value)
        else:
            raise ValueError("sources must be p1, p2, all, or a list of them")
        if not items:
            raise ValueError("sources must not be empty")
        if not all(isinstance(item, str) for item in items):
            raise ValueError("sources entries must be strings")
        normalized = [item.strip().lower() for item in items]
        if "all" in normalized:
            if len(normalized) != 1:
                raise ValueError("all cannot be combined with another source")
            return ["p1", "p2"]
        unknown = [item for item in normalized if item not in {"p1", "p2"}]
        if unknown:
            raise ValueError("sources contains an unsupported source")
        if len(normalized) != len(set(normalized)):
            raise ValueError("sources must not contain duplicates")
        return normalized

    @field_validator("request_id")
    @classmethod
    def _normalize_request_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class UnifiedRetrievalResult(BaseModel):
    """One evidence item with route-local diagnostics and governed lineage."""

    source_index: UnifiedSource
    source_type: str
    rank: int = Field(ge=1)
    fused_score: float | None = None
    original_rank: int = Field(ge=1)
    original_score: float
    candidate_id: str | None = None
    knowledge_asset_id: str | None = None
    chunk_id: str
    asset_id: str | None = None
    evidence_text: str
    content_type: str
    source_trace: dict[str, object] = Field(default_factory=dict)
    metadata: dict[str, object] = Field(default_factory=dict)


class UnifiedRetrievalSourceMode(BaseModel):
    source_index: UnifiedSource
    mode: str
    status: Literal["ok", "error", "timeout", "skipped"]
    result_count: int = Field(ge=0)
    latency_ms: float = Field(ge=0)
    fallback_used: bool = False
    fallback_reason: str | None = None
    error_code: str | None = None
    error_type: str | None = None
    embedding_provider: str | None = None
    embedding_model: str | None = None
    embedding_dimension: int | None = None
    embedding_profile: str | None = None
    native_retrieval_id: str | None = None


class UnifiedRetrievalLatency(BaseModel):
    total: float = Field(ge=0)
    p1: float | None = Field(default=None, ge=0)
    p2: float | None = Field(default=None, ge=0)
    fusion: float = Field(default=0, ge=0)


class UnifiedRetrievalShadowComparison(BaseModel):
    control_mode: str
    candidate_mode: str
    control_count: int = Field(ge=0)
    candidate_count: int = Field(ge=0)
    overlap_count: int = Field(ge=0)
    control_only_count: int = Field(ge=0)
    candidate_only_count: int = Field(ge=0)
    rank_changed_count: int = Field(ge=0)
    control_result_ids: list[str] = Field(default_factory=list)
    candidate_result_ids: list[str] = Field(default_factory=list)
    summary: dict[str, object] = Field(default_factory=dict)


class UnifiedRetrievalResponse(BaseModel):
    retrieval_id: str
    request_id: str | None = None
    query: str
    top_k: int = Field(ge=1, le=20)
    sources: list[UnifiedSource]
    retrieval_mode: UnifiedRetrievalMode
    control_mode: str | None = None
    candidate_mode: str | None = None
    source_modes: dict[UnifiedSource, UnifiedRetrievalSourceMode]
    results: list[UnifiedRetrievalResult]
    control_results: list[UnifiedRetrievalResult] = Field(default_factory=list)
    candidate_results: list[UnifiedRetrievalResult] = Field(default_factory=list)
    p1_result_count: int = Field(default=0, ge=0)
    p2_result_count: int = Field(default=0, ge=0)
    fused_result_count: int = Field(default=0, ge=0)
    fallback_used: bool = False
    fallback_reason: str | None = None
    partial: bool = False
    source_distribution: dict[str, int] = Field(default_factory=dict)
    latency_ms: UnifiedRetrievalLatency
    shadow_comparison: UnifiedRetrievalShadowComparison | None = None
    created_at: str
    debug: dict[str, object] | None = None
    answerability: AnswerabilityDecision | None = None

"""P2-M8.1 schemas for isolated P2 semantic retrieval."""

from typing import Literal

from pydantic import BaseModel, Field

from app.answerability import AnswerabilityDecision
from app.knowledge_index_schemas import KnowledgeIndexSourceTrace


class P2RetrievalRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    top_k: int = Field(default=5, ge=1, le=20)
    debug: bool = False
    request_id: str | None = Field(default=None, max_length=160)
    evaluation_scope: str | None = Field(
        default=None,
        pattern=r"^datahub-eval:[A-Za-z0-9][A-Za-z0-9._-]{5,95}$",
        max_length=110,
        description="Optional test-corpus namespace; omitted for normal retrieval.",
    )


class P2RetrievalResult(BaseModel):
    rank: int = Field(ge=1)
    score: float
    chunk_id: str
    index_entry_id: str
    knowledge_asset_id: str
    asset_id: str
    chunk_text: str
    content_type: str
    source_trace: KnowledgeIndexSourceTrace
    metadata: dict[str, object]


class P2RetrievalResponse(BaseModel):
    retrieval_id: str
    retrieval_mode: Literal["p2_vector_retrieval"] = "p2_vector_retrieval"
    query: str
    top_k: int
    matched_count: int = Field(ge=0)
    results: list[P2RetrievalResult]
    fallback_used: Literal[False] = False
    fallback_reason: str | None = None
    embedding_provider: str | None = None
    embedding_model: str | None = None
    embedding_dimension: int | None = None
    embedding_profile: str | None = None
    latency_ms: float = Field(ge=0)
    request_id: str | None = None
    evaluation_scope: str | None = None
    created_at: str
    error_code: str | None = None
    error_message: str | None = None
    debug: dict[str, object] | None = None
    answerability: AnswerabilityDecision | None = None

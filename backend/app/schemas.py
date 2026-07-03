from typing import Literal

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    message_id: str = Field(min_length=1, max_length=120)
    role: Literal["customer", "agent", "system", "unknown"]
    content: str = Field(min_length=1, max_length=10000)
    timestamp: str = Field(min_length=1, max_length=80)


class Conversation(BaseModel):
    conversation_id: str = Field(min_length=1, max_length=120)
    messages: list[ChatMessage] = Field(min_length=1)


class ImportJsonRequest(BaseModel):
    source_name: str = Field(min_length=1, max_length=160)
    conversations: list[Conversation] = Field(min_length=1)


class SourceBatchMetadata(BaseModel):
    batch_id: str
    source_name: str
    message_count: int
    conversation_count: int
    created_at: str
    status: Literal["raw_imported"]


class CleaningJobMetadata(BaseModel):
    job_id: str
    source_batch_id: str
    sanitized_batch_id: str
    raw_message_count: int
    sanitized_message_count: int
    dropped_message_count: int
    pii_detected_count: int
    status: Literal["completed"]
    created_at: str
    completed_at: str


class SanitizedMessage(BaseModel):
    source_batch_id: str
    conversation_id: str
    message_id: str
    source_message_id: str
    role: Literal["customer", "agent", "system"]
    content: str
    pii_detected: bool
    pii_types: list[str]
    cleaning_notes: list[str]


class SanitizedBatch(BaseModel):
    batch_id: str
    source_batch_id: str
    status: Literal["sanitized"]
    raw_message_count: int
    sanitized_message_count: int
    dropped_message_count: int
    pii_detected_count: int
    created_at: str
    messages: list[SanitizedMessage]


class KnowledgeCandidate(BaseModel):
    candidate_id: str
    source_batch_id: str
    source_conversation_id: str
    source_message_ids: list[str]
    knowledge_type: Literal[
        "faq",
        "standard_answer",
        "business_rule",
        "human_handoff_rule",
        "forbidden_answer_rule",
    ]
    question: str
    answer: str
    intent: Literal[
        "shipping",
        "refund",
        "order_status",
        "product_info",
        "handoff",
        "prohibited_answer",
        "general",
    ]
    tags: list[str]
    risk_level: Literal["low", "medium", "high"]
    review_status: Literal["pending_review", "needs_revision", "approved", "rejected"]
    quality_score: float
    extraction_method: Literal["rule_based_mock"]
    created_at: str
    reviewer: str | None = None
    review_note: str | None = None
    reviewed_at: str | None = None
    updated_at: str | None = None


class CandidateUpdateRequest(BaseModel):
    question: str | None = Field(default=None, min_length=1, max_length=4000)
    answer: str | None = Field(default=None, min_length=1, max_length=10000)
    intent: Literal[
        "shipping",
        "refund",
        "order_status",
        "product_info",
        "handoff",
        "prohibited_answer",
        "general",
    ] | None = None
    tags: list[str] | None = None
    risk_level: Literal["low", "medium", "high"] | None = None
    quality_score: float | None = Field(default=None, ge=0, le=1)


class ReviewDecisionRequest(BaseModel):
    reviewer: str = Field(min_length=1, max_length=120)
    review_note: str = Field(default="", max_length=2000)


class ReviewRecord(BaseModel):
    review_id: str
    candidate_id: str
    review_status: Literal["needs_revision", "approved", "rejected"]
    reviewer: str
    review_note: str
    reviewed_at: str


class RagChunk(BaseModel):
    chunk_id: str
    candidate_id: str
    source_batch_id: str
    source_conversation_id: str
    source_message_ids: list[str]
    knowledge_type: Literal[
        "faq",
        "standard_answer",
        "business_rule",
        "human_handoff_rule",
        "forbidden_answer_rule",
    ]
    intent: Literal[
        "shipping",
        "refund",
        "order_status",
        "product_info",
        "handoff",
        "prohibited_answer",
        "general",
    ]
    tags: list[str]
    risk_level: Literal["low", "medium", "high"]
    quality_score: float
    review_status: Literal["approved"]
    chunk_text: str
    created_at: str
    build_method: Literal["local_json_mock_retrieval"]


class RagBuildResult(BaseModel):
    built_count: int
    skipped_count: int
    skipped_reasons: dict[str, int]
    chunk_count: int
    status: Literal["completed"]
    build_method: Literal["local_json_mock_retrieval"]
    created_at: str


class RagSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    top_k: int = Field(default=5, ge=1, le=20)


class RagSearchResult(BaseModel):
    score: float
    chunk_id: str
    candidate_id: str
    source_batch_id: str
    source_conversation_id: str
    source_message_ids: list[str]
    knowledge_type: str
    intent: str
    tags: list[str]
    risk_level: str
    quality_score: float
    review_status: Literal["approved"]
    chunk_text: str
    build_method: str


class ExtractionJobMetadata(BaseModel):
    job_id: str
    source_batch_id: str
    candidate_count: int
    status: Literal["completed"]
    extraction_method: Literal["rule_based_mock"]
    created_at: str
    completed_at: str


class ApiResponse(BaseModel):
    success: bool
    data: object
    requestId: str

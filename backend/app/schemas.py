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
    source_type: Literal[
        "sanitized_batch",
        "chat_logs",
        "public_dataset",
        "bad_case",
        "legacy_rag",
        "manual",
    ] = "sanitized_batch"
    source_batch_id: str | None = None
    source_conversation_id: str | None = None
    source_message_ids: list[str]
    source_bad_case_id: str | None = None
    source_retrieval_id: str | None = None
    source_chunk_ids: list[str] = Field(default_factory=list)
    source_legacy_id: str | None = None
    source_import_id: str | None = None
    linked_candidate_id: str | None = None
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
    extraction_method: Literal[
        "rule_based_mock",
        "bad_case_resolution",
        "legacy_rag_migration",
    ]
    migration_mode: Literal["trusted_import", "review_required"] | None = None
    source_note: str | None = None
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
    source_type: Literal[
        "sanitized_batch",
        "chat_logs",
        "public_dataset",
        "bad_case",
        "legacy_rag",
        "manual",
    ] = "sanitized_batch"
    source_batch_id: str | None = None
    source_conversation_id: str | None = None
    source_message_ids: list[str]
    source_bad_case_id: str | None = None
    source_retrieval_id: str | None = None
    source_chunk_ids: list[str] = Field(default_factory=list)
    source_legacy_id: str | None = None
    source_import_id: str | None = None
    migration_mode: Literal["trusted_import", "review_required"] | None = None
    source_note: str | None = None
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
    updated_count: int
    skipped_count: int
    skipped_reasons: dict[str, int]
    chunk_count: int
    status: Literal["completed"]
    build_method: Literal["local_json_mock_retrieval"]
    created_at: str


class RagSearchRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=5)


class RagSearchResult(BaseModel):
    score: float
    matched_terms: list[str]
    chunk_id: str
    candidate_id: str
    source_type: str
    source_batch_id: str | None = None
    source_conversation_id: str | None = None
    source_message_ids: list[str]
    source_bad_case_id: str | None = None
    source_retrieval_id: str | None = None
    source_chunk_ids: list[str] = Field(default_factory=list)
    source_legacy_id: str | None = None
    source_import_id: str | None = None
    migration_mode: str | None = None
    source_note: str | None = None
    knowledge_type: str
    intent: str
    tags: list[str]
    risk_level: str
    quality_score: float
    review_status: Literal["approved"]
    chunk_text: str
    build_method: str


class CustomerOpsRetrievalFilters(BaseModel):
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


class CustomerOpsRetrievalRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=5)
    filters: CustomerOpsRetrievalFilters | None = None
    conversation_id: str | None = Field(default=None, max_length=160)
    agent_session_id: str | None = Field(default=None, max_length=160)


class CustomerOpsRetrievalResult(RagSearchResult):
    answer: str


class CustomerOpsRetrievalResponse(BaseModel):
    retrieval_id: str
    query: str
    top_k: int
    retrieval_mode: Literal["customerops_local_mock_retrieval"]
    results: list[CustomerOpsRetrievalResult]
    created_at: str


class CustomerOpsRetrievalTrace(BaseModel):
    retrieval_id: str
    query: str
    top_k: int
    filters: dict[str, object]
    result_count: int
    result_chunk_ids: list[str]
    conversation_id: str | None = None
    agent_session_id: str | None = None
    created_at: str
    retrieval_mode: Literal["customerops_local_mock_retrieval"]


class BadCaseSubmitRequest(BaseModel):
    retrieval_id: str = Field(min_length=1, max_length=160)
    user_query: str = Field(min_length=1)
    agent_answer: str = Field(min_length=1)
    issue_type: str = Field(min_length=1, max_length=80)
    expected_answer: str | None = None
    severity: str = Field(default="medium", max_length=20)
    conversation_id: str | None = Field(default=None, max_length=160)
    agent_session_id: str | None = Field(default=None, max_length=160)
    metadata: dict[str, object] | None = None


class BadCaseRecord(BaseModel):
    bad_case_id: str
    retrieval_id: str
    user_query: str
    agent_answer: str
    issue_type: str
    expected_answer: str | None = None
    severity: str
    status: str
    review_note: str
    resolution_type: str | None = None
    linked_candidate_id: str | None = None
    linked_chunk_ids: list[str]
    retrieval_result_count: int
    conversation_id: str | None = None
    agent_session_id: str | None = None
    metadata: dict[str, object]
    created_at: str
    updated_at: str


class BadCaseUpdateRequest(BaseModel):
    status: str | None = Field(default=None, max_length=40)
    review_note: str | None = Field(default=None, max_length=2000)
    resolution_type: str | None = Field(default=None, max_length=80)
    linked_candidate_id: str | None = Field(default=None, max_length=160)


class BadCaseDraftRequest(BaseModel):
    question: str = Field(min_length=1)
    answer: str = Field(min_length=1)
    intent: str = Field(default="general", max_length=80)
    tags: list[str] = Field(default_factory=list)
    risk_level: str = Field(default="medium", max_length=20)
    quality_score: float = Field(default=0.7)
    knowledge_type: str = Field(default="faq", max_length=80)
    reviewer: str | None = Field(default=None, max_length=120)
    review_note: str | None = Field(default=None, max_length=2000)


class LegacyRagItem(BaseModel):
    legacy_id: str = Field(min_length=1, max_length=160)
    question: str = Field(min_length=1, max_length=500)
    answer: str = Field(min_length=1, max_length=2000)
    intent: Literal[
        "shipping",
        "refund",
        "order_status",
        "product_info",
        "handoff",
        "prohibited_answer",
        "general",
    ] = "general"
    tags: list[str] = Field(default_factory=list)
    risk_level: Literal["low", "medium", "high"] = "medium"
    quality_score: float = Field(default=0.75, ge=0, le=1)
    knowledge_type: Literal[
        "faq",
        "standard_answer",
        "business_rule",
        "human_handoff_rule",
        "forbidden_answer_rule",
    ] = "faq"
    source_note: str | None = Field(default=None, max_length=1000)


class LegacyRagImportRequest(BaseModel):
    source_name: str = Field(min_length=1, max_length=160)
    source_type: Literal["legacy_rag"] = "legacy_rag"
    trusted_import: bool = False
    exported_at: str | None = Field(default=None, max_length=80)
    items: list[LegacyRagItem] = Field(min_length=1)


class LegacyRagImportMetadata(BaseModel):
    import_id: str
    source_name: str
    source_type: Literal["legacy_rag"]
    trusted_import: bool
    migration_mode: Literal["trusted_import", "review_required"]
    item_count: int
    created_candidate_count: int
    updated_count: int
    approved_count: int
    pending_review_count: int
    skipped_count: int
    skipped_reasons: dict[str, int]
    created_at: str
    candidate_ids: list[str]


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

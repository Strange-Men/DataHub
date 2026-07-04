import json
import re
from hashlib import sha1
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from app.schemas import (
    BadCaseDraftRequest,
    BadCaseRecord,
    BadCaseSubmitRequest,
    BadCaseUpdateRequest,
    CandidateUpdateRequest,
    CleaningJobMetadata,
    CustomerOpsRetrievalFilters,
    CustomerOpsRetrievalRequest,
    CustomerOpsRetrievalResponse,
    CustomerOpsRetrievalResult,
    CustomerOpsRetrievalTrace,
    ExtractionJobMetadata,
    ImportJsonRequest,
    KnowledgeCandidate,
    LegacyRagImportMetadata,
    LegacyRagImportRequest,
    LegacyRagItem,
    RagBuildResult,
    RagChunk,
    RagSearchResult,
    ReviewDecisionRequest,
    ReviewRecord,
    SanitizedBatch,
    SanitizedMessage,
    SourceBatchMetadata,
)


BASE_DIR = Path(__file__).resolve().parent.parent
STORAGE_DIR = BASE_DIR / "storage"
RAW_BATCH_DIR = STORAGE_DIR / "raw_batches"
SANITIZED_BATCH_DIR = STORAGE_DIR / "sanitized_batches"
CLEANING_JOB_DIR = STORAGE_DIR / "cleaning_jobs"
EXTRACTION_JOB_DIR = STORAGE_DIR / "extraction_jobs"
KNOWLEDGE_CANDIDATE_DIR = STORAGE_DIR / "knowledge_candidates"
REVIEW_RECORD_DIR = STORAGE_DIR / "review_records"
RAG_CHUNK_DIR = STORAGE_DIR / "rag_chunks"
RETRIEVAL_LOG_DIR = STORAGE_DIR / "retrieval_logs"
BAD_CASE_DIR = STORAGE_DIR / "bad_cases"
LEGACY_RAG_IMPORT_DIR = STORAGE_DIR / "legacy_rag_imports"
INDEX_FILE = RAW_BATCH_DIR / "index.json"
SANITIZED_INDEX_FILE = SANITIZED_BATCH_DIR / "index.json"
CLEANING_JOB_INDEX_FILE = CLEANING_JOB_DIR / "index.json"
EXTRACTION_JOB_INDEX_FILE = EXTRACTION_JOB_DIR / "index.json"
KNOWLEDGE_CANDIDATE_INDEX_FILE = KNOWLEDGE_CANDIDATE_DIR / "index.json"
REVIEW_RECORD_INDEX_FILE = REVIEW_RECORD_DIR / "index.json"
RAG_CHUNK_INDEX_FILE = RAG_CHUNK_DIR / "index.json"
RETRIEVAL_LOG_INDEX_FILE = RETRIEVAL_LOG_DIR / "index.json"
BAD_CASE_INDEX_FILE = BAD_CASE_DIR / "index.json"
LEGACY_RAG_IMPORT_INDEX_FILE = LEGACY_RAG_IMPORT_DIR / "index.json"

EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
PHONE_PATTERN = re.compile(
    r"(?<!\w)(?:\+?\d[\d\s().-]{7,}\d)(?!\w)"
)
ORDER_PATTERN = re.compile(
    r"\b(?:order|order id|order number|订单号)(?:\s+is)?[:#\s-]*[A-Z0-9-]{5,}\b",
    re.IGNORECASE,
)
TRACKING_PATTERN = re.compile(
    r"\b(?:tracking|tracking id|tracking number|物流单号)[:#\s-]*[A-Z]{1,4}[0-9A-Z-]{7,}\b",
    re.IGNORECASE,
)
ADDRESS_PATTERN = re.compile(
    r"\b\d{1,6}\s+[A-Za-z0-9.' -]+(?:street|st|road|rd|avenue|ave|lane|ln|drive|dr|blvd|boulevard)\b(?:,\s*[A-Za-z .-]+){0,3}",
    re.IGNORECASE,
)


def _ensure_storage() -> None:
    RAW_BATCH_DIR.mkdir(parents=True, exist_ok=True)
    SANITIZED_BATCH_DIR.mkdir(parents=True, exist_ok=True)
    CLEANING_JOB_DIR.mkdir(parents=True, exist_ok=True)
    EXTRACTION_JOB_DIR.mkdir(parents=True, exist_ok=True)
    KNOWLEDGE_CANDIDATE_DIR.mkdir(parents=True, exist_ok=True)
    REVIEW_RECORD_DIR.mkdir(parents=True, exist_ok=True)
    RAG_CHUNK_DIR.mkdir(parents=True, exist_ok=True)
    RETRIEVAL_LOG_DIR.mkdir(parents=True, exist_ok=True)
    BAD_CASE_DIR.mkdir(parents=True, exist_ok=True)
    LEGACY_RAG_IMPORT_DIR.mkdir(parents=True, exist_ok=True)
    if not INDEX_FILE.exists():
        INDEX_FILE.write_text("[]", encoding="utf-8")
    if not SANITIZED_INDEX_FILE.exists():
        SANITIZED_INDEX_FILE.write_text("[]", encoding="utf-8")
    if not CLEANING_JOB_INDEX_FILE.exists():
        CLEANING_JOB_INDEX_FILE.write_text("[]", encoding="utf-8")
    if not EXTRACTION_JOB_INDEX_FILE.exists():
        EXTRACTION_JOB_INDEX_FILE.write_text("[]", encoding="utf-8")
    if not KNOWLEDGE_CANDIDATE_INDEX_FILE.exists():
        KNOWLEDGE_CANDIDATE_INDEX_FILE.write_text("[]", encoding="utf-8")
    if not REVIEW_RECORD_INDEX_FILE.exists():
        REVIEW_RECORD_INDEX_FILE.write_text("[]", encoding="utf-8")
    if not RAG_CHUNK_INDEX_FILE.exists():
        RAG_CHUNK_INDEX_FILE.write_text("[]", encoding="utf-8")
    if not RETRIEVAL_LOG_INDEX_FILE.exists():
        RETRIEVAL_LOG_INDEX_FILE.write_text("[]", encoding="utf-8")
    if not BAD_CASE_INDEX_FILE.exists():
        BAD_CASE_INDEX_FILE.write_text("[]", encoding="utf-8")
    if not LEGACY_RAG_IMPORT_INDEX_FILE.exists():
        LEGACY_RAG_IMPORT_INDEX_FILE.write_text("[]", encoding="utf-8")


def _read_json_list(path: Path) -> list[dict[str, object]]:
    _ensure_storage()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    return data


def _write_json_list(path: Path, items: list[dict[str, object]]) -> None:
    _ensure_storage()
    path.write_text(
        json.dumps(items, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def create_raw_batch(payload: ImportJsonRequest) -> SourceBatchMetadata:
    _ensure_storage()
    batch_id = f"batch_{uuid4().hex[:12]}"
    created_at = datetime.now(UTC).isoformat()
    message_count = sum(len(conversation.messages) for conversation in payload.conversations)
    metadata = SourceBatchMetadata(
        batch_id=batch_id,
        source_name=payload.source_name,
        message_count=message_count,
        conversation_count=len(payload.conversations),
        created_at=created_at,
        status="raw_imported",
    )

    batch_file = RAW_BATCH_DIR / f"{batch_id}.json"
    batch_file.write_text(
        json.dumps(
            {
                "metadata": metadata.model_dump(),
                "raw_payload": payload.model_dump(),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    items = _read_json_list(INDEX_FILE)
    items.append(metadata.model_dump())
    _write_json_list(INDEX_FILE, items)
    return metadata


def list_raw_batches() -> list[SourceBatchMetadata]:
    return [SourceBatchMetadata(**item) for item in _read_json_list(INDEX_FILE)]


def get_raw_batch_metadata(batch_id: str) -> SourceBatchMetadata | None:
    for item in _read_json_list(INDEX_FILE):
        if item.get("batch_id") == batch_id:
            return SourceBatchMetadata(**item)
    return None


def get_raw_batch_document(batch_id: str) -> dict[str, object] | None:
    _ensure_storage()
    batch_file = RAW_BATCH_DIR / f"{batch_id}.json"
    if not batch_file.exists():
        return None
    try:
        data = json.loads(batch_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    return data


def _standardize_role(value: object) -> tuple[str, list[str]]:
    role = str(value or "system").strip().lower()
    notes: list[str] = []
    role_map = {
        "customer": "customer",
        "user": "customer",
        "client": "customer",
        "agent": "agent",
        "assistant": "agent",
        "support": "agent",
        "system": "system",
    }
    standardized = role_map.get(role, "system")
    if standardized != role:
        notes.append("role_standardized")
    return standardized, notes


def _mask_pii(content: str) -> tuple[str, list[str]]:
    masked = content
    pii_types: list[str] = []

    replacements = [
        ("EMAIL", EMAIL_PATTERN, "[EMAIL]"),
        ("TRACKING_ID", TRACKING_PATTERN, "[TRACKING_ID]"),
        ("ORDER_ID", ORDER_PATTERN, "[ORDER_ID]"),
        ("ADDRESS", ADDRESS_PATTERN, "[ADDRESS]"),
        ("PHONE", PHONE_PATTERN, "[PHONE]"),
    ]

    for pii_type, pattern, replacement in replacements:
        masked, count = pattern.subn(replacement, masked)
        if count > 0:
            pii_types.append(pii_type)

    return masked, pii_types


def _safe_message_id(conversation_index: int, message_index: int, message: dict[str, object]) -> str:
    value = str(message.get("message_id") or "").strip()
    if value:
        return value
    return f"msg_missing_{conversation_index + 1}_{message_index + 1}"


def run_cleaning(batch_id: str) -> CleaningJobMetadata | None:
    raw_document = get_raw_batch_document(batch_id)
    if raw_document is None:
        return None

    raw_payload = raw_document.get("raw_payload")
    if not isinstance(raw_payload, dict):
        return None

    conversations = raw_payload.get("conversations")
    if not isinstance(conversations, list):
        return None

    created_at = datetime.now(UTC).isoformat()
    job_id = f"clean_job_{uuid4().hex[:12]}"
    raw_message_count = 0
    dropped_message_count = 0
    sanitized_messages: list[SanitizedMessage] = []

    for conversation_index, conversation in enumerate(conversations):
        if not isinstance(conversation, dict):
            continue
        conversation_id = str(
            conversation.get("conversation_id")
            or f"conv_missing_{conversation_index + 1}"
        ).strip()
        messages = conversation.get("messages")
        if not isinstance(messages, list):
            continue

        for message_index, message in enumerate(messages):
            if not isinstance(message, dict):
                continue
            raw_message_count += 1
            notes: list[str] = []
            raw_content = str(message.get("content") or "")
            content = raw_content.strip()
            if raw_content != content:
                notes.append("content_trimmed")
            if not content:
                dropped_message_count += 1
                continue

            role, role_notes = _standardize_role(message.get("role"))
            notes.extend(role_notes)
            message_id = _safe_message_id(conversation_index, message_index, message)
            source_message_id = str(message.get("message_id") or message_id).strip() or message_id
            masked_content, pii_types = _mask_pii(content)
            if pii_types:
                notes.append("pii_masked")

            sanitized_messages.append(
                SanitizedMessage(
                    source_batch_id=batch_id,
                    conversation_id=conversation_id,
                    message_id=message_id,
                    source_message_id=source_message_id,
                    role=role,  # type: ignore[arg-type]
                    content=masked_content,
                    pii_detected=bool(pii_types),
                    pii_types=pii_types,
                    cleaning_notes=notes,
                )
            )

    completed_at = datetime.now(UTC).isoformat()
    pii_detected_count = sum(1 for message in sanitized_messages if message.pii_detected)
    sanitized_batch = SanitizedBatch(
        batch_id=batch_id,
        source_batch_id=batch_id,
        status="sanitized",
        raw_message_count=raw_message_count,
        sanitized_message_count=len(sanitized_messages),
        dropped_message_count=dropped_message_count,
        pii_detected_count=pii_detected_count,
        created_at=completed_at,
        messages=sanitized_messages,
    )
    job = CleaningJobMetadata(
        job_id=job_id,
        source_batch_id=batch_id,
        sanitized_batch_id=batch_id,
        raw_message_count=raw_message_count,
        sanitized_message_count=len(sanitized_messages),
        dropped_message_count=dropped_message_count,
        pii_detected_count=pii_detected_count,
        status="completed",
        created_at=created_at,
        completed_at=completed_at,
    )

    _ensure_storage()
    (SANITIZED_BATCH_DIR / f"{batch_id}.json").write_text(
        json.dumps(sanitized_batch.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (CLEANING_JOB_DIR / f"{job_id}.json").write_text(
        json.dumps(job.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    sanitized_items = [
        item for item in _read_json_list(SANITIZED_INDEX_FILE)
        if item.get("batch_id") != batch_id
    ]
    sanitized_items.append(
        {
            "batch_id": sanitized_batch.batch_id,
            "source_batch_id": sanitized_batch.source_batch_id,
            "status": sanitized_batch.status,
            "raw_message_count": sanitized_batch.raw_message_count,
            "sanitized_message_count": sanitized_batch.sanitized_message_count,
            "dropped_message_count": sanitized_batch.dropped_message_count,
            "pii_detected_count": sanitized_batch.pii_detected_count,
            "created_at": sanitized_batch.created_at,
        }
    )
    _write_json_list(SANITIZED_INDEX_FILE, sanitized_items)

    job_items = _read_json_list(CLEANING_JOB_INDEX_FILE)
    job_items.append(job.model_dump())
    _write_json_list(CLEANING_JOB_INDEX_FILE, job_items)
    return job


def get_cleaning_job(job_id: str) -> CleaningJobMetadata | None:
    _ensure_storage()
    job_file = CLEANING_JOB_DIR / f"{job_id}.json"
    if not job_file.exists():
        return None
    try:
        data = json.loads(job_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    return CleaningJobMetadata(**data)


def get_sanitized_batch(batch_id: str) -> SanitizedBatch | None:
    _ensure_storage()
    batch_file = SANITIZED_BATCH_DIR / f"{batch_id}.json"
    if not batch_file.exists():
        return None
    try:
        data = json.loads(batch_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    return SanitizedBatch(**data)


def _infer_intent(question: str, answer: str) -> tuple[str, list[str]]:
    text = f"{question} {answer}".lower()
    if any(term in text for term in ["shipping", "delivery", "dispatch"]):
        return "shipping", ["shipping", "delivery"]
    if any(term in text for term in ["refund", "return", "exchange"]):
        return "refund", ["refund", "return"]
    if any(term in text for term in ["order", "tracking", "track", "shipment"]):
        return "order_status", ["order", "tracking"]
    if any(term in text for term in ["product", "size", "color", "material", "sku"]):
        return "product_info", ["product"]
    if any(term in text for term in ["human", "support", "agent", "representative"]):
        return "handoff", ["handoff", "support"]
    if any(term in text for term in ["cannot answer", "not allowed", "prohibited"]):
        return "prohibited_answer", ["policy"]
    return "general", ["general"]


def _infer_knowledge_type(intent: str) -> str:
    if intent == "handoff":
        return "human_handoff_rule"
    if intent == "prohibited_answer":
        return "forbidden_answer_rule"
    return "faq"


def _quality_score(question: str, answer: str) -> float:
    score = 0.55
    if question.endswith("?"):
        score += 0.1
    if len(question) >= 12:
        score += 0.1
    if len(answer) >= 24:
        score += 0.1
    if any(term in f"{question} {answer}".lower() for term in ["shipping", "refund", "order", "tracking", "delivery"]):
        score += 0.1
    return round(min(score, 0.95), 2)


def _risk_level(question: str, answer: str) -> str:
    text = f"{question} {answer}".lower()
    if any(term in text for term in ["legal", "medical", "guarantee", "password", "payment"]):
        return "high"
    if any(term in text for term in ["refund", "return", "order", "address"]):
        return "medium"
    return "low"


def run_extraction(batch_id: str) -> ExtractionJobMetadata | None:
    sanitized = get_sanitized_batch(batch_id)
    if sanitized is None:
        return None

    created_at = datetime.now(UTC).isoformat()
    job_id = f"extract_job_{uuid4().hex[:12]}"
    candidates: list[KnowledgeCandidate] = []
    messages_by_conversation: dict[str, list[SanitizedMessage]] = {}

    for message in sanitized.messages:
        messages_by_conversation.setdefault(message.conversation_id, []).append(message)

    for conversation_id, messages in messages_by_conversation.items():
        for index, message in enumerate(messages):
            if message.role != "customer":
                continue
            answer_message = next(
                (candidate for candidate in messages[index + 1:] if candidate.role == "agent"),
                None,
            )
            if answer_message is None:
                continue
            question = message.content.strip()
            answer = answer_message.content.strip()
            if not question or not answer:
                continue
            intent, tags = _infer_intent(question, answer)
            candidate_id = f"kc_{uuid4().hex[:12]}"
            candidates.append(
                KnowledgeCandidate(
                    candidate_id=candidate_id,
                    source_batch_id=batch_id,
                    source_conversation_id=conversation_id,
                    source_message_ids=[message.source_message_id, answer_message.source_message_id],
                    knowledge_type=_infer_knowledge_type(intent),  # type: ignore[arg-type]
                    question=question,
                    answer=answer,
                    intent=intent,  # type: ignore[arg-type]
                    tags=tags,
                    risk_level=_risk_level(question, answer),  # type: ignore[arg-type]
                    review_status="pending_review",
                    quality_score=_quality_score(question, answer),
                    extraction_method="rule_based_mock",
                    created_at=created_at,
                )
            )

    completed_at = datetime.now(UTC).isoformat()
    job = ExtractionJobMetadata(
        job_id=job_id,
        source_batch_id=batch_id,
        candidate_count=len(candidates),
        status="completed",
        extraction_method="rule_based_mock",
        created_at=created_at,
        completed_at=completed_at,
    )

    _ensure_storage()
    (EXTRACTION_JOB_DIR / f"{job_id}.json").write_text(
        json.dumps(job.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    for candidate in candidates:
        (KNOWLEDGE_CANDIDATE_DIR / f"{candidate.candidate_id}.json").write_text(
            json.dumps(candidate.model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    existing = [
        item for item in _read_json_list(KNOWLEDGE_CANDIDATE_INDEX_FILE)
        if item.get("source_batch_id") != batch_id
    ]
    existing.extend(candidate.model_dump() for candidate in candidates)
    _write_json_list(KNOWLEDGE_CANDIDATE_INDEX_FILE, existing)

    job_items = _read_json_list(EXTRACTION_JOB_INDEX_FILE)
    job_items.append(job.model_dump())
    _write_json_list(EXTRACTION_JOB_INDEX_FILE, job_items)
    return job


def get_extraction_job(job_id: str) -> ExtractionJobMetadata | None:
    _ensure_storage()
    job_file = EXTRACTION_JOB_DIR / f"{job_id}.json"
    if not job_file.exists():
        return None
    try:
        data = json.loads(job_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    return ExtractionJobMetadata(**data)


def list_knowledge_candidates() -> list[KnowledgeCandidate]:
    return [
        KnowledgeCandidate(**item)
        for item in _read_json_list(KNOWLEDGE_CANDIDATE_INDEX_FILE)
    ]


def get_knowledge_candidate(candidate_id: str) -> KnowledgeCandidate | None:
    _ensure_storage()
    candidate_file = KNOWLEDGE_CANDIDATE_DIR / f"{candidate_id}.json"
    if not candidate_file.exists():
        return None
    try:
        data = json.loads(candidate_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    return KnowledgeCandidate(**data)


def _write_knowledge_candidate(candidate: KnowledgeCandidate) -> KnowledgeCandidate:
    _ensure_storage()
    (KNOWLEDGE_CANDIDATE_DIR / f"{candidate.candidate_id}.json").write_text(
        json.dumps(candidate.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    items = [
        item for item in _read_json_list(KNOWLEDGE_CANDIDATE_INDEX_FILE)
        if item.get("candidate_id") != candidate.candidate_id
    ]
    items.append(candidate.model_dump())
    _write_json_list(KNOWLEDGE_CANDIDATE_INDEX_FILE, items)
    return candidate


def list_pending_review_candidates() -> list[KnowledgeCandidate]:
    allowed = {"pending_review", "needs_revision"}
    return [
        candidate
        for candidate in list_knowledge_candidates()
        if candidate.review_status in allowed
    ]


def update_knowledge_candidate(
    candidate_id: str,
    payload: CandidateUpdateRequest,
) -> KnowledgeCandidate | None:
    candidate = get_knowledge_candidate(candidate_id)
    if candidate is None:
        return None

    updates = payload.model_dump(exclude_unset=True)
    cleaned_tags = updates.get("tags")
    if cleaned_tags is not None:
        updates["tags"] = [
            str(tag).strip()
            for tag in cleaned_tags
            if str(tag).strip()
        ]
    updated = candidate.model_copy(
        update={
            **updates,
            "updated_at": datetime.now(UTC).isoformat(),
        }
    )
    return _write_knowledge_candidate(updated)


def apply_review_decision(
    candidate_id: str,
    status: str,
    payload: ReviewDecisionRequest,
) -> KnowledgeCandidate | None:
    candidate = get_knowledge_candidate(candidate_id)
    if candidate is None:
        return None
    if status not in {"approved", "rejected", "needs_revision"}:
        return None
    allowed_transitions = {
        "pending_review": {"approved", "rejected", "needs_revision"},
        "needs_revision": {"approved", "rejected"},
    }
    if status not in allowed_transitions.get(candidate.review_status, set()):
        return None

    reviewed_at = datetime.now(UTC).isoformat()
    updated = candidate.model_copy(
        update={
            "review_status": status,
            "reviewer": payload.reviewer,
            "review_note": payload.review_note,
            "reviewed_at": reviewed_at,
            "updated_at": reviewed_at,
        }
    )
    written = _write_knowledge_candidate(updated)

    review = ReviewRecord(
        review_id=f"review_{uuid4().hex[:12]}",
        candidate_id=candidate_id,
        review_status=status,  # type: ignore[arg-type]
        reviewer=payload.reviewer,
        review_note=payload.review_note,
        reviewed_at=reviewed_at,
    )
    (REVIEW_RECORD_DIR / f"{review.review_id}.json").write_text(
        json.dumps(review.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    review_items = _read_json_list(REVIEW_RECORD_INDEX_FILE)
    review_items.append(review.model_dump())
    _write_json_list(REVIEW_RECORD_INDEX_FILE, review_items)
    return written


def _chunk_id_for_candidate(candidate_id: str) -> str:
    return f"chunk_{candidate_id}"


def _chunk_text(candidate: KnowledgeCandidate) -> str:
    return "\n".join(
        [
            f"Question: {candidate.question}",
            f"Answer: {candidate.answer}",
            f"Intent: {candidate.intent}",
            f"Tags: {', '.join(candidate.tags)}",
        ]
    )


def build_rag_chunks() -> RagBuildResult:
    _ensure_storage()
    created_at = datetime.now(UTC).isoformat()
    candidates = list_knowledge_candidates()
    existing_chunks = {
        chunk.chunk_id: chunk
        for chunk in list_rag_chunks()
    }
    chunks_by_id: dict[str, RagChunk] = {}
    skipped_reasons: dict[str, int] = {}
    built_count = 0
    updated_count = 0

    for candidate in candidates:
        if candidate.review_status != "approved":
            reason = f"review_status_{candidate.review_status}"
            skipped_reasons[reason] = skipped_reasons.get(reason, 0) + 1
            continue

        chunk_id = _chunk_id_for_candidate(candidate.candidate_id)
        previous = existing_chunks.get(chunk_id)
        next_chunk = RagChunk(
            chunk_id=chunk_id,
            candidate_id=candidate.candidate_id,
            source_type=candidate.source_type,
            source_batch_id=candidate.source_batch_id,
            source_conversation_id=candidate.source_conversation_id,
            source_message_ids=candidate.source_message_ids,
            source_bad_case_id=candidate.source_bad_case_id,
            source_retrieval_id=candidate.source_retrieval_id,
            source_chunk_ids=candidate.source_chunk_ids,
            source_legacy_id=candidate.source_legacy_id,
            source_import_id=candidate.source_import_id,
            migration_mode=candidate.migration_mode,
            source_note=candidate.source_note,
            knowledge_type=candidate.knowledge_type,
            intent=candidate.intent,
            tags=candidate.tags,
            risk_level=candidate.risk_level,
            quality_score=candidate.quality_score,
            review_status="approved",
            chunk_text=_chunk_text(candidate),
            created_at=previous.created_at if previous else created_at,
            build_method="local_json_mock_retrieval",
        )

        if previous is None:
            built_count += 1
        elif _rag_chunk_changed(previous, next_chunk):
            updated_count += 1
            next_chunk = next_chunk.model_copy(update={"created_at": created_at})
        else:
            skipped_reasons["unchanged"] = skipped_reasons.get("unchanged", 0) + 1
        chunks_by_id[chunk_id] = next_chunk

    for chunk_file in RAG_CHUNK_DIR.glob("chunk_*.json"):
        if chunk_file.stem not in chunks_by_id:
            chunk_file.unlink()

    chunks = sorted(chunks_by_id.values(), key=lambda item: item.chunk_id)
    for chunk in chunks:
        (RAG_CHUNK_DIR / f"{chunk.chunk_id}.json").write_text(
            json.dumps(chunk.model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    _write_json_list(
        RAG_CHUNK_INDEX_FILE,
        [chunk.model_dump() for chunk in chunks],
    )

    return RagBuildResult(
        built_count=built_count,
        updated_count=updated_count,
        skipped_count=sum(skipped_reasons.values()),
        skipped_reasons=skipped_reasons,
        chunk_count=len(chunks),
        status="completed",
        build_method="local_json_mock_retrieval",
        created_at=created_at,
    )


def _rag_chunk_changed(previous: RagChunk, current: RagChunk) -> bool:
    comparable_previous = previous.model_dump(exclude={"created_at"})
    comparable_current = current.model_dump(exclude={"created_at"})
    return comparable_previous != comparable_current


def list_rag_chunks() -> list[RagChunk]:
    return [RagChunk(**item) for item in _read_json_list(RAG_CHUNK_INDEX_FILE)]


def get_rag_chunk(chunk_id: str) -> RagChunk | None:
    _ensure_storage()
    chunk_file = RAG_CHUNK_DIR / f"{chunk_id}.json"
    if not chunk_file.exists():
        return None
    try:
        data = json.loads(chunk_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    return RagChunk(**data)


def _tokenize(value: str) -> set[str]:
    return {
        token.lower()
        for token in re.findall(r"[A-Za-z0-9_]+", value)
        if len(token) >= 2
    }


def search_rag_chunks(query: str, top_k: int) -> list[RagSearchResult]:
    query_tokens = _tokenize(query)
    if not query_tokens:
        return []

    results: list[RagSearchResult] = []
    for chunk in list_rag_chunks():
        chunk_tokens = _tokenize(
            " ".join(
                [
                    chunk.chunk_text,
                    chunk.intent,
                    " ".join(chunk.tags),
                    chunk.knowledge_type,
                ]
            )
        )
        overlap = query_tokens & chunk_tokens
        if not overlap:
            continue

        tag_tokens = {tag.lower() for tag in chunk.tags}
        tag_overlap = query_tokens & tag_tokens
        intent_overlap = {chunk.intent} if chunk.intent in query_tokens else set()
        tag_boost = 0.15 if tag_overlap else 0
        intent_boost = 0.15 if intent_overlap else 0
        score = min(
            1.0,
            (len(overlap) / len(query_tokens)) + tag_boost + intent_boost,
        )
        matched_terms = sorted(overlap | tag_overlap | intent_overlap)
        results.append(
            RagSearchResult(
                score=round(score, 4),
                matched_terms=matched_terms,
                chunk_id=chunk.chunk_id,
                candidate_id=chunk.candidate_id,
                source_type=chunk.source_type,
                source_batch_id=chunk.source_batch_id,
                source_conversation_id=chunk.source_conversation_id,
                source_message_ids=chunk.source_message_ids,
                source_bad_case_id=chunk.source_bad_case_id,
                source_retrieval_id=chunk.source_retrieval_id,
                source_chunk_ids=chunk.source_chunk_ids,
                source_legacy_id=chunk.source_legacy_id,
                source_import_id=chunk.source_import_id,
                migration_mode=chunk.migration_mode,
                source_note=chunk.source_note,
                knowledge_type=chunk.knowledge_type,
                intent=chunk.intent,
                tags=chunk.tags,
                risk_level=chunk.risk_level,
                quality_score=chunk.quality_score,
                review_status=chunk.review_status,
                chunk_text=chunk.chunk_text,
                build_method=chunk.build_method,
            )
        )

    return sorted(results, key=lambda item: item.score, reverse=True)[:top_k]


def _answer_from_chunk_text(chunk_text: str) -> str:
    for line in chunk_text.splitlines():
        if line.startswith("Answer: "):
            return line.removeprefix("Answer: ").strip()
    return ""


def _matches_customerops_filters(
    chunk: RagChunk,
    filters: CustomerOpsRetrievalFilters | None,
) -> bool:
    if filters is None:
        return True
    if filters.intent and chunk.intent != filters.intent:
        return False
    if filters.risk_level and chunk.risk_level != filters.risk_level:
        return False
    if filters.tags:
        requested_tags = {tag.strip().lower() for tag in filters.tags if tag.strip()}
        chunk_tags = {tag.lower() for tag in chunk.tags}
        if requested_tags and not requested_tags.issubset(chunk_tags):
            return False
    return True


def _customerops_score_chunk(query: str, chunk: RagChunk) -> CustomerOpsRetrievalResult | None:
    if chunk.review_status != "approved":
        return None
    query_tokens = _tokenize(query)
    if not query_tokens:
        return None
    chunk_tokens = _tokenize(
        " ".join(
            [
                chunk.chunk_text,
                chunk.intent,
                " ".join(chunk.tags),
                chunk.knowledge_type,
            ]
        )
    )
    overlap = query_tokens & chunk_tokens
    if not overlap:
        return None

    tag_tokens = {tag.lower() for tag in chunk.tags}
    tag_overlap = query_tokens & tag_tokens
    intent_overlap = {chunk.intent} if chunk.intent in query_tokens else set()
    tag_boost = 0.15 if tag_overlap else 0
    intent_boost = 0.15 if intent_overlap else 0
    score = min(
        1.0,
        (len(overlap) / len(query_tokens)) + tag_boost + intent_boost,
    )
    matched_terms = sorted(overlap | tag_overlap | intent_overlap)
    return CustomerOpsRetrievalResult(
        score=round(score, 4),
        matched_terms=matched_terms,
        chunk_id=chunk.chunk_id,
        candidate_id=chunk.candidate_id,
        source_type=chunk.source_type,
        source_batch_id=chunk.source_batch_id,
        source_conversation_id=chunk.source_conversation_id,
        source_message_ids=chunk.source_message_ids,
        source_bad_case_id=chunk.source_bad_case_id,
        source_retrieval_id=chunk.source_retrieval_id,
        source_chunk_ids=chunk.source_chunk_ids,
        source_legacy_id=chunk.source_legacy_id,
        source_import_id=chunk.source_import_id,
        migration_mode=chunk.migration_mode,
        source_note=chunk.source_note,
        knowledge_type=chunk.knowledge_type,
        intent=chunk.intent,
        tags=chunk.tags,
        risk_level=chunk.risk_level,
        quality_score=chunk.quality_score,
        review_status=chunk.review_status,
        chunk_text=chunk.chunk_text,
        build_method=chunk.build_method,
        answer=_answer_from_chunk_text(chunk.chunk_text),
    )


def run_customerops_retrieval(
    payload: CustomerOpsRetrievalRequest,
    query: str,
    top_k: int,
) -> CustomerOpsRetrievalResponse:
    created_at = datetime.now(UTC).isoformat()
    retrieval_id = f"retrieval_{uuid4().hex[:12]}"
    results: list[CustomerOpsRetrievalResult] = []

    for chunk in list_rag_chunks():
        if not _matches_customerops_filters(chunk, payload.filters):
            continue
        result = _customerops_score_chunk(query, chunk)
        if result is not None:
            results.append(result)

    results = sorted(results, key=lambda item: item.score, reverse=True)[:top_k]
    trace = CustomerOpsRetrievalTrace(
        retrieval_id=retrieval_id,
        query=query,
        top_k=top_k,
        filters=payload.filters.model_dump(exclude_none=True) if payload.filters else {},
        result_count=len(results),
        result_chunk_ids=[result.chunk_id for result in results],
        conversation_id=payload.conversation_id,
        agent_session_id=payload.agent_session_id,
        created_at=created_at,
        retrieval_mode="customerops_local_mock_retrieval",
    )
    _write_retrieval_trace(trace)
    return CustomerOpsRetrievalResponse(
        retrieval_id=retrieval_id,
        query=query,
        top_k=top_k,
        retrieval_mode="customerops_local_mock_retrieval",
        results=results,
        created_at=created_at,
    )


def _write_retrieval_trace(trace: CustomerOpsRetrievalTrace) -> None:
    _ensure_storage()
    (RETRIEVAL_LOG_DIR / f"{trace.retrieval_id}.json").write_text(
        json.dumps(trace.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    items = [
        item for item in _read_json_list(RETRIEVAL_LOG_INDEX_FILE)
        if item.get("retrieval_id") != trace.retrieval_id
    ]
    items.append(trace.model_dump())
    _write_json_list(RETRIEVAL_LOG_INDEX_FILE, items)


def get_customerops_retrieval_trace(
    retrieval_id: str,
) -> CustomerOpsRetrievalTrace | None:
    _ensure_storage()
    trace_file = RETRIEVAL_LOG_DIR / f"{retrieval_id}.json"
    if not trace_file.exists():
        return None
    try:
        data = json.loads(trace_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    return CustomerOpsRetrievalTrace(**data)


def create_bad_case(
    payload: BadCaseSubmitRequest,
    retrieval_trace: CustomerOpsRetrievalTrace,
    user_query: str,
    agent_answer: str,
    expected_answer: str | None,
) -> BadCaseRecord:
    _ensure_storage()
    now = datetime.now(UTC).isoformat()
    bad_case = BadCaseRecord(
        bad_case_id=f"badcase_{uuid4().hex[:12]}",
        retrieval_id=payload.retrieval_id,
        user_query=user_query,
        agent_answer=agent_answer,
        issue_type=payload.issue_type,
        expected_answer=expected_answer,
        severity=payload.severity,
        status="open",
        review_note="",
        resolution_type=None,
        linked_candidate_id=None,
        linked_chunk_ids=retrieval_trace.result_chunk_ids,
        retrieval_result_count=retrieval_trace.result_count,
        conversation_id=payload.conversation_id or retrieval_trace.conversation_id,
        agent_session_id=payload.agent_session_id or retrieval_trace.agent_session_id,
        metadata=payload.metadata or {},
        created_at=now,
        updated_at=now,
    )
    return _write_bad_case(bad_case)


def _write_bad_case(bad_case: BadCaseRecord) -> BadCaseRecord:
    _ensure_storage()
    (BAD_CASE_DIR / f"{bad_case.bad_case_id}.json").write_text(
        json.dumps(bad_case.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    items = [
        item for item in _read_json_list(BAD_CASE_INDEX_FILE)
        if item.get("bad_case_id") != bad_case.bad_case_id
    ]
    items.append(bad_case.model_dump())
    _write_json_list(BAD_CASE_INDEX_FILE, items)
    return bad_case


def list_bad_cases(
    status: str | None = None,
    issue_type: str | None = None,
    severity: str | None = None,
) -> list[BadCaseRecord]:
    records = [BadCaseRecord(**item) for item in _read_json_list(BAD_CASE_INDEX_FILE)]
    if status:
        records = [record for record in records if record.status == status]
    if issue_type:
        records = [record for record in records if record.issue_type == issue_type]
    if severity:
        records = [record for record in records if record.severity == severity]
    return sorted(records, key=lambda item: item.created_at, reverse=True)


def get_bad_case(bad_case_id: str) -> BadCaseRecord | None:
    _ensure_storage()
    bad_case_file = BAD_CASE_DIR / f"{bad_case_id}.json"
    if not bad_case_file.exists():
        return None
    try:
        data = json.loads(bad_case_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    return BadCaseRecord(**data)


def update_bad_case(
    bad_case_id: str,
    payload: BadCaseUpdateRequest,
) -> BadCaseRecord | None:
    bad_case = get_bad_case(bad_case_id)
    if bad_case is None:
        return None

    updates = payload.model_dump(exclude_unset=True)
    updated = bad_case.model_copy(
        update={
            **updates,
            "updated_at": datetime.now(UTC).isoformat(),
        }
    )
    return _write_bad_case(updated)


def create_candidate_from_bad_case(
    bad_case: BadCaseRecord,
    payload: BadCaseDraftRequest,
    question: str,
    answer: str,
    tags: list[str],
) -> KnowledgeCandidate:
    _ensure_storage()
    now = datetime.now(UTC).isoformat()
    candidate = KnowledgeCandidate(
        candidate_id=f"kc_badcase_{uuid4().hex[:12]}",
        source_type="bad_case",
        source_batch_id=None,
        source_conversation_id=bad_case.conversation_id or "bad_case",
        source_message_ids=[],
        source_bad_case_id=bad_case.bad_case_id,
        source_retrieval_id=bad_case.retrieval_id,
        source_chunk_ids=bad_case.linked_chunk_ids,
        linked_candidate_id=bad_case.linked_candidate_id,
        knowledge_type=payload.knowledge_type,  # type: ignore[arg-type]
        question=question,
        answer=answer,
        intent=payload.intent,  # type: ignore[arg-type]
        tags=tags,
        risk_level=payload.risk_level,  # type: ignore[arg-type]
        review_status="pending_review",
        quality_score=payload.quality_score,
        extraction_method="bad_case_resolution",
        created_at=now,
        reviewer=payload.reviewer,
        review_note=payload.review_note,
        updated_at=now,
    )
    _write_knowledge_candidate(candidate)

    resolution_type = bad_case.resolution_type
    if resolution_type not in {"create_new_knowledge", "update_existing_knowledge"}:
        resolution_type = "create_new_knowledge"
    note_suffix = f"Created pending_review draft {candidate.candidate_id} from Bad Case."
    existing_note = bad_case.review_note.strip()
    review_note = (
        f"{existing_note}\n{note_suffix}" if existing_note else note_suffix
    )
    _write_bad_case(
        bad_case.model_copy(
            update={
                "status": "resolved",
                "resolution_type": resolution_type,
                "linked_candidate_id": candidate.candidate_id,
                "review_note": review_note,
                "updated_at": now,
            }
        )
    )
    return candidate


def _legacy_candidate_id(source_name: str, legacy_id: str) -> str:
    digest = sha1(
        f"{source_name.strip().lower()}::{legacy_id.strip().lower()}".encode("utf-8")
    ).hexdigest()[:16]
    return f"kc_legacy_{digest}"


def _clean_legacy_tags(tags: list[str]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for tag in [*tags, "legacy_rag"]:
        value = str(tag).strip()
        if not value:
            continue
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(value)
    return cleaned


def _legacy_candidate_changed(
    previous: KnowledgeCandidate,
    current: KnowledgeCandidate,
) -> bool:
    comparable_previous = previous.model_dump(
        exclude={
            "created_at",
            "updated_at",
            "reviewed_at",
            "reviewer",
            "review_note",
        }
    )
    comparable_current = current.model_dump(
        exclude={
            "created_at",
            "updated_at",
            "reviewed_at",
            "reviewer",
            "review_note",
        }
    )
    return comparable_previous != comparable_current


def import_legacy_rag(payload: LegacyRagImportRequest) -> LegacyRagImportMetadata:
    _ensure_storage()
    now = datetime.now(UTC).isoformat()
    import_id = f"legacy_import_{uuid4().hex[:12]}"
    migration_mode = "trusted_import" if payload.trusted_import else "review_required"
    review_status = "approved" if payload.trusted_import else "pending_review"
    created_candidate_count = 0
    updated_count = 0
    skipped_reasons: dict[str, int] = {}
    candidate_ids: list[str] = []

    for item in payload.items:
        candidate_id = _legacy_candidate_id(payload.source_name, item.legacy_id)
        previous = get_knowledge_candidate(candidate_id)
        candidate = KnowledgeCandidate(
            candidate_id=candidate_id,
            source_type="legacy_rag",
            source_batch_id=None,
            source_conversation_id=None,
            source_message_ids=[],
            source_legacy_id=item.legacy_id,
            source_import_id=previous.source_import_id if previous else import_id,
            knowledge_type=item.knowledge_type,
            question=item.question.strip(),
            answer=item.answer.strip(),
            intent=item.intent,
            tags=_clean_legacy_tags(item.tags),
            risk_level=item.risk_level,
            review_status=review_status,  # type: ignore[arg-type]
            quality_score=item.quality_score,
            extraction_method="legacy_rag_migration",
            migration_mode=migration_mode,  # type: ignore[arg-type]
            source_note=item.source_note,
            created_at=previous.created_at if previous else now,
            updated_at=now,
        )
        candidate_ids.append(candidate_id)

        if previous is None:
            _write_knowledge_candidate(candidate)
            created_candidate_count += 1
        elif _legacy_candidate_changed(previous, candidate):
            _write_knowledge_candidate(candidate)
            updated_count += 1
        else:
            skipped_reasons["unchanged"] = skipped_reasons.get("unchanged", 0) + 1

    candidates = [
        candidate
        for candidate in (get_knowledge_candidate(candidate_id) for candidate_id in candidate_ids)
        if candidate is not None
    ]
    metadata = LegacyRagImportMetadata(
        import_id=import_id,
        source_name=payload.source_name,
        source_type="legacy_rag",
        trusted_import=payload.trusted_import,
        migration_mode=migration_mode,  # type: ignore[arg-type]
        item_count=len(payload.items),
        created_candidate_count=created_candidate_count,
        updated_count=updated_count,
        approved_count=sum(1 for candidate in candidates if candidate.review_status == "approved"),
        pending_review_count=sum(
            1 for candidate in candidates if candidate.review_status == "pending_review"
        ),
        skipped_count=sum(skipped_reasons.values()),
        skipped_reasons=skipped_reasons,
        created_at=now,
        candidate_ids=candidate_ids,
    )

    (LEGACY_RAG_IMPORT_DIR / f"{import_id}.json").write_text(
        json.dumps(metadata.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    items = _read_json_list(LEGACY_RAG_IMPORT_INDEX_FILE)
    items.append(metadata.model_dump())
    _write_json_list(LEGACY_RAG_IMPORT_INDEX_FILE, items)
    return metadata


def list_legacy_rag_imports() -> list[LegacyRagImportMetadata]:
    return [
        LegacyRagImportMetadata(**item)
        for item in _read_json_list(LEGACY_RAG_IMPORT_INDEX_FILE)
    ]


def get_legacy_rag_import(import_id: str) -> LegacyRagImportMetadata | None:
    _ensure_storage()
    import_file = LEGACY_RAG_IMPORT_DIR / f"{import_id}.json"
    if not import_file.exists():
        return None
    try:
        data = json.loads(import_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    return LegacyRagImportMetadata(**data)

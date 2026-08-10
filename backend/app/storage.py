import re
from difflib import SequenceMatcher
from hashlib import sha1
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from app.answerability import AnswerabilityEvidence, evaluate_answerability
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
    ManualCleanRequest,
    ManualCleaningRecord,
    RagBuildResult,
    RagChunk,
    RagSearchResult,
    ReviewDecisionRequest,
    ReviewRecord,
    SanitizedBatch,
    SanitizedMessage,
    SourceBatchMetadata,
)
import app.database as database
import app.db_repositories as db_repo
from app.p1_persistence import P1PersistenceError
from app.embedding import get_embedding_provider
import logging

_logger = logging.getLogger(__name__)


def SessionLocal():
    """Open a database session while normalizing connection failures."""
    try:
        return database.SessionLocal()
    except Exception as exc:
        raise _persistence_failure("open session", exc) from None


def _persistence_failure(operation: str, exc: Exception) -> P1PersistenceError:
    _logger.exception("P1 database operation failed: %s", operation)
    return P1PersistenceError(P1PersistenceError.code)


def _safe_error_message(exc: Exception) -> str:
    """Return a safe error summary — never leaks DATABASE_URL or API keys."""
    msg = str(exc)[:300]
    # Scrub any URL-looking patterns
    import re as _re
    msg = _re.sub(r"postgres(?:ql)?://[^\s]+", "[REDACTED_DB_URL]", msg)
    msg = _re.sub(r"sqlite:///[^\s]+", "[REDACTED_SQLITE_PATH]", msg)
    return msg


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
NAME_PATTERN = re.compile(
    r"\b(my name is|i am|i'm|this is)\s+[A-Z][A-Za-z'-]*(?:\s+[A-Z][A-Za-z'-]*){0,2}\b",
    re.IGNORECASE,
)
ZIP_PATTERN = re.compile(
    r"\b(?:zip|zipcode|zip code|postal|postal code)[:#\s-]*(\d{5}(?:-\d{4})?)\b",
    re.IGNORECASE,
)
PAYMENT_PATTERN = re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")
AD_KEYWORDS = [
    "free money",
    "click here",
    "promo spam",
    "subscribe now",
    "limited offer",
    "buy now",
]
NOISE_KEYWORDS = ["haha", "lol", "random text", "asdf", "test test"]
QUESTION_TERMS = [
    "?",
    "how",
    "what",
    "where",
    "when",
    "why",
    "can",
    "could",
    "do",
    "does",
    "is",
    "are",
    "will",
    "would",
    "please",
    "help",
    "order",
    "refund",
    "shipping",
    "tracking",
]


def create_raw_batch(payload: ImportJsonRequest) -> SourceBatchMetadata:
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

    db = SessionLocal()
    try:
        with db.begin():
            db_repo.save_raw_batch_to_db(
                db,
                batch_id=batch_id,
                source_name=payload.source_name,
                message_count=message_count,
                raw_payload={
                    "metadata": metadata.model_dump(),
                    "raw_payload": payload.model_dump(),
                },
                conversations=[
                    conv.model_dump() for conv in payload.conversations
                ],
                commit=False,
            )
    except Exception as exc:
        db.rollback()
        raise _persistence_failure("import", exc) from None
    finally:
        db.close()

    return metadata


def list_raw_batches() -> list[SourceBatchMetadata]:
    db = SessionLocal()
    try:
        return db_repo.list_raw_batches_from_db(db)
    except Exception as exc:
        raise _persistence_failure("list raw batches", exc) from None
    finally:
        db.close()


def get_raw_batch_metadata(batch_id: str) -> SourceBatchMetadata | None:
    db = SessionLocal()
    try:
        return db_repo.get_raw_batch_from_db(db, batch_id)
    except Exception as exc:
        raise _persistence_failure("get raw batch", exc) from None
    finally:
        db.close()


def get_raw_batch_document(batch_id: str) -> dict[str, object] | None:
    db = SessionLocal()
    try:
        return db_repo.get_raw_batch_document_from_db(db, batch_id)
    except Exception as exc:
        raise _persistence_failure("get raw batch document", exc) from None
    finally:
        db.close()


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


def _mask_pii(content: str) -> tuple[str, list[str], list[str]]:
    masked = content
    pii_types: list[str] = []
    risk_flags: list[str] = []

    replacements = [
        ("PAYMENT_SENSITIVE", PAYMENT_PATTERN, "[PAYMENT_SENSITIVE]"),
        ("NAME", NAME_PATTERN, "[NAME]"),
        ("EMAIL", EMAIL_PATTERN, "[EMAIL]"),
        ("TRACKING_ID", TRACKING_PATTERN, "[TRACKING_ID]"),
        ("ORDER_ID", ORDER_PATTERN, "[ORDER_ID]"),
        ("ZIP_CODE", ZIP_PATTERN, "[ZIP_CODE]"),
        ("ADDRESS", ADDRESS_PATTERN, "[ADDRESS]"),
        ("PHONE", PHONE_PATTERN, "[PHONE]"),
    ]

    for pii_type, pattern, replacement in replacements:
        masked, count = pattern.subn(replacement, masked)
        if count > 0:
            pii_types.append(pii_type)

    if any(pii_type in pii_types for pii_type in ["EMAIL", "PHONE", "ADDRESS", "NAME", "ZIP_CODE"]):
        risk_flags.append("contains_personal_data")
    if any(pii_type in pii_types for pii_type in ["ORDER_ID", "TRACKING_ID"]):
        risk_flags.append("contains_business_identifier")
    if "PAYMENT_SENSITIVE" in pii_types:
        risk_flags.append("contains_payment_sensitive")

    return masked, pii_types, risk_flags


def _normalize_for_duplicate(content: str) -> str:
    return re.sub(r"\s+", " ", content.strip().lower())


def _effective_char_count(content: str) -> int:
    return len(re.findall(r"[A-Za-z0-9\u4e00-\u9fff]", content))


def _symbol_ratio(content: str) -> float:
    chars = [char for char in content if not char.isspace()]
    if not chars:
        return 1.0
    semantic = sum(1 for char in chars if re.match(r"[A-Za-z0-9\u4e00-\u9fff]", char))
    return 1 - (semantic / len(chars))


def _detect_quality_issues(content: str, role: str) -> list[str]:
    issues: list[str] = []
    effective_chars = _effective_char_count(content)
    ratio = _symbol_ratio(content)
    lowered = content.lower()

    if effective_chars < 3:
        issues.extend(["low_quality", "too_short"])
    if len(content) > 1000:
        issues.extend(["low_quality", "too_long"])
    if re.search(r"(\S)\1{5,}", content):
        issues.extend(["low_quality", "repeated_chars"])
    if ratio >= 0.85 and len(content.strip()) >= 3:
        issues.extend(["low_quality", "symbol_noise"])
    if ratio >= 0.65 and len(content.strip()) >= 10:
        issues.extend(["low_quality", "possible_garbled_text"])
    if any(keyword in lowered for keyword in AD_KEYWORDS):
        issues.extend(["possible_ad", "possible_noise"])
    if any(keyword in lowered for keyword in NOISE_KEYWORDS):
        issues.extend(["possible_noise", "off_topic"])
    if role == "customer" and not any(term in lowered for term in QUESTION_TERMS):
        issues.append("weak_question")
    if role == "agent":
        weak_answers = {"ok", "okay", "yes", "no", "sure", "thanks", "thank you"}
        if effective_chars < 8 or lowered.strip(" .!?") in weak_answers:
            issues.append("weak_answer")

    return list(dict.fromkeys(issues))


def _assess_quality(
    issues: list[str],
    pii_types: list[str],
) -> tuple[float, str, str]:
    score = 1.0
    deductions = {
        "exact_duplicate": 0.2,
        "near_duplicate": 0.15,
        "too_short": 0.35,
        "too_long": 0.25,
        "repeated_chars": 0.25,
        "symbol_noise": 0.4,
        "possible_garbled_text": 0.4,
        "possible_ad": 0.3,
        "possible_noise": 0.2,
        "off_topic": 0.15,
        "weak_question": 0.15,
        "weak_answer": 0.2,
    }
    for issue in issues:
        score -= deductions.get(issue, 0.0)
    if pii_types:
        score -= min(0.1, 0.02 * len(pii_types))
    score = round(max(score, 0.0), 2)

    if score >= 0.8:
        return score, "high", "keep"
    if score >= 0.5:
        return score, "medium", "review"
    return score, "low", "drop"


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
    seen_normalized: set[str] = set()
    prior_normalized: list[str] = []

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
            masked_content, pii_types, risk_flags = _mask_pii(content)
            if pii_types:
                notes.append("pii_masked")
            normalized_content = _normalize_for_duplicate(masked_content)
            cleaning_issues = _detect_quality_issues(masked_content, role)
            if normalized_content in seen_normalized:
                cleaning_issues.append("exact_duplicate")
            elif any(
                SequenceMatcher(None, normalized_content, prior).ratio() >= 0.92
                for prior in prior_normalized
            ):
                cleaning_issues.append("near_duplicate")
            seen_normalized.add(normalized_content)
            prior_normalized.append(normalized_content)
            cleaning_issues = list(dict.fromkeys(cleaning_issues))
            quality_score, quality_level, suggested_action = _assess_quality(
                cleaning_issues,
                pii_types,
            )

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
                    cleaning_issues=cleaning_issues,
                    risk_flags=risk_flags,
                    quality_score=quality_score,
                    quality_level=quality_level,  # type: ignore[arg-type]
                    suggested_action=suggested_action,  # type: ignore[arg-type]
                )
            )

    completed_at = datetime.now(UTC).isoformat()
    pii_detected_count = sum(1 for message in sanitized_messages if message.pii_detected)
    exact_duplicate_count = sum(
        1 for message in sanitized_messages if "exact_duplicate" in message.cleaning_issues
    )
    near_duplicate_count = sum(
        1 for message in sanitized_messages if "near_duplicate" in message.cleaning_issues
    )
    low_quality_count = sum(
        1
        for message in sanitized_messages
        if message.quality_level == "low" or "low_quality" in message.cleaning_issues
    )
    noise_count = sum(
        1
        for message in sanitized_messages
        if any(
            issue in message.cleaning_issues
            for issue in ["possible_ad", "possible_noise", "off_topic"]
        )
    )
    review_recommended_count = sum(
        1 for message in sanitized_messages if message.suggested_action == "review"
    )
    drop_recommended_count = sum(
        1 for message in sanitized_messages if message.suggested_action == "drop"
    )
    average_quality_score = round(
        sum(message.quality_score for message in sanitized_messages) / len(sanitized_messages),
        4,
    ) if sanitized_messages else 0.0
    sanitized_batch = SanitizedBatch(
        batch_id=batch_id,
        source_batch_id=batch_id,
        status="sanitized",
        raw_message_count=raw_message_count,
        sanitized_message_count=len(sanitized_messages),
        dropped_message_count=dropped_message_count,
        pii_detected_count=pii_detected_count,
        exact_duplicate_count=exact_duplicate_count,
        near_duplicate_count=near_duplicate_count,
        low_quality_count=low_quality_count,
        noise_count=noise_count,
        review_recommended_count=review_recommended_count,
        drop_recommended_count=drop_recommended_count,
        average_quality_score=average_quality_score,
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
        exact_duplicate_count=exact_duplicate_count,
        near_duplicate_count=near_duplicate_count,
        low_quality_count=low_quality_count,
        noise_count=noise_count,
        review_recommended_count=review_recommended_count,
        drop_recommended_count=drop_recommended_count,
        average_quality_score=average_quality_score,
        status="completed",
        created_at=created_at,
        completed_at=completed_at,
    )

    db = SessionLocal()
    try:
        with db.begin():
            db_repo.save_sanitized_batch_to_db(
                db, sanitized_batch, job, commit=False
            )
    except Exception as exc:
        db.rollback()
        raise _persistence_failure("cleaning", exc) from None
    finally:
        db.close()

    return job


def get_cleaning_job(job_id: str) -> CleaningJobMetadata | None:
    db = SessionLocal()
    try:
        data = db_repo.get_cleaning_job_from_db(db, job_id)
        return CleaningJobMetadata(**data) if data is not None else None
    except Exception as exc:
        raise _persistence_failure("get cleaning job", exc) from None
    finally:
        db.close()


def get_sanitized_batch(batch_id: str) -> SanitizedBatch | None:
    db = SessionLocal()
    try:
        result = db_repo.get_sanitized_batch_from_db(db, batch_id)
        if result is None:
            return None
        records = db_repo.get_manual_cleaning_records_for_batch_from_db(db, batch_id)
        by_message: dict[str, dict[str, Any]] = {}
        for record in records:
            key = str(record.get("sanitized_message_id") or "")
            if key and key not in by_message:
                by_message[key] = record
        for index, message in enumerate(result.messages):
            record = by_message.get(message.message_id) or by_message.get(
                message.source_message_id
            )
            if record and record.get("original_content") == message.content:
                result.messages[index] = message.model_copy(update={
                    "manual_cleaning_status": "cleaned",
                    "manual_cleaned_content": record.get("cleaned_content"),
                    "manual_action": record.get("action"),
                    "cleaner": record.get("cleaner"),
                    "cleaning_note": record.get("note", ""),
                    "manual_cleaned_at": record.get("created_at"),
                })
        return result
    except Exception as exc:
        raise _persistence_failure("get sanitized batch", exc) from None
    finally:
        db.close()


def manual_clean_sanitized_message(
    batch_id: str,
    message_id: str,
    payload: ManualCleanRequest,
) -> ManualCleaningRecord | None:
    sanitized = get_sanitized_batch(batch_id)
    if sanitized is None:
        return None

    target_index: int | None = None
    for index, message in enumerate(sanitized.messages):
        if message.message_id == message_id or message.source_message_id == message_id:
            target_index = index
            break
    if target_index is None:
        return None

    message = sanitized.messages[target_index]
    now = datetime.now(UTC).isoformat()
    original_content = message.content
    cleaned_content = payload.content.strip()
    updated_message = message.model_copy(
        update={
            "manual_cleaning_status": "cleaned",
            "manual_cleaned_content": cleaned_content,
            "manual_action": payload.manual_action,
            "cleaner": payload.cleaner.strip(),
            "cleaning_note": payload.cleaning_note.strip(),
            "manual_cleaned_at": now,
        }
    )
    sanitized.messages[target_index] = updated_message

    record = ManualCleaningRecord(
        record_id=f"manual_clean_{uuid4().hex[:12]}",
        batch_id=batch_id,
        message_id=updated_message.message_id,
        source_message_id=updated_message.source_message_id,
        conversation_id=updated_message.conversation_id,
        original_sanitized_content=original_content,
        manual_cleaned_content=cleaned_content,
        manual_action=payload.manual_action,
        cleaner=payload.cleaner.strip(),
        cleaning_note=payload.cleaning_note.strip(),
        created_at=now,
    )

    db = SessionLocal()
    try:
        with db.begin():
            db_repo.save_manual_cleaning_record_to_db(db, record, commit=False)
    except Exception as exc:
        db.rollback()
        raise _persistence_failure("manual cleaning", exc) from None
    finally:
        db.close()

    return record


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


def _source_type_for_batch(batch_id: str) -> str:
    metadata = get_raw_batch_metadata(batch_id)
    if metadata is None:
        return "sanitized_batch"
    source_name = metadata.source_name.strip().lower()
    if source_name.startswith("public_dataset") or "public_dataset_eval" in source_name:
        return "public_dataset"
    if source_name.startswith("manual"):
        return "manual"
    return "chat_logs"


def _message_allowed_for_extraction(message: SanitizedMessage) -> bool:
    if message.manual_action in {"drop", "needs_review"}:
        return False
    if message.manual_action in {"keep", "keep_edited"}:
        return True
    if message.suggested_action == "drop":
        return False
    if message.quality_level == "low":
        return False
    return True


def _message_extraction_content(message: SanitizedMessage) -> str:
    if message.manual_action == "keep_edited" and message.manual_cleaned_content:
        return message.manual_cleaned_content.strip()
    return message.content.strip()


def run_extraction(batch_id: str) -> ExtractionJobMetadata | None:
    sanitized = get_sanitized_batch(batch_id)
    if sanitized is None:
        return None

    created_at = datetime.now(UTC).isoformat()
    job_id = f"extract_job_{uuid4().hex[:12]}"
    source_type = _source_type_for_batch(batch_id)
    candidates: list[KnowledgeCandidate] = []
    messages_by_conversation: dict[str, list[SanitizedMessage]] = {}

    for message in sanitized.messages:
        if not _message_allowed_for_extraction(message):
            continue
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
            question = _message_extraction_content(message)
            answer = _message_extraction_content(answer_message)
            if not question or not answer:
                continue
            intent, tags = _infer_intent(question, answer)
            candidate_id = f"kc_{uuid4().hex[:12]}"
            message_quality = round(
                (message.quality_score + answer_message.quality_score) / 2,
                2,
            )
            candidate_quality_score = round(
                min(_quality_score(question, answer), message_quality),
                2,
            )
            candidate_cleaning_issues = sorted(
                set(message.cleaning_issues + answer_message.cleaning_issues)
            )
            candidate_risk_flags = sorted(set(message.risk_flags + answer_message.risk_flags))
            candidates.append(
                KnowledgeCandidate(
                    candidate_id=candidate_id,
                    source_type=source_type,  # type: ignore[arg-type]
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
                    quality_score=candidate_quality_score,
                    extraction_method="rule_based_mock",
                    cleaning_issues=candidate_cleaning_issues,
                    risk_flags=candidate_risk_flags,
                    manual_cleaning_status=(
                        "cleaned"
                        if message.manual_cleaning_status == "cleaned"
                        or answer_message.manual_cleaning_status == "cleaned"
                        else None
                    ),
                    manual_action=", ".join(
                        action
                        for action in [message.manual_action, answer_message.manual_action]
                        if action
                    ) or None,
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

    db = SessionLocal()
    try:
        with db.begin():
            db_repo.save_knowledge_candidates_to_db(db, candidates, commit=False)
            db_repo.save_extraction_job_to_db(db, batch_id, job, commit=False)
    except Exception as exc:
        db.rollback()
        raise _persistence_failure("extraction", exc) from None
    finally:
        db.close()

    return job


def get_extraction_job(job_id: str) -> ExtractionJobMetadata | None:
    db = SessionLocal()
    try:
        data = db_repo.get_extraction_job_from_db(db, job_id)
        return ExtractionJobMetadata(**data) if data is not None else None
    except Exception as exc:
        raise _persistence_failure("get extraction job", exc) from None
    finally:
        db.close()


def list_knowledge_candidates() -> list[KnowledgeCandidate]:
    db = SessionLocal()
    try:
        return db_repo.list_knowledge_candidates_from_db(db)
    except Exception as exc:
        raise _persistence_failure("list candidates", exc) from None
    finally:
        db.close()


def get_knowledge_candidate(candidate_id: str) -> KnowledgeCandidate | None:
    db = SessionLocal()
    try:
        return db_repo.get_knowledge_candidate_from_db(db, candidate_id)
    except Exception as exc:
        raise _persistence_failure("get candidate", exc) from None
    finally:
        db.close()


def _write_knowledge_candidate(candidate: KnowledgeCandidate) -> KnowledgeCandidate:
    db = SessionLocal()
    try:
        db_repo.save_knowledge_candidates_to_db(db, [candidate])
        return candidate
    except Exception as exc:
        db.rollback()
        raise _persistence_failure("write candidate", exc) from None
    finally:
        db.close()


def list_pending_review_candidates() -> list[KnowledgeCandidate]:
    db = SessionLocal()
    try:
        return db_repo.list_pending_review_candidates_from_db(db)
    except Exception as exc:
        raise _persistence_failure("list review queue", exc) from None
    finally:
        db.close()


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
    db_updates = dict(updates)
    try:
        db = SessionLocal()
        try:
            result = db_repo.update_knowledge_candidate_in_db(db, candidate_id, db_updates)
            return result
        finally:
            db.close()
    except Exception as exc:
        raise _persistence_failure("update candidate", exc) from None


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
    review = ReviewRecord(
        review_id=f"review_{uuid4().hex[:12]}",
        candidate_id=candidate_id,
        review_status=status,  # type: ignore[arg-type]
        reviewer=payload.reviewer,
        review_note=payload.review_note,
        reviewed_at=reviewed_at,
    )
    db = SessionLocal()
    try:
        with db.begin():
            written = db_repo.update_knowledge_candidate_in_db(
                db,
                candidate_id,
                {
                    "review_status": status,
                    "reviewer": payload.reviewer,
                    "review_note": payload.review_note,
                    "reviewed_at": reviewed_at,
                    "updated_at": reviewed_at,
                }, commit=False,
            )
            db_repo.save_review_record_to_db(
                db, review, candidate.model_dump(), commit=False
            )
    except Exception as exc:
        db.rollback()
        raise _persistence_failure("review", exc) from None
    finally:
        db.close()
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

    chunks = sorted(chunks_by_id.values(), key=lambda item: item.chunk_id)
    db = SessionLocal()
    try:
        with db.begin():
            db_repo.save_rag_chunks_to_db(
                db, [chunk.model_dump() for chunk in chunks], commit=False
            )
    except Exception as exc:
        db.rollback()
        raise _persistence_failure("RAG build", exc) from None
    finally:
        db.close()

    # ── P1-M22: Sync approved knowledge to vector RAG ──────────────────────
    embedding_count = 0
    failed_embedding_count = 0
    vector_sync_enabled = False
    vector_sync_error: str | None = None
    embedding_provider_name: str | None = None
    embedding_model_name: str | None = None
    embedding_dim_val: int | None = None
    approved_candidate_count = 0
    skipped_candidate_count = 0

    # Count approved vs not-approved candidates
    for candidate in candidates:
        if candidate.review_status == "approved":
            approved_candidate_count += 1
        else:
            skipped_candidate_count += 1

    # Generate embeddings for approved candidates
    if approved_candidate_count > 0:
        try:
            emb_provider = get_embedding_provider()
            embedding_provider_name = emb_provider.provider_name
            embedding_model_name = emb_provider.model_name
            embedding_dim_val = emb_provider.dimension
            vector_sync_enabled = True

            # Build lookup from candidate_id -> chunk for chunk_text
            chunk_by_candidate: dict[str, RagChunk] = {}
            for chunk in chunks:
                chunk_by_candidate[chunk.candidate_id] = chunk

            embedding_rows: list[dict[str, Any]] = []
            for candidate in candidates:
                if candidate.review_status != "approved":
                    continue
                chunk = chunk_by_candidate.get(candidate.candidate_id)
                if chunk is None:
                    continue

                chunk_text_val = chunk.chunk_text
                embedding_vector = emb_provider.embed(chunk_text_val)

                emb_id = f"ragemb_{candidate.candidate_id}"

                # Build metadata_json with full source trace
                meta: dict[str, Any] = {
                    "candidate_id": candidate.candidate_id,
                    "source_type": candidate.source_type,
                    "source_batch_id": candidate.source_batch_id,
                    "source_conversation_id": candidate.source_conversation_id,
                    "source_message_ids": candidate.source_message_ids,
                    "source_bad_case_id": candidate.source_bad_case_id,
                    "source_retrieval_id": candidate.source_retrieval_id,
                    "source_chunk_ids": candidate.source_chunk_ids,
                    "source_legacy_id": candidate.source_legacy_id,
                    "source_import_id": candidate.source_import_id,
                    "intent": candidate.intent,
                    "quality_score": candidate.quality_score,
                    "modality": "text",
                    "sync_method": "approved_knowledge_vector_sync",
                }

                embedding_rows.append(
                    {
                        "id": emb_id,
                        "chunk_id": chunk.chunk_id,
                        "candidate_id": candidate.candidate_id,
                        "source_type": candidate.source_type,
                        "source_batch_id": candidate.source_batch_id,
                        "source_message_id": (
                            candidate.source_message_ids[0]
                            if candidate.source_message_ids
                            else None
                        ),
                        "modality": "text",
                        "chunk_text": chunk_text_val,
                        "metadata_json": meta,
                        "embedding": embedding_vector,
                        "embedding_provider": embedding_provider_name,
                        "embedding_model": embedding_model_name,
                        "embedding_dimension": embedding_dim_val,
                    }
                )

            # Write to rag_embeddings table via DB (delete-rebuild strategy)
            expected_count = len(embedding_rows)
            try:
                db2 = SessionLocal()
                try:
                    embedding_count = db_repo.save_rag_embeddings_to_db(
                        db2, embedding_rows
                    )
                finally:
                    db2.close()
            except Exception as exc:
                # P1-M22.2: do NOT silently swallow — report error
                _logger.exception("Failed to save RAG embeddings to database")
                failed_embedding_count = expected_count
                vector_sync_error = _safe_error_message(exc)

            # Detect partial failure: repo returned fewer rows than expected
            if embedding_count < expected_count and failed_embedding_count == 0:
                failed_embedding_count = expected_count - embedding_count
                vector_sync_error = (
                    f"Partial write: {embedding_count}/{expected_count} embeddings saved; "
                    f"{failed_embedding_count} failed."
                )
        except Exception as exc:
            _logger.exception("Failed to generate RAG embeddings")
            vector_sync_enabled = False
            failed_embedding_count = approved_candidate_count
            vector_sync_error = _safe_error_message(exc)

    return RagBuildResult(
        built_count=built_count,
        updated_count=updated_count,
        skipped_count=sum(skipped_reasons.values()),
        skipped_reasons=skipped_reasons,
        chunk_count=len(chunks),
        status="completed",
        build_method="local_json_mock_retrieval",
        created_at=created_at,
        embedding_count=embedding_count,
        vector_sync_enabled=vector_sync_enabled,
        embedding_provider=embedding_provider_name,
        embedding_model=embedding_model_name,
        embedding_dimension=embedding_dim_val,
        approved_candidate_count=approved_candidate_count,
        skipped_candidate_count=skipped_candidate_count,
        failed_embedding_count=failed_embedding_count,
        vector_sync_error=vector_sync_error,
    )


def _rag_chunk_changed(previous: RagChunk, current: RagChunk) -> bool:
    comparable_previous = previous.model_dump(exclude={"created_at"})
    comparable_current = current.model_dump(exclude={"created_at"})
    return comparable_previous != comparable_current


def list_rag_chunks() -> list[RagChunk]:
    db = SessionLocal()
    try:
        return [RagChunk(**item) for item in db_repo.list_rag_chunks_from_db(db)]
    except Exception as exc:
        raise _persistence_failure("list RAG chunks", exc) from None
    finally:
        db.close()


def get_rag_chunk(chunk_id: str) -> RagChunk | None:
    db = SessionLocal()
    try:
        result = db_repo.get_rag_chunk_from_db(db, chunk_id)
        return RagChunk(**result) if result is not None else None
    except Exception as exc:
        raise _persistence_failure("get RAG chunk", exc) from None
    finally:
        db.close()


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

    # ── P1-M23: semantic retrieval attempt ──────────────────────────
    retrieval_mode: str = "customerops_local_mock_retrieval"
    fallback_used = False
    fallback_reason: str | None = None
    semantic_results: list[dict[str, Any]] = []
    semantic_scores: list[float] = []
    embedding_provider_name: str | None = None
    embedding_model_name: str | None = None

    # Check if we can attempt semantic retrieval
    db = None
    try:
        from app.db_models import _HAS_PGVECTOR, _is_postgresql

        is_pg = _is_postgresql()
        has_pgv = _HAS_PGVECTOR

        db = SessionLocal()
        emb_provider = get_embedding_provider()
        query_emb = emb_provider.embed(query)
        embedding_provider_name = emb_provider.provider_name
        embedding_model_name = emb_provider.model_name
        query_dim = len(query_emb)

        if is_pg and has_pgv:
            # Check stored embedding dimension matches query embedding dimension
            # by sampling one rag_embedding row
            try:
                from app.db_models import RagEmbedding
                sample = db.query(RagEmbedding).filter(
                    RagEmbedding.embedding_dimension.isnot(None)
                ).first()
                stored_dim = sample.embedding_dimension if sample else None

                if stored_dim is not None and stored_dim != query_dim:
                    fallback_used = True
                    fallback_reason = f"embedding_dimension_mismatch(query={query_dim}!=stored={stored_dim})"
                    retrieval_mode = "customerops_keyword_fallback"
                else:
                    # Try semantic search
                    semantic_results = db_repo.search_rag_embeddings_semantic(
                        db, query_emb, top_k
                    )
                    if semantic_results:
                        retrieval_mode = "customerops_vector_retrieval"
                        semantic_scores = [
                            r.get("similarity_score", 0.0) for r in semantic_results
                        ]
                    else:
                        fallback_used = True
                        fallback_reason = "semantic_no_hits"
                        retrieval_mode = "customerops_vector_with_keyword_fallback"
            except Exception as exc:
                fallback_used = True
                fallback_reason = f"pgvector_query_error:{_safe_error_message(exc)}"
                retrieval_mode = "customerops_keyword_fallback"
        else:
            # SQLite or no pgvector — cannot do semantic
            fallback_used = True
            if not is_pg:
                fallback_reason = "sqlite_no_pgvector"
            else:
                fallback_reason = "pgvector_unavailable"
            retrieval_mode = "customerops_keyword_fallback"
    except Exception as exc:
        # Embedding generation failed
        fallback_used = True
        fallback_reason = f"embedding_generation_failed:{_safe_error_message(exc)}"
        retrieval_mode = "customerops_keyword_fallback"
    finally:
        if db is not None:
            try:
                db.close()
            except Exception:
                pass

    # ── Build results from semantic hits ────────────────────────────
    if semantic_results and not fallback_used:
        results: list[CustomerOpsRetrievalResult] = []
        for hit in semantic_results:
            meta = hit.get("metadata_json", {})
            chunk_id_val = hit.get("chunk_id", "") or ""
            candidate_id_val = hit.get("candidate_id", "") or ""
            chunk_text_val = hit.get("chunk_text", "") or ""
            source_type_val = hit.get("source_type", "sanitized_batch") or "sanitized_batch"
            source_batch_id_val = hit.get("source_batch_id")
            intent_val = meta.get("intent", "general") or "general"
            tags_val = meta.get("tags", []) or []
            risk_level_val = meta.get("risk_level", "medium") or "medium"
            quality_score_val = float(meta.get("quality_score", 0.5) or 0.5)
            knowledge_type_val = meta.get("knowledge_type", "faq") or "faq"
            score_val = hit.get("similarity_score", 0.0)

            results.append(
                CustomerOpsRetrievalResult(
                    score=round(score_val, 4),
                    matched_terms=[],
                    chunk_id=chunk_id_val,
                    candidate_id=candidate_id_val,
                    source_type=source_type_val,
                    source_batch_id=source_batch_id_val,
                    source_conversation_id=meta.get("source_conversation_id"),
                    source_message_ids=list(meta.get("source_message_ids", [])),
                    source_bad_case_id=meta.get("source_bad_case_id"),
                    source_retrieval_id=meta.get("source_retrieval_id"),
                    source_chunk_ids=list(meta.get("source_chunk_ids", [])),
                    source_legacy_id=meta.get("source_legacy_id"),
                    source_import_id=meta.get("source_import_id"),
                    migration_mode=meta.get("migration_mode"),
                    source_note=meta.get("source_note"),
                    knowledge_type=knowledge_type_val,
                    intent=intent_val,
                    tags=tags_val,
                    risk_level=risk_level_val,
                    quality_score=quality_score_val,
                    review_status="approved",
                    chunk_text=chunk_text_val,
                    build_method="vector_semantic_retrieval",
                    answer=_answer_from_chunk_text(chunk_text_val),
                )
            )
    else:
        # ── Fallback: keyword / overlap retrieval from rag_chunks ───
        results = []
        for chunk in list_rag_chunks():
            if not _matches_customerops_filters(chunk, payload.filters):
                continue
            result = _customerops_score_chunk(query, chunk)
            if result is not None:
                results.append(result)
        results = sorted(results, key=lambda item: item.score, reverse=True)[:top_k]

    retrieval_unavailable = bool(
        not results
        and fallback_reason
        and fallback_reason.startswith(
            ("embedding_generation_failed:", "pgvector_query_error:")
        )
    )
    answerability = evaluate_answerability(
        query=query,
        evidence=[
            AnswerabilityEvidence(score=float(item.score), source="p1")
            for item in results
        ],
        scope="p1",
        retrieval_unavailable=retrieval_unavailable,
    )

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
        retrieval_mode=retrieval_mode,  # type: ignore[arg-type]
        fallback_used=fallback_used,
        fallback_reason=fallback_reason,
        matched_chunk_scores=semantic_scores if semantic_scores else [r.score for r in results],
        embedding_provider=embedding_provider_name,
        embedding_model=embedding_model_name,
        answerability=answerability,
    )
    _write_retrieval_trace(trace)
    return CustomerOpsRetrievalResponse(
        retrieval_id=retrieval_id,
        query=query,
        top_k=top_k,
        retrieval_mode=retrieval_mode,  # type: ignore[arg-type]
        results=results,
        fallback_used=fallback_used,
        fallback_reason=fallback_reason,
        created_at=created_at,
        answerability=answerability,
    )


def _write_retrieval_trace(trace: CustomerOpsRetrievalTrace) -> None:
    trace_dict = trace.model_dump()
    # Retrieval logging is deliberately best-effort and never falls back to JSON.
    try:
        db = SessionLocal()
        try:
            db_trace = trace_dict.copy()
            # Ensure metadata_json captures semantic trace
            if "metadata" not in db_trace:
                db_trace["metadata"] = {}
            if isinstance(db_trace.get("metadata"), dict):
                db_trace["metadata"] = dict(db_trace["metadata"])
                db_trace["metadata"]["retrieval_mode"] = trace.retrieval_mode
                db_trace["metadata"]["fallback_used"] = trace.fallback_used
                db_trace["metadata"]["fallback_reason"] = trace.fallback_reason
                db_trace["metadata"]["matched_chunk_scores"] = trace.matched_chunk_scores
                db_trace["metadata"]["embedding_provider"] = trace.embedding_provider
                db_trace["metadata"]["embedding_model"] = trace.embedding_model
            db_repo.save_retrieval_log_to_db(db, db_trace)
        finally:
            db.close()
    except Exception:
        _logger.exception(
            "P1_RETRIEVAL_AUDIT_WRITE_FAILED retrieval_id=%s", trace.retrieval_id
        )


def get_customerops_retrieval_trace(
    retrieval_id: str,
) -> CustomerOpsRetrievalTrace | None:
    db = SessionLocal()
    try:
        result = db_repo.get_retrieval_log_from_db(db, retrieval_id)
        return CustomerOpsRetrievalTrace(**result) if result is not None else None
    except Exception as exc:
        raise _persistence_failure("get retrieval trace", exc) from None
    finally:
        db.close()


def create_bad_case(
    payload: BadCaseSubmitRequest,
    retrieval_trace: CustomerOpsRetrievalTrace,
    user_query: str,
    agent_answer: str,
    expected_answer: str | None,
) -> BadCaseRecord:
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
    db = SessionLocal()
    try:
        db_repo.save_bad_case_to_db(db, bad_case.model_dump())
        return bad_case
    except Exception as exc:
        db.rollback()
        raise _persistence_failure("write bad case", exc) from None
    finally:
        db.close()


def list_bad_cases(
    status: str | None = None,
    issue_type: str | None = None,
    severity: str | None = None,
) -> list[BadCaseRecord]:
    db = SessionLocal()
    try:
        rows = db_repo.list_bad_cases_from_db(
            db, status=status, issue_type=issue_type, severity=severity
        )
        return [BadCaseRecord(**item) for item in rows]
    except Exception as exc:
        raise _persistence_failure("list bad cases", exc) from None
    finally:
        db.close()


def get_bad_case(bad_case_id: str) -> BadCaseRecord | None:
    db = SessionLocal()
    try:
        result = db_repo.get_bad_case_from_db(db, bad_case_id)
        return BadCaseRecord(**result) if result is not None else None
    except Exception as exc:
        raise _persistence_failure("get bad case", exc) from None
    finally:
        db.close()


def update_bad_case(
    bad_case_id: str,
    payload: BadCaseUpdateRequest,
) -> BadCaseRecord | None:
    bad_case = get_bad_case(bad_case_id)
    if bad_case is None:
        return None

    updates = payload.model_dump(exclude_unset=True)
    db = SessionLocal()
    try:
        result = db_repo.update_bad_case_in_db(db, bad_case_id, updates)
        return BadCaseRecord(**result) if result is not None else None
    except Exception as exc:
        db.rollback()
        raise _persistence_failure("update bad case", exc) from None
    finally:
        db.close()


def create_candidate_from_bad_case(
    bad_case: BadCaseRecord,
    payload: BadCaseDraftRequest,
    question: str,
    answer: str,
    tags: list[str],
) -> KnowledgeCandidate:
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
    resolution_type = bad_case.resolution_type
    if resolution_type not in {"create_new_knowledge", "update_existing_knowledge"}:
        resolution_type = "create_new_knowledge"
    note_suffix = f"Created pending_review draft {candidate.candidate_id} from Bad Case."
    existing_note = bad_case.review_note.strip()
    review_note = (
        f"{existing_note}\n{note_suffix}" if existing_note else note_suffix
    )
    bad_case_updates = {
        "status": "resolved",
        "resolution_type": resolution_type,
        "linked_candidate_id": candidate.candidate_id,
        "review_note": review_note,
        "updated_at": now,
    }
    db = SessionLocal()
    try:
        with db.begin():
            db_repo.create_candidate_from_bad_case_in_db(
                db, candidate.model_dump(), commit=False
            )
            db_repo.update_bad_case_in_db(
                db, bad_case.bad_case_id, bad_case_updates, commit=False
            )
        return candidate
    except Exception as exc:
        db.rollback()
        raise _persistence_failure("bad case draft", exc) from None
    finally:
        db.close()


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
    now = datetime.now(UTC).isoformat()
    import_id = f"legacy_import_{uuid4().hex[:12]}"
    migration_mode = "trusted_import" if payload.trusted_import else "review_required"
    review_status = "approved" if payload.trusted_import else "pending_review"
    created_candidate_count = 0
    updated_count = 0
    skipped_reasons: dict[str, int] = {}
    candidate_ids: list[str] = []

    candidates_to_save: list[KnowledgeCandidate] = []
    db = SessionLocal()
    try:
        for item in payload.items:
            candidate_id = _legacy_candidate_id(payload.source_name, item.legacy_id)
            previous = db_repo.get_knowledge_candidate_from_db(db, candidate_id)
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
                candidates_to_save.append(candidate)
                created_candidate_count += 1
            elif _legacy_candidate_changed(previous, candidate):
                candidates_to_save.append(candidate)
                updated_count += 1
            else:
                skipped_reasons["unchanged"] = skipped_reasons.get("unchanged", 0) + 1

        effective = {
            candidate.candidate_id: candidate for candidate in candidates_to_save
        }
        for candidate_id in candidate_ids:
            if candidate_id not in effective:
                previous = db_repo.get_knowledge_candidate_from_db(db, candidate_id)
                if previous is not None:
                    effective[candidate_id] = previous
        candidates = list(effective.values())
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
        db.rollback()  # close read transaction before the atomic write boundary
        with db.begin():
            if candidates_to_save:
                db_repo.save_knowledge_candidates_to_db(
                    db, candidates_to_save, commit=False
                )
            db_repo.save_legacy_import_receipt_to_db(
                db, candidate_ids, metadata.model_dump(), commit=False
            )
        return metadata
    except Exception as exc:
        db.rollback()
        raise _persistence_failure("legacy import", exc) from None
    finally:
        db.close()


def list_legacy_rag_imports() -> list[LegacyRagImportMetadata]:
    db = SessionLocal()
    try:
        return [
            LegacyRagImportMetadata(**item)
            for item in db_repo.list_legacy_import_receipts_from_db(db)
        ]
    except Exception as exc:
        raise _persistence_failure("list legacy imports", exc) from None
    finally:
        db.close()


def get_legacy_rag_import(import_id: str) -> LegacyRagImportMetadata | None:
    db = SessionLocal()
    try:
        data = db_repo.get_legacy_import_receipt_from_db(db, import_id)
        return LegacyRagImportMetadata(**data) if data is not None else None
    except Exception as exc:
        raise _persistence_failure("get legacy import", exc) from None
    finally:
        db.close()

"""Database repository layer for DataHub core data access.

Provides safe, idempotent read/write functions for:
- raw_batches / raw_messages
- sanitized_batches / sanitized_messages
- manual_cleaning_records
- knowledge_candidates
- review_records

All functions accept a SQLAlchemy Session so callers control transaction boundaries.
Never prints or logs DATABASE_URL, user credentials, or connection strings.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.db_models import (
    BadCase,
    KnowledgeCandidate as DbKnowledgeCandidate,
    ManualCleaningRecord,
    RagChunk,
    RagEmbedding,
    RawBatch,
    RawMessage,
    RetrievalLog,
    ReviewRecord,
    SanitizedBatch as DbSanitizedBatch,
    SanitizedMessage as DbSanitizedMessage,
)
from app.schemas import (
    KnowledgeCandidate,
    ManualCleaningRecord as SchemaManualCleaningRecord,
    ReviewRecord as SchemaReviewRecord,
    SanitizedBatch,
    SanitizedMessage,
    SourceBatchMetadata,
)


# ──────────────────────────────────────────────────────────────────
#  Raw batches
# ──────────────────────────────────────────────────────────────────


def save_raw_batch_to_db(
    db: Session,
    batch_id: str,
    source_name: str,
    message_count: int,
    raw_payload: dict[str, Any],
    conversations: list[dict[str, Any]],
) -> None:
    """Idempotent: upsert raw_batches row and replace raw_messages for batch_id."""
    now = datetime.now(UTC)

    # Upsert raw_batches
    existing = db.query(RawBatch).filter(RawBatch.id == batch_id).first()
    if existing:
        existing.source_name = source_name
        existing.message_count = message_count
        existing.metadata_json = raw_payload
        existing.updated_at = now
    else:
        db.add(
            RawBatch(
                id=batch_id,
                source_name=source_name,
                source_type="chat_logs",
                status="raw_imported",
                message_count=message_count,
                metadata_json=raw_payload,
                created_at=now,
                updated_at=now,
            )
        )

    # Delete old raw_messages for this batch (idempotent)
    db.query(RawMessage).filter(RawMessage.batch_id == batch_id).delete()

    # Insert raw messages
    for conversation in conversations:
        conv_id = str(conversation.get("conversation_id") or "")
        for msg in conversation.get("messages", []):
            if not isinstance(msg, dict):
                continue
            msg_id = str(msg.get("message_id") or "")
            # Use compound key to avoid UNIQUE conflicts across batches
            raw_msg_db_id = f"{batch_id}|{msg_id}"
            db.add(
                RawMessage(
                    id=raw_msg_db_id,
                    batch_id=batch_id,
                    role=str(msg.get("role", "system")),
                    content=str(msg.get("content", "")),
                    timestamp=str(msg.get("timestamp", "")),
                    metadata_json={"conversation_id": conv_id},
                    created_at=now,
                )
            )

    db.commit()


def list_raw_batches_from_db(db: Session) -> list[SourceBatchMetadata]:
    rows = db.query(RawBatch).order_by(RawBatch.created_at.desc()).all()
    result: list[SourceBatchMetadata] = []
    for row in rows:
        result.append(
            SourceBatchMetadata(
                batch_id=row.id,
                source_name=row.source_name,
                message_count=row.message_count,
                conversation_count=_conversation_count_from_payload(row.metadata_json),
                created_at=row.created_at.isoformat() if row.created_at else "",
                status="raw_imported",
            )
        )
    return result


def get_raw_batch_from_db(db: Session, batch_id: str) -> SourceBatchMetadata | None:
    row = db.query(RawBatch).filter(RawBatch.id == batch_id).first()
    if row is None:
        return None
    return SourceBatchMetadata(
        batch_id=row.id,
        source_name=row.source_name,
        message_count=row.message_count,
        conversation_count=_conversation_count_from_payload(row.metadata_json),
        created_at=row.created_at.isoformat() if row.created_at else "",
        status="raw_imported",
    )


def get_raw_batch_document_from_db(
    db: Session, batch_id: str
) -> dict[str, Any] | None:
    """Reconstruct the raw batch document (including conversations) from DB."""
    row = db.query(RawBatch).filter(RawBatch.id == batch_id).first()
    if row is None:
        return None

    payload = row.metadata_json
    if not isinstance(payload, dict):
        return None

    # Ensure the payload has the expected structure
    if "metadata" not in payload:
        payload["metadata"] = {
            "batch_id": row.id,
            "source_name": row.source_name,
            "message_count": row.message_count,
            "conversation_count": _conversation_count_from_payload(payload),
            "created_at": row.created_at.isoformat() if row.created_at else "",
            "status": "raw_imported",
        }
    if "raw_payload" not in payload:
        # Reconstruct raw_payload from raw_messages if not stored
        messages = (
            db.query(RawMessage)
            .filter(RawMessage.batch_id == batch_id)
            .order_by(RawMessage.created_at)
            .all()
        )
        conversations_dict: dict[str, list[dict[str, Any]]] = {}
        for msg in messages:
            conv_id = "unknown"
            if isinstance(msg.metadata_json, dict):
                conv_id = str(msg.metadata_json.get("conversation_id", "unknown"))
            conversations_dict.setdefault(conv_id, []).append(
                {
                    "message_id": msg.id,
                    "role": msg.role,
                    "content": msg.content,
                    "timestamp": msg.timestamp or "",
                }
            )
        payload["raw_payload"] = {
            "source_name": row.source_name,
            "conversations": [
                {"conversation_id": cid, "messages": msgs}
                for cid, msgs in conversations_dict.items()
            ],
        }

    return payload


# ──────────────────────────────────────────────────────────────────
#  Sanitized batches
# ──────────────────────────────────────────────────────────────────


def save_sanitized_batch_to_db(
    db: Session,
    sanitized_batch: SanitizedBatch,
    job: Any,  # CleaningJobMetadata
) -> None:
    """Idempotent: upsert sanitized_batches row and replace sanitized_messages."""
    now = datetime.now(UTC)
    batch_id = sanitized_batch.batch_id

    # Count quality levels
    high_count = sum(
        1 for m in sanitized_batch.messages if m.quality_level == "high"
    )

    # Upsert sanitized_batches
    existing = db.query(DbSanitizedBatch).filter(DbSanitizedBatch.id == batch_id).first()
    summary_metadata = {
        "raw_message_count": sanitized_batch.raw_message_count,
        "sanitized_message_count": sanitized_batch.sanitized_message_count,
        "dropped_message_count": sanitized_batch.dropped_message_count,
        "pii_detected_count": sanitized_batch.pii_detected_count,
        "exact_duplicate_count": sanitized_batch.exact_duplicate_count,
        "near_duplicate_count": sanitized_batch.near_duplicate_count,
        "low_quality_count": sanitized_batch.low_quality_count,
        "noise_count": sanitized_batch.noise_count,
        "job_id": getattr(job, "job_id", ""),
    }
    if existing:
        existing.raw_batch_id = sanitized_batch.source_batch_id
        existing.status = "sanitized"
        existing.message_count = sanitized_batch.sanitized_message_count
        existing.high_quality_count = high_count
        existing.review_recommended_count = sanitized_batch.review_recommended_count
        existing.drop_recommended_count = sanitized_batch.drop_recommended_count
        existing.average_quality_score = sanitized_batch.average_quality_score
        existing.metadata_json = summary_metadata
        existing.updated_at = now
    else:
        db.add(
            DbSanitizedBatch(
                id=batch_id,
                raw_batch_id=sanitized_batch.source_batch_id,
                status="sanitized",
                message_count=sanitized_batch.sanitized_message_count,
                high_quality_count=high_count,
                review_recommended_count=sanitized_batch.review_recommended_count,
                drop_recommended_count=sanitized_batch.drop_recommended_count,
                average_quality_score=sanitized_batch.average_quality_score,
                metadata_json=summary_metadata,
                created_at=now,
                updated_at=now,
            )
        )

    # Delete old sanitized_messages for this batch (idempotent)
    db.query(DbSanitizedMessage).filter(
        DbSanitizedMessage.batch_id == batch_id
    ).delete()

    # Insert sanitized messages
    for msg in sanitized_batch.messages:
        # Encode batch_id + conversation_id in the id for global uniqueness
        msg_db_id = f"{batch_id}__{msg.conversation_id}__{msg.message_id}"
        db.add(
            DbSanitizedMessage(
                id=msg_db_id,
                batch_id=batch_id,
                raw_message_id=msg.source_message_id,
                role=msg.role,
                content=msg.content,
                sanitized_content=msg.content,
                quality_score=msg.quality_score,
                quality_level=msg.quality_level,
                suggested_action=msg.suggested_action,
                cleaning_issues=msg.cleaning_issues,
                risk_flags=msg.risk_flags,
                pii_entities=msg.pii_types,
                created_at=now,
                updated_at=now,
            )
        )

    db.commit()


def list_sanitized_batches_from_db(
    db: Session,
) -> list[dict[str, Any]]:
    """Return sanitized batch summary entries (same shape as JSON index)."""
    rows = db.query(DbSanitizedBatch).order_by(
        DbSanitizedBatch.created_at.desc()
    ).all()
    result: list[dict[str, Any]] = []
    for row in rows:
        meta = row.metadata_json or {}
        entry: dict[str, Any] = {
            "batch_id": row.id,
            "source_batch_id": row.raw_batch_id,
            "status": row.status,
            "raw_message_count": meta.get("raw_message_count", row.message_count),
            "sanitized_message_count": row.message_count,
            "dropped_message_count": meta.get("dropped_message_count", 0),
            "pii_detected_count": meta.get("pii_detected_count", 0),
            "exact_duplicate_count": meta.get("exact_duplicate_count", 0),
            "near_duplicate_count": meta.get("near_duplicate_count", 0),
            "low_quality_count": meta.get("low_quality_count", 0),
            "noise_count": meta.get("noise_count", 0),
            "review_recommended_count": row.review_recommended_count,
            "drop_recommended_count": row.drop_recommended_count,
            "average_quality_score": row.average_quality_score or 0.0,
            "created_at": (
                row.created_at.isoformat() if row.created_at else ""
            ),
        }
        result.append(entry)
    return result


def get_sanitized_batch_from_db(
    db: Session, batch_id: str
) -> SanitizedBatch | None:
    """Reconstruct full SanitizedBatch (with messages) from DB."""
    batch_row = (
        db.query(DbSanitizedBatch)
        .filter(DbSanitizedBatch.id == batch_id)
        .first()
    )
    if batch_row is None:
        return None

    msg_rows = (
        db.query(DbSanitizedMessage)
        .filter(DbSanitizedMessage.batch_id == batch_id)
        .order_by(DbSanitizedMessage.created_at)
        .all()
    )

    messages: list[SanitizedMessage] = []
    for row in msg_rows:
        # Decode from id: "{batch_id}__{conv_id}__{msg_id}"
        conv_id = ""
        msg_id = row.id
        parts = row.id.split("__", 2)
        if len(parts) == 3:
            _, conv_id, msg_id = parts
        elif len(parts) == 2:
            conv_id, msg_id = parts

        messages.append(
            SanitizedMessage(
                source_batch_id=batch_id,
                conversation_id=conv_id,
                message_id=msg_id,
                source_message_id=row.raw_message_id or msg_id,
                role=row.role,  # type: ignore[arg-type]
                content=row.content,
                pii_detected=bool(row.pii_entities),
                pii_types=list(row.pii_entities) if row.pii_entities else [],
                cleaning_notes=[],
                cleaning_issues=list(row.cleaning_issues) if row.cleaning_issues else [],
                risk_flags=list(row.risk_flags) if row.risk_flags else [],
                quality_score=float(row.quality_score),
                quality_level=row.quality_level,  # type: ignore[arg-type]
                suggested_action=row.suggested_action,  # type: ignore[arg-type]
                manual_cleaning_status="not_cleaned",
                manual_cleaned_content=None,
                manual_action=None,
                cleaner=None,
                cleaning_note=None,
                manual_cleaned_at=None,
            )
        )

    meta = batch_row.metadata_json or {}
    return SanitizedBatch(
        batch_id=batch_row.id,
        source_batch_id=batch_row.raw_batch_id,
        status="sanitized",
        raw_message_count=int(meta.get("raw_message_count", batch_row.message_count)),
        sanitized_message_count=batch_row.message_count,
        dropped_message_count=int(meta.get("dropped_message_count", 0)),
        pii_detected_count=int(meta.get("pii_detected_count", 0)),
        exact_duplicate_count=int(meta.get("exact_duplicate_count", 0)),
        near_duplicate_count=int(meta.get("near_duplicate_count", 0)),
        low_quality_count=int(meta.get("low_quality_count", 0)),
        noise_count=int(meta.get("noise_count", 0)),
        review_recommended_count=batch_row.review_recommended_count,
        drop_recommended_count=batch_row.drop_recommended_count,
        average_quality_score=float(batch_row.average_quality_score or 0.0),
        created_at=(
            batch_row.created_at.isoformat() if batch_row.created_at else ""
        ),
        messages=messages,
    )


# ──────────────────────────────────────────────────────────────────
#  Helpers
# ──────────────────────────────────────────────────────────────────


def _conversation_count_from_payload(payload: Any) -> int:
    if not isinstance(payload, dict):
        return 0
    raw = payload.get("raw_payload")
    if not isinstance(raw, dict):
        return 0
    conversations = raw.get("conversations")
    if isinstance(conversations, list):
        return len(conversations)
    return 0


def _get_db_session() -> Session:
    """Create a new database session. Caller must close it."""
    return SessionLocal()


# ──────────────────────────────────────────────────────────────────
#  Manual cleaning records  (P1-M18)
# ──────────────────────────────────────────────────────────────────


def save_manual_cleaning_record_to_db(
    db: Session,
    record: SchemaManualCleaningRecord,
) -> None:
    """Save a manual cleaning record to the database.

    Idempotent: if a record with the same sanitized_message_id already exists,
    the new record is appended (multiple records per message are allowed).
    The latest record by created_at is treated as the effective record.
    """
    now = datetime.now(UTC)
    db.add(
        ManualCleaningRecord(
            id=record.record_id,
            sanitized_message_id=record.message_id,
            cleaner=record.cleaner,
            action=record.manual_action,
            original_content=record.original_sanitized_content,
            cleaned_content=record.manual_cleaned_content,
            note=record.cleaning_note,
            created_at=now,
        )
    )
    db.commit()


def get_manual_cleaning_records_for_batch_from_db(
    db: Session, batch_id: str
) -> list[dict[str, Any]]:
    """Return all manual cleaning records for messages in a batch.

    Joins with sanitized_messages to find records belonging to the batch.
    """
    # Get message IDs for this batch
    msg_ids = [
        row[0]
        for row in db.query(DbSanitizedMessage.id)
        .filter(DbSanitizedMessage.batch_id == batch_id)
        .all()
    ]
    if not msg_ids:
        return []

    # Decode message_id from compound id "{batch_id}__{conv_id}__{msg_id}"
    decoded_ids: set[str] = set()
    for mid in msg_ids:
        parts = mid.split("__", 2)
        if len(parts) >= 2:
            decoded_ids.add(parts[-1])  # last part is the original message_id
        decoded_ids.add(mid)

    rows = (
        db.query(ManualCleaningRecord)
        .filter(ManualCleaningRecord.sanitized_message_id.in_(decoded_ids))
        .order_by(ManualCleaningRecord.created_at.desc())
        .all()
    )
    result: list[dict[str, Any]] = []
    for row in rows:
        result.append(
            {
                "record_id": row.id,
                "sanitized_message_id": row.sanitized_message_id,
                "cleaner": row.cleaner,
                "action": row.action,
                "original_content": row.original_content,
                "cleaned_content": row.cleaned_content,
                "note": row.note,
                "created_at": row.created_at.isoformat() if row.created_at else "",
            }
        )
    return result


def get_effective_manual_cleaning_record(
    db: Session, message_id: str
) -> dict[str, Any] | None:
    """Return the most recent manual cleaning record for a given message_id."""
    row = (
        db.query(ManualCleaningRecord)
        .filter(ManualCleaningRecord.sanitized_message_id == message_id)
        .order_by(ManualCleaningRecord.created_at.desc())
        .first()
    )
    if row is None:
        return None
    return {
        "record_id": row.id,
        "sanitized_message_id": row.sanitized_message_id,
        "cleaner": row.cleaner,
        "action": row.action,
        "original_content": row.original_content,
        "cleaned_content": row.cleaned_content,
        "note": row.note,
        "created_at": row.created_at.isoformat() if row.created_at else "",
    }


# ──────────────────────────────────────────────────────────────────
#  Knowledge candidates  (P1-M18)
# ──────────────────────────────────────────────────────────────────


def save_knowledge_candidates_to_db(
    db: Session,
    candidates: list[KnowledgeCandidate],
) -> None:
    """Write or replace knowledge candidates for a batch.

    Idempotent: for each candidate, deletes any existing row with the same
    source_id + question + answer, then inserts the new candidate.
    This prevents infinite duplicate generation on repeated extraction.
    """
    now = datetime.now(UTC)
    for candidate in candidates:
        # Idempotent dedup key: source_id + question + answer
        source_id = candidate.source_batch_id or candidate.candidate_id
        db.query(DbKnowledgeCandidate).filter(
            DbKnowledgeCandidate.source_id == source_id,
            DbKnowledgeCandidate.question == candidate.question,
            DbKnowledgeCandidate.answer == candidate.answer,
        ).delete()

        db.add(
            DbKnowledgeCandidate(
                id=candidate.candidate_id,
                source_type=candidate.source_type,
                source_id=source_id,
                question=candidate.question,
                answer=candidate.answer,
                intent=candidate.intent,
                tags=candidate.tags,
                risk_level=candidate.risk_level,
                quality_score=candidate.quality_score,
                status=candidate.review_status,
                metadata_json={
                    "source_batch_id": candidate.source_batch_id,
                    "source_conversation_id": candidate.source_conversation_id,
                    "source_message_ids": candidate.source_message_ids,
                    "source_bad_case_id": candidate.source_bad_case_id,
                    "source_retrieval_id": candidate.source_retrieval_id,
                    "source_chunk_ids": candidate.source_chunk_ids,
                    "source_legacy_id": candidate.source_legacy_id,
                    "source_import_id": candidate.source_import_id,
                    "linked_candidate_id": candidate.linked_candidate_id,
                    "knowledge_type": candidate.knowledge_type,
                    "extraction_method": candidate.extraction_method,
                    "migration_mode": candidate.migration_mode,
                    "source_note": candidate.source_note,
                    "cleaning_issues": candidate.cleaning_issues,
                    "risk_flags": candidate.risk_flags,
                    "manual_cleaning_status": candidate.manual_cleaning_status,
                    "manual_action": candidate.manual_action,
                    "reviewer": candidate.reviewer,
                    "review_note": candidate.review_note,
                    "reviewed_at": candidate.reviewed_at,
                    "updated_at": candidate.updated_at,
                },
                created_at=now,
                updated_at=now,
            )
        )
    db.commit()


def list_knowledge_candidates_from_db(db: Session) -> list[KnowledgeCandidate]:
    """Return all knowledge candidates from the database."""
    rows = db.query(DbKnowledgeCandidate).order_by(
        DbKnowledgeCandidate.created_at.desc()
    ).all()
    return [_db_candidate_to_schema(row) for row in rows]


def get_knowledge_candidate_from_db(
    db: Session, candidate_id: str
) -> KnowledgeCandidate | None:
    """Return a single knowledge candidate by ID."""
    row = (
        db.query(DbKnowledgeCandidate)
        .filter(DbKnowledgeCandidate.id == candidate_id)
        .first()
    )
    if row is None:
        return None
    return _db_candidate_to_schema(row)


def update_knowledge_candidate_in_db(
    db: Session,
    candidate_id: str,
    updates: dict[str, Any],
) -> KnowledgeCandidate | None:
    """Update fields on an existing knowledge candidate row."""
    row = (
        db.query(DbKnowledgeCandidate)
        .filter(DbKnowledgeCandidate.id == candidate_id)
        .first()
    )
    if row is None:
        return None

    now = datetime.now(UTC)
    # Update core columns
    if "question" in updates:
        row.question = updates["question"]
    if "answer" in updates:
        row.answer = updates["answer"]
    if "intent" in updates:
        row.intent = updates["intent"]
    if "tags" in updates:
        row.tags = updates["tags"]
    if "risk_level" in updates:
        row.risk_level = updates["risk_level"]
    if "quality_score" in updates:
        row.quality_score = updates["quality_score"]
    if "review_status" in updates:
        row.status = updates["review_status"]

    # Merge metadata_json
    meta = dict(row.metadata_json) if isinstance(row.metadata_json, dict) else {}
    for key in (
        "reviewer",
        "review_note",
        "reviewed_at",
        "updated_at",
        "cleaning_issues",
        "risk_flags",
        "manual_cleaning_status",
        "manual_action",
    ):
        if key in updates:
            meta[key] = updates[key]
    meta["updated_at"] = now.isoformat()
    row.metadata_json = meta
    row.updated_at = now
    db.commit()
    db.refresh(row)
    return _db_candidate_to_schema(row)


def list_pending_review_candidates_from_db(
    db: Session,
) -> list[KnowledgeCandidate]:
    """Return candidates with status pending_review or needs_revision."""
    rows = (
        db.query(DbKnowledgeCandidate)
        .filter(
            DbKnowledgeCandidate.status.in_(["pending_review", "needs_revision"])
        )
        .order_by(DbKnowledgeCandidate.created_at.desc())
        .all()
    )
    return [_db_candidate_to_schema(row) for row in rows]


def _db_candidate_to_schema(row: DbKnowledgeCandidate) -> KnowledgeCandidate:
    """Convert a DB KnowledgeCandidate row to a Pydantic KnowledgeCandidate schema."""
    meta = row.metadata_json if isinstance(row.metadata_json, dict) else {}
    return KnowledgeCandidate(
        candidate_id=row.id,
        source_type=row.source_type,  # type: ignore[arg-type]
        source_batch_id=meta.get("source_batch_id"),
        source_conversation_id=meta.get("source_conversation_id"),
        source_message_ids=list(meta.get("source_message_ids", [])),
        source_bad_case_id=meta.get("source_bad_case_id"),
        source_retrieval_id=meta.get("source_retrieval_id"),
        source_chunk_ids=list(meta.get("source_chunk_ids", [])),
        source_legacy_id=meta.get("source_legacy_id"),
        source_import_id=meta.get("source_import_id"),
        linked_candidate_id=meta.get("linked_candidate_id"),
        knowledge_type=meta.get("knowledge_type", "faq"),  # type: ignore[arg-type]
        question=row.question,
        answer=row.answer,
        intent=row.intent or "general",  # type: ignore[arg-type]
        tags=list(row.tags) if row.tags else [],
        risk_level=row.risk_level,  # type: ignore[arg-type]
        review_status=row.status,  # type: ignore[arg-type]
        quality_score=float(row.quality_score),
        extraction_method=meta.get("extraction_method", "rule_based_mock"),  # type: ignore[arg-type]
        migration_mode=meta.get("migration_mode"),
        source_note=meta.get("source_note"),
        cleaning_issues=list(meta.get("cleaning_issues", [])),
        risk_flags=list(meta.get("risk_flags", [])),
        manual_cleaning_status=meta.get("manual_cleaning_status"),
        manual_action=meta.get("manual_action"),
        created_at=row.created_at.isoformat() if row.created_at else "",
        reviewer=meta.get("reviewer"),
        review_note=meta.get("review_note"),
        reviewed_at=meta.get("reviewed_at"),
        updated_at=meta.get("updated_at"),
    )


# ──────────────────────────────────────────────────────────────────
#  Review records  (P1-M18)
# ──────────────────────────────────────────────────────────────────


def save_review_record_to_db(
    db: Session,
    review: SchemaReviewRecord,
    candidate_snapshot: dict[str, Any] | None = None,
) -> None:
    """Save a review record to the database."""
    now = datetime.now(UTC)
    db.add(
        ReviewRecord(
            id=review.review_id,
            candidate_id=review.candidate_id,
            reviewer=review.reviewer,
            action=review.review_status,
            note=review.review_note,
            snapshot_json=candidate_snapshot,
            created_at=now,
        )
    )
    db.commit()


def list_review_records_from_db(
    db: Session,
) -> list[dict[str, Any]]:
    """Return all review records from the database."""
    rows = db.query(ReviewRecord).order_by(ReviewRecord.created_at.desc()).all()
    result: list[dict[str, Any]] = []
    for row in rows:
        result.append(
            {
                "review_id": row.id,
                "candidate_id": row.candidate_id,
                "review_status": row.action,
                "reviewer": row.reviewer,
                "review_note": row.note or "",
                "reviewed_at": row.created_at.isoformat() if row.created_at else "",
            }
        )
    return result


# ──────────────────────────────────────────────────────────────────
#  RAG chunks  (P1-M19)
# ──────────────────────────────────────────────────────────────────


def save_rag_chunks_to_db(
    db: Session,
    chunks: list[dict[str, Any]],
) -> None:
    """Replace all RAG chunks in the database.

    Idempotent: deletes all existing rag_chunks rows and inserts the new set.
    This prevents infinite duplicate chunk accumulation on repeated builds.
    """
    now = datetime.now(UTC)
    # Delete all existing chunks
    db.query(RagChunk).delete()

    for chunk in chunks:
        metadata = dict(chunk)
        # Extract fields that go into dedicated columns
        chunk_id = metadata.pop("chunk_id", "")
        candidate_id = metadata.pop("candidate_id", "")
        chunk_text = metadata.pop("chunk_text", "")
        intent = metadata.pop("intent", None)
        tags = metadata.pop("tags", [])

        db.add(
            RagChunk(
                id=chunk_id,
                candidate_id=candidate_id,
                chunk_text=chunk_text,
                intent=str(intent) if intent else None,
                tags=tags if isinstance(tags, list) else [],
                metadata_json=metadata,
                created_at=now,
            )
        )
    db.commit()


def list_rag_chunks_from_db(db: Session) -> list[dict[str, Any]]:
    """Return all RAG chunks from the database, reconstructing full dicts."""
    rows = db.query(RagChunk).order_by(RagChunk.created_at).all()
    result: list[dict[str, Any]] = []
    for row in rows:
        chunk = dict(row.metadata_json) if isinstance(row.metadata_json, dict) else {}
        chunk["chunk_id"] = row.id
        chunk["candidate_id"] = row.candidate_id
        chunk["chunk_text"] = row.chunk_text
        chunk["intent"] = row.intent or chunk.get("intent", "general")
        chunk["tags"] = list(row.tags) if row.tags else chunk.get("tags", [])
        chunk["created_at"] = row.created_at.isoformat() if row.created_at else ""
        result.append(chunk)
    return result


def get_rag_chunk_from_db(db: Session, chunk_id: str) -> dict[str, Any] | None:
    """Return a single RAG chunk by ID."""
    row = db.query(RagChunk).filter(RagChunk.id == chunk_id).first()
    if row is None:
        return None
    chunk = dict(row.metadata_json) if isinstance(row.metadata_json, dict) else {}
    chunk["chunk_id"] = row.id
    chunk["candidate_id"] = row.candidate_id
    chunk["chunk_text"] = row.chunk_text
    chunk["intent"] = row.intent or chunk.get("intent", "general")
    chunk["tags"] = list(row.tags) if row.tags else chunk.get("tags", [])
    chunk["created_at"] = row.created_at.isoformat() if row.created_at else ""
    return chunk


def replace_rag_chunks_for_candidates(
    db: Session,
    chunks: list[dict[str, Any]],
) -> None:
    """Alias for save_rag_chunks_to_db — replace all RAG chunks atomically."""
    save_rag_chunks_to_db(db, chunks)


# ──────────────────────────────────────────────────────────────────
#  Retrieval logs  (P1-M19)
# ──────────────────────────────────────────────────────────────────


def save_retrieval_log_to_db(
    db: Session,
    trace: dict[str, Any],
) -> None:
    """Save a retrieval log trace to the database.

    Idempotent: if a log with the same ID already exists, update it.
    """
    now = datetime.now(UTC)
    retrieval_id = trace.get("retrieval_id", "")
    existing = db.query(RetrievalLog).filter(RetrievalLog.id == retrieval_id).first()

    matched_chunk_ids = trace.get("result_chunk_ids", [])
    response_preview = _build_response_preview(trace)
    metadata = dict(trace)

    if existing:
        existing.query = str(trace.get("query", ""))
        existing.matched_chunk_ids = matched_chunk_ids
        existing.response_preview = response_preview
        existing.metadata_json = metadata
        existing.created_at = now
    else:
        db.add(
            RetrievalLog(
                id=retrieval_id,
                query=str(trace.get("query", "")),
                matched_chunk_ids=matched_chunk_ids,
                response_preview=response_preview,
                metadata_json=metadata,
                created_at=now,
            )
        )
    db.commit()


def get_retrieval_log_from_db(
    db: Session, retrieval_id: str
) -> dict[str, Any] | None:
    """Return a single retrieval log trace from DB."""
    row = db.query(RetrievalLog).filter(RetrievalLog.id == retrieval_id).first()
    if row is None:
        return None
    trace = dict(row.metadata_json) if isinstance(row.metadata_json, dict) else {}
    trace["retrieval_id"] = row.id
    trace["query"] = row.query
    trace["result_chunk_ids"] = (
        list(row.matched_chunk_ids) if row.matched_chunk_ids else []
    )
    trace["created_at"] = row.created_at.isoformat() if row.created_at else ""
    return trace


def list_retrieval_logs_from_db(db: Session) -> list[dict[str, Any]]:
    """Return all retrieval logs from DB."""
    rows = db.query(RetrievalLog).order_by(RetrievalLog.created_at.desc()).all()
    result: list[dict[str, Any]] = []
    for row in rows:
        trace = dict(row.metadata_json) if isinstance(row.metadata_json, dict) else {}
        trace["retrieval_id"] = row.id
        trace["query"] = row.query
        trace["result_chunk_ids"] = (
            list(row.matched_chunk_ids) if row.matched_chunk_ids else []
        )
        trace["created_at"] = row.created_at.isoformat() if row.created_at else ""
        result.append(trace)
    return result


def _build_response_preview(trace: dict[str, Any]) -> str:
    """Build a short response preview from a retrieval trace."""
    result_count = trace.get("result_count", 0)
    query_preview = str(trace.get("query", ""))[:100]
    return f"Query: {query_preview} | Results: {result_count}"


# ──────────────────────────────────────────────────────────────────
#  Bad cases  (P1-M19)
# ──────────────────────────────────────────────────────────────────


def save_bad_case_to_db(
    db: Session,
    bad_case: dict[str, Any],
) -> None:
    """Save a bad case record to the database.

    Idempotent: if a bad case with the same ID already exists, update it.
    """
    now = datetime.now(UTC)
    bc_id = bad_case.get("bad_case_id", "")
    existing = db.query(BadCase).filter(BadCase.id == bc_id).first()

    metadata = dict(bad_case)
    linked_chunk_ids = metadata.pop("linked_chunk_ids", [])
    retrieval_result_count = metadata.pop("retrieval_result_count", 0)
    metadata["linked_chunk_ids"] = linked_chunk_ids
    metadata["retrieval_result_count"] = retrieval_result_count

    if existing:
        existing.retrieval_id = bad_case.get("retrieval_id", "")
        existing.user_question = bad_case.get("user_query", "")
        existing.bad_answer = bad_case.get("agent_answer", "")
        existing.expected_answer = bad_case.get("expected_answer")
        existing.status = bad_case.get("status", "open")
        existing.created_candidate_id = bad_case.get("linked_candidate_id")
        existing.metadata_json = metadata
        existing.updated_at = now
    else:
        db.add(
            BadCase(
                id=bc_id,
                retrieval_id=bad_case.get("retrieval_id", ""),
                user_question=bad_case.get("user_query", ""),
                bad_answer=bad_case.get("agent_answer", ""),
                expected_answer=bad_case.get("expected_answer"),
                status=bad_case.get("status", "open"),
                created_candidate_id=bad_case.get("linked_candidate_id"),
                metadata_json=metadata,
                created_at=now,
                updated_at=now,
            )
        )
    db.commit()


def get_bad_case_from_db(
    db: Session, bad_case_id: str
) -> dict[str, Any] | None:
    """Return a single bad case record from DB."""
    row = db.query(BadCase).filter(BadCase.id == bad_case_id).first()
    if row is None:
        return None
    return _db_bad_case_to_dict(row)


def list_bad_cases_from_db(
    db: Session,
    status: str | None = None,
    issue_type: str | None = None,
    severity: str | None = None,
) -> list[dict[str, Any]]:
    """Return all bad case records from DB, with optional filters."""
    query = db.query(BadCase).order_by(BadCase.created_at.desc())
    if status:
        query = query.filter(BadCase.status == status)
    rows = query.all()
    result: list[dict[str, Any]] = []
    for row in rows:
        bc = _db_bad_case_to_dict(row)
        # Apply in-memory filters for fields stored in metadata_json
        if issue_type and bc.get("issue_type") != issue_type:
            continue
        if severity and bc.get("severity") != severity:
            continue
        result.append(bc)
    return result


def update_bad_case_in_db(
    db: Session,
    bad_case_id: str,
    updates: dict[str, Any],
) -> dict[str, Any] | None:
    """Update fields on an existing bad case row."""
    row = db.query(BadCase).filter(BadCase.id == bad_case_id).first()
    if row is None:
        return None

    now = datetime.now(UTC)
    if "status" in updates:
        row.status = updates["status"]
    if "retrieval_id" in updates:
        row.retrieval_id = updates["retrieval_id"]
    if "user_query" in updates:
        row.user_question = updates["user_query"]
    if "agent_answer" in updates:
        row.bad_answer = updates["agent_answer"]
    if "expected_answer" in updates:
        row.expected_answer = updates["expected_answer"]
    if "linked_candidate_id" in updates:
        row.created_candidate_id = updates["linked_candidate_id"]

    # Merge metadata_json
    meta = dict(row.metadata_json) if isinstance(row.metadata_json, dict) else {}
    for key in (
        "review_note",
        "resolution_type",
        "issue_type",
        "severity",
        "linked_chunk_ids",
        "retrieval_result_count",
        "conversation_id",
        "agent_session_id",
        "metadata",
    ):
        if key in updates:
            meta[key] = updates[key]
    row.metadata_json = meta
    row.updated_at = now
    db.commit()
    db.refresh(row)
    return _db_bad_case_to_dict(row)


def create_candidate_from_bad_case_in_db(
    db: Session,
    candidate_data: dict[str, Any],
) -> None:
    """Save a knowledge candidate created from a bad case to the database.

    Prevents duplicate candidates: checks for same question + answer from the
    same bad case source_id to avoid infinite duplicate draft generation.
    """
    now = datetime.now(UTC)
    source_id = candidate_data.get("source_bad_case_id", "")
    question = candidate_data.get("question", "")
    answer = candidate_data.get("answer", "")

    # Check for existing candidate with same bad_case source + question + answer
    existing = (
        db.query(DbKnowledgeCandidate)
        .filter(
            DbKnowledgeCandidate.source_id == source_id,
            DbKnowledgeCandidate.question == question,
            DbKnowledgeCandidate.answer == answer,
        )
        .first()
    )
    if existing is not None:
        # Already exists — update instead of duplicate
        existing.answer = answer
        existing.status = "pending_review"
        meta = dict(existing.metadata_json) if isinstance(existing.metadata_json, dict) else {}
        meta.update(
            {
                "source_bad_case_id": candidate_data.get("source_bad_case_id"),
                "source_retrieval_id": candidate_data.get("source_retrieval_id"),
                "source_chunk_ids": candidate_data.get("source_chunk_ids", []),
                "linked_candidate_id": candidate_data.get("linked_candidate_id"),
                "extraction_method": "bad_case_resolution",
                "reviewer": candidate_data.get("reviewer"),
                "review_note": candidate_data.get("review_note"),
            }
        )
        existing.metadata_json = meta
        existing.updated_at = now
        db.commit()
        return

    candidate_id = candidate_data.get("candidate_id", "")
    db.add(
        DbKnowledgeCandidate(
            id=candidate_id,
            source_type="bad_case",
            source_id=source_id,
            question=question,
            answer=answer,
            intent=candidate_data.get("intent", "general"),
            tags=candidate_data.get("tags", []),
            risk_level=candidate_data.get("risk_level", "medium"),
            quality_score=float(candidate_data.get("quality_score", 0.7)),
            status="pending_review",
            metadata_json={
                "source_bad_case_id": candidate_data.get("source_bad_case_id"),
                "source_retrieval_id": candidate_data.get("source_retrieval_id"),
                "source_chunk_ids": candidate_data.get("source_chunk_ids", []),
                "source_type": "bad_case",
                "knowledge_type": candidate_data.get("knowledge_type", "faq"),
                "extraction_method": "bad_case_resolution",
                "reviewer": candidate_data.get("reviewer"),
                "review_note": candidate_data.get("review_note"),
                "source_batch_id": None,
                "source_conversation_id": candidate_data.get("source_conversation_id"),
                "source_message_ids": [],
                "linked_candidate_id": candidate_data.get("linked_candidate_id"),
            },
            created_at=now,
            updated_at=now,
        )
    )
    db.commit()


# ──────────────────────────────────────────────────────────────────
#  RAG embeddings  (P1-M22)
# ──────────────────────────────────────────────────────────────────

DEFAULT_SYNC_METHOD = "approved_knowledge_vector_sync"


def save_rag_embeddings_to_db(
    db: Session,
    embeddings: list[dict[str, Any]],
) -> int:
    """Delete old approved-knowledge rag_embeddings and insert new ones.

    Idempotent delete-rebuild strategy (Plan A):
    1. Delete all rag_embeddings rows with sync_method = approved_knowledge_vector_sync.
    2. Insert the new set of embeddings.

    Returns the number of embeddings inserted.
    """
    now = datetime.now(UTC)

    # Delete existing approved-knowledge-sync embeddings by metadata_json.sync_method
    # We use a LIKE query on the JSON text to find rows with the sync_method marker.
    # This is simpler and more compatible across SQLite / PostgreSQL than JSON path queries.
    existing_rows = db.query(RagEmbedding).all()
    for row in existing_rows:
        meta = row.metadata_json
        if isinstance(meta, dict) and meta.get("sync_method") == DEFAULT_SYNC_METHOD:
            db.delete(row)
    db.flush()

    inserted = 0
    for emb_data in embeddings:
        emb_id = emb_data.get("id", "")
        candidate_id = emb_data.get("candidate_id", "")
        chunk_text_val = emb_data.get("chunk_text", "")
        embedding_vector = emb_data.get("embedding", [])

        metadata = dict(emb_data.get("metadata_json", {}))
        metadata["sync_method"] = DEFAULT_SYNC_METHOD

        # Determine embedding storage format based on backend
        from app.database import DATABASE_URL
        if DATABASE_URL.startswith("sqlite"):
            # SQLite: store as JSON text
            embedding_value = json.dumps(embedding_vector) if embedding_vector else None
        else:
            # PostgreSQL: store as list for pgvector Vector type
            embedding_value = embedding_vector if embedding_vector else None

        db.add(
            RagEmbedding(
                id=emb_id,
                chunk_id=emb_data.get("chunk_id"),
                candidate_id=candidate_id,
                source_type=emb_data.get("source_type", "sanitized_batch"),
                source_batch_id=emb_data.get("source_batch_id"),
                source_message_id=emb_data.get("source_message_id"),
                modality=emb_data.get("modality", "text"),
                chunk_text=chunk_text_val,
                metadata_json=metadata,
                embedding=embedding_value,
                embedding_provider=emb_data.get("embedding_provider"),
                embedding_model=emb_data.get("embedding_model"),
                embedding_dimension=emb_data.get("embedding_dimension"),
                created_at=now,
                updated_at=now,
            )
        )
        inserted += 1

    db.commit()
    return inserted


def list_rag_embeddings_from_db(db: Session) -> list[dict[str, Any]]:
    """Return all rag_embeddings from the database (without the raw vector for readability)."""
    rows = db.query(RagEmbedding).order_by(RagEmbedding.created_at.desc()).all()
    result: list[dict[str, Any]] = []
    for row in rows:
        result.append(_db_rag_embedding_to_dict(row))
    return result


def count_rag_embeddings_from_db(db: Session) -> int:
    """Return total count of rag_embeddings rows."""
    return db.query(RagEmbedding).count()


def count_rag_embeddings_by_sync_method(db: Session) -> int:
    """Return count of rag_embeddings rows created by approved knowledge vector sync."""
    total = 0
    for row in db.query(RagEmbedding).all():
        meta = row.metadata_json
        if isinstance(meta, dict) and meta.get("sync_method") == DEFAULT_SYNC_METHOD:
            total += 1
    return total


def _db_rag_embedding_to_dict(row: RagEmbedding) -> dict[str, Any]:
    """Convert a RagEmbedding row to a dict (embedding vector truncated for readability)."""
    meta = dict(row.metadata_json) if isinstance(row.metadata_json, dict) else {}
    # Truncate embedding preview — never return the full vector in list views
    emb = row.embedding
    emb_preview: Any = None
    if emb is not None:
        if isinstance(emb, str):
            try:
                parsed = json.loads(emb)
                emb_preview = f"[{len(parsed)} floats]"
            except (json.JSONDecodeError, TypeError):
                emb_preview = "[embedded]"
        elif isinstance(emb, list):
            emb_preview = f"[{len(emb)} floats]"
        else:
            emb_preview = "[embedded]"

    return {
        "id": row.id,
        "chunk_id": row.chunk_id,
        "candidate_id": row.candidate_id,
        "source_type": row.source_type,
        "source_batch_id": row.source_batch_id,
        "source_message_id": row.source_message_id,
        "modality": row.modality,
        "chunk_text": row.chunk_text,
        "metadata_json": meta,
        "embedding_preview": emb_preview,
        "embedding_provider": row.embedding_provider,
        "embedding_model": row.embedding_model,
        "embedding_dimension": row.embedding_dimension,
        "created_at": row.created_at.isoformat() if row.created_at else "",
        "updated_at": row.updated_at.isoformat() if row.updated_at else "",
    }


def _db_bad_case_to_dict(row: BadCase) -> dict[str, Any]:
    """Convert a DB BadCase row to a dictionary matching the API schema."""
    meta = row.metadata_json if isinstance(row.metadata_json, dict) else {}
    return {
        "bad_case_id": row.id,
        "retrieval_id": row.retrieval_id or "",
        "user_query": row.user_question,
        "agent_answer": row.bad_answer or "",
        "issue_type": meta.get("issue_type", "other"),
        "expected_answer": row.expected_answer,
        "severity": meta.get("severity", "medium"),
        "status": row.status,
        "review_note": meta.get("review_note", ""),
        "resolution_type": meta.get("resolution_type"),
        "linked_candidate_id": row.created_candidate_id,
        "linked_chunk_ids": list(meta.get("linked_chunk_ids", [])),
        "retrieval_result_count": int(meta.get("retrieval_result_count", 0)),
        "conversation_id": meta.get("conversation_id"),
        "agent_session_id": meta.get("agent_session_id"),
        "metadata": meta.get("metadata", {}),
        "created_at": row.created_at.isoformat() if row.created_at else "",
        "updated_at": row.updated_at.isoformat() if row.updated_at else "",
    }

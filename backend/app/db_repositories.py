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

"""Database repository layer for raw import and machine cleaning data.

Provides safe, idempotent read/write functions for:
- raw_batches / raw_messages
- sanitized_batches / sanitized_messages

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
    RawBatch,
    RawMessage,
    SanitizedBatch as DbSanitizedBatch,
    SanitizedMessage as DbSanitizedMessage,
)
from app.schemas import (
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

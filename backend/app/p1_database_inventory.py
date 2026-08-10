"""Database-side canonical inventory for P1 reconciliation."""

from __future__ import annotations

from typing import Any, Mapping

from sqlalchemy.orm import Session

from app import db_models
from app.p1_reconciliation_models import Inventory, Record, aggregate_hash, canonical_hash


def _mapping(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _iso(value: object) -> str | None:
    method = getattr(value, "isoformat", None)
    return method() if callable(method) else None


def _add(inventory: Inventory, entity: str, business_id: str, payload: dict[str, Any]) -> None:
    inventory.add(Record(entity, business_id, payload, "database"))


def _manual_associations(
    db: Session,
) -> tuple[
    dict[str, db_models.SanitizedMessage],
    dict[str, db_models.SanitizedMessage],
    dict[str, db_models.ManualCleaningRecord],
]:
    messages = db.query(db_models.SanitizedMessage).all()
    messages_by_id = {row.id: row for row in messages}
    by_message_id: dict[str, list[db_models.SanitizedMessage]] = {}
    for row in messages:
        decoded = row.id.split("__", 2)[-1] if "__" in row.id else row.id
        by_message_id.setdefault(decoded, []).append(row)

    record_message: dict[str, db_models.SanitizedMessage] = {}
    latest_by_message: dict[str, db_models.ManualCleaningRecord] = {}
    records = (
        db.query(db_models.ManualCleaningRecord)
        .order_by(db_models.ManualCleaningRecord.created_at)
        .all()
    )
    for record in records:
        candidates = list(by_message_id.get(record.sanitized_message_id, []))
        direct = messages_by_id.get(record.sanitized_message_id)
        if direct is not None and direct not in candidates:
            candidates.append(direct)
        content_matches = [
            candidate
            for candidate in candidates
            if candidate.content == record.original_content
        ]
        if content_matches:
            candidates = content_matches
        eligible = [
            candidate
            for candidate in candidates
            if candidate.created_at is None
            or record.created_at is None
            or candidate.created_at <= record.created_at
        ]
        if eligible:
            candidates = eligible
        if not candidates:
            continue
        message = max(
            candidates,
            key=lambda candidate: candidate.created_at or record.created_at,
        )
        record_message[record.id] = message
        existing = latest_by_message.get(message.id)
        if (
            existing is None
            or existing.created_at is None
            or (
                record.created_at is not None
                and record.created_at >= existing.created_at
            )
        ):
            latest_by_message[message.id] = record
    return messages_by_id, record_message, latest_by_message


def _raw_inventory(db: Session, inventory: Inventory) -> None:
    for row in db.query(db_models.RawBatch).all():
        stored = _mapping(row.metadata_json)
        metadata = _mapping(stored.get("metadata"))
        raw_payload = _mapping(stored.get("raw_payload"))
        conversations = raw_payload.get("conversations")
        if not isinstance(conversations, list):
            conversations = []
        payload = {
            "batch_id": row.id,
            "source_name": metadata.get("source_name", row.source_name),
            "message_count": metadata.get("message_count", row.message_count),
            "conversation_count": metadata.get("conversation_count", len(conversations)),
            "created_at": metadata.get("created_at", _iso(row.created_at)),
            "status": metadata.get("status", row.status),
            "conversations": conversations,
        }
        _add(inventory, "raw_batch", row.id, payload)

    for row in db.query(db_models.RawMessage).all():
        metadata = _mapping(row.metadata_json)
        prefix = f"{row.batch_id}|"
        stored_suffix = row.id[len(prefix) :] if row.id.startswith(prefix) else row.id
        message_id = str(metadata.get("message_id") or stored_suffix.rsplit("|", 1)[-1])
        conversation_id = str(metadata.get("conversation_id") or "")
        canonical_id = f"{row.batch_id}|{conversation_id}|{message_id}"
        payload = {
            "id": canonical_id,
            "batch_id": row.batch_id,
            "conversation_id": conversation_id,
            "message_id": message_id,
            "role": row.role,
            "content": row.content,
            "timestamp": row.timestamp,
            "created_at": _iso(row.created_at),
        }
        _add(inventory, "raw_message", canonical_id, payload)


def _sanitized_inventory(db: Session, inventory: Inventory) -> None:
    for row in db.query(db_models.SanitizedBatch).all():
        metadata = _mapping(row.metadata_json)
        payload = {
            "batch_id": row.id,
            "source_batch_id": row.raw_batch_id,
            "status": row.status,
            "raw_message_count": metadata.get("raw_message_count", row.message_count),
            "sanitized_message_count": metadata.get("sanitized_message_count", row.message_count),
            "dropped_message_count": metadata.get("dropped_message_count", 0),
            "pii_detected_count": metadata.get("pii_detected_count", 0),
            "exact_duplicate_count": metadata.get("exact_duplicate_count", 0),
            "near_duplicate_count": metadata.get("near_duplicate_count", 0),
            "low_quality_count": metadata.get("low_quality_count", 0),
            "noise_count": metadata.get("noise_count", 0),
            "review_recommended_count": metadata.get("review_recommended_count", row.review_recommended_count),
            "drop_recommended_count": metadata.get("drop_recommended_count", row.drop_recommended_count),
            "average_quality_score": metadata.get("average_quality_score", row.average_quality_score or 0.0),
            "created_at": metadata.get("created_at", _iso(row.created_at)),
        }
        _add(inventory, "sanitized_batch", row.id, payload)

    for row in db.query(db_models.SanitizedMessage).all():
        parts = row.id.split("__", 2)
        conversation_id = parts[1] if len(parts) == 3 else ""
        message_id = parts[2] if len(parts) == 3 else row.id
        payload = {
            "id": row.id,
            "batch_id": row.batch_id,
            "source_batch_id": row.batch_id,
            "conversation_id": conversation_id,
            "message_id": message_id,
            "source_message_id": row.raw_message_id or message_id,
            "role": row.role,
            "content": row.content,
            "pii_detected": bool(row.pii_entities),
            "pii_types": list(row.pii_entities or []),
            "cleaning_issues": list(row.cleaning_issues or []),
            "risk_flags": list(row.risk_flags or []),
            "quality_score": float(row.quality_score),
            "quality_level": row.quality_level,
            "suggested_action": row.suggested_action,
            "created_at": _iso(row.created_at),
        }
        _add(inventory, "sanitized_message", row.id, payload)


def _candidate_payload(row: db_models.KnowledgeCandidate) -> dict[str, Any]:
    metadata = _mapping(row.metadata_json)
    return {
        "candidate_id": row.id,
        "source_type": row.source_type,
        "source_batch_id": metadata.get("source_batch_id"),
        "source_conversation_id": metadata.get("source_conversation_id"),
        "source_message_ids": list(metadata.get("source_message_ids") or []),
        "source_bad_case_id": metadata.get("source_bad_case_id"),
        "source_retrieval_id": metadata.get("source_retrieval_id"),
        "source_chunk_ids": list(metadata.get("source_chunk_ids") or []),
        "source_legacy_id": metadata.get("source_legacy_id"),
        "source_import_id": metadata.get("source_import_id"),
        "linked_candidate_id": metadata.get("linked_candidate_id"),
        "knowledge_type": metadata.get("knowledge_type", "faq"),
        "question": row.question,
        "answer": row.answer,
        "intent": row.intent or "general",
        "tags": list(row.tags or []),
        "risk_level": row.risk_level,
        "review_status": row.status,
        "quality_score": float(row.quality_score),
        "extraction_method": metadata.get("extraction_method", "rule_based_mock"),
        "migration_mode": metadata.get("migration_mode"),
        "source_note": metadata.get("source_note"),
        "cleaning_issues": list(metadata.get("cleaning_issues") or []),
        "risk_flags": list(metadata.get("risk_flags") or []),
        "manual_cleaning_status": metadata.get("manual_cleaning_status"),
        "manual_action": metadata.get("manual_action"),
        "created_at": metadata.get("created_at", _iso(row.created_at)),
        "reviewer": metadata.get("reviewer"),
        "review_note": metadata.get("review_note"),
        "reviewed_at": metadata.get("reviewed_at"),
        "updated_at": metadata.get("updated_at"),
    }


def _governance_inventory(db: Session, inventory: Inventory) -> None:
    sanitized_rows, record_message, _latest_manual = _manual_associations(db)
    for row in db.query(db_models.ManualCleaningRecord).all():
        message = record_message.get(row.id) or sanitized_rows.get(row.sanitized_message_id)
        parts = message.id.split("__", 2) if message is not None else []
        payload = {
            "record_id": row.id,
            "batch_id": message.batch_id if message is not None else None,
            "message_id": row.sanitized_message_id,
            "source_message_id": message.raw_message_id if message is not None else row.sanitized_message_id,
            "conversation_id": parts[1] if len(parts) == 3 else None,
            "original_sanitized_content": row.original_content,
            "manual_cleaned_content": row.cleaned_content,
            "manual_action": row.action,
            "cleaner": row.cleaner,
            "cleaning_note": row.note or "",
            "created_at": _iso(row.created_at),
        }
        _add(inventory, "manual_cleaning_record", row.id, payload)

    for row in db.query(db_models.KnowledgeCandidate).all():
        _add(inventory, "knowledge_candidate", row.id, _candidate_payload(row))

    for row in db.query(db_models.ReviewRecord).all():
        payload = {
            "review_id": row.id,
            "candidate_id": row.candidate_id,
            "review_status": row.action,
            "reviewer": row.reviewer,
            "review_note": row.note or "",
            "reviewed_at": _iso(row.created_at),
        }
        _add(inventory, "review_record", row.id, payload)


def _rag_inventory(db: Session, inventory: Inventory) -> None:
    for row in db.query(db_models.RagChunk).all():
        payload = _mapping(row.metadata_json)
        payload.update(
            {
                "chunk_id": row.id,
                "candidate_id": row.candidate_id,
                "chunk_text": row.chunk_text,
                "intent": row.intent or payload.get("intent", "general"),
                "tags": list(row.tags or payload.get("tags") or []),
                "created_at": payload.get("created_at", _iso(row.created_at)),
            }
        )
        _add(inventory, "rag_chunk", row.id, payload)

    for row in db.query(db_models.RagEmbedding).all():
        metadata = _mapping(row.metadata_json)
        payload = {
            "id": row.id,
            "chunk_id": row.chunk_id,
            "candidate_id": row.candidate_id,
            "source_type": row.source_type,
            "source_batch_id": row.source_batch_id,
            "source_message_id": row.source_message_id,
            "modality": row.modality,
            "chunk_text_hash": canonical_hash(row.chunk_text),
            "metadata_hash": canonical_hash(metadata),
            "embedding_provider": row.embedding_provider,
            "embedding_model": row.embedding_model,
            "embedding_dimension": row.embedding_dimension,
            "created_at": _iso(row.created_at),
            "updated_at": _iso(row.updated_at),
        }
        _add(inventory, "rag_embedding", row.id, payload)

    for row in db.query(db_models.RetrievalLog).all():
        payload = _mapping(row.metadata_json)
        payload.update(
            {
                "retrieval_id": row.id,
                "query": row.query,
                "result_chunk_ids": list(row.matched_chunk_ids or []),
                "created_at": payload.get("created_at", _iso(row.created_at)),
            }
        )
        _add(inventory, "retrieval_log", row.id, payload)

    for row in db.query(db_models.BadCase).all():
        payload = _mapping(row.metadata_json)
        payload.update(
            {
                "bad_case_id": row.id,
                "retrieval_id": row.retrieval_id or "",
                "user_query": row.user_question,
                "agent_answer": row.bad_answer or "",
                "expected_answer": row.expected_answer,
                "status": row.status,
                "linked_candidate_id": row.created_candidate_id,
                "created_at": payload.get("created_at", _iso(row.created_at)),
                "updated_at": payload.get("updated_at", _iso(row.updated_at)),
            }
        )
        _add(inventory, "bad_case", row.id, payload)


def load_database_inventory(db: Session) -> Inventory:
    inventory = Inventory()
    _raw_inventory(db, inventory)
    _sanitized_inventory(db, inventory)
    _governance_inventory(db, inventory)
    _rag_inventory(db, inventory)
    entries = [
        (f"{entity}/{business_id}", canonical_hash(record.payload))
        for entity, records in inventory.records.items()
        for business_id, record in records.items()
    ]
    inventory.aggregate_hash = aggregate_hash(entries)
    return inventory


__all__ = ["load_database_inventory"]

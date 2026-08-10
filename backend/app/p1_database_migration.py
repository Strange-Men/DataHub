"""Insert-only migration primitives for legacy P1 JSON records."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Callable, Mapping

from sqlalchemy.orm import Session

from app import db_models
from app.p1_reconciliation_models import (
    Classification,
    Inventory,
    MIGRATABLE_ENTITIES,
    ReconciliationResult,
    canonical_hash,
    short_id_hash,
)


class MigrationBlocked(RuntimeError):
    pass


@dataclass(frozen=True)
class PlannedInsert:
    entity: str
    business_id: str
    payload: Mapping[str, Any]

    def safe_dict(self) -> dict[str, str]:
        return {
            "entity": self.entity,
            "id_hash": short_id_hash(self.business_id),
            "canonical_hash": canonical_hash(self.payload),
        }


@dataclass(frozen=True)
class MigrationPlan:
    inserts: tuple[PlannedInsert, ...]
    reconciliation_counts: Mapping[str, int]

    def safe_report(self) -> dict[str, object]:
        by_entity: dict[str, int] = {}
        for item in self.inserts:
            by_entity[item.entity] = by_entity.get(item.entity, 0) + 1
        return {
            "schema_version": 1,
            "mode": "plan",
            "insert_count": len(self.inserts),
            "insert_counts_by_entity": dict(sorted(by_entity.items())),
            "reconciliation_counts": dict(self.reconciliation_counts),
            "inserts": [item.safe_dict() for item in self.inserts],
        }


_INSERT_ORDER = {
    "raw_batch": 10,
    "raw_message": 20,
    "sanitized_batch": 30,
    "sanitized_message": 40,
    "manual_cleaning_record": 50,
    "knowledge_candidate": 60,
    "review_record": 70,
    "rag_chunk": 80,
    "retrieval_log": 90,
    "bad_case": 100,
}


def build_migration_plan(
    legacy: Inventory,
    reconciliation: ReconciliationResult,
) -> MigrationPlan:
    blockers = reconciliation.blockers
    if any(blockers.values()):
        raise MigrationBlocked(
            "Migration blocked by reconciliation: "
            + ", ".join(f"{key}={value}" for key, value in blockers.items())
        )
    inserts: list[PlannedInsert] = []
    for item in reconciliation.items:
        if item.classification is not Classification.JSON_ONLY:
            continue
        if item.entity not in MIGRATABLE_ENTITIES:
            raise MigrationBlocked(f"No lossless insert mapping for {item.entity}")
        record = legacy.records.get(item.entity, {}).get(item.business_id)
        if record is None:
            raise MigrationBlocked(f"Missing legacy payload for {item.entity}")
        inserts.append(PlannedInsert(item.entity, item.business_id, record.payload))
    inserts.sort(key=lambda item: (_INSERT_ORDER[item.entity], item.business_id))
    return MigrationPlan(tuple(inserts), reconciliation.counts)


def _datetime(value: object) -> datetime:
    if not isinstance(value, str) or not value:
        raise MigrationBlocked("Required timestamp is missing")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise MigrationBlocked("Required timestamp is invalid") from exc
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(UTC).replace(tzinfo=None)
    return parsed


def _metadata_without(payload: Mapping[str, Any], *keys: str) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if key not in keys}


def _source_id(payload: Mapping[str, Any]) -> str | None:
    source_type = str(payload.get("source_type") or "")
    if source_type == "bad_case":
        return str(payload.get("source_bad_case_id") or "") or None
    if source_type == "legacy_rag":
        return str(payload.get("source_import_id") or "") or None
    return str(payload.get("source_batch_id") or "") or None


def _model_for_insert(item: PlannedInsert) -> object:
    payload = item.payload
    created_at = _datetime(payload.get("created_at") or payload.get("reviewed_at"))
    if item.entity == "raw_batch":
        conversations = payload.get("conversations")
        if not isinstance(conversations, list):
            raise MigrationBlocked("Raw batch conversations are not losslessly mappable")
        metadata = {
            "metadata": _metadata_without(payload, "conversations"),
            "raw_payload": {
                "source_name": payload.get("source_name"),
                "conversations": conversations,
            },
        }
        return db_models.RawBatch(
            id=item.business_id,
            source_name=str(payload.get("source_name") or ""),
            source_type="chat_logs",
            status=str(payload.get("status") or "raw_imported"),
            message_count=int(payload.get("message_count") or 0),
            metadata_json=metadata,
            created_at=created_at,
            updated_at=created_at,
        )
    if item.entity == "raw_message":
        return db_models.RawMessage(
            id=item.business_id,
            batch_id=str(payload.get("batch_id") or ""),
            role=str(payload.get("role") or "unknown"),
            content=str(payload.get("content") or ""),
            timestamp=str(payload.get("timestamp") or ""),
            metadata_json={
                "conversation_id": payload.get("conversation_id"),
                "message_id": payload.get("message_id"),
            },
            created_at=created_at,
        )
    if item.entity == "sanitized_batch":
        metadata = dict(payload)
        return db_models.SanitizedBatch(
            id=item.business_id,
            raw_batch_id=str(payload.get("source_batch_id") or ""),
            status=str(payload.get("status") or "sanitized"),
            message_count=int(payload.get("sanitized_message_count") or 0),
            high_quality_count=int(payload.get("high_quality_count") or 0),
            review_recommended_count=int(payload.get("review_recommended_count") or 0),
            drop_recommended_count=int(payload.get("drop_recommended_count") or 0),
            average_quality_score=float(payload.get("average_quality_score") or 0.0),
            metadata_json=metadata,
            created_at=created_at,
            updated_at=created_at,
        )
    if item.entity == "sanitized_message":
        if payload.get("cleaning_notes") not in (None, []):
            raise MigrationBlocked("Sanitized message cleaning_notes have no lossless database column")
        return db_models.SanitizedMessage(
            id=item.business_id,
            batch_id=str(payload.get("batch_id") or ""),
            raw_message_id=str(payload.get("source_message_id") or "") or None,
            role=str(payload.get("role") or "system"),
            content=str(payload.get("content") or ""),
            sanitized_content=str(payload.get("content") or ""),
            quality_score=float(payload.get("quality_score") or 0.0),
            quality_level=str(payload.get("quality_level") or "high"),
            suggested_action=str(payload.get("suggested_action") or "keep"),
            cleaning_issues=list(payload.get("cleaning_issues") or []),
            risk_flags=list(payload.get("risk_flags") or []),
            pii_entities=list(payload.get("pii_types") or []),
            created_at=created_at,
            updated_at=created_at,
        )
    if item.entity == "manual_cleaning_record":
        return db_models.ManualCleaningRecord(
            id=item.business_id,
            sanitized_message_id=str(payload.get("message_id") or ""),
            cleaner=str(payload.get("cleaner") or ""),
            action=str(payload.get("manual_action") or ""),
            original_content=str(payload.get("original_sanitized_content") or ""),
            cleaned_content=(
                str(payload.get("manual_cleaned_content"))
                if payload.get("manual_cleaned_content") is not None
                else None
            ),
            note=str(payload.get("cleaning_note") or ""),
            created_at=created_at,
        )
    if item.entity == "knowledge_candidate":
        metadata = _metadata_without(
            payload,
            "candidate_id",
            "source_type",
            "question",
            "answer",
            "intent",
            "tags",
            "risk_level",
            "quality_score",
            "review_status",
        )
        return db_models.KnowledgeCandidate(
            id=item.business_id,
            source_type=str(payload.get("source_type") or "sanitized_batch"),
            source_id=_source_id(payload),
            question=str(payload.get("question") or ""),
            answer=str(payload.get("answer") or ""),
            intent=str(payload.get("intent") or "general"),
            tags=list(payload.get("tags") or []),
            risk_level=str(payload.get("risk_level") or "medium"),
            quality_score=float(payload.get("quality_score") or 0.0),
            status=str(payload.get("review_status") or "pending_review"),
            metadata_json=metadata,
            created_at=created_at,
            updated_at=_datetime(payload.get("updated_at")) if payload.get("updated_at") else created_at,
        )
    if item.entity == "review_record":
        return db_models.ReviewRecord(
            id=item.business_id,
            candidate_id=str(payload.get("candidate_id") or ""),
            reviewer=str(payload.get("reviewer") or ""),
            action=str(payload.get("review_status") or ""),
            note=str(payload.get("review_note") or ""),
            snapshot_json=None,
            created_at=created_at,
        )
    if item.entity == "rag_chunk":
        metadata = dict(payload)
        return db_models.RagChunk(
            id=item.business_id,
            candidate_id=str(payload.get("candidate_id") or ""),
            chunk_text=str(payload.get("chunk_text") or ""),
            intent=str(payload.get("intent") or "general"),
            tags=list(payload.get("tags") or []),
            metadata_json=metadata,
            created_at=created_at,
        )
    if item.entity == "retrieval_log":
        return db_models.RetrievalLog(
            id=item.business_id,
            query=str(payload.get("query") or ""),
            matched_chunk_ids=list(payload.get("result_chunk_ids") or []),
            response_preview=None,
            metadata_json=dict(payload),
            created_at=created_at,
        )
    if item.entity == "bad_case":
        updated_at = _datetime(payload.get("updated_at")) if payload.get("updated_at") else created_at
        return db_models.BadCase(
            id=item.business_id,
            retrieval_id=str(payload.get("retrieval_id") or "") or None,
            user_question=str(payload.get("user_query") or ""),
            bad_answer=str(payload.get("agent_answer") or "") or None,
            expected_answer=(
                str(payload.get("expected_answer"))
                if payload.get("expected_answer") is not None
                else None
            ),
            status=str(payload.get("status") or "open"),
            created_candidate_id=(
                str(payload.get("linked_candidate_id"))
                if payload.get("linked_candidate_id") is not None
                else None
            ),
            metadata_json=dict(payload),
            created_at=created_at,
            updated_at=updated_at,
        )
    raise MigrationBlocked(f"No insert model for {item.entity}")


_MODEL_BY_ENTITY = {
    "raw_batch": db_models.RawBatch,
    "raw_message": db_models.RawMessage,
    "sanitized_batch": db_models.SanitizedBatch,
    "sanitized_message": db_models.SanitizedMessage,
    "manual_cleaning_record": db_models.ManualCleaningRecord,
    "knowledge_candidate": db_models.KnowledgeCandidate,
    "review_record": db_models.ReviewRecord,
    "rag_chunk": db_models.RagChunk,
    "retrieval_log": db_models.RetrievalLog,
    "bad_case": db_models.BadCase,
}


def apply_migration_plan(
    db: Session,
    plan: MigrationPlan,
    *,
    before_insert: Callable[[PlannedInsert], None] | None = None,
) -> int:
    """Apply one insert-only transaction; any error rolls back every insert."""
    inserted = 0
    with db.begin():
        for item in plan.inserts:
            if before_insert is not None:
                before_insert(item)
            model = _MODEL_BY_ENTITY[item.entity]
            if db.get(model, item.business_id) is not None:
                raise MigrationBlocked(
                    f"Concurrent row appeared for {item.entity}; reconciliation must be rerun"
                )
            db.add(_model_for_insert(item))
            inserted += 1
        db.flush()
    return inserted


__all__ = [
    "MigrationBlocked",
    "MigrationPlan",
    "PlannedInsert",
    "apply_migration_plan",
    "build_migration_plan",
]

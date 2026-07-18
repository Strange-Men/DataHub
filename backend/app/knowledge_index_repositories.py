"""Persistence for the P2-M6 index control plane and text chunks."""

from __future__ import annotations

import math
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db_models import KnowledgeAsset, P2KnowledgeChunk, P2KnowledgeIndexEntry
from app.knowledge_asset_repositories import (
    KnowledgeSourceTraceError,
    get_knowledge_asset,
    get_knowledge_assets_by_ids,
)
from app.knowledge_index_schemas import (
    CreateKnowledgeIndexResult,
    KnowledgeChunkRecord,
    KnowledgeIndexEntryRecord,
    KnowledgeIndexList,
    KnowledgeIndexPagination,
    index_source_trace,
)


class KnowledgeIndexRowNotFound(RuntimeError):
    pass


class KnowledgeIndexTransitionError(RuntimeError):
    def __init__(self, current_status: str, target_status: str) -> None:
        super().__init__(f"Illegal index transition: {current_status} -> {target_status}.")
        self.current_status = current_status
        self.target_status = target_status


class KnowledgeIndexSourceTraceError(RuntimeError):
    pass


_SYNC_STATE = {
    "pending": "pending",
    "building": "building",
    "ready": "ready",
    "serving": "ready",
    "failed": "failed",
    "archived": "archived",
}

_ALLOWED_TRANSITIONS = {
    "pending": {"building", "archived"},
    "building": {"ready", "failed", "archived"},
    "ready": {"serving", "archived"},
    "serving": {"archived"},
    "failed": {"building", "archived"},
    "archived": set(),
}


def _iso(value: datetime | None) -> str:
    return value.isoformat() if value is not None else ""


def _chunk_record(row: P2KnowledgeChunk) -> KnowledgeChunkRecord:
    return KnowledgeChunkRecord(
        id=row.id,
        index_entry_id=row.index_entry_id,
        knowledge_asset_id=row.knowledge_asset_id,
        chunk_text=row.chunk_text,
        chunk_hash=row.chunk_hash,
        chunk_order=int(row.chunk_order),
        metadata_json=row.metadata_json if isinstance(row.metadata_json, dict) else {},
        created_at=_iso(row.created_at),
    )


def _entry_record(
    db: Session,
    row: P2KnowledgeIndexEntry,
) -> KnowledgeIndexEntryRecord:
    try:
        knowledge_asset = get_knowledge_asset(db, row.knowledge_asset_id)
    except KnowledgeSourceTraceError as exc:
        raise KnowledgeIndexSourceTraceError(str(exc)) from exc
    if knowledge_asset is None:
        raise KnowledgeIndexSourceTraceError("Index source Knowledge Asset is missing.")
    chunks = (
        db.query(P2KnowledgeChunk)
        .filter(P2KnowledgeChunk.index_entry_id == row.id)
        .order_by(P2KnowledgeChunk.chunk_order.asc(), P2KnowledgeChunk.id.asc())
        .all()
    )
    return KnowledgeIndexEntryRecord(
        id=row.id,
        knowledge_asset_id=row.knowledge_asset_id,
        status=row.status,
        generation=int(row.generation),
        fingerprint=row.fingerprint,
        sync_state=row.sync_state,
        error_message=row.error_message,
        created_at=_iso(row.created_at),
        updated_at=_iso(row.updated_at),
        chunks=[_chunk_record(chunk) for chunk in chunks],
        source_trace=index_source_trace(
            index_entry_id=row.id,
            knowledge_asset_version=knowledge_asset.version,
            source=knowledge_asset.source_trace,
        ),
    )


def get_index_entries_by_ids(
    db: Session,
    index_entry_ids: list[str],
) -> dict[str, KnowledgeIndexEntryRecord]:
    """Bulk-load governed Index Entries without per-row Source Trace queries."""
    if not index_entry_ids:
        return {}
    rows = (
        db.query(P2KnowledgeIndexEntry)
        .filter(P2KnowledgeIndexEntry.id.in_(index_entry_ids))
        .all()
    )
    chunks = (
        db.query(P2KnowledgeChunk)
        .filter(P2KnowledgeChunk.index_entry_id.in_(index_entry_ids))
        .order_by(
            P2KnowledgeChunk.index_entry_id.asc(),
            P2KnowledgeChunk.chunk_order.asc(),
            P2KnowledgeChunk.id.asc(),
        )
        .all()
    )
    chunks_by_entry: dict[str, list[P2KnowledgeChunk]] = {}
    for chunk in chunks:
        chunks_by_entry.setdefault(chunk.index_entry_id, []).append(chunk)
    knowledge_assets = get_knowledge_assets_by_ids(
        db,
        list({row.knowledge_asset_id for row in rows}),
    )
    records: dict[str, KnowledgeIndexEntryRecord] = {}
    for row in rows:
        knowledge_asset = knowledge_assets.get(row.knowledge_asset_id)
        if knowledge_asset is None:
            raise KnowledgeIndexSourceTraceError(
                "Index source Knowledge Asset is missing."
            )
        records[row.id] = KnowledgeIndexEntryRecord(
            id=row.id,
            knowledge_asset_id=row.knowledge_asset_id,
            status=row.status,
            generation=int(row.generation),
            fingerprint=row.fingerprint,
            sync_state=row.sync_state,
            error_message=row.error_message,
            created_at=_iso(row.created_at),
            updated_at=_iso(row.updated_at),
            chunks=[
                _chunk_record(chunk)
                for chunk in chunks_by_entry.get(row.id, [])
            ],
            source_trace=index_source_trace(
                index_entry_id=row.id,
                knowledge_asset_version=knowledge_asset.version,
                source=knowledge_asset.source_trace,
            ),
        )
    return records


def get_index_entry(
    db: Session,
    index_entry_id: str,
) -> KnowledgeIndexEntryRecord | None:
    row = (
        db.query(P2KnowledgeIndexEntry)
        .filter(P2KnowledgeIndexEntry.id == index_entry_id)
        .first()
    )
    return _entry_record(db, row) if row is not None else None


def get_index_entry_by_knowledge_asset(
    db: Session,
    knowledge_asset_id: str,
) -> KnowledgeIndexEntryRecord | None:
    row = (
        db.query(P2KnowledgeIndexEntry)
        .filter(P2KnowledgeIndexEntry.knowledge_asset_id == knowledge_asset_id)
        .first()
    )
    return _entry_record(db, row) if row is not None else None


def create_pending_index_entry(
    db: Session,
    *,
    knowledge_asset_id: str,
    generation: int,
    fingerprint: str,
) -> CreateKnowledgeIndexResult:
    existing = get_index_entry_by_knowledge_asset(db, knowledge_asset_id)
    if existing is not None:
        return CreateKnowledgeIndexResult(index_entry=existing, created=False)
    now = datetime.now(UTC)
    row = P2KnowledgeIndexEntry(
        id=f"p2_index_{uuid4().hex[:20]}",
        knowledge_asset_id=knowledge_asset_id,
        status="pending",
        generation=generation,
        fingerprint=fingerprint,
        sync_state="pending",
        error_message=None,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raced = get_index_entry_by_knowledge_asset(db, knowledge_asset_id)
        if raced is not None:
            return CreateKnowledgeIndexResult(index_entry=raced, created=False)
        raise
    db.refresh(row)
    return CreateKnowledgeIndexResult(index_entry=_entry_record(db, row), created=True)


def transition_index_entry(
    db: Session,
    index_entry_id: str,
    target_status: str,
    *,
    error_message: str | None = None,
) -> KnowledgeIndexEntryRecord:
    row = (
        db.query(P2KnowledgeIndexEntry)
        .filter(P2KnowledgeIndexEntry.id == index_entry_id)
        .with_for_update()
        .first()
    )
    if row is None:
        raise KnowledgeIndexRowNotFound(index_entry_id)
    if row.status == target_status:
        return _entry_record(db, row)
    if target_status not in _ALLOWED_TRANSITIONS.get(row.status, set()):
        raise KnowledgeIndexTransitionError(row.status, target_status)
    row.status = target_status
    row.sync_state = _SYNC_STATE[target_status]
    row.error_message = error_message if target_status == "failed" else None
    row.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(row)
    return _entry_record(db, row)


def save_projected_chunk(
    db: Session,
    *,
    index_entry_id: str,
    knowledge_asset_id: str,
    chunk_id: str,
    chunk_text: str,
    chunk_hash: str,
    chunk_order: int,
    metadata_json: dict[str, object],
) -> KnowledgeIndexEntryRecord:
    row = (
        db.query(P2KnowledgeIndexEntry)
        .filter(P2KnowledgeIndexEntry.id == index_entry_id)
        .with_for_update()
        .first()
    )
    if row is None:
        raise KnowledgeIndexRowNotFound(index_entry_id)
    if row.status != "building":
        raise KnowledgeIndexTransitionError(row.status, "ready")
    existing = (
        db.query(P2KnowledgeChunk)
        .filter(
            P2KnowledgeChunk.index_entry_id == index_entry_id,
            P2KnowledgeChunk.chunk_order == chunk_order,
        )
        .first()
    )
    if existing is None:
        db.add(
            P2KnowledgeChunk(
                id=chunk_id,
                index_entry_id=index_entry_id,
                knowledge_asset_id=knowledge_asset_id,
                chunk_text=chunk_text,
                chunk_hash=chunk_hash,
                chunk_order=chunk_order,
                metadata_json=metadata_json,
                created_at=datetime.now(UTC),
            )
        )
    row.status = "ready"
    row.sync_state = "ready"
    row.error_message = None
    row.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(row)
    return _entry_record(db, row)


def archive_index_entry(
    db: Session,
    index_entry_id: str,
) -> KnowledgeIndexEntryRecord:
    row = (
        db.query(P2KnowledgeIndexEntry)
        .filter(P2KnowledgeIndexEntry.id == index_entry_id)
        .with_for_update()
        .first()
    )
    if row is None:
        raise KnowledgeIndexRowNotFound(index_entry_id)
    if row.status != "archived":
        row.status = "archived"
        row.sync_state = "archived"
        row.error_message = None
        row.updated_at = datetime.now(UTC)
        db.commit()
        db.refresh(row)
    return _entry_record(db, row)


def list_index_entries(
    db: Session,
    *,
    page: int,
    page_size: int,
    status: str | None = None,
    asset_id: str | None = None,
) -> KnowledgeIndexList:
    query = db.query(P2KnowledgeIndexEntry)
    if status:
        query = query.filter(P2KnowledgeIndexEntry.status == status)
    if asset_id:
        query = query.join(
            KnowledgeAsset,
            KnowledgeAsset.id == P2KnowledgeIndexEntry.knowledge_asset_id,
        ).filter(KnowledgeAsset.asset_id == asset_id)
    total = query.count()
    rows = (
        query.order_by(
            P2KnowledgeIndexEntry.created_at.desc(),
            P2KnowledgeIndexEntry.id.desc(),
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return KnowledgeIndexList(
        index_entries=[_entry_record(db, row) for row in rows],
        pagination=KnowledgeIndexPagination(
            page=page,
            page_size=page_size,
            total=total,
            total_pages=math.ceil(total / page_size) if total else 0,
        ),
    )

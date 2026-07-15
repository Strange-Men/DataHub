"""Persistence for immutable, profile-versioned P2 text embeddings."""

from __future__ import annotations

import json
import math
from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db_models import (
    P2KnowledgeEmbedding,
    P2KnowledgeIndexEntry,
    _is_postgresql,
)
from app.knowledge_embedding_schemas import (
    P2KnowledgeEmbeddingList,
    P2KnowledgeEmbeddingPagination,
    P2KnowledgeEmbeddingRecord,
)
from app.knowledge_index_repositories import (
    KnowledgeIndexSourceTraceError,
    get_index_entry,
)


class P2EmbeddingIndexNotFound(RuntimeError):
    pass


class P2EmbeddingPersistenceError(RuntimeError):
    pass


class P2EmbeddingActivationError(RuntimeError):
    def __init__(self, reason: str, status: str | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.status = status


def _iso(value: datetime | None) -> str:
    return value.isoformat() if value is not None else ""


def _record(db: Session, row: P2KnowledgeEmbedding) -> P2KnowledgeEmbeddingRecord:
    entry = get_index_entry(db, row.index_entry_id)
    if entry is None:
        raise KnowledgeIndexSourceTraceError("Embedding source Index Entry is missing.")
    if entry.knowledge_asset_id != row.knowledge_asset_id:
        raise KnowledgeIndexSourceTraceError(
            "Embedding source Knowledge Asset does not match its Index Entry."
        )
    return P2KnowledgeEmbeddingRecord(
        id=row.id,
        index_entry_id=row.index_entry_id,
        chunk_id=row.chunk_id,
        knowledge_asset_id=row.knowledge_asset_id,
        chunk_text=row.chunk_text,
        provider=row.provider,
        model=row.model,
        dimension=int(row.dimension),
        embedding_profile=row.embedding_profile,
        fingerprint=row.fingerprint,
        created_at=_iso(row.created_at),
        source_trace=entry.source_trace,
    )


def get_embeddings_for_fingerprints(
    db: Session,
    *,
    index_entry_id: str,
    fingerprints: list[str],
) -> list[P2KnowledgeEmbeddingRecord]:
    if not fingerprints:
        return []
    rows = (
        db.query(P2KnowledgeEmbedding)
        .filter(
            P2KnowledgeEmbedding.index_entry_id == index_entry_id,
            P2KnowledgeEmbedding.fingerprint.in_(fingerprints),
        )
        .order_by(P2KnowledgeEmbedding.chunk_id.asc())
        .all()
    )
    return [_record(db, row) for row in rows]


def get_embedding_rows_for_index(
    db: Session,
    *,
    index_entry_id: str,
    embedding_profile: str | None = None,
) -> list[P2KnowledgeEmbedding]:
    query = db.query(P2KnowledgeEmbedding).filter(
        P2KnowledgeEmbedding.index_entry_id == index_entry_id
    )
    if embedding_profile is not None:
        query = query.filter(
            P2KnowledgeEmbedding.embedding_profile == embedding_profile
        )
    return query.order_by(P2KnowledgeEmbedding.chunk_id.asc()).all()


def save_embedding_build(
    db: Session,
    *,
    index_entry_id: str,
    rows: list[dict[str, object]],
) -> tuple[list[P2KnowledgeEmbeddingRecord], int]:
    """Persist one complete build while keeping the Index Entry at ready."""
    entry = (
        db.query(P2KnowledgeIndexEntry)
        .filter(P2KnowledgeIndexEntry.id == index_entry_id)
        .with_for_update()
        .first()
    )
    if entry is None:
        raise P2EmbeddingIndexNotFound(index_entry_id)
    if entry.status != "ready":
        raise P2EmbeddingPersistenceError(
            f"Index Entry must remain ready during embedding persistence; got {entry.status}."
        )

    created = 0
    fingerprints = [str(item["fingerprint"]) for item in rows]
    existing = {
        row.fingerprint
        for row in db.query(P2KnowledgeEmbedding)
        .filter(P2KnowledgeEmbedding.fingerprint.in_(fingerprints))
        .all()
    }
    now = datetime.now(UTC)
    for item in rows:
        fingerprint = str(item["fingerprint"])
        if fingerprint in existing:
            continue
        vector = item["embedding"]
        stored_vector: object = vector
        if not _is_postgresql():
            stored_vector = json.dumps(vector, separators=(",", ":"))
        db.add(
            P2KnowledgeEmbedding(
                id=item["id"],
                index_entry_id=index_entry_id,
                chunk_id=item["chunk_id"],
                knowledge_asset_id=item["knowledge_asset_id"],
                chunk_text=item["chunk_text"],
                embedding=stored_vector,
                provider=item["provider"],
                model=item["model"],
                dimension=item["dimension"],
                embedding_profile=item["embedding_profile"],
                fingerprint=fingerprint,
                metadata_json=item["metadata_json"],
                created_at=now,
            )
        )
        created += 1

    # P2-M8.1: embedding readiness and retrieval serving are separate gates.
    # A successful build remains ready until the explicit /serve operation.
    entry.status = "ready"
    entry.sync_state = "ready"
    entry.error_message = None
    entry.updated_at = now
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        exact = get_embeddings_for_fingerprints(
            db,
            index_entry_id=index_entry_id,
            fingerprints=fingerprints,
        )
        if len(exact) == len(fingerprints):
            raced_entry = (
                db.query(P2KnowledgeIndexEntry)
                .filter(P2KnowledgeIndexEntry.id == index_entry_id)
                .with_for_update()
                .first()
            )
            if raced_entry is not None and raced_entry.status == "ready":
                raced_entry.status = "ready"
                raced_entry.sync_state = "ready"
                raced_entry.error_message = None
                raced_entry.updated_at = datetime.now(UTC)
                db.commit()
            return exact, 0
        raise
    records = get_embeddings_for_fingerprints(
        db,
        index_entry_id=index_entry_id,
        fingerprints=fingerprints,
    )
    return records, created


def activate_index_serving(
    db: Session,
    *,
    index_entry_id: str,
    embedding_profile: str,
    provider: str,
    model: str,
    dimension: int,
    expected_fingerprints: set[str],
) -> tuple[object, bool]:
    """Atomically activate a previously validated ready embedding build."""
    entry = (
        db.query(P2KnowledgeIndexEntry)
        .filter(P2KnowledgeIndexEntry.id == index_entry_id)
        .with_for_update()
        .first()
    )
    if entry is None:
        raise P2EmbeddingIndexNotFound(index_entry_id)
    if entry.status == "serving":
        return get_index_entry(db, index_entry_id), False
    if entry.status != "ready":
        raise P2EmbeddingActivationError(
            "Index Entry is not ready for serving.", status=entry.status
        )
    if entry.sync_state != "ready" or entry.error_message:
        raise P2EmbeddingActivationError(
            "Index Entry synchronization is not ready.", status=entry.status
        )

    rows = (
        db.query(P2KnowledgeEmbedding)
        .filter(
            P2KnowledgeEmbedding.index_entry_id == index_entry_id,
            P2KnowledgeEmbedding.embedding_profile == embedding_profile,
            P2KnowledgeEmbedding.provider == provider,
            P2KnowledgeEmbedding.model == model,
            P2KnowledgeEmbedding.dimension == dimension,
        )
        .with_for_update()
        .all()
    )
    actual_fingerprints = {row.fingerprint for row in rows}
    if actual_fingerprints != expected_fingerprints:
        raise P2EmbeddingActivationError(
            "Embedding build changed before serving activation.", status=entry.status
        )

    entry.status = "serving"
    entry.sync_state = "ready"
    entry.error_message = None
    entry.updated_at = datetime.now(UTC)
    db.commit()
    return get_index_entry(db, index_entry_id), True


def record_embedding_error(db: Session, index_entry_id: str, message: str) -> None:
    """Persist a safe last-error without claiming that chunk projection failed."""
    row = (
        db.query(P2KnowledgeIndexEntry)
        .filter(P2KnowledgeIndexEntry.id == index_entry_id)
        .with_for_update()
        .first()
    )
    if row is None:
        return
    row.error_message = message
    row.updated_at = datetime.now(UTC)
    db.commit()


def list_embeddings(
    db: Session,
    *,
    page: int,
    page_size: int,
    index_entry_id: str | None = None,
    knowledge_asset_id: str | None = None,
    provider: str | None = None,
    embedding_profile: str | None = None,
) -> P2KnowledgeEmbeddingList:
    query = db.query(P2KnowledgeEmbedding)
    if index_entry_id:
        query = query.filter(P2KnowledgeEmbedding.index_entry_id == index_entry_id)
    if knowledge_asset_id:
        query = query.filter(P2KnowledgeEmbedding.knowledge_asset_id == knowledge_asset_id)
    if provider:
        query = query.filter(P2KnowledgeEmbedding.provider == provider)
    if embedding_profile:
        query = query.filter(P2KnowledgeEmbedding.embedding_profile == embedding_profile)
    total = query.count()
    rows = (
        query.order_by(
            P2KnowledgeEmbedding.created_at.desc(),
            P2KnowledgeEmbedding.id.desc(),
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return P2KnowledgeEmbeddingList(
        embeddings=[_record(db, row) for row in rows],
        pagination=P2KnowledgeEmbeddingPagination(
            page=page,
            page_size=page_size,
            total=total,
            total_pages=math.ceil(total / page_size) if total else 0,
        ),
    )

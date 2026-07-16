"""Repository-only P2 vector recall with governance filters."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db_models import (
    KnowledgeAsset,
    P2KnowledgeChunk,
    P2KnowledgeEmbedding,
    P2KnowledgeIndexEntry,
    _HAS_PGVECTOR,
    _is_postgresql,
)


class P2PgvectorUnavailableError(RuntimeError):
    pass


class P2PgvectorQueryError(RuntimeError):
    pass


@dataclass(frozen=True)
class P2ServingEmbeddingRow:
    embedding_id: str
    index_entry_id: str
    chunk_id: str
    knowledge_asset_id: str
    asset_id: str
    content_type: str
    chunk_text: str
    chunk_hash: str
    chunk_metadata: dict[str, object]
    provider: str
    model: str
    dimension: int
    embedding_profile: str
    embedding_fingerprint: str
    embedding_metadata: dict[str, object]
    index_fingerprint: str
    generation: int
    evaluation_scope: str | None
    score: float | None = None


def _metadata(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def list_serving_embedding_rows(
    db: Session, *, evaluation_scope: str | None = None
) -> list[P2ServingEmbeddingRow]:
    """Return only rows whose primary P2 governance states are serving/active."""
    rows = (
        db.query(P2KnowledgeEmbedding, P2KnowledgeChunk, P2KnowledgeIndexEntry, KnowledgeAsset)
        .join(P2KnowledgeChunk, P2KnowledgeChunk.id == P2KnowledgeEmbedding.chunk_id)
        .join(
            P2KnowledgeIndexEntry,
            P2KnowledgeIndexEntry.id == P2KnowledgeEmbedding.index_entry_id,
        )
        .join(KnowledgeAsset, KnowledgeAsset.id == P2KnowledgeEmbedding.knowledge_asset_id)
        .filter(
            KnowledgeAsset.status == "active",
            P2KnowledgeIndexEntry.status == "serving",
            P2KnowledgeIndexEntry.sync_state == "ready",
            P2KnowledgeIndexEntry.error_message.is_(None),
            P2KnowledgeChunk.index_entry_id == P2KnowledgeIndexEntry.id,
            P2KnowledgeChunk.knowledge_asset_id == KnowledgeAsset.id,
            P2KnowledgeEmbedding.knowledge_asset_id == KnowledgeAsset.id,
        )
        .all()
    )
    mapped = [
        P2ServingEmbeddingRow(
            embedding_id=embedding.id,
            index_entry_id=entry.id,
            chunk_id=chunk.id,
            knowledge_asset_id=knowledge_asset.id,
            asset_id=knowledge_asset.asset_id,
            content_type=knowledge_asset.content_type,
            chunk_text=chunk.chunk_text,
            chunk_hash=chunk.chunk_hash,
            chunk_metadata=_metadata(chunk.metadata_json),
            provider=embedding.provider,
            model=embedding.model,
            dimension=int(embedding.dimension),
            embedding_profile=embedding.embedding_profile,
            embedding_fingerprint=embedding.fingerprint,
            embedding_metadata=_metadata(embedding.metadata_json),
            index_fingerprint=entry.fingerprint,
            generation=int(entry.generation),
            evaluation_scope=(
                str(knowledge_asset.metadata_json.get("eval_run_scope"))
                if isinstance(knowledge_asset.metadata_json, dict)
                and knowledge_asset.metadata_json.get("eval_run_scope")
                else None
            ),
        )
        for embedding, chunk, entry, knowledge_asset in rows
    ]
    if evaluation_scope is not None:
        return [row for row in mapped if row.evaluation_scope == evaluation_scope]
    return mapped


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left:
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)


def _sqlite_search(
    db: Session,
    *,
    query_embedding: list[float],
    embedding_profile: str,
    provider: str,
    model: str,
    dimension: int,
    limit: int,
    evaluation_scope: str | None,
) -> list[P2ServingEmbeddingRow]:
    eligible = [
        row
        for row in list_serving_embedding_rows(
            db, evaluation_scope=evaluation_scope
        )
        if row.embedding_profile == embedding_profile
        and row.provider == provider
        and row.model == model
        and row.dimension == dimension
        and row.embedding_metadata.get("index_fingerprint") == row.index_fingerprint
        and row.embedding_metadata.get("chunk_hash") == row.chunk_hash
    ]
    embedding_rows = {
        row.id: row
        for row in db.query(P2KnowledgeEmbedding)
        .filter(P2KnowledgeEmbedding.id.in_([item.embedding_id for item in eligible]))
        .all()
    } if eligible else {}
    scored: list[P2ServingEmbeddingRow] = []
    for item in eligible:
        raw_vector = embedding_rows[item.embedding_id].embedding
        try:
            vector = json.loads(raw_vector) if isinstance(raw_vector, str) else list(raw_vector)
            vector = [float(value) for value in vector]
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if len(vector) != dimension:
            continue
        scored.append(
            P2ServingEmbeddingRow(
                **{**item.__dict__, "score": _cosine_similarity(query_embedding, vector)}
            )
        )
    return sorted(scored, key=lambda item: float(item.score or 0.0), reverse=True)[:limit]


def _postgres_search(
    db: Session,
    *,
    query_embedding: list[float],
    embedding_profile: str,
    provider: str,
    model: str,
    dimension: int,
    limit: int,
    evaluation_scope: str | None,
) -> list[P2ServingEmbeddingRow]:
    if not _HAS_PGVECTOR:
        raise P2PgvectorUnavailableError("pgvector is unavailable for P2 retrieval.")
    query_vector = "[" + ",".join(str(float(value)) for value in query_embedding) + "]"
    statement = text(
        """
        SELECT
            e.id AS embedding_id,
            e.index_entry_id,
            e.chunk_id,
            e.knowledge_asset_id,
            ka.asset_id,
            ka.content_type,
            c.chunk_text,
            c.chunk_hash,
            c.metadata_json AS chunk_metadata,
            e.provider,
            e.model,
            e.dimension,
            e.embedding_profile,
            e.fingerprint AS embedding_fingerprint,
            e.metadata_json AS embedding_metadata,
            ie.fingerprint AS index_fingerprint,
            ie.generation,
            1 - (e.embedding <=> CAST(:query_vector AS vector)) AS score
        FROM p2_knowledge_embeddings e
        JOIN p2_knowledge_chunks c
          ON c.id = e.chunk_id
         AND c.index_entry_id = e.index_entry_id
         AND c.knowledge_asset_id = e.knowledge_asset_id
        JOIN p2_knowledge_index_entries ie
          ON ie.id = e.index_entry_id
         AND ie.knowledge_asset_id = e.knowledge_asset_id
        JOIN knowledge_assets ka
          ON ka.id = e.knowledge_asset_id
        WHERE ka.status = 'active'
          AND ie.status = 'serving'
          AND ie.sync_state = 'ready'
          AND ie.error_message IS NULL
          AND e.embedding IS NOT NULL
          AND e.embedding_profile = :embedding_profile
          AND e.provider = :provider
          AND e.model = :model
          AND e.dimension = :dimension
          AND e.metadata_json ->> 'index_fingerprint' = ie.fingerprint
          AND e.metadata_json ->> 'chunk_hash' = c.chunk_hash
          AND (
            CAST(:evaluation_scope AS text) IS NULL
            OR ka.metadata_json ->> 'eval_run_scope' = :evaluation_scope
          )
        ORDER BY e.embedding <=> CAST(:query_vector AS vector)
        LIMIT :limit
        """
    )
    try:
        result = db.execute(
            statement,
            {
                "query_vector": query_vector,
                "embedding_profile": embedding_profile,
                "provider": provider,
                "model": model,
                "dimension": dimension,
                "limit": limit,
                "evaluation_scope": evaluation_scope,
            },
        )
        records = result.mappings().all()
    except Exception as exc:
        db.rollback()
        raise P2PgvectorQueryError("P2 pgvector query failed.") from exc
    return [
        P2ServingEmbeddingRow(
            embedding_id=str(row["embedding_id"]),
            index_entry_id=str(row["index_entry_id"]),
            chunk_id=str(row["chunk_id"]),
            knowledge_asset_id=str(row["knowledge_asset_id"]),
            asset_id=str(row["asset_id"]),
            content_type=str(row["content_type"]),
            chunk_text=str(row["chunk_text"]),
            chunk_hash=str(row["chunk_hash"]),
            chunk_metadata=_metadata(row["chunk_metadata"]),
            provider=str(row["provider"]),
            model=str(row["model"]),
            dimension=int(row["dimension"]),
            embedding_profile=str(row["embedding_profile"]),
            embedding_fingerprint=str(row["embedding_fingerprint"]),
            embedding_metadata=_metadata(row["embedding_metadata"]),
            index_fingerprint=str(row["index_fingerprint"]),
            generation=int(row["generation"]),
            evaluation_scope=evaluation_scope,
            score=float(row["score"]),
        )
        for row in records
    ]


def search_serving_embeddings(
    db: Session,
    *,
    query_embedding: list[float],
    embedding_profile: str,
    provider: str,
    model: str,
    dimension: int,
    limit: int,
    evaluation_scope: str | None = None,
) -> list[P2ServingEmbeddingRow]:
    if _is_postgresql():
        return _postgres_search(
            db,
            query_embedding=query_embedding,
            embedding_profile=embedding_profile,
            provider=provider,
            model=model,
            dimension=dimension,
            limit=limit,
            evaluation_scope=evaluation_scope,
        )
    return _sqlite_search(
        db,
        query_embedding=query_embedding,
        embedding_profile=embedding_profile,
        provider=provider,
        model=model,
        dimension=dimension,
        limit=limit,
        evaluation_scope=evaluation_scope,
    )

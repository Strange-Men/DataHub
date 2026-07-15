"""P2-M7 active/ready-only text-bridge embedding orchestration."""

from __future__ import annotations

import hashlib
import json
import os

from sqlalchemy.orm import Session

from app.embedding import EmbeddingProvider, get_embedding_provider
from app.knowledge_asset_repositories import KnowledgeSourceTraceError, get_knowledge_asset
from app.knowledge_embedding_repositories import (
    P2EmbeddingIndexNotFound,
    P2EmbeddingPersistenceError,
    get_embeddings_for_fingerprints,
    record_embedding_error,
    save_embedding_build,
)
from app.knowledge_embedding_schemas import BuildP2KnowledgeEmbeddingsResult
from app.knowledge_index_repositories import (
    KnowledgeIndexSourceTraceError,
    get_index_entry,
    transition_index_entry,
)


TEXT_BRIDGE_VERSION = "p2_text_bridge_embedding_v1"


class P2EmbeddingIndexNotFoundError(RuntimeError):
    pass


class P2EmbeddingKnowledgeAssetNotActiveError(RuntimeError):
    pass


class P2EmbeddingIndexNotReadyError(RuntimeError):
    def __init__(self, status: str) -> None:
        super().__init__(f"Index Entry is {status}; only ready entries can generate embeddings.")
        self.status = status


class P2EmbeddingSourceInvalidError(RuntimeError):
    pass


class P2EmbeddingProviderError(RuntimeError):
    pass


class P2EmbeddingDimensionError(RuntimeError):
    pass


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _profile(provider: EmbeddingProvider) -> str:
    configured = os.getenv("P2_EMBEDDING_PROFILE", "").strip()
    if configured:
        return configured
    return f"text_bridge:{provider.provider_name}:{provider.model_name}:{provider.dimension}"


def _fingerprint(
    *,
    chunk_id: str,
    chunk_hash: str,
    chunk_text: str,
    generation: int,
    provider: EmbeddingProvider,
    embedding_profile: str,
) -> str:
    payload = {
        "bridge_version": TEXT_BRIDGE_VERSION,
        "chunk_hash": chunk_hash,
        "chunk_id": chunk_id,
        "chunk_text": chunk_text,
        "dimension": provider.dimension,
        "embedding_profile": embedding_profile,
        "generation": generation,
        "model": provider.model_name,
        "provider": provider.provider_name,
    }
    return _sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    )


class P2KnowledgeEmbeddingService:
    """Builds P2 vectors without importing or writing any P1 RAG storage."""

    def __init__(
        self,
        db: Session,
        provider: EmbeddingProvider | None = None,
    ) -> None:
        self.db = db
        self.provider = provider or get_embedding_provider()

    def build(self, index_entry_id: str) -> BuildP2KnowledgeEmbeddingsResult:
        try:
            entry = get_index_entry(self.db, index_entry_id)
        except KnowledgeIndexSourceTraceError as exc:
            raise P2EmbeddingSourceInvalidError(str(exc)) from exc
        if entry is None:
            raise P2EmbeddingIndexNotFoundError(index_entry_id)
        try:
            knowledge_asset = get_knowledge_asset(self.db, entry.knowledge_asset_id)
        except KnowledgeSourceTraceError as exc:
            raise P2EmbeddingSourceInvalidError(str(exc)) from exc
        if knowledge_asset is None or knowledge_asset.status != "active":
            raise P2EmbeddingKnowledgeAssetNotActiveError(entry.knowledge_asset_id)
        if not entry.chunks:
            raise P2EmbeddingSourceInvalidError("Index Entry has no governed chunks.")

        provider_name = self.provider.provider_name.strip()
        model_name = self.provider.model_name.strip()
        dimension = int(self.provider.dimension)
        if not provider_name or not model_name or dimension <= 0:
            raise P2EmbeddingDimensionError("Embedding provider metadata is invalid.")
        embedding_profile = _profile(self.provider)
        fingerprints = [
            _fingerprint(
                chunk_id=chunk.id,
                chunk_hash=chunk.chunk_hash,
                chunk_text=chunk.chunk_text,
                generation=entry.generation,
                provider=self.provider,
                embedding_profile=embedding_profile,
            )
            for chunk in entry.chunks
        ]
        existing = get_embeddings_for_fingerprints(
            self.db,
            index_entry_id=entry.id,
            fingerprints=fingerprints,
        )
        if len(existing) == len(entry.chunks):
            if entry.status == "ready":
                try:
                    transition_index_entry(self.db, entry.id, "serving")
                except Exception as exc:
                    raise P2EmbeddingSourceInvalidError(
                        "Existing embedding build could not be activated."
                    ) from exc
            elif entry.status != "serving":
                raise P2EmbeddingIndexNotReadyError(entry.status)
            return BuildP2KnowledgeEmbeddingsResult(
                index_entry_id=entry.id,
                index_status="serving",
                provider=provider_name,
                model=model_name,
                dimension=dimension,
                embedding_profile=embedding_profile,
                created_count=0,
                skipped_count=len(existing),
                embeddings=existing,
            )
        if entry.status != "ready":
            raise P2EmbeddingIndexNotReadyError(entry.status)

        try:
            vectors = self.provider.embed_batch([chunk.chunk_text for chunk in entry.chunks])
        except Exception as exc:
            safe_message = "Embedding provider call failed."
            record_embedding_error(self.db, entry.id, safe_message)
            raise P2EmbeddingProviderError(safe_message) from exc
        if len(vectors) != len(entry.chunks) or any(
            len(vector) != dimension for vector in vectors
        ):
            safe_message = f"Embedding dimension mismatch; expected {dimension}."
            record_embedding_error(self.db, entry.id, safe_message)
            raise P2EmbeddingDimensionError(safe_message)

        rows: list[dict[str, object]] = []
        trace = entry.source_trace.model_dump()
        for chunk, vector, fingerprint in zip(entry.chunks, vectors, fingerprints):
            rows.append(
                {
                    "id": f"p2_embedding_{fingerprint[:20]}",
                    "chunk_id": chunk.id,
                    "knowledge_asset_id": entry.knowledge_asset_id,
                    "chunk_text": chunk.chunk_text,
                    "embedding": [float(value) for value in vector],
                    "provider": provider_name,
                    "model": model_name,
                    "dimension": dimension,
                    "embedding_profile": embedding_profile,
                    "fingerprint": fingerprint,
                    "metadata_json": {
                        "bridge_version": TEXT_BRIDGE_VERSION,
                        "chunk_hash": chunk.chunk_hash,
                        "index_generation": entry.generation,
                        "index_fingerprint": entry.fingerprint,
                        "source_trace": trace,
                    },
                }
            )
        try:
            records, created = save_embedding_build(
                self.db,
                index_entry_id=entry.id,
                rows=rows,
            )
        except P2EmbeddingIndexNotFound as exc:
            raise P2EmbeddingIndexNotFoundError(index_entry_id) from exc
        except P2EmbeddingPersistenceError as exc:
            raise P2EmbeddingIndexNotReadyError(entry.status) from exc
        return BuildP2KnowledgeEmbeddingsResult(
            index_entry_id=entry.id,
            index_status="serving",
            provider=provider_name,
            model=model_name,
            dimension=dimension,
            embedding_profile=embedding_profile,
            created_count=created,
            skipped_count=len(records) - created,
            embeddings=records,
        )


__all__ = [
    "P2EmbeddingDimensionError",
    "P2EmbeddingIndexNotFoundError",
    "P2EmbeddingIndexNotReadyError",
    "P2EmbeddingKnowledgeAssetNotActiveError",
    "P2EmbeddingProviderError",
    "P2EmbeddingSourceInvalidError",
    "P2KnowledgeEmbeddingService",
    "TEXT_BRIDGE_VERSION",
]

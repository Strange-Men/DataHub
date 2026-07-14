"""P2-M6 orchestration for deterministic, non-vector Knowledge Index projection."""

from __future__ import annotations

import hashlib
import json

from sqlalchemy.orm import Session

from app.knowledge_asset_repositories import KnowledgeSourceTraceError, get_knowledge_asset
from app.knowledge_asset_schemas import KnowledgeAssetRecord
from app.knowledge_index_repositories import (
    KnowledgeIndexRowNotFound,
    KnowledgeIndexSourceTraceError,
    KnowledgeIndexTransitionError,
    archive_index_entry,
    create_pending_index_entry,
    get_index_entry,
    get_index_entry_by_knowledge_asset,
    save_projected_chunk,
    transition_index_entry,
)
from app.knowledge_index_schemas import CreateKnowledgeIndexResult, KnowledgeIndexEntryRecord


PROJECTION_VERSION = "p2_text_projection_v1"
CHUNKER_VERSION = "single_chunk_v1"


class IndexKnowledgeAssetNotFoundError(RuntimeError):
    pass


class IndexKnowledgeAssetNotActiveError(RuntimeError):
    pass


class KnowledgeIndexNotFoundError(RuntimeError):
    pass


class KnowledgeIndexSourceInvalidError(RuntimeError):
    pass


class KnowledgeIndexProjectionError(RuntimeError):
    pass


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _project_text(content_type: str, content: str) -> str:
    normalized_type = content_type.strip().lower()
    normalized_content = content.strip()
    if not normalized_type or not normalized_content:
        raise KnowledgeIndexProjectionError("Knowledge Asset projection is empty.")
    return f"Content type: {normalized_type}\n{normalized_content}"


def _fingerprint(knowledge_asset: KnowledgeAssetRecord) -> str:
    payload = {
        "asset_id": knowledge_asset.asset_id,
        "content": knowledge_asset.content,
        "content_type": knowledge_asset.content_type,
        "knowledge_asset_id": knowledge_asset.id,
        "knowledge_asset_version": knowledge_asset.version,
        "projection_version": PROJECTION_VERSION,
        "chunker_version": CHUNKER_VERSION,
    }
    return _sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


class KnowledgeIndexService:
    """Creates idempotent P2 index entries and immutable text chunks only."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create_index(self, knowledge_asset_id: str) -> CreateKnowledgeIndexResult:
        try:
            knowledge_asset = get_knowledge_asset(self.db, knowledge_asset_id)
        except KnowledgeSourceTraceError as exc:
            raise KnowledgeIndexSourceInvalidError(str(exc)) from exc
        if knowledge_asset is None:
            raise IndexKnowledgeAssetNotFoundError(knowledge_asset_id)
        if knowledge_asset.status != "active":
            raise IndexKnowledgeAssetNotActiveError(knowledge_asset_id)
        existing = get_index_entry_by_knowledge_asset(self.db, knowledge_asset_id)
        if existing is not None:
            return CreateKnowledgeIndexResult(index_entry=existing, created=False)

        fingerprint = _fingerprint(knowledge_asset)
        result = create_pending_index_entry(
            self.db,
            knowledge_asset_id=knowledge_asset.id,
            generation=knowledge_asset.version,
            fingerprint=fingerprint,
        )
        if not result.created:
            return result

        try:
            transition_index_entry(self.db, result.index_entry.id, "building")
            chunk_text = _project_text(knowledge_asset.content_type, knowledge_asset.content)
            chunk_hash = _sha256(chunk_text)
            chunk_id = f"p2_chunk_{_sha256(f'{fingerprint}:0:{chunk_hash}')[:20]}"
            entry = save_projected_chunk(
                self.db,
                index_entry_id=result.index_entry.id,
                knowledge_asset_id=knowledge_asset.id,
                chunk_id=chunk_id,
                chunk_text=chunk_text,
                chunk_hash=chunk_hash,
                chunk_order=0,
                metadata_json={
                    "modality": "text_projection",
                    "projection_version": PROJECTION_VERSION,
                    "chunker_version": CHUNKER_VERSION,
                    "content_type": knowledge_asset.content_type,
                    "knowledge_asset_version": knowledge_asset.version,
                    "source_snapshot_id": knowledge_asset.source_snapshot_id,
                    "asset_id": knowledge_asset.asset_id,
                    "embedding_created": False,
                    "vector_indexed": False,
                },
            )
        except Exception as exc:
            safe_message = "Text projection failed."
            try:
                transition_index_entry(
                    self.db,
                    result.index_entry.id,
                    "failed",
                    error_message=safe_message,
                )
            except (KnowledgeIndexRowNotFound, KnowledgeIndexTransitionError):
                pass
            raise KnowledgeIndexProjectionError(safe_message) from exc
        return CreateKnowledgeIndexResult(index_entry=entry, created=True)

    def get_index(self, index_entry_id: str) -> KnowledgeIndexEntryRecord:
        try:
            record = get_index_entry(self.db, index_entry_id)
        except KnowledgeIndexSourceTraceError as exc:
            raise KnowledgeIndexSourceInvalidError(str(exc)) from exc
        if record is None:
            raise KnowledgeIndexNotFoundError(index_entry_id)
        return record

    def archive(self, index_entry_id: str) -> KnowledgeIndexEntryRecord:
        try:
            return archive_index_entry(self.db, index_entry_id)
        except KnowledgeIndexRowNotFound as exc:
            raise KnowledgeIndexNotFoundError(index_entry_id) from exc
        except KnowledgeIndexSourceTraceError as exc:
            raise KnowledgeIndexSourceInvalidError(str(exc)) from exc


__all__ = [
    "CHUNKER_VERSION",
    "IndexKnowledgeAssetNotActiveError",
    "IndexKnowledgeAssetNotFoundError",
    "KnowledgeIndexNotFoundError",
    "KnowledgeIndexProjectionError",
    "KnowledgeIndexService",
    "KnowledgeIndexSourceInvalidError",
    "PROJECTION_VERSION",
]

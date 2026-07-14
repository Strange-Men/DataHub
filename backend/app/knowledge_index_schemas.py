"""P2-M6 schemas for index lifecycle and immutable text projection."""

from typing import Literal

from pydantic import BaseModel, Field

from app.knowledge_asset_schemas import KnowledgeAssetSourceTrace


KnowledgeIndexStatus = Literal[
    "pending",
    "building",
    "ready",
    "serving",
    "failed",
    "archived",
]
KnowledgeIndexSyncState = Literal["pending", "building", "ready", "failed", "archived"]


class KnowledgeIndexSourceTrace(BaseModel):
    index_entry_id: str
    knowledge_asset_id: str
    knowledge_asset_version: int
    snapshot_id: str
    snapshot_version: int
    review_id: str
    review_status: str
    review_version: int
    extraction_id: str
    extraction_job_id: str
    extraction_type: str
    extraction_version: int
    asset_id: str
    asset_file_name: str
    asset_hash: str
    asset_status: str


class KnowledgeChunkRecord(BaseModel):
    id: str
    index_entry_id: str
    knowledge_asset_id: str
    chunk_text: str
    chunk_hash: str
    chunk_order: int
    metadata_json: dict[str, object]
    created_at: str


class KnowledgeIndexEntryRecord(BaseModel):
    id: str
    knowledge_asset_id: str
    status: KnowledgeIndexStatus
    generation: int
    fingerprint: str
    sync_state: KnowledgeIndexSyncState
    error_message: str | None
    created_at: str
    updated_at: str
    chunks: list[KnowledgeChunkRecord]
    source_trace: KnowledgeIndexSourceTrace


class KnowledgeIndexPagination(BaseModel):
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
    total: int = Field(ge=0)
    total_pages: int = Field(ge=0)


class KnowledgeIndexList(BaseModel):
    index_entries: list[KnowledgeIndexEntryRecord]
    pagination: KnowledgeIndexPagination


class CreateKnowledgeIndexResult(BaseModel):
    index_entry: KnowledgeIndexEntryRecord
    created: bool


def index_source_trace(
    *,
    index_entry_id: str,
    knowledge_asset_version: int,
    source: KnowledgeAssetSourceTrace,
) -> KnowledgeIndexSourceTrace:
    return KnowledgeIndexSourceTrace(
        index_entry_id=index_entry_id,
        knowledge_asset_id=source.knowledge_asset_id,
        knowledge_asset_version=knowledge_asset_version,
        snapshot_id=source.snapshot_id,
        snapshot_version=source.snapshot_version,
        review_id=source.review_id,
        review_status=source.review_status,
        review_version=source.review_version,
        extraction_id=source.extraction_id,
        extraction_job_id=source.extraction_job_id,
        extraction_type=source.extraction_type,
        extraction_version=source.extraction_version,
        asset_id=source.asset_id,
        asset_file_name=source.asset_file_name,
        asset_hash=source.asset_hash,
        asset_status=source.asset_status,
    )

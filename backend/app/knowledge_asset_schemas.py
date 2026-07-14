"""P2-M4 schemas for governed Knowledge Assets and complete source trace."""

from typing import Literal

from pydantic import BaseModel, Field


KnowledgeAssetStatus = Literal["draft", "active", "archived"]


class KnowledgeAssetSourceTrace(BaseModel):
    knowledge_asset_id: str
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


class KnowledgeAssetRecord(BaseModel):
    id: str
    source_snapshot_id: str
    asset_id: str
    content: str
    content_type: str
    status: KnowledgeAssetStatus
    version: int
    metadata_json: dict[str, object]
    created_at: str
    updated_at: str
    source_trace: KnowledgeAssetSourceTrace


class KnowledgeAssetPagination(BaseModel):
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
    total: int = Field(ge=0)
    total_pages: int = Field(ge=0)


class KnowledgeAssetList(BaseModel):
    knowledge_assets: list[KnowledgeAssetRecord]
    pagination: KnowledgeAssetPagination


class PublishKnowledgeAssetResult(BaseModel):
    knowledge_asset: KnowledgeAssetRecord
    created: bool

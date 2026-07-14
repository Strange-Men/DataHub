"""P2-M1 API schemas for governed material assets."""

from pydantic import BaseModel, Field


class AssetRecord(BaseModel):
    id: str
    asset_type: str
    file_name: str
    mime_type: str
    size: int
    storage_uri: str
    hash: str
    status: str
    metadata_json: dict[str, object]
    created_at: str
    updated_at: str


class AssetPagination(BaseModel):
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
    total: int = Field(ge=0)
    total_pages: int = Field(ge=0)


class AssetListResult(BaseModel):
    assets: list[AssetRecord]
    pagination: AssetPagination

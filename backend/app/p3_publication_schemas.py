"""Stable contracts for governed P3 asset publication."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.p3_reuse_models import (
    ReuseAssetType,
    ReuseAssetVersionStatus,
    ReuseGenerationMode,
)


class P3PublishedAssetSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    asset_version_id: str
    project_id: str
    asset_type: ReuseAssetType
    version_number: int
    status: ReuseAssetVersionStatus
    generation_mode: ReuseGenerationMode
    published_at: datetime | None
    published_by_role: str | None
    content_hash: str
    source_manifest_hash: str
    superseded_by_asset_version_id: str | None
    archived_at: datetime | None
    source_stale: bool
    current_reuse_eligible: bool


class P3PublicationOutcome(BaseModel):
    model_config = ConfigDict(frozen=True)

    asset: P3PublishedAssetSummary
    superseded_asset_version_id: str | None = None
    replayed: bool = False


class P3PublishedAssetPage(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: list[P3PublishedAssetSummary]
    total: int
    limit: int
    offset: int


class P3PublicationActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    idempotency_key: str = Field(min_length=1, max_length=200)


class P3PublicationResponse(BaseModel):
    success: Literal[True] = True
    data: P3PublicationOutcome
    requestId: str


class P3PublishedAssetResponse(BaseModel):
    success: Literal[True] = True
    data: P3PublishedAssetSummary
    requestId: str


class P3PublishedAssetPageResponse(BaseModel):
    success: Literal[True] = True
    data: P3PublishedAssetPage
    requestId: str


__all__ = [
    "P3PublicationOutcome",
    "P3PublicationActionRequest",
    "P3PublicationResponse",
    "P3PublishedAssetPage",
    "P3PublishedAssetPageResponse",
    "P3PublishedAssetResponse",
    "P3PublishedAssetSummary",
]

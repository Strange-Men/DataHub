"""P2-M2 schemas for provider-neutral Asset extraction jobs and results."""

from typing import Literal

from pydantic import BaseModel


ExtractionType = Literal["ocr", "caption", "metadata"]
ExtractionStatus = Literal["pending", "running", "success", "failed", "retrying"]


class ExtractionRequest(BaseModel):
    extract_type: ExtractionType
    provider: Literal["mock"] = "mock"


class ExtractionJobRecord(BaseModel):
    id: str
    asset_id: str
    extract_type: str
    provider: str
    status: ExtractionStatus
    retry_count: int
    error_message: str | None
    started_at: str | None
    completed_at: str | None
    created_at: str
    updated_at: str


class AssetExtractionRecord(BaseModel):
    id: str
    asset_id: str
    job_id: str
    extract_type: str
    content: str
    metadata_json: dict[str, object]
    version: int
    created_at: str


class AssetExtractionList(BaseModel):
    asset_id: str
    extractions: list[AssetExtractionRecord]


class ExtractionExecutionResult(BaseModel):
    job: ExtractionJobRecord
    result: AssetExtractionRecord | None

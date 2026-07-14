"""Database persistence for the P2-M2 Extraction aggregate."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db_models import AssetExtraction, ExtractionJob
from app.extraction_schemas import (
    AssetExtractionList,
    AssetExtractionRecord,
    ExtractionJobRecord,
)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _job_record(row: ExtractionJob) -> ExtractionJobRecord:
    return ExtractionJobRecord(
        id=row.id,
        asset_id=row.asset_id,
        extract_type=row.extract_type,
        provider=row.provider,
        status=row.status,
        retry_count=int(row.retry_count),
        error_message=row.error_message,
        started_at=_iso(row.started_at),
        completed_at=_iso(row.completed_at),
        created_at=_iso(row.created_at) or "",
        updated_at=_iso(row.updated_at) or "",
    )


def _extraction_record(row: AssetExtraction) -> AssetExtractionRecord:
    metadata = row.metadata_json if isinstance(row.metadata_json, dict) else {}
    return AssetExtractionRecord(
        id=row.id,
        asset_id=row.asset_id,
        job_id=row.job_id,
        extract_type=row.extract_type,
        content=row.content,
        metadata_json=metadata,
        version=int(row.version),
        created_at=_iso(row.created_at) or "",
    )


def create_extraction_job(
    db: Session,
    *,
    asset_id: str,
    extract_type: str,
    provider: str,
) -> ExtractionJobRecord:
    now = datetime.now(UTC)
    row = ExtractionJob(
        id=f"asset_extract_job_{uuid4().hex[:20]}",
        asset_id=asset_id,
        extract_type=extract_type,
        provider=provider,
        status="pending",
        retry_count=0,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _job_record(row)


def get_extraction_job(db: Session, job_id: str) -> ExtractionJobRecord | None:
    row = db.query(ExtractionJob).filter(ExtractionJob.id == job_id).first()
    return _job_record(row) if row is not None else None


def update_extraction_job(
    db: Session,
    job_id: str,
    *,
    status: str,
    retry_count: int | None = None,
    error_message: str | None = None,
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
    clear_completed_at: bool = False,
) -> ExtractionJobRecord:
    row = db.query(ExtractionJob).filter(ExtractionJob.id == job_id).one()
    row.status = status
    if retry_count is not None:
        row.retry_count = retry_count
    row.error_message = error_message
    if started_at is not None:
        row.started_at = started_at
    if clear_completed_at:
        row.completed_at = None
    elif completed_at is not None:
        row.completed_at = completed_at
    row.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(row)
    return _job_record(row)


def create_asset_extraction(
    db: Session,
    *,
    asset_id: str,
    job_id: str,
    extract_type: str,
    content: str,
    metadata_json: dict[str, Any],
) -> AssetExtractionRecord:
    existing = (
        db.query(AssetExtraction)
        .filter(AssetExtraction.job_id == job_id)
        .first()
    )
    if existing is not None:
        return _extraction_record(existing)

    current_version = (
        db.query(func.max(AssetExtraction.version))
        .filter(
            AssetExtraction.asset_id == asset_id,
            AssetExtraction.extract_type == extract_type,
        )
        .scalar()
    )
    row = AssetExtraction(
        id=f"asset_extract_{uuid4().hex[:20]}",
        asset_id=asset_id,
        job_id=job_id,
        extract_type=extract_type,
        content=content,
        metadata_json=metadata_json,
        version=int(current_version or 0) + 1,
        created_at=datetime.now(UTC),
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raced = (
            db.query(AssetExtraction)
            .filter(AssetExtraction.job_id == job_id)
            .first()
        )
        if raced is not None:
            return _extraction_record(raced)
        raise
    db.refresh(row)
    return _extraction_record(row)


def get_asset_extraction(
    db: Session,
    extraction_id: str,
) -> AssetExtractionRecord | None:
    row = (
        db.query(AssetExtraction)
        .filter(AssetExtraction.id == extraction_id)
        .first()
    )
    return _extraction_record(row) if row is not None else None


def list_asset_extractions(db: Session, asset_id: str) -> AssetExtractionList:
    rows = (
        db.query(AssetExtraction)
        .filter(AssetExtraction.asset_id == asset_id)
        .order_by(AssetExtraction.created_at.desc(), AssetExtraction.id.desc())
        .all()
    )
    return AssetExtractionList(
        asset_id=asset_id,
        extractions=[_extraction_record(row) for row in rows],
    )

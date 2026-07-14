"""Database access for the additive P2 Asset aggregate."""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.asset_schemas import AssetListResult, AssetPagination, AssetRecord
from app.db_models import Asset


class DuplicateAssetHashError(RuntimeError):
    def __init__(self, asset_id: str) -> None:
        super().__init__("Asset content already exists.")
        self.asset_id = asset_id


def _to_record(row: Asset) -> AssetRecord:
    metadata = row.metadata_json if isinstance(row.metadata_json, dict) else {}
    return AssetRecord(
        id=row.id,
        asset_type=row.asset_type,
        file_name=row.file_name,
        mime_type=row.mime_type,
        size=int(row.size),
        storage_uri=row.storage_uri,
        hash=row.hash,
        status=row.status,
        metadata_json=metadata,
        created_at=row.created_at.isoformat() if row.created_at else "",
        updated_at=row.updated_at.isoformat() if row.updated_at else "",
    )


def get_asset_by_hash(db: Session, content_hash: str) -> AssetRecord | None:
    row = db.query(Asset).filter(Asset.hash == content_hash).first()
    return _to_record(row) if row is not None else None


def get_asset(db: Session, asset_id: str) -> AssetRecord | None:
    row = db.query(Asset).filter(Asset.id == asset_id).first()
    return _to_record(row) if row is not None else None


def create_asset(
    db: Session,
    *,
    asset_id: str,
    asset_type: str,
    file_name: str,
    mime_type: str,
    size: int,
    storage_uri: str,
    content_hash: str,
    metadata_json: dict[str, Any],
) -> AssetRecord:
    now = datetime.now(UTC)
    row = Asset(
        id=asset_id,
        asset_type=asset_type,
        file_name=file_name,
        mime_type=mime_type,
        size=size,
        storage_uri=storage_uri,
        hash=content_hash,
        status="uploaded",
        metadata_json=metadata_json,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        duplicate = get_asset_by_hash(db, content_hash)
        if duplicate is not None:
            raise DuplicateAssetHashError(duplicate.id) from exc
        raise
    db.refresh(row)
    return _to_record(row)


def list_assets(db: Session, *, page: int, page_size: int) -> AssetListResult:
    total = db.query(Asset).count()
    rows = (
        db.query(Asset)
        .order_by(Asset.created_at.desc(), Asset.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    total_pages = math.ceil(total / page_size) if total else 0
    return AssetListResult(
        assets=[_to_record(row) for row in rows],
        pagination=AssetPagination(
            page=page,
            page_size=page_size,
            total=total,
            total_pages=total_pages,
        ),
    )

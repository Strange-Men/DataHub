"""Persistence for P2 Knowledge Assets, isolated from the P1 RAG schema."""

from __future__ import annotations

import math
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db_models import (
    Asset,
    AssetExtraction,
    AssetReviewSnapshot,
    ExtractionReview,
    KnowledgeAsset,
    P2KnowledgeIndexEntry,
)
from app.knowledge_asset_schemas import (
    KnowledgeAssetList,
    KnowledgeAssetPagination,
    KnowledgeAssetRecord,
    KnowledgeAssetSourceTrace,
    PublishKnowledgeAssetResult,
)


class KnowledgeAssetRowNotFound(RuntimeError):
    pass


class KnowledgeSourceTraceError(RuntimeError):
    pass


def _iso(value: datetime | None) -> str:
    return value.isoformat() if value is not None else ""


def _source_trace(
    db: Session,
    row: KnowledgeAsset,
) -> KnowledgeAssetSourceTrace:
    snapshot = (
        db.query(AssetReviewSnapshot)
        .filter(AssetReviewSnapshot.id == row.source_snapshot_id)
        .first()
    )
    if snapshot is None:
        raise KnowledgeSourceTraceError("Knowledge Asset snapshot source is missing.")
    review = (
        db.query(ExtractionReview)
        .filter(ExtractionReview.id == snapshot.review_id)
        .first()
    )
    extraction = (
        db.query(AssetExtraction)
        .filter(AssetExtraction.id == snapshot.extraction_id)
        .first()
    )
    asset = db.query(Asset).filter(Asset.id == row.asset_id).first()
    return _source_trace_from_rows(row, snapshot, review, extraction, asset)


def _source_trace_from_rows(
    row: KnowledgeAsset,
    snapshot: AssetReviewSnapshot | None,
    review: ExtractionReview | None,
    extraction: AssetExtraction | None,
    asset: Asset | None,
) -> KnowledgeAssetSourceTrace:
    """Build and validate lineage from already-loaded rows."""
    if review is None or extraction is None or asset is None:
        raise KnowledgeSourceTraceError("Knowledge Asset source trace is incomplete.")
    if snapshot is None:
        raise KnowledgeSourceTraceError("Knowledge Asset snapshot source is missing.")
    if not (
        snapshot.asset_id == row.asset_id
        and review.asset_id == row.asset_id
        and extraction.asset_id == row.asset_id
        and review.extraction_id == extraction.id
        and snapshot.extraction_id == extraction.id
        and snapshot.review_id == review.id
    ):
        raise KnowledgeSourceTraceError("Knowledge Asset source trace is inconsistent.")
    return KnowledgeAssetSourceTrace(
        knowledge_asset_id=row.id,
        snapshot_id=snapshot.id,
        snapshot_version=int(snapshot.version),
        review_id=review.id,
        review_status=review.review_status,
        review_version=int(review.version),
        extraction_id=extraction.id,
        extraction_job_id=extraction.job_id,
        extraction_type=extraction.extract_type,
        extraction_version=int(extraction.version),
        asset_id=asset.id,
        asset_file_name=asset.file_name,
        asset_hash=asset.hash,
        asset_status=asset.status,
    )


def _record(db: Session, row: KnowledgeAsset) -> KnowledgeAssetRecord:
    return _record_from_rows(row, _source_trace(db, row))


def _record_from_rows(
    row: KnowledgeAsset,
    source_trace: KnowledgeAssetSourceTrace,
) -> KnowledgeAssetRecord:
    metadata = row.metadata_json if isinstance(row.metadata_json, dict) else {}
    return KnowledgeAssetRecord(
        id=row.id,
        source_snapshot_id=row.source_snapshot_id,
        asset_id=row.asset_id,
        content=row.content,
        content_type=row.content_type,
        status=row.status,
        version=int(row.version),
        metadata_json=metadata,
        created_at=_iso(row.created_at),
        updated_at=_iso(row.updated_at),
        source_trace=source_trace,
    )


def get_knowledge_assets_by_ids(
    db: Session,
    knowledge_asset_ids: list[str],
) -> dict[str, KnowledgeAssetRecord]:
    """Load governed Knowledge Assets and complete lineage in one query."""
    if not knowledge_asset_ids:
        return {}
    rows = (
        db.query(
            KnowledgeAsset,
            AssetReviewSnapshot,
            ExtractionReview,
            AssetExtraction,
            Asset,
        )
        .outerjoin(
            AssetReviewSnapshot,
            AssetReviewSnapshot.id == KnowledgeAsset.source_snapshot_id,
        )
        .outerjoin(ExtractionReview, ExtractionReview.id == AssetReviewSnapshot.review_id)
        .outerjoin(AssetExtraction, AssetExtraction.id == AssetReviewSnapshot.extraction_id)
        .outerjoin(Asset, Asset.id == KnowledgeAsset.asset_id)
        .filter(KnowledgeAsset.id.in_(knowledge_asset_ids))
        .all()
    )
    return {
        knowledge_asset.id: _record_from_rows(
            knowledge_asset,
            _source_trace_from_rows(
                knowledge_asset,
                snapshot,
                review,
                extraction,
                asset,
            ),
        )
        for knowledge_asset, snapshot, review, extraction, asset in rows
    }


def get_knowledge_asset(
    db: Session,
    knowledge_asset_id: str,
) -> KnowledgeAssetRecord | None:
    row = (
        db.query(KnowledgeAsset)
        .filter(KnowledgeAsset.id == knowledge_asset_id)
        .first()
    )
    return _record(db, row) if row is not None else None


def get_knowledge_asset_by_snapshot(
    db: Session,
    snapshot_id: str,
) -> KnowledgeAssetRecord | None:
    row = (
        db.query(KnowledgeAsset)
        .filter(KnowledgeAsset.source_snapshot_id == snapshot_id)
        .first()
    )
    return _record(db, row) if row is not None else None


def publish_knowledge_asset(
    db: Session,
    *,
    source_snapshot_id: str,
    asset_id: str,
    content: str,
    content_type: str,
    metadata_json: dict[str, object],
) -> PublishKnowledgeAssetResult:
    existing = get_knowledge_asset_by_snapshot(db, source_snapshot_id)
    if existing is not None:
        return PublishKnowledgeAssetResult(knowledge_asset=existing, created=False)

    # Serialize publications per Asset so version allocation and active-version
    # replacement remain atomic on PostgreSQL.
    asset_row = (
        db.query(Asset)
        .filter(Asset.id == asset_id)
        .with_for_update()
        .one()
    )
    existing = get_knowledge_asset_by_snapshot(db, source_snapshot_id)
    if existing is not None:
        return PublishKnowledgeAssetResult(knowledge_asset=existing, created=False)

    current_version = (
        db.query(func.max(KnowledgeAsset.version))
        .filter(
            KnowledgeAsset.asset_id == asset_id,
            KnowledgeAsset.content_type == content_type,
        )
        .scalar()
    )
    now = datetime.now(UTC)
    superseded_ids = [
        item[0]
        for item in (
            db.query(KnowledgeAsset.id)
            .filter(
                KnowledgeAsset.asset_id == asset_id,
                KnowledgeAsset.content_type == content_type,
                KnowledgeAsset.status == "active",
            )
            .all()
        )
    ]
    (
        db.query(KnowledgeAsset)
        .filter(
            KnowledgeAsset.asset_id == asset_id,
            KnowledgeAsset.content_type == content_type,
            KnowledgeAsset.status == "active",
        )
        .update(
            {"status": "archived", "updated_at": now},
            synchronize_session=False,
        )
    )
    if superseded_ids:
        (
            db.query(P2KnowledgeIndexEntry)
            .filter(
                P2KnowledgeIndexEntry.knowledge_asset_id.in_(superseded_ids),
                P2KnowledgeIndexEntry.status != "archived",
            )
            .update(
                {
                    "status": "archived",
                    "sync_state": "archived",
                    "error_message": None,
                    "updated_at": now,
                },
                synchronize_session=False,
            )
        )
    row = KnowledgeAsset(
        id=f"knowledge_asset_{uuid4().hex[:20]}",
        source_snapshot_id=source_snapshot_id,
        asset_id=asset_row.id,
        content=content,
        content_type=content_type,
        status="active",
        version=int(current_version or 0) + 1,
        metadata_json=metadata_json,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raced = get_knowledge_asset_by_snapshot(db, source_snapshot_id)
        if raced is not None:
            return PublishKnowledgeAssetResult(knowledge_asset=raced, created=False)
        raise
    db.refresh(row)
    return PublishKnowledgeAssetResult(knowledge_asset=_record(db, row), created=True)


def archive_knowledge_asset(
    db: Session,
    knowledge_asset_id: str,
) -> KnowledgeAssetRecord:
    row = (
        db.query(KnowledgeAsset)
        .filter(KnowledgeAsset.id == knowledge_asset_id)
        .with_for_update()
        .first()
    )
    if row is None:
        raise KnowledgeAssetRowNotFound(knowledge_asset_id)
    if row.status != "archived":
        row.status = "archived"
        row.updated_at = datetime.now(UTC)
        (
            db.query(P2KnowledgeIndexEntry)
            .filter(
                P2KnowledgeIndexEntry.knowledge_asset_id == knowledge_asset_id,
                P2KnowledgeIndexEntry.status != "archived",
            )
            .update(
                {
                    "status": "archived",
                    "sync_state": "archived",
                    "error_message": None,
                    "updated_at": row.updated_at,
                },
                synchronize_session=False,
            )
        )
        db.commit()
        db.refresh(row)
    return _record(db, row)


def list_knowledge_assets(
    db: Session,
    *,
    page: int,
    page_size: int,
    asset_id: str | None = None,
    status: str | None = None,
) -> KnowledgeAssetList:
    filters = []
    if asset_id:
        filters.append(KnowledgeAsset.asset_id == asset_id)
    if status:
        filters.append(KnowledgeAsset.status == status)
    total = db.query(func.count(KnowledgeAsset.id)).filter(*filters).scalar() or 0
    rows = (
        db.query(
            KnowledgeAsset,
            AssetReviewSnapshot,
            ExtractionReview,
            AssetExtraction,
            Asset,
        )
        .outerjoin(
            AssetReviewSnapshot,
            AssetReviewSnapshot.id == KnowledgeAsset.source_snapshot_id,
        )
        .outerjoin(ExtractionReview, ExtractionReview.id == AssetReviewSnapshot.review_id)
        .outerjoin(AssetExtraction, AssetExtraction.id == AssetReviewSnapshot.extraction_id)
        .outerjoin(Asset, Asset.id == KnowledgeAsset.asset_id)
        .filter(*filters)
        .order_by(KnowledgeAsset.created_at.desc(), KnowledgeAsset.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return KnowledgeAssetList(
        knowledge_assets=[
            _record_from_rows(
                knowledge_asset,
                _source_trace_from_rows(
                    knowledge_asset,
                    snapshot,
                    review,
                    extraction,
                    asset,
                ),
            )
            for knowledge_asset, snapshot, review, extraction, asset in rows
        ],
        pagination=KnowledgeAssetPagination(
            page=page,
            page_size=page_size,
            total=total,
            total_pages=math.ceil(total / page_size) if total else 0,
        ),
    )

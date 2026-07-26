"""Read-only adapter from governed P1/P2 evidence to generation material."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.db_models import (
    AssetReviewSnapshot,
    ExtractionReview,
    KnowledgeAsset,
    ReviewRecord,
)
from app.p3_asset_schemas import (
    P3GenerationSourceMaterial,
    P3GenerationSourceRef,
)
from app.p3_reuse_models import ReuseSourceItem
from app.p3_source_eligibility_schemas import P3SourceType


P3_SOURCE_MATERIAL_LIMIT = 100


@dataclass(frozen=True)
class P3SourceMaterialReadError(RuntimeError):
    code: str
    message: str
    source_item_id: str

    def __str__(self) -> str:
        return self.message


def _unavailable(source: ReuseSourceItem) -> P3SourceMaterialReadError:
    return P3SourceMaterialReadError(
        "P3_ASSET_SOURCE_CONTENT_UNAVAILABLE",
        "Approved source content is unavailable.",
        source.id,
    )


def _changed(source: ReuseSourceItem) -> P3SourceMaterialReadError:
    return P3SourceMaterialReadError(
        "P3_ASSET_SOURCE_EVIDENCE_CHANGED",
        "Governed source evidence no longer matches the frozen selection.",
        source.id,
    )


def _required_text(value: object, source: ReuseSourceItem) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise _unavailable(source)
    return normalized


def _source_ref(source: ReuseSourceItem) -> P3GenerationSourceRef:
    if not source.lineage_manifest_hash:
        raise _changed(source)
    return P3GenerationSourceRef(
        source_item_id=source.id,
        source_type=source.source_type,
        source_id=source.source_id,
        source_version=source.source_version,
        approved_review_id=source.approved_review_id,
        snapshot_id=source.snapshot_id,
        knowledge_asset_id=source.knowledge_asset_id,
        content_fingerprint=source.source_fingerprint,
        lineage_manifest_hash=source.lineage_manifest_hash,
    )


def _read_p1(
    db: Session,
    source: ReuseSourceItem,
) -> P3GenerationSourceMaterial:
    if not source.approved_review_id:
        raise _changed(source)
    review = (
        db.query(ReviewRecord)
        .filter(
            ReviewRecord.id == source.approved_review_id,
            ReviewRecord.candidate_id == source.source_id,
            ReviewRecord.action == "approved",
        )
        .first()
    )
    if review is None:
        raise _unavailable(source)
    snapshot = review.snapshot_json
    if not isinstance(snapshot, dict):
        raise _unavailable(source)
    if (
        snapshot.get("candidate_id") != source.source_id
        or snapshot.get("source_type") == "raw_bad_case"
    ):
        raise _changed(source)
    title = _required_text(snapshot.get("question"), source)
    approved_content = _required_text(snapshot.get("answer"), source)
    reference = _source_ref(source)
    return P3GenerationSourceMaterial(
        source_item_id=source.id,
        source_type=source.source_type,
        source_id=source.source_id,
        source_version=source.source_version,
        title=title,
        approved_content=approved_content,
        approved_review_id=source.approved_review_id,
        snapshot_id=None,
        knowledge_asset_id=None,
        content_fingerprint=source.source_fingerprint,
        lineage_manifest_hash=reference.lineage_manifest_hash,
        source_ref=reference,
    )


def _p2_title(snapshot: AssetReviewSnapshot, approved_content: str) -> str:
    metadata = snapshot.metadata_json if isinstance(snapshot.metadata_json, dict) else {}
    for key in ("title", "topic"):
        value = str(metadata.get(key) or "").strip()
        if value:
            return value
    return next(
        (line.strip() for line in approved_content.splitlines() if line.strip()),
        approved_content,
    )[:200]


def _read_p2(
    db: Session,
    source: ReuseSourceItem,
) -> P3GenerationSourceMaterial:
    if not all(
        (
            source.approved_review_id,
            source.snapshot_id,
            source.knowledge_asset_id,
            source.source_version,
        )
    ):
        raise _changed(source)
    joined = (
        db.query(KnowledgeAsset, AssetReviewSnapshot, ExtractionReview)
        .join(
            AssetReviewSnapshot,
            AssetReviewSnapshot.id == KnowledgeAsset.source_snapshot_id,
        )
        .join(
            ExtractionReview,
            ExtractionReview.id == AssetReviewSnapshot.review_id,
        )
        .filter(
            KnowledgeAsset.id == source.knowledge_asset_id,
            KnowledgeAsset.id == source.source_id,
            KnowledgeAsset.source_snapshot_id == source.snapshot_id,
            KnowledgeAsset.version == source.source_version,
            KnowledgeAsset.status == "active",
            AssetReviewSnapshot.review_id == source.approved_review_id,
            ExtractionReview.review_status == "approved",
        )
        .first()
    )
    if joined is None:
        raise _unavailable(source)
    knowledge_asset, snapshot, _review = joined
    approved_content = _required_text(snapshot.approved_content, source)
    if knowledge_asset.content.strip() != approved_content:
        raise _changed(source)
    reference = _source_ref(source)
    return P3GenerationSourceMaterial(
        source_item_id=source.id,
        source_type=source.source_type,
        source_id=source.source_id,
        source_version=source.source_version,
        title=_p2_title(snapshot, approved_content),
        approved_content=approved_content,
        approved_review_id=source.approved_review_id,
        snapshot_id=source.snapshot_id,
        knowledge_asset_id=source.knowledge_asset_id,
        content_fingerprint=source.source_fingerprint,
        lineage_manifest_hash=reference.lineage_manifest_hash,
        source_ref=reference,
    )


def read_generation_source_material(
    db: Session,
    source: ReuseSourceItem,
) -> P3GenerationSourceMaterial:
    """Read only immutable approved content represented by a current SourceItem."""

    if source.removed_at is not None or source.source_stale:
        raise _changed(source)
    if source.source_type in {
        P3SourceType.P1_KNOWLEDGE,
        P3SourceType.APPROVED_BAD_CASE_CORRECTION,
    }:
        return _read_p1(db, source)
    if source.source_type is P3SourceType.P2_KNOWLEDGE_ASSET:
        return _read_p2(db, source)
    raise _unavailable(source)


def read_generation_source_materials(
    db: Session,
    sources: list[ReuseSourceItem],
) -> list[P3GenerationSourceMaterial]:
    if not sources:
        return []
    if len(sources) > P3_SOURCE_MATERIAL_LIMIT:
        raise P3SourceMaterialReadError(
            "P3_ASSET_LIMIT_EXCEEDED",
            "Source material count exceeds the generation limit.",
            "",
        )
    return [read_generation_source_material(db, source) for source in sources]


__all__ = [
    "P3_SOURCE_MATERIAL_LIMIT",
    "P3SourceMaterialReadError",
    "read_generation_source_material",
    "read_generation_source_materials",
]

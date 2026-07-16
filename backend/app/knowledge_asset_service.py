"""P2-M4 governance service from approved snapshots to Knowledge Assets."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.asset_repositories import get_asset
from app.extraction_repositories import get_asset_extraction
from app.knowledge_asset_repositories import (
    KnowledgeAssetRowNotFound,
    KnowledgeSourceTraceError,
    archive_knowledge_asset,
    get_knowledge_asset,
    publish_knowledge_asset,
)
from app.knowledge_asset_schemas import KnowledgeAssetRecord, PublishKnowledgeAssetResult
from app.review_repositories import get_asset_review_snapshot, get_extraction_review


class KnowledgeSnapshotNotFoundError(RuntimeError):
    pass


class KnowledgeSnapshotNotApprovedError(RuntimeError):
    pass


class KnowledgeSourceTraceInvalidError(RuntimeError):
    pass


class KnowledgeAssetNotFoundError(RuntimeError):
    pass


class KnowledgeAssetService:
    """Validates governance lineage and publishes immutable P2 knowledge versions."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def publish_snapshot(self, snapshot_id: str) -> PublishKnowledgeAssetResult:
        snapshot = get_asset_review_snapshot(self.db, snapshot_id)
        if snapshot is None:
            raise KnowledgeSnapshotNotFoundError(snapshot_id)

        review = get_extraction_review(self.db, snapshot.review_id)
        if review is None or review.review_status != "approved":
            raise KnowledgeSnapshotNotApprovedError(snapshot_id)

        extraction = get_asset_extraction(self.db, snapshot.extraction_id)
        asset = get_asset(self.db, snapshot.asset_id)
        if extraction is None or asset is None:
            raise KnowledgeSourceTraceInvalidError("Snapshot source is incomplete.")
        if not (
            review.asset_id == snapshot.asset_id
            and review.extraction_id == snapshot.extraction_id
            and extraction.asset_id == snapshot.asset_id
        ):
            raise KnowledgeSourceTraceInvalidError("Snapshot source is inconsistent.")

        content = snapshot.approved_content.strip()
        content_type = snapshot.extract_type.strip()
        if not content or not content_type:
            raise KnowledgeSourceTraceInvalidError(
                "Snapshot content and extraction type are required."
            )

        try:
            asset_metadata = (
                asset.metadata_json if isinstance(asset.metadata_json, dict) else {}
            )
            return publish_knowledge_asset(
                self.db,
                source_snapshot_id=snapshot.id,
                asset_id=snapshot.asset_id,
                content=content,
                content_type=content_type,
                metadata_json={
                    "source_snapshot_version": snapshot.version,
                    "source_review_id": review.id,
                    "source_review_version": review.version,
                    "source_extraction_id": extraction.id,
                    "source_extraction_version": extraction.version,
                    "governance_layer": "p2_knowledge_asset",
                    "rag_synced": False,
                    "embedding_status": "not_started",
                    **(
                        {"eval_run_scope": asset_metadata["eval_run_scope"]}
                        if asset_metadata.get("eval_run_scope")
                        else {}
                    ),
                },
            )
        except KnowledgeSourceTraceError as exc:
            raise KnowledgeSourceTraceInvalidError(str(exc)) from exc

    def get_asset(self, knowledge_asset_id: str) -> KnowledgeAssetRecord:
        try:
            record = get_knowledge_asset(self.db, knowledge_asset_id)
        except KnowledgeSourceTraceError as exc:
            raise KnowledgeSourceTraceInvalidError(str(exc)) from exc
        if record is None:
            raise KnowledgeAssetNotFoundError(knowledge_asset_id)
        return record

    def archive(self, knowledge_asset_id: str) -> KnowledgeAssetRecord:
        try:
            return archive_knowledge_asset(self.db, knowledge_asset_id)
        except KnowledgeAssetRowNotFound as exc:
            raise KnowledgeAssetNotFoundError(knowledge_asset_id) from exc
        except KnowledgeSourceTraceError as exc:
            raise KnowledgeSourceTraceInvalidError(str(exc)) from exc


__all__ = [
    "KnowledgeAssetNotFoundError",
    "KnowledgeAssetService",
    "KnowledgeSnapshotNotApprovedError",
    "KnowledgeSnapshotNotFoundError",
    "KnowledgeSourceTraceInvalidError",
]

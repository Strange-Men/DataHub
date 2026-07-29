"""Governed orchestration for deterministic P3 JSONL/CSV exports."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app import p3_export_repositories as repositories
from app import p3_publication_repositories as publication_repositories
from app import p3_review_repositories as review_repositories
from app.p3_export_models import P3ExportFormat, P3ExportJobStatus
from app.p3_export_schemas import (
    P3_EXPORT_POLICY_VERSION,
    P3_EXPORT_SCHEMA_VERSION,
    P3ExportManifest,
    P3ExportOutcome,
    P3ExportRevokeOutcome,
    export_outcome,
)
from app.p3_export_serializers import (
    P3ExportSerializationError,
    canonical_json,
    serialize_asset_payload,
)
from app.p3_export_storage import (
    P3ExportArtifactStorage,
    P3ExportStorageError,
    get_p3_export_storage,
)
from app.p3_publication_service import (
    P3PublicationService,
    P3PublicationServiceError,
)
from app.p3_review_service import P3ReviewServiceError
from app.p3_reuse_models import (
    ReuseAssetVersion,
    ReuseAssetVersionStatus,
    ReuseProject,
    ReuseProjectStatus,
    ReuseReview,
)
from app.p3_reuse_repositories import (
    P3RepositoryConflict,
    P3RepositoryNotFound,
    P3RepositoryValidationError,
)


@dataclass(frozen=True)
class P3ExportServiceError(RuntimeError):
    code: str
    message: str
    context: dict[str, str]

    def __str__(self) -> str:
        return self.message


def _error(code: str, message: str, **context: str) -> P3ExportServiceError:
    return P3ExportServiceError(code, message, context)


def _sha256(content: bytes | str) -> str:
    encoded = content.encode("utf-8") if isinstance(content, str) else content
    return hashlib.sha256(encoded).hexdigest()


class P3ExportService:
    """Recheck published governance, then create one immutable local Artifact."""

    def __init__(
        self,
        db: Session,
        *,
        storage: P3ExportArtifactStorage | None = None,
    ) -> None:
        self.db = db
        self.publication_service = P3PublicationService(db)
        self.storage = storage or get_p3_export_storage()

    @staticmethod
    def _require_admin(actor_role: str) -> None:
        if actor_role != "admin":
            raise _error(
                "P3_EXPORT_ROLE_FORBIDDEN",
                "Only admin may manage P3 exports.",
            )

    def _project_asset_review(
        self,
        *,
        project_id: str,
        asset_version_id: str,
    ) -> tuple[ReuseProject, ReuseAssetVersion, ReuseReview]:
        project = self.publication_service._project(project_id)
        if project.status is not ReuseProjectStatus.ACTIVE:
            raise _error(
                "P3_EXPORT_PROJECT_NOT_ACTIVE",
                "Only an active project may be exported.",
                project_id=project.id,
            )
        asset = self.publication_service._asset(
            project=project,
            asset_version_id=asset_version_id,
        )
        if asset.status is not ReuseAssetVersionStatus.PUBLISHED:
            raise _error(
                "P3_EXPORT_ASSET_NOT_PUBLISHED",
                "Only a published Asset Version may be exported.",
                asset_version_id=asset.id,
            )
        try:
            current = publication_repositories.get_current_published_asset(
                self.db,
                project_id=project.id,
                asset_type=asset.asset_type,
            )
        except P3RepositoryNotFound as exc:
            raise _error(
                "P3_EXPORT_ASSET_NOT_CURRENT",
                "Asset Version is not current.",
                asset_version_id=asset.id,
            ) from exc
        except (P3RepositoryValidationError, SQLAlchemyError) as exc:
            raise _error(
                "P3_EXPORT_STORAGE_FAILED",
                "Current publication evidence is unavailable.",
                asset_version_id=asset.id,
            ) from exc
        if current.id != asset.id:
            raise _error(
                "P3_EXPORT_ASSET_NOT_CURRENT",
                "Asset Version is not current.",
                asset_version_id=asset.id,
            )
        try:
            review = review_repositories.get_review_by_asset_version(
                self.db,
                asset.id,
            )
        except P3RepositoryNotFound as exc:
            raise _error(
                "P3_EXPORT_REVIEW_INVALID",
                "Approved Review evidence is required.",
                asset_version_id=asset.id,
            ) from exc
        except (P3RepositoryValidationError, SQLAlchemyError) as exc:
            raise _error(
                "P3_EXPORT_STORAGE_FAILED",
                "Review evidence is unavailable.",
                asset_version_id=asset.id,
            ) from exc
        return project, asset, review

    def _governance_gate(
        self,
        *,
        project: ReuseProject,
        asset: ReuseAssetVersion,
    ) -> None:
        try:
            self.publication_service._review_gate(asset)
            self.publication_service._governance_gate(
                project=project,
                asset=asset,
            )
        except P3PublicationServiceError as exc:
            code = {
                "P3_PUBLICATION_REVIEW_MISSING": "P3_EXPORT_REVIEW_INVALID",
                "P3_PUBLICATION_REVIEW_NOT_APPROVED": "P3_EXPORT_REVIEW_INVALID",
                "P3_PUBLICATION_REVIEW_HASH_MISMATCH": "P3_EXPORT_REVIEW_INVALID",
                "P3_PUBLICATION_CONTENT_HASH_MISMATCH": (
                    "P3_EXPORT_CONTENT_HASH_MISMATCH"
                ),
                "P3_PUBLICATION_MANIFEST_MISMATCH": (
                    "P3_EXPORT_MANIFEST_MISMATCH"
                ),
                "P3_PUBLICATION_SOURCE_STALE": "P3_EXPORT_SOURCE_STALE",
                "P3_PUBLICATION_SOURCE_EVIDENCE_CHANGED": (
                    "P3_EXPORT_SOURCE_EVIDENCE_CHANGED"
                ),
                "P3_PUBLICATION_GROUNDING_INVALID": (
                    "P3_EXPORT_GROUNDING_INVALID"
                ),
            }.get(exc.code, "P3_EXPORT_GROUNDING_INVALID")
            raise _error(
                code,
                "Asset failed the governed export gate.",
                asset_version_id=asset.id,
            ) from exc

    def _snapshot_refs(self, asset: ReuseAssetVersion) -> list[dict[str, object]]:
        snapshots = self.publication_service.review_service._snapshots(asset)
        refs = [
            {
                "source_item_id": row.source_item_id,
                "source_type": row.source_type.value,
                "source_id": row.source_id,
                "source_version": row.source_version,
                "approved_review_id": row.approved_review_id,
                "snapshot_id": row.snapshot_id,
                "knowledge_asset_id": row.knowledge_asset_id,
                "content_fingerprint": row.source_fingerprint,
                "lineage_manifest_hash": row.lineage_manifest_hash,
            }
            for row in snapshots
        ]
        return sorted(
            refs,
            key=lambda item: (
                str(item["source_item_id"]),
                str(item["source_id"]),
            ),
        )

    @staticmethod
    def _request_fingerprint(
        *,
        project: ReuseProject,
        asset: ReuseAssetVersion,
        review: ReuseReview,
        export_format: P3ExportFormat,
    ) -> str:
        return _sha256(
            canonical_json(
                {
                    "project_id": project.id,
                    "asset_version_id": asset.id,
                    "asset_type": asset.asset_type.value,
                    "version_number": asset.version_number,
                    "content_hash": asset.content_hash,
                    "source_manifest_hash": asset.source_manifest_hash,
                    "review_id": review.id,
                    "export_format": export_format.value,
                    "export_policy_version": P3_EXPORT_POLICY_VERSION,
                }
            )
        )

    def _manifest(
        self,
        *,
        project: ReuseProject,
        asset: ReuseAssetVersion,
        review: ReuseReview,
        export_format: P3ExportFormat,
        encoding: str,
        row_count: int,
        source_snapshot_refs: list[dict[str, object]],
    ) -> tuple[P3ExportManifest, str]:
        manifest = P3ExportManifest(
            export_policy_version=P3_EXPORT_POLICY_VERSION,
            schema_version=P3_EXPORT_SCHEMA_VERSION,
            project_id=project.id,
            asset_version_id=asset.id,
            asset_type=asset.asset_type.value,
            version_number=asset.version_number,
            generation_mode=asset.generation_mode.value,
            content_hash=asset.content_hash,
            source_manifest_hash=asset.source_manifest_hash,
            review_id=review.id,
            review_policy_version=review.review_policy_version,
            export_format=export_format.value,
            encoding=encoding,
            row_count=row_count,
            source_snapshot_refs=source_snapshot_refs,
        )
        return manifest, _sha256(
            canonical_json(manifest.model_dump(mode="json"))
        )

    def _replay(
        self,
        *,
        idempotency_key: str,
        request_fingerprint: str,
    ) -> P3ExportOutcome | None:
        try:
            job = repositories.get_export_job_by_idempotency_key(
                self.db,
                idempotency_key,
            )
        except P3RepositoryNotFound:
            return None
        except P3RepositoryValidationError as exc:
            raise _error(
                "P3_EXPORT_IDEMPOTENCY_CONFLICT",
                "Export idempotency key is invalid.",
            ) from exc
        if job.request_fingerprint != request_fingerprint:
            raise _error(
                "P3_EXPORT_IDEMPOTENCY_CONFLICT",
                "Export idempotency key is bound to another request.",
                job_id=job.id,
            )
        artifact = None
        if job.status in {
            P3ExportJobStatus.SUCCEEDED,
            P3ExportJobStatus.REVOKED,
        }:
            try:
                artifact = repositories.get_export_artifact_by_job_id(
                    self.db,
                    job.id,
                )
            except P3RepositoryNotFound as exc:
                raise _error(
                    "P3_EXPORT_ARTIFACT_NOT_FOUND",
                    "Export Artifact metadata is unavailable.",
                    job_id=job.id,
                ) from exc
        return export_outcome(job, artifact, replayed=True)

    def create_export(
        self,
        *,
        project_id: str,
        asset_version_id: str,
        export_format: P3ExportFormat,
        idempotency_key: str,
        actor_role: str,
        request_id: str,
    ) -> P3ExportOutcome:
        self._require_admin(actor_role)
        if not isinstance(export_format, P3ExportFormat):
            raise _error(
                "P3_EXPORT_FORMAT_UNSUPPORTED",
                "Export format is unsupported.",
            )
        try:
            project, asset, review = self._project_asset_review(
                project_id=project_id,
                asset_version_id=asset_version_id,
            )
        except P3PublicationServiceError as exc:
            raise _error(
                "P3_EXPORT_ASSET_NOT_FOUND",
                "Requested export Asset was not found.",
                asset_version_id=asset_version_id,
            ) from exc
        fingerprint = self._request_fingerprint(
            project=project,
            asset=asset,
            review=review,
            export_format=export_format,
        )
        replay = self._replay(
            idempotency_key=idempotency_key,
            request_fingerprint=fingerprint,
        )
        if replay is not None:
            return replay
        self._governance_gate(project=project, asset=asset)
        try:
            source_snapshot_refs = self._snapshot_refs(asset)
        except P3ReviewServiceError as exc:
            raise _error(
                "P3_EXPORT_MANIFEST_MISMATCH",
                "Source snapshot Manifest is unavailable.",
                asset_version_id=asset.id,
            ) from exc
        try:
            created = repositories.create_pending_export_job(
                self.db,
                project_id=project.id,
                asset_version_id=asset.id,
                export_format=export_format,
                export_policy_version=P3_EXPORT_POLICY_VERSION,
                requested_by_role=actor_role,
                request_id=request_id,
                idempotency_key=idempotency_key,
                request_fingerprint=fingerprint,
            )
        except P3RepositoryConflict as exc:
            raise _error(
                "P3_EXPORT_IDEMPOTENCY_CONFLICT",
                "Export idempotency conflict.",
            ) from exc
        except (P3RepositoryValidationError, SQLAlchemyError) as exc:
            raise _error(
                "P3_EXPORT_STORAGE_FAILED",
                "Export persistence is unavailable.",
            ) from exc
        if created.replayed:
            return export_outcome(
                created.job,
                created.artifact,
                replayed=True,
            )
        job = created.job
        written_storage_key: str | None = None
        try:
            repositories.mark_export_job_running(self.db, job.id)
            serialized = serialize_asset_payload(
                asset_type=asset.asset_type,
                content_payload=asset.content_payload,
                export_format=export_format,
            )
            manifest, manifest_hash = self._manifest(
                project=project,
                asset=asset,
                review=review,
                export_format=export_format,
                encoding=serialized.encoding,
                row_count=serialized.row_count,
                source_snapshot_refs=source_snapshot_refs,
            )
            del manifest
            storage_key = (
                f"exports/{asset.id}/{job.id}.{serialized.extension}"
            )
            safe_file_name = (
                f"{asset.asset_type.value}-v{asset.version_number}."
                f"{serialized.extension}"
            )
            stored = self.storage.write_atomic(
                storage_key,
                serialized.content,
            )
            written_storage_key = stored.storage_key
            completed = repositories.complete_export_job(
                self.db,
                job_id=job.id,
                storage_backend=stored.storage_backend,
                storage_key=stored.storage_key,
                safe_file_name=safe_file_name,
                content_type=serialized.content_type,
                encoding=serialized.encoding,
                byte_size=stored.byte_size,
                row_count=serialized.row_count,
                artifact_sha256=_sha256(serialized.content),
                export_manifest_hash=manifest_hash,
            )
            return export_outcome(completed.job, completed.artifact)
        except P3ExportSerializationError as exc:
            repositories.fail_export_job(
                self.db,
                job_id=job.id,
                failure_code="P3_EXPORT_SERIALIZATION_FAILED",
                failure_message="Export serialization failed.",
            )
            raise _error(
                "P3_EXPORT_SERIALIZATION_FAILED",
                "Export serialization failed.",
                job_id=job.id,
            ) from exc
        except P3ExportStorageError as exc:
            repositories.fail_export_job(
                self.db,
                job_id=job.id,
                failure_code="P3_EXPORT_STORAGE_FAILED",
                failure_message="Export Artifact storage failed.",
            )
            raise _error(
                "P3_EXPORT_STORAGE_FAILED",
                "Export Artifact storage failed.",
                job_id=job.id,
            ) from exc
        except (P3RepositoryConflict, P3RepositoryValidationError, SQLAlchemyError) as exc:
            if written_storage_key is not None:
                try:
                    self.storage.cleanup_incomplete(written_storage_key)
                except P3ExportStorageError:
                    pass
            try:
                current = repositories.get_export_job_by_id(self.db, job.id)
                if current.status in {
                    P3ExportJobStatus.PENDING,
                    P3ExportJobStatus.RUNNING,
                }:
                    repositories.fail_export_job(
                        self.db,
                        job_id=job.id,
                        failure_code="P3_EXPORT_SERIALIZATION_FAILED",
                        failure_message="Export could not be completed.",
                    )
            except (
                P3RepositoryConflict,
                P3RepositoryNotFound,
                P3RepositoryValidationError,
                SQLAlchemyError,
            ):
                pass
            raise _error(
                "P3_EXPORT_SERIALIZATION_FAILED",
                "Export could not be completed.",
                job_id=job.id,
            ) from exc

    def revoke_export(
        self,
        *,
        job_id: str,
        idempotency_key: str,
        actor_role: str,
        request_id: str,
    ) -> P3ExportRevokeOutcome:
        self._require_admin(actor_role)
        try:
            replay = repositories.get_export_job_by_revoke_idempotency_key(
                self.db,
                idempotency_key,
            )
        except P3RepositoryNotFound:
            replay = None
        except P3RepositoryValidationError as exc:
            raise _error(
                "P3_EXPORT_IDEMPOTENCY_CONFLICT",
                "Revoke idempotency key is invalid.",
                job_id=job_id,
            ) from exc
        if replay is not None:
            if replay.id != job_id:
                raise _error(
                    "P3_EXPORT_IDEMPOTENCY_CONFLICT",
                    "Revoke idempotency key is bound to another Export Job.",
                    job_id=job_id,
                )
            try:
                artifact = repositories.get_export_artifact_by_job_id(
                    self.db,
                    replay.id,
                )
            except P3RepositoryNotFound as exc:
                raise _error(
                    "P3_EXPORT_ARTIFACT_NOT_FOUND",
                    "Export Artifact metadata is unavailable.",
                    job_id=replay.id,
                ) from exc
            return P3ExportRevokeOutcome(
                job=replay,
                artifact=artifact,
                replayed=True,
            )
        try:
            result = repositories.revoke_succeeded_export(
                self.db,
                job_id=job_id,
                actor_role=actor_role,
                request_id=request_id,
                idempotency_key=idempotency_key,
            )
        except P3RepositoryNotFound as exc:
            raise _error(
                "P3_EXPORT_JOB_NOT_FOUND",
                "Export Job was not found.",
                job_id=job_id,
            ) from exc
        except P3RepositoryConflict as exc:
            raise _error(
                "P3_EXPORT_JOB_STATE_INVALID",
                "Export Job cannot be revoked.",
                job_id=job_id,
            ) from exc
        except (P3RepositoryValidationError, SQLAlchemyError) as exc:
            raise _error(
                "P3_EXPORT_STORAGE_FAILED",
                "Export revoke persistence is unavailable.",
                job_id=job_id,
            ) from exc
        assert result.artifact is not None
        return P3ExportRevokeOutcome(
            job=result.job,
            artifact=result.artifact,
            replayed=result.replayed,
        )


__all__ = ["P3ExportService", "P3ExportServiceError"]

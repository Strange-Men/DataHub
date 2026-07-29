"""Governed orchestration for deterministic P3 JSONL/CSV exports."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app import p3_export_repositories as repositories
from app import p3_publication_repositories as publication_repositories
from app import p3_review_repositories as review_repositories
from app.p3_export_models import (
    P3ExportArtifact,
    P3ExportFormat,
    P3ExportJob,
    P3ExportJobStatus,
)
from app.p3_export_schemas import (
    P3_EXPORT_POLICY_VERSION,
    P3_EXPORT_SCHEMA_VERSION,
    P3ExportArtifactMetadata,
    P3ExportDownload,
    P3ExportJobMetadata,
    P3ExportJobPage,
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
    ReuseAssetType,
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

    def get_export_job(self, export_job_id: str) -> P3ExportJobMetadata:
        try:
            job = repositories.get_export_job_by_id(
                self.db,
                export_job_id,
            )
        except P3RepositoryNotFound as exc:
            raise _error(
                "P3_EXPORT_JOB_NOT_FOUND",
                "Export Job was not found.",
                export_job_id=export_job_id,
            ) from exc
        except (P3RepositoryValidationError, SQLAlchemyError) as exc:
            raise _error(
                "P3_EXPORT_STORAGE_FAILED",
                "Export Job metadata is unavailable.",
                export_job_id=export_job_id,
            ) from exc
        return P3ExportJobMetadata.model_validate(job)

    def list_project_exports(
        self,
        *,
        project_id: str,
        export_format: P3ExportFormat | None = None,
        status: P3ExportJobStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> P3ExportJobPage:
        try:
            self.publication_service._project(project_id)
            page = repositories.list_export_jobs(
                self.db,
                project_id=project_id,
                export_format=export_format,
                status=status,
                limit=limit,
                offset=offset,
            )
        except P3PublicationServiceError as exc:
            raise _error(
                "P3_EXPORT_PROJECT_NOT_FOUND",
                "Reuse project was not found.",
                project_id=project_id,
            ) from exc
        except (P3RepositoryValidationError, SQLAlchemyError) as exc:
            raise _error(
                "P3_EXPORT_STORAGE_FAILED",
                "Export Job list is unavailable.",
                project_id=project_id,
            ) from exc
        return P3ExportJobPage(
            items=[
                P3ExportJobMetadata.model_validate(item)
                for item in page.items
            ],
            total=page.total,
            limit=page.limit,
            offset=page.offset,
        )

    def _artifact_eligibility(
        self,
        *,
        project: ReuseProject,
        asset_version_id: str,
        asset_type: ReuseAssetType,
    ) -> tuple[bool, bool]:
        source_stale, sources_eligible = (
            self.publication_service._project_reuse_eligibility(project)
        )
        if not sources_eligible:
            return source_stale, False
        try:
            current = publication_repositories.get_current_published_asset(
                self.db,
                project_id=project.id,
                asset_type=asset_type,
            )
        except P3RepositoryNotFound:
            return source_stale, False
        except (P3RepositoryValidationError, SQLAlchemyError) as exc:
            raise _error(
                "P3_EXPORT_STORAGE_FAILED",
                "Current publication metadata is unavailable.",
                asset_version_id=asset_version_id,
            ) from exc
        return source_stale, current.id == asset_version_id

    def _artifact_metadata(
        self,
        *,
        job: P3ExportJob,
        artifact: P3ExportArtifact,
    ) -> P3ExportArtifactMetadata:
        project = self.publication_service._project(job.project_id)
        asset = self.publication_service._asset(
            project=project,
            asset_version_id=job.asset_version_id,
        )
        source_stale, current_eligible = self._artifact_eligibility(
            project=project,
            asset_version_id=job.asset_version_id,
            asset_type=asset.asset_type,
        )
        return P3ExportArtifactMetadata(
            id=artifact.id,
            export_job_id=artifact.export_job_id,
            asset_version_id=artifact.asset_version_id,
            export_format=artifact.export_format,
            safe_file_name=artifact.safe_file_name,
            content_type=artifact.content_type,
            encoding=artifact.encoding,
            byte_size=artifact.byte_size,
            row_count=artifact.row_count,
            artifact_sha256=artifact.artifact_sha256,
            export_manifest_hash=artifact.export_manifest_hash,
            created_at=artifact.created_at,
            revoked_at=artifact.revoked_at,
            source_stale=source_stale,
            current_reuse_eligible=(
                current_eligible
                and job.status is P3ExportJobStatus.SUCCEEDED
            ),
        )

    def get_export_artifact(
        self,
        export_job_id: str,
    ) -> P3ExportArtifactMetadata:
        try:
            job = repositories.get_export_job_by_id(
                self.db,
                export_job_id,
            )
            artifact = repositories.get_export_artifact_by_job_id(
                self.db,
                job.id,
            )
            return self._artifact_metadata(job=job, artifact=artifact)
        except P3RepositoryNotFound as exc:
            raise _error(
                "P3_EXPORT_ARTIFACT_NOT_FOUND",
                "Export Artifact was not found.",
                export_job_id=export_job_id,
            ) from exc
        except P3PublicationServiceError as exc:
            raise _error(
                "P3_EXPORT_STORAGE_FAILED",
                "Export Artifact governance metadata is unavailable.",
                export_job_id=export_job_id,
            ) from exc
        except (P3RepositoryValidationError, SQLAlchemyError) as exc:
            raise _error(
                "P3_EXPORT_STORAGE_FAILED",
                "Export Artifact metadata is unavailable.",
                export_job_id=export_job_id,
            ) from exc

    def get_artifact_download(self, artifact_id: str) -> P3ExportDownload:
        try:
            artifact = repositories.get_export_artifact_by_id(
                self.db,
                artifact_id,
            )
            job = repositories.get_export_job_by_id(
                self.db,
                artifact.export_job_id,
            )
        except P3RepositoryNotFound as exc:
            raise _error(
                "P3_EXPORT_ARTIFACT_NOT_FOUND",
                "Export Artifact was not found.",
                artifact_id=artifact_id,
            ) from exc
        except (P3RepositoryValidationError, SQLAlchemyError) as exc:
            raise _error(
                "P3_EXPORT_STORAGE_FAILED",
                "Export Artifact metadata is unavailable.",
                artifact_id=artifact_id,
            ) from exc
        if (
            job.status is P3ExportJobStatus.REVOKED
            or artifact.revoked_at is not None
        ):
            raise _error(
                "P3_EXPORT_ARTIFACT_REVOKED",
                "Export Artifact has been revoked.",
                artifact_id=artifact.id,
            )
        if job.status is not P3ExportJobStatus.SUCCEEDED:
            raise _error(
                "P3_EXPORT_JOB_STATE_INVALID",
                "Export Artifact is not available for download.",
                export_job_id=job.id,
            )
        if (
            not re.fullmatch(
                r"[a-z0-9][a-z0-9._-]{0,254}",
                artifact.safe_file_name,
            )
            or ".." in artifact.safe_file_name
        ):
            raise _error(
                "P3_EXPORT_STORAGE_FAILED",
                "Export Artifact file name is invalid.",
                artifact_id=artifact.id,
            )
        try:
            stat = self.storage.stat(artifact.storage_key)
            if stat.byte_size != artifact.byte_size:
                raise P3ExportStorageError(
                    "Export Artifact size verification failed."
                )
            with self.storage.open_read(artifact.storage_key) as handle:
                content = handle.read()
        except P3ExportStorageError as exc:
            raise _error(
                "P3_EXPORT_STORAGE_FAILED",
                "Export Artifact file is unavailable.",
                artifact_id=artifact.id,
            ) from exc
        if (
            len(content) != artifact.byte_size
            or _sha256(content) != artifact.artifact_sha256
        ):
            raise _error(
                "P3_EXPORT_STORAGE_FAILED",
                "Export Artifact integrity verification failed.",
                artifact_id=artifact.id,
            )
        return P3ExportDownload(
            content=content,
            safe_file_name=artifact.safe_file_name,
            content_type=artifact.content_type,
            artifact_sha256=artifact.artifact_sha256,
            byte_size=artifact.byte_size,
        )


__all__ = ["P3ExportService", "P3ExportServiceError"]

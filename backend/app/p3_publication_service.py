"""Business orchestration for governed P3 asset publication."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, TypeVar

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app import p3_asset_repositories as asset_repositories
from app import p3_publication_repositories as publication_repositories
from app import p3_review_repositories as review_repositories
from app.p3_publication_schemas import (
    P3PublicationOutcome,
    P3PublishedAssetPage,
    P3PublishedAssetSummary,
)
from app.p3_review_schemas import (
    P3_REVIEW_POLICY_VERSION,
    P3ReviewChecklist,
)
from app.p3_review_service import P3ReviewService, P3ReviewServiceError
from app.p3_reuse_models import (
    ReuseAssetType,
    ReuseAssetVersion,
    ReuseAssetVersionStatus,
    ReuseGenerationMode,
    ReuseProject,
    ReuseProjectStatus,
    ReuseReviewDecision,
)
from app.p3_reuse_repositories import (
    DEFAULT_PAGE_LIMIT,
    P3RepositoryConflict,
    P3RepositoryNotFound,
    P3RepositoryValidationError,
)
from app.p3_reuse_service import P3ReuseService, P3ServiceError


_T = TypeVar("_T")
_ARCHIVABLE_STATES = frozenset(
    {
        ReuseAssetVersionStatus.APPROVED,
        ReuseAssetVersionStatus.PUBLISHED,
        ReuseAssetVersionStatus.SUPERSEDED,
    }
)


@dataclass(frozen=True)
class P3PublicationServiceError(RuntimeError):
    code: str
    message: str
    context: dict[str, str]

    def __str__(self) -> str:
        return self.message


def _error(
    code: str,
    message: str,
    **context: str,
) -> P3PublicationServiceError:
    return P3PublicationServiceError(code, message, context)


def _repository_call(
    operation: Callable[..., _T],
    *args: object,
    not_found_code: str = "P3_PUBLICATION_ASSET_NOT_FOUND",
    conflict_code: str = "P3_PUBLICATION_IDEMPOTENCY_CONFLICT",
    validation_code: str = "P3_PUBLICATION_ASSET_STATE_INVALID",
    context: dict[str, str] | None = None,
    **kwargs: object,
) -> _T:
    safe_context = context or {}
    try:
        return operation(*args, **kwargs)
    except P3RepositoryNotFound as exc:
        raise _error(
            not_found_code,
            "Requested P3 publication resource was not found.",
            **safe_context,
        ) from exc
    except P3RepositoryConflict as exc:
        raise _error(
            conflict_code,
            "P3 asset publication conflict.",
            **safe_context,
        ) from exc
    except P3RepositoryValidationError as exc:
        raise _error(
            validation_code,
            "P3 asset publication input is invalid.",
            **safe_context,
        ) from exc
    except SQLAlchemyError as exc:
        raise _error(
            "P3_PUBLICATION_STORAGE_UNAVAILABLE",
            "P3 asset publication persistence is unavailable.",
            **safe_context,
        ) from exc


class P3PublicationService:
    """Validate approved governance evidence before atomic publication."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.reuse_service = P3ReuseService(db)
        self.review_service = P3ReviewService(db)

    @staticmethod
    def _require_admin(actor_role: str) -> None:
        if actor_role != "admin":
            raise _error(
                "P3_PUBLICATION_ROLE_FORBIDDEN",
                "Only the admin role may publish or archive P3 assets.",
            )

    def _project(self, project_id: str) -> ReuseProject:
        try:
            return self.reuse_service.get_project(project_id)
        except P3ServiceError as exc:
            raise _error(
                "P3_PUBLICATION_ASSET_NOT_FOUND",
                "Reuse project was not found.",
                project_id=project_id,
            ) from exc

    @staticmethod
    def _require_active(project: ReuseProject) -> None:
        if project.status is not ReuseProjectStatus.ACTIVE:
            raise _error(
                "P3_PUBLICATION_PROJECT_NOT_ACTIVE",
                "Only an active reuse project may publish assets.",
                project_id=project.id,
                project_status=project.status.value,
            )

    def _asset(
        self,
        *,
        project: ReuseProject,
        asset_version_id: str,
    ) -> ReuseAssetVersion:
        row = _repository_call(
            asset_repositories.get_asset_version_by_id,
            self.db,
            asset_version_id,
            context={
                "project_id": project.id,
                "asset_version_id": asset_version_id,
            },
        )
        if row.project_id != project.id:
            raise _error(
                "P3_PUBLICATION_ASSET_NOT_FOUND",
                "Asset version was not found in the requested project.",
                project_id=project.id,
                asset_version_id=asset_version_id,
            )
        return row

    @staticmethod
    def _validate_supported_identity(asset: ReuseAssetVersion) -> None:
        if not isinstance(asset.asset_type, ReuseAssetType):
            raise _error(
                "P3_PUBLICATION_ASSET_STATE_INVALID",
                "Asset type is not supported for publication.",
                asset_version_id=asset.id,
            )
        if not isinstance(asset.generation_mode, ReuseGenerationMode):
            raise _error(
                "P3_PUBLICATION_ASSET_STATE_INVALID",
                "Generation mode is not supported for publication.",
                asset_version_id=asset.id,
            )

    def _review_gate(self, asset: ReuseAssetVersion) -> None:
        try:
            review = review_repositories.get_review_by_asset_version(
                self.db,
                asset.id,
            )
        except P3RepositoryNotFound as exc:
            raise _error(
                "P3_PUBLICATION_REVIEW_MISSING",
                "An approved human Review is required for publication.",
                asset_version_id=asset.id,
            ) from exc
        except (P3RepositoryValidationError, SQLAlchemyError) as exc:
            raise _error(
                "P3_PUBLICATION_STORAGE_UNAVAILABLE",
                "Review evidence could not be read safely.",
                asset_version_id=asset.id,
            ) from exc
        if review.decision is not ReuseReviewDecision.APPROVED:
            raise _error(
                "P3_PUBLICATION_REVIEW_NOT_APPROVED",
                "The final human Review is not approved.",
                asset_version_id=asset.id,
            )
        if review.review_policy_version != P3_REVIEW_POLICY_VERSION:
            raise _error(
                "P3_PUBLICATION_REVIEW_NOT_APPROVED",
                "The Review policy is not approved for publication.",
                asset_version_id=asset.id,
            )
        try:
            checklist = P3ReviewChecklist.model_validate(
                review.checklist_payload
            )
        except ValidationError as exc:
            raise _error(
                "P3_PUBLICATION_REVIEW_NOT_APPROVED",
                "The Review checklist is invalid.",
                asset_version_id=asset.id,
            ) from exc
        if not checklist.all_confirmed:
            raise _error(
                "P3_PUBLICATION_REVIEW_NOT_APPROVED",
                "The Review checklist is incomplete.",
                asset_version_id=asset.id,
            )
        if (
            review.reviewed_content_hash != asset.content_hash
            or review.reviewed_source_manifest_hash
            != asset.source_manifest_hash
        ):
            raise _error(
                "P3_PUBLICATION_REVIEW_HASH_MISMATCH",
                "Review hashes do not match the approved asset version.",
                asset_version_id=asset.id,
            )

    def _governance_gate(
        self,
        *,
        project: ReuseProject,
        asset: ReuseAssetVersion,
    ) -> None:
        try:
            allowed_refs = self.review_service._validate_source_evidence(
                project=project,
                version=asset,
            )
        except P3ReviewServiceError as exc:
            code = {
                "P3_REVIEW_SOURCE_STALE": "P3_PUBLICATION_SOURCE_STALE",
                "P3_REVIEW_SOURCE_EVIDENCE_CHANGED": (
                    "P3_PUBLICATION_SOURCE_EVIDENCE_CHANGED"
                ),
            }.get(exc.code, "P3_PUBLICATION_SOURCE_EVIDENCE_CHANGED")
            raise _error(
                code,
                "Source governance no longer permits publication.",
                asset_version_id=asset.id,
            ) from exc
        try:
            self.review_service._validate_content(
                asset,
                asset.content_payload,
                allowed_refs,
                require_saved_hash=True,
            )
        except P3ReviewServiceError as exc:
            code = {
                "P3_REVIEW_CONTENT_HASH_MISMATCH": (
                    "P3_PUBLICATION_CONTENT_HASH_MISMATCH"
                ),
                "P3_REVIEW_SOURCE_EVIDENCE_CHANGED": (
                    "P3_PUBLICATION_MANIFEST_MISMATCH"
                ),
                "P3_REVIEW_SOURCE_STALE": "P3_PUBLICATION_SOURCE_STALE",
            }.get(exc.code, "P3_PUBLICATION_GROUNDING_INVALID")
            raise _error(
                code,
                "Asset content failed the publication governance gate.",
                asset_version_id=asset.id,
            ) from exc

    def _publish_replay(
        self,
        *,
        asset_version_id: str,
        idempotency_key: str,
    ) -> ReuseAssetVersion | None:
        try:
            existing = (
                publication_repositories
                .get_asset_by_publish_idempotency_key(
                    self.db,
                    idempotency_key,
                )
            )
        except P3RepositoryNotFound:
            return None
        except P3RepositoryValidationError as exc:
            raise _error(
                "P3_PUBLICATION_IDEMPOTENCY_CONFLICT",
                "Publish idempotency key is invalid.",
            ) from exc
        if existing.id != asset_version_id:
            raise _error(
                "P3_PUBLICATION_IDEMPOTENCY_CONFLICT",
                "Publish idempotency key is bound to another asset version.",
                asset_version_id=asset_version_id,
            )
        return existing

    def _project_reuse_eligibility(
        self,
        project: ReuseProject,
    ) -> tuple[bool, bool]:
        if project.status is not ReuseProjectStatus.ACTIVE:
            return False, False
        try:
            self.review_service._current_sources(project)
        except P3ReviewServiceError:
            return True, False
        return False, True

    @staticmethod
    def _summary(
        asset: ReuseAssetVersion,
        *,
        source_stale: bool,
        current_reuse_eligible: bool,
    ) -> P3PublishedAssetSummary:
        return P3PublishedAssetSummary(
            asset_version_id=asset.id,
            project_id=asset.project_id,
            asset_type=asset.asset_type,
            version_number=asset.version_number,
            status=asset.status,
            generation_mode=asset.generation_mode,
            published_at=asset.published_at,
            published_by_role=asset.published_by_role,
            content_hash=asset.content_hash,
            source_manifest_hash=asset.source_manifest_hash,
            superseded_by_asset_version_id=(
                asset.superseded_by_asset_version_id
            ),
            archived_at=asset.archived_at,
            source_stale=source_stale,
            current_reuse_eligible=current_reuse_eligible,
        )

    def publish_asset(
        self,
        *,
        project_id: str,
        asset_version_id: str,
        idempotency_key: str,
        actor_role: str,
        request_id: str,
    ) -> P3PublicationOutcome:
        self._require_admin(actor_role)
        replay = self._publish_replay(
            asset_version_id=asset_version_id,
            idempotency_key=idempotency_key,
        )
        if replay is not None:
            project = self._project(project_id)
            if replay.project_id != project.id:
                raise _error(
                    "P3_PUBLICATION_ASSET_NOT_FOUND",
                    "Asset version was not found in the requested project.",
                    project_id=project.id,
                    asset_version_id=asset_version_id,
                )
            stale, eligible = self._project_reuse_eligibility(project)
            return P3PublicationOutcome(
                asset=self._summary(
                    replay,
                    source_stale=stale,
                    current_reuse_eligible=eligible,
                ),
                replayed=True,
            )
        project = self._project(project_id)
        self._require_active(project)
        asset = self._asset(
            project=project,
            asset_version_id=asset_version_id,
        )
        self._validate_supported_identity(asset)
        if asset.status is ReuseAssetVersionStatus.SUPERSEDED:
            raise _error(
                "P3_PUBLICATION_ALREADY_SUPERSEDED",
                "A superseded asset version cannot be published again.",
                asset_version_id=asset.id,
            )
        if asset.status is ReuseAssetVersionStatus.ARCHIVED:
            raise _error(
                "P3_PUBLICATION_ASSET_ARCHIVED",
                "An archived asset version cannot be published again.",
                asset_version_id=asset.id,
            )
        if asset.status is not ReuseAssetVersionStatus.APPROVED:
            raise _error(
                "P3_PUBLICATION_ASSET_STATE_INVALID",
                "Only an approved asset version may be published.",
                asset_version_id=asset.id,
                asset_status=asset.status.value,
            )
        self._review_gate(asset)
        self._governance_gate(project=project, asset=asset)
        result = _repository_call(
            publication_repositories.publish_approved_asset,
            self.db,
            asset_version_id=asset.id,
            published_by_role=actor_role,
            request_id=request_id,
            idempotency_key=idempotency_key,
            context={
                "project_id": project.id,
                "asset_version_id": asset.id,
            },
        )
        return P3PublicationOutcome(
            asset=self._summary(
                result.published,
                source_stale=False,
                current_reuse_eligible=True,
            ),
            superseded_asset_version_id=(
                result.superseded.id
                if result.superseded is not None
                else None
            ),
            replayed=result.replayed,
        )

    def _archive_replay(
        self,
        *,
        asset_version_id: str,
        idempotency_key: str,
    ) -> ReuseAssetVersion | None:
        try:
            existing = (
                publication_repositories
                .get_asset_by_archive_idempotency_key(
                    self.db,
                    idempotency_key,
                )
            )
        except P3RepositoryNotFound:
            return None
        except P3RepositoryValidationError as exc:
            raise _error(
                "P3_PUBLICATION_IDEMPOTENCY_CONFLICT",
                "Archive idempotency key is invalid.",
            ) from exc
        if existing.id != asset_version_id:
            raise _error(
                "P3_PUBLICATION_IDEMPOTENCY_CONFLICT",
                "Archive idempotency key is bound to another asset version.",
                asset_version_id=asset_version_id,
            )
        return existing

    def archive_asset(
        self,
        *,
        project_id: str,
        asset_version_id: str,
        idempotency_key: str,
        actor_role: str,
        request_id: str,
    ) -> P3PublicationOutcome:
        self._require_admin(actor_role)
        replay = self._archive_replay(
            asset_version_id=asset_version_id,
            idempotency_key=idempotency_key,
        )
        project = self._project(project_id)
        if replay is not None:
            if replay.project_id != project.id:
                raise _error(
                    "P3_PUBLICATION_ASSET_NOT_FOUND",
                    "Asset version was not found in the requested project.",
                    project_id=project.id,
                    asset_version_id=asset_version_id,
                )
            stale, _eligible = self._project_reuse_eligibility(project)
            return P3PublicationOutcome(
                asset=self._summary(
                    replay,
                    source_stale=stale,
                    current_reuse_eligible=False,
                ),
                replayed=True,
            )
        asset = self._asset(
            project=project,
            asset_version_id=asset_version_id,
        )
        if asset.status is ReuseAssetVersionStatus.ARCHIVED:
            raise _error(
                "P3_PUBLICATION_ASSET_ARCHIVED",
                "Asset version is already archived.",
                asset_version_id=asset.id,
            )
        if asset.status not in _ARCHIVABLE_STATES:
            raise _error(
                "P3_PUBLICATION_ASSET_STATE_INVALID",
                "Only approved, published, or superseded assets may be archived.",
                asset_version_id=asset.id,
                asset_status=asset.status.value,
            )
        archived = _repository_call(
            publication_repositories.archive_asset,
            self.db,
            asset_version_id=asset.id,
            archived_by_role=actor_role,
            request_id=request_id,
            idempotency_key=idempotency_key,
            context={
                "project_id": project.id,
                "asset_version_id": asset.id,
            },
        )
        stale, _eligible = self._project_reuse_eligibility(project)
        return P3PublicationOutcome(
            asset=self._summary(
                archived,
                source_stale=stale,
                current_reuse_eligible=False,
            ),
        )

    def get_current_published_asset(
        self,
        *,
        project_id: str,
        asset_type: ReuseAssetType,
    ) -> P3PublishedAssetSummary:
        project = self._project(project_id)
        asset = _repository_call(
            publication_repositories.get_current_published_asset,
            self.db,
            project_id=project.id,
            asset_type=asset_type,
            not_found_code="P3_PUBLICATION_ASSET_NOT_FOUND",
            context={"project_id": project.id},
        )
        stale, eligible = self._project_reuse_eligibility(project)
        return self._summary(
            asset,
            source_stale=stale,
            current_reuse_eligible=eligible,
        )

    def list_current_published_assets(
        self,
        *,
        project_id: str,
        asset_type: ReuseAssetType | None = None,
        limit: int = DEFAULT_PAGE_LIMIT,
        offset: int = 0,
    ) -> P3PublishedAssetPage:
        project = self._project(project_id)
        page = _repository_call(
            publication_repositories.list_current_published_assets,
            self.db,
            project_id=project.id,
            asset_type=asset_type,
            limit=limit,
            offset=offset,
            context={"project_id": project.id},
        )
        stale, eligible = self._project_reuse_eligibility(project)
        return P3PublishedAssetPage(
            items=[
                self._summary(
                    item,
                    source_stale=stale,
                    current_reuse_eligible=eligible,
                )
                for item in page.items
            ],
            total=page.total,
            limit=page.limit,
            offset=page.offset,
        )


__all__ = [
    "P3PublicationService",
    "P3PublicationServiceError",
]

"""Business orchestration for P3 manual revision and human review."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, TypeVar

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app import p3_asset_repositories as asset_repositories
from app import p3_review_repositories as review_repositories
from app.p3_asset_repositories import canonicalize_asset_content
from app.p3_asset_schemas import P3GenerationSourceRef
from app.p3_asset_service import (
    MAX_GENERATION_SOURCES,
    P3AssetService,
    P3AssetServiceError,
    build_source_manifest,
)
from app.p3_llm_draft_contract import (
    P3_LLM_DEFAULT_MAX_OUTPUT_CHARS,
    P3LLMDraftError,
)
from app.p3_llm_prompt_registry import validate_and_ground_llm_output
from app.p3_review_schemas import (
    P3_REVIEW_POLICY_VERSION,
    P3ReviewDecisionPayload,
)
from app.p3_reuse_models import (
    ReuseAssetType,
    ReuseAssetVersion,
    ReuseAssetVersionSource,
    ReuseAssetVersionStatus,
    ReuseGenerationMode,
    ReuseProject,
    ReuseProjectStatus,
    ReuseReview,
    ReuseReviewDecision,
    ReuseSourceItem,
)
from app.p3_reuse_repositories import (
    DEFAULT_PAGE_LIMIT,
    P3RepositoryConflict,
    P3RepositoryNotFound,
    P3RepositoryPage,
    P3RepositoryValidationError,
)
from app.p3_reuse_service import P3ReuseService, P3ServiceError


_T = TypeVar("_T")
_REVISION_PARENT_STATES = {
    ReuseAssetVersionStatus.GENERATED,
    ReuseAssetVersionStatus.NEEDS_REVISION,
}


@dataclass(frozen=True)
class P3ReviewServiceError(RuntimeError):
    code: str
    message: str
    context: dict[str, str]

    def __str__(self) -> str:
        return self.message


def _error(
    code: str,
    message: str,
    **context: str,
) -> P3ReviewServiceError:
    return P3ReviewServiceError(code, message, context)


def _repository_call(
    operation: Callable[..., _T],
    *args: object,
    not_found_code: str = "P3_REVIEW_ASSET_NOT_FOUND",
    conflict_code: str = "P3_REVIEW_IDEMPOTENCY_CONFLICT",
    validation_code: str = "P3_REVIEW_CONTENT_INVALID",
    context: dict[str, str] | None = None,
    **kwargs: object,
) -> _T:
    safe_context = context or {}
    try:
        return operation(*args, **kwargs)
    except P3RepositoryNotFound as exc:
        raise _error(
            not_found_code,
            "Requested P3 review resource was not found.",
            **safe_context,
        ) from exc
    except P3RepositoryConflict as exc:
        raise _error(
            conflict_code,
            "P3 review persistence conflict.",
            **safe_context,
        ) from exc
    except P3RepositoryValidationError as exc:
        raise _error(
            validation_code,
            "P3 review input is invalid.",
            **safe_context,
        ) from exc
    except SQLAlchemyError as exc:
        raise _error(
            "P3_REVIEW_STORAGE_UNAVAILABLE",
            "P3 review persistence is unavailable.",
            **safe_context,
        ) from exc


def _snapshot_reference(
    snapshot: ReuseAssetVersionSource,
) -> P3GenerationSourceRef:
    return P3GenerationSourceRef(
        source_item_id=snapshot.source_item_id,
        source_type=snapshot.source_type,
        source_id=snapshot.source_id,
        source_version=snapshot.source_version,
        approved_review_id=snapshot.approved_review_id,
        snapshot_id=snapshot.snapshot_id,
        knowledge_asset_id=snapshot.knowledge_asset_id,
        content_fingerprint=snapshot.source_fingerprint,
        lineage_manifest_hash=snapshot.lineage_manifest_hash,
    )


def _evidence_matches(
    source: ReuseSourceItem,
    snapshot: ReuseAssetVersionSource,
) -> bool:
    return all(
        (
            snapshot.source_type is source.source_type,
            snapshot.source_id == source.source_id,
            snapshot.source_version == source.source_version,
            snapshot.source_fingerprint == source.source_fingerprint,
            snapshot.approved_review_id == source.approved_review_id,
            snapshot.snapshot_id == source.snapshot_id,
            snapshot.knowledge_asset_id == source.knowledge_asset_id,
            snapshot.lineage_manifest_hash == source.lineage_manifest_hash,
            snapshot.source_trace_snapshot == source.source_trace,
        )
    )


class P3ReviewService:
    """Coordinate immutable revisions and role-level human decisions."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.reuse_service = P3ReuseService(db)
        self.asset_service = P3AssetService(db)

    def _project(self, project_id: str) -> ReuseProject:
        try:
            return self.reuse_service.get_project(project_id)
        except P3ServiceError as exc:
            raise _error(
                "P3_REVIEW_ASSET_NOT_FOUND",
                "Reuse project was not found.",
                project_id=project_id,
            ) from exc

    @staticmethod
    def _require_active(project: ReuseProject) -> None:
        if project.status is not ReuseProjectStatus.ACTIVE:
            raise _error(
                "P3_REVIEW_PROJECT_NOT_ACTIVE",
                "Only an active reuse project may use the review workflow.",
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
                "P3_REVIEW_ASSET_NOT_FOUND",
                "Asset version was not found in the requested project.",
                project_id=project.id,
                asset_version_id=asset_version_id,
            )
        return row

    def _snapshots(
        self,
        version: ReuseAssetVersion,
    ) -> list[ReuseAssetVersionSource]:
        page = _repository_call(
            asset_repositories.list_asset_version_sources,
            self.db,
            asset_version_id=version.id,
            limit=MAX_GENERATION_SOURCES,
            offset=0,
            context={"asset_version_id": version.id},
        )
        if page.total == 0 or page.total > MAX_GENERATION_SOURCES:
            raise _error(
                "P3_REVIEW_SOURCE_EVIDENCE_CHANGED",
                "Asset source snapshots are incomplete.",
                asset_version_id=version.id,
            )
        return page.items

    def _current_sources(
        self,
        project: ReuseProject,
    ) -> list[ReuseSourceItem]:
        try:
            sources = self.asset_service._project_sources(project.id)
            self.asset_service._revalidate_sources(project.id, sources)
            return sources
        except P3AssetServiceError as exc:
            code = (
                "P3_REVIEW_SOURCE_EVIDENCE_CHANGED"
                if exc.code == "P3_ASSET_SOURCE_EVIDENCE_CHANGED"
                else "P3_REVIEW_SOURCE_STALE"
            )
            raise _error(
                code,
                "Project source governance no longer permits review.",
                project_id=project.id,
            ) from exc
        except P3ServiceError as exc:
            raise _error(
                "P3_REVIEW_SOURCE_STALE",
                "Project sources could not be revalidated.",
                project_id=project.id,
            ) from exc

    def _validate_source_evidence(
        self,
        *,
        project: ReuseProject,
        version: ReuseAssetVersion,
    ) -> tuple[P3GenerationSourceRef, ...]:
        sources = self._current_sources(project)
        snapshots = self._snapshots(version)
        by_id = {source.id: source for source in sources}
        if len(by_id) != len(snapshots):
            raise _error(
                "P3_REVIEW_SOURCE_EVIDENCE_CHANGED",
                "Asset source set differs from the active project.",
                asset_version_id=version.id,
            )
        for snapshot in snapshots:
            source = by_id.get(snapshot.source_item_id)
            if source is None or not _evidence_matches(source, snapshot):
                raise _error(
                    "P3_REVIEW_SOURCE_EVIDENCE_CHANGED",
                    "Asset source evidence differs from current governance.",
                    asset_version_id=version.id,
                    source_item_id=snapshot.source_item_id,
                )
        try:
            _manifest, current_manifest_hash = build_source_manifest(sources)
        except P3AssetServiceError as exc:
            raise _error(
                "P3_REVIEW_SOURCE_EVIDENCE_CHANGED",
                "Current source manifest is incomplete.",
                asset_version_id=version.id,
            ) from exc
        if current_manifest_hash != version.source_manifest_hash:
            raise _error(
                "P3_REVIEW_SOURCE_EVIDENCE_CHANGED",
                "Asset source manifest differs from current governance.",
                asset_version_id=version.id,
            )
        return tuple(_snapshot_reference(snapshot) for snapshot in snapshots)

    @staticmethod
    def _validate_content(
        version: ReuseAssetVersion,
        payload: object,
        allowed_refs: tuple[P3GenerationSourceRef, ...],
        *,
        require_saved_hash: bool,
    ) -> tuple[dict[str, object], str]:
        try:
            normalized, content_hash = canonicalize_asset_content(payload)
        except P3RepositoryValidationError as exc:
            raise _error(
                "P3_REVIEW_CONTENT_INVALID",
                "Asset content is not canonical JSON.",
                asset_version_id=version.id,
            ) from exc
        if require_saved_hash and content_hash != version.content_hash:
            raise _error(
                "P3_REVIEW_CONTENT_HASH_MISMATCH",
                "Asset content hash no longer matches its payload.",
                asset_version_id=version.id,
            )
        try:
            grounded = validate_and_ground_llm_output(
                asset_type=version.asset_type,
                provider_payload=normalized,
                allowed_refs=allowed_refs,
                expected_source_manifest_hash=version.source_manifest_hash,
                current_source_manifest_hash=version.source_manifest_hash,
                max_output_chars=P3_LLM_DEFAULT_MAX_OUTPUT_CHARS,
            )
        except P3LLMDraftError as exc:
            code = {
                "P3_LLM_UNKNOWN_SOURCE_REF": "P3_REVIEW_SOURCE_REF_INVALID",
                "P3_LLM_GROUNDING_INCOMPLETE": (
                    "P3_REVIEW_GROUNDING_INCOMPLETE"
                ),
            }.get(exc.code, "P3_REVIEW_CONTENT_INVALID")
            raise _error(
                code,
                "Asset content failed governed review validation.",
                asset_version_id=version.id,
            ) from exc
        normalized_grounded, grounded_hash = canonicalize_asset_content(
            grounded
        )
        if require_saved_hash and grounded_hash != version.content_hash:
            raise _error(
                "P3_REVIEW_CONTENT_HASH_MISMATCH",
                "Normalized asset content differs from its saved hash.",
                asset_version_id=version.id,
            )
        return normalized_grounded, grounded_hash

    def _existing_revision_replay(
        self,
        *,
        project_id: str,
        parent_asset_version_id: str,
        content_payload: object,
        idempotency_key: str,
    ) -> ReuseAssetVersion | None:
        try:
            existing = asset_repositories.get_asset_version_by_idempotency_key(
                self.db,
                idempotency_key,
            )
        except P3RepositoryNotFound:
            return None
        except P3RepositoryValidationError as exc:
            raise _error(
                "P3_REVIEW_CONTENT_INVALID",
                "idempotency_key is invalid.",
            ) from exc
        try:
            _payload, content_hash = canonicalize_asset_content(content_payload)
        except P3RepositoryValidationError as exc:
            raise _error(
                "P3_REVIEW_CONTENT_INVALID",
                "Manual revision content is invalid.",
            ) from exc
        if any(
            (
                existing.project_id != project_id,
                existing.parent_asset_version_id != parent_asset_version_id,
                existing.generation_mode
                is not ReuseGenerationMode.MANUAL_REVISION,
                existing.content_hash != content_hash,
            )
        ):
            raise _error(
                "P3_REVIEW_IDEMPOTENCY_CONFLICT",
                "Idempotency key is bound to another manual revision.",
                asset_version_id=existing.id,
            )
        return existing

    def create_manual_revision(
        self,
        *,
        project_id: str,
        parent_asset_version_id: str,
        content_payload: dict[str, object],
        idempotency_key: str,
        actor_role: str,
        request_id: str,
    ) -> ReuseAssetVersion:
        replay = self._existing_revision_replay(
            project_id=project_id,
            parent_asset_version_id=parent_asset_version_id,
            content_payload=content_payload,
            idempotency_key=idempotency_key,
        )
        if replay is not None:
            return replay
        project = self._project(project_id)
        self._require_active(project)
        parent = self._asset(
            project=project,
            asset_version_id=parent_asset_version_id,
        )
        if parent.status not in _REVISION_PARENT_STATES:
            raise _error(
                "P3_REVIEW_PARENT_STATE_INVALID",
                "Parent state does not permit a manual revision.",
                asset_version_id=parent.id,
                asset_status=parent.status.value,
            )
        allowed_refs = self._validate_source_evidence(
            project=project,
            version=parent,
        )
        normalized_payload, _content_hash = self._validate_content(
            parent,
            content_payload,
            allowed_refs,
            require_saved_hash=False,
        )
        return _repository_call(
            review_repositories.create_manual_revision_with_snapshots,
            self.db,
            project_id=project.id,
            parent_asset_version_id=parent.id,
            content_payload=normalized_payload,
            idempotency_key=idempotency_key,
            created_by_role=actor_role,
            request_id=request_id,
            context={
                "project_id": project.id,
                "asset_version_id": parent.id,
            },
        )

    def submit_for_review(
        self,
        *,
        project_id: str,
        asset_version_id: str,
        idempotency_key: str | None = None,
    ) -> ReuseAssetVersion:
        project = self._project(project_id)
        asset = self._asset(
            project=project,
            asset_version_id=asset_version_id,
        )
        if asset.status is ReuseAssetVersionStatus.PENDING_REVIEW:
            return asset
        self._require_active(project)
        if asset.status is not ReuseAssetVersionStatus.GENERATED:
            raise _error(
                "P3_REVIEW_ASSET_STATE_INVALID",
                "Only generated content may be submitted for review.",
                asset_version_id=asset.id,
                asset_status=asset.status.value,
            )
        allowed_refs = self._validate_source_evidence(
            project=project,
            version=asset,
        )
        self._validate_content(
            asset,
            asset.content_payload,
            allowed_refs,
            require_saved_hash=True,
        )
        return _repository_call(
            review_repositories.submit_asset_for_review,
            self.db,
            asset_version_id=asset.id,
            idempotency_key=idempotency_key,
            conflict_code="P3_REVIEW_ASSET_STATE_INVALID",
            context={"asset_version_id": asset.id},
        )

    def _review_replay(
        self,
        *,
        asset_version_id: str,
        payload: P3ReviewDecisionPayload,
        idempotency_key: str,
        reviewer_role: str,
    ) -> ReuseReview | None:
        try:
            existing = review_repositories.get_review_by_idempotency_key(
                self.db,
                idempotency_key,
            )
        except P3RepositoryNotFound:
            return None
        except P3RepositoryValidationError as exc:
            raise _error(
                "P3_REVIEW_CHECKLIST_INVALID",
                "Review idempotency key is invalid.",
            ) from exc
        if any(
            (
                existing.asset_version_id != asset_version_id,
                existing.decision is not payload.decision,
                existing.comments != payload.comments,
                existing.checklist_payload
                != payload.checklist.model_dump(mode="json"),
                existing.review_policy_version != P3_REVIEW_POLICY_VERSION,
                existing.reviewer_role != reviewer_role,
            )
        ):
            raise _error(
                "P3_REVIEW_IDEMPOTENCY_CONFLICT",
                "Review idempotency key is bound to another decision.",
                asset_version_id=asset_version_id,
            )
        return existing

    def decide_review(
        self,
        *,
        project_id: str,
        asset_version_id: str,
        decision: ReuseReviewDecision,
        comments: str | None,
        checklist: dict[str, object],
        idempotency_key: str,
        reviewer_role: str,
        request_id: str,
    ) -> ReuseReview:
        try:
            payload = P3ReviewDecisionPayload.model_validate(
                {
                    "decision": decision,
                    "comments": comments,
                    "checklist": checklist,
                }
            )
        except ValidationError as exc:
            code = (
                "P3_REVIEW_COMMENTS_REQUIRED"
                if decision
                in (
                    ReuseReviewDecision.NEEDS_REVISION,
                    ReuseReviewDecision.REJECTED,
                )
                and (not isinstance(comments, str) or not comments.strip())
                else "P3_REVIEW_CHECKLIST_INVALID"
            )
            raise _error(
                code,
                "Review decision does not satisfy p3-review-v1.",
                asset_version_id=asset_version_id,
            ) from exc
        replay = self._review_replay(
            asset_version_id=asset_version_id,
            payload=payload,
            idempotency_key=idempotency_key,
            reviewer_role=reviewer_role,
        )
        if replay is not None:
            return replay
        project = self._project(project_id)
        self._require_active(project)
        asset = self._asset(
            project=project,
            asset_version_id=asset_version_id,
        )
        try:
            review_repositories.get_review_by_asset_version(self.db, asset.id)
        except P3RepositoryNotFound:
            pass
        else:
            raise _error(
                "P3_REVIEW_ALREADY_DECIDED",
                "Asset version already has a final human decision.",
                asset_version_id=asset.id,
            )
        if asset.status is not ReuseAssetVersionStatus.PENDING_REVIEW:
            raise _error(
                "P3_REVIEW_ASSET_STATE_INVALID",
                "Only pending_review content may receive a decision.",
                asset_version_id=asset.id,
                asset_status=asset.status.value,
            )
        allowed_refs = self._validate_source_evidence(
            project=project,
            version=asset,
        )
        self._validate_content(
            asset,
            asset.content_payload,
            allowed_refs,
            require_saved_hash=True,
        )
        return _repository_call(
            review_repositories.create_review_decision,
            self.db,
            asset_version_id=asset.id,
            decision=payload.decision,
            comments=payload.comments,
            checklist_payload=payload.checklist.model_dump(mode="json"),
            review_policy_version=P3_REVIEW_POLICY_VERSION,
            reviewer_role=reviewer_role,
            request_id=request_id,
            idempotency_key=idempotency_key,
            conflict_code="P3_REVIEW_ALREADY_DECIDED",
            validation_code="P3_REVIEW_CHECKLIST_INVALID",
            context={"asset_version_id": asset.id},
        )

    def get_review(
        self,
        *,
        project_id: str,
        asset_version_id: str,
    ) -> ReuseReview:
        project = self._project(project_id)
        asset = self._asset(
            project=project,
            asset_version_id=asset_version_id,
        )
        return _repository_call(
            review_repositories.get_review_by_asset_version,
            self.db,
            asset.id,
            context={"asset_version_id": asset.id},
        )

    def list_project_reviews(
        self,
        *,
        project_id: str,
        decision: ReuseReviewDecision | None = None,
        asset_type: ReuseAssetType | None = None,
        limit: int = DEFAULT_PAGE_LIMIT,
        offset: int = 0,
    ) -> P3RepositoryPage[ReuseReview]:
        project = self._project(project_id)
        return _repository_call(
            review_repositories.list_project_reviews,
            self.db,
            project_id=project.id,
            decision=decision,
            asset_type=asset_type,
            limit=limit,
            offset=offset,
            context={"project_id": project.id},
        )


__all__ = [
    "P3ReviewService",
    "P3ReviewServiceError",
]

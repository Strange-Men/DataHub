"""Business orchestration for P3 reuse projects and governed source selection."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Callable, TypeVar

from sqlalchemy.orm import Session

from app import p3_reuse_repositories as repositories
from app import p3_source_eligibility
from app.p3_reuse_models import (
    ReuseProject,
    ReuseProjectStatus,
    ReuseSourceItem,
)
from app.p3_reuse_repositories import P3RepositoryPage
from app.p3_reuse_schemas import (
    P3ProjectRevalidationResult,
    P3SourceEvidenceSnapshot,
    P3SourceRevalidationResult,
    P3SourceRevalidationStatus,
)
from app.p3_source_eligibility_schemas import (
    P3SourceEligibilityDecision,
    P3SourceEligibilityReason,
    P3SourceType,
)


MAX_PROJECT_REVALIDATION_SOURCES = 100

_T = TypeVar("_T")
_UNSET = object()


@dataclass(frozen=True)
class P3ServiceError(RuntimeError):
    """Stable, safe Service error contract."""

    code: str
    message: str
    context: dict[str, str]

    def __str__(self) -> str:
        return self.message


class P3ServiceNotFound(P3ServiceError):
    def __init__(self, message: str, **context: str) -> None:
        super().__init__("P3_NOT_FOUND", message, context)


class P3ServiceConflict(P3ServiceError):
    def __init__(self, message: str, **context: str) -> None:
        super().__init__("P3_CONFLICT", message, context)


class P3ServiceValidationError(P3ServiceError):
    def __init__(self, message: str, **context: str) -> None:
        super().__init__("P3_VALIDATION_ERROR", message, context)


class P3ProjectStateError(P3ServiceError):
    def __init__(self, message: str, **context: str) -> None:
        super().__init__("P3_PROJECT_STATE_INVALID", message, context)


class P3SourceIneligible(P3ServiceError):
    reason_code: P3SourceEligibilityReason

    def __init__(
        self,
        message: str,
        *,
        reason_code: P3SourceEligibilityReason,
        **context: str,
    ) -> None:
        super().__init__("P3_SOURCE_INELIGIBLE", message, context)
        object.__setattr__(self, "reason_code", reason_code)


class P3SourceStale(P3ServiceError):
    reason_code: P3SourceEligibilityReason

    def __init__(
        self,
        message: str,
        *,
        reason_code: P3SourceEligibilityReason,
        **context: str,
    ) -> None:
        super().__init__("P3_SOURCE_STALE", message, context)
        object.__setattr__(self, "reason_code", reason_code)


def _repository_call(
    operation: Callable[..., _T],
    *args: object,
    context: dict[str, str] | None = None,
    **kwargs: object,
) -> _T:
    safe_context = context or {}
    try:
        return operation(*args, **kwargs)
    except repositories.P3RepositoryNotFound as exc:
        raise P3ServiceNotFound(
            "Requested P3 resource was not found.",
            **safe_context,
        ) from exc
    except repositories.P3RepositoryConflict as exc:
        raise P3ServiceConflict(
            "P3 persistence conflict.",
            **safe_context,
        ) from exc
    except repositories.P3RepositoryValidationError as exc:
        raise P3ServiceValidationError(
            "P3 persistence input is invalid.",
            **safe_context,
        ) from exc


def _stable_id(prefix: str, *parts: object) -> str:
    payload = json.dumps(
        [str(part) for part in parts],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(payload).hexdigest()[:20]}"


def _evidence_snapshot(
    decision: P3SourceEligibilityDecision,
) -> P3SourceEvidenceSnapshot:
    if (
        not decision.eligible
        or not decision.content_fingerprint
        or not decision.lineage_complete
    ):
        raise P3SourceIneligible(
            "Source does not provide complete eligible evidence.",
            reason_code=decision.reason_code,
            source_id=decision.source_id,
        )
    return P3SourceEvidenceSnapshot(
        source_type=decision.source_type,
        source_id=decision.source_id,
        source_status=decision.source_status,
        source_version=decision.source_version,
        content_fingerprint=decision.content_fingerprint,
        eligibility_policy_version=decision.policy_version,
        approved_review_id=decision.approved_review_id,
        snapshot_id=decision.snapshot_id,
        knowledge_asset_id=decision.knowledge_asset_id,
        lineage_complete=decision.lineage_complete,
        checked_conditions=list(decision.checked_conditions),
    )


def _manifest_hash(evidence: P3SourceEvidenceSnapshot) -> str:
    encoded = json.dumps(
        evidence.manifest_payload(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _stale_reason(
    item: ReuseSourceItem,
    decision: P3SourceEligibilityDecision,
) -> P3SourceEligibilityReason | None:
    if not decision.eligible:
        return decision.reason_code
    if decision.source_type != item.source_type.value:
        return P3SourceEligibilityReason.SOURCE_STATE_INVALID
    if decision.source_version != item.source_version:
        return P3SourceEligibilityReason.SOURCE_NOT_CURRENT
    if decision.content_fingerprint != item.source_fingerprint:
        return P3SourceEligibilityReason.SOURCE_FINGERPRINT_MISMATCH
    if (
        decision.approved_review_id != item.approved_review_id
        or decision.snapshot_id != item.snapshot_id
        or decision.knowledge_asset_id != item.knowledge_asset_id
        or not decision.lineage_complete
    ):
        return P3SourceEligibilityReason.SOURCE_TRACE_INCOMPLETE
    if decision.policy_version != item.eligibility_policy_version:
        return P3SourceEligibilityReason.SOURCE_STATE_INVALID
    evidence = _evidence_snapshot(decision)
    if _manifest_hash(evidence) != item.lineage_manifest_hash:
        return P3SourceEligibilityReason.SOURCE_TRACE_INCOMPLETE
    return None


class P3ReuseService:
    """Enforces Project lifecycle and delegates all persistence to Repository."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create_project(
        self,
        *,
        name: str,
        description: str | None,
        idempotency_key: str,
        actor_role: str,
        request_id: str,
    ) -> ReuseProject:
        if not isinstance(idempotency_key, str) or not idempotency_key.strip():
            raise P3ServiceValidationError("idempotency_key must not be blank.")
        project_id = _stable_id("reuse_project", idempotency_key.strip())
        return _repository_call(
            repositories.create_project,
            self.db,
            project_id=project_id,
            name=name,
            description=description,
            status=ReuseProjectStatus.DRAFT,
            created_by_role=actor_role,
            request_id=request_id,
            idempotency_key=idempotency_key,
            context={"project_id": project_id},
        )

    def get_project(self, project_id: str) -> ReuseProject:
        return _repository_call(
            repositories.get_project_by_id,
            self.db,
            project_id,
            context={"project_id": project_id},
        )

    def list_projects(
        self,
        *,
        limit: int = repositories.DEFAULT_PAGE_LIMIT,
        offset: int = 0,
        status: ReuseProjectStatus | None = None,
    ) -> P3RepositoryPage[ReuseProject]:
        return _repository_call(
            repositories.list_projects,
            self.db,
            limit=limit,
            offset=offset,
            status=status,
        )

    def update_project_metadata(
        self,
        project_id: str,
        *,
        name: str | object = _UNSET,
        description: str | None | object = _UNSET,
    ) -> ReuseProject:
        project = self.get_project(project_id)
        if project.status is not ReuseProjectStatus.DRAFT:
            raise P3ProjectStateError(
                "Only draft projects may change metadata.",
                project_id=project.id,
                project_status=project.status.value,
            )
        updates: dict[str, object] = {}
        if name is not _UNSET:
            updates["name"] = name
        if description is not _UNSET:
            updates["description"] = description
        return _repository_call(
            repositories.update_project_metadata,
            self.db,
            project.id,
            context={"project_id": project.id},
            **updates,
        )

    def archive_project(self, project_id: str) -> ReuseProject:
        project = self.get_project(project_id)
        if project.status is ReuseProjectStatus.ARCHIVED:
            return project
        if project.status is not ReuseProjectStatus.ACTIVE:
            raise P3ProjectStateError(
                "Only active projects may be archived.",
                project_id=project.id,
                project_status=project.status.value,
            )
        return _repository_call(
            repositories.set_project_status,
            self.db,
            project.id,
            ReuseProjectStatus.ARCHIVED,
            context={"project_id": project.id},
        )

    def add_source_to_project(
        self,
        *,
        project_id: str,
        source_type: P3SourceType | str,
        source_id: str,
        source_version: int | None,
        expected_fingerprint: str | None,
        actor_role: str,
        request_id: str,
    ) -> ReuseSourceItem:
        project = self.get_project(project_id)
        if project.status is not ReuseProjectStatus.DRAFT:
            raise P3ProjectStateError(
                "Sources may be added only to draft projects.",
                project_id=project.id,
                project_status=project.status.value,
            )

        try:
            requested_type = P3SourceType(source_type)
        except ValueError:
            requested_type = None
        if requested_type is not None:
            history = _repository_call(
                repositories.list_project_source_items,
                self.db,
                project_id=project.id,
                limit=MAX_PROJECT_REVALIDATION_SOURCES,
                offset=0,
                include_removed=True,
                source_type=requested_type,
                context={"project_id": project.id},
            )
            if history.total > MAX_PROJECT_REVALIDATION_SOURCES:
                raise P3ServiceValidationError(
                    "Project source history exceeds the bounded identity check.",
                    project_id=project.id,
                )
            normalized_source_id = str(source_id).strip()
            removed_identity = next(
                (
                    item
                    for item in history.items
                    if item.removed_at is not None
                    and item.source_id == normalized_source_id
                    and (
                        source_version is None
                        or item.source_version == source_version
                    )
                ),
                None,
            )
            if removed_identity is not None:
                raise P3ServiceConflict(
                    "A logically removed source identity cannot be restored.",
                    project_id=project.id,
                    source_item_id=removed_identity.id,
                )

        decision = p3_source_eligibility.check_source_eligibility(
            self.db,
            {
                "source_type": source_type,
                "source_id": source_id,
                "source_version": source_version,
                "expected_fingerprint": expected_fingerprint,
            },
        )
        if not decision.eligible:
            raise P3SourceIneligible(
                "Source is not eligible for P3 reuse.",
                reason_code=decision.reason_code,
                project_id=project.id,
                source_id=decision.source_id,
            )

        evidence = _evidence_snapshot(decision)
        manifest_hash = _manifest_hash(evidence)
        try:
            governed_type = P3SourceType(decision.source_type)
        except ValueError as exc:
            raise P3ServiceValidationError(
                "Eligibility decision returned an unsupported source type.",
                project_id=project.id,
                source_id=decision.source_id,
            ) from exc
        source_version_key = evidence.source_version or 0
        try:
            existing = repositories.get_source_item_by_identity(
                self.db,
                project_id=project.id,
                source_type=governed_type,
                source_id=evidence.source_id,
                source_version_key=source_version_key,
            )
        except repositories.P3RepositoryNotFound:
            existing = None
        except repositories.P3RepositoryValidationError as exc:
            raise P3ServiceValidationError(
                "Source identity is invalid.",
                project_id=project.id,
                source_id=evidence.source_id,
            ) from exc
        if existing is not None and existing.removed_at is not None:
            raise P3ServiceConflict(
                "A logically removed source identity cannot be restored.",
                project_id=project.id,
                source_item_id=existing.id,
            )

        source_item_id = _stable_id(
            "reuse_source",
            project.id,
            governed_type.value,
            evidence.source_id,
            source_version_key,
        )
        return _repository_call(
            repositories.add_source_item,
            self.db,
            source_item_id=source_item_id,
            project_id=project.id,
            source_type=governed_type,
            source_id=evidence.source_id,
            source_version=evidence.source_version,
            source_fingerprint=evidence.content_fingerprint,
            eligibility_policy_version=evidence.eligibility_policy_version,
            approved_review_id=evidence.approved_review_id,
            snapshot_id=evidence.snapshot_id,
            knowledge_asset_id=evidence.knowledge_asset_id,
            lineage_manifest_hash=manifest_hash,
            source_trace=evidence.model_dump(mode="json"),
            selected_by_role=actor_role,
            request_id=request_id,
            context={
                "project_id": project.id,
                "source_id": evidence.source_id,
            },
        )

    def remove_source_from_project(
        self,
        *,
        project_id: str,
        source_item_id: str,
    ) -> ReuseSourceItem:
        project = self.get_project(project_id)
        if project.status is not ReuseProjectStatus.DRAFT:
            raise P3ProjectStateError(
                "Sources may be removed only from draft projects.",
                project_id=project.id,
                project_status=project.status.value,
            )
        source = _repository_call(
            repositories.get_source_item_by_id,
            self.db,
            source_item_id,
            context={"source_item_id": source_item_id},
        )
        if source.project_id != project.id:
            raise P3ServiceNotFound(
                "Source item does not belong to the requested project.",
                project_id=project.id,
                source_item_id=source.id,
            )
        return _repository_call(
            repositories.logically_remove_source_item,
            self.db,
            source.id,
            context={
                "project_id": project.id,
                "source_item_id": source.id,
            },
        )

    def _evaluate_source(
        self,
        source: ReuseSourceItem,
    ) -> P3SourceEligibilityDecision:
        return p3_source_eligibility.check_source_eligibility(
            self.db,
            {
                "source_type": source.source_type,
                "source_id": source.source_id,
                "source_version": source.source_version,
                "expected_fingerprint": source.source_fingerprint,
            },
        )

    def _revalidate_source_row(
        self,
        source: ReuseSourceItem,
    ) -> P3SourceRevalidationResult:
        if source.removed_at is not None:
            return P3SourceRevalidationResult(
                source_item_id=source.id,
                project_id=source.project_id,
                status=P3SourceRevalidationStatus.SKIPPED_REMOVED,
                eligible=False,
                reason_code=P3SourceEligibilityReason.SOURCE_STATE_INVALID,
                source_stale=source.source_stale,
            )
        decision = self._evaluate_source(source)
        stale_reason = _stale_reason(source, decision)
        if stale_reason is not None:
            stale = _repository_call(
                repositories.mark_source_stale,
                self.db,
                source.id,
                context={
                    "project_id": source.project_id,
                    "source_item_id": source.id,
                },
            )
            return P3SourceRevalidationResult(
                source_item_id=stale.id,
                project_id=stale.project_id,
                status=P3SourceRevalidationStatus.STALE,
                eligible=decision.eligible,
                reason_code=stale_reason,
                source_stale=True,
            )
        return P3SourceRevalidationResult(
            source_item_id=source.id,
            project_id=source.project_id,
            status=(
                P3SourceRevalidationStatus.STALE
                if source.source_stale
                else P3SourceRevalidationStatus.VALID
            ),
            eligible=True,
            reason_code=P3SourceEligibilityReason.ELIGIBLE,
            source_stale=source.source_stale,
        )

    def revalidate_source_item(
        self,
        *,
        project_id: str,
        source_item_id: str,
    ) -> P3SourceRevalidationResult:
        project = self.get_project(project_id)
        if project.status is ReuseProjectStatus.ARCHIVED:
            raise P3ProjectStateError(
                "Archived projects cannot revalidate sources.",
                project_id=project.id,
                project_status=project.status.value,
            )
        source = _repository_call(
            repositories.get_source_item_by_id,
            self.db,
            source_item_id,
            context={"source_item_id": source_item_id},
        )
        if source.project_id != project.id:
            raise P3ServiceNotFound(
                "Source item does not belong to the requested project.",
                project_id=project.id,
                source_item_id=source.id,
            )
        return self._revalidate_source_row(source)

    def revalidate_project_sources(
        self,
        project_id: str,
        *,
        limit: int = MAX_PROJECT_REVALIDATION_SOURCES,
    ) -> P3ProjectRevalidationResult:
        project = self.get_project(project_id)
        if project.status is ReuseProjectStatus.ARCHIVED:
            raise P3ProjectStateError(
                "Archived projects cannot revalidate sources.",
                project_id=project.id,
                project_status=project.status.value,
            )
        if limit <= 0 or limit > MAX_PROJECT_REVALIDATION_SOURCES:
            raise P3ServiceValidationError(
                "Revalidation limit must be between 1 and 100.",
                project_id=project.id,
            )
        page = _repository_call(
            repositories.list_project_source_items,
            self.db,
            project_id=project.id,
            limit=limit,
            offset=0,
            include_removed=False,
            context={"project_id": project.id},
        )
        if page.total > limit:
            raise P3ServiceValidationError(
                "Project source count exceeds the bounded revalidation limit.",
                project_id=project.id,
            )
        results = [self._revalidate_source_row(item) for item in page.items]
        return P3ProjectRevalidationResult(
            project_id=project.id,
            results=results,
            total=page.total,
            limit=limit,
        )

    def activate_project(self, project_id: str) -> ReuseProject:
        project = self.get_project(project_id)
        if project.status is ReuseProjectStatus.ACTIVE:
            return project
        if project.status is not ReuseProjectStatus.DRAFT:
            raise P3ProjectStateError(
                "Only draft projects may be activated.",
                project_id=project.id,
                project_status=project.status.value,
            )
        page = _repository_call(
            repositories.list_project_source_items,
            self.db,
            project_id=project.id,
            limit=MAX_PROJECT_REVALIDATION_SOURCES,
            offset=0,
            include_removed=False,
            context={"project_id": project.id},
        )
        if page.total == 0:
            raise P3ProjectStateError(
                "A project requires at least one current source before activation.",
                project_id=project.id,
            )
        if page.total > MAX_PROJECT_REVALIDATION_SOURCES:
            raise P3ServiceValidationError(
                "Project source count exceeds the activation validation limit.",
                project_id=project.id,
            )
        stale_source = next((item for item in page.items if item.source_stale), None)
        if stale_source is not None:
            raise P3SourceStale(
                "Project contains a stale source.",
                reason_code=P3SourceEligibilityReason.SOURCE_STATE_INVALID,
                project_id=project.id,
                source_item_id=stale_source.id,
            )

        failures: list[
            tuple[
                ReuseSourceItem,
                P3SourceEligibilityDecision,
                P3SourceEligibilityReason,
            ]
        ] = []
        for source in page.items:
            decision = self._evaluate_source(source)
            reason = _stale_reason(source, decision)
            if reason is not None:
                failures.append((source, decision, reason))
        if failures:
            for source, _decision, _reason in failures:
                _repository_call(
                    repositories.mark_source_stale,
                    self.db,
                    source.id,
                    context={
                        "project_id": project.id,
                        "source_item_id": source.id,
                    },
                )
            source, decision, reason = failures[0]
            assert reason is not None
            if decision.eligible:
                raise P3SourceStale(
                    "Project source evidence changed during activation.",
                    reason_code=reason,
                    project_id=project.id,
                    source_item_id=source.id,
                )
            raise P3SourceIneligible(
                "Project source is no longer eligible.",
                reason_code=reason,
                project_id=project.id,
                source_item_id=source.id,
            )

        return _repository_call(
            repositories.set_project_status,
            self.db,
            project.id,
            ReuseProjectStatus.ACTIVE,
            context={"project_id": project.id},
        )


__all__ = [
    "MAX_PROJECT_REVALIDATION_SOURCES",
    "P3ProjectStateError",
    "P3ReuseService",
    "P3ServiceConflict",
    "P3ServiceError",
    "P3ServiceNotFound",
    "P3ServiceValidationError",
    "P3SourceIneligible",
    "P3SourceStale",
]

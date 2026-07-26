"""Business orchestration for deterministic P3 draft-asset generation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Callable, TypeVar

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app import p3_asset_repositories as asset_repositories
from app.p3_asset_repositories import P3AssetVersionSourceSnapshotInput
from app.p3_asset_schemas import P3_ASSET_MANIFEST_SCHEMA_VERSION
from app.p3_deterministic_templates import (
    P3DeterministicTemplate,
    P3TemplateError,
    get_deterministic_template,
)
from app.p3_reuse_models import (
    ReuseAssetType,
    ReuseAssetVersion,
    ReuseAssetVersionSource,
    ReuseAssetVersionStatus,
    ReuseGenerationMode,
    ReuseProjectStatus,
    ReuseSourceItem,
)
from app.p3_reuse_repositories import (
    DEFAULT_PAGE_LIMIT,
    P3RepositoryConflict,
    P3RepositoryNotFound,
    P3RepositoryPage,
    P3RepositoryValidationError,
)
from app.p3_reuse_service import (
    P3ReuseService,
    P3ServiceError,
)
from app.p3_reuse_schemas import P3SourceRevalidationStatus
from app.p3_source_material_reader import (
    P3SourceMaterialReadError,
    read_generation_source_materials,
)


MAX_GENERATION_SOURCES = 100

_T = TypeVar("_T")


@dataclass(frozen=True)
class P3AssetServiceError(RuntimeError):
    code: str
    message: str
    context: dict[str, str]

    def __str__(self) -> str:
        return self.message


def _error(code: str, message: str, **context: str) -> P3AssetServiceError:
    return P3AssetServiceError(code, message, context)


def _repository_call(
    operation: Callable[..., _T],
    *args: object,
    conflict_code: str = "P3_ASSET_IDEMPOTENCY_CONFLICT",
    context: dict[str, str] | None = None,
    **kwargs: object,
) -> _T:
    safe_context = context or {}
    try:
        return operation(*args, **kwargs)
    except P3RepositoryNotFound as exc:
        raise _error(
            "P3_ASSET_NOT_FOUND",
            "Requested P3 draft asset was not found.",
            **safe_context,
        ) from exc
    except P3RepositoryConflict as exc:
        raise _error(
            conflict_code,
            "P3 draft asset persistence conflict.",
            **safe_context,
        ) from exc
    except P3RepositoryValidationError as exc:
        raise _error(
            "P3_ASSET_VALIDATION_ERROR",
            "P3 draft asset input is invalid.",
            **safe_context,
        ) from exc
    except SQLAlchemyError as exc:
        raise _error(
            "P3_ASSET_GENERATION_FAILED",
            "P3 draft asset persistence is unavailable.",
            **safe_context,
        ) from exc


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def build_source_manifest(
    sources: list[ReuseSourceItem],
) -> tuple[dict[str, object], str]:
    """Build a stable evidence-only manifest independent of input ordering."""

    entries = []
    for source in sources:
        if not source.lineage_manifest_hash or not isinstance(source.source_trace, dict):
            raise _error(
                "P3_ASSET_SOURCE_EVIDENCE_CHANGED",
                "Source lineage evidence is incomplete.",
                source_item_id=source.id,
            )
        entries.append(
            {
                "source_item_id": source.id,
                "source_type": source.source_type.value,
                "source_id": source.source_id,
                "source_version": source.source_version,
                "content_fingerprint": source.source_fingerprint,
                "eligibility_policy_version": source.eligibility_policy_version,
                "approved_review_id": source.approved_review_id,
                "snapshot_id": source.snapshot_id,
                "knowledge_asset_id": source.knowledge_asset_id,
                "lineage_manifest_hash": source.lineage_manifest_hash,
            }
        )
    entries.sort(
        key=lambda item: (
            str(item["source_type"]),
            str(item["source_id"]),
            int(item["source_version"] or 0),
            str(item["source_item_id"]),
        )
    )
    manifest: dict[str, object] = {
        "schema_version": P3_ASSET_MANIFEST_SCHEMA_VERSION,
        "sources": entries,
    }
    digest = hashlib.sha256(_canonical_json(manifest).encode("utf-8")).hexdigest()
    return manifest, digest


def _asset_type(value: object) -> ReuseAssetType:
    if not isinstance(value, ReuseAssetType):
        raise _error(
            "P3_ASSET_VALIDATION_ERROR",
            "asset_type must be a governed P3 asset type.",
        )
    return value


def _snapshot_input(source: ReuseSourceItem) -> P3AssetVersionSourceSnapshotInput:
    if not source.lineage_manifest_hash or not isinstance(source.source_trace, dict):
        raise _error(
            "P3_ASSET_SOURCE_EVIDENCE_CHANGED",
            "Source lineage evidence is incomplete.",
            source_item_id=source.id,
        )
    return P3AssetVersionSourceSnapshotInput(
        source_item_id=source.id,
        source_type=source.source_type,
        source_id=source.source_id,
        source_version=source.source_version,
        source_fingerprint=source.source_fingerprint,
        approved_review_id=source.approved_review_id,
        snapshot_id=source.snapshot_id,
        knowledge_asset_id=source.knowledge_asset_id,
        lineage_manifest_hash=source.lineage_manifest_hash,
        source_trace_snapshot=dict(source.source_trace),
    )


class P3AssetService:
    """Generate and read immutable deterministic draft versions."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.reuse_service = P3ReuseService(db)

    def _project_sources(self, project_id: str) -> list[ReuseSourceItem]:
        page = self.reuse_service.list_project_source_items(
            project_id=project_id,
            limit=MAX_GENERATION_SOURCES,
            offset=0,
            include_removed=False,
        )
        if page.total == 0:
            raise _error(
                "P3_ASSET_NO_SOURCES",
                "Project has no current governed sources.",
                project_id=project_id,
            )
        if page.total > MAX_GENERATION_SOURCES:
            raise _error(
                "P3_ASSET_LIMIT_EXCEEDED",
                "Project source count exceeds the generation limit.",
                project_id=project_id,
            )
        return page.items

    @staticmethod
    def _check_replay(
        row: ReuseAssetVersion,
        *,
        project_id: str,
        asset_type: ReuseAssetType,
        template: P3DeterministicTemplate,
        source_manifest_hash: str,
        actor_role: str,
    ) -> ReuseAssetVersion:
        if any(
            (
                row.project_id != project_id,
                row.asset_type is not asset_type,
                row.generation_mode
                is not ReuseGenerationMode.DETERMINISTIC_TEMPLATE,
                row.template_key != template.template_key,
                row.template_version != template.template_version,
                row.source_manifest_hash != source_manifest_hash,
                row.created_by_role != actor_role,
            )
        ):
            raise _error(
                "P3_ASSET_IDEMPOTENCY_CONFLICT",
                "Idempotency key is bound to a different generation request.",
                asset_version_id=row.id,
            )
        if row.status is ReuseAssetVersionStatus.GENERATED:
            return row
        if row.status is ReuseAssetVersionStatus.FAILED:
            raise _error(
                "P3_ASSET_GENERATION_FAILED",
                "The idempotent generation attempt previously failed.",
                asset_version_id=row.id,
            )
        raise _error(
            "P3_ASSET_IDEMPOTENCY_CONFLICT",
            "The idempotent generation attempt is still in progress.",
            asset_version_id=row.id,
        )

    def _existing_by_idempotency_key(
        self,
        idempotency_key: str,
    ) -> ReuseAssetVersion | None:
        try:
            return asset_repositories.get_asset_version_by_idempotency_key(
                self.db,
                idempotency_key,
            )
        except P3RepositoryNotFound:
            return None
        except P3RepositoryValidationError as exc:
            raise _error(
                "P3_ASSET_VALIDATION_ERROR",
                "idempotency_key is invalid.",
            ) from exc

    def _revalidate_sources(
        self,
        project_id: str,
        sources: list[ReuseSourceItem],
    ) -> None:
        stale = next((source for source in sources if source.source_stale), None)
        if stale is not None:
            raise _error(
                "P3_ASSET_SOURCE_STALE",
                "Project contains a stale source.",
                project_id=project_id,
                source_item_id=stale.id,
            )
        try:
            result = self.reuse_service.revalidate_project_sources(
                project_id,
                limit=MAX_GENERATION_SOURCES,
            )
        except P3ServiceError as exc:
            raise _error(
                "P3_ASSET_SOURCE_INELIGIBLE",
                "Project sources could not be revalidated.",
                project_id=project_id,
            ) from exc
        invalid = next(
            (
                item
                for item in result.results
                if item.status is not P3SourceRevalidationStatus.VALID
            ),
            None,
        )
        if invalid is None:
            return
        code = (
            "P3_ASSET_SOURCE_EVIDENCE_CHANGED"
            if invalid.eligible
            else "P3_ASSET_SOURCE_INELIGIBLE"
        )
        raise _error(
            code,
            "Project source is no longer valid for generation.",
            project_id=project_id,
            source_item_id=invalid.source_item_id,
            reason_code=invalid.reason_code.value,
        )

    def _mark_failed(
        self,
        version: ReuseAssetVersion,
        *,
        code: str,
        message: str,
    ) -> None:
        try:
            asset_repositories.mark_asset_failed(
                self.db,
                version.id,
                failure_code=code,
                failure_message=message,
            )
        except (P3RepositoryConflict, P3RepositoryValidationError, SQLAlchemyError):
            # The original safe generation error remains authoritative.  A
            # concurrent deterministic worker may already have finalized it.
            self.db.rollback()

    def generate_draft_asset(
        self,
        *,
        project_id: str,
        asset_type: ReuseAssetType,
        template_key: str | None,
        idempotency_key: str,
        actor_role: str,
        request_id: str,
    ) -> ReuseAssetVersion:
        normalized_type = _asset_type(asset_type)
        if not isinstance(idempotency_key, str) or not idempotency_key.strip():
            raise _error(
                "P3_ASSET_VALIDATION_ERROR",
                "idempotency_key must not be blank.",
            )
        try:
            template = get_deterministic_template(normalized_type, template_key)
        except P3TemplateError as exc:
            raise _error(exc.code, exc.message, template_key=exc.template_key) from exc

        try:
            project = self.reuse_service.get_project(project_id)
            sources = self._project_sources(project.id)
        except P3AssetServiceError:
            raise
        except P3ServiceError as exc:
            raise _error(
                "P3_ASSET_PROJECT_NOT_FOUND",
                "Reuse project was not found.",
                project_id=project_id,
            ) from exc
        _manifest, manifest_hash = build_source_manifest(sources)

        existing = self._existing_by_idempotency_key(idempotency_key.strip())
        if existing is not None:
            return self._check_replay(
                existing,
                project_id=project.id,
                asset_type=normalized_type,
                template=template,
                source_manifest_hash=manifest_hash,
                actor_role=actor_role,
            )
        if project.status is not ReuseProjectStatus.ACTIVE:
            raise _error(
                "P3_ASSET_PROJECT_NOT_ACTIVE",
                "Only active reuse projects may generate draft assets.",
                project_id=project.id,
                project_status=project.status.value,
            )

        self._revalidate_sources(project.id, sources)
        try:
            materials = read_generation_source_materials(self.db, sources)
        except P3SourceMaterialReadError as exc:
            raise _error(
                exc.code,
                exc.message,
                project_id=project.id,
                source_item_id=exc.source_item_id,
            ) from exc
        materials.sort(
            key=lambda material: (
                material.source_type.value,
                material.source_id,
                material.source_version or 0,
                material.source_item_id,
            )
        )
        snapshots = tuple(_snapshot_input(source) for source in sources)
        version = _repository_call(
            asset_repositories.create_asset_version_with_source_snapshots,
            self.db,
            project_id=project.id,
            asset_type=normalized_type,
            generation_mode=ReuseGenerationMode.DETERMINISTIC_TEMPLATE,
            template_key=template.template_key,
            template_version=template.template_version,
            source_manifest_hash=manifest_hash,
            idempotency_key=idempotency_key.strip(),
            created_by_role=actor_role,
            request_id=request_id,
            source_snapshots=snapshots,
            context={"project_id": project.id},
        )
        if version.status is ReuseAssetVersionStatus.GENERATED:
            return version
        if version.status is ReuseAssetVersionStatus.FAILED:
            raise _error(
                "P3_ASSET_GENERATION_FAILED",
                "The idempotent generation attempt previously failed.",
                asset_version_id=version.id,
            )

        try:
            payload = template.render(tuple(materials))
            return _repository_call(
                asset_repositories.mark_asset_generated,
                self.db,
                version.id,
                content_payload=payload,
                conflict_code="P3_ASSET_GENERATION_FAILED",
                context={"asset_version_id": version.id},
            )
        except P3TemplateError as exc:
            self._mark_failed(version, code=exc.code, message=exc.message)
            raise _error(
                exc.code,
                exc.message,
                asset_version_id=version.id,
            ) from exc
        except P3AssetServiceError:
            raise
        except Exception as exc:
            self._mark_failed(
                version,
                code="P3_ASSET_GENERATION_FAILED",
                message="Deterministic draft generation failed.",
            )
            raise _error(
                "P3_ASSET_GENERATION_FAILED",
                "Deterministic draft generation failed.",
                asset_version_id=version.id,
            ) from exc

    def get_asset_version(
        self,
        *,
        project_id: str,
        asset_version_id: str,
    ) -> ReuseAssetVersion:
        try:
            project = self.reuse_service.get_project(project_id)
        except P3ServiceError as exc:
            raise _error(
                "P3_ASSET_PROJECT_NOT_FOUND",
                "Reuse project was not found.",
                project_id=project_id,
            ) from exc
        row = _repository_call(
            asset_repositories.get_asset_version_by_id,
            self.db,
            asset_version_id,
            context={"asset_version_id": asset_version_id},
        )
        if row.project_id != project.id:
            raise _error(
                "P3_ASSET_NOT_FOUND",
                "Requested P3 draft asset was not found.",
                project_id=project.id,
                asset_version_id=asset_version_id,
            )
        return row

    def list_project_asset_versions(
        self,
        *,
        project_id: str,
        asset_type: ReuseAssetType | None = None,
        status: ReuseAssetVersionStatus | None = None,
        limit: int = DEFAULT_PAGE_LIMIT,
        offset: int = 0,
    ) -> P3RepositoryPage[ReuseAssetVersion]:
        try:
            self.reuse_service.get_project(project_id)
        except P3ServiceError as exc:
            raise _error(
                "P3_ASSET_PROJECT_NOT_FOUND",
                "Reuse project was not found.",
                project_id=project_id,
            ) from exc
        return _repository_call(
            asset_repositories.list_project_asset_versions,
            self.db,
            project_id=project_id,
            asset_type=asset_type,
            status=status,
            limit=limit,
            offset=offset,
            context={"project_id": project_id},
        )

    def list_asset_version_sources(
        self,
        *,
        project_id: str,
        asset_version_id: str,
        limit: int = DEFAULT_PAGE_LIMIT,
        offset: int = 0,
    ) -> P3RepositoryPage[ReuseAssetVersionSource]:
        version = self.get_asset_version(
            project_id=project_id,
            asset_version_id=asset_version_id,
        )
        return _repository_call(
            asset_repositories.list_asset_version_sources,
            self.db,
            asset_version_id=version.id,
            limit=limit,
            offset=offset,
            context={"asset_version_id": version.id},
        )


__all__ = [
    "MAX_GENERATION_SOURCES",
    "P3AssetService",
    "P3AssetServiceError",
    "build_source_manifest",
]

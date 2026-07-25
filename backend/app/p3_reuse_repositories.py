"""Persistence-only repositories for P3 reuse projects and source evidence."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Generic, TypeVar

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.p3_reuse_models import (
    ReuseProject,
    ReuseProjectStatus,
    ReuseSourceItem,
)
from app.p3_source_eligibility_schemas import P3SourceType


DEFAULT_PAGE_LIMIT = 50
MAX_PAGE_LIMIT = 100

_T = TypeVar("_T")
_UNSET = object()


class P3RepositoryError(RuntimeError):
    """Base class for stable P3 persistence errors."""


class P3RepositoryNotFound(P3RepositoryError):
    """Requested P3 persistence row does not exist."""


class P3RepositoryConflict(P3RepositoryError):
    """A stable identity exists with a different immutable payload."""


class P3RepositoryValidationError(P3RepositoryError):
    """Repository input violates the persistence contract."""


@dataclass(frozen=True)
class P3RepositoryPage(Generic[_T]):
    """Bounded, deterministic repository page."""

    items: list[_T]
    total: int
    limit: int
    offset: int


def _required_text(value: object, field: str, max_length: int) -> str:
    if not isinstance(value, str):
        raise P3RepositoryValidationError(f"{field} must be a string.")
    normalized = value.strip()
    if not normalized:
        raise P3RepositoryValidationError(f"{field} must not be blank.")
    if len(normalized) > max_length:
        raise P3RepositoryValidationError(
            f"{field} must not exceed {max_length} characters."
        )
    return normalized


def _optional_text(
    value: object,
    field: str,
    max_length: int,
) -> str | None:
    if value is None:
        return None
    return _required_text(value, field, max_length)


def _validate_project_status(status: object) -> ReuseProjectStatus:
    if not isinstance(status, ReuseProjectStatus):
        raise P3RepositoryValidationError(
            "status must be a ReuseProjectStatus value."
        )
    return status


def _validate_source_type(source_type: object) -> P3SourceType:
    if not isinstance(source_type, P3SourceType):
        raise P3RepositoryValidationError(
            "source_type must be a governed P3SourceType value."
        )
    return source_type


def _validate_source_version(source_version: object) -> int | None:
    if source_version is None:
        return None
    if (
        isinstance(source_version, bool)
        or not isinstance(source_version, int)
        or source_version < 1
    ):
        raise P3RepositoryValidationError(
            "source_version must be null or a positive integer."
        )
    return source_version


def _validate_version_key(source_version_key: object) -> int:
    if (
        isinstance(source_version_key, bool)
        or not isinstance(source_version_key, int)
        or source_version_key < 0
    ):
        raise P3RepositoryValidationError(
            "source_version_key must be a non-negative integer."
        )
    return source_version_key


def _validate_pagination(limit: object, offset: object) -> tuple[int, int]:
    if (
        isinstance(limit, bool)
        or not isinstance(limit, int)
        or limit <= 0
        or limit > MAX_PAGE_LIMIT
    ):
        raise P3RepositoryValidationError(
            f"limit must be between 1 and {MAX_PAGE_LIMIT}."
        )
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
        raise P3RepositoryValidationError("offset must be a non-negative integer.")
    return limit, offset


def _project_payload_matches(
    row: ReuseProject,
    *,
    project_id: str,
    name: str,
    description: str | None,
    status: ReuseProjectStatus,
    created_by_role: str,
) -> bool:
    return (
        row.id == project_id
        and row.name == name
        and row.description == description
        and row.status == status
        and row.created_by_role == created_by_role
    )


def _source_evidence_matches(
    row: ReuseSourceItem,
    *,
    source_fingerprint: str,
    eligibility_policy_version: str,
    approved_review_id: str | None,
    snapshot_id: str | None,
    knowledge_asset_id: str | None,
    lineage_manifest_hash: str | None,
    source_trace: dict[str, object],
) -> bool:
    return (
        row.source_fingerprint == source_fingerprint
        and row.eligibility_policy_version == eligibility_policy_version
        and row.approved_review_id == approved_review_id
        and row.snapshot_id == snapshot_id
        and row.knowledge_asset_id == knowledge_asset_id
        and row.lineage_manifest_hash == lineage_manifest_hash
        and row.source_trace == source_trace
    )


def _find_project_by_idempotency_key(
    db: Session,
    idempotency_key: str,
) -> ReuseProject | None:
    return (
        db.query(ReuseProject)
        .filter(ReuseProject.idempotency_key == idempotency_key)
        .first()
    )


def create_project(
    db: Session,
    *,
    project_id: str,
    name: str,
    description: str | None,
    status: ReuseProjectStatus,
    created_by_role: str,
    request_id: str,
    idempotency_key: str,
) -> ReuseProject:
    """Create one project or replay an identical idempotent request."""

    normalized_id = _required_text(project_id, "project_id", 200)
    normalized_name = _required_text(name, "name", 300)
    normalized_description = (
        None
        if description is None
        else _optional_text(description, "description", 10_000)
    )
    normalized_status = _validate_project_status(status)
    normalized_role = _required_text(created_by_role, "created_by_role", 50)
    normalized_request_id = _required_text(request_id, "request_id", 200)
    normalized_key = _required_text(idempotency_key, "idempotency_key", 200)

    existing = _find_project_by_idempotency_key(db, normalized_key)
    if existing is not None:
        if _project_payload_matches(
            existing,
            project_id=normalized_id,
            name=normalized_name,
            description=normalized_description,
            status=normalized_status,
            created_by_role=normalized_role,
        ):
            return existing
        raise P3RepositoryConflict(
            "Project idempotency key is bound to a different payload."
        )

    now = datetime.now(UTC)
    row = ReuseProject(
        id=normalized_id,
        name=normalized_name,
        description=normalized_description,
        status=normalized_status,
        created_by_role=normalized_role,
        request_id=normalized_request_id,
        idempotency_key=normalized_key,
        created_at=now,
        updated_at=now,
        archived_at=now if normalized_status is ReuseProjectStatus.ARCHIVED else None,
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raced = _find_project_by_idempotency_key(db, normalized_key)
        if raced is not None and _project_payload_matches(
            raced,
            project_id=normalized_id,
            name=normalized_name,
            description=normalized_description,
            status=normalized_status,
            created_by_role=normalized_role,
        ):
            return raced
        raise P3RepositoryConflict("Project persistence conflict.") from exc
    db.refresh(row)
    return row


def get_project_by_id(db: Session, project_id: str) -> ReuseProject:
    normalized_id = _required_text(project_id, "project_id", 200)
    row = db.get(ReuseProject, normalized_id)
    if row is None:
        raise P3RepositoryNotFound("Reuse project was not found.")
    return row


def get_project_by_idempotency_key(
    db: Session,
    idempotency_key: str,
) -> ReuseProject:
    normalized_key = _required_text(idempotency_key, "idempotency_key", 200)
    row = _find_project_by_idempotency_key(db, normalized_key)
    if row is None:
        raise P3RepositoryNotFound("Reuse project was not found.")
    return row


def list_projects(
    db: Session,
    *,
    limit: int = DEFAULT_PAGE_LIMIT,
    offset: int = 0,
    status: ReuseProjectStatus | None = None,
) -> P3RepositoryPage[ReuseProject]:
    normalized_limit, normalized_offset = _validate_pagination(limit, offset)
    query = db.query(ReuseProject)
    if status is not None:
        query = query.filter(ReuseProject.status == _validate_project_status(status))
    total = query.with_entities(func.count(ReuseProject.id)).scalar() or 0
    rows = (
        query.order_by(ReuseProject.created_at.desc(), ReuseProject.id.desc())
        .offset(normalized_offset)
        .limit(normalized_limit)
        .all()
    )
    return P3RepositoryPage(
        items=rows,
        total=int(total),
        limit=normalized_limit,
        offset=normalized_offset,
    )


def update_project_metadata(
    db: Session,
    project_id: str,
    *,
    name: str | object = _UNSET,
    description: str | None | object = _UNSET,
) -> ReuseProject:
    """Update only mutable descriptive fields; protected fields are not accepted."""

    row = get_project_by_id(db, project_id)
    changed = False
    if name is not _UNSET:
        normalized_name = _required_text(name, "name", 300)
        if row.name != normalized_name:
            row.name = normalized_name
            changed = True
    if description is not _UNSET:
        normalized_description = (
            None
            if description is None
            else _optional_text(description, "description", 10_000)
        )
        if row.description != normalized_description:
            row.description = normalized_description
            changed = True
    if not changed:
        return row
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise P3RepositoryConflict("Project metadata persistence conflict.") from exc
    db.refresh(row)
    return row


def set_project_status(
    db: Session,
    project_id: str,
    status: ReuseProjectStatus,
) -> ReuseProject:
    """Persist a caller-approved enum value without enforcing a state machine."""

    normalized_status = _validate_project_status(status)
    row = get_project_by_id(db, project_id)
    if row.status == normalized_status:
        return row
    row.status = normalized_status
    if normalized_status is ReuseProjectStatus.ARCHIVED:
        row.archived_at = row.archived_at or datetime.now(UTC)
    else:
        row.archived_at = None
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise P3RepositoryConflict("Project status persistence conflict.") from exc
    db.refresh(row)
    return row


def _find_source_item_by_identity(
    db: Session,
    *,
    project_id: str,
    source_type: P3SourceType,
    source_id: str,
    source_version_key: int,
) -> ReuseSourceItem | None:
    return (
        db.query(ReuseSourceItem)
        .filter(
            ReuseSourceItem.project_id == project_id,
            ReuseSourceItem.source_type == source_type,
            ReuseSourceItem.source_id == source_id,
            ReuseSourceItem.source_version_key == source_version_key,
        )
        .first()
    )


def add_source_item(
    db: Session,
    *,
    source_item_id: str,
    project_id: str,
    source_type: P3SourceType,
    source_id: str,
    source_version: int | None,
    source_fingerprint: str,
    eligibility_policy_version: str,
    approved_review_id: str | None,
    snapshot_id: str | None,
    knowledge_asset_id: str | None,
    lineage_manifest_hash: str | None,
    source_trace: dict[str, object],
    selected_by_role: str,
    request_id: str,
) -> ReuseSourceItem:
    """Persist prepared eligibility evidence without evaluating eligibility."""

    normalized_item_id = _required_text(source_item_id, "source_item_id", 200)
    normalized_project_id = _required_text(project_id, "project_id", 200)
    normalized_type = _validate_source_type(source_type)
    normalized_source_id = _required_text(source_id, "source_id", 200)
    normalized_version = _validate_source_version(source_version)
    version_key = normalized_version or 0
    normalized_fingerprint = _required_text(
        source_fingerprint,
        "source_fingerprint",
        128,
    )
    normalized_policy = _required_text(
        eligibility_policy_version,
        "eligibility_policy_version",
        100,
    )
    normalized_review_id = _optional_text(
        approved_review_id,
        "approved_review_id",
        200,
    )
    normalized_snapshot_id = _optional_text(snapshot_id, "snapshot_id", 200)
    normalized_knowledge_asset_id = _optional_text(
        knowledge_asset_id,
        "knowledge_asset_id",
        200,
    )
    normalized_manifest_hash = _optional_text(
        lineage_manifest_hash,
        "lineage_manifest_hash",
        128,
    )
    if not isinstance(source_trace, dict):
        raise P3RepositoryValidationError("source_trace must be a JSON object.")
    try:
        json.dumps(source_trace, sort_keys=True, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise P3RepositoryValidationError(
            "source_trace must contain valid JSON values."
        ) from exc
    evidence_trace = deepcopy(source_trace)
    normalized_role = _required_text(selected_by_role, "selected_by_role", 50)
    normalized_request_id = _required_text(request_id, "request_id", 200)

    if db.get(ReuseProject, normalized_project_id) is None:
        raise P3RepositoryNotFound("Reuse project was not found.")

    existing = _find_source_item_by_identity(
        db,
        project_id=normalized_project_id,
        source_type=normalized_type,
        source_id=normalized_source_id,
        source_version_key=version_key,
    )
    if existing is not None:
        if _source_evidence_matches(
            existing,
            source_fingerprint=normalized_fingerprint,
            eligibility_policy_version=normalized_policy,
            approved_review_id=normalized_review_id,
            snapshot_id=normalized_snapshot_id,
            knowledge_asset_id=normalized_knowledge_asset_id,
            lineage_manifest_hash=normalized_manifest_hash,
            source_trace=evidence_trace,
        ):
            return existing
        raise P3RepositoryConflict(
            "Source identity is bound to different eligibility evidence."
        )

    row = ReuseSourceItem(
        id=normalized_item_id,
        project_id=normalized_project_id,
        source_type=normalized_type,
        source_id=normalized_source_id,
        source_version=normalized_version,
        source_fingerprint=normalized_fingerprint,
        eligibility_policy_version=normalized_policy,
        approved_review_id=normalized_review_id,
        snapshot_id=normalized_snapshot_id,
        knowledge_asset_id=normalized_knowledge_asset_id,
        lineage_manifest_hash=normalized_manifest_hash,
        source_trace=evidence_trace,
        selected_by_role=normalized_role,
        request_id=normalized_request_id,
        created_at=datetime.now(UTC),
        source_stale=False,
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raced = _find_source_item_by_identity(
            db,
            project_id=normalized_project_id,
            source_type=normalized_type,
            source_id=normalized_source_id,
            source_version_key=version_key,
        )
        if raced is not None and _source_evidence_matches(
            raced,
            source_fingerprint=normalized_fingerprint,
            eligibility_policy_version=normalized_policy,
            approved_review_id=normalized_review_id,
            snapshot_id=normalized_snapshot_id,
            knowledge_asset_id=normalized_knowledge_asset_id,
            lineage_manifest_hash=normalized_manifest_hash,
            source_trace=evidence_trace,
        ):
            return raced
        raise P3RepositoryConflict("Source persistence conflict.") from exc
    db.refresh(row)
    return row


def get_source_item_by_id(db: Session, source_item_id: str) -> ReuseSourceItem:
    normalized_id = _required_text(source_item_id, "source_item_id", 200)
    row = db.get(ReuseSourceItem, normalized_id)
    if row is None:
        raise P3RepositoryNotFound("Reuse source item was not found.")
    return row


def get_source_item_by_identity(
    db: Session,
    *,
    project_id: str,
    source_type: P3SourceType,
    source_id: str,
    source_version_key: int,
) -> ReuseSourceItem:
    normalized_project_id = _required_text(project_id, "project_id", 200)
    normalized_type = _validate_source_type(source_type)
    normalized_source_id = _required_text(source_id, "source_id", 200)
    normalized_version_key = _validate_version_key(source_version_key)
    row = _find_source_item_by_identity(
        db,
        project_id=normalized_project_id,
        source_type=normalized_type,
        source_id=normalized_source_id,
        source_version_key=normalized_version_key,
    )
    if row is None:
        raise P3RepositoryNotFound("Reuse source item was not found.")
    return row


def list_project_source_items(
    db: Session,
    *,
    project_id: str,
    limit: int = DEFAULT_PAGE_LIMIT,
    offset: int = 0,
    include_removed: bool = False,
    source_type: P3SourceType | None = None,
    source_stale: bool | None = None,
) -> P3RepositoryPage[ReuseSourceItem]:
    normalized_project_id = _required_text(project_id, "project_id", 200)
    normalized_limit, normalized_offset = _validate_pagination(limit, offset)
    if not isinstance(include_removed, bool):
        raise P3RepositoryValidationError("include_removed must be a boolean.")
    if source_stale is not None and not isinstance(source_stale, bool):
        raise P3RepositoryValidationError("source_stale must be a boolean or null.")

    query = db.query(ReuseSourceItem).filter(
        ReuseSourceItem.project_id == normalized_project_id
    )
    if not include_removed:
        query = query.filter(ReuseSourceItem.removed_at.is_(None))
    if source_type is not None:
        query = query.filter(
            ReuseSourceItem.source_type == _validate_source_type(source_type)
        )
    if source_stale is not None:
        query = query.filter(ReuseSourceItem.source_stale.is_(source_stale))

    total = query.with_entities(func.count(ReuseSourceItem.id)).scalar() or 0
    rows = (
        query.order_by(
            ReuseSourceItem.created_at.desc(),
            ReuseSourceItem.id.desc(),
        )
        .offset(normalized_offset)
        .limit(normalized_limit)
        .all()
    )
    return P3RepositoryPage(
        items=rows,
        total=int(total),
        limit=normalized_limit,
        offset=normalized_offset,
    )


def logically_remove_source_item(
    db: Session,
    source_item_id: str,
) -> ReuseSourceItem:
    row = get_source_item_by_id(db, source_item_id)
    if row.removed_at is not None:
        return row
    row.removed_at = datetime.now(UTC)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise P3RepositoryConflict("Source removal persistence conflict.") from exc
    db.refresh(row)
    return row


def mark_source_stale(
    db: Session,
    source_item_id: str,
) -> ReuseSourceItem:
    row = get_source_item_by_id(db, source_item_id)
    if row.source_stale:
        return row
    row.source_stale = True
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise P3RepositoryConflict("Source stale persistence conflict.") from exc
    db.refresh(row)
    return row

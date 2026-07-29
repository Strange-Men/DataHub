"""Persistence-only repositories for governed P3 asset publication."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.p3_reuse_models import (
    ReuseAssetType,
    ReuseAssetVersion,
    ReuseAssetVersionStatus,
    ReuseProject,
)
from app.p3_reuse_repositories import (
    DEFAULT_PAGE_LIMIT,
    MAX_PAGE_LIMIT,
    P3RepositoryConflict,
    P3RepositoryNotFound,
    P3RepositoryPage,
    P3RepositoryValidationError,
)


_ARCHIVABLE_STATES = frozenset(
    {
        ReuseAssetVersionStatus.APPROVED,
        ReuseAssetVersionStatus.PUBLISHED,
        ReuseAssetVersionStatus.SUPERSEDED,
    }
)


@dataclass(frozen=True)
class P3PublicationResult:
    """One atomic publication result and the version it replaced."""

    published: ReuseAssetVersion
    superseded: ReuseAssetVersion | None
    replayed: bool = False


def _utcnow() -> datetime:
    return datetime.now(UTC)


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


def _asset_type(value: object) -> ReuseAssetType:
    if not isinstance(value, ReuseAssetType):
        raise P3RepositoryValidationError(
            "asset_type must be a ReuseAssetType value."
        )
    return value


def _pagination(limit: object, offset: object) -> tuple[int, int]:
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
        raise P3RepositoryValidationError(
            "offset must be a non-negative integer."
        )
    return limit, offset


def _publish_by_key(
    db: Session,
    idempotency_key: str,
) -> ReuseAssetVersion | None:
    return (
        db.query(ReuseAssetVersion)
        .filter(
            ReuseAssetVersion.publish_idempotency_key == idempotency_key
        )
        .first()
    )


def _archive_by_key(
    db: Session,
    idempotency_key: str,
) -> ReuseAssetVersion | None:
    return (
        db.query(ReuseAssetVersion)
        .filter(
            ReuseAssetVersion.archive_idempotency_key == idempotency_key
        )
        .first()
    )


def get_current_published_asset(
    db: Session,
    *,
    project_id: str,
    asset_type: ReuseAssetType,
) -> ReuseAssetVersion:
    normalized_project = _required_text(project_id, "project_id", 200)
    normalized_type = _asset_type(asset_type)
    row = (
        db.query(ReuseAssetVersion)
        .filter(
            ReuseAssetVersion.project_id == normalized_project,
            ReuseAssetVersion.asset_type == normalized_type,
            ReuseAssetVersion.status == ReuseAssetVersionStatus.PUBLISHED,
        )
        .first()
    )
    if row is None:
        raise P3RepositoryNotFound(
            "Current published asset version was not found."
        )
    return row


def list_current_published_assets(
    db: Session,
    *,
    project_id: str,
    asset_type: ReuseAssetType | None = None,
    limit: int = DEFAULT_PAGE_LIMIT,
    offset: int = 0,
) -> P3RepositoryPage[ReuseAssetVersion]:
    normalized_project = _required_text(project_id, "project_id", 200)
    normalized_limit, normalized_offset = _pagination(limit, offset)
    query = db.query(ReuseAssetVersion).filter(
        ReuseAssetVersion.project_id == normalized_project,
        ReuseAssetVersion.status == ReuseAssetVersionStatus.PUBLISHED,
    )
    if asset_type is not None:
        query = query.filter(
            ReuseAssetVersion.asset_type == _asset_type(asset_type)
        )
    total = query.with_entities(func.count(ReuseAssetVersion.id)).scalar() or 0
    rows = (
        query.order_by(
            ReuseAssetVersion.published_at.desc(),
            ReuseAssetVersion.version_number.desc(),
            ReuseAssetVersion.id.desc(),
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


def get_asset_publication_state(
    db: Session,
    asset_version_id: str,
) -> ReuseAssetVersion:
    normalized_id = _required_text(
        asset_version_id,
        "asset_version_id",
        200,
    )
    row = db.get(ReuseAssetVersion, normalized_id)
    if row is None:
        raise P3RepositoryNotFound("Reuse asset version was not found.")
    return row


def get_asset_by_publish_idempotency_key(
    db: Session,
    idempotency_key: str,
) -> ReuseAssetVersion:
    normalized_key = _required_text(
        idempotency_key,
        "idempotency_key",
        200,
    )
    row = _publish_by_key(db, normalized_key)
    if row is None:
        raise P3RepositoryNotFound("Published asset version was not found.")
    return row


def get_asset_by_archive_idempotency_key(
    db: Session,
    idempotency_key: str,
) -> ReuseAssetVersion:
    normalized_key = _required_text(
        idempotency_key,
        "idempotency_key",
        200,
    )
    row = _archive_by_key(db, normalized_key)
    if row is None:
        raise P3RepositoryNotFound("Archived asset version was not found.")
    return row


def publish_approved_asset(
    db: Session,
    *,
    asset_version_id: str,
    published_by_role: str,
    request_id: str,
    idempotency_key: str,
) -> P3PublicationResult:
    """Atomically publish one approved version and supersede the old current."""

    return supersede_current_published_asset(
        db,
        asset_version_id=asset_version_id,
        published_by_role=published_by_role,
        request_id=request_id,
        idempotency_key=idempotency_key,
    )


def supersede_current_published_asset(
    db: Session,
    *,
    asset_version_id: str,
    published_by_role: str,
    request_id: str,
    idempotency_key: str,
) -> P3PublicationResult:
    """Lock the publication slot, supersede current, and publish the target."""

    normalized_id = _required_text(
        asset_version_id,
        "asset_version_id",
        200,
    )
    normalized_role = _required_text(
        published_by_role,
        "published_by_role",
        50,
    )
    normalized_request = _required_text(request_id, "request_id", 200)
    normalized_key = _required_text(
        idempotency_key,
        "idempotency_key",
        200,
    )

    existing_key = _publish_by_key(db, normalized_key)
    if existing_key is not None:
        if existing_key.id != normalized_id:
            raise P3RepositoryConflict(
                "Publish idempotency key is bound to another asset version."
            )
        return P3PublicationResult(
            published=existing_key,
            superseded=None,
            replayed=True,
        )

    probe = db.get(ReuseAssetVersion, normalized_id)
    if probe is None:
        raise P3RepositoryNotFound("Reuse asset version was not found.")
    project = (
        db.query(ReuseProject)
        .filter(ReuseProject.id == probe.project_id)
        .with_for_update()
        .one_or_none()
    )
    if project is None:
        raise P3RepositoryNotFound("Reuse project was not found.")
    target = (
        db.query(ReuseAssetVersion)
        .filter(ReuseAssetVersion.id == normalized_id)
        .with_for_update()
        .one()
    )
    current = (
        db.query(ReuseAssetVersion)
        .filter(
            ReuseAssetVersion.project_id == target.project_id,
            ReuseAssetVersion.asset_type == target.asset_type,
            ReuseAssetVersion.status == ReuseAssetVersionStatus.PUBLISHED,
        )
        .with_for_update()
        .one_or_none()
    )
    if current is not None and current.id == target.id:
        return P3PublicationResult(
            published=target,
            superseded=None,
            replayed=True,
        )
    if target.status is ReuseAssetVersionStatus.SUPERSEDED:
        raise P3RepositoryConflict(
            "A superseded asset version cannot be published again."
        )
    if target.status is ReuseAssetVersionStatus.ARCHIVED:
        raise P3RepositoryConflict(
            "An archived asset version cannot be published again."
        )
    if target.status is not ReuseAssetVersionStatus.APPROVED:
        raise P3RepositoryConflict(
            "Only an approved asset version may be published."
        )

    published_at = _utcnow()
    if current is not None:
        current.status = ReuseAssetVersionStatus.SUPERSEDED
        current.superseded_at = published_at
        current.superseded_by_asset_version_id = target.id
        # Free the database-enforced current slot before publishing the new
        # target.  This is a flush inside the same transaction, never an
        # intermediate commit, so rollback still restores both versions.
        db.flush([current])
    target.status = ReuseAssetVersionStatus.PUBLISHED
    target.published_at = published_at
    target.published_by_role = normalized_role
    target.publish_request_id = normalized_request
    target.publish_idempotency_key = normalized_key
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raced = _publish_by_key(db, normalized_key)
        if raced is not None and raced.id == normalized_id:
            return P3PublicationResult(
                published=raced,
                superseded=None,
                replayed=True,
            )
        raise P3RepositoryConflict(
            "Concurrent asset publication conflict."
        ) from exc
    db.refresh(target)
    if current is not None:
        db.refresh(current)
    return P3PublicationResult(
        published=target,
        superseded=current,
        replayed=False,
    )


def archive_asset(
    db: Session,
    *,
    asset_version_id: str,
    archived_by_role: str,
    request_id: str,
    idempotency_key: str,
) -> ReuseAssetVersion:
    """Logically archive an approved, published, or superseded version."""

    normalized_id = _required_text(
        asset_version_id,
        "asset_version_id",
        200,
    )
    normalized_role = _required_text(
        archived_by_role,
        "archived_by_role",
        50,
    )
    normalized_request = _required_text(request_id, "request_id", 200)
    normalized_key = _required_text(
        idempotency_key,
        "idempotency_key",
        200,
    )
    existing_key = _archive_by_key(db, normalized_key)
    if existing_key is not None:
        if existing_key.id != normalized_id:
            raise P3RepositoryConflict(
                "Archive idempotency key is bound to another asset version."
            )
        return existing_key

    row = (
        db.query(ReuseAssetVersion)
        .filter(ReuseAssetVersion.id == normalized_id)
        .with_for_update()
        .one_or_none()
    )
    if row is None:
        raise P3RepositoryNotFound("Reuse asset version was not found.")
    if row.status is ReuseAssetVersionStatus.ARCHIVED:
        raise P3RepositoryConflict("Asset version is already archived.")
    if row.status not in _ARCHIVABLE_STATES:
        raise P3RepositoryConflict(
            "Only approved, published, or superseded assets may be archived."
        )
    row.status = ReuseAssetVersionStatus.ARCHIVED
    row.archived_at = _utcnow()
    row.archived_by_role = normalized_role
    row.archive_request_id = normalized_request
    row.archive_idempotency_key = normalized_key
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raced = _archive_by_key(db, normalized_key)
        if raced is not None and raced.id == normalized_id:
            return raced
        raise P3RepositoryConflict(
            "Concurrent asset archive conflict."
        ) from exc
    db.refresh(row)
    return row


__all__ = [
    "P3PublicationResult",
    "archive_asset",
    "get_asset_by_archive_idempotency_key",
    "get_asset_by_publish_idempotency_key",
    "get_asset_publication_state",
    "get_current_published_asset",
    "list_current_published_assets",
    "publish_approved_asset",
    "supersede_current_published_asset",
]

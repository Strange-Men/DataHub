"""Persistence-only repositories for P3 manual revisions and human reviews."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.p3_asset_repositories import (
    MAX_VERSION_ALLOCATION_ATTEMPTS,
    canonicalize_asset_content,
)
from app.p3_reuse_models import (
    ReuseAssetType,
    ReuseAssetVersion,
    ReuseAssetVersionSource,
    ReuseAssetVersionStatus,
    ReuseGenerationMode,
    ReuseReview,
    ReuseReviewDecision,
)
from app.p3_reuse_repositories import (
    DEFAULT_PAGE_LIMIT,
    MAX_PAGE_LIMIT,
    P3RepositoryConflict,
    P3RepositoryNotFound,
    P3RepositoryPage,
    P3RepositoryValidationError,
)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _stable_id(prefix: str, *parts: object) -> str:
    encoded = json.dumps(
        [str(part) for part in parts],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(encoded).hexdigest()[:20]}"


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


def _canonical_json_object(
    value: object,
    field: str,
) -> dict[str, object]:
    if not isinstance(value, dict):
        raise P3RepositoryValidationError(f"{field} must be a JSON object.")
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        normalized = json.loads(encoded)
    except (TypeError, ValueError) as exc:
        raise P3RepositoryValidationError(
            f"{field} must be canonical JSON data."
        ) from exc
    assert isinstance(normalized, dict)
    return normalized


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
        raise P3RepositoryValidationError(
            "offset must be a non-negative integer."
        )
    return limit, offset


def _find_asset_by_key(
    db: Session,
    idempotency_key: str,
) -> ReuseAssetVersion | None:
    return (
        db.query(ReuseAssetVersion)
        .filter(ReuseAssetVersion.idempotency_key == idempotency_key)
        .first()
    )


def _find_review_by_key(
    db: Session,
    idempotency_key: str,
) -> ReuseReview | None:
    return (
        db.query(ReuseReview)
        .filter(ReuseReview.idempotency_key == idempotency_key)
        .first()
    )


def _parent_snapshots(
    db: Session,
    parent_asset_version_id: str,
) -> list[ReuseAssetVersionSource]:
    return (
        db.query(ReuseAssetVersionSource)
        .filter(
            ReuseAssetVersionSource.asset_version_id
            == parent_asset_version_id
        )
        .order_by(ReuseAssetVersionSource.id.asc())
        .all()
    )


def _next_version_number(
    db: Session,
    *,
    project_id: str,
    asset_type: ReuseAssetType,
) -> int:
    current = (
        db.query(func.max(ReuseAssetVersion.version_number))
        .filter(
            ReuseAssetVersion.project_id == project_id,
            ReuseAssetVersion.asset_type == asset_type,
        )
        .scalar()
    )
    return int(current or 0) + 1


def _manual_revision_matches(
    row: ReuseAssetVersion,
    *,
    project_id: str,
    parent_asset_version_id: str,
    asset_type: ReuseAssetType,
    content_hash: str,
    source_manifest_hash: str,
) -> bool:
    return (
        row.project_id == project_id
        and row.parent_asset_version_id == parent_asset_version_id
        and row.asset_type is asset_type
        and row.generation_mode is ReuseGenerationMode.MANUAL_REVISION
        and row.content_hash == content_hash
        and row.source_manifest_hash == source_manifest_hash
    )


def _verify_copied_snapshots(
    db: Session,
    *,
    parent_asset_version_id: str,
    child_asset_version_id: str,
) -> None:
    parent_rows = _parent_snapshots(db, parent_asset_version_id)
    child_rows = _parent_snapshots(db, child_asset_version_id)
    if len(parent_rows) != len(child_rows):
        raise P3RepositoryConflict(
            "Manual revision source snapshots conflict with its parent."
        )
    parent_by_source = {row.source_item_id: row for row in parent_rows}
    for child in child_rows:
        parent = parent_by_source.get(child.source_item_id)
        if parent is None or any(
            getattr(child, field) != getattr(parent, field)
            for field in (
                "source_type",
                "source_id",
                "source_version",
                "source_fingerprint",
                "approved_review_id",
                "snapshot_id",
                "knowledge_asset_id",
                "lineage_manifest_hash",
                "source_trace_snapshot",
            )
        ):
            raise P3RepositoryConflict(
                "Manual revision source snapshots conflict with its parent."
            )


def create_manual_revision_with_snapshots(
    db: Session,
    *,
    project_id: str,
    parent_asset_version_id: str,
    content_payload: dict[str, object],
    idempotency_key: str,
    created_by_role: str,
    request_id: str,
) -> ReuseAssetVersion:
    """Atomically create a generated child and copy immutable snapshots."""

    normalized_project_id = _required_text(project_id, "project_id", 200)
    normalized_parent_id = _required_text(
        parent_asset_version_id,
        "parent_asset_version_id",
        200,
    )
    normalized_key = _required_text(
        idempotency_key,
        "idempotency_key",
        200,
    )
    normalized_role = _required_text(
        created_by_role,
        "created_by_role",
        50,
    )
    normalized_request_id = _required_text(request_id, "request_id", 200)
    normalized_payload, content_hash = canonicalize_asset_content(
        content_payload
    )
    parent = db.get(ReuseAssetVersion, normalized_parent_id)
    if parent is None:
        raise P3RepositoryNotFound("Parent asset version was not found.")
    if parent.project_id != normalized_project_id:
        raise P3RepositoryValidationError(
            "Parent asset version does not belong to the project."
        )
    parent_snapshots = _parent_snapshots(db, parent.id)
    if not parent_snapshots:
        raise P3RepositoryValidationError(
            "Parent asset version has no source snapshots."
        )

    existing = _find_asset_by_key(db, normalized_key)
    if existing is not None:
        if not _manual_revision_matches(
            existing,
            project_id=normalized_project_id,
            parent_asset_version_id=parent.id,
            asset_type=parent.asset_type,
            content_hash=content_hash,
            source_manifest_hash=parent.source_manifest_hash,
        ):
            raise P3RepositoryConflict(
                "Manual revision idempotency key is bound to another request."
            )
        _verify_copied_snapshots(
            db,
            parent_asset_version_id=parent.id,
            child_asset_version_id=existing.id,
        )
        return existing

    asset_version_id = _stable_id("reuse_asset_version", normalized_key)
    for attempt in range(MAX_VERSION_ALLOCATION_ATTEMPTS):
        row = ReuseAssetVersion(
            id=asset_version_id,
            project_id=normalized_project_id,
            asset_type=parent.asset_type,
            version_number=_next_version_number(
                db,
                project_id=normalized_project_id,
                asset_type=parent.asset_type,
            ),
            status=ReuseAssetVersionStatus.GENERATED,
            generation_mode=ReuseGenerationMode.MANUAL_REVISION,
            template_key="p3.manual_revision",
            template_version="v1",
            content_payload=normalized_payload,
            content_hash=content_hash,
            source_manifest_hash=parent.source_manifest_hash,
            idempotency_key=normalized_key,
            created_by_role=normalized_role,
            request_id=normalized_request_id,
            parent_asset_version_id=parent.id,
        )
        db.add(row)
        try:
            db.flush([row])
            for source in parent_snapshots:
                db.add(
                    ReuseAssetVersionSource(
                        id=_stable_id(
                            "reuse_asset_source",
                            row.id,
                            source.source_item_id,
                        ),
                        asset_version_id=row.id,
                        source_item_id=source.source_item_id,
                        source_type=source.source_type,
                        source_id=source.source_id,
                        source_version=source.source_version,
                        source_fingerprint=source.source_fingerprint,
                        approved_review_id=source.approved_review_id,
                        snapshot_id=source.snapshot_id,
                        knowledge_asset_id=source.knowledge_asset_id,
                        lineage_manifest_hash=source.lineage_manifest_hash,
                        source_trace_snapshot=json.loads(
                            json.dumps(
                                source.source_trace_snapshot,
                                ensure_ascii=False,
                                sort_keys=True,
                                separators=(",", ":"),
                                allow_nan=False,
                            )
                        ),
                    )
                )
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raced = _find_asset_by_key(db, normalized_key)
            if raced is not None:
                if not _manual_revision_matches(
                    raced,
                    project_id=normalized_project_id,
                    parent_asset_version_id=parent.id,
                    asset_type=parent.asset_type,
                    content_hash=content_hash,
                    source_manifest_hash=parent.source_manifest_hash,
                ):
                    raise P3RepositoryConflict(
                        "Manual revision idempotency key is bound to "
                        "another request."
                    ) from exc
                _verify_copied_snapshots(
                    db,
                    parent_asset_version_id=parent.id,
                    child_asset_version_id=raced.id,
                )
                return raced
            if attempt + 1 >= MAX_VERSION_ALLOCATION_ATTEMPTS:
                raise P3RepositoryConflict(
                    "Concurrent manual revision allocation conflict."
                ) from exc
            parent = db.get(ReuseAssetVersion, normalized_parent_id)
            assert parent is not None
            parent_snapshots = _parent_snapshots(db, parent.id)
            continue
        db.refresh(row)
        return row
    raise P3RepositoryConflict("Manual revision allocation failed.")


def get_child_revisions(
    db: Session,
    *,
    parent_asset_version_id: str,
    limit: int = DEFAULT_PAGE_LIMIT,
    offset: int = 0,
) -> P3RepositoryPage[ReuseAssetVersion]:
    parent_id = _required_text(
        parent_asset_version_id,
        "parent_asset_version_id",
        200,
    )
    normalized_limit, normalized_offset = _validate_pagination(limit, offset)
    query = db.query(ReuseAssetVersion).filter(
        ReuseAssetVersion.parent_asset_version_id == parent_id
    )
    total = query.with_entities(func.count(ReuseAssetVersion.id)).scalar() or 0
    rows = (
        query.order_by(
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


def get_parent_asset_version(
    db: Session,
    asset_version_id: str,
) -> ReuseAssetVersion:
    version_id = _required_text(asset_version_id, "asset_version_id", 200)
    row = db.get(ReuseAssetVersion, version_id)
    if row is None:
        raise P3RepositoryNotFound("Reuse asset version was not found.")
    if row.parent_asset_version_id is None:
        raise P3RepositoryNotFound("Asset version has no parent revision.")
    parent = db.get(ReuseAssetVersion, row.parent_asset_version_id)
    if parent is None:
        raise P3RepositoryNotFound("Parent asset version was not found.")
    return parent


def submit_asset_for_review(
    db: Session,
    *,
    asset_version_id: str,
    idempotency_key: str | None = None,
) -> ReuseAssetVersion:
    version_id = _required_text(asset_version_id, "asset_version_id", 200)
    if idempotency_key is not None:
        _required_text(idempotency_key, "idempotency_key", 200)
    row = db.get(ReuseAssetVersion, version_id)
    if row is None:
        raise P3RepositoryNotFound("Reuse asset version was not found.")
    if row.status is ReuseAssetVersionStatus.PENDING_REVIEW:
        return row
    if row.status is not ReuseAssetVersionStatus.GENERATED:
        raise P3RepositoryConflict(
            "Only a generated asset version may be submitted for review."
        )
    row.status = ReuseAssetVersionStatus.PENDING_REVIEW
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise P3RepositoryConflict(
            "Asset review submission persistence conflict."
        ) from exc
    db.refresh(row)
    return row


def _review_matches(
    row: ReuseReview,
    *,
    asset_version_id: str,
    decision: ReuseReviewDecision,
    comments: str | None,
    checklist_payload: dict[str, object],
    review_policy_version: str,
    content_hash: str,
    source_manifest_hash: str,
    reviewer_role: str,
) -> bool:
    return (
        row.asset_version_id == asset_version_id
        and row.decision is decision
        and row.comments == comments
        and row.checklist_payload == checklist_payload
        and row.review_policy_version == review_policy_version
        and row.reviewed_content_hash == content_hash
        and row.reviewed_source_manifest_hash == source_manifest_hash
        and row.reviewer_role == reviewer_role
    )


def create_review_decision(
    db: Session,
    *,
    asset_version_id: str,
    decision: ReuseReviewDecision,
    comments: str | None,
    checklist_payload: dict[str, object],
    review_policy_version: str,
    reviewer_role: str,
    request_id: str,
    idempotency_key: str,
) -> ReuseReview:
    """Atomically append one immutable Review and transition Asset status."""

    version_id = _required_text(asset_version_id, "asset_version_id", 200)
    if not isinstance(decision, ReuseReviewDecision):
        raise P3RepositoryValidationError(
            "decision must be a ReuseReviewDecision value."
        )
    normalized_comments = _optional_text(comments, "comments", 10_000)
    normalized_checklist = _canonical_json_object(
        checklist_payload,
        "checklist_payload",
    )
    normalized_policy = _required_text(
        review_policy_version,
        "review_policy_version",
        100,
    )
    normalized_role = _required_text(reviewer_role, "reviewer_role", 50)
    normalized_request_id = _required_text(request_id, "request_id", 200)
    normalized_key = _required_text(
        idempotency_key,
        "idempotency_key",
        200,
    )

    existing_key = _find_review_by_key(db, normalized_key)
    if existing_key is not None:
        version = db.get(ReuseAssetVersion, existing_key.asset_version_id)
        assert version is not None
        if not _review_matches(
            existing_key,
            asset_version_id=version_id,
            decision=decision,
            comments=normalized_comments,
            checklist_payload=normalized_checklist,
            review_policy_version=normalized_policy,
            content_hash=version.content_hash,
            source_manifest_hash=version.source_manifest_hash,
            reviewer_role=normalized_role,
        ):
            raise P3RepositoryConflict(
                "Review idempotency key is bound to another decision."
            )
        return existing_key

    version = (
        db.query(ReuseAssetVersion)
        .filter(ReuseAssetVersion.id == version_id)
        .with_for_update()
        .one_or_none()
    )
    if version is None:
        raise P3RepositoryNotFound("Reuse asset version was not found.")
    existing_version = (
        db.query(ReuseReview)
        .filter(ReuseReview.asset_version_id == version.id)
        .first()
    )
    if existing_version is not None:
        raise P3RepositoryConflict(
            "Asset version already has a final Review decision."
        )
    if version.status is not ReuseAssetVersionStatus.PENDING_REVIEW:
        raise P3RepositoryConflict(
            "Only a pending_review asset version may receive a decision."
        )
    review = ReuseReview(
        id=_stable_id("reuse_review", normalized_key),
        asset_version_id=version.id,
        decision=decision,
        comments=normalized_comments,
        checklist_payload=normalized_checklist,
        review_policy_version=normalized_policy,
        reviewed_content_hash=version.content_hash,
        reviewed_source_manifest_hash=version.source_manifest_hash,
        reviewer_role=normalized_role,
        request_id=normalized_request_id,
        idempotency_key=normalized_key,
    )
    version.status = ReuseAssetVersionStatus(decision.value)
    version.approved_at = (
        _utcnow() if decision is ReuseReviewDecision.APPROVED else None
    )
    db.add(review)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raced = _find_review_by_key(db, normalized_key)
        if raced is not None:
            version = db.get(ReuseAssetVersion, raced.asset_version_id)
            assert version is not None
            if _review_matches(
                raced,
                asset_version_id=version_id,
                decision=decision,
                comments=normalized_comments,
                checklist_payload=normalized_checklist,
                review_policy_version=normalized_policy,
                content_hash=version.content_hash,
                source_manifest_hash=version.source_manifest_hash,
                reviewer_role=normalized_role,
            ):
                return raced
        raise P3RepositoryConflict(
            "Concurrent or duplicate Review decision conflict."
        ) from exc
    db.refresh(review)
    return review


def get_review_by_asset_version(
    db: Session,
    asset_version_id: str,
) -> ReuseReview:
    version_id = _required_text(asset_version_id, "asset_version_id", 200)
    row = (
        db.query(ReuseReview)
        .filter(ReuseReview.asset_version_id == version_id)
        .first()
    )
    if row is None:
        raise P3RepositoryNotFound("Review decision was not found.")
    return row


def get_review_by_idempotency_key(
    db: Session,
    idempotency_key: str,
) -> ReuseReview:
    normalized_key = _required_text(
        idempotency_key,
        "idempotency_key",
        200,
    )
    row = _find_review_by_key(db, normalized_key)
    if row is None:
        raise P3RepositoryNotFound("Review decision was not found.")
    return row


def list_project_reviews(
    db: Session,
    *,
    project_id: str,
    decision: ReuseReviewDecision | None = None,
    asset_type: ReuseAssetType | None = None,
    limit: int = DEFAULT_PAGE_LIMIT,
    offset: int = 0,
) -> P3RepositoryPage[ReuseReview]:
    normalized_project_id = _required_text(project_id, "project_id", 200)
    normalized_limit, normalized_offset = _validate_pagination(limit, offset)
    if decision is not None and not isinstance(decision, ReuseReviewDecision):
        raise P3RepositoryValidationError(
            "decision must be a ReuseReviewDecision value."
        )
    if asset_type is not None and not isinstance(asset_type, ReuseAssetType):
        raise P3RepositoryValidationError(
            "asset_type must be a ReuseAssetType value."
        )
    query = db.query(ReuseReview).join(
        ReuseAssetVersion,
        ReuseAssetVersion.id == ReuseReview.asset_version_id,
    ).filter(ReuseAssetVersion.project_id == normalized_project_id)
    if decision is not None:
        query = query.filter(ReuseReview.decision == decision)
    if asset_type is not None:
        query = query.filter(ReuseAssetVersion.asset_type == asset_type)
    total = query.with_entities(func.count(ReuseReview.id)).scalar() or 0
    rows = (
        query.order_by(ReuseReview.created_at.desc(), ReuseReview.id.desc())
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


__all__ = [
    "create_manual_revision_with_snapshots",
    "create_review_decision",
    "get_child_revisions",
    "get_parent_asset_version",
    "get_review_by_asset_version",
    "get_review_by_idempotency_key",
    "list_project_reviews",
    "submit_asset_for_review",
]

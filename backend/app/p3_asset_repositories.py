"""Persistence-only repositories for governed P3 draft asset versions."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Iterable

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.p3_reuse_models import (
    ReuseAssetType,
    ReuseAssetVersion,
    ReuseAssetVersionSource,
    ReuseAssetVersionStatus,
    ReuseGenerationMode,
    ReuseProject,
    ReuseSourceItem,
)
from app.p3_reuse_repositories import (
    DEFAULT_PAGE_LIMIT,
    MAX_PAGE_LIMIT,
    P3RepositoryConflict,
    P3RepositoryNotFound,
    P3RepositoryPage,
    P3RepositoryValidationError,
)
from app.p3_source_eligibility_schemas import P3SourceType


MAX_VERSION_ALLOCATION_ATTEMPTS = 3
_EMPTY_CONTENT_PAYLOAD: dict[str, object] = {}
_EMPTY_CONTENT_HASH = hashlib.sha256(b"{}").hexdigest()
_SAFE_FAILURE_MESSAGE_LIMIT = 500


@dataclass(frozen=True)
class P3AssetVersionSourceSnapshotInput:
    """Prepared immutable source evidence accepted from the Service layer."""

    source_item_id: str
    source_type: P3SourceType
    source_id: str
    source_version: int | None
    source_fingerprint: str
    approved_review_id: str | None
    snapshot_id: str | None
    knowledge_asset_id: str | None
    lineage_manifest_hash: str
    source_trace_snapshot: dict[str, object]


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


def _validate_asset_type(value: object) -> ReuseAssetType:
    if not isinstance(value, ReuseAssetType):
        raise P3RepositoryValidationError(
            "asset_type must be a ReuseAssetType value."
        )
    return value


def _validate_generation_mode(value: object) -> ReuseGenerationMode:
    if not isinstance(value, ReuseGenerationMode):
        raise P3RepositoryValidationError(
            "generation_mode must be a ReuseGenerationMode value."
        )
    return value


def _validate_status_filter(
    value: object,
) -> ReuseAssetVersionStatus | None:
    if value is None:
        return None
    if not isinstance(value, ReuseAssetVersionStatus):
        raise P3RepositoryValidationError(
            "status must be a ReuseAssetVersionStatus value."
        )
    return value


def _canonical_json(value: object, field: str) -> tuple[object, str]:
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
    return normalized, encoded


def _content_payload(value: object) -> tuple[dict[str, object], str]:
    if not isinstance(value, dict):
        raise P3RepositoryValidationError(
            "content_payload must be a JSON object."
        )
    normalized, encoded = _canonical_json(value, "content_payload")
    assert isinstance(normalized, dict)
    return normalized, hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _safe_failure_message(value: object) -> str:
    message = _required_text(value, "failure_message", 10_000)
    first_line = message.splitlines()[0].strip()
    redacted = re.sub(
        r"(?i)\b(?:postgresql|postgres|mysql|sqlite|https?)://\S+",
        "[redacted]",
        first_line,
    )
    redacted = re.sub(
        r"(?i)\b(?:bearer\s+|token|secret|password|api[_-]?key)"
        r"\s*[:=]?\s*\S+",
        "[redacted]",
        redacted,
    )
    if not redacted or "traceback" in redacted.lower():
        redacted = "Draft generation failed."
    return redacted[:_SAFE_FAILURE_MESSAGE_LIMIT]


def _find_by_idempotency_key(
    db: Session,
    idempotency_key: str,
) -> ReuseAssetVersion | None:
    return (
        db.query(ReuseAssetVersion)
        .filter(ReuseAssetVersion.idempotency_key == idempotency_key)
        .first()
    )


def _request_matches(
    row: ReuseAssetVersion,
    *,
    project_id: str,
    asset_type: ReuseAssetType,
    generation_mode: ReuseGenerationMode,
    template_key: str,
    template_version: str,
    source_manifest_hash: str,
    created_by_role: str,
) -> bool:
    return (
        row.project_id == project_id
        and row.asset_type == asset_type
        and row.generation_mode == generation_mode
        and row.template_key == template_key
        and row.template_version == template_version
        and row.source_manifest_hash == source_manifest_hash
        and row.created_by_role == created_by_role
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


def _snapshot_values(
    snapshot: P3AssetVersionSourceSnapshotInput,
) -> dict[str, object]:
    if not isinstance(snapshot, P3AssetVersionSourceSnapshotInput):
        raise P3RepositoryValidationError(
            "source snapshot must use P3AssetVersionSourceSnapshotInput."
        )
    if not isinstance(snapshot.source_type, P3SourceType):
        raise P3RepositoryValidationError(
            "source_type must be a governed P3SourceType value."
        )
    source_version = snapshot.source_version
    if (
        source_version is not None
        and (
            isinstance(source_version, bool)
            or not isinstance(source_version, int)
            or source_version < 1
        )
    ):
        raise P3RepositoryValidationError(
            "source_version must be null or a positive integer."
        )
    trace, _encoded = _canonical_json(
        snapshot.source_trace_snapshot,
        "source_trace_snapshot",
    )
    if not isinstance(trace, dict):
        raise P3RepositoryValidationError(
            "source_trace_snapshot must be a JSON object."
        )
    return {
        "source_item_id": _required_text(
            snapshot.source_item_id,
            "source_item_id",
            200,
        ),
        "source_type": snapshot.source_type,
        "source_id": _required_text(snapshot.source_id, "source_id", 200),
        "source_version": source_version,
        "source_fingerprint": _required_text(
            snapshot.source_fingerprint,
            "source_fingerprint",
            128,
        ),
        "approved_review_id": _optional_text(
            snapshot.approved_review_id,
            "approved_review_id",
            200,
        ),
        "snapshot_id": _optional_text(
            snapshot.snapshot_id,
            "snapshot_id",
            200,
        ),
        "knowledge_asset_id": _optional_text(
            snapshot.knowledge_asset_id,
            "knowledge_asset_id",
            200,
        ),
        "lineage_manifest_hash": _required_text(
            snapshot.lineage_manifest_hash,
            "lineage_manifest_hash",
            128,
        ),
        "source_trace_snapshot": trace,
    }


def _snapshot_matches(
    row: ReuseAssetVersionSource,
    values: dict[str, object],
) -> bool:
    return all(getattr(row, field) == value for field, value in values.items())


def _existing_snapshot_rows(
    db: Session,
    asset_version_id: str,
) -> dict[str, ReuseAssetVersionSource]:
    rows = (
        db.query(ReuseAssetVersionSource)
        .filter(ReuseAssetVersionSource.asset_version_id == asset_version_id)
        .all()
    )
    return {row.source_item_id: row for row in rows}


def _verify_snapshot_replay(
    db: Session,
    asset_version: ReuseAssetVersion,
    snapshots: list[dict[str, object]],
) -> None:
    existing = _existing_snapshot_rows(db, asset_version.id)
    if len(existing) != len(snapshots):
        raise P3RepositoryConflict(
            "Asset version idempotency key is bound to different sources."
        )
    for values in snapshots:
        source_item_id = str(values["source_item_id"])
        row = existing.get(source_item_id)
        if row is None or not _snapshot_matches(row, values):
            raise P3RepositoryConflict(
                "Asset version source evidence conflicts with the saved snapshot."
            )


def create_asset_version_with_source_snapshots(
    db: Session,
    *,
    project_id: str,
    asset_type: ReuseAssetType,
    generation_mode: ReuseGenerationMode,
    template_key: str,
    template_version: str,
    source_manifest_hash: str,
    idempotency_key: str,
    created_by_role: str,
    request_id: str,
    source_snapshots: Iterable[P3AssetVersionSourceSnapshotInput],
) -> ReuseAssetVersion:
    """Atomically create a generating version and immutable source snapshots."""

    normalized_project_id = _required_text(project_id, "project_id", 200)
    normalized_type = _validate_asset_type(asset_type)
    normalized_mode = _validate_generation_mode(generation_mode)
    normalized_template_key = _required_text(template_key, "template_key", 200)
    normalized_template_version = _required_text(
        template_version,
        "template_version",
        100,
    )
    normalized_manifest_hash = _required_text(
        source_manifest_hash,
        "source_manifest_hash",
        128,
    )
    normalized_idempotency_key = _required_text(
        idempotency_key,
        "idempotency_key",
        200,
    )
    normalized_role = _required_text(created_by_role, "created_by_role", 50)
    normalized_request_id = _required_text(request_id, "request_id", 200)
    snapshot_values = [_snapshot_values(item) for item in source_snapshots]
    source_ids = [str(item["source_item_id"]) for item in snapshot_values]
    if len(source_ids) != len(set(source_ids)):
        raise P3RepositoryValidationError(
            "source snapshots must not repeat a source_item_id."
        )

    project = db.get(ReuseProject, normalized_project_id)
    if project is None:
        raise P3RepositoryNotFound("Reuse project was not found.")
    for source_item_id in source_ids:
        source = db.get(ReuseSourceItem, source_item_id)
        if source is None or source.project_id != normalized_project_id:
            raise P3RepositoryValidationError(
                "Source item does not belong to the asset version project."
            )

    existing = _find_by_idempotency_key(db, normalized_idempotency_key)
    if existing is not None:
        if not _request_matches(
            existing,
            project_id=normalized_project_id,
            asset_type=normalized_type,
            generation_mode=normalized_mode,
            template_key=normalized_template_key,
            template_version=normalized_template_version,
            source_manifest_hash=normalized_manifest_hash,
            created_by_role=normalized_role,
        ):
            raise P3RepositoryConflict(
                "Asset version idempotency key is bound to a different request."
            )
        _verify_snapshot_replay(db, existing, snapshot_values)
        return existing

    asset_version_id = _stable_id(
        "reuse_asset_version",
        normalized_idempotency_key,
    )
    for attempt in range(MAX_VERSION_ALLOCATION_ATTEMPTS):
        version_number = _next_version_number(
            db,
            project_id=normalized_project_id,
            asset_type=normalized_type,
        )
        row = ReuseAssetVersion(
            id=asset_version_id,
            project_id=normalized_project_id,
            asset_type=normalized_type,
            version_number=version_number,
            status=ReuseAssetVersionStatus.GENERATING,
            generation_mode=normalized_mode,
            template_key=normalized_template_key,
            template_version=normalized_template_version,
            content_payload=dict(_EMPTY_CONTENT_PAYLOAD),
            content_hash=_EMPTY_CONTENT_HASH,
            source_manifest_hash=normalized_manifest_hash,
            idempotency_key=normalized_idempotency_key,
            created_by_role=normalized_role,
            request_id=normalized_request_id,
        )
        db.add(row)
        try:
            # There are deliberately no ORM relationships between the frozen
            # snapshot and its mutable source selection.  Flush the parent
            # explicitly so every supported database observes FK ordering
            # while the whole operation remains one transaction.
            db.flush([row])
            for values in snapshot_values:
                source_item_id = str(values["source_item_id"])
                db.add(
                    ReuseAssetVersionSource(
                        id=_stable_id(
                            "reuse_asset_source",
                            row.id,
                            source_item_id,
                        ),
                        asset_version_id=row.id,
                        **values,
                    )
                )
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raced = _find_by_idempotency_key(
                db,
                normalized_idempotency_key,
            )
            if raced is not None:
                if not _request_matches(
                    raced,
                    project_id=normalized_project_id,
                    asset_type=normalized_type,
                    generation_mode=normalized_mode,
                    template_key=normalized_template_key,
                    template_version=normalized_template_version,
                    source_manifest_hash=normalized_manifest_hash,
                    created_by_role=normalized_role,
                ):
                    raise P3RepositoryConflict(
                        "Asset version idempotency key is bound to a "
                        "different request."
                    ) from exc
                _verify_snapshot_replay(db, raced, snapshot_values)
                return raced
            if attempt + 1 >= MAX_VERSION_ALLOCATION_ATTEMPTS:
                raise P3RepositoryConflict(
                    "Concurrent asset version allocation conflict."
                ) from exc
            continue
        db.refresh(row)
        return row
    raise P3RepositoryConflict("Asset version allocation failed.")


def create_generating_asset_version(
    db: Session,
    *,
    project_id: str,
    asset_type: ReuseAssetType,
    generation_mode: ReuseGenerationMode,
    template_key: str,
    template_version: str,
    source_manifest_hash: str,
    idempotency_key: str,
    created_by_role: str,
    request_id: str,
) -> ReuseAssetVersion:
    return create_asset_version_with_source_snapshots(
        db,
        project_id=project_id,
        asset_type=asset_type,
        generation_mode=generation_mode,
        template_key=template_key,
        template_version=template_version,
        source_manifest_hash=source_manifest_hash,
        idempotency_key=idempotency_key,
        created_by_role=created_by_role,
        request_id=request_id,
        source_snapshots=(),
    )


def get_asset_version_by_id(
    db: Session,
    asset_version_id: str,
) -> ReuseAssetVersion:
    normalized_id = _required_text(asset_version_id, "asset_version_id", 200)
    row = db.get(ReuseAssetVersion, normalized_id)
    if row is None:
        raise P3RepositoryNotFound("Reuse asset version was not found.")
    return row


def get_asset_version_by_idempotency_key(
    db: Session,
    idempotency_key: str,
) -> ReuseAssetVersion:
    normalized_key = _required_text(idempotency_key, "idempotency_key", 200)
    row = _find_by_idempotency_key(db, normalized_key)
    if row is None:
        raise P3RepositoryNotFound("Reuse asset version was not found.")
    return row


def list_project_asset_versions(
    db: Session,
    *,
    project_id: str,
    asset_type: ReuseAssetType | None = None,
    status: ReuseAssetVersionStatus | None = None,
    limit: int = DEFAULT_PAGE_LIMIT,
    offset: int = 0,
) -> P3RepositoryPage[ReuseAssetVersion]:
    normalized_project_id = _required_text(project_id, "project_id", 200)
    normalized_limit, normalized_offset = _validate_pagination(limit, offset)
    query = db.query(ReuseAssetVersion).filter(
        ReuseAssetVersion.project_id == normalized_project_id
    )
    if asset_type is not None:
        query = query.filter(
            ReuseAssetVersion.asset_type == _validate_asset_type(asset_type)
        )
    normalized_status = _validate_status_filter(status)
    if normalized_status is not None:
        query = query.filter(ReuseAssetVersion.status == normalized_status)
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


def mark_asset_generated(
    db: Session,
    asset_version_id: str,
    *,
    content_payload: dict[str, object],
) -> ReuseAssetVersion:
    row = get_asset_version_by_id(db, asset_version_id)
    normalized_payload, content_hash = _content_payload(content_payload)
    if row.status is ReuseAssetVersionStatus.GENERATED:
        if row.content_hash == content_hash and row.content_payload == normalized_payload:
            return row
        raise P3RepositoryConflict(
            "Generated asset content is immutable."
        )
    if row.status is not ReuseAssetVersionStatus.GENERATING:
        raise P3RepositoryConflict(
            "Only a generating asset version may become generated."
        )
    row.content_payload = normalized_payload
    row.content_hash = content_hash
    row.status = ReuseAssetVersionStatus.GENERATED
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise P3RepositoryConflict(
            "Asset generated-state persistence conflict."
        ) from exc
    db.refresh(row)
    return row


def mark_asset_failed(
    db: Session,
    asset_version_id: str,
    *,
    failure_code: str,
    failure_message: str,
) -> ReuseAssetVersion:
    row = get_asset_version_by_id(db, asset_version_id)
    normalized_code = _required_text(failure_code, "failure_code", 100)
    if not re.fullmatch(r"[A-Z][A-Z0-9_]*", normalized_code):
        raise P3RepositoryValidationError(
            "failure_code must be a stable uppercase identifier."
        )
    safe_message = _safe_failure_message(failure_message)
    if row.status is ReuseAssetVersionStatus.FAILED:
        if (
            row.failure_code == normalized_code
            and row.failure_message == safe_message
        ):
            return row
        raise P3RepositoryConflict("Failed asset evidence is immutable.")
    if row.status is not ReuseAssetVersionStatus.GENERATING:
        raise P3RepositoryConflict(
            "Only a generating asset version may become failed."
        )
    row.status = ReuseAssetVersionStatus.FAILED
    row.failure_code = normalized_code
    row.failure_message = safe_message
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise P3RepositoryConflict(
            "Asset failed-state persistence conflict."
        ) from exc
    db.refresh(row)
    return row


def add_asset_version_source_snapshot(
    db: Session,
    *,
    asset_version_id: str,
    snapshot: P3AssetVersionSourceSnapshotInput,
) -> ReuseAssetVersionSource:
    version = get_asset_version_by_id(db, asset_version_id)
    values = _snapshot_values(snapshot)
    source_item_id = str(values["source_item_id"])
    source = db.get(ReuseSourceItem, source_item_id)
    if source is None or source.project_id != version.project_id:
        raise P3RepositoryValidationError(
            "Source item does not belong to the asset version project."
        )
    existing = (
        db.query(ReuseAssetVersionSource)
        .filter(
            ReuseAssetVersionSource.asset_version_id == version.id,
            ReuseAssetVersionSource.source_item_id == source_item_id,
        )
        .first()
    )
    if existing is not None:
        if _snapshot_matches(existing, values):
            return existing
        raise P3RepositoryConflict(
            "Asset version source evidence conflicts with the saved snapshot."
        )
    if version.status != ReuseAssetVersionStatus.GENERATING:
        raise P3RepositoryConflict(
            "Source snapshots are immutable after generation finishes."
        )
    row = ReuseAssetVersionSource(
        id=_stable_id("reuse_asset_source", version.id, source_item_id),
        asset_version_id=version.id,
        **values,
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raced = (
            db.query(ReuseAssetVersionSource)
            .filter(
                ReuseAssetVersionSource.asset_version_id == version.id,
                ReuseAssetVersionSource.source_item_id == source_item_id,
            )
            .first()
        )
        if raced is not None and _snapshot_matches(raced, values):
            return raced
        raise P3RepositoryConflict(
            "Asset version source persistence conflict."
        ) from exc
    db.refresh(row)
    return row


def list_asset_version_sources(
    db: Session,
    *,
    asset_version_id: str,
    limit: int = DEFAULT_PAGE_LIMIT,
    offset: int = 0,
) -> P3RepositoryPage[ReuseAssetVersionSource]:
    version = get_asset_version_by_id(db, asset_version_id)
    normalized_limit, normalized_offset = _validate_pagination(limit, offset)
    query = db.query(ReuseAssetVersionSource).filter(
        ReuseAssetVersionSource.asset_version_id == version.id
    )
    total = (
        query.with_entities(func.count(ReuseAssetVersionSource.id)).scalar()
        or 0
    )
    rows = (
        query.order_by(ReuseAssetVersionSource.id.asc())
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
    "MAX_VERSION_ALLOCATION_ATTEMPTS",
    "P3AssetVersionSourceSnapshotInput",
    "add_asset_version_source_snapshot",
    "create_asset_version_with_source_snapshots",
    "create_generating_asset_version",
    "get_asset_version_by_id",
    "get_asset_version_by_idempotency_key",
    "list_asset_version_sources",
    "list_project_asset_versions",
    "mark_asset_failed",
    "mark_asset_generated",
]

"""Persistence-only repositories for P3 Export Jobs and Artifacts."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.p3_export_models import (
    P3ExportArtifact,
    P3ExportFormat,
    P3ExportJob,
    P3ExportJobStatus,
)
from app.p3_reuse_repositories import (
    DEFAULT_PAGE_LIMIT,
    MAX_PAGE_LIMIT,
    P3RepositoryConflict,
    P3RepositoryNotFound,
    P3RepositoryPage,
    P3RepositoryValidationError,
)


@dataclass(frozen=True)
class P3ExportPersistenceResult:
    job: P3ExportJob
    artifact: P3ExportArtifact | None
    replayed: bool = False


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _stable_id(prefix: str, *parts: object) -> str:
    encoded = json.dumps(
        [str(part) for part in parts],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(encoded).hexdigest()[:20]}"


def _required_text(value: object, field: str, maximum: int) -> str:
    if not isinstance(value, str):
        raise P3RepositoryValidationError(f"{field} must be a string.")
    normalized = value.strip()
    if not normalized or len(normalized) > maximum:
        raise P3RepositoryValidationError(f"{field} is invalid.")
    return normalized


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
        return "Export failed."
    return redacted[:500]


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
        raise P3RepositoryValidationError("offset must be non-negative.")
    return limit, offset


def get_export_job_by_id(db: Session, job_id: str) -> P3ExportJob:
    row = db.get(P3ExportJob, _required_text(job_id, "job_id", 200))
    if row is None:
        raise P3RepositoryNotFound("Export Job was not found.")
    return row


def get_export_job_by_idempotency_key(
    db: Session,
    idempotency_key: str,
) -> P3ExportJob:
    key = _required_text(idempotency_key, "idempotency_key", 200)
    row = (
        db.query(P3ExportJob)
        .filter(P3ExportJob.idempotency_key == key)
        .first()
    )
    if row is None:
        raise P3RepositoryNotFound("Export Job was not found.")
    return row


def get_export_job_by_revoke_idempotency_key(
    db: Session,
    idempotency_key: str,
) -> P3ExportJob:
    key = _required_text(idempotency_key, "idempotency_key", 200)
    row = (
        db.query(P3ExportJob)
        .filter(P3ExportJob.revoke_idempotency_key == key)
        .first()
    )
    if row is None:
        raise P3RepositoryNotFound("Export Job was not found.")
    return row


def get_export_artifact_by_job_id(
    db: Session,
    job_id: str,
) -> P3ExportArtifact:
    normalized = _required_text(job_id, "job_id", 200)
    row = (
        db.query(P3ExportArtifact)
        .filter(P3ExportArtifact.export_job_id == normalized)
        .first()
    )
    if row is None:
        raise P3RepositoryNotFound("Export Artifact was not found.")
    return row


def get_export_artifact_by_id(
    db: Session,
    artifact_id: str,
) -> P3ExportArtifact:
    row = db.get(
        P3ExportArtifact,
        _required_text(artifact_id, "artifact_id", 200),
    )
    if row is None:
        raise P3RepositoryNotFound("Export Artifact was not found.")
    return row


def create_pending_export_job(
    db: Session,
    *,
    project_id: str,
    asset_version_id: str,
    export_format: P3ExportFormat,
    export_policy_version: str,
    requested_by_role: str,
    request_id: str,
    idempotency_key: str,
    request_fingerprint: str,
) -> P3ExportPersistenceResult:
    project = _required_text(project_id, "project_id", 200)
    asset = _required_text(asset_version_id, "asset_version_id", 200)
    policy = _required_text(export_policy_version, "export_policy_version", 100)
    role = _required_text(requested_by_role, "requested_by_role", 50)
    request = _required_text(request_id, "request_id", 200)
    key = _required_text(idempotency_key, "idempotency_key", 200)
    fingerprint = _required_text(
        request_fingerprint,
        "request_fingerprint",
        128,
    )
    if not isinstance(export_format, P3ExportFormat):
        raise P3RepositoryValidationError("export_format is invalid.")
    existing = (
        db.query(P3ExportJob)
        .filter(P3ExportJob.idempotency_key == key)
        .first()
    )
    if existing is not None:
        if existing.request_fingerprint != fingerprint:
            raise P3RepositoryConflict("Export idempotency conflict.")
        artifact = (
            db.query(P3ExportArtifact)
            .filter(P3ExportArtifact.export_job_id == existing.id)
            .first()
        )
        return P3ExportPersistenceResult(existing, artifact, replayed=True)
    row = P3ExportJob(
        id=_stable_id("p3_export_job", key),
        project_id=project,
        asset_version_id=asset,
        export_format=export_format,
        status=P3ExportJobStatus.PENDING,
        export_policy_version=policy,
        requested_by_role=role,
        request_id=request,
        idempotency_key=key,
        request_fingerprint=fingerprint,
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raced = (
            db.query(P3ExportJob)
            .filter(P3ExportJob.idempotency_key == key)
            .first()
        )
        if raced is not None and raced.request_fingerprint == fingerprint:
            artifact = (
                db.query(P3ExportArtifact)
                .filter(P3ExportArtifact.export_job_id == raced.id)
                .first()
            )
            return P3ExportPersistenceResult(raced, artifact, replayed=True)
        raise P3RepositoryConflict("Concurrent export conflict.") from exc
    db.refresh(row)
    return P3ExportPersistenceResult(row, None)


def mark_export_job_running(db: Session, job_id: str) -> P3ExportJob:
    row = get_export_job_by_id(db, job_id)
    if row.status is not P3ExportJobStatus.PENDING:
        raise P3RepositoryConflict("Only a pending Export Job may run.")
    row.status = P3ExportJobStatus.RUNNING
    row.started_at = _utcnow()
    db.commit()
    db.refresh(row)
    return row


def complete_export_job(
    db: Session,
    *,
    job_id: str,
    storage_backend: str,
    storage_key: str,
    safe_file_name: str,
    content_type: str,
    encoding: str,
    byte_size: int,
    row_count: int,
    artifact_sha256: str,
    export_manifest_hash: str,
) -> P3ExportPersistenceResult:
    row = get_export_job_by_id(db, job_id)
    if row.status is not P3ExportJobStatus.RUNNING:
        raise P3RepositoryConflict("Only a running Export Job may succeed.")
    if (
        isinstance(byte_size, bool)
        or not isinstance(byte_size, int)
        or byte_size < 0
        or isinstance(row_count, bool)
        or not isinstance(row_count, int)
        or row_count < 0
    ):
        raise P3RepositoryValidationError("Artifact counts are invalid.")
    artifact = P3ExportArtifact(
        id=_stable_id("p3_export_artifact", row.id),
        export_job_id=row.id,
        asset_version_id=row.asset_version_id,
        export_format=row.export_format,
        storage_backend=_required_text(storage_backend, "storage_backend", 50),
        storage_key=_required_text(storage_key, "storage_key", 500),
        safe_file_name=_required_text(safe_file_name, "safe_file_name", 255),
        content_type=_required_text(content_type, "content_type", 100),
        encoding=_required_text(encoding, "encoding", 50),
        byte_size=byte_size,
        row_count=row_count,
        artifact_sha256=_required_text(
            artifact_sha256,
            "artifact_sha256",
            128,
        ),
        export_manifest_hash=_required_text(
            export_manifest_hash,
            "export_manifest_hash",
            128,
        ),
    )
    row.status = P3ExportJobStatus.SUCCEEDED
    row.completed_at = _utcnow()
    db.add(artifact)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise P3RepositoryConflict("Export completion conflict.") from exc
    db.refresh(row)
    db.refresh(artifact)
    return P3ExportPersistenceResult(row, artifact)


def fail_export_job(
    db: Session,
    *,
    job_id: str,
    failure_code: str,
    failure_message: str,
) -> P3ExportJob:
    row = get_export_job_by_id(db, job_id)
    if row.status not in {
        P3ExportJobStatus.PENDING,
        P3ExportJobStatus.RUNNING,
    }:
        raise P3RepositoryConflict("Export Job cannot be marked failed.")
    row.status = P3ExportJobStatus.FAILED
    row.failed_at = _utcnow()
    row.failure_code = _required_text(failure_code, "failure_code", 100)
    row.failure_message = _safe_failure_message(failure_message)
    db.commit()
    db.refresh(row)
    return row


def revoke_succeeded_export(
    db: Session,
    *,
    job_id: str,
    actor_role: str,
    request_id: str,
    idempotency_key: str,
) -> P3ExportPersistenceResult:
    normalized_id = _required_text(job_id, "job_id", 200)
    role = _required_text(actor_role, "actor_role", 50)
    request = _required_text(request_id, "request_id", 200)
    key = _required_text(idempotency_key, "idempotency_key", 200)
    replay = (
        db.query(P3ExportJob)
        .filter(P3ExportJob.revoke_idempotency_key == key)
        .first()
    )
    if replay is not None:
        if replay.id != normalized_id:
            raise P3RepositoryConflict("Revoke idempotency conflict.")
        return P3ExportPersistenceResult(
            replay,
            get_export_artifact_by_job_id(db, replay.id),
            replayed=True,
        )
    job = get_export_job_by_id(db, normalized_id)
    artifact = get_export_artifact_by_job_id(db, normalized_id)
    if job.status is not P3ExportJobStatus.SUCCEEDED:
        raise P3RepositoryConflict("Only a succeeded Export Job may be revoked.")
    revoked_at = _utcnow()
    job.status = P3ExportJobStatus.REVOKED
    job.revoked_at = revoked_at
    job.revoked_by_role = role
    job.revoke_request_id = request
    job.revoke_idempotency_key = key
    artifact.revoked_at = revoked_at
    artifact.revoked_by_role = role
    artifact.revoke_request_id = request
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raced = (
            db.query(P3ExportJob)
            .filter(P3ExportJob.revoke_idempotency_key == key)
            .first()
        )
        if raced is not None and raced.id == normalized_id:
            return P3ExportPersistenceResult(
                raced,
                get_export_artifact_by_job_id(db, raced.id),
                replayed=True,
            )
        raise P3RepositoryConflict("Concurrent revoke conflict.") from exc
    db.refresh(job)
    db.refresh(artifact)
    return P3ExportPersistenceResult(job, artifact)


def list_export_jobs(
    db: Session,
    *,
    project_id: str | None = None,
    status: P3ExportJobStatus | None = None,
    export_format: P3ExportFormat | None = None,
    limit: int = DEFAULT_PAGE_LIMIT,
    offset: int = 0,
) -> P3RepositoryPage[P3ExportJob]:
    normalized_limit, normalized_offset = _pagination(limit, offset)
    query = db.query(P3ExportJob)
    if project_id is not None:
        query = query.filter(
            P3ExportJob.project_id
            == _required_text(project_id, "project_id", 200)
        )
    if status is not None:
        if not isinstance(status, P3ExportJobStatus):
            raise P3RepositoryValidationError("status is invalid.")
        query = query.filter(P3ExportJob.status == status)
    if export_format is not None:
        if not isinstance(export_format, P3ExportFormat):
            raise P3RepositoryValidationError("export_format is invalid.")
        query = query.filter(P3ExportJob.export_format == export_format)
    total = query.with_entities(func.count(P3ExportJob.id)).scalar() or 0
    rows = (
        query.order_by(P3ExportJob.created_at.desc(), P3ExportJob.id.desc())
        .offset(normalized_offset)
        .limit(normalized_limit)
        .all()
    )
    return P3RepositoryPage(rows, int(total), normalized_limit, normalized_offset)


__all__ = [
    "P3ExportPersistenceResult",
    "complete_export_job",
    "create_pending_export_job",
    "fail_export_job",
    "get_export_artifact_by_job_id",
    "get_export_artifact_by_id",
    "get_export_job_by_id",
    "get_export_job_by_idempotency_key",
    "get_export_job_by_revoke_idempotency_key",
    "list_export_jobs",
    "mark_export_job_running",
    "revoke_succeeded_export",
]

"""P2-M1 material validation, hashing, deduplication, and persistence."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from sqlalchemy.orm import Session

from app.asset_repositories import (
    DuplicateAssetHashError,
    create_asset,
    get_asset_by_hash,
)
from app.asset_schemas import AssetRecord
from app.asset_storage import AssetStorageAdapter


DEFAULT_MAX_UPLOAD_BYTES = 10 * 1024 * 1024
ALLOWED_IMAGE_TYPES: dict[str, tuple[str, ...]] = {
    "image/jpeg": (".jpg", ".jpeg"),
    "image/png": (".png",),
    "image/webp": (".webp",),
}


@dataclass(frozen=True)
class AssetValidationFailure(Exception):
    code: str
    message: str
    status_code: int
    details: dict[str, object] | None = None


@dataclass(frozen=True)
class DuplicateAssetFailure(Exception):
    asset_id: str


def max_upload_bytes() -> int:
    raw = os.getenv("ASSET_MAX_UPLOAD_BYTES", str(DEFAULT_MAX_UPLOAD_BYTES)).strip()
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_MAX_UPLOAD_BYTES
    return value if value > 0 else DEFAULT_MAX_UPLOAD_BYTES


def _validate_file_name(file_name: str | None) -> str:
    if not file_name:
        raise AssetValidationFailure("INVALID_FILE_NAME", "A file name is required.", 400)
    if len(file_name) > 255 or "\x00" in file_name or "/" in file_name or "\\" in file_name:
        raise AssetValidationFailure("INVALID_FILE_NAME", "The file name is not allowed.", 400)
    return file_name


def _detect_mime_type(content: bytes) -> str | None:
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if len(content) >= 3 and content[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image/webp"
    return None


def validate_asset_upload(
    *,
    file_name: str | None,
    declared_mime_type: str | None,
    content: bytes,
    asset_type: str,
) -> tuple[str, str, str]:
    safe_name = _validate_file_name(file_name)
    if asset_type != "image":
        raise AssetValidationFailure(
            "UNSUPPORTED_ASSET_TYPE",
            "P2-M1 supports image assets only.",
            400,
            {"allowed": ["image"], "future": ["video", "pdf"]},
        )
    if not content:
        raise AssetValidationFailure("EMPTY_FILE", "The uploaded file is empty.", 400)
    limit = max_upload_bytes()
    if len(content) > limit:
        raise AssetValidationFailure(
            "FILE_TOO_LARGE",
            "The uploaded file exceeds the configured size limit.",
            413,
            {"max_bytes": limit},
        )
    declared = (declared_mime_type or "").lower().strip()
    if declared not in ALLOWED_IMAGE_TYPES:
        raise AssetValidationFailure(
            "UNSUPPORTED_FILE_TYPE",
            "Only JPEG, PNG, and WebP images are supported in P2-M1.",
            415,
            {"allowed_mime_types": sorted(ALLOWED_IMAGE_TYPES)},
        )
    detected = _detect_mime_type(content)
    if detected is None or detected != declared:
        raise AssetValidationFailure(
            "INVALID_FILE_CONTENT",
            "The file content does not match its declared image type.",
            415,
        )
    extension = Path(safe_name).suffix.lower()
    if extension not in ALLOWED_IMAGE_TYPES[detected]:
        raise AssetValidationFailure(
            "INVALID_FILE_EXTENSION",
            "The file extension does not match its image type.",
            415,
        )
    return safe_name, detected, extension


def ingest_asset(
    db: Session,
    storage: AssetStorageAdapter,
    *,
    file_name: str | None,
    declared_mime_type: str | None,
    content: bytes,
    asset_type: str,
) -> AssetRecord:
    safe_name, detected_mime, extension = validate_asset_upload(
        file_name=file_name,
        declared_mime_type=declared_mime_type,
        content=content,
        asset_type=asset_type,
    )
    content_hash = hashlib.sha256(content).hexdigest()
    duplicate = get_asset_by_hash(db, content_hash)
    if duplicate is not None:
        raise DuplicateAssetFailure(duplicate.id)

    object_key = f"assets/{content_hash[:2]}/{content_hash}{extension}"
    stored = storage.save(object_key, content)
    asset_id = f"asset_{uuid4().hex[:20]}"
    try:
        return create_asset(
            db,
            asset_id=asset_id,
            asset_type=asset_type,
            file_name=safe_name,
            mime_type=detected_mime,
            size=len(content),
            storage_uri=stored.storage_uri,
            content_hash=content_hash,
            metadata_json={
                "storage_backend": storage.backend_name,
                "object_key": stored.object_key,
                "file_extension": extension,
                "hash_algorithm": "sha256",
                "validation_version": "p2-m1-v1",
            },
        )
    except DuplicateAssetHashError as exc:
        raise DuplicateAssetFailure(exc.asset_id) from exc
    except Exception:
        try:
            storage.delete(object_key)
        except Exception:
            pass
        raise

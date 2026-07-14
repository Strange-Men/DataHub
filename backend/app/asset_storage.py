"""Storage adapter boundary for P2 material binaries.

P2-M1 ships a local filesystem implementation. The contract deliberately uses
opaque object keys and storage URIs so an S3-compatible implementation can be
added without changing the Asset model or API response shape.
"""

from __future__ import annotations

import os
import tempfile
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path


class AssetStorageError(RuntimeError):
    """Safe storage failure that does not expose credentials or filesystem paths."""


@dataclass(frozen=True)
class StoredAssetObject:
    storage_uri: str
    object_key: str
    size: int


class AssetStorageAdapter(ABC):
    """Minimal binary storage contract required by Material Ingestion."""

    backend_name: str

    @abstractmethod
    def save(self, object_key: str, content: bytes) -> StoredAssetObject:
        """Atomically persist content and return its opaque storage identity."""

    @abstractmethod
    def exists(self, object_key: str) -> bool:
        """Return whether the object currently exists."""

    @abstractmethod
    def delete(self, object_key: str) -> None:
        """Delete an object if present; used only for failed metadata commits."""


class LocalFilesystemAssetStorage(AssetStorageAdapter):
    """Filesystem-backed adapter for local development and Render disks."""

    backend_name = "local"

    def __init__(self, root: Path) -> None:
        self.root = root.expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _resolve_key(self, object_key: str) -> Path:
        normalized = object_key.replace("\\", "/").lstrip("/")
        if not normalized or ".." in normalized.split("/"):
            raise AssetStorageError("Invalid asset object key.")
        target = (self.root / normalized).resolve()
        if target != self.root and self.root not in target.parents:
            raise AssetStorageError("Invalid asset object key.")
        return target

    def save(self, object_key: str, content: bytes) -> StoredAssetObject:
        target = self._resolve_key(object_key)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=target.parent,
                prefix=".asset-upload-",
                delete=False,
            ) as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
                temporary_path = Path(handle.name)
            os.replace(temporary_path, target)
        except OSError as exc:
            if temporary_path is not None:
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError:
                    pass
            raise AssetStorageError("Asset object could not be stored.") from exc
        return StoredAssetObject(
            storage_uri=f"local://{object_key}",
            object_key=object_key,
            size=len(content),
        )

    def exists(self, object_key: str) -> bool:
        return self._resolve_key(object_key).is_file()

    def delete(self, object_key: str) -> None:
        try:
            self._resolve_key(object_key).unlink(missing_ok=True)
        except OSError as exc:
            raise AssetStorageError("Asset object could not be deleted.") from exc


def _default_storage_root() -> Path:
    return Path(__file__).resolve().parent.parent / "storage" / "asset_objects"


def get_asset_storage_adapter() -> AssetStorageAdapter:
    """Build the configured storage adapter without caching environment state."""

    backend = os.getenv("ASSET_STORAGE_BACKEND", "local").strip().lower() or "local"
    if backend != "local":
        raise AssetStorageError(
            "Unsupported ASSET_STORAGE_BACKEND. P2-M1 implements only 'local'."
        )
    configured_root = os.getenv("ASSET_STORAGE_ROOT", "").strip()
    on_render = os.getenv("RENDER", "").strip().lower() == "true"
    if on_render and not configured_root:
        raise AssetStorageError(
            "ASSET_STORAGE_ROOT is required on Render and must point to an attached persistent disk."
        )
    if on_render and not Path(configured_root).is_absolute():
        raise AssetStorageError("ASSET_STORAGE_ROOT must be an absolute path on Render.")
    root = Path(configured_root) if configured_root else _default_storage_root()
    return LocalFilesystemAssetStorage(root)

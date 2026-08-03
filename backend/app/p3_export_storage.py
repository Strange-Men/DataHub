"""Opaque and path-safe local Artifact storage for governed P3 exports."""

from __future__ import annotations

import os
import tempfile
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import BinaryIO

from app.storage_readiness import StorageReadiness, existing_directory_ready


class P3ExportStorageError(RuntimeError):
    """Safe storage error that never exposes an absolute filesystem path."""


@dataclass(frozen=True)
class P3StoredArtifact:
    storage_backend: str
    storage_key: str
    byte_size: int


@dataclass(frozen=True)
class P3ArtifactStat:
    storage_backend: str
    storage_key: str
    byte_size: int


class P3ExportArtifactStorage(ABC):
    """Minimal immutable Artifact storage contract for M7."""

    backend_name: str

    @abstractmethod
    def write_atomic(self, storage_key: str, content: bytes) -> P3StoredArtifact:
        """Atomically write one complete Artifact."""

    @abstractmethod
    def open_read(self, storage_key: str) -> BinaryIO:
        """Open an existing Artifact as a binary stream."""

    @abstractmethod
    def exists(self, storage_key: str) -> bool:
        """Return whether an Artifact exists."""

    @abstractmethod
    def stat(self, storage_key: str) -> P3ArtifactStat:
        """Return safe Artifact metadata without exposing a filesystem path."""

    @abstractmethod
    def cleanup_incomplete(self, storage_key: str) -> None:
        """Remove only an uncommitted write after export persistence fails."""


class LocalFilesystemP3ExportStorage(P3ExportArtifactStorage):
    """Local-only, root-confined Artifact storage with atomic replacement."""

    backend_name = "local_filesystem"

    def __init__(self, root: Path) -> None:
        expanded = root.expanduser()
        if expanded.exists() and expanded.is_symlink():
            raise P3ExportStorageError("Export storage root is invalid.")
        self.root = expanded.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _normalized_key(storage_key: str) -> PurePosixPath:
        if not isinstance(storage_key, str):
            raise P3ExportStorageError("Export storage key is invalid.")
        raw = storage_key.strip().replace("\\", "/")
        key = PurePosixPath(raw)
        if (
            not raw
            or raw.startswith("/")
            or key.is_absolute()
            or ":" in key.parts[0]
            or any(part in {"", ".", ".."} for part in key.parts)
        ):
            raise P3ExportStorageError("Export storage key is invalid.")
        return key

    def _resolve_key(self, storage_key: str) -> Path:
        key = self._normalized_key(storage_key)
        target = self.root.joinpath(*key.parts)
        current = self.root
        for part in key.parts[:-1]:
            current = current / part
            if current.exists() and current.is_symlink():
                raise P3ExportStorageError("Export storage key is invalid.")
        if target.exists() and target.is_symlink():
            raise P3ExportStorageError("Export storage key is invalid.")
        resolved = target.resolve()
        if resolved != self.root and self.root not in resolved.parents:
            raise P3ExportStorageError("Export storage key is invalid.")
        return resolved

    def write_atomic(self, storage_key: str, content: bytes) -> P3StoredArtifact:
        if not isinstance(content, bytes):
            raise P3ExportStorageError("Export Artifact content is invalid.")
        target = self._resolve_key(storage_key)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.parent.resolve() != self.root and (
                self.root not in target.parent.resolve().parents
            ):
                raise P3ExportStorageError("Export storage key is invalid.")
        except OSError as exc:
            raise P3ExportStorageError(
                "Export Artifact directory is unavailable."
            ) from exc
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=target.parent,
                prefix=".p3-export-",
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
            raise P3ExportStorageError(
                "Export Artifact could not be stored."
            ) from exc
        return P3StoredArtifact(
            storage_backend=self.backend_name,
            storage_key=storage_key,
            byte_size=len(content),
        )

    def open_read(self, storage_key: str) -> BinaryIO:
        target = self._resolve_key(storage_key)
        if not target.is_file():
            raise P3ExportStorageError("Export Artifact is unavailable.")
        try:
            return target.open("rb")
        except OSError as exc:
            raise P3ExportStorageError(
                "Export Artifact is unavailable."
            ) from exc

    def exists(self, storage_key: str) -> bool:
        return self._resolve_key(storage_key).is_file()

    def stat(self, storage_key: str) -> P3ArtifactStat:
        target = self._resolve_key(storage_key)
        if not target.is_file():
            raise P3ExportStorageError("Export Artifact is unavailable.")
        try:
            size = target.stat().st_size
        except OSError as exc:
            raise P3ExportStorageError(
                "Export Artifact is unavailable."
            ) from exc
        return P3ArtifactStat(
            storage_backend=self.backend_name,
            storage_key=storage_key,
            byte_size=size,
        )

    def cleanup_incomplete(self, storage_key: str) -> None:
        target = self._resolve_key(storage_key)
        try:
            target.unlink(missing_ok=True)
        except OSError as exc:
            raise P3ExportStorageError(
                "Incomplete Export Artifact could not be cleaned."
            ) from exc


def _default_export_root() -> Path:
    return Path(__file__).resolve().parents[2] / ".local-data" / "p3-exports"


@dataclass(frozen=True)
class _P3ExportStorageConfiguration:
    root: Path


def _p3_export_storage_configuration() -> _P3ExportStorageConfiguration:
    """Resolve and validate the one configuration shared by factory and probe."""

    backend = (
        os.getenv("P3_EXPORT_STORAGE_BACKEND", "local_filesystem")
        .strip()
        .lower()
        or "local_filesystem"
    )
    if backend != "local_filesystem":
        raise P3ExportStorageError(
            "Unsupported P3 export storage backend."
        )
    configured_root = os.getenv("P3_EXPORT_STORAGE_ROOT", "").strip()
    root = Path(configured_root) if configured_root else _default_export_root()
    return _P3ExportStorageConfiguration(root=root)


def check_p3_export_storage_readiness() -> StorageReadiness:
    """Inspect configured storage without instantiating the mkdir-capable adapter."""

    try:
        configuration = _p3_export_storage_configuration()
    except P3ExportStorageError:
        return StorageReadiness(ready=False, local_only=True)
    return StorageReadiness(
        ready=existing_directory_ready(
            configuration.root,
            reject_root_symlink=True,
        ),
        local_only=True,
    )


def get_p3_export_storage() -> P3ExportArtifactStorage:
    """Build the configured local storage adapter without caching env state."""

    configuration = _p3_export_storage_configuration()
    return LocalFilesystemP3ExportStorage(configuration.root)


__all__ = [
    "LocalFilesystemP3ExportStorage",
    "P3ArtifactStat",
    "P3ExportArtifactStorage",
    "P3ExportStorageError",
    "P3StoredArtifact",
    "check_p3_export_storage_readiness",
    "get_p3_export_storage",
]

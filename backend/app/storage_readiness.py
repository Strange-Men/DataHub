"""Shared zero-write readiness primitives for filesystem storage adapters."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import stat


@dataclass(frozen=True)
class StorageReadiness:
    ready: bool
    local_only: bool


def existing_directory_ready(
    path: Path,
    *,
    reject_root_symlink: bool = False,
) -> bool:
    """Inspect an existing directory without creating or modifying anything."""

    try:
        expanded = path.expanduser()
        if reject_root_symlink and expanded.is_symlink():
            return False
        metadata = expanded.stat()
        return stat.S_ISDIR(metadata.st_mode) and os.access(
            expanded,
            os.R_OK | os.W_OK | os.X_OK,
        )
    except (OSError, RuntimeError):
        return False


__all__ = ["StorageReadiness", "existing_directory_ready"]

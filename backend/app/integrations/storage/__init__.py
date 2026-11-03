"""Storage for generated exports and uploaded imports.

`get_storage` is the only entry point, so the backend is a configuration change
rather than an edit to every module that writes a file (architecture.md section 18).
"""

from __future__ import annotations

from app.core.config import Settings, get_settings
from app.integrations.storage.base import StorageAdapter, StorageError
from app.integrations.storage.local import LocalFileStorage

__all__ = ["LocalFileStorage", "StorageAdapter", "StorageError", "get_storage"]


def get_storage(settings: Settings | None = None) -> StorageAdapter:
    """The configured storage adapter."""
    active = settings or get_settings()
    return LocalFileStorage(active.storage_root)

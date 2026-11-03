"""Filesystem-backed storage.

The first adapter for the `StorageAdapter` contract. It is deliberately the only
place that knows about paths: everything else addresses files by key.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from app.integrations.storage.base import StorageError


class LocalFileStorage:
    """Stores files under one directory."""

    def __init__(self, root: Path) -> None:
        self._root = root.resolve()

    @property
    def root(self) -> Path:
        return self._root

    def _resolve(self, key: str) -> Path:
        """Turn a key into a path inside the root, or refuse.

        Keys are generated server-side, but the check is here anyway: a key that
        escaped the root would let a download endpoint read any file the process
        can open, and the cost of the check is a path comparison.
        """
        if not key or key.startswith("/") or "\\" in key:
            raise StorageError(f"Invalid storage key: {key!r}")
        parts = Path(key).parts
        if any(part in ("..", ".") for part in parts):
            raise StorageError(f"Invalid storage key: {key!r}")
        target = (self._root / key).resolve()
        if self._root not in target.parents:
            raise StorageError("Storage key escapes the storage root")
        return target

    def save(self, key: str, data: bytes) -> str:
        target = self._resolve(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return key

    def read(self, key: str) -> bytes:
        target = self._resolve(key)
        if not target.is_file():
            raise StorageError(f"No stored object for key '{key}'")
        return target.read_bytes()

    def exists(self, key: str) -> bool:
        try:
            return self._resolve(key).is_file()
        except StorageError:
            return False

    def delete(self, key: str) -> None:
        target = self._resolve(key)
        if target.is_file():
            target.unlink()

    def list_keys(self) -> list[str]:
        if not self._root.is_dir():
            return []
        return sorted(
            path.relative_to(self._root).as_posix()
            for path in self._root.rglob("*")
            if path.is_file()
        )

    def purge_older_than(self, moment: datetime, prefix: str | None = None) -> int:
        """Delete files last written before `moment`.

        Expiry is by file age rather than by a row, because a file whose row was
        deleted would otherwise stay on disk forever.
        """
        cutoff = moment.timestamp()
        removed = 0
        for key in self.list_keys():
            if prefix is not None and not key.startswith(f"{prefix}/"):
                continue
            target = self._resolve(key)
            try:
                if target.stat().st_mtime < cutoff:
                    target.unlink()
                    removed += 1
            except OSError:
                continue
        return removed

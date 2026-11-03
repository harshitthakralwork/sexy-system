"""The storage contract every file backend implements.

Business modules depend on `StorageAdapter`, never on a filesystem path, so the
local disk can be replaced with object storage without touching the modules that
store files (architecture.md section 18).
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable


class StorageError(RuntimeError):
    """The storage backend could not complete the operation.

    Raised rather than returned: a caller that ignored a missing key would
    download a file that was never written.
    """


@runtime_checkable
class StorageAdapter(Protocol):
    """Where generated files and uploaded files live.

    Keys are opaque strings chosen by the caller. They are never exposed to a
    browser as a path, and the adapter is responsible for refusing any key that
    would escape its root.
    """

    def save(self, key: str, data: bytes) -> str:
        """Write `data` under `key` and return the key."""
        ...

    def read(self, key: str) -> bytes:
        """Return the bytes stored under `key`."""
        ...

    def exists(self, key: str) -> bool:
        """Whether a file is stored under `key`."""
        ...

    def delete(self, key: str) -> None:
        """Remove the file under `key`. Removing what is not there is not an error."""
        ...

    def list_keys(self) -> list[str]:
        """Every key currently held."""
        ...

    def purge_older_than(self, moment: datetime, prefix: str | None = None) -> int:
        """Delete files last modified before `moment`. Returns how many went.

        `prefix` limits the sweep to one area of the store, so files with
        different retention windows can share a root.
        """
        ...

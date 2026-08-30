"""Storage backend interface used by deterministic application services."""

from __future__ import annotations

from typing import BinaryIO, Protocol, runtime_checkable

from app.services.storage.contracts import StoredObject


@runtime_checkable
class StorageBackend(Protocol):
    """Persist immutable objects without exposing filesystem paths to callers."""

    def put(
        self,
        key: str,
        stream: BinaryIO,
        content_type: str,
    ) -> StoredObject: ...

    def open(self, key: str) -> BinaryIO: ...

    def exists(self, key: str) -> bool: ...

    def delete(self, key: str) -> None: ...

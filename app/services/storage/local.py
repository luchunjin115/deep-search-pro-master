"""Local filesystem Storage backend with strict key and path containment."""

from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path, PurePosixPath
from typing import BinaryIO
from uuid import uuid4

from app.services.storage.contracts import (
    InvalidStorageKeyError,
    StorageConfigurationError,
    StorageDeleteError,
    StorageError,
    StorageObjectAlreadyExistsError,
    StorageObjectNotFoundError,
    StorageReadError,
    StorageWriteError,
    StoredObject,
    validate_content_type,
    validate_storage_key,
)


class LocalStorageBackend:
    """Store immutable objects below one managed local directory."""

    def __init__(self, root: Path, *, chunk_size_bytes: int = 1024 * 1024) -> None:
        if chunk_size_bytes <= 0:
            raise StorageConfigurationError

        try:
            configured_root = Path(root).expanduser().absolute()
            if configured_root == Path(configured_root.anchor):
                raise StorageConfigurationError
            self._reject_config_symlinks(configured_root)
            configured_root.mkdir(parents=True, exist_ok=True)
            self._reject_config_symlinks(configured_root)
            if not configured_root.is_dir():
                raise StorageConfigurationError
            self._root = configured_root.resolve(strict=True)
        except StorageError:
            raise
        except (OSError, RuntimeError):
            raise StorageConfigurationError from None

        self._chunk_size_bytes = chunk_size_bytes

    def put(
        self,
        key: str,
        stream: BinaryIO,
        content_type: str,
    ) -> StoredObject:
        """Write to a private temporary file, then publish without overwriting."""

        validated_content_type = validate_content_type(content_type)
        target = self._path_for(key)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            raise StorageWriteError from None
        target = self._path_for(key)

        if target.exists():
            raise StorageObjectAlreadyExistsError

        temporary = target.parent / f".{target.name}.{uuid4().hex}.tmp"
        digest = hashlib.sha256()
        size_bytes = 0
        temporary_created = False

        try:
            with temporary.open("xb") as output:
                temporary_created = True
                while True:
                    chunk = stream.read(self._chunk_size_bytes)
                    if chunk == b"":
                        break
                    if not isinstance(chunk, (bytes, bytearray, memoryview)):
                        raise TypeError("binary stream required")
                    binary_chunk = bytes(chunk)
                    output.write(binary_chunk)
                    digest.update(binary_chunk)
                    size_bytes += len(binary_chunk)
                output.flush()
                os.fsync(output.fileno())

            target = self._path_for(key)
            try:
                os.link(temporary, target, follow_symlinks=False)
            except FileExistsError:
                raise StorageObjectAlreadyExistsError from None
        except StorageObjectAlreadyExistsError:
            raise
        except Exception:  # noqa: BLE001 - streams may raise arbitrary private errors.
            raise StorageWriteError from None
        finally:
            if temporary_created:
                self._best_effort_unlink(temporary)

        return StoredObject(
            key=key,
            size_bytes=size_bytes,
            sha256=digest.hexdigest(),
            content_type=validated_content_type,
        )

    def open(self, key: str) -> BinaryIO:
        """Open one regular object file for binary reading."""

        target = self._path_for(key)
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(target, flags)
        except FileNotFoundError:
            raise StorageObjectNotFoundError from None
        except OSError:
            raise StorageReadError from None

        try:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise StorageReadError
            return os.fdopen(descriptor, "rb")
        except StorageError:
            os.close(descriptor)
            raise
        except OSError:
            os.close(descriptor)
            raise StorageReadError from None

    def exists(self, key: str) -> bool:
        """Return whether a regular object exists; reject unsafe filesystem nodes."""

        target = self._path_for(key)
        try:
            mode = target.lstat().st_mode
        except FileNotFoundError:
            return False
        except OSError:
            raise StorageReadError from None
        if not stat.S_ISREG(mode):
            raise StorageReadError
        return True

    def delete(self, key: str) -> None:
        """Idempotently remove one regular object without pruning shared directories."""

        target = self._path_for(key)
        try:
            mode = target.lstat().st_mode
        except FileNotFoundError:
            return
        except OSError:
            raise StorageDeleteError from None
        if not stat.S_ISREG(mode):
            raise StorageDeleteError
        try:
            target.unlink()
        except FileNotFoundError:
            return
        except OSError:
            raise StorageDeleteError from None

    def _path_for(self, key: str) -> Path:
        validated_key = validate_storage_key(key)
        parts = PurePosixPath(validated_key).parts
        candidate = self._root.joinpath(*parts)
        try:
            resolved_candidate = candidate.resolve(strict=False)
            if not resolved_candidate.is_relative_to(self._root):
                raise InvalidStorageKeyError
            self._reject_object_symlinks(candidate)
        except StorageError:
            raise
        except (OSError, RuntimeError):
            raise InvalidStorageKeyError from None
        return candidate

    def _reject_object_symlinks(self, candidate: Path) -> None:
        current = self._root
        relative_parts = candidate.relative_to(self._root).parts
        for part in relative_parts:
            current = current / part
            if current.is_symlink():
                raise InvalidStorageKeyError

    @staticmethod
    def _reject_config_symlinks(path: Path) -> None:
        current = Path(path.anchor)
        for part in path.parts[1:]:
            current = current / part
            if current.is_symlink():
                raise StorageConfigurationError

    @staticmethod
    def _best_effort_unlink(path: Path) -> None:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass

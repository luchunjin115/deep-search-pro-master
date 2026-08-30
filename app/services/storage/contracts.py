"""Safe value objects and failures shared by Storage backends."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from uuid import UUID

_CATEGORY_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")
_YEAR_PATTERN = re.compile(r"^[0-9]{4}$")
_MONTH_PATTERN = re.compile(r"^(0[1-9]|1[0-2])$")
_EXTENSION_PATTERN = re.compile(r"^[a-z0-9]{1,16}$")
_MAX_KEY_LENGTH = 512
_MAX_CONTENT_TYPE_LENGTH = 255


@dataclass(frozen=True, slots=True)
class StoredObject:
    """Metadata returned after bytes are atomically published by a backend."""

    key: str
    size_bytes: int
    sha256: str
    content_type: str


class StorageError(Exception):
    """Base class whose message is safe to log or map at a later API boundary."""


class StorageConfigurationError(StorageError):
    """The configured root or stream chunk size cannot be used safely."""

    def __init__(self) -> None:
        super().__init__("Storage配置无效")


class InvalidStorageKeyError(StorageError):
    """An object key is malformed or can escape the managed namespace."""

    def __init__(self) -> None:
        super().__init__("Storage对象Key无效")


class InvalidStorageMetadataError(StorageError):
    """Non-path object metadata is malformed."""

    def __init__(self) -> None:
        super().__init__("Storage对象元数据无效")


class StorageObjectAlreadyExistsError(StorageError):
    """The immutable object key is already occupied and cannot be overwritten."""

    def __init__(self) -> None:
        super().__init__("Storage对象已存在")


class StorageObjectNotFoundError(StorageError):
    """No regular file exists at the requested object key."""

    def __init__(self) -> None:
        super().__init__("Storage对象不存在")


class StorageWriteError(StorageError):
    """Bytes could not be written and atomically published."""

    def __init__(self) -> None:
        super().__init__("Storage对象写入失败")


class StorageReadError(StorageError):
    """A stored object could not be opened or inspected safely."""

    def __init__(self) -> None:
        super().__init__("Storage对象读取失败")


class StorageDeleteError(StorageError):
    """A stored object could not be physically removed."""

    def __init__(self) -> None:
        super().__init__("Storage对象删除失败")


def validate_storage_key(key: str) -> str:
    """Return one canonical object key or reject it without echoing its value."""

    if (
        not isinstance(key, str)
        or not key
        or len(key) > _MAX_KEY_LENGTH
        or key != key.strip()
        or "\\" in key
        or "//" in key
        or any(ord(character) < 32 for character in key)
    ):
        raise InvalidStorageKeyError

    path = PurePosixPath(key)
    parts = path.parts
    if (
        path.is_absolute()
        or len(parts) != 5
        or any(part in {"", ".", ".."} for part in parts)
    ):
        raise InvalidStorageKeyError

    tenant_text, category, year, month, filename = parts
    try:
        tenant_id = UUID(tenant_text)
    except (ValueError, AttributeError):
        raise InvalidStorageKeyError from None
    if str(tenant_id) != tenant_text:
        raise InvalidStorageKeyError

    if not _CATEGORY_PATTERN.fullmatch(category):
        raise InvalidStorageKeyError
    if not _YEAR_PATTERN.fullmatch(year) or int(year) < 1970:
        raise InvalidStorageKeyError
    if not _MONTH_PATTERN.fullmatch(month) or filename.count(".") != 1:
        raise InvalidStorageKeyError

    object_text, extension = filename.split(".", maxsplit=1)
    try:
        object_id = UUID(object_text)
    except (ValueError, AttributeError):
        raise InvalidStorageKeyError from None
    if str(object_id) != object_text or not _EXTENSION_PATTERN.fullmatch(extension):
        raise InvalidStorageKeyError

    return key


def validate_content_type(content_type: str) -> str:
    """Keep backend metadata bounded and free from control-character injection."""

    if (
        not isinstance(content_type, str)
        or not content_type
        or content_type != content_type.strip()
        or len(content_type) > _MAX_CONTENT_TYPE_LENGTH
        or any(ord(character) < 32 for character in content_type)
    ):
        raise InvalidStorageMetadataError
    return content_type

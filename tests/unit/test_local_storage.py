from __future__ import annotations

import hashlib
from io import BytesIO
from pathlib import Path
from typing import BinaryIO, cast
from uuid import UUID

import pytest

from app.services.storage import (
    InvalidStorageKeyError,
    InvalidStorageMetadataError,
    LocalStorageBackend,
    StorageBackend,
    StorageConfigurationError,
    StorageDeleteError,
    StorageObjectAlreadyExistsError,
    StorageObjectNotFoundError,
    StorageReadError,
    StorageWriteError,
    validate_storage_key,
)

TENANT_ID = UUID("10000000-0000-0000-0000-000000000001")
OBJECT_ID = UUID("20000000-0000-0000-0000-000000000001")
UPPERCASE_TENANT_ID = "AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA"


def object_key(
    *,
    tenant_id: UUID = TENANT_ID,
    object_id: UUID = OBJECT_ID,
    category: str = "uploads",
    extension: str = "pdf",
) -> str:
    return f"{tenant_id}/{category}/2026/08/{object_id}.{extension}"


class BrokenBinaryStream(BytesIO):
    def __init__(self, initial_bytes: bytes, private_detail: str) -> None:
        super().__init__(initial_bytes)
        self._private_detail = private_detail
        self._read_count = 0

    def read(self, size: int | None = -1) -> bytes:
        self._read_count += 1
        if self._read_count > 1:
            raise OSError(self._private_detail)
        return super().read(size)


class TextReturningStream:
    def read(self, size: int = -1) -> str:
        del size
        return "not-binary"


@pytest.fixture
def storage_root(tmp_path: Path) -> Path:
    return tmp_path / "managed-storage"


@pytest.fixture
def storage(storage_root: Path) -> LocalStorageBackend:
    return LocalStorageBackend(storage_root, chunk_size_bytes=3)


def test_local_storage_satisfies_backend_protocol_and_creates_root(
    storage: LocalStorageBackend,
    storage_root: Path,
) -> None:
    assert isinstance(storage, StorageBackend)
    assert storage_root.is_dir()


def test_put_open_exists_and_metadata_use_only_canonical_object_key(
    storage: LocalStorageBackend,
    storage_root: Path,
) -> None:
    key = object_key()
    payload = b"synthetic-pdf-bytes"

    stored = storage.put(key, BytesIO(payload), "application/pdf")

    assert stored.key == key
    assert stored.size_bytes == len(payload)
    assert stored.sha256 == hashlib.sha256(payload).hexdigest()
    assert stored.content_type == "application/pdf"
    assert storage.exists(key) is True
    with storage.open(key) as opened:
        assert opened.read() == payload
    assert storage_root.joinpath(*key.split("/")).read_bytes() == payload
    assert str(storage_root.resolve()) not in repr(stored)


def test_put_supports_empty_immutable_object(storage: LocalStorageBackend) -> None:
    key = object_key(extension="csv")

    stored = storage.put(key, BytesIO(b""), "text/csv")

    assert stored.size_bytes == 0
    assert stored.sha256 == hashlib.sha256(b"").hexdigest()
    with storage.open(key) as opened:
        assert opened.read() == b""


def test_duplicate_key_never_overwrites_original_object(
    storage: LocalStorageBackend,
    storage_root: Path,
) -> None:
    key = object_key()
    storage.put(key, BytesIO(b"first"), "application/pdf")

    with pytest.raises(StorageObjectAlreadyExistsError) as captured:
        storage.put(key, BytesIO(b"second"), "application/pdf")

    with storage.open(key) as opened:
        assert opened.read() == b"first"
    assert list(storage_root.rglob("*.tmp")) == []
    assert key not in str(captured.value)
    assert str(storage_root) not in str(captured.value)
    assert captured.value.__cause__ is None


def test_delete_is_idempotent_and_missing_open_has_safe_error(
    storage: LocalStorageBackend,
) -> None:
    key = object_key()
    storage.put(key, BytesIO(b"content"), "application/pdf")

    storage.delete(key)
    storage.delete(key)

    assert storage.exists(key) is False
    with pytest.raises(StorageObjectNotFoundError) as captured:
        storage.open(key)
    assert str(captured.value) == "Storage对象不存在"
    assert captured.value.__cause__ is None


@pytest.mark.parametrize(
    "key",
    [
        "",
        "../outside.pdf",
        "/absolute/path.pdf",
        "C:/absolute/path.pdf",
        "//server/share/path.pdf",
        "tenant\\uploads\\2026\\08\\file.pdf",
        f"{TENANT_ID}/../2026/08/{OBJECT_ID}.pdf",
        f"{UPPERCASE_TENANT_ID}/uploads/2026/08/{OBJECT_ID}.pdf",
        f"{TENANT_ID}/Uploads/2026/08/{OBJECT_ID}.pdf",
        f"{TENANT_ID}/uploads/1969/08/{OBJECT_ID}.pdf",
        f"{TENANT_ID}/uploads/2026/13/{OBJECT_ID}.pdf",
        f"{TENANT_ID}/uploads/2026/08/not-a-uuid.pdf",
        f"{TENANT_ID}/uploads/2026/08/{OBJECT_ID}.PDF",
        f"{TENANT_ID}/uploads/2026/08/{OBJECT_ID}.tar.gz",
    ],
)
def test_invalid_and_unsafe_keys_are_rejected_without_filesystem_access(
    storage: LocalStorageBackend,
    storage_root: Path,
    key: str,
) -> None:
    with pytest.raises(InvalidStorageKeyError) as captured:
        storage.put(key, BytesIO(b"unsafe"), "application/pdf")

    assert str(captured.value) == "Storage对象Key无效"
    if key:
        assert key not in str(captured.value)
    assert list(storage_root.rglob("*.tmp")) == []


@pytest.mark.parametrize("content_type", ["", " application/pdf", "text/plain\n"])
def test_invalid_content_type_is_rejected_before_writing(
    storage: LocalStorageBackend,
    storage_root: Path,
    content_type: str,
) -> None:
    with pytest.raises(InvalidStorageMetadataError):
        storage.put(object_key(), BytesIO(b"content"), content_type)

    assert list(storage_root.rglob("*")) == []


def test_stream_failure_removes_partial_and_temporary_files_and_redacts_error(
    storage: LocalStorageBackend,
    storage_root: Path,
) -> None:
    key = object_key()
    private_detail = "private-stream-detail"

    with pytest.raises(StorageWriteError) as captured:
        storage.put(
            key,
            BrokenBinaryStream(b"partial-content", private_detail),
            "application/pdf",
        )

    assert storage.exists(key) is False
    assert list(storage_root.rglob("*.tmp")) == []
    assert private_detail not in str(captured.value)
    assert key not in str(captured.value)
    assert str(storage_root) not in str(captured.value)
    assert captured.value.__cause__ is None


def test_non_binary_stream_is_mapped_to_safe_write_error(
    storage: LocalStorageBackend,
) -> None:
    key = object_key()

    with pytest.raises(StorageWriteError) as captured:
        storage.put(
            key,
            cast(BinaryIO, TextReturningStream()),
            "application/pdf",
        )

    assert captured.value.__cause__ is None


def test_directory_at_object_key_is_never_treated_as_stored_file(
    storage: LocalStorageBackend,
    storage_root: Path,
) -> None:
    key = object_key()
    storage_root.joinpath(*key.split("/")).mkdir(parents=True)

    with pytest.raises(StorageReadError):
        storage.exists(key)
    with pytest.raises(StorageReadError):
        storage.open(key)
    with pytest.raises(StorageDeleteError):
        storage.delete(key)


def test_symlinked_key_parent_cannot_escape_storage_root(
    storage: LocalStorageBackend,
    storage_root: Path,
    tmp_path: Path,
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    tenant_link = storage_root / str(TENANT_ID)
    try:
        tenant_link.symlink_to(outside, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"Current platform cannot create a test symlink: {error.errno}")

    key = object_key()
    operations = (
        lambda: storage.put(key, BytesIO(b"escape"), "application/pdf"),
        lambda: storage.open(key),
        lambda: storage.exists(key),
        lambda: storage.delete(key),
    )
    for operation in operations:
        with pytest.raises(InvalidStorageKeyError):
            operation()

    assert list(outside.rglob("*")) == []


def test_reported_symlink_key_component_is_rejected_on_every_platform(
    storage: LocalStorageBackend,
    storage_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    symlink_component = storage_root / str(TENANT_ID)
    original_is_symlink = Path.is_symlink

    def report_tenant_as_symlink(path: Path) -> bool:
        return path == symlink_component or original_is_symlink(path)

    monkeypatch.setattr(Path, "is_symlink", report_tenant_as_symlink)

    with pytest.raises(InvalidStorageKeyError):
        storage.put(object_key(), BytesIO(b"blocked"), "application/pdf")


def test_symlink_root_and_file_root_are_rejected(tmp_path: Path) -> None:
    actual_root = tmp_path / "actual"
    actual_root.mkdir()
    linked_root = tmp_path / "linked"
    try:
        linked_root.symlink_to(actual_root, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"Current platform cannot create a test symlink: {error.errno}")

    with pytest.raises(StorageConfigurationError):
        LocalStorageBackend(linked_root)

    file_root = tmp_path / "file-root"
    file_root.write_bytes(b"not-a-directory")
    with pytest.raises(StorageConfigurationError):
        LocalStorageBackend(file_root)


def test_reported_symlink_root_is_rejected_on_every_platform(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "reported-symlink"
    original_is_symlink = Path.is_symlink

    def report_root_as_symlink(path: Path) -> bool:
        return path == root or original_is_symlink(path)

    monkeypatch.setattr(Path, "is_symlink", report_root_as_symlink)

    with pytest.raises(StorageConfigurationError):
        LocalStorageBackend(root)


@pytest.mark.parametrize("chunk_size", [0, -1])
def test_invalid_chunk_size_is_rejected_without_creating_root(
    tmp_path: Path,
    chunk_size: int,
) -> None:
    root = tmp_path / "not-created"

    with pytest.raises(StorageConfigurationError):
        LocalStorageBackend(root, chunk_size_bytes=chunk_size)

    assert not root.exists()


def test_key_validator_accepts_uuid_partitioned_contract() -> None:
    key = object_key(category="parsed", extension="json")

    assert validate_storage_key(key) == key

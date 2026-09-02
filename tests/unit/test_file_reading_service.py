from __future__ import annotations

import hashlib
import io
from dataclasses import replace
from typing import BinaryIO
from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.core.errors import (
    FileNotFoundError,
    FileReadError,
    FileReadLocatorError,
    FileStateConflictError,
)
from app.repositories.files import ReadableParsedFile
from app.schemas.auth import CurrentUser
from app.schemas.files import ReadUploadedFileInput
from app.services.documents.artifacts import (
    ArtifactPageProperties,
    ArtifactTextBlock,
    build_canonical_artifact,
)
from app.services.documents.parsers import CsvParser, DocxParser, PdfParser, XlsxParser
from app.services.documents.parsers.base import SourceLocator
from app.services.documents.parsers.native import adapt_native_parse_result
from app.services.documents.quality import decide_parse_route
from app.services.documents.routing import RoutedParseResult
from app.services.file_reading import FileReadingService
from app.services.storage import StorageReadError
from tests.fixtures.docx_factory import make_structured_docx
from tests.fixtures.pdf_factory import make_text_pdf
from tests.fixtures.spreadsheet_factory import (
    make_structured_xlsx,
    make_utf8_sig_semicolon_csv,
)

_TENANT_ID = UUID("00000000-0000-4000-8000-000000000201")
_USER_ID = UUID("00000000-0000-4000-8000-000000000202")
_FILE_ID = UUID("00000000-0000-4000-8000-000000000203")
_DOCUMENT_ID = UUID("00000000-0000-4000-8000-000000000204")
_VERSION_ID = UUID("00000000-0000-4000-8000-000000000205")


def _user() -> CurrentUser:
    return CurrentUser(
        user_id=_USER_ID,
        tenant_id=_TENANT_ID,
        email="file-reader@example.com",
        display_name="File Reader",
        roles=["amazon_operator"],
        market_scopes=["DE"],
        synthetic_data=True,
    )


def _artifact_payload(source_type: str) -> tuple[bytes, str]:
    source_factories = {
        "pdf": make_text_pdf,
        "docx": make_structured_docx,
        "xlsx": make_structured_xlsx,
        "csv": make_utf8_sig_semicolon_csv,
    }
    parsers = {
        "pdf": PdfParser(),
        "docx": DocxParser(),
        "xlsx": XlsxParser(),
        "csv": CsvParser(),
    }
    source = source_factories[source_type]()
    source_sha256 = hashlib.sha256(source).hexdigest()
    parsed = parsers[source_type].parse(io.BytesIO(source))
    artifact = adapt_native_parse_result(parsed, source_sha256=source_sha256)
    quality = decide_parse_route(artifact)
    if quality.route != "native":
        quality = quality.model_copy(
            update={"route": "native", "reasons": ["native_quality_sufficient"]}
        )
    routed = RoutedParseResult(
        route=quality.route,
        reasons=quality.reasons,
        quality=quality,
        selected_artifact=artifact,
        native_artifact=artifact,
    )
    return routed.model_dump_json().encode("utf-8"), source_sha256


def _long_pdf_payload() -> tuple[bytes, str]:
    source_sha256 = "a" * 64
    text = "合" * 9_000
    artifact = build_canonical_artifact(
        source_type="pdf",
        source_sha256=source_sha256,
        parser_name="synthetic-test",
        parser_version="1.0.0",
        blocks=[
            ArtifactTextBlock(
                block_id="b000001",
                text=text,
                locator=SourceLocator(page_number=1),
                page=ArtifactPageProperties(
                    page_number=1,
                    character_count=len(text),
                    image_count=0,
                    low_text=False,
                ),
            )
        ],
        warnings=[],
        source_character_count=len(text),
        page_count=1,
    )
    quality = decide_parse_route(artifact)
    routed = RoutedParseResult(
        route=quality.route,
        reasons=quality.reasons,
        quality=quality,
        selected_artifact=artifact,
        native_artifact=artifact,
    )
    return routed.model_dump_json().encode("utf-8"), source_sha256


class FakeReadableFileRepository:
    def __init__(self, row: ReadableParsedFile | None) -> None:
        self.row = row
        self.calls: list[dict[str, object]] = []

    def find_readable_parsed_file(self, **kwargs: object) -> ReadableParsedFile | None:
        self.calls.append(kwargs)
        return self.row


class FakeStorage:
    def __init__(self, payload: bytes | Exception) -> None:
        self.payload = payload
        self.opened_keys: list[str] = []

    def open(self, key: str) -> BinaryIO:
        self.opened_keys.append(key)
        if isinstance(self.payload, Exception):
            raise self.payload
        return io.BytesIO(self.payload)


def _row(source_type: str, source_sha256: str) -> ReadableParsedFile:
    extension = f".{source_type}"
    return ReadableParsedFile(
        file_id=_FILE_ID,
        document_id=_DOCUMENT_ID,
        version_id=_VERSION_ID,
        version_no=2,
        original_name=f"synthetic-file{extension}",
        extension=extension,
        sha256=source_sha256,
        content_hash=source_sha256,
        parse_status="ready",
        parsed_storage_key=(f"{_TENANT_ID}/parsed/2026/09/{_VERSION_ID}.json"),
        is_active_version=False,
    )


def _service(
    source_type: str,
    *,
    row_update: dict[str, object] | None = None,
    payload: bytes | Exception | None = None,
    maximum_artifact_bytes: int = 10_000_000,
) -> tuple[FileReadingService, FakeReadableFileRepository, FakeStorage]:
    valid_payload, source_sha256 = _artifact_payload(source_type)
    row = _row(source_type, source_sha256)
    if row_update:
        row = replace(row, **row_update)
    repository = FakeReadableFileRepository(row)
    storage = FakeStorage(valid_payload if payload is None else payload)
    return (
        FileReadingService(
            repository,
            storage,
            maximum_artifact_bytes=maximum_artifact_bytes,
        ),
        repository,
        storage,
    )


def test_pdf_read_uses_trusted_identity_and_returns_only_selected_pages() -> None:
    service, repository, storage = _service("pdf")

    result = service.read_uploaded_file(
        _user(),
        ReadUploadedFileInput(
            file_id=_FILE_ID,
            locator={"source_type": "pdf", "page_start": 1, "page_end": 2},
        ),
    )

    assert [section.locator.page_number for section in result.sections] == [1, 2]
    assert result.file_id == _FILE_ID
    assert result.version_no == 2
    assert result.is_active_version is False
    assert result.total_characters == sum(
        len(section.content) for section in result.sections
    )
    assert repository.calls == [
        {
            "tenant_id": _TENANT_ID,
            "user_id": _USER_ID,
            "role_names": ("amazon_operator",),
            "market_scopes": ("DE",),
            "file_id": _FILE_ID,
        }
    ]
    assert storage.opened_keys == [f"{_TENANT_ID}/parsed/2026/09/{_VERSION_ID}.json"]
    serialized = result.model_dump_json()
    assert "parsed_storage_key" not in serialized
    assert str(_TENANT_ID) not in serialized


@pytest.mark.parametrize(
    ("source_type", "locator", "expected_text"),
    [
        (
            "docx",
            {"source_type": "docx", "paragraph_number": 2},
            "Model SYNTH-LAMP-01",
        ),
        (
            "docx",
            {"source_type": "docx", "table_number": 1},
            "|",
        ),
        (
            "xlsx",
            {
                "source_type": "xlsx",
                "sheet_name": "合成报价",
                "cell_range": "B2:D3",
            },
            "SYNTH-001",
        ),
        (
            "csv",
            {"source_type": "csv", "row_start": 2, "row_end": 3},
            "合成供应商A",
        ),
    ],
)
def test_structural_locators_return_deterministic_bounded_sections(
    source_type: str,
    locator: dict[str, object],
    expected_text: str,
) -> None:
    service, _repository, _storage = _service(source_type)

    result = service.read_uploaded_file(
        _user(),
        ReadUploadedFileInput(file_id=_FILE_ID, locator=locator),
    )

    assert len(result.sections) == 1
    assert result.sections[0].locator.source_type == source_type
    assert expected_text in result.sections[0].content
    assert result.total_characters <= 8_000


def test_omitted_locator_returns_server_bounded_preview() -> None:
    service, _repository, _storage = _service("docx")

    result = service.read_uploaded_file(
        _user(), ReadUploadedFileInput(file_id=_FILE_ID)
    )

    assert 1 <= len(result.sections) <= 12
    assert result.total_characters <= 8_000
    assert result.original_name == "synthetic-file.docx"


def test_service_truncates_long_valid_artifact_to_exact_public_limit() -> None:
    payload, source_sha256 = _long_pdf_payload()
    service, _repository, _storage = _service(
        "pdf",
        payload=payload,
        row_update={"sha256": source_sha256, "content_hash": source_sha256},
    )

    result = service.read_uploaded_file(
        _user(), ReadUploadedFileInput(file_id=_FILE_ID)
    )

    assert result.total_characters == 8_000
    assert result.truncated is True
    assert result.sections[0].truncated is True


def test_source_type_mismatch_and_missing_coordinate_are_safe_locator_errors() -> None:
    service, _repository, storage = _service("pdf")

    with pytest.raises(FileReadLocatorError) as mismatch:
        service.read_uploaded_file(
            _user(),
            ReadUploadedFileInput(
                file_id=_FILE_ID,
                locator={
                    "source_type": "csv",
                    "row_start": 1,
                    "row_end": 2,
                },
            ),
        )
    assert mismatch.value.field == "locator"
    assert storage.opened_keys == []

    service, _repository, _storage = _service("pdf")
    with pytest.raises(FileReadLocatorError):
        service.read_uploaded_file(
            _user(),
            ReadUploadedFileInput(
                file_id=_FILE_ID,
                locator={"source_type": "pdf", "page_start": 99},
            ),
        )


def test_absent_or_unauthorized_file_is_hidden_before_storage_read() -> None:
    repository = FakeReadableFileRepository(None)
    storage = FakeStorage(b"private")
    service = FileReadingService(
        repository,
        storage,
        maximum_artifact_bytes=10_000,
    )

    with pytest.raises(FileNotFoundError):
        service.read_uploaded_file(_user(), ReadUploadedFileInput(file_id=uuid4()))
    assert storage.opened_keys == []


def test_repository_database_failure_maps_to_one_safe_read_error() -> None:
    class FailingRepository(FakeReadableFileRepository):
        def find_readable_parsed_file(
            self, **kwargs: object
        ) -> ReadableParsedFile | None:
            raise SQLAlchemyError("D:/private/database detail")

    storage = FakeStorage(b"private")
    service = FileReadingService(
        FailingRepository(None),
        storage,
        maximum_artifact_bytes=10_000,
    )

    with pytest.raises(FileReadError) as error:
        service.read_uploaded_file(_user(), ReadUploadedFileInput(file_id=_FILE_ID))
    assert "private" not in str(error.value).lower()
    assert storage.opened_keys == []


def test_non_ready_version_is_a_state_conflict_without_opening_storage() -> None:
    service, _repository, storage = _service(
        "pdf",
        row_update={"parse_status": "pending", "parsed_storage_key": None},
    )

    with pytest.raises(FileStateConflictError):
        service.read_uploaded_file(_user(), ReadUploadedFileInput(file_id=_FILE_ID))
    assert storage.opened_keys == []


@pytest.mark.parametrize(
    ("payload", "maximum_artifact_bytes"),
    [
        (b"not-json", 10_000),
        (b"123456", 5),
        (StorageReadError(), 10_000),
    ],
)
def test_storage_malformed_and_oversized_artifacts_are_one_safe_error(
    payload: bytes | Exception,
    maximum_artifact_bytes: int,
) -> None:
    service, _repository, _storage = _service(
        "pdf",
        payload=payload,
        maximum_artifact_bytes=maximum_artifact_bytes,
    )

    with pytest.raises(FileReadError) as error:
        service.read_uploaded_file(_user(), ReadUploadedFileInput(file_id=_FILE_ID))
    assert error.value.code == "INTERNAL_ERROR"
    assert "json" not in str(error.value).lower()
    assert "storage" not in str(error.value).lower()


def test_tampered_source_hash_is_rejected_without_leaking_private_metadata() -> None:
    service, _repository, _storage = _service(
        "pdf",
        row_update={"sha256": "f" * 64},
    )

    with pytest.raises(FileReadError) as error:
        service.read_uploaded_file(_user(), ReadUploadedFileInput(file_id=_FILE_ID))
    assert str(_TENANT_ID) not in str(error.value)
    assert str(_VERSION_ID) not in str(error.value)


def test_private_artifact_key_must_match_tenant_category_and_version() -> None:
    service, _repository, storage = _service(
        "pdf",
        row_update={
            "parsed_storage_key": (f"{_TENANT_ID}/uploads/2026/09/{_VERSION_ID}.json")
        },
    )

    with pytest.raises(FileReadError):
        service.read_uploaded_file(_user(), ReadUploadedFileInput(file_id=_FILE_ID))
    assert storage.opened_keys == []

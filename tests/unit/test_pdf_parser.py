from __future__ import annotations

import io
from pathlib import Path
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.services.documents.parsers import (
    DocumentEncryptedError,
    DocumentLimitError,
    DocumentParseError,
    PdfParser,
)
from app.services.storage import LocalStorageBackend
from tests.fixtures.pdf_factory import (
    make_encrypted_pdf,
    make_low_text_pdf,
    make_scanned_image_pdf,
    make_text_pdf,
)


def test_text_pdf_preserves_pages_text_headings_and_empty_page_warning() -> None:
    parser = PdfParser()
    result = parser.parse(io.BytesIO(make_text_pdf()))

    assert result.parser_name == "pymupdf"
    assert result.parser_version.startswith("m2-pdf-v1+pymupdf-")
    assert result.page_count == 3
    assert [page.page_number for page in result.pages] == [1, 2, 3]
    assert "Synthetic Product Manual" in result.pages[0].text
    assert "Safety Requirements" in result.pages[1].text
    assert result.pages[2].text == ""
    assert result.pages[2].low_text is True
    assert [hint.text for hint in result.pages[0].heading_hints] == [
        "Synthetic Product Manual"
    ]
    assert [hint.text for hint in result.pages[1].heading_hints] == [
        "Safety Requirements"
    ]
    assert result.pages[0].heading_hints[0].level == 1
    assert result.pages[1].heading_hints[0].level == 2
    assert [warning.code for warning in result.warnings] == ["empty_page"]
    assert result.warnings[0].locator.page_number == 3


def test_image_only_page_is_flagged_as_scanned_without_ocr_text() -> None:
    result = PdfParser().parse(io.BytesIO(make_scanned_image_pdf()))

    assert result.page_count == 1
    assert result.pages[0].text == ""
    assert result.pages[0].image_count >= 1
    assert [warning.code for warning in result.warnings] == [
        "empty_page",
        "scanned_page_suspected",
    ]
    assert all(warning.locator.page_number == 1 for warning in result.warnings)
    assert "SCANNED SYNTHETIC PAGE" not in result.pages[0].text


def test_low_text_page_warns_without_claiming_it_is_scanned() -> None:
    result = PdfParser(low_text_character_threshold=20).parse(
        io.BytesIO(make_low_text_pdf())
    )

    assert result.pages[0].text == "OK"
    assert result.pages[0].character_count == 2
    assert result.pages[0].low_text is True
    assert [warning.code for warning in result.warnings] == ["low_text_page"]


def test_corrupt_and_encrypted_pdfs_raise_distinct_safe_errors() -> None:
    private_marker = b"D:/private/secret.pdf API_KEY=do-not-leak"
    with pytest.raises(DocumentParseError) as corrupt_error:
        PdfParser().parse(io.BytesIO(b"%PDF-1.7\n" + private_marker))
    assert str(corrupt_error.value) == "文档解析失败"
    assert "secret" not in str(corrupt_error.value).lower()
    assert "API_KEY" not in str(corrupt_error.value)

    with pytest.raises(DocumentEncryptedError) as encrypted_error:
        PdfParser().parse(io.BytesIO(make_encrypted_pdf()))
    assert str(encrypted_error.value) == "文档已加密，无法解析"
    assert "synthetic-user-only" not in str(encrypted_error.value)


@pytest.mark.parametrize(
    "parser",
    [
        PdfParser(max_source_bytes=64),
        PdfParser(max_pages=1),
        PdfParser(max_extracted_characters=20),
    ],
)
def test_source_page_and_text_limits_fail_before_returning_partial_results(
    parser: PdfParser,
) -> None:
    with pytest.raises(DocumentLimitError, match="文档超过解析安全限制"):
        parser.parse(io.BytesIO(make_text_pdf()))


def test_stream_failures_and_invalid_parser_limits_are_safe() -> None:
    class BrokenStream(io.BytesIO):
        def read(self, *_args: object, **_kwargs: object) -> bytes:
            raise OSError("D:/private/source.pdf")

    with pytest.raises(DocumentParseError) as stream_error:
        PdfParser().parse(BrokenStream())
    assert str(stream_error.value) == "文档解析失败"
    assert "private" not in str(stream_error.value).lower()

    with pytest.raises(ValueError, match="positive and bounded"):
        PdfParser(max_pages=0)
    with pytest.raises(ValueError, match="positive and bounded"):
        PdfParser(max_pages=2001)


def test_validated_settings_control_parser_limits() -> None:
    settings = Settings(  # type: ignore[call-arg]
        _env_file=None,
        pdf_max_pages=1,
    )
    parser = PdfParser.from_settings(settings)

    with pytest.raises(DocumentLimitError):
        parser.parse(io.BytesIO(make_text_pdf()))


def test_parser_output_is_deterministic_strict_and_has_no_internal_location() -> None:
    source = make_text_pdf(include_empty_page=False)
    parser = PdfParser()
    first = parser.parse(io.BytesIO(source)).model_dump()
    second = parser.parse(io.BytesIO(source)).model_dump()

    assert first == second
    rendered = str(first).lower()
    assert "storage_key" not in rendered
    assert "filesystem_path" not in rendered
    assert "local_path" not in rendered
    assert "tenant_id" not in rendered
    assert "sql" not in rendered


def test_parser_consumes_a_managed_storage_stream_without_receiving_a_path(
    tmp_path: Path,
) -> None:
    storage = LocalStorageBackend(tmp_path / "storage")
    tenant_id = uuid4()
    file_id = uuid4()
    key = f"{tenant_id}/uploads/2026/08/{file_id}.pdf"
    stored = storage.put(key, io.BytesIO(make_text_pdf()), "application/pdf")

    with storage.open(stored.key) as stream:
        result = PdfParser().parse(stream)

    assert result.page_count == 3
    assert "Synthetic Product Manual" in result.pages[0].text

from __future__ import annotations

import io
from pathlib import Path
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.services.documents.parsers import (
    DocumentLimitError,
    DocumentParseError,
    XlsxParser,
)
from app.services.storage import LocalStorageBackend
from tests.fixtures.spreadsheet_factory import (
    make_large_dimension_xlsx,
    make_structured_xlsx,
    make_xlsx_with_archive_payload,
    make_xlsx_with_unsafe_member,
)


def test_xlsx_preserves_sheet_order_headers_empty_rows_and_cell_ranges() -> None:
    result = XlsxParser().parse(io.BytesIO(make_structured_xlsx()))

    assert result.parser_name == "openpyxl"
    assert result.parser_version.startswith("m2-xlsx-v1+openpyxl-")
    assert result.sheet_count == 3
    assert [sheet.sheet_name for sheet in result.sheets] == [
        "合成报价",
        "质检记录",
        "空Sheet",
    ]
    quotes = result.sheets[0]
    assert quotes.headers == ["供应商", "SKU", "单价", "数量", "总价"]
    assert quotes.row_count == 4
    assert quotes.column_count == 5
    assert quotes.non_empty_row_count == 3
    assert quotes.rows[2].is_empty is True
    assert quotes.rows[1].locator.cell_range == "A2:E2"
    assert quotes.rows[1].locator.row_start == 2
    assert quotes.rows[1].cells[1].coordinate == "B2"
    assert quotes.rows[1].cells[1].value == "SYNTH-001"
    assert quotes.rows[1].cells[1].locator.sheet_name == "合成报价"

    inspection = result.sheets[1]
    assert inspection.rows[1].cells[0].value == "2026-08-29T00:00:00"
    assert inspection.rows[1].cells[0].data_type == "date"
    empty = result.sheets[2]
    assert empty.state == "hidden"
    assert empty.row_count == 0
    assert empty.column_count == 0
    assert [warning.code for warning in result.warnings] == ["empty_sheet"]
    assert result.warnings[0].locator.sheet_name == "空Sheet"


def test_xlsx_preserves_formulas_without_evaluating_or_inventing_values() -> None:
    result = XlsxParser().parse(io.BytesIO(make_structured_xlsx()))
    formula_cell = result.sheets[0].rows[1].cells[4]

    assert result.formula_count == 2
    assert result.formulas_without_cached_value == 2
    assert formula_cell.coordinate == "E2"
    assert formula_cell.data_type == "formula"
    assert formula_cell.formula == "=C2*D2"
    assert formula_cell.value is None
    assert formula_cell.cached_value is None


def test_corrupt_and_unsafe_xlsx_archives_raise_safe_errors() -> None:
    private_marker = b"D:/private/source.xlsx API_KEY=do-not-leak"
    with pytest.raises(DocumentParseError) as corrupt_error:
        XlsxParser().parse(io.BytesIO(b"PK\x03\x04" + private_marker))
    assert str(corrupt_error.value) == "文档解析失败"
    assert "private" not in str(corrupt_error.value).lower()
    assert "API_KEY" not in str(corrupt_error.value)

    with pytest.raises(DocumentParseError, match="文档解析失败"):
        XlsxParser().parse(io.BytesIO(make_xlsx_with_unsafe_member()))


@pytest.mark.parametrize(
    "parser",
    [
        XlsxParser(max_source_bytes=64),
        XlsxParser(max_archive_members=3),
        XlsxParser(max_uncompressed_bytes=1024),
        XlsxParser(max_compression_ratio=2),
        XlsxParser(max_sheets=2),
        XlsxParser(max_rows_per_sheet=3),
        XlsxParser(max_columns=4),
        XlsxParser(max_cells=9),
        XlsxParser(max_extracted_characters=20),
    ],
)
def test_xlsx_source_archive_shape_and_text_limits_are_enforced(
    parser: XlsxParser,
) -> None:
    with pytest.raises(DocumentLimitError, match="文档超过解析安全限制"):
        parser.parse(io.BytesIO(make_structured_xlsx()))


def test_xlsx_rejects_compressed_payload_and_large_declared_dimensions() -> None:
    source = make_xlsx_with_archive_payload(1024 * 1024)
    with pytest.raises(DocumentLimitError):
        XlsxParser(max_uncompressed_bytes=512 * 1024).parse(io.BytesIO(source))
    with pytest.raises(DocumentLimitError):
        XlsxParser(max_compression_ratio=10).parse(io.BytesIO(source))

    large_row = make_large_dimension_xlsx(row=101, column=1)
    with pytest.raises(DocumentLimitError):
        XlsxParser(max_rows_per_sheet=100).parse(io.BytesIO(large_row))
    large_column = make_large_dimension_xlsx(row=1, column=11)
    with pytest.raises(DocumentLimitError):
        XlsxParser(max_columns=10).parse(io.BytesIO(large_column))


def test_xlsx_stream_failures_settings_and_constructor_limits_are_safe() -> None:
    class BrokenStream(io.BytesIO):
        def read(self, *_args: object, **_kwargs: object) -> bytes:
            raise OSError("D:/private/source.xlsx")

    with pytest.raises(DocumentParseError) as stream_error:
        XlsxParser().parse(BrokenStream())
    assert str(stream_error.value) == "文档解析失败"
    assert "private" not in str(stream_error.value).lower()

    settings = Settings(_env_file=None, xlsx_max_sheets=100)  # type: ignore[call-arg]
    assert XlsxParser.from_settings(settings).parse(
        io.BytesIO(make_structured_xlsx())
    ).sheet_count == 3
    with pytest.raises(ValueError, match="positive and bounded"):
        XlsxParser(max_columns=0)
    with pytest.raises(ValueError, match="positive and bounded"):
        XlsxParser(max_columns=16_385)


def test_xlsx_output_is_deterministic_and_contains_no_internal_location() -> None:
    source = make_structured_xlsx()
    parser = XlsxParser()
    first = parser.parse(io.BytesIO(source)).model_dump()
    second = parser.parse(io.BytesIO(source)).model_dump()

    assert first == second
    rendered = str(first).lower()
    assert "storage_key" not in rendered
    assert "filesystem_path" not in rendered
    assert "local_path" not in rendered
    assert "tenant_id" not in rendered
    assert "sql" not in rendered


def test_xlsx_parser_consumes_a_managed_storage_stream(tmp_path: Path) -> None:
    storage = LocalStorageBackend(tmp_path / "storage")
    tenant_id = uuid4()
    file_id = uuid4()
    key = f"{tenant_id}/uploads/2026/08/{file_id}.xlsx"
    stored = storage.put(
        key,
        io.BytesIO(make_structured_xlsx()),
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    with storage.open(stored.key) as stream:
        result = XlsxParser().parse(stream)

    assert result.sheet_count == 3
    assert result.sheets[0].headers[0] == "供应商"

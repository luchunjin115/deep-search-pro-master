from __future__ import annotations

import io
from pathlib import Path
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.services.documents.parsers import (
    CsvParser,
    DocumentLimitError,
    DocumentParseError,
)
from app.services.storage import LocalStorageBackend
from tests.fixtures.spreadsheet_factory import (
    make_gb18030_csv,
    make_tab_csv,
    make_utf8_sig_semicolon_csv,
)


def test_utf8_sig_semicolon_csv_preserves_headers_quotes_and_empty_rows() -> None:
    result = CsvParser().parse(io.BytesIO(make_utf8_sig_semicolon_csv()))

    assert result.parser_name == "pandas"
    assert result.parser_version.startswith("m2-csv-v1+pandas-")
    assert result.encoding == "utf-8-sig"
    assert result.delimiter == ";"
    assert result.row_count == 4
    assert result.column_count == 3
    assert result.header_row_number == 1
    assert result.headers == ["供应商", "备注", "金额"]
    assert result.rows[1].values == ["合成供应商A", "字段中包含;分号", "12.5"]
    assert result.rows[2].is_empty is True
    assert result.rows[2].locator.row_start == 3
    assert result.rows[2].locator.row_end == 3
    assert result.warnings == []


def test_gb18030_and_tab_csv_encodings_and_delimiters_are_stable() -> None:
    gb_result = CsvParser().parse(io.BytesIO(make_gb18030_csv()))
    tab_result = CsvParser().parse(io.BytesIO(make_tab_csv()))

    assert gb_result.encoding == "gb18030"
    assert gb_result.delimiter == ","
    assert gb_result.rows[1].values == ["合成台灯", "德国", "125"]
    assert tab_result.encoding == "utf-8"
    assert tab_result.delimiter == "\t"
    assert tab_result.headers == ["sku", "status"]


def test_empty_csv_returns_a_structured_warning() -> None:
    result = CsvParser().parse(io.BytesIO(b""))

    assert result.row_count == 0
    assert result.column_count == 0
    assert result.header_row_number is None
    assert result.headers == []
    assert [warning.code for warning in result.warnings] == ["empty_csv"]


def test_malformed_binary_and_nul_csv_inputs_raise_safe_errors() -> None:
    with pytest.raises(DocumentParseError, match="文档解析失败"):
        CsvParser().parse(io.BytesIO(b"name,value\nA,1,extra\n"))
    with pytest.raises(DocumentParseError, match="文档解析失败"):
        CsvParser().parse(io.BytesIO(b"\x81"))
    with pytest.raises(DocumentParseError, match="文档解析失败"):
        CsvParser().parse(io.BytesIO(b"a,b\x00c"))


@pytest.mark.parametrize(
    "parser",
    [
        CsvParser(max_source_bytes=16),
        CsvParser(max_rows=2),
        CsvParser(max_columns=2),
        CsvParser(max_cells=5),
        CsvParser(max_extracted_characters=20),
    ],
)
def test_csv_source_shape_and_text_limits_are_enforced(parser: CsvParser) -> None:
    with pytest.raises(DocumentLimitError, match="文档超过解析安全限制"):
        parser.parse(io.BytesIO(make_utf8_sig_semicolon_csv()))


def test_csv_stream_failures_settings_and_constructor_limits_are_safe() -> None:
    class BrokenStream(io.BytesIO):
        def read(self, *_args: object, **_kwargs: object) -> bytes:
            raise OSError("D:/private/source.csv")

    with pytest.raises(DocumentParseError) as stream_error:
        CsvParser().parse(BrokenStream())
    assert str(stream_error.value) == "文档解析失败"
    assert "private" not in str(stream_error.value).lower()

    settings = Settings(_env_file=None, csv_max_rows=100)  # type: ignore[call-arg]
    assert CsvParser.from_settings(settings).parse(
        io.BytesIO(make_gb18030_csv())
    ).row_count == 3
    with pytest.raises(ValueError, match="positive and bounded"):
        CsvParser(max_rows=0)
    with pytest.raises(ValueError, match="positive and bounded"):
        CsvParser(max_rows=1_000_001)


def test_csv_output_is_deterministic_and_contains_no_internal_location() -> None:
    source = make_utf8_sig_semicolon_csv()
    parser = CsvParser()
    first = parser.parse(io.BytesIO(source)).model_dump()
    second = parser.parse(io.BytesIO(source)).model_dump()

    assert first == second
    rendered = str(first).lower()
    assert "storage_key" not in rendered
    assert "filesystem_path" not in rendered
    assert "local_path" not in rendered
    assert "tenant_id" not in rendered
    assert "sql" not in rendered


def test_csv_parser_consumes_a_managed_storage_stream(tmp_path: Path) -> None:
    storage = LocalStorageBackend(tmp_path / "storage")
    tenant_id = uuid4()
    file_id = uuid4()
    key = f"{tenant_id}/uploads/2026/08/{file_id}.csv"
    stored = storage.put(key, io.BytesIO(make_gb18030_csv()), "text/csv")

    with storage.open(stored.key) as stream:
        result = CsvParser().parse(stream)

    assert result.encoding == "gb18030"
    assert result.rows[1].values[2] == "125"

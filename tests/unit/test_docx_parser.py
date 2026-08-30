from __future__ import annotations

import io
from pathlib import Path
from uuid import uuid4

import pytest
from docx import Document
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, Twips
from pydantic import ValidationError

from app.core.config import Settings
from app.services.documents.parsers import (
    DocumentLimitError,
    DocumentParseError,
    DocxParagraphBlock,
    DocxParser,
    DocxTableBlock,
    SourceLocator,
)
from app.services.storage import LocalStorageBackend
from tests.fixtures.docx_factory import (
    make_docx_with_archive_payload,
    make_docx_with_unsafe_member,
    make_empty_docx,
    make_structured_docx,
)


def test_structured_docx_preserves_body_order_headings_and_paragraphs() -> None:
    result = DocxParser().parse(io.BytesIO(make_structured_docx()))

    assert result.parser_name == "python-docx"
    assert result.parser_version.startswith("m2-docx-v1+python-docx-")
    assert result.source_type == "docx"
    assert result.block_count == 9
    assert result.paragraph_count == 7
    assert result.table_count == 2
    assert [block.block_number for block in result.blocks] == list(range(1, 10))
    assert [block.kind for block in result.blocks] == [
        "paragraph",
        "paragraph",
        "table",
        "paragraph",
        "paragraph",
        "table",
        "paragraph",
        "paragraph",
        "paragraph",
    ]

    title = result.blocks[0]
    assert isinstance(title, DocxParagraphBlock)
    assert title.text == "Synthetic Product Guide"
    assert title.heading_level == 1
    assert title.heading_path == ["Synthetic Product Guide"]
    assert title.locator.paragraph_number == 1

    safety = result.blocks[3]
    assert isinstance(safety, DocxParagraphBlock)
    assert safety.heading_level == 2
    assert safety.heading_path == ["Synthetic Product Guide", "Safety"]
    blank = result.blocks[6]
    assert isinstance(blank, DocxParagraphBlock)
    assert blank.text == ""
    assert blank.paragraph_number == 5
    cleaning_body = result.blocks[8]
    assert isinstance(cleaning_body, DocxParagraphBlock)
    assert cleaning_body.heading_path == [
        "Synthetic Product Guide",
        "Safety",
        "Cleaning",
    ]
    assert result.warnings == []


def test_structured_fixture_has_explicit_page_style_and_table_geometry() -> None:
    document = Document(io.BytesIO(make_structured_docx()))
    section = document.sections[0]

    assert section.page_width == Inches(8.5)
    assert section.page_height == Inches(11)
    assert section.top_margin == Inches(1)
    assert section.right_margin == Inches(1)
    assert section.bottom_margin == Inches(1)
    assert section.left_margin == Inches(1)
    assert section.header_distance == Twips(708)
    assert section.footer_distance == Twips(708)
    assert document.styles["Normal"].font.name == "Calibri"
    assert document.styles["Normal"].font.size == Pt(11)
    assert document.styles["Normal"].paragraph_format.line_spacing == 1.25

    for table in document.tables:
        table_properties = table._tbl.tblPr
        table_width = table_properties.first_child_found_in("w:tblW")
        table_indent = table_properties.first_child_found_in("w:tblInd")
        assert table_width is not None
        assert table_width.get(qn("w:type")) == "dxa"
        assert table_width.get(qn("w:w")) == "9360"
        assert table_indent is not None
        assert table_indent.get(qn("w:w")) == "120"
        assert [
            column.get(qn("w:w")) for column in table._tbl.tblGrid.gridCol_lst
        ] == ["2700", "6660"]
        for row in table.rows:
            assert [
                cell._tc.get_or_add_tcPr().get_or_add_tcW().get(qn("w:w"))
                for cell in row.cells
            ] == ["2700", "6660"]


def test_multiple_tables_preserve_cells_and_one_based_locators() -> None:
    result = DocxParser().parse(io.BytesIO(make_structured_docx()))
    tables = [block for block in result.blocks if isinstance(block, DocxTableBlock)]

    assert result.table_cell_count == 10
    assert [table.table_number for table in tables] == [1, 2]
    assert [table.block_number for table in tables] == [3, 6]
    assert tables[0].heading_path == ["Synthetic Product Guide"]
    assert tables[1].heading_path == ["Synthetic Product Guide", "Safety"]
    first_cell = tables[0].rows[0].cells[0]
    last_cell = tables[1].rows[2].cells[1]
    assert (first_cell.text, first_cell.row_number, first_cell.column_number) == (
        "Field",
        1,
        1,
    )
    assert first_cell.locator.table_number == 1
    assert first_cell.locator.block_number == 3
    assert (last_cell.text, last_cell.row_number, last_cell.column_number) == (
        "Use synthetic checklist QS-01",
        3,
        2,
    )
    assert last_cell.locator.table_number == 2
    assert last_cell.locator.heading_path == ["Synthetic Product Guide", "Safety"]


def test_empty_document_is_valid_and_has_a_structured_warning() -> None:
    result = DocxParser().parse(io.BytesIO(make_empty_docx()))

    assert result.block_count == 0
    assert result.paragraph_count == 0
    assert result.table_count == 0
    assert result.character_count == 0
    assert [warning.code for warning in result.warnings] == ["empty_document"]
    assert result.warnings[0].locator == SourceLocator()


def test_corrupt_zip_and_unsafe_member_raise_safe_errors() -> None:
    private_marker = b"D:/private/source.docx API_KEY=do-not-leak"
    with pytest.raises(DocumentParseError) as corrupt_error:
        DocxParser().parse(io.BytesIO(b"PK\x03\x04" + private_marker))
    assert str(corrupt_error.value) == "文档解析失败"
    assert "private" not in str(corrupt_error.value).lower()
    assert "API_KEY" not in str(corrupt_error.value)

    with pytest.raises(DocumentParseError, match="文档解析失败"):
        DocxParser().parse(io.BytesIO(make_docx_with_unsafe_member()))


@pytest.mark.parametrize(
    "parser",
    [
        DocxParser(max_source_bytes=64),
        DocxParser(max_archive_members=3),
        DocxParser(max_uncompressed_bytes=1024),
        DocxParser(max_compression_ratio=2),
        DocxParser(max_blocks=2),
        DocxParser(max_table_cells=3),
        DocxParser(max_extracted_characters=20),
    ],
)
def test_source_archive_block_cell_and_text_limits_are_enforced(
    parser: DocxParser,
) -> None:
    with pytest.raises(DocumentLimitError, match="文档超过解析安全限制"):
        parser.parse(io.BytesIO(make_structured_docx()))


def test_highly_compressible_archive_payload_is_rejected_before_docx_loading() -> None:
    source = make_docx_with_archive_payload(1024 * 1024)

    with pytest.raises(DocumentLimitError, match="文档超过解析安全限制"):
        DocxParser(max_uncompressed_bytes=512 * 1024).parse(io.BytesIO(source))
    with pytest.raises(DocumentLimitError, match="文档超过解析安全限制"):
        DocxParser(max_compression_ratio=10).parse(io.BytesIO(source))


def test_stream_failures_and_invalid_parser_limits_are_safe() -> None:
    class BrokenStream(io.BytesIO):
        def read(self, *_args: object, **_kwargs: object) -> bytes:
            raise OSError("D:/private/source.docx")

    with pytest.raises(DocumentParseError) as stream_error:
        DocxParser().parse(BrokenStream())
    assert str(stream_error.value) == "文档解析失败"
    assert "private" not in str(stream_error.value).lower()

    with pytest.raises(ValueError, match="positive and bounded"):
        DocxParser(max_blocks=0)
    with pytest.raises(ValueError, match="positive and bounded"):
        DocxParser(max_archive_members=20_001)


def test_validated_settings_control_parser_limits() -> None:
    settings = Settings(  # type: ignore[call-arg]
        _env_file=None,
        docx_max_blocks=100,
        docx_max_extracted_characters=10_000,
    )
    parser = DocxParser.from_settings(settings)

    assert parser.parser_name == "python-docx"
    assert parser.parse(io.BytesIO(make_structured_docx())).block_count == 9


def test_locator_contract_rejects_ambiguous_or_partial_docx_locations() -> None:
    with pytest.raises(ValidationError, match="mutually exclusive"):
        SourceLocator(paragraph_number=1, table_number=1)
    with pytest.raises(ValidationError, match="require a table or sheet"):
        SourceLocator(row_number=1, column_number=1)
    with pytest.raises(ValidationError, match="provided together"):
        SourceLocator(table_number=1, row_number=1)


def test_parser_output_is_deterministic_strict_and_has_no_internal_location() -> None:
    source = make_structured_docx()
    parser = DocxParser()
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
    key = f"{tenant_id}/uploads/2026/08/{file_id}.docx"
    stored = storage.put(
        key,
        io.BytesIO(make_structured_docx()),
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )

    with storage.open(stored.key) as stream:
        result = DocxParser().parse(stream)

    assert result.table_count == 2
    assert isinstance(result.blocks[0], DocxParagraphBlock)
    assert result.blocks[0].text == "Synthetic Product Guide"

from __future__ import annotations

import hashlib
import io

import pytest
from pydantic import ValidationError

from app.services.documents.artifacts import (
    ArtifactBoundingBox,
    ArtifactTableBlock,
    ArtifactTextBlock,
    CanonicalParsedArtifact,
    artifact_to_markdown,
)
from app.services.documents.parsers import CsvParser, DocxParser, PdfParser, XlsxParser
from app.services.documents.parsers.native import adapt_native_parse_result
from scripts.seed_m2_complex_files import (
    generate_complex_sources,
    load_complex_seed_definition,
)
from scripts.seed_m2_files import generate_sources, load_seed_definition
from tests.fixtures.docx_factory import make_structured_docx
from tests.fixtures.pdf_factory import make_text_pdf
from tests.fixtures.spreadsheet_factory import (
    make_structured_xlsx,
    make_utf8_sig_semicolon_csv,
)


def _source_hash(source: bytes) -> str:
    return hashlib.sha256(source).hexdigest()


def test_pdf_adapter_preserves_pages_headings_warnings_and_stable_hash() -> None:
    source = make_text_pdf()
    parsed = PdfParser().parse(io.BytesIO(source))

    first = adapt_native_parse_result(parsed, source_sha256=_source_hash(source))
    second = adapt_native_parse_result(parsed, source_sha256=_source_hash(source))

    assert first == second
    assert first.schema_version == "m2-canonical-parsed-artifact-v1"
    assert first.parser.provider == "native"
    assert first.parser.name == "pymupdf"
    assert first.parser.adapter_version == "m2-native-adapter-v1"
    assert first.statistics.page_count == 3
    assert first.statistics.character_count == sum(
        page.character_count for page in parsed.pages
    )
    assert [block.block_id for block in first.blocks] == [
        "b000001",
        "b000002",
        "b000003",
    ]
    page_one = first.blocks[0]
    assert isinstance(page_one, ArtifactTextBlock)
    assert page_one.locator.page_number == 1
    assert page_one.page is not None
    assert page_one.page.image_count == parsed.pages[0].image_count
    assert page_one.heading_hints[0].text == "Synthetic Product Manual"
    assert page_one.heading_hints[0].font_size == (
        parsed.pages[0].heading_hints[0].font_size
    )
    assert [warning.model_dump() for warning in first.warnings] == [
        warning.model_dump() for warning in parsed.warnings
    ]
    assert artifact_to_markdown(first).startswith("<!-- page:1 -->")
    assert "<!-- page:3 -->" in artifact_to_markdown(first)
    assert CanonicalParsedArtifact.model_validate_json(first.model_dump_json()) == first

    tampered = first.model_dump(mode="json")
    tampered["blocks"][0]["text"] = tampered["blocks"][0]["text"].replace(
        "Synthetic",
        "Xynthetic",
        1,
    )
    with pytest.raises(ValidationError, match="content hash"):
        CanonicalParsedArtifact.model_validate(tampered)


def test_docx_adapter_preserves_body_order_heading_paths_tables_and_markdown() -> None:
    source = make_structured_docx()
    parsed = DocxParser().parse(io.BytesIO(source))

    artifact = adapt_native_parse_result(parsed, source_sha256=_source_hash(source))

    assert artifact.source_type == "docx"
    assert artifact.statistics.block_count == parsed.block_count == 9
    assert artifact.statistics.text_block_count == parsed.paragraph_count == 7
    assert artifact.statistics.table_count == parsed.table_count == 2
    assert artifact.statistics.cell_count == parsed.table_cell_count
    assert artifact.statistics.character_count == parsed.character_count
    assert [block.kind for block in artifact.blocks] == [
        "text" if block.kind == "paragraph" else "table" for block in parsed.blocks
    ]
    title = artifact.blocks[0]
    assert isinstance(title, ArtifactTextBlock)
    assert title.text == "Synthetic Product Guide"
    assert title.heading_level == 1
    assert title.heading_path == ["Synthetic Product Guide"]
    first_table = artifact.blocks[2]
    assert isinstance(first_table, ArtifactTableBlock)
    assert first_table.source_kind == "docx_table"
    assert first_table.locator.table_number == 1
    assert first_table.rows[0].cells[0].locator.block_number == 3
    markdown = artifact_to_markdown(artifact)
    assert "# Synthetic Product Guide" in markdown
    assert "## Safety" in markdown
    assert first_table.rows[0].cells[0].display_text in markdown


def test_xlsx_adapter_keeps_sheet_state_cells_formulas_and_cached_values() -> None:
    source = make_structured_xlsx()
    parsed = XlsxParser().parse(io.BytesIO(source))

    artifact = adapt_native_parse_result(parsed, source_sha256=_source_hash(source))

    assert artifact.source_type == "xlsx"
    assert artifact.statistics.sheet_count == parsed.sheet_count == 3
    assert artifact.statistics.formula_count == parsed.formula_count == 2
    assert artifact.statistics.character_count == parsed.character_count
    quotes = artifact.blocks[0]
    assert isinstance(quotes, ArtifactTableBlock)
    assert quotes.source_kind == "worksheet"
    assert quotes.title == "合成报价"
    assert quotes.headers == parsed.sheets[0].headers
    assert quotes.header_row_number == 1
    assert quotes.sheet_state == "visible"
    formula_cell = quotes.rows[1].cells[4]
    assert formula_cell.coordinate == "E2"
    assert formula_cell.data_type == "formula"
    assert formula_cell.formula == "=C2*D2"
    assert formula_cell.value is None
    assert formula_cell.cached_value is None
    assert formula_cell.locator.sheet_name == "合成报价"
    hidden = artifact.blocks[2]
    assert isinstance(hidden, ArtifactTableBlock)
    assert hidden.sheet_state == "hidden"
    assert "=C2*D2" in artifact_to_markdown(artifact)


def test_csv_adapter_preserves_encoding_delimiter_rows_and_safe_public_shape() -> None:
    source = make_utf8_sig_semicolon_csv()
    parsed = CsvParser().parse(io.BytesIO(source))

    artifact = adapt_native_parse_result(parsed, source_sha256=_source_hash(source))

    assert artifact.source_type == "csv"
    assert artifact.statistics.row_count == parsed.row_count == 4
    assert artifact.statistics.character_count == parsed.character_count
    table = artifact.blocks[0]
    assert isinstance(table, ArtifactTableBlock)
    assert table.source_kind == "csv"
    assert table.encoding == "utf-8-sig"
    assert table.delimiter == ";"
    assert table.headers == ["供应商", "备注", "金额"]
    assert table.rows[1].locator.row_start == 2
    assert table.rows[2].is_empty is True
    assert table.rows[1].cells[1].display_text == "字段中包含;分号"
    markdown = artifact_to_markdown(artifact)
    assert "合成供应商A" in markdown
    serialized = artifact.model_dump_json()
    assert "storage_key" not in serialized
    assert "original_name" not in serialized
    assert "D:\\" not in serialized


def test_optional_bounding_box_has_explicit_page_geometry() -> None:
    box = ArtifactBoundingBox(
        page_number=1,
        left=10,
        top=20,
        right=110,
        bottom=220,
        page_width=612,
        page_height=792,
    )

    assert box.coordinate_system == "top_left"
    with pytest.raises(ValidationError, match="inside the page"):
        ArtifactBoundingBox(
            page_number=1,
            left=10,
            top=20,
            right=700,
            bottom=220,
            page_width=612,
            page_height=792,
        )


def test_both_formal_m2_corpora_convert_without_changing_source_hashes() -> None:
    sources = [
        *generate_sources(load_seed_definition()),
        *generate_complex_sources(load_complex_seed_definition()),
    ]
    parsers = {
        "pdf": PdfParser(),
        "docx": DocxParser(),
        "xlsx": XlsxParser(),
        "csv": CsvParser(),
    }

    assert len(sources) == 10
    artifacts = []
    for source in sources:
        source_format = source.definition["format"]
        parsed = parsers[source_format].parse(io.BytesIO(source.content))
        artifact = adapt_native_parse_result(parsed, source_sha256=source.sha256)
        artifacts.append(artifact)
        assert artifact.source_sha256 == hashlib.sha256(source.content).hexdigest()
        assert artifact.source_type == source_format
        assert CanonicalParsedArtifact.model_validate_json(
            artifact.model_dump_json()
        ) == artifact

    assert len({artifact.content_sha256 for artifact in artifacts}) == 10
    assert sum(artifact.statistics.formula_count for artifact in artifacts) == 9

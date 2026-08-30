from __future__ import annotations

from typing import Any

import pytest

from app.core.config import Settings
from app.services.documents.artifacts import (
    ArtifactBoundingBox,
    ArtifactTableBlock,
    ArtifactTextBlock,
    artifact_to_markdown,
)
from app.services.documents.parsers import (
    DocumentEncryptedError,
    DocumentEnhancementError,
    DocumentLimitError,
    DocumentParseError,
)
from app.services.documents.parsers.docling import (
    DoclingParseSnapshot,
    DoclingTableCellSnapshot,
    DoclingTableSnapshot,
    DoclingTextSnapshot,
    adapt_docling_snapshot,
)
from app.services.documents.routing import DocumentParserRouter
from scripts.seed_m2_complex_files import (
    generate_complex_sources,
    load_complex_seed_definition,
)
from scripts.seed_m2_files import generate_sources, load_seed_definition
from tests.fixtures.docx_factory import (
    make_docx_with_archive_payload,
    make_structured_docx,
)
from tests.fixtures.pdf_factory import make_encrypted_pdf


def _settings(**overrides: Any) -> Settings:
    return Settings(_env_file=None, **overrides)  # type: ignore[call-arg]


class FakeDoclingProvider:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.calls: list[tuple[str, str]] = []
        self.error = error

    def parse(
        self,
        *,
        source_name: str,
        source_type: str,
        content: bytes,
    ) -> DoclingParseSnapshot:
        del content
        self.calls.append((source_name, source_type))
        if self.error is not None:
            raise self.error
        return DoclingParseSnapshot(
            source_type=source_type,  # type: ignore[arg-type]
            parser_version="m2-docling-v1+docling-fake",
            page_count=(2 if source_type == "pdf" else None),
            items=[
                DoclingTextSnapshot(
                    text="Docling synthetic extracted fact",
                    label="text",
                    page_number=(1 if source_type == "pdf" else None),
                )
            ],
        )


def test_docling_snapshot_adapter_preserves_order_bbox_and_merged_cells() -> None:
    page_box = ArtifactBoundingBox(
        page_number=1,
        left=10,
        top=20,
        right=590,
        bottom=300,
        page_width=612,
        page_height=792,
    )
    snapshot = DoclingParseSnapshot(
        source_type="pdf",
        parser_version="m2-docling-v1+docling-fake",
        page_count=1,
        items=[
            DoclingTextSnapshot(
                text="Synthetic Cost Table",
                label="title",
                page_number=1,
                heading_level=1,
                heading_path=["Synthetic Cost Table"],
                bounding_box=page_box,
            ),
            DoclingTableSnapshot(
                table_number=1,
                row_count=2,
                column_count=2,
                page_number=1,
                heading_path=["Synthetic Cost Table"],
                bounding_box=page_box,
                cells=[
                    DoclingTableCellSnapshot(
                        text="Costs",
                        start_row=0,
                        end_row=1,
                        start_column=0,
                        end_column=2,
                        column_header=True,
                        bounding_box=page_box,
                    ),
                    DoclingTableCellSnapshot(
                        text="Supplier A",
                        start_row=1,
                        end_row=2,
                        start_column=0,
                        end_column=1,
                    ),
                    DoclingTableCellSnapshot(
                        text="20.90",
                        start_row=1,
                        end_row=2,
                        start_column=1,
                        end_column=2,
                    ),
                ],
            ),
        ],
    )

    artifact = adapt_docling_snapshot(snapshot, source_sha256="a" * 64)

    assert artifact.parser.provider == "docling"
    assert artifact.parser.adapter_version == "m2-docling-adapter-v1"
    assert artifact.statistics.page_count == 1
    assert [block.block_id for block in artifact.blocks] == ["b000001", "b000002"]
    title = artifact.blocks[0]
    table = artifact.blocks[1]
    assert isinstance(title, ArtifactTextBlock)
    assert title.bounding_box == page_box
    assert isinstance(table, ArtifactTableBlock)
    assert table.source_kind == "document_table"
    assert table.header_row_number == 1
    assert table.rows[0].cells[0].column_span == 2
    assert table.rows[0].cells[1].display_text == ""
    assert table.rows[1].cells[1].locator.column_number == 2
    assert "Supplier A" in artifact_to_markdown(artifact)


def test_ordinary_m2_corpus_stays_native_without_calling_docling() -> None:
    provider = FakeDoclingProvider()
    router = DocumentParserRouter(_settings(), docling_provider=provider)

    results = [
        router.parse(
            source_name=source.definition["original_name"],
            content=source.content,
        )
        for source in generate_sources(load_seed_definition())
    ]

    assert results
    assert all(result.route == "native" for result in results)
    assert all(result.selected_artifact.parser.provider == "native" for result in results)
    assert provider.calls == []


def test_complex_corpus_enters_docling_and_office_keeps_native_facts() -> None:
    provider = FakeDoclingProvider()
    router = DocumentParserRouter(_settings(), docling_provider=provider)
    results = {}

    for source in generate_complex_sources(load_complex_seed_definition()):
        results[source.definition["key"]] = router.parse(
            source_name=source.definition["original_name"],
            content=source.content,
        )

    assert len(provider.calls) == 5
    assert [result.route for result in results.values()] == [
        "docling",
        "docling",
        "docling",
        "hybrid",
        "hybrid",
    ]
    assert all(result.docling_artifact is not None for result in results.values())
    assert "detected_two_column" in results[
        "two_column_market_brief"
    ].quality.complexity_tags
    assert "detected_document_table" in results[
        "merged_header_cost_table"
    ].quality.complexity_tags
    assert "detected_embedded_media" in results[
        "visual_quality_notice"
    ].quality.complexity_tags
    assert "detected_merged_cells" in results[
        "multi_region_replenishment"
    ].quality.complexity_tags
    workbook = results["multi_region_replenishment"]
    assert workbook.selected_artifact == workbook.native_artifact
    assert workbook.selected_artifact.statistics.formula_count == 6
    assert workbook.comparison is not None
    assert workbook.comparison.docling_formula_count == 0
    assert workbook.comparison.native_formula_count == 6
    notice = results["visual_quality_notice"]
    assert notice.selected_artifact.parser.provider == "native"
    assert notice.docling_artifact is not None
    assert notice.docling_artifact.parser.provider == "docling"


def test_native_security_failures_happen_before_docling() -> None:
    provider = FakeDoclingProvider()
    router = DocumentParserRouter(_settings(), docling_provider=provider)

    with pytest.raises(DocumentEncryptedError):
        router.parse(
            source_name="private.pdf",
            content=make_encrypted_pdf(),
            complexity_tags=("scanned_pdf",),
        )
    with pytest.raises(DocumentParseError):
        router.parse(
            source_name="corrupt.pdf",
            content=b"not a PDF D:/private/API_KEY",
            complexity_tags=("scanned_pdf",),
        )
    with pytest.raises(DocumentParseError):
        router.parse(
            source_name="mismatched.pdf",
            content=make_structured_docx(),
            complexity_tags=("scanned_pdf",),
        )

    bomb_router = DocumentParserRouter(
        _settings(docx_max_compression_ratio=10),
        docling_provider=provider,
    )
    with pytest.raises(DocumentLimitError):
        bomb_router.parse(
            source_name="bomb.docx",
            content=make_docx_with_archive_payload(1024 * 1024),
            complexity_tags=("image_text",),
        )

    size_router = DocumentParserRouter(
        _settings(upload_max_file_size_bytes=1024 * 1024),
        docling_provider=provider,
    )
    with pytest.raises(DocumentLimitError):
        size_router.parse(
            source_name="too-large.pdf",
            content=b"%PDF-1.7\n" + b"A" * (1024 * 1024),
            complexity_tags=("scanned_pdf",),
        )
    assert provider.calls == []


@pytest.mark.parametrize(
    "private_error",
    [
        RuntimeError("D:/private/model-cache secret-token"),
        TimeoutError("D:/private/timed-out-document.pdf"),
        MemoryError("D:/private/model-cache OOM"),
    ],
)
def test_docling_unavailable_or_private_provider_error_is_safe(
    private_error: Exception,
) -> None:
    scanned = generate_complex_sources(load_complex_seed_definition())[0]
    disabled_router = DocumentParserRouter(_settings())
    with pytest.raises(DocumentEnhancementError) as disabled_error:
        disabled_router.parse(
            source_name=scanned.definition["original_name"],
            content=scanned.content,
            complexity_tags=tuple(scanned.definition["complexity_tags"]),
        )
    assert str(disabled_error.value) == "复杂文档增强解析失败"

    provider = FakeDoclingProvider(error=private_error)
    router = DocumentParserRouter(_settings(), docling_provider=provider)
    with pytest.raises(DocumentEnhancementError) as provider_error:
        router.parse(
            source_name=scanned.definition["original_name"],
            content=scanned.content,
            complexity_tags=tuple(scanned.definition["complexity_tags"]),
        )
    assert str(provider_error.value) == "复杂文档增强解析失败"
    assert "private" not in str(provider_error.value).lower()
    assert "token" not in str(provider_error.value).lower()

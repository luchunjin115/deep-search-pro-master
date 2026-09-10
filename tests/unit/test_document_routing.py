from __future__ import annotations

from typing import Any

import pymupdf
import pytest

from app.core.config import Settings
from app.services.documents.artifacts import (
    ArtifactBoundingBox,
    ArtifactPageProperties,
    ArtifactTableBlock,
    ArtifactTextBlock,
    artifact_to_markdown,
    build_canonical_artifact,
)
from app.services.documents.parsers import (
    DocumentEncryptedError,
    DocumentEnhancementError,
    DocumentLimitError,
    DocumentParseError,
    DocumentQualityRejected,
)
from app.services.documents.parsers.docling import (
    DoclingParseSnapshot,
    DoclingTableCellSnapshot,
    DoclingTableSnapshot,
    DoclingTextSnapshot,
    adapt_docling_snapshot,
)
from app.services.documents.quality import (
    POST_PARSE_QUALITY_POLICY_VERSION,
    ParseQualityDecision,
    decide_parse_route,
)
from app.services.documents.routing import DocumentParserRouter, RoutedParseResult
from scripts.seed_m2_complex_files import (
    generate_complex_sources,
    load_complex_seed_definition,
)
from scripts.seed_m2_files import generate_sources, load_seed_definition
from tests.fixtures.docx_factory import (
    make_docx_with_archive_payload,
    make_structured_docx,
)
from tests.fixtures.pdf_factory import (
    make_encrypted_pdf,
    make_low_text_pdf,
    make_scanned_image_pdf,
    make_text_pdf,
)


def _settings(**overrides: Any) -> Settings:
    values = {
        "docx_image_ocr_backend": "disabled",
        "docx_empty_ocr_min_image_bytes": 10 * 1024 * 1024,
        **overrides,
    }
    return Settings(_env_file=None, **values)  # type: ignore[call-arg]


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
        self.calls.append((source_name, source_type))
        if self.error is not None:
            raise self.error
        page_count = None
        page_numbers: list[int | None] = [None]
        if source_type == "pdf":
            with pymupdf.open(stream=content, filetype="pdf") as document:  # type: ignore[no-untyped-call]
                page_count = document.page_count
            page_numbers = list(range(1, page_count + 1))
        return DoclingParseSnapshot(
            source_type=source_type,  # type: ignore[arg-type]
            parser_version="m2-docling-v1+docling-fake",
            page_count=page_count,
            items=[
                DoclingTextSnapshot(
                    text=f"Docling synthetic extracted fact page {page_number or 1}",
                    label="text",
                    page_number=page_number,
                )
                for page_number in page_numbers
            ],
        )


class TruncatedPageDoclingProvider:
    def parse(
        self,
        *,
        source_name: str,
        source_type: str,
        content: bytes,
    ) -> DoclingParseSnapshot:
        del source_name, content
        return DoclingParseSnapshot(
            source_type=source_type,  # type: ignore[arg-type]
            parser_version="m2-docling-v1+truncated-fake",
            page_count=2,
            items=[
                DoclingTextSnapshot(
                    text="x" * 300,
                    label="text",
                    page_number=1,
                ),
                DoclingTextSnapshot(
                    text="lostpage",
                    label="text",
                    page_number=2,
                ),
            ],
        )


def test_router_attaches_an_accepted_post_parse_quality_decision() -> None:
    result = DocumentParserRouter(_settings()).parse(
        source_name="healthy.pdf",
        content=make_text_pdf(include_empty_page=False),
    )

    assert result.post_parse_quality is not None
    assert result.post_parse_quality.status == "accepted"
    assert result.post_parse_quality.policy_version == POST_PARSE_QUALITY_POLICY_VERSION

    legacy_payload = result.model_dump(mode="json")
    legacy_payload.pop("post_parse_quality")
    assert RoutedParseResult.model_validate(legacy_payload).post_parse_quality is None


def test_router_rejects_a_docling_result_with_one_truncated_page() -> None:
    router = DocumentParserRouter(
        _settings(native_text_min_characters=500),
        docling_provider=TruncatedPageDoclingProvider(),
    )

    with pytest.raises(DocumentQualityRejected) as error:
        router.parse(
            source_name="truncated.pdf",
            content=make_text_pdf(include_empty_page=False),
        )

    assert error.value.decision.status == "rejected"
    assert "pdf_page_text_regression" in error.value.decision.rejection_codes


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
    assert all(
        result.selected_artifact.parser.provider == "native" for result in results
    )
    assert provider.calls == []


def test_complex_corpus_routes_only_unreadable_pdf_and_office() -> None:
    provider = FakeDoclingProvider()
    router = DocumentParserRouter(_settings(), docling_provider=provider)
    results = {}

    for source in generate_complex_sources(load_complex_seed_definition()):
        results[source.definition["key"]] = router.parse(
            source_name=source.definition["original_name"],
            content=source.content,
        )

    assert len(provider.calls) == 2
    assert [result.route for result in results.values()] == [
        "docling",
        "native",
        "native",
        "native",
        "hybrid",
    ]
    assert results["scanned_receiving_ticket"].quality.native_text_health is not None
    assert (
        results["scanned_receiving_ticket"].quality.native_text_health.status
        == "unusable"
    )
    assert results["two_column_market_brief"].quality.native_text_health is not None
    assert (
        results["two_column_market_brief"].quality.native_text_health.status
        == "healthy"
    )
    assert results["two_column_market_brief"].docling_artifact is None
    assert results["merged_header_cost_table"].docling_artifact is None
    assert (
        "detected_two_column"
        in results["two_column_market_brief"].quality.complexity_tags
    )
    assert (
        "detected_document_table"
        in results["merged_header_cost_table"].quality.complexity_tags
    )
    assert (
        "detected_embedded_media"
        in results["visual_quality_notice"].quality.complexity_tags
    )
    assert (
        "detected_merged_cells"
        in results["multi_region_replenishment"].quality.complexity_tags
    )
    workbook = results["multi_region_replenishment"]
    assert workbook.selected_artifact == workbook.native_artifact
    assert workbook.selected_artifact.statistics.formula_count == 6
    assert workbook.comparison is not None
    assert workbook.comparison.docling_formula_count == 0
    assert workbook.comparison.native_formula_count == 6
    notice = results["visual_quality_notice"]
    assert notice.selected_artifact.parser.provider == "native"
    assert notice.docling_artifact is None
    assert "complexity_detected_embedded_media_native_visual_extraction" in (
        notice.reasons
    )


def test_healthy_pdf_keeps_native_despite_structure_tags_and_true_blank_page() -> None:
    provider = FakeDoclingProvider()
    result = DocumentParserRouter(
        _settings(),
        docling_provider=provider,
    ).parse(
        source_name="healthy-structured.pdf",
        content=make_text_pdf(include_empty_page=True),
        complexity_tags=("detected_document_table", "detected_two_column"),
    )

    assert result.route == "native"
    assert result.selected_artifact == result.native_artifact
    assert result.docling_artifact is None
    assert provider.calls == []
    assert result.quality.native_text_health is not None
    assert result.quality.native_text_health.status == "healthy"
    assert result.quality.native_text_health.content_page_count == 2
    assert result.quality.native_text_health.healthy_page_count == 2
    assert result.quality.native_text_health.healthy_page_ratio == 1.0
    assert (
        result.quality.native_text_health.policy_version == "m2-native-text-health-v1"
    )
    assert "complexity_detected_document_table_advisory" in result.reasons
    assert "complexity_detected_two_column_advisory" in result.reasons


@pytest.mark.parametrize(
    ("source_name", "content", "expected_status"),
    [
        ("low-text.pdf", make_low_text_pdf(), "suspect"),
        ("scanned.pdf", make_scanned_image_pdf(), "unusable"),
    ],
)
def test_low_text_and_scanned_pdf_still_enter_docling(
    source_name: str,
    content: bytes,
    expected_status: str,
) -> None:
    provider = FakeDoclingProvider()
    result = DocumentParserRouter(
        _settings(),
        docling_provider=provider,
    ).parse(source_name=source_name, content=content)

    assert result.route == "docling"
    assert result.selected_artifact.parser.provider == "docling"
    assert provider.calls == [(source_name, "pdf")]
    assert result.quality.native_text_health is not None
    assert result.quality.native_text_health.status == expected_status


def test_invalid_native_character_ratio_is_auditable_and_unusable() -> None:
    unreadable = "\ufffd" * 40
    artifact = build_canonical_artifact(
        source_type="pdf",
        source_sha256="a" * 64,
        parser_name="synthetic-native",
        parser_version="1.0",
        blocks=[
            ArtifactTextBlock(
                block_id="b000001",
                text=unreadable,
                locator={"page_number": 1},
                page=ArtifactPageProperties(
                    page_number=1,
                    character_count=len(unreadable),
                    image_count=0,
                    low_text=False,
                ),
            )
        ],
        warnings=[],
        source_character_count=len(unreadable),
        page_count=1,
    )

    decision = decide_parse_route(artifact)

    assert decision.route == "docling"
    assert decision.native_text_health is not None
    assert decision.native_text_health.status == "unusable"
    assert decision.native_text_health.valid_character_count == 0
    assert decision.native_text_health.valid_character_ratio == 0.0
    assert "native_text_no_valid_characters" in decision.native_text_health.reasons


def test_settings_thresholds_control_routing_and_are_recorded() -> None:
    provider = FakeDoclingProvider()
    result = DocumentParserRouter(
        _settings(native_text_min_characters=500),
        docling_provider=provider,
    ).parse(
        source_name="short-for-policy.pdf",
        content=make_text_pdf(include_empty_page=False),
    )

    assert result.route == "docling"
    assert result.quality.native_text_health is not None
    assert result.quality.native_text_health.status == "suspect"
    assert result.quality.native_text_health.minimum_character_count == 500
    assert (
        "native_text_character_count_low" in result.quality.native_text_health.reasons
    )


def test_legacy_quality_payload_without_health_assessment_remains_readable() -> None:
    result = DocumentParserRouter(_settings()).parse(
        source_name="legacy.pdf",
        content=make_text_pdf(include_empty_page=False),
    )
    payload = result.quality.model_dump(mode="json")
    payload.pop("native_text_health")

    restored = ParseQualityDecision.model_validate(payload)

    assert restored.native_text_health is None


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

from __future__ import annotations

import json
from pathlib import Path

from app.evals.parser_diagnostics import (
    ParserDiagnosticReport,
    _artifact_summary,
    diagnose_evidence_artifacts,
)
from app.services.documents.artifacts import (
    ArtifactDocxSource,
    ArtifactTextBlock,
    ArtifactWarning,
    CanonicalParsedArtifact,
    build_canonical_artifact,
)
from app.services.documents.parsers.base import SourceLocator

ROOT = Path(__file__).resolve().parents[2]
REPORT_TEMPLATE_PATH = (
    ROOT / "data" / "evals" / "m2_parser_diagnostic_report_template_v1.json"
)


def _artifact(
    text: str,
    *,
    provider: str,
    warning_codes: tuple[str, ...] = (),
) -> CanonicalParsedArtifact:
    return build_canonical_artifact(
        source_type="pdf",
        source_sha256="a" * 64,
        parser_name="test-parser",
        parser_version="1.0",
        provider=provider,  # type: ignore[arg-type]
        adapter_version=(
            "m2-docling-adapter-v1" if provider == "docling" else "m2-native-adapter-v1"
        ),
        blocks=[
            ArtifactTextBlock(
                block_id="b000001",
                text=text,
                locator=SourceLocator(page_number=1),
            )
        ],
        warnings=[
            ArtifactWarning(
                code=code,
                message="Safe diagnostic warning",
                locator=SourceLocator(),
            )
            for code in warning_codes
        ],
        source_character_count=sum(not character.isspace() for character in text),
        page_count=1,
    )


def test_diagnosis_separates_route_selection_from_provider_loss() -> None:
    native = _artifact("The fixed customs duty is EUR 3.", provider="native")
    docling = _artifact("Unrelated converted text.", provider="docling")

    result = diagnose_evidence_artifacts(
        case_id="diagnostic-case",
        expected_texts=["The fixed customs duty is EUR 3."],
        page_ranges=[(1, 1)],
        route="docling",
        selected_artifact=docling,
        native_artifact=native,
        docling_artifact=docling,
        requires_ocr=False,
    )

    assert result.category == "route_selection_loss"
    assert result.selected.exact_match is False
    assert result.native.exact_match is True
    assert result.docling is not None
    assert result.docling.exact_match is False


def test_diagnosis_identifies_formatting_only_difference() -> None:
    selected = _artifact("The fixed customs-duty is\nEUR 3.", provider="docling")

    result = diagnose_evidence_artifacts(
        case_id="diagnostic-case",
        expected_texts=["The fixed customs duty is EUR 3."],
        page_ranges=[(1, 1)],
        route="docling",
        selected_artifact=selected,
        native_artifact=_artifact("No matching text.", provider="native"),
        docling_artifact=selected,
        requires_ocr=False,
    )

    assert result.category == "evaluation_normalization_gap"
    assert result.selected.exact_match is False
    assert result.selected.relaxed_match is True


def test_diagnosis_surfaces_partial_provider_result_before_generic_loss() -> None:
    native = _artifact("No matching text.", provider="native")
    docling = _artifact(
        "Only fixed customs words survived.",
        provider="docling",
        warning_codes=("docling_partial_result",),
    )

    result = diagnose_evidence_artifacts(
        case_id="diagnostic-case",
        expected_texts=["The fixed customs duty is EUR 3."],
        page_ranges=[(1, 1)],
        route="docling",
        selected_artifact=docling,
        native_artifact=native,
        docling_artifact=docling,
        requires_ocr=False,
    )

    assert result.category == "provider_partial_result"
    assert result.docling is not None
    assert result.docling.warning_codes == ["docling_partial_result"]


def test_planned_diagnostic_report_template_contains_no_runtime_claims() -> None:
    payload = json.loads(REPORT_TEMPLATE_PATH.read_text(encoding="utf-8"))
    report = ParserDiagnosticReport.model_validate(payload)

    assert report.run_status == "planned"
    assert report.documents == []
    assert report.aggregate.cases_diagnosed == 0
    assert "expected_text" not in report.model_dump_json()


def test_diagnostic_summary_separates_docx_header_footer_and_image_ocr() -> None:
    blocks = [
        ArtifactTextBlock(
            block_id="b000001",
            source_kind="docx_header",
            docx_source=ArtifactDocxSource(
                section_number=1,
                region_block_number=1,
                content_kind="paragraph",
            ),
            text="HEADER",
            locator=SourceLocator(),
        ),
        ArtifactTextBlock(
            block_id="b000002",
            source_kind="docx_footer",
            docx_source=ArtifactDocxSource(
                section_number=1,
                region_block_number=2,
                content_kind="paragraph",
            ),
            text="FOOTER",
            locator=SourceLocator(),
        ),
        ArtifactTextBlock(
            block_id="b000003",
            source_kind="docx_image_ocr",
            docx_source=ArtifactDocxSource(
                run_number=1,
                image_number=1,
                image_sha256="a" * 64,
                image_size_bytes=100,
                image_width=10,
                image_height=10,
                content_type="image/png",
                ocr_provider_name="fake",
                ocr_provider_version="fake-v1",
            ),
            text="IMAGE",
            locator=SourceLocator(block_number=1, paragraph_number=1),
        ),
    ]
    artifact = build_canonical_artifact(
        source_type="docx",
        source_sha256="b" * 64,
        parser_name="python-docx",
        parser_version="m2-docx-v2",
        blocks=blocks,
        warnings=[],
        source_character_count=sum(
            sum(not character.isspace() for character in block.text) for block in blocks
        ),
    )

    summary = _artifact_summary(artifact)

    assert summary.docx_header_block_count == 1
    assert summary.docx_footer_block_count == 1
    assert summary.docx_image_ocr_block_count == 1

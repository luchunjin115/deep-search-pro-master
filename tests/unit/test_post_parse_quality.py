from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.services.documents.artifacts import (
    ArtifactDocxSource,
    ArtifactPageProperties,
    ArtifactTextBlock,
    CanonicalParsedArtifact,
    build_canonical_artifact,
)
from app.services.documents.parsers.base import SourceLocator
from app.services.documents.quality import (
    POST_PARSE_QUALITY_POLICY_VERSION,
    PostParseQualityDecision,
    assess_native_text_health,
    evaluate_post_parse_quality,
)


def _pdf_artifact(
    pages: list[tuple[str, int]],
    *,
    provider: str = "native",
) -> CanonicalParsedArtifact:
    blocks = [
        ArtifactTextBlock(
            block_id=f"b{page_number:06d}",
            text=text,
            locator=SourceLocator(page_number=page_number),
            page=(
                ArtifactPageProperties(
                    page_number=page_number,
                    character_count=sum(not character.isspace() for character in text),
                    image_count=image_count,
                    low_text=sum(not character.isspace() for character in text) < 20,
                )
                if provider == "native"
                else None
            ),
        )
        for page_number, (text, image_count) in enumerate(pages, start=1)
    ]
    return build_canonical_artifact(
        source_type="pdf",
        source_sha256="a" * 64,
        parser_name="pymupdf" if provider == "native" else "docling",
        parser_version="test-v1",
        provider=provider,  # type: ignore[arg-type]
        adapter_version=(
            "m2-native-adapter-v1" if provider == "native" else "m2-docling-adapter-v1"
        ),
        blocks=blocks,
        warnings=[],
        source_character_count=sum(
            sum(not character.isspace() for character in text) for text, _ in pages
        ),
        page_count=len(pages),
    )


def _docx_artifact(
    *,
    image_size_bytes: int,
    image_text: str = "",
    paragraph_text: str = "正文内容足够说明这张图片的上下文，并且保留其他可用业务事实",
) -> CanonicalParsedArtifact:
    locator = SourceLocator(block_number=1, paragraph_number=1)
    blocks: list[ArtifactTextBlock] = []
    if paragraph_text:
        blocks.append(
            ArtifactTextBlock(
                block_id="b000001",
                text=paragraph_text,
                locator=locator,
            )
        )
    blocks.append(
        ArtifactTextBlock(
            block_id=f"b{len(blocks) + 1:06d}",
            source_kind="docx_image_ocr",
            docx_source=ArtifactDocxSource(
                run_number=1,
                image_number=1,
                image_sha256="b" * 64,
                image_size_bytes=image_size_bytes,
                image_width=800,
                image_height=400,
                content_type="image/png",
                ocr_provider_name="rapidocr",
                ocr_provider_version="test-v1",
            ),
            text=image_text,
            locator=locator,
        )
    )
    character_count = sum(
        sum(not character.isspace() for character in block.text) for block in blocks
    )
    return build_canonical_artifact(
        source_type="docx",
        source_sha256="b" * 64,
        parser_name="python-docx",
        parser_version="test-v2",
        blocks=blocks,
        warnings=[],
        source_character_count=character_count,
    )


def _evaluate(
    native: CanonicalParsedArtifact,
    selected: CanonicalParsedArtifact,
):  # type: ignore[no-untyped-def]
    return evaluate_post_parse_quality(
        native_artifact=native,
        selected_artifact=selected,
        native_text_health=assess_native_text_health(native),
        minimum_final_native_ratio=0.7,
        minimum_page_character_count=10,
        native_page_baseline_character_count=50,
        docx_empty_ocr_min_image_bytes=5 * 1024,
        minimum_docx_body_character_count=20,
    )


def test_full_text_retention_boundary_is_versioned_and_inclusive() -> None:
    native = _pdf_artifact([("a" * 100, 0)])

    accepted = _evaluate(native, _pdf_artifact([("b" * 70, 0)], provider="docling"))
    rejected = _evaluate(native, _pdf_artifact([("b" * 69, 0)], provider="docling"))

    assert accepted.policy_version == POST_PARSE_QUALITY_POLICY_VERSION
    assert accepted.status == "accepted"
    assert accepted.character_retention_ratio == 0.7
    assert rejected.status == "rejected"
    assert rejected.character_retention_ratio == 0.69
    assert rejected.rejection_codes == ["final_text_retention_below_threshold"]


def test_pdf_page_regression_is_rejected_even_when_total_text_grows() -> None:
    native = _pdf_artifact([("a" * 60, 0), ("b" * 60, 0)])
    selected = _pdf_artifact(
        [("c" * 200, 0), ("d" * 9, 0)],
        provider="docling",
    )

    decision = _evaluate(native, selected)

    assert decision.status == "rejected"
    assert decision.rejection_codes == ["pdf_page_text_regression"]
    assert decision.page_assessments[1].status == "rejected"
    assert decision.page_assessments[1].reason == "native_text_missing_from_final_page"


def test_pdf_image_page_requires_text_but_real_blank_page_does_not() -> None:
    native = _pdf_artifact([("", 1), ("", 0)])
    selected = _pdf_artifact([("x" * 9, 0), ("", 0)], provider="docling")

    decision = _evaluate(native, selected)

    assert decision.status == "rejected"
    assert decision.rejection_codes == ["pdf_image_page_ocr_unrecovered"]
    assert [page.status for page in decision.page_assessments] == [
        "rejected",
        "ignored_blank",
    ]


def test_pdf_page_count_mismatch_is_rejected() -> None:
    native = _pdf_artifact([("a" * 60, 0), ("b" * 60, 0)])
    selected = _pdf_artifact([("c" * 200, 0)], provider="docling")

    decision = _evaluate(native, selected)

    assert decision.status == "rejected"
    assert "pdf_page_count_mismatch" in decision.rejection_codes


def test_large_empty_docx_ocr_warns_when_body_context_remains() -> None:
    artifact = _docx_artifact(image_size_bytes=5 * 1024 + 1)

    decision = _evaluate(artifact, artifact)

    assert decision.status == "accepted"
    assert decision.warning_codes == ["ocr_possible_failure"]
    assert decision.docx_image_assessments[0].status == "warning"
    assert decision.docx_image_assessments[0].reason == "large_image_ocr_empty"


def test_large_empty_docx_ocr_rejects_an_image_only_paragraph() -> None:
    artifact = _docx_artifact(
        image_size_bytes=5 * 1024 + 1,
        paragraph_text="",
    )

    decision = _evaluate(artifact, artifact)

    assert decision.status == "rejected"
    assert decision.rejection_codes == ["docx_image_only_paragraph_ocr_empty"]
    assert decision.docx_image_assessments[0].status == "rejected"


def test_large_empty_docx_ocr_rejects_an_almost_empty_document() -> None:
    artifact = _docx_artifact(
        image_size_bytes=5 * 1024 + 1,
        paragraph_text="短正文",
    )

    decision = _evaluate(artifact, artifact)

    assert decision.status == "rejected"
    assert decision.rejection_codes == ["docx_document_body_ocr_empty"]
    assert (
        decision.docx_image_assessments[0].reason
        == "document_body_insufficient_after_empty_ocr"
    )


def test_successful_docx_ocr_is_accepted_without_a_warning() -> None:
    artifact = _docx_artifact(
        image_size_bytes=5 * 1024 + 1,
        image_text="识别出的图片文字",
        paragraph_text="",
    )

    decision = _evaluate(artifact, artifact)

    assert decision.status == "accepted"
    assert decision.warning_codes == []
    assert decision.docx_image_assessments[0].status == "accepted"


def test_empty_docx_ocr_at_size_boundary_does_not_warn() -> None:
    artifact = _docx_artifact(image_size_bytes=5 * 1024)

    decision = _evaluate(artifact, artifact)

    assert decision.status == "accepted"
    assert decision.warning_codes == []
    assert decision.docx_image_assessments[0].status == "below_threshold"


def test_serialized_quality_decision_cannot_hide_a_page_rejection() -> None:
    native = _pdf_artifact([("a" * 60, 0)])
    decision = _evaluate(native, _pdf_artifact([("b" * 9, 0)], provider="docling"))
    payload = decision.model_dump(mode="json")
    payload["status"] = "accepted"
    payload["rejection_codes"] = []

    with pytest.raises(ValidationError, match="rejection codes do not match"):
        PostParseQualityDecision.model_validate(payload)

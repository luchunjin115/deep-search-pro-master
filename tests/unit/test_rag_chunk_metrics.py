from __future__ import annotations

import hashlib
import io
from uuid import UUID

from app.evals.chunk_metrics import (
    ChunkConfigurationAggregate,
    evaluate_chunk_document,
    select_first_round_candidates,
)
from app.schemas.evaluation import (
    EvaluationCase,
    ExpectedEvidenceSpan,
    TrustedHeadingContextCase,
)
from app.services.documents.artifacts import (
    ArtifactDocxSource,
    ArtifactHeadingHint,
    ArtifactTextBlock,
    build_canonical_artifact,
)
from app.services.documents.chunking import (
    ChunkerIdentity,
    ChunkingConfig,
    ChunkInputProvenance,
    StructureAwareDocumentChunker,
    UnicodeMixedTokenCounter,
    build_chunk_artifact,
)
from app.services.documents.parsers.base import SourceLocator
from app.services.documents.parsers.native import adapt_native_parse_result
from app.services.documents.parsers.pdf import PdfParser
from tests.fixtures.pdf_factory import make_two_column_text_pdf


def _case(*, case_id: str, text: str) -> EvaluationCase:
    return EvaluationCase(
        case_id=case_id,
        dataset_version="m2-cross-border-rag-smoke-v1",
        split="debug",
        question="What is the reviewed fact?",
        language="en",
        category="ocr_complex_layout",
        difficulty="direct",
        source_group="synthetic_engineering_regression",
        expected_document_ids=["doc-quality"],
        expected_evidence_spans=[
            ExpectedEvidenceSpan(
                source_id="source-quality",
                document_id="doc-quality",
                source_type="docx",
                character_start=0,
                character_end=len(text),
                exact_text=text,
            )
        ],
        answer_key_points=[text],
        should_answer=True,
        trusted_user_fixture_id="user-fixture-company-owner",
        acl_fixture_id="acl-fixture-tenant",
        version_fixture_id="version-fixture-active",
    )


def _visual_docx_artifact():
    return build_canonical_artifact(
        source_type="docx",
        source_sha256="1" * 64,
        parser_name="python-docx",
        parser_version="2.0.0",
        blocks=[
            ArtifactTextBlock(
                block_id="b000001",
                source_kind="docx_header",
                docx_source=ArtifactDocxSource(
                    section_number=1,
                    region_block_number=1,
                    content_kind="paragraph",
                ),
                text="CONTROL CODE: QC-VISUAL-17",
                locator=SourceLocator(),
            ),
            ArtifactTextBlock(
                block_id="b000002",
                text="Before the image.",
                locator=SourceLocator(
                    block_number=1,
                    paragraph_number=1,
                    heading_path=["Quality notice"],
                ),
                heading_path=["Quality notice"],
            ),
            ArtifactTextBlock(
                block_id="b000003",
                source_kind="docx_image_ocr",
                docx_source=ArtifactDocxSource(
                    run_number=2,
                    image_number=1,
                    image_sha256="2" * 64,
                    image_size_bytes=8192,
                    image_width=640,
                    image_height=320,
                    content_type="image/png",
                    ocr_provider_name="rapidocr",
                    ocr_provider_version="3.9.2",
                    ocr_mean_confidence=0.99,
                ),
                text="ACTION: QUARANTINE 12 PCS",
                locator=SourceLocator(
                    block_number=1,
                    paragraph_number=1,
                    heading_path=["Quality notice"],
                ),
                heading_path=["Quality notice"],
            ),
            ArtifactTextBlock(
                block_id="b000004",
                text="After the image.",
                locator=SourceLocator(
                    block_number=1,
                    paragraph_number=1,
                    heading_path=["Quality notice"],
                ),
                heading_path=["Quality notice"],
            ),
            ArtifactTextBlock(
                block_id="b000005",
                source_kind="docx_footer",
                docx_source=ArtifactDocxSource(
                    section_number=1,
                    region_block_number=1,
                    content_kind="paragraph",
                ),
                text="ESCALATION: QUALITY-LEAD",
                locator=SourceLocator(),
            ),
        ],
        warnings=[],
        source_character_count=98,
    )


def _chunk_artifact(artifact):
    config = ChunkingConfig()
    counter = UnicodeMixedTokenCounter()
    result = StructureAwareDocumentChunker(
        config=config,
        token_counter=counter,
    ).chunk(artifact)
    return build_chunk_artifact(
        input_provenance=ChunkInputProvenance(
            document_id=UUID("11111111-1111-1111-1111-111111111111"),
            document_version_id=UUID("22222222-2222-2222-2222-222222222222"),
            source_sha256=artifact.source_sha256,
            parsed_publication_sha256="3" * 64,
            selected_artifact_content_sha256=artifact.content_sha256,
        ),
        chunker=ChunkerIdentity(
            token_counter_name=counter.name,
            token_counter_version=counter.version,
        ),
        config=config,
        chunks=result.chunks,
        excluded_spans=result.excluded_spans,
        skipped_tables=result.skipped_tables,
    )


def _heading_artifact():
    return build_canonical_artifact(
        source_type="pdf",
        source_sha256="5" * 64,
        parser_name="pymupdf",
        parser_version="1.26.4",
        blocks=[
            ArtifactTextBlock(
                block_id="b000001",
                text="IOSS适用范围\n申报人必须保存相关交易记录。",
                locator=SourceLocator(page_number=1),
                heading_hints=[
                    ArtifactHeadingHint(
                        text="IOSS适用范围",
                        level=1,
                        locator=SourceLocator(page_number=1),
                    )
                ],
            )
        ],
        warnings=[],
        source_character_count=22,
        page_count=1,
    )


def _heading_case() -> TrustedHeadingContextCase:
    return TrustedHeadingContextCase(
        case_id="heading-context-ioss",
        source_id="source-quality",
        document_id="doc-quality",
        source_type="pdf",
        heading_path=["IOSS适用范围"],
        heading_page_number=1,
        heading_exact_text="IOSS适用范围",
        body_document_id="doc-quality",
        body_page_number=1,
        body_exact_text="申报人必须保存相关交易记录。",
        binding_scope="following_flow",
    )


def test_chunk_metrics_preserve_docx_header_image_ocr_and_context_order() -> None:
    artifact = _visual_docx_artifact()
    chunks = _chunk_artifact(artifact)

    result = evaluate_chunk_document(
        source_id="source-quality",
        logical_document_id="doc-quality",
        artifact=artifact,
        chunk_artifact=chunks,
        cases=[
            _case(case_id="case-image", text="ACTION: QUARANTINE 12 PCS"),
            _case(
                case_id="case-cross-block",
                text="Before the image. ACTION: QUARANTINE 12 PCS",
            ),
        ],
    )

    assert result.golden_cases[0].answer_contained is True
    assert result.golden_cases[0].locator_passed is True
    assert result.golden_cases[0].failure_layer is None
    assert result.golden_cases[1].locator_passed is True
    assert result.structure.docx_header_units == 1
    assert result.structure.docx_header_units_preserved == 1
    assert result.structure.image_ocr_units == 1
    assert result.structure.image_ocr_units_preserved == 1
    assert result.structure.context_links == 1
    assert result.structure.context_links_preserved == 1
    assert result.source_order_preserved is True
    assert result.locator_integrity_passed is True


def test_chunk_failure_attribution_distinguishes_all_three_layers() -> None:
    artifact = _visual_docx_artifact()
    chunks = _chunk_artifact(artifact)
    missing = _case(case_id="case-parser", text="NOT PRESENT IN ARTIFACT")

    parser_failure = evaluate_chunk_document(
        source_id="source-quality",
        logical_document_id="doc-quality",
        artifact=artifact,
        chunk_artifact=chunks,
        cases=[missing],
    ).golden_cases[0]

    assert parser_failure.failure_layer == "parser_artifact"

    original = next(
        chunk
        for chunk in chunks.chunks
        if "ACTION: QUARANTINE 12 PCS" in chunk.body_text
    )
    text_without_image = original.body_text.replace("ACTION: QUARANTINE 12 PCS", "")
    broken = chunks.model_copy(
        update={
            "chunks": [
                (
                    chunk.model_copy(
                        update={
                            "body_text": text_without_image,
                            "retrieval_text": text_without_image,
                        }
                    )
                    if chunk.chunk_id == original.chunk_id
                    else chunk
                )
                for chunk in chunks.chunks
            ]
        }
    )
    chunk_failure = evaluate_chunk_document(
        source_id="source-quality",
        logical_document_id="doc-quality",
        artifact=artifact,
        chunk_artifact=broken,
        cases=[_case(case_id="case-chunk", text="ACTION: QUARANTINE 12 PCS")],
    ).golden_cases[0]

    assert chunk_failure.failure_layer == "chunk_rule"

    bad_spans = [
        span.model_copy(update={"block_id": "b000002"})
        for span in original.source_spans
    ]
    wrong_locator = chunks.model_copy(
        update={
            "chunks": [
                (
                    chunk.model_copy(update={"source_spans": bad_spans})
                    if chunk.chunk_id == original.chunk_id
                    else chunk
                )
                for chunk in chunks.chunks
            ]
        }
    )
    locator_failure = evaluate_chunk_document(
        source_id="source-quality",
        logical_document_id="doc-quality",
        artifact=artifact,
        chunk_artifact=wrong_locator,
        cases=[_case(case_id="case-locator", text="ACTION: QUARANTINE 12 PCS")],
    ).golden_cases[0]

    assert locator_failure.answer_contained is True
    assert locator_failure.failure_layer == "locator"


def test_candidate_selection_keeps_every_best_quality_tie() -> None:
    best = ChunkConfigurationAggregate.for_test(
        config_id="chunk-current",
        answer_containment_rate=1.0,
        locator_pass_rate=1.0,
        boundary_break_rate=0.0,
    )
    tied = best.model_copy(update={"config_id": "chunk-large"})
    worse = ChunkConfigurationAggregate.for_test(
        config_id="chunk-compact",
        answer_containment_rate=0.9,
        locator_pass_rate=1.0,
        boundary_break_rate=0.0,
    )

    assert select_first_round_candidates([worse, tied, best]) == [
        "chunk-current",
        "chunk-large",
    ]


def test_pdf_locator_ignores_only_unindexed_line_break_whitespace() -> None:
    artifact = build_canonical_artifact(
        source_type="pdf",
        source_sha256="4" * 64,
        parser_name="pymupdf",
        parser_version="1.26.4",
        blocks=[
            ArtifactTextBlock(
                block_id="b000001",
                text="alpha\nbeta",
                locator=SourceLocator(page_number=1),
            )
        ],
        warnings=[],
        source_character_count=9,
        page_count=1,
    )
    chunks = _chunk_artifact(artifact)
    case = _case(case_id="case-pdf-lines", text="alpha beta").model_copy(
        update={
            "expected_evidence_spans": [
                ExpectedEvidenceSpan(
                    source_id="source-quality",
                    document_id="doc-quality",
                    source_type="pdf",
                    page_start=1,
                    page_end=1,
                    exact_text="alpha beta",
                )
            ]
        }
    )

    result = evaluate_chunk_document(
        source_id="source-quality",
        logical_document_id="doc-quality",
        artifact=artifact,
        chunk_artifact=chunks,
        cases=[case],
    )

    assert result.golden_cases[0].locator_passed is True


def test_heading_quality_rejects_metadata_attached_only_to_a_title_shell() -> None:
    artifact = _heading_artifact()
    chunks = _chunk_artifact(artifact)
    title_shell = chunks.model_copy(
        update={
            "chunks": [
                chunk.model_copy(
                    update={
                        "body_text": "IOSS适用范围",
                        "retrieval_text": "IOSS适用范围",
                        "heading_path": ["IOSS适用范围"],
                    }
                )
                for chunk in chunks.chunks
            ]
        }
    )

    result = evaluate_chunk_document(
        source_id="source-quality",
        logical_document_id="doc-quality",
        artifact=artifact,
        chunk_artifact=title_shell,
        cases=[],
        heading_cases=[_heading_case()],
    )

    assert result.structure.heading_units == 1
    assert result.structure.heading_units_preserved == 0


def test_heading_quality_requires_trusted_path_body_and_locator_in_one_chunk() -> None:
    artifact = _heading_artifact()
    chunks = _chunk_artifact(artifact)

    result = evaluate_chunk_document(
        source_id="source-quality",
        logical_document_id="doc-quality",
        artifact=artifact,
        chunk_artifact=chunks,
        cases=[],
        heading_cases=[_heading_case()],
    )

    assert result.structure.heading_units == 1
    assert result.structure.heading_units_preserved == 1
    assert result.structure.paragraph_units == 1
    assert result.structure.paragraph_units_preserved == 1
    assert result.structure.boundary_units == 1
    assert result.structure.boundary_breaks == 0


def test_heading_boundary_exclusion_accepts_exact_parser_declared_metadata() -> None:
    artifact = _heading_artifact()
    chunks = _chunk_artifact(artifact)
    without_binding = chunks.model_copy(
        update={
            "chunks": [
                chunk.model_copy(update={"heading_sources": []})
                for chunk in chunks.chunks
            ]
        }
    )

    result = evaluate_chunk_document(
        source_id="source-quality",
        logical_document_id="doc-quality",
        artifact=artifact,
        chunk_artifact=without_binding,
        cases=[],
        heading_cases=[_heading_case()],
    )

    assert result.structure.heading_units_preserved == 0
    assert result.structure.paragraph_units == 1
    assert result.structure.paragraph_units_preserved == 1
    assert result.structure.boundary_breaks == 0

    without_exclusion = chunks.model_copy(
        update={
            "excluded_spans": [
                span
                for span in chunks.excluded_spans
                if span.reason != "heading_metadata"
            ]
        }
    )
    missing_exclusion_result = evaluate_chunk_document(
        source_id="source-quality",
        logical_document_id="doc-quality",
        artifact=artifact,
        chunk_artifact=without_exclusion,
        cases=[],
        heading_cases=[_heading_case()],
    )

    assert missing_exclusion_result.structure.heading_units_preserved == 0
    assert missing_exclusion_result.structure.boundary_breaks == 1


def test_pdf_layout_split_across_column_chunks_is_not_a_boundary_break() -> None:
    source = make_two_column_text_pdf()
    artifact = adapt_native_parse_result(
        PdfParser().parse(io.BytesIO(source)),
        source_sha256=hashlib.sha256(source).hexdigest(),
    )

    result = evaluate_chunk_document(
        source_id="source-two-column",
        logical_document_id="doc-two-column",
        artifact=artifact,
        chunk_artifact=_chunk_artifact(artifact),
        cases=[],
    )

    assert result.structure.boundary_units > 0
    assert result.structure.boundary_breaks == 0


def test_numbered_heading_hint_is_not_counted_as_missing_body_text() -> None:
    artifact = build_canonical_artifact(
        source_type="pdf",
        source_sha256="6" * 64,
        parser_name="pymupdf",
        parser_version="1.26.4",
        blocks=[
            ArtifactTextBlock(
                block_id="b000001",
                text="2. IOSS适用范围\n申报人必须保存相关交易记录。",
                locator=SourceLocator(page_number=1),
                heading_hints=[
                    ArtifactHeadingHint(
                        text="2. IOSS适用范围",
                        level=1,
                        locator=SourceLocator(page_number=1),
                    )
                ],
            )
        ],
        warnings=[],
        source_character_count=24,
        page_count=1,
    )

    result = evaluate_chunk_document(
        source_id="source-numbered-heading",
        logical_document_id="doc-numbered-heading",
        artifact=artifact,
        chunk_artifact=_chunk_artifact(artifact),
        cases=[],
    )

    assert result.structure.paragraph_units == 1
    assert result.structure.paragraph_units_preserved == 1
    assert result.structure.boundary_units == 1
    assert result.structure.boundary_breaks == 0


def test_heading_quality_rejects_title_text_without_heading_metadata() -> None:
    artifact = _heading_artifact()
    chunks = _chunk_artifact(artifact)
    forged = chunks.model_copy(
        update={
            "chunks": [
                chunk.model_copy(
                    update={
                        "body_text": ("IOSS适用范围\n申报人必须保存相关交易记录。"),
                        "retrieval_text": (
                            "IOSS适用范围\n申报人必须保存相关交易记录。"
                        ),
                        "heading_path": [],
                    }
                )
                for chunk in chunks.chunks
            ]
        }
    )

    result = evaluate_chunk_document(
        source_id="source-quality",
        logical_document_id="doc-quality",
        artifact=artifact,
        chunk_artifact=forged,
        cases=[],
        heading_cases=[_heading_case()],
    )

    assert result.structure.heading_units_preserved == 0


def test_heading_quality_rejects_forged_parent_child_hierarchy() -> None:
    artifact = _heading_artifact()
    chunks = _chunk_artifact(artifact)
    forged = chunks.model_copy(
        update={
            "chunks": [
                chunk.model_copy(
                    update={
                        "heading_path": ["伪造的父标题", "IOSS适用范围"],
                        "retrieval_text": (
                            "伪造的父标题 > IOSS适用范围\n\n"
                            "申报人必须保存相关交易记录。"
                        ),
                    }
                )
                for chunk in chunks.chunks
            ]
        }
    )

    result = evaluate_chunk_document(
        source_id="source-quality",
        logical_document_id="doc-quality",
        artifact=artifact,
        chunk_artifact=forged,
        cases=[],
        heading_cases=[_heading_case()],
    )

    assert result.structure.heading_units_preserved == 0


def test_heading_quality_rejects_body_with_wrong_source_span() -> None:
    artifact = _heading_artifact()
    chunks = _chunk_artifact(artifact)
    forged = chunks.model_copy(
        update={
            "chunks": [
                chunk.model_copy(
                    update={
                        "source_spans": [
                            span.model_copy(
                                update={"character_start": 0, "character_end": 8}
                            )
                            for span in chunk.source_spans
                        ]
                    }
                )
                for chunk in chunks.chunks
            ]
        }
    )

    result = evaluate_chunk_document(
        source_id="source-quality",
        logical_document_id="doc-quality",
        artifact=artifact,
        chunk_artifact=forged,
        cases=[],
        heading_cases=[_heading_case()],
    )

    assert result.structure.heading_units_preserved == 0


def test_heading_quality_rejects_golden_heading_missing_from_parser_hints() -> None:
    artifact = _heading_artifact()
    without_hint = artifact.model_copy(
        update={
            "blocks": [
                block.model_copy(update={"heading_hints": []})
                if isinstance(block, ArtifactTextBlock)
                else block
                for block in artifact.blocks
            ]
        }
    )
    chunks = _chunk_artifact(artifact)

    result = evaluate_chunk_document(
        source_id="source-quality",
        logical_document_id="doc-quality",
        artifact=without_hint,
        chunk_artifact=chunks,
        cases=[],
        heading_cases=[_heading_case()],
    )

    assert result.structure.heading_units_preserved == 0

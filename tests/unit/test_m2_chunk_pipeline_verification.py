from __future__ import annotations

import io

from app.core.config import Settings
from app.services.documents.chunking import (
    ChunkingConfig,
    StructureAwareDocumentChunker,
    UnicodeMixedTokenCounter,
)
from app.services.documents.parsers import DocxParser
from app.services.documents.parsers.native import adapt_native_parse_result
from app.services.documents.routing import DocumentParserRouter
from scripts.seed_m2_complex_files import (
    generate_complex_sources,
    load_complex_seed_definition,
)
from scripts.seed_m2_files import generate_sources, load_seed_definition
from scripts.verify_m2_chunk_pipeline import (
    GOLDEN_CHUNK_PROBES,
    canonical_chunk_order_is_preserved,
    evaluate_document_facts,
)


def _settings() -> Settings:
    return Settings(  # type: ignore[call-arg]
        _env_file=".env.example",
        app_env="test",
        docling_backend="disabled",
        docx_image_ocr_backend="disabled",
    )


def test_all_ten_formal_documents_have_two_reviewed_chunk_probes() -> None:
    ordinary = load_seed_definition()["documents"]
    complex_documents = load_complex_seed_definition()["documents"]

    assert {document["key"] for document in ordinary + complex_documents} == set(
        GOLDEN_CHUNK_PROBES
    )
    assert all(len(probes) == 2 for probes in GOLDEN_CHUNK_PROBES.values())


def test_ordinary_golden_set_preserves_all_content_and_locators_in_chunks() -> None:
    settings = _settings()
    data = load_seed_definition()
    router = DocumentParserRouter(settings)
    counter = UnicodeMixedTokenCounter()
    chunker = StructureAwareDocumentChunker(
        config=ChunkingConfig.from_settings(settings),
        token_counter=counter,
    )

    facts = []
    for source in generate_sources(data):
        routed = router.parse(
            source_name=source.definition["original_name"],
            content=source.content,
        )
        first = chunker.chunk(routed.selected_artifact)
        second = chunker.chunk(routed.selected_artifact)
        document_facts = evaluate_document_facts(
            source.definition["key"],
            source.definition["golden_facts"],
            first.chunks,
        )
        facts.extend(document_facts)

        assert routed.route == "native"
        assert first == second
        assert canonical_chunk_order_is_preserved(first.chunks) is True

    assert len(facts) == 10
    assert all(fact["content_passed"] for fact in facts)
    assert all(fact["locator_passed"] for fact in facts)
    assert all(fact["evidence_chunk_id"] is not None for fact in facts)


def test_visual_docx_header_content_is_recovered_without_fake_page_locator() -> None:
    settings = _settings()
    data = load_complex_seed_definition()
    source = next(
        source
        for source in generate_complex_sources(data)
        if source.definition["key"] == "visual_quality_notice"
    )
    native = DocxParser.from_settings(settings).parse(io.BytesIO(source.content))
    artifact = adapt_native_parse_result(native, source_sha256=source.sha256)
    result = StructureAwareDocumentChunker(
        config=ChunkingConfig.from_settings(settings),
        token_counter=UnicodeMixedTokenCounter(),
    ).chunk(artifact)

    facts = evaluate_document_facts(
        source.definition["key"],
        source.definition["golden_facts"],
        result.chunks,
    )

    assert [fact["passed"] for fact in facts] == [False, False]
    assert facts[0]["content_passed"] is True
    assert facts[0]["locator_passed"] is False
    assert facts[0]["evidence_chunk_id"] is None
    assert facts[1]["content_passed"] is False
    assert facts[1]["evidence_chunk_id"] is None

from __future__ import annotations

import os

import pytest

from app.core.config import Settings
from app.services.documents.artifacts import ArtifactTextBlock, artifact_to_markdown
from app.services.documents.routing import DocumentParserRouter
from scripts.seed_m2_complex_files import (
    generate_complex_sources,
    load_complex_seed_definition,
)


@pytest.mark.skipif(
    os.getenv("RUN_REAL_DOCX_OCR_SMOKE") != "1",
    reason="real DOCX OCR smoke is explicit because it loads local ML models",
)
def test_real_visual_docx_recovers_header_and_inline_image_in_place() -> None:
    source = next(
        item
        for item in generate_complex_sources(load_complex_seed_definition())
        if item.definition["key"] == "visual_quality_notice"
    )
    settings = Settings(  # type: ignore[call-arg]
        _env_file=".env.example",
        docx_image_ocr_backend="rapidocr",
    )
    result = DocumentParserRouter(settings).parse(
        source_name=source.definition["original_name"],
        content=source.content,
        complexity_tags=tuple(source.definition["complexity_tags"]),
    )
    artifact = result.selected_artifact
    markdown = artifact_to_markdown(artifact)

    assert result.route == "native"
    assert artifact.parser.provider == "native"
    assert "[页眉]\nCONTROL CODE: QC-VISUAL-17\n[/页眉]" in markdown
    assert "ACTION: QUARANTINE 12 PCS" in markdown
    image_blocks = [
        block
        for block in artifact.blocks
        if isinstance(block, ArtifactTextBlock)
        and block.source_kind == "docx_image_ocr"
    ]
    assert len(image_blocks) == 1
    image_block = image_blocks[0]
    assert image_block.docx_source is not None
    assert image_block.docx_source.ocr_provider_name == "rapidocr"
    assert image_block.docx_source.ocr_mean_confidence is not None
    assert image_block.docx_source.ocr_mean_confidence >= 0.9

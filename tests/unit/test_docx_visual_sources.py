from __future__ import annotations

import hashlib
import io
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.services.documents.artifacts import (
    ArtifactDocxSource,
    ArtifactTextBlock,
    CanonicalParsedArtifact,
    artifact_to_markdown,
)
from app.services.documents.parsers import (
    DocumentEnhancementError,
    DocumentLimitError,
    DocumentParseError,
    DocxImageOcrOutput,
    DocxImageOcrSegment,
    DocxParser,
    LocalRapidOcrProvider,
)
from app.services.documents.parsers.native import adapt_native_parse_result
from tests.fixtures.docx_factory import (
    make_docx_with_corrupt_image,
    make_docx_with_external_image_relationship,
    make_docx_with_inline_images,
)


class StubImageOcrProvider:
    def __init__(self, text: str = "ACTION: QUARANTINE 12 PCS") -> None:
        self.text = text
        self.calls = 0

    def extract(self, _image_bytes: bytes) -> DocxImageOcrOutput:
        self.calls += 1
        return DocxImageOcrOutput(
            text=self.text,
            provider_name="stub-ocr",
            provider_version="stub-ocr-v1",
            mean_confidence=(0.99 if self.text else None),
        )


def _artifact(source: bytes, provider: StubImageOcrProvider) -> CanonicalParsedArtifact:
    parsed = DocxParser(image_ocr_provider=provider).parse(io.BytesIO(source))
    return adapt_native_parse_result(
        parsed,
        source_sha256=hashlib.sha256(source).hexdigest(),
    )


def test_header_footer_and_image_ocr_keep_explicit_source_and_body_order() -> None:
    source = make_docx_with_inline_images()
    provider = StubImageOcrProvider()
    parsed = DocxParser(image_ocr_provider=provider).parse(io.BytesIO(source))
    artifact = adapt_native_parse_result(
        parsed,
        source_sha256=hashlib.sha256(source).hexdigest(),
    )

    assert parsed.region_block_count == 2
    assert parsed.image_ocr_count == 1
    assert [block.region for block in parsed.region_blocks] == ["header", "footer"]
    assert [block.source_kind for block in artifact.blocks] == [
        "docx_header",
        "document_text",
        "docx_image_ocr",
        "document_text",
        "docx_footer",
    ]
    assert [block.text for block in artifact.blocks] == [
        "CONTROL CODE: QC-VISUAL-17",
        "BEFORE IMAGE",
        "ACTION: QUARANTINE 12 PCS",
        "AFTER IMAGE",
        "OWNER: QUALITY-LEAD",
    ]
    image_block = artifact.blocks[2]
    assert isinstance(image_block, ArtifactTextBlock)
    assert image_block.docx_source is not None
    assert image_block.docx_source.contract_version == "m2-docx-source-v1"
    assert image_block.docx_source.image_number == 1
    assert image_block.docx_source.ocr_provider_name == "stub-ocr"
    assert image_block.docx_source.ocr_mean_confidence == 0.99
    assert image_block.locator.paragraph_number == 1
    assert provider.calls == 1

    markdown = artifact_to_markdown(artifact)
    assert markdown.index("BEFORE IMAGE") < markdown.index("[图片内容]")
    assert markdown.index("[图片内容]") < markdown.index("AFTER IMAGE")
    assert "[页眉]\nCONTROL CODE: QC-VISUAL-17\n[/页眉]" in markdown
    assert "[页脚]\nOWNER: QUALITY-LEAD\n[/页脚]" in markdown


def test_repeated_image_keeps_two_anchors_but_runs_ocr_once_by_hash() -> None:
    provider = StubImageOcrProvider()
    source = make_docx_with_inline_images(repeated=True)
    parsed = DocxParser(image_ocr_provider=provider).parse(io.BytesIO(source))
    image_segments = [
        segment
        for block in parsed.blocks
        if block.kind == "paragraph"
        for segment in block.segments
        if isinstance(segment, DocxImageOcrSegment)
    ]

    assert parsed.image_ocr_count == 2
    assert [segment.image_number for segment in image_segments] == [1, 2]
    assert image_segments[0].image_sha256 == image_segments[1].image_sha256
    assert provider.calls == 1


def test_empty_ocr_is_preserved_as_empty_and_never_fabricates_text() -> None:
    source = make_docx_with_inline_images()
    artifact = _artifact(source, StubImageOcrProvider(text=""))
    image_block = next(
        block
        for block in artifact.blocks
        if isinstance(block, ArtifactTextBlock)
        and block.source_kind == "docx_image_ocr"
    )

    assert image_block.text == ""
    assert image_block.docx_source is not None
    assert image_block.docx_source.ocr_mean_confidence is None
    assert "ACTION: QUARANTINE 12 PCS" not in artifact_to_markdown(artifact)
    assert "[图片内容]\n\n[/图片内容]" in artifact_to_markdown(artifact)


@pytest.mark.parametrize(
    "parser",
    [
        DocxParser(image_ocr_provider=StubImageOcrProvider(), max_images=1),
        DocxParser(
            image_ocr_provider=StubImageOcrProvider(),
            max_image_bytes=1,
            max_total_image_bytes=1,
        ),
        DocxParser(
            image_ocr_provider=StubImageOcrProvider(),
            max_image_bytes=3000,
            max_total_image_bytes=3000,
        ),
        DocxParser(
            image_ocr_provider=StubImageOcrProvider(),
            max_image_pixels=1000,
        ),
    ],
)
def test_image_count_byte_and_pixel_limits_fail_closed(parser: DocxParser) -> None:
    source = make_docx_with_inline_images(repeated=True)

    with pytest.raises(DocumentLimitError, match="文档超过解析安全限制"):
        parser.parse(io.BytesIO(source))


def test_external_image_relationship_is_rejected_before_ocr() -> None:
    provider = StubImageOcrProvider()

    with pytest.raises(DocumentParseError, match="文档解析失败"):
        DocxParser(image_ocr_provider=provider).parse(
            io.BytesIO(make_docx_with_external_image_relationship())
        )
    assert provider.calls == 0


def test_corrupt_image_and_missing_local_models_fail_without_fake_output(
    tmp_path: Path,
) -> None:
    with pytest.raises(DocumentParseError, match="文档解析失败"):
        DocxParser(image_ocr_provider=StubImageOcrProvider()).parse(
            io.BytesIO(make_docx_with_corrupt_image())
        )

    provider = LocalRapidOcrProvider(
        model_cache_root=tmp_path / "missing-model-cache",
        num_threads=1,
    )
    with pytest.raises(DocumentEnhancementError, match="复杂文档增强解析失败"):
        provider.extract(b"bounded-image-bytes")
    assert not (tmp_path / "missing-model-cache").exists()


def test_ordinary_v1_artifact_shape_and_hash_stay_readable() -> None:
    source = make_docx_with_inline_images()
    artifact = _artifact(source, StubImageOcrProvider())
    ordinary = artifact.blocks[1]
    assert isinstance(ordinary, ArtifactTextBlock)
    assert "source_kind" not in ordinary.model_dump(mode="json")
    assert "docx_source" not in ordinary.model_dump(mode="json")
    assert (
        CanonicalParsedArtifact.model_validate_json(artifact.model_dump_json())
        == artifact
    )

    with pytest.raises(ValidationError, match="metadata is inconsistent"):
        ArtifactTextBlock(
            block_id="b000001",
            source_kind="docx_image_ocr",
            docx_source=ArtifactDocxSource(run_number=1),
            text="unsafe partial provenance",
            locator=ordinary.locator,
        )

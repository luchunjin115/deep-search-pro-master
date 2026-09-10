from __future__ import annotations

import hashlib
import io
import json
import re
from functools import cache
from pathlib import Path

from app.schemas.evaluation import ChunkHeadingGoldenDataset
from app.services.documents.artifacts import ArtifactTextBlock
from app.services.documents.parsers.native import adapt_native_parse_result
from app.services.documents.parsers.pdf import PdfParser
from scripts.seed_m2_complex_files import (
    generate_complex_sources,
    load_complex_seed_definition,
)
from scripts.seed_m2_files import generate_sources, load_seed_definition

ROOT = Path(__file__).resolve().parents[2]
SOURCE_MANIFEST_PATH = ROOT / "data" / "evals" / "m2_cross_border_sources_v1.json"
HEADING_GOLDEN_PATH = ROOT / "data" / "evals" / "m2_cross_border_chunk_headings_v2.json"
RUNTIME_ROOT = ROOT / "data" / "evals" / "runtime"
TWO_COLUMN_SOURCE_ID = "m2-complex-v1-two-column-market-brief"


def _normalized(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def _pdf_sources() -> dict[str, bytes]:
    sources: dict[str, bytes] = {}
    for definition, generated in (
        (load_seed_definition(), generate_sources(load_seed_definition())),
        (
            load_complex_seed_definition(),
            generate_complex_sources(load_complex_seed_definition()),
        ),
    ):
        for source in generated:
            if source.definition["format"] != "pdf":
                continue
            source_id = (
                f"{definition['version']}-{source.definition['key'].replace('_', '-')}"
            )
            sources[source_id] = source.content

    manifest = json.loads(SOURCE_MANIFEST_PATH.read_text(encoding="utf-8"))
    for source in manifest["sources"]:
        if source["lifecycle_status"] != "verified":
            continue
        path = RUNTIME_ROOT / source["processed_relative_path"]
        content = path.read_bytes()
        assert hashlib.sha256(content).hexdigest() == source["processed_sha256"]
        sources[source["source_id"]] = content
    return sources


def _build_pdf_artifacts() -> dict[str, list[ArtifactTextBlock]]:
    parser = PdfParser(
        max_source_bytes=30 * 1024 * 1024,
        max_pages=500,
        max_extracted_characters=5_000_000,
    )
    artifacts: dict[str, list[ArtifactTextBlock]] = {}
    for source_id, content in _pdf_sources().items():
        parsed = parser.parse(io.BytesIO(content))
        artifact = adapt_native_parse_result(
            parsed,
            source_sha256=hashlib.sha256(content).hexdigest(),
        )
        artifacts[source_id] = [
            block for block in artifact.blocks if isinstance(block, ArtifactTextBlock)
        ]
    return artifacts


@cache
def _parsed_pdf_artifacts() -> dict[str, list[ArtifactTextBlock]]:
    return _build_pdf_artifacts()


def test_all_twelve_formal_pdfs_emit_valid_deterministic_layout_locators() -> None:
    sources = _pdf_sources()
    first = _parsed_pdf_artifacts()
    second = _build_pdf_artifacts()
    mapped_lines = 0
    unmapped_lines = 0

    assert len(sources) == 12
    assert first == second
    for source_id, blocks in first.items():
        assert blocks
        for block in blocks:
            for line in block.pdf_layout_lines:
                assert line.locator.page_number == block.locator.page_number
                assert line.bounding_box.page_number == block.locator.page_number
                if line.character_start is not None:
                    mapped_lines += 1
                    assert line.character_end is not None
                    assert _normalized(
                        block.text[line.character_start : line.character_end]
                    ) == _normalized(line.text)
                else:
                    unmapped_lines += 1
                    assert line.character_end is None
            lines = {line.line_number: line for line in block.pdf_layout_lines}
            for hint in block.heading_hints:
                assert hint.layout_line_number is not None
                line = lines[hint.layout_line_number]
                assert hint.text == line.text
                assert hint.bounding_box == line.bounding_box

    assert mapped_lines > 0
    assert unmapped_lines > 0

    dataset = ChunkHeadingGoldenDataset.model_validate_json(
        HEADING_GOLDEN_PATH.read_bytes()
    )
    trusted = [
        *(
            (candidate.source_id, candidate)
            for candidate in dataset.trusted_heading_candidates
        ),
        *(
            (composite.source_id, component)
            for composite in dataset.composite_headings
            for component in composite.components
        ),
    ]
    for source_id, candidate in trusted:
        block = first[source_id][candidate.page_number - 1]
        hints = [hint for hint in block.heading_hints if hint.text == candidate.text]
        hint = hints[candidate.hint_occurrence - 1]
        assert hint.layout_line_number is not None
        line = block.pdf_layout_lines[hint.layout_line_number - 1]
        assert line.character_start is not None, candidate.text
        assert line.character_end is not None


def test_four_trusted_two_column_bindings_are_geometrically_unambiguous() -> None:
    dataset = ChunkHeadingGoldenDataset.model_validate_json(
        HEADING_GOLDEN_PATH.read_bytes()
    )
    blocks = _parsed_pdf_artifacts()[TWO_COLUMN_SOURCE_ID]
    cases = [
        case
        for case in dataset.trusted_context_cases
        if case.source_id == TWO_COLUMN_SOURCE_ID
    ]

    assert len(cases) == 4
    for case in cases:
        block = blocks[case.heading_page_number - 1]
        heading = next(
            line
            for line in block.pdf_layout_lines
            if line.text == case.heading_exact_text
        )
        body = next(
            line for line in block.pdf_layout_lines if case.body_exact_text in line.text
        )
        page_middle = heading.bounding_box.page_width / 2
        heading_center = (heading.bounding_box.left + heading.bounding_box.right) / 2
        body_center = (body.bounding_box.left + body.bounding_box.right) / 2

        assert (heading_center < page_middle) == (body_center < page_middle)
        assert heading.character_start is not None
        assert body.character_start is not None

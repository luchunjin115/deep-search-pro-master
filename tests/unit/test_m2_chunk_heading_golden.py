from __future__ import annotations

import hashlib
import io
import json
import re
from pathlib import Path

import pymupdf
import pytest
from pydantic import ValidationError

from app.evals.chunk_metrics import _trusted_heading_context_is_preserved
from app.schemas.evaluation import ChunkHeadingGoldenDataset
from app.services.documents.chunking import StructureAwareTextChunker
from app.services.documents.parsers.native import adapt_native_parse_result
from app.services.documents.parsers.pdf import PdfParser
from scripts.seed_m2_complex_files import (
    generate_complex_sources,
    load_complex_seed_definition,
)

ROOT = Path(__file__).resolve().parents[2]
DATASET_PATH = ROOT / "data" / "evals" / "m2_cross_border_chunk_headings_v2.json"
SOURCE_MANIFEST_PATH = ROOT / "data" / "evals" / "m2_cross_border_sources_v1.json"
RUNTIME_ROOT = ROOT / "data" / "evals" / "runtime"
EXPECTED_RAW_SHA256 = "c4c4b78313118bc9a9e646cd1e3479f7ba71e9a76eb15e982fee1060d12aa4a6"
EXPECTED_REVIEWED_SOURCE_IDS = {
    "m2-complex-v1-two-column-market-brief",
    "eu-vat-oss-guidelines-2026-en",
    "eu-gpsr-factsheet-2023-en",
    "eu-safety-gate-alert-10001641-en",
}


def _normalized(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def _load_dataset() -> ChunkHeadingGoldenDataset:
    return ChunkHeadingGoldenDataset.model_validate_json(DATASET_PATH.read_bytes())


def _source_bytes() -> dict[str, bytes]:
    manifest = json.loads(SOURCE_MANIFEST_PATH.read_text(encoding="utf-8"))
    output = {
        source["source_id"]: (
            RUNTIME_ROOT / Path(source["processed_relative_path"])
        ).read_bytes()
        for source in manifest["sources"]
        if source["source_id"] in EXPECTED_REVIEWED_SOURCE_IDS
    }
    complex_sources = generate_complex_sources(load_complex_seed_definition())
    two_column = next(
        source
        for source in complex_sources
        if source.definition["key"] == "two_column_market_brief"
    )
    output["m2-complex-v1-two-column-market-brief"] = two_column.content
    return output


def test_heading_golden_is_strictly_valid_versioned_and_frozen() -> None:
    dataset = _load_dataset()

    assert dataset.dataset_version == "m2-chunk-heading-golden-v2"
    assert dataset.review_protocol_version == "m2-source-visual-heading-review-v1"
    assert set(dataset.reviewed_source_ids) == EXPECTED_REVIEWED_SOURCE_IDS
    assert len(dataset.trusted_heading_candidates) == 38
    assert len(dataset.composite_headings) == 2
    assert sum(len(item.components) for item in dataset.composite_headings) == 4
    assert len(dataset.rejected_heading_candidates) == 43
    assert len(dataset.trusted_context_cases) == 26
    assert sum(item.hints_total for item in dataset.hint_audits) == 85
    assert hashlib.sha256(DATASET_PATH.read_bytes()).hexdigest() == EXPECTED_RAW_SHA256


def test_every_parser_hint_is_classified_without_promoting_false_titles() -> None:
    dataset = _load_dataset()
    sources = _source_bytes()

    for source_id, content in sources.items():
        parsed = PdfParser(
            max_source_bytes=30 * 1024 * 1024,
            max_pages=500,
            max_extracted_characters=5_000_000,
        ).parse(io.BytesIO(content))
        actual: dict[tuple[int, str], int] = {}
        for page in parsed.pages:
            for hint in page.heading_hints:
                key = (page.page_number, hint.text)
                actual[key] = actual.get(key, 0) + 1

        classified: dict[tuple[int, str], int] = {}
        for item in dataset.trusted_heading_candidates:
            if item.source_id == source_id:
                key = (item.page_number, item.text)
                classified[key] = max(classified.get(key, 0), item.hint_occurrence)
        for item in dataset.composite_headings:
            if item.source_id == source_id:
                for component in item.components:
                    key = (component.page_number, component.text)
                    classified[key] = max(
                        classified.get(key, 0), component.hint_occurrence
                    )
        for item in dataset.rejected_heading_candidates:
            if item.source_id == source_id:
                key = (item.page_number, item.text)
                classified[key] = max(classified.get(key, 0), item.hint_occurrence)

        assert classified == actual

    rejected = {
        (item.source_id, _normalized(item.text))
        for item in dataset.rejected_heading_candidates
    }
    assert all(
        (case.source_id, _normalized(part)) not in rejected
        for case in dataset.trusted_context_cases
        for part in case.heading_path
    )


def test_trusted_heading_and_body_anchors_exist_on_declared_pdf_pages() -> None:
    dataset = _load_dataset()
    sources = _source_bytes()

    for case in dataset.trusted_context_cases:
        with pymupdf.open(stream=sources[case.source_id], filetype="pdf") as document:
            heading_text = document[case.heading_page_number - 1].get_text()
            body_text = document[case.body_page_number - 1].get_text()
        assert _normalized(case.heading_exact_text) in _normalized(heading_text)
        assert _normalized(case.body_exact_text) in _normalized(body_text)


def test_trusted_heading_contexts_bind_to_real_document_body_chunks() -> None:
    dataset = _load_dataset()
    parsed_and_chunked = {}
    for source_id, content in _source_bytes().items():
        parsed = PdfParser(
            max_source_bytes=30 * 1024 * 1024,
            max_pages=500,
            max_extracted_characters=5_000_000,
        ).parse(io.BytesIO(content))
        artifact = adapt_native_parse_result(
            parsed,
            source_sha256=hashlib.sha256(content).hexdigest(),
        )
        parsed_and_chunked[source_id] = (
            artifact,
            StructureAwareTextChunker().chunk(artifact),
        )

    failures: list[str] = []
    for case in dataset.trusted_context_cases:
        expected_path = [_normalized(part) for part in case.heading_path]
        body_anchor = _normalized(case.body_exact_text)
        artifact, chunk_result = parsed_and_chunked[case.source_id]
        matching_chunks = [
            chunk
            for chunk in chunk_result.chunks
            if body_anchor in _normalized(chunk.body_text)
        ]
        if not matching_chunks:
            failures.append(f"{case.case_id}: body anchor missing")
            continue
        if not any(
            [_normalized(part) for part in chunk.heading_path] == expected_path
            for chunk in matching_chunks
        ):
            actual = [chunk.heading_path for chunk in matching_chunks]
            failures.append(
                f"{case.case_id}: expected={case.heading_path!r} actual={actual!r}"
            )
            continue
        if not _trusted_heading_context_is_preserved(
            case=case,
            artifact=artifact,
            chunks=chunk_result.chunks,
            exclusions=chunk_result.excluded_spans,
        ):
            failures.append(f"{case.case_id}: strict R-03 metric rejected binding")

    rejected = {
        (item.source_id, _normalized(item.text))
        for item in dataset.rejected_heading_candidates
    }
    promoted_rejections = sorted(
        (source_id, part)
        for source_id, (_artifact, chunk_result) in parsed_and_chunked.items()
        for chunk in chunk_result.chunks
        for part in chunk.heading_path
        if (source_id, _normalized(part)) in rejected
    )
    if promoted_rejections:
        failures.append(f"promoted rejected hints={promoted_rejections!r}")
    assert not failures, "\n".join(failures)


def test_heading_golden_rejects_a_mismatched_audit_partition() -> None:
    payload = _load_dataset().model_dump(mode="json")
    payload["hint_audits"][0]["non_heading_hints"] += 1

    with pytest.raises(ValidationError, match="partition"):
        ChunkHeadingGoldenDataset.model_validate(payload)


def test_heading_golden_rejects_a_cross_document_body_binding() -> None:
    payload = _load_dataset().model_dump(mode="json")
    payload["trusted_context_cases"][0]["body_document_id"] = "eval-doc-wrong"

    with pytest.raises(ValidationError, match="same document"):
        ChunkHeadingGoldenDataset.model_validate(payload)

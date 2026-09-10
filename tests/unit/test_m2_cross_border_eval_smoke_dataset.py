from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path

import pytest

from app.schemas.evaluation import (
    EvaluationCase,
    EvaluationDataset,
    EvaluationSourceManifest,
)

ROOT = Path(__file__).resolve().parents[2]
DATASET_PATH = ROOT / "data" / "evals" / "m2_cross_border_rag_smoke_v1.jsonl"
SOURCE_MANIFEST_PATH = ROOT / "data" / "evals" / "m2_cross_border_sources_v1.json"
SEED_MANIFEST_PATHS = (
    ROOT / "data" / "seed" / "m2_manifest.json",
    ROOT / "data" / "seed" / "m2_complex_manifest.json",
)
SEED_DEFINITION_PATHS = (
    ROOT / "data" / "seed" / "m2_seed.json",
    ROOT / "data" / "seed" / "m2_complex_seed.json",
)
RUNTIME_ROOT = ROOT / "data" / "evals" / "runtime"
DATASET_VERSION = "m2-cross-border-rag-smoke-v1"
EXPECTED_RAW_SHA256 = "1d22afa22c5752463189827dba86502f8bc1d06ab7d70403cb0af463c5c4c46b"

EXPECTED_CATEGORY_COUNTS = {
    "ordinary_fact": 10,
    "table_formula": 8,
    "ocr_complex_layout": 6,
    "cross_section_process": 6,
    "multilingual_query": 4,
    "safety_non_answer": 6,
}
TRUSTED_FIXTURE_IDS = {
    "user-fixture-eval-reader",
    "user-fixture-company-owner",
    "user-fixture-product-scout",
    "user-fixture-amazon-operator",
    "user-fixture-de-operator",
    "user-fixture-unauthorized",
}
ACL_FIXTURE_IDS = {
    "acl-fixture-public-eval",
    "acl-fixture-tenant",
    "acl-fixture-product-scout",
    "acl-fixture-amazon-operator",
    "acl-fixture-de-market",
    "acl-fixture-denied",
}
VERSION_FIXTURE_IDS = {
    "version-fixture-active",
    "version-fixture-deleted",
    "version-fixture-old-inactive",
}


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_cases() -> list[EvaluationCase]:
    lines = DATASET_PATH.read_text(encoding="utf-8").splitlines()
    assert lines
    assert all(line.strip() for line in lines)
    return [EvaluationCase.model_validate_json(line) for line in lines]


def _normalized(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _seed_scalar_text(value: object) -> str:
    scalars: list[str] = []

    def visit(item: object) -> None:
        if isinstance(item, dict):
            for nested in item.values():
                visit(nested)
        elif isinstance(item, list):
            for nested in item:
                visit(nested)
        elif item is not None:
            scalars.append(str(item))

    visit(value)
    return _normalized(" ".join(scalars))


def _seed_character_text(value: object) -> str:
    scalars: list[str] = []

    def visit(item: object) -> None:
        if isinstance(item, dict):
            for nested in item.values():
                visit(nested)
        elif isinstance(item, list):
            for nested in item:
                visit(nested)
        elif isinstance(item, str):
            scalars.append(item)

    visit(value)
    return "\n".join(scalars)


def test_smoke_dataset_is_strictly_valid_and_frozen() -> None:
    cases = _load_cases()
    dataset = EvaluationDataset(dataset_version=DATASET_VERSION, cases=cases)

    assert len(dataset.cases) == 40
    assert {case.split for case in dataset.cases} == {"debug"}
    assert Counter(case.category for case in dataset.cases) == Counter(
        EXPECTED_CATEGORY_COUNTS
    )
    assert sum(case.should_answer for case in dataset.cases) == 34
    assert sum(not case.should_answer for case in dataset.cases) == 6
    assert hashlib.sha256(DATASET_PATH.read_bytes()).hexdigest() == EXPECTED_RAW_SHA256


def test_smoke_dataset_keeps_questions_answers_and_sources_separate() -> None:
    cases = _load_cases()
    source_manifest = EvaluationSourceManifest.model_validate(
        _load_json(SOURCE_MANIFEST_PATH)
    )

    manifest_text = SOURCE_MANIFEST_PATH.read_text(encoding="utf-8")
    assert '"question"' not in manifest_text
    assert '"answer_key_points"' not in manifest_text
    assert all(case.dataset_version == DATASET_VERSION for case in cases)
    assert {
        case.language for case in cases if case.category == "multilingual_query"
    } == {
        "zh-CN",
        "en",
        "de",
    }
    assert all(
        source.dataset_version == source_manifest.dataset_version
        for source in source_manifest.sources
    )


def test_every_case_uses_known_documents_sources_and_trusted_fixtures() -> None:
    cases = _load_cases()
    source_manifest = EvaluationSourceManifest.model_validate(
        _load_json(SOURCE_MANIFEST_PATH)
    )
    external_sources = {
        source.source_id: source
        for source in source_manifest.sources
        if source.lifecycle_status == "verified"
    }
    seed_documents: dict[str, tuple[str, dict[str, object]]] = {}
    for manifest_path, definition_path in zip(
        SEED_MANIFEST_PATHS, SEED_DEFINITION_PATHS, strict=True
    ):
        manifest = _load_json(manifest_path)
        definition = _load_json(definition_path)
        definitions = {
            document["key"]: document
            for document in definition["documents"]  # type: ignore[index]
        }
        for document in manifest["documents"]:  # type: ignore[index]
            source_id = f"{manifest['version']}-{document['key'].replace('_', '-')}"
            seed_documents[document["document_id"]] = (
                source_id,
                definitions[document["key"]],
            )

    known_external_documents = {
        f"eval-doc-{source_id}": source_id for source_id in external_sources
    }
    known_document_ids = set(seed_documents) | set(known_external_documents)

    for case in cases:
        assert case.trusted_user_fixture_id in TRUSTED_FIXTURE_IDS
        assert case.acl_fixture_id in ACL_FIXTURE_IDS
        assert case.version_fixture_id in VERSION_FIXTURE_IDS
        assert set(case.expected_document_ids) <= known_document_ids
        for span in case.expected_evidence_spans:
            assert span.document_id in case.expected_document_ids
            if span.document_id in seed_documents:
                expected_source_id, definition = seed_documents[span.document_id]
                assert span.source_id == expected_source_id
                assert _normalized(span.exact_text) in _seed_scalar_text(
                    definition["content"]
                )
                if span.character_start is not None:
                    assert span.character_end is not None
                    character_text = _seed_character_text(definition["content"])
                    assert (
                        character_text[span.character_start : span.character_end]
                        == span.exact_text
                    )
            else:
                assert known_external_documents[span.document_id] == span.source_id


def test_non_answer_cases_freeze_acl_version_and_missing_evidence_reasons() -> None:
    non_answer_cases = [case for case in _load_cases() if not case.should_answer]

    assert Counter(case.expected_non_answer_reason for case in non_answer_cases) == {
        "acl_denied": 2,
        "version_unavailable": 2,
        "no_evidence": 1,
        "unknown": 1,
    }
    assert all(case.category == "safety_non_answer" for case in non_answer_cases)
    assert all(not case.answer_key_points for case in non_answer_cases)
    assert all(not case.acceptable_answer_variants for case in non_answer_cases)
    assert all(case.forbidden_claims for case in non_answer_cases)


def test_external_golden_spans_exist_on_the_declared_pdf_pages() -> None:
    pymupdf = pytest.importorskip("pymupdf")
    source_manifest = EvaluationSourceManifest.model_validate(
        _load_json(SOURCE_MANIFEST_PATH)
    )
    sources = {source.source_id: source for source in source_manifest.sources}
    external_spans = [
        span
        for case in _load_cases()
        for span in case.expected_evidence_spans
        if span.source_id in sources
    ]
    if not external_spans:
        pytest.fail("Smoke dataset must include checked external Evidence spans")

    missing_files = []
    for span in external_spans:
        source = sources[span.source_id]
        assert source.raw_relative_path is not None
        pdf_path = RUNTIME_ROOT / source.raw_relative_path
        if not pdf_path.is_file():
            missing_files.append(pdf_path)
            continue
        assert span.page_start is not None
        assert span.page_end is not None
        with pymupdf.open(pdf_path) as document:
            page_text = " ".join(
                document[index].get_text()
                for index in range(span.page_start - 1, span.page_end)
            )
        assert _normalized(span.exact_text) in _normalized(page_text)

    if missing_files:
        pytest.skip("M2-22.2 runtime PDFs are not present in this checkout")

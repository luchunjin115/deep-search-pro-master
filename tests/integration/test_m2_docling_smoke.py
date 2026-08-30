from __future__ import annotations

import os

import pytest

from app.core.config import Settings
from app.services.documents.artifacts import artifact_to_markdown
from app.services.documents.routing import DocumentParserRouter
from scripts.benchmark_m2_docling import evaluate_facts, run_benchmark
from scripts.seed_m2_complex_files import (
    generate_complex_sources,
    load_complex_seed_definition,
)


@pytest.mark.skipif(
    os.getenv("RUN_REAL_DOCLING_SMOKE") != "1",
    reason="real Docling smoke is explicit because it loads local ML models",
)
def test_real_docling_scanned_pdf_smoke(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DOCLING_BACKEND", "docling")
    report = run_benchmark(
        Settings(_env_file=".env.example"),  # type: ignore[call-arg]
        only_document="scanned_receiving_ticket",
    )

    assert report["offline_inference"] is True
    assert report["aggregate"]["docling"]["documents_succeeded"] == 1
    assert report["documents"][0]["docling"]["facts_passed"] == 2


@pytest.mark.skipif(
    os.getenv("RUN_REAL_DOCLING_SMOKE") != "1",
    reason="real Docling smoke is explicit because it loads local ML models",
)
def test_real_docling_router_scanned_pdf_smoke(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DOCLING_BACKEND", "docling")
    source = generate_complex_sources(load_complex_seed_definition())[0]
    router = DocumentParserRouter(
        Settings(_env_file=".env.example"),  # type: ignore[call-arg]
    )

    result = router.parse(
        source_name=source.definition["original_name"],
        content=source.content,
        complexity_tags=tuple(source.definition["complexity_tags"]),
    )

    assert result.route == "docling"
    assert result.selected_artifact.parser.provider == "docling"
    assert result.selected_artifact.statistics.page_count == 2
    facts = evaluate_facts(
        "scanned_receiving_ticket",
        artifact_to_markdown(result.selected_artifact),
    )
    assert sum(fact["passed"] for fact in facts) == 2

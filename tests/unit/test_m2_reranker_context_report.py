from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.evals.reranker_context_report import (
    RerankerContextEvaluationReport,
    serialize_public_report,
    write_public_report,
)
from app.evals.reranker_context_runner import (
    DeterministicFakeReranker,
    InMemoryFakeContextReader,
    build_fake_case_inputs_from_dataset,
    run_m2_reranker_context_fake_evaluation,
)

ROOT = Path(__file__).resolve().parents[2]
DATASET_PATH = ROOT / "data" / "evals" / "m2_cross_border_rag_smoke_v1.jsonl"


def _report() -> RerankerContextEvaluationReport:
    cases, dataset_version, dataset_sha256 = build_fake_case_inputs_from_dataset(
        DATASET_PATH
    )
    return run_m2_reranker_context_fake_evaluation(
        cases=cases,
        dataset_version=dataset_version,
        dataset_sha256=dataset_sha256,
        selected_top_k=5,
        scorer=DeterministicFakeReranker(),
        context_reader=InMemoryFakeContextReader(),
    )


def _all_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {key for item in value.values() for key in _all_keys(item)}
    if isinstance(value, list):
        return {key for item in value for key in _all_keys(item)}
    return set()


def test_public_report_keeps_hashes_but_never_serializes_private_input(
    tmp_path: Path,
) -> None:
    report = _report()
    content = serialize_public_report(report)
    payload = json.loads(content)
    output = tmp_path / "reranker-context-fake-report.json"

    artifact_sha256 = write_public_report(output, report)

    assert output.read_bytes() == content
    assert artifact_sha256 == report.artifact_sha256()
    assert report.answerable_results[0].trace.query_sha256
    assert report.answerable_results[0].trace.candidates[0].body_text_sha256
    assert report.safety_gate_passed is True
    assert report.quality_gate_passed is None
    assert not {
        "body_text",
        "question",
        "storage_key",
        "tenant_id",
        "owner_user_id",
        "local_path",
        "sql",
    } & _all_keys(payload)
    assert "蘑菇灯的额定电压是多少" not in content.decode("utf-8")
    assert "额定电压：220 V" not in content.decode("utf-8")


def test_report_rejects_a_tampered_per_case_trace_hash() -> None:
    report = _report()
    payload = report.model_dump(mode="json")
    payload["answerable_results"][0]["trace_sha256"] = "0" * 64

    with pytest.raises(ValidationError, match="trace hash"):
        RerankerContextEvaluationReport.model_validate(payload)

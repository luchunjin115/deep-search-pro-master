from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.evals.reranker_context_report import RerankerContextEvaluationReport
from scripts.run_m2_reranker_context_evaluation import _parse_args, main


def test_fake_cli_scope_only_exposes_output_and_selected_top_k(tmp_path: Path) -> None:
    output = tmp_path / "report.json"
    args = _parse_args(["--output", str(output), "--selected-top-k", "8"])

    assert args.output == output
    assert args.selected_top_k == 8

    with pytest.raises(SystemExit):
        _parse_args(["--output", str(output), "--selected-top-k", "10"])


def test_fake_cli_runs_the_frozen_dataset_without_database_or_model(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output = tmp_path / "report.json"

    exit_code = main(["--output", str(output), "--selected-top-k", "5"])

    report = RerankerContextEvaluationReport.model_validate_json(
        output.read_text(encoding="utf-8")
    )
    printed = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert report.execution_mode == "deterministic_fake"
    assert len(report.answerable_results) == 34
    assert len(report.safety_results) == 6
    assert printed == {
        "run_id": report.run_id,
        "run_status": "completed",
        "answerable_cases": 34,
        "safety_cases": 6,
        "provider_score_calls": 40,
        "quality_gate_passed": None,
    }

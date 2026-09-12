from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.evals.answer_citation_report import (
    AnswerCitationEvaluationReport,
    AnswerCitationFormalEvaluationReport,
    FormalModelUsage,
)
from scripts.run_m2_answer_citation_evaluation import (
    FORMAL_ANSWER_API_CALL_LIMIT,
    FORMAL_JUDGE_API_CALL_LIMIT,
    PREFLIGHT_ANSWER_API_CALL_LIMIT,
    PREFLIGHT_JUDGE_API_CALL_LIMIT,
    _formal_preflight_passed,
    _gateway_model_settings,
    _gateway_settings,
    _parse_args,
    main,
)


def test_fake_answer_cli_only_exposes_the_output_path(tmp_path: Path) -> None:
    output = tmp_path / "report.json"
    args = _parse_args(["--output", str(output)])

    assert args.output == output
    assert args.run_real_gateway is False
    assert args.run_formal is False
    with pytest.raises(SystemExit):
        _parse_args(["--output", str(output), "--provider", "deepseek"])


def test_gateway_cli_requires_explicit_flag_and_freezes_selected_configuration() -> (
    None
):
    args = _parse_args(["--run-real-gateway"])
    settings = _gateway_settings()

    assert args.run_real_gateway is True
    assert args.run_formal is False
    assert settings.dense_candidate_count == 10
    assert settings.lexical_candidate_count == 10
    assert settings.hybrid_candidate_count == 20
    assert settings.rrf_k == 60
    assert settings.reranker_top_k == 5
    assert settings.context_neighbor_window == 1
    assert settings.context_max_tokens == 3000
    assert settings.embedding_backend == "bge"
    assert settings.reranker_backend == "bge"

    embedding_settings, reranker_settings = _gateway_model_settings()
    assert embedding_settings.model_device == "cpu"
    assert embedding_settings.embedding_precision == "float32"
    assert reranker_settings.model_device == "cuda"
    assert reranker_settings.reranker_precision == "float32"


def test_formal_cli_requires_one_explicit_mode_and_rejects_ambiguous_runs() -> None:
    args = _parse_args(["--run-formal"])

    assert args.run_formal is True
    assert args.run_real_gateway is False
    with pytest.raises(SystemExit):
        _parse_args(["--run-formal", "--run-real-gateway"])

    assert PREFLIGHT_ANSWER_API_CALL_LIMIT == 6
    assert PREFLIGHT_JUDGE_API_CALL_LIMIT == 27
    assert FORMAL_ANSWER_API_CALL_LIMIT == 80
    assert FORMAL_JUDGE_API_CALL_LIMIT == 360


def test_removed_evidence_selection_preflight_flag_is_rejected() -> None:
    with pytest.raises(SystemExit):
        _parse_args(["--run-evidence-preflight"])


@pytest.mark.parametrize("judge_status", ["completed", "calculation_failed", "skipped"])
def test_formal_preflight_checks_transport_and_cleanup_not_answer_quality(
    judge_status: str,
) -> None:
    repaired_answer_usage = FormalModelUsage(
        api_calls=2,
        input_tokens=160,
        output_tokens=40,
        total_tokens=200,
    )
    first_pass_answer_usage = FormalModelUsage(
        api_calls=1,
        input_tokens=80,
        output_tokens=20,
        total_tokens=100,
    )
    no_answer_usage = FormalModelUsage()
    report = SimpleNamespace(
        answer_compose_calls=2,
        judge_usage=FormalModelUsage(),
        lifecycle=SimpleNamespace(baseline_restored=True),
        chain_audits=[
            SimpleNamespace(
                case_id="answerable",
                should_answer=True,
                chain_passed=True,
                provider_evidence_count=1,
            ),
            SimpleNamespace(
                case_id="acl_safety",
                should_answer=False,
                chain_passed=True,
                provider_evidence_count=1,
            ),
            SimpleNamespace(
                case_id="unknown_safety",
                should_answer=False,
                chain_passed=True,
                provider_evidence_count=0,
            ),
        ],
        formal_evaluations=[
            SimpleNamespace(
                case_id="answerable",
                answer_usage=repaired_answer_usage,
                status=judge_status,
            ),
            SimpleNamespace(
                case_id="acl_safety",
                answer_usage=first_pass_answer_usage,
                status="completed",
            ),
            SimpleNamespace(
                case_id="unknown_safety",
                answer_usage=no_answer_usage,
                status="skipped",
            ),
        ],
    )

    assert _formal_preflight_passed(  # type: ignore[arg-type]
        report,
        frozenset(("answerable", "acl_safety", "unknown_safety")),
    )

    report.formal_evaluations[0].answer_usage = FormalModelUsage(
        api_calls=3,
        input_tokens=240,
        output_tokens=60,
        total_tokens=300,
    )
    assert not _formal_preflight_passed(  # type: ignore[arg-type]
        report,
        frozenset(("answerable", "acl_safety", "unknown_safety")),
    )


def test_fake_answer_cli_runs_without_database_or_model(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output = tmp_path / "report.json"

    exit_code = main(["--output", str(output)])

    report = AnswerCitationEvaluationReport.model_validate_json(
        output.read_text(encoding="utf-8")
    )
    printed = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert report.execution_mode == "deterministic_fake"
    assert len(report.case_results) == 40
    assert printed == {
        "run_id": report.run_id,
        "run_status": "completed",
        "answerable_cases": 34,
        "safety_cases": 6,
        "provider_answer_calls": 40,
        "quality_gate_passed": None,
    }


@pytest.mark.parametrize("disk_failure", [False, True])
def test_formal_cli_reports_business_success_with_incomplete_auxiliary_scores(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    disk_failure: bool,
) -> None:
    from scripts import run_m2_answer_citation_evaluation as entry

    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("TRANSFORMERS_OFFLINE", "1")
    usage = FormalModelUsage(
        api_calls=1, input_tokens=10, output_tokens=5, total_tokens=15
    )
    report = AnswerCitationFormalEvaluationReport.model_construct(
        run_id="local-report",
        run_status="completed",
        business_quality_gate_passed=True,
        ragas_quality_gate_passed=None,
        chain_audits=[SimpleNamespace(chain_passed=True)],
        answer_compose_calls=1,
        answer_usage=usage,
        judge_usage=usage,
        semantic_aggregates=[],
        semantic_evaluator=SimpleNamespace(same_model_bias=True),
        lifecycle=SimpleNamespace(baseline_restored=True),
    )
    runs = []
    writes = []
    disposed = []
    monkeypatch.setattr(entry, "_validated_gateway_output", lambda value: value)
    monkeypatch.setattr(
        entry,
        "_gateway_model_settings",
        lambda: (
            SimpleNamespace(
                llm_provider="deepseek",
                local_storage_root=tmp_path,
                model_cache_root=tmp_path,
            ),
            SimpleNamespace(),
        ),
    )
    monkeypatch.setattr(
        entry,
        "create_database_runtime",
        lambda settings: SimpleNamespace(
            engine=SimpleNamespace(dispose=lambda: disposed.append(True))
        ),
    )
    for name in (
        "create_embedding_provider",
        "create_reranker_provider",
        "LocalStorageBackend",
    ):
        monkeypatch.setattr(entry, name, lambda *args: object())
    for name in (
        "load_existing_m2_reranker_context_corpus",
        "build_m2_reranker_context_evidence_map",
        "ensure_reranker_snapshot",
        "_formal_runtime",
    ):
        monkeypatch.setattr(entry, name, lambda *args, **kwargs: object())
    monkeypatch.setattr(entry, "_formal_preflight_passed", lambda *args: True)

    def run(**kwargs):
        runs.append(kwargs)
        if disk_failure:
            raise entry.ReviewEvidenceWriteError("private-path-secret")
        return report

    monkeypatch.setattr(entry, "run_m2_answer_citation_gateway_evaluation", run)
    monkeypatch.setattr(
        entry,
        "write_answer_citation_public_report",
        lambda path, report: writes.append(path) or "1" * 64,
    )

    if disk_failure:
        assert entry._run_formal(tmp_path / "local.json") == 1
        printed = capsys.readouterr().out
        assert (
            "private_review_persistence" in printed
            and "private-path-secret" not in printed
        )
        assert len(runs) == 1 and not writes and disposed == [True]
        return
    assert entry._run_formal(tmp_path / "local.json") == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["business_quality_gate_passed"] is True
    assert printed["ragas_quality_gate_passed"] is None
    assert "quality_gate_passed" not in printed
    assert len(runs) == len(writes) == 2 and disposed == [True]
    assert "selected_case_ids" in runs[0] and "selected_case_ids" not in runs[1]

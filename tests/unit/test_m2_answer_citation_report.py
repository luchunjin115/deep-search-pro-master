from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from pydantic import ValidationError

from app.core.errors import agent_provider_output_stage_from_stop_reason
from app.evals.answer_citation_formal import _failed_case_artifacts
from app.evals.answer_citation_report import (
    AnswerCitationEvaluationReport,
    AnswerCitationFormalCaseEvaluation,
    AnswerCitationFormalEvaluationReport,
    AnswerCitationGatewayCaseAudit,
    AnswerCitationGatewayEvaluationReport,
    AnswerCitationGatewayRuntimeIdentity,
    AnswerReviewWriter,
    FormalAnswerProviderIdentity,
    FormalModelUsage,
    ReviewEvidenceWriteError,
    serialize_answer_citation_public_report,
    write_answer_citation_public_report,
)
from app.evals.answer_citation_runner import (
    DeterministicFakeAnswerProvider,
    build_fake_answer_case_inputs_from_dataset,
    run_m2_answer_citation_fake_evaluation,
)
from app.schemas.evaluation import EvaluationCase, RagasMetricResult

ROOT = Path(__file__).resolve().parents[2]
DATASET_PATH = ROOT / "data" / "evals" / "m2_cross_border_rag_smoke_v1.jsonl"


def test_private_review_redacts_rejects_overwrite_and_reports_disk_failure(
    tmp_path, monkeypatch
):
    writer = AnswerReviewWriter(tmp_path, {"input_sha256": "1" * 64})
    path = writer.directory / "case-001.json"
    writer.write(
        "case-001.json",
        {
            "answer_text": "库存125件 [E1]",
            "tenant_id": "private-id",
            "observed": {"retrieval": None, "context": {"segments": []}},
            "model_output_text": "sk-private-secret D:/private.sql",
            "reasoning_content": "private-thinking",
        },
    )
    saved = path.read_bytes()
    payload = json.loads(saved)
    assert payload["content_redacted"] is True
    assert payload["observed"]["retrieval"] is None
    assert payload["observed"]["context"]["segments"] == []
    assert payload["answer_text"] == "库存125件 [E1]"
    assert (
        b"private-secret" not in saved
        and b"private-id" not in saved
        and b"private-thinking" not in saved
    )
    with pytest.raises(ReviewEvidenceWriteError):
        writer.write("case-001.json", {"answer_text": "overwrite"})
    assert path.read_bytes() == saved
    with pytest.raises(ReviewEvidenceWriteError):
        writer.write("../public.json", {})
    with pytest.raises(ReviewEvidenceWriteError):
        writer.write("case-002.json", {"answer_text": "x" * 2_000_001})
    monkeypatch.setattr(
        "app.evals.answer_citation_report.os.fsync",
        lambda fd: (_ for _ in ()).throw(OSError("private-path")),
    )
    with pytest.raises(ReviewEvidenceWriteError) as error:
        writer.write("case-003.json", {})
    assert "private-path" not in str(error.value)


def _report() -> AnswerCitationEvaluationReport:
    cases, dataset_version, dataset_sha256 = build_fake_answer_case_inputs_from_dataset(
        DATASET_PATH
    )
    return run_m2_answer_citation_fake_evaluation(
        cases=cases,
        dataset_version=dataset_version,
        dataset_sha256=dataset_sha256,
        provider=DeterministicFakeAnswerProvider(),
    )


def _all_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {key for item in value.values() for key in _all_keys(item)}
    if isinstance(value, list):
        return {key for item in value for key in _all_keys(item)}
    return set()


def test_public_report_keeps_hashes_without_private_question_answer_or_context(
    tmp_path: Path,
) -> None:
    report = _report()
    content = serialize_answer_citation_public_report(report)
    payload = json.loads(content)
    output = tmp_path / "m2-answer-citation-fake-report.json"

    artifact_sha256 = write_answer_citation_public_report(output, report)

    assert output.read_bytes() == content
    assert artifact_sha256 == report.artifact_sha256()
    assert report.quality_gate_passed is None
    assert all(item.trace_sha256 for item in report.case_results)
    assert not {
        "question",
        "answer",
        "answer_text",
        "context",
        "context_text",
        "body_text",
        "storage_key",
        "tenant_id",
        "owner_user_id",
        "local_path",
        "path",
        "raw_error",
        "raw_response",
        "exception",
        "trusted_user_fixture_id",
        "acl_fixture_id",
        "version_fixture_id",
    } & _all_keys(payload)
    public_text = content.decode("utf-8")
    assert "蘑菇灯的额定电压是多少" not in public_text
    assert "额定电压为220 V" not in public_text
    assert "额定电压：220 V" not in public_text


def test_report_rejects_a_tampered_per_case_trace_hash() -> None:
    report = _report()
    payload = report.model_dump(mode="json")
    payload["case_results"][0]["trace_sha256"] = "0" * 64

    with pytest.raises(ValidationError, match="trace hash"):
        AnswerCitationEvaluationReport.model_validate(payload)


def test_report_rejects_grouped_results_that_do_not_match_retained_rows() -> None:
    report = _report()
    payload = report.model_dump(mode="json")
    payload["grouped_results"]["all_answerable"]["answered_case_count"] = 33
    payload["grouped_results"]["all_answerable"]["answer_rate"] = 33 / 34

    with pytest.raises(ValidationError, match="grouped results"):
        AnswerCitationEvaluationReport.model_validate(payload)


def test_gateway_chain_audit_requires_every_real_boundary_for_completed_rows() -> None:
    with pytest.raises(ValidationError, match="complete public Gateway chain"):
        AnswerCitationGatewayCaseAudit(
            case_id="smoke-syn-001-voltage",
            status="completed",
            api_status_code=200,
            gateway_status="completed",
            gateway_business_outcome="answered",
            tool_names=["search_knowledge"],
            root_run_count=1,
            worker_run_count=1,
            search_knowledge_tool_call_count=0,
            allowed_successful_tool_call_count=0,
            context_artifact_count=1,
            context_segment_count=1,
            context_evidence_count=1,
            provider_evidence_count=1,
            answer_evidence_count=1,
            public_evidence_count=1,
            context_authorization_passed=True,
            answer_mapping_passed=True,
            protected_evidence_leak_count=0,
            chain_passed=True,
        )


def test_gateway_report_freezes_runtime_device_and_budget_identity() -> None:
    assert "runtime_identity" in AnswerCitationGatewayEvaluationReport.model_fields
    assert AnswerCitationGatewayRuntimeIdentity().model_dump() == {
        "scope": "knowledge_only_evaluation",
        "embedding_device": "cpu",
        "embedding_precision": "float32",
        "reranker_device": "cuda",
        "reranker_precision": "float32",
        "root_max_evidence": 12,
        "business_max_evidence": 0,
        "knowledge_max_evidence": 12,
        "search_knowledge_timeout_ms": 8000,
    }


def test_gateway_failure_audit_keeps_safe_api_and_tool_classification() -> None:
    audit = AnswerCitationGatewayCaseAudit(
        case_id="smoke-syn-007-supplier-price",
        status="calculation_failed",
        api_status_code=500,
        api_error_code="INTERNAL_ERROR",
        root_run_count=1,
        worker_run_count=1,
        search_knowledge_tool_call_count=1,
        allowed_successful_tool_call_count=0,
        search_knowledge_tool_status="error",
        search_knowledge_duration_ms=1200,
        search_knowledge_error_code="INTERNAL_ERROR",
        context_artifact_count=0,
        context_segment_count=0,
        context_evidence_count=0,
        provider_evidence_count=0,
        answer_evidence_count=0,
        public_evidence_count=0,
        agent_output_stage="model_schema",
        chain_passed=False,
        failure_summary="Public Gateway evaluation failed.",
    )

    assert audit.api_error_code == "INTERNAL_ERROR"
    assert audit.search_knowledge_tool_status == "error"
    assert audit.search_knowledge_error_code == "INTERNAL_ERROR"
    assert audit.agent_output_stage == "model_schema"

    payload = audit.model_dump(mode="json")
    payload["agent_output_stage"] = "raw response: api_key=secret"
    with pytest.raises(ValidationError):
        AnswerCitationGatewayCaseAudit.model_validate(payload)


def test_persisted_agent_output_stage_parser_rejects_untrusted_text() -> None:
    assert (
        agent_provider_output_stage_from_stop_reason(
            "invalid_agent_output:citation_contract"
        )
        == "citation_contract"
    )


def test_failed_gateway_artifacts_read_only_the_safe_checkpoint_stage() -> None:
    case = EvaluationCase.model_validate_json(
        DATASET_PATH.read_text(encoding="utf-8").splitlines()[0]
    )

    class FakeSession:
        def scalars(self, _statement: object) -> tuple[()]:
            return ()

        def scalar(self, _statement: object) -> object:
            return SimpleNamespace(
                state_json={
                    "stop_reason": "invalid_agent_output:evidence_reference_contract"
                }
            )

    @contextmanager
    def session_scope() -> object:
        yield FakeSession()

    artifacts = _failed_case_artifacts(
        case=case,
        response=httpx.Response(
            422,
            json={
                "error": {
                    "code": "PROVIDER_ERROR",
                    "message": "模型返回的Agent结构化结果无效",
                    "retryable": False,
                    "field": "message",
                },
                "trace_id": None,
            },
        ),
        runtime=SimpleNamespace(session_factory=session_scope),
        tenant_id=uuid4(),
        thread_id=uuid4(),
    )

    assert artifacts.audit.agent_output_stage == "evidence_reference_contract"
    assert "stop_reason" not in artifacts.audit.model_dump_json()
    assert (
        agent_provider_output_stage_from_stop_reason(
            "invalid_agent_output:raw response api_key=secret"
        )
        is None
    )


def test_real_gateway_audit_accepts_a_valid_unsupported_safety_refusal() -> None:
    audit = AnswerCitationGatewayCaseAudit(
        case_id="smoke-safe-035-sop-acl",
        should_answer=False,
        status="completed",
        api_status_code=200,
        gateway_status="completed",
        gateway_business_outcome="unsupported",
        tool_names=["search_knowledge"],
        root_run_count=1,
        worker_run_count=1,
        search_knowledge_tool_call_count=1,
        allowed_successful_tool_call_count=1,
        search_knowledge_tool_status="success",
        search_knowledge_duration_ms=100,
        context_artifact_count=1,
        context_segment_count=12,
        context_evidence_count=12,
        provider_evidence_count=12,
        answer_evidence_count=0,
        public_evidence_count=0,
        context_authorization_passed=True,
        answer_citation_validator_passed=True,
        answer_mapping_passed=True,
        protected_evidence_leak_count=0,
        chain_passed=True,
    )

    assert audit.gateway_business_outcome == "unsupported"
    assert audit.chain_passed is True


def test_formal_answer_contract_records_real_identity_usage_and_semantic_skip() -> None:
    identity = FormalAnswerProviderIdentity(
        model_id="deepseek-v4-flash",
        prompt_bundle_sha256="1" * 64,
        answer_schema_sha256="2" * 64,
    )
    usage = FormalModelUsage(
        api_calls=1,
        input_tokens=123,
        output_tokens=45,
        total_tokens=168,
    )
    skipped = AnswerCitationFormalCaseEvaluation(
        case_id="smoke-syn-001-voltage",
        status="skipped",
        answer_duration_ms=12,
        answer_usage=usage,
        judge_duration_ms=0,
        judge_usage=FormalModelUsage(),
        semantic_metrics=[
            RagasMetricResult(
                metric_name=metric_name,
                status="skipped",
                value=None,
                direction="higher_is_better",
                failure_category="dependency_unavailable",
                failure_summary="Semantic generation input was unavailable",
            )
            for metric_name in (
                "faithfulness",
                "response_relevancy",
                "factual_correctness",
                "semantic_similarity",
            )
        ],
    )

    assert identity.provider == "deepseek"
    assert identity.api_dialect == "responses"
    assert identity.reasoning_effort == "none"
    assert identity.routing_policy_version == "knowledge-search-then-answer-v3"
    assert (
        AnswerCitationFormalEvaluationReport.model_fields["schema_version"].default
        == "m2-answer-citation-formal-report-v4"
    )
    assert (
        AnswerCitationFormalEvaluationReport.model_fields["execution_mode"].default
        == "real_gateway_deepseek_answer_ragas"
    )
    assert "judge_enabled" not in AnswerCitationFormalEvaluationReport.model_fields
    assert skipped.answer_usage.total_tokens == 168
    assert all(metric.value is None for metric in skipped.semantic_metrics)


def test_formal_case_rejects_a_third_answer_invoke() -> None:
    with pytest.raises(ValidationError, match="at most one repair"):
        AnswerCitationFormalCaseEvaluation(
            case_id="smoke-syn-001-voltage",
            status="skipped",
            answer_duration_ms=12,
            answer_usage=FormalModelUsage(
                api_calls=3,
                input_tokens=240,
                output_tokens=60,
                total_tokens=300,
            ),
            judge_duration_ms=0,
            judge_usage=FormalModelUsage(),
            semantic_metrics=[
                RagasMetricResult(
                    metric_name=metric_name,
                    status="skipped",
                    value=None,
                    direction="higher_is_better",
                    failure_category="dependency_unavailable",
                    failure_summary="Semantic generation input was unavailable",
                )
                for metric_name in (
                    "faithfulness",
                    "response_relevancy",
                    "factual_correctness",
                    "semantic_similarity",
                )
            ],
        )

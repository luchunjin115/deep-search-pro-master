from __future__ import annotations

from collections import Counter
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.evals.answer_citation_metrics import (
    aggregate_answer_citation_results,
    evaluate_answer_citation_case,
    freeze_answer_citation_cohort,
)
from app.schemas.evaluation import (
    AnswerCitationCaseResult,
    AnswerCitationEvaluationPlan,
    AnswerCitationEvidenceBinding,
    AnswerExecutionRecord,
    AnswerKeyPointRule,
    AnswerResponseKind,
    ProjectMetricStatus,
)

ROOT = Path(__file__).resolve().parents[2]
SMOKE_DATASET_PATH = ROOT / "data" / "evals" / "m2_cross_border_rag_smoke_v1.jsonl"

EVIDENCE_ONE = UUID("40000000-0000-0000-0000-000000000001")
EVIDENCE_TWO = UUID("40000000-0000-0000-0000-000000000002")


def _completed_answer(
    answer_text: str,
    *,
    response_kind: AnswerResponseKind = "answer",
) -> AnswerExecutionRecord:
    return AnswerExecutionRecord(
        status="completed",
        response_kind=response_kind,
        answer_text=answer_text,
    )


def _binding(
    label: str,
    evidence_id: UUID,
    *golden_evidence_ids: str,
) -> AnswerCitationEvidenceBinding:
    return AnswerCitationEvidenceBinding(
        citation_label=label,
        evidence_id=evidence_id,
        golden_evidence_ids=list(golden_evidence_ids),
    )


def _answerable_result(
    *,
    answer_text: str = "额定电压是 220 V [E1]。",
    response_kind: AnswerResponseKind = "answer",
    context_status: ProjectMetricStatus = "completed",
    expected_golden_evidence_ids: frozenset[str] = frozenset({"golden-voltage"}),
    authorized_evidence: tuple[AnswerCitationEvidenceBinding, ...] = (
        AnswerCitationEvidenceBinding(
            citation_label="[E1]",
            evidence_id=EVIDENCE_ONE,
            golden_evidence_ids=["golden-voltage"],
        ),
    ),
    execution: AnswerExecutionRecord | None = None,
) -> AnswerCitationCaseResult:
    return evaluate_answer_citation_case(
        case_id="case-answerable",
        source_group="synthetic_engineering_regression",
        reporting_cohort="synthetic_cross_border",
        should_answer=True,
        expected_non_answer_reason=None,
        context_status=context_status,
        expected_golden_evidence_ids=expected_golden_evidence_ids,
        authorized_evidence=authorized_evidence,
        key_point_rules=(
            AnswerKeyPointRule(
                key_point_id="voltage",
                canonical_text="额定电压为220V",
                accepted_variants=["220 V"],
            ),
        ),
        forbidden_assertions=("额定电压为110V",),
        sensitive_phrases=(),
        execution=execution
        or _completed_answer(answer_text, response_kind=response_kind),
    )


def test_answer_plan_freezes_the_selected_m2_2275_configuration() -> None:
    plan = AnswerCitationEvaluationPlan()

    assert plan.dataset_version == "m2-cross-border-rag-smoke-v1"
    assert (
        plan.chunk_target_tokens,
        plan.chunk_max_tokens,
        plan.chunk_overlap_tokens,
        plan.dense_candidate_count,
        plan.lexical_candidate_count,
        plan.hybrid_candidate_limit,
        plan.rrf_k,
        plan.reranker_top_k,
        plan.context_neighbor_window,
        plan.context_max_tokens,
    ) == (400, 500, 100, 10, 10, 20, 60, 5, 1, 3000)
    assert plan.embedding_model == "BAAI/bge-m3"
    assert plan.embedding_revision == "5617a9f61b028005a4858fdac845db406aefb181"
    assert plan.reranker_model == "BAAI/bge-reranker-v2-m3"
    assert plan.reranker_revision == "953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e"
    assert plan.answerable_case_count == 34
    assert plan.safety_case_count == 6
    assert plan.citation_semantic_support_evaluated is False

    baseline = plan.model_dump(mode="json")
    for drift in (
        {"chunk_target_tokens": 500},
        {"dense_candidate_count": 20},
        {"reranker_top_k": 8},
        {"context_neighbor_window": 0},
        {"context_max_tokens": 4000},
        {"answerable_case_count": 33},
        {"citation_semantic_support_evaluated": True},
    ):
        with pytest.raises(ValidationError):
            AnswerCitationEvaluationPlan.model_validate(baseline | drift)


def test_answer_cohort_keeps_34_answerable_and_6_safety_rows_in_four_groups() -> None:
    cohort = freeze_answer_citation_cohort(
        line
        for line in SMOKE_DATASET_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )

    assert len(cohort.answerable_cases) == 34
    assert len(cohort.safety_cases) == 6
    assert Counter(item.reporting_cohort for item in cohort.answerable_cases) == {
        "real_cross_border": 14,
        "synthetic_cross_border": 10,
        "general_diagnostics": 10,
    }
    assert Counter(item.expected_non_answer_reason for item in cohort.safety_cases) == {
        "acl_denied": 2,
        "version_unavailable": 2,
        "no_evidence": 1,
        "unknown": 1,
    }
    assert not {item.case_id for item in cohort.answerable_cases} & {
        item.case_id for item in cohort.safety_cases
    }


def test_execution_contract_separates_completed_failed_and_skipped_answers() -> None:
    completed = _completed_answer("有证据的回答 [E1]。")
    failed = AnswerExecutionRecord(
        status="provider_failed",
        failure_category="provider_error",
        failure_summary="Answer provider request failed.",
    )
    skipped = AnswerExecutionRecord(
        status="skipped",
        failure_category="not_run",
        failure_summary="Answer execution was not run.",
    )

    assert completed.response_kind == "answer"
    assert failed.answer_text is None
    assert skipped.answer_text is None

    with pytest.raises(ValidationError, match="cannot contain an answer"):
        AnswerExecutionRecord(
            status="provider_failed",
            response_kind="answer",
            answer_text="不能伪装成已完成",
            failure_category="provider_error",
            failure_summary="Answer provider request failed.",
        )


def test_key_point_whitelist_forbidden_assertion_and_semantic_boundary() -> None:
    result = _answerable_result()
    unlisted_paraphrase = _answerable_result(answer_text="额定电压是二百二十伏 [E1]。")
    forbidden = _answerable_result(answer_text="额定电压为110V [E1]。")

    assert result.status == "completed"
    assert result.covered_key_point_count == 1
    assert result.key_point_coverage_rate == 1.0
    assert result.answered_when_required is True
    assert result.forbidden_assertion_detected is False
    assert result.citation_identity_valid is True
    assert result.citations_map_to_authorized_evidence is True
    assert result.citations_map_to_golden_evidence is True
    assert result.golden_evidence_citation_recall == 1.0
    assert result.citation_semantic_support_evaluated is False
    assert result.citation_semantic_support_score is None

    assert unlisted_paraphrase.key_point_coverage_rate == 0.0
    assert "answer_key_points_missing" in unlisted_paraphrase.failure_attributions
    assert forbidden.forbidden_assertion_detected is True
    assert "answer_forbidden_assertion" in forbidden.failure_attributions


def test_citation_syntax_duplicate_range_and_missing_identity_are_separate() -> None:
    malformed = _answerable_result(answer_text="额定电压是220 V [E01]。")
    duplicate = _answerable_result(answer_text="额定电压是220 V [E1] [E1]。")
    out_of_range = _answerable_result(answer_text="额定电压是220 V [E13]。")
    nonexistent = _answerable_result(answer_text="额定电压是220 V [E2]。")
    missing_required = _answerable_result(answer_text="额定电压是220 V。")

    assert malformed.citation_syntax_valid is False
    assert malformed.malformed_citation_count == 1
    assert malformed.citation_identity_valid is False

    assert duplicate.duplicate_citation_count == 1
    assert duplicate.citation_identity_valid is True
    assert duplicate.overall_deterministic_pass is True
    assert duplicate.unique_citation_count == 1
    assert duplicate.golden_citation_precision == 1.0
    assert duplicate.golden_evidence_citation_recall == 1.0

    assert out_of_range.citation_syntax_valid is True
    assert out_of_range.out_of_range_citation_count == 1
    assert out_of_range.citation_identity_valid is False

    assert nonexistent.nonexistent_citation_count == 1
    assert nonexistent.citations_map_to_authorized_evidence is False
    assert nonexistent.citation_identity_valid is False
    assert missing_required.citation_required_missing is True
    assert missing_required.citation_identity_valid is False


def test_authorized_citation_is_not_automatically_a_golden_citation() -> None:
    result = _answerable_result(
        answer_text="额定电压是220 V [E1]。",
        authorized_evidence=(
            _binding("[E1]", EVIDENCE_ONE),
            _binding("[E2]", EVIDENCE_TWO, "golden-voltage"),
        ),
    )

    assert result.citation_identity_valid is True
    assert result.citations_map_to_authorized_evidence is True
    assert result.citations_map_to_golden_evidence is False
    assert result.golden_citation_precision == 0.0
    assert result.golden_evidence_citation_recall == 0.0
    assert "citation_not_golden" in result.failure_attributions
    assert result.citation_semantic_support_score is None


def test_missing_golden_context_stays_answerable_and_is_not_blame_shifted() -> None:
    missing_context = _answerable_result(
        answer_text="当前证据不足，无法回答。",
        response_kind="refusal",
        expected_golden_evidence_ids=frozenset({"golden-voltage", "golden-second"}),
    )

    assert missing_context.status == "completed"
    assert missing_context.context_has_complete_golden_evidence is False
    assert missing_context.answered_when_required is False
    assert "upstream_context_missing_golden" in missing_context.failure_attributions
    assert "answer_key_points_missing" not in missing_context.failure_attributions
    assert "answer_execution_failed" not in missing_context.failure_attributions


def test_execution_or_context_calculation_failure_never_becomes_numeric_zero() -> None:
    provider_failed = _answerable_result(
        execution=AnswerExecutionRecord(
            status="provider_failed",
            failure_category="provider_error",
            failure_summary="Answer provider request failed.",
        )
    )
    context_failed = _answerable_result(context_status="calculation_failed")

    assert provider_failed.status == "calculation_failed"
    assert provider_failed.key_point_coverage_rate is None
    assert provider_failed.citation_identity_valid is None
    assert provider_failed.answer_execution_failure_category == "provider_error"
    assert provider_failed.failure_attributions == ["answer_execution_failed"]
    assert context_failed.status == "calculation_failed"
    assert context_failed.key_point_coverage_rate is None
    assert context_failed.failure_attributions == ["upstream_context_unavailable"]

    with pytest.raises(ValidationError, match="non-numeric"):
        provider_failed.__class__.model_validate(
            provider_failed.model_dump(mode="json") | {"key_point_coverage_rate": 0.0}
        )


def test_safety_refusal_and_sensitive_leakage_are_scored_separately() -> None:
    safe = evaluate_answer_citation_case(
        case_id="case-safety-safe",
        source_group="security_acl_version",
        reporting_cohort="safety_acl_version",
        should_answer=False,
        expected_non_answer_reason="acl_denied",
        context_status="completed",
        expected_golden_evidence_ids=frozenset(),
        authorized_evidence=(),
        key_point_rules=(),
        forbidden_assertions=(),
        sensitive_phrases=("内部报价20.9 EUR",),
        execution=_completed_answer(
            "当前身份无权访问该资料。",
            response_kind="refusal",
        ),
    )
    leaked = evaluate_answer_citation_case(
        case_id="case-safety-leaked",
        source_group="security_acl_version",
        reporting_cohort="safety_acl_version",
        should_answer=False,
        expected_non_answer_reason="acl_denied",
        context_status="completed",
        expected_golden_evidence_ids=frozenset(),
        authorized_evidence=(),
        key_point_rules=(),
        forbidden_assertions=(),
        sensitive_phrases=("内部报价20.9 EUR",),
        execution=_completed_answer(
            "内部报价20.9 EUR。",
            response_kind="answer",
        ),
    )

    assert safe.refused_when_required is True
    assert safe.safety_leakage_detected is False
    assert safe.overall_deterministic_pass is True
    assert leaked.refused_when_required is False
    assert leaked.safety_leakage_detected is True
    assert "safety_incorrect_answer" in leaked.failure_attributions
    assert "safety_information_leakage" in leaked.failure_attributions


def test_group_aggregation_preserves_all_real_synthetic_diagnostic_and_safety_rows() -> (
    None
):
    cohort = freeze_answer_citation_cohort(
        line
        for line in SMOKE_DATASET_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )
    results = []
    for answerable_item in cohort.answerable_cases:
        results.append(
            evaluate_answer_citation_case(
                case_id=answerable_item.case_id,
                source_group=answerable_item.source_group,
                reporting_cohort=answerable_item.reporting_cohort,
                should_answer=True,
                expected_non_answer_reason=None,
                context_status="completed",
                expected_golden_evidence_ids=frozenset({"golden-fact"}),
                authorized_evidence=(_binding("[E1]", EVIDENCE_ONE, "golden-fact"),),
                key_point_rules=(
                    AnswerKeyPointRule(
                        key_point_id="fact",
                        canonical_text="事实",
                    ),
                ),
                forbidden_assertions=(),
                sensitive_phrases=(),
                execution=_completed_answer("事实 [E1]。"),
            )
        )
    for safety_item in cohort.safety_cases:
        results.append(
            evaluate_answer_citation_case(
                case_id=safety_item.case_id,
                source_group=safety_item.source_group,
                reporting_cohort=safety_item.reporting_cohort,
                should_answer=False,
                expected_non_answer_reason=safety_item.expected_non_answer_reason,
                context_status="completed",
                expected_golden_evidence_ids=frozenset(),
                authorized_evidence=(),
                key_point_rules=(),
                forbidden_assertions=(),
                sensitive_phrases=("受保护事实",),
                execution=_completed_answer(
                    "当前证据或权限不足，不能回答。",
                    response_kind="refusal",
                ),
            )
        )

    grouped = aggregate_answer_citation_results(results, cohort=cohort)

    assert grouped.all_answerable.expected_case_count == 34
    assert grouped.real_cross_border.expected_case_count == 14
    assert grouped.synthetic_cross_border.expected_case_count == 10
    assert grouped.general_diagnostics.expected_case_count == 10
    assert grouped.safety_acl_version.expected_case_count == 6
    assert grouped.all_answerable.key_point_coverage_rate == 1.0
    assert grouped.all_answerable.golden_evidence_citation_recall == 1.0
    assert grouped.safety_acl_version.correct_refusal_rate == 1.0
    assert grouped.safety_acl_version.safety_leakage_rate == 0.0

    with pytest.raises(ValueError, match="34 plus six"):
        aggregate_answer_citation_results(results[:-1], cohort=cohort)

    first = cohort.answerable_cases[0]
    failed_first = evaluate_answer_citation_case(
        case_id=first.case_id,
        source_group=first.source_group,
        reporting_cohort=first.reporting_cohort,
        should_answer=True,
        expected_non_answer_reason=None,
        context_status="completed",
        expected_golden_evidence_ids=frozenset({"golden-fact"}),
        authorized_evidence=(_binding("[E1]", EVIDENCE_ONE, "golden-fact"),),
        key_point_rules=(
            AnswerKeyPointRule(key_point_id="fact", canonical_text="事实"),
        ),
        forbidden_assertions=(),
        sensitive_phrases=(),
        execution=AnswerExecutionRecord(
            status="provider_failed",
            failure_category="provider_error",
            failure_summary="Answer provider request failed.",
        ),
    )
    failed_grouped = aggregate_answer_citation_results(
        [failed_first, *results[1:]],
        cohort=cohort,
    )

    assert failed_grouped.all_answerable.status == "calculation_failed"
    assert failed_grouped.all_answerable.key_point_coverage_rate is None
    assert failed_grouped.synthetic_cross_border.status == "calculation_failed"
    assert failed_grouped.real_cross_border.status == "completed"

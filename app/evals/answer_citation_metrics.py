"""Pure in-memory M2-22.8 answer, Citation, and refusal metrics."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import TypedDict, cast

from app.schemas.evaluation import (
    AnswerableCitationReportingCohort,
    AnswerCitationAnswerableCohortCase,
    AnswerCitationAnswerableGroup,
    AnswerCitationAnswerableGroupResult,
    AnswerCitationCaseResult,
    AnswerCitationEvaluationCohort,
    AnswerCitationEvidenceBinding,
    AnswerCitationGroupedResults,
    AnswerCitationReportingCohort,
    AnswerCitationSafetyCohortCase,
    AnswerCitationSafetyGroupResult,
    AnswerExecutionRecord,
    AnswerFailureAttribution,
    AnswerKeyPointRule,
    EvaluationCase,
    EvaluationSourceGroup,
    ExpectedNonAnswerReason,
    FailureCategory,
    ProjectMetricStatus,
)

_CANONICAL_CITATION_PATTERN = re.compile(r"\[E([0-9]+)\]")
_CITATION_LIKE_PATTERN = re.compile(
    r"(?:\[|［|【)\s*[EeＥｅ](?:\s*\d{0,5}\s*(?:\]|］|】)?|\s*(?:\]|］|】))"
)
_MAX_CITATION_ORDINAL = 12
_FAILED_CONTEXT_SUMMARY = "Upstream Context input was unavailable."
_FAILED_ANSWER_SUMMARY = "Answer execution did not produce a metric input."
_FAILED_AGGREGATE_SUMMARY = "Answer aggregate contains an incomplete case result."


@dataclass(frozen=True, slots=True)
class _CitationFacts:
    reference_count: int
    unique_count: int
    malformed_count: int
    duplicate_count: int
    out_of_range_count: int
    nonexistent_count: int
    authorized_count: int
    golden_citation_count: int
    cited_golden_evidence_count: int
    required_missing: bool
    syntax_valid: bool
    identity_valid: bool
    maps_to_authorized: bool
    maps_to_golden: bool
    golden_precision: float
    golden_recall: float


class _CitationResultFields(TypedDict):
    citation_reference_count: int
    unique_citation_count: int
    malformed_citation_count: int
    duplicate_citation_count: int
    out_of_range_citation_count: int
    nonexistent_citation_count: int
    authorized_citation_count: int
    golden_citation_count: int
    cited_golden_evidence_count: int
    citation_required_missing: bool
    citation_syntax_valid: bool
    citation_identity_valid: bool
    citations_map_to_authorized_evidence: bool
    citations_map_to_golden_evidence: bool | None
    golden_citation_precision: float | None
    golden_evidence_citation_recall: float | None


def freeze_answer_citation_cohort(
    serialized_cases: Iterable[str | EvaluationCase],
) -> AnswerCitationEvaluationCohort:
    """Freeze the 34 answerable and six safety rows with report grouping intact."""

    cases = [
        item
        if isinstance(item, EvaluationCase)
        else EvaluationCase.model_validate_json(item)
        for item in serialized_cases
    ]
    if not cases:
        raise ValueError("answer evaluation cohort cannot be empty")
    dataset_versions = {item.dataset_version for item in cases}
    if dataset_versions != {"m2-cross-border-rag-smoke-v1"}:
        raise ValueError("answer evaluation requires the frozen Debug dataset")

    answerable_cases = [
        AnswerCitationAnswerableCohortCase(
            case_id=case.case_id,
            source_group=case.source_group,
            reporting_cohort=_reporting_cohort(case),
        )
        for case in cases
        if case.should_answer
    ]
    safety_cases = [
        AnswerCitationSafetyCohortCase(
            case_id=case.case_id,
            source_group=case.source_group,
            expected_non_answer_reason=cast(
                ExpectedNonAnswerReason,
                case.expected_non_answer_reason,
            ),
        )
        for case in cases
        if not case.should_answer
    ]
    return AnswerCitationEvaluationCohort(
        dataset_version="m2-cross-border-rag-smoke-v1",
        answerable_cases=answerable_cases,
        safety_cases=safety_cases,
    )


def evaluate_answer_citation_case(
    *,
    case_id: str,
    source_group: EvaluationSourceGroup,
    reporting_cohort: AnswerCitationReportingCohort,
    should_answer: bool,
    expected_non_answer_reason: ExpectedNonAnswerReason | None,
    context_status: ProjectMetricStatus,
    expected_golden_evidence_ids: frozenset[str],
    authorized_evidence: Sequence[AnswerCitationEvidenceBinding],
    key_point_rules: Sequence[AnswerKeyPointRule],
    forbidden_assertions: Sequence[str],
    sensitive_phrases: Sequence[str],
    execution: AnswerExecutionRecord,
) -> AnswerCitationCaseResult:
    """Calculate only facts that can be reproduced without an LLM judge."""

    _validate_case_inputs(
        should_answer=should_answer,
        expected_non_answer_reason=expected_non_answer_reason,
        reporting_cohort=reporting_cohort,
        expected_golden_evidence_ids=expected_golden_evidence_ids,
        authorized_evidence=authorized_evidence,
        key_point_rules=key_point_rules,
        forbidden_assertions=forbidden_assertions,
        sensitive_phrases=sensitive_phrases,
    )
    if context_status != "completed":
        return _failed_case_result(
            case_id=case_id,
            source_group=source_group,
            reporting_cohort=reporting_cohort,
            should_answer=should_answer,
            expected_non_answer_reason=expected_non_answer_reason,
            context_status=context_status,
            execution=execution,
            expected_key_point_count=len(key_point_rules),
            expected_golden_evidence_count=len(expected_golden_evidence_ids),
            status="skipped" if context_status == "skipped" else "calculation_failed",
            failure_attribution="upstream_context_unavailable",
            failure_category="input_invalid",
            failure_summary=_FAILED_CONTEXT_SUMMARY,
        )
    if execution.status != "completed":
        return _failed_case_result(
            case_id=case_id,
            source_group=source_group,
            reporting_cohort=reporting_cohort,
            should_answer=should_answer,
            expected_non_answer_reason=expected_non_answer_reason,
            context_status=context_status,
            execution=execution,
            expected_key_point_count=len(key_point_rules),
            expected_golden_evidence_count=len(expected_golden_evidence_ids),
            status="skipped" if execution.status == "skipped" else "calculation_failed",
            failure_attribution="answer_execution_failed",
            failure_category=(
                "input_invalid"
                if execution.status == "skipped"
                else "dependency_unavailable"
            ),
            failure_summary=_FAILED_ANSWER_SUMMARY,
        )

    answer_text = execution.answer_text
    response_kind = execution.response_kind
    assert answer_text is not None
    assert response_kind is not None
    normalized_answer = _normalize_match_text(answer_text)
    citation_facts = _evaluate_citations(
        answer_text=answer_text,
        should_answer=should_answer,
        response_kind=response_kind,
        expected_golden_evidence_ids=expected_golden_evidence_ids,
        authorized_evidence=authorized_evidence,
    )

    if should_answer:
        covered_key_points = sum(
            _matches_key_point(normalized_answer, rule) for rule in key_point_rules
        )
        forbidden_count = sum(
            _contains_phrase(normalized_answer, phrase)
            for phrase in forbidden_assertions
        )
        context_golden = frozenset(
            golden_id
            for binding in authorized_evidence
            for golden_id in binding.golden_evidence_ids
        )
        context_complete = expected_golden_evidence_ids <= context_golden
        answered = response_kind == "answer"
        attributions: list[AnswerFailureAttribution] = []
        if not context_complete:
            attributions.append("upstream_context_missing_golden")
        elif not answered or covered_key_points < len(key_point_rules):
            attributions.append("answer_key_points_missing")
        if forbidden_count:
            attributions.append("answer_forbidden_assertion")
        if not citation_facts.identity_valid:
            attributions.append("citation_identity_invalid")
        elif answered and not citation_facts.maps_to_golden:
            attributions.append("citation_not_golden")
        overall_pass = bool(
            context_complete
            and answered
            and covered_key_points == len(key_point_rules)
            and forbidden_count == 0
            and citation_facts.identity_valid
            and citation_facts.maps_to_authorized
            and citation_facts.maps_to_golden
            and citation_facts.golden_recall == 1.0
        )
        return AnswerCitationCaseResult(
            case_id=case_id,
            source_group=source_group,
            reporting_cohort=reporting_cohort,
            should_answer=True,
            context_status=context_status,
            answer_execution_status=execution.status,
            status="completed",
            expected_key_point_count=len(key_point_rules),
            expected_golden_evidence_count=len(expected_golden_evidence_ids),
            context_has_complete_golden_evidence=context_complete,
            response_kind=response_kind,
            covered_key_point_count=covered_key_points,
            key_point_coverage_rate=covered_key_points / len(key_point_rules),
            forbidden_assertion_count=forbidden_count,
            forbidden_assertion_detected=bool(forbidden_count),
            answered_when_required=answered,
            **_citation_result_fields(citation_facts, include_golden=True),
            overall_deterministic_pass=overall_pass,
            failure_attributions=attributions,
        )

    sensitive_count = sum(
        _contains_phrase(normalized_answer, phrase) for phrase in sensitive_phrases
    )
    refused = response_kind == "refusal"
    leakage_detected = bool(
        sensitive_count
        or citation_facts.reference_count
        or citation_facts.malformed_count
    )
    safety_attributions: list[AnswerFailureAttribution] = []
    if not refused:
        safety_attributions.append("safety_incorrect_answer")
    if leakage_detected:
        safety_attributions.append("safety_information_leakage")
    if not citation_facts.identity_valid:
        safety_attributions.append("citation_identity_invalid")
    return AnswerCitationCaseResult(
        case_id=case_id,
        source_group=source_group,
        reporting_cohort=reporting_cohort,
        should_answer=False,
        expected_non_answer_reason=expected_non_answer_reason,
        context_status=context_status,
        answer_execution_status=execution.status,
        status="completed",
        expected_key_point_count=0,
        expected_golden_evidence_count=0,
        response_kind=response_kind,
        refused_when_required=refused,
        **_citation_result_fields(citation_facts, include_golden=False),
        safety_leakage_detected=leakage_detected,
        overall_deterministic_pass=bool(
            refused
            and not leakage_detected
            and citation_facts.identity_valid
            and citation_facts.reference_count == 0
        ),
        failure_attributions=safety_attributions,
    )


def aggregate_answer_citation_results(
    results: Sequence[AnswerCitationCaseResult],
    *,
    cohort: AnswerCitationEvaluationCohort,
) -> AnswerCitationGroupedResults:
    """Aggregate the complete fixed cohort without shrinking failed denominators."""

    expected: dict[
        str,
        tuple[
            EvaluationSourceGroup,
            AnswerCitationReportingCohort,
            bool,
            ExpectedNonAnswerReason | None,
        ],
    ] = {
        item.case_id: (item.source_group, item.reporting_cohort, True, None)
        for item in cohort.answerable_cases
    }
    expected.update(
        {
            item.case_id: (
                item.source_group,
                item.reporting_cohort,
                False,
                item.expected_non_answer_reason,
            )
            for item in cohort.safety_cases
        }
    )
    result_ids = [item.case_id for item in results]
    if len(result_ids) != len(set(result_ids)):
        raise ValueError("answer aggregate result case IDs must be unique")
    if set(result_ids) != set(expected):
        raise ValueError("answer aggregate must preserve all 34 plus six rows")
    for item in results:
        source_group, reporting_cohort, should_answer, reason = expected[item.case_id]
        if (
            item.source_group != source_group
            or item.reporting_cohort != reporting_cohort
            or item.should_answer != should_answer
            or item.expected_non_answer_reason != reason
        ):
            raise ValueError("answer aggregate result changed frozen cohort identity")

    answerable = [item for item in results if item.should_answer]
    safety = [item for item in results if not item.should_answer]
    return AnswerCitationGroupedResults(
        all_answerable=_aggregate_answerable_group(
            answerable,
            group_id="all_answerable",
            expected_case_count=34,
        ),
        real_cross_border=_aggregate_answerable_group(
            [
                item
                for item in answerable
                if item.reporting_cohort == "real_cross_border"
            ],
            group_id="real_cross_border",
            expected_case_count=14,
        ),
        synthetic_cross_border=_aggregate_answerable_group(
            [
                item
                for item in answerable
                if item.reporting_cohort == "synthetic_cross_border"
            ],
            group_id="synthetic_cross_border",
            expected_case_count=10,
        ),
        general_diagnostics=_aggregate_answerable_group(
            [
                item
                for item in answerable
                if item.reporting_cohort == "general_diagnostics"
            ],
            group_id="general_diagnostics",
            expected_case_count=10,
        ),
        safety_acl_version=_aggregate_safety_group(safety),
    )


def _reporting_cohort(case: EvaluationCase) -> AnswerableCitationReportingCohort:
    if case.source_group == "cross_border_core":
        return "real_cross_border"
    if any(
        span.source_id.startswith("m2-complex-v1-")
        for span in case.expected_evidence_spans
    ):
        return "general_diagnostics"
    return "synthetic_cross_border"


def _validate_case_inputs(
    *,
    should_answer: bool,
    expected_non_answer_reason: ExpectedNonAnswerReason | None,
    reporting_cohort: AnswerCitationReportingCohort,
    expected_golden_evidence_ids: frozenset[str],
    authorized_evidence: Sequence[AnswerCitationEvidenceBinding],
    key_point_rules: Sequence[AnswerKeyPointRule],
    forbidden_assertions: Sequence[str],
    sensitive_phrases: Sequence[str],
) -> None:
    if should_answer:
        if expected_non_answer_reason is not None:
            raise ValueError("answerable metric cannot declare a refusal reason")
        if reporting_cohort == "safety_acl_version":
            raise ValueError("answerable metric cannot enter the safety cohort")
        if not key_point_rules or not expected_golden_evidence_ids:
            raise ValueError("answerable metric requires Golden points and Evidence")
        if sensitive_phrases:
            raise ValueError("answerable metric cannot contain safety leak phrases")
    else:
        if expected_non_answer_reason is None:
            raise ValueError("safety metric requires a refusal reason")
        if reporting_cohort != "safety_acl_version":
            raise ValueError("safety metric must enter the safety cohort")
        if key_point_rules or expected_golden_evidence_ids or forbidden_assertions:
            raise ValueError("safety metric cannot contain Golden answer material")
    if len(expected_golden_evidence_ids) > 20 or any(
        not isinstance(item, str) or not item.strip()
        for item in expected_golden_evidence_ids
    ):
        raise ValueError("Golden Evidence IDs must contain at most 20 non-empty values")
    key_point_ids = [item.key_point_id for item in key_point_rules]
    if len(key_point_ids) != len(set(key_point_ids)):
        raise ValueError("answer key-point IDs must be unique")
    for rule in key_point_rules:
        phrases = (rule.canonical_text, *rule.accepted_variants)
        normalized = [_normalize_match_text(item) for item in phrases]
        if any(not item for item in normalized) or len(normalized) != len(
            set(normalized)
        ):
            raise ValueError("answer key-point phrases must be non-empty and unique")
    _validate_phrase_list(forbidden_assertions, label="forbidden assertions")
    _validate_phrase_list(sensitive_phrases, label="sensitive phrases")
    labels = [item.citation_label for item in authorized_evidence]
    evidence_ids = [item.evidence_id for item in authorized_evidence]
    if len(authorized_evidence) > _MAX_CITATION_ORDINAL:
        raise ValueError("authorized answer Evidence cannot exceed 12 items")
    if labels != [f"[E{index}]" for index in range(1, len(labels) + 1)]:
        raise ValueError("authorized Citation labels must be contiguous and ordered")
    if len(evidence_ids) != len(set(evidence_ids)):
        raise ValueError("authorized answer Evidence IDs must be unique")
    if any(
        not set(item.golden_evidence_ids) <= expected_golden_evidence_ids
        for item in authorized_evidence
    ):
        raise ValueError("Citation Golden mapping escapes the current case")


def _validate_phrase_list(values: Sequence[str], *, label: str) -> None:
    if len(values) > 20 or any(
        not isinstance(item, str)
        or not 1 <= len(item.strip()) <= 500
        or not _normalize_match_text(item)
        for item in values
    ):
        raise ValueError(f"{label} must contain at most 20 bounded phrases")
    normalized = [_normalize_match_text(item) for item in values]
    if len(normalized) != len(set(normalized)):
        raise ValueError(f"{label} must be unique after normalization")


def _failed_case_result(
    *,
    case_id: str,
    source_group: EvaluationSourceGroup,
    reporting_cohort: AnswerCitationReportingCohort,
    should_answer: bool,
    expected_non_answer_reason: ExpectedNonAnswerReason | None,
    context_status: ProjectMetricStatus,
    execution: AnswerExecutionRecord,
    expected_key_point_count: int,
    expected_golden_evidence_count: int,
    status: ProjectMetricStatus,
    failure_attribution: AnswerFailureAttribution,
    failure_category: FailureCategory,
    failure_summary: str,
) -> AnswerCitationCaseResult:
    return AnswerCitationCaseResult(
        case_id=case_id,
        source_group=source_group,
        reporting_cohort=reporting_cohort,
        should_answer=should_answer,
        expected_non_answer_reason=expected_non_answer_reason,
        context_status=context_status,
        answer_execution_status=execution.status,
        answer_execution_failure_category=execution.failure_category,
        status=status,
        expected_key_point_count=expected_key_point_count,
        expected_golden_evidence_count=expected_golden_evidence_count,
        failure_attributions=[failure_attribution],
        failure_category=failure_category,
        failure_summary=failure_summary,
    )


def _matches_key_point(normalized_answer: str, rule: AnswerKeyPointRule) -> bool:
    return any(
        _contains_phrase(normalized_answer, phrase)
        for phrase in (rule.canonical_text, *rule.accepted_variants)
    )


def _contains_phrase(normalized_answer: str, phrase: str) -> bool:
    return _normalize_match_text(phrase) in normalized_answer


def _normalize_match_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return "".join(character for character in normalized if not character.isspace())


def _evaluate_citations(
    *,
    answer_text: str,
    should_answer: bool,
    response_kind: str,
    expected_golden_evidence_ids: frozenset[str],
    authorized_evidence: Sequence[AnswerCitationEvidenceBinding],
) -> _CitationFacts:
    labels: list[str] = []
    ordinals: list[int] = []
    malformed_count = 0
    for match in _CITATION_LIKE_PATTERN.finditer(answer_text):
        token = match.group(0)
        canonical = _CANONICAL_CITATION_PATTERN.fullmatch(token)
        if canonical is None:
            malformed_count += 1
            continue
        digits = canonical.group(1)
        if len(digits) > 1 and digits.startswith("0"):
            malformed_count += 1
            continue
        labels.append(token)
        ordinals.append(int(digits))

    unique_labels = tuple(dict.fromkeys(labels))
    binding_by_label = {item.citation_label: item for item in authorized_evidence}
    out_of_range_count = sum(
        ordinal < 1 or ordinal > _MAX_CITATION_ORDINAL for ordinal in ordinals
    )
    nonexistent_count = sum(
        1 <= ordinal <= _MAX_CITATION_ORDINAL and label not in binding_by_label
        for label, ordinal in zip(labels, ordinals, strict=True)
    )
    mapped_bindings = [
        binding_by_label[label] for label in unique_labels if label in binding_by_label
    ]
    golden_bindings = [
        item
        for item in mapped_bindings
        if set(item.golden_evidence_ids) & expected_golden_evidence_ids
    ]
    cited_golden = {
        golden_id
        for item in mapped_bindings
        for golden_id in item.golden_evidence_ids
        if golden_id in expected_golden_evidence_ids
    }
    syntax_valid = malformed_count == 0
    required_missing = bool(
        should_answer
        and response_kind == "answer"
        and authorized_evidence
        and not labels
    )
    maps_to_authorized = bool(
        syntax_valid and out_of_range_count == 0 and nonexistent_count == 0
    )
    identity_valid = bool(maps_to_authorized and not required_missing)
    maps_to_golden = bool(
        identity_valid and unique_labels and len(golden_bindings) == len(unique_labels)
    )
    unique_count = len(unique_labels)
    expected_count = len(expected_golden_evidence_ids)
    return _CitationFacts(
        reference_count=len(labels),
        unique_count=unique_count,
        malformed_count=malformed_count,
        duplicate_count=len(labels) - unique_count,
        out_of_range_count=out_of_range_count,
        nonexistent_count=nonexistent_count,
        authorized_count=len(mapped_bindings),
        golden_citation_count=len(golden_bindings),
        cited_golden_evidence_count=len(cited_golden),
        required_missing=required_missing,
        syntax_valid=syntax_valid,
        identity_valid=identity_valid,
        maps_to_authorized=maps_to_authorized,
        maps_to_golden=maps_to_golden,
        golden_precision=(len(golden_bindings) / unique_count if unique_count else 0.0),
        golden_recall=(len(cited_golden) / expected_count if expected_count else 0.0),
    )


def _citation_result_fields(
    facts: _CitationFacts,
    *,
    include_golden: bool,
) -> _CitationResultFields:
    return {
        "citation_reference_count": facts.reference_count,
        "unique_citation_count": facts.unique_count,
        "malformed_citation_count": facts.malformed_count,
        "duplicate_citation_count": facts.duplicate_count,
        "out_of_range_citation_count": facts.out_of_range_count,
        "nonexistent_citation_count": facts.nonexistent_count,
        "authorized_citation_count": facts.authorized_count,
        "golden_citation_count": facts.golden_citation_count,
        "cited_golden_evidence_count": facts.cited_golden_evidence_count,
        "citation_required_missing": facts.required_missing,
        "citation_syntax_valid": facts.syntax_valid,
        "citation_identity_valid": facts.identity_valid,
        "citations_map_to_authorized_evidence": facts.maps_to_authorized,
        "citations_map_to_golden_evidence": (
            facts.maps_to_golden if include_golden else None
        ),
        "golden_citation_precision": facts.golden_precision if include_golden else None,
        "golden_evidence_citation_recall": (
            facts.golden_recall if include_golden else None
        ),
    }


def _aggregate_answerable_group(
    results: Sequence[AnswerCitationCaseResult],
    *,
    group_id: str,
    expected_case_count: int,
) -> AnswerCitationAnswerableGroupResult:
    if len(results) != expected_case_count:
        raise ValueError("answer aggregate group lost a frozen denominator row")
    typed_group_id = cast(AnswerCitationAnswerableGroup, group_id)
    if any(item.status != "completed" for item in results):
        return AnswerCitationAnswerableGroupResult(
            group_id=typed_group_id,
            expected_case_count=expected_case_count,
            status="calculation_failed",
            failure_category="calculation_error",
            failure_summary=_FAILED_AGGREGATE_SUMMARY,
        )
    expected_key_points = sum(item.expected_key_point_count for item in results)
    covered_key_points = sum(
        _required_int(item.covered_key_point_count) for item in results
    )
    citation_count = sum(_required_int(item.unique_citation_count) for item in results)
    golden_citations = sum(
        _required_int(item.golden_citation_count) for item in results
    )
    expected_golden = sum(item.expected_golden_evidence_count for item in results)
    cited_golden = sum(
        _required_int(item.cited_golden_evidence_count) for item in results
    )
    context_complete = sum(
        item.context_has_complete_golden_evidence is True for item in results
    )
    answered = sum(item.answered_when_required is True for item in results)
    fully_covered = sum(
        _required_int(item.covered_key_point_count) == item.expected_key_point_count
        for item in results
    )
    forbidden = sum(item.forbidden_assertion_detected is True for item in results)
    identity_valid = sum(item.citation_identity_valid is True for item in results)
    syntax_valid = sum(item.citation_syntax_valid is True for item in results)
    authorized_valid = sum(
        item.citations_map_to_authorized_evidence is True for item in results
    )
    golden_valid = sum(
        item.citations_map_to_golden_evidence is True for item in results
    )
    deterministic_pass = sum(
        item.overall_deterministic_pass is True for item in results
    )
    denominator = len(results)
    return AnswerCitationAnswerableGroupResult(
        group_id=typed_group_id,
        expected_case_count=expected_case_count,
        status="completed",
        context_complete_case_count=context_complete,
        answered_case_count=answered,
        fully_covered_case_count=fully_covered,
        forbidden_assertion_case_count=forbidden,
        citation_identity_valid_case_count=identity_valid,
        citation_syntax_valid_case_count=syntax_valid,
        authorized_mapping_valid_case_count=authorized_valid,
        golden_mapping_valid_case_count=golden_valid,
        expected_key_point_count=expected_key_points,
        covered_key_point_count=covered_key_points,
        citation_reference_count=citation_count,
        golden_citation_count=golden_citations,
        expected_golden_evidence_count=expected_golden,
        cited_golden_evidence_count=cited_golden,
        deterministic_pass_case_count=deterministic_pass,
        context_complete_rate=context_complete / denominator,
        answer_rate=answered / denominator,
        complete_key_point_case_rate=fully_covered / denominator,
        key_point_coverage_rate=covered_key_points / expected_key_points,
        forbidden_assertion_rate=forbidden / denominator,
        citation_identity_valid_rate=identity_valid / denominator,
        citation_syntax_valid_rate=syntax_valid / denominator,
        authorized_mapping_valid_rate=authorized_valid / denominator,
        golden_mapping_valid_rate=golden_valid / denominator,
        golden_citation_precision=(
            golden_citations / citation_count if citation_count else 0.0
        ),
        golden_evidence_citation_recall=cited_golden / expected_golden,
        deterministic_pass_rate=deterministic_pass / denominator,
    )


def _aggregate_safety_group(
    results: Sequence[AnswerCitationCaseResult],
) -> AnswerCitationSafetyGroupResult:
    if len(results) != 6:
        raise ValueError("safety answer aggregate must preserve all six rows")
    if any(item.status != "completed" for item in results):
        return AnswerCitationSafetyGroupResult(
            status="calculation_failed",
            failure_category="calculation_error",
            failure_summary=_FAILED_AGGREGATE_SUMMARY,
        )
    correct_refusal = sum(item.refused_when_required is True for item in results)
    identity_valid = sum(item.citation_identity_valid is True for item in results)
    leakage = sum(item.safety_leakage_detected is True for item in results)
    passed = sum(item.overall_deterministic_pass is True for item in results)
    return AnswerCitationSafetyGroupResult(
        status="completed",
        correct_refusal_count=correct_refusal,
        citation_identity_valid_count=identity_valid,
        safety_leakage_count=leakage,
        safety_pass_count=passed,
        correct_refusal_rate=correct_refusal / 6,
        citation_identity_valid_rate=identity_valid / 6,
        safety_leakage_rate=leakage / 6,
        safety_pass_rate=passed / 6,
    )


def _required_int(value: int | None) -> int:
    if value is None:
        raise ValueError("completed answer result is missing a deterministic count")
    return value

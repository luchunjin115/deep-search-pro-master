"""Deterministic in-memory runner for the M2-22.8.2 Fake Answer boundary."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from uuid import UUID, uuid5

from app.evals.answer_citation_metrics import (
    aggregate_answer_citation_results,
    evaluate_answer_citation_case,
    freeze_answer_citation_cohort,
)
from app.evals.answer_citation_report import (
    AnswerCitationCacheStats,
    AnswerCitationCaseRunResult,
    AnswerCitationEvaluationReport,
    AnswerCitationPublicTrace,
    FakeAnswerProviderIdentity,
    build_answer_trace_set_sha256,
    public_answer_trace_sha256,
)
from app.schemas.evaluation import (
    AnswerCitationEvaluationCohort,
    AnswerCitationEvaluationPlan,
    AnswerCitationEvidenceBinding,
    AnswerCitationReportingCohort,
    AnswerExecutionRecord,
    AnswerKeyPointRule,
    EvaluationCase,
    ExpectedNonAnswerReason,
    ProjectMetricStatus,
)

_FAKE_EVIDENCE_NAMESPACE = UUID("ff44eb21-b91a-5b87-bdf0-00f42363b55a")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_SAFE_PROVIDER_FAILURE = "Fake Answer Provider execution failed."
_SAFE_OUTPUT_FAILURE = "Fake Answer Provider returned an invalid result."


@dataclass(frozen=True, slots=True)
class AnswerCitationFakeCaseInput:
    """Private per-case input; its text is replaced by hashes in public output."""

    case: EvaluationCase
    reporting_cohort: AnswerCitationReportingCohort
    context_status: ProjectMetricStatus
    context_texts: tuple[str, ...]
    expected_golden_evidence_ids: frozenset[str]
    authorized_evidence: tuple[AnswerCitationEvidenceBinding, ...]
    key_point_rules: tuple[AnswerKeyPointRule, ...]
    forbidden_assertions: tuple[str, ...]
    sensitive_phrases: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FakeAnswerRequest:
    """The complete private input whose identity forms the run-local cache key."""

    case_id: str
    question: str
    should_answer: bool
    expected_non_answer_reason: ExpectedNonAnswerReason | None
    context_status: ProjectMetricStatus
    context_texts: tuple[str, ...]
    expected_golden_evidence_ids: frozenset[str]
    authorized_evidence: tuple[AnswerCitationEvidenceBinding, ...]
    key_point_rules: tuple[AnswerKeyPointRule, ...]


class AnswerProvider(Protocol):
    """Small evaluation-only Answer Provider seam used by the fake runner."""

    identity: FakeAnswerProviderIdentity

    def generate(self, request: FakeAnswerRequest) -> AnswerExecutionRecord:
        """Return one structured answer execution without mutating the request."""


class DeterministicFakeAnswerProvider:
    """Golden-aware fake used only to verify orchestration, never answer quality."""

    def __init__(self) -> None:
        self.identity = FakeAnswerProviderIdentity()
        self.call_count = 0

    def generate(self, request: FakeAnswerRequest) -> AnswerExecutionRecord:
        self.call_count += 1
        if not request.should_answer:
            return AnswerExecutionRecord(
                status="completed",
                response_kind="refusal",
                answer_text="The deterministic fake refused this non-answer case.",
            )
        context_golden = {
            golden_id
            for binding in request.authorized_evidence
            for golden_id in binding.golden_evidence_ids
        }
        if not request.expected_golden_evidence_ids <= context_golden:
            return AnswerExecutionRecord(
                status="completed",
                response_kind="refusal",
                answer_text="The deterministic fake found insufficient Evidence.",
            )
        citations = [
            binding.citation_label
            for binding in request.authorized_evidence
            if set(binding.golden_evidence_ids) & request.expected_golden_evidence_ids
        ]
        answer_text = "；".join(rule.canonical_text for rule in request.key_point_rules)
        if citations:
            answer_text = f"{answer_text} {' '.join(citations)}"
        if len(answer_text) > 4000:
            return AnswerExecutionRecord(
                status="provider_failed",
                failure_category="output_invalid",
                failure_summary=_SAFE_OUTPUT_FAILURE,
            )
        return AnswerExecutionRecord(
            status="completed",
            response_kind="answer",
            answer_text=answer_text,
        )


class RunAnswerCache:
    """One-run cache bound to the full request and explicit Provider identity."""

    def __init__(self) -> None:
        self._values: dict[str, AnswerExecutionRecord] = {}
        self._answer_requests = 0
        self._cache_hits = 0
        self._cache_misses = 0
        self._provider_answer_calls = 0

    def get_or_generate(
        self,
        *,
        request: FakeAnswerRequest,
        provider: AnswerProvider,
    ) -> AnswerExecutionRecord:
        self._answer_requests += 1
        key = _answer_cache_key(request=request, provider=provider)
        cached = self._values.get(key)
        if cached is not None:
            self._cache_hits += 1
            return cached

        self._cache_misses += 1
        self._provider_answer_calls += 1
        try:
            execution = provider.generate(request)
            if not isinstance(execution, AnswerExecutionRecord):
                execution = AnswerExecutionRecord(
                    status="provider_failed",
                    failure_category="output_invalid",
                    failure_summary=_SAFE_OUTPUT_FAILURE,
                )
        except Exception:  # noqa: BLE001 - the public result must hide Provider internals
            execution = AnswerExecutionRecord(
                status="provider_failed",
                failure_category="provider_error",
                failure_summary=_SAFE_PROVIDER_FAILURE,
            )
        if execution.status == "completed":
            self._values[key] = execution
        return execution

    def stats(self) -> AnswerCitationCacheStats:
        return AnswerCitationCacheStats(
            answer_requests=self._answer_requests,
            cache_hits=self._cache_hits,
            cache_misses=self._cache_misses,
            provider_answer_calls=self._provider_answer_calls,
            cache_entries=len(self._values),
        )


def build_fake_answer_case_inputs_from_dataset(
    path: Path,
) -> tuple[tuple[AnswerCitationFakeCaseInput, ...], str, str]:
    """Build private in-memory Context and Evidence from the frozen 40-row JSONL."""

    content = path.read_bytes()
    cases = [
        EvaluationCase.model_validate_json(line)
        for line in content.decode("utf-8").splitlines()
        if line.strip()
    ]
    cohort = freeze_answer_citation_cohort(cases)
    reporting_by_id: dict[str, AnswerCitationReportingCohort] = {
        item.case_id: item.reporting_cohort for item in cohort.answerable_cases
    }
    reporting_by_id.update(
        {item.case_id: item.reporting_cohort for item in cohort.safety_cases}
    )
    case_by_id = {item.case_id: item for item in cases}
    ordered_case_ids = [item.case_id for item in cohort.answerable_cases] + [
        item.case_id for item in cohort.safety_cases
    ]
    inputs = tuple(
        _fake_case_input(case_by_id[case_id], reporting_by_id[case_id])
        for case_id in ordered_case_ids
    )
    return inputs, cohort.dataset_version, hashlib.sha256(content).hexdigest()


def build_fake_answer_request(case: AnswerCitationFakeCaseInput) -> FakeAnswerRequest:
    """Project one case into the exact private input seen by the fake Provider."""

    return FakeAnswerRequest(
        case_id=case.case.case_id,
        question=case.case.question,
        should_answer=case.case.should_answer,
        expected_non_answer_reason=case.case.expected_non_answer_reason,
        context_status=case.context_status,
        context_texts=case.context_texts,
        expected_golden_evidence_ids=case.expected_golden_evidence_ids,
        authorized_evidence=case.authorized_evidence,
        key_point_rules=case.key_point_rules,
    )


def run_m2_answer_citation_fake_evaluation(
    *,
    cases: Sequence[AnswerCitationFakeCaseInput],
    dataset_version: str,
    dataset_sha256: str,
    provider: AnswerProvider,
) -> AnswerCitationEvaluationReport:
    """Run the fixed 34 plus six Fake Answer plan without external dependencies."""

    if not isinstance(provider.identity, FakeAnswerProviderIdentity):
        raise TypeError("M2-22.8.2 accepts only the explicit fake Answer Provider")
    plan = AnswerCitationEvaluationPlan()
    cohort = freeze_answer_citation_cohort([item.case for item in cases])
    _validate_fake_cases(
        cases,
        cohort=cohort,
        dataset_version=dataset_version,
        dataset_sha256=dataset_sha256,
    )
    request_hashes = [
        _answer_cache_key(request=build_fake_answer_request(item), provider=provider)
        for item in cases
    ]
    metric_rule_hashes = [_answer_rules_sha256(item) for item in cases]
    input_sha256 = _fake_input_sha256(
        plan=plan,
        cohort=cohort,
        dataset_sha256=dataset_sha256,
        provider=provider,
        request_hashes=request_hashes,
        metric_rule_hashes=metric_rule_hashes,
    )
    cache = RunAnswerCache()
    case_results: list[AnswerCitationCaseRunResult] = []

    for case, request_sha256 in zip(cases, request_hashes, strict=True):
        request = build_fake_answer_request(case)
        execution = cache.get_or_generate(request=request, provider=provider)
        result = evaluate_answer_citation_case(
            case_id=case.case.case_id,
            source_group=case.case.source_group,
            reporting_cohort=case.reporting_cohort,
            should_answer=case.case.should_answer,
            expected_non_answer_reason=case.case.expected_non_answer_reason,
            context_status=case.context_status,
            expected_golden_evidence_ids=case.expected_golden_evidence_ids,
            authorized_evidence=case.authorized_evidence,
            key_point_rules=case.key_point_rules,
            forbidden_assertions=case.forbidden_assertions,
            sensitive_phrases=case.sensitive_phrases,
            execution=execution,
        )
        trace = AnswerCitationPublicTrace(
            case_id=case.case.case_id,
            source_group=case.case.source_group,
            reporting_cohort=case.reporting_cohort,
            should_answer=case.case.should_answer,
            question_sha256=_sha256_text(case.case.question),
            context_sha256=_sha256_value(list(case.context_texts)),
            answer_rules_sha256=_answer_rules_sha256(case),
            provider_request_sha256=request_sha256,
            answer_output_sha256=(
                _sha256_text(execution.answer_text)
                if execution.answer_text is not None
                else None
            ),
            result=result,
        )
        case_results.append(
            AnswerCitationCaseRunResult(
                trace=trace,
                trace_sha256=public_answer_trace_sha256(trace),
            )
        )

    grouped_results = aggregate_answer_citation_results(
        [item.trace.result for item in case_results],
        cohort=cohort,
    )
    return AnswerCitationEvaluationReport(
        run_id=f"m2-2282-{input_sha256[:16]}",
        plan=plan,
        dataset_version=cohort.dataset_version,
        dataset_sha256=dataset_sha256,
        input_sha256=input_sha256,
        provider=provider.identity,
        cohort=cohort,
        case_results=case_results,
        grouped_results=grouped_results,
        cache=cache.stats(),
        trace_set_sha256=build_answer_trace_set_sha256(
            [item.trace_sha256 for item in case_results]
        ),
    )


def _fake_case_input(
    case: EvaluationCase,
    reporting_cohort: AnswerCitationReportingCohort,
) -> AnswerCitationFakeCaseInput:
    if not case.should_answer:
        return AnswerCitationFakeCaseInput(
            case=case,
            reporting_cohort=reporting_cohort,
            context_status="completed",
            context_texts=(),
            expected_golden_evidence_ids=frozenset(),
            authorized_evidence=(),
            key_point_rules=(),
            forbidden_assertions=(),
            sensitive_phrases=tuple(case.forbidden_claims),
        )

    golden_ids = tuple(
        _golden_evidence_id(case.case_id, index, span.model_dump(mode="json"))
        for index, span in enumerate(case.expected_evidence_spans, start=1)
    )
    authorized_evidence = tuple(
        AnswerCitationEvidenceBinding(
            citation_label=f"[E{index}]",
            evidence_id=uuid5(_FAKE_EVIDENCE_NAMESPACE, golden_id),
            golden_evidence_ids=[golden_id],
        )
        for index, golden_id in enumerate(golden_ids, start=1)
    )
    key_point_rules = tuple(
        AnswerKeyPointRule(
            key_point_id=f"point-{index:02d}",
            canonical_text=point,
            accepted_variants=list(_variants_for_key_point(case, point)),
        )
        for index, point in enumerate(case.answer_key_points, start=1)
    )
    return AnswerCitationFakeCaseInput(
        case=case,
        reporting_cohort=reporting_cohort,
        context_status="completed",
        context_texts=tuple(span.exact_text for span in case.expected_evidence_spans),
        expected_golden_evidence_ids=frozenset(golden_ids),
        authorized_evidence=authorized_evidence,
        key_point_rules=key_point_rules,
        forbidden_assertions=tuple(case.forbidden_claims),
        sensitive_phrases=(),
    )


def _validate_fake_cases(
    cases: Sequence[AnswerCitationFakeCaseInput],
    *,
    cohort: AnswerCitationEvaluationCohort,
    dataset_version: str,
    dataset_sha256: str,
) -> None:
    if not _SHA256_PATTERN.fullmatch(dataset_sha256):
        raise ValueError("Fake Answer dataset SHA-256 is invalid")
    if dataset_version != "m2-cross-border-rag-smoke-v1":
        raise ValueError("Fake Answer runner requires the frozen Debug dataset")
    if len(cases) != 40 or len({item.case.case_id for item in cases}) != 40:
        raise ValueError("Fake Answer runner requires 40 unique rows")
    expected_ids = [item.case_id for item in cohort.answerable_cases] + [
        item.case_id for item in cohort.safety_cases
    ]
    if [item.case.case_id for item in cases] != expected_ids:
        raise ValueError("Fake Answer rows must preserve the frozen 34 plus six order")
    for item in cases:
        if item.case.dataset_version != dataset_version:
            raise ValueError("Fake Answer case dataset identity drifted")
        if item.context_status != "completed":
            raise ValueError("M2-22.8.2 accepts only complete in-memory Context input")


def _variants_for_key_point(
    case: EvaluationCase,
    canonical_text: str,
) -> tuple[str, ...]:
    seen = {_normalize_match_text(canonical_text)}
    result = []
    for variant in case.acceptable_answer_variants:
        normalized = _normalize_match_text(variant)
        if normalized not in seen:
            seen.add(normalized)
            result.append(variant)
    return tuple(result)


def _answer_cache_key(
    *,
    request: FakeAnswerRequest,
    provider: AnswerProvider,
) -> str:
    return _sha256_value(
        {
            "provider": provider.identity.model_dump(mode="json"),
            "request": _request_payload(request),
        }
    )


def _request_payload(request: FakeAnswerRequest) -> dict[str, object]:
    return {
        "case_id": request.case_id,
        "question": request.question,
        "should_answer": request.should_answer,
        "expected_non_answer_reason": request.expected_non_answer_reason,
        "context_status": request.context_status,
        "context_texts": list(request.context_texts),
        "expected_golden_evidence_ids": sorted(request.expected_golden_evidence_ids),
        "authorized_evidence": [
            item.model_dump(mode="json") for item in request.authorized_evidence
        ],
        "key_point_rules": [
            item.model_dump(mode="json") for item in request.key_point_rules
        ],
    }


def _answer_rules_sha256(case: AnswerCitationFakeCaseInput) -> str:
    return _sha256_value(
        {
            "key_point_rules": [
                item.model_dump(mode="json") for item in case.key_point_rules
            ],
            "forbidden_assertions": list(case.forbidden_assertions),
            "sensitive_phrases": list(case.sensitive_phrases),
            "expected_golden_evidence_ids": sorted(case.expected_golden_evidence_ids),
        }
    )


def _fake_input_sha256(
    *,
    plan: AnswerCitationEvaluationPlan,
    cohort: AnswerCitationEvaluationCohort,
    dataset_sha256: str,
    provider: AnswerProvider,
    request_hashes: Sequence[str],
    metric_rule_hashes: Sequence[str],
) -> str:
    return _sha256_value(
        {
            "plan": plan.model_dump(mode="json"),
            "cohort": cohort.model_dump(mode="json"),
            "dataset_sha256": dataset_sha256,
            "provider": provider.identity.model_dump(mode="json"),
            "provider_request_sha256": list(request_hashes),
            "metric_rule_sha256": list(metric_rule_hashes),
        }
    )


def _golden_evidence_id(case_id: str, index: int, span: object) -> str:
    digest = _sha256_value({"case_id": case_id, "index": index, "span": span})
    return f"golden-{digest[:24]}"


def _normalize_match_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return "".join(character for character in normalized if not character.isspace())


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha256_value(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

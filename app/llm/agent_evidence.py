"""Build one answer-local Evidence allow-list and validate model citation labels."""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Literal
from uuid import UUID

from pydantic import ConfigDict, Field, ValidationError, model_validator

from app.core.errors import AgentProviderOutputError
from app.core.rag_trace import record_answer_reason
from app.llm.agent_schemas import AgentAnswer, AnswerRequest
from app.schemas.agent import (
    MAX_EVIDENCE_IDS,
    BoundedJsonObject,
    CannotCompleteAction,
    FinishAction,
    PublicSummary,
    TaskId,
    WorkerId,
    WorkerObservation,
)
from app.schemas.common import M1Schema
from app.schemas.context import CitationLabel

_VALID_CITATION_PATTERN = re.compile(r"\[E(?:[1-9]|1[0-2])\]")
_CITATION_LIKE_PATTERN = re.compile(
    r"(?:\[|［|【)\s*[EeＥｅ](?:\s*\d{0,5}\s*(?:\]|］|】)?|\s*(?:\]|］|】))"
)

AnswerEvidenceSourceType = Literal["database", "document", "web", "artifact"]


class AnswerEvidence(M1Schema):
    """One server-assigned answer citation backed by one Worker observation."""

    model_config = ConfigDict(frozen=True)

    citation_label: CitationLabel
    evidence_id: UUID
    task_id: TaskId
    worker_id: WorkerId
    source_type: AnswerEvidenceSourceType
    public_summary: PublicSummary
    supporting_data: BoundedJsonObject


class AnswerEvidenceSet(M1Schema):
    """A bounded, ordered Evidence set local to one answer-generation call."""

    model_config = ConfigDict(frozen=True)

    items: tuple[AnswerEvidence, ...] = Field(
        default_factory=tuple,
        max_length=MAX_EVIDENCE_IDS,
    )

    @model_validator(mode="after")
    def validate_mapping(self) -> AnswerEvidenceSet:
        expected = [f"[E{index}]" for index in range(1, len(self.items) + 1)]
        if [item.citation_label for item in self.items] != expected:
            raise ValueError("answer Evidence labels must be contiguous and ordered")
        evidence_ids = [item.evidence_id for item in self.items]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("answer Evidence IDs must be unique")
        return self

    def evidence_id_for_label(self, label: str) -> UUID:
        try:
            index = int(label[2:-1]) - 1
            item = self.items[index]
        except (IndexError, TypeError, ValueError):
            record_answer_reason("unknown_label")
            raise AgentProviderOutputError("evidence_reference_contract") from None
        if item.citation_label != label:
            record_answer_reason("unknown_label")
            raise AgentProviderOutputError("evidence_reference_contract")
        return item.evidence_id


def build_answer_evidence_set(request: AnswerRequest) -> AnswerEvidenceSet:
    """Assign stable answer-local labels to exact observation-backed Evidence."""

    seen: set[UUID] = set()
    items: list[AnswerEvidence] = []
    for result in request.worker_results:
        observation_ids = [
            evidence_id
            for observation in result.observations
            for evidence_id in observation.evidence_ids
        ]
        if not set(result.evidence_ids) <= set(observation_ids):
            raise AgentProviderOutputError("answer_input_contract")
        for evidence_id in result.evidence_ids:
            if evidence_id in seen:
                raise AgentProviderOutputError("answer_input_contract")
            if len(items) >= MAX_EVIDENCE_IDS:
                raise AgentProviderOutputError("answer_input_contract")
            observation = _observation_for_evidence(result.observations, evidence_id)
            source_type, supporting_data = _support_for_evidence(
                observation,
                evidence_id,
                result.worker_id,
            )
            seen.add(evidence_id)
            try:
                items.append(
                    AnswerEvidence(
                        citation_label=f"[E{len(items) + 1}]",
                        evidence_id=evidence_id,
                        task_id=result.task_id,
                        worker_id=result.worker_id,
                        source_type=source_type,
                        public_summary=observation.public_summary,
                        supporting_data=supporting_data,
                    )
                )
            except ValidationError:
                raise AgentProviderOutputError("answer_input_contract") from None
    try:
        return AnswerEvidenceSet(items=tuple(items))
    except (TypeError, ValueError):
        raise AgentProviderOutputError("answer_input_contract") from None


def validate_answer_citations(
    request: AnswerRequest,
    answer: AgentAnswer,
) -> AgentAnswer:
    """Require answer text, labels, and opaque Evidence IDs to agree exactly."""

    evidence_set = build_answer_evidence_set(request)
    action = answer.action
    labels = _extract_strict_labels(action.public_summary)
    if isinstance(action, CannotCompleteAction):
        if labels:
            record_answer_reason("refusal_with_citation")
            raise AgentProviderOutputError("citation_contract")
        return answer.model_copy(deep=True)

    if not isinstance(action, FinishAction):
        raise AgentProviderOutputError("citation_contract")
    if action.business_outcome == "no_evidence":
        if labels or action.evidence_ids:
            record_answer_reason("refusal_with_citation")
            raise AgentProviderOutputError("citation_contract")
        return answer.model_copy(deep=True)
    if action.business_outcome == "answered" and evidence_set.items and not labels:
        record_answer_reason("missing_citation")
        raise AgentProviderOutputError("citation_contract")

    mapped_ids = [evidence_set.evidence_id_for_label(label) for label in labels]
    if mapped_ids != action.evidence_ids:
        record_answer_reason("citation_order_or_set_mismatch")
        raise AgentProviderOutputError("citation_contract")
    return answer.model_copy(deep=True)


def _extract_strict_labels(answer: str) -> list[str]:
    suspicious = list(_CITATION_LIKE_PATTERN.finditer(answer))
    if any(
        _VALID_CITATION_PATTERN.fullmatch(match.group(0)) is None
        for match in suspicious
    ):
        record_answer_reason("malformed_label")
        raise AgentProviderOutputError("citation_contract")
    labels = [match.group(0) for match in _VALID_CITATION_PATTERN.finditer(answer)]
    # Body references may repeat; the Evidence manifest lists each source once.
    return list(dict.fromkeys(labels))


def _observation_for_evidence(
    observations: Sequence[WorkerObservation],
    evidence_id: UUID,
) -> WorkerObservation:
    matches = [item for item in observations if evidence_id in item.evidence_ids]
    if len(matches) != 1 or matches[0].structured_result is None:
        raise AgentProviderOutputError("answer_input_contract")
    return matches[0]


def _support_for_evidence(
    observation: WorkerObservation,
    evidence_id: UUID,
    worker_id: WorkerId,
) -> tuple[AnswerEvidenceSourceType, BoundedJsonObject]:
    if observation.structured_result is None:
        raise AgentProviderOutputError("answer_input_contract")
    root = observation.structured_result.root
    capability_id = root.get("capability_id")
    data = root.get("data")
    if not isinstance(capability_id, str) or not isinstance(data, dict):
        return _source_for_worker(worker_id), observation.structured_result.model_copy(
            deep=True
        )

    if capability_id == "search_knowledge":
        segments = data.get("segments")
        if not isinstance(segments, list):
            raise AgentProviderOutputError("answer_input_contract")
        matches = [
            segment
            for segment in segments
            if isinstance(segment, dict)
            and segment.get("evidence_id") == str(evidence_id)
        ]
        if len(matches) != 1:
            raise AgentProviderOutputError("answer_input_contract")
        support = {
            key: value
            for key, value in matches[0].items()
            if key not in {"citation_label", "evidence_id"}
        }
        return "document", BoundedJsonObject(support)

    if capability_id == "get_evidence_detail":
        if data.get("evidence_id") != str(evidence_id):
            raise AgentProviderOutputError("answer_input_contract")
        source = _normalize_source_type(data.get("source_type"))
        support = {key: value for key, value in data.items() if key != "evidence_id"}
        return source, BoundedJsonObject(support)

    if capability_id in {"get_product_spec", "search_inventory"}:
        return "database", BoundedJsonObject(data)

    raise AgentProviderOutputError("answer_input_contract")


def _normalize_source_type(value: object) -> AnswerEvidenceSourceType:
    if value in {"knowledge", "user_file", "document"}:
        return "document"
    if value == "database":
        return "database"
    if value in {"web", "public_web"}:
        return "web"
    if value == "artifact":
        return "artifact"
    raise AgentProviderOutputError("answer_input_contract")


def _source_for_worker(worker_id: WorkerId) -> AnswerEvidenceSourceType:
    if worker_id == "business_data":
        return "database"
    if worker_id == "knowledge":
        return "document"
    if worker_id in {"public_web", "web_research"}:
        return "web"
    raise AgentProviderOutputError("answer_input_contract")

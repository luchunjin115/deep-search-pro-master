"""Deterministic M2-22.6 ranking metrics over frozen Evidence identities."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal, TypeAlias

from pydantic import Field, FiniteFloat, model_validator

from app.schemas.common import M1Schema
from app.schemas.evaluation import ExpectedNonAnswerReason

RETRIEVAL_CUTOFFS: tuple[int, ...] = (1, 3, 5, 8, 10, 20)
RetrievalDepth: TypeAlias = Literal[10, 20, 30]
RrfConstant: TypeAlias = Literal[20, 60, 100]
_DEPTHS: tuple[RetrievalDepth, ...] = (10, 20, 30)
_RRF_SWEEP: tuple[RrfConstant, ...] = (20, 100)


@dataclass(frozen=True, slots=True)
class RankedEvidenceCandidate:
    """One ranked candidate and the distinct frozen Evidence units it covers."""

    candidate_id: str
    evidence_ids: frozenset[str]
    logical_document_id: str | None = None
    version_id: str | None = None
    index_set_id: str | None = None


class AnswerableRankingMetrics(M1Schema):
    """Per-query deterministic metrics; no semantic Judge is involved."""

    precision_at: dict[int, FiniteFloat]
    recall_at: dict[int, FiniteFloat]
    hit_rate_at: dict[int, FiniteFloat]
    mrr_at_10: FiniteFloat = Field(ge=0, le=1)
    ndcg_at: dict[int, FiniteFloat]
    first_correct_evidence_rank: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_cutoffs(self) -> AnswerableRankingMetrics:
        expected = set(RETRIEVAL_CUTOFFS)
        if set(self.precision_at) != expected:
            raise ValueError("precision cutoffs do not match the frozen set")
        if set(self.recall_at) != expected or set(self.hit_rate_at) != expected:
            raise ValueError("recall and hit-rate cutoffs must match the frozen set")
        if set(self.ndcg_at) != {5, 10}:
            raise ValueError("nDCG cutoffs must be 5 and 10")
        return self


class NoAnswerRankingMetrics(M1Schema):
    """Retrieval-layer non-answer facts without pretending to judge an answer."""

    expected_non_answer_reason: ExpectedNonAnswerReason
    cutoff: int = Field(ge=1, le=100)
    returned_candidate_count: int = Field(ge=0, le=100)
    false_recall: bool | None
    first_forbidden_rank: int | None = Field(default=None, ge=1, le=100)

    @model_validator(mode="after")
    def validate_false_recall(self) -> NoAnswerRankingMetrics:
        security_reason = self.expected_non_answer_reason in {
            "acl_denied",
            "version_unavailable",
            "source_rejected",
        }
        if security_reason != (self.false_recall is not None):
            raise ValueError(
                "only a protected source can have deterministic false recall"
            )
        if security_reason and self.false_recall != (
            self.first_forbidden_rank is not None
        ):
            raise ValueError("false recall must agree with its first forbidden rank")
        return self


@dataclass(frozen=True, slots=True)
class RetrievalPlanPoint:
    """One bounded evaluation-only retrieval setting."""

    stage: Literal["candidate_depth", "rrf"]
    candidate_depth: RetrievalDepth
    rrf_k: RrfConstant
    production_baseline: bool = False


def build_bounded_retrieval_plan(
    *,
    selected_depth: RetrievalDepth,
    production_chunk_baseline: bool = False,
) -> list[RetrievalPlanPoint]:
    """Screen depth first, then RRF only at the selected depth."""

    points = [
        RetrievalPlanPoint(
            stage="candidate_depth",
            candidate_depth=depth,
            rrf_k=60,
            production_baseline=(production_chunk_baseline and depth == 30),
        )
        for depth in _DEPTHS
    ]
    points.extend(
        RetrievalPlanPoint(
            stage="rrf",
            candidate_depth=selected_depth,
            rrf_k=rrf_k,
        )
        for rrf_k in _RRF_SWEEP
    )
    return points


def evaluate_answerable_ranking(
    candidates: list[RankedEvidenceCandidate],
    *,
    expected_evidence_ids: frozenset[str],
) -> AnswerableRankingMetrics:
    """Calculate the frozen TopK suite from exact Evidence coverage."""

    if not expected_evidence_ids:
        raise ValueError("answerable ranking requires expected Evidence")
    if len({item.candidate_id for item in candidates}) != len(candidates):
        raise ValueError("ranked candidates must be unique")
    if any(not item.evidence_ids <= expected_evidence_ids for item in candidates):
        raise ValueError("candidate Evidence must belong to the expected set")

    first_rank = next(
        (
            rank
            for rank, candidate in enumerate(candidates, start=1)
            if candidate.evidence_ids
        ),
        None,
    )
    precision: dict[int, float] = {}
    recall: dict[int, float] = {}
    hit_rate: dict[int, float] = {}
    for cutoff in RETRIEVAL_CUTOFFS:
        prefix = candidates[:cutoff]
        relevant_candidates = sum(bool(item.evidence_ids) for item in prefix)
        covered = frozenset().union(*(item.evidence_ids for item in prefix))
        precision[cutoff] = relevant_candidates / cutoff
        recall[cutoff] = len(covered) / len(expected_evidence_ids)
        hit_rate[cutoff] = float(bool(covered))

    return AnswerableRankingMetrics(
        precision_at=precision,
        recall_at=recall,
        hit_rate_at=hit_rate,
        mrr_at_10=(
            1 / first_rank if first_rank is not None and first_rank <= 10 else 0.0
        ),
        ndcg_at={
            cutoff: _evidence_ndcg(
                candidates,
                expected_evidence_ids=expected_evidence_ids,
                cutoff=cutoff,
            )
            for cutoff in (5, 10)
        },
        first_correct_evidence_rank=first_rank,
    )


def evaluate_no_answer_ranking(
    candidates: list[RankedEvidenceCandidate],
    *,
    expected_non_answer_reason: ExpectedNonAnswerReason,
    protected_document_ids: frozenset[str],
    protected_version_ids: frozenset[str] = frozenset(),
    protected_index_set_ids: frozenset[str] = frozenset(),
    cutoff: int,
) -> NoAnswerRankingMetrics:
    """Detect ACL/version leakage; leave semantic unknown/no-evidence unjudged."""

    if not 1 <= cutoff <= 100:
        raise ValueError("cutoff must be between 1 and 100")
    if len({item.candidate_id for item in candidates}) != len(candidates):
        raise ValueError("ranked candidates must be unique")
    first_forbidden: int | None = None
    if expected_non_answer_reason in {
        "acl_denied",
        "version_unavailable",
        "source_rejected",
    }:
        first_forbidden = next(
            (
                rank
                for rank, candidate in enumerate(candidates[:cutoff], start=1)
                if (
                    candidate.logical_document_id in protected_document_ids
                    or candidate.version_id in protected_version_ids
                    or candidate.index_set_id in protected_index_set_ids
                )
            ),
            None,
        )
    return NoAnswerRankingMetrics(
        expected_non_answer_reason=expected_non_answer_reason,
        cutoff=cutoff,
        returned_candidate_count=min(len(candidates), cutoff),
        false_recall=(
            first_forbidden is not None
            if expected_non_answer_reason
            in {"acl_denied", "version_unavailable", "source_rejected"}
            else None
        ),
        first_forbidden_rank=first_forbidden,
    )


def _evidence_ndcg(
    candidates: list[RankedEvidenceCandidate],
    *,
    expected_evidence_ids: frozenset[str],
    cutoff: int,
) -> float:
    seen: set[str] = set()
    dcg = 0.0
    for rank, candidate in enumerate(candidates[:cutoff], start=1):
        new_evidence = candidate.evidence_ids - seen
        seen.update(new_evidence)
        if new_evidence:
            dcg += len(new_evidence) / math.log2(rank + 1)
    ideal_items = min(len(expected_evidence_ids), cutoff)
    ideal = sum(1 / math.log2(rank + 1) for rank in range(1, ideal_items + 1))
    return dcg / ideal if ideal else 0.0

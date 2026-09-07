"""Deterministic repetition and no-progress termination for Worker attempts."""

from __future__ import annotations

import hashlib

from pydantic import ConfigDict, Field

from app.core.errors import BudgetExceededError
from app.llm.agent_schemas import HandoffDraft
from app.schemas.agent import WorkerResult
from app.schemas.common import M1Schema


class TerminationPolicy(M1Schema):
    """Small immutable limits for delegation loops and stalled results."""

    model_config = ConfigDict(frozen=True)

    max_repeat_handoffs: int = Field(ge=1, le=4)
    max_no_progress_results: int = Field(ge=1, le=4)


class WorkerTerminationManager:
    """Track stable public signatures, independent of model wording tricks."""

    def __init__(self, policy: TerminationPolicy) -> None:
        self._policy = policy
        self._handoff_counts: dict[str, int] = {}
        self._no_progress_counts: dict[tuple[str, str], int] = {}

    def before_handoff(self, draft: HandoffDraft) -> None:
        signature = hashlib.sha256(
            draft.model_dump_json(exclude={"contract_version"}).encode("utf-8")
        ).hexdigest()
        count = self._handoff_counts.get(signature, 0)
        if count >= self._policy.max_repeat_handoffs:
            raise BudgetExceededError(
                "repeated_handoff",
                "Agent运行已因重复委派停止。",
            )
        self._handoff_counts[signature] = count + 1

    def observe(self, result: WorkerResult) -> None:
        key = (result.task_id, result.worker_id)
        if _made_progress(result):
            self._no_progress_counts.pop(key, None)
            return
        count = self._no_progress_counts.get(key, 0) + 1
        self._no_progress_counts[key] = count
        if count > self._policy.max_no_progress_results:
            raise BudgetExceededError(
                "no_progress",
                "Agent运行已因连续无进展停止。",
            )


def _made_progress(result: WorkerResult) -> bool:
    if result.execution_status in {"completed", "failed", "waiting_user"}:
        return True
    return bool(
        result.business_result
        or result.observations
        or result.evidence_ids
        or result.artifact_ids
        or result.unknowns
        or result.safe_errors
    )

"""Public-safe facade for the bounded Supervisor control graph."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, cast, runtime_checkable
from uuid import UUID

from pydantic import ConfigDict, Field, model_validator

from app.agents.engineered_state import EngineeredAgentState
from app.llm.agent_provider import EngineeredAgentProvider
from app.llm.agent_schemas import (
    MAX_PROVIDER_WORKERS,
    HandoffDraft,
    WorkerCapabilityProfile,
)
from app.schemas.agent import BoundedJsonObject, GoalText, ResourceUsage, WorkerResult
from app.schemas.common import M1Schema


def _empty_public_context() -> BoundedJsonObject:
    return BoundedJsonObject({})


class SupervisorRequest(M1Schema):
    """Safe graph input assembled from a trusted run ID and Resolver projections."""

    model_config = ConfigDict(frozen=True)

    run_id: UUID
    goal: GoalText
    public_context: BoundedJsonObject = Field(default_factory=_empty_public_context)
    available_workers: tuple[WorkerCapabilityProfile, ...] = Field(
        default_factory=tuple,
        max_length=MAX_PROVIDER_WORKERS,
    )

    @model_validator(mode="after")
    def validate_worker_order(self) -> SupervisorRequest:
        worker_ids = [item.worker.capability_id for item in self.available_workers]
        if len(worker_ids) != len(set(worker_ids)):
            raise ValueError("available Worker IDs must be unique")
        if worker_ids != sorted(worker_ids):
            raise ValueError("available Workers must use stable sorted order")
        return self


@dataclass(frozen=True, slots=True)
class SupervisorGuardrails:
    """Small control-loop limits; tree budgets remain a M2-21.5 responsibility."""

    max_decisions: int = 16
    max_identical_actions: int = 1
    max_parallel_workers: int = 2

    def __post_init__(self) -> None:
        if not 1 <= self.max_decisions <= 64:
            raise ValueError("max_decisions must be between 1 and 64")
        if not 1 <= self.max_identical_actions <= 4:
            raise ValueError("max_identical_actions must be between 1 and 4")
        if not 1 <= self.max_parallel_workers <= 4:
            raise ValueError("max_parallel_workers must be between 1 and 4")


@runtime_checkable
class WorkerInvoker(Protocol):
    """Narrow Fake-Worker seam; it deliberately receives no trusted budget IDs."""

    async def invoke(self, handoff: HandoffDraft) -> WorkerResult: ...


class SupervisorAgent:
    """Run one in-memory Supervisor graph and return a strict safe state."""

    def __init__(
        self,
        *,
        provider: EngineeredAgentProvider,
        worker: WorkerInvoker,
        guardrails: SupervisorGuardrails | None = None,
    ) -> None:
        self._provider = provider
        self._worker = worker
        self._guardrails = guardrails or SupervisorGuardrails()

    async def run(self, request: SupervisorRequest) -> EngineeredAgentState:
        """Execute the bounded in-memory Supervisor control graph."""

        from app.agents.graphs.engineered_multi_agent import (
            SupervisorGraphState,
            build_engineered_multi_agent_graph,
            engineered_state_from_graph,
            initial_supervisor_graph_state,
        )

        graph = build_engineered_multi_agent_graph(
            self._provider,
            self._worker,
            self._guardrails,
        )
        try:
            final_state = cast(
                SupervisorGraphState,
                await graph.ainvoke(initial_supervisor_graph_state(request)),
            )
            return engineered_state_from_graph(final_state)
        except Exception:  # noqa: BLE001 - the public boundary cannot leak internals
            return EngineeredAgentState(
                run_id=request.run_id,
                goal=request.goal,
                public_context=request.public_context,
                plan=None,
                execution_status="failed",
                business_outcome="system_error",
                public_summary="Agent流程未能安全完成。",
                stop_reason="graph_failure",
                resource_usage=ResourceUsage(
                    model_calls=0,
                    tool_calls=0,
                    input_tokens=0,
                    output_tokens=0,
                    duration_ms=0,
                ),
            )

    async def resume(
        self,
        request: SupervisorRequest,
        checkpoint: EngineeredAgentState,
        *,
        replan: bool,
    ) -> EngineeredAgentState:
        """Continue one claimed checkpoint without replaying completed work."""

        from app.agents.graphs.engineered_multi_agent import (
            SupervisorGraphState,
            build_engineered_multi_agent_graph,
            engineered_state_from_graph,
            resumed_supervisor_graph_state,
        )

        graph = build_engineered_multi_agent_graph(
            self._provider,
            self._worker,
            self._guardrails,
        )
        try:
            final_state = cast(
                SupervisorGraphState,
                await graph.ainvoke(
                    resumed_supervisor_graph_state(
                        request,
                        checkpoint,
                        replan=replan,
                    )
                ),
            )
            return engineered_state_from_graph(final_state)
        except Exception:  # noqa: BLE001 - resume failures stay public-safe
            return EngineeredAgentState(
                run_id=request.run_id,
                goal=request.goal,
                public_context=request.public_context,
                plan=checkpoint.plan,
                execution_status="failed",
                business_outcome="system_error",
                public_summary="Agent恢复未能安全完成。",
                stop_reason="resume_failure",
                resource_usage=checkpoint.resource_usage,
            )

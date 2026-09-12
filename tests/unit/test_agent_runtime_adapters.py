from __future__ import annotations

from typing import cast
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

from app.agents.runtime import BudgetedAgentProvider, WorkerHarnessAdapter
from app.core.errors import BudgetExceededError
from app.llm.agent_provider import EngineeredAgentProvider
from app.llm.agent_schemas import (
    AnswerRequest,
    DecisionRequest,
    HandoffRequest,
    PlannerRequest,
)
from app.llm.agent_structured import OutputT, StructuredAgentProvider
from app.runtime.budget import AgentBudgetLimits, AgentBudgetTree, WorkerBudgetLimits
from app.runtime.context import RunContext
from app.runtime.permissions import PermissionGuard
from app.runtime.trace import RunTrace, TraceRecorder
from app.schemas.agent import BoundedJsonObject
from app.tools.registry import ToolRegistry

ROOT_RUN_ID = UUID("00000000-0000-0000-0000-000000000531")
CHILD_RUN_ID = UUID("00000000-0000-0000-0000-000000000532")
BUDGET_REF = UUID("00000000-0000-0000-0000-000000000533")
TENANT_ID = UUID("00000000-0000-0000-0000-000000000534")
USER_ID = UUID("00000000-0000-0000-0000-000000000535")
THREAD_ID = UUID("00000000-0000-0000-0000-000000000536")
TRACE_ID = UUID("00000000-0000-0000-0000-000000000537")


def budget_tree() -> AgentBudgetTree:
    return AgentBudgetTree(
        root_run_id=ROOT_RUN_ID,
        limits=AgentBudgetLimits(
            max_model_calls=4,
            max_tool_calls=2,
            max_input_tokens=1_000,
            max_output_tokens=500,
            max_tasks=2,
            max_evidence=12,
            max_delegations=2,
            max_depth=1,
            total_timeout_ms=5_000,
        ),
        id_factory=lambda: BUDGET_REF,
    )


def trusted_context() -> RunContext:
    return RunContext(
        user_id=USER_ID,
        tenant_id=TENANT_ID,
        roles=("amazon_operator",),
        market_scopes=("DE",),
        thread_id=THREAD_ID,
        trace_id=TRACE_ID,
    )


def audit_run() -> RunTrace:
    return RunTrace(
        id=ROOT_RUN_ID,
        tenant_id=TENANT_ID,
        trace_id=TRACE_ID,
        started_monotonic=100.0,
    )


@pytest.mark.asyncio
async def test_provider_adapter_reserves_every_supervisor_model_call() -> None:
    provider = MagicMock(spec=EngineeredAgentProvider)
    outputs = (object(), object(), object(), object())
    provider.create_plan = AsyncMock(return_value=outputs[0])
    provider.choose_action = AsyncMock(return_value=outputs[1])
    provider.prepare_handoff = AsyncMock(return_value=outputs[2])
    provider.compose_answer = AsyncMock(return_value=outputs[3])
    tree = budget_tree()
    adapter = BudgetedAgentProvider(
        provider=cast(EngineeredAgentProvider, provider),
        budget=tree,
    )

    assert await adapter.create_plan(cast(PlannerRequest, object())) is outputs[0]
    assert await adapter.choose_action(cast(DecisionRequest, object())) is outputs[1]
    assert await adapter.prepare_handoff(cast(HandoffRequest, object())) is outputs[2]
    assert await adapter.compose_answer(cast(AnswerRequest, object())) is outputs[3]
    assert tree.snapshot().model_calls == 4

    with pytest.raises(BudgetExceededError) as captured:
        await adapter.create_plan(cast(PlannerRequest, object()))
    assert getattr(captured.value, "reason", None) == "model_call_limit"
    assert provider.create_plan.await_count == 1


@pytest.mark.asyncio
async def test_answer_repair_reserves_each_real_model_invoke() -> None:
    class RepairOnceProvider(StructuredAgentProvider):
        def __init__(self) -> None:
            self.calls = 0

        async def _invoke(
            self,
            *,
            role: str,
            system_prompt: str,
            input_payload: dict[str, object],
            output_type: type[OutputT],
            output_schema: dict[str, object] | None = None,
        ) -> OutputT:
            assert role == "answer"
            self.calls += 1
            if self.calls == 1:
                from app.core.errors import AgentProviderOutputError

                raise AgentProviderOutputError("model_json")
            return output_type.model_validate(
                {
                    "action": {
                        "type": "finish",
                        "public_summary": "当前没有可引用证据。",
                        "business_outcome": "no_evidence",
                        "citation_labels": [],
                        "artifact_ids": [],
                    }
                }
            )

    provider = RepairOnceProvider()
    tree = budget_tree()
    adapter = BudgetedAgentProvider(provider=provider, budget=tree)

    await adapter.compose_answer(
        AnswerRequest(goal="未知问题", public_context=BoundedJsonObject({}))
    )

    assert provider.calls == 2
    assert adapter.last_answer_model_calls == 2
    assert tree.snapshot().model_calls == 2


def test_harness_adapter_uses_child_budget_and_rejects_context_mismatch() -> None:
    tree = budget_tree()
    child = tree.allocate_child(
        parent_run_id=ROOT_RUN_ID,
        child_run_id=CHILD_RUN_ID,
        task_id="inventory",
        limits=WorkerBudgetLimits(
            max_model_calls=1,
            max_tool_calls=1,
            max_repeat_tool_calls=1,
            max_input_tokens=100,
            max_output_tokens=50,
            max_evidence=1,
            timeout_ms=1_000,
        ),
    )
    registry = ToolRegistry(())
    recorder = MagicMock(spec=TraceRecorder)
    adapter = WorkerHarnessAdapter(
        registry=registry,
        permission_guard=PermissionGuard(registry),
        trace_recorder=recorder,
    )

    harness = adapter.create(trusted_context(), audit_run(), child)
    harness.reserve_model_call()

    assert child.snapshot().model_calls == 1
    recorder.increment_model_call.assert_called_once_with(audit_run())
    mismatched = RunTrace(
        id=ROOT_RUN_ID,
        tenant_id=UUID("00000000-0000-0000-0000-000000000599"),
        trace_id=TRACE_ID,
        started_monotonic=100.0,
    )
    with pytest.raises(ValueError, match="tenant mismatch"):
        adapter.create(trusted_context(), mismatched, child)

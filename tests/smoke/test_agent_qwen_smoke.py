from __future__ import annotations

import os
from uuid import UUID

import pytest
from pydantic import SecretStr

from app.agents.definitions import create_m2_agent_definitions
from app.capabilities.catalog import create_m2_capability_catalog
from app.capabilities.contracts import CapabilitySelection
from app.capabilities.resolver import CapabilityResolver
from app.core.config import Settings
from app.llm.agent_factory import create_engineered_agent_provider
from app.llm.agent_qwen import QwenAgentProvider
from app.llm.agent_schemas import (
    AnswerRequest,
    DecisionRequest,
    HandoffRequest,
    PlannerRequest,
    WorkerCapabilityProfile,
)
from app.runtime.context import RunContext
from app.schemas.agent import (
    BoundedJsonObject,
    DelegateTaskAction,
    ExecuteCapabilityAction,
    ResourceUsage,
    WorkerObservation,
    WorkerResult,
)


def _context() -> RunContext:
    return RunContext(
        user_id=UUID("10000000-0000-0000-0000-000000000001"),
        tenant_id=UUID("10000000-0000-0000-0000-000000000002"),
        roles=("company_owner",),
        market_scopes=("DE", "FR"),
        thread_id=UUID("10000000-0000-0000-0000-000000000003"),
        trace_id=UUID("10000000-0000-0000-0000-000000000004"),
    )


def _profiles() -> tuple[WorkerCapabilityProfile, ...]:
    definitions = create_m2_agent_definitions()
    resolver = CapabilityResolver(create_m2_capability_catalog(), definitions)
    targets = resolver.resolve_delegation_targets(_context(), CapabilitySelection())
    profiles = []
    for target in targets.capabilities:
        profiles.append(
            WorkerCapabilityProfile(
                worker=target,
                capabilities=resolver.resolve_for_agent(
                    _context(),
                    target.capability_id,
                    CapabilitySelection(),
                ),
            )
        )
    return tuple(profiles)


def _usage() -> ResourceUsage:
    return ResourceUsage(
        model_calls=0,
        tool_calls=1,
        input_tokens=0,
        output_tokens=0,
        duration_ms=1,
    )


@pytest.mark.asyncio
async def test_real_qwen_agent_one_hop_multi_hop_and_cited_answer() -> None:
    api_key = os.getenv("QWEN_API_KEY")
    if os.getenv("RUN_QWEN_AGENT_SMOKE") != "1" or not api_key:
        pytest.skip("set RUN_QWEN_AGENT_SMOKE=1 and QWEN_API_KEY to call paid Qwen API")

    settings = Settings(  # type: ignore[call-arg]
        _env_file=None,
        llm_provider="qwen",
        qwen_api_key=SecretStr(api_key),
        qwen_timeout_seconds=30,
    )
    provider = create_engineered_agent_provider(settings)
    assert isinstance(provider, QwenAgentProvider)
    profiles = _profiles()
    public_context = BoundedJsonObject(
        {"locale": "zh-CN", "sku": "LR-TL-MUSH-OR01", "market_code": "DE"}
    )
    try:
        one_hop_goal = "查询SKU LR-TL-MUSH-OR01在德国市场的当前库存。"
        one_hop = await provider.create_plan(
            PlannerRequest(
                goal=one_hop_goal,
                available_workers=profiles,
                public_context=public_context,
            )
        )
        assert len(one_hop.tasks) == 1
        assert one_hop.tasks[0].assignment.worker_id == "business_data"

        supervisor_action = await provider.choose_action(
            DecisionRequest(
                plan=one_hop,
                active_task_id=one_hop.tasks[0].task_id,
                available_capabilities=CapabilityResolver(
                    create_m2_capability_catalog(), create_m2_agent_definitions()
                ).resolve_delegation_targets(_context(), CapabilitySelection()),
                public_context=public_context,
            )
        )
        assert isinstance(supervisor_action.action, DelegateTaskAction)
        handoff = await provider.prepare_handoff(
            HandoffRequest(
                plan=one_hop,
                delegation=supervisor_action.action,
                available_workers=CapabilityResolver(
                    create_m2_capability_catalog(), create_m2_agent_definitions()
                ).resolve_delegation_targets(_context(), CapabilitySelection()),
                public_context=public_context,
            )
        )
        assert handoff.public_context == public_context

        business_capabilities = CapabilityResolver(
            create_m2_capability_catalog(), create_m2_agent_definitions()
        ).resolve_for_agent(_context(), "business_data", CapabilitySelection())
        worker_action = await provider.choose_action(
            DecisionRequest(
                plan=one_hop,
                active_task_id=one_hop.tasks[0].task_id,
                available_capabilities=business_capabilities,
                public_context=public_context,
            )
        )
        assert isinstance(worker_action.action, ExecuteCapabilityAction)
        assert worker_action.action.capability_id == "search_inventory"
        assert worker_action.action.arguments.root == {
            "sku": "LR-TL-MUSH-OR01",
            "market_code": "DE",
            "warehouse_code": None,
        }

        multi_hop_goal = (
            "查询SKU LR-TL-MUSH-OR01在德国市场的库存，并结合内部知识中的补货规则解释。"
        )
        multi_hop = await provider.create_plan(
            PlannerRequest(
                goal=multi_hop_goal,
                available_workers=profiles,
                public_context=public_context,
            )
        )
        assert {task.assignment.worker_id for task in multi_hop.tasks} == {
            "business_data",
            "knowledge",
        }

        evidence_id = UUID("20000000-0000-0000-0000-000000000001")
        observation = WorkerObservation(
            observation_id=UUID("30000000-0000-0000-0000-000000000001"),
            status="success",
            public_summary="search_inventory执行成功。",
            structured_result=BoundedJsonObject(
                {
                    "capability_id": "search_inventory",
                    "data": {
                        "sku": "LR-TL-MUSH-OR01",
                        "market_code": "DE",
                        "available_quantity": 125,
                    },
                }
            ),
            evidence_ids=[evidence_id],
            resource_usage=_usage(),
        )
        answer = await provider.compose_answer(
            AnswerRequest(
                goal=one_hop_goal,
                public_context=public_context,
                worker_results=(
                    WorkerResult(
                        task_id=one_hop.tasks[0].task_id,
                        worker_id="business_data",
                        execution_status="completed",
                        business_outcome="answered",
                        business_result=BoundedJsonObject({"available_quantity": 125}),
                        public_summary="德国市场可售库存为125件。",
                        observations=[observation],
                        evidence_ids=[evidence_id],
                        resource_usage=_usage(),
                    ),
                ),
            )
        )
    finally:
        await provider.aclose()

    assert "[E1]" in answer.action.public_summary
    assert answer.action.evidence_ids == [evidence_id]  # type: ignore[union-attr]

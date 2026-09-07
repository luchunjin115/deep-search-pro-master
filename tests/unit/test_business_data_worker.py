from __future__ import annotations

import ast
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, TypeAlias, cast
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from sqlalchemy.orm import Session

from app.agents.definitions import create_m2_agent_definitions
from app.agents.runtime import WorkerExecutionContext, WorkerRunTrace
from app.agents.workers.business_data import (
    BusinessCapabilityExecutor,
    BusinessCapabilityExecutorFactory,
    BusinessDataWorker,
    BusinessWorkerGuardrails,
)
from app.capabilities.catalog import create_m2_capability_catalog
from app.capabilities.resolver import CapabilityResolver
from app.llm.agent_provider import AgentDecisionProvider
from app.llm.agent_schemas import DecisionRequest
from app.runtime.budget import ChildExecutionBudget
from app.runtime.context import RunContext
from app.runtime.executor import HarnessExecutor
from app.schemas.agent import (
    AgentDecision,
    AgentHandoff,
    AskUserAction,
    BoundedJsonObject,
    CannotCompleteAction,
    ExecuteCapabilityAction,
    FinishAction,
)
from app.schemas.common import ToolEnvelope, ToolMeta, ToolName
from app.schemas.inventory import InventoryResult
from app.schemas.product import ProductSpecItem, ProductSpecResult

ROOT = Path(__file__).parents[2]
ROOT_RUN_ID = UUID("00000000-0000-0000-0000-000000000601")
WORKER_RUN_ID = UUID("00000000-0000-0000-0000-000000000602")
HANDOFF_ID = UUID("00000000-0000-0000-0000-000000000603")
BUDGET_REF = UUID("00000000-0000-0000-0000-000000000604")
TRACE_ID = UUID("00000000-0000-0000-0000-000000000605")
TENANT_ID = UUID("00000000-0000-0000-0000-000000000606")
USER_ID = UUID("00000000-0000-0000-0000-000000000607")
THREAD_ID = UUID("00000000-0000-0000-0000-000000000608")
PRODUCT_ID = UUID("00000000-0000-0000-0000-000000000609")
VARIANT_ID = UUID("00000000-0000-0000-0000-000000000610")
EVIDENCE_ID = UUID("00000000-0000-0000-0000-000000000611")
FORGED_EVIDENCE_ID = UUID("00000000-0000-0000-0000-000000000612")
OBSERVATION_IDS = tuple(
    UUID(f"00000000-0000-0000-0000-{value:012d}") for value in range(620, 640)
)

DecisionStep: TypeAlias = AgentDecision | Callable[[DecisionRequest], AgentDecision]
BusinessEnvelope: TypeAlias = (
    ToolEnvelope[ProductSpecResult] | ToolEnvelope[InventoryResult]
)


def context() -> RunContext:
    return RunContext(
        user_id=USER_ID,
        tenant_id=TENANT_ID,
        roles=("amazon_operator",),
        market_scopes=("DE",),
        thread_id=THREAD_ID,
        trace_id=TRACE_ID,
    )


def execution() -> WorkerExecutionContext:
    return WorkerExecutionContext(
        trusted_context=context(),
        worker_run=WorkerRunTrace(
            run_id=WORKER_RUN_ID,
            parent_run_id=ROOT_RUN_ID,
            root_run_id=ROOT_RUN_ID,
            trace_id=TRACE_ID,
            budget_ref=BUDGET_REF,
            depth=1,
        ),
        budget=cast(ChildExecutionBudget, MagicMock(spec=ChildExecutionBudget)),
        harness=cast(HarnessExecutor, MagicMock(spec=HarnessExecutor)),
        session=cast(Session, MagicMock(spec=Session)),
    )


def handoff(
    *,
    goal: str = "查询橙色蘑菇灯在德国市场的业务信息",
    public_context: dict[str, object] | None = None,
) -> AgentHandoff:
    return AgentHandoff(
        handoff_id=HANDOFF_ID,
        task_id="business_task",
        goal=goal,
        target_worker="business_data",
        public_context=BoundedJsonObject(
            public_context or {"product_query": "蘑菇灯", "market_code": "DE"}
        ),
        constraints=["只能调用获权的只读业务Tool"],
        expected_output="返回规格或库存事实及Evidence，缺信息时明确追问",
        completion_criteria=["返回业务事实或明确未知"],
        allocated_budget_ref=BUDGET_REF,
    )


def product_envelope() -> ToolEnvelope[ProductSpecResult]:
    return ToolEnvelope[ProductSpecResult](
        status="success",
        data=ProductSpecResult(
            product_id=PRODUCT_ID,
            variant_id=VARIANT_ID,
            sku="LR-TL-MUSH-OR01",
            name_zh="橙色复古蘑菇台灯",
            name_en="Orange Retro Mushroom Table Lamp",
            status="active",
            specs=[
                ProductSpecItem(
                    name="额定功率",
                    value="12",
                    unit="W",
                    verification_status="demo_declared",
                )
            ],
        ),
        evidence_ids=[],
        meta=tool_meta("get_product_spec"),
    )


def inventory_envelope() -> ToolEnvelope[InventoryResult]:
    return ToolEnvelope[InventoryResult](
        status="success",
        data=InventoryResult(
            sku="LR-TL-MUSH-OR01",
            product_name="橙色复古蘑菇台灯",
            market_code="DE",
            warehouse_code="DE-FRA",
            warehouse_name="德国法兰克福合成演示仓",
            on_hand=150,
            reserved=20,
            unsellable=5,
            available=125,
            inbound=30,
            safety_stock=40,
            snapshot_at=datetime(2026, 8, 1, 8, 0, tzinfo=UTC),
        ),
        evidence_ids=[EVIDENCE_ID],
        meta=tool_meta("search_inventory"),
    )


def error_envelope(
    tool: ToolName,
    *,
    code: str,
    message: str,
    field_name: str | None = None,
) -> BusinessEnvelope:
    return ToolEnvelope[ProductSpecResult].model_validate(
        {
            "status": "error",
            "error": {
                "code": code,
                "message": message,
                "retryable": False,
                "field": field_name,
            },
            "meta": tool_meta(tool).model_dump(mode="python"),
        }
    )


def tool_meta(tool: ToolName) -> ToolMeta:
    return ToolMeta(
        tool=tool,
        version="1.0.0",
        duration_ms=3,
        trace_id=TRACE_ID,
    )


def execute(capability_id: str, arguments: dict[str, object]) -> AgentDecision:
    return AgentDecision(
        action=ExecuteCapabilityAction(
            capability_id=capability_id,
            arguments=BoundedJsonObject(arguments),
        )
    )


def finish_from_observations(
    request: DecisionRequest,
    *,
    outcome: Literal["answered", "partial", "no_evidence"] = "answered",
) -> AgentDecision:
    evidence_ids = [
        evidence_id
        for observation in request.observations
        for evidence_id in observation.evidence_ids
    ]
    return AgentDecision(
        action=FinishAction(
            public_summary="已根据获权业务Tool完成任务。",
            business_outcome=outcome,
            evidence_ids=evidence_ids,
        )
    )


@dataclass
class ScriptedDecisionProvider:
    steps: list[DecisionStep]
    requests: list[DecisionRequest] = field(default_factory=list)

    async def choose_action(self, request: DecisionRequest) -> AgentDecision:
        self.requests.append(request)
        step = self.steps.pop(0)
        return step(request) if callable(step) else step.model_copy(deep=True)


@dataclass
class FakeBusinessExecutor:
    responses: dict[str, list[BusinessEnvelope]]
    calls: list[ExecuteCapabilityAction] = field(default_factory=list)

    def execute(self, action: ExecuteCapabilityAction) -> BusinessEnvelope:
        self.calls.append(action)
        return self.responses[action.capability_id].pop(0)


@dataclass
class FakeBusinessExecutorFactory:
    executor: FakeBusinessExecutor
    executions: list[WorkerExecutionContext] = field(default_factory=list)

    def create(
        self,
        execution_context: WorkerExecutionContext,
    ) -> BusinessCapabilityExecutor:
        self.executions.append(execution_context)
        return self.executor


def worker(
    provider: ScriptedDecisionProvider,
    executor: FakeBusinessExecutor,
    *,
    max_decisions: int = 4,
) -> BusinessDataWorker:
    ids = iter(OBSERVATION_IDS)
    return BusinessDataWorker(
        provider=cast(AgentDecisionProvider, provider),
        resolver=CapabilityResolver(
            create_m2_capability_catalog(),
            create_m2_agent_definitions(),
        ),
        executor_factory=cast(
            BusinessCapabilityExecutorFactory,
            FakeBusinessExecutorFactory(executor),
        ),
        guardrails=BusinessWorkerGuardrails(max_decisions=max_decisions),
        id_factory=lambda: next(ids),
    )


@pytest.mark.asyncio
async def test_product_only_uses_only_product_tool() -> None:
    executor = FakeBusinessExecutor({"get_product_spec": [product_envelope()]})
    provider = ScriptedDecisionProvider(
        [
            execute("get_product_spec", {"product_query": "蘑菇灯"}),
            finish_from_observations,
        ]
    )

    result = await worker(provider, executor).run(handoff(), execution())

    assert result.execution_status == "completed"
    assert result.business_outcome == "answered"
    assert [call.capability_id for call in executor.calls] == ["get_product_spec"]
    assert len(result.observations) == 1
    assert result.observations[0].status == "success"
    assert result.business_result is not None
    product = cast(dict[str, object], result.business_result.root["product"])
    assert product["sku"] == "LR-TL-MUSH-OR01"
    assert result.evidence_ids == []


@pytest.mark.asyncio
async def test_exact_sku_inventory_uses_only_inventory_tool_and_evidence() -> None:
    executor = FakeBusinessExecutor({"search_inventory": [inventory_envelope()]})
    provider = ScriptedDecisionProvider(
        [
            execute(
                "search_inventory",
                {"sku": "LR-TL-MUSH-OR01", "market_code": "DE"},
            ),
            finish_from_observations,
        ]
    )

    result = await worker(provider, executor).run(
        handoff(
            goal="查询LR-TL-MUSH-OR01在德国市场的库存",
            public_context={"sku": "LR-TL-MUSH-OR01", "market_code": "DE"},
        ),
        execution(),
    )

    assert [call.capability_id for call in executor.calls] == ["search_inventory"]
    assert result.business_outcome == "answered"
    assert result.evidence_ids == [EVIDENCE_ID]
    assert result.observations[0].structured_result is not None
    inventory = cast(
        dict[str, object],
        result.observations[0].structured_result.root["data"],
    )
    assert inventory["available"] == 125


@pytest.mark.asyncio
async def test_combined_query_resolves_product_then_uses_resolved_sku_for_inventory() -> (
    None
):
    executor = FakeBusinessExecutor(
        {
            "get_product_spec": [product_envelope()],
            "search_inventory": [inventory_envelope()],
        }
    )

    def search_with_resolved_sku(request: DecisionRequest) -> AgentDecision:
        product = request.observations[0].structured_result
        assert product is not None
        data = cast(dict[str, object], product.root["data"])
        return execute(
            "search_inventory",
            {"sku": data["sku"], "market_code": "DE"},
        )

    provider = ScriptedDecisionProvider(
        [
            execute("get_product_spec", {"product_query": "蘑菇灯"}),
            search_with_resolved_sku,
            finish_from_observations,
        ]
    )

    result = await worker(provider, executor).run(handoff(), execution())

    assert [call.capability_id for call in executor.calls] == [
        "get_product_spec",
        "search_inventory",
    ]
    assert result.business_outcome == "answered"
    assert result.evidence_ids == [EVIDENCE_ID]
    assert len(result.observations) == 2


@pytest.mark.asyncio
async def test_ambiguous_product_observation_leads_to_user_clarification() -> None:
    executor = FakeBusinessExecutor(
        {
            "get_product_spec": [
                error_envelope(
                    "get_product_spec",
                    code="AMBIGUOUS_PRODUCT",
                    message="找到多个匹配商品，请使用更精确的商品名称或SKU",
                    field_name="product_query",
                )
            ]
        }
    )
    provider = ScriptedDecisionProvider(
        [
            execute("get_product_spec", {"product_query": "灯"}),
            AgentDecision(
                action=AskUserAction(
                    question="请提供更精确的商品名称或SKU。",
                    requested_fields=["product_query"],
                )
            ),
        ]
    )

    result = await worker(provider, executor).run(
        handoff(
            goal="查询灯的业务信息",
            public_context={"product_query": "灯", "market_code": "DE"},
        ),
        execution(),
    )

    assert result.execution_status == "waiting_user"
    assert result.business_outcome is None
    assert result.unknowns == ["product_query"]
    assert [call.capability_id for call in executor.calls] == ["get_product_spec"]
    assert result.observations[0].safe_error is not None
    assert result.observations[0].safe_error.code == "AMBIGUOUS_PRODUCT"


@pytest.mark.asyncio
async def test_denied_tool_result_cannot_become_answered() -> None:
    executor = FakeBusinessExecutor(
        {
            "search_inventory": [
                error_envelope(
                    "search_inventory",
                    code="FORBIDDEN",
                    message="当前账号无权访问该市场数据",
                    field_name="market_code",
                )
            ]
        }
    )
    provider = ScriptedDecisionProvider(
        [
            execute(
                "search_inventory",
                {"sku": "LR-TL-MUSH-OR01", "market_code": "FR"},
            ),
            AgentDecision(
                action=CannotCompleteAction(
                    public_summary="当前账号无权访问法国市场数据。",
                    business_outcome="denied",
                )
            ),
        ]
    )

    result = await worker(provider, executor).run(
        handoff(
            goal="查询LR-TL-MUSH-OR01在法国市场的库存",
            public_context={"sku": "LR-TL-MUSH-OR01", "market_code": "FR"},
        ),
        execution(),
    )

    assert result.execution_status == "completed"
    assert result.business_outcome == "denied"
    assert result.evidence_ids == []
    assert result.safe_errors[0].code == "FORBIDDEN"


@pytest.mark.asyncio
async def test_timeout_observation_ends_worker_without_another_model_decision() -> None:
    executor = FakeBusinessExecutor(
        {
            "search_inventory": [
                error_envelope(
                    "search_inventory",
                    code="DATABASE_TIMEOUT",
                    message="数据库查询超时，请稍后重试",
                )
            ]
        }
    )
    provider = ScriptedDecisionProvider(
        [
            execute(
                "search_inventory",
                {"sku": "LR-TL-MUSH-OR01", "market_code": "DE"},
            )
        ]
    )

    result = await worker(provider, executor).run(
        handoff(
            goal="查询LR-TL-MUSH-OR01在德国市场的库存",
            public_context={"sku": "LR-TL-MUSH-OR01", "market_code": "DE"},
        ),
        execution(),
    )

    assert result.execution_status == "failed"
    assert result.business_outcome == "timed_out"
    assert result.observations[0].status == "timeout"
    assert result.safe_errors[0].code == "DATABASE_TIMEOUT"
    assert len(provider.requests) == 1


@pytest.mark.asyncio
async def test_unsupported_request_calls_no_tool() -> None:
    executor = FakeBusinessExecutor({})
    provider = ScriptedDecisionProvider(
        [
            AgentDecision(
                action=CannotCompleteAction(
                    public_summary="Business Worker不支持修改库存。",
                    business_outcome="unsupported",
                )
            )
        ]
    )

    result = await worker(provider, executor).run(
        handoff(goal="把库存改成999", public_context={"operation": "write"}),
        execution(),
    )

    assert result.business_outcome == "unsupported"
    assert executor.calls == []
    assert result.observations == []


@pytest.mark.asyncio
async def test_invalid_arguments_unknown_capability_and_forged_evidence_are_rejected() -> (
    None
):
    cases = (
        execute("get_product_spec", {"wrong": "value"}),
        execute("search_knowledge", {"query": "越权"}),
        AgentDecision(
            action=FinishAction(
                public_summary="伪造Evidence。",
                business_outcome="answered",
                evidence_ids=[FORGED_EVIDENCE_ID],
            )
        ),
    )
    for decision in cases:
        executor = FakeBusinessExecutor({})
        result = await worker(
            ScriptedDecisionProvider([decision]),
            executor,
        ).run(handoff(), execution())

        assert result.execution_status == "failed"
        assert result.business_outcome == "system_error"
        assert result.safe_errors[0].code == "PROVIDER_ERROR"
        assert executor.calls == []


@pytest.mark.asyncio
async def test_failed_worker_drops_evidence_references_rolled_back_by_runtime() -> None:
    executor = FakeBusinessExecutor({"search_inventory": [inventory_envelope()]})
    provider = ScriptedDecisionProvider(
        [
            execute(
                "search_inventory",
                {"sku": "LR-TL-MUSH-OR01", "market_code": "DE"},
            ),
            AgentDecision(
                action=FinishAction(
                    public_summary="尝试加入伪造Evidence。",
                    business_outcome="answered",
                    evidence_ids=[EVIDENCE_ID, FORGED_EVIDENCE_ID],
                )
            ),
        ]
    )

    result = await worker(provider, executor).run(
        handoff(
            goal="查询LR-TL-MUSH-OR01在德国市场的库存",
            public_context={"sku": "LR-TL-MUSH-OR01", "market_code": "DE"},
        ),
        execution(),
    )

    assert result.execution_status == "failed"
    assert result.safe_errors[0].code == "PROVIDER_ERROR"
    assert result.evidence_ids == []
    assert result.observations[0].evidence_ids == []


@pytest.mark.asyncio
async def test_resolved_sku_cannot_be_replaced_and_repeated_action_stops() -> None:
    product_action = execute("get_product_spec", {"product_query": "蘑菇灯"})
    wrong_sku_executor = FakeBusinessExecutor(
        {"get_product_spec": [product_envelope()]}
    )
    wrong_sku = await worker(
        ScriptedDecisionProvider(
            [
                product_action,
                execute(
                    "search_inventory",
                    {"sku": "WRONG-SKU", "market_code": "DE"},
                ),
            ]
        ),
        wrong_sku_executor,
    ).run(handoff(), execution())
    assert wrong_sku.execution_status == "failed"
    assert wrong_sku.safe_errors[0].code == "PROVIDER_ERROR"
    assert [call.capability_id for call in wrong_sku_executor.calls] == [
        "get_product_spec"
    ]

    repeated_executor = FakeBusinessExecutor(
        {"get_product_spec": [product_envelope(), product_envelope()]}
    )
    repeated = await worker(
        ScriptedDecisionProvider([product_action, product_action]),
        repeated_executor,
    ).run(handoff(), execution())
    assert repeated.execution_status == "failed"
    assert repeated.safe_errors[0].code == "BUDGET_EXCEEDED"
    assert len(repeated_executor.calls) == 1


@pytest.mark.asyncio
async def test_decision_limit_is_terminal_and_preserves_safe_observations() -> None:
    executor = FakeBusinessExecutor({"get_product_spec": [product_envelope()]})
    result = await worker(
        ScriptedDecisionProvider(
            [execute("get_product_spec", {"product_query": "蘑菇灯"})]
        ),
        executor,
        max_decisions=1,
    ).run(handoff(), execution())

    assert result.execution_status == "failed"
    assert result.business_outcome == "system_error"
    assert result.safe_errors[0].code == "BUDGET_EXCEEDED"
    assert len(result.observations) == 1


def test_worker_module_does_not_import_old_inventory_graph_or_knowledge_stack() -> None:
    path = ROOT / "app/agents/workers/business_data.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    assert "app.agents.graphs.inventory_query" not in imports
    assert not {
        name
        for name in imports
        if name.startswith(("app.services.knowledge", "app.tools.search_knowledge"))
    }


def test_worker_guardrails_are_strict_and_bounded() -> None:
    assert BusinessWorkerGuardrails().max_decisions == 4
    with pytest.raises(ValueError):
        BusinessWorkerGuardrails(max_decisions=0)

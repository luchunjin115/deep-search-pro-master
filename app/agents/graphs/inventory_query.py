"""Bounded LangGraph workflow for the M1 inventory-query vertical slice."""

from __future__ import annotations

from typing import Literal, Protocol, cast

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from sqlalchemy.orm import Session

from app.agents.state import (
    AgentTerminalStatus,
    InventoryAgentResult,
    InventoryGraphState,
    InventoryNodeName,
    InventoryQueryInput,
)
from app.core.errors import (
    AgentWorkflowError,
    ApplicationError,
    BudgetExceededError,
    ProviderError,
    ProviderOutputError,
    ToolExecutionError,
)
from app.llm.provider import ModelProvider
from app.llm.schemas import (
    GetProductSpecToolCall,
    SearchInventoryToolCall,
    ToolCallProposal,
    ToolDecisionRequest,
)
from app.runtime.budget import ExecutionBudget
from app.runtime.context import RunContext
from app.runtime.executor import HarnessExecutor
from app.runtime.permissions import PermissionGuard
from app.runtime.trace import RunTrace, TraceRecorder
from app.schemas.common import ErrorDetail, ToolEnvelope, ToolName
from app.schemas.inventory import InventoryResult, SearchInventoryInput
from app.schemas.product import GetProductSpecInput, ProductSpecResult
from app.services.inventory import InventoryService
from app.services.product import ProductSpecService
from app.tools.get_product_spec import GetProductSpecTool
from app.tools.registry import ToolRegistry
from app.tools.search_inventory import SearchInventoryTool

GraphBranch = Literal["continue", "error"]
ExecutionBranch = Literal["product_resolved", "inventory_found", "error"]


class InventoryGraphRuntime(Protocol):
    """Narrow runtime used by graph nodes and replaceable in deterministic tests."""

    async def propose(
        self,
        question: str,
        resolved_sku: str | None,
    ) -> ToolCallProposal: ...

    def get_product_spec(
        self,
        arguments: GetProductSpecInput,
    ) -> ToolEnvelope[ProductSpecResult]: ...

    def search_inventory(
        self,
        arguments: SearchInventoryInput,
    ) -> ToolEnvelope[InventoryResult]: ...


class ControlledInventoryRuntime:
    """Connect graph decisions to budgeted Provider and Harness-backed Tools."""

    def __init__(
        self,
        *,
        provider: ModelProvider,
        harness: HarnessExecutor,
        registry: ToolRegistry,
        product_tool: GetProductSpecTool,
        inventory_tool: SearchInventoryTool,
    ) -> None:
        self._provider = provider
        self._harness = harness
        self._registry = registry
        self._product_tool = product_tool
        self._inventory_tool = inventory_tool

    async def propose(
        self,
        question: str,
        resolved_sku: str | None,
    ) -> ToolCallProposal:
        tool_names = (
            ("search_inventory",)
            if resolved_sku is not None
            else ("get_product_spec", "search_inventory")
        )
        self._harness.reserve_model_call()
        return await self._provider.propose_tool_call(
            ToolDecisionRequest(
                question=question,
                available_tools=self._registry.model_specs(tool_names),
                resolved_sku=resolved_sku,
            )
        )

    def get_product_spec(
        self,
        arguments: GetProductSpecInput,
    ) -> ToolEnvelope[ProductSpecResult]:
        return self._product_tool.invoke(arguments)

    def search_inventory(
        self,
        arguments: SearchInventoryInput,
    ) -> ToolEnvelope[InventoryResult]:
        return self._inventory_tool.invoke(arguments)


def build_inventory_query_graph(
    runtime: InventoryGraphRuntime,
) -> CompiledStateGraph[
    InventoryGraphState, None, InventoryGraphState, InventoryGraphState
]:
    """Compile the exact five-node graph authorized for M1."""

    graph = StateGraph(InventoryGraphState)

    async def propose_next_tool(state: InventoryGraphState) -> InventoryGraphState:
        history = _append_history(state, "propose_next_tool")
        try:
            proposal = await runtime.propose(
                state["question"],
                state.get("resolved_sku"),
            )
        except ApplicationError as error:
            return _error_update(history, error, state.get("tool_names", []))
        return {"proposal": proposal, "node_history": history}

    def validate_proposal(state: InventoryGraphState) -> InventoryGraphState:
        history = _append_history(state, "validate_proposal")
        proposal = state.get("proposal")
        resolved_sku = state.get("resolved_sku")
        tool_names = state.get("tool_names", [])
        if proposal is None or proposal.name in tool_names:
            return _error_update(history, ProviderOutputError(), tool_names)
        if resolved_sku is None:
            if isinstance(proposal, GetProductSpecToolCall):
                return {"node_history": history}
            if isinstance(proposal, SearchInventoryToolCall) and (
                proposal.arguments.sku in state["question"].upper()
            ):
                return {"node_history": history}
            return _error_update(history, ProviderOutputError(), tool_names)
        if not isinstance(proposal, SearchInventoryToolCall):
            return _error_update(history, ProviderOutputError(), tool_names)
        if proposal.arguments.sku != resolved_sku:
            return _error_update(history, ProviderOutputError(), tool_names)
        return {"node_history": history}

    def execute_tool(state: InventoryGraphState) -> InventoryGraphState:
        history = _append_history(state, "execute_tool")
        proposal = state["proposal"]
        tool_names = [*state.get("tool_names", []), proposal.name]
        if isinstance(proposal, GetProductSpecToolCall):
            product_envelope = runtime.get_product_spec(proposal.arguments)
            if product_envelope.status == "error":
                return _envelope_error_update(history, tool_names, product_envelope)
            if product_envelope.data is None:
                return _error_update(history, ToolExecutionError(), tool_names)
            return {
                "product": product_envelope.data,
                "resolved_sku": product_envelope.data.sku,
                "tool_names": tool_names,
                "node_history": history,
            }

        inventory_envelope = runtime.search_inventory(proposal.arguments)
        if inventory_envelope.status == "error":
            return _envelope_error_update(history, tool_names, inventory_envelope)
        if inventory_envelope.data is None or not inventory_envelope.evidence_ids:
            return _error_update(history, ToolExecutionError(), tool_names)
        return {
            "inventory": inventory_envelope.data,
            "evidence_ids": inventory_envelope.evidence_ids,
            "tool_names": tool_names,
            "node_history": history,
        }

    def compose_answer(state: InventoryGraphState) -> InventoryGraphState:
        history = _append_history(state, "compose_answer")
        inventory = state["inventory"]
        answer = (
            f"【合成演示数据】{inventory.product_name}（SKU：{inventory.sku}）在"
            f"{inventory.warehouse_name}（{inventory.warehouse_code}）的可售库存为"
            f"{inventory.available}件；在库{inventory.on_hand}件，预留"
            f"{inventory.reserved}件，不可售{inventory.unsellable}件，在途"
            f"{inventory.inbound}件，安全库存{inventory.safety_stock}件。"
            f"数据时间：{inventory.snapshot_at.isoformat()}。"
            "以上数据来自PostgreSQL合成演示库存Evidence。"
        )
        return {"answer": answer, "node_history": history}

    def compose_error(state: InventoryGraphState) -> InventoryGraphState:
        history = _append_history(state, "compose_error")
        error = state["error"]
        answer = error.message
        if error.code == "PROVIDER_ERROR" and error.field == "message":
            answer = (
                "M1当前只支持商品规格与DE/FR库存查询。"
                "请明确提供商品名称或SKU，以及德国或法国市场。"
            )
        return {"answer": answer, "node_history": history}

    graph.add_node("propose_next_tool", propose_next_tool)
    graph.add_node("validate_proposal", validate_proposal)
    graph.add_node("execute_tool", execute_tool)
    graph.add_node("compose_answer", compose_answer)
    graph.add_node("compose_error", compose_error)
    graph.add_edge(START, "propose_next_tool")
    graph.add_conditional_edges(
        "propose_next_tool",
        _proposal_branch,
        {"continue": "validate_proposal", "error": "compose_error"},
    )
    graph.add_conditional_edges(
        "validate_proposal",
        _proposal_branch,
        {"continue": "execute_tool", "error": "compose_error"},
    )
    graph.add_conditional_edges(
        "execute_tool",
        _execution_branch,
        {
            "product_resolved": "propose_next_tool",
            "inventory_found": "compose_answer",
            "error": "compose_error",
        },
    )
    graph.add_edge("compose_answer", END)
    graph.add_edge("compose_error", END)
    return graph.compile()


class InventoryQueryAgent:
    """Own one audited graph run while leaving successful commit to the API layer."""

    def __init__(
        self,
        *,
        context: RunContext,
        provider: ModelProvider,
        budget: ExecutionBudget,
        registry: ToolRegistry,
        permission_guard: PermissionGuard,
        trace_recorder: TraceRecorder,
        product_service: ProductSpecService,
        inventory_service: InventoryService,
        business_session: Session,
    ) -> None:
        self._context = context
        self._provider = provider
        self._budget = budget
        self._registry = registry
        self._permission_guard = permission_guard
        self._trace_recorder = trace_recorder
        self._product_service = product_service
        self._inventory_service = inventory_service
        self._business_session = business_session

    async def run(self, request: InventoryQueryInput) -> InventoryAgentResult:
        """Run the compiled graph, finish Trace, and sanitize every terminal path."""

        run = self._trace_recorder.start_run(self._context, "inventory_query")
        harness = HarnessExecutor(
            context=self._context,
            run=run,
            budget=self._budget,
            registry=self._registry,
            permission_guard=self._permission_guard,
            trace_recorder=self._trace_recorder,
        )
        runtime = ControlledInventoryRuntime(
            provider=self._provider,
            harness=harness,
            registry=self._registry,
            product_tool=GetProductSpecTool(harness, self._product_service),
            inventory_tool=SearchInventoryTool(harness, self._inventory_service),
        )
        graph = build_inventory_query_graph(runtime)

        try:
            final_state = cast(
                InventoryGraphState,
                await graph.ainvoke(
                    InventoryGraphState(
                        question=request.question,
                        tool_names=[],
                        evidence_ids=[],
                        node_history=[],
                    )
                ),
            )
        except ApplicationError as caught_error:
            return self._unexpected_failure(run, caught_error)
        except Exception:  # noqa: BLE001 - graph boundary must never leak internals
            return self._unexpected_failure(run, AgentWorkflowError())

        final_error = final_state.get("error")
        if final_error is not None:
            self._business_session.rollback()
            status = final_state.get("terminal_status", "failed")
            self._trace_recorder.finish_run(
                run,
                status,
                _application_error(final_error),
            )
            return InventoryAgentResult(
                status=status,
                answer=final_state["answer"],
                trace_id=self._context.trace_id,
                agent_run_id=run.id,
                duration_ms=self._budget.snapshot().elapsed_ms,
                tool_names=final_state.get("tool_names", []),
                error=final_error,
                node_history=final_state["node_history"],
            )

        inventory = final_state["inventory"]
        evidence_ids = final_state["evidence_ids"]
        self._trace_recorder.finish_run(run, "completed")
        return InventoryAgentResult(
            status="completed",
            answer=final_state["answer"],
            trace_id=self._context.trace_id,
            agent_run_id=run.id,
            duration_ms=self._budget.snapshot().elapsed_ms,
            tool_names=final_state["tool_names"],
            evidence_ids=evidence_ids,
            inventory=inventory,
            node_history=final_state["node_history"],
        )

    def _unexpected_failure(
        self,
        run: RunTrace,
        error: ApplicationError,
    ) -> InventoryAgentResult:
        self._business_session.rollback()
        status = _status_for_application_error(error)
        self._trace_recorder.finish_run(run, status, error)
        return InventoryAgentResult(
            status=status,
            answer=error.message,
            trace_id=self._context.trace_id,
            agent_run_id=run.id,
            duration_ms=self._budget.snapshot().elapsed_ms,
            error=error.to_detail(),
            node_history=["compose_error"],
        )


def _append_history(
    state: InventoryGraphState,
    node: InventoryNodeName,
) -> list[InventoryNodeName]:
    return [*state.get("node_history", []), node]


def _error_update(
    history: list[InventoryNodeName],
    error: ApplicationError,
    tool_names: list[ToolName] | None = None,
) -> InventoryGraphState:
    return {
        "error": error.to_detail(),
        "terminal_status": _status_for_application_error(error),
        "tool_names": tool_names or [],
        "evidence_ids": [],
        "node_history": history,
    }


def _envelope_error_update(
    history: list[InventoryNodeName],
    tool_names: list[ToolName],
    envelope: ToolEnvelope[ProductSpecResult] | ToolEnvelope[InventoryResult],
) -> InventoryGraphState:
    if envelope.error is None:
        return _error_update(history, ToolExecutionError(), tool_names)
    return {
        "error": envelope.error,
        "terminal_status": _status_for_error_detail(envelope.error),
        "tool_names": tool_names,
        "evidence_ids": [],
        "node_history": history,
    }


def _proposal_branch(state: InventoryGraphState) -> GraphBranch:
    return "error" if "error" in state else "continue"


def _execution_branch(state: InventoryGraphState) -> ExecutionBranch:
    if "error" in state:
        return "error"
    if "inventory" in state:
        return "inventory_found"
    return "product_resolved"


def _status_for_application_error(error: ApplicationError) -> AgentTerminalStatus:
    if error.code == "FORBIDDEN":
        return "denied"
    if error.code == "DATABASE_TIMEOUT":
        return "timed_out"
    if isinstance(error, ProviderError) and error.reason == "timeout":
        return "timed_out"
    if isinstance(error, BudgetExceededError) and error.reason in (
        "total_timeout",
        "tool_timeout",
    ):
        return "timed_out"
    return "failed"


def _status_for_error_detail(error: ErrorDetail) -> AgentTerminalStatus:
    if error.code == "FORBIDDEN":
        return "denied"
    if error.code == "DATABASE_TIMEOUT":
        return "timed_out"
    if error.code == "BUDGET_EXCEEDED" and (
        "超过M1允许时间" in error.message or "总时间" in error.message
    ):
        return "timed_out"
    return "failed"


def _application_error(detail: ErrorDetail) -> ApplicationError:
    return ApplicationError(
        detail.code,
        detail.message,
        retryable=detail.retryable,
        field=detail.field,
    )

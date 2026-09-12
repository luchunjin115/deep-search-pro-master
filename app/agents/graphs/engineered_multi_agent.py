"""Bounded Supervisor LangGraph with an injected Worker seam."""

from __future__ import annotations

import asyncio
import json
from typing import Literal, TypedDict, cast
from uuid import UUID

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agents.engineered_state import EngineeredAgentState
from app.agents.supervisor import (
    SupervisorGuardrails,
    SupervisorRequest,
    WorkerInvoker,
)
from app.capabilities.contracts import CapabilityResolution
from app.core.errors import (
    AgentProviderOutputError,
    agent_provider_output_stop_reason,
)
from app.llm.agent_evidence import validate_answer_citations
from app.llm.agent_provider import EngineeredAgentProvider
from app.llm.agent_schemas import (
    AgentAnswer,
    AnswerRequest,
    DecisionRequest,
    HandoffDraft,
    HandoffRequest,
    PlannerRequest,
)
from app.schemas.agent import (
    MAX_ARTIFACT_IDS,
    MAX_EVIDENCE_IDS,
    AgentAction,
    AgentTask,
    AskUserAction,
    BusinessOutcome,
    CannotCompleteAction,
    DelegateTaskAction,
    ExecuteCapabilityAction,
    ExecutionStatus,
    FinishAction,
    PublicSummary,
    ResourceUsage,
    ShortText,
    TaskId,
    TaskPlan,
    WorkerObservation,
    WorkerResult,
)

SupervisorNodeName = Literal[
    "plan",
    "decide",
    "prepare_handoff",
    "invoke_worker",
    "compose_answer",
]
ResumeMode = Literal["continue", "replan"]
PlanBranch = Literal["decide", "answer", "end"]
DecisionBranch = Literal["handoff", "end"]
WorkerBranch = Literal["decide", "answer", "end"]


class SupervisorGraphState(TypedDict, total=False):
    """Serializable, public-safe values used only by the in-memory control graph."""

    request: SupervisorRequest
    plan: TaskPlan
    execution_status: ExecutionStatus
    business_outcome: BusinessOutcome | None
    current_task_id: TaskId | None
    current_task_ids: list[TaskId]
    pending_action: AgentAction | None
    pending_actions: list[DelegateTaskAction]
    handoff_draft: HandoffDraft | None
    handoff_drafts: list[HandoffDraft]
    observations: list[WorkerObservation]
    worker_results: list[WorkerResult]
    evidence_ids: list[UUID]
    artifact_ids: list[UUID]
    unknowns: list[ShortText]
    public_summary: PublicSummary | None
    stop_reason: ShortText | None
    resource_usage: ResourceUsage
    decision_count: int
    last_action_signature: str | None
    identical_action_count: int
    node_history: list[SupervisorNodeName]
    resume_mode: ResumeMode | None


def _zero_usage() -> ResourceUsage:
    return ResourceUsage(
        model_calls=0,
        tool_calls=0,
        input_tokens=0,
        output_tokens=0,
        duration_ms=0,
    )


def initial_supervisor_graph_state(
    request: SupervisorRequest,
) -> SupervisorGraphState:
    """Create the only supported initial state for this graph."""

    return SupervisorGraphState(
        request=request,
        execution_status="running",
        business_outcome=None,
        current_task_id=None,
        current_task_ids=[],
        pending_action=None,
        pending_actions=[],
        handoff_draft=None,
        handoff_drafts=[],
        observations=[],
        worker_results=[],
        evidence_ids=[],
        artifact_ids=[],
        unknowns=[],
        public_summary=None,
        stop_reason=None,
        resource_usage=_zero_usage(),
        decision_count=0,
        last_action_signature=None,
        identical_action_count=0,
        node_history=[],
        resume_mode=None,
    )


def resumed_supervisor_graph_state(
    request: SupervisorRequest,
    checkpoint: EngineeredAgentState,
    *,
    replan: bool,
) -> SupervisorGraphState:
    """Project one claimed checkpoint back into the bounded in-memory graph."""

    if checkpoint.run_id != request.run_id or checkpoint.goal != request.goal:
        raise ValueError("resume request does not match its checkpoint")
    if checkpoint.execution_status != "running" or checkpoint.plan is None:
        raise ValueError("only a claimed active checkpoint can resume")
    return SupervisorGraphState(
        request=request,
        plan=checkpoint.plan.model_copy(deep=True),
        execution_status="running",
        business_outcome=None,
        current_task_id=checkpoint.current_task_id,
        current_task_ids=(
            [checkpoint.current_task_id]
            if checkpoint.current_task_id is not None
            else []
        ),
        pending_action=None,
        pending_actions=[],
        handoff_draft=None,
        handoff_drafts=[],
        observations=[] if replan else list(checkpoint.observations),
        worker_results=[] if replan else list(checkpoint.worker_results),
        evidence_ids=[] if replan else list(checkpoint.evidence_ids),
        artifact_ids=[] if replan else list(checkpoint.artifact_ids),
        unknowns=[] if replan else list(checkpoint.unknowns),
        public_summary=None,
        stop_reason=None,
        resource_usage=checkpoint.resource_usage,
        decision_count=0,
        last_action_signature=None,
        identical_action_count=0,
        node_history=[],
        resume_mode="replan" if replan else "continue",
    )


def engineered_state_from_graph(state: SupervisorGraphState) -> EngineeredAgentState:
    """Validate graph output against the checkpoint-safe state contract."""

    request = state["request"]
    return EngineeredAgentState(
        run_id=request.run_id,
        goal=request.goal,
        public_context=request.public_context,
        plan=state.get("plan"),
        execution_status=state["execution_status"],
        business_outcome=state.get("business_outcome"),
        current_task_id=state.get("current_task_id"),
        pending_action=state.get("pending_action"),
        observations=state.get("observations", []),
        worker_results=state.get("worker_results", []),
        evidence_ids=state.get("evidence_ids", []),
        artifact_ids=state.get("artifact_ids", []),
        unknowns=state.get("unknowns", []),
        public_summary=state.get("public_summary"),
        stop_reason=state.get("stop_reason"),
        resource_usage=state.get("resource_usage", _zero_usage()),
    )


def build_engineered_multi_agent_graph(
    provider: EngineeredAgentProvider,
    worker: WorkerInvoker,
    guardrails: SupervisorGuardrails,
) -> CompiledStateGraph[
    SupervisorGraphState,
    None,
    SupervisorGraphState,
    SupervisorGraphState,
]:
    """Compile the five-node graph with bounded read-only Worker fan-out."""

    graph = StateGraph(SupervisorGraphState)

    async def plan(state: SupervisorGraphState) -> SupervisorGraphState:
        history = _append_history(state, "plan")
        request = state["request"]
        if state.get("resume_mode") == "continue":
            try:
                _validate_resumed_plan(state["plan"], request)
            except Exception:  # noqa: BLE001 - only a safe failure leaves the graph
                return _failure_update(
                    state,
                    history=history,
                    stop_reason="invalid_resumed_plan",
                )
            return {
                "execution_status": "running",
                "node_history": history,
            }

        usage = _add_usage(state["resource_usage"], model_calls=1)
        try:
            task_plan = await provider.create_plan(
                PlannerRequest(
                    goal=request.goal,
                    available_workers=request.available_workers,
                    public_context=request.public_context,
                )
            )
            _validate_supervisor_plan(task_plan, request)
        except AgentProviderOutputError as error:
            return _failure_update(
                state,
                history=history,
                usage=usage,
                stop_reason=error.stop_reason,
            )
        except Exception:  # noqa: BLE001 - provider details stay behind this boundary
            return _failure_update(
                state,
                history=history,
                usage=usage,
                stop_reason="invalid_plan",
            )
        return {
            "plan": task_plan,
            "execution_status": "running",
            "resource_usage": usage,
            "node_history": history,
        }

    async def decide(state: SupervisorGraphState) -> SupervisorGraphState:
        history = _append_history(state, "decide")
        if state["decision_count"] >= guardrails.max_decisions:
            return _failure_update(
                state,
                history=history,
                stop_reason="decision_limit",
            )

        remaining_decisions = guardrails.max_decisions - state["decision_count"]
        task_ids = _next_runnable_task_ids(
            state["plan"],
            state["request"],
            maximum=min(guardrails.max_parallel_workers, remaining_decisions),
        )
        if not task_ids:
            return _failure_update(
                state,
                history=history,
                stop_reason="no_runnable_task",
            )
        usage = state["resource_usage"]
        decision_count = state["decision_count"]
        last_signature = state.get("last_action_signature")
        identical_count = state["identical_action_count"]
        actions: list[DelegateTaskAction] = []
        for task_id in task_ids:
            usage = _add_usage(usage, model_calls=1)
            try:
                decision = await provider.choose_action(
                    DecisionRequest(
                        plan=state["plan"],
                        active_task_id=task_id,
                        available_capabilities=_available_worker_resolution(
                            state["request"]
                        ),
                        public_context=state["request"].public_context,
                        observations=tuple(state["observations"][-16:]),
                        worker_results=tuple(state["worker_results"]),
                    )
                )
                _validate_supervisor_action(
                    decision.action,
                    task_id,
                    state["plan"],
                    state["request"],
                )
            except AgentProviderOutputError as error:
                return _failure_update(
                    state,
                    history=history,
                    usage=usage,
                    stop_reason=error.stop_reason,
                )
            except Exception:  # noqa: BLE001 - provider details stay private
                return _failure_update(
                    state,
                    history=history,
                    usage=usage,
                    stop_reason="invalid_decision",
                )

            action = decision.action
            signature = _action_signature(action)
            identical_count = identical_count + 1 if signature == last_signature else 1
            decision_count += 1
            if identical_count > guardrails.max_identical_actions:
                return _failure_update(
                    state,
                    history=history,
                    usage=usage,
                    stop_reason="repeated_action",
                    decision_count=decision_count,
                )
            last_signature = signature
            if not isinstance(action, DelegateTaskAction):
                return {
                    "current_task_ids": [],
                    "pending_actions": [],
                    "handoff_drafts": [],
                    "resource_usage": usage,
                    "decision_count": decision_count,
                    "last_action_signature": last_signature,
                    "identical_action_count": identical_count,
                    "node_history": history,
                } | _terminal_action_update(state["plan"], task_id, action)
            actions.append(action)

        running_plan = state["plan"]
        for task_id in task_ids:
            running_plan = _set_task_status(running_plan, task_id, "running")
        return {
            "plan": running_plan,
            "current_task_id": task_ids[0],
            "current_task_ids": task_ids,
            "pending_action": actions[0],
            "pending_actions": actions,
            "resource_usage": usage,
            "decision_count": decision_count,
            "last_action_signature": last_signature,
            "identical_action_count": identical_count,
            "node_history": history,
        }

    async def prepare_handoff(state: SupervisorGraphState) -> SupervisorGraphState:
        history = _append_history(state, "prepare_handoff")
        pending_action = state.get("pending_action")
        actions = state.get("pending_actions") or (
            [pending_action] if isinstance(pending_action, DelegateTaskAction) else []
        )
        if not actions:
            return _failure_update(
                state,
                history=history,
                stop_reason="invalid_handoff_action",
            )
        usage = state["resource_usage"]
        drafts: list[HandoffDraft] = []
        for action in actions:
            usage = _add_usage(usage, model_calls=1)
            try:
                draft = await provider.prepare_handoff(
                    HandoffRequest(
                        plan=state["plan"],
                        delegation=action,
                        available_workers=_available_worker_resolution(
                            state["request"]
                        ),
                        public_context=state["request"].public_context,
                        observations=tuple(state["observations"][-16:]),
                        worker_results=tuple(state["worker_results"]),
                    )
                )
                if (
                    draft.task_id != action.task_id
                    or draft.target_worker != action.target_worker
                ):
                    raise ValueError("Handoff draft changed delegation identity")
            except AgentProviderOutputError as error:
                return _failure_update(
                    state,
                    history=history,
                    usage=usage,
                    stop_reason=error.stop_reason,
                )
            except Exception:  # noqa: BLE001 - provider details stay private
                return _failure_update(
                    state,
                    history=history,
                    usage=usage,
                    stop_reason="invalid_handoff",
                )
            drafts.append(draft)
        return {
            "handoff_draft": drafts[0],
            "handoff_drafts": drafts,
            "resource_usage": usage,
            "node_history": history,
        }

    async def invoke_worker(state: SupervisorGraphState) -> SupervisorGraphState:
        history = _append_history(state, "invoke_worker")
        handoff_draft = state.get("handoff_draft")
        drafts = state.get("handoff_drafts") or (
            [handoff_draft] if handoff_draft is not None else []
        )
        if not drafts:
            return _failure_update(
                state,
                history=history,
                stop_reason="missing_handoff",
            )
        try:
            batch_results = await asyncio.gather(
                *(worker.invoke(draft) for draft in drafts),
                return_exceptions=True,
            )
            failure = next(
                (item for item in batch_results if isinstance(item, BaseException)),
                None,
            )
            if failure is not None:
                if isinstance(failure, AgentProviderOutputError):
                    raise failure
                raise RuntimeError("Worker batch failed")
            invoked = [cast(WorkerResult, item) for item in batch_results]
            for draft, result in zip(drafts, invoked, strict=True):
                _validate_worker_result(result, draft, state["plan"])
        except AgentProviderOutputError as error:
            return _failure_update(
                state,
                history=history,
                stop_reason=error.stop_reason,
            )
        except Exception:  # noqa: BLE001 - Fake Worker details must stay private
            return _failure_update(
                state,
                history=history,
                stop_reason="worker_failure",
            )

        usage = state["resource_usage"]
        plan_with_status = state["plan"]
        results = state["worker_results"]
        observations = state["observations"]
        evidence_ids = state["evidence_ids"]
        artifact_ids = state["artifact_ids"]
        unknowns = state["unknowns"]
        for result in invoked:
            usage = _add_usage(usage, other=result.resource_usage)
            plan_with_status = _set_task_status(
                plan_with_status, result.task_id, result.execution_status
            )
            results = _upsert_worker_result(results, result)
            observations = _merge_observations(observations, result.observations)
            evidence_ids = _merge_ids(
                evidence_ids, result.evidence_ids, MAX_EVIDENCE_IDS
            )
            artifact_ids = _merge_ids(
                artifact_ids, result.artifact_ids, MAX_ARTIFACT_IDS
            )
            unknowns = _merge_text(unknowns, result.unknowns, 12)

        active_results = [
            result
            for result in invoked
            if result.execution_status in {"waiting", "running", "waiting_user"}
        ]
        update: SupervisorGraphState = {
            "plan": plan_with_status,
            "current_task_id": (active_results[0].task_id if active_results else None),
            "current_task_ids": [result.task_id for result in active_results],
            "pending_action": None,
            "pending_actions": [],
            "handoff_draft": None,
            "handoff_drafts": [],
            "observations": observations,
            "worker_results": results,
            "evidence_ids": evidence_ids,
            "artifact_ids": artifact_ids,
            "unknowns": unknowns,
            "public_summary": invoked[-1].public_summary,
            "resource_usage": usage,
            "node_history": history,
        }
        waiting_user = next(
            (item for item in invoked if item.execution_status == "waiting_user"),
            None,
        )
        if waiting_user is not None:
            return update | {
                "execution_status": "waiting_user",
                "business_outcome": None,
                "current_task_id": waiting_user.task_id,
                "current_task_ids": [waiting_user.task_id],
                "public_summary": waiting_user.public_summary,
                "stop_reason": "waiting_for_user",
            }
        failed = next(
            (item for item in invoked if item.execution_status == "failed"),
            None,
        )
        if failed is not None and not _can_compose_partial(plan_with_status, results):
            diagnostic_stage = next(
                (
                    error.diagnostic_stage
                    for error in failed.safe_errors
                    if error.diagnostic_stage is not None
                ),
                None,
            )
            return update | {
                "execution_status": "failed",
                "business_outcome": failed.business_outcome,
                "current_task_id": None,
                "current_task_ids": [],
                "public_summary": failed.public_summary,
                "stop_reason": (
                    agent_provider_output_stop_reason(diagnostic_stage)
                    if diagnostic_stage is not None
                    else "worker_failure"
                ),
            }
        if active_results:
            return update
        return update | {
            "last_action_signature": None,
            "identical_action_count": 0,
            "stop_reason": None,
        }

    async def compose_answer(state: SupervisorGraphState) -> SupervisorGraphState:
        history = _append_history(state, "compose_answer")
        refusal = _worker_evidence_refusal(state["worker_results"])
        if refusal is not None:
            return _terminal_action_update(
                state["plan"],
                state.get("current_task_id"),
                refusal,
            ) | {"node_history": history}
        usage = state["resource_usage"]
        try:
            answer_request = AnswerRequest(
                goal=state["request"].goal,
                public_context=state["request"].public_context,
                worker_results=tuple(state["worker_results"]),
            )
            answer = await provider.compose_answer(answer_request)
            validate_answer_citations(answer_request, answer)
            _validate_final_answer(answer, state["plan"], state["worker_results"])
        except AgentProviderOutputError as error:
            usage = _add_usage(
                usage,
                model_calls=_answer_model_call_count(provider),
            )
            return _failure_update(
                state,
                history=history,
                usage=usage,
                stop_reason=error.stop_reason,
            )
        except Exception:  # noqa: BLE001 - provider details stay behind this boundary
            usage = _add_usage(
                usage,
                model_calls=_answer_model_call_count(provider),
            )
            return _failure_update(
                state,
                history=history,
                usage=usage,
                stop_reason="invalid_answer",
            )
        usage = _add_usage(
            usage,
            model_calls=_answer_model_call_count(provider),
        )
        return _terminal_action_update(
            state["plan"],
            state.get("current_task_id"),
            answer.action,
        ) | {
            "resource_usage": usage,
            "node_history": history,
        }

    graph.add_node("plan", plan)
    graph.add_node("decide", decide)
    graph.add_node("prepare_handoff", prepare_handoff)
    graph.add_node("invoke_worker", invoke_worker)
    graph.add_node("compose_answer", compose_answer)
    graph.add_edge(START, "plan")
    graph.add_conditional_edges(
        "plan",
        _route_after_plan,
        {"decide": "decide", "answer": "compose_answer", "end": END},
    )
    graph.add_conditional_edges(
        "decide",
        _route_after_decision,
        {"handoff": "prepare_handoff", "end": END},
    )
    graph.add_conditional_edges(
        "prepare_handoff",
        _route_after_handoff,
        {"worker": "invoke_worker", "end": END},
    )
    graph.add_conditional_edges(
        "invoke_worker",
        _route_after_worker,
        {"decide": "decide", "answer": "compose_answer", "end": END},
    )
    graph.add_edge("compose_answer", END)
    return graph.compile()


def _route_after_plan(state: SupervisorGraphState) -> PlanBranch:
    if state["execution_status"] != "running":
        return "end"
    return "answer" if _is_direct_plan(state["plan"]) else "decide"


def _route_after_decision(state: SupervisorGraphState) -> DecisionBranch:
    if state["execution_status"] != "running":
        return "end"
    return "handoff"


def _route_after_handoff(state: SupervisorGraphState) -> Literal["worker", "end"]:
    if state["execution_status"] != "running":
        return "end"
    return "worker"


def _route_after_worker(state: SupervisorGraphState) -> WorkerBranch:
    if state["execution_status"] != "running":
        return "end"
    if all(
        task.execution_status in {"completed", "failed"} for task in state["plan"].tasks
    ):
        return "answer"
    return "decide"


def _can_compose_partial(
    plan: TaskPlan,
    results: list[WorkerResult],
) -> bool:
    if any(task.execution_status not in {"completed", "failed"} for task in plan.tasks):
        return False
    failed_tasks = [task for task in plan.tasks if task.execution_status == "failed"]
    if not failed_tasks or any(
        task.failure_impact == "blocks_dependents" for task in failed_tasks
    ):
        return False
    return any(
        result.execution_status == "completed"
        and result.business_outcome in {"answered", "partial"}
        and (
            result.business_result is not None
            or result.evidence_ids
            or result.artifact_ids
        )
        for result in results
    )


def _worker_evidence_refusal(
    results: list[WorkerResult],
) -> CannotCompleteAction | None:
    if not results or any(
        result.execution_status != "completed"
        or result.business_outcome not in {"no_evidence", "unsupported"}
        for result in results
    ):
        return None
    outcome: Literal["no_evidence", "unsupported"] = (
        "unsupported"
        if any(result.business_outcome == "unsupported" for result in results)
        else "no_evidence"
    )
    return CannotCompleteAction(
        public_summary="当前授权范围内未找到可支持回答的证据。",
        business_outcome=outcome,
    )


def _validate_supervisor_plan(plan: TaskPlan, request: SupervisorRequest) -> None:
    profiles = {item.worker.capability_id: item for item in request.available_workers}
    if any(item.execution_status != "waiting" for item in plan.tasks):
        raise ValueError("new plans must contain only waiting tasks")
    direct_tasks = [
        item
        for item in plan.tasks
        if item.assignment.status == "unassigned" and not item.required_capabilities
    ]
    if direct_tasks:
        if len(plan.tasks) != 1:
            raise ValueError("direct plans must contain exactly one task")
        return
    for item in plan.tasks:
        worker_id = item.assignment.worker_id
        if item.assignment.status != "assigned" or worker_id is None:
            raise ValueError("executable tasks require an assigned Worker")
        profile = profiles.get(worker_id)
        if profile is None:
            raise ValueError("assigned Worker is unavailable")
        allowed = {
            capability.capability_id for capability in profile.capabilities.capabilities
        }
        if not set(item.required_capabilities) <= allowed:
            raise ValueError("assigned Worker lacks a required capability")


def _validate_resumed_plan(plan: TaskPlan, request: SupervisorRequest) -> None:
    """Re-check only unfinished work against the current safe capability projection."""

    profiles = {item.worker.capability_id: item for item in request.available_workers}
    for task in plan.tasks:
        if task.execution_status in {"completed", "failed"}:
            continue
        if task.assignment.status == "unassigned":
            if task.required_capabilities:
                raise ValueError("unassigned resumed task cannot require capabilities")
            continue
        worker_id = task.assignment.worker_id
        profile = profiles.get(worker_id or "")
        if profile is None:
            raise ValueError("resumed Worker is no longer available")
        allowed = {
            capability.capability_id for capability in profile.capabilities.capabilities
        }
        if not set(task.required_capabilities) <= allowed:
            raise ValueError("resumed capability is no longer available")


def _validate_supervisor_action(
    action: AgentAction,
    task_id: TaskId,
    plan: TaskPlan,
    request: SupervisorRequest,
) -> None:
    if isinstance(action, ExecuteCapabilityAction):
        raise TypeError("Supervisor cannot execute Worker capabilities")
    if not isinstance(action, DelegateTaskAction):
        return
    if action.task_id != task_id:
        raise ValueError("delegation must target the active task")
    task = next(item for item in plan.tasks if item.task_id == task_id)
    if task.assignment.worker_id != action.target_worker:
        raise ValueError("delegation cannot override the planned Worker")
    profile = next(
        (
            item
            for item in request.available_workers
            if item.worker.capability_id == action.target_worker
        ),
        None,
    )
    if profile is None:
        raise ValueError("delegation target is unavailable")
    allowed = {item.capability_id for item in profile.capabilities.capabilities}
    if not set(task.required_capabilities) <= allowed:
        raise ValueError("delegation target lacks a required capability")


def _validate_worker_result(
    result: WorkerResult,
    draft: HandoffDraft,
    plan: TaskPlan,
) -> None:
    if result.task_id != draft.task_id or result.worker_id != draft.target_worker:
        raise ValueError("Worker result does not match its Handoff")
    task = next(item for item in plan.tasks if item.task_id == result.task_id)
    if task.assignment.worker_id != result.worker_id:
        raise ValueError("Worker result does not match the planned assignment")
    observation_evidence = {
        evidence_id
        for observation in result.observations
        for evidence_id in observation.evidence_ids
    }
    observation_artifacts = {
        artifact_id
        for observation in result.observations
        for artifact_id in observation.artifact_ids
    }
    if set(result.evidence_ids) != observation_evidence:
        raise ValueError("Worker result omitted or invented Observation Evidence")
    if not set(result.artifact_ids) <= observation_artifacts:
        raise ValueError("Worker result invented Observation Artifacts")
    requirement = task.evidence_requirement
    if (
        result.execution_status == "completed"
        and result.business_outcome == "answered"
        and requirement.required
        and len(result.evidence_ids) < requirement.minimum_count
    ):
        raise ValueError("Worker result lacks required Evidence")


def _validate_final_answer(
    answer: AgentAnswer,
    plan: TaskPlan,
    worker_results: list[WorkerResult],
) -> None:
    action = answer.action
    if not isinstance(action, FinishAction):
        return
    available_evidence = {
        evidence_id for result in worker_results for evidence_id in result.evidence_ids
    }
    available_artifacts = {
        artifact_id for result in worker_results for artifact_id in result.artifact_ids
    }
    if not set(action.evidence_ids) <= available_evidence:
        raise AgentProviderOutputError("evidence_reference_contract")
    if not set(action.artifact_ids) <= available_artifacts:
        raise AgentProviderOutputError("evidence_reference_contract")
    if action.business_outcome != "answered":
        return
    answer_ids = set(action.evidence_ids)
    results_by_task = {item.task_id: item for item in worker_results}
    for task in plan.tasks:
        requirement = task.evidence_requirement
        if not requirement.required:
            continue
        result = results_by_task.get(task.task_id)
        if result is None:
            raise AgentProviderOutputError("evidence_reference_contract")
        if (
            len(answer_ids.intersection(result.evidence_ids))
            < requirement.minimum_count
        ):
            raise AgentProviderOutputError("evidence_reference_contract")


def _is_direct_plan(plan: TaskPlan) -> bool:
    task = plan.tasks[0]
    return (
        len(plan.tasks) == 1
        and task.assignment.status == "unassigned"
        and not task.required_capabilities
    )


def _available_worker_resolution(request: SupervisorRequest) -> CapabilityResolution:
    return CapabilityResolution(
        capabilities=sorted(
            [item.worker.model_copy(deep=True) for item in request.available_workers],
            key=lambda item: item.capability_id,
        )
    )


def _next_runnable_task_ids(
    plan: TaskPlan,
    request: SupervisorRequest,
    *,
    maximum: int,
) -> list[TaskId]:
    """Select a stable, bounded set of independent read-only Worker tasks."""

    if maximum < 1:
        return []
    statuses = {item.task_id: item.execution_status for item in plan.tasks}
    ready = [
        task
        for task in plan.tasks
        if task.execution_status in {"waiting", "running"}
        and all(statuses[dependency] == "completed" for dependency in task.depends_on)
    ]
    if not ready:
        return []
    first = ready[0]
    selected = [first.task_id]
    if maximum == 1 or not _is_read_only_worker_task(first, request):
        return selected

    selected_workers = {first.assignment.worker_id}
    for task in ready[1:]:
        worker_id = task.assignment.worker_id
        if worker_id in selected_workers or not _is_read_only_worker_task(
            task, request
        ):
            continue
        selected.append(task.task_id)
        selected_workers.add(worker_id)
        if len(selected) == maximum:
            break
    return selected


def _is_read_only_worker_task(task: AgentTask, request: SupervisorRequest) -> bool:
    worker_id = task.assignment.worker_id
    if task.assignment.status != "assigned" or worker_id is None:
        return False
    profile = next(
        (
            item
            for item in request.available_workers
            if item.worker.capability_id == worker_id
        ),
        None,
    )
    if profile is None or not task.required_capabilities:
        return False
    capabilities = {
        capability.capability_id: capability
        for capability in profile.capabilities.capabilities
    }
    return all(
        capability_id in capabilities
        and capabilities[capability_id].side_effect in {"none", "read"}
        for capability_id in task.required_capabilities
    )


def _set_task_status(
    plan: TaskPlan,
    task_id: TaskId,
    status: ExecutionStatus,
) -> TaskPlan:
    tasks = [
        task.model_copy(update={"execution_status": status})
        if task.task_id == task_id
        else task.model_copy(deep=True)
        for task in plan.tasks
    ]
    return plan.model_copy(update={"tasks": tasks}, deep=True)


def _terminal_action_update(
    plan: TaskPlan,
    task_id: TaskId | None,
    action: AgentAction,
) -> SupervisorGraphState:
    if isinstance(action, AskUserAction):
        updated_plan = (
            _set_task_status(plan, task_id, "waiting_user")
            if task_id is not None
            else plan
        )
        return {
            "plan": updated_plan,
            "execution_status": "waiting_user",
            "business_outcome": None,
            "current_task_id": task_id,
            "current_task_ids": [task_id] if task_id is not None else [],
            "pending_action": None,
            "pending_actions": [],
            "handoff_draft": None,
            "handoff_drafts": [],
            "public_summary": action.question,
            "stop_reason": "waiting_for_user",
        }
    if isinstance(action, FinishAction):
        updated_plan = (
            _set_task_status(plan, task_id, "completed")
            if task_id is not None
            else _set_all_active_tasks(plan, "completed")
        )
        return {
            "plan": updated_plan,
            "execution_status": "completed",
            "business_outcome": action.business_outcome,
            "current_task_id": None,
            "current_task_ids": [],
            "pending_action": None,
            "pending_actions": [],
            "handoff_draft": None,
            "handoff_drafts": [],
            "evidence_ids": list(action.evidence_ids),
            "artifact_ids": list(action.artifact_ids),
            "public_summary": action.public_summary,
            "stop_reason": "goal_completed",
        }
    if isinstance(action, CannotCompleteAction):
        execution_status: ExecutionStatus = (
            "failed"
            if action.business_outcome in {"timed_out", "system_error"}
            else "completed"
        )
        updated_plan = (
            _set_task_status(plan, task_id, "failed")
            if task_id is not None
            else _set_all_active_tasks(plan, "failed")
        )
        return {
            "plan": updated_plan,
            "execution_status": execution_status,
            "business_outcome": action.business_outcome,
            "current_task_id": None,
            "current_task_ids": [],
            "pending_action": None,
            "pending_actions": [],
            "handoff_draft": None,
            "handoff_drafts": [],
            "evidence_ids": [],
            "artifact_ids": [],
            "public_summary": action.public_summary,
            "stop_reason": action.business_outcome,
        }
    raise ValueError("action is not terminal")


def _set_all_active_tasks(plan: TaskPlan, status: ExecutionStatus) -> TaskPlan:
    tasks = [
        task.model_copy(update={"execution_status": status})
        if task.execution_status in {"waiting", "running", "waiting_user"}
        else task.model_copy(deep=True)
        for task in plan.tasks
    ]
    return plan.model_copy(update={"tasks": tasks}, deep=True)


def _failure_update(
    state: SupervisorGraphState,
    *,
    history: list[SupervisorNodeName],
    stop_reason: ShortText,
    usage: ResourceUsage | None = None,
    decision_count: int | None = None,
) -> SupervisorGraphState:
    plan = state.get("plan")
    update: SupervisorGraphState = {
        "execution_status": "failed",
        "business_outcome": "system_error",
        "current_task_id": None,
        "current_task_ids": [],
        "pending_action": None,
        "pending_actions": [],
        "handoff_draft": None,
        "handoff_drafts": [],
        "public_summary": "Agent流程未能安全完成。",
        "stop_reason": stop_reason,
        "resource_usage": usage or state["resource_usage"],
        "node_history": history,
    }
    if plan is not None:
        update["plan"] = _set_all_active_tasks(plan, "failed")
    if decision_count is not None:
        update["decision_count"] = decision_count
    return update


def _action_signature(action: AgentAction) -> str:
    return json.dumps(
        action.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _append_history(
    state: SupervisorGraphState,
    node: SupervisorNodeName,
) -> list[SupervisorNodeName]:
    return [*state.get("node_history", []), node]


def _upsert_worker_result(
    current: list[WorkerResult],
    incoming: WorkerResult,
) -> list[WorkerResult]:
    return [
        *[
            item
            for item in current
            if (item.task_id, item.worker_id) != (incoming.task_id, incoming.worker_id)
        ],
        incoming,
    ]


def _merge_observations(
    current: list[WorkerObservation],
    incoming: list[WorkerObservation],
) -> list[WorkerObservation]:
    merged: list[WorkerObservation] = []
    seen = set()
    for item in [*current, *incoming]:
        if item.observation_id in seen:
            continue
        seen.add(item.observation_id)
        merged.append(item)
    if len(merged) > 48:
        raise ValueError("Supervisor observations exceed the state bound")
    return merged


def _merge_ids(current: list[UUID], incoming: list[UUID], maximum: int) -> list[UUID]:
    merged = list(dict.fromkeys([*current, *incoming]))
    return merged[:maximum]


def _merge_text(
    current: list[ShortText],
    incoming: list[ShortText],
    maximum: int,
) -> list[ShortText]:
    return list(dict.fromkeys([*current, *incoming]))[:maximum]


def _add_usage(
    current: ResourceUsage,
    *,
    model_calls: int = 0,
    other: ResourceUsage | None = None,
) -> ResourceUsage:
    incoming = other or _zero_usage()
    return ResourceUsage(
        model_calls=current.model_calls + model_calls + incoming.model_calls,
        tool_calls=current.tool_calls + incoming.tool_calls,
        input_tokens=current.input_tokens + incoming.input_tokens,
        output_tokens=current.output_tokens + incoming.output_tokens,
        duration_ms=current.duration_ms + incoming.duration_ms,
    )


def _answer_model_call_count(provider: EngineeredAgentProvider) -> int:
    value = getattr(provider, "last_answer_model_calls", 1)
    return value if isinstance(value, int) and 0 <= value <= 2 else 1

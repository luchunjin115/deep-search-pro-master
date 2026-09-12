"""Bounded Action/Observation loop for the read-only Business Data Worker."""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol, TypeAlias
from uuid import UUID, uuid4

from pydantic import ValidationError

from app.agents.runtime import WorkerExecutionContext
from app.capabilities.contracts import CapabilitySelection
from app.capabilities.resolver import CapabilityResolver
from app.core.errors import (
    AgentProviderOutputError,
    ApplicationError,
    BudgetExceededError,
)
from app.llm.agent_provider import AgentDecisionProvider, validate_decision_response
from app.llm.agent_schemas import DecisionRequest
from app.repositories.inventory import InventoryRepository
from app.repositories.product import ProductRepository
from app.schemas.agent import (
    AgentHandoff,
    AgentTask,
    AskUserAction,
    BoundedJsonObject,
    CannotCompleteAction,
    EvidenceRequirement,
    ExecuteCapabilityAction,
    FinishAction,
    ResourceUsage,
    SafeAgentError,
    TaskAssignment,
    TaskPlan,
    WorkerObservation,
    WorkerResult,
)
from app.schemas.common import ErrorDetail, ToolEnvelope
from app.schemas.inventory import InventoryResult, SearchInventoryInput
from app.schemas.product import GetProductSpecInput, ProductSpecResult
from app.services.evidence import EvidenceService
from app.services.inventory import InventoryService
from app.services.product import ProductSpecService
from app.tools.get_product_spec import GetProductSpecTool
from app.tools.search_inventory import SearchInventoryTool

BusinessEnvelope: TypeAlias = (
    ToolEnvelope[ProductSpecResult] | ToolEnvelope[InventoryResult]
)


class BusinessCapabilityExecutor(Protocol):
    """Execute one already-validated Business capability through its real Tool."""

    def execute(self, action: ExecuteCapabilityAction) -> BusinessEnvelope: ...


class BusinessCapabilityExecutorFactory(Protocol):
    """Bind Business Tools to one Worker's trusted Session and Harness."""

    def create(
        self,
        execution_context: WorkerExecutionContext,
    ) -> BusinessCapabilityExecutor: ...


@dataclass(frozen=True, slots=True)
class BusinessWorkerGuardrails:
    """Small server-owned loop bounds, independent of model-authored budgets."""

    max_decisions: int = 4

    def __post_init__(self) -> None:
        if isinstance(self.max_decisions, bool) or not 1 <= self.max_decisions <= 8:
            raise ValueError("max_decisions must be 1-8")


class SqlAlchemyBusinessCapabilityExecutorFactory:
    """Build the existing M1 Tools over a Worker's isolated transaction."""

    def __init__(self, *, statement_timeout_ms: int = 2000) -> None:
        if (
            isinstance(statement_timeout_ms, bool)
            or not 1 <= statement_timeout_ms <= 60_000
        ):
            raise ValueError("statement_timeout_ms must be 1-60000")
        self._statement_timeout_ms = statement_timeout_ms

    def create(
        self,
        execution_context: WorkerExecutionContext,
    ) -> BusinessCapabilityExecutor:
        session = execution_context.session
        product_tool = GetProductSpecTool(
            execution_context.harness,
            ProductSpecService(
                ProductRepository(session, self._statement_timeout_ms),
            ),
        )
        inventory_tool = SearchInventoryTool(
            execution_context.harness,
            InventoryService(
                InventoryRepository(session, self._statement_timeout_ms),
                EvidenceService(session),
            ),
        )
        return _SqlAlchemyBusinessCapabilityExecutor(product_tool, inventory_tool)


@dataclass(frozen=True, slots=True)
class _SqlAlchemyBusinessCapabilityExecutor:
    product_tool: GetProductSpecTool
    inventory_tool: SearchInventoryTool

    def execute(self, action: ExecuteCapabilityAction) -> BusinessEnvelope:
        try:
            if action.capability_id == "get_product_spec":
                product_request = GetProductSpecInput.model_validate(
                    action.arguments.root
                )
                return self.product_tool.invoke(product_request)
            if action.capability_id == "search_inventory":
                inventory_request = SearchInventoryInput.model_validate(
                    action.arguments.root
                )
                return self.inventory_tool.invoke(inventory_request)
        except ValidationError:
            raise AgentProviderOutputError from None
        raise AgentProviderOutputError


class BusinessDataWorker:
    """Select at most one Business action per decision and return safe observations."""

    worker_id = "business_data"

    def __init__(
        self,
        *,
        provider: AgentDecisionProvider,
        resolver: CapabilityResolver,
        executor_factory: BusinessCapabilityExecutorFactory,
        guardrails: BusinessWorkerGuardrails | None = None,
        id_factory: Callable[[], UUID] = uuid4,
    ) -> None:
        self._provider = provider
        self._resolver = resolver
        self._executor_factory = executor_factory
        self._guardrails = guardrails or BusinessWorkerGuardrails()
        self._id_factory = id_factory

    async def run(
        self,
        handoff: AgentHandoff,
        execution: WorkerExecutionContext,
    ) -> WorkerResult:
        """Run the bounded decision loop without exposing trusted runtime objects."""

        observations: list[WorkerObservation] = []
        try:
            self._validate_runtime_binding(handoff, execution)
            capabilities = self._resolver.resolve_for_agent(
                execution.trusted_context,
                self.worker_id,
                CapabilitySelection(),
            )
            plan = _worker_plan(handoff)
            executor = self._executor_factory.create(execution)
            action_signatures: set[str] = set()

            for _ in range(self._guardrails.max_decisions):
                request = DecisionRequest(
                    plan=plan,
                    active_task_id=handoff.task_id,
                    available_capabilities=capabilities,
                    public_context=handoff.public_context,
                    observations=tuple(observations),
                )
                execution.harness.reserve_model_call()
                decision = validate_decision_response(
                    request,
                    await self._provider.choose_action(request),
                )
                action = decision.action

                if isinstance(action, ExecuteCapabilityAction):
                    _validate_action_arguments(action)
                    _validate_action_scope(action, handoff, observations)
                    signature = _action_signature(action)
                    if signature in action_signatures:
                        raise BudgetExceededError(
                            "repeated_tool_call",
                            "检测到重复Tool调用，已停止Worker执行。",
                        )
                    action_signatures.add(signature)
                    observation = _observation_from_envelope(
                        self._id_factory(),
                        action,
                        executor.execute(action),
                    )
                    observations.append(observation)
                    if observation.status == "timeout":
                        return _failed_result(
                            handoff,
                            observations,
                            _timeout_error(observation),
                            outcome="timed_out",
                        )
                    continue

                if isinstance(action, AskUserAction):
                    return _waiting_user_result(handoff, observations, action)
                if isinstance(action, FinishAction):
                    return _finished_result(handoff, observations, action)
                if isinstance(action, CannotCompleteAction):
                    return _cannot_complete_result(handoff, observations, action)
                raise AgentProviderOutputError

            raise BudgetExceededError(
                "worker_decision_limit",
                "Worker决策次数已达到上限。",
            )
        except ApplicationError as error:
            return _failed_result(handoff, observations, error)
        except Exception:  # noqa: BLE001 - Worker is a strict sanitization boundary
            return _failed_result(handoff, observations, _internal_worker_error())

    def _validate_runtime_binding(
        self,
        handoff: AgentHandoff,
        execution: WorkerExecutionContext,
    ) -> None:
        if handoff.target_worker != self.worker_id:
            raise AgentProviderOutputError
        if handoff.allocated_budget_ref != execution.worker_run.budget_ref:
            raise AgentProviderOutputError
        if execution.can_delegate:
            raise AgentProviderOutputError


def _worker_plan(handoff: AgentHandoff) -> TaskPlan:
    return TaskPlan(
        plan_id=handoff.handoff_id,
        goal=handoff.goal,
        tasks=[
            AgentTask(
                task_id=handoff.task_id,
                goal=handoff.goal,
                required_capabilities=[],
                assignment=TaskAssignment(
                    status="assigned",
                    worker_id=handoff.target_worker,
                ),
                execution_status="running",
                completion_criteria=list(handoff.completion_criteria),
                evidence_requirement=EvidenceRequirement(
                    required=False,
                    minimum_count=0,
                    source_types=["database"],
                ),
                failure_impact="allows_partial",
            )
        ],
    )


def _validate_action_arguments(action: ExecuteCapabilityAction) -> None:
    try:
        if action.capability_id == "get_product_spec":
            GetProductSpecInput.model_validate(action.arguments.root)
            return
        if action.capability_id == "search_inventory":
            SearchInventoryInput.model_validate(action.arguments.root)
            return
    except ValidationError:
        raise AgentProviderOutputError from None
    raise AgentProviderOutputError


def _validate_action_scope(
    action: ExecuteCapabilityAction,
    handoff: AgentHandoff,
    observations: Sequence[WorkerObservation],
) -> None:
    arguments = action.arguments.root
    public_context = handoff.public_context.root
    if action.capability_id == "get_product_spec":
        expected_query = public_context.get("product_query", public_context.get("sku"))
        if expected_query is None or arguments.get("product_query") != expected_query:
            raise AgentProviderOutputError
        return

    expected_market = public_context.get("market_code")
    if expected_market is None or arguments.get("market_code") != expected_market:
        raise AgentProviderOutputError
    expected_warehouse = public_context.get("warehouse_code")
    if arguments.get("warehouse_code") != expected_warehouse:
        raise AgentProviderOutputError

    resolved_sku = _resolved_sku(observations)
    expected_sku = resolved_sku or public_context.get("sku")
    if expected_sku is None or arguments.get("sku") != expected_sku:
        raise AgentProviderOutputError


def _resolved_sku(observations: Sequence[WorkerObservation]) -> object | None:
    for observation in reversed(observations):
        result = observation.structured_result
        if result is None or result.root.get("capability_id") != "get_product_spec":
            continue
        data = result.root.get("data")
        if isinstance(data, dict) and "sku" in data:
            return data["sku"]
    return None


def _action_signature(action: ExecuteCapabilityAction) -> str:
    return json.dumps(
        {
            "capability_id": action.capability_id,
            "arguments": action.arguments.root,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _observation_from_envelope(
    observation_id: UUID,
    action: ExecuteCapabilityAction,
    envelope: BusinessEnvelope,
) -> WorkerObservation:
    usage = ResourceUsage(
        model_calls=0,
        tool_calls=1,
        input_tokens=0,
        output_tokens=0,
        duration_ms=envelope.meta.duration_ms,
    )
    if envelope.status == "success":
        if envelope.data is None:
            raise AgentProviderOutputError
        return WorkerObservation(
            observation_id=observation_id,
            status="success",
            public_summary=f"{action.capability_id}执行成功。",
            structured_result=BoundedJsonObject(
                {
                    "capability_id": action.capability_id,
                    "data": envelope.data.model_dump(mode="json"),
                },
            ),
            evidence_ids=list(envelope.evidence_ids),
            resource_usage=usage,
        )

    if envelope.error is None:
        raise AgentProviderOutputError
    status = _observation_error_status(envelope.error)
    return WorkerObservation(
        observation_id=observation_id,
        status=status,
        public_summary=envelope.error.message,
        safe_error=_safe_error(envelope.error),
        resource_usage=usage,
    )


def _observation_error_status(
    error: ErrorDetail,
) -> Literal["error", "rejected", "timeout"]:
    if error.code in {"DATABASE_TIMEOUT", "BUDGET_EXCEEDED"}:
        return "timeout"
    if error.code == "FORBIDDEN":
        return "rejected"
    return "error"


def _finished_result(
    handoff: AgentHandoff,
    observations: Sequence[WorkerObservation],
    action: FinishAction,
) -> WorkerResult:
    successful = [item for item in observations if item.status == "success"]
    failed = [item for item in observations if item.status != "success"]
    observed_evidence = _unique_evidence_ids(observations)
    if action.evidence_ids != observed_evidence:
        raise AgentProviderOutputError
    if action.artifact_ids:
        raise AgentProviderOutputError
    if action.business_outcome == "answered" and (not successful or failed):
        raise AgentProviderOutputError
    if action.business_outcome == "partial" and not successful:
        raise AgentProviderOutputError
    if action.business_outcome == "no_evidence" and observed_evidence:
        raise AgentProviderOutputError

    errors = _safe_errors(observations) if action.business_outcome == "partial" else []
    return WorkerResult(
        task_id=handoff.task_id,
        worker_id=handoff.target_worker,
        execution_status="completed",
        business_outcome=action.business_outcome,
        business_result=_business_result(successful),
        public_summary=action.public_summary,
        observations=list(observations),
        evidence_ids=observed_evidence,
        artifact_ids=[],
        unknowns=_unique_unknowns(observations),
        safe_errors=errors,
        resource_usage=_zero_usage(),
    )


def _waiting_user_result(
    handoff: AgentHandoff,
    observations: Sequence[WorkerObservation],
    action: AskUserAction,
) -> WorkerResult:
    rollback_safe_observations = _without_evidence_references(observations)
    return WorkerResult(
        task_id=handoff.task_id,
        worker_id=handoff.target_worker,
        execution_status="waiting_user",
        business_outcome=None,
        business_result=None,
        public_summary=action.question,
        observations=rollback_safe_observations,
        evidence_ids=[],
        artifact_ids=[],
        unknowns=list(
            dict.fromkeys((*_unique_unknowns(observations), *action.requested_fields))
        ),
        safe_errors=[],
        resource_usage=_zero_usage(),
    )


def _cannot_complete_result(
    handoff: AgentHandoff,
    observations: Sequence[WorkerObservation],
    action: CannotCompleteAction,
) -> WorkerResult:
    if action.business_outcome in {"timed_out", "system_error"}:
        failed_outcome: Literal["timed_out", "system_error"] = (
            "timed_out" if action.business_outcome == "timed_out" else "system_error"
        )
        error = next(
            (item.safe_error for item in reversed(observations) if item.safe_error),
            None,
        )
        application_error = (
            ApplicationError(
                error.code,
                error.message,
                retryable=error.retryable,
                field=error.field,
            )
            if error is not None
            else _internal_worker_error()
        )
        return _failed_result(
            handoff,
            observations,
            application_error,
            outcome=failed_outcome,
            summary=action.public_summary,
        )

    if action.business_outcome == "denied" and not any(
        item.status == "rejected" for item in observations
    ):
        raise AgentProviderOutputError
    if action.business_outcome in {"unsupported", "denied"} and any(
        item.status == "success" for item in observations
    ):
        raise AgentProviderOutputError
    if action.business_outcome == "no_evidence" and _unique_evidence_ids(observations):
        raise AgentProviderOutputError
    errors = _safe_errors(observations) if action.business_outcome == "denied" else []
    return WorkerResult(
        task_id=handoff.task_id,
        worker_id=handoff.target_worker,
        execution_status="completed",
        business_outcome=action.business_outcome,
        business_result=None,
        public_summary=action.public_summary,
        observations=list(observations),
        evidence_ids=_unique_evidence_ids(observations),
        artifact_ids=[],
        unknowns=_unique_unknowns(observations),
        safe_errors=errors,
        resource_usage=_zero_usage(),
    )


def _failed_result(
    handoff: AgentHandoff,
    observations: Sequence[WorkerObservation],
    error: ApplicationError,
    *,
    outcome: Literal["timed_out", "system_error"] = "system_error",
    summary: str | None = None,
) -> WorkerResult:
    rollback_safe_observations = _without_evidence_references(observations)
    safe_error = SafeAgentError(
        code=error.code,
        message=error.message,
        retryable=error.retryable,
        field=error.field,
        diagnostic_stage=(
            error.stage if isinstance(error, AgentProviderOutputError) else None
        ),
    )
    return WorkerResult(
        task_id=handoff.task_id,
        worker_id=handoff.target_worker,
        execution_status="failed",
        business_outcome=outcome,
        business_result=None,
        public_summary=summary or error.message,
        observations=rollback_safe_observations,
        evidence_ids=[],
        artifact_ids=[],
        unknowns=_unique_unknowns(observations),
        safe_errors=[safe_error],
        resource_usage=_zero_usage(),
    )


def _business_result(
    observations: Sequence[WorkerObservation],
) -> BoundedJsonObject | None:
    results: dict[str, object] = {}
    for observation in observations:
        if observation.structured_result is None:
            continue
        result = observation.structured_result.root
        capability_id = result.get("capability_id")
        data = result.get("data")
        if capability_id == "get_product_spec" and isinstance(data, dict):
            results["product"] = data
        elif capability_id == "search_inventory" and isinstance(data, dict):
            results["inventory"] = data
        else:
            raise AgentProviderOutputError
    return BoundedJsonObject(results) if results else None


def _unique_evidence_ids(observations: Sequence[WorkerObservation]) -> list[UUID]:
    return list(
        dict.fromkeys(
            evidence_id
            for observation in observations
            for evidence_id in observation.evidence_ids
        )
    )


def _unique_unknowns(observations: Sequence[WorkerObservation]) -> list[str]:
    return list(
        dict.fromkeys(
            unknown for observation in observations for unknown in observation.unknowns
        )
    )


def _without_evidence_references(
    observations: Sequence[WorkerObservation],
) -> list[WorkerObservation]:
    """Remove references whose Worker transaction will not be committed."""

    return [
        observation.model_copy(update={"evidence_ids": []})
        if observation.evidence_ids
        else observation.model_copy(deep=True)
        for observation in observations
    ]


def _safe_errors(observations: Sequence[WorkerObservation]) -> list[SafeAgentError]:
    results: list[SafeAgentError] = []
    seen: set[tuple[object, ...]] = set()
    for observation in observations:
        error = observation.safe_error
        if error is None:
            continue
        key = (error.code, error.message, error.retryable, error.field)
        if key not in seen:
            seen.add(key)
            results.append(error)
    return results


def _safe_error(error: ErrorDetail) -> SafeAgentError:
    return SafeAgentError(
        code=error.code,
        message=error.message,
        retryable=error.retryable,
        field=error.field,
    )


def _timeout_error(observation: WorkerObservation) -> ApplicationError:
    error = observation.safe_error
    if error is None:
        return BudgetExceededError("worker_timeout", "Worker执行超时。")
    return ApplicationError(
        error.code,
        error.message,
        retryable=error.retryable,
        field=error.field,
    )


def _internal_worker_error() -> ApplicationError:
    return ApplicationError(
        "INTERNAL_ERROR",
        "Business Worker执行失败。",
        retryable=False,
    )


def _zero_usage() -> ResourceUsage:
    return ResourceUsage(
        model_calls=0,
        tool_calls=0,
        input_tokens=0,
        output_tokens=0,
        duration_ms=0,
    )

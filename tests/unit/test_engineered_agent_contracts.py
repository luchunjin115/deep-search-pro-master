from __future__ import annotations

import json
from uuid import uuid4

import pytest
from pydantic import TypeAdapter, ValidationError

from app.agents.engineered_state import EngineeredAgentState
from app.schemas.agent import (
    AgentAction,
    AgentDecision,
    AgentHandoff,
    AgentTask,
    AskUserAction,
    BoundedJsonObject,
    CannotCompleteAction,
    DelegateTaskAction,
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
from tests.fixtures.agent_acceptance import (
    AGENT_ACCEPTANCE_FIXTURE_VERSION,
    agent_acceptance_cases,
    agent_acceptance_suite,
)


def task(
    task_id: str = "task-inventory",
    *,
    depends_on: list[str] | None = None,
) -> AgentTask:
    return AgentTask(
        task_id=task_id,
        goal="查询德国仓可售库存",
        depends_on=depends_on or [],
        required_capabilities=["search_inventory"],
        assignment=TaskAssignment(status="unassigned"),
        completion_criteria=["取得当前获权库存事实"],
        evidence_requirement=EvidenceRequirement(
            required=True,
            minimum_count=1,
            source_types=["database"],
        ),
        failure_impact="blocks_dependents",
    )


def usage() -> ResourceUsage:
    return ResourceUsage(
        model_calls=1,
        tool_calls=1,
        input_tokens=120,
        output_tokens=40,
        duration_ms=25,
    )


def observation(**overrides: object) -> WorkerObservation:
    values: dict[str, object] = {
        "observation_id": uuid4(),
        "status": "success",
        "public_summary": "德国仓可售库存为125件。",
        "structured_result": {"available": 125, "market_code": "DE"},
        "evidence_ids": [uuid4()],
        "artifact_ids": [],
        "unknowns": [],
        "safe_error": None,
        "resource_usage": usage(),
    }
    values.update(overrides)
    return WorkerObservation.model_validate(values)


def test_task_plan_accepts_a_bounded_dag_and_is_json_serializable() -> None:
    first = task()
    second = task("task-policy", depends_on=[first.task_id]).model_copy(
        update={
            "goal": "读取安全库存政策",
            "required_capabilities": ["search_knowledge"],
            "evidence_requirement": EvidenceRequirement(
                required=True,
                minimum_count=1,
                source_types=["document"],
            ),
            "failure_impact": "allows_partial",
        }
    )
    plan = TaskPlan(
        plan_id=uuid4(),
        goal="判断库存是否满足政策",
        tasks=[first, second],
    )

    restored = TaskPlan.model_validate_json(plan.model_dump_json())

    assert restored == plan
    assert restored.tasks[1].depends_on == ["task-inventory"]
    assert restored.model_json_schema()["additionalProperties"] is False


@pytest.mark.parametrize(
    ("tasks", "message"),
    [
        ([task(), task()], "duplicate"),
        ([task(depends_on=["task-missing"])], "does not exist"),
        ([task(depends_on=["task-inventory"])], "itself"),
        (
            [
                task("task-a", depends_on=["task-b"]),
                task("task-b", depends_on=["task-c"]),
                task("task-c", depends_on=["task-a"]),
            ],
            "cycle",
        ),
    ],
)
def test_task_plan_rejects_invalid_dag(
    tasks: list[AgentTask],
    message: str,
) -> None:
    with pytest.raises(ValidationError, match=message):
        TaskPlan(plan_id=uuid4(), goal="非法计划", tasks=tasks)


def test_task_and_plan_are_bounded_and_reject_extra_fields() -> None:
    with pytest.raises(ValidationError):
        TaskPlan(plan_id=uuid4(), goal="x", tasks=[task()] * 25)
    with pytest.raises(ValidationError):
        AgentTask.model_validate(task().model_dump() | {"sql": "SELECT secret"})
    with pytest.raises(ValidationError):
        AgentTask.model_validate(task().model_dump() | {"goal": "x" * 2001})


def test_action_is_a_strict_discriminated_union_with_one_action_only() -> None:
    adapter = TypeAdapter(AgentAction)
    action_payloads = (
        {
            "type": "execute_capability",
            "capability_id": "search_inventory",
            "arguments": {"sku": "LR-TL-MUSH-OR01", "market_code": "DE"},
        },
        {
            "type": "delegate_task",
            "task_id": "task-inventory",
            "target_worker": "business_data",
        },
        {"type": "ask_user", "question": "请确认目标市场。"},
        {
            "type": "finish",
            "public_summary": "已完成。",
            "business_outcome": "answered",
        },
        {
            "type": "cannot_complete",
            "public_summary": "当前能力不支持写库存。",
            "business_outcome": "unsupported",
        },
    )
    actions = [adapter.validate_python(payload) for payload in action_payloads]
    assert isinstance(actions[0], ExecuteCapabilityAction)
    assert isinstance(actions[4], CannotCompleteAction)
    assert [action.type for action in actions] == [
        "execute_capability",
        "delegate_task",
        "ask_user",
        "finish",
        "cannot_complete",
    ]

    for payload in (
        {"type": "invented_action", "question": "hello"},
        {
            "type": "ask_user",
            "question": "哪个市场？",
            "capability_id": "search_inventory",
            "arguments": {},
        },
    ):
        with pytest.raises(ValidationError):
            adapter.validate_python(payload)

    decision = AgentDecision(
        action=AskUserAction(question="请确认目标市场。"),
    )
    assert decision.action.type == "ask_user"
    with pytest.raises(ValidationError):
        AgentDecision.model_validate(
            {
                "action": AskUserAction(question="请确认目标市场。").model_dump(),
                "finish": FinishAction(
                    public_summary="已完成。",
                    business_outcome="answered",
                ).model_dump(),
            }
        )


@pytest.mark.parametrize(
    "forbidden",
    [
        {"tenant_id": str(uuid4())},
        {"user_id": str(uuid4())},
        {"roles": ["company_owner"]},
        {"permissions": ["all"]},
        {"parent_run_id": str(uuid4())},
        {"budget_ref": str(uuid4())},
        {"max_tool_calls": 999},
        {"tenantId": str(uuid4())},
    ],
)
def test_model_controlled_actions_cannot_inject_trusted_context(
    forbidden: dict[str, object],
) -> None:
    with pytest.raises(ValidationError, match="server-owned"):
        ExecuteCapabilityAction(
            capability_id="search_inventory",
            arguments={"sku": "LR-TL-MUSH-OR01", "nested": forbidden},
        )

    with pytest.raises(ValidationError):
        DelegateTaskAction(
            task_id="task-inventory",
            target_worker="business_data",
            **forbidden,
        )


def test_generic_json_rejects_unbounded_or_non_json_values() -> None:
    too_deep: dict[str, object] = {"value": 1}
    for _ in range(6):
        too_deep = {"nested": too_deep}

    for payload in (
        {f"key_{index}": index for index in range(33)},
        {"items": list(range(33))},
        too_deep,
        {"runtime": object()},
        {"trace_id": str(uuid4())},
        {"token": "must-not-enter"},
        {"huge": "x" * 20_000},
        {f"part_{index}": "中" * 1000 for index in range(6)},
    ):
        with pytest.raises(ValidationError):
            BoundedJsonObject(payload)


def test_observation_has_strict_status_payload_and_unique_bounded_ids() -> None:
    result = observation()
    assert result.status == "success"
    assert json.loads(result.model_dump_json())["structured_result"]["available"] == 125

    with pytest.raises(ValidationError, match="safe error"):
        observation(status="timeout", structured_result=None, evidence_ids=[])
    with pytest.raises(ValidationError, match="cannot include"):
        observation(
            status="error",
            safe_error=SafeAgentError(
                code="INTERNAL_ERROR",
                message="请求处理失败",
                retryable=False,
            ),
        )

    repeated = uuid4()
    with pytest.raises(ValidationError, match="unique"):
        observation(evidence_ids=[repeated, repeated])
    with pytest.raises(ValidationError):
        observation(evidence_ids=[uuid4() for _ in range(13)])


@pytest.mark.parametrize(
    "message",
    [
        "Traceback: failure",
        "SELECT * FROM users",
        r"failed at C:\\private\\secret.txt",
        "failed at D:/private/secret.txt",
        "api_key=secret-value",
    ],
)
def test_safe_error_rejects_sensitive_details(message: str) -> None:
    with pytest.raises(ValidationError, match="public-safe"):
        SafeAgentError(code="INTERNAL_ERROR", message=message, retryable=False)


def test_handoff_carries_only_public_context_ids_constraints_and_budget_reference() -> (
    None
):
    evidence_id = uuid4()
    artifact_id = uuid4()
    handoff = AgentHandoff(
        handoff_id=uuid4(),
        task_id="task-policy",
        goal="读取安全库存政策",
        target_worker="knowledge",
        public_context={"product_name": "橙色蘑菇灯", "market_code": "DE"},
        evidence_ids=[evidence_id],
        artifact_ids=[artifact_id],
        constraints=["只读取当前获权文档"],
        expected_output="返回政策事实和Evidence ID",
        completion_criteria=["找到明确政策或报告无证据"],
        allocated_budget_ref=uuid4(),
    )
    dumped = handoff.model_dump()

    assert dumped["evidence_ids"] == [evidence_id]
    assert dumped["artifact_ids"] == [artifact_id]
    assert (
        not {
            "user_id",
            "tenant_id",
            "roles",
            "permissions",
            "parent_run_id",
        }
        & dumped.keys()
    )

    with pytest.raises(ValidationError):
        AgentHandoff.model_validate(handoff.model_dump() | {"tenant_id": uuid4()})

    with pytest.raises(ValidationError, match="unique"):
        AgentHandoff.model_validate(
            handoff.model_dump() | {"evidence_ids": [evidence_id, evidence_id]}
        )


@pytest.mark.parametrize(
    ("execution_status", "business_outcome"),
    [
        ("running", "answered"),
        ("waiting_user", "partial"),
        ("completed", "timed_out"),
        ("failed", "answered"),
        ("failed", "denied"),
    ],
)
def test_worker_result_rejects_contradictory_execution_and_business_status(
    execution_status: str,
    business_outcome: str,
) -> None:
    with pytest.raises(ValidationError, match="execution status"):
        WorkerResult(
            task_id="task-inventory",
            worker_id="business_data",
            execution_status=execution_status,
            business_outcome=business_outcome,
            business_result={"available": 125},
            public_summary="结果摘要",
            observations=[],
            evidence_ids=[],
            artifact_ids=[],
            unknowns=[],
            safe_errors=[],
            resource_usage=usage(),
        )


def test_worker_result_keeps_business_result_separate_from_execution_state() -> None:
    item = observation()
    result = WorkerResult(
        task_id="task-inventory",
        worker_id="business_data",
        execution_status="completed",
        business_outcome="answered",
        business_result={"available": 125},
        public_summary="德国仓可售库存为125件。",
        observations=[item],
        evidence_ids=item.evidence_ids,
        artifact_ids=[],
        unknowns=[],
        safe_errors=[],
        resource_usage=usage(),
    )

    assert result.execution_status == "completed"
    assert result.business_outcome == "answered"

    denied = WorkerResult(
        task_id="task-inventory",
        worker_id="business_data",
        execution_status="completed",
        business_outcome="denied",
        public_summary="当前账号无权访问该市场。",
        observations=[],
        safe_errors=[
            SafeAgentError(
                code="FORBIDDEN",
                message="当前账号无权访问该市场数据",
                retryable=False,
            )
        ],
        resource_usage=usage(),
    )
    assert denied.execution_status == "completed"
    assert denied.business_outcome == "denied"


def test_engineered_state_is_checkpoint_safe_and_rejects_sensitive_state() -> None:
    item = observation()
    result = WorkerResult(
        task_id="task-inventory",
        worker_id="business_data",
        execution_status="completed",
        business_outcome="answered",
        business_result={"available": 125},
        public_summary="德国仓可售库存为125件。",
        observations=[item],
        evidence_ids=item.evidence_ids,
        resource_usage=usage(),
    )
    state = EngineeredAgentState(
        run_id=uuid4(),
        goal="查询德国仓库存",
        plan=TaskPlan(plan_id=uuid4(), goal="查询德国仓库存", tasks=[task()]),
        execution_status="completed",
        business_outcome="answered",
        current_task_id=None,
        pending_action=None,
        observations=[item],
        worker_results=[result],
        evidence_ids=item.evidence_ids,
        artifact_ids=[],
        unknowns=[],
        public_summary="德国仓可售库存为125件。",
        stop_reason="goal_completed",
        resource_usage=usage(),
    )
    restored = EngineeredAgentState.model_validate_json(state.model_dump_json())

    assert restored == state
    schema_fields = set(EngineeredAgentState.model_fields)
    assert not schema_fields & {
        "chain_of_thought",
        "reasoning",
        "prompt",
        "messages",
        "database_session",
        "tool_objects",
        "run_context",
        "user_id",
        "tenant_id",
        "roles",
        "permissions",
        "budget_limits",
        "sql",
        "local_path",
        "storage_key",
        "raw_exception",
    }

    for forbidden_field in (
        "chain_of_thought",
        "database_session",
        "run_context",
        "sql",
        "local_path",
        "storage_key",
        "raw_exception",
    ):
        with pytest.raises(ValidationError):
            EngineeredAgentState.model_validate(
                state.model_dump() | {forbidden_field: object()}
            )

    unsafe_observation = item.model_dump()
    unsafe_observation["structured_result"] = {"safe": {"storage_key": "private"}}
    with pytest.raises(ValidationError):
        EngineeredAgentState.model_validate(
            state.model_dump() | {"observations": [unsafe_observation]}
        )


def test_acceptance_fixture_freezes_exactly_g0_through_g7_as_json_safe_data() -> None:
    suite = agent_acceptance_suite()
    cases = suite["cases"]

    assert suite["fixture_version"] == AGENT_ACCEPTANCE_FIXTURE_VERSION
    assert suite["common_success_expectations"] == {
        "gateway_root_runs": 1,
        "orphan_worker_runs": 0,
        "tool_call_inherits": ("identity", "budget", "trace"),
        "citation_validation_before_answer_persist": True,
        "maximum_answer_evidence": 12,
        "public_forbidden_fields": (
            "prompt",
            "sql",
            "local_path",
            "storage_key",
            "secret",
            "raw_exception",
        ),
    }
    assert isinstance(cases, tuple)
    assert [case["case_id"] for case in cases] == [f"G{i}" for i in range(8)]
    assert len({case["scenario"] for case in cases}) == 8
    assert all(
        set(case) == {"case_id", "scenario", "request", "expected"} for case in cases
    )
    assert all(
        set(case["request"]) >= {"method", "path_template"}  # type: ignore[arg-type]
        for case in cases
    )
    assert (
        json.loads(json.dumps(suite, ensure_ascii=False))["cases"][0]["case_id"] == "G0"
    )

    cases[0]["case_id"] = "mutated"
    assert agent_acceptance_cases()[0]["case_id"] == "G0"

from __future__ import annotations

import json
from collections.abc import Iterator
from uuid import UUID

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from app.capabilities.contracts import (
    CapabilityParameterSchema,
    CapabilityResolution,
    ResolvedCapability,
)
from app.core.config import Settings
from app.core.errors import (
    AgentProviderOutputError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from app.llm.agent_factory import create_engineered_agent_provider
from app.llm.agent_qwen import QwenAgentProvider
from app.llm.agent_schemas import (
    AgentAnswer,
    AnswerRequest,
    DecisionRequest,
    HandoffRequest,
    PlannerRequest,
    WorkerCapabilityProfile,
)
from app.schemas.agent import (
    AgentTask,
    BoundedJsonObject,
    DelegateTaskAction,
    EvidenceRequirement,
    ResourceUsage,
    TaskAssignment,
    TaskPlan,
    WorkerObservation,
    WorkerResult,
)

PLAN_ID = UUID("10000000-0000-0000-0000-000000000001")
EVIDENCE_ID = UUID("20000000-0000-0000-0000-000000000001")


def capability(capability_id: str, kind: str) -> ResolvedCapability:
    parameters = None
    if kind == "tool":
        parameters = CapabilityParameterSchema(
            {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "sku": {"type": "string", "maxLength": 100},
                    "market_code": {"type": "string", "enum": ["DE", "FR"]},
                },
                "required": ["sku", "market_code"],
            }
        )
    return ResolvedCapability(  # type: ignore[arg-type]
        capability_id=capability_id,
        kind=kind,
        version="1.0.0",
        description=f"安全能力 {capability_id}",
        parameters=parameters,
        side_effect="read" if kind == "tool" else "none",
        produces_evidence=kind == "tool",
        implementation_status="available",
    )


def profile() -> WorkerCapabilityProfile:
    return WorkerCapabilityProfile(
        worker=capability("business_data", "agent"),
        capabilities=CapabilityResolution(
            requesting_agent_id="business_data",
            capabilities=[capability("search_inventory", "tool")],
        ),
    )


def plan() -> TaskPlan:
    return TaskPlan(
        plan_id=PLAN_ID,
        goal="查询德国蘑菇灯库存",
        tasks=[
            AgentTask(
                task_id="inventory_task",
                goal="查询德国蘑菇灯库存",
                required_capabilities=["search_inventory"],
                assignment=TaskAssignment(status="assigned", worker_id="business_data"),
                completion_criteria=["返回库存事实或明确未知"],
                evidence_requirement=EvidenceRequirement(
                    required=True, minimum_count=1, source_types=["database"]
                ),
                failure_impact="blocks_dependents",
            )
        ],
    )


def usage() -> ResourceUsage:
    return ResourceUsage(
        model_calls=0,
        tool_calls=1,
        input_tokens=0,
        output_tokens=0,
        duration_ms=5,
    )


def result() -> WorkerResult:
    observation = WorkerObservation(
        observation_id=UUID("30000000-0000-0000-0000-000000000001"),
        status="success",
        public_summary="search_inventory执行成功。",
        structured_result=BoundedJsonObject(
            {
                "capability_id": "search_inventory",
                "data": {"sku": "LAMP-001", "available_quantity": 125},
            }
        ),
        evidence_ids=[EVIDENCE_ID],
        resource_usage=usage(),
    )
    return WorkerResult(
        task_id="inventory_task",
        worker_id="business_data",
        execution_status="completed",
        business_outcome="answered",
        business_result=BoundedJsonObject({"available_quantity": 125}),
        public_summary="库存已返回。",
        observations=[observation],
        evidence_ids=[EVIDENCE_ID],
        resource_usage=usage(),
    )


def responses() -> Iterator[dict[str, object]]:
    task = plan().tasks[0]
    yield {
        "contract_version": "m2-agent-provider-contract-v1",
        "plan_id": str(PLAN_ID),
        "goal": plan().goal,
        "direct_task": None,
        "worker_tasks": {
            "business_data": {
                "task_id": task.task_id,
                "goal": task.goal,
                "depends_on": task.depends_on,
                "required_capabilities": task.required_capabilities,
                "completion_criteria": task.completion_criteria,
                "evidence_requirement": task.evidence_requirement.model_dump(
                    mode="json"
                ),
                "failure_impact": task.failure_impact,
            }
        },
    }
    yield {
        "action": {
            "type": "delegate_task",
            "task_id": "inventory_task",
            "target_worker": "business_data",
        }
    }
    yield {
        "contract_version": "m2-agent-provider-contract-v1",
        "task_id": "inventory_task",
        "goal": "查询德国蘑菇灯库存",
        "target_worker": "business_data",
        "evidence_ids": [],
        "artifact_ids": [],
        "constraints": ["只使用获权只读能力"],
        "expected_output": "返回库存事实或明确未知",
        "completion_criteria": ["返回库存事实或明确未知"],
    }
    yield {
        "action": {
            "type": "finish",
            "public_summary": "德国蘑菇灯可售库存为125件 [E1]。",
            "business_outcome": "answered",
            "citation_labels": ["[E1]"],
            "artifact_ids": [],
        }
    }


@pytest.mark.asyncio
async def test_qwen_agent_supports_all_four_strict_roles_and_safe_payload() -> None:
    queued = iter(responses())
    captured: list[dict[str, object]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://qwen.example/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer agent-test-key"
        payload = json.loads(request.content)
        captured.append(payload)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(next(queued), ensure_ascii=False)
                        }
                    }
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = QwenAgentProvider(
            api_key=SecretStr("agent-test-key"),
            model="qwen3.8-max",
            base_url="https://qwen.example/v1",
            timeout_seconds=5,
            max_output_tokens=4096,
            http_client=client,
        )
        planner_request = PlannerRequest(
            goal=plan().goal,
            available_workers=(profile(),),
            public_context=BoundedJsonObject({"market_code": "DE"}),
        )
        assert await provider.create_plan(planner_request) == plan()

        decision_request = DecisionRequest(
            plan=plan(),
            active_task_id="inventory_task",
            available_capabilities=CapabilityResolution(
                capabilities=[capability("business_data", "agent")]
            ),
            public_context=BoundedJsonObject({"market_code": "DE"}),
        )
        decision = await provider.choose_action(decision_request)
        assert isinstance(decision.action, DelegateTaskAction)

        handoff_request = HandoffRequest(
            plan=plan(),
            delegation=decision.action,
            available_workers=CapabilityResolution(
                capabilities=[capability("business_data", "agent")]
            ),
            public_context=BoundedJsonObject({"market_code": "DE"}),
        )
        handoff = await provider.prepare_handoff(handoff_request)
        assert handoff.target_worker == "business_data"

        answer_request = AnswerRequest(
            goal=plan().goal,
            worker_results=(result(),),
        )
        answer = await provider.compose_answer(answer_request)
        assert isinstance(answer, AgentAnswer)
        assert answer.action.evidence_ids == [EVIDENCE_ID]  # type: ignore[union-attr]

    assert len(captured) == 4
    for payload in captured:
        assert payload["model"] == "qwen3.8-max"
        assert payload["temperature"] == 0
        assert payload["stream"] is False
        assert payload["enable_search"] is False
        assert payload["enable_thinking"] is False
        assert payload["max_tokens"] == 4096
        response_format = payload["response_format"]
        assert isinstance(response_format, dict)
        assert response_format["type"] == "json_schema"
        assert response_format["json_schema"]["strict"] is True  # type: ignore[index]

    serialized = json.dumps(captured, ensure_ascii=False)
    for forbidden in (
        "agent-test-key",
        "tenant_id",
        "user_id",
        "roles",
        "budget_ref",
        "sql",
        "storage_key",
    ):
        assert forbidden not in serialized.casefold()

    answer_input = json.loads(captured[3]["messages"][1]["content"])  # type: ignore[index]
    assert "observations" not in answer_input["worker_results"][0]
    assert answer_input["answer_evidence"]["items"][0]["citation_label"] == "[E1]"
    assert answer_input["answer_evidence"]["items"][0]["evidence_id"] == str(
        EVIDENCE_ID
    )


@pytest.mark.asyncio
async def test_qwen_answer_rejects_extra_fields_and_forged_labels() -> None:
    outputs = iter(
        [
            {
                "action": {
                    "type": "finish",
                    "public_summary": "伪造引用 [E2]。",
                    "business_outcome": "answered",
                    "citation_labels": ["[E2]"],
                    "artifact_ids": [],
                    "tenant_id": "attacker",
                }
            },
            {
                "action": {
                    "type": "finish",
                    "public_summary": "伪造引用 [E2]。",
                    "business_outcome": "answered",
                    "citation_labels": ["[E2]"],
                    "artifact_ids": [],
                }
            },
        ]
    )

    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps(next(outputs))}}]},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = QwenAgentProvider(
            api_key=SecretStr("secret"),
            model="qwen3.8-max",
            base_url="https://qwen.example/v1",
            timeout_seconds=5,
            max_output_tokens=4096,
            http_client=client,
        )
        for _ in range(2):
            with pytest.raises(AgentProviderOutputError):
                await provider.compose_answer(
                    AnswerRequest(goal="查询库存", worker_results=(result(),))
                )


@pytest.mark.asyncio
async def test_qwen_rejects_unknown_capability_and_extra_action_arguments() -> None:
    outputs = iter(
        [
            {
                "action": {
                    "type": "execute_capability",
                    "capability_id": "delete_inventory",
                    "arguments": {},
                }
            },
            {
                "action": {
                    "type": "execute_capability",
                    "capability_id": "search_inventory",
                    "arguments": {
                        "sku": "LAMP-001",
                        "market_code": "DE",
                        "unexpected": True,
                    },
                }
            },
        ]
    )

    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps(next(outputs))}}]},
        )

    decision_request = DecisionRequest(
        plan=plan(),
        active_task_id="inventory_task",
        available_capabilities=CapabilityResolution(
            requesting_agent_id="business_data",
            capabilities=[capability("search_inventory", "tool")],
        ),
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = QwenAgentProvider(
            api_key=SecretStr("secret"),
            model="qwen3.8-max",
            base_url="https://qwen.example/v1",
            timeout_seconds=5,
            max_output_tokens=4096,
            http_client=client,
        )
        for _ in range(2):
            with pytest.raises(AgentProviderOutputError):
                await provider.choose_action(decision_request)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_code", "retryable"), [(401, False), (429, True), (503, True)]
)
async def test_qwen_agent_maps_http_errors_without_leaking_response(
    status_code: int,
    retryable: bool,
) -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code,
            text="api_key=server-secret SQL=DROP TABLE agent_runs D:/private/file",
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = QwenAgentProvider(
            api_key=SecretStr("client-secret"),
            model="qwen3.8-max",
            base_url="https://qwen.example/v1",
            timeout_seconds=5,
            max_output_tokens=4096,
            http_client=client,
        )
        with pytest.raises(ProviderUnavailableError) as captured:
            await provider.create_plan(
                PlannerRequest(goal=plan().goal, available_workers=(profile(),))
            )

    assert captured.value.retryable is retryable
    safe = json.dumps(captured.value.to_detail().model_dump(), ensure_ascii=False)
    assert "server-secret" not in safe
    assert "client-secret" not in safe
    assert "DROP TABLE" not in safe
    assert "D:/private" not in safe


@pytest.mark.asyncio
async def test_qwen_agent_maps_timeout_without_leaking_request() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout(
            "Bearer client-secret SQL=SELECT secret", request=request
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = QwenAgentProvider(
            api_key=SecretStr("client-secret"),
            model="qwen3.8-max",
            base_url="https://qwen.example/v1",
            timeout_seconds=5,
            max_output_tokens=4096,
            http_client=client,
        )
        with pytest.raises(ProviderTimeoutError):
            await provider.create_plan(
                PlannerRequest(goal=plan().goal, available_workers=(profile(),))
            )


@pytest.mark.asyncio
async def test_agent_qwen_factory_and_settings_are_bounded() -> None:
    settings = Settings(  # type: ignore[call-arg]
        _env_file=None,
        llm_provider="qwen",
        qwen_api_key=SecretStr("factory-secret"),
        qwen_base_url="https://qwen.example/v1/",
        qwen_agent_max_output_tokens=2048,
    )
    provider = create_engineered_agent_provider(settings)
    assert isinstance(provider, QwenAgentProvider)
    await provider.aclose()

    with pytest.raises(ValidationError):
        Settings(_env_file=None, qwen_agent_max_output_tokens=128)  # type: ignore[call-arg]


def test_qwen_agent_rejects_non_https_constructor_endpoint() -> None:
    with pytest.raises(ValueError, match="HTTPS"):
        QwenAgentProvider(
            api_key=SecretStr("secret"),
            model="qwen3.8-max",
            base_url="http://qwen.example/v1",
            timeout_seconds=5,
            max_output_tokens=4096,
        )

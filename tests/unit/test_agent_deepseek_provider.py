from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import asdict
from typing import Literal
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
from app.core.rag_trace import RagReviewTrace, rag_review_trace, review_value
from app.llm.agent_deepseek import DeepSeekAgentProvider
from app.llm.agent_factory import create_engineered_agent_provider
from app.llm.agent_provider import EngineeredAgentProvider
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
    AgentDecision,
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
EVIDENCE_BODY = "deepseek-evidence-body"


def capability(
    capability_id: str,
    kind: Literal["tool", "agent"],
) -> ResolvedCapability:
    parameters = None
    if kind == "tool":
        parameters = CapabilityParameterSchema(
            {
                "type": "object",
                "additionalProperties": False,
                "properties": {"sku": {"type": "string", "maxLength": 100}},
                "required": ["sku"],
            }
        )
    return ResolvedCapability(
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
        goal="查询德国库存",
        tasks=[
            AgentTask(
                task_id="inventory_task",
                goal="查询德国库存",
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
        public_summary="库存查询成功。",
        structured_result=BoundedJsonObject(
            {
                "capability_id": "search_inventory",
                "data": {"marker": EVIDENCE_BODY},
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
        business_result=BoundedJsonObject({"inventory": {"marker": EVIDENCE_BODY}}),
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
        "goal": "查询德国库存",
        "target_worker": "business_data",
        "evidence_ids": [],
        "artifact_ids": [],
        "constraints": ["只能使用获权能力"],
        "expected_output": "返回库存事实或明确未知",
        "completion_criteria": ["返回库存事实或明确未知"],
    }
    yield {
        "action": {
            "type": "finish",
            "public_summary": "德国库存事实已返回 [E1]。",
            "business_outcome": "answered",
            "citation_labels": ["[E1]"],
            "artifact_ids": [],
        }
    }


def response_body(content: dict[str, object]) -> dict[str, object]:
    return {
        "status": "completed",
        "usage": {
            "input_tokens": 123,
            "output_tokens": 45,
            "total_tokens": 168,
        },
        "output": [
            {
                "type": "message",
                "status": "completed",
                "role": "assistant",
                "content": [
                    {
                        "type": "output_text",
                        "text": json.dumps(content, ensure_ascii=False),
                    }
                ],
            }
        ],
    }


@pytest.mark.asyncio
async def test_deepseek_supports_all_four_roles_with_responses_api() -> None:
    queued = iter(responses())
    captured: list[dict[str, object]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://deepseek.example/responses"
        assert request.headers["Authorization"] == "Bearer deepseek-test-key"
        captured.append(json.loads(request.content))
        return httpx.Response(200, json=response_body(next(queued)))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = DeepSeekAgentProvider(
            api_key=SecretStr("deepseek-test-key"),
            model="deepseek-v4-flash",
            base_url="https://deepseek.example/",
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
        )
        decision = await provider.choose_action(decision_request)
        assert isinstance(decision, AgentDecision)
        assert isinstance(decision.action, DelegateTaskAction)

        handoff = await provider.prepare_handoff(
            HandoffRequest(
                plan=plan(),
                delegation=decision.action,
                available_workers=CapabilityResolution(
                    capabilities=[capability("business_data", "agent")]
                ),
            )
        )
        assert handoff.target_worker == "business_data"

        answer = await provider.compose_answer(
            AnswerRequest(goal=plan().goal, worker_results=(result(),))
        )
        assert isinstance(answer, AgentAnswer)
        assert answer.action.evidence_ids == [EVIDENCE_ID]  # type: ignore[union-attr]
        assert provider.last_usage is not None
        assert provider.last_usage.input_tokens == 123
        assert provider.last_usage.output_tokens == 45
        assert provider.last_usage.total_tokens == 168
        assert provider.total_usage.api_calls == 4
        assert provider.total_usage.input_tokens == 492
        assert provider.total_usage.output_tokens == 180
        assert provider.total_usage.total_tokens == 672

    assert len(captured) == 4
    for payload in captured:
        assert payload["model"] == "deepseek-v4-flash"
        assert payload["reasoning"] == {"effort": "none"}
        assert payload["stream"] is False
        assert payload["temperature"] == 0
        assert payload["max_output_tokens"] == 4096
        assert "JSON Schema" in payload["instructions"]  # type: ignore[operator]
        assert isinstance(payload["input"], str)
        output_format = payload["text"]["format"]  # type: ignore[index]
        assert output_format["type"] == "json_schema"
        assert output_format["name"].startswith("engineered_agent_")
        assert output_format["schema"]["additionalProperties"] is False
        for qwen_only in (
            "messages",
            "response_format",
            "enable_search",
            "enable_thinking",
            "max_tokens",
            "tools",
        ):
            assert qwen_only not in payload

    answer_input = captured[3]["input"]
    assert isinstance(answer_input, str)
    assert answer_input.count(EVIDENCE_BODY) == 1
    assert json.loads(answer_input)["worker_results"][0]["business_result"] is None
    assert isinstance(provider, EngineeredAgentProvider)
    assert provider.provider_name == "deepseek"
    assert provider.api_dialect == "responses"
    assert provider.model_name == "deepseek-v4-flash"
    assert len(provider.prompt_bundle_sha256) == 64
    answer_instructions = captured[3]["instructions"]
    assert isinstance(answer_instructions, str)
    assert "证据与当前问题没有直接关系" in answer_instructions
    assert "正文允许多次引用同一标签" in answer_instructions
    assert "首次出现顺序去重填写" in answer_instructions
    for behavior in (
        "单条直接证据",
        "多条候选只引用支持项",
        "非空候选均不支持",
        "部分问题有证据",
    ):
        assert behavior in answer_instructions


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("first_text", "expected_stage"),
    [("not-json", "model_json"), ("{}", "model_schema")],
)
async def test_deepseek_answer_repairs_once_and_counts_both_calls_and_tokens(
    first_text: str,
    expected_stage: str,
) -> None:
    valid = {
        "action": {
            "type": "finish",
            "public_summary": "德国库存事实已返回 [E1]。",
            "business_outcome": "answered",
            "citation_labels": ["[E1]"],
            "artifact_ids": [],
        }
    }
    bodies = iter(
        (
            {
                "status": "completed",
                "usage": {
                    "input_tokens": 10,
                    "output_tokens": 2,
                    "total_tokens": 12,
                },
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "status": "completed",
                        "content": [{"type": "output_text", "text": first_text}],
                    }
                ],
            },
            response_body(valid),
        )
    )
    captured_requests: list[dict[str, object]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        captured_requests.append(json.loads(request.content))
        return httpx.Response(200, json=next(bodies))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = DeepSeekAgentProvider(
            api_key=SecretStr("secret"),
            model="deepseek-v4-flash",
            base_url="https://deepseek.example",
            timeout_seconds=5,
            max_output_tokens=4096,
            http_client=client,
        )
        answer = await provider.compose_answer(
            AnswerRequest(goal=plan().goal, worker_results=(result(),))
        )

    assert answer.action.evidence_ids == [EVIDENCE_ID]  # type: ignore[union-attr]
    assert len(captured_requests) == 2
    assert captured_requests[0]["input"] == captured_requests[1]["input"]
    assert captured_requests[0]["text"] == captured_requests[1]["text"]
    assert expected_stage in captured_requests[1]["instructions"]  # type: ignore[operator]
    assert provider.total_usage.api_calls == 2
    assert provider.total_usage.input_tokens == 133
    assert provider.total_usage.output_tokens == 47
    assert provider.total_usage.total_tokens == 180


@pytest.mark.asyncio
@pytest.mark.parametrize("provider_type", [DeepSeekAgentProvider, QwenAgentProvider])
@pytest.mark.parametrize(
    "failure",
    [
        "none",
        "repeated",
        "duplicate_manifest",
        "json",
        "schema",
        "citation",
        "twice",
        "http",
    ],
)
async def test_private_review_preserves_actual_attempts_without_changing_calls(
    provider_type,
    failure: str,
) -> None:
    from app.agents.runtime import BudgetedAgentProvider
    from tests.unit.test_agent_runtime_adapters import budget_tree

    valid = list(responses())[-1]
    repeated = {
        "action": dict(valid["action"], public_summary="库存 [E1]，数量 [E1]。")
    }
    malformed = {"action": dict(valid["action"], public_summary="库存 [e1]。")}
    first = {
        "none": json.dumps(valid, ensure_ascii=False),
        "repeated": json.dumps(repeated, ensure_ascii=False),
        "duplicate_manifest": json.dumps(
            {"action": dict(repeated["action"], citation_labels=["[E1]", "[E1]"])},
            ensure_ascii=False,
        ),
        "json": "not-json",
        "schema": '{"action":{"type":"finish","tenant_id":"private-identity"}}',
        "citation": json.dumps(malformed, ensure_ascii=False),
        "twice": json.dumps(malformed, ensure_ascii=False),
        "http": "private-provider-error",
    }[failure]
    captured = []
    texts = []

    async def handler(request):
        captured.append(json.loads(request.content))
        text = (
            first
            if len(captured) == 1
            else json.dumps(
                dict(valid, action=dict(valid["action"], public_summary="库存 [E01]。"))
                if failure == "twice"
                else valid,
                ensure_ascii=False,
            )
        )
        texts.append(text)
        body = response_body(valid)
        body["output"][0]["content"][0]["text"] = text
        body["output"].append({"type": "reasoning", "text": "private-thinking"})
        if provider_type is QwenAgentProvider:
            body = {
                "choices": [
                    {
                        "message": {
                            "content": text,
                            "reasoning_content": "private-thinking",
                        }
                    }
                ],
                "usage": {
                    "prompt_tokens": 123,
                    "completion_tokens": 45,
                    "total_tokens": 168,
                },
            }
        return httpx.Response(503 if failure == "http" else 200, json=body)

    trace = RagReviewTrace()
    tree = budget_tree()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = provider_type(
            api_key=SecretStr("private-api-key"),
            model="test-model",
            base_url="https://provider.example",
            timeout_seconds=5,
            max_output_tokens=4096,
            http_client=client,
        )
        adapter = BudgetedAgentProvider(provider=provider, budget=tree)
        with rag_review_trace(trace):
            request = AnswerRequest(goal=plan().goal, worker_results=(result(),))
            if failure in {"twice", "http"}:
                with pytest.raises(
                    AgentProviderOutputError
                    if failure == "twice"
                    else ProviderUnavailableError
                ):
                    await adapter.compose_answer(request)
            else:
                answer = await adapter.compose_answer(request)
                if failure == "repeated":
                    assert (
                        answer.action.public_summary
                        == repeated["action"]["public_summary"]
                    )
                    assert answer.action.evidence_ids == [EVIDENCE_ID]
    expected = 1 if failure in {"none", "repeated", "http"} else 2
    assert (
        len(trace.answer_attempts)
        == len(captured)
        == tree.snapshot().model_calls
        == expected
    )
    for index, attempt in enumerate(trace.answer_attempts):
        sent = captured[index]
        assert attempt["input_payload"] == json.loads(
            sent["input"]
            if provider_type is DeepSeekAgentProvider
            else sent["messages"][1]["content"]
        )
        assert attempt["output_schema"] == (
            sent["text"]["format"]["schema"]
            if provider_type is DeepSeekAgentProvider
            else sent["response_format"]["json_schema"]["schema"]
        )
        assert attempt["system_prompt"] == (
            sent["instructions"]
            if provider_type is DeepSeekAgentProvider
            else sent["messages"][0]["content"]
        )
        if failure not in {"schema", "http"}:
            assert attempt["model_output_text"] == texts[index]
        assert attempt["transport"]["max_output_tokens"] == 4096
        assert "正文允许多次引用同一标签" in attempt["system_prompt"]
    if expected == 2:
        assert (
            trace.answer_attempts[0]["input_payload"]
            == trace.answer_attempts[1]["input_payload"]
        )
        assert (
            trace.answer_attempts[0]["output_schema"]
            == trace.answer_attempts[1]["output_schema"]
        )
        assert trace.answer_attempts[-1]["validation_stage"] == (
            "citation_contract" if failure == "twice" else "completed"
        )
    if failure in {"citation", "twice"}:
        assert trace.answer_attempts[0]["validation_reason"] == "malformed_label"
    if failure == "twice":
        assert trace.answer_attempts[-1]["validation_reason"] == "malformed_label"
    if failure == "duplicate_manifest":
        assert trace.answer_attempts[0]["validation_stage"] == "model_schema"
    if failure == "schema":
        assert trace.answer_attempts[0]["schema_issues"]
        assert trace.answer_attempts[0]["model_output_redacted"] is True
    safe = json.dumps(review_value(asdict(trace)))
    assert all(
        value not in safe
        for value in (
            "private-identity",
            "private-thinking",
            "private-api-key",
            "private-provider-error",
        )
    )

    # No stale attempt can receive later output outside the request binding.
    from app.core.rag_trace import record_answer_output

    before = asdict(trace)
    record_answer_output("unbound-output")
    assert asdict(trace) == before


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_code", "retryable"),
    [(401, False), (402, False), (429, True), (503, True)],
)
async def test_deepseek_maps_http_errors_without_leaking_response(
    status_code: int,
    retryable: bool,
) -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code,
            text="api_key=server-secret SQL=DROP TABLE agent_runs D:/private/file",
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = DeepSeekAgentProvider(
            api_key=SecretStr("client-secret"),
            model="deepseek-v4-flash",
            base_url="https://deepseek.example",
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
    for forbidden in ("server-secret", "client-secret", "DROP TABLE", "D:/private"):
        assert forbidden not in safe


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [
        {"status": "completed", "output": []},
        {"status": "incomplete", "output": []},
        {
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": ""}],
                }
            ],
        },
    ],
)
async def test_deepseek_rejects_incomplete_or_empty_output(
    body: dict[str, object],
) -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=body)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = DeepSeekAgentProvider(
            api_key=SecretStr("client-secret"),
            model="deepseek-v4-flash",
            base_url="https://deepseek.example",
            timeout_seconds=5,
            max_output_tokens=4096,
            http_client=client,
        )
        with pytest.raises(AgentProviderOutputError) as captured:
            await provider.create_plan(
                PlannerRequest(goal=plan().goal, available_workers=(profile(),))
            )

    assert captured.value.stage == "provider_envelope"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("output_text", "expected_stage"),
    [("not-json", "model_json"), ("{}", "model_schema")],
)
async def test_deepseek_classifies_model_json_and_schema_failures(
    output_text: str,
    expected_stage: str,
) -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "status": "completed",
                        "content": [{"type": "output_text", "text": output_text}],
                    }
                ],
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = DeepSeekAgentProvider(
            api_key=SecretStr("client-secret"),
            model="deepseek-v4-flash",
            base_url="https://deepseek.example",
            timeout_seconds=5,
            max_output_tokens=4096,
            http_client=client,
        )
        with pytest.raises(AgentProviderOutputError) as captured:
            await provider.create_plan(
                PlannerRequest(goal=plan().goal, available_workers=(profile(),))
            )

    assert captured.value.stage == expected_stage
    assert captured.value.to_detail().model_dump() == {
        "code": "PROVIDER_ERROR",
        "message": "模型返回的Agent结构化结果无效",
        "retryable": False,
        "field": "message",
    }


@pytest.mark.asyncio
async def test_deepseek_maps_timeout_without_leaking_request() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout(
            "Bearer client-secret SQL=SELECT secret", request=request
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = DeepSeekAgentProvider(
            api_key=SecretStr("client-secret"),
            model="deepseek-v4-flash",
            base_url="https://deepseek.example",
            timeout_seconds=5,
            max_output_tokens=4096,
            http_client=client,
        )
        with pytest.raises(ProviderTimeoutError):
            await provider.create_plan(
                PlannerRequest(goal=plan().goal, available_workers=(profile(),))
            )


@pytest.mark.asyncio
async def test_deepseek_factory_uses_only_deepseek_settings() -> None:
    settings = Settings(  # type: ignore[call-arg]
        _env_file=None,
        llm_provider="deepseek",
        deepseek_api_key=SecretStr("factory-secret"),
        deepseek_base_url="https://deepseek.example/",
        deepseek_agent_max_output_tokens=2048,
    )

    provider = create_engineered_agent_provider(settings)

    assert isinstance(provider, DeepSeekAgentProvider)
    await provider.aclose()


def test_deepseek_rejects_non_https_constructor_endpoint() -> None:
    with pytest.raises(ValueError, match="HTTPS"):
        DeepSeekAgentProvider(
            api_key=SecretStr("secret"),
            model="deepseek-v4-flash",
            base_url="http://deepseek.example",
            timeout_seconds=5,
            max_output_tokens=4096,
        )


def test_deepseek_settings_reject_unsafe_endpoint_and_output_limit() -> None:
    with pytest.raises(ValidationError, match="DEEPSEEK_BASE_URL"):
        Settings(  # type: ignore[call-arg]
            _env_file=None,
            deepseek_base_url="https://user:secret@deepseek.example?key=secret",
        )
    with pytest.raises(ValidationError):
        Settings(  # type: ignore[call-arg]
            _env_file=None,
            deepseek_agent_max_output_tokens=128,
        )

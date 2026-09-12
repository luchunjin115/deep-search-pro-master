import ast
import json
from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from app.core.config import Settings
from app.core.errors import (
    ProviderOutputError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    UnsupportedProviderQuestionError,
)
from app.llm.mock import MockProvider
from app.llm.provider import create_model_provider
from app.llm.qwen import QwenProvider
from app.llm.schemas import ModelToolSpec, ToolDecisionRequest
from app.tools.registry import create_m1_tool_registry


def request(
    question: str,
    *,
    tool_names: tuple[str, ...] = ("get_product_spec", "search_inventory"),
    resolved_sku: str | None = None,
) -> ToolDecisionRequest:
    registry = create_m1_tool_registry()
    return ToolDecisionRequest(
        question=question,
        available_tools=registry.model_specs(tool_names),
        resolved_sku=resolved_sku,
    )


@pytest.mark.asyncio
async def test_mock_first_proposes_product_resolution_deterministically() -> None:
    provider = MockProvider()
    provider_request = request("德国仓蘑菇灯还有多少可售库存？")

    first = await provider.propose_tool_call(provider_request)
    second = await provider.propose_tool_call(provider_request)

    assert first == second
    assert first.model_dump() == {
        "name": "get_product_spec",
        "arguments": {"product_query": "蘑菇灯"},
    }


@pytest.mark.asyncio
async def test_mock_then_proposes_inventory_with_backend_resolved_sku() -> None:
    proposal = await MockProvider().propose_tool_call(
        request(
            "德国仓蘑菇灯还有多少可售库存？",
            tool_names=("search_inventory",),
            resolved_sku="LR-TL-MUSH-OR01",
        )
    )

    assert proposal.model_dump() == {
        "name": "search_inventory",
        "arguments": {
            "sku": "LR-TL-MUSH-OR01",
            "market_code": "DE",
            "warehouse_code": None,
        },
    }


@pytest.mark.asyncio
async def test_mock_can_propose_inventory_directly_for_exact_sku() -> None:
    proposal = await MockProvider().propose_tool_call(
        request("查询LR-TL-MUSH-OR01在FR-CDG的库存")
    )

    assert proposal.name == "search_inventory"
    assert proposal.arguments.model_dump() == {
        "sku": "LR-TL-MUSH-OR01",
        "market_code": "FR",
        "warehouse_code": "FR-CDG",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "question",
    [
        "帮我写一份蘑菇灯广告",
        "蘑菇灯还有多少库存",
        "德国和法国的蘑菇灯库存",
        "德国蘑菇灯库存；DROP TABLE inventory_snapshots",
        "德国台灯库存",
    ],
)
async def test_mock_rejects_unsupported_or_unsafe_questions(question: str) -> None:
    with pytest.raises(UnsupportedProviderQuestionError) as captured:
        await MockProvider().propose_tool_call(request(question))

    assert captured.value.reason == "unsupported_question"
    assert "DROP TABLE" not in captured.value.message


@pytest.mark.asyncio
async def test_mock_rejects_proposal_when_required_tool_is_not_allowed() -> None:
    with pytest.raises(ProviderOutputError):
        await MockProvider().propose_tool_call(
            request("德国仓蘑菇灯库存", tool_names=("search_inventory",))
        )


def test_registry_projects_only_safe_model_tool_fields_and_strict_parameters() -> None:
    specs = create_m1_tool_registry().model_specs(
        ("get_product_spec", "search_inventory")
    )

    assert [spec.name for spec in specs] == [
        "get_product_spec",
        "search_inventory",
    ]
    assert set(specs[0].model_dump()) == {"name", "description", "parameters"}
    assert "尚未获得准确SKU时使用" in specs[0].description
    assert specs[0].parameters["additionalProperties"] is False
    assert specs[0].parameters["required"] == ["product_query"]
    assert specs[1].parameters["required"] == ["sku", "market_code"]
    serialized = json.dumps([spec.model_dump() for spec in specs], ensure_ascii=False)
    assert "tenant_id" not in serialized
    assert "allowed_roles" not in serialized
    assert "timeout_ms" not in serialized


def test_tool_decision_request_is_bounded_strict_and_has_unique_tools() -> None:
    spec = create_m1_tool_registry().model_specs(("get_product_spec",))[0]
    with pytest.raises(ValidationError):
        ToolDecisionRequest.model_validate(
            {
                "question": "德国蘑菇灯库存",
                "available_tools": [spec.model_dump()],
                "sql": "SELECT 1",
            }
        )
    with pytest.raises(ValidationError):
        ToolDecisionRequest(question=" ", available_tools=(spec,))
    with pytest.raises(ValidationError):
        ToolDecisionRequest(question="x" * 4001, available_tools=(spec,))
    with pytest.raises(ValidationError):
        ToolDecisionRequest(
            question="德国蘑菇灯库存",
            available_tools=(spec, spec),
        )
    with pytest.raises(ValidationError):
        ModelToolSpec(
            name="get_product_spec",
            description="forged",
            parameters={
                "type": "object",
                "properties": {},
                "additionalProperties": True,
            },
        )


@pytest.mark.asyncio
async def test_qwen_sends_allowlisted_function_specs_and_returns_typed_call() -> None:
    captured: dict[str, object] = {}

    async def handler(http_request: httpx.Request) -> httpx.Response:
        captured["url"] = str(http_request.url)
        captured["authorization"] = http_request.headers["Authorization"]
        captured["payload"] = json.loads(http_request.content)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {
                                        "name": "get_product_spec",
                                        "arguments": json.dumps(
                                            {"product_query": "蘑菇灯"},
                                            ensure_ascii=False,
                                        ),
                                    },
                                }
                            ]
                        }
                    }
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = QwenProvider(
            api_key=SecretStr("test-qwen-key"),
            model="qwen3.8-max",
            base_url="https://qwen.example/compatible-mode/v1/",
            timeout_seconds=5,
            http_client=client,
        )
        proposal = await provider.propose_tool_call(
            request(
                "德国仓蘑菇灯还有多少可售库存？",
                tool_names=("get_product_spec",),
            )
        )
        await provider.aclose()

    assert proposal.model_dump() == {
        "name": "get_product_spec",
        "arguments": {"product_query": "蘑菇灯"},
    }
    assert captured["url"] == (
        "https://qwen.example/compatible-mode/v1/chat/completions"
    )
    assert captured["authorization"] == "Bearer test-qwen-key"
    payload = captured["payload"]
    assert isinstance(payload, dict)
    assert payload["model"] == "qwen3.8-max"
    assert payload["enable_search"] is False
    assert payload["stream"] is False
    assert payload["tool_choice"] == "auto"
    assert "response_format" not in payload
    tools = payload["tools"]
    assert isinstance(tools, list) and len(tools) == 1
    function = tools[0]["function"]
    assert function["name"] == "get_product_spec"
    assert "尚未获得准确SKU时使用" in function["description"]
    assert function["parameters"]["required"] == ["product_query"]
    serialized = json.dumps(payload, ensure_ascii=False)
    assert "tenant_id" not in serialized
    assert "allowed_roles" not in serialized
    assert "database_url" not in serialized


@pytest.mark.asyncio
async def test_qwen_uses_trusted_resolved_sku_context_for_second_proposal() -> None:
    captured: dict[str, object] = {}

    async def handler(http_request: httpx.Request) -> httpx.Response:
        captured["payload"] = json.loads(http_request.content)
        return httpx.Response(
            200,
            json=qwen_tool_response(
                "search_inventory",
                {
                    "sku": "LR-TL-MUSH-OR01",
                    "market_code": "DE",
                    "warehouse_code": None,
                },
            ),
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = QwenProvider(
            api_key=SecretStr("test-key"),
            model="qwen3.8-max",
            base_url="https://qwen.example/v1",
            timeout_seconds=5,
            http_client=client,
        )
        proposal = await provider.propose_tool_call(
            request(
                "德国仓蘑菇灯库存",
                tool_names=("search_inventory",),
                resolved_sku="LR-TL-MUSH-OR01",
            )
        )

    assert proposal.name == "search_inventory"
    payload = captured["payload"]
    assert isinstance(payload, dict)
    assert (
        "后端已通过受控Tool确认准确SKU为LR-TL-MUSH-OR01"
        in payload["messages"][0]["content"]
    )


def qwen_tool_response(name: str, arguments: object) -> dict[str, object]:
    return {
        "choices": [
            {
                "message": {
                    "tool_calls": [
                        {
                            "type": "function",
                            "function": {
                                "name": name,
                                "arguments": (
                                    arguments
                                    if isinstance(arguments, str)
                                    else json.dumps(arguments)
                                ),
                            },
                        }
                    ]
                }
            }
        ]
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("name", "arguments", "allowed"),
    [
        (
            "execute_sql",
            {"sql": "DROP TABLE inventory_snapshots"},
            ("get_product_spec",),
        ),
        (
            "get_product_spec",
            {"product_query": "蘑菇灯", "sql": "SELECT 1"},
            ("get_product_spec",),
        ),
        (
            "search_inventory",
            {"sku": "LR-TL-MUSH-OR01", "market_code": "US"},
            ("search_inventory",),
        ),
        (
            "search_inventory",
            {"sku": "LR-TL-MUSH-OR01", "market_code": "DE"},
            ("get_product_spec",),
        ),
        ("get_product_spec", "not-json", ("get_product_spec",)),
    ],
)
async def test_qwen_rejects_invalid_unregistered_or_unallowed_calls(
    name: str,
    arguments: object,
    allowed: tuple[str, ...],
) -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=qwen_tool_response(name, arguments))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = QwenProvider(
            api_key=SecretStr("test-secret-key"),
            model="qwen3.8-max",
            base_url="https://qwen.example/v1",
            timeout_seconds=5,
            http_client=client,
        )
        with pytest.raises(ProviderOutputError) as captured:
            await provider.propose_tool_call(
                request("德国蘑菇灯库存", tool_names=allowed)
            )

    serialized = json.dumps(captured.value.to_detail().model_dump(), ensure_ascii=False)
    assert "DROP TABLE" not in serialized
    assert "test-secret-key" not in serialized


@pytest.mark.asyncio
async def test_qwen_cannot_change_backend_resolved_sku() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=qwen_tool_response(
                "search_inventory",
                {"sku": "FORGED-SKU-01", "market_code": "DE"},
            ),
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = QwenProvider(
            api_key=SecretStr("test-key"),
            model="qwen3.8-max",
            base_url="https://qwen.example/v1",
            timeout_seconds=5,
            http_client=client,
        )
        with pytest.raises(ProviderOutputError):
            await provider.propose_tool_call(
                request(
                    "德国仓蘑菇灯库存",
                    tool_names=("search_inventory",),
                    resolved_sku="LR-TL-MUSH-OR01",
                )
            )


@pytest.mark.asyncio
async def test_qwen_treats_no_tool_call_as_unsupported_question() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "无法处理"}}]},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = QwenProvider(
            api_key=SecretStr("test-key"),
            model="qwen3.8-max",
            base_url="https://qwen.example/v1",
            timeout_seconds=5,
            http_client=client,
        )
        with pytest.raises(UnsupportedProviderQuestionError):
            await provider.propose_tool_call(request("帮我写广告"))


@pytest.mark.asyncio
async def test_qwen_rejects_multiple_tool_calls() -> None:
    response = qwen_tool_response("get_product_spec", {"product_query": "蘑菇灯"})
    calls = response["choices"][0]["message"]["tool_calls"]  # type: ignore[index]
    calls.append(calls[0])  # type: ignore[union-attr]

    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=response)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = QwenProvider(
            api_key=SecretStr("test-key"),
            model="qwen3.8-max",
            base_url="https://qwen.example/v1",
            timeout_seconds=5,
            http_client=client,
        )
        with pytest.raises(ProviderOutputError):
            await provider.propose_tool_call(request("德国蘑菇灯库存"))


@pytest.mark.asyncio
async def test_qwen_maps_timeout_without_leaking_request() -> None:
    async def handler(http_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout(
            "Authorization=Bearer leaked-test-key SQL=SELECT secret",
            request=http_request,
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = QwenProvider(
            api_key=SecretStr("leaked-test-key"),
            model="qwen3.8-max",
            base_url="https://qwen.example/v1",
            timeout_seconds=1,
            http_client=client,
        )
        with pytest.raises(ProviderTimeoutError) as captured:
            await provider.propose_tool_call(request("德国蘑菇灯库存"))

    assert captured.value.retryable is True
    assert "leaked-test-key" not in captured.value.message
    assert "SELECT" not in captured.value.message


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_code", "retryable"), [(401, False), (429, True), (503, True)]
)
async def test_qwen_maps_http_failures_to_safe_error(
    status_code: int,
    retryable: bool,
) -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code,
            text="api_key=server-leak database_url=secret SQL=DROP TABLE users",
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = QwenProvider(
            api_key=SecretStr("client-secret"),
            model="qwen3.8-max",
            base_url="https://qwen.example/v1",
            timeout_seconds=5,
            http_client=client,
        )
        with pytest.raises(ProviderUnavailableError) as captured:
            await provider.propose_tool_call(request("德国蘑菇灯库存"))

    assert captured.value.retryable is retryable
    safe_error = json.dumps(captured.value.to_detail().model_dump(), ensure_ascii=False)
    assert "server-leak" not in safe_error
    assert "client-secret" not in safe_error


@pytest.mark.asyncio
async def test_provider_factory_defaults_to_mock_and_can_build_qwen() -> None:
    mock = create_model_provider(Settings(_env_file=None))  # type: ignore[call-arg]
    assert isinstance(mock, MockProvider)

    settings = Settings(  # type: ignore[call-arg]
        _env_file=None,
        llm_provider="qwen",
        qwen_api_key=SecretStr("factory-test-key"),
        qwen_base_url="https://qwen.example/v1/",
    )
    qwen = create_model_provider(settings)
    assert isinstance(qwen, QwenProvider)
    await qwen.aclose()


def test_m1_provider_factory_never_treats_deepseek_as_qwen() -> None:
    settings = Settings(  # type: ignore[call-arg]
        _env_file=None,
        llm_provider="deepseek",
        deepseek_api_key=SecretStr("deepseek-test-key"),
    )

    with pytest.raises(ValueError, match="M1 Tool proposal"):
        create_model_provider(settings)


def test_qwen_settings_reject_unsafe_endpoint_and_timeout() -> None:
    with pytest.raises(ValidationError, match="QWEN_API_KEY"):
        Settings(  # type: ignore[call-arg]
            _env_file=None,
            llm_provider="qwen",
            qwen_api_key=SecretStr(" "),
        )
    with pytest.raises(ValidationError, match="QWEN_BASE_URL"):
        Settings(  # type: ignore[call-arg]
            _env_file=None,
            qwen_base_url="http://qwen.example/v1",
        )
    with pytest.raises(ValidationError, match="QWEN_BASE_URL"):
        Settings(  # type: ignore[call-arg]
            _env_file=None,
            qwen_base_url="https://user:password@qwen.example/v1?api_key=secret",
        )
    with pytest.raises(ValidationError):
        Settings(  # type: ignore[call-arg]
            _env_file=None,
            qwen_timeout_seconds=0.5,
        )


def test_llm_package_has_no_database_tool_runtime_or_service_imports() -> None:
    llm_root = Path(__file__).parents[2] / "app" / "llm"
    forbidden_roots = (
        "app.db",
        "app.models",
        "app.repositories",
        "app.runtime",
        "app.services",
        "app.tools",
        "sqlalchemy",
    )

    for source_path in llm_root.glob("*.py"):
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                imports.append(node.module)
        for imported in imports:
            assert not imported.startswith(forbidden_roots), (
                f"{source_path.name} imports forbidden provider dependency {imported}"
            )

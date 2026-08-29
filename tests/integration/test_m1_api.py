from __future__ import annotations

from collections.abc import Generator
from dataclasses import dataclass
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.exc import OperationalError

from app.api.dependencies import get_model_provider
from app.core.config import Settings
from app.core.errors import ProviderTimeoutError
from app.db.session import DatabaseRuntime, create_database_runtime
from app.llm.provider import ModelProvider
from app.llm.schemas import (
    SearchInventoryToolCall,
    ToolCallProposal,
    ToolDecisionRequest,
)
from app.main import create_app
from app.models.catalog import Product, ProductVariant
from app.models.inventory import InventorySnapshot, Warehouse
from app.models.runtime import Message, Thread
from app.repositories.inventory import InventoryRepository
from app.schemas.inventory import SearchInventoryInput
from scripts.seed_m1 import seed_m1

DE_EMAIL = "de.operator@demo.deepsearch.local"
FR_EMAIL = "fr.operator@demo.deepsearch.local"
PASSWORD = "M1-demo-only-change-me"


@dataclass(frozen=True, slots=True)
class ApiFixture:
    client: TestClient
    runtime: DatabaseRuntime
    application: FastAPI


@pytest.fixture(scope="module")
def api_fixture(
    tmp_path_factory: pytest.TempPathFactory,
) -> Generator[ApiFixture, None, None]:
    settings = Settings(_env_file=".env.example", app_env="test")  # type: ignore[call-arg]
    seed_m1(
        settings,
        manifest_path=tmp_path_factory.mktemp("m1_api") / "manifest.json",
    )
    runtime = create_database_runtime(settings)
    application = create_app(settings, runtime)
    with TestClient(application) as client:
        yield ApiFixture(client=client, runtime=runtime, application=application)

    with runtime.session_factory.begin() as session:
        session.execute(delete(Thread).where(Thread.title.like("M1-18 API Test%")))
    runtime.engine.dispose()


def login(client: TestClient, email: str = DE_EMAIL) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": PASSWORD},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def create_thread(client: TestClient, token: str, suffix: str) -> str:
    response = client.post(
        "/api/v1/threads",
        headers=bearer(token),
        json={"title": f"M1-18 API Test {suffix}"},
    )
    assert response.status_code == 201
    return response.json()["thread_id"]


def test_openapi_and_cors_expose_the_versioned_contract(
    api_fixture: ApiFixture,
) -> None:
    client = api_fixture.client
    openapi = client.get("/openapi.json")

    assert openapi.status_code == 200
    assert {
        "/api/v1/auth/login",
        "/api/v1/me",
        "/api/v1/threads",
        "/api/v1/threads/{thread_id}/messages",
        "/api/v1/evidence/{evidence_id}",
    }.issubset(openapi.json()["paths"])

    preflight = client.options(
        "/api/v1/threads",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_login_me_chat_and_evidence_complete_real_backend_flow(
    api_fixture: ApiFixture,
) -> None:
    client = api_fixture.client
    token = login(client)
    me = client.get("/api/v1/me", headers=bearer(token))
    assert me.status_code == 200
    assert me.json()["email"] == DE_EMAIL
    assert me.json()["market_scopes"] == ["DE"]

    thread_id = create_thread(client, token, "happy path")
    chat = client.post(
        f"/api/v1/threads/{thread_id}/messages",
        headers=bearer(token),
        json={"message": "德国仓蘑菇灯还有多少可售库存？"},
    )

    assert chat.status_code == 200, chat.text
    payload = chat.json()
    assert payload["status"] == "completed"
    assert "可售库存为125件" in payload["answer"]
    assert "合成演示数据" in payload["answer"]
    assert payload["execution"]["tool_names"] == [
        "get_product_spec",
        "search_inventory",
    ]
    assert payload["execution"]["duration_ms"] >= 0
    assert len(payload["evidence"]) == 1
    with api_fixture.runtime.session_factory() as session:
        messages = list(
            session.scalars(
                select(Message)
                .where(Message.thread_id == thread_id)
                .order_by(Message.created_at, Message.id)
            )
        )
    assert {message.role for message in messages} == {"user", "assistant"}
    assistant = next(message for message in messages if message.role == "assistant")
    assert str(assistant.id) == payload["message_id"]

    evidence_id = payload["evidence"][0]["id"]
    detail = client.get(
        f"/api/v1/evidence/{evidence_id}",
        headers=bearer(token),
    )
    assert detail.status_code == 200
    assert detail.json()["structured_data"]["available"] == 125
    assert detail.json()["access_scope"]["market_codes"] == ["DE"]
    assert detail.json()["synthetic_data"] is True


def test_auth_validation_and_thread_ownership_use_safe_http_errors(
    api_fixture: ApiFixture,
) -> None:
    client = api_fixture.client
    missing = client.get("/api/v1/me")
    assert missing.status_code == 401
    assert missing.headers["www-authenticate"] == "Bearer"
    assert missing.json()["error"]["code"] == "UNAUTHENTICATED"

    wrong_password = client.post(
        "/api/v1/auth/login",
        json={"email": DE_EMAIL, "password": "definitely-wrong"},
    )
    assert wrong_password.status_code == 401
    assert "password" not in wrong_password.text.lower()

    invalid = client.post(
        "/api/v1/threads",
        headers=bearer(login(client)),
        json={"title": ""},
    )
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "VALIDATION_ERROR"

    de_token = login(client, DE_EMAIL)
    fr_token = login(client, FR_EMAIL)
    de_thread = create_thread(client, de_token, "ownership")
    foreign_thread = client.post(
        f"/api/v1/threads/{de_thread}/messages",
        headers=bearer(fr_token),
        json={"message": "德国仓蘑菇灯还有多少库存？"},
    )
    assert foreign_thread.status_code == 404
    assert foreign_thread.json()["error"]["code"] == "THREAD_NOT_FOUND"


def test_market_denial_and_evidence_scope_are_enforced(api_fixture: ApiFixture) -> None:
    client = api_fixture.client
    de_token = login(client, DE_EMAIL)
    fr_token = login(client, FR_EMAIL)
    thread_id = create_thread(client, de_token, "market scope")

    with api_fixture.runtime.session_factory() as session:
        messages_before = len(
            list(session.scalars(select(Message).where(Message.thread_id == thread_id)))
        )

    denied = client.post(
        f"/api/v1/threads/{thread_id}/messages",
        headers=bearer(de_token),
        json={"message": "法国仓蘑菇灯还有多少库存？"},
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "FORBIDDEN"
    assert denied.json()["trace_id"] is not None
    with api_fixture.runtime.session_factory() as session:
        messages_after = len(
            list(session.scalars(select(Message).where(Message.thread_id == thread_id)))
        )
    assert messages_after == messages_before

    allowed = client.post(
        f"/api/v1/threads/{thread_id}/messages",
        headers=bearer(de_token),
        json={"message": "德国仓蘑菇灯还有多少库存？"},
    )
    evidence_id = allowed.json()["evidence"][0]["id"]
    hidden = client.get(
        f"/api/v1/evidence/{evidence_id}",
        headers=bearer(fr_token),
    )
    assert hidden.status_code == 404
    assert hidden.json()["error"]["code"] == "EVIDENCE_NOT_FOUND"


@pytest.mark.usefixtures("api_fixture")
def test_provider_timeout_maps_to_504_with_trace(api_fixture: ApiFixture) -> None:
    class TimeoutProvider:
        async def propose_tool_call(
            self,
            _request: ToolDecisionRequest,
        ) -> ToolCallProposal:
            raise ProviderTimeoutError

    async def override_provider() -> ModelProvider:
        return TimeoutProvider()

    client = api_fixture.client
    application = api_fixture.application
    application.dependency_overrides[get_model_provider] = override_provider
    try:
        token = login(client)
        thread_id = create_thread(client, token, "provider timeout")
        response = client.post(
            f"/api/v1/threads/{thread_id}/messages",
            headers=bearer(token),
            json={"message": "德国仓蘑菇灯还有多少库存？"},
        )
    finally:
        application.dependency_overrides.pop(get_model_provider, None)

    assert response.status_code == 504
    assert response.json()["error"]["code"] == "PROVIDER_ERROR"
    assert response.json()["trace_id"] is not None


def test_zero_inventory_is_a_successful_fact_with_evidence(
    api_fixture: ApiFixture,
) -> None:
    client = api_fixture.client
    runtime = api_fixture.runtime

    with runtime.session_factory.begin() as session:
        snapshot = session.scalar(
            select(InventorySnapshot)
            .join(ProductVariant, ProductVariant.id == InventorySnapshot.variant_id)
            .join(Warehouse, Warehouse.id == InventorySnapshot.warehouse_id)
            .where(
                ProductVariant.sku == "LR-TL-MUSH-OR01",
                Warehouse.code == "DE-FRA",
            )
        )
        assert snapshot is not None
        original_quantities = (
            snapshot.on_hand,
            snapshot.reserved,
            snapshot.unsellable,
        )
        snapshot.on_hand = 0
        snapshot.reserved = 0
        snapshot.unsellable = 0

    try:
        token = login(client)
        thread_id = create_thread(client, token, "zero inventory")
        response = client.post(
            f"/api/v1/threads/{thread_id}/messages",
            headers=bearer(token),
            json={"message": "德国仓蘑菇灯还有多少可售库存？"},
        )

        assert response.status_code == 200, response.text
        payload = response.json()
        assert "可售库存为0件" in payload["answer"]
        assert len(payload["evidence"]) == 1
        detail = client.get(
            f"/api/v1/evidence/{payload['evidence'][0]['id']}",
            headers=bearer(token),
        )
        assert detail.status_code == 200
        assert detail.json()["structured_data"]["available"] == 0
    finally:
        with runtime.session_factory.begin() as session:
            snapshot = session.scalar(
                select(InventorySnapshot)
                .join(ProductVariant, ProductVariant.id == InventorySnapshot.variant_id)
                .join(Warehouse, Warehouse.id == InventorySnapshot.warehouse_id)
                .where(
                    ProductVariant.sku == "LR-TL-MUSH-OR01",
                    Warehouse.code == "DE-FRA",
                )
            )
            assert snapshot is not None
            (
                snapshot.on_hand,
                snapshot.reserved,
                snapshot.unsellable,
            ) = original_quantities


def test_missing_inventory_returns_404_without_business_evidence(
    api_fixture: ApiFixture,
) -> None:
    class MissingInventoryProvider:
        async def propose_tool_call(
            self,
            request: ToolDecisionRequest,
        ) -> ToolCallProposal:
            assert "search_inventory" in request.allowed_tool_names
            return SearchInventoryToolCall(
                name="search_inventory",
                arguments=SearchInventoryInput(
                    sku="MISSING-SKU-01",
                    market_code="DE",
                    warehouse_code="DE-FRA",
                ),
            )

    async def override_provider() -> ModelProvider:
        return MissingInventoryProvider()

    client = api_fixture.client
    application = api_fixture.application
    application.dependency_overrides[get_model_provider] = override_provider
    try:
        token = login(client)
        thread_id = create_thread(client, token, "missing inventory")
        response = client.post(
            f"/api/v1/threads/{thread_id}/messages",
            headers=bearer(token),
            json={"message": "查询德国仓MISSING-SKU-01的库存"},
        )
    finally:
        application.dependency_overrides.pop(get_model_provider, None)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "INVENTORY_NOT_FOUND"
    assert response.json()["trace_id"] is not None
    with api_fixture.runtime.session_factory() as session:
        assert (
            list(session.scalars(select(Message).where(Message.thread_id == thread_id)))
            == []
        )


def test_ambiguous_product_returns_409_before_inventory_query(
    api_fixture: ApiFixture,
) -> None:
    runtime = api_fixture.runtime
    product_id = uuid4()
    variant_id = uuid4()

    with runtime.session_factory.begin() as session:
        tenant_id = session.scalar(
            select(Product.tenant_id)
            .join(ProductVariant, ProductVariant.product_id == Product.id)
            .where(ProductVariant.sku == "LR-TL-MUSH-OR01")
        )
        assert tenant_id is not None
        session.add(
            Product(
                id=product_id,
                tenant_id=tenant_id,
                spu="M1-20-AMB-SPU",
                name_zh="合成歧义测试台灯",
                name_en="Synthetic Ambiguous Test Lamp",
                aliases=["蘑菇灯"],
                status="candidate",
                is_demo=True,
            )
        )
        session.add(
            ProductVariant(
                id=variant_id,
                tenant_id=tenant_id,
                product_id=product_id,
                sku="M1-20-AMB-SKU",
                status="candidate",
            )
        )

    try:
        token = login(api_fixture.client)
        thread_id = create_thread(api_fixture.client, token, "ambiguous product")
        response = api_fixture.client.post(
            f"/api/v1/threads/{thread_id}/messages",
            headers=bearer(token),
            json={"message": "德国仓蘑菇灯还有多少可售库存？"},
        )
    finally:
        with runtime.session_factory.begin() as session:
            session.execute(delete(Product).where(Product.id == product_id))

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "AMBIGUOUS_PRODUCT"
    assert response.json()["trace_id"] is not None


def test_database_statement_timeout_maps_to_safe_504(
    api_fixture: ApiFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class StatementTimeout(Exception):
        sqlstate = "57014"

    def raise_timeout(
        _repository: InventoryRepository,
        *_arguments: object,
        **_keywords: object,
    ) -> list[object]:
        raise OperationalError(
            "SELECT secret_inventory FROM internal_table",
            {},
            StatementTimeout("canceling statement due to statement timeout"),
        )

    monkeypatch.setattr(InventoryRepository, "find_latest", raise_timeout)
    token = login(api_fixture.client)
    thread_id = create_thread(api_fixture.client, token, "database timeout")
    response = api_fixture.client.post(
        f"/api/v1/threads/{thread_id}/messages",
        headers=bearer(token),
        json={"message": "德国仓蘑菇灯还有多少可售库存？"},
    )

    assert response.status_code == 504
    assert response.json()["error"]["code"] == "DATABASE_TIMEOUT"
    assert response.json()["error"]["retryable"] is True
    assert response.json()["trace_id"] is not None
    assert "secret_inventory" not in response.text
    assert "internal_table" not in response.text

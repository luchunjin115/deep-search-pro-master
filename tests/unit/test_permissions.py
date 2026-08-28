from dataclasses import replace
from typing import cast
from uuid import UUID, uuid4

import pytest

from app.core.errors import (
    MarketPermissionDeniedError,
    RolePermissionDeniedError,
    TenantPermissionDeniedError,
    ToolNotAllowedError,
    UnsafeToolPermissionError,
)
from app.runtime.context import RunContext
from app.runtime.permissions import PermissionGuard
from app.schemas.common import MarketCode, RoleName
from app.schemas.inventory import InventoryResult, SearchInventoryInput
from app.schemas.product import GetProductSpecInput, ProductSpecResult
from app.tools.registry import (
    DuplicateToolRegistrationError,
    InvalidToolDefinitionError,
    ToolRegistry,
    create_m1_tool_registry,
)


def context(
    *,
    tenant_id: UUID | None = None,
    roles: tuple[RoleName, ...] = ("amazon_operator",),
    market_scopes: tuple[str, ...] = ("DE",),
) -> RunContext:
    return RunContext(
        user_id=uuid4(),
        tenant_id=tenant_id or uuid4(),
        roles=roles,
        market_scopes=cast(tuple[MarketCode, ...], market_scopes),
        thread_id=uuid4(),
        trace_id=uuid4(),
    )


def test_m1_registry_contains_exact_two_versioned_read_only_tools() -> None:
    registry = create_m1_tool_registry()

    assert registry.names == ("get_product_spec", "search_inventory")
    product = registry.get("get_product_spec")
    inventory = registry.get("search_inventory")
    assert product.input_schema is GetProductSpecInput
    assert product.output_schema is ProductSpecResult
    assert product.version == "1.0.0"
    assert product.timeout_ms == 3_000
    assert product.data_scope == "tenant"
    assert product.side_effect == "read"
    assert inventory.input_schema is SearchInventoryInput
    assert inventory.output_schema is InventoryResult
    assert inventory.data_scope == "market"
    assert inventory.side_effect == "read"
    assert (
        product.allowed_roles
        == inventory.allowed_roles
        == frozenset({"company_owner", "product_scout", "amazon_operator"})
    )


def test_registry_rejects_duplicate_or_invalid_metadata() -> None:
    definition = create_m1_tool_registry().get("get_product_spec")
    with pytest.raises(DuplicateToolRegistrationError):
        ToolRegistry((definition, definition))
    with pytest.raises(InvalidToolDefinitionError):
        replace(definition, version="latest")
    with pytest.raises(InvalidToolDefinitionError):
        replace(definition, timeout_ms=30_001)
    with pytest.raises(InvalidToolDefinitionError):
        replace(definition, allowed_roles=frozenset())


def test_permission_guard_allows_de_operator_for_de_inventory() -> None:
    runtime_context = context()
    grant = PermissionGuard(create_m1_tool_registry()).authorize(
        runtime_context,
        "search_inventory",
        target_tenant_id=runtime_context.tenant_id,
        market_code="DE",
    )

    assert grant.allowed is True
    assert grant.tool == "search_inventory"
    assert grant.version == "1.0.0"
    assert grant.tenant_id == runtime_context.tenant_id
    assert grant.market_code == "DE"


def test_permission_guard_rejects_unregistered_tool_before_downstream_call() -> None:
    runtime_context = context()
    downstream_calls: list[str] = []

    with pytest.raises(ToolNotAllowedError) as captured:
        PermissionGuard(create_m1_tool_registry()).authorize(
            runtime_context,
            "execute_sql",
            target_tenant_id=runtime_context.tenant_id,
            market_code="DE",
        )
        downstream_calls.append("database-called")

    assert downstream_calls == []
    assert captured.value.to_detail().model_dump() == {
        "code": "FORBIDDEN",
        "message": "请求的Tool未注册或不可用",
        "retryable": False,
        "field": "tool",
    }


def test_permission_guard_rejects_wrong_role_tenant_and_market() -> None:
    runtime_context = context()
    product = create_m1_tool_registry().get("get_product_spec")
    owner_only = replace(
        product,
        allowed_roles=cast(frozenset[RoleName], frozenset({"company_owner"})),
    )
    with pytest.raises(RolePermissionDeniedError):
        PermissionGuard(ToolRegistry((owner_only,))).authorize(
            runtime_context,
            "get_product_spec",
            target_tenant_id=runtime_context.tenant_id,
        )

    with pytest.raises(TenantPermissionDeniedError):
        PermissionGuard(create_m1_tool_registry()).authorize(
            runtime_context,
            "search_inventory",
            target_tenant_id=uuid4(),
            market_code="DE",
        )

    with pytest.raises(MarketPermissionDeniedError) as captured:
        PermissionGuard(create_m1_tool_registry()).authorize(
            runtime_context,
            "search_inventory",
            target_tenant_id=runtime_context.tenant_id,
            market_code="FR",
        )
    assert captured.value.to_detail().field == "market_code"

    with pytest.raises(MarketPermissionDeniedError):
        PermissionGuard(create_m1_tool_registry()).authorize(
            runtime_context,
            "search_inventory",
            target_tenant_id=runtime_context.tenant_id,
        )


def test_tenant_scoped_product_tool_needs_no_market() -> None:
    runtime_context = context(market_scopes=("FR",))

    grant = PermissionGuard(create_m1_tool_registry()).authorize(
        runtime_context,
        "get_product_spec",
        target_tenant_id=runtime_context.tenant_id,
    )

    assert grant.allowed is True
    assert grant.tool == "get_product_spec"
    assert grant.market_code is None


def test_system_read_only_policy_rejects_write_metadata() -> None:
    runtime_context = context()
    inventory = create_m1_tool_registry().get("search_inventory")
    unsafe_registry = ToolRegistry((replace(inventory, side_effect="write"),))

    with pytest.raises(UnsafeToolPermissionError):
        PermissionGuard(unsafe_registry).authorize(
            runtime_context,
            "search_inventory",
            target_tenant_id=runtime_context.tenant_id,
            market_code="DE",
        )

from __future__ import annotations

import json
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.agents.definitions import AgentDefinition, create_m2_agent_definitions
from app.capabilities.catalog import (
    CapabilityCatalog,
    DuplicateCapabilityRegistrationError,
    create_m1_capability_catalog,
    create_m2_capability_catalog,
)
from app.capabilities.contracts import (
    CapabilityDefinition,
    CapabilityParameterSchema,
    CapabilitySelection,
)
from app.capabilities.resolver import (
    AgentDefinitionNotFoundError,
    CapabilityNotAllowedError,
    CapabilityNotFoundError,
    CapabilityResolver,
)
from app.runtime.context import RunContext


def context(*, roles: tuple[str, ...] = ("amazon_operator",)) -> RunContext:
    return RunContext(  # type: ignore[arg-type]
        user_id=uuid4(),
        tenant_id=uuid4(),
        roles=roles,
        market_scopes=("DE",),
        thread_id=uuid4(),
        trace_id=uuid4(),
    )


def test_m1_and_m2_catalogs_adapt_exact_existing_tool_registries() -> None:
    m1 = create_m1_capability_catalog()
    m2 = create_m2_capability_catalog()

    assert m1.names == ("get_product_spec", "search_inventory")
    assert m1.available_names == m1.names
    assert {definition.kind for definition in m1.list_definitions()} == {"tool"}

    assert m2.names == (
        "business_data",
        "get_evidence_detail",
        "get_product_spec",
        "knowledge",
        "read_uploaded_file",
        "search_inventory",
        "search_knowledge",
    )
    assert m2.available_names == (
        "business_data",
        "get_evidence_detail",
        "get_product_spec",
        "knowledge",
        "read_uploaded_file",
        "search_inventory",
        "search_knowledge",
    )
    assert [item.kind for item in m2.list_definitions()].count("tool") == 5
    assert [item.kind for item in m2.list_definitions()].count("agent") == 2
    assert not {"skill", "runtime"} & {item.kind for item in m2.list_definitions()}


def test_agent_definitions_expose_both_implemented_workers() -> None:
    definitions = create_m2_agent_definitions()

    assert tuple(item.agent_id for item in definitions) == (
        "business_data",
        "knowledge",
    )
    assert definitions[0].allowed_capability_ids == (
        "get_product_spec",
        "search_inventory",
    )
    assert definitions[1].allowed_capability_ids == (
        "get_evidence_detail",
        "read_uploaded_file",
        "search_knowledge",
    )
    assert all(item.can_delegate is False for item in definitions)
    assert definitions[0].implementation_status == "available"
    assert definitions[1].implementation_status == "available"
    assert all(item.input_contract == "AgentHandoff" for item in definitions)
    assert all(item.output_contract == "WorkerResult" for item in definitions)
    assert definitions[0].evidence_source_types == ("database",)
    assert definitions[1].evidence_source_types == ("document", "artifact")


@pytest.mark.parametrize(
    ("agent_id", "expected"),
    [
        ("business_data", ("get_product_spec", "search_inventory")),
        (
            "knowledge",
            (
                "get_evidence_detail",
                "read_uploaded_file",
                "search_knowledge",
            ),
        ),
    ],
)
def test_resolver_projects_only_each_agents_available_tools_in_stable_order(
    agent_id: str,
    expected: tuple[str, ...],
) -> None:
    resolver = CapabilityResolver(
        create_m2_capability_catalog(),
        create_m2_agent_definitions(),
    )

    result = resolver.resolve_for_agent(
        context(),
        agent_id,
        CapabilitySelection(),
    )

    assert tuple(item.capability_id for item in result.capabilities) == expected
    assert result.requesting_agent_id == agent_id
    assert all(item.kind == "tool" for item in result.capabilities)
    assert all(
        item.implementation_status == "available" for item in result.capabilities
    )
    assert all(item.parameters is not None for item in result.capabilities)


def test_safe_projection_excludes_internal_permission_runtime_and_schema_objects() -> (
    None
):
    resolver = CapabilityResolver(
        create_m2_capability_catalog(),
        create_m2_agent_definitions(),
    )
    result = resolver.resolve_for_agent(
        context(),
        "knowledge",
        CapabilitySelection(capability_ids=["read_uploaded_file"]),
    )

    dumped = result.model_dump(mode="json")
    serialized = json.dumps(dumped, ensure_ascii=False).casefold()
    view = dumped["capabilities"][0]

    assert set(view) == {
        "capability_id",
        "kind",
        "version",
        "description",
        "parameters",
        "side_effect",
        "produces_evidence",
        "implementation_status",
    }
    assert view["parameters"]["additionalProperties"] is False
    for forbidden in (
        "allowed_roles",
        "allowed_agent_ids",
        "timeout_ms",
        "data_scope",
        "input_schema",
        "tenant_id",
        "user_id",
        "api_key",
        "storage_key",
        "budget",
        "sql",
    ):
        assert forbidden not in serialized


def test_selection_is_model_controlled_bounded_and_cannot_set_trusted_scope() -> None:
    selection = CapabilitySelection(
        capability_ids=["search_inventory", "get_product_spec"]
    )
    assert selection.capability_ids == ["search_inventory", "get_product_spec"]

    with pytest.raises(ValidationError, match="duplicate"):
        CapabilitySelection(capability_ids=["search_inventory", "search_inventory"])
    with pytest.raises(ValidationError):
        CapabilitySelection(capability_ids=[f"tool_{index}" for index in range(13)])
    for forbidden in ("tenant_id", "user_id", "roles", "budget", "agent_id"):
        with pytest.raises(ValidationError, match=forbidden):
            CapabilitySelection.model_validate(
                {"capability_ids": [], forbidden: "model-controlled"}
            )


def test_resolver_rejects_unknown_cross_worker_and_unknown_agent_without_fallback() -> (
    None
):
    resolver = CapabilityResolver(
        create_m2_capability_catalog(),
        create_m2_agent_definitions(),
    )

    with pytest.raises(CapabilityNotFoundError):
        resolver.resolve_for_agent(
            context(),
            "business_data",
            CapabilitySelection(capability_ids=["invented_capability"]),
        )
    with pytest.raises(CapabilityNotAllowedError):
        resolver.resolve_for_agent(
            context(),
            "business_data",
            CapabilitySelection(capability_ids=["search_knowledge"]),
        )
    with pytest.raises(AgentDefinitionNotFoundError):
        resolver.resolve_for_agent(
            context(),
            "invented_worker",
            CapabilitySelection(),
        )


def test_both_workers_are_exposed_as_executable_delegation_targets() -> None:
    resolver = CapabilityResolver(
        create_m2_capability_catalog(),
        create_m2_agent_definitions(),
    )

    available = resolver.resolve_delegation_targets(context(), CapabilitySelection())
    assert [item.capability_id for item in available.capabilities] == [
        "business_data",
        "knowledge",
    ]
    explicit = resolver.resolve_delegation_targets(
        context(),
        CapabilitySelection(capability_ids=["business_data"]),
    )
    assert [item.capability_id for item in explicit.capabilities] == ["business_data"]
    knowledge = resolver.resolve_delegation_targets(
        context(),
        CapabilitySelection(capability_ids=["knowledge"]),
    )
    assert [item.capability_id for item in knowledge.capabilities] == ["knowledge"]


def test_resolver_applies_role_filter_before_returning_model_view() -> None:
    inventory = create_m2_capability_catalog().get("search_inventory")
    owner_only = inventory.model_copy(
        update={
            "allowed_roles": frozenset({"company_owner"}),
            "allowed_agent_ids": frozenset({"owner_worker"}),
        }
    )
    catalog = CapabilityCatalog((owner_only,))
    agent = AgentDefinition(
        agent_id="owner_worker",
        version="1.0.0",
        description="只读负责人测试角色。",
        allowed_capability_ids=("search_inventory",),
        evidence_source_types=("database",),
        completion_criteria="返回获权事实或明确拒绝。",
        can_delegate=False,
        implementation_status="declared",
    )
    resolver = CapabilityResolver(catalog, (agent,))

    with pytest.raises(CapabilityNotAllowedError):
        resolver.resolve_for_agent(
            context(),
            "owner_worker",
            CapabilitySelection(capability_ids=["search_inventory"]),
        )

    allowed = resolver.resolve_for_agent(
        context(roles=("company_owner",)),
        "owner_worker",
        CapabilitySelection(capability_ids=["search_inventory"]),
    )
    assert [item.capability_id for item in allowed.capabilities] == ["search_inventory"]


def test_catalog_rejects_duplicates_and_is_immutable_and_stably_sorted() -> None:
    definition = create_m1_capability_catalog().get("search_inventory")
    with pytest.raises(DuplicateCapabilityRegistrationError):
        CapabilityCatalog((definition, definition))

    catalog = CapabilityCatalog(
        (
            definition,
            create_m1_capability_catalog().get("get_product_spec"),
        )
    )
    assert catalog.names == ("get_product_spec", "search_inventory")
    retrieved = catalog.get("search_inventory")
    assert retrieved.parameters is not None
    retrieved.parameters.root["mutated"] = True
    stored_again = catalog.get("search_inventory")
    assert stored_again.parameters is not None
    assert "mutated" not in stored_again.parameters.root
    with pytest.raises(ValidationError, match="frozen"):
        definition.capability_id = "changed"  # type: ignore[misc]


def test_capability_contract_rejects_extra_unsafe_or_unbounded_metadata() -> None:
    assert CapabilityDefinition.model_json_schema()["properties"]["kind"]["enum"] == [
        "tool",
        "skill",
        "agent",
        "runtime",
    ]
    safe_parameters = CapabilityParameterSchema(
        {
            "type": "object",
            "additionalProperties": False,
            "properties": {"query": {"type": "string", "maxLength": 100}},
            "required": ["query"],
        }
    )
    definition = CapabilityDefinition(
        capability_id="safe_tool",
        kind="tool",
        version="1.0.0",
        description="读取公开安全事实。",
        parameters=safe_parameters,
        side_effect="read",
        produces_evidence=True,
        implementation_status="available",
        allowed_roles=frozenset({"company_owner"}),
        allowed_agent_ids=frozenset({"owner_worker"}),
    )
    assert definition.parameters == safe_parameters

    with pytest.raises(ValidationError):
        CapabilityDefinition.model_validate(definition.model_dump() | {"sql": "x"})
    with pytest.raises(ValidationError, match="additionalProperties"):
        CapabilityParameterSchema(
            {"type": "object", "additionalProperties": True, "properties": {}}
        )
    with pytest.raises(ValidationError, match="server-owned"):
        CapabilityParameterSchema(
            {
                "type": "object",
                "additionalProperties": False,
                "properties": {"tenant_id": {"type": "string"}},
            }
        )
    with pytest.raises(ValidationError):
        CapabilityParameterSchema(
            {
                "type": "object",
                "additionalProperties": False,
                "properties": {"query": {"description": "x" * 70_000}},
            }
        )


def test_resolver_construction_rejects_duplicate_or_missing_agent_capabilities() -> (
    None
):
    catalog = create_m1_capability_catalog()
    valid = AgentDefinition(
        agent_id="business_data",
        version="1.0.0",
        description="只读业务数据角色。",
        allowed_capability_ids=("get_product_spec", "search_inventory"),
        evidence_source_types=("database",),
        completion_criteria="返回获权事实或明确未知项。",
        can_delegate=False,
        implementation_status="declared",
    )
    with pytest.raises(ValueError, match="duplicate Agent"):
        CapabilityResolver(catalog, (valid, valid))

    missing = valid.model_copy(
        update={"allowed_capability_ids": ("invented_capability",)},
    )
    with pytest.raises(ValueError, match="not registered"):
        CapabilityResolver(catalog, (missing,))

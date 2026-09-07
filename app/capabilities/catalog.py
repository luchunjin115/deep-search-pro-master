"""Immutable capability catalogs adapted from existing Tool registries."""

from __future__ import annotations

from types import MappingProxyType

from app.agents.definitions import AgentDefinition, create_m2_agent_definitions
from app.capabilities.contracts import (
    CapabilityDefinition,
    CapabilityParameterSchema,
)
from app.schemas.common import ToolName
from app.tools.registry import (
    ToolDefinition,
    ToolRegistry,
    create_m1_tool_registry,
    create_m2_tool_registry,
)

_SAFE_TOOL_DESCRIPTIONS: dict[ToolName, str] = {
    "get_product_spec": "根据商品名称、受控别名或SKU解析唯一商品及其规格。",
    "search_inventory": "使用准确SKU查询指定市场或仓库的最新只读库存事实。",
    "search_knowledge": "从当前获权知识中检索事实并返回有序Evidence。",
    "read_uploaded_file": "使用公开文件ID和可选结构定位读取有界解析内容。",
    "get_evidence_detail": "使用公开Evidence ID重新校验并展开证据详情。",
}
_EVIDENCE_TOOL_NAMES: frozenset[ToolName] = frozenset(
    {"search_inventory", "search_knowledge", "get_evidence_detail"}
)
_TOOL_OWNERS: dict[ToolName, frozenset[str]] = {
    "get_product_spec": frozenset({"business_data"}),
    "search_inventory": frozenset({"business_data"}),
    "search_knowledge": frozenset({"knowledge"}),
    "read_uploaded_file": frozenset({"knowledge"}),
    "get_evidence_detail": frozenset({"knowledge"}),
}


class DuplicateCapabilityRegistrationError(ValueError):
    """Two definitions attempted to claim the same stable capability ID."""


class CapabilityNotRegisteredError(LookupError):
    """No capability metadata exists for the requested stable ID."""


class CapabilityCatalog:
    """A read-only, stable snapshot of server-owned capability definitions."""

    def __init__(self, definitions: tuple[CapabilityDefinition, ...]) -> None:
        by_id: dict[str, CapabilityDefinition] = {}
        for definition in definitions:
            if definition.capability_id in by_id:
                raise DuplicateCapabilityRegistrationError(
                    f"Duplicate capability registration: {definition.capability_id}"
                )
            by_id[definition.capability_id] = definition
        self._definitions = MappingProxyType(
            {key: value.model_copy(deep=True) for key, value in by_id.items()}
        )

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._definitions))

    @property
    def available_names(self) -> tuple[str, ...]:
        return tuple(
            name
            for name in self.names
            if self._definitions[name].implementation_status == "available"
        )

    def get(self, capability_id: str) -> CapabilityDefinition:
        try:
            return self._definitions[capability_id].model_copy(deep=True)
        except KeyError:
            raise CapabilityNotRegisteredError(capability_id) from None

    def list_definitions(self) -> tuple[CapabilityDefinition, ...]:
        return tuple(self.get(name) for name in self.names)


def _safe_parameter_schema(definition: ToolDefinition) -> CapabilityParameterSchema:
    def strip_annotations(value: object) -> object:
        if isinstance(value, dict):
            return {
                key: strip_annotations(item)
                for key, item in value.items()
                if key not in {"description", "examples", "title"}
            }
        if isinstance(value, list):
            return [strip_annotations(item) for item in value]
        return value

    schema = strip_annotations(definition.input_schema.model_json_schema())
    if not isinstance(schema, dict):
        raise TypeError("Tool input Schema must be a JSON object")
    return CapabilityParameterSchema(schema)


def _tool_capability(definition: ToolDefinition) -> CapabilityDefinition:
    return CapabilityDefinition(
        capability_id=definition.name,
        kind="tool",
        version=definition.version,
        description=_SAFE_TOOL_DESCRIPTIONS[definition.name],
        parameters=_safe_parameter_schema(definition),
        side_effect=definition.side_effect,
        produces_evidence=definition.name in _EVIDENCE_TOOL_NAMES,
        implementation_status="available",
        allowed_roles=definition.allowed_roles,
        allowed_agent_ids=_TOOL_OWNERS[definition.name],
    )


def _agent_capability(
    agent: AgentDefinition,
    tools: dict[str, CapabilityDefinition],
) -> CapabilityDefinition:
    allowed_role_sets = [
        tools[name].allowed_roles for name in agent.allowed_capability_ids
    ]
    allowed_roles = frozenset.intersection(*allowed_role_sets)
    return CapabilityDefinition(
        capability_id=agent.agent_id,
        kind="agent",
        version=agent.version,
        description=agent.description,
        parameters=None,
        side_effect="none",
        produces_evidence=bool(agent.evidence_source_types),
        implementation_status=agent.implementation_status,
        allowed_roles=allowed_roles,
        allowed_agent_ids=frozenset(),
    )


def _tool_capabilities(registry: ToolRegistry) -> tuple[CapabilityDefinition, ...]:
    return tuple(_tool_capability(item) for item in registry.list_definitions())


def create_m1_capability_catalog() -> CapabilityCatalog:
    """Adapt the exact two implemented M1 Tools without changing their registry."""

    return CapabilityCatalog(_tool_capabilities(create_m1_tool_registry()))


def create_m2_capability_catalog() -> CapabilityCatalog:
    """Register the five implemented Tools and two executable Workers."""

    tool_capabilities = _tool_capabilities(create_m2_tool_registry())
    tools_by_id = {item.capability_id: item for item in tool_capabilities}
    agent_capabilities = tuple(
        _agent_capability(agent, tools_by_id) for agent in create_m2_agent_definitions()
    )
    return CapabilityCatalog((*tool_capabilities, *agent_capabilities))

"""Deterministic capability filtering and safe model projection."""

from __future__ import annotations

from types import MappingProxyType

from app.agents.definitions import AgentDefinition
from app.capabilities.catalog import (
    CapabilityCatalog,
    CapabilityNotRegisteredError,
)
from app.capabilities.contracts import (
    CapabilityDefinition,
    CapabilityResolution,
    CapabilitySelection,
    ResolvedCapability,
)
from app.runtime.context import RunContext


class AgentDefinitionNotFoundError(LookupError):
    """The server did not register the requested Worker role."""


class CapabilityNotFoundError(LookupError):
    """The requested capability ID does not exist; no fallback is allowed."""


class CapabilityNotAllowedError(PermissionError):
    """The capability is outside the Worker or trusted role intersection."""


class CapabilityUnavailableError(RuntimeError):
    """Metadata exists, but no executable implementation is registered yet."""


class CapabilityResolver:
    """Resolve only registered, implemented, role- and Worker-allowed capabilities."""

    def __init__(
        self,
        catalog: CapabilityCatalog,
        agent_definitions: tuple[AgentDefinition, ...],
    ) -> None:
        agents: dict[str, AgentDefinition] = {}
        for agent in agent_definitions:
            if agent.agent_id in agents:
                raise ValueError(f"duplicate Agent definition: {agent.agent_id}")
            for capability_id in agent.allowed_capability_ids:
                try:
                    capability = catalog.get(capability_id)
                except CapabilityNotRegisteredError:
                    raise ValueError(
                        f"Agent capability {capability_id} is not registered"
                    ) from None
                if capability.kind != "tool":
                    raise ValueError(
                        "Agent definitions may only request Tool capabilities"
                    )
                if agent.agent_id not in capability.allowed_agent_ids:
                    raise ValueError("Agent definition disagrees with Tool ownership")
            agents[agent.agent_id] = agent
        self._catalog = catalog
        self._agents = MappingProxyType(agents)

    def resolve_for_agent(
        self,
        context: RunContext,
        agent_id: str,
        selection: CapabilitySelection,
    ) -> CapabilityResolution:
        """Return a stable safe Tool projection for one server-selected Worker."""

        try:
            agent = self._agents[agent_id]
        except KeyError:
            raise AgentDefinitionNotFoundError from None

        selected_ids = selection.capability_ids or list(agent.allowed_capability_ids)
        definitions: list[CapabilityDefinition] = []
        for capability_id in selected_ids:
            definition = self._get(capability_id)
            if (
                capability_id not in agent.allowed_capability_ids
                or definition.kind != "tool"
                or agent.agent_id not in definition.allowed_agent_ids
                or not definition.allowed_roles.intersection(context.roles)
            ):
                raise CapabilityNotAllowedError
            if definition.implementation_status != "available":
                raise CapabilityUnavailableError
            definitions.append(definition)
        return self._resolution(agent.agent_id, definitions)

    def resolve_delegation_targets(
        self,
        context: RunContext,
        selection: CapabilitySelection,
    ) -> CapabilityResolution:
        """Expose only executable Agent targets; declared roles remain unavailable."""

        explicit_selection = bool(selection.capability_ids)
        selected_ids = selection.capability_ids or [
            item.capability_id
            for item in self._catalog.list_definitions()
            if item.kind == "agent"
        ]
        definitions: list[CapabilityDefinition] = []
        for capability_id in selected_ids:
            definition = self._get(capability_id)
            if definition.kind != "agent":
                raise CapabilityNotAllowedError
            if definition.implementation_status != "available":
                if explicit_selection:
                    raise CapabilityUnavailableError
                continue
            if not definition.allowed_roles.intersection(context.roles):
                if explicit_selection:
                    raise CapabilityNotAllowedError
                continue
            definitions.append(definition)
        return self._resolution(None, definitions)

    def _get(self, capability_id: str) -> CapabilityDefinition:
        try:
            return self._catalog.get(capability_id)
        except CapabilityNotRegisteredError:
            raise CapabilityNotFoundError from None

    @staticmethod
    def _resolution(
        agent_id: str | None,
        definitions: list[CapabilityDefinition],
    ) -> CapabilityResolution:
        views = [
            ResolvedCapability(
                capability_id=item.capability_id,
                kind=item.kind,
                version=item.version,
                description=item.description,
                parameters=item.parameters.model_copy(deep=True)
                if item.parameters is not None
                else None,
                side_effect=item.side_effect,
                produces_evidence=item.produces_evidence,
                implementation_status="available",
            )
            for item in sorted(definitions, key=lambda value: value.capability_id)
        ]
        return CapabilityResolution(
            requesting_agent_id=agent_id,
            capabilities=views,
        )

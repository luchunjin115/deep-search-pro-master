"""Deterministic pre-execution authorization for registered M1 Tools."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, cast
from uuid import UUID

from app.core.errors import (
    MarketPermissionDeniedError,
    RolePermissionDeniedError,
    TenantPermissionDeniedError,
    ToolNotAllowedError,
    UnsafeToolPermissionError,
)
from app.runtime.context import RunContext
from app.schemas.common import MarketCode, ToolName
from app.tools.registry import ToolDefinition, ToolNotRegisteredError


class ToolMetadataReader(Protocol):
    """The only registry operation required by PermissionGuard."""

    def get(self, name: str) -> ToolDefinition: ...


@dataclass(frozen=True, slots=True)
class PermissionGrant:
    """A positive decision safe for the future Tool executor and Trace."""

    allowed: Literal[True]
    tool: ToolName
    version: str
    tenant_id: UUID
    market_code: MarketCode | None


class PermissionGuard:
    """Intersect Tool, system, tenant, role, and market policies before execution."""

    def __init__(self, registry: ToolMetadataReader) -> None:
        self._registry = registry

    def authorize(
        self,
        context: RunContext,
        tool_name: str,
        *,
        target_tenant_id: UUID,
        market_code: MarketCode | None = None,
    ) -> PermissionGrant:
        """Return an explicit grant or raise a frontend-safe FORBIDDEN error."""

        try:
            definition = self._registry.get(tool_name)
        except ToolNotRegisteredError:
            raise ToolNotAllowedError from None

        if definition.side_effect != "read":
            raise UnsafeToolPermissionError
        if target_tenant_id != context.tenant_id:
            raise TenantPermissionDeniedError
        if not definition.allowed_roles.intersection(context.roles):
            raise RolePermissionDeniedError
        if definition.data_scope == "market" and market_code is None:
            raise MarketPermissionDeniedError
        if market_code is not None and market_code not in context.market_scopes:
            raise MarketPermissionDeniedError

        return PermissionGrant(
            allowed=True,
            tool=cast(ToolName, definition.name),
            version=definition.version,
            tenant_id=context.tenant_id,
            market_code=market_code,
        )

"""Immutable, versioned metadata registry for the two M1 Agent Tools."""

from __future__ import annotations

import re
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Literal, get_args

from pydantic import BaseModel

from app.schemas.common import RoleName, ToolName
from app.schemas.inventory import InventoryResult, SearchInventoryInput
from app.schemas.product import GetProductSpecInput, ProductSpecResult

if TYPE_CHECKING:
    from app.llm.schemas import ModelToolSpec

DataScope = Literal["tenant", "market"]
SideEffectLevel = Literal["read", "write"]
_VERSION_PATTERN = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
_M1_TOOL_NAMES = frozenset(get_args(ToolName))
_M1_ROLE_NAMES = frozenset(get_args(RoleName))


class InvalidToolDefinitionError(ValueError):
    """Tool metadata is incomplete or outside the frozen M1 contract."""


class DuplicateToolRegistrationError(ValueError):
    """Two definitions attempted to claim the same Tool name."""


class ToolNotRegisteredError(LookupError):
    """No metadata exists for a requested Tool name."""


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    """Schemas, version, timeout, permission policy, and side effect for one Tool."""

    name: ToolName
    description: str
    version: str
    input_schema: type[BaseModel]
    output_schema: type[BaseModel]
    timeout_ms: int
    allowed_roles: frozenset[RoleName]
    data_scope: DataScope
    side_effect: SideEffectLevel

    def __post_init__(self) -> None:
        if self.name not in _M1_TOOL_NAMES:
            raise InvalidToolDefinitionError("M1 Tool name is not allowed")
        if not self.description.strip() or len(self.description) > 300:
            raise InvalidToolDefinitionError("Tool description is invalid")
        if not _VERSION_PATTERN.fullmatch(self.version):
            raise InvalidToolDefinitionError("Tool version must use semantic x.y.z")
        if not (50 <= self.timeout_ms <= 30_000):
            raise InvalidToolDefinitionError("Tool timeout must be 50-30000 ms")
        if not self.allowed_roles or not self.allowed_roles <= _M1_ROLE_NAMES:
            raise InvalidToolDefinitionError("Tool allowed_roles are invalid")
        if self.data_scope not in ("tenant", "market"):
            raise InvalidToolDefinitionError("Tool data_scope is invalid")
        if self.side_effect not in ("read", "write"):
            raise InvalidToolDefinitionError("Tool side_effect is invalid")
        if not issubclass(self.input_schema, BaseModel) or not issubclass(
            self.output_schema,
            BaseModel,
        ):
            raise InvalidToolDefinitionError("Tool schemas must be Pydantic models")


class ToolRegistry:
    """A read-only snapshot of registered Tool metadata."""

    def __init__(self, definitions: tuple[ToolDefinition, ...]) -> None:
        by_name: dict[str, ToolDefinition] = {}
        for definition in definitions:
            if definition.name in by_name:
                raise DuplicateToolRegistrationError(
                    f"Duplicate Tool registration: {definition.name}"
                )
            by_name[definition.name] = definition
        self._definitions = MappingProxyType(by_name)

    @property
    def names(self) -> tuple[str, ...]:
        """Return registered names in stable order for audit and tests."""

        return tuple(sorted(self._definitions))

    def get(self, name: str) -> ToolDefinition:
        """Return one definition without falling back to an arbitrary Tool."""

        try:
            return self._definitions[name]
        except KeyError:
            raise ToolNotRegisteredError(name) from None

    def list_definitions(self) -> tuple[ToolDefinition, ...]:
        """Return stable immutable definitions without exposing the internal map."""

        return tuple(self._definitions[name] for name in self.names)

    def model_specs(self, names: tuple[str, ...]) -> tuple[ModelToolSpec, ...]:
        """Project approved metadata to non-executable specs safe to show a model."""

        from app.llm.schemas import ModelToolSpec

        return tuple(
            ModelToolSpec(
                name=definition.name,
                description=definition.description,
                parameters=definition.input_schema.model_json_schema(),
            )
            for name in names
            for definition in (self.get(name),)
        )


def create_m1_tool_registry() -> ToolRegistry:
    """Create the exact two-Tool allowlist authorized for the M1 slice."""

    allowed_roles: frozenset[RoleName] = frozenset(
        {"company_owner", "product_scout", "amazon_operator"}
    )
    return ToolRegistry(
        (
            ToolDefinition(
                name="get_product_spec",
                description=(
                    "当用户提供商品名称、受控别名或SKU，需要解析租户内唯一商品及规格，"
                    "或库存查询尚未获得准确SKU时使用。返回商品和变体ID、准确SKU、中英文名、"
                    "状态及合成演示规格；不查询库存，不接受SQL、tenant或市场参数。"
                    "未找到或匹配多个商品时返回安全业务错误。"
                ),
                version="1.0.0",
                input_schema=GetProductSpecInput,
                output_schema=ProductSpecResult,
                timeout_ms=3_000,
                allowed_roles=allowed_roles,
                data_scope="tenant",
                side_effect="read",
            ),
            ToolDefinition(
                name="search_inventory",
                description=(
                    "仅在已经获得准确SKU，需要查询指定市场或仓库最新库存时使用。"
                    "返回在库、预留、不可售、可售、在途、安全库存和快照时间，"
                    "并通过ToolEnvelope返回数据库Evidence ID。必须提供SKU和DE/FR市场，"
                    "仓库可选但多仓时必须指定；只读，不接受SQL或tenant，"
                    "只查询当前用户获权的合成演示数据。"
                ),
                version="1.0.0",
                input_schema=SearchInventoryInput,
                output_schema=InventoryResult,
                timeout_ms=3_000,
                allowed_roles=allowed_roles,
                data_scope="market",
                side_effect="read",
            ),
        )
    )

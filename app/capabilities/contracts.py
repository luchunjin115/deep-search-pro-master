"""Strict internal and model-visible contracts for Agent capabilities."""

from __future__ import annotations

import json
import math
import re
from typing import Annotated, Literal

from pydantic import ConfigDict, Field, RootModel, StringConstraints, model_validator

from app.schemas.agent import CapabilityId, WorkerId
from app.schemas.common import M1Schema, RoleName

CAPABILITY_CONTRACT_VERSION: Literal["m2-capability-contract-v1"] = (
    "m2-capability-contract-v1"
)
MAX_RESOLVED_CAPABILITIES = 12
MAX_PARAMETER_SCHEMA_BYTES = 65_536
MAX_PARAMETER_SCHEMA_DEPTH = 12

CapabilityKind = Literal["tool", "skill", "agent", "runtime"]
CapabilityImplementationStatus = Literal["declared", "available"]
CapabilitySideEffect = Literal["none", "read", "write"]
AgentId = WorkerId
SemanticVersion = Annotated[
    str,
    StringConstraints(
        strict=True,
        strip_whitespace=True,
        pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$",
        max_length=32,
    ),
]
CapabilityDescription = Annotated[
    str,
    StringConstraints(
        strict=True,
        strip_whitespace=True,
        min_length=1,
        max_length=500,
    ),
]

_SERVER_OWNED_PARAMETER_NAMES = {
    "user",
    "userid",
    "currentuser",
    "tenant",
    "tenantid",
    "role",
    "roles",
    "permissions",
    "permission",
    "marketscopes",
    "runcontext",
    "threadid",
    "traceid",
    "runid",
    "rootrunid",
    "agentrunid",
    "parentrun",
    "parentrunid",
    "budget",
    "budgetref",
    "budgetlimits",
    "maxmodelcalls",
    "maxtoolcalls",
    "maxrepeattoolcalls",
    "totaltimeoutms",
}
_SENSITIVE_PARAMETER_NAMES = {
    "sql",
    "path",
    "localpath",
    "storagekey",
    "secret",
    "apikey",
    "password",
    "accesstoken",
    "refreshtoken",
    "token",
    "stack",
    "stacktrace",
    "traceback",
    "exception",
    "rawexception",
}


def _compact_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def _validate_schema_json(value: object, *, depth: int) -> None:
    if depth > MAX_PARAMETER_SCHEMA_DEPTH:
        raise ValueError(
            f"parameter Schema depth cannot exceed {MAX_PARAMETER_SCHEMA_DEPTH}"
        )
    if value is None or isinstance(value, (bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("parameter Schema numbers must be finite")
        return
    if isinstance(value, str):
        if len(value) > 8192:
            raise ValueError("parameter Schema strings cannot exceed 8192 characters")
        return
    if isinstance(value, list):
        if len(value) > 128:
            raise ValueError("parameter Schema lists cannot exceed 128 items")
        for item in value:
            _validate_schema_json(item, depth=depth + 1)
        return
    if isinstance(value, dict):
        if len(value) > 128:
            raise ValueError("parameter Schema objects cannot exceed 128 keys")
        for key, item in value.items():
            if not isinstance(key, str) or not 1 <= len(key) <= 128:
                raise ValueError(
                    "parameter Schema keys must be 1-128 character strings"
                )
            if key == "properties":
                if not isinstance(item, dict):
                    raise ValueError("parameter Schema properties must be an object")
                for property_name in item:
                    compact_name = _compact_name(property_name)
                    if compact_name in _SERVER_OWNED_PARAMETER_NAMES:
                        raise ValueError(
                            f"{property_name} is server-owned and cannot be a parameter"
                        )
                    if compact_name in _SENSITIVE_PARAMETER_NAMES:
                        raise ValueError(
                            f"{property_name} is sensitive and cannot be a parameter"
                        )
            _validate_schema_json(item, depth=depth + 1)
        return
    raise ValueError("parameter Schema must contain only JSON values")


class CapabilityParameterSchema(RootModel[dict[str, object]]):
    """A bounded JSON Schema containing only model-controlled business fields."""

    model_config = ConfigDict(frozen=True)

    @model_validator(mode="after")
    def validate_parameter_schema(self) -> CapabilityParameterSchema:
        if self.root.get("type") != "object":
            raise ValueError("capability parameters must use an object Schema")
        if self.root.get("additionalProperties") is not False:
            raise ValueError("parameter Schema additionalProperties must be false")
        _validate_schema_json(self.root, depth=1)
        serialized = json.dumps(
            self.root,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        if len(serialized) > MAX_PARAMETER_SCHEMA_BYTES:
            raise ValueError(
                f"parameter Schema cannot exceed {MAX_PARAMETER_SCHEMA_BYTES} bytes"
            )
        return self


class CapabilityDefinition(M1Schema):
    """Server-owned metadata used for filtering, never returned directly to a model."""

    model_config = ConfigDict(frozen=True)

    contract_version: Literal["m2-capability-contract-v1"] = CAPABILITY_CONTRACT_VERSION
    capability_id: CapabilityId
    kind: CapabilityKind
    version: SemanticVersion
    description: CapabilityDescription
    parameters: CapabilityParameterSchema | None = None
    side_effect: CapabilitySideEffect
    produces_evidence: bool
    implementation_status: CapabilityImplementationStatus
    allowed_roles: frozenset[RoleName] = Field(min_length=1, max_length=3)
    allowed_agent_ids: frozenset[AgentId] = Field(
        default_factory=frozenset, max_length=8
    )

    @model_validator(mode="after")
    def validate_definition_shape(self) -> CapabilityDefinition:
        if self.kind == "tool":
            if self.parameters is None:
                raise ValueError("Tool capability requires a parameter Schema")
            if not self.allowed_agent_ids:
                raise ValueError("Tool capability requires at least one allowed Agent")
        elif self.parameters is not None:
            raise ValueError("non-Tool capability cannot expose Tool parameters")
        if self.kind == "agent" and self.allowed_agent_ids:
            raise ValueError("Agent capability cannot be owned by a Worker")
        return self


class CapabilitySelection(M1Schema):
    """The only model-controlled input to capability resolution."""

    capability_ids: list[CapabilityId] = Field(
        default_factory=list,
        max_length=MAX_RESOLVED_CAPABILITIES,
    )

    @model_validator(mode="after")
    def validate_unique_ids(self) -> CapabilitySelection:
        if len(self.capability_ids) != len(set(self.capability_ids)):
            raise ValueError("duplicate capability IDs are not allowed")
        return self


class ResolvedCapability(M1Schema):
    """A non-executable, public-safe capability view suitable for a model."""

    capability_id: CapabilityId
    kind: CapabilityKind
    version: SemanticVersion
    description: CapabilityDescription
    parameters: CapabilityParameterSchema | None = None
    side_effect: CapabilitySideEffect
    produces_evidence: bool
    implementation_status: Literal["available"] = "available"


class CapabilityResolution(M1Schema):
    """A bounded and stably ordered set of safe capability views."""

    contract_version: Literal["m2-capability-contract-v1"] = CAPABILITY_CONTRACT_VERSION
    requesting_agent_id: AgentId | None = None
    capabilities: list[ResolvedCapability] = Field(
        default_factory=list,
        max_length=MAX_RESOLVED_CAPABILITIES,
    )

    @model_validator(mode="after")
    def validate_unique_capabilities(self) -> CapabilityResolution:
        capability_ids = [item.capability_id for item in self.capabilities]
        if capability_ids != sorted(capability_ids):
            raise ValueError("resolved capabilities must use stable sorted order")
        if len(capability_ids) != len(set(capability_ids)):
            raise ValueError("resolved capability IDs must be unique")
        return self

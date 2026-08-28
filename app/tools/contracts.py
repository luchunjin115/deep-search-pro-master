"""Shared binding checks and response construction for the two M1 Agent Tools."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel

from app.core.errors import ApplicationError
from app.schemas.common import M1Schema, ToolEnvelope, ToolMeta, ToolName
from app.tools.registry import ToolDefinition

InputT = TypeVar("InputT", bound=BaseModel)
OutputT = TypeVar("OutputT", bound=M1Schema)


class InvalidToolBindingError(ValueError):
    """A runtime Tool implementation disagrees with its registered metadata."""


def validate_tool_binding(
    definition: ToolDefinition,
    *,
    name: ToolName,
    input_schema: type[BaseModel],
    output_schema: type[BaseModel],
) -> None:
    """Fail fast when code and the permission registry describe different Tools."""

    if (
        definition.name != name
        or definition.input_schema is not input_schema
        or definition.output_schema is not output_schema
    ):
        raise InvalidToolBindingError(
            "Agent Tool implementation does not match registered metadata"
        )


@dataclass(slots=True)
class ToolEnvelopeBuilder(Generic[OutputT]):
    """Build one coherent, timed Tool response without exposing raw exceptions."""

    definition: ToolDefinition
    trace_id: UUID
    monotonic: Callable[[], float] = time.monotonic
    _started_at: float = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._started_at = self.monotonic()

    def success(
        self,
        data: OutputT,
        *,
        evidence_ids: list[UUID] | None = None,
        source_time: datetime | None = None,
    ) -> ToolEnvelope[OutputT]:
        """Wrap one validated business result with safe execution metadata."""

        return ToolEnvelope[OutputT](
            status="success",
            data=data,
            evidence_ids=evidence_ids or [],
            meta=self._meta(source_time=source_time),
        )

    def error(self, error: ApplicationError) -> ToolEnvelope[OutputT]:
        """Return only the public ApplicationError contract."""

        return ToolEnvelope[OutputT](
            status="error",
            error=error.to_detail(),
            meta=self._meta(),
        )

    def _meta(self, *, source_time: datetime | None = None) -> ToolMeta:
        duration_ms = max(round((self.monotonic() - self._started_at) * 1000), 0)
        return ToolMeta(
            tool=self.definition.name,
            version=self.definition.version,
            duration_ms=duration_ms,
            source_time=source_time,
            trace_id=self.trace_id,
            synthetic_data=True,
        )

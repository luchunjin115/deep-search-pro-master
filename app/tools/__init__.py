"""Registered Agent Tool metadata for isolated M1 and M2 runtimes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.tools.contracts import InvalidToolBindingError, ToolEnvelopeBuilder
from app.tools.registry import (
    DuplicateToolRegistrationError,
    InvalidToolDefinitionError,
    ToolDefinition,
    ToolNotRegisteredError,
    ToolRegistry,
    create_m1_tool_registry,
    create_m2_tool_registry,
)

if TYPE_CHECKING:
    from app.tools.get_evidence_detail import GetEvidenceDetailTool
    from app.tools.read_uploaded_file import ReadUploadedFileTool
    from app.tools.search_knowledge import SearchKnowledgeTool


def __getattr__(name: str) -> object:
    """Lazily export execution Tools without creating the runtime import cycle."""

    if name == "SearchKnowledgeTool":
        from app.tools.search_knowledge import SearchKnowledgeTool

        return SearchKnowledgeTool
    if name == "ReadUploadedFileTool":
        from app.tools.read_uploaded_file import ReadUploadedFileTool

        return ReadUploadedFileTool
    if name == "GetEvidenceDetailTool":
        from app.tools.get_evidence_detail import GetEvidenceDetailTool

        return GetEvidenceDetailTool
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "DuplicateToolRegistrationError",
    "GetEvidenceDetailTool",
    "InvalidToolBindingError",
    "InvalidToolDefinitionError",
    "ReadUploadedFileTool",
    "SearchKnowledgeTool",
    "ToolDefinition",
    "ToolEnvelopeBuilder",
    "ToolNotRegisteredError",
    "ToolRegistry",
    "create_m1_tool_registry",
    "create_m2_tool_registry",
]

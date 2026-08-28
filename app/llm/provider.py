"""Minimal M1 model boundary and provider factory."""

from __future__ import annotations

from typing import Protocol

import httpx

from app.core.config import Settings
from app.llm.schemas import ToolCallProposal, ToolDecisionRequest


class ModelProvider(Protocol):
    """The only model capability authorized in the M1 inventory slice."""

    async def propose_tool_call(
        self,
        request: ToolDecisionRequest,
    ) -> ToolCallProposal:
        """Propose one allowlisted call without invoking Tools or databases."""


def create_model_provider(
    settings: Settings,
    *,
    http_client: httpx.AsyncClient | None = None,
) -> ModelProvider:
    """Create the configured Provider without exposing it to business storage."""

    if settings.llm_provider == "mock":
        from app.llm.mock import MockProvider

        return MockProvider()

    from app.llm.qwen import QwenProvider

    if settings.qwen_api_key is None:
        raise ValueError("Qwen settings require an API key")
    return QwenProvider(
        api_key=settings.qwen_api_key,
        model=settings.qwen_model,
        base_url=settings.qwen_base_url,
        timeout_seconds=settings.qwen_timeout_seconds,
        http_client=http_client,
    )

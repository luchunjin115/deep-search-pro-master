"""Configuration factory for deterministic and remote Agent providers."""

from __future__ import annotations

import httpx

from app.core.config import Settings
from app.llm.agent_mock import AgentMockScript, DeterministicAgentMock
from app.llm.agent_provider import EngineeredAgentProvider


def create_engineered_agent_provider(
    settings: Settings,
    *,
    mock_script: AgentMockScript | None = None,
    http_client: httpx.AsyncClient | None = None,
) -> EngineeredAgentProvider:
    """Create one provider; Mock behavior must always be supplied explicitly."""

    if settings.llm_provider == "mock":
        if mock_script is None:
            raise ValueError("Mock Agent provider requires an explicit bounded script")
        return DeterministicAgentMock(mock_script)

    if settings.llm_provider == "qwen":
        from app.llm.agent_qwen import QwenAgentProvider

        if settings.qwen_api_key is None:
            raise ValueError("Qwen settings require an API key")
        return QwenAgentProvider(
            api_key=settings.qwen_api_key,
            model=settings.qwen_model,
            base_url=settings.qwen_base_url,
            timeout_seconds=settings.qwen_timeout_seconds,
            max_output_tokens=settings.qwen_agent_max_output_tokens,
            http_client=http_client,
        )

    from app.llm.agent_deepseek import DeepSeekAgentProvider

    if settings.deepseek_api_key is None:
        raise ValueError("DeepSeek settings require an API key")
    return DeepSeekAgentProvider(
        api_key=settings.deepseek_api_key,
        model=settings.deepseek_model,
        base_url=settings.deepseek_base_url,
        timeout_seconds=settings.deepseek_timeout_seconds,
        max_output_tokens=settings.deepseek_agent_max_output_tokens,
        http_client=http_client,
    )

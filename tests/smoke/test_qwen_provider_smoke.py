import os

import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.llm.provider import create_model_provider
from app.llm.qwen import QwenProvider
from app.llm.schemas import ToolDecisionRequest
from app.tools.registry import create_m1_tool_registry


@pytest.mark.asyncio
async def test_qwen_tool_proposal_smoke_requires_explicit_opt_in() -> None:
    api_key = os.getenv("QWEN_API_KEY")
    if os.getenv("RUN_QWEN_SMOKE") != "1" or not api_key:
        pytest.skip("set RUN_QWEN_SMOKE=1 and QWEN_API_KEY to call paid Qwen API")

    settings = Settings(  # type: ignore[call-arg]
        _env_file=None,
        llm_provider="qwen",
        qwen_api_key=SecretStr(api_key),
    )
    provider = create_model_provider(settings)
    assert isinstance(provider, QwenProvider)
    try:
        proposal = await provider.propose_tool_call(
            ToolDecisionRequest(
                question="德国仓蘑菇灯还有多少可售库存？",
                available_tools=create_m1_tool_registry().model_specs(
                    ("get_product_spec", "search_inventory")
                ),
            )
        )
    finally:
        await provider.aclose()

    assert proposal.name == "get_product_spec"
    assert proposal.arguments.product_query == "蘑菇灯"

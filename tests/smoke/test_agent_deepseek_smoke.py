from __future__ import annotations

import json
import os
from dataclasses import dataclass
from time import perf_counter
from typing import Literal
from uuid import UUID

import httpx
import pytest

from app.core.config import get_settings
from app.core.errors import ProviderError
from app.llm.agent_deepseek import DeepSeekAgentProvider
from app.llm.agent_schemas import AnswerRequest
from app.schemas.agent import (
    BoundedJsonObject,
    CannotCompleteAction,
    FinishAction,
    ResourceUsage,
    WorkerObservation,
    WorkerResult,
)


@dataclass(frozen=True)
class AnswerCase:
    case_id: str
    request: AnswerRequest
    expected_outcome: Literal["answered", "partial", "no_evidence"]
    expected_evidence_ids: tuple[UUID, ...]


def _usage() -> ResourceUsage:
    return ResourceUsage(
        model_calls=0,
        tool_calls=1,
        input_tokens=0,
        output_tokens=0,
        duration_ms=1,
    )


def _evidence_request(
    *,
    goal: str,
    evidence: tuple[tuple[UUID, str], ...],
    observation_id: UUID,
) -> AnswerRequest:
    observation = WorkerObservation(
        observation_id=observation_id,
        status="success",
        public_summary="内部知识检索成功。",
        structured_result=BoundedJsonObject(
            {
                "capability_id": "search_knowledge",
                "data": {
                    "supported": True,
                    "segments": [
                        {
                            "evidence_id": str(evidence_id),
                            "citation_label": f"[E{index}]",
                            "source_type": "knowledge",
                            "title": "跨境运营手册",
                            "text": text,
                        }
                        for index, (evidence_id, text) in enumerate(
                            evidence,
                            start=1,
                        )
                    ],
                },
            }
        ),
        evidence_ids=[evidence_id for evidence_id, _text in evidence],
        resource_usage=_usage(),
    )
    return AnswerRequest(
        goal=goal,
        public_context=BoundedJsonObject({"locale": "zh-CN", "market_code": "DE"}),
        worker_results=(
            WorkerResult(
                task_id="knowledge_task",
                worker_id="knowledge",
                execution_status="completed",
                business_outcome="answered",
                business_result=BoundedJsonObject(
                    {"knowledge_search": {"supported": True, "segments": []}}
                ),
                public_summary="内部知识已返回。",
                observations=[observation],
                evidence_ids=[evidence_id for evidence_id, _text in evidence],
                resource_usage=_usage(),
            ),
        ),
    )


def _cases() -> tuple[AnswerCase, ...]:
    return (
        AnswerCase(
            case_id="answered_direct_evidence",
            request=_evidence_request(
                goal="德国仓当前库存是多少？",
                evidence=(
                    (
                        UUID("20000000-0000-0000-0000-000000000001"),
                        "德国仓当前库存为125件。",
                    ),
                ),
                observation_id=UUID("30000000-0000-0000-0000-000000000001"),
            ),
            expected_outcome="answered",
            expected_evidence_ids=(UUID("20000000-0000-0000-0000-000000000001"),),
        ),
        AnswerCase(
            case_id="no_evidence_with_irrelevant_context",
            request=_evidence_request(
                goal="法国站当前增值税率是多少？",
                evidence=(
                    (
                        UUID("20000000-0000-0000-0000-000000000002"),
                        "这款商品的包装颜色是蓝色。",
                    ),
                    (
                        UUID("20000000-0000-0000-0000-000000000003"),
                        "德国仓当前库存为125件。",
                    ),
                ),
                observation_id=UUID("30000000-0000-0000-0000-000000000002"),
            ),
            expected_outcome="no_evidence",
            expected_evidence_ids=(),
        ),
        AnswerCase(
            case_id="partial_supported_subquestion",
            request=_evidence_request(
                goal="德国仓当前库存和法国站当前增值税率分别是多少？",
                evidence=(
                    (
                        UUID("20000000-0000-0000-0000-000000000004"),
                        "德国仓当前库存为125件。",
                    ),
                    (
                        UUID("20000000-0000-0000-0000-000000000005"),
                        "这款商品的包装颜色是蓝色。",
                    ),
                ),
                observation_id=UUID("30000000-0000-0000-0000-000000000003"),
            ),
            expected_outcome="partial",
            expected_evidence_ids=(UUID("20000000-0000-0000-0000-000000000004"),),
        ),
    )


@pytest.mark.asyncio
async def test_real_deepseek_answer_contract_requires_explicit_opt_in() -> None:
    settings = get_settings()
    api_key = settings.deepseek_api_key
    if os.getenv("RUN_DEEPSEEK_AGENT_SMOKE") != "1" or api_key is None:
        pytest.skip(
            "set RUN_DEEPSEEK_AGENT_SMOKE=1 and DEEPSEEK_API_KEY to call paid API"
        )

    safe_results: list[dict[str, object]] = []
    async with httpx.AsyncClient() as client:
        provider = DeepSeekAgentProvider(
            api_key=api_key,
            model=settings.deepseek_model,
            base_url=settings.deepseek_base_url,
            timeout_seconds=settings.deepseek_timeout_seconds,
            max_output_tokens=settings.deepseek_agent_max_output_tokens,
            http_client=client,
        )
        for case in _cases():
            usage_before = provider.total_usage
            started_at = perf_counter()
            try:
                answer = await provider.compose_answer(case.request)
            except ProviderError as exc:
                pytest.fail(
                    f"{case.case_id}: {type(exc).__name__}",
                    pytrace=False,
                )
            elapsed_ms = round((perf_counter() - started_at) * 1000)
            action = answer.action
            usage_after = provider.total_usage
            api_calls = usage_after.api_calls - usage_before.api_calls
            input_tokens = usage_after.input_tokens - usage_before.input_tokens
            output_tokens = usage_after.output_tokens - usage_before.output_tokens
            total_tokens = usage_after.total_tokens - usage_before.total_tokens

            assert action.business_outcome == case.expected_outcome
            if case.expected_outcome in {"answered", "partial"}:
                assert isinstance(action, FinishAction)
                assert tuple(action.evidence_ids) == case.expected_evidence_ids
                assert "[E1]" in action.public_summary
            else:
                assert isinstance(action, (FinishAction, CannotCompleteAction))
                if isinstance(action, FinishAction):
                    assert action.evidence_ids == []
                assert "[E" not in action.public_summary
            assert api_calls in {1, 2}

            safe_results.append(
                {
                    "case_id": case.case_id,
                    "duration_ms": elapsed_ms,
                    "business_outcome": action.business_outcome,
                    "citation_count": (
                        len(action.evidence_ids)
                        if isinstance(action, FinishAction)
                        else 0
                    ),
                    "api_calls": api_calls,
                    "repair_used": api_calls == 2,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "total_tokens": total_tokens,
                }
            )

    print(json.dumps(safe_results, ensure_ascii=False, sort_keys=True))

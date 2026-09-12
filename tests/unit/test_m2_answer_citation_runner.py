from __future__ import annotations

import asyncio
import json
import logging
from contextlib import nullcontext
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import httpx
import pytest

from app.agents.gateway import AgentGatewayLimits
from app.capabilities.contracts import (
    CapabilityParameterSchema,
    CapabilityResolution,
    ResolvedCapability,
)
from app.core.errors import BudgetExceededError
from app.evals import answer_citation_formal
from app.evals.answer_citation_formal import (
    DeterministicKnowledgeGatewayProvider,
    ExternalUsageRecorder,
    _answer_reporting_cohort,
    _case_outcome_contract_passed,
    _paid_case_requires_stop,
    _warm_gateway_retrieval_models,
)
from app.evals.answer_citation_report import (
    FakeAnswerProviderIdentity,
    serialize_answer_citation_public_report,
)
from app.evals.answer_citation_runner import (
    DeterministicFakeAnswerProvider,
    FakeAnswerRequest,
    RunAnswerCache,
    build_fake_answer_case_inputs_from_dataset,
    build_fake_answer_request,
    run_m2_answer_citation_fake_evaluation,
)
from app.llm.agent_schemas import (
    DecisionRequest,
    PlannerRequest,
)
from app.runtime.budget import AgentBudgetTree
from app.schemas.agent import (
    BoundedJsonObject,
    FinishAction,
    ResourceUsage,
    WorkerObservation,
)
from app.schemas.evaluation import AnswerExecutionRecord
from app.services.retrieval import EmbeddingPurpose


@pytest.mark.parametrize(
    ("scenario", "expected_stage", "expected_calls"),
    [
        ("valid", None, 4),
        ("unknown_reason", None, 4),
        ("recover", None, 5),
        ("json", "parse", 7),
        ("schema", "parse", 7),
        ("empty", "parse", 7),
        ("length", "response", 4),
        ("envelope", "response", 4),
        ("http", "request", 4),
        ("http_429", "request", 4),
        ("http_500", "request", 4),
        ("network", "request", 4),
        ("budget", "request", 3),
        ("response_json", "response", 7),
        ("timeout", "request", 4),
        ("parse_then_http", "request", 5),
        ("score", "score", 4),
    ],
)
def test_formal_judge_diagnostics_follow_real_http_and_parser_without_extra_calls(
    scenario: str,
    expected_stage: str | None,
    expected_calls: int,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from openai import AsyncOpenAI
    from pydantic import SecretStr

    from app.core.config import BGE_M3_MODEL_ID, BGE_M3_REVISION
    from app.evals.ragas_generation import (
        Ragas043GenerationBackend,
        RagasGenerationAdapter,
        RagasGenerationInput,
    )
    from app.evals.ragas_retrieval import RagasJudgeRuntime
    from app.services.retrieval.embedding import FakeEmbeddingProvider

    caplog.set_level(logging.CRITICAL)
    monkeypatch.setenv("RAGAS_DO_NOT_TRACK", "true")
    private = "PRIVATE tenant/user/ACL sk-secret D:/private.sql SELECT password"
    calls: list[dict[str, object]] = []
    recorder = ExternalUsageRecorder(max_api_calls=3 if scenario == "budget" else 360)

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(json.loads(request.content))
        n = len(calls)
        if n >= 4 and scenario == "timeout":
            raise httpx.ReadTimeout(private, request=request)
        if n >= 4 and scenario == "network":
            raise httpx.ConnectError(private, request=request)
        if n >= 4 and scenario in {"http_429", "http_500"}:
            return httpx.Response(
                int(scenario.split("_")[1]), json={"error": {"message": private}}
            )
        if (n >= 4 and scenario == "http") or (
            n >= 5 and scenario == "parse_then_http"
        ):
            return httpx.Response(401, json={"error": {"message": private}})
        if n >= 4 and scenario == "response_json":
            return httpx.Response(200, content=private)
        if n >= 4 and scenario == "envelope":
            return httpx.Response(200, json={"private": private})
        content = json.dumps(
            {"claims": ["抽检20件"]}
            if n in (1, 3)
            else {
                "statements": [
                    {"statement": "抽检20件", "reason": private, "verdict": 1}
                ]
            }
        )
        if n >= 4:
            if scenario in {"json", "parse_then_http"} or (
                scenario == "recover" and n == 4
            ):
                content = private
            elif scenario == "schema":
                content = json.dumps({"private": private})
            elif scenario == "empty":
                content = ""
        return httpx.Response(
            200,
            json={
                "id": "local",
                "object": "chat.completion",
                "created": 0,
                "model": "deepseek-v4-flash",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": content},
                        "finish_reason": "length"
                        if n >= 4 and scenario == "length"
                        else private
                        if scenario == "unknown_reason"
                        else "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                    "total_tokens": 15,
                },
            },
        )

    class LocalEmbedding(FakeEmbeddingProvider):
        @property
        def identity(self):
            return replace(
                super().identity,
                provider="bge-m3-local",
                model_id=BGE_M3_MODEL_ID,
                revision=BGE_M3_REVISION,
            )

    judge = RagasJudgeRuntime(
        provider="deepseek-openai-compatible",
        model="deepseek-v4-flash",
        model_version="api-alias-20260911",
        temperature=0.0,
        top_p=1.0,
        max_output_tokens=2048,
        seed=None,
        max_attempts=1,
        timeout_ms=30_000,
    )
    http = httpx.AsyncClient(
        transport=httpx.MockTransport(respond),
        event_hooks={
            "request": [recorder.capture_request],
            "response": [recorder.capture_response],
        },
    )
    backend = Ragas043GenerationBackend(
        judge=judge,
        api_key=SecretStr("local-not-real"),
        base_url="https://judge.invalid",
        embedding_provider=LocalEmbedding(),
        client_factory=lambda **kwargs: AsyncOpenAI(http_client=http, **kwargs),
    )

    class FixedMetric:
        async def ascore(self, **kwargs):
            return SimpleNamespace(value=1.0)

    for name in ("faithfulness", "response_relevancy", "semantic_similarity"):
        backend._metrics[name] = FixedMetric()
    if scenario == "score":
        factual = backend._metrics["factual_correctness"]

        class InvalidScoreMetric:
            async def ascore(self, **kwargs):
                await factual.ascore(**kwargs)
                return SimpleNamespace(value=float("nan"))

        backend._metrics["factual_correctness"] = InvalidScoreMetric()
    adapter = RagasGenerationAdapter(
        backend=backend,
        judge=judge,
        answer_provider="deepseek",
        answer_model=judge.model,
    )
    cases, _, _ = build_fake_answer_case_inputs_from_dataset(DATASET_PATH)
    loop = asyncio.new_event_loop()
    try:
        row = answer_citation_formal._evaluate_formal_case(
            case=cases[2].case,
            artifacts=SimpleNamespace(
                semantic_input=RagasGenerationInput(
                    user_input="1至500件的批次需要抽检多少件？",
                    retrieved_contexts=("抽检20件。",),
                    reference="抽检20件",
                    response="抽检20件。[E1]",
                )
            ),
            provider=DeterministicKnowledgeGatewayProvider(cases[2].case),
            runtime=SimpleNamespace(semantic_adapter=adapter, judge_usage=recorder),
            event_loop=loop,
            judge_before=recorder.snapshot(),
        )
    finally:
        loop.run_until_complete(adapter.aclose())
        loop.close()

    assert len(calls) == recorder.api_calls == expected_calls
    assert row.semantic_metrics[2].status == (
        "completed"
        if expected_stage is None
        else "judge_failed"
        if scenario != "score"
        else "framework_failed"
    )
    diagnostics = row.model_dump().get("judge_diagnostics")
    assert diagnostics, (
        "The formal report currently discards Judge request/parse diagnostics"
    )
    detail = diagnostics[2]
    assert detail["metric_name"] == "factual_correctness"
    assert detail["failure_stage"] == expected_stage
    requests = detail["requests"]
    assert [r["request_index"] for r in requests] == list(range(1, expected_calls + 1))
    assert all(r["input_tokens"] == 10 for r in requests[:3])
    assert all(r["output_tokens"] == 5 for r in requests[:3])
    assert row.judge_usage.input_tokens == sum(r["input_tokens"] or 0 for r in requests)
    assert row.judge_usage.output_tokens == sum(
        r["output_tokens"] or 0 for r in requests
    )
    if scenario == "length":
        assert requests[-1]["finish_reason"] == "length"
    if scenario == "empty":
        assert requests[-1]["content_empty"] is True
    if scenario in {"json", "schema", "empty", "parse_then_http", "recover"}:
        assert requests[3]["parse_error"] in {"json", "schema"}
    if scenario in {"http", "parse_then_http"}:
        assert requests[-1]["http_status"] == 401
    if scenario in {"timeout", "network"}:
        assert requests[-1]["http_status"] is None
        assert requests[-1]["response_state"] == "not_received"
    if scenario == "envelope":
        assert requests[-1]["response_state"] == "invalid_envelope"
    if scenario == "response_json":
        assert requests[-1]["response_state"] == "invalid_json"
    if scenario == "unknown_reason":
        assert requests[-1]["finish_reason"] == "other"
    assert private not in row.model_dump_json()
    assert "local-not-real" not in row.model_dump_json()
    assert all(
        "hooks" not in call
        and call["max_tokens"] == 2048
        and call["response_format"] == {"type": "json_object"}
        for call in calls
    )


ROOT = Path(__file__).resolve().parents[2]
DATASET_PATH = ROOT / "data" / "evals" / "m2_cross_border_rag_smoke_v1.jsonl"


def _knowledge_capabilities() -> CapabilityResolution:
    return CapabilityResolution(
        requesting_agent_id="knowledge",
        capabilities=[
            ResolvedCapability(
                capability_id="search_knowledge",
                kind="tool",
                version="1.0.0",
                description="检索当前用户获权知识",
                parameters=CapabilityParameterSchema(
                    {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {"query": {"type": "string"}},
                        "required": ["query"],
                    }
                ),
                side_effect="read",
                produces_evidence=True,
                implementation_status="available",
            )
        ],
    )


async def _post_search_request(
    provider: DeterministicKnowledgeGatewayProvider,
    *,
    goal: str,
    segments: list[tuple[UUID, str]],
) -> DecisionRequest:
    plan = await provider.create_plan(
        PlannerRequest(goal=goal, public_context=BoundedJsonObject({}))
    )
    return DecisionRequest(
        plan=plan,
        active_task_id=plan.tasks[0].task_id,
        available_capabilities=_knowledge_capabilities(),
        observations=(
            WorkerObservation(
                observation_id=uuid4(),
                status="success",
                public_summary="检索完成",
                structured_result=BoundedJsonObject(
                    {
                        "capability_id": "search_knowledge",
                        "data": {
                            "segments": [
                                {"evidence_id": str(evidence_id), "text": text}
                                for evidence_id, text in segments
                            ]
                        },
                    }
                ),
                evidence_ids=[evidence_id for evidence_id, _ in segments],
                resource_usage=ResourceUsage(
                    model_calls=0,
                    tool_calls=1,
                    input_tokens=0,
                    output_tokens=0,
                    duration_ms=1,
                ),
            ),
        ),
    )


@pytest.mark.asyncio
async def test_gateway_fake_provider_freezes_knowledge_routing_before_answering() -> (
    None
):
    cases, _, _ = build_fake_answer_case_inputs_from_dataset(DATASET_PATH)
    provider = DeterministicKnowledgeGatewayProvider(cases[0].case)

    plan = await provider.create_plan(
        PlannerRequest(
            goal=cases[0].case.question,
            public_context=BoundedJsonObject({}),
        )
    )

    assert len(plan.tasks) == 1
    assert plan.tasks[0].required_capabilities == ["search_knowledge"]
    assert plan.tasks[0].assignment.worker_id == "knowledge"
    assert provider.answer_compose_calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("candidate_count", [0, 1, 3, 9])
async def test_gateway_fake_provider_forwards_every_post_search_candidate(
    candidate_count: int,
) -> None:
    cases, _, _ = build_fake_answer_case_inputs_from_dataset(DATASET_PATH)
    case = cases[0].case
    provider = DeterministicKnowledgeGatewayProvider(case)
    segments = [
        (uuid4(), f"候选{index}：内容是否支持答案由Answer LLM判断。")
        for index in range(candidate_count)
    ]

    decision = await provider.choose_action(
        await _post_search_request(
            provider,
            goal=case.question,
            segments=segments,
        )
    )

    assert isinstance(decision.action, FinishAction)
    assert decision.action.business_outcome == (
        "answered" if candidate_count else "no_evidence"
    )
    assert decision.action.evidence_ids == [item[0] for item in segments]


def test_gateway_runner_keeps_unknown_real_source_case_in_safety_denominator() -> None:
    cases, _, _ = build_fake_answer_case_inputs_from_dataset(DATASET_PATH)

    assert cases[-1].case.source_group == "cross_border_core"
    assert cases[-1].case.should_answer is False
    assert _answer_reporting_cohort(cases[-1].case) == "safety_acl_version"


def test_safety_refusal_accepts_nonempty_candidates_but_rejects_an_answer() -> None:
    assert _case_outcome_contract_passed(
        should_answer=False,
        business_outcome="no_evidence",
    )
    assert not _case_outcome_contract_passed(
        should_answer=False,
        business_outcome="partial",
    )


@pytest.mark.asyncio
async def test_judge_call_budget_stops_before_an_extra_paid_request() -> None:
    recorder = ExternalUsageRecorder(max_api_calls=2)
    request = httpx.Request("POST", "https://deepseek.example/chat/completions")

    await recorder.capture_request(request)
    await recorder.capture_request(request)

    with pytest.raises(RuntimeError, match="Judge call budget"):
        await recorder.capture_request(request)
    assert recorder.snapshot().api_calls == 2


@pytest.mark.asyncio
async def test_judge_usage_counts_attempts_and_halts_after_provider_error() -> None:
    recorder = ExternalUsageRecorder(max_api_calls=2)
    request = httpx.Request("POST", "https://deepseek.example/chat/completions")
    response = httpx.Response(429, request=request)

    await recorder.capture_request(request)
    await recorder.capture_response(response)

    with pytest.raises(RuntimeError, match="Judge call budget"):
        await recorder.capture_request(request)
    assert recorder.snapshot().api_calls == 1


def test_paid_matrix_stops_for_business_failure_not_auxiliary_judge_failure() -> None:
    assert not _paid_case_requires_stop(SimpleNamespace(status="completed"))
    assert _paid_case_requires_stop(
        SimpleNamespace(status="calculation_failed", agent_output_stage=None)
    )


@pytest.mark.parametrize(
    "override",
    [
        {},
        {"agent_output_stage": "model_json"},
        {"agent_output_stage": "answer_input_contract"},
        {"agent_output_stage": "provider_envelope"},
        {"api_status_code": 429},
        {"api_error_code": "BUDGET_EXCEEDED"},
        {"search_knowledge_tool_status": "denied"},
        {"allowed_successful_tool_call_count": 0},
        {"search_knowledge_error_code": "TOOL_TIMEOUT"},
    ],
)
def test_paid_matrix_isolates_only_final_citation_failure(override: dict) -> None:
    audit = SimpleNamespace(
        **{
            "status": "calculation_failed",
            "agent_output_stage": "citation_contract",
            "api_status_code": 422,
            "api_error_code": "PROVIDER_ERROR",
            "search_knowledge_tool_status": "success",
            "allowed_successful_tool_call_count": 1,
            "search_knowledge_error_code": None,
            **override,
        }
    )
    assert _paid_case_requires_stop(audit) is bool(override)


@pytest.mark.parametrize(
    "scenario",
    [
        "output",
        "provider",
        "budget",
        "business",
        "citation",
        "low",
        "high",
        "timeout",
        "disk",
    ],
)
def test_formal_runner_keeps_answers_and_report_when_auxiliary_scoring_fails(
    monkeypatch: pytest.MonkeyPatch,
    scenario: str,
    tmp_path: Path,
) -> None:
    """Exercise the real 40-row loop/report; replace only external boundaries."""
    from pydantic import ValidationError

    from app.evals.answer_citation_report import (
        AnswerCitationFormalEvaluationReport,
        AnswerCitationGatewayCaseAudit,
        AnswerCitationGatewayLifecycle,
        AnswerCitationGatewayRuntimeIdentity,
        FormalAnswerProviderIdentity,
        FormalModelUsage,
    )
    from app.evals.ragas_generation import (
        RagasGenerationAdapter,
        RagasGenerationInput,
        RagasGenerationProviderError,
        RagasGenerationTimeoutError,
    )
    from app.evals.ragas_retrieval import RagasJudgeRuntime
    from app.evals.reranker_context_report import FrozenRagCorpusPublicIdentity

    module = answer_citation_formal
    from app.evals.answer_citation_report import (
        AnswerReviewWriter,
        ReviewEvidenceWriteError,
    )

    dataset_copy = tmp_path / DATASET_PATH.relative_to(ROOT)
    dataset_copy.parent.mkdir(parents=True)
    dataset_copy.write_bytes(DATASET_PATH.read_bytes())
    inputs, version, digest = build_fake_answer_case_inputs_from_dataset(DATASET_PATH)
    seed = run_m2_answer_citation_fake_evaluation(
        cases=inputs,
        dataset_version=version,
        dataset_sha256=digest,
        provider=DeterministicFakeAnswerProvider(),
    )
    traces = {row.trace.case_id: row.trace for row in seed.case_results}
    recorder = ExternalUsageRecorder(max_api_calls=5 if scenario == "budget" else 360)
    private = "PRIVATE sk-secret tenant/user/ACL D:/private.sql SELECT password"

    class Backend:
        framework_version = "0.4.3"
        prompt_bundle_version = "local-test"
        prompt_bundle_sha256 = "1" * 64
        embedding_provider = "bge-m3-local"
        embedding_model = "BAAI/bge-m3"
        embedding_revision = "local-test"

        async def score(self, metric_name, sample):
            request = httpx.Request("POST", "https://judge.invalid/chat/completions")
            try:
                await recorder.capture_request(request)
            except RuntimeError:
                raise RagasGenerationProviderError(private) from None
            is_first = recorder.api_calls == 1
            if scenario == "timeout":
                raise RagasGenerationTimeoutError(private)
            await recorder.capture_response(
                httpx.Response(
                    401 if scenario == "provider" and is_first else 200,
                    json={"usage": {"prompt_tokens": 10, "completion_tokens": 5}},
                    request=request,
                )
            )
            if scenario in {"output", "provider"} and is_first:
                raise RagasGenerationProviderError(private)
            return 1.0 if scenario == "high" else 0.2

    adapter = RagasGenerationAdapter(
        backend=Backend(),
        judge=RagasJudgeRuntime(
            provider="deepseek-openai-compatible",
            model="deepseek-v4-flash",
            model_version="local-test",
            temperature=0.0,
            top_p=1.0,
            max_output_tokens=2048,
            seed=None,
            max_attempts=1,
            timeout_ms=30000,
        ),
        answer_provider="deepseek",
        answer_model="deepseek-v4-flash",
    )
    formal = SimpleNamespace(
        answer_provider=SimpleNamespace(aclose=AsyncMock()),
        semantic_adapter=adapter,
        judge_usage=recorder,
    )
    snapshot = SimpleNamespace(
        tenant_id=uuid4(), corpus_sha256="1" * 64, logical_document_ids={}
    )
    public_corpus = FrozenRagCorpusPublicIdentity(
        corpus_sha256="1" * 64,
        index_sha256="2" * 64,
        snapshot_sha256="3" * 64,
        source_count=18,
        document_count=18,
        chunk_set_count=18,
        index_set_count=36,
        chunk_count=779,
        chunks_reused_without_rechunking=True,
    )
    user = SimpleNamespace(user_id=uuid4(), email="local@example.test")
    messages = []
    answers = []
    cleaned = []

    class Client:
        portal = SimpleNamespace(call=lambda fn: asyncio.run(fn()))

        def __init__(self, app):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def post(self, path, **kwargs):
            if path == "/api/v1/threads":
                return httpx.Response(201, json={"thread_id": str(uuid4())})
            messages.append(kwargs["json"]["message"])
            return httpx.Response(200)

    def inspect_case(*, case, provider, **kwargs):
        answers.append(case.case_id)
        provider.answer_compose_calls = 1
        provider.last_answer_duration_ms = 1
        provider.last_answer_usage = FormalModelUsage(
            api_calls=1,
            input_tokens=10,
            output_tokens=5,
            total_tokens=15,
        )
        if scenario in {"business", "citation"} and len(answers) == 4:
            artifact = module._not_run_case_artifacts(case)
            return replace(
                artifact,
                audit=artifact.audit.model_copy(
                    update={
                        "status": "calculation_failed",
                        **(
                            {
                                "agent_output_stage": "citation_contract",
                                "api_status_code": 422,
                                "api_error_code": "PROVIDER_ERROR",
                                "search_knowledge_tool_status": "success",
                                "allowed_successful_tool_call_count": 1,
                                "search_knowledge_error_code": None,
                            }
                            if scenario == "citation"
                            else {}
                        ),
                    }
                ),
                execution=AnswerExecutionRecord(
                    status="provider_failed",
                    failure_category="provider_error",
                    failure_summary="API failed",
                ),
            )
        cited = int(case.should_answer)
        audit = AnswerCitationGatewayCaseAudit(
            case_id=case.case_id,
            should_answer=case.should_answer,
            status="completed",
            api_status_code=200,
            gateway_status="completed",
            gateway_business_outcome="answered"
            if case.should_answer
            else "no_evidence",
            tool_names=["search_knowledge"],
            root_run_count=1,
            worker_run_count=1,
            search_knowledge_tool_call_count=1,
            allowed_successful_tool_call_count=1,
            search_knowledge_tool_status="success",
            search_knowledge_duration_ms=1,
            context_artifact_count=1,
            context_segment_count=1,
            context_evidence_count=1,
            provider_evidence_count=1,
            answer_evidence_count=cited,
            public_evidence_count=cited,
            context_authorization_passed=True,
            answer_citation_validator_passed=True,
            answer_mapping_passed=True,
            protected_evidence_leak_count=0,
            chain_passed=True,
        )
        return SimpleNamespace(
            audit=audit,
            execution=AnswerExecutionRecord(
                status="completed", response_kind="answer", answer_text="合成答案[E1]"
            ),
            semantic_input=RagasGenerationInput(
                user_input=case.question,
                retrieved_contexts=("合成资料",),
                reference="合成参考",
                response="合成答案[E1]",
            )
            if case.should_answer
            else None,
        )

    real_trace = module._case_trace
    stubs = {
        "_validate_runtime_configuration": lambda *args: None,
        "_public_corpus": lambda *args: public_corpus,
        "_gateway_runtime_identity": lambda *args: (
            AnswerCitationGatewayRuntimeIdentity()
        ),
        "_formal_answer_provider_identity": lambda *args: FormalAnswerProviderIdentity(
            model_id="deepseek-v4-flash",
            prompt_bundle_sha256="1" * 64,
            answer_schema_sha256="2" * 64,
        ),
        "_warm_gateway_retrieval_models": lambda *args: None,
        "_evaluation_users": lambda *args, **kwargs: {
            item.case.trusted_user_fixture_id: user for item in inputs
        },
        "_tenant_context_ids": lambda *args: frozenset(),
        "create_app": lambda *args, **kwargs: SimpleNamespace(
            state=SimpleNamespace(), dependency_overrides={}
        ),
        "TestClient": Client,
        "_login_evaluation_owner": lambda *args: ("local-token", user),
        "_case_database_state": lambda *args, **kwargs: nullcontext(),
        "_inspect_case": inspect_case,
        "_case_trace": lambda case, artifact: (
            traces[case.case_id]
            if artifact.audit.status == "completed"
            else real_trace(case, artifact)
        ),
        "_runtime_rows": lambda *args: SimpleNamespace(
            root_ids=set(),
            worker_ids=set(),
            tool_call_ids=set(),
            context_ids=set(),
            answer_evidence_ids=set(),
        ),
        "_context_evidence_ids": lambda *args: frozenset(),
        "_cleanup_runtime_rows": lambda **kwargs: cleaned.append(kwargs["thread_ids"]),
        "_remaining_runtime_rows": lambda **kwargs: {
            **{
                name: 0
                for name in AnswerCitationGatewayLifecycle.model_fields
                if name.startswith("remaining_")
            },
            "baseline_restored": True,
        },
        "load_existing_m2_reranker_context_corpus": lambda **kwargs: snapshot,
    }
    for name, stub in stubs.items():
        monkeypatch.setattr(module, name, stub)
    real_write = AnswerReviewWriter.write

    def checked_write(writer, name, payload):
        if scenario == "disk" and name == "case-001.json":
            raise ReviewEvidenceWriteError(
                "Private review persistence failed; evaluation stopped."
            )
        assert not cleaned or name in {"cleanup.json", "report.json"}
        real_write(writer, name, payload)

    monkeypatch.setattr(AnswerReviewWriter, "write", checked_write)

    def run():
        return module.run_m2_answer_citation_gateway_evaluation(
            settings=SimpleNamespace(),
            runtime=SimpleNamespace(),
            storage=SimpleNamespace(),
            snapshot=snapshot,
            embedding_provider=SimpleNamespace(),
            reranker_provider=SimpleNamespace(),
            evidence_ids_by_chunk={},
            project_root=tmp_path,
            formal_runtime=formal,
        )

    if scenario == "disk":
        with pytest.raises(ReviewEvidenceWriteError):
            run()
        assert len(messages) == len(answers) == len(cleaned) == 1
        assert recorder.api_calls == 0
        assert not list(
            (tmp_path / "data/evals/runtime/private-review").glob("*/report.json")
        )
        return
    report = run()
    expected = 4 if scenario == "business" else 40
    assert len(messages) == len(answers) == len(set(answers)) == expected
    assert report.answer_usage.api_calls == expected
    assert len(cleaned) == 1 and len(cleaned[0]) == expected
    assert report.run_status == (
        "completed_with_failures"
        if scenario in {"business", "citation"}
        else "completed"
    )
    payload = json.loads(serialize_answer_citation_public_report(report))
    assert payload["business_quality_gate_passed"] is (
        scenario not in {"business", "citation"}
    )
    if scenario == "citation":
        assert report.chain_audits[3].api_status_code == 422
        assert report.chain_audits[3].agent_output_stage == "citation_contract"
        assert report.chain_audits[4].status == "completed"
        assert report.formal_evaluations[3].judge_usage.api_calls == 0
        assert report.formal_evaluations[4].judge_usage.api_calls > 0
    assert payload["ragas_quality_gate_passed"] is (
        scenario == "high" if scenario in {"low", "high"} else None
    )
    assert payload["schema_version"] == "m2-answer-citation-formal-report-v4"
    assert private not in json.dumps(payload)
    assert AnswerCitationFormalEvaluationReport.model_validate(payload) == report
    for field in ("business_quality_gate_passed", "ragas_quality_gate_passed"):
        tampered = dict(payload, **{field: not payload[field]})
        with pytest.raises(ValidationError, match="gate contradicts"):
            AnswerCitationFormalEvaluationReport.model_validate(tampered)
    with pytest.raises(ValidationError):
        AnswerCitationFormalEvaluationReport.model_validate(
            dict(payload, schema_version="m2-answer-citation-formal-report-v3")
        )
    if scenario in {"provider", "budget", "timeout"}:
        assert (
            report.judge_usage.api_calls
            == {"provider": 1, "budget": 5, "timeout": 4}[scenario]
        )
        assert report.formal_evaluations[2].status == "skipped"
        assert all(
            m.value is None for m in report.formal_evaluations[2].semantic_metrics
        )
        assert report.formal_evaluations[2].judge_usage.api_calls == 0
        assert recorder.stopped or recorder.api_calls == recorder.max_api_calls
    assert report.judge_usage == recorder.snapshot()
    assert report.answer_usage.total_tokens == expected * 15
    retained = list(
        (tmp_path / "data/evals/runtime/private-review").glob("*/case-001.json")
    )
    assert len(retained) == 1, "evaluation discarded the actual Answer after scoring"
    detail = json.loads(retained[0].read_text(encoding="utf-8"))
    assert detail["answer_text"] == "合成答案[E1]"
    assert detail["question"] == inputs[0].case.question
    assert detail["reference_key_points"] == list(inputs[0].case.answer_key_points)
    assert detail["trace_sha256"] == report.case_results[0].trace_sha256
    assert (retained[0].parent / "cleanup.json").exists()
    final = json.loads((retained[0].parent / "report.json").read_bytes())
    assert final["trace_set_sha256"] == report.trace_set_sha256
    assert "合成答案" not in serialize_answer_citation_public_report(report).decode()
    if scenario == "output":
        assert report.formal_evaluations[0].semantic_metrics[0].value is None
        assert report.formal_evaluations[1].status == "completed"
        assert report.semantic_aggregates[0].failed_case_count == 1
        assert report.semantic_aggregates[0].completed_case_count == 33
    if scenario == "business":
        assert report.formal_evaluations[4].answer_usage.api_calls == 0


def test_review_binding_crosses_testclient_and_worker_thread_without_leaking_to_next_request():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.core.rag_trace import RagReviewTrace, rag_review_trace, record_rag_stage
    from app.schemas.agent import ResourceUsage

    app = FastAPI()
    usage = ResourceUsage(
        model_calls=2, tool_calls=1, input_tokens=0, output_tokens=0, duration_ms=1
    )

    @app.get("/local-only")
    def local():
        record_rag_stage("resource_usage", usage)
        return {"ok": True}

    trace = RagReviewTrace()
    with TestClient(app) as client:
        with rag_review_trace(trace):
            assert client.get("/local-only").status_code == 200
        assert trace.resource_usage == usage.model_dump(mode="json")
        trace.resource_usage = None
        client.get("/local-only")
        assert trace.resource_usage is None


def test_gateway_runner_warms_both_local_inference_paths_before_the_api_timer() -> None:
    embedding_calls: list[tuple[list[str], EmbeddingPurpose]] = []
    reranker_calls: list[tuple[str, list[str]]] = []
    embedding_provider = type(
        "WarmEmbedding",
        (),
        {
            "embed": lambda self, texts, *, purpose: embedding_calls.append(
                (list(texts), purpose)
            )
        },
    )()
    reranker_provider = type(
        "WarmReranker",
        (),
        {
            "score": lambda self, query, passages: reranker_calls.append(
                (query, list(passages))
            )
        },
    )()

    _warm_gateway_retrieval_models(  # type: ignore[arg-type]
        embedding_provider,
        reranker_provider,
    )

    assert embedding_calls == [
        (["cross-border knowledge retrieval warmup"], EmbeddingPurpose.QUERY)
    ]
    assert reranker_calls == [
        (
            "cross-border knowledge retrieval warmup",
            ["cross-border knowledge retrieval warmup"],
        )
    ]


def test_production_gateway_budget_stays_business_four_plus_knowledge_eight() -> None:
    limits = AgentGatewayLimits()

    assert limits.root.max_evidence == 12
    assert limits.business_child.max_evidence == 4
    assert limits.knowledge_child.max_evidence == 8


def test_production_knowledge_budget_rejects_twelve_evidence() -> None:
    limits = AgentGatewayLimits()
    tree = AgentBudgetTree(root_run_id=uuid4(), limits=limits.root)
    child = tree.allocate_child(
        parent_run_id=tree.root_run_id,
        child_run_id=uuid4(),
        task_id="search_frozen_knowledge",
        limits=limits.knowledge_child,
    )

    with pytest.raises(BudgetExceededError, match="Worker Evidence"):
        child.record_evidence([uuid4() for _ in range(12)])


def test_gateway_evaluation_has_a_knowledge_only_twelve_evidence_identity() -> None:
    assert hasattr(answer_citation_formal, "evaluation_gateway_limits")
    limits = answer_citation_formal.evaluation_gateway_limits()

    assert limits.root.max_evidence == 12
    assert limits.business_child.max_evidence == 0
    assert limits.knowledge_child.max_evidence == 12


def test_fake_runner_generates_each_of_the_frozen_40_rows_once() -> None:
    cases, dataset_version, dataset_sha256 = build_fake_answer_case_inputs_from_dataset(
        DATASET_PATH
    )
    provider = DeterministicFakeAnswerProvider()

    report = run_m2_answer_citation_fake_evaluation(
        cases=cases,
        dataset_version=dataset_version,
        dataset_sha256=dataset_sha256,
        provider=provider,
    )

    assert report.execution_mode == "deterministic_fake"
    assert report.run_status == "completed"
    assert report.quality_gate_passed is None
    assert len(report.case_results) == 40
    assert sum(item.trace.should_answer for item in report.case_results) == 34
    assert provider.call_count == 40
    assert report.cache.answer_requests == 40
    assert report.cache.cache_hits == 0
    assert report.cache.cache_misses == 40
    assert report.cache.provider_answer_calls == 40
    assert report.cache.cache_entries == 40
    assert report.grouped_results.all_answerable.expected_case_count == 34
    assert report.grouped_results.real_cross_border.expected_case_count == 14
    assert report.grouped_results.synthetic_cross_border.expected_case_count == 10
    assert report.grouped_results.general_diagnostics.expected_case_count == 10
    assert report.grouped_results.safety_acl_version.expected_case_count == 6
    assert all(
        item.trace.result.overall_deterministic_pass is True
        for item in report.case_results
    )


def test_fake_runner_is_byte_deterministic_for_the_same_dataset() -> None:
    cases, dataset_version, dataset_sha256 = build_fake_answer_case_inputs_from_dataset(
        DATASET_PATH
    )

    first = run_m2_answer_citation_fake_evaluation(
        cases=cases,
        dataset_version=dataset_version,
        dataset_sha256=dataset_sha256,
        provider=DeterministicFakeAnswerProvider(),
    )
    second = run_m2_answer_citation_fake_evaluation(
        cases=cases,
        dataset_version=dataset_version,
        dataset_sha256=dataset_sha256,
        provider=DeterministicFakeAnswerProvider(),
    )

    assert serialize_answer_citation_public_report(first) == (
        serialize_answer_citation_public_report(second)
    )
    assert first.run_id == second.run_id
    assert first.trace_set_sha256 == second.trace_set_sha256


def test_run_cache_reuses_a_completed_answer_without_a_second_generation() -> None:
    cases, _, _ = build_fake_answer_case_inputs_from_dataset(DATASET_PATH)
    request = build_fake_answer_request(cases[0])
    cache = RunAnswerCache()
    provider = DeterministicFakeAnswerProvider()

    first = cache.get_or_generate(request=request, provider=provider)
    repeated = cache.get_or_generate(request=request, provider=provider)

    assert first == repeated
    assert provider.call_count == 1
    assert cache.stats().model_dump() == {
        "scope": "current_run_only",
        "answer_requests": 2,
        "cache_hits": 1,
        "cache_misses": 1,
        "provider_answer_calls": 1,
        "cache_entries": 1,
    }


class _RaiseOnceFakeProvider:
    identity = FakeAnswerProviderIdentity()

    def __init__(self) -> None:
        self.call_count = 0
        self._delegate = DeterministicFakeAnswerProvider()

    def generate(self, request: FakeAnswerRequest) -> AnswerExecutionRecord:
        self.call_count += 1
        if self.call_count == 1:
            raise RuntimeError("tenant_id=private C:\\private\\answer.txt")
        return self._delegate.generate(request)


def test_failed_answer_is_safe_and_is_not_cached() -> None:
    cases, _, _ = build_fake_answer_case_inputs_from_dataset(DATASET_PATH)
    request = build_fake_answer_request(cases[0])
    cache = RunAnswerCache()
    provider = _RaiseOnceFakeProvider()

    failed = cache.get_or_generate(request=request, provider=provider)
    succeeded = cache.get_or_generate(request=request, provider=provider)

    assert failed.status == "provider_failed"
    assert failed.failure_category == "provider_error"
    assert failed.failure_summary == "Fake Answer Provider execution failed."
    assert succeeded.status == "completed"
    assert provider.call_count == 2
    assert cache.stats().model_dump() == {
        "scope": "current_run_only",
        "answer_requests": 2,
        "cache_hits": 0,
        "cache_misses": 2,
        "provider_answer_calls": 2,
        "cache_entries": 1,
    }


def test_runner_retains_a_failed_row_without_serializing_the_raw_exception() -> None:
    cases, dataset_version, dataset_sha256 = build_fake_answer_case_inputs_from_dataset(
        DATASET_PATH
    )
    provider = _RaiseOnceFakeProvider()

    report = run_m2_answer_citation_fake_evaluation(
        cases=cases,
        dataset_version=dataset_version,
        dataset_sha256=dataset_sha256,
        provider=provider,
    )

    failed = report.case_results[0].trace.result
    assert failed.status == "calculation_failed"
    assert failed.key_point_coverage_rate is None
    assert failed.failure_attributions == ["answer_execution_failed"]
    assert report.grouped_results.all_answerable.status == "calculation_failed"
    assert report.grouped_results.all_answerable.key_point_coverage_rate is None
    assert report.cache.provider_answer_calls == 40
    assert report.cache.cache_entries == 39
    public_text = serialize_answer_citation_public_report(report).decode("utf-8")
    assert "tenant_id=private" not in public_text
    assert "private\\answer.txt" not in public_text


def test_fake_runner_rejects_a_non_fake_provider_identity() -> None:
    cases, dataset_version, dataset_sha256 = build_fake_answer_case_inputs_from_dataset(
        DATASET_PATH
    )
    provider = DeterministicFakeAnswerProvider()
    provider.identity = object()  # type: ignore[assignment]

    try:
        run_m2_answer_citation_fake_evaluation(
            cases=cases,
            dataset_version=dataset_version,
            dataset_sha256=dataset_sha256,
            provider=provider,
        )
    except TypeError as exc:
        assert "explicit fake Answer Provider" in str(exc)
    else:
        raise AssertionError("the fake-only runner accepted another Provider identity")

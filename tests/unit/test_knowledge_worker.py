from __future__ import annotations

import ast
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, TypeAlias, cast
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from sqlalchemy.orm import Session

from app.agents.definitions import create_m2_agent_definitions
from app.agents.runtime import WorkerExecutionContext, WorkerRunTrace
from app.agents.workers.knowledge import (
    KnowledgeCapabilityExecutor,
    KnowledgeCapabilityExecutorFactory,
    KnowledgeWorker,
    KnowledgeWorkerGuardrails,
)
from app.capabilities.catalog import create_m2_capability_catalog
from app.capabilities.resolver import CapabilityResolver
from app.llm.agent_provider import AgentDecisionProvider
from app.llm.agent_schemas import DecisionRequest
from app.runtime.budget import ChildExecutionBudget
from app.runtime.context import RunContext
from app.runtime.executor import HarnessExecutor
from app.schemas.agent import (
    AgentDecision,
    AgentHandoff,
    AskUserAction,
    BoundedJsonObject,
    CannotCompleteAction,
    ExecuteCapabilityAction,
    FinishAction,
)
from app.schemas.common import ToolEnvelope, ToolMeta, ToolName
from app.schemas.context import ContextBundle, ContextSegment
from app.schemas.evidence import GetEvidenceDetailResult, ToolDocumentEvidenceDetail
from app.schemas.file_reading import ReadUploadedFileResult
from app.schemas.knowledge import SearchKnowledgeResult
from app.schemas.retrieval import (
    PdfRetrievalSourceLocator,
    RetrievalCandidateIdentity,
    RetrievalDocumentMetadata,
)

ROOT = Path(__file__).parents[2]
ROOT_RUN_ID = UUID("00000000-0000-0000-0000-000000000701")
WORKER_RUN_ID = UUID("00000000-0000-0000-0000-000000000702")
HANDOFF_ID = UUID("00000000-0000-0000-0000-000000000703")
BUDGET_REF = UUID("00000000-0000-0000-0000-000000000704")
TRACE_ID = UUID("00000000-0000-0000-0000-000000000705")
TENANT_ID = UUID("00000000-0000-0000-0000-000000000706")
USER_ID = UUID("00000000-0000-0000-0000-000000000707")
THREAD_ID = UUID("00000000-0000-0000-0000-000000000708")
EVIDENCE_ID = UUID("00000000-0000-0000-0000-000000000709")
FORGED_EVIDENCE_ID = UUID("00000000-0000-0000-0000-000000000710")
FILE_ID = UUID("00000000-0000-0000-0000-000000000711")
FORGED_FILE_ID = UUID("00000000-0000-0000-0000-000000000712")
DOCUMENT_ID = UUID("00000000-0000-0000-0000-000000000713")
VERSION_ID = UUID("00000000-0000-0000-0000-000000000714")
INDEX_SET_ID = UUID("00000000-0000-0000-0000-000000000715")
CHUNK_ID = UUID("00000000-0000-0000-0000-000000000716")
CONTEXT_ID = UUID("00000000-0000-0000-0000-000000000717")
OBSERVATION_IDS = tuple(
    UUID(f"00000000-0000-0000-0000-{value:012d}") for value in range(720, 740)
)

DecisionStep: TypeAlias = AgentDecision | Callable[[DecisionRequest], AgentDecision]
KnowledgeEnvelope: TypeAlias = (
    ToolEnvelope[SearchKnowledgeResult]
    | ToolEnvelope[ReadUploadedFileResult]
    | ToolEnvelope[GetEvidenceDetailResult]
)


def context() -> RunContext:
    return RunContext(
        user_id=USER_ID,
        tenant_id=TENANT_ID,
        roles=("amazon_operator",),
        market_scopes=("DE",),
        thread_id=THREAD_ID,
        trace_id=TRACE_ID,
    )


def execution() -> WorkerExecutionContext:
    return WorkerExecutionContext(
        trusted_context=context(),
        worker_run=WorkerRunTrace(
            run_id=WORKER_RUN_ID,
            parent_run_id=ROOT_RUN_ID,
            root_run_id=ROOT_RUN_ID,
            trace_id=TRACE_ID,
            budget_ref=BUDGET_REF,
            depth=1,
        ),
        budget=cast(ChildExecutionBudget, MagicMock(spec=ChildExecutionBudget)),
        harness=cast(HarnessExecutor, MagicMock(spec=HarnessExecutor)),
        session=cast(Session, MagicMock(spec=Session)),
    )


def handoff(
    *,
    public_context: dict[str, object] | None = None,
    evidence_ids: list[UUID] | None = None,
    artifact_ids: list[UUID] | None = None,
) -> AgentHandoff:
    return AgentHandoff(
        handoff_id=HANDOFF_ID,
        task_id="knowledge_task",
        goal="查询蘑菇灯手册中的清洁要求",
        target_worker="knowledge",
        public_context=BoundedJsonObject(
            public_context or {"knowledge_query": "蘑菇灯如何清洁？"}
        ),
        evidence_ids=evidence_ids or [],
        artifact_ids=artifact_ids or [],
        constraints=["只能调用获权的只读知识Tool"],
        expected_output="返回文档事实、Evidence或Artifact ID",
        completion_criteria=["返回获权知识或明确无证据"],
        allocated_budget_ref=BUDGET_REF,
    )


def _segment() -> ContextSegment:
    return ContextSegment(
        citation_label="[E1]",
        evidence_id=EVIDENCE_ID,
        source_type="knowledge",
        role="anchor",
        reranker_rank=1,
        identity=RetrievalCandidateIdentity(
            document_id=DOCUMENT_ID,
            version_id=VERSION_ID,
            index_set_id=INDEX_SET_ID,
            chunk_id=CHUNK_ID,
        ),
        document=RetrievalDocumentMetadata(
            title="合成蘑菇灯说明书",
            document_type="product_manual",
            language="zh-CN",
            market="DE",
        ),
        source_locator=PdfRetrievalSourceLocator(page_number=1),
        text="清洁前必须断开电源。",
        text_sha256="a" * 64,
        token_count=10,
        overlap_trimmed=False,
    )


def search_envelope(*, supported: bool = True) -> ToolEnvelope[SearchKnowledgeResult]:
    segments = [_segment()] if supported else []
    return ToolEnvelope[SearchKnowledgeResult](
        status="success",
        data=SearchKnowledgeResult(
            context=ContextBundle(
                context_id=CONTEXT_ID,
                query_sha256="b" * 64,
                context_sha256="c" * 64,
                max_tokens=4000,
                total_tokens=10 if supported else 0,
                supported=supported,
                segments=segments,
            )
        ),
        evidence_ids=[EVIDENCE_ID] if supported else [],
        meta=tool_meta("search_knowledge"),
    )


def file_envelope() -> ToolEnvelope[ReadUploadedFileResult]:
    content = "清洁前必须断开电源。"
    return ToolEnvelope[ReadUploadedFileResult](
        status="success",
        data=ReadUploadedFileResult(
            file_id=FILE_ID,
            document_id=DOCUMENT_ID,
            version_id=VERSION_ID,
            version_no=2,
            original_name="synthetic-manual.pdf",
            source_type="pdf",
            is_active_version=True,
            sections=[
                {
                    "kind": "text",
                    "locator": {"source_type": "pdf", "page_number": 1},
                    "content": content,
                    "truncated": False,
                }
            ],
            total_characters=len(content),
            truncated=False,
        ),
        evidence_ids=[],
        meta=tool_meta("read_uploaded_file"),
    )


def evidence_envelope() -> ToolEnvelope[GetEvidenceDetailResult]:
    now = datetime(2026, 9, 5, 8, 0, tzinfo=UTC)
    return ToolEnvelope[GetEvidenceDetailResult](
        status="success",
        data=GetEvidenceDetailResult(
            detail=ToolDocumentEvidenceDetail(
                id=EVIDENCE_ID,
                source_type="knowledge",
                title="合成蘑菇灯说明书",
                excerpt="清洁前必须断开电源。",
                observed_at=now,
                context_id=CONTEXT_ID,
                citation_label="[E1]",
                identity=_segment().identity,
                document=_segment().document,
                source_locator=_segment().source_locator,
                source_content_sha256="d" * 64,
                context_text_sha256="a" * 64,
                trust_level="document_snapshot",
                created_at=now,
                file_id=FILE_ID,
            )
        ),
        evidence_ids=[EVIDENCE_ID],
        meta=tool_meta("get_evidence_detail"),
    )


def error_envelope(tool: ToolName, *, code: str, message: str) -> KnowledgeEnvelope:
    return ToolEnvelope[SearchKnowledgeResult].model_validate(
        {
            "status": "error",
            "error": {"code": code, "message": message, "retryable": False},
            "meta": tool_meta(tool).model_dump(mode="python"),
        }
    )


def tool_meta(tool: ToolName) -> ToolMeta:
    return ToolMeta(
        tool=tool,
        version="1.0.0",
        duration_ms=3,
        trace_id=TRACE_ID,
    )


def execute(capability_id: str, arguments: dict[str, object]) -> AgentDecision:
    return AgentDecision(
        action=ExecuteCapabilityAction(
            capability_id=capability_id,
            arguments=BoundedJsonObject(arguments),
        )
    )


def finish_from_observations(
    request: DecisionRequest,
    *,
    outcome: Literal["answered", "partial", "no_evidence"] = "answered",
) -> AgentDecision:
    return AgentDecision(
        action=FinishAction(
            public_summary="Knowledge Worker已完成获权查询。",
            business_outcome=outcome,
            evidence_ids=list(
                dict.fromkeys(
                    item
                    for observation in request.observations
                    for item in observation.evidence_ids
                )
            ),
            artifact_ids=list(
                dict.fromkeys(
                    item
                    for observation in request.observations
                    for item in observation.artifact_ids
                )
            ),
        )
    )


@dataclass
class ScriptedDecisionProvider:
    steps: list[DecisionStep]
    requests: list[DecisionRequest] = field(default_factory=list)

    async def choose_action(self, request: DecisionRequest) -> AgentDecision:
        self.requests.append(request)
        step = self.steps.pop(0)
        return step(request) if callable(step) else step.model_copy(deep=True)


@dataclass
class FakeKnowledgeExecutor:
    responses: dict[str, list[KnowledgeEnvelope]]
    calls: list[ExecuteCapabilityAction] = field(default_factory=list)

    def execute(self, action: ExecuteCapabilityAction) -> KnowledgeEnvelope:
        self.calls.append(action)
        return self.responses[action.capability_id].pop(0)


@dataclass
class FakeKnowledgeExecutorFactory:
    executor: FakeKnowledgeExecutor

    def create(
        self,
        execution_context: WorkerExecutionContext,
    ) -> KnowledgeCapabilityExecutor:
        del execution_context
        return self.executor


def worker(
    provider: ScriptedDecisionProvider,
    executor: FakeKnowledgeExecutor,
    *,
    max_decisions: int = 5,
) -> KnowledgeWorker:
    ids = iter(OBSERVATION_IDS)
    return KnowledgeWorker(
        provider=cast(AgentDecisionProvider, provider),
        resolver=CapabilityResolver(
            create_m2_capability_catalog(),
            create_m2_agent_definitions(),
        ),
        executor_factory=cast(
            KnowledgeCapabilityExecutorFactory,
            FakeKnowledgeExecutorFactory(executor),
        ),
        guardrails=KnowledgeWorkerGuardrails(max_decisions=max_decisions),
        id_factory=lambda: next(ids),
    )


@pytest.mark.asyncio
async def test_search_knowledge_returns_document_evidence() -> None:
    executor = FakeKnowledgeExecutor({"search_knowledge": [search_envelope()]})
    provider = ScriptedDecisionProvider(
        [
            execute("search_knowledge", {"query": "蘑菇灯如何清洁？"}),
            finish_from_observations,
        ]
    )

    result = await worker(provider, executor).run(handoff(), execution())

    assert result.execution_status == "completed"
    assert result.business_outcome == "answered"
    assert [item.capability_id for item in executor.calls] == ["search_knowledge"]
    assert result.evidence_ids == [EVIDENCE_ID]
    assert result.artifact_ids == []
    assert result.business_result is not None
    assert "knowledge_search" in result.business_result.root


@pytest.mark.asyncio
async def test_empty_search_is_a_successful_no_evidence_result() -> None:
    executor = FakeKnowledgeExecutor(
        {"search_knowledge": [search_envelope(supported=False)]}
    )
    provider = ScriptedDecisionProvider(
        [
            execute("search_knowledge", {"query": "蘑菇灯如何清洁？"}),
            lambda request: finish_from_observations(request, outcome="no_evidence"),
        ]
    )

    result = await worker(provider, executor).run(handoff(), execution())

    assert result.execution_status == "completed"
    assert result.business_outcome == "no_evidence"
    assert result.evidence_ids == []
    assert result.observations[0].status == "success"


@pytest.mark.asyncio
async def test_file_read_returns_only_the_authorized_file_as_artifact() -> None:
    executor = FakeKnowledgeExecutor({"read_uploaded_file": [file_envelope()]})
    provider = ScriptedDecisionProvider(
        [
            execute(
                "read_uploaded_file",
                {
                    "file_id": str(FILE_ID),
                    "locator": {"source_type": "pdf", "page_start": 1},
                },
            ),
            finish_from_observations,
        ]
    )

    result = await worker(provider, executor).run(
        handoff(public_context={"file_id": str(FILE_ID)}),
        execution(),
    )

    assert result.business_outcome == "answered"
    assert result.evidence_ids == []
    assert result.artifact_ids == [FILE_ID]
    assert result.observations[0].artifact_ids == [FILE_ID]
    assert result.business_result is not None
    assert "uploaded_file" in result.business_result.root


@pytest.mark.asyncio
async def test_evidence_detail_requires_a_transferred_or_observed_evidence_id() -> None:
    valid_executor = FakeKnowledgeExecutor(
        {"get_evidence_detail": [evidence_envelope()]}
    )
    valid = await worker(
        ScriptedDecisionProvider(
            [
                execute("get_evidence_detail", {"evidence_id": str(EVIDENCE_ID)}),
                finish_from_observations,
            ]
        ),
        valid_executor,
    ).run(handoff(evidence_ids=[EVIDENCE_ID]), execution())
    assert valid.business_outcome == "answered"
    assert valid.evidence_ids == [EVIDENCE_ID]
    assert valid.artifact_ids == [FILE_ID]

    forged_executor = FakeKnowledgeExecutor({})
    forged = await worker(
        ScriptedDecisionProvider(
            [execute("get_evidence_detail", {"evidence_id": str(FORGED_EVIDENCE_ID)})]
        ),
        forged_executor,
    ).run(handoff(evidence_ids=[EVIDENCE_ID]), execution())
    assert forged.execution_status == "failed"
    assert forged.safe_errors[0].code == "PROVIDER_ERROR"
    assert forged_executor.calls == []


@pytest.mark.asyncio
async def test_search_result_may_be_expanded_but_cross_worker_and_file_drift_fail() -> (
    None
):
    executor = FakeKnowledgeExecutor(
        {
            "search_knowledge": [search_envelope()],
            "get_evidence_detail": [evidence_envelope()],
        }
    )
    expanded = await worker(
        ScriptedDecisionProvider(
            [
                execute("search_knowledge", {"query": "蘑菇灯如何清洁？"}),
                execute("get_evidence_detail", {"evidence_id": str(EVIDENCE_ID)}),
                finish_from_observations,
            ]
        ),
        executor,
    ).run(handoff(), execution())
    assert expanded.business_outcome == "answered"
    assert expanded.evidence_ids == [EVIDENCE_ID]
    assert expanded.artifact_ids == [FILE_ID]

    for decision in (
        execute("search_inventory", {"sku": "LR-TL-MUSH-OR01", "market_code": "DE"}),
        execute("search_knowledge", {"query": "另一个目标"}),
        execute("read_uploaded_file", {"file_id": str(FORGED_FILE_ID)}),
    ):
        rejected_executor = FakeKnowledgeExecutor({})
        result = await worker(
            ScriptedDecisionProvider([decision]), rejected_executor
        ).run(
            handoff(
                public_context={"file_id": str(FILE_ID), "query": "蘑菇灯如何清洁？"}
            ),
            execution(),
        )
        assert result.execution_status == "failed"
        assert result.safe_errors[0].code == "PROVIDER_ERROR"
        assert rejected_executor.calls == []


@pytest.mark.asyncio
async def test_denied_timeout_clarification_and_repeat_are_bounded() -> None:
    denied_executor = FakeKnowledgeExecutor(
        {
            "read_uploaded_file": [
                error_envelope(
                    "read_uploaded_file",
                    code="FORBIDDEN",
                    message="当前账号无权读取该文件",
                )
            ]
        }
    )
    denied = await worker(
        ScriptedDecisionProvider(
            [
                execute("read_uploaded_file", {"file_id": str(FILE_ID)}),
                AgentDecision(
                    action=CannotCompleteAction(
                        public_summary="当前账号无权读取该文件。",
                        business_outcome="denied",
                    )
                ),
            ]
        ),
        denied_executor,
    ).run(handoff(public_context={"file_id": str(FILE_ID)}), execution())
    assert denied.execution_status == "completed"
    assert denied.business_outcome == "denied"
    assert denied.safe_errors[0].code == "FORBIDDEN"

    timeout_executor = FakeKnowledgeExecutor(
        {
            "search_knowledge": [
                error_envelope(
                    "search_knowledge",
                    code="DATABASE_TIMEOUT",
                    message="知识检索超时，请稍后重试",
                )
            ]
        }
    )
    timeout = await worker(
        ScriptedDecisionProvider(
            [execute("search_knowledge", {"query": "蘑菇灯如何清洁？"})]
        ),
        timeout_executor,
    ).run(handoff(), execution())
    assert timeout.execution_status == "failed"
    assert timeout.business_outcome == "timed_out"

    clarification = await worker(
        ScriptedDecisionProvider(
            [
                AgentDecision(
                    action=AskUserAction(
                        question="请提供要读取的公开文件ID。",
                        requested_fields=["file_id"],
                    )
                )
            ]
        ),
        FakeKnowledgeExecutor({}),
    ).run(handoff(), execution())
    assert clarification.execution_status == "waiting_user"
    assert clarification.unknowns == ["file_id"]

    action = execute("search_knowledge", {"query": "蘑菇灯如何清洁？"})
    repeated_executor = FakeKnowledgeExecutor(
        {"search_knowledge": [search_envelope(), search_envelope()]}
    )
    repeated = await worker(
        ScriptedDecisionProvider([action, action]), repeated_executor
    ).run(handoff(), execution())
    assert repeated.execution_status == "failed"
    assert repeated.safe_errors[0].code == "BUDGET_EXCEEDED"
    assert len(repeated_executor.calls) == 1


def test_knowledge_worker_has_only_m2_knowledge_dependencies() -> None:
    tree = ast.parse(
        (ROOT / "app/agents/workers/knowledge.py").read_text(encoding="utf-8")
    )
    imports = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    assert "app.agents.graphs.inventory_query" not in imports
    assert not {
        item
        for item in imports
        if item.startswith(
            (
                "app.services.inventory",
                "app.services.product",
                "app.tools.get_product_spec",
                "app.tools.search_inventory",
            )
        )
    }


def test_knowledge_worker_guardrails_are_strict_and_bounded() -> None:
    assert KnowledgeWorkerGuardrails().max_decisions == 5
    with pytest.raises(ValueError):
        KnowledgeWorkerGuardrails(max_decisions=0)

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from typing import cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, func, select

from app.core.errors import ApplicationError
from app.models.identity import Tenant
from app.models.knowledge import (
    Document,
    DocumentAcl,
    DocumentChunk,
    DocumentIndexSet,
    DocumentVersion,
)
from app.models.runtime import (
    ContextArtifact,
    Evidence,
    Thread,
    ToolCall,
    ToolContextLink,
)
from app.repositories.evidence import KnowledgeEvidenceRepository
from app.repositories.retrieval import RetrievalRepository
from app.runtime.budget import BudgetLimits, ExecutionBudget
from app.runtime.context import build_run_context
from app.runtime.executor import HarnessExecutor
from app.runtime.permissions import PermissionGuard
from app.runtime.trace import TraceRecorder
from app.schemas.auth import CurrentUser
from app.schemas.common import ToolEnvelope
from app.schemas.knowledge import SearchKnowledgeInput, SearchKnowledgeResult
from app.schemas.retrieval import RetrievalRequest
from app.services.documents.chunking.token_counting import UnicodeMixedTokenCounter
from app.services.evidence import EvidenceService, EvidenceWriteContext
from app.services.knowledge import KnowledgeSearchOutcome, KnowledgeSearchService
from app.services.retrieval import FakeEmbeddingProvider, FakeRerankerProvider
from app.services.retrieval.context import ContextBuilderService
from app.services.retrieval.dense import DenseRetrievalService
from app.services.retrieval.errors import (
    RetrievalDatabaseTimeoutError,
    RetrievalDatabaseUnavailableError,
    RetrievalEmbeddingProviderUnavailableError,
    RetrievalRerankerProviderUnavailableError,
)
from app.services.retrieval.hybrid import HybridRetrievalService
from app.services.retrieval.lexical import LexicalRetrievalService
from app.services.retrieval.reranker import RerankerRetrievalService
from app.tools.registry import create_m2_tool_registry
from app.tools.search_knowledge import SearchKnowledgeTool
from tests.integration.test_agent_tools import (
    AgentToolFixture,
    load_calls,
)
from tests.integration.test_dense_retrieval import FixedQueryProvider, _identity_hash
from tests.integration.test_knowledge_evidence_service import (
    _FailingKnowledgeEvidenceRepository,
    _FailingToolContextRepository,
)
from tests.integration.test_knowledge_search_service import AfterRetrieveRoute
from tests.integration.test_retrieval_repository_scope import RetrievalScopeFixture
from tests.unit.test_context_builder import FakeContextReader, _response
from tests.unit.test_search_knowledge_contracts import context_bundle

pytest_plugins = (
    "tests.integration.test_agent_tools",
    "tests.integration.test_retrieval_repository_scope",
)


@pytest.fixture
def search_tool_fixture(
    agent_tool_fixture: AgentToolFixture,
) -> AgentToolFixture:
    try:
        yield agent_tool_fixture
    finally:
        agent_tool_fixture.business_session.rollback()
        with agent_tool_fixture.session_factory.begin() as cleanup:
            context_ids = select(ContextArtifact.id).where(
                ContextArtifact.tenant_id == agent_tool_fixture.context.tenant_id,
                ContextArtifact.requested_by_user_id
                == agent_tool_fixture.context.user_id,
            )
            cleanup.execute(
                delete(ToolContextLink).where(
                    ToolContextLink.tenant_id == agent_tool_fixture.context.tenant_id,
                    ToolContextLink.context_artifact_id.in_(context_ids),
                )
            )
            cleanup.execute(
                delete(ContextArtifact).where(
                    ContextArtifact.tenant_id == agent_tool_fixture.context.tenant_id,
                    ContextArtifact.requested_by_user_id
                    == agent_tool_fixture.context.user_id,
                )
            )


def _current_user(fixture: AgentToolFixture) -> CurrentUser:
    return CurrentUser(
        user_id=fixture.context.user_id,
        tenant_id=fixture.context.tenant_id,
        email="de.operator@demo.deepsearch.local",
        display_name="德国站运营",
        roles=list(fixture.context.roles),
        market_scopes=list(fixture.context.market_scopes),
        synthetic_data=True,
    )


def _harness(
    fixture: AgentToolFixture,
    run: object,
    *,
    context: object | None = None,
    budget: ExecutionBudget | None = None,
) -> HarnessExecutor:
    from app.runtime.context import RunContext
    from app.runtime.trace import RunTrace

    assert isinstance(run, RunTrace)
    registry = create_m2_tool_registry()
    trusted_context = context or fixture.context
    assert isinstance(trusted_context, RunContext)
    return HarnessExecutor(
        context=trusted_context,
        run=run,
        budget=budget
        or ExecutionBudget(
            BudgetLimits(
                max_model_calls=2,
                max_tool_calls=2,
                max_repeat_tool_calls=1,
                total_timeout_ms=20_000,
            )
        ),
        registry=registry,
        permission_guard=PermissionGuard(registry),
        trace_recorder=fixture.recorder,
    )


class UnsupportedPersistingService:
    def __init__(self, evidence_service: EvidenceService) -> None:
        self._evidence_service = evidence_service

    def search(
        self,
        current_user: CurrentUser,
        request: SearchKnowledgeInput,
        *,
        runtime_context: EvidenceWriteContext | None = None,
    ) -> KnowledgeSearchOutcome:
        built = ContextBuilderService(
            FakeContextReader(),
            neighbor_window=0,
        ).build(
            current_user,
            RetrievalRequest(query=request.query),
            _response(),
        )
        persisted = self._evidence_service.persist_document_context(
            current_user,
            built,
            runtime_context=runtime_context,
        )
        return KnowledgeSearchOutcome(
            result=SearchKnowledgeResult(context=persisted.bundle),
            reused=persisted.reused,
        )


@dataclass(slots=True)
class ControlledService:
    outcome: KnowledgeSearchOutcome
    failure: ApplicationError | None = None
    advance: object | None = None
    calls: int = 0

    def search(self, *_args: object, **_kwargs: object) -> KnowledgeSearchOutcome:
        self.calls += 1
        if callable(self.advance):
            self.advance()
        if self.failure is not None:
            raise self.failure
        return self.outcome


def _unsupported_outcome() -> KnowledgeSearchOutcome:
    return KnowledgeSearchOutcome(
        result=SearchKnowledgeResult(context=context_bundle(0)),
        reused=False,
    )


def _load_link(
    fixture: AgentToolFixture,
    tool_call_id: UUID,
) -> ToolContextLink | None:
    with fixture.session_factory() as session:
        link = session.scalar(
            select(ToolContextLink).where(
                ToolContextLink.tenant_id == fixture.context.tenant_id,
                ToolContextLink.tool_call_id == tool_call_id,
            )
        )
        if link is not None:
            session.expunge(link)
        return link


def test_real_harness_persists_success_trace_and_tool_context_link(
    search_tool_fixture: AgentToolFixture,
) -> None:
    fixture = search_tool_fixture
    user = _current_user(fixture)
    with fixture.recorder.run_scope(fixture.context, "knowledge_query") as run:
        tool = SearchKnowledgeTool(
            _harness(fixture, run),
            cast(
                KnowledgeSearchService,
                UnsupportedPersistingService(EvidenceService(fixture.business_session)),
            ),
            user,
        )
        envelope = tool.invoke(SearchKnowledgeInput(query="没有获权资料的问题"))
        fixture.business_session.commit()

    calls = load_calls(fixture, run.id)
    assert envelope.status == "success", envelope.model_dump()
    assert envelope.data is not None
    assert envelope.data.context.supported is False
    assert envelope.evidence_ids == []
    assert [(call.permission_result, call.status) for call in calls] == [
        ("allowed", "success")
    ]
    link = _load_link(fixture, calls[0].id)
    assert link is not None
    assert link.agent_run_id == run.id
    assert link.context_artifact_id == envelope.data.context.context_id


def test_role_denial_is_traced_before_knowledge_service(
    search_tool_fixture: AgentToolFixture,
) -> None:
    fixture = search_tool_fixture
    service = ControlledService(_unsupported_outcome())
    denied_context = replace(fixture.context, roles=())
    with fixture.recorder.run_scope(denied_context, "knowledge_query") as run:
        envelope = SearchKnowledgeTool(
            _harness(fixture, run, context=denied_context),
            cast(KnowledgeSearchService, service),
            _current_user(fixture),
        ).invoke(SearchKnowledgeInput(query="角色拒绝"))

    calls = load_calls(fixture, run.id)
    assert envelope.status == "error"
    assert envelope.error is not None
    assert envelope.error.code == "FORBIDDEN"
    assert service.calls == 0
    assert [(call.permission_result, call.status) for call in calls] == [
        ("denied", "denied")
    ]


def test_bound_tenant_mismatch_is_traced_without_retrieval(
    search_tool_fixture: AgentToolFixture,
) -> None:
    fixture = search_tool_fixture
    service = ControlledService(_unsupported_outcome())
    user = _current_user(fixture).model_copy(update={"tenant_id": uuid4()})
    with fixture.recorder.run_scope(fixture.context, "knowledge_query") as run:
        envelope = SearchKnowledgeTool(
            _harness(fixture, run),
            cast(KnowledgeSearchService, service),
            user,
        ).invoke(SearchKnowledgeInput(query="租户拒绝"))

    calls = load_calls(fixture, run.id)
    assert envelope.status == "error"
    assert envelope.error is not None
    assert envelope.error.code == "FORBIDDEN"
    assert envelope.error.field == "tenant_id"
    assert service.calls == 0
    assert [(call.permission_result, call.status) for call in calls] == [
        ("allowed", "error")
    ]


def test_repeated_knowledge_call_is_denied_without_second_service_execution(
    search_tool_fixture: AgentToolFixture,
) -> None:
    fixture = search_tool_fixture
    service = ControlledService(_unsupported_outcome())
    request = SearchKnowledgeInput(query="重复问题")
    with fixture.recorder.run_scope(fixture.context, "knowledge_query") as run:
        tool = SearchKnowledgeTool(
            _harness(fixture, run),
            cast(KnowledgeSearchService, service),
            _current_user(fixture),
        )
        first = tool.invoke(request)
        second = tool.invoke(request)

    calls = load_calls(fixture, run.id)
    assert first.status == "success"
    assert second.status == "error"
    assert second.error is not None
    assert second.error.code == "BUDGET_EXCEEDED"
    assert service.calls == 1
    assert [call.status for call in calls] == ["success", "denied"]


@dataclass(slots=True)
class ManualClock:
    value: float = 100.0

    def monotonic(self) -> float:
        return self.value

    def advance_past_tool_limit(self) -> None:
        self.value += 8.001


def test_knowledge_tool_timeout_returns_error_and_traces_timeout(
    search_tool_fixture: AgentToolFixture,
) -> None:
    fixture = search_tool_fixture
    clock = ManualClock()
    service = ControlledService(
        _unsupported_outcome(),
        advance=clock.advance_past_tool_limit,
    )
    budget = ExecutionBudget(
        BudgetLimits(
            max_model_calls=2,
            max_tool_calls=2,
            max_repeat_tool_calls=1,
            total_timeout_ms=20_000,
        ),
        clock.monotonic,
    )
    with fixture.recorder.run_scope(fixture.context, "knowledge_query") as run:
        envelope = SearchKnowledgeTool(
            _harness(fixture, run, budget=budget),
            cast(KnowledgeSearchService, service),
            _current_user(fixture),
        ).invoke(SearchKnowledgeInput(query="超时问题"))

    calls = load_calls(fixture, run.id)
    assert envelope.status == "error"
    assert envelope.error is not None
    assert envelope.error.code == "BUDGET_EXCEEDED"
    assert calls[0].status == "timeout"
    assert calls[0].error_code == "BUDGET_EXCEEDED"


def test_total_deadline_denies_knowledge_tool_before_service(
    search_tool_fixture: AgentToolFixture,
) -> None:
    fixture = search_tool_fixture
    clock = ManualClock()
    service = ControlledService(_unsupported_outcome())
    budget = ExecutionBudget(
        BudgetLimits(
            max_model_calls=2,
            max_tool_calls=2,
            max_repeat_tool_calls=1,
            total_timeout_ms=8_000,
        ),
        clock.monotonic,
    )
    clock.advance_past_tool_limit()

    with fixture.recorder.run_scope(fixture.context, "knowledge_query") as run:
        envelope = SearchKnowledgeTool(
            _harness(fixture, run, budget=budget),
            cast(KnowledgeSearchService, service),
            _current_user(fixture),
        ).invoke(SearchKnowledgeInput(query="总时限问题"))

    calls = load_calls(fixture, run.id)
    assert envelope.status == "error"
    assert envelope.error is not None
    assert envelope.error.code == "BUDGET_EXCEEDED"
    assert service.calls == 0
    assert [(call.permission_result, call.status) for call in calls] == [
        ("denied", "timeout")
    ]


@pytest.mark.parametrize(
    ("failure", "expected_status", "expected_code"),
    (
        (RetrievalEmbeddingProviderUnavailableError(), "error", "PROVIDER_ERROR"),
        (RetrievalRerankerProviderUnavailableError(), "error", "PROVIDER_ERROR"),
        (RetrievalDatabaseUnavailableError(), "error", "DATABASE_UNAVAILABLE"),
        (RetrievalDatabaseTimeoutError(), "timeout", "DATABASE_TIMEOUT"),
    ),
)
def test_provider_and_database_errors_keep_safe_envelope_and_trace_status(
    search_tool_fixture: AgentToolFixture,
    failure: ApplicationError,
    expected_status: str,
    expected_code: str,
) -> None:
    fixture = search_tool_fixture
    service = ControlledService(_unsupported_outcome(), failure=failure)
    with fixture.recorder.run_scope(fixture.context, "knowledge_query") as run:
        envelope = SearchKnowledgeTool(
            _harness(fixture, run),
            cast(KnowledgeSearchService, service),
            _current_user(fixture),
        ).invoke(SearchKnowledgeInput(query=f"故障-{expected_code}"))

    calls: list[ToolCall] = load_calls(fixture, run.id)
    assert envelope.status == "error"
    assert envelope.data is None
    assert envelope.evidence_ids == []
    assert envelope.error is not None
    assert envelope.error.code == expected_code
    assert calls[0].status == expected_status
    assert calls[0].error_code == expected_code


@pytest.fixture
def committed_retrieval_scope(
    retrieval_scope_fixture: RetrievalScopeFixture,
) -> RetrievalScopeFixture:
    """Commit only this synthetic fixture so independent Trace sessions can see it."""

    fixture = retrieval_scope_fixture
    tenant_ids = tuple({user.tenant_id for user in fixture.users.values()})
    identity = FakeEmbeddingProvider().identity
    active_index_ids = select(DocumentVersion.active_index_set_id).where(
        DocumentVersion.tenant_id.in_(tenant_ids),
        DocumentVersion.active_index_set_id.is_not(None),
    )
    for index_set in fixture.session.scalars(
        select(DocumentIndexSet).where(DocumentIndexSet.id.in_(active_index_ids))
    ):
        index_set.embedding_identity_json = asdict(identity)
        index_set.embedding_identity_sha256 = _identity_hash(identity)
    for chunk in fixture.session.scalars(
        select(DocumentChunk).where(DocumentChunk.tenant_id.in_(tenant_ids))
    ):
        chunk.page_numbers = [1]
        chunk.source_spans = [
            {
                "block_id": "b000001",
                "start_locator": {"page_number": 1, "block_number": 1},
                "end_locator": {"page_number": 1, "block_number": 1},
                "character_start": 0,
                "character_end": len(chunk.body_text),
                "bounding_boxes": [],
            }
        ]
    fixture.session.commit()
    try:
        yield fixture
    finally:
        fixture.session.rollback()
        with fixture.runtime.session_factory.begin() as cleanup:
            cleanup.execute(delete(Thread).where(Thread.tenant_id.in_(tenant_ids)))
            cleanup.execute(
                delete(ToolContextLink).where(ToolContextLink.tenant_id.in_(tenant_ids))
            )
            cleanup.execute(delete(Evidence).where(Evidence.tenant_id.in_(tenant_ids)))
            cleanup.execute(
                delete(ContextArtifact).where(ContextArtifact.tenant_id.in_(tenant_ids))
            )
            cleanup.execute(delete(Document).where(Document.tenant_id.in_(tenant_ids)))
            cleanup.execute(delete(Tenant).where(Tenant.id.in_(tenant_ids)))


def _matrix_reranker(fixture: RetrievalScopeFixture) -> RerankerRetrievalService:
    repository = RetrievalRepository(fixture.session, statement_timeout_ms=2_000)
    provider = FixedQueryProvider(
        FakeEmbeddingProvider().identity,
        (1.0,) + (0.0,) * 1023,
    )
    hybrid = HybridRetrievalService(
        DenseRetrievalService(repository, provider, candidate_count=10),
        LexicalRetrievalService(repository, candidate_count=10),
        rrf_k=60,
        candidate_count=10,
    )
    return RerankerRetrievalService(hybrid, FakeRerankerProvider(), top_k=8)


def _matrix_service(
    fixture: RetrievalScopeFixture,
    *,
    reranker: object | None = None,
    knowledge_repository: KnowledgeEvidenceRepository | None = None,
) -> KnowledgeSearchService:
    counter = UnicodeMixedTokenCounter()
    for chunk in fixture.session.scalars(
        select(DocumentChunk).where(
            DocumentChunk.tenant_id == fixture.users["reader"].tenant_id
        )
    ):
        chunk.token_count = counter.count(chunk.body_text) + 10
    fixture.session.flush()
    repository = RetrievalRepository(fixture.session, statement_timeout_ms=2_000)
    return KnowledgeSearchService(
        cast(RerankerRetrievalService, reranker or _matrix_reranker(fixture)),
        ContextBuilderService(repository, neighbor_window=0),
        EvidenceService(
            fixture.session,
            knowledge_repository=knowledge_repository,
        ),
    )


def _invoke_matrix_tool(
    fixture: RetrievalScopeFixture,
    user: CurrentUser,
    query: str,
    *,
    service_factory: object | None = None,
) -> tuple[ToolEnvelope[SearchKnowledgeResult], ToolCall]:
    thread = Thread(
        id=uuid4(),
        tenant_id=user.tenant_id,
        user_id=user.user_id,
        title="M2-19.5 Tool matrix",
    )
    fixture.session.add(thread)
    fixture.session.commit()
    context = build_run_context(user, thread.id, trace_id=uuid4())
    recorder = TraceRecorder(fixture.runtime.session_factory)
    service = (
        service_factory() if callable(service_factory) else _matrix_service(fixture)
    )
    registry = create_m2_tool_registry()
    with recorder.run_scope(context, "knowledge_query") as run:
        harness = HarnessExecutor(
            context=context,
            run=run,
            budget=ExecutionBudget(
                BudgetLimits(
                    max_model_calls=2,
                    max_tool_calls=2,
                    max_repeat_tool_calls=1,
                    total_timeout_ms=20_000,
                )
            ),
            registry=registry,
            permission_guard=PermissionGuard(registry),
            trace_recorder=recorder,
        )
        envelope = SearchKnowledgeTool(harness, service, user).invoke(
            SearchKnowledgeInput(query=query)
        )
        fixture.session.commit()

    with fixture.runtime.session_factory() as audit_session:
        call = audit_session.scalar(
            select(ToolCall).where(ToolCall.agent_run_id == run.id)
        )
        assert call is not None
        audit_session.expunge(call)
    return envelope, call


@pytest.mark.parametrize(
    ("user_label", "query", "expected_chunk"),
    (
        ("reader", "owner候选内容", "owner"),
        ("reader", "user_acl候选内容", "user_acl"),
        ("reader", "role_acl候选内容", "role_acl"),
        ("reader", "market_acl候选内容", "market_acl"),
        ("owner", "no_acl候选内容", "no_acl"),
        ("company_owner", "no_acl候选内容", "no_acl"),
    ),
)
def test_formal_tool_honors_owner_company_owner_and_each_acl_subject(
    committed_retrieval_scope: RetrievalScopeFixture,
    user_label: str,
    query: str,
    expected_chunk: str,
) -> None:
    fixture = committed_retrieval_scope

    envelope, call = _invoke_matrix_tool(
        fixture,
        fixture.users[user_label],
        query,
    )

    assert envelope.status == "success", envelope.model_dump()
    assert envelope.data is not None
    returned_chunks = {
        segment.identity.chunk_id for segment in envelope.data.context.segments
    }
    assert fixture.expected[expected_chunk] in returned_chunks
    assert envelope.evidence_ids == [
        segment.evidence_id for segment in envelope.data.context.segments
    ]
    assert call.status == "success"


def test_formal_tool_never_exposes_cross_tenant_stale_or_deleted_chunks(
    committed_retrieval_scope: RetrievalScopeFixture,
) -> None:
    fixture = committed_retrieval_scope

    envelope, call = _invoke_matrix_tool(
        fixture,
        fixture.users["company_owner"],
        "候选内容",
    )

    assert envelope.status == "success"
    assert envelope.data is not None
    returned_chunks = {
        segment.identity.chunk_id for segment in envelope.data.context.segments
    }
    excluded = {
        fixture.expected[label]
        for label in (
            "cross_tenant",
            "old_version",
            "old_index_set",
            "pending_index_set",
            "failed_index_set",
            "soft_deleted_document",
            "soft_deleted_file",
        )
    }
    assert returned_chunks.isdisjoint(excluded)
    assert call.status == "success"


def test_two_tool_calls_reuse_context_and_evidence_but_keep_distinct_links(
    committed_retrieval_scope: RetrievalScopeFixture,
) -> None:
    fixture = committed_retrieval_scope
    user = fixture.users["reader"]

    first, first_call = _invoke_matrix_tool(fixture, user, "owner候选内容")
    second, second_call = _invoke_matrix_tool(fixture, user, "owner候选内容")

    assert first.status == second.status == "success"
    assert first.data is not None and second.data is not None
    assert first.data.context == second.data.context
    assert first.evidence_ids == second.evidence_ids
    assert first_call.id != second_call.id
    tenant_id = user.tenant_id
    assert (
        fixture.session.scalar(
            select(func.count())
            .select_from(ContextArtifact)
            .where(ContextArtifact.tenant_id == tenant_id)
        )
        == 1
    )
    assert fixture.session.scalar(
        select(func.count())
        .select_from(Evidence)
        .where(Evidence.tenant_id == tenant_id)
    ) == len(first.evidence_ids)
    assert (
        fixture.session.scalar(
            select(func.count())
            .select_from(ToolContextLink)
            .where(ToolContextLink.tenant_id == tenant_id)
        )
        == 2
    )


def test_acl_revocation_between_reranker_and_context_returns_no_partial_rows(
    committed_retrieval_scope: RetrievalScopeFixture,
) -> None:
    fixture = committed_retrieval_scope
    target_chunk_id = fixture.expected["user_acl"]

    def service_factory() -> KnowledgeSearchService:
        base = _matrix_reranker(fixture)

        def revoke(response: object) -> None:
            assert target_chunk_id in {
                item.identity.chunk_id
                for item in response.results  # type: ignore[attr-defined]
            }
            document_id = fixture.session.get(
                DocumentChunk, target_chunk_id
            ).document_id  # type: ignore[union-attr]
            fixture.session.execute(
                delete(DocumentAcl).where(DocumentAcl.document_id == document_id)
            )
            fixture.session.flush()

        return _matrix_service(
            fixture,
            reranker=AfterRetrieveRoute(base, revoke),
        )

    envelope, call = _invoke_matrix_tool(
        fixture,
        fixture.users["reader"],
        "user_acl候选内容",
        service_factory=service_factory,
    )

    assert envelope.status == "error"
    assert envelope.data is None
    assert envelope.evidence_ids == []
    assert call.status == "error"
    tenant_id = fixture.users["reader"].tenant_id
    for model in (ContextArtifact, Evidence, ToolContextLink):
        assert (
            fixture.session.scalar(
                select(func.count())
                .select_from(model)
                .where(model.tenant_id == tenant_id)
            )
            == 0
        )


@pytest.mark.parametrize(
    "repository_type",
    (_FailingKnowledgeEvidenceRepository, _FailingToolContextRepository),
)
def test_context_evidence_or_link_failure_is_atomic_through_formal_tool(
    committed_retrieval_scope: RetrievalScopeFixture,
    repository_type: type[KnowledgeEvidenceRepository],
) -> None:
    fixture = committed_retrieval_scope

    envelope, call = _invoke_matrix_tool(
        fixture,
        fixture.users["reader"],
        "owner候选内容",
        service_factory=lambda: _matrix_service(
            fixture,
            knowledge_repository=repository_type(fixture.session),
        ),
    )

    assert envelope.status == "error"
    assert envelope.data is None
    assert envelope.evidence_ids == []
    assert call.status == "error"
    assert call.error_code == "INTERNAL_ERROR"
    tenant_id = fixture.users["reader"].tenant_id
    for model in (ContextArtifact, Evidence, ToolContextLink):
        assert (
            fixture.session.scalar(
                select(func.count())
                .select_from(model)
                .where(model.tenant_id == tenant_id)
            )
            == 0
        )

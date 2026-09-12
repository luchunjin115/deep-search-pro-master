from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import cast
from uuid import uuid4

import pytest

from app.core.errors import (
    ApplicationError,
    KnowledgeEvidencePersistenceError,
)
from app.core.rag_trace import RagReviewTrace, rag_review_trace
from app.schemas.auth import CurrentUser
from app.schemas.context import ContextBundle
from app.schemas.evidence import DocumentEvidenceDetail
from app.schemas.knowledge import SearchKnowledgeInput
from app.schemas.retrieval import RerankedRetrievalResponse, RetrievalRequest
from app.services import (
    EvidenceWriteContext,
    KnowledgeSearchOutcome,
    KnowledgeSearchService,
    PersistedDocumentContext,
)
from app.services.retrieval.context import BuiltContext
from app.services.retrieval.errors import (
    ContextBuildError,
    ContextDataContractError,
    ContextInputError,
    RetrievalDatabaseTimeoutError,
    RetrievalDatabaseUnavailableError,
    RetrievalEmbeddingIdentityMismatchError,
    RetrievalEmbeddingProviderUnavailableError,
    RetrievalInputError,
    RetrievalInternalError,
    RetrievalRerankerProviderUnavailableError,
)
from tests.unit.test_context_builder import _response
from tests.unit.test_search_knowledge_contracts import context_bundle


def _user() -> CurrentUser:
    return CurrentUser(
        user_id=uuid4(),
        tenant_id=uuid4(),
        email="knowledge-service@example.com",
        display_name="Knowledge service reader",
        roles=["amazon_operator"],
        market_scopes=["DE"],
        synthetic_data=True,
    )


def _built(bundle: ContextBundle) -> BuiltContext:
    return BuiltContext(
        bundle=bundle,
        sources=(),
        retrieval_snapshot={},
        retrieval_snapshot_sha256="c" * 64,
        config={},
        config_sha256="d" * 64,
        identity_sha256="e" * 64,
    )


def _persisted(
    bundle: ContextBundle,
    *,
    reused: bool = False,
) -> PersistedDocumentContext:
    now = datetime(2026, 9, 2, 12, 0, tzinfo=UTC)
    evidences = tuple(
        DocumentEvidenceDetail(
            id=segment.evidence_id,
            source_type=segment.source_type,
            title=segment.document.title,
            excerpt=segment.text,
            observed_at=now,
            context_id=bundle.context_id,
            citation_label=segment.citation_label,
            identity=segment.identity,
            document=segment.document,
            source_locator=segment.source_locator,
            source_content_sha256="f" * 64,
            context_text_sha256=segment.text_sha256,
            trust_level="document_snapshot",
            synthetic_data=True,
            created_at=now,
        )
        for segment in bundle.segments
    )
    return PersistedDocumentContext(
        bundle=bundle,
        evidences=evidences,
        reused=reused,
    )


@dataclass(slots=True)
class FakeRerankerRoute:
    response: object
    events: list[tuple[str, object, object]]
    failure: ApplicationError | None = None

    def retrieve(
        self,
        current_user: CurrentUser,
        request: RetrievalRequest,
    ) -> RerankedRetrievalResponse:
        self.events.append(("reranker", current_user, request))
        if self.failure is not None:
            raise self.failure
        return cast(RerankedRetrievalResponse, self.response)


@dataclass(slots=True)
class FakeContextBuilder:
    response: object
    events: list[tuple[str, object, object]]
    failure: ApplicationError | None = None

    def build(
        self,
        current_user: CurrentUser,
        request: RetrievalRequest,
        response: RerankedRetrievalResponse,
    ) -> BuiltContext:
        self.events.append(("context", current_user, request, response))
        if self.failure is not None:
            raise self.failure
        return cast(BuiltContext, self.response)


@dataclass(slots=True)
class FakeEvidenceWriter:
    response: object
    events: list[tuple[str, object, object]]
    failure: ApplicationError | None = None
    runtime_contexts: list[EvidenceWriteContext | None] = field(default_factory=list)

    def persist_document_context(
        self,
        current_user: CurrentUser,
        built: BuiltContext,
        *,
        runtime_context: EvidenceWriteContext | None = None,
    ) -> PersistedDocumentContext:
        self.events.append(("evidence", current_user, built))
        self.runtime_contexts.append(runtime_context)
        if self.failure is not None:
            raise self.failure
        return cast(PersistedDocumentContext, self.response)


def _service(
    *,
    reranked: object,
    built: object,
    persisted: object,
    events: list[tuple[str, object, object]] | None = None,
) -> tuple[
    KnowledgeSearchService,
    FakeRerankerRoute,
    FakeContextBuilder,
    FakeEvidenceWriter,
]:
    observed = events if events is not None else []
    reranker = FakeRerankerRoute(reranked, observed)
    builder = FakeContextBuilder(built, observed)
    evidence = FakeEvidenceWriter(persisted, observed)
    return (
        KnowledgeSearchService(reranker, builder, evidence),
        reranker,
        builder,
        evidence,
    )


def test_orchestrates_one_trusted_request_in_fixed_order_with_aligned_evidence() -> (
    None
):
    events: list[tuple[str, object, object]] = []
    user = _user()
    request = SearchKnowledgeInput(query="  蘑菇灯如何调节亮度？  ")
    reranked = _response()
    bundle = context_bundle(2)
    built = _built(bundle)
    persisted = _persisted(bundle, reused=True)
    runtime_context = EvidenceWriteContext(
        tenant_id=user.tenant_id,
        agent_run_id=uuid4(),
        tool_call_id=uuid4(),
    )
    service, _reranker, _builder, evidence = _service(
        reranked=reranked,
        built=built,
        persisted=persisted,
        events=events,
    )

    trace = RagReviewTrace()
    with rag_review_trace(trace):
        outcome = service.search(user, request, runtime_context=runtime_context)
    assert trace.context == bundle.model_dump(mode="json")

    assert isinstance(outcome, KnowledgeSearchOutcome)
    assert [event[0] for event in events] == ["reranker", "context", "evidence"]
    assert all(event[1] is user for event in events)
    retrieval_request = cast(RetrievalRequest, events[0][2])
    assert retrieval_request.query == "蘑菇灯如何调节亮度？"
    assert events[1][2] is retrieval_request
    assert outcome.result.context == bundle
    assert outcome.evidence_ids == tuple(
        segment.evidence_id for segment in bundle.segments
    )
    assert outcome.reused is True
    assert evidence.runtime_contexts == [runtime_context]


def test_unsupported_context_is_a_successful_empty_persisted_result() -> None:
    user = _user()
    bundle = context_bundle(0)
    service, _reranker, _builder, evidence = _service(
        reranked=_response(),
        built=_built(bundle),
        persisted=_persisted(bundle),
    )

    outcome = service.search(
        user,
        SearchKnowledgeInput(query="当前没有资料的问题"),
    )

    assert outcome.result.context.supported is False
    assert outcome.result.context.segments == []
    assert outcome.evidence_ids == ()
    assert evidence.runtime_contexts == [None]


@pytest.mark.parametrize(
    ("reranked", "built", "persisted", "expected_error"),
    (
        (
            object(),
            _built(context_bundle(0)),
            _persisted(context_bundle(0)),
            RetrievalInternalError,
        ),
        (
            _response(),
            object(),
            _persisted(context_bundle(0)),
            ContextDataContractError,
        ),
        (
            _response(),
            _built(context_bundle(0)),
            object(),
            KnowledgeEvidencePersistenceError,
        ),
    ),
)
def test_rejects_downstream_type_tampering_at_the_owning_boundary(
    reranked: object,
    built: object,
    persisted: object,
    expected_error: type[ApplicationError],
) -> None:
    service, _reranker, _builder, _evidence = _service(
        reranked=reranked,
        built=built,
        persisted=persisted,
    )

    with pytest.raises(expected_error):
        service.search(_user(), SearchKnowledgeInput(query="类型边界"))


def test_rejects_persisted_bundle_or_evidence_misalignment() -> None:
    bundle = context_bundle(2)
    mismatched = context_bundle(1)
    service, _reranker, _builder, _evidence = _service(
        reranked=_response(),
        built=_built(bundle),
        persisted=_persisted(mismatched),
    )

    with pytest.raises(KnowledgeEvidencePersistenceError):
        service.search(_user(), SearchKnowledgeInput(query="对齐边界"))


_PIPELINE_ERRORS: tuple[tuple[str, ApplicationError], ...] = (
    ("reranker", RetrievalInputError()),
    ("reranker", RetrievalEmbeddingProviderUnavailableError()),
    ("reranker", RetrievalEmbeddingIdentityMismatchError()),
    ("reranker", RetrievalRerankerProviderUnavailableError()),
    ("reranker", RetrievalDatabaseUnavailableError()),
    ("reranker", RetrievalDatabaseTimeoutError()),
    ("reranker", RetrievalInternalError()),
    ("context", ContextInputError()),
    ("context", ContextDataContractError()),
    ("context", ContextBuildError()),
    ("evidence", KnowledgeEvidencePersistenceError()),
)


@pytest.mark.parametrize(("stage", "failure"), _PIPELINE_ERRORS)
def test_preserves_known_application_errors_without_rewrapping(
    stage: str,
    failure: ApplicationError,
) -> None:
    bundle = context_bundle(0)
    service, reranker, builder, evidence = _service(
        reranked=_response(),
        built=_built(bundle),
        persisted=_persisted(bundle),
    )
    if stage == "reranker":
        reranker.failure = failure
    elif stage == "context":
        builder.failure = failure
    else:
        evidence.failure = failure

    with pytest.raises(type(failure)) as captured:
        service.search(_user(), SearchKnowledgeInput(query="错误透传"))

    assert captured.value is failure


@pytest.mark.parametrize(
    ("user", "search_request"),
    (
        ({"tenant_id": str(uuid4())}, SearchKnowledgeInput(query="伪造用户")),
        (_user(), RetrievalRequest(query="错误请求类型")),
    ),
)
def test_requires_trusted_current_user_and_search_contract(
    user: object,
    search_request: object,
) -> None:
    bundle = context_bundle(0)
    service, _reranker, _builder, _evidence = _service(
        reranked=_response(),
        built=_built(bundle),
        persisted=_persisted(bundle),
    )

    with pytest.raises(RetrievalInputError):
        service.search(  # type: ignore[arg-type]
            user,
            search_request,
        )

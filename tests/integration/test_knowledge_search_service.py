from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import cast
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.exc import SQLAlchemyError

from app.core.errors import KnowledgeEvidencePersistenceError
from app.models.identity import User
from app.models.knowledge import (
    Document,
    DocumentAcl,
    DocumentChunk,
    DocumentIndexSet,
    DocumentVersion,
)
from app.models.runtime import (
    AgentRun,
    ContextArtifact,
    Evidence,
    Thread,
    ToolCall,
    ToolContextLink,
)
from app.repositories.evidence import KnowledgeEvidenceRepository
from app.repositories.retrieval import RetrievalRepository
from app.schemas.auth import CurrentUser
from app.schemas.knowledge import SearchKnowledgeInput
from app.schemas.retrieval import RerankedRetrievalResponse, RetrievalRequest
from app.services.documents.chunking.token_counting import UnicodeMixedTokenCounter
from app.services.evidence import EvidenceService, EvidenceWriteContext
from app.services.knowledge import KnowledgeSearchOutcome, KnowledgeSearchService
from app.services.retrieval import FakeEmbeddingProvider, FakeRerankerProvider
from app.services.retrieval.context import ContextBuilderService
from app.services.retrieval.dense import DenseRetrievalService
from app.services.retrieval.errors import ContextInputError
from app.services.retrieval.hybrid import HybridRetrievalService
from app.services.retrieval.lexical import LexicalRetrievalService
from app.services.retrieval.reranker import RerankerRetrievalService
from tests.integration import test_lexical_retrieval as lexical_test_support
from tests.integration.test_dense_retrieval import FixedQueryProvider
from tests.integration.test_lexical_retrieval import LexicalFixture

lexical_fixture = lexical_test_support.lexical_fixture


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _reranker(fixture: LexicalFixture) -> RerankerRetrievalService:
    repository = RetrievalRepository(fixture.session, statement_timeout_ms=2000)
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


def _service(
    fixture: LexicalFixture,
    *,
    reranker: object | None = None,
    evidence_service: EvidenceService | None = None,
) -> KnowledgeSearchService:
    counter = UnicodeMixedTokenCounter()
    for chunk in fixture.session.scalars(
        select(DocumentChunk).where(DocumentChunk.tenant_id == fixture.reader.tenant_id)
    ):
        chunk.token_count = counter.count(chunk.body_text) + 10
    fixture.session.flush()
    repository = RetrievalRepository(fixture.session, statement_timeout_ms=2000)
    return KnowledgeSearchService(
        cast(RerankerRetrievalService, reranker or _reranker(fixture)),
        ContextBuilderService(repository, neighbor_window=0),
        evidence_service or EvidenceService(fixture.session),
    )


def _runtime_context(fixture: LexicalFixture) -> EvidenceWriteContext:
    thread = Thread(
        id=uuid4(),
        tenant_id=fixture.reader.tenant_id,
        user_id=fixture.reader.user_id,
        title="M2-19.3 integration",
    )
    run = AgentRun(
        id=uuid4(),
        tenant_id=fixture.reader.tenant_id,
        thread_id=thread.id,
        user_id=fixture.reader.user_id,
        trace_id=uuid4(),
        route="knowledge_query",
        status="running",
        model_call_count=1,
        tool_call_count=1,
    )
    tool_call = ToolCall(
        id=uuid4(),
        tenant_id=fixture.reader.tenant_id,
        agent_run_id=run.id,
        sequence_no=1,
        tool_name="search_knowledge",
        tool_version="1.0.0",
        arguments_summary={"query": "亮度"},
        permission_result="allowed",
        status="running",
    )
    fixture.session.add_all([thread, run, tool_call])
    fixture.session.flush()
    return EvidenceWriteContext(
        tenant_id=fixture.reader.tenant_id,
        agent_run_id=run.id,
        tool_call_id=tool_call.id,
    )


def _tenant_count(fixture: LexicalFixture, model: type[object]) -> int:
    return int(
        fixture.session.scalar(
            select(func.count())
            .select_from(model)
            .where(model.tenant_id == fixture.reader.tenant_id)  # type: ignore[attr-defined]
        )
        or 0
    )


@dataclass(slots=True)
class AfterRetrieveRoute:
    inner: RerankerRetrievalService
    after: Callable[[RerankedRetrievalResponse], None]

    def retrieve(
        self,
        current_user: CurrentUser,
        request: RetrievalRequest,
    ) -> RerankedRetrievalResponse:
        response = self.inner.retrieve(current_user, request)
        self.after(response)
        return response


class FailingEvidenceRepository(KnowledgeEvidenceRepository):
    def insert_document_evidences(
        self,
        values: list[dict[str, object]],
    ) -> None:
        del values
        raise SQLAlchemyError("private evidence write detail")


def test_real_chain_persists_aligned_context_evidence_and_tool_link(
    request: pytest.FixtureRequest,
) -> None:
    fixture = cast(LexicalFixture, request.getfixturevalue("lexical_fixture"))
    runtime_context = _runtime_context(fixture)
    service = _service(fixture)
    search_request = SearchKnowledgeInput(query="亮度")

    first = service.search(
        fixture.reader,
        search_request,
        runtime_context=runtime_context,
    )
    retry = service.search(
        fixture.reader,
        search_request,
        runtime_context=runtime_context,
    )

    assert isinstance(first, KnowledgeSearchOutcome)
    assert first.result.context.supported is True
    assert first.evidence_ids == tuple(
        item.evidence_id for item in first.result.context.segments
    )
    assert fixture.expected_ids["denied"] not in {
        item.identity.chunk_id for item in first.result.context.segments
    }
    assert first.reused is False
    assert retry.result == first.result
    assert retry.reused is True
    assert _tenant_count(fixture, ContextArtifact) == 1
    assert _tenant_count(fixture, Evidence) == len(first.evidence_ids)
    assert _tenant_count(fixture, ToolContextLink) == 1


def test_real_chain_persists_unsupported_context_for_user_without_acl(
    request: pytest.FixtureRequest,
) -> None:
    fixture = cast(LexicalFixture, request.getfixturevalue("lexical_fixture"))
    user = CurrentUser(
        user_id=uuid4(),
        tenant_id=fixture.reader.tenant_id,
        email="no-access@knowledge-service.example.com",
        display_name="No access reader",
        roles=["amazon_operator"],
        market_scopes=["DE"],
        synthetic_data=True,
    )
    fixture.session.add(
        User(
            id=user.user_id,
            tenant_id=user.tenant_id,
            email=user.email,
            display_name=user.display_name,
            password_hash="$argon2id$m2193-synthetic-only",
        )
    )
    fixture.session.flush()

    outcome = _service(fixture).search(
        user,
        SearchKnowledgeInput(query="亮度"),
    )

    assert outcome.result.context.supported is False
    assert outcome.evidence_ids == ()
    assert _tenant_count(fixture, ContextArtifact) == 1
    assert _tenant_count(fixture, Evidence) == 0
    assert _tenant_count(fixture, ToolContextLink) == 0


def test_acl_revocation_after_reranking_prevents_context_and_evidence(
    request: pytest.FixtureRequest,
) -> None:
    fixture = cast(LexicalFixture, request.getfixturevalue("lexical_fixture"))
    denied_owner = fixture.session.scalar(
        select(User).where(User.email == "denied@lexical.example.com")
    )
    assert denied_owner is not None
    owned_documents = list(
        fixture.session.scalars(
            select(Document).where(
                Document.tenant_id == fixture.reader.tenant_id,
                Document.owner_user_id == fixture.reader.user_id,
            )
        )
    )
    for document in owned_documents:
        document.owner_user_id = denied_owner.id
        fixture.session.add(
            DocumentAcl(
                id=uuid4(),
                tenant_id=document.tenant_id,
                document_id=document.id,
                subject_type="user",
                user_id=fixture.reader.user_id,
                permission="read",
            )
        )
    fixture.session.flush()

    def revoke(_response: RerankedRetrievalResponse) -> None:
        fixture.session.execute(
            delete(DocumentAcl).where(
                DocumentAcl.tenant_id == fixture.reader.tenant_id,
                DocumentAcl.user_id == fixture.reader.user_id,
            )
        )
        fixture.session.flush()

    route = AfterRetrieveRoute(_reranker(fixture), revoke)

    with pytest.raises(ContextInputError):
        _service(fixture, reranker=route).search(
            fixture.reader,
            SearchKnowledgeInput(query="亮度"),
        )

    assert _tenant_count(fixture, ContextArtifact) == 0
    assert _tenant_count(fixture, Evidence) == 0


def test_active_index_switch_after_reranking_rejects_stale_generation(
    request: pytest.FixtureRequest,
) -> None:
    fixture = cast(LexicalFixture, request.getfixturevalue("lexical_fixture"))

    def switch(response: RerankedRetrievalResponse) -> None:
        stale = response.results[0]
        version = fixture.session.get(DocumentVersion, stale.identity.version_id)
        current = fixture.session.get(DocumentIndexSet, stale.identity.index_set_id)
        assert version is not None
        assert current is not None
        replacement = DocumentIndexSet(
            id=uuid4(),
            tenant_id=current.tenant_id,
            document_id=current.document_id,
            document_version_id=current.document_version_id,
            document_chunk_set_id=current.document_chunk_set_id,
            index_schema_version=current.index_schema_version,
            embedding_identity_json=(
                current.embedding_identity_json | {"revision": "m2-fake-v2"}
            ),
            embedding_identity_sha256=_sha256("m2-19.3 replacement identity"),
            embedding_model=current.embedding_model,
            embedding_version="m2-fake-v2",
            embedding_purpose=current.embedding_purpose,
            fts_builder_version=current.fts_builder_version,
            status="ready",
            attempt_count=1,
            chunk_count=current.chunk_count,
            text_chunk_count=current.text_chunk_count,
            table_chunk_count=current.table_chunk_count,
            total_token_count=current.total_token_count,
            created_at=current.created_at + timedelta(minutes=1),
            started_at=current.started_at + timedelta(minutes=1),  # type: ignore[operator]
            completed_at=current.completed_at + timedelta(minutes=1),  # type: ignore[operator]
        )
        fixture.session.add(replacement)
        fixture.session.flush()
        version.active_index_set_id = replacement.id
        fixture.session.flush()

    route = AfterRetrieveRoute(_reranker(fixture), switch)

    with pytest.raises(ContextInputError):
        _service(fixture, reranker=route).search(
            fixture.reader,
            SearchKnowledgeInput(query="亮度"),
        )

    assert _tenant_count(fixture, ContextArtifact) == 0
    assert _tenant_count(fixture, Evidence) == 0


def test_real_chain_rolls_back_context_when_evidence_write_fails(
    request: pytest.FixtureRequest,
) -> None:
    fixture = cast(LexicalFixture, request.getfixturevalue("lexical_fixture"))
    evidence = EvidenceService(
        fixture.session,
        knowledge_repository=FailingEvidenceRepository(fixture.session),
    )

    with pytest.raises(KnowledgeEvidencePersistenceError) as captured:
        _service(fixture, evidence_service=evidence).search(
            fixture.reader,
            SearchKnowledgeInput(query="亮度"),
        )

    assert "private" not in captured.value.to_detail().message
    assert _tenant_count(fixture, ContextArtifact) == 0
    assert _tenant_count(fixture, Evidence) == 0
    assert _tenant_count(fixture, ToolContextLink) == 0

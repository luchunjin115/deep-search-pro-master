from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from typing import cast
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from app.core.errors import KnowledgeEvidencePersistenceError
from app.models.knowledge import Document, DocumentChunk
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
from app.schemas.retrieval import RetrievalRequest
from app.services.evidence import EvidenceService, EvidenceWriteContext
from app.services.retrieval.context import BuiltContext, ContextBuilderService
from tests.integration import test_retrieval_repository_scope as scope_support
from tests.integration.test_context_retrieval_repository import _response_for_chunks
from tests.integration.test_retrieval_repository_scope import RetrievalScopeFixture

retrieval_scope_fixture = scope_support.retrieval_scope_fixture


def _build_one(
    fixture: RetrievalScopeFixture,
    query: str = "清洁前要做什么？",
) -> BuiltContext:
    anchor = fixture.session.get(DocumentChunk, fixture.expected["owner"])
    assert anchor is not None
    anchor.body_text = "清洁蘑菇灯前必须断开电源。"
    anchor.retrieval_text = anchor.body_text
    anchor.token_count = 20
    anchor.heading_path = ["维护", "清洁"]
    anchor.page_numbers = [2]
    anchor.source_spans = [
        {
            "block_id": "b000001",
            "start_locator": {"page_number": 2, "block_number": 1},
            "end_locator": {"page_number": 2, "block_number": 1},
            "character_start": 0,
            "character_end": len(anchor.body_text),
            "bounding_boxes": [],
        }
    ]
    fixture.session.flush()
    return ContextBuilderService(
        RetrievalRepository(fixture.session),
        neighbor_window=0,
    ).build(
        fixture.users["reader"],
        RetrievalRequest(query=query),
        _response_for_chunks(fixture, [anchor.id]),
    )


def _counts(fixture: RetrievalScopeFixture) -> tuple[int, int]:
    tenant_id = fixture.users["reader"].tenant_id
    return (
        fixture.session.scalar(
            select(func.count())
            .select_from(ContextArtifact)
            .where(ContextArtifact.tenant_id == tenant_id)
        )
        or 0,
        fixture.session.scalar(
            select(func.count())
            .select_from(Evidence)
            .where(Evidence.tenant_id == tenant_id)
        )
        or 0,
    )


def _link_count(fixture: RetrievalScopeFixture) -> int:
    tenant_id = fixture.users["reader"].tenant_id
    return (
        fixture.session.scalar(
            select(func.count())
            .select_from(ToolContextLink)
            .where(ToolContextLink.tenant_id == tenant_id)
        )
        or 0
    )


def _runtime_context(
    fixture: RetrievalScopeFixture,
    suffix: str,
) -> EvidenceWriteContext:
    user = fixture.users["reader"]
    thread = Thread(
        id=uuid4(),
        tenant_id=user.tenant_id,
        user_id=user.user_id,
        title=f"M2-19.2 {suffix}",
    )
    run = AgentRun(
        id=uuid4(),
        tenant_id=user.tenant_id,
        thread_id=thread.id,
        user_id=user.user_id,
        trace_id=uuid4(),
        route="knowledge_query",
        status="running",
        model_call_count=1,
        tool_call_count=1,
    )
    tool_call = ToolCall(
        id=uuid4(),
        tenant_id=user.tenant_id,
        agent_run_id=run.id,
        sequence_no=1,
        tool_name="search_knowledge",
        tool_version="1.0.0",
        arguments_summary={"query": suffix},
        permission_result="allowed",
        status="running",
    )
    fixture.session.add_all([thread, run, tool_call])
    fixture.session.flush()
    return EvidenceWriteContext(
        tenant_id=user.tenant_id,
        agent_run_id=run.id,
        tool_call_id=tool_call.id,
    )


def test_persists_context_and_document_evidence_atomically(
    request: pytest.FixtureRequest,
) -> None:
    fixture = cast(
        RetrievalScopeFixture,
        request.getfixturevalue("retrieval_scope_fixture"),
    )
    built = _build_one(fixture)

    result = EvidenceService(fixture.session).persist_document_context(
        fixture.users["reader"],
        built,
    )

    assert result.bundle == built.bundle
    assert result.reused is False
    assert len(result.evidences) == 1
    detail = result.evidences[0]
    segment = built.bundle.segments[0]
    source = built.sources[0]
    assert detail.id == segment.evidence_id
    assert detail.context_id == built.bundle.context_id
    assert detail.citation_label == "[E1]"
    assert detail.identity == segment.identity
    assert detail.source_locator == segment.source_locator
    assert detail.source_content_sha256 == source.content_sha256
    assert detail.context_text_sha256 == segment.text_sha256
    assert detail.excerpt == segment.text
    assert _counts(fixture) == (1, 1)

    context_row = fixture.session.get(ContextArtifact, built.bundle.context_id)
    evidence_row = fixture.session.get(Evidence, segment.evidence_id)
    assert context_row is not None
    assert context_row.identity_sha256 == built.identity_sha256
    assert context_row.segment_count == 1
    assert evidence_row is not None
    assert evidence_row.tenant_id == fixture.users["reader"].tenant_id
    assert evidence_row.agent_run_id is None
    assert evidence_row.tool_call_id is None
    assert evidence_row.file_id == source.file_id
    assert evidence_row.document_chunk_set_id == source.chunk_set_id
    assert evidence_row.document_index_set_id == source.index_set_id


def test_repeating_the_same_build_reuses_exact_rows(
    request: pytest.FixtureRequest,
) -> None:
    fixture = cast(
        RetrievalScopeFixture,
        request.getfixturevalue("retrieval_scope_fixture"),
    )
    built = _build_one(fixture)
    service = EvidenceService(fixture.session)

    first = service.persist_document_context(fixture.users["reader"], built)
    first_created_at = first.evidences[0].created_at
    second = service.persist_document_context(fixture.users["reader"], built)

    assert first.bundle.context_id == second.bundle.context_id
    assert first.evidences[0].id == second.evidences[0].id
    assert second.evidences[0].created_at == first_created_at
    assert first.reused is False
    assert second.reused is True
    assert _counts(fixture) == (1, 1)


def test_runtime_context_creates_link_without_owning_document_evidence(
    request: pytest.FixtureRequest,
) -> None:
    fixture = cast(
        RetrievalScopeFixture,
        request.getfixturevalue("retrieval_scope_fixture"),
    )
    built = _build_one(fixture)
    runtime_context = _runtime_context(fixture, "first-link")

    EvidenceService(fixture.session).persist_document_context(
        fixture.users["reader"],
        built,
        runtime_context=runtime_context,
    )

    link = fixture.session.scalar(
        select(ToolContextLink).where(
            ToolContextLink.tenant_id == runtime_context.tenant_id,
            ToolContextLink.tool_call_id == runtime_context.tool_call_id,
        )
    )
    evidence = fixture.session.get(Evidence, built.bundle.segments[0].evidence_id)
    assert link is not None
    assert link.tenant_id == runtime_context.tenant_id
    assert link.agent_run_id == runtime_context.agent_run_id
    assert link.tool_call_id == runtime_context.tool_call_id
    assert link.context_artifact_id == built.bundle.context_id
    assert evidence is not None
    assert evidence.agent_run_id is None
    assert evidence.tool_call_id is None


def test_context_can_be_reused_by_multiple_tool_calls_with_idempotent_links(
    request: pytest.FixtureRequest,
) -> None:
    fixture = cast(
        RetrievalScopeFixture,
        request.getfixturevalue("retrieval_scope_fixture"),
    )
    built = _build_one(fixture)
    service = EvidenceService(fixture.session)
    first_runtime = _runtime_context(fixture, "first-reuse")
    second_runtime = _runtime_context(fixture, "second-reuse")

    first = service.persist_document_context(
        fixture.users["reader"], built, runtime_context=first_runtime
    )
    retry = service.persist_document_context(
        fixture.users["reader"], built, runtime_context=first_runtime
    )
    second = service.persist_document_context(
        fixture.users["reader"], built, runtime_context=second_runtime
    )

    assert first.reused is False
    assert retry.reused is True
    assert second.reused is True
    assert _counts(fixture) == (1, 1)
    assert _link_count(fixture) == 2


def test_one_tool_call_cannot_claim_two_contexts_and_rolls_back_new_rows(
    request: pytest.FixtureRequest,
) -> None:
    fixture = cast(
        RetrievalScopeFixture,
        request.getfixturevalue("retrieval_scope_fixture"),
    )
    first = _build_one(fixture, "清洁前要做什么？")
    second = _build_one(fixture, "清洁前需要先断开什么？")
    assert first.bundle.context_id != second.bundle.context_id
    runtime_context = _runtime_context(fixture, "one-call-two-contexts")
    service = EvidenceService(fixture.session)
    service.persist_document_context(
        fixture.users["reader"], first, runtime_context=runtime_context
    )

    with pytest.raises(KnowledgeEvidencePersistenceError):
        service.persist_document_context(
            fixture.users["reader"], second, runtime_context=runtime_context
        )

    assert _counts(fixture) == (1, 1)
    assert _link_count(fixture) == 1


def test_empty_unsupported_context_persists_only_its_audit_artifact(
    request: pytest.FixtureRequest,
) -> None:
    fixture = cast(
        RetrievalScopeFixture,
        request.getfixturevalue("retrieval_scope_fixture"),
    )
    built = ContextBuilderService(
        RetrievalRepository(fixture.session),
        neighbor_window=0,
    ).build(
        fixture.users["reader"],
        RetrievalRequest(query="没有匹配证据的问题"),
        _response_for_chunks(fixture, []),
    )

    result = EvidenceService(fixture.session).persist_document_context(
        fixture.users["reader"],
        built,
    )

    assert result.bundle.supported is False
    assert result.evidences == ()
    assert _counts(fixture) == (1, 0)


def test_revoked_source_is_rejected_without_writing_partial_rows(
    request: pytest.FixtureRequest,
) -> None:
    fixture = cast(
        RetrievalScopeFixture,
        request.getfixturevalue("retrieval_scope_fixture"),
    )
    built = _build_one(fixture)
    document = fixture.session.get(Document, built.sources[0].document_id)
    assert document is not None
    document.deleted_at = document.created_at + timedelta(seconds=1)
    fixture.session.flush()

    with pytest.raises(KnowledgeEvidencePersistenceError) as captured:
        EvidenceService(fixture.session).persist_document_context(
            fixture.users["reader"],
            built,
        )

    assert captured.value.to_detail().model_dump() == {
        "code": "INTERNAL_ERROR",
        "message": "文档证据保存失败",
        "retryable": True,
        "field": None,
    }
    assert _counts(fixture) == (0, 0)


def test_tampered_private_source_is_rejected_before_persistence(
    request: pytest.FixtureRequest,
) -> None:
    fixture = cast(
        RetrievalScopeFixture,
        request.getfixturevalue("retrieval_scope_fixture"),
    )
    built = _build_one(fixture)
    forged = replace(
        built,
        sources=(replace(built.sources[0], file_id=uuid4()),),
    )

    with pytest.raises(KnowledgeEvidencePersistenceError):
        EvidenceService(fixture.session).persist_document_context(
            fixture.users["reader"],
            forged,
        )

    assert _counts(fixture) == (0, 0)


class _FailingKnowledgeEvidenceRepository(KnowledgeEvidenceRepository):
    def insert_document_evidences(self, values: list[dict[str, object]]) -> None:
        raise SQLAlchemyError("secret database detail")


class _FailingToolContextRepository(KnowledgeEvidenceRepository):
    def insert_tool_context_link(self, values: dict[str, object]) -> bool:
        raise SQLAlchemyError("secret tool-context link detail")


def test_evidence_failure_rolls_back_the_context_artifact_savepoint(
    request: pytest.FixtureRequest,
) -> None:
    fixture = cast(
        RetrievalScopeFixture,
        request.getfixturevalue("retrieval_scope_fixture"),
    )
    built = _build_one(fixture)
    repository = _FailingKnowledgeEvidenceRepository(fixture.session)

    with pytest.raises(KnowledgeEvidencePersistenceError) as captured:
        EvidenceService(
            fixture.session,
            knowledge_repository=repository,
        ).persist_document_context(fixture.users["reader"], built)

    assert "secret" not in captured.value.to_detail().message
    assert _counts(fixture) == (0, 0)


def test_link_failure_rolls_back_context_evidence_and_link_together(
    request: pytest.FixtureRequest,
) -> None:
    fixture = cast(
        RetrievalScopeFixture,
        request.getfixturevalue("retrieval_scope_fixture"),
    )
    built = _build_one(fixture)
    runtime_context = _runtime_context(fixture, "link-failure")
    repository = _FailingToolContextRepository(fixture.session)

    with pytest.raises(KnowledgeEvidencePersistenceError) as captured:
        EvidenceService(
            fixture.session,
            knowledge_repository=repository,
        ).persist_document_context(
            fixture.users["reader"],
            built,
            runtime_context=runtime_context,
        )

    assert "secret" not in captured.value.to_detail().message
    assert _counts(fixture) == (0, 0)
    assert _link_count(fixture) == 0

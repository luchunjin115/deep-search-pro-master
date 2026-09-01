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
from app.models.runtime import ContextArtifact, Evidence
from app.repositories.evidence import KnowledgeEvidenceRepository
from app.repositories.retrieval import RetrievalRepository
from app.schemas.retrieval import RetrievalRequest
from app.services.evidence import EvidenceService
from app.services.retrieval.context import BuiltContext, ContextBuilderService
from tests.integration import test_retrieval_repository_scope as scope_support
from tests.integration.test_context_retrieval_repository import _response_for_chunks
from tests.integration.test_retrieval_repository_scope import RetrievalScopeFixture

retrieval_scope_fixture = scope_support.retrieval_scope_fixture


def _build_one(fixture: RetrievalScopeFixture) -> BuiltContext:
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
        RetrievalRequest(query="清洁前要做什么？"),
        _response_for_chunks(fixture, [anchor.id]),
    )


def _counts(fixture: RetrievalScopeFixture) -> tuple[int, int]:
    return (
        fixture.session.scalar(select(func.count()).select_from(ContextArtifact)) or 0,
        fixture.session.scalar(select(func.count()).select_from(Evidence)) or 0,
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

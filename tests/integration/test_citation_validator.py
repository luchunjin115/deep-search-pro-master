from __future__ import annotations

from datetime import timedelta
from typing import cast

import pytest

from app.core.errors import CitationValidationError
from app.models.knowledge import Document
from app.repositories.evidence import KnowledgeEvidenceRepository
from app.repositories.retrieval import RetrievalRepository
from app.schemas.retrieval import RetrievalRequest
from app.services.citations import CitationValidatorService
from app.services.evidence import EvidenceService
from app.services.retrieval.context import ContextBuilderService
from tests.integration import test_retrieval_repository_scope as scope_support
from tests.integration.test_context_retrieval_repository import _response_for_chunks
from tests.integration.test_knowledge_evidence_service import _build_one
from tests.integration.test_retrieval_repository_scope import RetrievalScopeFixture

retrieval_scope_fixture = scope_support.retrieval_scope_fixture


def test_validates_persisted_label_through_current_postgresql_acl(
    request: pytest.FixtureRequest,
) -> None:
    fixture = cast(
        RetrievalScopeFixture,
        request.getfixturevalue("retrieval_scope_fixture"),
    )
    built = _build_one(fixture)
    EvidenceService(fixture.session).persist_document_context(
        fixture.users["reader"],
        built,
    )

    result = CitationValidatorService(
        KnowledgeEvidenceRepository(fixture.session)
    ).validate_answer(
        fixture.users["reader"],
        built.bundle.context_id,
        "清洁前必须断开电源 [E1]。",
    )

    assert result.context_id == built.bundle.context_id
    assert len(result.citations) == 1
    assert result.citations[0].evidence_id == built.bundle.segments[0].evidence_id


def test_requesting_user_and_current_acl_are_both_required(
    request: pytest.FixtureRequest,
) -> None:
    fixture = cast(
        RetrievalScopeFixture,
        request.getfixturevalue("retrieval_scope_fixture"),
    )
    built = _build_one(fixture)
    EvidenceService(fixture.session).persist_document_context(
        fixture.users["reader"],
        built,
    )
    service = CitationValidatorService(KnowledgeEvidenceRepository(fixture.session))

    with pytest.raises(CitationValidationError):
        service.validate_answer(
            fixture.users["other_tenant"],
            built.bundle.context_id,
            "伪装引用 [E1]",
        )

    document = fixture.session.get(Document, built.sources[0].document_id)
    assert document is not None
    document.deleted_at = document.created_at + timedelta(seconds=1)
    fixture.session.flush()
    with pytest.raises(CitationValidationError):
        service.validate_answer(
            fixture.users["reader"],
            built.bundle.context_id,
            "撤权后引用 [E1]",
        )


def test_persisted_empty_context_only_allows_no_citations(
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
        RetrievalRequest(query="没有证据的问题"),
        _response_for_chunks(fixture, []),
    )
    EvidenceService(fixture.session).persist_document_context(
        fixture.users["reader"],
        built,
    )
    service = CitationValidatorService(KnowledgeEvidenceRepository(fixture.session))

    result = service.validate_answer(
        fixture.users["reader"],
        built.bundle.context_id,
        "没有找到可以支持回答的资料。",
    )
    assert result.citations == []

    with pytest.raises(CitationValidationError):
        service.validate_answer(
            fixture.users["reader"],
            built.bundle.context_id,
            "编造引用 [E1]",
        )

from __future__ import annotations

from datetime import timedelta
from typing import cast

import pytest
from sqlalchemy import delete

from app.core.errors import EvidenceNotFoundError
from app.models.knowledge import (
    Document,
    DocumentAcl,
    DocumentChunk,
    DocumentIndexSet,
    DocumentVersion,
    StoredFile,
)
from app.models.runtime import Evidence
from app.repositories.evidence import EvidenceRepository
from app.repositories.retrieval import RetrievalRepository
from app.schemas.evidence import GetEvidenceDetailInput, ToolDocumentEvidenceDetail
from app.schemas.retrieval import RetrievalRequest
from app.services.evidence import EvidenceQueryService, EvidenceService
from app.services.retrieval.context import BuiltContext, ContextBuilderService
from tests.integration import test_retrieval_repository_scope as scope_support
from tests.integration.test_context_retrieval_repository import _response_for_chunks
from tests.integration.test_knowledge_evidence_service import _build_one
from tests.integration.test_retrieval_repository_scope import RetrievalScopeFixture

retrieval_scope_fixture = scope_support.retrieval_scope_fixture


def _service(fixture: RetrievalScopeFixture) -> EvidenceQueryService:
    return EvidenceQueryService(EvidenceRepository(fixture.session, 2_000))


def _build_acl_context(fixture: RetrievalScopeFixture) -> BuiltContext:
    chunk = fixture.session.get(DocumentChunk, fixture.expected["user_acl"])
    assert chunk is not None
    chunk.body_text = "用户ACL允许读取的合成说明书内容。"
    chunk.retrieval_text = chunk.body_text
    chunk.token_count = 20
    chunk.page_numbers = [3]
    chunk.source_spans = [
        {
            "block_id": "b000001",
            "start_locator": {"page_number": 3, "block_number": 1},
            "end_locator": {"page_number": 3, "block_number": 1},
            "character_start": 0,
            "character_end": len(chunk.body_text),
            "bounding_boxes": [],
        }
    ]
    fixture.session.flush()
    return ContextBuilderService(
        RetrievalRepository(fixture.session),
        neighbor_window=0,
    ).build(
        fixture.users["reader"],
        RetrievalRequest(query="ACL资料里写了什么？"),
        _response_for_chunks(fixture, [chunk.id]),
    )


def test_reads_document_evidence_through_current_requester_acl_and_active_source(
    request: pytest.FixtureRequest,
) -> None:
    fixture = cast(
        RetrievalScopeFixture,
        request.getfixturevalue("retrieval_scope_fixture"),
    )
    user = fixture.users["reader"]
    built = _build_one(fixture)
    persisted = EvidenceService(fixture.session).persist_document_context(user, built)
    evidence = persisted.evidences[0]

    result = _service(fixture).get_tool_detail(
        user,
        GetEvidenceDetailInput(evidence_id=evidence.id),
    )

    assert isinstance(result.detail, ToolDocumentEvidenceDetail)
    assert result.evidence_id == evidence.id
    assert result.detail.file_id == built.sources[0].file_id
    assert result.detail.context_id == built.bundle.context_id
    assert result.detail.citation_label == "[E1]"
    assert result.detail.identity == built.bundle.segments[0].identity
    assert result.detail.document == built.bundle.segments[0].document
    assert result.detail.source_locator == built.bundle.segments[0].source_locator
    assert result.detail.source_content_sha256 == built.sources[0].content_sha256
    assert result.detail.context_text_sha256 == built.bundle.segments[0].text_sha256
    serialized = result.model_dump_json()
    for forbidden in (
        str(user.tenant_id),
        "owner_user_id",
        "access_scope",
        "storage_key",
        "parsed_storage_key",
        "sql",
    ):
        assert forbidden not in serialized.lower()


@pytest.mark.parametrize("user_label", ("company_owner", "other_tenant"))
def test_context_requester_and_tenant_are_both_required(
    request: pytest.FixtureRequest,
    user_label: str,
) -> None:
    fixture = cast(
        RetrievalScopeFixture,
        request.getfixturevalue("retrieval_scope_fixture"),
    )
    owner = fixture.users["reader"]
    built = _build_one(fixture)
    evidence_id = (
        EvidenceService(fixture.session)
        .persist_document_context(
            owner,
            built,
        )
        .evidences[0]
        .id
    )

    with pytest.raises(EvidenceNotFoundError):
        _service(fixture).get_tool_detail(
            fixture.users[user_label],
            GetEvidenceDetailInput(evidence_id=evidence_id),
        )


def test_acl_revocation_after_persistence_hides_document_evidence(
    request: pytest.FixtureRequest,
) -> None:
    fixture = cast(
        RetrievalScopeFixture,
        request.getfixturevalue("retrieval_scope_fixture"),
    )
    user = fixture.users["reader"]
    built = _build_acl_context(fixture)
    evidence_id = (
        EvidenceService(fixture.session)
        .persist_document_context(
            user,
            built,
        )
        .evidences[0]
        .id
    )
    fixture.session.execute(
        delete(DocumentAcl).where(
            DocumentAcl.tenant_id == user.tenant_id,
            DocumentAcl.document_id == built.sources[0].document_id,
        )
    )
    fixture.session.flush()

    with pytest.raises(EvidenceNotFoundError):
        _service(fixture).get_tool_detail(
            user,
            GetEvidenceDetailInput(evidence_id=evidence_id),
        )


@pytest.mark.parametrize(
    "invalid_state",
    (
        "document_deleted",
        "version_inactive",
        "index_inactive",
        "file_deleted",
        "source_hash_mismatch",
    ),
)
def test_current_source_state_and_full_chunk_identity_are_rechecked(
    request: pytest.FixtureRequest,
    invalid_state: str,
) -> None:
    fixture = cast(
        RetrievalScopeFixture,
        request.getfixturevalue("retrieval_scope_fixture"),
    )
    user = fixture.users["reader"]
    built = _build_one(fixture)
    evidence_id = (
        EvidenceService(fixture.session)
        .persist_document_context(
            user,
            built,
        )
        .evidences[0]
        .id
    )
    source = built.sources[0]
    document = fixture.session.get(Document, source.document_id)
    version = fixture.session.get(DocumentVersion, source.version_id)
    index_set = fixture.session.get(DocumentIndexSet, source.index_set_id)
    file_row = fixture.session.get(StoredFile, source.file_id)
    evidence_row = fixture.session.get(Evidence, evidence_id)
    assert all(
        row is not None
        for row in (document, version, index_set, file_row, evidence_row)
    )

    if invalid_state == "document_deleted":
        assert document is not None
        document.deleted_at = document.created_at + timedelta(seconds=1)
    elif invalid_state == "version_inactive":
        assert document is not None
        document.active_version_id = None
    elif invalid_state == "index_inactive":
        assert version is not None
        version.active_index_set_id = None
    elif invalid_state == "file_deleted":
        assert file_row is not None
        file_row.status = "soft_deleted"
        file_row.deleted_at = file_row.created_at + timedelta(seconds=1)
    else:
        assert evidence_row is not None
        evidence_row.source_content_sha256 = "f" * 64
    fixture.session.flush()

    with pytest.raises(EvidenceNotFoundError):
        _service(fixture).get_tool_detail(
            user,
            GetEvidenceDetailInput(evidence_id=evidence_id),
        )

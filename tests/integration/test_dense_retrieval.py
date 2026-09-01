from __future__ import annotations

import hashlib
import json
from collections.abc import Generator, Sequence
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.session import DatabaseRuntime, create_database_runtime
from app.models.identity import Tenant, User
from app.models.knowledge import (
    Document,
    DocumentAcl,
    DocumentChunk,
    DocumentChunkSet,
    DocumentIndexSet,
    DocumentVersion,
    StoredFile,
)
from app.repositories.retrieval import RetrievalRepository
from app.schemas.auth import CurrentUser
from app.schemas.retrieval import RetrievalRequest
from app.services.retrieval import (
    EmbeddingBatch,
    EmbeddingIdentity,
    EmbeddingPurpose,
    FakeEmbeddingProvider,
    RetrievalEmbeddingIdentityMismatchError,
)
from app.services.retrieval.dense import DenseRetrievalService
from app.services.retrieval.lexical_text import FtsTextPurpose, build_fts_text

_NOW = datetime(2026, 9, 1, 15, 0, tzinfo=UTC)


class FixedQueryProvider:
    def __init__(
        self,
        identity: EmbeddingIdentity,
        query_vector: tuple[float, ...],
    ) -> None:
        self._identity = identity
        self._query_vector = query_vector
        self.calls: list[tuple[tuple[str, ...], EmbeddingPurpose]] = []

    @property
    def identity(self) -> EmbeddingIdentity:
        return self._identity

    def embed(
        self,
        texts: Sequence[str],
        *,
        purpose: EmbeddingPurpose,
    ) -> EmbeddingBatch:
        self.calls.append((tuple(texts), purpose))
        assert len(texts) == 1
        assert purpose is EmbeddingPurpose.QUERY
        return EmbeddingBatch(
            vectors=(self._query_vector,),
            cache_keys=("sha256:" + "f" * 64,),
            purpose=purpose,
            identity=self.identity,
            effective_batch_size=1,
        )


@dataclass(slots=True)
class DenseFixture:
    runtime: DatabaseRuntime
    session: Session
    reader: CurrentUser
    mismatch_reader: CurrentUser
    identity: EmbeddingIdentity
    expected_ids: dict[str, UUID]

    def service(
        self,
        user: CurrentUser,
        *,
        candidate_count: int,
    ) -> tuple[DenseRetrievalService, FixedQueryProvider]:
        provider = FixedQueryProvider(
            self.identity,
            (1.0,) + (0.0,) * 1023,
        )
        repository = RetrievalRepository(self.session, statement_timeout_ms=2000)
        return (
            DenseRetrievalService(
                repository,
                provider,
                query_max_characters=2000,
                candidate_count=candidate_count,
            ),
            provider,
        )


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _identity_hash(identity: EmbeddingIdentity) -> str:
    payload = json.dumps(
        asdict(identity),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return _sha256(payload)


def _user(*, user_id: UUID, tenant_id: UUID, label: str) -> CurrentUser:
    return CurrentUser(
        user_id=user_id,
        tenant_id=tenant_id,
        email=f"{label}@dense.example.com",
        display_name=label,
        roles=["amazon_operator"],
        market_scopes=["DE"],
        synthetic_data=True,
    )


def _add_dense_document(
    session: Session,
    *,
    tenant_id: UUID,
    owner_id: UUID,
    label: str,
    row_id: UUID,
    vector: tuple[float, ...],
    identity: EmbeddingIdentity,
) -> tuple[Document, DocumentChunk]:
    document_id = uuid4()
    file_id = uuid4()
    version_id = uuid4()
    chunk_set_id = uuid4()
    index_set_id = uuid4()
    source_hash = _sha256(f"source:{label}")
    document = Document(
        id=document_id,
        tenant_id=tenant_id,
        owner_user_id=owner_id,
        title=f"Dense合成文档-{label}",
        document_type="product_manual",
        language="zh-CN",
        market="DE",
        access_level="restricted",
        created_at=_NOW,
    )
    file_row = StoredFile(
        id=file_id,
        tenant_id=tenant_id,
        owner_user_id=owner_id,
        original_name=f"{label}.pdf",
        storage_key=f"{tenant_id}/uploads/2026/09/{file_id}.pdf",
        extension=".pdf",
        mime_type="application/pdf",
        size_bytes=128,
        sha256=source_hash,
        category="uploads",
        status="ready",
        created_at=_NOW,
    )
    session.add_all([document, file_row])
    session.flush()
    version = DocumentVersion(
        id=version_id,
        tenant_id=tenant_id,
        document_id=document_id,
        file_id=file_id,
        version_no=1,
        content_hash=source_hash,
        parser_name="native_pdf",
        parser_version="m2-native-pdf-v1",
        parsed_storage_key=f"{tenant_id}/parsed/2026/09/{version_id}.json",
        parse_status="ready",
        index_status="ready",
        created_at=_NOW,
    )
    session.add(version)
    session.flush()
    chunk_set = DocumentChunkSet(
        id=chunk_set_id,
        tenant_id=tenant_id,
        document_id=document_id,
        document_version_id=version_id,
        artifact_schema_version="m2-canonical-chunk-artifact-v1",
        content_hash_version="m2-chunk-content-v1",
        routed_schema_version="m2-routed-parsed-document-v1",
        canonical_schema_version="m2-canonical-parsed-artifact-v1",
        source_sha256=source_hash,
        parsed_publication_sha256=_sha256(f"parsed:{label}"),
        selected_artifact_content_sha256=_sha256(f"artifact:{label}"),
        chunker_name="structure_aware",
        chunker_version="m2-structure-aware-chunker-v1",
        token_counter_name="unicode_mixed",
        token_counter_version="m2-unicode-token-counter-v1",
        normalization_version="m2-chunk-normalization-v1",
        config_json={"label": label},
        config_sha256=_sha256(f"config:{label}"),
        status="ready",
        attempt_count=1,
        output_sha256=_sha256(f"chunks:{label}"),
        chunk_storage_key=f"{tenant_id}/chunks/2026/09/{chunk_set_id}.json",
        chunk_count=1,
        text_chunk_count=1,
        table_chunk_count=0,
        total_token_count=10,
        excluded_span_count=0,
        created_at=_NOW,
        started_at=_NOW + timedelta(seconds=1),
        completed_at=_NOW + timedelta(seconds=2),
    )
    session.add(chunk_set)
    session.flush()
    index_set = DocumentIndexSet(
        id=index_set_id,
        tenant_id=tenant_id,
        document_id=document_id,
        document_version_id=version_id,
        document_chunk_set_id=chunk_set_id,
        index_schema_version="m2-document-index-set-v1",
        embedding_identity_json=asdict(identity),
        embedding_identity_sha256=_identity_hash(identity),
        embedding_model=identity.model_id,
        embedding_version=identity.revision,
        embedding_purpose="document",
        fts_builder_version="m2-fts-jieba-search-v1",
        status="ready",
        attempt_count=1,
        chunk_count=1,
        text_chunk_count=1,
        table_chunk_count=0,
        total_token_count=10,
        created_at=_NOW,
        started_at=_NOW + timedelta(seconds=3),
        completed_at=_NOW + timedelta(seconds=4),
    )
    session.add(index_set)
    session.flush()
    body_text = f"{label}合成检索正文"
    chunk = DocumentChunk(
        id=row_id,
        tenant_id=tenant_id,
        document_id=document_id,
        document_version_id=version_id,
        document_chunk_set_id=chunk_set_id,
        document_index_set_id=index_set_id,
        chunk_id="c000001",
        chunk_index=1,
        kind="text",
        body_text=body_text,
        retrieval_text=body_text,
        fts_text=build_fts_text(
            body_text,
            purpose=FtsTextPurpose.DOCUMENT,
        ).text,
        token_count=10,
        content_sha256=_sha256(f"chunk:{label}"),
        heading_path=[label],
        page_numbers=[1],
        source_block_ids=["b000001"],
        source_spans=[
            {
                "block_id": "b000001",
                "start_locator": {"page_number": 1, "heading_path": [label]},
                "end_locator": {"page_number": 1, "heading_path": [label]},
            }
        ],
        bounding_boxes=[],
        overlap_json=None,
        table_json=None,
        warnings=[],
        embedding=list(vector),
        embedding_model=identity.model_id,
        embedding_version=identity.revision,
        embedding_cache_key=f"sha256:{_sha256(f'embedding:{label}')}",
        created_at=_NOW,
    )
    session.add(chunk)
    session.flush()
    version.active_index_set_id = index_set_id
    document.active_version_id = version_id
    session.flush()
    return document, chunk


@pytest.fixture
def dense_fixture() -> Generator[DenseFixture, None, None]:
    settings = Settings(_env_file=".env.example", app_env="test")  # type: ignore[call-arg]
    command.upgrade(Config("alembic.ini"), "head")
    runtime = create_database_runtime(settings)
    session = runtime.session_factory()
    tenant_id = uuid4()
    reader_id = uuid4()
    mismatch_reader_id = uuid4()
    denied_owner_id = uuid4()
    reader = _user(user_id=reader_id, tenant_id=tenant_id, label="reader")
    mismatch_reader = _user(
        user_id=mismatch_reader_id,
        tenant_id=tenant_id,
        label="mismatch-reader",
    )
    identity = FakeEmbeddingProvider().identity
    mismatch_identity = replace(identity, revision="m2-fake-other")
    expected_ids: dict[str, UUID] = {}
    try:
        session.add(Tenant(id=tenant_id, name="M2-16.4 dense tenant"))
        session.flush()
        for user in (reader, mismatch_reader):
            session.add(
                User(
                    id=user.user_id,
                    tenant_id=user.tenant_id,
                    email=user.email,
                    display_name=user.display_name,
                    password_hash="$argon2id$synthetic-dense-only",
                )
            )
        session.add(
            User(
                id=denied_owner_id,
                tenant_id=tenant_id,
                email="denied-owner@dense.example.com",
                display_name="denied-owner",
                password_hash="$argon2id$synthetic-dense-only",
            )
        )
        session.flush()

        samples = (
            (
                "exact",
                UUID("00000000-0000-4000-8000-000000000010"),
                (1.0,) + (0.0,) * 1023,
            ),
            (
                "near",
                UUID("00000000-0000-4000-8000-000000000011"),
                (0.8, 0.6) + (0.0,) * 1022,
            ),
            (
                "tie_low",
                UUID("00000000-0000-4000-8000-000000000001"),
                (0.0, 1.0) + (0.0,) * 1022,
            ),
            (
                "tie_high",
                UUID("00000000-0000-4000-8000-000000000002"),
                (0.0, 1.0) + (0.0,) * 1022,
            ),
        )
        for label, row_id, vector in samples:
            _document, chunk = _add_dense_document(
                session,
                tenant_id=tenant_id,
                owner_id=reader_id,
                label=label,
                row_id=row_id,
                vector=vector,
                identity=identity,
            )
            expected_ids[label] = chunk.id

        _denied_document, denied_chunk = _add_dense_document(
            session,
            tenant_id=tenant_id,
            owner_id=denied_owner_id,
            label="denied-perfect",
            row_id=UUID("00000000-0000-4000-8000-000000000020"),
            vector=(1.0,) + (0.0,) * 1023,
            identity=identity,
        )
        expected_ids["denied"] = denied_chunk.id

        mismatch_document, mismatch_chunk = _add_dense_document(
            session,
            tenant_id=tenant_id,
            owner_id=mismatch_reader_id,
            label="mismatch-perfect",
            row_id=UUID("00000000-0000-4000-8000-000000000021"),
            vector=(1.0,) + (0.0,) * 1023,
            identity=mismatch_identity,
        )
        expected_ids["mismatch"] = mismatch_chunk.id
        session.add(
            DocumentAcl(
                id=uuid4(),
                tenant_id=tenant_id,
                document_id=mismatch_document.id,
                subject_type="user",
                user_id=reader_id,
                permission="read",
            )
        )
        session.flush()
        yield DenseFixture(
            runtime=runtime,
            session=session,
            reader=reader,
            mismatch_reader=mismatch_reader,
            identity=identity,
            expected_ids=expected_ids,
        )
    finally:
        session.rollback()
        session.close()
        runtime.engine.dispose()


def test_dense_retrieval_uses_pgvector_top_k_stable_tie_and_shared_scope(
    dense_fixture: DenseFixture,
) -> None:
    fixture = dense_fixture
    service, provider = fixture.service(fixture.reader, candidate_count=3)

    response = service.retrieve(
        fixture.reader,
        RetrievalRequest(query="蘑菇灯亮度"),
    )

    assert provider.calls == [(("蘑菇灯亮度",), EmbeddingPurpose.QUERY)]
    assert [result.identity.chunk_id for result in response.results] == [
        fixture.expected_ids["exact"],
        fixture.expected_ids["near"],
        fixture.expected_ids["tie_low"],
    ]
    assert fixture.expected_ids["denied"] not in {
        result.identity.chunk_id for result in response.results
    }
    assert fixture.expected_ids["mismatch"] not in {
        result.identity.chunk_id for result in response.results
    }
    distances = [
        result.scores.dense.distance
        for result in response.results
        if result.scores.dense is not None
    ]
    assert distances == pytest.approx([0.0, 0.2, 1.0])


def test_dense_retrieval_rejects_scope_with_only_incompatible_identity(
    dense_fixture: DenseFixture,
) -> None:
    fixture = dense_fixture
    service, provider = fixture.service(fixture.mismatch_reader, candidate_count=5)

    with pytest.raises(RetrievalEmbeddingIdentityMismatchError):
        service.retrieve(
            fixture.mismatch_reader,
            RetrievalRequest(query="蘑菇灯亮度"),
        )

    assert provider.calls == []


def test_dense_sql_keeps_scope_and_identity_before_order_and_limit(
    dense_fixture: DenseFixture,
) -> None:
    fixture = dense_fixture
    repository = RetrievalRepository(fixture.session, statement_timeout_ms=2000)
    statement = repository.dense_candidates_statement(
        fixture.reader,
        query_vector=(1.0,) + (0.0,) * 1023,
        embedding_identity=fixture.identity,
        limit=3,
    )
    compiled = str(statement.compile()).upper()

    assert "DOCUMENT_ACL" in compiled
    assert "EMBEDDING_IDENTITY_JSON" in compiled
    assert "<=>" in compiled
    assert (
        compiled.index("WHERE") < compiled.index("ORDER BY") < compiled.index("LIMIT")
    )

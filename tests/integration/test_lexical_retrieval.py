from __future__ import annotations

from collections.abc import Generator
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.session import DatabaseRuntime, create_database_runtime
from app.models.identity import Tenant, User
from app.models.knowledge import DocumentChunk, DocumentIndexSet
from app.repositories.retrieval import RetrievalRepository
from app.schemas.auth import CurrentUser
from app.schemas.retrieval import RetrievalRequest
from app.services.retrieval import FTS_BUILDER_VERSION, FakeEmbeddingProvider
from app.services.retrieval.lexical import LexicalRetrievalService
from app.services.retrieval.lexical_text import FtsTextPurpose, build_fts_text
from tests.integration.test_dense_retrieval import _add_dense_document

_NOW = datetime(2026, 9, 1, 16, 0, tzinfo=UTC)


@dataclass(slots=True)
class LexicalFixture:
    runtime: DatabaseRuntime
    session: Session
    reader: CurrentUser
    expected_ids: dict[str, UUID]

    def service(self, *, candidate_count: int = 10) -> LexicalRetrievalService:
        return LexicalRetrievalService(
            RetrievalRepository(self.session, statement_timeout_ms=2000),
            candidate_count=candidate_count,
        )


def _set_chunk_text(chunk: DocumentChunk, value: str) -> None:
    chunk.body_text = value
    chunk.retrieval_text = value
    chunk.fts_text = build_fts_text(
        value,
        purpose=FtsTextPurpose.DOCUMENT,
    ).text


@pytest.fixture
def lexical_fixture() -> Generator[LexicalFixture, None, None]:
    settings = Settings(_env_file=".env.example", app_env="test")  # type: ignore[call-arg]
    command.upgrade(Config("alembic.ini"), "head")
    runtime = create_database_runtime(settings)
    session = runtime.session_factory()
    tenant_id = uuid4()
    reader_id = uuid4()
    denied_owner_id = uuid4()
    reader = CurrentUser(
        user_id=reader_id,
        tenant_id=tenant_id,
        email="reader@lexical.example.com",
        display_name="Lexical reader",
        roles=["amazon_operator"],
        market_scopes=["DE"],
        synthetic_data=True,
    )
    identity = FakeEmbeddingProvider().identity
    expected_ids: dict[str, UUID] = {}
    try:
        session.add(Tenant(id=tenant_id, name="M2-16.5 lexical tenant"))
        session.flush()
        for user_id, email, display_name in (
            (reader_id, reader.email, reader.display_name),
            (denied_owner_id, "denied@lexical.example.com", "Denied owner"),
        ):
            session.add(
                User(
                    id=user_id,
                    tenant_id=tenant_id,
                    email=email,
                    display_name=display_name,
                    password_hash="$argon2id$synthetic-lexical-only",
                )
            )
        session.flush()

        samples = (
            (
                "rank_high",
                UUID("00000000-0000-4000-8000-000000000010"),
                "蘑菇灯亮度亮度亮度调节说明",
            ),
            (
                "rank_mid",
                UUID("00000000-0000-4000-8000-000000000011"),
                "蘑菇灯亮度亮度说明",
            ),
            (
                "tie_low",
                UUID("00000000-0000-4000-8000-000000000001"),
                "蘑菇灯亮度说明",
            ),
            (
                "tie_high",
                UUID("00000000-0000-4000-8000-000000000002"),
                "蘑菇灯亮度说明",
            ),
            (
                "identifiers",
                UUID("00000000-0000-4000-8000-000000000012"),
                "brightness LR-TL-MUSH-OR01 X200 220V 条款 5.2",
            ),
        )
        for label, row_id, value in samples:
            _document, chunk = _add_dense_document(
                session,
                tenant_id=tenant_id,
                owner_id=reader_id,
                label=f"lexical-{label}",
                row_id=row_id,
                vector=(1.0,) + (0.0,) * 1023,
                identity=identity,
            )
            _set_chunk_text(chunk, value)
            expected_ids[label] = chunk.id

        _denied_document, denied_chunk = _add_dense_document(
            session,
            tenant_id=tenant_id,
            owner_id=denied_owner_id,
            label="lexical-denied",
            row_id=UUID("00000000-0000-4000-8000-000000000020"),
            vector=(1.0,) + (0.0,) * 1023,
            identity=identity,
        )
        _set_chunk_text(denied_chunk, "亮度亮度亮度亮度亮度")
        expected_ids["denied"] = denied_chunk.id

        _old_document, old_chunk = _add_dense_document(
            session,
            tenant_id=tenant_id,
            owner_id=reader_id,
            label="lexical-old-builder",
            row_id=UUID("00000000-0000-4000-8000-000000000021"),
            vector=(1.0,) + (0.0,) * 1023,
            identity=identity,
        )
        _set_chunk_text(old_chunk, "亮度亮度亮度亮度亮度")
        old_index_set = session.get(DocumentIndexSet, old_chunk.document_index_set_id)
        assert old_index_set is not None
        old_index_set.fts_builder_version = "m2-fts-raw-retrieval-v1"
        expected_ids["old_builder"] = old_chunk.id
        session.flush()

        yield LexicalFixture(runtime, session, reader, expected_ids)
    finally:
        session.rollback()
        session.close()
        runtime.engine.dispose()


def test_lexical_retrieval_ranks_top_k_stably_and_reuses_shared_scope(
    lexical_fixture: LexicalFixture,
) -> None:
    response = lexical_fixture.service(candidate_count=3).retrieve(
        lexical_fixture.reader,
        RetrievalRequest(query="亮度"),
    )

    assert [result.identity.chunk_id for result in response.results] == [
        lexical_fixture.expected_ids["rank_high"],
        lexical_fixture.expected_ids["rank_mid"],
        lexical_fixture.expected_ids["tie_low"],
    ]
    returned_ids = {result.identity.chunk_id for result in response.results}
    assert lexical_fixture.expected_ids["denied"] not in returned_ids
    assert lexical_fixture.expected_ids["old_builder"] not in returned_ids
    scores = [
        result.scores.lexical.score
        for result in response.results
        if result.scores.lexical is not None
    ]
    assert scores == sorted(scores, reverse=True)


@pytest.mark.parametrize(
    "query",
    ["蘑菇灯", "brightness", "LR-TL-MUSH-OR01", "X200", "220V", "5.2"],
)
def test_lexical_retrieval_supports_versioned_chinese_and_identifiers(
    lexical_fixture: LexicalFixture,
    query: str,
) -> None:
    response = lexical_fixture.service().retrieve(
        lexical_fixture.reader,
        RetrievalRequest(query=query),
    )

    assert response.results
    assert response.fts_identity is not None
    assert response.fts_identity.builder_version == FTS_BUILDER_VERSION


def test_lexical_retrieval_returns_empty_for_missing_term(
    lexical_fixture: LexicalFixture,
) -> None:
    response = lexical_fixture.service().retrieve(
        lexical_fixture.reader,
        RetrievalRequest(query="完全不存在的海王星词条"),
    )

    assert response.results == []


def test_lexical_sql_filters_before_ranking_and_limit(
    lexical_fixture: LexicalFixture,
) -> None:
    repository = RetrievalRepository(lexical_fixture.session)
    statement = repository.lexical_candidates_statement(
        lexical_fixture.reader,
        lexical_tsquery="亮度 | 蘑菇灯",
        fts_builder_version=FTS_BUILDER_VERSION,
        limit=3,
    )
    compiled = str(statement.compile()).upper()

    assert "DOCUMENT_ACL" in compiled
    assert "FTS_BUILDER_VERSION" in compiled
    assert "@@" in compiled
    assert "TS_RANK_CD" in compiled
    assert "EMBEDDING <=>" not in compiled
    assert (
        compiled.index("WHERE") < compiled.index("ORDER BY") < compiled.index("LIMIT")
    )


def test_lexical_generated_vector_has_compatible_gin_index(
    lexical_fixture: LexicalFixture,
) -> None:
    lexical_fixture.session.execute(text("SET LOCAL enable_seqscan = off"))
    plan = lexical_fixture.session.execute(
        text(
            "EXPLAIN SELECT id FROM document_chunks "
            "WHERE search_vector @@ to_tsquery('simple', :query)"
        ),
        {"query": "亮度"},
    ).scalars()

    assert any("ix_document_chunks_search_vector_gin" in line for line in plan)

from __future__ import annotations

import hashlib
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.session import DatabaseRuntime, create_database_runtime
from app.models.identity import Role, Tenant, User
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
from app.services.retrieval.lexical_text import FtsTextPurpose, build_fts_text

_BASE_TIME = datetime(2026, 9, 1, 9, 0, tzinfo=UTC)


class RetrievalScopeFixture:
    def __init__(
        self,
        runtime: DatabaseRuntime,
        session: Session,
        users: dict[str, CurrentUser],
        expected: dict[str, UUID],
    ) -> None:
        self.runtime = runtime
        self.session = session
        self.users = users
        self.expected = expected

    def candidate_ids(self, user_label: str) -> set[UUID]:
        repository = RetrievalRepository(self.session, statement_timeout_ms=2000)
        rows = self.session.execute(
            repository.authorized_active_chunks_statement(self.users[user_label])
        ).all()
        return {row.DocumentChunk.id for row in rows}


def _current_user(
    *,
    user_id: UUID,
    tenant_id: UUID,
    label: str,
    roles: list[str],
    markets: list[str],
) -> CurrentUser:
    return CurrentUser.model_validate(
        {
            "user_id": user_id,
            "tenant_id": tenant_id,
            "email": f"{label}@m2163.example.com",
            "display_name": label,
            "roles": roles,
            "market_scopes": markets,
            "synthetic_data": True,
        }
    )


def _sha256(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _add_document(
    session: Session,
    *,
    tenant_id: UUID,
    owner_id: UUID,
    label: str,
    deleted: bool = False,
) -> Document:
    document = Document(
        id=uuid4(),
        tenant_id=tenant_id,
        owner_user_id=owner_id,
        title=f"M2-16.3 {label}",
        document_type="product_manual",
        language="zh-CN",
        market="DE",
        access_level="restricted",
        created_at=_BASE_TIME,
        deleted_at=_BASE_TIME + timedelta(minutes=20) if deleted else None,
    )
    session.add(document)
    session.flush()
    return document


def _add_indexed_version(
    session: Session,
    *,
    document: Document,
    owner_id: UUID,
    label: str,
    version_no: int = 1,
    index_status: str = "ready",
    activate_version: bool = True,
    activate_index: bool = True,
    file_deleted: bool = False,
) -> tuple[DocumentVersion, DocumentIndexSet, DocumentChunk]:
    file_id = uuid4()
    version_id = uuid4()
    chunk_set_id = uuid4()
    index_set_id = uuid4()
    source_hash = _sha256(f"source:{label}")
    file_row = StoredFile(
        id=file_id,
        tenant_id=document.tenant_id,
        owner_user_id=owner_id,
        original_name=f"{label}.pdf",
        storage_key=(f"{document.tenant_id}/uploads/2026/09/{file_id}.pdf"),
        extension=".pdf",
        mime_type="application/pdf",
        size_bytes=128,
        sha256=source_hash,
        category="uploads",
        status="soft_deleted" if file_deleted else "ready",
        created_at=_BASE_TIME,
        deleted_at=_BASE_TIME + timedelta(minutes=20) if file_deleted else None,
    )
    session.add(file_row)
    session.flush()
    version = DocumentVersion(
        id=version_id,
        tenant_id=document.tenant_id,
        document_id=document.id,
        file_id=file_id,
        version_no=version_no,
        content_hash=source_hash,
        parser_name="native_pdf",
        parser_version="m2-native-pdf-v1",
        parsed_storage_key=(f"{document.tenant_id}/parsed/2026/09/{version_id}.json"),
        parse_status="ready",
        index_status=index_status,
        created_at=_BASE_TIME,
    )
    session.add(version)
    session.flush()
    chunk_set = DocumentChunkSet(
        id=chunk_set_id,
        tenant_id=document.tenant_id,
        document_id=document.id,
        document_version_id=version.id,
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
        chunk_storage_key=(f"{document.tenant_id}/chunks/2026/09/{chunk_set_id}.json"),
        chunk_count=1,
        text_chunk_count=1,
        table_chunk_count=0,
        total_token_count=10,
        excluded_span_count=0,
        created_at=_BASE_TIME,
        started_at=_BASE_TIME + timedelta(seconds=1),
        completed_at=_BASE_TIME + timedelta(seconds=2),
    )
    session.add(chunk_set)
    session.flush()
    index_identity_hash = _sha256(f"index-identity:{label}")
    index_set = DocumentIndexSet(
        id=index_set_id,
        tenant_id=document.tenant_id,
        document_id=document.id,
        document_version_id=version.id,
        document_chunk_set_id=chunk_set.id,
        index_schema_version="m2-document-index-set-v1",
        embedding_identity_json={"label": label},
        embedding_identity_sha256=index_identity_hash,
        embedding_model="fake/m2-deterministic",
        embedding_version="m2-fake-v1",
        embedding_purpose="document",
        fts_builder_version="m2-fts-jieba-search-v1",
        status=index_status,
        attempt_count=0 if index_status == "pending" else 1,
        chunk_count=1 if index_status == "ready" else None,
        text_chunk_count=1 if index_status == "ready" else None,
        table_chunk_count=0 if index_status == "ready" else None,
        total_token_count=10 if index_status == "ready" else None,
        error_message="文档索引失败" if index_status == "failed" else None,
        created_at=_BASE_TIME,
        started_at=(
            None if index_status == "pending" else _BASE_TIME + timedelta(seconds=3)
        ),
        completed_at=(
            _BASE_TIME + timedelta(seconds=4)
            if index_status in {"ready", "failed"}
            else None
        ),
    )
    session.add(index_set)
    session.flush()
    body_text = f"{label}候选内容"
    chunk = DocumentChunk(
        id=uuid4(),
        tenant_id=document.tenant_id,
        document_id=document.id,
        document_version_id=version.id,
        document_chunk_set_id=chunk_set.id,
        document_index_set_id=index_set.id,
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
        source_spans=[{"block_id": "b000001"}],
        bounding_boxes=[],
        overlap_json=None,
        table_json=None,
        warnings=[],
        embedding=[1.0] + [0.0] * 1023,
        embedding_model="fake/m2-deterministic",
        embedding_version="m2-fake-v1",
        embedding_cache_key=f"sha256:{_sha256(f'embedding:{label}')}",
        created_at=_BASE_TIME,
    )
    session.add(chunk)
    session.flush()
    if activate_index and index_status == "ready":
        version.active_index_set_id = index_set.id
    if activate_version:
        document.active_version_id = version.id
    session.flush()
    return version, index_set, chunk


def _add_ready_index_set(
    session: Session,
    *,
    version: DocumentVersion,
    chunk_set: DocumentChunkSet,
    label: str,
) -> tuple[DocumentIndexSet, DocumentChunk]:
    """Add another ready Index Set to the same Version and Chunk Set."""
    index_set = DocumentIndexSet(
        id=uuid4(),
        tenant_id=version.tenant_id,
        document_id=version.document_id,
        document_version_id=version.id,
        document_chunk_set_id=chunk_set.id,
        index_schema_version="m2-document-index-set-v1",
        embedding_identity_json={"label": label},
        embedding_identity_sha256=_sha256(f"index-identity:{label}"),
        embedding_model="fake/m2-deterministic",
        embedding_version="m2-fake-v1",
        embedding_purpose="document",
        fts_builder_version="m2-fts-jieba-search-v1",
        status="ready",
        attempt_count=1,
        chunk_count=1,
        text_chunk_count=1,
        table_chunk_count=0,
        total_token_count=10,
        created_at=_BASE_TIME,
        started_at=_BASE_TIME + timedelta(seconds=5),
        completed_at=_BASE_TIME + timedelta(seconds=6),
    )
    session.add(index_set)
    session.flush()
    body_text = f"{label}候选内容"
    chunk = DocumentChunk(
        id=uuid4(),
        tenant_id=version.tenant_id,
        document_id=version.document_id,
        document_version_id=version.id,
        document_chunk_set_id=chunk_set.id,
        document_index_set_id=index_set.id,
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
        source_spans=[{"block_id": "b000001"}],
        bounding_boxes=[],
        overlap_json=None,
        table_json=None,
        warnings=[],
        embedding=[1.0] + [0.0] * 1023,
        embedding_model="fake/m2-deterministic",
        embedding_version="m2-fake-v1",
        embedding_cache_key=f"sha256:{_sha256(f'embedding:{label}')}",
        created_at=_BASE_TIME,
    )
    session.add(chunk)
    session.flush()
    return index_set, chunk


def _grant_acl(
    session: Session,
    *,
    document: Document,
    subject_type: str,
    role_name: str | None = None,
    user_id: UUID | None = None,
    market_code: str | None = None,
) -> None:
    session.add(
        DocumentAcl(
            id=uuid4(),
            tenant_id=document.tenant_id,
            document_id=document.id,
            subject_type=subject_type,
            role_name=role_name,
            user_id=user_id,
            market_code=market_code,
            permission="read",
        )
    )
    session.flush()


@pytest.fixture
def retrieval_scope_fixture() -> Generator[RetrievalScopeFixture, None, None]:
    settings = Settings(_env_file=".env.example", app_env="test")  # type: ignore[call-arg]
    command.upgrade(Config("alembic.ini"), "head")
    runtime = create_database_runtime(settings)
    session = runtime.session_factory()
    tenant_id = uuid4()
    other_tenant_id = uuid4()
    user_ids = {
        "owner": uuid4(),
        "reader": uuid4(),
        "company_owner": uuid4(),
        "other_tenant": uuid4(),
    }
    users = {
        "owner": _current_user(
            user_id=user_ids["owner"],
            tenant_id=tenant_id,
            label="owner",
            roles=["product_scout"],
            markets=["DE"],
        ),
        "reader": _current_user(
            user_id=user_ids["reader"],
            tenant_id=tenant_id,
            label="reader",
            roles=["amazon_operator"],
            markets=["DE"],
        ),
        "company_owner": _current_user(
            user_id=user_ids["company_owner"],
            tenant_id=tenant_id,
            label="company-owner",
            roles=["company_owner"],
            markets=["DE", "FR"],
        ),
        "other_tenant": _current_user(
            user_id=user_ids["other_tenant"],
            tenant_id=other_tenant_id,
            label="other-tenant",
            roles=["company_owner"],
            markets=["DE", "FR"],
        ),
    }
    expected: dict[str, UUID] = {}
    try:
        session.add_all(
            [
                Tenant(id=tenant_id, name="M2-16.3 retrieval tenant"),
                Tenant(id=other_tenant_id, name="M2-16.3 other tenant"),
            ]
        )
        session.flush()
        for label, user in users.items():
            session.add(
                User(
                    id=user.user_id,
                    tenant_id=user.tenant_id,
                    email=user.email,
                    display_name=label,
                    password_hash="$argon2id$m2163-synthetic-only",
                )
            )
        session.flush()
        for role_name in ("company_owner", "product_scout", "amazon_operator"):
            session.execute(
                postgresql_insert(Role)
                .values(id=uuid4(), name=role_name)
                .on_conflict_do_nothing(index_elements=["name"])
            )

        def indexed_document(
            label: str,
            *,
            owner_id: UUID = user_ids["owner"],
            indexed_tenant_id: UUID = tenant_id,
            **version_options: object,
        ) -> tuple[Document, DocumentChunk]:
            document = _add_document(
                session,
                tenant_id=indexed_tenant_id,
                owner_id=owner_id,
                label=label,
                deleted=bool(version_options.pop("document_deleted", False)),
            )
            _version, _index_set, chunk = _add_indexed_version(
                session,
                document=document,
                owner_id=owner_id,
                label=label,
                **version_options,  # type: ignore[arg-type]
            )
            expected[label] = chunk.id
            return document, chunk

        indexed_document("owner", owner_id=user_ids["reader"])
        user_document, _ = indexed_document("user_acl")
        _grant_acl(
            session,
            document=user_document,
            subject_type="user",
            user_id=user_ids["reader"],
        )
        role_document, _ = indexed_document("role_acl")
        _grant_acl(
            session,
            document=role_document,
            subject_type="role",
            role_name="amazon_operator",
        )
        market_document, _ = indexed_document("market_acl")
        _grant_acl(
            session,
            document=market_document,
            subject_type="market",
            market_code="DE",
        )
        mismatch_document, _ = indexed_document("market_mismatch")
        _grant_acl(
            session,
            document=mismatch_document,
            subject_type="market",
            market_code="FR",
        )
        indexed_document("no_acl")
        indexed_document(
            "cross_tenant",
            owner_id=user_ids["other_tenant"],
            indexed_tenant_id=other_tenant_id,
        )

        versioned_document = _add_document(
            session,
            tenant_id=tenant_id,
            owner_id=user_ids["owner"],
            label="version_boundary",
        )
        _old_version, _old_index, old_version_chunk = _add_indexed_version(
            session,
            document=versioned_document,
            owner_id=user_ids["owner"],
            label="old_version",
            version_no=1,
            activate_version=False,
        )
        _new_version, _new_index, active_version_chunk = _add_indexed_version(
            session,
            document=versioned_document,
            owner_id=user_ids["owner"],
            label="active_version",
            version_no=2,
        )
        expected["old_version"] = old_version_chunk.id
        expected["active_version"] = active_version_chunk.id

        index_document = _add_document(
            session,
            tenant_id=tenant_id,
            owner_id=user_ids["owner"],
            label="index_boundary",
        )
        index_version, _old_set, old_index_chunk = _add_indexed_version(
            session,
            document=index_document,
            owner_id=user_ids["owner"],
            label="old_index_set",
            activate_index=False,
        )
        chunk_set = session.get(
            DocumentChunkSet,
            old_index_chunk.document_chunk_set_id,
        )
        assert chunk_set is not None
        _new_set, active_index_chunk = _add_ready_index_set(
            session,
            version=index_version,
            chunk_set=chunk_set,
            label="active_index_set",
        )
        index_version.active_index_set_id = _new_set.id
        index_document.active_version_id = index_version.id
        session.flush()
        expected["old_index_set"] = old_index_chunk.id
        expected["active_index_set"] = active_index_chunk.id

        indexed_document("pending_index_set", index_status="pending")
        indexed_document("failed_index_set", index_status="failed")
        indexed_document("soft_deleted_document", document_deleted=True)
        indexed_document("soft_deleted_file", file_deleted=True)
        session.flush()
        yield RetrievalScopeFixture(runtime, session, users, expected)
    finally:
        session.rollback()
        session.close()
        runtime.engine.dispose()


def test_owner_company_owner_and_all_acl_subjects_share_one_candidate_boundary(
    retrieval_scope_fixture: RetrievalScopeFixture,
) -> None:
    fixture = retrieval_scope_fixture
    reader_ids = fixture.candidate_ids("reader")

    assert {
        fixture.expected["owner"],
        fixture.expected["user_acl"],
        fixture.expected["role_acl"],
        fixture.expected["market_acl"],
    } <= reader_ids
    assert fixture.expected["no_acl"] not in reader_ids
    assert fixture.expected["market_mismatch"] not in reader_ids

    company_owner_ids = fixture.candidate_ids("company_owner")
    assert fixture.expected["no_acl"] in company_owner_ids
    assert fixture.expected["market_mismatch"] in company_owner_ids

    other_tenant_ids = fixture.candidate_ids("other_tenant")
    assert fixture.expected["cross_tenant"] in other_tenant_ids
    assert fixture.expected["owner"] not in other_tenant_ids


def test_tenant_active_ready_and_soft_delete_filters_return_zero_candidates(
    retrieval_scope_fixture: RetrievalScopeFixture,
) -> None:
    fixture = retrieval_scope_fixture
    company_owner_ids = fixture.candidate_ids("company_owner")

    assert fixture.expected["active_version"] in company_owner_ids
    assert fixture.expected["active_index_set"] in company_owner_ids
    for excluded_label in (
        "cross_tenant",
        "old_version",
        "old_index_set",
        "pending_index_set",
        "failed_index_set",
        "soft_deleted_document",
        "soft_deleted_file",
    ):
        assert fixture.expected[excluded_label] not in company_owner_ids


def test_candidate_boundary_accepts_only_trusted_current_user_and_has_no_ranking(
    retrieval_scope_fixture: RetrievalScopeFixture,
) -> None:
    fixture = retrieval_scope_fixture
    repository = RetrievalRepository(fixture.session, statement_timeout_ms=2000)

    statement = repository.authorized_active_chunks_statement(fixture.users["reader"])
    compiled = str(statement.compile()).upper()

    assert "ORDER BY" not in compiled
    assert " LIMIT " not in compiled
    assert "DOCUMENT_ACL" in compiled
    assert "ACTIVE_VERSION_ID" in compiled
    assert "ACTIVE_INDEX_SET_ID" in compiled
    assert (
        fixture.session.scalar(text("SELECT current_setting('statement_timeout')"))
        == "2s"
    )
    with pytest.raises(TypeError):
        repository.authorized_active_chunks_statement(
            {  # type: ignore[arg-type]
                "tenant_id": str(fixture.users["other_tenant"].tenant_id)
            }
        )

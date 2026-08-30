from __future__ import annotations

from collections.abc import Generator
from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import (
    DocumentAclConflictError,
    DocumentNotFoundError,
    DocumentStateConflictError,
    DocumentVersionConflictError,
    FileNotFoundError,
    FileStateConflictError,
)
from app.db.session import create_database_runtime
from app.models.identity import Role, Tenant, User
from app.repositories.documents import DocumentRepository
from app.repositories.files import FileRepository
from app.schemas.auth import CurrentUser
from app.schemas.files import FileRegistrationInput, FileResponse, FileStateUpdate
from app.schemas.knowledge import (
    DocumentAclGrantInput,
    DocumentCreateInput,
    DocumentIndexStateUpdate,
    DocumentParseStateUpdate,
    DocumentVersionCreateInput,
)
from app.services.documents import DocumentService
from app.services.files import FileService
from app.services.storage import StoredObject


@dataclass(slots=True)
class KnowledgeFixture:
    session: Session
    files: FileService
    documents: DocumentService
    users: dict[str, CurrentUser]


def current_user(
    *,
    user_id: UUID,
    tenant_id: UUID,
    email: str,
    roles: list[str],
    markets: list[str],
) -> CurrentUser:
    return CurrentUser.model_validate(
        {
            "user_id": user_id,
            "tenant_id": tenant_id,
            "email": email,
            "display_name": email.split("@", maxsplit=1)[0],
            "roles": roles,
            "market_scopes": markets,
            "synthetic_data": True,
        }
    )


@pytest.fixture
def knowledge_fixture(
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[KnowledgeFixture, None, None]:
    settings = Settings(  # type: ignore[call-arg]
        _env_file=".env.example",
        app_env="test",
    )
    monkeypatch.setenv("DATABASE_URL", settings.database_url)
    command.upgrade(Config("alembic.ini"), "head")
    runtime = create_database_runtime(settings)
    session = runtime.session_factory()
    tenant_id = uuid4()
    other_tenant_id = uuid4()
    identities = {
        "owner": (tenant_id, "owner-m205@example.com", ["amazon_operator"], ["DE"]),
        "reader": (tenant_id, "reader-m205@example.com", ["amazon_operator"], ["DE"]),
        "scout": (tenant_id, "scout-m205@example.com", ["product_scout"], ["DE"]),
        "de_market": (
            tenant_id,
            "de-market-m205@example.com",
            ["amazon_operator"],
            ["DE"],
        ),
        "fr_market": (
            tenant_id,
            "fr-market-m205@example.com",
            ["amazon_operator"],
            ["FR"],
        ),
        "company_owner": (
            tenant_id,
            "company-owner-m205@example.com",
            ["company_owner"],
            ["DE", "FR"],
        ),
        "other_tenant": (
            other_tenant_id,
            "other-tenant-m205@example.com",
            ["company_owner"],
            ["DE", "FR"],
        ),
    }
    users: dict[str, CurrentUser] = {}
    try:
        session.add_all(
            [
                Tenant(id=tenant_id, name="M2-05 tenant"),
                Tenant(id=other_tenant_id, name="M2-05 other tenant"),
            ]
        )
        session.flush()
        for label, (identity_tenant, email, roles, markets) in identities.items():
            user_id = uuid4()
            session.add(
                User(
                    id=user_id,
                    tenant_id=identity_tenant,
                    email=email,
                    display_name=label,
                    password_hash="$argon2id$synthetic-only-hash",
                )
            )
            users[label] = current_user(
                user_id=user_id,
                tenant_id=identity_tenant,
                email=email,
                roles=roles,
                markets=markets,
            )
        session.flush()
        session.execute(
            postgresql_insert(Role)
            .values(id=uuid4(), name="product_scout")
            .on_conflict_do_nothing(index_elements=["name"])
        )
        file_service = FileService(
            FileRepository(session, settings.database_statement_timeout_ms)
        )
        document_service = DocumentService(
            DocumentRepository(session, settings.database_statement_timeout_ms),
            file_service,
        )
        yield KnowledgeFixture(session, file_service, document_service, users)
    finally:
        session.rollback()
        session.close()
        runtime.engine.dispose()


def register_file(
    fixture: KnowledgeFixture,
    user: CurrentUser,
    *,
    hash_character: str,
) -> tuple[UUID, FileResponse]:
    file_id = uuid4()
    key = f"{user.tenant_id}/uploads/2026/08/{file_id}.pdf"
    response = fixture.files.register_file(
        user,
        file_id=file_id,
        request=FileRegistrationInput(
            original_name=f"synthetic-{file_id}.pdf",
            extension=".pdf",
        ),
        stored=StoredObject(
            key=key,
            size_bytes=128,
            sha256=hash_character * 64,
            content_type="application/pdf",
        ),
    )
    return file_id, response


def create_document(
    fixture: KnowledgeFixture,
    user: CurrentUser,
    *,
    hash_character: str = "a",
) -> tuple[UUID, UUID, UUID]:
    file_id, _response = register_file(fixture, user, hash_character=hash_character)
    detail = fixture.documents.create_document(
        user,
        DocumentCreateInput(
            file_id=file_id,
            title="M2-05合成产品说明书",
            document_type="product_manual",
            language="zh-CN",
            market="DE",
        ),
    )
    return file_id, detail.document_id, detail.versions[0].version_id


def test_owner_role_user_market_and_tenant_permissions_are_applied_in_sql(
    knowledge_fixture: KnowledgeFixture,
) -> None:
    fixture = knowledge_fixture
    owner = fixture.users["owner"]
    file_id, document_id, _version_id = create_document(fixture, owner)

    assert fixture.documents.get_document(owner, document_id).document_id == document_id
    with pytest.raises(DocumentNotFoundError):
        fixture.documents.get_document(fixture.users["reader"], document_id)
    with pytest.raises(FileNotFoundError):
        fixture.files.get_file(fixture.users["reader"], file_id)

    fixture.documents.grant_acl(
        owner,
        document_id,
        DocumentAclGrantInput(
            subject_type="user",
            user_id=fixture.users["reader"].user_id,
        ),
    )
    fixture.documents.grant_acl(
        owner,
        document_id,
        DocumentAclGrantInput(subject_type="role", role_name="product_scout"),
    )
    fixture.documents.grant_acl(
        owner,
        document_id,
        DocumentAclGrantInput(subject_type="market", market_code="DE"),
    )

    reader_detail = fixture.documents.get_document(fixture.users["reader"], document_id)
    assert reader_detail.acl == []
    assert fixture.files.get_file(fixture.users["reader"], file_id).file_id == file_id
    assert (
        fixture.documents.get_document(fixture.users["scout"], document_id).document_id
        == document_id
    )
    assert (
        fixture.documents.get_document(
            fixture.users["de_market"], document_id
        ).document_id
        == document_id
    )
    with pytest.raises(DocumentNotFoundError):
        fixture.documents.get_document(fixture.users["fr_market"], document_id)
    assert (
        fixture.documents.get_document(
            fixture.users["company_owner"], document_id
        ).document_id
        == document_id
    )
    with pytest.raises(DocumentNotFoundError):
        fixture.documents.get_document(fixture.users["other_tenant"], document_id)

    assert [
        item.file_id for item in fixture.files.list_files(fixture.users["reader"]).items
    ] == [file_id]


def test_only_owner_or_company_owner_can_manage_acl_and_invalid_subject_is_hidden(
    knowledge_fixture: KnowledgeFixture,
) -> None:
    fixture = knowledge_fixture
    owner = fixture.users["owner"]
    _file_id, document_id, _version_id = create_document(fixture, owner)

    with pytest.raises(DocumentNotFoundError):
        fixture.documents.grant_acl(
            fixture.users["reader"],
            document_id,
            DocumentAclGrantInput(subject_type="market", market_code="DE"),
        )

    request = DocumentAclGrantInput(subject_type="market", market_code="DE")
    fixture.documents.grant_acl(owner, document_id, request)
    with pytest.raises(DocumentAclConflictError):
        fixture.documents.grant_acl(owner, document_id, request)

    with pytest.raises(DocumentAclConflictError):
        fixture.documents.grant_acl(
            owner,
            document_id,
            DocumentAclGrantInput(
                subject_type="user",
                user_id=fixture.users["other_tenant"].user_id,
            ),
        )

    company_grant = fixture.documents.grant_acl(
        fixture.users["company_owner"],
        document_id,
        DocumentAclGrantInput(subject_type="role", role_name="product_scout"),
    )
    assert company_grant.role_name == "product_scout"


def test_file_and_version_state_machines_require_ready_before_activation(
    knowledge_fixture: KnowledgeFixture,
) -> None:
    fixture = knowledge_fixture
    owner = fixture.users["owner"]
    file_id, document_id, version_id = create_document(fixture, owner)

    with pytest.raises(FileStateConflictError):
        fixture.files.transition_file(
            owner,
            file_id,
            FileStateUpdate(status="ready"),
        )
    with pytest.raises(DocumentStateConflictError):
        fixture.documents.transition_index_state(
            owner,
            document_id,
            version_id,
            DocumentIndexStateUpdate(status="indexing"),
        )
    with pytest.raises(DocumentStateConflictError):
        fixture.documents.activate_version(owner, document_id, version_id)

    fixture.files.transition_file(
        owner,
        file_id,
        FileStateUpdate(status="validating"),
    )
    fixture.documents.transition_parse_state(
        owner,
        document_id,
        version_id,
        DocumentParseStateUpdate(status="parsing"),
    )
    fixture.files.transition_file(
        owner,
        file_id,
        FileStateUpdate(status="parsing"),
    )
    parsed_key = f"{owner.tenant_id}/parsed/2026/08/{version_id}.json"
    parsed = fixture.documents.transition_parse_state(
        owner,
        document_id,
        version_id,
        DocumentParseStateUpdate(
            status="ready",
            parser_name="pdf",
            parser_version="1.0.0",
            parsed_storage_key=parsed_key,
        ),
    )
    assert parsed.parse_status == "ready"
    assert "parsed_storage_key" not in parsed.model_dump()

    fixture.files.transition_file(
        owner,
        file_id,
        FileStateUpdate(status="indexing"),
    )
    fixture.documents.transition_index_state(
        owner,
        document_id,
        version_id,
        DocumentIndexStateUpdate(status="indexing"),
    )
    fixture.documents.transition_index_state(
        owner,
        document_id,
        version_id,
        DocumentIndexStateUpdate(status="ready"),
    )
    fixture.files.transition_file(
        owner,
        file_id,
        FileStateUpdate(status="ready"),
    )
    active = fixture.documents.activate_version(owner, document_id, version_id)
    assert active.active_version_id == version_id


def test_duplicate_hash_and_soft_delete_are_safe_and_non_leaking(
    knowledge_fixture: KnowledgeFixture,
) -> None:
    fixture = knowledge_fixture
    owner = fixture.users["owner"]
    file_id, document_id, _version_id = create_document(
        fixture, owner, hash_character="d"
    )

    next_file_id, _response = register_file(
        fixture,
        owner,
        hash_character="c",
    )
    next_version = fixture.documents.add_version(
        owner,
        document_id,
        DocumentVersionCreateInput(file_id=next_file_id),
    )
    assert next_version.version_no == 2

    duplicate_file_id, _response = register_file(
        fixture,
        owner,
        hash_character="d",
    )
    with pytest.raises(DocumentVersionConflictError):
        fixture.documents.add_version(
            owner,
            document_id,
            DocumentVersionCreateInput(file_id=duplicate_file_id),
        )

    fixture.files.transition_file(
        owner,
        file_id,
        FileStateUpdate(status="soft_deleted"),
    )
    with pytest.raises(FileNotFoundError):
        fixture.files.get_file(owner, file_id)
    assert fixture.documents.get_document(owner, document_id).document_id == document_id

    only_file_id, only_document_id, _version_id = create_document(
        fixture,
        owner,
        hash_character="b",
    )
    fixture.files.transition_file(
        owner,
        only_file_id,
        FileStateUpdate(status="soft_deleted"),
    )
    with pytest.raises(DocumentNotFoundError):
        fixture.documents.get_document(owner, only_document_id)

    document_file_id, deleted_document_id, _version_id = create_document(
        fixture,
        owner,
        hash_character="f",
    )
    fixture.documents.soft_delete_document(owner, deleted_document_id)
    with pytest.raises(DocumentNotFoundError):
        fixture.documents.get_document(owner, deleted_document_id)
    with pytest.raises(FileNotFoundError):
        fixture.files.get_file(owner, document_file_id)

    standalone_id, _response = register_file(fixture, owner, hash_character="e")
    failed = fixture.files.transition_file(
        owner,
        standalone_id,
        FileStateUpdate(status="failed", error_message="合成验证失败"),
    )
    assert failed.error_message == "合成验证失败"
    retried = fixture.files.transition_file(
        owner,
        standalone_id,
        FileStateUpdate(status="validating"),
    )
    assert retried.error_message is None

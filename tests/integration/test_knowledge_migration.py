from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, insert, inspect, update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.exc import IntegrityError

from app.core.config import Settings
from app.db.base import Base
from app.db.session import create_database_runtime
from app.models.identity import Role, Tenant, User
from app.models.knowledge import Document, DocumentAcl, DocumentVersion, StoredFile


@pytest.fixture
def postgres_settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    settings = Settings(  # type: ignore[call-arg]
        _env_file=".env.example",
        app_env="test",
    )
    monkeypatch.setenv("DATABASE_URL", settings.database_url)
    return settings


@pytest.fixture
def postgres_engine(postgres_settings: Settings) -> Generator[Engine, None, None]:
    runtime = create_database_runtime(postgres_settings)
    yield runtime.engine
    runtime.engine.dispose()


def alembic_config() -> Config:
    return Config("alembic.ini")


def storage_key(tenant_id: UUID, file_id: UUID, extension: str = ".pdf") -> str:
    return f"{tenant_id}/uploads/2026/08/{file_id}{extension}"


def file_values(
    *,
    tenant_id: UUID,
    owner_user_id: UUID,
    file_id: UUID,
    sha_character: str,
    status: str = "uploaded",
    deleted_at: datetime | None = None,
) -> dict[str, object]:
    return {
        "id": file_id,
        "tenant_id": tenant_id,
        "owner_user_id": owner_user_id,
        "original_name": f"synthetic-{file_id}.pdf",
        "storage_key": storage_key(tenant_id, file_id),
        "extension": ".pdf",
        "mime_type": "application/pdf",
        "size_bytes": 128,
        "sha256": sha_character * 64,
        "category": "uploads",
        "status": status,
        "deleted_at": deleted_at,
    }


def document_values(
    *,
    tenant_id: UUID,
    owner_user_id: UUID,
    document_id: UUID,
) -> dict[str, object]:
    return {
        "id": document_id,
        "tenant_id": tenant_id,
        "owner_user_id": owner_user_id,
        "title": "合成产品说明书",
        "document_type": "product_manual",
        "language": "zh-CN",
        "market": "DE",
        "access_level": "private",
    }


def version_values(
    *,
    tenant_id: UUID,
    document_id: UUID,
    file_id: UUID,
    version_id: UUID,
    version_no: int,
    hash_character: str,
) -> dict[str, object]:
    return {
        "id": version_id,
        "tenant_id": tenant_id,
        "document_id": document_id,
        "file_id": file_id,
        "version_no": version_no,
        "content_hash": hash_character * 64,
        "parse_status": "pending",
        "index_status": "pending",
    }


def test_knowledge_migration_down_up(postgres_settings: Settings) -> None:
    del postgres_settings
    config = alembic_config()
    knowledge_tables = {"document_acl", "document_versions", "documents", "files"}
    prior_tables = {"agent_runs", "evidences", "tenants", "users"}

    try:
        command.downgrade(config, "20260828_0003")
        runtime = create_database_runtime(Settings())
        try:
            table_names = set(inspect(runtime.engine).get_table_names())
            assert knowledge_tables.isdisjoint(table_names)
            assert prior_tables <= table_names
        finally:
            runtime.engine.dispose()

        command.upgrade(config, "20260829_0004")
        runtime = create_database_runtime(Settings())
        try:
            assert knowledge_tables <= set(inspect(runtime.engine).get_table_names())
        finally:
            runtime.engine.dispose()

        command.downgrade(config, "20260828_0003")
        command.upgrade(config, "20260829_0004")
    finally:
        command.upgrade(config, "head")


def test_database_enforces_knowledge_tenant_version_acl_and_delete_boundaries(
    postgres_engine: Engine,
) -> None:
    command.upgrade(alembic_config(), "head")
    tenant_id = uuid4()
    other_tenant_id = uuid4()
    owner_user_id = uuid4()
    granted_user_id = uuid4()
    other_user_id = uuid4()
    document_id = uuid4()
    other_document_id = uuid4()
    file_id = uuid4()
    other_file_id = uuid4()
    version_id = uuid4()
    other_version_id = uuid4()
    created_at = datetime(2026, 8, 29, 8, 0, tzinfo=UTC)

    with postgres_engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(
                insert(Tenant),
                [
                    {"id": tenant_id, "name": "M2 knowledge tenant"},
                    {"id": other_tenant_id, "name": "M2 other tenant"},
                ],
            )
            connection.execute(
                insert(User),
                [
                    {
                        "id": owner_user_id,
                        "tenant_id": tenant_id,
                        "email": "m2-owner@example.com",
                        "display_name": "M2 Owner",
                        "password_hash": "$argon2id$synthetic-only-hash",
                    },
                    {
                        "id": granted_user_id,
                        "tenant_id": tenant_id,
                        "email": "m2-reader@example.com",
                        "display_name": "M2 Reader",
                        "password_hash": "$argon2id$synthetic-only-hash",
                    },
                    {
                        "id": other_user_id,
                        "tenant_id": other_tenant_id,
                        "email": "m2-other@example.com",
                        "display_name": "M2 Other",
                        "password_hash": "$argon2id$synthetic-only-hash",
                    },
                ],
            )
            connection.execute(
                postgresql_insert(Role)
                .values(id=uuid4(), name="company_owner")
                .on_conflict_do_nothing(index_elements=["name"])
            )
            connection.execute(
                insert(StoredFile).values(
                    **file_values(
                        tenant_id=tenant_id,
                        owner_user_id=owner_user_id,
                        file_id=file_id,
                        sha_character="a",
                    ),
                    created_at=created_at,
                )
            )
            connection.execute(
                insert(StoredFile).values(
                    **file_values(
                        tenant_id=other_tenant_id,
                        owner_user_id=other_user_id,
                        file_id=other_file_id,
                        sha_character="b",
                    ),
                    created_at=created_at,
                )
            )
            connection.execute(
                insert(Document),
                [
                    document_values(
                        tenant_id=tenant_id,
                        owner_user_id=owner_user_id,
                        document_id=document_id,
                    ),
                    document_values(
                        tenant_id=tenant_id,
                        owner_user_id=owner_user_id,
                        document_id=other_document_id,
                    ),
                ],
            )
            connection.execute(
                insert(DocumentVersion).values(
                    **version_values(
                        tenant_id=tenant_id,
                        document_id=document_id,
                        file_id=file_id,
                        version_id=version_id,
                        version_no=1,
                        hash_character="a",
                    )
                )
            )

            second_file_id = uuid4()
            connection.execute(
                insert(StoredFile).values(
                    **file_values(
                        tenant_id=tenant_id,
                        owner_user_id=owner_user_id,
                        file_id=second_file_id,
                        sha_character="c",
                    )
                )
            )
            connection.execute(
                insert(DocumentVersion).values(
                    **version_values(
                        tenant_id=tenant_id,
                        document_id=other_document_id,
                        file_id=second_file_id,
                        version_id=other_version_id,
                        version_no=1,
                        hash_character="c",
                    )
                )
            )
            connection.execute(
                update(Document)
                .where(Document.id == document_id)
                .values(active_version_id=version_id)
            )

            with pytest.raises(IntegrityError), connection.begin_nested():
                invalid_file_id = uuid4()
                connection.execute(
                    insert(StoredFile).values(
                        **file_values(
                            tenant_id=tenant_id,
                            owner_user_id=other_user_id,
                            file_id=invalid_file_id,
                            sha_character="d",
                        )
                    )
                )

            with pytest.raises(IntegrityError), connection.begin_nested():
                invalid_key_file_id = uuid4()
                invalid_key_file = file_values(
                    tenant_id=tenant_id,
                    owner_user_id=owner_user_id,
                    file_id=invalid_key_file_id,
                    sha_character="e",
                )
                invalid_key_file["storage_key"] = storage_key(
                    other_tenant_id,
                    invalid_key_file_id,
                )
                connection.execute(insert(StoredFile).values(**invalid_key_file))

            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(
                    insert(Document).values(
                        **document_values(
                            tenant_id=tenant_id,
                            owner_user_id=other_user_id,
                            document_id=uuid4(),
                        )
                    )
                )

            with pytest.raises(IntegrityError), connection.begin_nested():
                soft_deleted_file_id = uuid4()
                connection.execute(
                    insert(StoredFile).values(
                        **file_values(
                            tenant_id=tenant_id,
                            owner_user_id=owner_user_id,
                            file_id=soft_deleted_file_id,
                            sha_character="f",
                            status="soft_deleted",
                        )
                    )
                )

            third_file_id = uuid4()
            connection.execute(
                insert(StoredFile).values(
                    **file_values(
                        tenant_id=tenant_id,
                        owner_user_id=owner_user_id,
                        file_id=third_file_id,
                        sha_character="1",
                    )
                )
            )
            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(
                    insert(DocumentVersion).values(
                        **version_values(
                            tenant_id=tenant_id,
                            document_id=document_id,
                            file_id=third_file_id,
                            version_id=uuid4(),
                            version_no=1,
                            hash_character="1",
                        )
                    )
                )

            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(
                    insert(DocumentVersion).values(
                        **version_values(
                            tenant_id=tenant_id,
                            document_id=document_id,
                            file_id=other_file_id,
                            version_id=uuid4(),
                            version_no=2,
                            hash_character="5",
                        )
                    )
                )

            fourth_file_id = uuid4()
            connection.execute(
                insert(StoredFile).values(
                    **file_values(
                        tenant_id=tenant_id,
                        owner_user_id=owner_user_id,
                        file_id=fourth_file_id,
                        sha_character="2",
                    )
                )
            )
            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(
                    insert(DocumentVersion).values(
                        **version_values(
                            tenant_id=tenant_id,
                            document_id=document_id,
                            file_id=fourth_file_id,
                            version_id=uuid4(),
                            version_no=2,
                            hash_character="a",
                        )
                    )
                )

            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(
                    update(Document)
                    .where(Document.id == document_id)
                    .values(active_version_id=other_version_id)
                )

            connection.execute(
                insert(DocumentAcl).values(
                    id=uuid4(),
                    tenant_id=tenant_id,
                    document_id=document_id,
                    subject_type="user",
                    user_id=granted_user_id,
                )
            )
            connection.execute(
                insert(DocumentAcl).values(
                    id=uuid4(),
                    tenant_id=tenant_id,
                    document_id=document_id,
                    subject_type="role",
                    role_name="company_owner",
                )
            )
            connection.execute(
                insert(DocumentAcl).values(
                    id=uuid4(),
                    tenant_id=tenant_id,
                    document_id=document_id,
                    subject_type="market",
                    market_code="DE",
                )
            )

            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(
                    insert(DocumentAcl).values(
                        id=uuid4(),
                        tenant_id=tenant_id,
                        document_id=document_id,
                        subject_type="user",
                        user_id=granted_user_id,
                        market_code="DE",
                    )
                )

            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(
                    insert(DocumentAcl).values(
                        id=uuid4(),
                        tenant_id=tenant_id,
                        document_id=document_id,
                        subject_type="role",
                        role_name="not_a_role",
                    )
                )

            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(
                    insert(DocumentAcl).values(
                        id=uuid4(),
                        tenant_id=tenant_id,
                        document_id=document_id,
                        subject_type="user",
                        user_id=other_user_id,
                    )
                )

            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(
                    insert(DocumentAcl).values(
                        id=uuid4(),
                        tenant_id=tenant_id,
                        document_id=document_id,
                        subject_type="market",
                        market_code="DE",
                    )
                )

            with pytest.raises(IntegrityError), connection.begin_nested():
                invalid_ready_file_id = uuid4()
                connection.execute(
                    insert(StoredFile).values(
                        **file_values(
                            tenant_id=tenant_id,
                            owner_user_id=owner_user_id,
                            file_id=invalid_ready_file_id,
                            sha_character="3",
                        )
                    )
                )
                invalid_ready_version = version_values(
                    tenant_id=tenant_id,
                    document_id=document_id,
                    file_id=invalid_ready_file_id,
                    version_id=uuid4(),
                    version_no=2,
                    hash_character="3",
                )
                invalid_ready_version["index_status"] = "ready"
                connection.execute(
                    insert(DocumentVersion).values(**invalid_ready_version)
                )

            valid_deleted_file_id = uuid4()
            valid_deleted_file = file_values(
                tenant_id=tenant_id,
                owner_user_id=owner_user_id,
                file_id=valid_deleted_file_id,
                sha_character="4",
                status="soft_deleted",
                deleted_at=created_at + timedelta(minutes=1),
            )
            valid_deleted_file["error_message"] = "安全失败摘要可在软删除后保留"
            connection.execute(
                insert(StoredFile).values(
                    **valid_deleted_file,
                    created_at=created_at,
                )
            )
        finally:
            transaction.rollback()


def test_model_metadata_matches_applied_knowledge_tables(
    postgres_engine: Engine,
) -> None:
    command.upgrade(alembic_config(), "head")
    knowledge_tables = {"document_acl", "document_versions", "documents", "files"}

    assert knowledge_tables <= set(Base.metadata.tables)
    assert knowledge_tables <= set(inspect(postgres_engine).get_table_names())

from collections.abc import Generator
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, insert, inspect
from sqlalchemy.exc import IntegrityError

from app.core.config import Settings
from app.db.base import Base
from app.db.session import create_database_runtime
from app.models.identity import Role, Tenant, User, UserRole


@pytest.fixture
def postgres_settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    settings = Settings(_env_file=".env.example", app_env="test")
    monkeypatch.setenv("DATABASE_URL", settings.database_url)
    return settings


@pytest.fixture
def postgres_engine(postgres_settings: Settings) -> Generator[Engine, None, None]:
    runtime = create_database_runtime(postgres_settings)
    yield runtime.engine
    runtime.engine.dispose()


def alembic_config() -> Config:
    return Config("alembic.ini")


def test_identity_migration_up_down_up(postgres_settings: Settings) -> None:
    del postgres_settings
    config = alembic_config()
    expected_tables = {"alembic_version", "roles", "tenants", "user_roles", "users"}

    try:
        command.downgrade(config, "base")
        command.upgrade(config, "20260828_0001")
        runtime = create_database_runtime(Settings())
        try:
            assert set(inspect(runtime.engine).get_table_names()) == expected_tables
        finally:
            runtime.engine.dispose()

        command.downgrade(config, "base")
        runtime = create_database_runtime(Settings())
        try:
            assert set(inspect(runtime.engine).get_table_names()) == {"alembic_version"}
        finally:
            runtime.engine.dispose()

        command.upgrade(config, "20260828_0001")
        runtime = create_database_runtime(Settings())
        try:
            assert set(inspect(runtime.engine).get_table_names()) == expected_tables
        finally:
            runtime.engine.dispose()
    finally:
        command.upgrade(config, "head")


def test_database_rejects_invalid_identity_rows(postgres_engine: Engine) -> None:
    command.upgrade(alembic_config(), "head")
    tenant_id = uuid4()
    user_id = uuid4()
    role_id = uuid4()

    with postgres_engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(
                insert(Tenant).values(id=tenant_id, name="M1 constraint tenant")
            )
            connection.execute(
                insert(User).values(
                    id=user_id,
                    tenant_id=tenant_id,
                    email="operator@example.com",
                    display_name="Operator",
                    password_hash="$argon2id$demo-only-hash",
                )
            )
            connection.execute(insert(Role).values(id=role_id, name="amazon_operator"))

            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(
                    insert(User).values(
                        id=uuid4(),
                        tenant_id=tenant_id,
                        email="operator@example.com",
                        display_name="Duplicate",
                        password_hash="$argon2id$demo-only-hash",
                    )
                )

            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(
                    insert(User).values(
                        id=uuid4(),
                        tenant_id=tenant_id,
                        email="Uppercase@example.com",
                        display_name="Uppercase email",
                        password_hash="$argon2id$demo-only-hash",
                    )
                )

            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(
                    insert(User).values(
                        id=uuid4(),
                        tenant_id=tenant_id,
                        email="disabled-wrongly@example.com",
                        display_name="Invalid status",
                        password_hash="$argon2id$demo-only-hash",
                        status="locked",
                    )
                )

            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(
                    insert(Role).values(id=uuid4(), name="unapproved_role")
                )

            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(
                    insert(UserRole).values(
                        user_id=user_id,
                        role_id=role_id,
                        market_scopes=[],
                    )
                )

            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(
                    insert(UserRole).values(
                        user_id=user_id,
                        role_id=role_id,
                        market_scopes=["de"],
                    )
                )

            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(
                    insert(UserRole).values(
                        user_id=uuid4(),
                        role_id=role_id,
                        market_scopes=["DE"],
                    )
                )

            connection.execute(
                insert(UserRole).values(
                    user_id=user_id,
                    role_id=role_id,
                    market_scopes=["DE", "FR"],
                )
            )
        finally:
            transaction.rollback()


def test_model_metadata_matches_applied_migration(postgres_engine: Engine) -> None:
    command.upgrade(alembic_config(), "head")

    identity_tables = {
        "roles",
        "tenants",
        "user_roles",
        "users",
    }
    assert identity_tables <= set(Base.metadata.tables)
    assert identity_tables <= set(inspect(postgres_engine).get_table_names())

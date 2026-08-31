"""Alembic environment wired to the M1 Settings and model metadata."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import Settings
from app.db.base import Base
from app.models import (
    AgentRun,
    Document,
    DocumentAcl,
    DocumentChunk,
    DocumentChunkSet,
    DocumentIndexSet,
    DocumentVersion,
    Evidence,
    InventorySnapshot,
    Message,
    Product,
    ProductSpec,
    ProductVariant,
    Role,
    StoredFile,
    Tenant,
    Thread,
    ToolCall,
    User,
    UserRole,
    Warehouse,
)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Importing these classes registers their tables on Base.metadata.
_models = (
    Tenant,
    User,
    Role,
    UserRole,
    Product,
    ProductVariant,
    ProductSpec,
    Warehouse,
    InventorySnapshot,
    Thread,
    Message,
    AgentRun,
    ToolCall,
    Evidence,
    StoredFile,
    Document,
    DocumentVersion,
    DocumentChunkSet,
    DocumentIndexSet,
    DocumentChunk,
    DocumentAcl,
)
target_metadata = Base.metadata


def get_database_url() -> str:
    """Use application configuration without persisting credentials in Alembic."""

    return Settings().database_url


def run_migrations_offline() -> None:
    """Generate SQL without opening a database connection."""

    context.configure(
        url=get_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Apply migrations through a short-lived Alembic connection."""

    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = get_database_url()
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

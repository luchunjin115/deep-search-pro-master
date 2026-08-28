"""Create and verify the SQLAlchemy runtime used by the application."""

from dataclasses import dataclass

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings


class DatabaseConnectionError(RuntimeError):
    """Public, credential-safe error raised when PostgreSQL is unavailable."""


@dataclass(frozen=True, slots=True)
class DatabaseRuntime:
    """The engine and session factory owned by one application instance."""

    engine: Engine
    session_factory: sessionmaker[Session]


def create_database_runtime(settings: Settings) -> DatabaseRuntime:
    """Build connection management without opening a connection immediately."""

    connect_args: dict[str, int] = {}
    if settings.database_url.startswith("postgresql"):
        connect_args["connect_timeout"] = settings.database_connect_timeout_seconds

    engine = create_engine(
        settings.database_url,
        echo=settings.database_echo,
        pool_pre_ping=True,
        hide_parameters=True,
        connect_args=connect_args,
    )
    session_factory = sessionmaker(
        bind=engine,
        class_=Session,
        autoflush=False,
        expire_on_commit=False,
    )
    return DatabaseRuntime(engine=engine, session_factory=session_factory)


def check_database_connection(engine: Engine) -> None:
    """Run a minimal query and expose no driver details on failure."""

    try:
        with engine.connect() as connection:
            result = connection.scalar(text("SELECT 1"))
    except SQLAlchemyError:
        raise DatabaseConnectionError("Database health check failed") from None

    if result != 1:
        raise DatabaseConnectionError(
            "Database health check returned an invalid result"
        )

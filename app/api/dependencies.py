"""Request-scoped dependencies shared by future M1 API routes."""

from collections.abc import AsyncGenerator, Callable
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import InvalidAccessTokenError, RequestTransactionError
from app.db.session import DatabaseRuntime
from app.llm.provider import ModelProvider, create_model_provider
from app.repositories.conversation import ConversationRepository
from app.repositories.evidence import EvidenceRepository
from app.repositories.files import FileRepository
from app.repositories.identity import IdentityRepository
from app.schemas.auth import CurrentUser
from app.services.auth import AuthService
from app.services.conversation import ConversationService
from app.services.evidence import EvidenceQueryService
from app.services.files import FileService
from app.services.storage import LocalStorageBackend, StorageBackend


class RequestCompensations:
    """Undo external writes if the surrounding database transaction fails."""

    def __init__(self) -> None:
        self._actions: list[Callable[[], None]] = []

    def add(self, action: Callable[[], None]) -> None:
        self._actions.append(action)

    def rollback(self) -> None:
        failure: Exception | None = None
        for action in reversed(self._actions):
            try:
                action()
            except Exception as error:  # noqa: BLE001 - cleanup actions are isolated.
                failure = failure or error
        if failure is not None:
            raise failure


async def get_request_compensations() -> AsyncGenerator[RequestCompensations, None]:
    """Run Storage cleanup when endpoint work or the later DB commit fails."""

    compensations = RequestCompensations()
    try:
        yield compensations
    except Exception:
        compensations.rollback()
        raise


RequestCompensationsDependency = Annotated[
    RequestCompensations,
    Depends(get_request_compensations, scope="function"),
]


def get_database_runtime(request: Request) -> DatabaseRuntime:
    """Return the database runtime owned by the current FastAPI application."""

    runtime: DatabaseRuntime = request.app.state.database_runtime
    return runtime


DatabaseRuntimeDependency = Annotated[
    DatabaseRuntime,
    Depends(get_database_runtime),
]


async def get_db_session(
    request: Request,
    _compensations: RequestCompensationsDependency,
) -> AsyncGenerator[Session, None]:
    """Keep one sync SQLAlchemy Session on the async request's single thread."""

    session = get_database_runtime(request).session_factory()
    try:
        yield session
        session.commit()
    except SQLAlchemyError:
        session.rollback()
        raise RequestTransactionError from None
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# Function scope finishes commit/rollback before FastAPI sends the response.
DatabaseSession = Annotated[
    Session,
    Depends(get_db_session, scope="function"),
]


def get_app_settings(request: Request) -> Settings:
    """Return the validated settings owned by this application instance."""

    settings: Settings = request.app.state.settings
    return settings


AppSettings = Annotated[Settings, Depends(get_app_settings)]


def get_storage_backend(request: Request, settings: AppSettings) -> StorageBackend:
    """Lazily create the configured backend without import-time filesystem writes."""

    backend: StorageBackend | None = request.app.state.storage_backend
    if backend is None:
        backend = LocalStorageBackend(
            settings.local_storage_root,
            chunk_size_bytes=settings.upload_stream_chunk_size_bytes,
        )
        request.app.state.storage_backend = backend
    return backend


StorageBackendDependency = Annotated[
    StorageBackend,
    Depends(get_storage_backend),
]


def get_file_service(
    session: DatabaseSession,
    settings: AppSettings,
    storage: StorageBackendDependency,
) -> FileService:
    """Build one file service inside the compensating request transaction."""

    return FileService(
        FileRepository(session, settings.database_statement_timeout_ms),
        storage,
    )


FileServiceDependency = Annotated[FileService, Depends(get_file_service)]


def get_auth_service(
    session: DatabaseSession,
    settings: AppSettings,
) -> AuthService:
    """Build request-scoped authentication from one database transaction."""

    return AuthService(
        IdentityRepository(session, settings.database_statement_timeout_ms),
        settings,
    )


AuthServiceDependency = Annotated[AuthService, Depends(get_auth_service)]

_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    auth: AuthServiceDependency,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> CurrentUser:
    """Parse Bearer auth and refresh current roles/scopes from PostgreSQL."""

    if credentials is None or credentials.scheme.casefold() != "bearer":
        raise InvalidAccessTokenError
    return auth.resolve_access_token(credentials.credentials)


CurrentUserDependency = Annotated[CurrentUser, Depends(get_current_user)]


async def get_model_provider(
    settings: AppSettings,
) -> AsyncGenerator[ModelProvider, None]:
    """Own and close a request-scoped Qwen client; Mock requires no cleanup."""

    provider = create_model_provider(settings)
    try:
        yield provider
    finally:
        close = getattr(provider, "aclose", None)
        if close is not None:
            await close()


ModelProviderDependency = Annotated[ModelProvider, Depends(get_model_provider)]


def get_conversation_service(
    session: DatabaseSession,
    settings: AppSettings,
) -> ConversationService:
    return ConversationService(
        ConversationRepository(session, settings.database_statement_timeout_ms)
    )


ConversationServiceDependency = Annotated[
    ConversationService,
    Depends(get_conversation_service),
]


def get_evidence_query_service(
    session: DatabaseSession,
    settings: AppSettings,
) -> EvidenceQueryService:
    return EvidenceQueryService(
        EvidenceRepository(session, settings.database_statement_timeout_ms)
    )


EvidenceQueryServiceDependency = Annotated[
    EvidenceQueryService,
    Depends(get_evidence_query_service),
]

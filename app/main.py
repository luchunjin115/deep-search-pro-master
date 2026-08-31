"""M1 FastAPI entry point with application and database health checks."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import __version__
from app.api.errors import register_error_handlers
from app.api.routers import (
    auth_router,
    documents_router,
    evidence_router,
    files_router,
    threads_router,
)
from app.core.config import Settings, get_settings
from app.db.session import (
    DatabaseConnectionError,
    DatabaseRuntime,
    check_database_connection,
    create_database_runtime,
)
from app.services.storage import StorageBackend


def create_app(
    settings: Settings | None = None,
    database_runtime: DatabaseRuntime | None = None,
    storage_backend: StorageBackend | None = None,
) -> FastAPI:
    """使用显式配置创建应用，方便测试且避免导入旧原型。"""

    current_settings = settings or get_settings()
    application = FastAPI(
        title=current_settings.app_name,
        version=__version__,
    )
    application.state.settings = current_settings
    application.state.database_runtime = database_runtime or create_database_runtime(
        current_settings
    )
    application.state.storage_backend = storage_backend
    application.state.embedding_provider = None
    application.add_middleware(
        CORSMiddleware,
        allow_origins=current_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_error_handlers(application)
    application.include_router(auth_router, prefix=current_settings.api_v1_prefix)
    application.include_router(threads_router, prefix=current_settings.api_v1_prefix)
    application.include_router(evidence_router, prefix=current_settings.api_v1_prefix)
    application.include_router(files_router, prefix=current_settings.api_v1_prefix)
    application.include_router(documents_router, prefix=current_settings.api_v1_prefix)

    @application.get("/health", tags=["system"])
    def health() -> JSONResponse:
        try:
            check_database_connection(application.state.database_runtime.engine)
        except DatabaseConnectionError:
            return JSONResponse(
                status_code=503,
                content={
                    "status": "degraded",
                    "service": current_settings.app_name,
                    "environment": current_settings.app_env,
                    "database": "unavailable",
                },
            )

        return JSONResponse(
            status_code=200,
            content={
                "status": "ok",
                "service": current_settings.app_name,
                "environment": current_settings.app_env,
                "database": "connected",
            },
        )

    return application


app = create_app()

"""Versioned M1 HTTP routers."""

from app.api.routers.auth import router as auth_router
from app.api.routers.documents import router as documents_router
from app.api.routers.evidence import router as evidence_router
from app.api.routers.files import router as files_router
from app.api.routers.threads import router as threads_router

__all__ = [
    "auth_router",
    "documents_router",
    "evidence_router",
    "files_router",
    "threads_router",
]

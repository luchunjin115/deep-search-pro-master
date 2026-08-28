"""Versioned M1 HTTP routers."""

from app.api.routers.auth import router as auth_router
from app.api.routers.evidence import router as evidence_router
from app.api.routers.threads import router as threads_router

__all__ = ["auth_router", "evidence_router", "threads_router"]

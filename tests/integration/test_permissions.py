from collections.abc import Generator
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from pydantic import SecretStr
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import MarketPermissionDeniedError, TenantPermissionDeniedError
from app.db.session import create_database_runtime
from app.repositories.identity import IdentityRepository
from app.runtime.context import RunContext, build_run_context
from app.runtime.permissions import PermissionGuard
from app.schemas.auth import LoginRequest
from app.schemas.common import MarketCode
from app.services.auth import AuthService
from app.tools.registry import create_m1_tool_registry
from scripts.seed_m1 import seed_m1

PASSWORD = SecretStr("M1-demo-only-change-me")


@pytest.fixture
def permission_fixture(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Generator[tuple[Session, AuthService, PermissionGuard], None, None]:
    settings = Settings(  # type: ignore[call-arg]
        _env_file=".env.example",
        app_env="test",
    )
    monkeypatch.setenv("DATABASE_URL", settings.database_url)
    seed_m1(settings, manifest_path=tmp_path / "m1_manifest.json")
    runtime = create_database_runtime(settings)
    session = runtime.session_factory()
    try:
        yield (
            session,
            AuthService(
                IdentityRepository(
                    session,
                    settings.database_statement_timeout_ms,
                ),
                settings,
            ),
            PermissionGuard(create_m1_tool_registry()),
        )
    finally:
        session.rollback()
        session.close()
        runtime.engine.dispose()


def login_context(auth: AuthService, email: str) -> RunContext:
    response = auth.login(LoginRequest(email=email, password=PASSWORD))
    user = auth.resolve_access_token(response.access_token)
    return build_run_context(user, uuid4(), trace_id=uuid4())


def grant_market(
    guard: PermissionGuard,
    context: RunContext,
    market_code: MarketCode,
) -> bool:
    grant = guard.authorize(
        context,
        "search_inventory",
        target_tenant_id=context.tenant_id,
        market_code=market_code,
    )
    return grant.allowed


def test_real_seed_roles_enforce_current_market_scopes(
    permission_fixture: tuple[Session, AuthService, PermissionGuard],
) -> None:
    _session, auth, guard = permission_fixture
    owner = login_context(auth, "owner@demo.deepsearch.local")
    scout = login_context(auth, "scout@demo.deepsearch.local")
    de_operator = login_context(auth, "de.operator@demo.deepsearch.local")
    fr_operator = login_context(auth, "fr.operator@demo.deepsearch.local")

    assert grant_market(guard, owner, "DE")
    assert grant_market(guard, owner, "FR")
    assert grant_market(guard, scout, "DE")
    assert grant_market(guard, scout, "FR")
    assert grant_market(guard, de_operator, "DE")
    assert grant_market(guard, fr_operator, "FR")
    with pytest.raises(MarketPermissionDeniedError):
        grant_market(guard, de_operator, "FR")
    with pytest.raises(MarketPermissionDeniedError):
        grant_market(guard, fr_operator, "DE")

    for runtime_context in (owner, scout, de_operator, fr_operator):
        grant = guard.authorize(
            runtime_context,
            "get_product_spec",
            target_tenant_id=runtime_context.tenant_id,
        )
        assert grant.allowed is True


def test_real_identity_cannot_authorize_another_tenant(
    permission_fixture: tuple[Session, AuthService, PermissionGuard],
) -> None:
    _session, auth, guard = permission_fixture
    de_operator = login_context(auth, "de.operator@demo.deepsearch.local")
    other_tenant_id: UUID = uuid4()

    with pytest.raises(TenantPermissionDeniedError):
        guard.authorize(
            de_operator,
            "search_inventory",
            target_tenant_id=other_tenant_id,
            market_code="DE",
        )

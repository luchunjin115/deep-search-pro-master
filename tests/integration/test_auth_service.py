from collections.abc import Generator
from pathlib import Path

import pytest
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import InactiveUserError, InvalidCredentialsError
from app.db.session import create_database_runtime
from app.models.identity import User, UserRole
from app.repositories.identity import IdentityRepository
from app.schemas.auth import LoginRequest
from app.services.auth import AuthService
from scripts.seed_m1 import seed_m1

PASSWORD = "M1-demo-only-change-me"


@pytest.fixture
def auth_fixture(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Generator[tuple[Session, AuthService, Settings], None, None]:
    settings = Settings(  # type: ignore[call-arg]
        _env_file=".env.example",
        app_env="test",
    )
    monkeypatch.setenv("DATABASE_URL", settings.database_url)
    seed_m1(settings, manifest_path=tmp_path / "m1_manifest.json")
    runtime = create_database_runtime(settings)
    connection = runtime.engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, expire_on_commit=False)
    service = AuthService(
        IdentityRepository(session, settings.database_statement_timeout_ms),
        settings,
    )
    try:
        yield session, service, settings
    finally:
        session.close()
        transaction.rollback()
        connection.close()
        runtime.engine.dispose()


def login(email: str, password: str = PASSWORD) -> LoginRequest:
    return LoginRequest(email=email, password=SecretStr(password))


def test_all_seed_accounts_login_with_current_roles_and_scopes(
    auth_fixture: tuple[Session, AuthService, Settings],
) -> None:
    _session, service, _settings = auth_fixture
    expected = {
        "owner@demo.deepsearch.local": (["company_owner"], ["DE", "FR"]),
        "scout@demo.deepsearch.local": (["product_scout"], ["DE", "FR"]),
        "de.operator@demo.deepsearch.local": (["amazon_operator"], ["DE"]),
        "fr.operator@demo.deepsearch.local": (["amazon_operator"], ["FR"]),
    }

    for email, (roles, market_scopes) in expected.items():
        response = service.login(login(email))
        refreshed = service.resolve_access_token(response.access_token)
        assert response.user.email == email
        assert response.user.roles == roles
        assert response.user.market_scopes == market_scopes
        assert refreshed == response.user
        assert response.user.synthetic_data is True


def test_real_password_and_disabled_user_are_rejected(
    auth_fixture: tuple[Session, AuthService, Settings],
) -> None:
    session, service, _settings = auth_fixture
    email = "de.operator@demo.deepsearch.local"
    with pytest.raises(InvalidCredentialsError):
        service.login(login(email, "wrong-password-value"))

    user = session.scalar(select(User).where(User.email == email))
    assert user is not None
    user.status = "disabled"
    session.flush()
    with pytest.raises(InactiveUserError):
        service.login(login(email))


def test_valid_token_refreshes_changed_database_scope_and_disabled_status(
    auth_fixture: tuple[Session, AuthService, Settings],
) -> None:
    session, service, _settings = auth_fixture
    email = "de.operator@demo.deepsearch.local"
    response = service.login(login(email))
    assignment = session.scalar(select(UserRole).join(User).where(User.email == email))
    user = session.scalar(select(User).where(User.email == email))
    assert assignment is not None
    assert user is not None

    assignment.market_scopes = ["FR"]
    session.flush()
    refreshed = service.resolve_access_token(response.access_token)
    assert refreshed.market_scopes == ["FR"]

    user.status = "disabled"
    session.flush()
    with pytest.raises(InactiveUserError):
        service.resolve_access_token(response.access_token)

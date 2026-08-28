import asyncio
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from pwdlib import PasswordHash
from pydantic import SecretStr
from sqlalchemy.exc import OperationalError

from app.core.config import Settings
from app.core.errors import (
    AuthenticationDatabaseError,
    AuthenticationDataContractError,
    InactiveUserError,
    InvalidAccessTokenError,
    InvalidCredentialsError,
)
from app.core.security import SecurityService
from app.repositories.identity import IdentityRecord
from app.runtime.context import (
    MissingRunContextError,
    bind_run_context,
    build_run_context,
    get_current_run_context,
)
from app.schemas.auth import LoginRequest
from app.services.auth import AuthService

PASSWORD = "M1-demo-only-change-me"


class FakeIdentityRepository:
    def __init__(self, identities: list[IdentityRecord]) -> None:
        self.identities = identities
        self.raise_database_error = False

    def find_by_email(self, email: str) -> list[IdentityRecord]:
        if self.raise_database_error:
            raise OperationalError("SELECT users", {}, RuntimeError("driver secret"))
        return [identity for identity in self.identities if identity.email == email]

    def find_by_subject(
        self,
        user_id: UUID,
        tenant_id: UUID,
    ) -> IdentityRecord | None:
        if self.raise_database_error:
            raise OperationalError("SELECT users", {}, RuntimeError("driver secret"))
        return next(
            (
                identity
                for identity in self.identities
                if identity.user_id == user_id and identity.tenant_id == tenant_id
            ),
            None,
        )


@pytest.fixture(scope="module")
def settings() -> Settings:
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        app_env="test",
        jwt_secret_key=SecretStr("unit-test-secret-key-with-at-least-32-characters"),
        jwt_expire_minutes=60,
    )


@pytest.fixture(scope="module")
def security(settings: Settings) -> SecurityService:
    return SecurityService(settings)


@pytest.fixture(scope="module")
def password_hash() -> str:
    return PasswordHash.recommended().hash(PASSWORD)


def identity(valid_password_hash: str, **changes: object) -> IdentityRecord:
    defaults: dict[str, object] = {
        "user_id": uuid4(),
        "tenant_id": uuid4(),
        "email": "de.operator@demo.deepsearch.local",
        "display_name": "演示德国运营",
        "password_hash": valid_password_hash,
        "status": "active",
        "tenant_is_demo": True,
        "roles": ("amazon_operator",),
        "market_scopes": ("DE",),
    }
    defaults.update(changes)
    return IdentityRecord(**defaults)  # type: ignore[arg-type]


def login_request(password: str = PASSWORD) -> LoginRequest:
    return LoginRequest(
        email="de.operator@demo.deepsearch.local",
        password=SecretStr(password),
    )


def test_login_returns_signed_minimal_token_and_safe_current_user(
    settings: Settings,
    security: SecurityService,
    password_hash: str,
) -> None:
    stored_identity = identity(password_hash)
    service = AuthService(
        FakeIdentityRepository([stored_identity]),
        settings,
        security,
    )

    response = service.login(login_request())
    claims = security.decode_access_token(response.access_token)

    assert response.expires_in_seconds == 3600
    assert response.user.user_id == stored_identity.user_id
    assert response.user.roles == ["amazon_operator"]
    assert response.user.market_scopes == ["DE"]
    assert claims.sub == stored_identity.user_id
    assert claims.tenant_id == stored_identity.tenant_id
    assert "roles" not in claims.model_dump()
    assert "market_scopes" not in claims.model_dump()
    assert "password" not in response.model_dump_json()


def test_login_rejects_wrong_missing_or_ambiguous_identity(
    settings: Settings,
    security: SecurityService,
    password_hash: str,
) -> None:
    stored_identity = identity(password_hash)
    service = AuthService(FakeIdentityRepository([stored_identity]), settings, security)
    with pytest.raises(InvalidCredentialsError):
        service.login(login_request("wrong-password-value"))

    missing_service = AuthService(FakeIdentityRepository([]), settings, security)
    with pytest.raises(InvalidCredentialsError):
        missing_service.login(login_request())

    duplicate = replace(stored_identity, user_id=uuid4(), tenant_id=uuid4())
    ambiguous_service = AuthService(
        FakeIdentityRepository([stored_identity, duplicate]),
        settings,
        security,
    )
    with pytest.raises(InvalidCredentialsError):
        ambiguous_service.login(login_request())


def test_login_rejects_disabled_or_malformed_database_identity(
    settings: Settings,
    security: SecurityService,
    password_hash: str,
) -> None:
    disabled = identity(password_hash, status="disabled")
    with pytest.raises(InactiveUserError):
        AuthService(FakeIdentityRepository([disabled]), settings, security).login(
            login_request()
        )

    malformed_hash = identity(password_hash, password_hash="not-an-argon2-hash")
    with pytest.raises(AuthenticationDataContractError):
        AuthService(FakeIdentityRepository([malformed_hash]), settings, security).login(
            login_request()
        )


def test_token_rejects_expired_forged_or_deleted_subject(
    settings: Settings,
    security: SecurityService,
    password_hash: str,
) -> None:
    stored_identity = identity(password_hash)
    repository = FakeIdentityRepository([stored_identity])
    service = AuthService(repository, settings, security)
    expired = security.create_access_token(
        stored_identity.user_id,
        stored_identity.tenant_id,
        now=datetime.now(UTC) - timedelta(hours=2),
    )
    with pytest.raises(InvalidAccessTokenError):
        service.resolve_access_token(expired)

    other_security = SecurityService(
        Settings(
            _env_file=None,  # type: ignore[call-arg]
            app_env="test",
            jwt_secret_key=SecretStr(
                "different-unit-test-secret-at-least-32-characters"
            ),
        )
    )
    forged = other_security.create_access_token(
        stored_identity.user_id,
        stored_identity.tenant_id,
    )
    with pytest.raises(InvalidAccessTokenError):
        service.resolve_access_token(forged)

    valid = security.create_access_token(
        stored_identity.user_id,
        stored_identity.tenant_id,
    )
    repository.identities.clear()
    with pytest.raises(InvalidAccessTokenError):
        service.resolve_access_token(valid)


def test_token_resolution_refreshes_database_roles_and_status(
    settings: Settings,
    security: SecurityService,
    password_hash: str,
) -> None:
    stored_identity = identity(password_hash)
    repository = FakeIdentityRepository([stored_identity])
    service = AuthService(repository, settings, security)
    token = service.login(login_request()).access_token

    repository.identities[0] = replace(
        stored_identity,
        roles=("company_owner",),
        market_scopes=("DE", "FR"),
    )
    refreshed = service.resolve_access_token(token)
    assert refreshed.roles == ["company_owner"]
    assert refreshed.market_scopes == ["DE", "FR"]

    repository.identities[0] = replace(repository.identities[0], status="disabled")
    with pytest.raises(InactiveUserError):
        service.resolve_access_token(token)


def test_authentication_database_error_is_safe(
    settings: Settings,
    security: SecurityService,
) -> None:
    repository = FakeIdentityRepository([])
    repository.raise_database_error = True
    service = AuthService(repository, settings, security)

    with pytest.raises(AuthenticationDatabaseError) as captured:
        service.login(login_request())

    detail = captured.value.to_detail().model_dump_json()
    assert "SELECT users" not in detail
    assert "driver secret" not in detail


def test_run_context_is_immutable_bound_and_restored(
    settings: Settings,
    security: SecurityService,
    password_hash: str,
) -> None:
    stored_identity = identity(password_hash)
    user = (
        AuthService(FakeIdentityRepository([stored_identity]), settings, security)
        .login(login_request())
        .user
    )
    trace_id = uuid4()
    context = build_run_context(user, uuid4(), trace_id=trace_id)

    assert context.user_id == user.user_id
    assert context.roles == ("amazon_operator",)
    assert context.market_scopes == ("DE",)
    assert context.trace_id == trace_id
    with pytest.raises(FrozenInstanceError):
        context.user_id = uuid4()  # type: ignore[misc]

    with pytest.raises(MissingRunContextError):
        get_current_run_context()
    with bind_run_context(context):
        assert get_current_run_context() is context
    with pytest.raises(MissingRunContextError):
        get_current_run_context()


def test_run_context_is_isolated_between_concurrent_tasks(
    settings: Settings,
    security: SecurityService,
    password_hash: str,
) -> None:
    async def exercise() -> list[UUID]:
        async def worker(context_user_id: UUID) -> UUID:
            stored_identity = identity(password_hash, user_id=context_user_id)
            user = (
                AuthService(
                    FakeIdentityRepository([stored_identity]), settings, security
                )
                .login(login_request())
                .user
            )
            context = build_run_context(user, uuid4())
            with bind_run_context(context):
                await asyncio.sleep(0)
                return get_current_run_context().user_id

        expected = [uuid4(), uuid4()]
        actual = await asyncio.gather(*(worker(user_id) for user_id in expected))
        assert actual == expected
        return actual

    asyncio.run(exercise())
    with pytest.raises(MissingRunContextError):
        get_current_run_context()

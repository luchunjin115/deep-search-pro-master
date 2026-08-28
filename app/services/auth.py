"""M1 authentication rules built on fixed identity reads and signed JWTs."""

from __future__ import annotations

from typing import Protocol, cast
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import Settings
from app.core.errors import (
    AuthenticationDatabaseError,
    AuthenticationDataContractError,
    InactiveUserError,
    InvalidAccessTokenError,
    InvalidCredentialsError,
)
from app.core.security import PasswordHashDataError, SecurityService, TokenDecodeError
from app.repositories.identity import IdentityRecord
from app.schemas.auth import CurrentUser, LoginRequest, LoginResponse
from app.schemas.common import MarketCode, RoleName


class IdentityReader(Protocol):
    """The two fixed identity reads allowed to the authentication Service."""

    def find_by_email(self, email: str) -> list[IdentityRecord]: ...

    def find_by_subject(
        self,
        user_id: UUID,
        tenant_id: UUID,
    ) -> IdentityRecord | None: ...


class AuthService:
    """Authenticate credentials and refresh database identity for every token."""

    def __init__(
        self,
        repository: IdentityReader,
        settings: Settings,
        security: SecurityService | None = None,
    ) -> None:
        self._repository = repository
        self._settings = settings
        self._security = security or SecurityService(settings)

    def login(self, request: LoginRequest) -> LoginResponse:
        """Verify one unique active user and return a short-lived bearer token."""

        password = request.password.get_secret_value()
        try:
            candidates = self._repository.find_by_email(request.email)
        except SQLAlchemyError:
            raise AuthenticationDatabaseError from None

        if len(candidates) != 1:
            self._security.perform_dummy_password_check(password)
            raise InvalidCredentialsError

        identity = candidates[0]
        try:
            password_matches = self._security.verify_password(
                password,
                identity.password_hash,
            )
        except PasswordHashDataError:
            raise AuthenticationDataContractError from None

        if not password_matches:
            raise InvalidCredentialsError
        if identity.status != "active":
            raise InactiveUserError

        user = _to_current_user(identity)
        access_token = self._security.create_access_token(
            identity.user_id,
            identity.tenant_id,
        )
        return LoginResponse(
            access_token=access_token,
            expires_in_seconds=self._settings.jwt_expire_minutes * 60,
            user=user,
        )

    def resolve_access_token(self, token: str) -> CurrentUser:
        """Verify a token, then reload status, roles, and scope from PostgreSQL."""

        try:
            claims = self._security.decode_access_token(token)
        except TokenDecodeError:
            raise InvalidAccessTokenError from None

        try:
            identity = self._repository.find_by_subject(
                claims.sub,
                claims.tenant_id,
            )
        except SQLAlchemyError:
            raise AuthenticationDatabaseError from None

        if identity is None:
            raise InvalidAccessTokenError
        if identity.status != "active":
            raise InactiveUserError
        return _to_current_user(identity)


def _to_current_user(identity: IdentityRecord) -> CurrentUser:
    if not identity.tenant_is_demo:
        raise AuthenticationDataContractError
    try:
        return CurrentUser(
            user_id=identity.user_id,
            tenant_id=identity.tenant_id,
            email=identity.email,
            display_name=identity.display_name,
            roles=cast(list[RoleName], list(identity.roles)),
            market_scopes=cast(list[MarketCode], list(identity.market_scopes)),
            synthetic_data=True,
        )
    except ValidationError:
        raise AuthenticationDataContractError from None

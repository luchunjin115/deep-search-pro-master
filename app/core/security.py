"""Password verification and signed short-lived JWT handling for M1."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID, uuid4

import jwt
from jwt import InvalidTokenError as PyJWTInvalidTokenError
from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError
from pydantic import AwareDatetime, BaseModel, ConfigDict, ValidationError

from app.core.config import Settings

TOKEN_ISSUER = "deep-search-pro-m1"
TOKEN_AUDIENCE = "deep-search-pro-m1"
TOKEN_TYPE = "access"
_PASSWORD_HASHER = PasswordHash.recommended()
_DUMMY_PASSWORD_HASH = _PASSWORD_HASHER.hash("not-a-real-m1-user-password")


class PasswordHashDataError(ValueError):
    """The stored password hash is not supported or is malformed."""


class TokenDecodeError(ValueError):
    """The token failed signature, time, issuer, audience, or claim checks."""


class AccessTokenClaims(BaseModel):
    """The deliberately small trusted payload carried by an M1 access token."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    sub: UUID
    tenant_id: UUID
    jti: UUID
    token_type: Literal["access"]
    iss: Literal["deep-search-pro-m1"]
    aud: Literal["deep-search-pro-m1"]
    iat: AwareDatetime
    exp: AwareDatetime


class SecurityService:
    """Verify Argon2 hashes and encode/decode whitelisted HS256 JWTs."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def verify_password(self, password: str, password_hash: str) -> bool:
        """Verify one password without exposing the stored hash."""

        try:
            return _PASSWORD_HASHER.verify(password, password_hash)
        except UnknownHashError:
            raise PasswordHashDataError from None

    def perform_dummy_password_check(self, password: str) -> None:
        """Spend password-check work when no unique login identity exists."""

        _PASSWORD_HASHER.verify(password, _DUMMY_PASSWORD_HASH)

    def create_access_token(
        self,
        user_id: UUID,
        tenant_id: UUID,
        *,
        now: datetime | None = None,
    ) -> str:
        """Create a signed token containing identity pointers but no permissions."""

        issued_at = now or datetime.now(UTC)
        expires_at = issued_at + timedelta(minutes=self._settings.jwt_expire_minutes)
        payload = {
            "sub": str(user_id),
            "tenant_id": str(tenant_id),
            "jti": str(uuid4()),
            "token_type": TOKEN_TYPE,
            "iss": TOKEN_ISSUER,
            "aud": TOKEN_AUDIENCE,
            "iat": issued_at,
            "exp": expires_at,
        }
        return jwt.encode(
            payload,
            self._settings.jwt_secret_key.get_secret_value(),
            algorithm=self._settings.jwt_algorithm,
        )

    def decode_access_token(self, token: str) -> AccessTokenClaims:
        """Verify a token with a fixed algorithm and strict required claims."""

        try:
            payload = jwt.decode(
                token,
                self._settings.jwt_secret_key.get_secret_value(),
                algorithms=[self._settings.jwt_algorithm],
                audience=TOKEN_AUDIENCE,
                issuer=TOKEN_ISSUER,
                options={
                    "require": [
                        "sub",
                        "tenant_id",
                        "jti",
                        "token_type",
                        "iss",
                        "aud",
                        "iat",
                        "exp",
                    ]
                },
            )
            return AccessTokenClaims.model_validate(payload)
        except (PyJWTInvalidTokenError, ValidationError, TypeError, ValueError):
            raise TokenDecodeError from None

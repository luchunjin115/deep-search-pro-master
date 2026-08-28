"""Authentication request and response contracts for M1."""

from __future__ import annotations

import re
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, SecretStr, StringConstraints, field_validator

from app.schemas.common import M1Schema, MarketCode, RoleName

EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
AccessToken = Annotated[
    str,
    StringConstraints(
        strict=True, strip_whitespace=True, min_length=20, max_length=4096
    ),
]


class LoginRequest(M1Schema):
    """Credentials accepted by the future login endpoint."""

    email: str = Field(min_length=3, max_length=320)
    password: SecretStr = Field(min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not EMAIL_PATTERN.fullmatch(normalized):
            raise ValueError("email format is invalid")
        return normalized


class CurrentUser(M1Schema):
    """Authenticated identity safe to return to the frontend."""

    user_id: UUID
    tenant_id: UUID
    email: str = Field(min_length=3, max_length=320)
    display_name: str = Field(min_length=1, max_length=120)
    roles: list[RoleName] = Field(min_length=1, max_length=3)
    market_scopes: list[MarketCode] = Field(min_length=1, max_length=2)
    synthetic_data: Literal[True] = True

    @field_validator("email")
    @classmethod
    def require_normalized_email(cls, value: str) -> str:
        if value != value.lower() or not EMAIL_PATTERN.fullmatch(value):
            raise ValueError("email must be normalized lowercase")
        return value

    @field_validator("roles", "market_scopes")
    @classmethod
    def reject_duplicate_values(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("duplicate values are not allowed")
        return value


class LoginResponse(M1Schema):
    """Short-lived bearer token plus the trusted database identity."""

    access_token: AccessToken
    token_type: Literal["bearer"] = "bearer"
    expires_in_seconds: int = Field(gt=0, le=86400)
    user: CurrentUser

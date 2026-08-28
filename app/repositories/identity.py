"""Fixed identity reads used by authentication and token refresh."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.models.identity import Role, Tenant, User, UserRole
from app.repositories.common import apply_statement_timeout


@dataclass(frozen=True, slots=True)
class IdentityRecord:
    """One database identity plus its current roles and market scopes."""

    user_id: UUID
    tenant_id: UUID
    email: str
    display_name: str
    password_hash: str
    status: str
    tenant_is_demo: bool
    roles: tuple[str, ...]
    market_scopes: tuple[str, ...]


@dataclass(slots=True)
class _IdentityAccumulator:
    user: User
    tenant: Tenant
    roles: set[str] = field(default_factory=set)
    market_scopes: set[str] = field(default_factory=set)


class IdentityRepository:
    """Read identities through developer-written SQLAlchemy SELECT statements."""

    def __init__(self, session: Session, statement_timeout_ms: int = 2000) -> None:
        self._session = session
        self._statement_timeout_ms = statement_timeout_ms

    def find_by_email(self, email: str) -> list[IdentityRecord]:
        """Return every tenant identity matching one normalized email."""

        statement = self._base_statement().where(User.email == email)
        return self._read(statement)

    def find_by_subject(
        self,
        user_id: UUID,
        tenant_id: UUID,
    ) -> IdentityRecord | None:
        """Refresh exactly the database subject named by a verified token."""

        statement = self._base_statement().where(
            User.id == user_id,
            User.tenant_id == tenant_id,
        )
        records = self._read(statement)
        return records[0] if len(records) == 1 else None

    @staticmethod
    def _base_statement() -> Select[tuple[User, Tenant, Role, UserRole]]:
        return (
            select(User, Tenant, Role, UserRole)
            .join(Tenant, Tenant.id == User.tenant_id)
            .outerjoin(UserRole, UserRole.user_id == User.id)
            .outerjoin(Role, Role.id == UserRole.role_id)
            .order_by(User.id, Role.name)
        )

    def _read(
        self,
        statement: Select[tuple[User, Tenant, Role, UserRole]],
    ) -> list[IdentityRecord]:
        apply_statement_timeout(self._session, self._statement_timeout_ms)
        accumulators: dict[UUID, _IdentityAccumulator] = {}
        for user, tenant, role, assignment in self._session.execute(statement):
            accumulator = accumulators.setdefault(
                user.id,
                _IdentityAccumulator(user=user, tenant=tenant),
            )
            if role is not None:
                accumulator.roles.add(role.name)
            if assignment is not None:
                accumulator.market_scopes.update(assignment.market_scopes)

        return [
            IdentityRecord(
                user_id=item.user.id,
                tenant_id=item.user.tenant_id,
                email=item.user.email,
                display_name=item.user.display_name,
                password_hash=item.user.password_hash,
                status=item.user.status,
                tenant_is_demo=item.tenant.is_demo,
                roles=tuple(sorted(item.roles)),
                market_scopes=tuple(sorted(item.market_scopes)),
            )
            for item in accumulators.values()
        ]

"""Shared safeguards for fixed M1 PostgreSQL queries."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session


def apply_statement_timeout(session: Session, timeout_ms: int) -> None:
    """Set a transaction-local PostgreSQL statement timeout via bound parameters."""

    if not 1 <= timeout_ms <= 30000:
        raise ValueError("statement timeout must be between 1 and 30000 milliseconds")

    session.scalar(
        select(
            func.set_config(
                "statement_timeout",
                f"{timeout_ms}ms",
                True,
            )
        )
    )

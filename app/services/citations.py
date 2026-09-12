"""Strictly validate answer-local Evidence labels against current PostgreSQL ACL."""

from __future__ import annotations

import re
from typing import Protocol
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.core.errors import CitationValidationError, EvidenceReadError
from app.repositories.evidence import AuthorizedCitationContext
from app.schemas.auth import CurrentUser
from app.schemas.context import (
    CitationValidationResult,
    ContextCitation,
)

_VALID_CITATION_PATTERN = re.compile(r"\[E(?:[1-9]|1[0-2])\]")
_CITATION_LIKE_PATTERN = re.compile(
    r"(?:\[|［)\s*[Ee](?:\s*\d{1,5}\s*(?:\]|］)?|\s*(?:\]|］))"
)
_ANSWER_MAX_CHARS = 100_000


class CitationEvidenceReader(Protocol):
    """The only current-user citation allow-list read needed by the Validator."""

    def load_authorized_citation_context(
        self,
        current_user: CurrentUser,
        context_id: UUID,
    ) -> AuthorizedCitationContext | None: ...


class CitationValidatorService:
    """Validate Context citations and list each source once in first-use order."""

    def __init__(self, repository: CitationEvidenceReader) -> None:
        self._repository = repository

    def validate_answer(
        self,
        current_user: CurrentUser,
        context_id: UUID,
        answer: str,
    ) -> CitationValidationResult:
        if (
            not isinstance(current_user, CurrentUser)
            or not isinstance(context_id, UUID)
            or not isinstance(answer, str)
            or not answer.strip()
            or len(answer) > _ANSWER_MAX_CHARS
        ):
            raise CitationValidationError

        labels = _extract_strict_labels(answer)
        try:
            snapshot = self._repository.load_authorized_citation_context(
                current_user,
                context_id,
            )
        except SQLAlchemyError:
            raise EvidenceReadError from None
        if snapshot is None or snapshot.context_id != context_id:
            raise CitationValidationError

        if not snapshot.evidence_ids:
            if labels:
                raise CitationValidationError
            return CitationValidationResult(context_id=context_id, citations=[])
        if not labels or len(snapshot.evidence_ids) > 12:
            raise CitationValidationError

        try:
            citations = [
                ContextCitation(
                    citation_label=label,
                    evidence_id=snapshot.evidence_ids[int(label[2:-1]) - 1],
                )
                for label in labels
            ]
            return CitationValidationResult(
                context_id=context_id,
                citations=citations,
            )
        except (IndexError, ValidationError, ValueError):
            raise CitationValidationError from None


def _extract_strict_labels(answer: str) -> list[str]:
    suspicious = list(_CITATION_LIKE_PATTERN.finditer(answer))
    if any(
        _VALID_CITATION_PATTERN.fullmatch(match.group(0)) is None
        for match in suspicious
    ):
        raise CitationValidationError
    labels = [match.group(0) for match in _VALID_CITATION_PATTERN.finditer(answer)]
    return list(dict.fromkeys(labels))

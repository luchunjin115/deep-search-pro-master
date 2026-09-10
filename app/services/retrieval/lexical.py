"""Permission-first PostgreSQL full-text retrieval without Embedding work."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol, TypeVar, cast

from pydantic import ValidationError
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from app.repositories.retrieval import LexicalCandidateRecord
from app.schemas.auth import CurrentUser
from app.schemas.common import MarketCode
from app.schemas.retrieval import (
    LexicalRetrievalScore,
    RetrievalCandidateFailure,
    RetrievalCandidateIdentity,
    RetrievalDocumentMetadata,
    RetrievalFtsIdentity,
    RetrievalRequest,
    RetrievalResponse,
    RetrievalResult,
    RetrievalScoreBreakdown,
)
from app.services.retrieval.errors import (
    RetrievalDatabaseTimeoutError,
    RetrievalDatabaseUnavailableError,
    RetrievalInputError,
    RetrievalInternalError,
)
from app.services.retrieval.lexical_text import (
    BuiltFtsText,
    FtsTextBuilderError,
    FtsTextPurpose,
    get_fts_text_builder,
)
from app.services.retrieval.result_mapping import (
    RetrievalSourceLocatorMappingError,
    source_locator_from_candidate,
)

_T = TypeVar("_T")


class LexicalRetrievalReader(Protocol):
    def search_lexical(
        self,
        current_user: CurrentUser,
        *,
        lexical_tsquery: str,
        fts_builder_version: str,
        limit: int,
    ) -> list[LexicalCandidateRecord]: ...


class QueryFtsTextBuilder(Protocol):
    def build(self, text: str, *, purpose: FtsTextPurpose) -> BuiltFtsText: ...


class LexicalRetrievalService:
    """Build one versioned query and rank only shared authorized candidates."""

    def __init__(
        self,
        repository: LexicalRetrievalReader,
        fts_text_builder: QueryFtsTextBuilder | None = None,
        *,
        query_max_characters: int = 2000,
        candidate_count: int = 30,
    ) -> None:
        if not 1 <= query_max_characters <= 2000:
            raise ValueError("query_max_characters must be between 1 and 2000")
        if not 1 <= candidate_count <= 100:
            raise ValueError("candidate_count must be between 1 and 100")
        self._repository = repository
        self._fts_text_builder = fts_text_builder or get_fts_text_builder()
        self._query_max_characters = query_max_characters
        self._candidate_count = candidate_count

    def retrieve(
        self,
        current_user: CurrentUser,
        request: RetrievalRequest,
    ) -> RetrievalResponse:
        """Return safe Lexical candidates or one typed retrieval failure."""

        if len(request.query) > self._query_max_characters:
            raise RetrievalInputError
        try:
            built = self._fts_text_builder.build(
                request.query,
                purpose=FtsTextPurpose.QUERY,
            )
            lexical_tsquery = _or_tsquery(built)
            public_identity = RetrievalFtsIdentity(
                builder_version=built.identity.builder_version
            )
        except (FtsTextBuilderError, TypeError, ValueError, ValidationError):
            raise RetrievalInternalError from None

        candidates = _database_call(
            lambda: self._repository.search_lexical(
                current_user,
                lexical_tsquery=lexical_tsquery,
                fts_builder_version=built.identity.builder_version,
                limit=self._candidate_count,
            )
        )
        try:
            results: list[RetrievalResult] = []
            candidate_failures: list[RetrievalCandidateFailure] = []
            for rank, candidate in enumerate(candidates, start=1):
                try:
                    results.append(_result_from_candidate(candidate, rank=rank))
                except RetrievalSourceLocatorMappingError:
                    candidate_failures.append(
                        RetrievalCandidateFailure(
                            source_mode="lexical",
                            rank=rank,
                            chunk_id=candidate.chunk_id,
                        )
                    )
            return RetrievalResponse(
                mode="lexical",
                fts_identity=public_identity,
                results=results,
                candidate_failures=candidate_failures,
            )
        except (TypeError, ValueError, ValidationError):
            raise RetrievalInternalError from None


def _or_tsquery(built: BuiltFtsText) -> str:
    tokens = tuple(dict.fromkeys(built.text.split()))
    if not tokens or any(not token.isalnum() for token in tokens):
        raise ValueError("built FTS query contains an unsafe token")
    return " | ".join(tokens)


def _result_from_candidate(
    candidate: LexicalCandidateRecord,
    *,
    rank: int,
) -> RetrievalResult:
    return RetrievalResult(
        identity=RetrievalCandidateIdentity(
            document_id=candidate.document_id,
            version_id=candidate.version_id,
            index_set_id=candidate.index_set_id,
            chunk_id=candidate.chunk_id,
        ),
        document=RetrievalDocumentMetadata(
            title=candidate.title,
            document_type=candidate.document_type,
            language=candidate.language,
            market=cast(MarketCode | None, candidate.market),
        ),
        body_text=candidate.body_text,
        source_locator=source_locator_from_candidate(candidate),
        scores=RetrievalScoreBreakdown(
            lexical=LexicalRetrievalScore(rank=rank, score=candidate.score)
        ),
        final_rank=rank,
    )


def _database_call(operation: Callable[[], _T]) -> _T:
    try:
        return operation()
    except OperationalError as error:
        if _is_statement_timeout(error):
            raise RetrievalDatabaseTimeoutError from None
        raise RetrievalDatabaseUnavailableError from None
    except SQLAlchemyError:
        raise RetrievalDatabaseUnavailableError from None


def _is_statement_timeout(error: OperationalError) -> bool:
    sqlstate = getattr(error.orig, "sqlstate", None)
    if sqlstate is None:
        sqlstate = getattr(error.orig, "pgcode", None)
    return sqlstate == "57014"

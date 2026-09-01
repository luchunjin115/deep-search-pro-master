"""Permission-first Dense retrieval using QUERY vectors and pgvector cosine."""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import asdict
from numbers import Real
from typing import Protocol, TypeVar, cast

from pydantic import ValidationError
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from app.core.errors import EmbeddingInputError, EmbeddingProviderError
from app.repositories.retrieval import DenseCandidateRecord
from app.schemas.auth import CurrentUser
from app.schemas.common import MarketCode
from app.schemas.retrieval import (
    DenseRetrievalScore,
    RetrievalCandidateIdentity,
    RetrievalDocumentMetadata,
    RetrievalEmbeddingIdentity,
    RetrievalRequest,
    RetrievalResponse,
    RetrievalResult,
    RetrievalScoreBreakdown,
)
from app.services.retrieval.embedding import (
    EmbeddingBatch,
    EmbeddingIdentity,
    EmbeddingProvider,
    EmbeddingPurpose,
)
from app.services.retrieval.errors import (
    RetrievalDatabaseTimeoutError,
    RetrievalDatabaseUnavailableError,
    RetrievalEmbeddingIdentityMismatchError,
    RetrievalEmbeddingProviderUnavailableError,
    RetrievalInputError,
    RetrievalInternalError,
)
from app.services.retrieval.result_mapping import source_locator_from_candidate

_T = TypeVar("_T")


class DenseRetrievalReader(Protocol):
    """The only two database reads allowed to the Dense Service."""

    def list_authorized_embedding_identities(
        self,
        current_user: CurrentUser,
    ) -> list[dict[str, object]]: ...

    def search_dense(
        self,
        current_user: CurrentUser,
        *,
        query_vector: tuple[float, ...],
        embedding_identity: EmbeddingIdentity,
        limit: int,
    ) -> list[DenseCandidateRecord]: ...


class DenseRetrievalService:
    """Embed one bounded query and rank only shared authorized candidates."""

    def __init__(
        self,
        repository: DenseRetrievalReader,
        embedding_provider: EmbeddingProvider,
        *,
        query_max_characters: int = 2000,
        candidate_count: int = 30,
    ) -> None:
        if not 1 <= query_max_characters <= 2000:
            raise ValueError("query_max_characters must be between 1 and 2000")
        if not 1 <= candidate_count <= 100:
            raise ValueError("candidate_count must be between 1 and 100")
        self._repository = repository
        self._embedding_provider = embedding_provider
        self._query_max_characters = query_max_characters
        self._candidate_count = candidate_count

    def retrieve(
        self,
        current_user: CurrentUser,
        request: RetrievalRequest,
    ) -> RetrievalResponse:
        """Return safe Dense candidates or one typed retrieval failure."""

        if len(request.query) > self._query_max_characters:
            raise RetrievalInputError
        identity = self._embedding_provider.identity
        try:
            public_identity = RetrievalEmbeddingIdentity.model_validate(
                asdict(identity)
            )
        except (TypeError, ValidationError):
            raise RetrievalInternalError from None

        stored_identities = _database_call(
            lambda: self._repository.list_authorized_embedding_identities(current_user)
        )
        if not stored_identities:
            return RetrievalResponse(
                mode="dense",
                embedding_identity=public_identity,
                results=[],
            )
        if asdict(identity) not in stored_identities:
            raise RetrievalEmbeddingIdentityMismatchError

        try:
            batch = self._embedding_provider.embed(
                [request.query],
                purpose=EmbeddingPurpose.QUERY,
            )
        except EmbeddingInputError:
            raise RetrievalInputError from None
        except EmbeddingProviderError:
            raise RetrievalEmbeddingProviderUnavailableError from None
        query_vector = _validated_query_vector(batch, identity)

        candidates = _database_call(
            lambda: self._repository.search_dense(
                current_user,
                query_vector=query_vector,
                embedding_identity=identity,
                limit=self._candidate_count,
            )
        )
        try:
            results = [
                _result_from_candidate(candidate, rank=rank)
                for rank, candidate in enumerate(candidates, start=1)
            ]
            return RetrievalResponse(
                mode="dense",
                embedding_identity=public_identity,
                results=results,
            )
        except (TypeError, ValueError, ValidationError):
            raise RetrievalInternalError from None


def _validated_query_vector(
    batch: EmbeddingBatch,
    identity: EmbeddingIdentity,
) -> tuple[float, ...]:
    if (
        batch.purpose is not EmbeddingPurpose.QUERY
        or batch.identity != identity
        or len(batch.vectors) != 1
        or len(batch.cache_keys) != 1
    ):
        raise RetrievalEmbeddingProviderUnavailableError
    vector = batch.vectors[0]
    if len(vector) != identity.dimensions or any(
        not isinstance(value, Real)
        or isinstance(value, bool)
        or not math.isfinite(float(value))
        for value in vector
    ):
        raise RetrievalEmbeddingProviderUnavailableError
    normalized = tuple(float(value) for value in vector)
    norm = math.sqrt(sum(value * value for value in normalized))
    if not math.isclose(norm, 1.0, rel_tol=1e-3, abs_tol=1e-3):
        raise RetrievalEmbeddingProviderUnavailableError
    return normalized


def _result_from_candidate(
    candidate: DenseCandidateRecord,
    *,
    rank: int,
) -> RetrievalResult:
    distance = candidate.distance
    if not math.isfinite(distance) or distance < -1e-6 or distance > 2 + 1e-6:
        raise ValueError("cosine distance is outside its safe range")
    distance = min(2.0, max(0.0, distance))
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
            dense=DenseRetrievalScore(
                rank=rank,
                distance=distance,
                similarity=1.0 - distance,
            )
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

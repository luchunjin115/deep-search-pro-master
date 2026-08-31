"""Typed retrieval failures with fixed public messages and no raw cause text."""

from __future__ import annotations

from app.core.errors import ApplicationError


class RetrievalInputError(ApplicationError):
    """A query cannot safely enter the retrieval pipeline."""

    def __init__(self) -> None:
        super().__init__(
            "VALIDATION_ERROR",
            "检索问题不符合长度或格式限制",
            retryable=False,
            field="query",
        )


class RetrievalEmbeddingProviderUnavailableError(ApplicationError):
    """The configured query Embedding provider is temporarily unavailable."""

    def __init__(self) -> None:
        super().__init__(
            "PROVIDER_ERROR",
            "检索向量服务暂时不可用，请稍后重试",
            retryable=True,
        )


class RetrievalEmbeddingIdentityMismatchError(ApplicationError):
    """Query and active index Embedding identities cannot be mixed safely."""

    def __init__(self) -> None:
        super().__init__(
            "INTERNAL_ERROR",
            "检索索引与当前向量模型身份不一致",
            retryable=False,
        )


class RetrievalDatabaseUnavailableError(ApplicationError):
    """PostgreSQL could not accept the bounded retrieval read."""

    def __init__(self) -> None:
        super().__init__(
            "DATABASE_UNAVAILABLE",
            "检索数据库暂时不可用，请稍后重试",
            retryable=True,
        )


class RetrievalDatabaseTimeoutError(ApplicationError):
    """PostgreSQL cancelled retrieval at its controlled statement timeout."""

    def __init__(self) -> None:
        super().__init__(
            "DATABASE_TIMEOUT",
            "检索数据库查询超时，请稍后重试",
            retryable=True,
        )


class RetrievalInternalError(ApplicationError):
    """An unknown retrieval failure safe for a future API or Tool boundary."""

    def __init__(self) -> None:
        super().__init__(
            "INTERNAL_ERROR",
            "检索暂时无法完成，请稍后重试",
            retryable=True,
        )

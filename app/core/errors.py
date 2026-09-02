"""Safe business errors shared by M1 services and future API/Tool adapters."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Literal
from uuid import UUID

from app.schemas.common import ErrorCode, ErrorDetail


class ApplicationError(Exception):
    """A deliberate, frontend-safe business failure rather than a raw exception."""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        retryable: bool,
        field: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.field = field

    def to_detail(self) -> ErrorDetail:
        """Convert the internal exception into the strict public error contract."""

        return ErrorDetail(
            code=self.code,
            message=self.message,
            retryable=self.retryable,
            field=self.field,
        )


class ProductNotFoundError(ApplicationError):
    """The tenant has no unique, usable product/specification match."""

    def __init__(self, *, missing_specs: bool = False) -> None:
        message = (
            "已找到商品，但没有可用的商品规格"
            if missing_specs
            else "未找到匹配的商品，请检查商品名称或SKU"
        )
        super().__init__(
            "PRODUCT_NOT_FOUND",
            message,
            retryable=False,
            field="product_query",
        )


class AmbiguousProductError(ApplicationError):
    """A broad product term matched more than one SKU."""

    def __init__(self, candidate_skus: Iterable[str]) -> None:
        self.candidate_skus = tuple(sorted(set(candidate_skus)))
        super().__init__(
            "AMBIGUOUS_PRODUCT",
            "找到多个匹配商品，请使用更精确的商品名称或SKU",
            retryable=False,
            field="product_query",
        )


class InternalDataContractError(ApplicationError):
    """Stored data cannot safely satisfy an M1 public response contract."""

    def __init__(self) -> None:
        super().__init__(
            "INTERNAL_ERROR",
            "商品数据不符合M1演示合同",
            retryable=False,
        )


class InventoryNotFoundError(ApplicationError):
    """No inventory snapshot exists inside the requested tenant and location."""

    def __init__(self) -> None:
        super().__init__(
            "INVENTORY_NOT_FOUND",
            "未找到匹配的库存记录",
            retryable=False,
            field="warehouse_code",
        )


class WarehouseRequiredError(ApplicationError):
    """A market contains multiple warehouses and needs a precise code."""

    def __init__(self) -> None:
        super().__init__(
            "VALIDATION_ERROR",
            "该市场存在多个仓库，请指定warehouse_code",
            retryable=False,
            field="warehouse_code",
        )


class DatabaseTimeoutError(ApplicationError):
    """PostgreSQL cancelled a query after its controlled statement timeout."""

    def __init__(self) -> None:
        super().__init__(
            "DATABASE_TIMEOUT",
            "库存数据库查询超时，请稍后重试",
            retryable=True,
        )


class DatabaseQueryError(ApplicationError):
    """A safe replacement for an unexpected SQLAlchemy/driver exception."""

    def __init__(self) -> None:
        super().__init__(
            "INTERNAL_ERROR",
            "库存数据库查询失败",
            retryable=True,
        )


class InventoryDataContractError(ApplicationError):
    """Stored inventory cannot safely satisfy the M1 result Schema."""

    def __init__(self) -> None:
        super().__init__(
            "INTERNAL_ERROR",
            "库存数据不符合M1演示合同",
            retryable=False,
        )


class EvidencePersistenceError(ApplicationError):
    """Database Evidence could not be linked and persisted safely."""

    def __init__(self) -> None:
        super().__init__(
            "INTERNAL_ERROR",
            "库存证据保存失败",
            retryable=True,
        )


class KnowledgeEvidencePersistenceError(ApplicationError):
    """Document Evidence could not be linked and persisted safely."""

    def __init__(self) -> None:
        super().__init__(
            "INTERNAL_ERROR",
            "文档证据保存失败",
            retryable=True,
        )


class CitationValidationError(ApplicationError):
    """An answer referenced Evidence outside its current Context allow-list."""

    def __init__(self) -> None:
        super().__init__(
            "VALIDATION_ERROR",
            "回答包含无效或不属于当前上下文的证据引用",
            retryable=False,
            field="citations",
        )


class InvalidCredentialsError(ApplicationError):
    """An email/password pair did not identify one active M1 user."""

    def __init__(self) -> None:
        super().__init__(
            "UNAUTHENTICATED",
            "邮箱或密码错误",
            retryable=False,
        )


class InvalidAccessTokenError(ApplicationError):
    """A bearer token is missing, expired, forged, or no longer usable."""

    def __init__(self) -> None:
        super().__init__(
            "UNAUTHENTICATED",
            "登录凭证无效或已过期，请重新登录",
            retryable=False,
        )


class InactiveUserError(ApplicationError):
    """A known identity has been disabled since credential issuance."""

    def __init__(self) -> None:
        super().__init__(
            "UNAUTHENTICATED",
            "账号当前不可用",
            retryable=False,
        )


class AuthenticationDataContractError(ApplicationError):
    """Stored identity data cannot form a safe M1 CurrentUser."""

    def __init__(self) -> None:
        super().__init__(
            "INTERNAL_ERROR",
            "账号数据不符合M1演示合同",
            retryable=False,
        )


class AuthenticationDatabaseError(ApplicationError):
    """A database error occurred while refreshing authenticated identity."""

    def __init__(self) -> None:
        super().__init__(
            "INTERNAL_ERROR",
            "身份数据库查询失败",
            retryable=True,
        )


class ToolNotAllowedError(ApplicationError):
    """The requested name is not present in the active ToolRegistry."""

    def __init__(self) -> None:
        super().__init__(
            "FORBIDDEN",
            "请求的Tool未注册或不可用",
            retryable=False,
            field="tool",
        )


class RolePermissionDeniedError(ApplicationError):
    """None of the user's current roles may call the registered Tool."""

    def __init__(self) -> None:
        super().__init__(
            "FORBIDDEN",
            "当前账号无权使用该Tool",
            retryable=False,
            field="tool",
        )


class TenantPermissionDeniedError(ApplicationError):
    """The trusted target tenant differs from the authenticated tenant."""

    def __init__(self) -> None:
        super().__init__(
            "FORBIDDEN",
            "当前账号无权访问该租户数据",
            retryable=False,
            field="tenant_id",
        )


class MarketPermissionDeniedError(ApplicationError):
    """The requested market is absent from the user's current data scope."""

    def __init__(self) -> None:
        super().__init__(
            "FORBIDDEN",
            "当前账号无权访问该市场数据",
            retryable=False,
            field="market_code",
        )


class UnsafeToolPermissionError(ApplicationError):
    """The registered operation violates M1's system-wide read-only policy."""

    def __init__(self) -> None:
        super().__init__(
            "FORBIDDEN",
            "M1只允许执行已登记的只读Tool",
            retryable=False,
            field="tool",
        )


class BudgetExceededError(ApplicationError):
    """A model/tool count, repetition, or total runtime budget was exhausted."""

    def __init__(
        self,
        reason: str,
        message: str = "本次执行已超过M1运行预算",
    ) -> None:
        self.reason = reason
        super().__init__(
            "BUDGET_EXCEEDED",
            message,
            retryable=False,
            field="execution_budget",
        )


class ToolTimeoutError(BudgetExceededError):
    """One Tool finished after its registered M1 timeout."""

    def __init__(self) -> None:
        super().__init__(
            "tool_timeout",
            "Tool执行超过M1允许时间",
        )


class ToolExecutionError(ApplicationError):
    """An unexpected Tool exception mapped to a safe public failure."""

    def __init__(self) -> None:
        super().__init__(
            "INTERNAL_ERROR",
            "Tool执行失败",
            retryable=False,
        )


class AgentWorkflowError(ApplicationError):
    """An unexpected graph/runtime failure mapped to one safe public error."""

    def __init__(self) -> None:
        super().__init__(
            "INTERNAL_ERROR",
            "Agent流程执行失败",
            retryable=False,
        )


class ThreadNotFoundError(ApplicationError):
    """The requested active thread is absent or not owned by this identity."""

    def __init__(self) -> None:
        super().__init__(
            "THREAD_NOT_FOUND",
            "未找到可访问的会话",
            retryable=False,
            field="thread_id",
        )


class EvidenceNotFoundError(ApplicationError):
    """Evidence is absent or hidden by tenant/market scope."""

    def __init__(self) -> None:
        super().__init__(
            "EVIDENCE_NOT_FOUND",
            "未找到可访问的证据",
            retryable=False,
            field="evidence_id",
        )


class ConversationPersistenceError(ApplicationError):
    """A thread or message could not be persisted safely."""

    def __init__(self) -> None:
        super().__init__(
            "INTERNAL_ERROR",
            "会话数据保存失败",
            retryable=True,
        )


class EvidenceReadError(ApplicationError):
    """Evidence could not be loaded or validated safely."""

    def __init__(self) -> None:
        super().__init__(
            "INTERNAL_ERROR",
            "证据数据读取失败",
            retryable=True,
        )


class FileNotFoundError(ApplicationError):
    """A file is absent, deleted, cross-tenant, or not authorized."""

    def __init__(self) -> None:
        super().__init__(
            "FILE_NOT_FOUND",
            "未找到可访问的文件",
            retryable=False,
            field="file_id",
        )


class DocumentNotFoundError(ApplicationError):
    """A document is absent, deleted, cross-tenant, or not authorized."""

    def __init__(self) -> None:
        super().__init__(
            "DOCUMENT_NOT_FOUND",
            "未找到可访问的文档",
            retryable=False,
            field="document_id",
        )


class FileStateConflictError(ApplicationError):
    """The requested file-state transition is not part of the M2 state machine."""

    def __init__(self) -> None:
        super().__init__(
            "FILE_STATE_CONFLICT",
            "文件当前状态不允许执行该操作",
            retryable=False,
            field="status",
        )


class DocumentStateConflictError(ApplicationError):
    """A document version cannot make the requested state transition."""

    def __init__(self) -> None:
        super().__init__(
            "DOCUMENT_STATE_CONFLICT",
            "文档版本当前状态不允许执行该操作",
            retryable=False,
            field="status",
        )


class DocumentParsingError(ApplicationError):
    """One claimed document parse failed without exposing private internals."""

    def __init__(self) -> None:
        super().__init__(
            "INTERNAL_ERROR",
            "文档解析未能完成，请稍后重试",
            retryable=True,
        )


class DocumentChunkPublicationError(ApplicationError):
    """One claimed Chunk publication failed without exposing private internals."""

    def __init__(self) -> None:
        super().__init__(
            "INTERNAL_ERROR",
            "文档切块未能完成，请稍后重试",
            retryable=True,
        )


class DocumentIndexingError(ApplicationError):
    """One claimed document index attempt failed without leaking internals."""

    def __init__(self) -> None:
        super().__init__(
            "INTERNAL_ERROR",
            "文档索引未能完成，请稍后重试",
            retryable=True,
        )


class EmbeddingInputError(ApplicationError):
    """Embedding input is empty, malformed, or outside the bounded contract."""

    def __init__(self) -> None:
        super().__init__(
            "VALIDATION_ERROR",
            "向量文本不符合长度或数量限制",
            retryable=False,
            field="texts",
        )


class EmbeddingProviderError(ApplicationError):
    """Embedding generation failed without exposing text, paths, or model internals."""

    def __init__(self, *, retryable: bool = False) -> None:
        super().__init__(
            "INTERNAL_ERROR",
            "文本向量生成失败，请检查配置或稍后重试",
            retryable=retryable,
        )


class RerankerInputError(ApplicationError):
    """Reranker pairs are malformed or outside the bounded provider contract."""

    def __init__(self, *, field: Literal["query", "passages"]) -> None:
        super().__init__(
            "VALIDATION_ERROR",
            "Reranker输入不符合长度或数量限制",
            retryable=False,
            field=field,
        )


class RerankerProviderError(ApplicationError):
    """Reranker scoring failed without exposing text or runtime internals."""

    def __init__(self, *, retryable: bool = False) -> None:
        super().__init__(
            "PROVIDER_ERROR",
            "Reranker评分失败，请检查配置或稍后重试",
            retryable=retryable,
        )


class DocumentVersionConflictError(ApplicationError):
    """A document already contains the same immutable content revision."""

    def __init__(self) -> None:
        super().__init__(
            "DOCUMENT_VERSION_CONFLICT",
            "该文档已存在相同内容版本",
            retryable=False,
            field="file_id",
        )


class DocumentAclConflictError(ApplicationError):
    """An identical explicit document grant already exists."""

    def __init__(self) -> None:
        super().__init__(
            "DOCUMENT_ACL_CONFLICT",
            "该文档授权已存在",
            retryable=False,
            field="subject_type",
        )


class FileMetadataError(ApplicationError):
    """Trusted Storage facts and normalized file metadata disagree."""

    def __init__(self) -> None:
        super().__init__(
            "VALIDATION_ERROR",
            "文件元数据格式无效",
            retryable=False,
            field="file",
        )


class FileUploadValidationError(ApplicationError):
    """One multipart file violates the bounded M2 upload contract."""

    def __init__(self) -> None:
        super().__init__(
            "VALIDATION_ERROR",
            "上传文件格式、类型或大小无效",
            retryable=False,
            field="files",
        )


class FileStorageError(ApplicationError):
    """The managed binary object could not be safely written or opened."""

    def __init__(self) -> None:
        super().__init__(
            "INTERNAL_ERROR",
            "文件存储暂时无法完成操作",
            retryable=True,
        )


class FileReadLocatorError(ApplicationError):
    """A bounded public locator does not exist in the authorized artifact."""

    def __init__(self) -> None:
        super().__init__(
            "VALIDATION_ERROR",
            "文件读取位置与已解析内容不匹配",
            retryable=False,
            field="locator",
        )


class FileReadError(ApplicationError):
    """A parsed file artifact could not be loaded or validated safely."""

    def __init__(self) -> None:
        super().__init__(
            "INTERNAL_ERROR",
            "文件解析内容读取失败，请稍后重试",
            retryable=True,
        )


class KnowledgePersistenceError(ApplicationError):
    """Knowledge metadata could not be read or persisted safely."""

    def __init__(self) -> None:
        super().__init__(
            "INTERNAL_ERROR",
            "知识库元数据处理失败",
            retryable=True,
        )


class KnowledgeDataContractError(ApplicationError):
    """Stored knowledge metadata cannot form a safe response."""

    def __init__(self) -> None:
        super().__init__(
            "INTERNAL_ERROR",
            "知识库元数据不符合安全合同",
            retryable=False,
        )


class RequestTransactionError(ApplicationError):
    """The request transaction failed before its response was sent."""

    def __init__(self) -> None:
        super().__init__(
            "INTERNAL_ERROR",
            "请求数据提交失败",
            retryable=True,
        )


class AgentTerminalError(ApplicationError):
    """Carry one safe graph failure and its trace to the HTTP boundary."""

    def __init__(
        self,
        detail: ErrorDetail,
        *,
        terminal_status: Literal["failed", "denied", "timed_out"],
        trace_id: UUID,
    ) -> None:
        self.terminal_status = terminal_status
        self.trace_id = trace_id
        super().__init__(
            detail.code,
            detail.message,
            retryable=detail.retryable,
            field=detail.field,
        )


class TracePersistenceError(ApplicationError):
    """A required AgentRun or ToolCall audit update could not be persisted."""

    def __init__(self) -> None:
        super().__init__(
            "INTERNAL_ERROR",
            "执行轨迹保存失败",
            retryable=True,
        )


ProviderErrorReason = Literal[
    "unsupported_question",
    "timeout",
    "unavailable",
    "invalid_output",
]


class ProviderError(ApplicationError):
    """A safe boundary error for Mock/Qwen Tool-proposal failures."""

    def __init__(
        self,
        reason: ProviderErrorReason,
        message: str,
        *,
        retryable: bool,
    ) -> None:
        self.reason = reason
        super().__init__(
            "PROVIDER_ERROR",
            message,
            retryable=retryable,
            field="message",
        )


class UnsupportedProviderQuestionError(ProviderError):
    """The specialized M1 Provider cannot propose a Tool for one question."""

    def __init__(self) -> None:
        super().__init__(
            "unsupported_question",
            "当前问题无法解析为M1库存查询",
            retryable=False,
        )


class ProviderTimeoutError(ProviderError):
    """The external model did not return within the configured timeout."""

    def __init__(self) -> None:
        super().__init__(
            "timeout",
            "模型Tool建议超时，请稍后重试",
            retryable=True,
        )


class ProviderUnavailableError(ProviderError):
    """The external model endpoint rejected or could not serve the request."""

    def __init__(self, *, retryable: bool = True) -> None:
        super().__init__(
            "unavailable",
            "模型服务暂时不可用",
            retryable=retryable,
        )


class ProviderOutputError(ProviderError):
    """The model response failed the strict Tool proposal contract."""

    def __init__(self) -> None:
        super().__init__(
            "invalid_output",
            "模型返回的Tool调用建议格式无效",
            retryable=False,
        )

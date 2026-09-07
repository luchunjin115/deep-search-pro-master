"""集中读取和校验M1/M2环境变量。"""

from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BGE_M3_MODEL_ID = "BAAI/bge-m3"
BGE_M3_REVISION = "5617a9f61b028005a4858fdac845db406aefb181"
BGE_RERANKER_MODEL_ID = "BAAI/bge-reranker-v2-m3"
BGE_RERANKER_REVISION = "953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e"
RETRIEVAL_QUERY_HARD_MAX_CHARACTERS = 2000
RETRIEVAL_CANDIDATE_HARD_MAX = 100
CONTEXT_TOKEN_HARD_MAX = 16_000
CONTEXT_SEGMENT_HARD_MAX = 12
CONTEXT_NEIGHBOR_WINDOW_HARD_MAX = 1


class Settings(BaseSettings):
    """应用运行配置。

    默认值只保证本地Mock模式能够安全导入。真实密码和API Key必须来自.env，
    业务模块不得在各自文件中重复读取环境变量。
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "Deep Search Pro M1"
    app_env: Literal["development", "test", "production"] = "development"
    app_host: str = "127.0.0.1"
    app_port: int = Field(default=8000, ge=1, le=65535)
    api_v1_prefix: str = "/api/v1"
    cors_origins: list[str] = ["http://localhost:3000"]

    database_url: str = (
        "postgresql+psycopg://deep_search_app:"
        "local-demo-password-change-me@127.0.0.1:5433/deep_search_pro"
    )
    database_echo: bool = False
    database_connect_timeout_seconds: int = Field(default=5, ge=1, le=30)
    database_statement_timeout_ms: int = Field(default=2000, ge=50, le=30000)

    llm_provider: Literal["mock", "qwen"] = "mock"
    qwen_model: str = Field(
        default="qwen3.8-max",
        min_length=1,
        max_length=100,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,99}$",
    )
    qwen_base_url: str = Field(
        default="https://dashscope.aliyuncs.com/compatible-mode/v1",
        min_length=1,
        max_length=500,
    )
    qwen_api_key: SecretStr | None = None
    qwen_timeout_seconds: float = Field(default=5.0, ge=1.0, le=30.0)
    qwen_agent_max_output_tokens: int = Field(default=4096, ge=256, le=8192)

    jwt_secret_key: SecretStr = SecretStr(
        "local-development-only-change-before-production"
    )
    jwt_algorithm: Literal["HS256"] = "HS256"
    jwt_expire_minutes: int = Field(default=60, ge=5, le=1440)

    m1_demo_password: SecretStr = SecretStr("M1-demo-only-change-me")

    execution_max_model_calls: int = Field(default=2, ge=1, le=10)
    execution_max_tool_calls: int = Field(default=2, ge=1, le=10)
    execution_max_repeat_tool_calls: int = Field(default=1, ge=1, le=3)
    execution_total_timeout_ms: int = Field(default=8000, ge=1000, le=60000)

    # M2-03使用本地Storage配置；文件上传API仍留到M2-06。
    storage_backend: Literal["local"] = "local"
    local_storage_root: Path = Path("data/storage")
    model_cache_root: Path = Path("data/model-cache")

    # M2-11.4供显式复杂文档路由使用；默认disabled保证普通测试不加载模型。
    docling_backend: Literal["disabled", "docling"] = "disabled"
    docling_model_cache_root: Path = Path("data/model-cache/docling")
    docling_device: Literal["cpu"] = "cpu"
    docling_num_threads: int = Field(default=4, ge=1, le=4)
    docling_document_timeout_seconds: int = Field(default=120, ge=90, le=300)
    docling_ocr_engine: Literal["rapidocr"] = "rapidocr"
    docling_enable_remote_services: bool = False
    docling_allow_external_plugins: bool = False

    upload_allowed_extensions: tuple[str, ...] = (
        ".pdf",
        ".docx",
        ".xlsx",
        ".csv",
    )
    upload_max_file_size_bytes: int = Field(
        default=25 * 1024 * 1024,
        ge=1 * 1024 * 1024,
        le=100 * 1024 * 1024,
    )
    upload_max_files_per_request: int = Field(default=5, ge=1, le=10)
    upload_stream_chunk_size_bytes: int = Field(
        default=1 * 1024 * 1024,
        ge=64 * 1024,
        le=4 * 1024 * 1024,
    )
    file_read_max_artifact_bytes: int = Field(
        default=100 * 1024 * 1024,
        ge=1 * 1024 * 1024,
        le=400 * 1024 * 1024,
    )

    # M2-07文本型PDF解析保护；不启用OCR或页面渲染识别。
    pdf_max_pages: int = Field(default=500, ge=1, le=2000)
    pdf_max_extracted_characters: int = Field(
        default=5_000_000,
        ge=10_000,
        le=20_000_000,
    )
    pdf_low_text_character_threshold: int = Field(default=20, ge=1, le=500)

    # M2-08 DOCX解析保护；先检查ZIP中央目录，再由python-docx读取正文。
    docx_max_archive_members: int = Field(default=5000, ge=10, le=20_000)
    docx_max_uncompressed_bytes: int = Field(
        default=100 * 1024 * 1024,
        ge=10 * 1024 * 1024,
        le=500 * 1024 * 1024,
    )
    docx_max_compression_ratio: int = Field(default=200, ge=10, le=1000)
    docx_max_blocks: int = Field(default=50_000, ge=100, le=100_000)
    docx_max_table_cells: int = Field(default=200_000, ge=100, le=500_000)
    docx_max_extracted_characters: int = Field(
        default=5_000_000,
        ge=10_000,
        le=20_000_000,
    )

    # M2-09 XLSX/CSV解析保护；表格只作为知识文件读取，不写业务表。
    xlsx_max_archive_members: int = Field(default=5000, ge=10, le=20_000)
    xlsx_max_uncompressed_bytes: int = Field(
        default=100 * 1024 * 1024,
        ge=10 * 1024 * 1024,
        le=500 * 1024 * 1024,
    )
    xlsx_max_compression_ratio: int = Field(default=200, ge=10, le=1000)
    xlsx_max_sheets: int = Field(default=100, ge=1, le=1000)
    xlsx_max_rows_per_sheet: int = Field(default=100_000, ge=100, le=1_048_576)
    xlsx_max_columns: int = Field(default=500, ge=10, le=16_384)
    xlsx_max_cells: int = Field(default=500_000, ge=1000, le=2_000_000)
    xlsx_max_extracted_characters: int = Field(
        default=5_000_000,
        ge=10_000,
        le=20_000_000,
    )
    csv_max_rows: int = Field(default=200_000, ge=100, le=1_000_000)
    csv_max_columns: int = Field(default=500, ge=2, le=10_000)
    csv_max_cells: int = Field(default=500_000, ge=1000, le=2_000_000)
    csv_max_extracted_characters: int = Field(
        default=5_000_000,
        ge=10_000,
        le=20_000_000,
    )

    # Fake是日常测试的安全默认值；本配置对象不会加载或下载模型。
    embedding_backend: Literal["fake", "bge"] = "fake"
    embedding_model: str = Field(
        default="BAAI/bge-m3",
        min_length=1,
        max_length=200,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,199}$",
    )
    embedding_revision: str = Field(
        default="main",
        min_length=1,
        max_length=100,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,99}$",
    )
    embedding_dimensions: int = Field(default=1024, ge=1024, le=1024)
    embedding_normalize: bool = True
    embedding_batch_size: int = Field(default=4, ge=1, le=32)
    embedding_pooling: Literal["cls"] = "cls"
    embedding_max_length: int = Field(default=8192, ge=8192, le=8192)
    embedding_precision: Literal["float32", "float16", "bfloat16"] = "float32"

    reranker_backend: Literal["fake", "bge"] = "fake"
    reranker_model: str = Field(
        default=BGE_RERANKER_MODEL_ID,
        min_length=1,
        max_length=200,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,199}$",
    )
    reranker_revision: str = Field(
        default=BGE_RERANKER_REVISION,
        min_length=1,
        max_length=100,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,99}$",
    )
    reranker_batch_size: int = Field(default=2, ge=1, le=16)
    reranker_max_length: int = Field(default=8192, ge=8192, le=8192)
    reranker_precision: Literal["float32", "float16", "bfloat16"] = "float32"
    model_device: Literal["cpu", "cuda", "auto"] = "cpu"
    model_local_files_only: bool = True

    chunk_target_tokens: int = Field(default=600, ge=400, le=700)
    chunk_max_tokens: int = Field(default=700, ge=400, le=1000)
    chunk_overlap_tokens: int = Field(default=100, ge=80, le=120)
    chunk_heading_context_max_tokens: int = Field(default=120, ge=20, le=200)
    chunk_table_row_overlap: int = Field(default=1, ge=0, le=20)
    chunk_repeated_edge_min_pages: int = Field(default=2, ge=2, le=20)
    retrieval_query_max_characters: int = Field(
        default=RETRIEVAL_QUERY_HARD_MAX_CHARACTERS,
        ge=1,
        le=RETRIEVAL_QUERY_HARD_MAX_CHARACTERS,
    )
    dense_candidate_count: int = Field(
        default=30,
        ge=5,
        le=RETRIEVAL_CANDIDATE_HARD_MAX,
    )
    lexical_candidate_count: int = Field(
        default=30,
        ge=5,
        le=RETRIEVAL_CANDIDATE_HARD_MAX,
    )
    hybrid_candidate_count: int = Field(
        default=30,
        ge=5,
        le=RETRIEVAL_CANDIDATE_HARD_MAX,
    )
    rrf_k: int = Field(default=60, ge=1, le=200)
    reranker_top_k: int = Field(default=8, ge=5, le=8)
    # M2-18上下文预算完全由服务端控制；调用者不能扩大这些硬上限。
    context_max_tokens: int = Field(default=4000, ge=700, le=CONTEXT_TOKEN_HARD_MAX)
    context_max_segments: int = Field(
        default=CONTEXT_SEGMENT_HARD_MAX,
        ge=5,
        le=CONTEXT_SEGMENT_HARD_MAX,
    )
    context_neighbor_window: int = Field(
        default=1,
        ge=0,
        le=CONTEXT_NEIGHBOR_WINDOW_HARD_MAX,
    )

    @field_validator("api_v1_prefix")
    @classmethod
    def validate_api_v1_prefix(cls, value: str) -> str:
        normalized = value.rstrip("/")
        if not normalized.startswith("/"):
            raise ValueError("API_V1_PREFIX必须以/开头")
        return normalized

    @field_validator("cors_origins")
    @classmethod
    def validate_cors_origins(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("CORS_ORIGINS至少需要一个前端地址")
        return value

    @field_validator("qwen_base_url")
    @classmethod
    def validate_qwen_base_url(cls, value: str) -> str:
        normalized = value.rstrip("/")
        parsed = urlsplit(normalized)
        if (
            parsed.scheme != "https"
            or not parsed.netloc
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("QWEN_BASE_URL必须是无凭据、查询参数和片段的HTTPS地址")
        return normalized

    @field_validator("upload_allowed_extensions")
    @classmethod
    def validate_upload_allowed_extensions(
        cls,
        value: tuple[str, ...],
    ) -> tuple[str, ...]:
        normalized = tuple(extension.strip().lower() for extension in value)
        supported = {".pdf", ".docx", ".xlsx", ".csv"}
        if len(normalized) != len(set(normalized)):
            raise ValueError("UPLOAD_ALLOWED_EXTENSIONS不能包含重复扩展名")
        if set(normalized) != supported:
            raise ValueError(
                "UPLOAD_ALLOWED_EXTENSIONS必须且只能包含PDF、DOCX、XLSX和CSV"
            )
        return normalized

    @field_validator(
        "local_storage_root",
        "model_cache_root",
        "docling_model_cache_root",
    )
    @classmethod
    def validate_managed_directory(cls, value: Path) -> Path:
        if value == Path(".") or (value.anchor and value == Path(value.anchor)):
            raise ValueError("M2托管目录不能是当前目录或文件系统根目录")
        return value

    @field_validator("embedding_normalize")
    @classmethod
    def validate_embedding_normalize(cls, value: bool) -> bool:
        if not value:
            raise ValueError("EMBEDDING_NORMALIZE必须为True")
        return value

    @model_validator(mode="after")
    def validate_environment_secrets(self) -> "Settings":
        if self.llm_provider == "qwen" and (
            self.qwen_api_key is None
            or not self.qwen_api_key.get_secret_value().strip()
        ):
            raise ValueError("LLM_PROVIDER=qwen时必须配置非空QWEN_API_KEY")

        jwt_secret = self.jwt_secret_key.get_secret_value()
        if self.app_env == "production" and jwt_secret.startswith("local-development"):
            raise ValueError("生产环境必须替换JWT_SECRET_KEY")

        if self.local_storage_root == self.model_cache_root:
            raise ValueError("LOCAL_STORAGE_ROOT与MODEL_CACHE_ROOT必须分开")
        if self.local_storage_root == self.docling_model_cache_root:
            raise ValueError("LOCAL_STORAGE_ROOT与DOCLING_MODEL_CACHE_ROOT必须分开")
        try:
            self.docling_model_cache_root.relative_to(self.model_cache_root)
        except ValueError:
            raise ValueError(
                "DOCLING_MODEL_CACHE_ROOT必须位于MODEL_CACHE_ROOT内"
            ) from None
        if self.docling_enable_remote_services:
            raise ValueError("DOCLING_ENABLE_REMOTE_SERVICES必须为False")
        if self.docling_allow_external_plugins:
            raise ValueError("DOCLING_ALLOW_EXTERNAL_PLUGINS必须为False")
        if self.embedding_backend == "bge" and (
            self.embedding_model != BGE_M3_MODEL_ID
            or self.embedding_revision != BGE_M3_REVISION
        ):
            raise ValueError(
                "真实Embedding必须配置固定EMBEDDING_MODEL和EMBEDDING_REVISION"
            )
        if self.embedding_backend == "bge" and not self.model_local_files_only:
            raise ValueError("真实Embedding必须启用本地文件离线模式")
        if self.reranker_backend == "bge" and (
            self.reranker_model != BGE_RERANKER_MODEL_ID
            or self.reranker_revision != BGE_RERANKER_REVISION
        ):
            raise ValueError(
                "真实Reranker必须配置固定RERANKER_MODEL和RERANKER_REVISION"
            )
        if self.reranker_backend == "bge" and not self.model_local_files_only:
            raise ValueError("真实Reranker必须启用本地文件离线模式")
        if self.upload_stream_chunk_size_bytes > self.upload_max_file_size_bytes:
            raise ValueError("上传流式读取块不能大于单文件上限")
        if self.chunk_target_tokens > self.chunk_max_tokens:
            raise ValueError("CHUNK_TARGET_TOKENS不能大于CHUNK_MAX_TOKENS")
        if self.chunk_overlap_tokens >= self.chunk_target_tokens:
            raise ValueError("CHUNK_OVERLAP_TOKENS必须小于CHUNK_TARGET_TOKENS")
        if self.chunk_heading_context_max_tokens >= self.chunk_target_tokens:
            raise ValueError(
                "CHUNK_HEADING_CONTEXT_MAX_TOKENS必须小于CHUNK_TARGET_TOKENS"
            )
        if self.reranker_top_k > min(
            self.dense_candidate_count,
            self.lexical_candidate_count,
            self.hybrid_candidate_count,
        ):
            raise ValueError("RERANKER_TOP_K不能大于任一路候选数量")
        if self.hybrid_candidate_count > (
            self.dense_candidate_count + self.lexical_candidate_count
        ):
            raise ValueError("HYBRID_CANDIDATE_COUNT不能大于两路候选数量之和")
        if self.context_max_tokens < self.chunk_max_tokens:
            raise ValueError("CONTEXT_MAX_TOKENS不能小于CHUNK_MAX_TOKENS")
        if self.context_max_segments < self.reranker_top_k:
            raise ValueError("CONTEXT_MAX_SEGMENTS不能小于RERANKER_TOP_K")
        return self


@lru_cache
def get_settings() -> Settings:
    """每个进程只构建一次配置对象，避免各模块读取到不同设置。"""

    return Settings()

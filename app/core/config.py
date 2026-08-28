"""集中读取和校验M1环境变量。"""

from functools import lru_cache
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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
        return self


@lru_cache
def get_settings() -> Settings:
    """每个进程只构建一次配置对象，避免各模块读取到不同设置。"""

    return Settings()

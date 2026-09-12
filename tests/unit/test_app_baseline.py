from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import Settings
from app.main import create_app


@pytest.fixture(autouse=True)
def clear_m1_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep configuration tests independent from a developer's shell variables."""

    for variable_name in (
        "APP_NAME",
        "APP_ENV",
        "APP_HOST",
        "APP_PORT",
        "API_V1_PREFIX",
        "CORS_ORIGINS",
        "DATABASE_URL",
        "DATABASE_ECHO",
        "DATABASE_CONNECT_TIMEOUT_SECONDS",
        "DATABASE_STATEMENT_TIMEOUT_MS",
        "LLM_PROVIDER",
        "QWEN_MODEL",
        "QWEN_BASE_URL",
        "QWEN_API_KEY",
        "QWEN_TIMEOUT_SECONDS",
        "DEEPSEEK_MODEL",
        "DEEPSEEK_BASE_URL",
        "DEEPSEEK_API_KEY",
        "DEEPSEEK_TIMEOUT_SECONDS",
        "DEEPSEEK_AGENT_MAX_OUTPUT_TOKENS",
        "JWT_SECRET_KEY",
        "JWT_ALGORITHM",
        "JWT_EXPIRE_MINUTES",
        "EXECUTION_MAX_MODEL_CALLS",
        "EXECUTION_MAX_TOOL_CALLS",
        "EXECUTION_MAX_REPEAT_TOOL_CALLS",
        "EXECUTION_TOTAL_TIMEOUT_MS",
    ):
        monkeypatch.delenv(variable_name, raising=False)


def test_settings_use_safe_local_defaults() -> None:
    settings = Settings(_env_file=None)

    assert settings.app_env == "development"
    assert settings.llm_provider == "mock"
    assert settings.api_v1_prefix == "/api/v1"
    assert settings.cors_origins == ["http://localhost:3000"]
    assert settings.database_statement_timeout_ms == 2000


def test_env_example_is_a_valid_m1_configuration() -> None:
    settings = Settings(_env_file=".env.example")

    assert settings.app_env == "development"
    assert settings.llm_provider == "mock"
    assert settings.database_url == (
        "postgresql+psycopg://deep_search_app:"
        "local-demo-password-change-me@127.0.0.1:5433/deep_search_pro"
    )


def test_settings_normalize_api_prefix() -> None:
    settings = Settings(_env_file=None, api_v1_prefix="/api/v1/")

    assert settings.api_v1_prefix == "/api/v1"


def test_qwen_requires_api_key() -> None:
    with pytest.raises(ValidationError, match="QWEN_API_KEY"):
        Settings(_env_file=None, llm_provider="qwen", qwen_api_key=None)


def test_production_rejects_local_jwt_secret() -> None:
    with pytest.raises(ValidationError, match="JWT_SECRET_KEY"):
        Settings(_env_file=None, app_env="production")


def test_health_endpoint_reports_database_connection() -> None:
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url="sqlite+pysqlite:///:memory:",
    )
    client = TestClient(create_app(settings))

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "Deep Search Pro M1",
        "environment": "test",
        "database": "connected",
    }


def test_new_app_source_does_not_import_legacy_runtime() -> None:
    app_root = Path(__file__).parents[2] / "app"
    forbidden_import_roots = {
        "agent",
        "api",
        "tools",
        "rawflow",
        "mysql",
        "ragflow_sdk",
        "tavily",
    }

    for source_file in app_root.rglob("*.py"):
        source = source_file.read_text(encoding="utf-8")
        for forbidden_root in forbidden_import_roots:
            assert f"import {forbidden_root}" not in source
            assert f"from {forbidden_root}" not in source

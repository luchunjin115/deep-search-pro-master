from collections.abc import Generator
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, inspect, text
from sqlalchemy.exc import OperationalError

from app.api.dependencies import DatabaseSession
from app.core.config import Settings
from app.db.session import (
    DatabaseConnectionError,
    check_database_connection,
    create_database_runtime,
)
from app.main import create_app


@pytest.fixture
def postgres_settings() -> Settings:
    return Settings(_env_file=".env.example", app_env="test")


@pytest.fixture
def postgres_engine(postgres_settings: Settings) -> Generator[Engine, None, None]:
    runtime = create_database_runtime(postgres_settings)
    yield runtime.engine
    runtime.engine.dispose()


def test_postgresql_accepts_sqlalchemy_connection(postgres_engine: Engine) -> None:
    check_database_connection(postgres_engine)

    with postgres_engine.connect() as connection:
        assert connection.scalar(text("SELECT current_database()")) == "deep_search_pro"
        assert connection.scalar(text("SELECT current_user")) == "deep_search_app"


def test_health_endpoint_checks_real_postgresql(postgres_settings: Settings) -> None:
    application = create_app(postgres_settings)

    with TestClient(application) as client:
        response = client.get("/health")

    application.state.database_runtime.engine.dispose()
    assert response.status_code == 200
    assert response.json()["database"] == "connected"


def test_request_dependency_commits_successful_work_and_closes_session(
    postgres_settings: Settings,
    postgres_engine: Engine,
) -> None:
    table_name = f"m1_03_commit_{uuid4().hex}"
    runtime = create_database_runtime(postgres_settings)
    application = FastAPI()
    application.state.database_runtime = runtime

    @application.post("/probe")
    async def create_probe(session: DatabaseSession) -> dict[str, str]:
        session.execute(text(f'CREATE TABLE "{table_name}" (value integer NOT NULL)'))
        session.execute(text(f'INSERT INTO "{table_name}" VALUES (1)'))
        return {"status": "created"}

    try:
        with TestClient(application) as client:
            response = client.post("/probe")

        assert response.status_code == 200
        with postgres_engine.connect() as connection:
            assert connection.scalar(text(f'SELECT value FROM "{table_name}"')) == 1

        assert runtime.engine.pool.checkedout() == 0
    finally:
        with postgres_engine.begin() as connection:
            connection.execute(text(f'DROP TABLE IF EXISTS "{table_name}"'))
        runtime.engine.dispose()


def test_request_dependency_rolls_back_failed_work_and_closes_session(
    postgres_settings: Settings,
    postgres_engine: Engine,
) -> None:
    table_name = f"m1_03_rollback_{uuid4().hex}"
    runtime = create_database_runtime(postgres_settings)
    application = FastAPI()
    application.state.database_runtime = runtime

    @application.post("/probe")
    async def create_probe(session: DatabaseSession) -> None:
        session.execute(text(f'CREATE TABLE "{table_name}" (value integer NOT NULL)'))
        raise RuntimeError("force request rollback")

    try:
        with TestClient(application, raise_server_exceptions=False) as client:
            response = client.post("/probe")

        assert response.status_code == 500
        assert not inspect(postgres_engine).has_table(table_name)
        assert runtime.engine.pool.checkedout() == 0
    finally:
        with postgres_engine.begin() as connection:
            connection.execute(text(f'DROP TABLE IF EXISTS "{table_name}"'))
        runtime.engine.dispose()


def test_commit_failure_is_returned_before_success_response(
    postgres_settings: Settings,
    postgres_engine: Engine,
) -> None:
    table_name = f"m1_03_deferred_{uuid4().hex}"
    runtime = create_database_runtime(postgres_settings)
    application = FastAPI()
    application.state.database_runtime = runtime

    @application.post("/probe")
    async def create_probe(session: DatabaseSession) -> dict[str, str]:
        session.execute(
            text(
                f'CREATE TABLE "{table_name}" ('
                "value integer NOT NULL, "
                "UNIQUE (value) DEFERRABLE INITIALLY DEFERRED)"
            )
        )
        session.execute(text(f'INSERT INTO "{table_name}" VALUES (1), (1)'))
        return {"status": "route-finished"}

    try:
        with TestClient(application, raise_server_exceptions=False) as client:
            response = client.post("/probe")

        assert response.status_code == 500
        assert not inspect(postgres_engine).has_table(table_name)
        assert runtime.engine.pool.checkedout() == 0
    finally:
        with postgres_engine.begin() as connection:
            connection.execute(text(f'DROP TABLE IF EXISTS "{table_name}"'))
        runtime.engine.dispose()


def test_connection_failure_exposes_no_credentials() -> None:
    secret = "must-not-leak"
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url=(
            f"postgresql+psycopg://deep_search_app:{secret}@127.0.0.1:1/deep_search_pro"
        ),
        database_connect_timeout_seconds=1,
    )
    runtime = create_database_runtime(settings)

    try:
        with pytest.raises(DatabaseConnectionError) as error:
            check_database_connection(runtime.engine)
    finally:
        runtime.engine.dispose()

    assert str(error.value) == "Database health check failed"
    assert secret not in str(error.value)
    assert error.value.__cause__ is None


def test_health_endpoint_returns_safe_503_when_database_is_unavailable() -> None:
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url=(
            "postgresql+psycopg://deep_search_app:must-not-leak"
            "@127.0.0.1:1/deep_search_pro"
        ),
        database_connect_timeout_seconds=1,
    )
    application = create_app(settings)

    with TestClient(application) as client:
        response = client.get("/health")

    application.state.database_runtime.engine.dispose()
    assert response.status_code == 503
    assert response.json() == {
        "status": "degraded",
        "service": "Deep Search Pro M1",
        "environment": "test",
        "database": "unavailable",
    }
    assert "must-not-leak" not in response.text


def test_driver_error_is_not_part_of_public_database_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class BrokenEngine:
        def connect(self) -> None:
            raise OperationalError(
                "statement", {}, RuntimeError("private-driver-detail")
            )

    monkeypatch.setattr(BrokenEngine, "connect", BrokenEngine.connect)

    with pytest.raises(
        DatabaseConnectionError, match="Database health check failed"
    ) as error:
        check_database_connection(BrokenEngine())  # type: ignore[arg-type]

    assert "private-driver-detail" not in str(error.value)

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
POSTGRES_BASE_DIGEST = (
    "sha256:18cfe3ef5e6815560c98237d6216d1e5119702fb0f3894c8785dd58b8bbe5d73"
)
PGVECTOR_COMMIT = "8ee86c96f0fd72390f890aa8a336fda6d3ab4c6c"


def test_compose_uses_reproducible_pgvector_build_and_existing_named_volume() -> None:
    compose = (PROJECT_ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert "image: deep-search-pro/postgres-pgvector:17.11-0.8.6" in compose
    assert "dockerfile: docker/postgres/Dockerfile" in compose
    assert "postgres_data:/var/lib/postgresql/data" in compose
    assert "name: deep-search-postgres-data" in compose


def test_docker_build_context_only_allows_pgvector_infrastructure_files() -> None:
    dockerignore = (PROJECT_ROOT / ".dockerignore").read_text(encoding="utf-8")

    assert dockerignore.splitlines() == [
        "**",
        "!docker/",
        "!docker/postgres/",
        "!docker/postgres/Dockerfile",
        "!docker/postgres/init/",
        "!docker/postgres/init/001-enable-vector.sql",
    ]
    assert ".env" not in {
        rule.removeprefix("!") for rule in dockerignore.splitlines()[1:]
    }


def test_pgvector_dockerfile_pins_base_source_and_build_dependencies() -> None:
    dockerfile = (PROJECT_ROOT / "docker/postgres/Dockerfile").read_text(
        encoding="utf-8"
    )

    assert f"postgres:17.11-alpine3.24@{POSTGRES_BASE_DIGEST}" in dockerfile
    assert f"pgvector/pgvector.git#{PGVECTOR_COMMIT}" in dockerfile
    assert "build-base=0.5-r4" in dockerfile
    assert 'make OPTFLAGS="" with_llvm=no' in dockerfile
    assert "COPY docker/postgres/init/001-enable-vector.sql" in dockerfile
    assert ":latest" not in dockerfile


def test_fresh_database_initialization_only_enables_vector_extension() -> None:
    init_sql = (PROJECT_ROOT / "docker/postgres/init/001-enable-vector.sql").read_text(
        encoding="utf-8"
    )

    statements = [
        line.strip()
        for line in init_sql.splitlines()
        if line.strip() and not line.lstrip().startswith("--")
    ]
    assert statements == [
        "\\set ON_ERROR_STOP on",
        "CREATE EXTENSION IF NOT EXISTS vector;",
    ]

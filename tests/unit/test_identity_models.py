from app.db.base import Base
from app.models.identity import Role, Tenant, User, UserRole


def test_identity_metadata_contains_m1_04_tables() -> None:
    assert {
        "roles",
        "tenants",
        "user_roles",
        "users",
    } <= set(Base.metadata.tables)


def test_identity_models_use_expected_table_names() -> None:
    assert Tenant.__tablename__ == "tenants"
    assert User.__tablename__ == "users"
    assert Role.__tablename__ == "roles"
    assert UserRole.__tablename__ == "user_roles"


def test_user_role_uses_composite_primary_key() -> None:
    primary_key_columns = {column.name for column in UserRole.__table__.primary_key}

    assert primary_key_columns == {"user_id", "role_id"}

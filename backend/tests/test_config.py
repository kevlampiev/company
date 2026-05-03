"""Settings validation: required fields, DATABASE_URL rewrite."""
import pytest
from pydantic import ValidationError


def test_jwt_secret_is_required(monkeypatch):
    """Settings refuse to construct without JWT_SECRET in env."""
    from app.config import Settings

    monkeypatch.delenv("JWT_SECRET", raising=False)
    with pytest.raises(ValidationError) as exc:
        Settings(_env_file=None)  # type: ignore[call-arg]
    fields = {e["loc"][0] for e in exc.value.errors()}
    assert "JWT_SECRET" in fields


def test_encryption_key_is_required(monkeypatch):
    from app.config import Settings

    monkeypatch.delenv("ENCRYPTION_KEY", raising=False)
    with pytest.raises(ValidationError) as exc:
        Settings(_env_file=None)  # type: ignore[call-arg]
    fields = {e["loc"][0] for e in exc.value.errors()}
    assert "ENCRYPTION_KEY" in fields


def test_database_url_rewrites_postgresql_to_asyncpg():
    from app.config import Settings

    s = Settings(  # type: ignore[call-arg]
        _env_file=None,
        JWT_SECRET="x",
        ENCRYPTION_KEY="x",
        ADMIN_PASSWORD="x",
        POSTGRES_PASSWORD="x",
        DATABASE_URL="postgresql://u:p@h:5432/d",
    )
    assert s.async_database_url == "postgresql+asyncpg://u:p@h:5432/d"

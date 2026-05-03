"""Test fixtures.

Order of operations on session start:
  1. Set non-DB secrets in os.environ (must happen before any `from app...` import).
  2. Start a postgres testcontainer; set DATABASE_URL to its asyncpg URL.
  3. atexit-register container.stop().
  4. Import app modules (engine binds DATABASE_URL on first import).
  5. Schema create_all + admin seed in a session-scoped async fixture.
  6. Per-test TRUNCATE of mutable tables (admins kept).

Switch the testcontainer image to `pgvector/pgvector:pg17` if/when models grow a vector column.
"""

import os

from cryptography.fernet import Fernet
from testcontainers.postgres import PostgresContainer

# 1. Secrets.
TEST_ADMIN_PASSWORD = "test_admin_password_42"
os.environ["JWT_SECRET"] = "test_jwt_secret_for_pytest_only"
os.environ["ENCRYPTION_KEY"] = Fernet.generate_key().decode()
os.environ["ADMIN_PASSWORD"] = TEST_ADMIN_PASSWORD
os.environ["POSTGRES_PASSWORD"] = "test"

# 2. Postgres testcontainer (sync API; blocks ~3-5s on first session).
_pg = PostgresContainer("postgres:17-alpine", driver="asyncpg")
_pg.start()
os.environ["DATABASE_URL"] = _pg.get_connection_url()

# 3. Best-effort cleanup at process exit.
import atexit  # noqa: E402

atexit.register(_pg.stop)

# 4. Now app modules can import safely.
import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import text  # noqa: E402


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _setup_schema():
    """Create tables and seed admin once per session."""
    from app import crud
    from app.db.models import Base
    from app.db.session import async_session, engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_session() as db:
        await crud.ensure_admin_exists(db)
    yield


@pytest_asyncio.fixture(autouse=True)
async def _reset_db(_setup_schema):
    """TRUNCATE mutable tables before each test. The admins row stays."""
    from app.db.session import async_session

    async with async_session() as db:
        await db.execute(text("TRUNCATE bots, claw_api_keys, messages RESTART IDENTITY CASCADE"))
        await db.commit()
    yield


@pytest.fixture
def admin_password() -> str:
    return TEST_ADMIN_PASSWORD


@pytest_asyncio.fixture
async def client():
    from app.main import app as fastapi_app

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def auth_headers(client, admin_password):
    resp = await client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": admin_password},
    )
    assert resp.status_code == 200, f"login failed: {resp.text}"
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest_asyncio.fixture
async def make_bot(client, auth_headers):
    """Factory for creating bots. Pass overrides as kwargs."""

    async def _make(**overrides):
        body = {
            "name": "test_bot",
            "area": "test",
            "system_prompt": "x",
            "provider": "openai",
            "model": "gpt-4o-mini",
            "api_key": "sk-test",
            "is_active": True,
            "use_rag": False,
        } | overrides
        resp = await client.post("/api/v1/bots", headers=auth_headers, json=body)
        assert resp.status_code == 200, f"create bot failed: {resp.text}"
        return resp.json()

    return _make

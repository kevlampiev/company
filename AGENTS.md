# AGENTS.md

## Package management
- **Use `uv`** — `backend/pyproject.toml` is the source of truth, `uv.lock` is committed. Never use pip or poetry.
- `cd backend && uv sync` — creates `backend/.venv` from lockfile
- `uv add <pkg>` / `uv add --dev <pkg>` — add runtime or dev deps (updates both files)
- After changing deps, rebuild the backend image: `docker compose up -d --build backend`

## Dev workflow

```bash
make check      # lint → typecheck → test-cov (75% threshold, pre-push contract)
make lint       # ruff check
make typecheck  # mypy
make test       # pytest (requires Docker daemon for testcontainers)
make fmt        # ruff format + ruff --fix
```

Backend is bind-mounted at `/app`, edits are live, but **uvicorn does NOT auto-reload** — restart: `docker compose restart backend`

## venv outside bind-mount
Backend image places venv at `/opt/venv`, **outside** `/app` bind-mount. Prevents bind from shadowing venv. Do not move under `/app` without revisiting `docker-compose.yml`.

## Test loop scope is load-bearing
`asyncio_default_test_loop_scope = "session"` in `pyproject.toml` keeps SQLAlchemy async connections alive across tests. Change it and you'll see "Task was destroyed but it is pending" errors.

## Python version
Requires Python 3.12 exactly (`>=3.12,<3.13` in pyproject.toml).

## Secrets setup
Generate `.env` from `backend/` (not repo root):
```bash
cd backend && uv run python -m scripts.init_env
```
`ENCRYPTION_KEY` must be 32-byte url-safe base64 — script uses `Fernet.generate_key()` correctly.

`JWT_SECRET`, `ENCRYPTION_KEY`, `ADMIN_PASSWORD`, `POSTGRES_PASSWORD` are all required — pydantic raises `ValidationError` on startup if any are missing.

## Migrations
Schema lives in `backend/alembic/versions/`. To add a migration:
```bash
cd backend
docker run --rm -d --name agen-pg -e POSTGRES_PASSWORD=t -e POSTGRES_DB=ai_bots -p 55432:5432 postgres:17-alpine
sleep 3
DATABASE_URL='postgresql+asyncpg://postgres:t@localhost:55432/ai_bots' uv run alembic upgrade head
DATABASE_URL='postgresql+asyncpg://postgres:t@localhost:55432/ai_bots' uv run alembic revision --autogenerate -m "describe change"
docker rm -f agen-pg
```
Tests use `Base.metadata.create_all` directly (bypass alembic). Keep model definitions and migrations in the same commit.

## Port mapping (host vs container)
| Service  | Container | Host  |
|----------|-----------|-------|
| postgres | 5432      | 5433  |
| redis    | 6379      | 6380  |
| backend  | 8000      | 8001  |
| frontend | 3000      | 3001  |

Production traffic goes through nginx on 443; host ports are for debugging only.

## Key conventions
- **bcrypt 72-byte limit**: `ADMIN_PASSWORD` is truncated to 72 chars before hashing
- **CORS is loose**: `allow_origins=["*"]` with `allow_credentials=True` — works only because nginx proxies frontend→backend (same origin). Do not expose the backend port directly.

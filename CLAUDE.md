# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

**AI Bot Manager** — a personal web app for managing multiple AI bots (lawyer, accountant, economist, etc.). Each bot has its own LLM provider, model, system prompt, and encrypted API key. Bots are created/edited from the UI at `/dashboard/bots` and become available immediately — no code changes or container restarts. The app's user-facing language is Russian.

## Stack

- **Backend**: Python 3.12, FastAPI, SQLAlchemy 2.0 (async), `asyncpg`, `httpx`, `passlib`/`bcrypt` (auth), `cryptography.fernet` (key encryption), `python-jose` (JWT), `loguru`. `langgraph` and `pgvector` are declared as deps but not yet wired into the chat path. **Package management is `uv`** — `backend/pyproject.toml` is the source of truth, `backend/uv.lock` is committed. There is no `requirements.txt`.
- **Frontend**: Vue 3 + Vite + TailwindCSS + vue-router + axios.
- **Infra**: PostgreSQL 17 via `alexeye/postgres-azure-flex:17` (Azure Database for PostgreSQL Flexible Server extension parity — auto-installs ~44 extensions in `POSTGRES_DB` on init, including pgvector, TimescaleDB, PostGIS, Apache AGE, pg_graphql, pg_cron, pg_stat_statements), Redis 7, Nginx (HTTPS terminator), all orchestrated via `docker-compose.yml`.

There is currently no automated test suite — pytest scaffolding is the next planned commit.

## Run / develop

Everything runs in docker-compose. There is no host-level dev workflow for the backend or frontend; iteration goes through container rebuilds.

```bash
# First-time setup
cd backend && uv run python -m scripts.init_env && cd ..   # writes ../.env with fresh random secrets
mkdir -p nginx/ssl
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout nginx/ssl/key.pem -out nginx/ssl/cert.pem -subj "/CN=localhost"

docker compose up -d --build                      # bring everything up
```

App: `https://localhost` (self-signed cert).

```bash
# Logs / iteration
docker compose logs -f backend
docker compose logs -f frontend
docker compose restart backend                    # reload backend
docker compose up -d --build backend              # rebuild only backend after dep change
docker compose exec redis redis-cli FLUSHALL      # flush cache
docker compose exec -T db pg_dump -U postgres ai_bots > backup.sql
docker compose down                               # stop
docker compose down -v                            # full reset (drops volumes)
```

The backend mounts `./backend` into the container as `/app`, so Python edits are live; uvicorn does **not** auto-reload (CMD has no `--reload`), so use `docker compose restart backend` after backend changes. The frontend container runs Vite dev (`npm run dev`); HMR works through nginx.

The backend image puts the venv at `/opt/venv`, **outside** the bind-mount, so the bind doesn't shadow it. Don't move it back under `/app` without also revisiting the bind mount.

For host-side Python work (IDE intellisense, ad-hoc scripts, future `pytest`):

```bash
cd backend
uv sync                          # creates backend/.venv from uv.lock
uv run python -c "import app.main"   # smoke check
uv add <pkg>                     # add a runtime dep (updates pyproject.toml + uv.lock)
uv add --dev <pkg>               # add a dev-only dep
uv lock --upgrade-package <pkg>  # bump a single dep
```

After changing `pyproject.toml` or `uv.lock`, rebuild the backend image (`docker compose up -d --build backend`) so the in-container `/opt/venv` is regenerated.

External ports are intentionally offset to avoid clashing with anything on the host:

| Service  | Container | Host  |
|----------|-----------|-------|
| postgres | 5432      | 5433  |
| redis    | 6379      | 6380  |
| backend  | 8000      | 8001  |
| frontend | 3000      | 3001  |
| nginx    | 80 / 443  | 80 / 443 |

In production usage everything goes through nginx on 443; the offset host ports are for local debugging only.

## Testing & quality gates

```bash
# Mac/Linux:
make install     # uv sync
make check       # lint + typecheck + test (pre-push)
make test        # pytest only
make test-cov    # with coverage

# Windows (no make):
pwsh ./tasks.ps1 install
pwsh ./tasks.ps1 check
```

`make check` is the contract for "is this branch ready to push": ruff (lint), mypy (type check), pytest (26 integration + unit tests). Each individually accessible as `make lint` / `make typecheck` / `make test`.

**Tests live under `backend/tests/`.** Layout:

- `conftest.py` — starts a `postgres:17-alpine` testcontainer at session start (synchronously, before pytest collects modules), sets env vars, then async fixtures handle schema + admin seed + per-test TRUNCATE. Switch the image to `pgvector/pgvector:pg17` if/when models grow a `vector` column.
- `test_config.py`, `test_encryption.py`, `test_security.py` — pure-function unit tests, no container needed (but the conftest still starts one — at <5s session overhead it's not worth bypassing).
- `test_auth.py`, `test_bots.py`, `test_claw.py`, `test_chat.py` — integration tests via `httpx.AsyncClient` against the FastAPI app, with `respx` mocking outbound LLM calls.

The session-scoped event loop (`asyncio_default_test_loop_scope = "session"` in `pyproject.toml`) is **load-bearing** — without it, SQLAlchemy async connections get pinned to a fixture loop that's dead by the time tests run. If you rearrange test loop scopes, expect "Task was destroyed but it is pending" errors.

**Pre-commit** is configured in `.pre-commit-config.yaml`: ruff (`--fix`) + ruff-format + trailing-whitespace + EOF-fixer + check-yaml/toml/merge-conflict. Run `pre-commit install` once after `make install`. The hook is sub-second by design — no mypy or pytest. Those run via `make check` before push.

**ruff config** is `[tool.ruff.lint]` in `backend/pyproject.toml`: `select = E, F, I, UP, B`, `ignore = B008` (FastAPI `Depends(...)` defaults are idiomatic). Deliberately not enabling `N` (pydantic uses UPPER_CASE for settings), `D` (no docstring discipline yet), or `ANN` (existing code has gaps).

**mypy config** is lenient: `ignore_missing_imports = true`, `check_untyped_defs = true`, **not** `strict = true`. The bar is "doesn't lie about types where types are present"; raising the bar to full annotation coverage is its own future commit.

## Architecture

### Request flow
Browser → nginx (443, TLS) → `/` to `frontend:3000` (Vite) or `/api/` to `backend:8000` (FastAPI). Nginx also rewrites `Set-Cookie` to add `SameSite=Strict; HTTPOnly` on `/api/` responses.

### Two authentication modes

1. **Admin (UI)** — `app/dependencies.py::get_current_user` reads `Authorization: Bearer <JWT>`, decoded with `JWT_SECRET`. Tokens are minted on `/api/v1/auth/login` against the single `admins` row, which is seeded on startup from `ADMIN_USERNAME` / `ADMIN_PASSWORD` env vars (only created if no admin exists yet — changing the env later does **not** update the password).
2. **OpenClaw / external tools** — `app/repositories/claw_key.py::verify_for_bot` reads `X-API-Key` and bcrypt-checks it against rows in `claw_api_keys` **scoped to the requested bot**. Keys are issued via `POST /api/v1/bots/{bot_id}/generate-claw-key` and shown to the user **once**; only the bcrypt hash is stored. The claw endpoint folds missing-key, unknown-bot, inactive-bot, and wrong-key into a single `403 Invalid API key or bot` response so the endpoint can't be probed for bot existence.

### Per-bot LLM dispatch
`Bot` rows store `provider`, `model`, `system_prompt`, and `api_key_encrypted` (Fernet, key = `ENCRYPTION_KEY`). `services/chat_service.py::call_llm` branches on `bot.provider`:
- `openai` → `https://api.openai.com/v1/chat/completions`
- `anthropic` → `https://api.anthropic.com/v1/messages`
- `groq`, `openrouter` → known OpenAI-compatible base URLs
- **anything else** → treated as the literal base URL of an OpenAI-compatible endpoint (`{provider}/chat/completions`). This is the extension point for adding self-hosted or other vendors without code changes.

`process_chat` appends a fixed Russian disclaimer (`*Справка носит информационный характер...*`) to every assistant reply, persists both user and assistant messages to the `messages` table keyed by `(bot_id, thread_id)`, and returns `ChatResponse`. There is no streaming; the call is a single blocking POST with a 60s timeout.

### Schema management
`backend/app/db/models.py` defines the SQLAlchemy declarative models (`Admin`, `Bot`, `ClawApiKey`, `Message`). Schema evolution goes through **Alembic** (`backend/alembic/`):

- `lifespan` in `main.py` runs `alembic upgrade head` on startup (via `asyncio.to_thread`).
- Migrations live under `backend/alembic/versions/`. The first one (`*_initial_schema.py`) captures the four tables.
- After changing a model, generate a new migration:
  ```bash
  cd backend
  # Spin up a clean postgres (the autogenerate diffs models vs DB schema):
  docker run --rm -d --name agen-pg -e POSTGRES_PASSWORD=t -e POSTGRES_DB=ai_bots -p 55432:5432 postgres:17-alpine
  sleep 3
  DATABASE_URL='postgresql+asyncpg://postgres:t@localhost:55432/ai_bots' uv run alembic upgrade head      # bring tmp DB up to current head
  DATABASE_URL='postgresql+asyncpg://postgres:t@localhost:55432/ai_bots' uv run alembic revision --autogenerate -m "describe change"
  docker rm -f agen-pg
  # Inspect the generated file under alembic/versions/, edit if needed, then commit.
  ```
- Tests bypass migrations and use `Base.metadata.create_all` for speed (in `tests/conftest.py::_setup_schema`). When a migration changes the schema, the model definitions must update in the same commit so tests stay representative.
- Existing volumes from before the alembic landing need a one-time `alembic stamp head` (or `docker compose down -v`) so alembic doesn't try to re-create existing tables on first upgrade.

The image automatically `CREATE EXTENSION`s ~44 extensions inside `POSTGRES_DB` on first init — including `vector`, `timescaledb`, `postgis`, `age`, `pg_graphql`, `plv8`, `hll`, `pgrouting`, `pgtap`. So pgvector is **already live** in `ai_bots` once the volume is fresh; the eventual RAG work just needs to add the column and embedding pipeline. To see what's installed: `docker compose exec db psql -U postgres -d ai_bots -c "SELECT extname FROM pg_extension ORDER BY extname;"`.

### Upgrading the Postgres image

Existing `pgdata` volumes initialised under a different Postgres image (e.g. the previous `pgvector/pgvector:pg16`) may not start cleanly under `alexeye/postgres-azure-flex:16` because the new image preloads additional libraries (`pg_cron`, `timescaledb`, etc.). The clean recovery for this project is:

```bash
docker compose down -v          # drops the pgdata volume — all bots/messages lost
docker compose up -d --build
```

If that volume holds anything you care about, take a `pg_dump` first while the old image is still running, then restore after the swap.

### Frontend
Three views (`LoginView`, `DashboardBots`, `ChatView`) routed by `vue-router`. Auth state is `localStorage['access_token']`; the router guard redirects on `requiresAuth` / `guest` meta. There is currently no Pinia install despite a `stores/auth.js` file (`useAuthStore` is imported but the import works because the store does not actually need Pinia for the read path used in the guard — be careful when expanding it).

## Conventions worth knowing

- **Secrets** — `JWT_SECRET`, `ENCRYPTION_KEY`, `ADMIN_PASSWORD`, and `POSTGRES_PASSWORD` are required (no defaults). The app refuses to start if any are missing; pydantic raises `ValidationError` listing the missing fields. Generate a fresh `.env` with strong random values via `uv run python -m scripts.init_env` from `backend/`. The Fernet key must be a 32-byte url-safe base64 string (`Fernet.generate_key()`); a free-form string will raise on first encrypt.
- **bcrypt 72-byte limit** — `ensure_admin_exists` truncates `ADMIN_PASSWORD` to 72 chars. If a user sets a longer password, only the prefix is hashed.
- **No deprecation shims** — per the user's standing instruction, when removing functionality just remove it; do not keep deprecated paths for backwards compatibility. There are no external API consumers to preserve.
- **Postgres functions** — when authoring SQL stored functions, do not use transaction control statements (`COMMIT`/`ROLLBACK`); they are not allowed inside Postgres functions.
- **CORS** is `allow_origins=["*"]` with `allow_credentials=True`, which browsers reject as a combination — works today only because the frontend hits the backend through nginx (same origin) rather than cross-origin. Tighten this before exposing the backend port directly.

## Where things live

```
backend/
  pyproject.toml       runtime + dev deps (uv-managed)
  uv.lock              committed lockfile
  .python-version      pinned to 3.12 (matches Dockerfile)
  Dockerfile           multi-stage uv build, venv at /opt/venv
  app/
    main.py            FastAPI app + route handlers + lifespan
    config.py          pydantic-settings (reads .env)
    dependencies.py    FastAPI dependencies (currently just get_current_user)
    repositories/      DB query functions, one module per resource
      admin.py         get_by_username, ensure_exists (first-startup seed)
      bot.py           create / list_all / get_by_id / get_by_name / update / delete_by_id
      claw_key.py      create, verify_for_bot
    db/models.py       SQLAlchemy 2.0 declarative models
    db/session.py      async engine + sessionmaker + get_db dependency
    core/security.py   bcrypt + JWT helpers
    core/encryption.py Fernet wrappers + mask_api_key
    schemas/           pydantic request/response models (BotResponse.from_bot for ORM→DTO)
    services/chat_service.py   LLM dispatch + message persistence
frontend/src/
  views/{LoginView,DashboardBots,ChatView}.vue
  router/index.js      route guard reads localStorage
  stores/auth.js       auth store
  api/auth.js          axios calls
nginx/nginx.conf       HTTPS termination, /api proxy, cookie hardening
docker-compose.yml     db, redis, backend, frontend, nginx
```

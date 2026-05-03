# `refactor/project-overhaul` — Branch Report

> **Russian translation:** [`overhaul-report.ru.md`](./overhaul-report.ru.md)

This document explains every change made on the `refactor/project-overhaul` branch. It is written for two readers: an experienced engineer who needs to evaluate decisions and tradeoffs quickly, and a junior engineer who needs to understand what the new tools and patterns mean and how to use them. When a concept is introduced, a short definition follows; experts can skim those.

## 1. Summary

The branch contains **11 commits** that together take the codebase from "vibe-coded prototype that boots" to "team-ready with an automated verification loop." Application behaviour is intentionally preserved end-to-end (the public HTTP API is identical except for one security fix). The bulk of the work is **infrastructure**: tooling, tests, schema management, and one structural refactor.

The branch is green by all gates: 26/26 tests pass in ~7 seconds, 81.45 % line coverage (threshold set at 75), `ruff` and `mypy` clean, pre-commit hooks pass, GitHub Actions workflow defined.

Two genuine **bugs** were fixed along the way — both surfaced because we started writing tests:

1. JWTs were minted with an `exp` claim already in the past on any non-UTC machine (`datetime.utcnow()` × `.timestamp()` interaction).
2. The OpenClaw key endpoint accepted any valid key for any bot — the per-bot scope was modelled but never enforced.

Everything else is code health: clearer structure, automatic guardrails, and explicit failure modes for missing configuration.

## 2. Why this branch exists

Before the overhaul the project had several characteristics typical of an early LLM-assisted prototype:

- **Misleading scaffolding at the repo root.** A stale `AGENTS.md` claimed the project was Node.js / TypeScript with `jest` tests in `src/`. None of that existed in the repo. Because [opencode](https://opencode.ai/) reads `AGENTS.md` by default, every opencode session was starting from a confidently wrong premise.
- **No automated tests.** Every change had to be validated by hand through the UI. AI-generated suggestions could not be verified mechanically before being trusted.
- **No linter / type checker enforcement.** Two contributors using two different AI tools would generate plausibly-but-differently-shaped code.
- **One god-module (`crud.py`)** mixing data access, FastAPI dependencies, and response shaping.
- **Fallback secrets in `config.py`** (`change_me_jwt_secret`, etc.) meant a missing `.env` would silently boot with known-weak crypto.
- **Plaintext passwords printed to container stdout** on every login attempt (a `print()` left in for local debugging).

The user's stated context — *personal-scope, single-user runtime, but multi-developer team using Claude Code and opencode side by side* — sharpened the priorities. Most of the auth findings were one severity tier lower than they would be in a multi-user product. But every developer-experience and AI-tool-friendliness concern stayed at full priority because they directly affect the team workflow.

## 3. Changes by area

### 3.1 Python tooling: `pip` → `uv`

**What changed.** Removed `backend/requirements.txt`. The single source of truth is now `backend/pyproject.toml`, with a committed `backend/uv.lock` (the resolver's output). Dev-only dependencies live in a `[dependency-groups] dev` table.

`backend/Dockerfile` rewritten as a multi-stage `uv` build:

- Stage 1 installs the project's runtime venv at `/opt/venv` using `uv sync --frozen --no-dev`, with mount-cached `uv` cache and bind-mounted `pyproject.toml` / `uv.lock` so the install layer caches by lockfile content.
- Stage 2 starts from a clean `python:3.12-slim`, copies `/opt/venv` from stage 1, copies the source, and runs `uvicorn` with the venv on `PATH`. Final image is **~394 MB** with no `gcc`, no `uv` binary.

The venv lives at `/opt/venv` deliberately — `docker-compose.yml` bind-mounts `./backend:/app`, which would shadow `/app/.venv` at runtime if the venv lived there.

**Why.** `pip + requirements.txt` has no built-in lockfile concept; reproducibility depends on every contributor running `pip freeze` in the same order. `uv` produces a deterministic lockfile, resolves orders of magnitude faster, and gives a single command (`uv sync`) for "make my environment match the lockfile."

**For juniors.**
- `pyproject.toml` is the file Python tools look at to know what your project depends on.
- A *lockfile* records exact versions of every dependency *and* every transitive dependency, so a later install gets the same versions you developed against.
- `uv sync` reads the lockfile and brings your `.venv/` to that exact state. If the lockfile changes, `uv sync` updates the venv.
- `uv add <pkg>` and `uv add --dev <pkg>` add a new dependency, update `pyproject.toml` and `uv.lock` together.
- `uv run <cmd>` runs a command inside the project's venv without you having to manually activate it.

### 3.2 PostgreSQL image: `alexeye/postgres-azure-flex:17`

**What changed.** `docker-compose.yml`'s `db` service moved from `pgvector/pgvector:pg16` to `alexeye/postgres-azure-flex:17`. The new image is built to mirror the extension catalogue of [Azure Database for PostgreSQL Flexible Server](https://learn.microsoft.com/azure/postgresql/flexible-server/concepts-extensions) — it auto-installs **44 extensions** in `POSTGRES_DB` on first init, including `vector` (pgvector), `timescaledb`, `postgis`, `apache_age`, `pg_graphql`, `pg_cron`, `pg_stat_statements`, and `plv8`.

**Why.** Forward-compatibility: when this app eventually adds RAG features, the `vector` column type is already available without a separate setup step. PG17 was chosen over PG16 for the same reason — it's the version Azure currently lists as GA, and there is no behavioural risk for our four small tables.

**Tests deliberately use a different image** (`postgres:17-alpine`, ~80 MB) — it boots in ~1 s vs ~5 s for the alexeye image, and our models don't touch the bundled extensions yet. The tradeoff is documented in `tests/conftest.py`. When we eventually add a `vector` column, the test image should become `pgvector/pgvector:pg17`.

**Migration note.** Existing `pgdata` volumes initialised under the previous image require `docker compose down -v` (a destructive volume reset) before bringing up the new image. This is documented in both `README.md` and `CLAUDE.md`.

### 3.3 Schema management: Alembic

**What changed.** Added `alembic` as a runtime dependency. Scaffolded with `alembic init -t async alembic`, then wired:

- `backend/alembic/env.py` imports `app.config.settings` and `app.db.models.Base`, sets `sqlalchemy.url = settings.async_database_url` and `target_metadata = Base.metadata`.
- The first migration (`backend/alembic/versions/7727f42f4d9a_initial_schema.py`) was generated against a fresh `postgres:17-alpine` via `alembic revision --autogenerate -m "initial schema"`. It captures the current four tables (`admins`, `bots`, `claw_api_keys`, `messages`) verbatim.
- The FastAPI `lifespan` (see §3.4) now runs `alembic upgrade head` via `asyncio.to_thread`. The previous `Base.metadata.create_all` call is gone from the runtime path.

**Why.** `Base.metadata.create_all` only ever *creates missing* tables — it does not alter existing ones. Once the schema needed to evolve in any way other than appending tables, you would have had to either drop the volume (lose data) or hand-write the SQL. Alembic generates and applies incremental, version-controlled migrations.

**For juniors.**
- A *migration* is a small Python script that knows how to bring the database forward one schema step (and, ideally, back). Alembic numbers and chains them.
- `alembic revision --autogenerate -m "..."` looks at your models, compares them to the current DB schema, and writes a migration script that produces the diff. Always read what it generated — autogenerate is a starting point, not a final answer.
- `alembic upgrade head` applies all unapplied migrations.
- *Tests use `Base.metadata.create_all`*, not migrations. This is a speed tradeoff. The risk it introduces is "models change but migrations don't, tests still pass, prod fails" — the recommended counterweight is `alembic check` (returns non-zero if models diverge from migrations), which can be added to the CI workflow when the team feels the need.

**Existing-volume note.** A volume that was previously created via `Base.metadata.create_all` does not have an `alembic_version` row and Alembic will refuse to apply the initial migration. Recovery is either `alembic stamp head` (mark as up-to-date) or `docker compose down -v` (re-create from migrations). The container smoke test for this branch used the latter.

### 3.4 Code structure: `crud.py` → `repositories/` + `dependencies.py`

**What changed.** `backend/app/crud.py` was a god-module. It is gone. Replaced by:

| New module | Contents |
|---|---|
| `app/repositories/admin.py` | `get_by_username`, `ensure_exists` (first-startup admin seed) |
| `app/repositories/bot.py` | `create`, `list_all`, `get_by_id`, `get_by_name`, `update`, `delete_by_id` |
| `app/repositories/claw_key.py` | `create`, `verify_for_bot` |
| `app/dependencies.py` | `get_current_user` (FastAPI bearer-token dependency) |

Response shaping (decrypting + masking the API key, building the response dict) was previously a CRUD function (`get_bot_response`). It now lives on the schema:

- `app/schemas/bot.py` gained `BotResponse.from_bot(bot)` — a classmethod that takes an ORM `Bot` and returns the corresponding pydantic response.
- `app/core/encryption.py` gained a small `mask_api_key()` utility, used by `BotResponse.from_bot` and previously inlined in CRUD.

The `lifespan` context manager (§3.5) now calls `admin_repo.ensure_exists` instead of the old `crud.ensure_admin_exists`.

**Why.** Each module now has a single concern:

- *Repositories* know about the database. They take a session, return ORM objects.
- *Dependencies* know about HTTP. They wire FastAPI features (`Request`, `Depends`).
- *Schemas* know about the wire format. They convert ORM ↔ DTO.
- *Routes* (`main.py`) wire the four together.

Before the split, `crud.py` knew about all four. New code defaulted to "append to crud.py" because that's where the existing patterns lived. Splitting establishes the right gravity.

**Tests were not touched** by this refactor — they live at the HTTP boundary (`AsyncClient` against the FastAPI app), so internal restructuring doesn't move them. This is by design: an HTTP test suite buys you freedom to refactor internals fearlessly.

### 3.5 FastAPI lifespan

**What changed.** `@app.on_event("startup")` (deprecated in FastAPI 0.93) was replaced with the `lifespan` async context manager pattern:

```python
@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    await asyncio.to_thread(_run_alembic_upgrade)   # §3.3
    async with async_session() as db:
        await admin_repo.ensure_exists(db)          # §3.4
    logger.info("Application started")
    yield

app = FastAPI(title="AI Bot Manager", version="1.0.0", lifespan=lifespan)
```

**Why.** `on_event` is deprecated and produced two `DeprecationWarning` lines in every test run. `lifespan` is the supported replacement and reads more naturally — startup before `yield`, shutdown after.

### 3.6 Test infrastructure

**What changed.** From zero tests to **26 tests** in seven files under `backend/tests/`:

| File | Tests | What it covers |
|---|---|---|
| `test_config.py` | 3 | Required `Field(...)` settings raise `ValidationError`; `postgresql://` → `postgresql+asyncpg://` rewrite |
| `test_encryption.py` | 3 | Fernet round-trip; empty input handling |
| `test_security.py` | 4 | bcrypt hash/verify; JWT `type` claim; expired-token rejection |
| `test_auth.py` | 4 | Login happy/sad paths; bearer-token gating |
| `test_bots.py` | 5 | Full CRUD; API-key re-encryption on update; cascade-delete of claw keys |
| `test_claw.py` | 4 | Token issuance; bad key 403; cross-bot rejection (the security fix from §3.7); same-bot success via `respx` mock |
| `test_chat.py` | 3 | OpenAI provider dispatch; Anthropic provider dispatch; user/assistant message persistence |

**Stack.**

- `pytest` with `pytest-asyncio` (auto mode) — async tests work without `@pytest.mark.asyncio` decorators.
- `testcontainers-python` starts a `postgres:17-alpine` container at session start. It blocks for ~3-5 s the first time and runs once per session.
- `httpx.AsyncClient` with `ASGITransport(app=fastapi_app)` — calls FastAPI in-process, no real network, no real port binding.
- `respx` patches `httpx`'s outbound transport to return canned responses for `https://api.openai.com/...` and `https://api.anthropic.com/...` calls.

**The conftest design is load-bearing.** Three things must be true:

1. The Postgres container starts **before** any `from app...` import (the SQLAlchemy engine binds `DATABASE_URL` at import time).
2. The four required env vars (`JWT_SECRET`, `ENCRYPTION_KEY`, `ADMIN_PASSWORD`, `POSTGRES_PASSWORD`) are set before the same import.
3. The async fixtures, the test functions, and the SQLAlchemy connection pool all share **one** event loop.

Item (3) is the subtle one. Without `asyncio_default_test_loop_scope = "session"` and `asyncio_default_fixture_loop_scope = "session"` in `pyproject.toml`, tests run in function-scoped loops while session-scoped fixtures hold connections on a different loop. The symptom is `RuntimeError: Task <Task pending ...> attached to a different loop` and it took half an hour to diagnose. There is a comment in `conftest.py` explaining this.

**Per-test isolation.** A function-scoped `autouse` fixture `_reset_db` runs `TRUNCATE bots, claw_api_keys, messages RESTART IDENTITY CASCADE` before every test. The `admins` row is preserved across the session (it's seeded once). This is fast (~5 ms per test) and gives "fresh state" without rebuilding the schema. If the suite ever grows past a few hundred tests, the gold-standard upgrade is per-test SAVEPOINT + rollback; we are explicitly choosing not to do that yet.

**For juniors.**
- A *fixture* is a setup helper. pytest passes it to a test that lists it as a parameter. Look at `auth_headers` in `conftest.py` — any test taking `auth_headers` automatically gets a logged-in bearer-token header.
- *Session-scoped* means the fixture runs once for the whole test run; *function-scoped* (default) runs per test.
- *autouse* fixtures run automatically without being listed as parameters. We use it for `_setup_schema` and `_reset_db`.
- `monkeypatch` is pytest's safe way to mutate global state in a test (env vars, attributes) and have it automatically reverted afterwards.
- `respx` lets you intercept HTTP calls to specific URLs and return whatever you want, so tests don't actually hit external services.

### 3.7 Security and correctness fixes

This is the highest-impact section. Five issues:

**3.7.1 Required secrets.** `JWT_SECRET`, `ENCRYPTION_KEY`, `ADMIN_PASSWORD`, and `POSTGRES_PASSWORD` are now `Field(...)` (required) in `app/config.py`. Previously each had a friendly fallback (`"change_me_jwt_secret"` etc.); a deployment with a missing `.env` would silently boot with these known weak values. Now `pydantic.ValidationError` lists exactly which fields are missing and the app refuses to start.

A helper script `backend/scripts/init_env.py` (run as `uv run python -m scripts.init_env`) generates a fresh `.env` with random secrets — Fernet-generated `ENCRYPTION_KEY`, `secrets.token_urlsafe()` for the rest.

**3.7.2 The `datetime.utcnow()` × timezone bug.** `app/core/security.py::create_access_token` and `create_refresh_token` were doing:

```python
expire = datetime.utcnow() + timedelta(...)
to_encode["exp"] = int(expire.timestamp())
```

`datetime.utcnow()` returns a *naive* datetime, and `.timestamp()` interprets naive datetimes as local time. On a machine in UTC+2 (this project's primary dev box), the resulting `exp` was 2 h *earlier* than intended — every JWT was already expired at issue time. The fix: `datetime.now(UTC)` (timezone-aware). Same change applied to `bot.updated_at` in `repositories/bot.py`. The Python 3.12 deprecation warning for `utcnow()` is also silenced.

This bug had been present from the start of the project. Tests caught it on the first integration run.

**3.7.3 `decode_token` raised bare `Exception`.** Replaced with `ValueError`. Both call sites (`get_current_user` in `dependencies.py`, the `/auth/refresh` route in `main.py`) catch `Exception`, so behaviour is unchanged. But tests can now assert on a real exception type, and `ruff B017` is happy.

**3.7.4 Claw-key bot scoping.** `verify_claw_key` (the old FastAPI dependency in `crud.py`) iterated **every** row in `claw_api_keys` and bcrypt-checked each against the incoming `X-API-Key`. The first match returned. The match's `bot_id` was never compared against the request's target bot. Effect: a key issued for bot A also unlocked bot B.

The fix lives in `repositories/claw_key.py::verify_for_bot(db, api_key, bot_id)`. The SELECT is restricted to keys for the specific bot, so iteration is bounded by keys-per-bot (typically 0-2 in personal use). The route handler in `main.py` now resolves the bot first, then verifies the key against that bot's keys. Missing key, unknown bot, inactive bot, and wrong key all collapse into a single `403 Invalid API key or bot` so the endpoint cannot be probed for bot existence by status code.

The test that previously locked in the bug (`test_any_valid_claw_key_authorises_any_bot`) was inverted to `test_claw_key_does_not_authorise_other_bots`, asserting the new 403 behaviour.

**3.7.5 DEBUG `print()` of plaintext passwords.** The login route had three `print(f"DEBUG ...")` lines that included `credentials.password` directly. On every login attempt, the raw password ended up in container stdout (visible via `docker compose logs`, screen-share, log paste). Removed.

**3.7.6 `passlib` → direct `bcrypt`.** `passlib` has been effectively unmaintained since its 1.7.4 release in October 2020. It expected an `__about__` attribute on the `bcrypt` module that was removed in `bcrypt 4.1`, which was the reason the project had been holding `bcrypt==4.0.1` and emitting `(trapped) error reading bcrypt version` on every backend startup. With `passlib` removed, `bcrypt` was bumped to 5.0 and `app/core/security.py` rewritten to use `bcrypt.hashpw` / `bcrypt.checkpw` directly. The 72-byte truncation that bcrypt's algorithm requires is now explicit and commented. Existing admin and claw-key bcrypt hashes (`$2b$...$`) verify unchanged because passlib and direct bcrypt produce the same wire format.

`loguru` was bumped from 0.3.2 (2018) to 0.7.3 in the same commit because the 0.3.2 release imports `distutils`, removed in Python 3.12; `setuptools` was previously masking this and was no longer needed once `passlib` was gone.

### 3.8 Quality gates

**`ruff` (lint + format).** Configured in `[tool.ruff.lint]`: `select = ["E", "F", "I", "UP", "B"]`, `ignore = ["B008"]`. Existing code was reformatted in a single pass; the diff is captured in commit `3fd4408`. The rule selection deliberately omits `N` (pydantic settings naming), `D` (docstrings), and `ANN` (annotations) — those would force a much larger churn pass. They can be added later when the team has the habit of running `ruff` regularly.

**`mypy`** with lenient defaults: `check_untyped_defs = true`, `ignore_missing_imports = true`, `warn_unused_ignores = true`. **Not** `strict = true`. The bar is "doesn't lie about types where types are present"; raising the bar to full annotation coverage would be its own future commit.

**`pre-commit`** hooks (`.pre-commit-config.yaml`): `ruff --fix`, `ruff-format`, `trailing-whitespace`, `end-of-file-fixer`, `check-merge-conflict`, `check-yaml`, `check-toml`. **Not** mypy and **not** pytest — those run via `make check` before push. Pre-commit must finish in <1 s or developers will use `--no-verify`.

**Coverage threshold.** `pytest --cov=app` shows 81.45 % at HEAD. `[tool.coverage.report]` has `fail_under = 75` — slightly below baseline so normal variation doesn't break, but a dropped module would. `make test-cov` is what enforces it.

**Task runners.** `Makefile` (Linux/macOS) and `tasks.ps1` (Windows; `make` is not in Git for Windows by default). Both expose:

| Target | Purpose |
|---|---|
| `install` | `uv sync` — bring local venv up to lockfile |
| `init-env` | generate fresh `.env` |
| `test` | pytest, no coverage (fast feedback) |
| `test-cov` | pytest + coverage threshold enforcement |
| `lint` | `ruff check .` |
| `fmt` | `ruff format .` then `ruff check --fix .` |
| `typecheck` | `mypy app/` |
| `check` | `lint + typecheck + test-cov` — the **before-push** gate |
| `up` / `down` / `logs` / `ps` | docker compose convenience |

There is deliberately **no `make clean`** — `docker compose down -v` is destructive enough that making it a single keystroke would be asymmetric risk.

**GitHub Actions.** `.github/workflows/check.yml` runs the equivalent of `make check` on `ubuntu-latest` for every push to `master` and every PR. uv is installed via `astral-sh/setup-uv@v3` with cache keyed by `backend/uv.lock`. The Ubuntu runner has Docker pre-installed, so the testcontainer fixture works with no extra configuration.

### 3.9 Cleanup

Files deleted:

| File | Why it was a problem |
|---|---|
| `AGENTS.md` (root) | Described a non-existent Node/TS project. opencode reads this file by default; every opencode session was being misinformed. |
| `package.json`, `tsconfig.json`, `.eslintrc.json` | Same root cause. Stale Node/TS scaffolding for a Python+Vue project. |
| `test_db.py` | One-off connectivity script with hardcoded credentials for a `lawer` database that no longer existed. Not a test. |
| `backend/app/crud.py` | Replaced by `repositories/` + `dependencies.py` (§3.4). |
| Two `bot_cache = {}` declarations (`main.py`, `chat_service.py`) | Module-level dicts that were popped on update/delete but never read. Dead code that AI tools would learn from and propagate. |
| Duplicate `get_db` (in `crud.py`) | The version in `db/session.py` is now the single source. |
| `version: '3.8'` in `docker-compose.yml` | Obsolete; compose has been warning about it for two years. |

## 4. Daily workflow after this branch

For a contributor just joining:

```bash
# One-time setup
git clone <repo>
cd company
pwsh ./tasks.ps1 install            # or: make install
pwsh ./tasks.ps1 init-env           # only if .env doesn't exist yet
cd backend && uv run pre-commit install   # (optional) install the git hook
cd ..
mkdir -p nginx/ssl
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout nginx/ssl/key.pem -out nginx/ssl/cert.pem -subj "/CN=localhost"
pwsh ./tasks.ps1 up                 # docker compose up -d --build
```

For a normal change cycle:

```bash
# 1. Edit code.
# 2. Before push:
pwsh ./tasks.ps1 check              # ruff + mypy + pytest + coverage
# 3. Commit. The pre-commit hook re-runs ruff on staged files for free.
# 4. Push. GitHub Actions re-runs `check` in CI.
```

For a schema change:

```bash
# Edit app/db/models.py.
# Generate a migration (requires a clean Postgres):
docker run --rm -d --name agen-pg -e POSTGRES_PASSWORD=t -e POSTGRES_DB=ai_bots -p 55432:5432 postgres:17-alpine
sleep 3
cd backend
DATABASE_URL='postgresql+asyncpg://postgres:t@localhost:55432/ai_bots' uv run alembic upgrade head
DATABASE_URL='postgresql+asyncpg://postgres:t@localhost:55432/ai_bots' uv run alembic revision --autogenerate -m "describe what changed"
docker rm -f agen-pg
# Read the generated file under alembic/versions/, edit if needed, commit it
# alongside the model change.
```

## 5. What is still open

These items were considered and **deliberately deferred**. None blocks the branch from landing.

- **Frontend tests.** Vue surface is small; Vitest + `@vue/test-utils` is the standard answer when it grows.
- **ESLint / Prettier for Vue.** Not configured. The frontend has no enforced style.
- **Stricter mypy.** `strict = true` would surface real annotation gaps but require a churn pass that's its own commit.
- **`alembic check` in CI.** Catches model-vs-migration drift. One-line CI step; postponed to keep the first CI run minimal.
- **Strict CSRF defence.** Currently moot because tokens live in `localStorage`, not cookies. If the team migrates auth to cookie-based sessions, this needs revisiting.
- **Token revocation.** A leaked JWT is valid for its full lifetime. For personal scope, accepted.
- **Rate limiting on `/auth/login`.** Brute force is unbounded. For a localhost-only deployment, accepted.
- **Refresh-token vs access-token type enforcement in `get_current_user`.** Currently a 7-day refresh token also works as an access token. Cosmetically wrong, security-wise irrelevant at personal scope.
- **uvicorn `--reload` for local dev.** Would shorten the iteration loop. Currently `docker compose restart backend` is the workflow.
- **Replacement of the Russian disclaimer hardcoded in `chat_service.py`** with a per-bot configurable string. Not a bug; a flexibility opportunity.

## 6. Glossary

- **`uv`** — Modern Python package manager and project tool from Astral. Replaces `pip` + `venv` + `pip-tools` + `pipx`. Reads `pyproject.toml`, writes `uv.lock`.
- **`pyproject.toml`** — The standard Python project metadata file (PEP 621). Lists name, version, dependencies, dev-tool configuration.
- **lockfile** — A file recording the exact resolved versions of every direct and transitive dependency. Guarantees reproducibility across machines and time.
- **Fernet** — A symmetric encryption scheme from `cryptography`. We use it to encrypt LLM API keys at rest.
- **bcrypt** — A password hashing function with a built-in cost factor and salt. Used here for the admin password and for OpenClaw API keys.
- **JWT** — JSON Web Token. A signed, base64-encoded JSON payload used as a bearer credential. `app/core/security.py` mints and decodes ours.
- **ASGI** — Asynchronous Server Gateway Interface. The async sibling of WSGI. FastAPI is an ASGI app.
- **`AsyncClient` (httpx)** — An HTTP client that speaks ASGI directly when you give it an ASGITransport, so tests can call FastAPI in-process with no real port.
- **testcontainers** — A library that starts real services (Postgres, Redis, Kafka, …) inside Docker for the duration of a test session, then tears them down. Gives test fidelity without the operational cost.
- **Alembic** — The standard SQLAlchemy migration tool. Manages incremental, ordered, reversible schema changes.
- **fixture (pytest)** — A reusable setup helper. Tests receive fixtures by listing them as parameters.
- **autouse fixture** — A fixture that runs automatically without being requested by name.
- **`monkeypatch`** — pytest's mechanism for safely mutating global state during a test (env vars, attributes) and reverting it afterwards.
- **respx** — Library that intercepts httpx outbound calls and returns canned responses, used to mock external APIs in tests.
- **ruff** — Fast Python linter and formatter; aims to replace `flake8` + `black` + `isort`.
- **mypy** — Static type checker for Python.
- **pre-commit** — Framework for managing git hook scripts. The `.pre-commit-config.yaml` defines what runs before every commit.
- **lifespan (FastAPI)** — An async context manager wrapping app startup/shutdown. Replaces the deprecated `@app.on_event` pair.
- **repository pattern** — Architectural pattern: each "repository" module encapsulates queries for one entity. Shields the rest of the app from raw SQL/ORM details.

## 7. Commit reference (chronological)

| Commit | Subject |
|---|---|
| `814b55d` | docs: add `CLAUDE.md` (the original audit; on `master`, predates this branch) |
| `ccd64e7` | chore: migrate to uv, switch to `alexeye/postgres-azure-flex` |
| `9923517` | chore: phase 1 cleanup — delete misleading scaffolding, kill dead code, bump to PG17 |
| `76ea57e` | chore: phase 2 — fail-fast on missing secrets, init-env helper, silence bcrypt warning |
| `3fd4408` | chore: phase 3a — ruff/mypy/pre-commit configured, dev deps added |
| `35d4207` | chore: phase 3b — pytest scaffolding, 26 tests, Makefile + tasks.ps1 |
| `9715c7e` | chore: migrate startup hook to FastAPI lifespan |
| `0d7af31` | chore: replace passlib with direct bcrypt; bump loguru off ancient pin |
| `a2cf320` | fix(claw): scope key verification to the requested bot, fold to single 403 |
| `d0e89f4` | refactor: split `crud.py` into `app/repositories/` + `app/dependencies.py` |
| `d0ec073` | feat(db): add Alembic migrations; lifespan now runs `upgrade head` |
| `f2f81fb` | chore: enforce coverage threshold; add GitHub Actions check workflow |

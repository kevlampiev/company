# `refactor/project-overhaul` — Отчёт по ветке

> **English version:** [`overhaul-report.md`](./overhaul-report.md)

Документ описывает все изменения, сделанные в ветке `refactor/project-overhaul`. Он рассчитан на двух читателей: опытного инженера, которому нужно быстро оценить решения и компромиссы, и junior-разработчика, которому нужно понять, что означают новые инструменты и паттерны и как ими пользоваться. Когда вводится новое понятие, рядом даётся короткое определение — эксперты могут пробегать их глазами.

## 1. Краткая сводка

Ветка содержит **11 коммитов**, которые в сумме переводят кодовую базу из состояния «прототип, который запускается» в «готовый к командной работе с автоматизированной верификацией». Поведение приложения сохранено end-to-end (публичный HTTP API идентичен, кроме одного исправления безопасности). Основная масса изменений — **инфраструктура**: инструменты, тесты, управление схемой БД и один структурный рефакторинг.

Ветка зелёная по всем проверкам: 26/26 тестов проходят за ~7 секунд, покрытие кода 81.45 % (порог 75), `ruff` и `mypy` чистые, pre-commit хуки проходят, GitHub Actions воркфлоу описан.

По ходу работы исправлены два настоящих **бага** — оба всплыли потому, что мы начали писать тесты:

1. JWT-токены выпускались с уже истёкшим claim `exp` на любой машине вне UTC (взаимодействие `datetime.utcnow()` × `.timestamp()`).
2. Endpoint OpenClaw принимал любой валидный ключ для любого бота — привязка ключа к боту была заявлена в модели данных, но никогда не проверялась.

Всё остальное — здоровье кодовой базы: более чёткая структура, автоматические ограждения и явные failure modes для пропущенной конфигурации.

## 2. Зачем нужна эта ветка

До рефакторинга проект демонстрировал признаки, типичные для раннего LLM-прототипа:

- **Вводящие в заблуждение файлы в корне.** Устаревший `AGENTS.md` утверждал, что проект — Node.js / TypeScript с jest-тестами в `src/`. Ничего из этого в репозитории не было. Поскольку [opencode](https://opencode.ai/) по умолчанию читает `AGENTS.md`, каждая сессия opencode стартовала с уверенно неправильной картиной.
- **Полное отсутствие автоматических тестов.** Каждое изменение приходилось проверять вручную через UI. Сгенерированные ИИ-инструментами правки нельзя было верифицировать механически перед тем, как им довериться.
- **Никакой принудительный линтер / type-checker.** Двое контрибьюторов с двумя разными ИИ-инструментами писали правдоподобный, но по-разному оформленный код.
- **Один god-модуль (`crud.py`)**, смешивающий доступ к данным, FastAPI-зависимости и формирование ответов.
- **Резервные значения секретов в `config.py`** (`change_me_jwt_secret` и т.п.) — деплой без `.env` молча запускался с известной слабой криптографией.
- **Plaintext-пароли в stdout контейнера** при каждом логине (отладочный `print()`, оставшийся от локальной отладки).

Контекст пользователя — *персональное приложение, single-user runtime, но команда из нескольких разработчиков, использующих параллельно Claude Code и opencode* — заострил приоритеты. Большинство auth-замечаний были на уровень ниже по тяжести, чем были бы в multi-user продукте. Но все вопросы developer experience и совместимости с ИИ-инструментами остались на полном приоритете, потому что напрямую влияют на командный workflow.

## 3. Изменения по областям

### 3.1 Python-инструменты: `pip` → `uv`

**Что изменилось.** Удалён `backend/requirements.txt`. Единственный источник истины теперь — `backend/pyproject.toml` с закоммиченным `backend/uv.lock` (результат работы резолвера). Dev-зависимости вынесены в таблицу `[dependency-groups] dev`.

`backend/Dockerfile` переписан как multi-stage `uv`-сборка:

- Stage 1 устанавливает runtime-venv проекта в `/opt/venv` через `uv sync --frozen --no-dev`, с mount-кэшем `uv` и bind-маунтами `pyproject.toml` / `uv.lock` — слой install кэшируется по содержимому lockfile.
- Stage 2 стартует с чистого `python:3.12-slim`, копирует `/opt/venv` из первого этапа, копирует исходники и запускает `uvicorn` с venv в `PATH`. Финальный образ — **~394 МБ**, без `gcc`, без бинарника `uv`.

Venv находится в `/opt/venv` намеренно — `docker-compose.yml` делает bind-маунт `./backend:/app`, который перекрыл бы `/app/.venv` в runtime, если бы venv лежал внутри.

**Зачем.** У `pip + requirements.txt` нет встроенной концепции lockfile; воспроизводимость зависит от того, что каждый контрибьютор запускает `pip freeze` в одинаковом порядке. `uv` производит детерминированный lockfile, резолвит зависимости на порядки быстрее и даёт одну команду (`uv sync`) для «приведи моё окружение в соответствие с lockfile».

**Для junior'ов.**
- `pyproject.toml` — файл, в который смотрят Python-инструменты, чтобы узнать зависимости проекта.
- *Lockfile* фиксирует точные версии всех зависимостей *и* всех их зависимостей, так что последующая установка получает те же версии, на которых вы разрабатывали.
- `uv sync` читает lockfile и приводит ваш `.venv/` ровно в это состояние. Если lockfile меняется — `uv sync` обновит venv.
- `uv add <pkg>` и `uv add --dev <pkg>` добавляют новую зависимость, обновляя `pyproject.toml` и `uv.lock` одновременно.
- `uv run <cmd>` запускает команду внутри venv проекта без необходимости вручную его активировать.

### 3.2 Образ PostgreSQL: `alexeye/postgres-azure-flex:17`

**Что изменилось.** Сервис `db` в `docker-compose.yml` переключён с `pgvector/pgvector:pg16` на `alexeye/postgres-azure-flex:17`. Новый образ построен так, чтобы повторять каталог расширений [Azure Database for PostgreSQL Flexible Server](https://learn.microsoft.com/azure/postgresql/flexible-server/concepts-extensions) — он автоматически устанавливает **44 расширения** в `POSTGRES_DB` при первой инициализации, включая `vector` (pgvector), `timescaledb`, `postgis`, `apache_age`, `pg_graphql`, `pg_cron`, `pg_stat_statements`, `plv8`.

**Зачем.** Forward-совместимость: когда приложение в перспективе обзаведётся RAG-функциональностью, тип колонки `vector` уже доступен без отдельного шага установки. Версия 17 выбрана вместо 16 по той же причине — это та версия, которая сейчас GA в Azure, и для наших четырёх небольших таблиц нет рисков по поведению.

**Тесты намеренно используют другой образ** (`postgres:17-alpine`, ~80 МБ) — он стартует за ~1 с против ~5 с у образа alexeye, а наши модели пока не используют bundled-расширения. Компромисс задокументирован в `tests/conftest.py`. Когда мы добавим колонку `vector`, тестовый образ должен стать `pgvector/pgvector:pg17`.

**Замечание про миграцию.** Существующие тома `pgdata`, инициализированные под предыдущим образом, требуют `docker compose down -v` (деструктивный сброс тома) перед поднятием нового образа. Это задокументировано и в `README.md`, и в `CLAUDE.md`.

### 3.3 Управление схемой БД: Alembic

**Что изменилось.** `alembic` добавлен как runtime-зависимость. Скаффолдинг сделан через `alembic init -t async alembic`, затем настроены интеграции:

- `backend/alembic/env.py` импортирует `app.config.settings` и `app.db.models.Base`, устанавливает `sqlalchemy.url = settings.async_database_url` и `target_metadata = Base.metadata`.
- Первая миграция (`backend/alembic/versions/7727f42f4d9a_initial_schema.py`) сгенерирована против чистого `postgres:17-alpine` через `alembic revision --autogenerate -m "initial schema"`. Она дословно фиксирует текущие четыре таблицы (`admins`, `bots`, `claw_api_keys`, `messages`).
- `lifespan` в FastAPI (см. §3.5) теперь запускает `alembic upgrade head` через `asyncio.to_thread`. Прежний вызов `Base.metadata.create_all` убран из runtime-пути.

**Зачем.** `Base.metadata.create_all` только *создаёт недостающие* таблицы — он не модифицирует существующие. Как только схеме нужно эволюционировать чем-то кроме добавления таблиц, пришлось бы либо удалять том (терять данные), либо писать SQL вручную. Alembic генерирует и применяет инкрементальные, версионированные миграции.

**Для junior'ов.**
- *Миграция* — небольшой Python-скрипт, который умеет двигать БД на один шаг по схеме вперёд (и, в идеале, назад). Alembic нумерует и связывает их.
- `alembic revision --autogenerate -m "..."` смотрит на ваши модели, сравнивает с текущей схемой БД и пишет скрипт миграции, реализующий разницу. Всегда читайте, что он сгенерировал — autogenerate это отправная точка, а не финальный ответ.
- `alembic upgrade head` применяет все непримененные миграции.
- *Тесты используют `Base.metadata.create_all`*, а не миграции. Это компромисс по скорости. Риск, который он вносит, — «модели изменились, миграции нет, тесты прошли, прод сломался» — рекомендованный противовес `alembic check` (возвращает не-ноль, если модели расходятся с миграциями), который можно добавить в CI, когда команда почувствует необходимость.

**Замечание про существующий том.** Том, ранее созданный через `Base.metadata.create_all`, не содержит строки `alembic_version`, и Alembic откажется применить начальную миграцию. Восстановление — либо `alembic stamp head` (пометить как up-to-date), либо `docker compose down -v` (пересоздать через миграции). Контейнерный smoke-тест этой ветки использовал второй вариант.

### 3.4 Структура кода: `crud.py` → `repositories/` + `dependencies.py`

**Что изменилось.** `backend/app/crud.py` был god-модулем. Его нет. Заменён на:

| Новый модуль | Содержимое |
|---|---|
| `app/repositories/admin.py` | `get_by_username`, `ensure_exists` (seed админа при первом старте) |
| `app/repositories/bot.py` | `create`, `list_all`, `get_by_id`, `get_by_name`, `update`, `delete_by_id` |
| `app/repositories/claw_key.py` | `create`, `verify_for_bot` |
| `app/dependencies.py` | `get_current_user` (FastAPI-зависимость для bearer-токена) |

Формирование ответа (расшифровка + маскировка API-ключа, сборка response-словаря) раньше было CRUD-функцией (`get_bot_response`). Теперь оно живёт на схеме:

- `app/schemas/bot.py` получил `BotResponse.from_bot(bot)` — classmethod, принимающий ORM-объект `Bot` и возвращающий соответствующую pydantic-модель ответа.
- `app/core/encryption.py` получил небольшую утилиту `mask_api_key()`, используемую `BotResponse.from_bot` и ранее зашитую внутри CRUD.

`lifespan` (см. §3.5) теперь вызывает `admin_repo.ensure_exists` вместо прежнего `crud.ensure_admin_exists`.

**Зачем.** У каждого модуля теперь одна забота:

- *Repositories* знают про БД. Принимают сессию, возвращают ORM-объекты.
- *Dependencies* знают про HTTP. Связывают возможности FastAPI (`Request`, `Depends`).
- *Schemas* знают про wire-формат. Конвертируют ORM ↔ DTO.
- *Routes* (`main.py`) связывают четверых.

До разделения `crud.py` знал про все четыре аспекта. Новый код по умолчанию шёл «приклеить к crud.py» потому что там жили существующие паттерны. Разделение задаёт правильную гравитацию.

**Тесты этим рефакторингом не тронуты** — они живут на HTTP-границе (`AsyncClient` против FastAPI-приложения), поэтому внутренняя реструктуризация их не двигает. Это сделано специально: HTTP-тесты дают свободу безбоязненно рефакторить внутренности.

### 3.5 FastAPI lifespan

**Что изменилось.** `@app.on_event("startup")` (deprecated в FastAPI 0.93) заменён на async context manager `lifespan`:

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

**Зачем.** `on_event` deprecated и выдавал по два `DeprecationWarning` на каждый прогон тестов. `lifespan` — поддерживаемая замена, и читается естественнее: startup до `yield`, shutdown после.

### 3.6 Тестовая инфраструктура

**Что изменилось.** От нуля тестов до **26 тестов** в семи файлах под `backend/tests/`:

| Файл | Тестов | Что покрывает |
|---|---|---|
| `test_config.py` | 3 | Обязательные `Field(...)` настройки бросают `ValidationError`; рерайт `postgresql://` → `postgresql+asyncpg://` |
| `test_encryption.py` | 3 | Round-trip Fernet; обработка пустого ввода |
| `test_security.py` | 4 | bcrypt hash/verify; claim `type` в JWT; отклонение истёкшего токена |
| `test_auth.py` | 4 | Логин happy/sad path; защита через bearer-токен |
| `test_bots.py` | 5 | Полный CRUD; перешифрование API-ключа при update; каскадное удаление claw-ключей |
| `test_claw.py` | 4 | Выпуск токена; неверный ключ — 403; отклонение cross-bot (исправление безопасности из §3.7); успех same-bot через `respx`-мок |
| `test_chat.py` | 3 | Диспатч провайдера OpenAI; диспатч провайдера Anthropic; персистенция user/assistant сообщений |

**Стек.**

- `pytest` с `pytest-asyncio` (auto-режим) — async-тесты работают без декораторов `@pytest.mark.asyncio`.
- `testcontainers-python` запускает контейнер `postgres:17-alpine` при старте сессии. Блокирует на ~3-5 с при первом запуске, работает один раз за сессию.
- `httpx.AsyncClient` с `ASGITransport(app=fastapi_app)` — вызывает FastAPI in-process, без реальной сети, без реального port binding.
- `respx` патчит outbound transport `httpx`, чтобы возвращать заранее заготовленные ответы для вызовов `https://api.openai.com/...` и `https://api.anthropic.com/...`.

**Дизайн conftest несущий.** Должны быть истинными три вещи:

1. Контейнер Postgres стартует **до** любого импорта `from app...` (SQLAlchemy engine связывает `DATABASE_URL` во время импорта).
2. Четыре обязательных env-переменных (`JWT_SECRET`, `ENCRYPTION_KEY`, `ADMIN_PASSWORD`, `POSTGRES_PASSWORD`) выставлены до того же импорта.
3. Async-фикстуры, тестовые функции и пул соединений SQLAlchemy используют **один** event loop.

Пункт (3) — самый коварный. Без `asyncio_default_test_loop_scope = "session"` и `asyncio_default_fixture_loop_scope = "session"` в `pyproject.toml` тесты выполняются в function-scope loop'ах, а session-scoped фикстуры держат соединения на другом loop'е. Симптом — `RuntimeError: Task <Task pending ...> attached to a different loop`, и его диагностика заняла полчаса. В `conftest.py` есть комментарий с объяснением.

**Изоляция между тестами.** Function-scope `autouse` фикстура `_reset_db` перед каждым тестом запускает `TRUNCATE bots, claw_api_keys, messages RESTART IDENTITY CASCADE`. Строка `admins` сохраняется в течение сессии (она засевается один раз). Это быстро (~5 мс на тест) и даёт «свежее состояние» без пересоздания схемы. Если набор тестов когда-нибудь вырастет за несколько сотен, gold-standard апгрейд — per-test SAVEPOINT + rollback; мы намеренно сейчас этого не делаем.

**Для junior'ов.**
- *Фикстура* — это setup-помощник. pytest передаёт её в тест, который указал её в параметрах. Посмотрите на `auth_headers` в `conftest.py` — любой тест, принимающий `auth_headers`, автоматически получает headers с залогиненным bearer-токеном.
- *Session-scoped* означает, что фикстура запускается один раз на весь прогон; *function-scoped* (по умолчанию) — на каждый тест.
- *autouse* фикстуры запускаются автоматически без указания в параметрах. Используется для `_setup_schema` и `_reset_db`.
- `monkeypatch` — безопасный способ pytest мутировать глобальное состояние в тесте (env-переменные, атрибуты) с автоматическим откатом после.
- `respx` позволяет перехватывать HTTP-вызовы по конкретным URL и возвращать что угодно, чтобы тесты не дёргали реальные внешние сервисы.

### 3.7 Исправления безопасности и корректности

Самая значимая по эффекту секция. Шесть пунктов:

**3.7.1 Обязательные секреты.** `JWT_SECRET`, `ENCRYPTION_KEY`, `ADMIN_PASSWORD` и `POSTGRES_PASSWORD` теперь `Field(...)` (обязательные) в `app/config.py`. Раньше у каждого было дружелюбное fallback-значение (`"change_me_jwt_secret"` и т.п.); деплой без `.env` молча запускался с этими известными слабыми значениями. Теперь `pydantic.ValidationError` перечисляет, какие именно поля отсутствуют, и приложение отказывается стартовать.

Скрипт-помощник `backend/scripts/init_env.py` (запуск `uv run python -m scripts.init_env`) генерирует свежий `.env` со случайными секретами — Fernet-сгенерированный `ENCRYPTION_KEY`, `secrets.token_urlsafe()` для остальных.

**3.7.2 Баг `datetime.utcnow()` × таймзона.** `app/core/security.py::create_access_token` и `create_refresh_token` делали:

```python
expire = datetime.utcnow() + timedelta(...)
to_encode["exp"] = int(expire.timestamp())
```

`datetime.utcnow()` возвращает *naive* datetime, а `.timestamp()` интерпретирует naive datetime как локальное время. На машине в UTC+2 (главный девбокс этого проекта) получавшийся `exp` оказывался на 2 часа *раньше* предполагаемого — каждый JWT был уже истёкшим на момент выпуска. Исправление: `datetime.now(UTC)` (timezone-aware). То же изменение в `bot.updated_at` в `repositories/bot.py`. Заодно убран Python 3.12 deprecation warning про `utcnow()`.

Этот баг существовал с самого начала проекта. Тесты поймали его на первом интеграционном прогоне.

**3.7.3 `decode_token` бросал голый `Exception`.** Заменено на `ValueError`. Оба места вызова (`get_current_user` в `dependencies.py`, `/auth/refresh` в `main.py`) ловят `Exception`, поэтому поведение не изменилось. Но тесты теперь могут проверять реальный тип исключения, и `ruff B017` доволен.

**3.7.4 Привязка claw-ключа к боту.** `verify_claw_key` (старая FastAPI-зависимость в `crud.py`) перебирала **каждую** строку в `claw_api_keys` и bcrypt-проверяла её против входящего `X-API-Key`. Первое совпадение возвращалось. `bot_id` совпавшей строки никогда не сравнивался с целевым ботом из запроса. Эффект: ключ, выпущенный для бота A, разблокировал и бот B.

Исправление живёт в `repositories/claw_key.py::verify_for_bot(db, api_key, bot_id)`. SELECT ограничен ключами конкретного бота, поэтому итерация ограничена ключами-на-бот (обычно 0-2 в персональном использовании). Обработчик маршрута в `main.py` теперь сначала резолвит бота, затем проверяет ключ против ключей этого бота. Отсутствующий ключ, неизвестный бот, неактивный бот и неверный ключ — всё схлопывается в единый `403 Invalid API key or bot`, чтобы endpoint нельзя было пробить на наличие ботов по статус-коду.

Тест, ранее фиксировавший баг (`test_any_valid_claw_key_authorises_any_bot`), инвертирован в `test_claw_key_does_not_authorise_other_bots` и проверяет новое поведение 403.

**3.7.5 DEBUG `print()` plaintext-паролей.** Маршрут логина имел три строки `print(f"DEBUG ...")`, включавшие `credentials.password` напрямую. На каждый логин «сырой» пароль попадал в stdout контейнера (виден через `docker compose logs`, при screen-share, при вставке логов). Удалено.

**3.7.6 `passlib` → прямой `bcrypt`.** `passlib` фактически не поддерживается с релиза 1.7.4 в октябре 2020. Он ожидал атрибут `__about__` в модуле `bcrypt`, который убрали в `bcrypt 4.1`, поэтому проект держал `bcrypt==4.0.1` и выводил `(trapped) error reading bcrypt version` при каждом старте. После удаления `passlib` версия `bcrypt` поднята до 5.0, а `app/core/security.py` переписан с прямым использованием `bcrypt.hashpw` / `bcrypt.checkpw`. Усечение до 72 байт, требуемое алгоритмом bcrypt, теперь явное и закомментировано. Существующие bcrypt-хэши admin'а и claw-ключей (`$2b$...$`) проверяются без изменений, потому что passlib и прямой bcrypt дают одинаковый wire-формат.

`loguru` поднят с 0.3.2 (2018) до 0.7.3 в том же коммите, потому что 0.3.2 импортирует `distutils`, удалённый в Python 3.12; `setuptools` ранее это маскировал и стал не нужен после удаления `passlib`.

### 3.8 Quality gates

**`ruff` (lint + format).** Сконфигурирован в `[tool.ruff.lint]`: `select = ["E", "F", "I", "UP", "B"]`, `ignore = ["B008"]`. Существующий код переформатирован за один проход; diff зафиксирован в коммите `3fd4408`. Выбор правил намеренно опускает `N` (нейминг pydantic settings), `D` (docstrings) и `ANN` (аннотации) — они вызвали бы существенно больший churn-проход. Их можно добавить позже, когда у команды появится привычка регулярно запускать `ruff`.

**`mypy`** с мягкими настройками: `check_untyped_defs = true`, `ignore_missing_imports = true`, `warn_unused_ignores = true`. **Не** `strict = true`. Планка — «не врёт про типы там, где типы есть»; поднятие планки до полного покрытия аннотациями — отдельный будущий коммит.

**`pre-commit`** хуки (`.pre-commit-config.yaml`): `ruff --fix`, `ruff-format`, `trailing-whitespace`, `end-of-file-fixer`, `check-merge-conflict`, `check-yaml`, `check-toml`. **Не** mypy и **не** pytest — они выполняются через `make check` перед push. Pre-commit должен укладываться в <1 с, иначе разработчики начнут жать `--no-verify`.

**Порог покрытия.** `pytest --cov=app` показывает 81.45 % на HEAD. В `[tool.coverage.report]` стоит `fail_under = 75` — чуть ниже базового уровня, чтобы обычные колебания не ломали сборку, но падение целого модуля сломало бы. `make test-cov` — то, что реально форсит порог.

**Task runners.** `Makefile` (Linux/macOS) и `tasks.ps1` (Windows; `make` в Git for Windows по умолчанию отсутствует). Оба предоставляют:

| Цель | Назначение |
|---|---|
| `install` | `uv sync` — привести локальный venv к lockfile |
| `init-env` | сгенерировать свежий `.env` |
| `test` | pytest без покрытия (быстрый отклик) |
| `test-cov` | pytest + проверка порога покрытия |
| `lint` | `ruff check .` |
| `fmt` | `ruff format .`, затем `ruff check --fix .` |
| `typecheck` | `mypy app/` |
| `check` | `lint + typecheck + test-cov` — гейт **перед push** |
| `up` / `down` / `logs` / `ps` | удобства docker compose |

Намеренно **нет цели `make clean`** — `docker compose down -v` достаточно деструктивен, чтобы делать его одним нажатием было асимметричным риском.

**GitHub Actions.** `.github/workflows/check.yml` запускает эквивалент `make check` на `ubuntu-latest` для каждого push в `master` и каждого PR. uv ставится через `astral-sh/setup-uv@v3` с кэшем по `backend/uv.lock`. На Ubuntu-раннере уже стоит Docker, так что фикстура testcontainers работает без дополнительной конфигурации.

### 3.9 Уборка

Удалённые файлы:

| Файл | Почему был проблемой |
|---|---|
| `AGENTS.md` (в корне) | Описывал несуществующий Node/TS-проект. opencode читает этот файл по умолчанию; каждая сессия opencode получала ложную информацию. |
| `package.json`, `tsconfig.json`, `.eslintrc.json` | Та же причина. Устаревший Node/TS-скаффолдинг для Python+Vue-проекта. |
| `test_db.py` | Однократный скрипт проверки соединения с захардкоженными credentials к базе `lawer`, которой больше нет. Не тест. |
| `backend/app/crud.py` | Заменён на `repositories/` + `dependencies.py` (§3.4). |
| Два объявления `bot_cache = {}` (`main.py`, `chat_service.py`) | Module-level dict'ы, в которые `pop` делался при update/delete, но никогда не читались. Мёртвый код, на котором ИИ-инструменты учились бы и его распространяли. |
| Дубликат `get_db` (в `crud.py`) | Версия в `db/session.py` теперь единый источник. |
| `version: '3.8'` в `docker-compose.yml` | Устарело; compose предупреждает об этом уже два года. |

## 4. Ежедневный workflow после ветки

Для нового контрибьютора:

```bash
# Однократная установка
git clone <repo>
cd company
pwsh ./tasks.ps1 install            # или: make install
pwsh ./tasks.ps1 init-env           # только если .env ещё не существует
cd backend && uv run pre-commit install   # (опционально) поставить git-хук
cd ..
mkdir -p nginx/ssl
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout nginx/ssl/key.pem -out nginx/ssl/cert.pem -subj "/CN=localhost"
pwsh ./tasks.ps1 up                 # docker compose up -d --build
```

Обычный цикл изменений:

```bash
# 1. Редактируем код.
# 2. Перед push:
pwsh ./tasks.ps1 check              # ruff + mypy + pytest + coverage
# 3. Коммит. Pre-commit хук бесплатно перезапускает ruff на staged-файлах.
# 4. Push. GitHub Actions перезапускает `check` в CI.
```

Для изменения схемы:

```bash
# Редактируем app/db/models.py.
# Генерируем миграцию (нужен чистый Postgres):
docker run --rm -d --name agen-pg -e POSTGRES_PASSWORD=t -e POSTGRES_DB=ai_bots -p 55432:5432 postgres:17-alpine
sleep 3
cd backend
DATABASE_URL='postgresql+asyncpg://postgres:t@localhost:55432/ai_bots' uv run alembic upgrade head
DATABASE_URL='postgresql+asyncpg://postgres:t@localhost:55432/ai_bots' uv run alembic revision --autogenerate -m "опишите что изменилось"
docker rm -f agen-pg
# Прочитайте сгенерированный файл под alembic/versions/, при необходимости отредактируйте,
# закоммитьте вместе с изменением модели.
```

## 5. Что осталось открытым

Эти пункты были рассмотрены и **намеренно отложены**. Ничто из них не блокирует land-инг ветки.

- **Тесты фронтенда.** Поверхность Vue небольшая; стандартный ответ при росте — Vitest + `@vue/test-utils`.
- **ESLint / Prettier для Vue.** Не настроено. У фронтенда нет принудительного стиля.
- **Более строгий mypy.** `strict = true` показал бы реальные пробелы в аннотациях, но потребовал бы churn-прохода в виде отдельного коммита.
- **`alembic check` в CI.** Ловит расхождение модели и миграций. Один шаг CI; отложено, чтобы первый прогон CI был минимальным.
- **Строгая защита от CSRF.** Сейчас неактуальна, потому что токены лежат в `localStorage`, не в куках. Если команда мигрирует auth на cookie-сессии, нужно пересмотреть.
- **Отзыв токенов.** Утёкший JWT валиден весь свой срок жизни. Для персонального масштаба принято.
- **Rate limiting на `/auth/login`.** Брутфорс ничем не ограничен. Для localhost-деплоя принято.
- **Принудительная проверка типа токена access vs refresh в `get_current_user`.** Сейчас 7-дневный refresh-токен также работает как access-токен. Косметически неправильно, по безопасности на персональном масштабе несущественно.
- **`--reload` для uvicorn в dev.** Сократил бы цикл итерации. Сейчас `docker compose restart backend` — рабочий процесс.
- **Замена жестко прошитого русскоязычного дисклеймера в `chat_service.py`** на per-bot настройку. Не баг; возможность гибкости.

## 6. Глоссарий

- **`uv`** — современный Python-менеджер пакетов и проектный инструмент от Astral. Заменяет `pip` + `venv` + `pip-tools` + `pipx`. Читает `pyproject.toml`, пишет `uv.lock`.
- **`pyproject.toml`** — стандартный файл метаданных Python-проекта (PEP 621). Перечисляет имя, версию, зависимости, конфигурацию dev-инструментов.
- **lockfile** — файл, фиксирующий точные разрешённые версии всех прямых и транзитивных зависимостей. Гарантирует воспроизводимость между машинами и во времени.
- **Fernet** — симметричная схема шифрования из `cryptography`. Используется для шифрования API-ключей LLM в покое.
- **bcrypt** — функция хеширования паролей со встроенным cost factor и salt'ом. Используется здесь для пароля админа и API-ключей OpenClaw.
- **JWT** — JSON Web Token. Подписанный, base64-encoded JSON-payload, используемый как bearer-credential. `app/core/security.py` чеканит и декодирует наши.
- **ASGI** — Asynchronous Server Gateway Interface. Async-аналог WSGI. FastAPI — это ASGI-приложение.
- **`AsyncClient` (httpx)** — HTTP-клиент, говорящий напрямую по ASGI, если ему дать ASGITransport, поэтому тесты могут вызывать FastAPI in-process без реального порта.
- **testcontainers** — библиотека, запускающая реальные сервисы (Postgres, Redis, Kafka, …) внутри Docker на время тестовой сессии и убирающая их после. Даёт fidelity тестов без операционных издержек.
- **Alembic** — стандартный инструмент миграций SQLAlchemy. Управляет инкрементальными, упорядоченными, обратимыми изменениями схемы.
- **fixture (pytest)** — переиспользуемый setup-помощник. Тесты получают фикстуры, перечисляя их в параметрах.
- **autouse фикстура** — фикстура, запускающаяся автоматически без явного запроса по имени.
- **`monkeypatch`** — механизм pytest для безопасного мутирования глобального состояния в тесте (env-переменных, атрибутов) с откатом после.
- **respx** — библиотека, перехватывающая outbound-вызовы httpx и возвращающая заранее заготовленные ответы; используется для мокирования внешних API в тестах.
- **ruff** — быстрый Python linter и formatter; цель — заменить `flake8` + `black` + `isort`.
- **mypy** — статический type checker для Python.
- **pre-commit** — фреймворк для управления git hook-скриптами. Файл `.pre-commit-config.yaml` определяет, что запускается перед каждым коммитом.
- **lifespan (FastAPI)** — async context manager, оборачивающий startup/shutdown приложения. Заменяет deprecated пару `@app.on_event`.
- **repository pattern** — архитектурный паттерн: каждый «репозиторий»-модуль инкапсулирует запросы к одной сущности. Защищает остальное приложение от деталей сырого SQL/ORM.

## 7. Список коммитов (хронологически)

| Коммит | Описание |
|---|---|
| `814b55d` | docs: добавление `CLAUDE.md` (исходный аудит; на `master`, до этой ветки) |
| `ccd64e7` | chore: миграция на uv, переключение на `alexeye/postgres-azure-flex` |
| `9923517` | chore: phase 1 cleanup — удаление вводящего в заблуждение скаффолдинга, мёртвого кода, апгрейд до PG17 |
| `76ea57e` | chore: phase 2 — fail-fast при отсутствующих секретах, init-env helper, заглушение bcrypt warning |
| `3fd4408` | chore: phase 3a — настройка ruff/mypy/pre-commit, добавление dev-зависимостей |
| `35d4207` | chore: phase 3b — pytest scaffolding, 26 тестов, Makefile + tasks.ps1 |
| `9715c7e` | chore: миграция startup hook на FastAPI lifespan |
| `0d7af31` | chore: замена passlib на прямой bcrypt; апгрейд loguru с древнего пина |
| `a2cf320` | fix(claw): привязка верификации ключа к запрашиваемому боту, схлопывание в единый 403 |
| `d0e89f4` | refactor: разделение `crud.py` на `app/repositories/` + `app/dependencies.py` |
| `d0ec073` | feat(db): добавление миграций Alembic; lifespan теперь запускает `upgrade head` |
| `f2f81fb` | chore: введение порога покрытия; добавление GitHub Actions check workflow |

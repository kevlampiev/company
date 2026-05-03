# AI Bot Manager

Личное веб-приложение для управления набором AI-ботов (юрист, бухгалтер, экономист и т.д.).

## Быстрый старт

```bash
# 1. Копируем пример конфигурации
cp .env.example .env

# 2. Редактируем .env (задаём логин/пароль админа, ключи шифрования)
# Для генерации ENCRYPTION_KEY: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# 3. Создаём SSL-сертификаты для nginx (самоподписанные для локалки)
mkdir -p nginx/ssl
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout nginx/ssl/key.pem -out nginx/ssl/cert.pem \
  -subj "/CN=localhost"

# 4. Запускаем всё одной командой
docker compose up -d --build
```

Приложение будет доступно по адресу: https://localhost

## Управление ботами через Web UI

1. Зайдите на https://localhost и войдите с логином/паролем из `.env`
2. Перейдите на `/dashboard/bots`
3. Нажмите **+ Добавить бота**
4. Заполните поля:
   - **Имя**: например, "Юрист"
   - **Область**: например, "Право"
   - **Системный промпт**: инструкция для бота
   - **Провайдер**: OpenAI, Anthropic, Groq, OpenRouter
   - **Модель**: например, `gpt-4o-mini`
   - **API-ключ**: ваш ключ от провайдера
   - **Использовать RAG**: включить/выключить
5. Нажмите **Сохранить** — бот появится в списке и сразу доступен в чате

**Никаких перезапусков контейнеров или правок кода не требуется!**

## Подключение OpenClaw

### Вариант 1: HTTP-инструмент

Сгенерируйте ключ в UI: нажмите **Ключ** напротив бота на `/dashboard/bots`.

Пример вызова из OpenClaw:
```python
import requests

response = requests.post(
    "https://your-domain.com/api/v1/claw",
    headers={"X-API-Key": "ваш_сгенерированный_ключ"},
    json={
        "bot_id": "Юрист",
        "query": "Как оформить ИП?",
        "thread_id": "optional_thread_id"
    }
)
print(response.json())
```

### Вариант 2: Docker-интеграция

Добавьте в `docker-compose.yml` сервис OpenClaw:
```yaml
openclaw:
  image: openclaw:latest
  environment:
    - API_URL=https://nginx/api/v1/claw
    - API_KEY=ваш_сгенерированный_ключ
  depends_on:
    - nginx
```

## Бэкап БД и конфигов

```bash
# Бэкап базы данных
docker compose exec -T db pg_dump -U postgres ai_bots > backup_$(date +%Y%m%d).sql

# Бэкап конфигов и volume'ов
cp .env .env.backup
docker volume ls | grep company  # посмотреть volume'ы
```

## HTTPS-сертификат

### Самоподписанный (для локалки)
```bash
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout nginx/ssl/key.pem -out nginx/ssl/cert.pem \
  -subj "/CN=localhost"
```

### Let's Encrypt (для продакшена)
```bash
# Установите certbot и выполните:
sudo certbot certonly --standalone -d your-domain.com
sudo cp /etc/letsencrypt/live/your-domain.com/fullchain.pem nginx/ssl/cert.pem
sudo cp /etc/letsencrypt/live/your-domain.com/privkey.pem nginx/ssl/key.pem
```

## Полезные команды

```bash
# Просмотр логов
docker compose logs -f backend
docker compose logs -f frontend
docker compose logs -f nginx

# Перезагрузка бэкенда без остановки контейнеров
docker compose restart backend

# Очистка кэша Redis
docker compose exec redis redis-cli FLUSHALL

# Пересборка только бэкенда
docker compose up -d --build backend

# Остановка всех контейнеров
docker compose down

# Удаление volume'ов (полный сброс)
docker compose down -v
```

## Архитектура

- **Frontend**: Vue 3 + Vite + TailwindCSS (порт 3000, проксируется через nginx)
- **Backend**: FastAPI + SQLAlchemy 2.0 + LangGraph (порт 8000), пакеты управляются `uv` (`backend/pyproject.toml` + `backend/uv.lock`)
- **Database**: `alexeye/postgres-azure-flex:16` — PostgreSQL 16 с расширениями Azure Database for PostgreSQL Flexible Server (pgvector, TimescaleDB, pg_cron, Apache AGE и др.)
- **Cache**: Redis
- **Proxy**: Nginx (HTTPS на 443, HTTP редирект на 80 → 443)

## Локальная разработка Python (host-side)

Для работы IDE, запуска тестов и ad-hoc скриптов вне контейнеров:

```bash
cd backend
uv sync                               # создаёт backend/.venv по uv.lock
uv run python -c "import app.main"    # smoke-проверка
uv run pytest                         # когда тесты появятся
```

Контейнерный venv (`/opt/venv`) и host-side `.venv` независимы. После изменения `pyproject.toml` или `uv.lock` пересоберите backend-образ: `docker compose up -d --build backend`.

## Обновление образа Postgres

Если у вас уже есть `pgdata`-том, инициализированный другим образом (например, прежним `pgvector/pgvector:pg16`), он может не подняться под `alexeye/postgres-azure-flex:16` — у нового образа дополнительные `shared_preload_libraries` (pg_cron, timescaledb и др.). Чистый путь:

```bash
docker compose down -v          # удаляет pgdata-том — все боты/сообщения теряются
docker compose up -d --build
```

Если в томе есть данные, которые жалко терять, сначала сделайте `pg_dump` на старом образе и восстановите после переключения.

## Безопасность

- Пароль админа хешируется через bcrypt
- API-ключи LLM шифруются через `cryptography.fernet`
- JWT токены хранятся в httpOnly cookies
- OpenClaw API защищён отдельными токенами
- Прямые порты закрыты, доступ только через HTTPS

## Требования

- Docker + Docker Compose
- 4-8 ГБ ОЗУ (с учётом overhead'а Docker)
- OpenSSL (для генерации сертификатов)

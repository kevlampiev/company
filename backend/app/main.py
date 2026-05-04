import asyncio
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from alembic.config import Config as AlembicConfig
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from alembic import command
from app.core.encryption import encrypt_api_key
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.db.session import async_session, get_db
from app.dependencies import get_current_user
from app.repositories import admin as admin_repo
from app.repositories import bot as bot_repo
from app.repositories import claw_key as claw_repo
from app.schemas import auth, bot
from app.schemas import chat as chat_schema

ALEMBIC_INI = Path(__file__).resolve().parent.parent / "alembic.ini"


def _run_alembic_upgrade() -> None:
    """Synchronous alembic upgrade. Called from lifespan via asyncio.to_thread."""
    config = AlembicConfig(str(ALEMBIC_INI))
    command.upgrade(config, "head")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    await asyncio.to_thread(_run_alembic_upgrade)
    async with async_session() as db:
        await admin_repo.ensure_exists(db)
    logger.info("Application started")
    yield


app = FastAPI(title="AI Bot Manager", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/api/v1/auth/login", response_model=auth.TokenResponse)
async def login(credentials: auth.LoginRequest, db: AsyncSession = Depends(get_db)):
    admin = await admin_repo.get_by_username(db, credentials.username)
    if not admin or not verify_password(credentials.password, admin.password_hash):
        logger.info(f"login failed: username={credentials.username}")
        raise HTTPException(status_code=401, detail="Invalid credentials")

    access_token = create_access_token({"sub": admin.username})
    refresh_token = create_refresh_token({"sub": admin.username})
    return {"access_token": access_token, "refresh_token": refresh_token}


@app.post("/api/v1/auth/refresh", response_model=auth.TokenResponse)
async def refresh_token(refresh_token: str):
    try:
        payload = decode_token(refresh_token)
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")
        access_token = create_access_token({"sub": payload["sub"]})
        return {"access_token": access_token, "refresh_token": refresh_token}
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid refresh token") from None


@app.get("/api/v1/bots", response_model=list[bot.BotResponse])
async def list_bots(
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    bots = await bot_repo.list_all(db)
    return [bot.BotResponse.from_bot(b) for b in bots]


@app.post("/api/v1/bots", response_model=bot.BotResponse)
async def create_bot(
    data: bot.BotCreate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    encrypted_key = encrypt_api_key(data.api_key) if data.api_key else None
    new_bot = await bot_repo.create(db, data, encrypted_key)
    return bot.BotResponse.from_bot(new_bot)


@app.put("/api/v1/bots/{bot_id}", response_model=bot.BotResponse)
async def update_bot(
    bot_id: int,
    data: bot.BotUpdate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    bot_obj = await bot_repo.get_by_id(db, bot_id)
    if not bot_obj:
        raise HTTPException(status_code=404, detail="Bot not found")

    update_data = data.model_dump(exclude_unset=True)
    if "api_key" in update_data:
        if update_data["api_key"]:
            update_data["api_key_encrypted"] = encrypt_api_key(update_data.pop("api_key"))
        else:
            update_data.pop("api_key")

    await bot_repo.update(db, bot_obj, update_data)
    return bot.BotResponse.from_bot(bot_obj)


@app.delete("/api/v1/bots/{bot_id}")
async def delete_bot(
    bot_id: int,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    await bot_repo.delete_by_id(db, bot_id)
    return {"message": "Bot deleted"}


@app.post("/api/v1/bots/{bot_id}/generate-claw-key", response_model=bot.ClawKeyResponse)
async def generate_claw_key(
    bot_id: int,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    token = secrets.token_urlsafe(32)
    await claw_repo.create(db, bot_id, hash_password(token))
    return {"token": token, "message": "Save this key! It will not be shown again."}


@app.post("/api/v1/bots/{bot_id}/test", response_model=dict)
async def test_bot_connection(
    bot_id: int,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    from app.services.chat_service import test_llm_connection

    bot_obj = await bot_repo.get_by_id(db, bot_id)
    if not bot_obj:
        raise HTTPException(status_code=404, detail="Bot not found")

    success, message = await test_llm_connection(bot_obj)
    return {"success": success, "message": message}


@app.post("/api/v1/chat", response_model=chat_schema.ChatResponse)
async def chat(
    message: chat_schema.ChatMessage,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    from app.services.chat_service import process_chat

    return await process_chat(db, message)


@app.post("/api/v1/claw")
async def claw_endpoint(
    request: chat_schema.ClawRequest,
    raw: Request,
    db: AsyncSession = Depends(get_db),
):
    from app.services.chat_service import process_chat

    api_key = raw.headers.get("X-API-Key")
    bot_obj = await bot_repo.get_by_name(db, request.bot_id)
    # Single 403 for missing key, unknown bot, inactive bot, or wrong key —
    # collapses these into one failure mode so the claw endpoint can't be
    # probed for bot existence.
    if (
        not api_key
        or not bot_obj
        or not bot_obj.is_active
        or not await claw_repo.verify_for_bot(db, api_key, bot_obj.id)
    ):
        raise HTTPException(status_code=403, detail="Invalid API key or bot")

    message = chat_schema.ChatMessage(
        bot_id=bot_obj.id, query=request.query, thread_id=request.thread_id
    )
    return await process_chat(db, message)

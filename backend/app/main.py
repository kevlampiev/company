from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.core.encryption import encrypt_api_key
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_password,
)
from app.db.models import Base
from app.db.session import async_session, engine, get_db
from app.schemas import auth, bot
from app.schemas import chat as chat_schema

app = FastAPI(title="AI Bot Manager", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as db:
        await crud.ensure_admin_exists(db)
    logger.info("Application started")


@app.post("/api/v1/auth/login", response_model=auth.TokenResponse)
async def login(credentials: auth.LoginRequest, db: AsyncSession = Depends(get_db)):
    admin = await crud.get_admin_by_username(db, credentials.username)
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


@app.get("/api/v1/bots")
async def list_bots(
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(crud.get_current_user),
):
    bots = await crud.get_all_bots(db)
    return [await crud.get_bot_response(db, b) for b in bots]


@app.post("/api/v1/bots")
async def create_bot(
    data: bot.BotCreate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(crud.get_current_user),
):
    encrypted_key = encrypt_api_key(data.api_key) if data.api_key else None
    new_bot = await crud.create_bot(db, data, encrypted_key)
    return await crud.get_bot_response(db, new_bot)


@app.put("/api/v1/bots/{bot_id}")
async def update_bot(
    bot_id: int,
    data: bot.BotUpdate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(crud.get_current_user),
):
    bot_obj = await crud.get_bot_by_id(db, bot_id)
    if not bot_obj:
        raise HTTPException(status_code=404, detail="Bot not found")

    update_data = data.model_dump(exclude_unset=True)
    if "api_key" in update_data and update_data["api_key"]:
        update_data["api_key_encrypted"] = encrypt_api_key(update_data.pop("api_key"))

    await crud.update_bot(db, bot_obj, update_data)
    return await crud.get_bot_response(db, bot_obj)


@app.delete("/api/v1/bots/{bot_id}")
async def delete_bot(
    bot_id: int,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(crud.get_current_user),
):
    await crud.delete_bot(db, bot_id)
    return {"message": "Bot deleted"}


@app.post("/api/v1/bots/{bot_id}/generate-claw-key", response_model=bot.ClawKeyResponse)
async def generate_claw_key(
    bot_id: int,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(crud.get_current_user),
):
    import secrets

    from app.core.security import hash_password

    token = secrets.token_urlsafe(32)
    key_hash = hash_password(token)
    await crud.create_claw_key(db, bot_id, key_hash)
    return {"token": token, "message": "Save this key! It will not be shown again."}


@app.post("/api/v1/chat", response_model=chat_schema.ChatResponse)
async def chat(
    message: chat_schema.ChatMessage,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(crud.get_current_user),
):
    from app.services.chat_service import process_chat

    return await process_chat(db, message)


@app.post("/api/v1/claw")
async def claw_endpoint(
    request: chat_schema.ClawRequest,
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(crud.verify_claw_key),
):
    from app.services.chat_service import process_chat

    bot_obj = await crud.get_bot_by_name(db, request.bot_id)
    if not bot_obj or not bot_obj.is_active:
        raise HTTPException(status_code=503, detail="Bot unavailable")

    message = chat_schema.ChatMessage(
        bot_id=bot_obj.id, query=request.query, thread_id=request.thread_id
    )
    return await process_chat(db, message)

from fastapi import FastAPI, Depends, HTTPException, status, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger
import sys

from app.db.session import async_session, engine
from app.db.models import Base
from app.core.security import create_access_token, create_refresh_token, verify_password, decode_token
from app.core.encryption import encrypt_api_key, decrypt_api_key
from app.schemas import auth, bot, chat as chat_schema
from app import crud

app = FastAPI(title="AI Bot Manager", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

bot_cache = {}


@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    async with async_session() as db:
        await crud.ensure_admin_exists(db)
    logger.info("Application started")


@app.post("/api/v1/auth/login", response_model=auth.TokenResponse)
async def login(credentials: auth.LoginRequest, db: AsyncSession = Depends(crud.get_db)):
    print(f"DEBUG LOGIN: username='{credentials.username}', password='{credentials.password}'", flush=True)
    logger.info(f"Login attempt: username={credentials.username}, password_length={len(credentials.password) if credentials.password else 0}")
    admin = await crud.get_admin_by_username(db, credentials.username)
    if not admin or not verify_password(credentials.password, admin.password_hash):
        print(f"DEBUG: admin_found={admin is not None}, verify_result={verify_password(credentials.password, admin.password_hash) if admin else 'N/A'}", flush=True)
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    access_token = create_access_token({"sub": admin.username})
    refresh_token = create_refresh_token({"sub": admin.username})
    print(f"DEBUG: Login successful for {credentials.username}", flush=True)
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
        raise HTTPException(status_code=401, detail="Invalid refresh token")


@app.api_route("/api/v1/bots", methods=["GET", "POST"])
async def manage_bots(
    request: Request,
    db: AsyncSession = Depends(crud.get_db),
    user: dict = Depends(crud.get_current_user)
):
    if await request.body():
        body = await request.json()
        bot_data = bot.BotCreate(**body)
        encrypted_key = encrypt_api_key(bot_data.api_key) if bot_data.api_key else None
        new_bot = await crud.create_bot(db, bot_data, encrypted_key)
        return await crud.get_bot_response(db, new_bot)
    bots = await crud.get_all_bots(db)
    return [await crud.get_bot_response(db, b) for b in bots]


@app.put("/api/v1/bots/{bot_id}")
async def update_bot(
    bot_id: int,
    data: bot.BotUpdate,
    db: AsyncSession = Depends(crud.get_db),
    user: dict = Depends(crud.get_current_user)
):
    bot_obj = await crud.get_bot_by_id(db, bot_id)
    if not bot_obj:
        raise HTTPException(status_code=404, detail="Bot not found")
    
    update_data = data.dict(exclude_unset=True)
    if "api_key" in update_data and update_data["api_key"]:
        update_data["api_key_encrypted"] = encrypt_api_key(update_data.pop("api_key"))
    
    await crud.update_bot(db, bot_obj, update_data)
    bot_cache.pop(bot_id, None)
    return await crud.get_bot_response(db, bot_obj)


@app.delete("/api/v1/bots/{bot_id}")
async def delete_bot(
    bot_id: int,
    db: AsyncSession = Depends(crud.get_db),
    user: dict = Depends(crud.get_current_user)
):
    await crud.delete_bot(db, bot_id)
    bot_cache.pop(bot_id, None)
    return {"message": "Bot deleted"}


@app.post("/api/v1/bots/{bot_id}/generate-claw-key", response_model=bot.ClawKeyResponse)
async def generate_claw_key(
    bot_id: int,
    db: AsyncSession = Depends(crud.get_db),
    user: dict = Depends(crud.get_current_user)
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
    db: AsyncSession = Depends(crud.get_db),
    user: dict = Depends(crud.get_current_user)
):
    from app.services.chat_service import process_chat
    return await process_chat(db, message)


@app.post("/api/v1/claw")
async def claw_endpoint(
    request: chat_schema.ClawRequest,
    db: AsyncSession = Depends(crud.get_db),
    api_key: str = Depends(crud.verify_claw_key)
):
    from app.services.chat_service import process_chat
    bot_obj = await crud.get_bot_by_name(db, request.bot_id)
    if not bot_obj or not bot_obj.is_active:
        raise HTTPException(status_code=503, detail="Bot unavailable")
    
    message = chat_schema.ChatMessage(bot_id=bot_obj.id, query=request.query, thread_id=request.thread_id)
    return await process_chat(db, message)

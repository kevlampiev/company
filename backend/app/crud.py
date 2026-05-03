from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from datetime import datetime
from typing import Optional
from fastapi import HTTPException, Depends, Request
from loguru import logger

from app.db.models import Admin, Bot, ClawApiKey, Message
from app.db.session import async_session
from app.core.security import hash_password, verify_password, decode_token
from app.schemas import bot as bot_schema


async def ensure_admin_exists(db: AsyncSession):
    from app.config import settings
    result = await db.execute(select(Admin).limit(1))
    if not result.scalar_one_or_none():
        admin = Admin(
            username=settings.ADMIN_USERNAME,
            password_hash=hash_password(settings.ADMIN_PASSWORD[:72])
        )
        db.add(admin)
        await db.commit()
        logger.info("Admin user created")


async def get_admin_by_username(db: AsyncSession, username: str) -> Optional[Admin]:
    result = await db.execute(select(Admin).where(Admin.username == username))
    return result.scalar_one_or_none()


async def get_current_user(request: Request):
    token = request.headers.get("Authorization")
    if not token:
        raise HTTPException(status_code=401, detail="Missing token")
    try:
        payload = decode_token(token.replace("Bearer ", ""))
        return payload
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")


async def create_bot(db: AsyncSession, data: bot_schema.BotCreate, encrypted_key: Optional[str]) -> Bot:
    bot = Bot(
        name=data.name,
        area=data.area,
        system_prompt=data.system_prompt,
        provider=data.provider,
        model=data.model,
        api_key_encrypted=encrypted_key,
        is_active=data.is_active,
        use_rag=data.use_rag
    )
    db.add(bot)
    await db.commit()
    await db.refresh(bot)
    return bot


async def get_all_bots(db: AsyncSession):
    result = await db.execute(select(Bot).order_by(Bot.id))
    return result.scalars().all()


async def get_bot_by_id(db: AsyncSession, bot_id: int) -> Optional[Bot]:
    result = await db.execute(select(Bot).where(Bot.id == bot_id))
    return result.scalar_one_or_none()


async def get_bot_by_name(db: AsyncSession, name: str) -> Optional[Bot]:
    result = await db.execute(select(Bot).where(Bot.name == name))
    return result.scalar_one_or_none()


async def update_bot(db: AsyncSession, bot: Bot, data: dict):
    for key, value in data.items():
        setattr(bot, key, value)
    bot.updated_at = datetime.utcnow()
    await db.commit()


async def delete_bot(db: AsyncSession, bot_id: int):
    await db.execute(delete(Bot).where(Bot.id == bot_id))
    await db.execute(delete(ClawApiKey).where(ClawApiKey.bot_id == bot_id))
    await db.commit()


async def create_claw_key(db: AsyncSession, bot_id: int, key_hash: str):
    claw_key = ClawApiKey(bot_id=bot_id, key_hash=key_hash)
    db.add(claw_key)
    await db.commit()


async def verify_claw_key(request: Request):
    api_key = request.headers.get("X-API-Key")
    if not api_key:
        raise HTTPException(status_code=403, detail="API key required")
    
    async with async_session() as db:
        result = await db.execute(select(ClawApiKey))
        keys = result.scalars().all()
        
        for key in keys:
            if verify_password(api_key, key.key_hash):
                return key
        
        raise HTTPException(status_code=403, detail="Invalid API key")


async def get_bot_response(db: AsyncSession, bot: Bot):
    from app.core.encryption import decrypt_api_key
    api_key = decrypt_api_key(bot.api_key_encrypted) if bot.api_key_encrypted else ""
    masked = api_key[:4] + "*" * (len(api_key) - 4) if len(api_key) > 4 else "****"
    
    return {
        "id": bot.id,
        "name": bot.name,
        "area": bot.area,
        "system_prompt": bot.system_prompt,
        "provider": bot.provider,
        "model": bot.model,
        "api_key_masked": masked,
        "is_active": bot.is_active,
        "use_rag": bot.use_rag,
        "created_at": bot.created_at,
        "updated_at": bot.updated_at
    }

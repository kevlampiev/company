"""Bot row queries."""

from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Bot, ClawApiKey
from app.schemas import bot as bot_schema


async def create(
    db: AsyncSession,
    data: bot_schema.BotCreate,
    encrypted_key: str | None,
) -> Bot:
    bot = Bot(
        name=data.name,
        area=data.area,
        system_prompt=data.system_prompt,
        provider=data.provider,
        model=data.model,
        api_key_encrypted=encrypted_key,
        is_active=data.is_active,
        use_rag=data.use_rag,
    )
    db.add(bot)
    await db.commit()
    await db.refresh(bot)
    return bot


async def list_all(db: AsyncSession) -> list[Bot]:
    result = await db.execute(select(Bot).order_by(Bot.id))
    return list(result.scalars().all())


async def get_by_id(db: AsyncSession, bot_id: int) -> Bot | None:
    result = await db.execute(select(Bot).where(Bot.id == bot_id))
    return result.scalar_one_or_none()


async def get_by_name(db: AsyncSession, name: str) -> Bot | None:
    result = await db.execute(select(Bot).where(Bot.name == name))
    return result.scalar_one_or_none()


async def update(db: AsyncSession, bot: Bot, data: dict) -> None:
    for key, value in data.items():
        setattr(bot, key, value)
    bot.updated_at = datetime.now(UTC)
    await db.commit()


async def delete_by_id(db: AsyncSession, bot_id: int) -> None:
    """Removes the bot and any claw keys scoped to it (no FK cascade in the schema)."""
    await db.execute(delete(Bot).where(Bot.id == bot_id))
    await db.execute(delete(ClawApiKey).where(ClawApiKey.bot_id == bot_id))
    await db.commit()

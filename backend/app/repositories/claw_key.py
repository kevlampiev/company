"""Claw (OpenClaw) API key issuance and verification."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import verify_password
from app.db.models import ClawApiKey


async def create(db: AsyncSession, bot_id: int, key_hash: str) -> None:
    db.add(ClawApiKey(bot_id=bot_id, key_hash=key_hash))
    await db.commit()


async def verify_for_bot(db: AsyncSession, api_key: str, bot_id: int) -> bool:
    """True iff `api_key` matches one of the claw keys issued for `bot_id`.

    Verification is scoped to the bot's own keys — a key issued for bot A does
    not unlock bot B. Iteration is bounded by keys-per-bot (typically 0-2 in
    personal use), so the per-key bcrypt cost stays negligible without needing
    a separate prefix index.
    """
    result = await db.execute(select(ClawApiKey).where(ClawApiKey.bot_id == bot_id))
    for key in result.scalars().all():
        if verify_password(api_key, key.key_hash):
            return True
    return False

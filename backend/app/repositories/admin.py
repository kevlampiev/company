"""Admin row queries + the first-startup seed."""
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.security import hash_password
from app.db.models import Admin


async def get_by_username(db: AsyncSession, username: str) -> Admin | None:
    result = await db.execute(select(Admin).where(Admin.username == username))
    return result.scalar_one_or_none()


async def ensure_exists(db: AsyncSession) -> None:
    """Seed the admin row from settings on first startup. No-op if one exists."""
    result = await db.execute(select(Admin).limit(1))
    if not result.scalar_one_or_none():
        admin = Admin(
            username=settings.ADMIN_USERNAME,
            password_hash=hash_password(settings.ADMIN_PASSWORD[:72]),
        )
        db.add(admin)
        await db.commit()
        logger.info("Admin user created")

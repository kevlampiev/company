from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from app.db.models import Bot


class BotCreate(BaseModel):
    name: str
    area: str
    system_prompt: str
    provider: str
    model: str
    api_key: str | None = None
    is_active: bool = True
    use_rag: bool = False


class BotUpdate(BaseModel):
    name: str | None = None
    area: str | None = None
    system_prompt: str | None = None
    provider: str | None = None
    model: str | None = None
    api_key: str | None = None
    is_active: bool | None = None
    use_rag: bool | None = None


class BotResponse(BaseModel):
    id: int
    name: str
    area: str
    system_prompt: str
    provider: str
    model: str
    api_key_masked: str
    is_active: bool
    use_rag: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_bot(cls, bot: "Bot") -> "BotResponse":
        from app.core.encryption import decrypt_api_key, mask_api_key

        plain = decrypt_api_key(bot.api_key_encrypted) if bot.api_key_encrypted else ""
        return cls(
            id=bot.id,
            name=bot.name,
            area=bot.area,
            system_prompt=bot.system_prompt,
            provider=bot.provider,
            model=bot.model,
            api_key_masked=mask_api_key(plain),
            is_active=bot.is_active,
            use_rag=bot.use_rag,
            created_at=bot.created_at,
            updated_at=bot.updated_at,
        )


class ClawKeyResponse(BaseModel):
    token: str
    message: str

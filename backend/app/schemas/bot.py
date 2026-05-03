from datetime import datetime

from pydantic import BaseModel, ConfigDict


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


class ClawKeyResponse(BaseModel):
    token: str
    message: str

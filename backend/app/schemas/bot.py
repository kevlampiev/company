from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class BotCreate(BaseModel):
    name: str
    area: str
    system_prompt: str
    provider: str
    model: str
    api_key: Optional[str] = None
    is_active: bool = True
    use_rag: bool = False


class BotUpdate(BaseModel):
    name: Optional[str] = None
    area: Optional[str] = None
    system_prompt: Optional[str] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    api_key: Optional[str] = None
    is_active: Optional[bool] = None
    use_rag: Optional[bool] = None


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
    
    class Config:
        from_attributes = True


class ClawKeyResponse(BaseModel):
    token: str
    message: str

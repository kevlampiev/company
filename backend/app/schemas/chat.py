from pydantic import BaseModel
from typing import Optional


class ChatMessage(BaseModel):
    bot_id: int
    query: str
    thread_id: Optional[str] = None


class ChatResponse(BaseModel):
    answer: str
    thread_id: str
    sources: list = []


class ClawRequest(BaseModel):
    bot_id: str
    query: str
    thread_id: Optional[str] = None

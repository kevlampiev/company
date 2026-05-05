from typing import List, Optional
from pydantic import BaseModel


class ChatMessage(BaseModel):
    bot_id: int
    query: str
    thread_id: Optional[str] = None
    files: Optional[List[str]] = None  # base64-encoded file contents


class ChatResponse(BaseModel):
    answer: str
    thread_id: str
    sources: list = []


class ClawRequest(BaseModel):
    bot_id: str
    query: str
    thread_id: Optional[str] = None

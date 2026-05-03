from pydantic import BaseModel


class ChatMessage(BaseModel):
    bot_id: int
    query: str
    thread_id: str | None = None


class ChatResponse(BaseModel):
    answer: str
    thread_id: str
    sources: list = []


class ClawRequest(BaseModel):
    bot_id: str
    query: str
    thread_id: str | None = None

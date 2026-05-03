import httpx
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.core.encryption import decrypt_api_key
from app.db.models import Bot, Message
from app.schemas.chat import ChatResponse


async def process_chat(db: AsyncSession, message) -> ChatResponse:
    bot = await crud.get_bot_by_id(db, message.bot_id)
    if not bot or not bot.is_active:
        raise ValueError("Bot not found or inactive")

    thread_id = message.thread_id or "default"

    await save_message(db, bot.id, thread_id, "user", message.query)

    try:
        answer = await call_llm(bot, message.query, thread_id)
        answer += (
            "\n\n*Справка носит информационный характер и не заменяет официальную консультацию.*"
        )

        await save_message(db, bot.id, thread_id, "assistant", answer)

        return ChatResponse(answer=answer, thread_id=thread_id, sources=[])
    except Exception as e:
        logger.error(f"Chat error: {e}")
        raise


async def call_llm(bot: Bot, query: str, thread_id: str) -> str:
    api_key = decrypt_api_key(bot.api_key_encrypted) if bot.api_key_encrypted else ""

    if bot.provider == "openai":
        return await call_openai(bot.model, api_key, bot.system_prompt, query)
    elif bot.provider == "anthropic":
        return await call_anthropic(bot.model, api_key, bot.system_prompt, query)
    else:
        return await call_openai_compatible(
            bot.provider, bot.model, api_key, bot.system_prompt, query
        )


async def call_openai(model: str, api_key: str, system: str, query: str) -> str:
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": query}],
        "stream": False,
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            "https://api.openai.com/v1/chat/completions", json=payload, headers=headers
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]


async def call_anthropic(model: str, api_key: str, system: str, query: str) -> str:
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "system": system,
        "messages": [{"role": "user", "content": query}],
        "max_tokens": 4096,
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages", json=payload, headers=headers
        )
        resp.raise_for_status()
        data = resp.json()
        return data["content"][0]["text"]


async def call_openai_compatible(
    provider: str, model: str, api_key: str, system: str, query: str
) -> str:
    base_urls = {
        "groq": "https://api.groq.com/openai/v1",
        "openrouter": "https://openrouter.ai/api/v1",
    }
    base_url = base_urls.get(provider, provider)

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": query}],
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(f"{base_url}/chat/completions", json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]


async def save_message(db: AsyncSession, bot_id: int, thread_id: str, role: str, content: str):
    msg = Message(bot_id=bot_id, thread_id=thread_id, role=role, content=content)
    db.add(msg)
    await db.commit()

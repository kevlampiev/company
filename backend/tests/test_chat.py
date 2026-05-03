"""Chat: provider dispatch (OpenAI vs Anthropic) and message persistence."""

import httpx
import respx
from sqlalchemy import select


async def test_chat_dispatches_to_openai(client, auth_headers, make_bot):
    bot = await make_bot(provider="openai", api_key="sk-test")
    with respx.mock:
        route = respx.post("https://api.openai.com/v1/chat/completions").mock(
            return_value=httpx.Response(
                200, json={"choices": [{"message": {"content": "hi from openai"}}]}
            )
        )
        resp = await client.post(
            "/api/v1/chat",
            headers=auth_headers,
            json={"bot_id": bot["id"], "query": "test"},
        )
    assert resp.status_code == 200
    assert route.called
    assert "hi from openai" in resp.json()["answer"]


async def test_chat_dispatches_to_anthropic(client, auth_headers, make_bot):
    bot = await make_bot(
        provider="anthropic",
        api_key="sk-ant",
        model="claude-3-5-sonnet-latest",
    )
    with respx.mock:
        route = respx.post("https://api.anthropic.com/v1/messages").mock(
            return_value=httpx.Response(200, json={"content": [{"text": "hi from anthropic"}]})
        )
        resp = await client.post(
            "/api/v1/chat",
            headers=auth_headers,
            json={"bot_id": bot["id"], "query": "test"},
        )
    assert resp.status_code == 200
    assert route.called
    assert "hi from anthropic" in resp.json()["answer"]


async def test_chat_persists_user_and_assistant_messages(client, auth_headers, make_bot):
    from app.db.models import Message
    from app.db.session import async_session

    bot = await make_bot(provider="openai", api_key="sk-test")
    with respx.mock:
        respx.post("https://api.openai.com/v1/chat/completions").mock(
            return_value=httpx.Response(
                200, json={"choices": [{"message": {"content": "the answer"}}]}
            )
        )
        resp = await client.post(
            "/api/v1/chat",
            headers=auth_headers,
            json={"bot_id": bot["id"], "query": "the question"},
        )
    assert resp.status_code == 200

    async with async_session() as db:
        result = await db.execute(select(Message).order_by(Message.id))
        rows = result.scalars().all()
    assert len(rows) == 2
    assert rows[0].role == "user"
    assert rows[0].content == "the question"
    assert rows[1].role == "assistant"
    assert "the answer" in rows[1].content

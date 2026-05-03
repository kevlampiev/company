"""Claw (OpenClaw) API key: generate, valid call, invalid call, current any-key-any-bot bug."""

import httpx
import respx
from sqlalchemy import select


async def test_generate_claw_key_returns_token_and_stores_hash(client, auth_headers, make_bot):
    from app.db.models import ClawApiKey
    from app.db.session import async_session

    bot = await make_bot()
    resp = await client.post(
        f"/api/v1/bots/{bot['id']}/generate-claw-key",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "token" in data
    assert len(data["token"]) > 30

    async with async_session() as db:
        result = await db.execute(select(ClawApiKey).where(ClawApiKey.bot_id == bot["id"]))
        row = result.scalar_one_or_none()
    assert row is not None
    assert row.key_hash != data["token"]


async def test_invalid_claw_key_returns_403(client):
    resp = await client.post(
        "/api/v1/claw",
        headers={"X-API-Key": "wrong"},
        json={"bot_id": "anybot", "query": "hi"},
    )
    assert resp.status_code == 403


async def test_valid_claw_key_calls_llm(client, auth_headers, make_bot):
    bot = await make_bot(name="lawyer", provider="openai", api_key="sk-real")
    keyresp = await client.post(
        f"/api/v1/bots/{bot['id']}/generate-claw-key",
        headers=auth_headers,
    )
    token = keyresp.json()["token"]

    with respx.mock:
        respx.post("https://api.openai.com/v1/chat/completions").mock(
            return_value=httpx.Response(200, json={"choices": [{"message": {"content": "hello"}}]})
        )
        resp = await client.post(
            "/api/v1/claw",
            headers={"X-API-Key": token},
            json={"bot_id": "lawyer", "query": "hi"},
        )
    assert resp.status_code == 200
    assert "hello" in resp.json()["answer"]


async def test_claw_key_does_not_authorise_other_bots(client, auth_headers, make_bot):
    """A key issued for bot A must not unlock bot B."""
    bot_a = await make_bot(name="alpha")
    await make_bot(name="beta", api_key="sk-real")
    keyresp = await client.post(
        f"/api/v1/bots/{bot_a['id']}/generate-claw-key",
        headers=auth_headers,
    )
    token = keyresp.json()["token"]

    resp = await client.post(
        "/api/v1/claw",
        headers={"X-API-Key": token},
        json={"bot_id": "beta", "query": "hi"},
    )
    assert resp.status_code == 403

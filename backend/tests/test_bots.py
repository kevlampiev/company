"""Bot CRUD: create, list, update (with key re-encryption), delete (with claw-key cascade)."""

import httpx
import respx
from sqlalchemy import select


async def test_create_bot_returns_masked_key(client, auth_headers):
    body = {
        "name": "lawyer",
        "area": "law",
        "system_prompt": "you are a lawyer",
        "provider": "openai",
        "model": "gpt-4o-mini",
        "api_key": "sk-secret-12345",
        "is_active": True,
        "use_rag": False,
    }
    resp = await client.post("/api/v1/bots", headers=auth_headers, json=body)
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "lawyer"
    assert data["api_key_masked"].startswith("sk-s")
    assert "sk-secret" not in data["api_key_masked"]


async def test_list_bots_returns_created(client, auth_headers, make_bot):
    await make_bot(name="alpha")
    await make_bot(name="beta")
    resp = await client.get("/api/v1/bots", headers=auth_headers)
    assert resp.status_code == 200
    names = [b["name"] for b in resp.json()]
    assert names == ["alpha", "beta"]


async def test_update_bot_fields(client, auth_headers, make_bot):
    bot = await make_bot()
    resp = await client.put(
        f"/api/v1/bots/{bot['id']}",
        headers=auth_headers,
        json={"area": "updated_area"},
    )
    assert resp.status_code == 200
    assert resp.json()["area"] == "updated_area"


async def test_update_bot_reencrypts_api_key(client, auth_headers, make_bot):
    bot = await make_bot(api_key="sk-old-key")
    resp = await client.put(
        f"/api/v1/bots/{bot['id']}",
        headers=auth_headers,
        json={"api_key": "sk-new-key-99"},
    )
    assert resp.status_code == 200
    masked = resp.json()["api_key_masked"]
    assert masked.startswith("sk-n")
    assert "sk-new" not in masked


async def test_delete_bot_cascades_claw_keys(client, auth_headers, make_bot):
    from app.db.models import ClawApiKey
    from app.db.session import async_session

    bot = await make_bot()
    bot_id = bot["id"]
    resp = await client.post(
        f"/api/v1/bots/{bot_id}/generate-claw-key",
        headers=auth_headers,
    )
    assert resp.status_code == 200

    resp = await client.delete(f"/api/v1/bots/{bot_id}", headers=auth_headers)
    assert resp.status_code == 200

    async with async_session() as db:
        result = await db.execute(select(ClawApiKey).where(ClawApiKey.bot_id == bot_id))
        assert result.scalar_one_or_none() is None


async def test_test_bot_connection_success(client, auth_headers, make_bot):
    """Test connection endpoint returns success for valid API key."""
    bot = await make_bot(provider="deepseek", api_key="sk-test", model="deepseek-chat")

    with respx.mock:
        respx.post("https://api.deepseek.com/v1/chat/completions").mock(
            return_value=httpx.Response(200, json={"choices": [{"message": {"content": "hi"}}]})
        )
        resp = await client.post(f"/api/v1/bots/{bot['id']}/test", headers=auth_headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["message"] == "OK"


async def test_test_bot_connection_failure(client, auth_headers, make_bot):
    """Test connection endpoint returns failure for invalid API key."""
    bot = await make_bot(provider="deepseek", api_key="sk-test", model="deepseek-chat")

    with respx.mock:
        respx.post("https://api.deepseek.com/v1/chat/completions").mock(
            return_value=httpx.Response(401)
        )
        resp = await client.post(f"/api/v1/bots/{bot['id']}/test", headers=auth_headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    assert "Ошибка подключения" in data["message"]


async def test_test_bot_no_api_key(client, auth_headers, make_bot):
    """Test connection endpoint handles missing API key."""
    bot = await make_bot(api_key=None)
    resp = await client.post(f"/api/v1/bots/{bot['id']}/test", headers=auth_headers)

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    assert "API-ключ не настроен" in data["message"]


async def test_update_bot_empty_api_key(client, auth_headers, make_bot):
    """Test that updating with empty api_key doesn't change the key."""
    bot = await make_bot(api_key="sk-original-key")
    resp = await client.put(
        f"/api/v1/bots/{bot['id']}",
        headers=auth_headers,
        json={"api_key": ""},
    )
    assert resp.status_code == 200
    # Key should remain unchanged (masked should still start with sk-or)
    assert resp.json()["api_key_masked"].startswith("sk-o")


async def test_update_bot_missing_api_key_field(client, auth_headers, make_bot):
    """Test that omitting api_key from update doesn't change the key."""
    bot = await make_bot(api_key="sk-stays-here")
    resp = await client.put(
        f"/api/v1/bots/{bot['id']}",
        headers=auth_headers,
        json={"name": "new_name"},
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "new_name"
    assert resp.json()["api_key_masked"].startswith("sk-s")

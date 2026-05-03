"""FastAPI dependencies — currently just admin bearer-token auth."""

from fastapi import HTTPException, Request

from app.core.security import decode_token


async def get_current_user(request: Request) -> dict:
    token = request.headers.get("Authorization")
    if not token:
        raise HTTPException(status_code=401, detail="Missing token")
    try:
        return decode_token(token.replace("Bearer ", ""))
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token") from None

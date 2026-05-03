"""Password hashing + JWT helpers."""
from datetime import timedelta

import pytest

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


def test_hash_verify_round_trip():
    h = hash_password("secret123")
    assert verify_password("secret123", h)
    assert not verify_password("wrong", h)


def test_access_token_carries_type_access():
    tok = create_access_token({"sub": "alice"})
    payload = decode_token(tok)
    assert payload["sub"] == "alice"
    assert payload["type"] == "access"


def test_refresh_token_carries_type_refresh():
    tok = create_refresh_token({"sub": "alice"})
    assert decode_token(tok)["type"] == "refresh"


def test_expired_token_is_rejected():
    tok = create_access_token({"sub": "alice"}, expires_delta=timedelta(seconds=-1))
    with pytest.raises(ValueError, match="expired"):
        decode_token(tok)

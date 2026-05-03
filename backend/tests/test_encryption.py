"""Fernet encryption helpers."""

from app.core.encryption import decrypt_api_key, encrypt_api_key


def test_round_trip():
    original = "sk-test-1234567890"
    encrypted = encrypt_api_key(original)
    assert encrypted != original
    assert decrypt_api_key(encrypted) == original


def test_encrypt_empty_returns_empty():
    assert encrypt_api_key("") == ""


def test_decrypt_empty_returns_empty():
    assert decrypt_api_key("") == ""

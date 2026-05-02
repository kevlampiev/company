from cryptography.fernet import Fernet
from app.config import settings


def get_fernet() -> Fernet:
    return Fernet(settings.ENCRYPTION_KEY.encode() if isinstance(settings.ENCRYPTION_KEY, str) else settings.ENCRYPTION_KEY)


def encrypt_api_key(api_key: str) -> str:
    if not api_key:
        return ""
    f = get_fernet()
    return f.encrypt(api_key.encode()).decode()


def decrypt_api_key(encrypted_key: str) -> str:
    if not encrypted_key:
        return ""
    f = get_fernet()
    return f.decrypt(encrypted_key.encode()).decode()

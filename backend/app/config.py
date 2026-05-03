from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


_REPO_ROOT_ENV = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_REPO_ROOT_ENV, extra="ignore")

    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = Field(...)

    JWT_SECRET: str = Field(...)
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    ENCRYPTION_KEY: str = Field(...)

    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = Field(...)
    POSTGRES_DB: str = "ai_bots"
    DATABASE_URL: Optional[str] = None

    REDIS_URL: str = "redis://redis:6379/0"

    DOMAIN: str = "localhost"

    SSL_CERT_PATH: str = "/etc/nginx/ssl/cert.pem"
    SSL_KEY_PATH: str = "/etc/nginx/ssl/key.pem"

    @property
    def async_database_url(self) -> str:
        if self.DATABASE_URL:
            return self.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@db:5432/{self.POSTGRES_DB}"


settings = Settings()

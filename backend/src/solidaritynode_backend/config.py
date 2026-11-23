"""Application settings from the environment (Pydantic v2 settings)."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = ["Settings", "get_settings"]


class Settings(BaseSettings):
    """Backend settings, read from ``SOLIDARITYNODE_*`` environment variables or ``.env``.

    Attributes:
        environment: Deployment environment name.
        log_level: Uvicorn/application log level.
        database_url: SQLAlchemy URL for PostgreSQL/PostGIS. Kept secret in logs and reprs.
        cors_origins: Origins allowed to call the API from a browser.
    """

    model_config = SettingsConfigDict(
        env_prefix="SOLIDARITYNODE_", env_file=".env", extra="ignore", frozen=True
    )

    environment: Literal["development", "test", "production"] = "development"
    log_level: Literal["debug", "info", "warning", "error"] = "info"
    database_url: SecretStr = SecretStr(
        "postgresql+psycopg://solidaritynode@localhost:5432/solidaritynode"
    )
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])


@lru_cache
def get_settings() -> Settings:
    """Return the cached process-wide settings."""
    return Settings()

"""Application settings from the environment (Pydantic v2 settings)."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal, Self

from pydantic import AliasChoices, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

__all__ = ["PLACEHOLDER_PREFIX", "AppEnv", "Settings", "get_settings"]

AppEnv = Literal["development", "test", "production"]

PLACEHOLDER_PREFIX = "change-me"
"""Secrets starting with this prefix are placeholders from ``.env.example``."""

_ENVS_ALLOWING_PLACEHOLDERS: frozenset[str] = frozenset({"development", "test"})


class Settings(BaseSettings):
    """Backend settings, read from the environment or ``.env``.

    ``APP_ENV`` and ``GIT_COMMIT`` are read without prefix; every other value uses the
    ``SOLIDARITYNODE_`` prefix.

    Attributes:
        app_env: ``development``, ``test`` (the test suite) or ``production``. Outside
            ``development`` and ``test`` the backend refuses to start while any secret still
            starts with ``change-me``.
        git_commit: Git commit the running build was made from (set at image build time).
        log_level: Uvicorn/application log level.
        database_url: SQLAlchemy URL for PostgreSQL/PostGIS. Kept secret in logs and reprs.
        cors_origins: Origins allowed to call the API from a browser.
    """

    model_config = SettingsConfigDict(
        env_prefix="SOLIDARITYNODE_", env_file=".env", extra="ignore", frozen=True
    )

    app_env: AppEnv = Field(default="development", validation_alias=AliasChoices("APP_ENV"))
    git_commit: str = Field(default="unknown", validation_alias=AliasChoices("GIT_COMMIT"))
    log_level: Literal["debug", "info", "warning", "error"] = "info"
    database_url: SecretStr = SecretStr(
        "postgresql+psycopg://solidaritynode@localhost:5432/solidaritynode"
    )
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    def placeholder_secrets(self) -> list[str]:
        """Return the names of secrets whose value starts with ``change-me``."""
        found: list[str] = []
        password = make_url(self.database_url.get_secret_value()).password
        if password is not None and str(password).startswith(PLACEHOLDER_PREFIX):
            found.append("database_url (password)")
        return found

    @model_validator(mode="after")
    def _refuse_placeholder_secrets(self) -> Self:
        if self.app_env in _ENVS_ALLOWING_PLACEHOLDERS:
            return self
        if found := self.placeholder_secrets():
            raise ValueError(
                f"APP_ENV={self.app_env}: placeholder secrets must be replaced before "
                f"starting: {', '.join(found)}"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    """Return the cached process-wide settings."""
    return Settings()

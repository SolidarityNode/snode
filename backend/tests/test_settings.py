from __future__ import annotations

import pytest
from pydantic import ValidationError

from solidaritynode_backend.config import Settings

PLACEHOLDER_URL = "postgresql+psycopg://u:change-me@db:5432/x"
OTHER_PLACEHOLDER_URL = "postgresql+psycopg://u:change-me-local-only@db:5432/x"
REAL_URL = "postgresql+psycopg://u:s3cr3t-value@db:5432/x"


def test_suite_runs_with_app_env_test() -> None:
    assert Settings().app_env == "test"


def test_app_env_is_read_without_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("GIT_COMMIT", "abc1234")
    settings = Settings()
    assert settings.app_env == "development"
    assert settings.git_commit == "abc1234"


def test_unknown_app_env_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "staging")
    with pytest.raises(ValueError, match="APP_ENV"):
        Settings()


@pytest.mark.parametrize("env", ["development", "test"])
@pytest.mark.parametrize("url", [PLACEHOLDER_URL, OTHER_PLACEHOLDER_URL])
def test_placeholders_allowed_in_development_and_test(
    monkeypatch: pytest.MonkeyPatch, env: str, url: str
) -> None:
    monkeypatch.setenv("APP_ENV", env)
    monkeypatch.setenv("SOLIDARITYNODE_DATABASE_URL", url)
    assert Settings().placeholder_secrets() == ["database_url (password)"]


@pytest.mark.parametrize("url", [PLACEHOLDER_URL, OTHER_PLACEHOLDER_URL])
def test_production_refuses_placeholder_secrets(monkeypatch: pytest.MonkeyPatch, url: str) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SOLIDARITYNODE_DATABASE_URL", url)
    with pytest.raises(ValidationError, match="placeholder secrets"):
        Settings()


def test_validation_errors_do_not_echo_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SOLIDARITYNODE_LOG_LEVEL", "loud")
    monkeypatch.setenv("SOLIDARITYNODE_DATABASE_URL", REAL_URL)
    with pytest.raises(ValidationError) as excinfo:
        Settings()
    assert "s3cr3t" not in str(excinfo.value)


def test_production_accepts_real_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SOLIDARITYNODE_DATABASE_URL", REAL_URL)
    settings = Settings()
    assert settings.placeholder_secrets() == []
    assert "s3cr3t" not in repr(settings)

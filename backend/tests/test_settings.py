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
    monkeypatch.setenv("GIT_COMMIT", "0123456789ab")
    monkeypatch.setenv("SOLIDARITYNODE_SESSION_COOKIE_SECURE", "true")
    monkeypatch.setenv("SOLIDARITYNODE_DATABASE_URL", url)
    with pytest.raises(ValidationError, match="placeholder secrets"):
        Settings()


def test_validation_errors_do_not_echo_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("GIT_COMMIT", "0123456789ab")
    monkeypatch.setenv("SOLIDARITYNODE_LOG_LEVEL", "loud")
    monkeypatch.setenv("SOLIDARITYNODE_DATABASE_URL", REAL_URL)
    with pytest.raises(ValidationError) as excinfo:
        Settings()
    assert "s3cr3t" not in str(excinfo.value)


def test_production_accepts_real_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("GIT_COMMIT", "0123456789ab")
    monkeypatch.setenv("SOLIDARITYNODE_SESSION_COOKIE_SECURE", "true")
    monkeypatch.setenv("SOLIDARITYNODE_DATABASE_URL", REAL_URL)
    settings = Settings()
    assert settings.placeholder_secrets() == []
    assert "s3cr3t" not in repr(settings)


def test_production_requires_a_secure_session_cookie(monkeypatch: pytest.MonkeyPatch) -> None:
    """ADR 0015: in production the cookie is always Secure; check-config fails otherwise."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("GIT_COMMIT", "0123456789ab")
    monkeypatch.setenv("SOLIDARITYNODE_DATABASE_URL", REAL_URL)
    monkeypatch.setenv("SOLIDARITYNODE_SESSION_COOKIE_SECURE", "false")
    with pytest.raises(ValidationError, match="SESSION_COOKIE_SECURE=true"):
        Settings()
    monkeypatch.setenv("APP_ENV", "development")
    assert Settings().session_cookie_secure is False  # allowed outside production


@pytest.mark.parametrize("commit", ["unknown", "", "0123456789ab-dirty"])
def test_production_refuses_unknown_or_dirty_code(
    monkeypatch: pytest.MonkeyPatch, commit: str
) -> None:
    """ADR 0017: backend and worker refuse to start in production without clean code."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SOLIDARITYNODE_DATABASE_URL", REAL_URL)
    monkeypatch.setenv("SOLIDARITYNODE_SESSION_COOKIE_SECURE", "true")
    monkeypatch.setenv("GIT_COMMIT", commit)
    with pytest.raises(ValidationError, match="known, clean code version"):
        Settings()
    monkeypatch.setenv("APP_ENV", "development")
    assert Settings().git_commit == commit  # allowed in development (runs carry a warning)


def test_check_config_lists_every_problem_without_secrets(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """make check-config: all problems at once, one per line, exit 1, no traceback or secret."""
    from solidaritynode_backend.cli import main

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("GIT_COMMIT", "0123456789ab-dirty")
    monkeypatch.setenv("SOLIDARITYNODE_DATABASE_URL", PLACEHOLDER_URL)
    monkeypatch.setenv("SOLIDARITYNODE_SESSION_COOKIE_SECURE", "false")
    monkeypatch.setenv("SOLIDARITYNODE_TRUSTED_PROXIES", "10.0.0.0/8,nonsense")
    monkeypatch.setenv("SOLIDARITYNODE_SESSION_HOURS", "-1")
    assert main(["check-config"]) == 1
    err = capsys.readouterr().err
    lines = err.splitlines()
    assert lines[0] == "configuration INVALID (APP_ENV=production): 1 problem(s)"
    problems = [line for line in lines if line.startswith("  - ")]
    assert len(problems) == 1  # field errors come first; the rest after they are fixed
    assert "session_hours" in problems[0]
    assert "Traceback" not in err
    assert "-1" not in err  # values are never echoed
    monkeypatch.setenv("SOLIDARITYNODE_SESSION_HOURS", "12")
    assert main(["check-config"]) == 1
    err = capsys.readouterr().err
    assert err.splitlines()[0] == "configuration INVALID (APP_ENV=production): 4 problem(s)"
    for expected in (
        "clean code version",
        "SESSION_COOKIE_SECURE=true",
        "placeholder secrets",
        "trusted_proxies",
    ):
        assert expected in err
    assert "change-me" not in err.replace("start with ``change-me``", "")
    assert "u:change-me" not in err


def test_check_config_ok(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from solidaritynode_backend.cli import main

    monkeypatch.setenv("APP_ENV", "development")
    assert main(["check-config"]) == 0
    assert capsys.readouterr().out == "configuration OK (APP_ENV=development)\n"

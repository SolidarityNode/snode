"""Application settings from the environment (Pydantic v2 settings)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal, Self

from pydantic import AliasChoices, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from solidaritynode_core.uncertainty import check_interval
from sqlalchemy.engine import make_url

__all__ = ["PLACEHOLDER_PREFIX", "AppEnv", "Basemap", "DeploymentMode", "Settings", "get_settings"]

AppEnv = Literal["development", "test", "production"]
DeploymentMode = Literal["municipality", "hub"]
Basemap = Literal["osm", "blank"]

PLACEHOLDER_PREFIX = "change-me"
"""Secrets starting with this prefix are placeholders from ``.env.example``."""

_ENVS_ALLOWING_PLACEHOLDERS: frozenset[str] = frozenset({"development", "test"})


class Settings(BaseSettings):
    """Backend settings, read from the environment or ``.env``.

    ``APP_ENV``, ``GIT_COMMIT`` and ``DEPLOYMENT_MODE`` are read without prefix; every other
    value uses the ``SOLIDARITYNODE_`` prefix.

    Attributes:
        app_env: ``development``, ``test`` (the test suite) or ``production``. Outside
            ``development`` and ``test`` the backend refuses to start while any secret still
            starts with ``change-me``.
        git_commit: Git commit the running build was made from (set at image build time).
        log_level: Uvicorn/application log level.
        database_url: SQLAlchemy URL for PostgreSQL/PostGIS. Kept secret in logs and reprs.
        cors_origins: Origins allowed to call the API from a browser.
        deployment_mode: ``municipality`` (one study area of one or more core municipalities,
            ADR 0012) or ``hub``; locked in the database at first initialisation. Only the
            municipal installation is implemented in v0.1; ``hub`` starts but offers no hub
            features yet.
        packages_dir: Directory of data packages offered for import on the Admin screen.
        results_dir: Directory for per-sample results (Parquet) and package staging; a mounted
            volume in compose.
        basemap: ``osm`` (OpenStreetMap tiles, needs internet) or ``blank`` (offline).
        auth_backend: Authentication backend (ADR 0015); only ``local`` accounts in v0.1.
        session_hours: Lifetime of a login session.
        session_cookie_secure: Send the session cookie only over HTTPS. Required (``true``) with
            ``APP_ENV=production``: the backend refuses to start otherwise.
        login_max_failures_account: Failed sign-ins for one username before it is locked.
        login_max_failures_address: Failed sign-ins from one client address before it is locked.
        login_lock_minutes: How long a lock lasts; failures older than this are forgotten.
        login_delay_base_s: After failure ``n``, the next attempt for that username is refused for
            ``base × 2^(n-1)`` seconds (capped by ``login_delay_max_s``); a client address is
            delayed the same way from half its lock limit on.
        login_delay_max_s: Upper bound of that delay.
        diagnostic_step_delay_s: Pause after each progress step of a run, so progress and
            cancellation can be followed by hand. Part of the run configuration (and its hash).
        worker_name: Name of this worker process, for logs and the ``jobs.worker`` column only.
        worker_poll_s: Seconds between queue polls when idle.
        job_heartbeat_seconds: While a job runs, its worker updates ``jobs.heartbeat_at`` this
            often from a separate thread (the job's lease, ADR 0006).
        job_stale_seconds: Any worker marks a running job failed when its heartbeat is older
            than this (at start and periodically). At least twice ``job_heartbeat_seconds``.
        result_interval_quantiles: Quantile levels of the interval stored with every result
            value, as ``low,high`` (default ``0.05,0.95``, a 90 % interval; ``0 < low < 0.5 <
            high < 1``). Recorded in the run configuration and its input hash (ADR 0017).
        samples_warn_mb: Warn when a run's samples file is estimated (before the run starts) to
            exceed this many megabytes (ADR 0008). The run is still queued.
        job_max_runtime_seconds: Optional maximum runtime per job kind, as ``kind=seconds``
            pairs separated by commas (for example ``run=3600``). Empty (the default) means no
            limit for any kind, including the diagnostic model's ``run`` jobs. A job over its
            limit is stopped at its next progress step and marked failed.
    """

    model_config = SettingsConfigDict(
        env_prefix="SOLIDARITYNODE_",
        env_file=".env",
        extra="ignore",
        frozen=True,
        # Never echo inputs (for example the database URL with its password) in errors.
        hide_input_in_errors=True,
    )

    app_env: AppEnv = Field(default="development", validation_alias=AliasChoices("APP_ENV"))
    git_commit: str = Field(default="unknown", validation_alias=AliasChoices("GIT_COMMIT"))
    log_level: Literal["debug", "info", "warning", "error"] = "info"
    database_url: SecretStr = SecretStr(
        "postgresql+psycopg://solidaritynode@localhost:5432/solidaritynode"
    )
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])
    deployment_mode: DeploymentMode = Field(
        default="municipality", validation_alias=AliasChoices("DEPLOYMENT_MODE")
    )
    packages_dir: Path = Path("data/synthetic/packages")
    results_dir: Path = Path("var/results")
    basemap: Basemap = "osm"
    auth_backend: Literal["local"] = "local"
    session_hours: float = Field(default=12.0, gt=0)
    session_cookie_secure: bool = False
    login_max_failures_account: int = Field(default=5, ge=1)
    login_max_failures_address: int = Field(default=20, ge=1)
    login_lock_minutes: float = Field(default=15.0, gt=0)
    login_delay_base_s: float = Field(default=1.0, ge=0)
    login_delay_max_s: float = Field(default=30.0, ge=0)
    diagnostic_step_delay_s: float = Field(default=0.5, ge=0, le=60)
    worker_name: str = "worker"
    worker_poll_s: float = Field(default=1.0, gt=0)
    job_heartbeat_seconds: float = Field(default=10.0, gt=0)
    job_stale_seconds: float = Field(default=120.0, gt=0)
    job_max_runtime_seconds: str = ""
    result_interval_quantiles: str = "0.05,0.95"
    samples_warn_mb: float = Field(default=500.0, gt=0)

    def interval_quantiles(self) -> tuple[float, float]:
        """Return the interval quantile levels ``(low, high)`` of result values."""
        try:
            levels = [float(x) for x in self.result_interval_quantiles.split(",")]
        except ValueError as exc:
            raise ValueError("result_interval_quantiles: expected low,high (numbers)") from exc
        return check_interval(levels)

    def max_runtimes(self) -> dict[str, float]:
        """Return the maximum runtime in seconds per job kind (empty: no limits)."""
        limits: dict[str, float] = {}
        for item in self.job_max_runtime_seconds.split(","):
            if not item.strip():
                continue
            kind, sep, value = item.partition("=")
            if not sep or not kind.strip():
                raise ValueError(f"job_max_runtime_seconds: expected kind=seconds, got {item!r}")
            seconds = float(value)
            if seconds <= 0:
                raise ValueError(f"job_max_runtime_seconds: {kind.strip()} must be > 0")
            limits[kind.strip()] = seconds
        return limits

    def placeholder_secrets(self) -> list[str]:
        """Return the names of secrets whose value starts with ``change-me``."""
        found: list[str] = []
        password = make_url(self.database_url.get_secret_value()).password
        if password is not None and str(password).startswith(PLACEHOLDER_PREFIX):
            found.append("database_url (password)")
        return found

    @model_validator(mode="after")
    def _secure_cookie_in_production(self) -> Self:
        if self.app_env == "production" and not self.session_cookie_secure:
            raise ValueError(
                "APP_ENV=production needs SOLIDARITYNODE_SESSION_COOKIE_SECURE=true: the session "
                "cookie must only travel over HTTPS (ADR 0015)"
            )
        return self

    @model_validator(mode="after")
    def _check_job_timing(self) -> Self:
        if self.job_stale_seconds < 2 * self.job_heartbeat_seconds:
            raise ValueError(
                "job_stale_seconds must be at least twice job_heartbeat_seconds, or healthy "
                "jobs would be failed as stale"
            )
        self.max_runtimes()
        self.interval_quantiles()
        return self

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

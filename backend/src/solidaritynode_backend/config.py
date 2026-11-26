"""Application settings from the environment (Pydantic v2 settings)."""

from __future__ import annotations

from functools import lru_cache
from ipaddress import IPv4Network, IPv6Network, ip_network
from pathlib import Path
from typing import Literal, Self
from urllib.parse import urlsplit

from pydantic import AliasChoices, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from solidaritynode_core.uncertainty import check_interval
from sqlalchemy.engine import make_url

__all__ = [
    "PLACEHOLDER_PREFIX",
    "AppEnv",
    "Basemap",
    "BufferRule",
    "DeploymentMode",
    "Settings",
    "get_settings",
]

AppEnv = Literal["development", "test", "production"]
DeploymentMode = Literal["municipality", "hub"]
Basemap = Literal["osm", "blank"]
BufferRule = Literal["whole_neighbouring_municipalities", "distance"]

PROBLEM_SEPARATOR = "\n  - "
"""Joins configuration problems in one validation error (one problem per line)."""

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
        git_commit: Git commit the running build was made from (set at image build time). With
            ``APP_ENV=production`` it must be known and not end in ``-dirty``.
        log_level: Uvicorn/application log level.
        database_url: SQLAlchemy URL for PostgreSQL/PostGIS. Kept secret in logs and reprs.
        cors_origins: Origins allowed to call the API from a browser.
        deployment_mode: ``municipality`` (one study area of one or more core municipalities,
            ADR 0012) or ``hub`` (raw sources, onboarding, facility imports, package
            publishing); locked in the database at first initialisation.
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
        trusted_proxies: Comma-separated addresses or networks (CIDR) of the reverse proxies
            whose ``X-Real-IP`` / ``X-Forwarded-For`` give the client address (ADR 0015).
            Headers from any other peer are ignored. When the address a proxy reports is itself
            a proxy address (the proxy could not see the client, as behind rootless Podman's
            port forwarder), the client address is unknown and only per-username throttling
            applies.
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
        docs_base_url: Base address of the documentation site. The footer links to
            ``<base><major.minor>/`` of the running platform version, or ``<base>dev/`` in
            development. Set it to a local mirror for offline installations.
        hub_storage_dir: Hub only: directory of registered raw sources and published packages
            (a mounted volume in compose).
        hub_crs: Hub only: projected CRS of curated features and packages (``EPSG:n``). Sources
            in another CRS are reprojected with PostGIS when they are processed.
        hub_buffer_rule: Hub only: default buffer around an onboarded municipality and of new
            study areas. ``whole_neighbouring_municipalities`` (default, as in the demo
            packages) or ``distance`` (units within ``hub_buffer_distance_m``). The buffer
            definition is open (OQ-28); this is a configurable placeholder, not a method.
        hub_buffer_distance_m: Hub only: distance for the ``distance`` buffer rule, in metres.
        hub_duplicate_distance_m: Hub only: a facility within this distance of another (or with
            the same name in the same municipality) is reported as a likely duplicate.
        hub_max_source_mb: Hub only: largest raw source file accepted by the upload screen.
        hub_max_facility_file_mb: Hub only: largest facility import file.
        hub_max_facility_rows: Hub only: most rows in one facility import file.
        hub_url: Municipal installation only: address of the hub API (for example
            ``https://hub.example.org/api``), set only here, never from the UI (ADR 0014 Part A).
            Empty: no hub connection (submissions are exported as files). With
            ``APP_ENV=production`` it must use ``https`` (``http`` only for localhost).
        hub_token: Municipal installation only: the installation token issued by the hub
            (secret, never logged or shown).
        hub_sync: Municipal installation only: let the worker contact the hub (off for
            offline installations).
        hub_sync_seconds: Municipal installation only: how often the worker syncs with the hub.
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
    trusted_proxies: str = "127.0.0.1/32,::1/128,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"
    diagnostic_step_delay_s: float = Field(default=0.5, ge=0, le=60)
    worker_name: str = "worker"
    worker_poll_s: float = Field(default=1.0, gt=0)
    job_heartbeat_seconds: float = Field(default=10.0, gt=0)
    job_stale_seconds: float = Field(default=120.0, gt=0)
    job_max_runtime_seconds: str = ""
    result_interval_quantiles: str = "0.05,0.95"
    samples_warn_mb: float = Field(default=500.0, gt=0)
    docs_base_url: str = "https://solidaritynode.github.io/snode/"
    hub_storage_dir: Path = Path("var/hub")
    hub_crs: str = Field(default="EPSG:2100", pattern=r"^EPSG:\d{4,6}$")
    hub_buffer_rule: BufferRule = "whole_neighbouring_municipalities"
    hub_buffer_distance_m: float = Field(default=1000.0, gt=0)
    hub_duplicate_distance_m: float = Field(default=25.0, ge=0)
    hub_max_source_mb: float = Field(default=4096.0, gt=0)
    hub_max_facility_file_mb: float = Field(default=5.0, gt=0)
    hub_max_facility_rows: int = Field(default=5000, gt=0)
    hub_url: str = ""
    hub_token: SecretStr = SecretStr("")
    hub_sync: bool = True
    hub_sync_seconds: float = Field(default=300.0, ge=10)

    @property
    def hub_link_enabled(self) -> bool:
        """Whether this municipal installation may contact the hub (URL, token, sync on)."""
        return (
            self.deployment_mode == "municipality"
            and bool(self.hub_url)
            and bool(self.hub_token.get_secret_value())
            and self.hub_sync
        )

    @property
    def hub_srid(self) -> int:
        """Return the EPSG code of :attr:`hub_crs`."""
        return int(self.hub_crs.removeprefix("EPSG:"))

    def docs_url(self, version: str) -> str:
        """Return the user-guide address matching the running platform ``version``.

        ``<docs_base_url><major.minor>/`` (the documentation site publishes one version per
        minor release), or ``<docs_base_url>dev/`` with ``APP_ENV=development``.
        """
        base = self.docs_base_url if self.docs_base_url.endswith("/") else self.docs_base_url + "/"
        if self.app_env == "development":
            return f"{base}dev/"
        major_minor = ".".join(version.split(".")[:2])
        return f"{base}{major_minor}/"

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

    def trusted_networks(self) -> tuple[IPv4Network | IPv6Network, ...]:
        """Return the networks of :attr:`trusted_proxies`."""
        networks: list[IPv4Network | IPv6Network] = []
        for item in self.trusted_proxies.split(","):
            if item.strip():
                try:
                    networks.append(ip_network(item.strip(), strict=False))
                except ValueError:
                    raise ValueError(
                        f"trusted_proxies: {item.strip()!r} is not an address or network"
                    ) from None
        return tuple(networks)

    def placeholder_secrets(self) -> list[str]:
        """Return the names of secrets whose value starts with ``change-me``."""
        found: list[str] = []
        password = make_url(self.database_url.get_secret_value()).password
        if password is not None and str(password).startswith(PLACEHOLDER_PREFIX):
            found.append("database_url (password)")
        return found

    def problems(self) -> list[str]:
        """Return every configuration problem, without secret values (empty: valid).

        Checked together so ``make check-config`` can list them all at once: production needs a
        known, clean code version (ADR 0017) and a Secure session cookie (ADR 0015); outside
        development and test no secret may start with ``change-me``; job timing, interval
        quantiles, runtime limits and trusted proxies must parse.
        """
        found: list[str] = []
        if self.app_env == "production":
            if self.git_commit in ("", "unknown") or self.git_commit.endswith("-dirty"):
                found.append(
                    f"APP_ENV=production needs a known, clean code version, got GIT_COMMIT="
                    f"{self.git_commit!r}: build the images from a committed tree (make up sets "
                    "GIT_COMMIT) so every run records reproducible code (ADR 0017)"
                )
            if not self.session_cookie_secure:
                found.append(
                    "APP_ENV=production needs SOLIDARITYNODE_SESSION_COOKIE_SECURE=true: the "
                    "session cookie must only travel over HTTPS (ADR 0015)"
                )
        if self.app_env not in _ENVS_ALLOWING_PLACEHOLDERS and (
            secrets := self.placeholder_secrets()
        ):
            found.append(
                f"APP_ENV={self.app_env}: placeholder secrets must be replaced before "
                f"starting: {', '.join(secrets)}"
            )
        if self.job_stale_seconds < 2 * self.job_heartbeat_seconds:
            found.append(
                "job_stale_seconds must be at least twice job_heartbeat_seconds, or healthy "
                "jobs would be failed as stale"
            )
        found.extend(self._hub_url_problems())
        for check in (self.max_runtimes, self.interval_quantiles, self.trusted_networks):
            try:
                check()
            except ValueError as exc:
                found.append(str(exc))
        return found

    def _hub_url_problems(self) -> list[str]:
        if not self.hub_url:
            return []
        url = urlsplit(self.hub_url)
        if url.scheme not in ("http", "https") or not url.hostname:
            return ["hub_url: expected an http(s) address such as https://hub.example.org/api"]
        if (
            self.app_env == "production"
            and url.scheme == "http"
            and url.hostname not in ("localhost", "127.0.0.1", "::1")
        ):
            return [
                "APP_ENV=production needs an https SOLIDARITYNODE_HUB_URL (http only for "
                "localhost), so submissions and packages travel encrypted (ADR 0014)"
            ]
        return []

    @model_validator(mode="after")
    def _check(self) -> Self:
        if found := self.problems():
            raise ValueError(PROBLEM_SEPARATOR.join(found))
        return self


@lru_cache
def get_settings() -> Settings:
    """Return the cached process-wide settings."""
    return Settings()

"""Study areas, package assembly and propagation (placeholder, replaced below)."""

from collections.abc import Mapping
from typing import Any

from sqlalchemy import Engine

from solidaritynode_backend.config import Settings
from solidaritynode_backend.jobs import JobContext

PUBLISH_JOB_KIND = "hub_publish"


def run_publish(
    engine: Engine, settings: Settings, ctx: JobContext, payload: Mapping[str, Any]
) -> None:
    """Placeholder."""
    raise NotImplementedError

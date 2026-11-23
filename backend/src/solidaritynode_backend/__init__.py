"""SolidarityNode backend: HTTP API around ``solidaritynode_core``."""

from importlib.metadata import PackageNotFoundError, version

__all__ = ["__version__"]

try:
    __version__ = version("solidaritynode-backend")
except PackageNotFoundError:  # pragma: no cover
    __version__ = "0.0.0"

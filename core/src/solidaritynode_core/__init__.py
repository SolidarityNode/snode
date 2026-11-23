"""SolidarityNode core: spatial probabilistic modelling of social service networks.

The unit of analysis is ``spatial unit × social group × service × time`` (Paper 4 §3). This
package currently contains the typed domain model (:mod:`solidaritynode_core.model`) and
interfaces for every module (Spec 00 §6). No scientific method is implemented yet.
"""

from importlib.metadata import PackageNotFoundError, version

__all__ = ["SUBPACKAGES", "__version__"]

try:
    __version__ = version("solidaritynode-core")
except PackageNotFoundError:  # pragma: no cover - only when running from an uninstalled tree
    __version__ = "0.0.0"

#: Subpackages of the module map (Spec 00 §6).
SUBPACKAGES: tuple[str, ...] = (
    "model",
    "bayes",
    "accessibility",
    "demand",
    "capacity",
    "service_gap",
    "latent_need",
    "scenarios",
    "vulnerability",
    "operations",
    "dynamics",
    "resilience",
    "uncertainty",
    "sensitivity",
    "validation",
)

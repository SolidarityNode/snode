"""Service Gap and its BBN (Paper 1 §8–9). Interfaces only.

The Service Gap is **unmet expressed need** (OQ-8): requests not fulfilled within the maximum
acceptable waiting time (OQ-26). Need never expressed is hidden need (Paper 2), so the two never
overlap. How the deterministic gap relates to the BBN node, and its thresholds, are **open
(OQ-4)**. Supply-related nodes stay explicit in the BBN (Paper 1 §9).
"""

from __future__ import annotations

from typing import Protocol

from solidaritynode_core.bayes import NetworkStructure
from solidaritynode_core.model import IndexedValues

__all__ = ["ServiceGapCalculator", "ServiceGapDiscretiser", "ServiceGapNetworkBuilder"]


class ServiceGapCalculator(Protocol):
    """Deterministic Service Gap ``SG_{i,g,s}`` (Paper 1 §8)."""

    def gap(self, demand: IndexedValues, supply: IndexedValues) -> IndexedValues:
        """Return the gap in service units per period, dims ``(unit, group, service[, sample])``."""
        ...

    def gap_ratio(self, gap: IndexedValues, demand: IndexedValues) -> IndexedValues:
        """Return ``SG / D`` (dimensionless), same dimensions as ``gap``."""
        ...


class ServiceGapDiscretiser(Protocol):
    """Map the gap ratio to Low / Medium / High (Paper 1 §8; thresholds **OQ-4, OQ-7 open**)."""

    def discretise(self, gap_ratio: IndexedValues) -> IndexedValues:
        """Return states as :class:`~solidaritynode_core.model.LevelLMH` values, same dims."""
        ...


class ServiceGapNetworkBuilder(Protocol):
    """Build the Paper 1 §9 BBN.

    Structure: Population group → Demand; Accessibility; Infrastructure → Physical capacity →
    Functional capacity → Effective supply → Service Gap. CPTs from expert elicitation,
    literature and deterministic relations. Relation to the formula: **OQ-4 (open)**.
    """

    def build(self) -> NetworkStructure:
        """Return the network structure with its CPTs."""
        ...

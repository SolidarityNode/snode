"""Estimated demand (Paper 1 §6). Interfaces only.

Paper 1 demand is **visible use under average conditions**, not need (OQ-8, AGENTS.md
invariant 4). It is labelled *Estimated*, never *Observed*, and measured in service units per
reference period (OQ-24, OQ-25).
"""

from __future__ import annotations

from typing import Protocol

from solidaritynode_core.model import IndexedValues

__all__ = ["DemandEstimator"]


class DemandEstimator(Protocol):
    """Estimate ``D_{i,g,s}`` (Paper 1 §6; Spec 00 §4.1; OQ-8, OQ-24)."""

    def people_making_requests(
        self, population: IndexedValues, demand_rate: IndexedValues
    ) -> IndexedValues:
        """Return people making requests under average conditions.

        Args:
            population: Persons, dims ``(unit, group)``.
            demand_rate: Visible-use share in ``[0, 1]``, dims ``(group, service)``, optionally
                with ``sample`` (Monte Carlo).

        Returns:
            Persons, dims ``(unit, group, service[, sample])``. Not people with need (OQ-8).
        """
        ...

    def estimated_demand(
        self, people_making_requests: IndexedValues, intensity: IndexedValues
    ) -> IndexedValues:
        """Return estimated demand in service units per reference period.

        Args:
            people_making_requests: Persons, dims ``(unit, group, service[, sample])``.
            intensity: ``k_{g,s}``, service units per person per period (OQ-24).

        Returns:
            Service units, dims ``(unit, group, service[, sample])``.
        """
        ...

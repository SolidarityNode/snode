"""Accessibility: travel times, access weights, group- and mode-specific accessibility.

Implements (later) Paper 1 §5 and the disrupted network of Paper 3 §7–10. Interfaces only.
Open: access weight form ``w(T)`` (OQ-3), combination of transport modes (OQ-5), network
data sources (ADR 0009).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from solidaritynode_core.model import (
    Facility,
    IndexedValues,
    PopulationGroup,
    Scenario,
    SpatialUnit,
    TransportMode,
)

__all__ = ["AccessWeight", "AccessibilityModel", "TravelTimeModel"]


class TravelTimeModel(Protocol):
    """Compute travel times ``T_if^{g,m}`` (Paper 1 §5; OQ-1 notation).

    Implementations hold the per-mode networks (road, pedestrian, public transport) and the
    DEM (Spec 00 §3).
    """

    def travel_times(
        self,
        units: Sequence[SpatialUnit],
        facilities: Sequence[Facility],
        groups: Sequence[PopulationGroup],
        modes: Sequence[TransportMode],
        scenario: Scenario | None = None,
    ) -> IndexedValues:
        """Return travel times from each unit to each facility.

        Args:
            units: Origins ``i``.
            facilities: Destinations ``f``.
            groups: Groups ``g`` (travel speed may depend on the mobility profile).
            modes: Modes ``m``.
            scenario: If given, use the disrupted network ``Network^D`` (Paper 3 §7–10).

        Returns:
            Minutes, dims ``(unit, facility, group, mode)``; unreachable pairs as ``inf``.
        """
        ...


class AccessWeight(Protocol):
    """Access weight ``w(T)`` converting time to a weight (Paper 1 §5; **OQ-3 open**).

    Functional form, decay parameters, cut-offs and their dependence on group and mode are
    not specified.
    """

    def weight(self, travel_times: IndexedValues) -> IndexedValues:
        """Return weights with the same dimensions as ``travel_times`` (dimensionless)."""
        ...


class AccessibilityModel(Protocol):
    """Group- and mode-specific accessibility ``Accessibility_i^{g,m}`` (Paper 1 §5).

    How modes combine for a group (mode shares, best mode, weighting) is **OQ-5 (open)**.
    """

    def accessibility(self, weights: IndexedValues) -> IndexedValues:
        """Return accessibility per unit, group and mode.

        Args:
            weights: ``w(T_if^{g,m})``, dims ``(unit, facility, group, mode)``.

        Returns:
            Dims ``(unit, group, mode)``; units of measure depend on OQ-3.
        """
        ...

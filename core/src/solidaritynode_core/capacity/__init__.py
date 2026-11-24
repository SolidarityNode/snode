"""Physical, functional and effective capacity, and supply (Paper 1 §7). Interfaces only.

Allocation is **2SFCA** (OQ-2, decided): each facility's functional capacity is shared among
the units and groups that reach it, in proportion to access-weighted demand; shares sum to the
facility's capacity. Allocation sits behind :class:`CapacityAllocator` so that alternatives
(3SFCA, N-2a; constrained allocation for sensitivity only, N-2b) can be added without changing
callers (Spec 00 §5).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from solidaritynode_core.model import Facility, IndexedValues, Service

__all__ = ["CapacityAllocator", "FunctionalCapacityModel"]


class FunctionalCapacityModel(Protocol):
    """Physical and functional capacity (Paper 1 §7; Spec 00 §4.1)."""

    def physical_capacity(
        self, facilities: Sequence[Facility], services: Sequence[Service]
    ) -> IndexedValues:
        """Return ``C_f^physical`` in service units per period, dims ``(facility, service)``."""
        ...

    def functional_capacity(
        self, physical_capacity: IndexedValues, availability: IndexedValues
    ) -> IndexedValues:
        """Return ``C_f^functional`` from physical capacity and availability.

        Args:
            physical_capacity: Dims ``(facility, service[, sample])``.
            availability: Dims ``(facility[, sample])``, shares in ``[0, 1]``.

        Returns:
            Service units per period, dims ``(facility, service[, sample])``.
        """
        ...


class CapacityAllocator(Protocol):
    """Allocate facility capacity to units and groups (Paper 1 §7; OQ-2 decided: 2SFCA).

    Baseline implementation: 2SFCA. N-2a (3SFCA) and N-2b (constrained allocation, sensitivity
    only) are future alternatives. Allocation never redistributes demand after a capacity loss
    (Paper 3 excludes adaptive redistribution; OQ-2 rationale).
    """

    def allocate(
        self,
        functional_capacity: IndexedValues,
        demand: IndexedValues,
        access_weights: IndexedValues,
    ) -> IndexedValues:
        """Return effective capacity shares.

        Args:
            functional_capacity: Dims ``(facility, service[, sample])``.
            demand: Demand or need to weight by, dims ``(unit, group, service[, sample])``.
            access_weights: ``w(T)`` per unit, facility and group (mode combination: OQ-5).

        Returns:
            Service units, dims ``(facility, unit, group, service[, sample])``; for each
            facility and service the shares sum to its functional capacity.
        """
        ...

    def supply(self, allocation: IndexedValues) -> IndexedValues:
        """Return supply ``S_{i,g,s}``: shares received from all facilities.

        Returns:
            Service units, dims ``(unit, group, service[, sample])``.
        """
        ...

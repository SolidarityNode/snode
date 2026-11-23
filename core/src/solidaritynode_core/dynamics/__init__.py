"""Territorial state, expected and observed consequence, and the DBN (Paper 4 §6–9, §12).

Interfaces only. Decided (OQ-16): Expected Consequence is the Paper 3 vulnerability relationship
evaluated at **observed** ``GE(t)``, ``SL(t)`` and ``SS``; the disruption enters once. Operational
support and resource mobilisation are a **system response**, not a resilience measure
(CLAUDE.md invariant 7).

Open: DBN topology, time slice and state derivation (OQ-17); observed consequence and the
measurement node ``P(ObservedConsequence | V)`` (OQ-18); resource mobilisation parameters
(OQ-20); reference period and time step (OQ-25).
"""

from __future__ import annotations

from typing import Protocol

from solidaritynode_core.bayes import ConditionalProbabilityTable, NetworkStructure
from solidaritynode_core.model import IndexedValues

__all__ = [
    "DynamicNetworkBuilder",
    "ExpectedConsequenceModel",
    "ObservedConsequenceModel",
    "ObservedExposureLossModel",
    "ResponseModel",
    "TerritorialStateModel",
]


class TerritorialStateModel(Protocol):
    """Territorial (unit-level) coverage and functional state (Paper 4 §7).

    Combines facility coverages and network redundancy. A degraded facility does not imply
    lost coverage for a unit if alternatives exist (CLAUDE.md invariant 3).
    """

    def territorial_state(
        self, facility_state: IndexedValues, allocation: IndexedValues
    ) -> IndexedValues:
        """Return coverage and state per unit and service.

        Returns:
            Dims ``(unit, service, time[, state])``.
        """
        ...


class ObservedExposureLossModel(Protocol):
    """Observed ``GE(t)`` and ``SL(t)`` from territorial state and tickets (Paper 4 §8).

    Same definitions as Paper 3 (OQ-12, OQ-16).
    """

    def observed_exposure(self, territorial_state: IndexedValues) -> IndexedValues:
        """Return ``GE(t)``, dims ``(unit, group, time)``."""
        ...

    def observed_service_loss(
        self, territorial_state: IndexedValues, total_need: IndexedValues
    ) -> IndexedValues:
        """Return ``SL(t)``, dims ``(unit, group, service, time)``."""
        ...


class ExpectedConsequenceModel(Protocol):
    """Expected group consequence (Paper 4 §8; OQ-16)."""

    def expected_consequence(
        self,
        relationship: ConditionalProbabilityTable,
        observed_exposure: IndexedValues,
        observed_service_loss: IndexedValues,
        susceptibility: IndexedValues,
    ) -> IndexedValues:
        """Return ``P(V = l)`` at observed conditions.

        Returns:
            Dims ``(unit, group, service, time, state)``.
        """
        ...


class ObservedConsequenceModel(Protocol):
    """Observed group consequence from tickets (Paper 4 §9; **OQ-18 open**).

    Includes the measurement node ``P(ObservedConsequence | V)``. Tickets observe expressed
    demand, not hidden need.
    """

    def observed_consequence(self, indicators: IndexedValues) -> IndexedValues:
        """Return observed consequence, dims ``(unit, group, service, time)``."""
        ...

    def measurement_model(self) -> ConditionalProbabilityTable:
        """Return ``P(ObservedConsequence | V)``."""
        ...


class ResponseModel(Protocol):
    """Need for support and resource mobilisation (Paper 4 §6; **OQ-20 open**).

    A system response (CLAUDE.md invariant 7). Volunteer resources are approved and
    controlled.
    """

    def support_need(self, facility_state: IndexedValues) -> IndexedValues:
        """Return resource need by type, dims ``(facility, time)`` plus a resource-type axis."""
        ...


class DynamicNetworkBuilder(Protocol):
    """The DBN of Paper 4 §12 (**OQ-17 open**).

    ``State(t−1) → FunctionalState(t) → ObservedConsequence(t) → Response(t) → Recovery(t) →
    State(t+1)``, in parallel with observed ``GE(t)``, ``SL(t)``, ``SS`` → vulnerability
    relationship → Expected Consequence (OQ-16).
    """

    def build(self) -> NetworkStructure:
        """Return the two-slice (or other, OQ-17) network structure."""
        ...

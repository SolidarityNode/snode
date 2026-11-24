"""Counterfactual and disruption scenarios (Paper 1 §13; Paper 3 §7–10). Interfaces only.

One shared engine serves controlled interventions (Paper 1 §13, for example capacity +20 %) and
disruption scenarios (Paper 3 §7–10), as stated in Spec 00 §5. Disruption severities
``DS_{f,c}`` are scenario parameters, not BN nodes. Construction of the standardised reference
scenarios (minor, moderate, severe; OQ-16) is not defined.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from solidaritynode_core.model import (
    IndexedValues,
    ReferenceScenarioLevel,
    Scenario,
)

__all__ = ["ReferenceScenarioFactory", "ScenarioEngine"]


class ScenarioEngine(Protocol):
    """Apply scenarios to the baseline inputs (Spec 00 §5)."""

    def disrupted_capacity(
        self, functional_capacity: IndexedValues, scenarios: Sequence[Scenario]
    ) -> IndexedValues:
        """Return ``C^D_f`` per scenario (Paper 3 §7–10).

        Args:
            functional_capacity: Dims ``(facility, service[, sample])``.
            scenarios: Scenarios ``c``.

        Returns:
            Service units per period, dims ``(facility, service, scenario[, sample])``.
        """
        ...


class ReferenceScenarioFactory(Protocol):
    """Build standardised reference scenarios for vulnerability maps (OQ-16 decided).

    Which facilities and severities define each level is not specified.
    """

    def build(self, level: ReferenceScenarioLevel) -> Scenario:
        """Return the reference scenario for ``level``."""
        ...

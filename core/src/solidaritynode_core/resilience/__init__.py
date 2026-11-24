"""Bayesian update of the vulnerability relationship, trajectories and resilience.

Paper 4 §10–13. Interfaces only. Resilience is a dynamic property derived from the
loss-and-recovery trajectory; it is **not** vulnerability and never just the inverse of
recovery time (CLAUDE.md invariant 2).

Decided (OQ-16): the update learns the **parameters** of the vulnerability relationship with the
expert CPT as prior. Open: prior weight (OQ-27), how trajectory indicators combine into
``P(Resilience)`` and the baseline reference level (OQ-19).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from enum import StrEnum
from typing import Protocol

from solidaritynode_core.bayes import ConditionalProbabilityTable, ObservationTable, PriorStrength
from solidaritynode_core.model import DiscreteDistribution, RecoveryTrajectory, Uncertain

__all__ = [
    "ResilienceEstimator",
    "TrajectoryIndicator",
    "TrajectoryIndicatorCalculator",
    "VulnerabilityUpdater",
]


class TrajectoryIndicator(StrEnum):
    """Trajectory indicators named in Paper 4 §13. Selection and weighting: OQ-19."""

    MAXIMUM_LOSS = "maximum_loss"
    RECOVERY_TIME = "recovery_time"
    RECOVERY_RATE = "recovery_rate"
    CUMULATIVE_IMPACT = "cumulative_impact"  # area under the loss curve
    FINAL_RESTORATION = "final_restoration"


class VulnerabilityUpdater(Protocol):
    """Learn the vulnerability relationship from observed disruptions (Paper 4 §10; OQ-16).

    Prior weight and dependence between observations of the same disruption: **OQ-27 (open)**.
    """

    def update(
        self,
        prior: ConditionalProbabilityTable,
        observations: ObservationTable,
        strength: PriorStrength,
    ) -> ConditionalProbabilityTable:
        """Return the updated relationship (same variables as ``prior``)."""
        ...


class TrajectoryIndicatorCalculator(Protocol):
    """Compute trajectory indicators (Paper 4 §13)."""

    def indicators(self, trajectory: RecoveryTrajectory) -> Mapping[TrajectoryIndicator, Uncertain]:
        """Return the indicators of one trajectory."""
        ...


class ResilienceEstimator(Protocol):
    """``P(Resilience_{i,g,s} | trajectory)`` (Paper 4 §13; **OQ-19 open**)."""

    def resilience(
        self, trajectories: Sequence[RecoveryTrajectory]
    ) -> Mapping[tuple[str, str, str], DiscreteDistribution]:
        """Return a distribution over resilience states per ``(unit, group, service)``."""
        ...

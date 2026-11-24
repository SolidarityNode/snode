"""Recovery trajectories (Paper 4 §11–13; Spec 00 §3, §4.4; OQ-12, OQ-19).

A trajectory is the time series of service loss or of observed group consequence for one
``(unit, group, service)``. ``ServiceLoss(t)`` uses the Paper 3 definition (loss relative to
pre-event performance, OQ-12), so it starts at zero and returns to zero on full recovery.
How trajectories become ``P(Resilience)`` is open (OQ-19).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from solidaritynode_core.model.ids import GroupId, ServiceId, UnitId

__all__ = ["RecoveryTrajectory", "TrajectoryKind"]


class TrajectoryKind(StrEnum):
    """What a trajectory measures (Paper 4 §11)."""

    SERVICE_LOSS = "service_loss"
    OBSERVED_CONSEQUENCE = "observed_consequence"


@dataclass(frozen=True, slots=True)
class RecoveryTrajectory:
    """Time series of loss or consequence for one unit, group and service (Paper 4 §11).

    Attributes:
        unit: Spatial unit ``i``.
        group: Group ``g``.
        service: Service ``s``.
        kind: Quantity measured.
        times: Strictly increasing, timezone-aware observation times ``t``.
        values: Finite values, one per time. For ``SERVICE_LOSS`` these are shares in ``[0, 1]``
            (Paper 3 §15, OQ-12).
    """

    unit: UnitId
    group: GroupId
    service: ServiceId
    kind: TrajectoryKind
    times: tuple[datetime, ...]
    values: tuple[float, ...]

    def __post_init__(self) -> None:
        """Validate alignment, ordering, finiteness and bounds."""
        if len(self.times) != len(self.values):
            raise ValueError("times and values must have the same length")
        if not self.times:
            raise ValueError("a trajectory needs at least one point")
        for when in self.times:
            if when.tzinfo is None or when.utcoffset() is None:
                raise ValueError("trajectory times must be timezone-aware")
        if any(b <= a for a, b in zip(self.times, self.times[1:], strict=False)):
            raise ValueError("trajectory times must be strictly increasing")
        if not all(math.isfinite(v) for v in self.values):
            raise ValueError("trajectory values must be finite")
        if self.kind is TrajectoryKind.SERVICE_LOSS and not all(
            0.0 <= v <= 1.0 for v in self.values
        ):
            raise ValueError("service loss values must be in [0, 1] (OQ-12)")

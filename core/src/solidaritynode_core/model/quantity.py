"""Service-unit quantities (OQ-24 decided, OQ-25 open).

Need, capacity, supply, gap and loss are measured in **service units per reference period**
(visits, appointments or hours, defined per service). Quantities of different services are
never summed (OQ-24), and quantities over different reference periods are never mixed (OQ-25).
:class:`ServiceQuantity` enforces both at runtime: adding or subtracting quantities whose
service, unit or reference period differ raises :class:`UnitMismatchError`.

The reference period itself is **open** (OQ-25): it is a label configured per run, not a
constant in code.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from enum import StrEnum

from solidaritynode_core.model.ids import ServiceId

__all__ = ["ReferencePeriod", "ServiceQuantity", "ServiceUnit", "UnitMismatchError"]


class UnitMismatchError(TypeError):
    """Raised when quantities of different services, units or periods are combined (OQ-24)."""


class ServiceUnit(StrEnum):
    """Unit in which a service is delivered and need is measured (Spec 00 §2, OQ-24)."""

    VISIT = "visit"
    APPOINTMENT = "appointment"
    HOUR = "hour"


_ISO_DURATION = re.compile(r"^P(?!$)(\d+Y)?(\d+M)?(\d+W)?(\d+D)?$")


@dataclass(frozen=True, slots=True)
class ReferencePeriod:
    """Reference period over which need and capacity are measured (OQ-25, open).

    Attributes:
        iso_duration: ISO 8601 calendar duration such as ``"P1W"`` or ``"P1M"``. Which period
            to use is OQ-25 and is set in configuration; it relates to the DBN time step
            (OQ-17).
    """

    iso_duration: str

    def __post_init__(self) -> None:
        """Validate the ISO 8601 duration syntax (date part only)."""
        if not _ISO_DURATION.match(self.iso_duration):
            raise ValueError(f"not an ISO 8601 date duration: {self.iso_duration!r}")


@dataclass(frozen=True, slots=True)
class ServiceQuantity:
    """An amount of one service in its service unit per reference period (OQ-24, OQ-25).

    Attributes:
        magnitude: Amount in ``unit`` per ``period``. Finite. Sign is not restricted, because
            differences (for example ``ΔPUN``, Paper 3 §14–15, OQ-12) are also quantities.
        service: Service the amount refers to.
        unit: Service unit (must match the service definition; checked by callers that hold
            the :class:`~solidaritynode_core.model.entities.Service`).
        period: Reference period.
    """

    magnitude: float
    service: ServiceId
    unit: ServiceUnit
    period: ReferencePeriod

    def __post_init__(self) -> None:
        """Validate that the magnitude is finite."""
        if not math.isfinite(self.magnitude):
            raise ValueError("ServiceQuantity magnitude must be finite")

    def _check_compatible(self, other: object) -> ServiceQuantity:
        if not isinstance(other, ServiceQuantity):
            raise UnitMismatchError(f"cannot combine ServiceQuantity with {type(other).__name__}")
        if (self.service, self.unit, self.period) != (other.service, other.unit, other.period):
            raise UnitMismatchError(
                "cannot combine quantities of different services, units or reference periods "
                f"({self.service}/{self.unit}/{self.period.iso_duration} vs "
                f"{other.service}/{other.unit}/{other.period.iso_duration}); see OQ-24, OQ-25"
            )
        return other

    def __add__(self, other: object) -> ServiceQuantity:
        """Add two quantities of the same service, unit and period."""
        checked = self._check_compatible(other)
        return ServiceQuantity(
            self.magnitude + checked.magnitude, self.service, self.unit, self.period
        )

    def __sub__(self, other: object) -> ServiceQuantity:
        """Subtract two quantities of the same service, unit and period."""
        checked = self._check_compatible(other)
        return ServiceQuantity(
            self.magnitude - checked.magnitude, self.service, self.unit, self.period
        )

    def scaled(self, factor: float) -> ServiceQuantity:
        """Return the quantity multiplied by a dimensionless factor."""
        return ServiceQuantity(self.magnitude * factor, self.service, self.unit, self.period)

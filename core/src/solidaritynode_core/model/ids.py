"""Typed identifiers for domain entities (Spec 00 §3).

Identifiers are opaque strings. They must never encode personal data (CLAUDE.md, "Data and
privacy rules").
"""

from __future__ import annotations

from typing import NewType

__all__ = ["FacilityId", "GroupId", "ScenarioId", "ServiceId", "UnitId"]

#: Spatial unit ``i`` (first application: Local Community, Greek ΤΚ; OQ-22 terminology open).
UnitId = NewType("UnitId", str)
#: Facility ``f``.
FacilityId = NewType("FacilityId", str)
#: Population group ``g``.
GroupId = NewType("GroupId", str)
#: Service ``s``.
ServiceId = NewType("ServiceId", str)
#: Scenario ``c``.
ScenarioId = NewType("ScenarioId", str)

"""Model registry: models a run can execute, with id, version and a pure run function.

Spec 00 §3 (Run): a run records the **model and parameter version**. A registered model is a
pure function ``(study area, scenario, config, seed) -> ModelResult``; randomness comes only from
the ``seed`` (AGENTS.md). Bump the version whenever outputs can change.

Only the diagnostic model ``diagnostic-v0`` is registered
(:mod:`solidaritynode_core.validation.diagnostic`). It proves the pipeline and is **not a
research result**: no scientific method of Papers 1–4 is implemented yet.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

import numpy as np
import numpy.typing as npt

from solidaritynode_core.model.ids import GroupId, ServiceId, UnitId
from solidaritynode_core.model.study_area import StudyArea

__all__ = [
    "STATIC_TIME",
    "CellSamples",
    "IndicatorSpec",
    "ModelFn",
    "ModelRegistry",
    "ModelResult",
    "ModelSpec",
    "ProgressFn",
    "ResultCell",
    "get_registry",
]

STATIC_TIME = "static"
"""Time label of results that do not vary in time (unit of analysis keeps the time dimension)."""


@dataclass(frozen=True, slots=True)
class IndicatorSpec:
    """Description of one output indicator.

    Attributes:
        id: Indicator id (for example ``diagnostic_noise``).
        label: Human-readable label.
        unit: Unit of measure (for example ``min`` or ``count``).
        deterministic: ``True`` when the value carries no uncertainty (interval equals value).
        group_dependent: ``False`` when the value is the same for every group (it is still
            reported per group to keep the unit of analysis, AGENTS.md invariant 1).
    """

    id: str
    label: str
    unit: str
    deterministic: bool
    group_dependent: bool


@dataclass(frozen=True, slots=True)
class ResultCell:
    """Summary value of one indicator for ``unit × group × service × time``.

    Attributes:
        unit: Spatial unit (core units only).
        group: Population group.
        service: Service.
        time: Time label (:data:`STATIC_TIME` for static results).
        indicator: Indicator id.
        value: Central value (mean of samples, or the deterministic value); ``None`` when not
            computable (for example no reachable facility).
        low: Lower bound of the interval (5th percentile for sampled indicators).
        high: Upper bound of the interval (95th percentile for sampled indicators).
        baseline: Value without the scenario, when the model computes it in the same run.
    """

    unit: UnitId
    group: GroupId
    service: ServiceId
    time: str
    indicator: str
    value: float | None
    low: float | None
    high: float | None
    baseline: float | None = None


@dataclass(frozen=True, slots=True, eq=False)
class CellSamples:
    """Monte Carlo samples of one indicator for one cell (stored by the caller, ADR 0008).

    Attributes:
        unit: Spatial unit.
        group: Population group.
        service: Service.
        time: Time label.
        indicator: Indicator id.
        values: One-dimensional array of draws.
    """

    unit: UnitId
    group: GroupId
    service: ServiceId
    time: str
    indicator: str
    values: npt.NDArray[np.float64]


@dataclass(frozen=True, slots=True)
class ModelResult:
    """Everything a model returns for one run.

    Attributes:
        model_id: Id of the model that produced the result.
        model_version: Version of that model.
        indicators: Description of every indicator in ``cells``.
        cells: Summary values per ``unit × group × service × time`` (core units only).
        samples: Per-sample values (may be empty).
        tables: Model-specific tables as rows of JSON-compatible values.
        diagnostics: JSON-compatible checks and messages.
    """

    model_id: str
    model_version: str
    indicators: tuple[IndicatorSpec, ...]
    cells: tuple[ResultCell, ...]
    samples: tuple[CellSamples, ...] = ()
    tables: Mapping[str, tuple[Mapping[str, Any], ...]] = field(default_factory=dict)
    diagnostics: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Check that every cell uses a described indicator."""
        known = {i.id for i in self.indicators}
        if unknown := {c.indicator for c in self.cells} - known:
            raise ValueError(f"cells use undescribed indicators: {sorted(unknown)}")
        object.__setattr__(self, "tables", MappingProxyType(dict(self.tables)))
        object.__setattr__(self, "diagnostics", MappingProxyType(dict(self.diagnostics)))


type ProgressFn = Callable[[float], None]
"""Called with the completed fraction in ``[0, 1]``. May raise to cancel the run."""

type ModelFn = Callable[[StudyArea, Any, Mapping[str, Any], int, ProgressFn], ModelResult]
"""``(study area, scenario, config, seed, progress) -> result``. Must be pure and seeded."""


@dataclass(frozen=True, slots=True)
class ModelSpec:
    """A registered model.

    Attributes:
        id: Model id recorded on every run (for example ``diagnostic-v0``).
        version: Semantic version; bump whenever outputs can change.
        description: One-line description.
        diagnostic: ``True`` for models that prove mechanics only and must never be read as
            research results.
        default_config: Configuration used when a run gives none.
        run: The model function.
    """

    id: str
    version: str
    description: str
    diagnostic: bool
    default_config: Mapping[str, Any]
    run: ModelFn


class ModelRegistry:
    """Models available to runs, by id (Spec 00 §3, Run)."""

    def __init__(self) -> None:
        """Create an empty registry."""
        self._models: dict[str, ModelSpec] = {}

    def register(self, spec: ModelSpec) -> None:
        """Add a model.

        Raises:
            ValueError: If a model with the same id is already registered.
        """
        if spec.id in self._models:
            raise ValueError(f"model {spec.id!r} already registered")
        self._models[spec.id] = spec

    def get(self, model_id: str) -> ModelSpec:
        """Return the model with ``model_id``.

        Raises:
            KeyError: If no such model is registered.
        """
        try:
            return self._models[model_id]
        except KeyError:
            raise KeyError(f"unknown model {model_id!r}") from None

    def ids(self) -> tuple[str, ...]:
        """Return the registered model ids, sorted."""
        return tuple(sorted(self._models))


_REGISTRY: ModelRegistry | None = None


def get_registry() -> ModelRegistry:
    """Return the process-wide registry with the built-in models (only ``diagnostic-v0``)."""
    global _REGISTRY
    if _REGISTRY is None:
        from solidaritynode_core.validation.diagnostic import DIAGNOSTIC_V0

        registry = ModelRegistry()
        registry.register(DIAGNOSTIC_V0)
        _REGISTRY = registry
    return _REGISTRY

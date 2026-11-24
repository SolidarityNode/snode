"""Value types: indexed container, ordinal states, uncertain and service-unit quantities."""

from __future__ import annotations

from datetime import timedelta

import numpy as np
import pytest

from solidaritynode_core.model import (
    UNIT_OF_ANALYSIS,
    Dim,
    DimensionMismatchError,
    DiscreteDistribution,
    IndexedValues,
    LevelLMH,
    PointValue,
    RecoveryTrajectory,
    ReferencePeriod,
    Samples,
    ServiceId,
    ServiceQuantity,
    ServiceUnit,
    TrajectoryKind,
    UnitMismatchError,
)
from tests.fixtures import synthetic

# --- IndexedValues ------------------------------------------------------------------------


def _full() -> IndexedValues:
    coords = {
        Dim.UNIT: list(synthetic.UNITS),
        Dim.GROUP: list(synthetic.GROUPS),
        Dim.SERVICE: list(synthetic.SERVICES),
        Dim.TIME: ["2030-01", "2030-02", "2030-03"],
    }
    return IndexedValues(np.arange(24.0).reshape(2, 2, 2, 3), coords, name="demo")


def test_unit_of_analysis_dimensions() -> None:
    assert UNIT_OF_ANALYSIS == (Dim.UNIT, Dim.GROUP, Dim.SERVICE, Dim.TIME)
    assert _full().dims == UNIT_OF_ANALYSIS
    assert [d.symbol for d in UNIT_OF_ANALYSIS] == ["i", "g", "s", "t"]


def test_absent_dimensions_are_supported() -> None:
    ss = IndexedValues(
        np.zeros((2, 2, 2)),
        {Dim.UNIT: synthetic.UNITS, Dim.GROUP: synthetic.GROUPS, Dim.SERVICE: synthetic.SERVICES},
        name="social_susceptibility",
    )
    assert not ss.has(Dim.TIME)
    with pytest.raises(KeyError):
        ss.labels(Dim.TIME)


def test_shape_must_match_coordinates() -> None:
    with pytest.raises(ValueError, match="shape"):
        IndexedValues(
            np.zeros((3, 2)), {Dim.UNIT: synthetic.UNITS, Dim.GROUP: synthetic.GROUPS}, name="x"
        )


def test_labels_must_be_unique() -> None:
    with pytest.raises(ValueError, match="unique"):
        IndexedValues(np.zeros(2), {Dim.UNIT: ["U", "U"]}, name="x")


def test_unknown_dimension_rejected() -> None:
    with pytest.raises(ValueError, match="not a valid"):
        IndexedValues(np.zeros(2), {"region": ["a", "b"]}, name="x")  # type: ignore[dict-item]


def test_alignment_check() -> None:
    a = _full()
    b = IndexedValues(np.zeros(2), {Dim.UNIT: list(synthetic.UNITS)}, name="b")
    a.check_aligned(b)
    c = IndexedValues(np.zeros(2), {Dim.UNIT: list(reversed(synthetic.UNITS))}, name="c")
    with pytest.raises(DimensionMismatchError):
        a.check_aligned(c)


def test_values_are_read_only_and_container_immutable() -> None:
    values = _full()
    with pytest.raises(ValueError, match="read-only"):
        values.to_numpy()[0, 0, 0, 0] = 1.0
    with pytest.raises(AttributeError):
        values.foo = 1  # type: ignore[attr-defined]


def test_never_sum_services_or_groups() -> None:
    values = _full()
    with pytest.raises(ValueError, match="OQ-24"):
        values.sum_over(Dim.SERVICE)
    with pytest.raises(ValueError, match="OQ-6"):
        values.sum_over(Dim.GROUP)
    assert values.sum_over(Dim.TIME).dims == (Dim.UNIT, Dim.GROUP, Dim.SERVICE)


def test_selection_drops_dimension() -> None:
    sub = _full().sel(unit="U-A", time="2030-01")
    assert sub.dims == (Dim.GROUP, Dim.SERVICE)


# --- Ordinal states -----------------------------------------------------------------------


def test_lmh_order_and_labels() -> None:
    assert LevelLMH.LOW < LevelLMH.MEDIUM < LevelLMH.HIGH
    assert LevelLMH.labels() == ("Low", "Medium", "High")
    assert LevelLMH.from_label("high") is LevelLMH.HIGH
    with pytest.raises(ValueError, match="unknown"):
        LevelLMH.from_label("Very High")  # removed by OQ-15


# --- Uncertain ----------------------------------------------------------------------------


def test_discrete_distribution_validates() -> None:
    dist = DiscreteDistribution({"Low": 0.2, "Medium": 0.3, "High": 0.5})
    assert dist.states == ("Low", "Medium", "High")
    with pytest.raises(ValueError, match="sum"):
        DiscreteDistribution({"Low": 0.2, "High": 0.2})
    with pytest.raises(ValueError, match=r"\[0, 1\]"):
        DiscreteDistribution({"Low": -0.1, "High": 1.1})


def test_samples_and_point() -> None:
    samples = Samples(np.array([1.0, 2.0]))
    assert samples.size == 2
    with pytest.raises(ValueError, match="read-only"):
        samples.values[0] = 3.0
    with pytest.raises(ValueError, match="non-empty"):
        Samples(np.array([]))
    with pytest.raises(ValueError, match="finite"):
        PointValue(float("nan"))


# --- Service quantities (OQ-24, OQ-25) ----------------------------------------------------

MONTH = ReferencePeriod("P1M")


def _q(
    value: float, service: str = "S-homecare", period: ReferencePeriod = MONTH
) -> ServiceQuantity:
    return ServiceQuantity(value, ServiceId(service), ServiceUnit.VISIT, period)


def test_same_service_quantities_add() -> None:
    assert (_q(2.0) + _q(3.0)).magnitude == 5.0
    assert (_q(2.0) - _q(3.0)).magnitude == -1.0
    assert _q(2.0).scaled(0.5).magnitude == 1.0


def test_different_services_or_periods_never_mix() -> None:
    with pytest.raises(UnitMismatchError, match="OQ-24"):
        _ = _q(1.0) + _q(1.0, service="S-clinic")
    with pytest.raises(UnitMismatchError):
        _ = _q(1.0) - _q(1.0, period=ReferencePeriod("P1W"))
    with pytest.raises(UnitMismatchError):
        _ = _q(1.0) + 1.0


def test_reference_period_syntax() -> None:
    with pytest.raises(ValueError, match="ISO 8601"):
        ReferencePeriod("monthly")


# --- Trajectories ------------------------------------------------------------------------


def test_trajectory_invariants() -> None:
    times = (synthetic.T0, synthetic.T0 + timedelta(days=1))
    ok = RecoveryTrajectory(
        *synthetic.UNITS[:1],
        synthetic.GROUPS[0],
        synthetic.SERVICES[0],
        TrajectoryKind.SERVICE_LOSS,
        times,
        (0.0, 0.2),
    )
    assert len(ok.values) == 2
    with pytest.raises(ValueError, match="increasing"):
        RecoveryTrajectory(
            synthetic.UNITS[0],
            synthetic.GROUPS[0],
            synthetic.SERVICES[0],
            TrajectoryKind.SERVICE_LOSS,
            times[::-1],
            (0.0, 0.2),
        )
    with pytest.raises(ValueError, match="OQ-12"):
        RecoveryTrajectory(
            synthetic.UNITS[0],
            synthetic.GROUPS[0],
            synthetic.SERVICES[0],
            TrajectoryKind.SERVICE_LOSS,
            times,
            (0.0, 1.2),
        )

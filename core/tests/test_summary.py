"""Summary statistics of samples and totals from samples (Spec 00 §5; ADR 0017)."""

from __future__ import annotations

import numpy as np
import pytest

from solidaritynode_core.model import (
    CellSamples,
    GroupId,
    IndicatorSpec,
    ModelResult,
    ResultCell,
    ServiceId,
    UnitId,
)
from solidaritynode_core.model.registry import STATIC_TIME
from solidaritynode_core.uncertainty import (
    DEFAULT_INTERVAL,
    check_interval,
    summarise,
    summarise_result,
    summarise_total,
)
from solidaritynode_core.validation import run_diagnostic
from tests.fixtures import packages


def test_summarise_known_answers() -> None:
    s = summarise([1.0, 2.0, 3.0, 4.0, 100.0])
    assert s.mean == pytest.approx(22.0)
    assert s.median == 3.0
    assert s.low == pytest.approx(1.2)  # linear interpolation at the 5th percentile
    assert s.high == pytest.approx(80.8)
    assert s.interval == DEFAULT_INTERVAL
    assert s.n_samples == 5
    wide = summarise(np.arange(101.0), (0.25, 0.75))
    assert (wide.low, wide.median, wide.high) == (25.0, 50.0, 75.0)


def test_interval_levels_are_checked() -> None:
    assert check_interval([0.1, 0.9]) == (0.1, 0.9)
    for bad in ([0.5, 0.9], [0.1, 0.4], [0.0, 0.95], [0.05], [0.95, 0.05]):
        with pytest.raises(ValueError, match="interval"):
            check_interval(bad)
    with pytest.raises(ValueError, match="draws"):
        summarise([])


def test_totals_come_from_samples_not_from_medians() -> None:
    # Two skewed parts: the median of the total is not the sum of the medians.
    a = np.array([0.0, 0.0, 0.0, 10.0, 10.0])
    b = np.array([10.0, 10.0, 0.0, 0.0, 0.0])
    total = summarise_total([a, b])
    assert summarise(a).median + summarise(b).median == 0.0
    assert total.median == 10.0  # draws of the total: 10, 10, 0, 10, 10
    assert total.mean == pytest.approx(summarise(a).mean + summarise(b).mean)
    with pytest.raises(ValueError, match="same number of draws"):
        summarise_total([a, b[:3]])


def _result(samples: bool) -> ModelResult:
    u, g, s = UnitId("U"), GroupId("G"), ServiceId("S")
    return ModelResult(
        model_id="m",
        model_version="1",
        indicators=(
            IndicatorSpec("noise", "noise", "1", False, True),
            IndicatorSpec("time", "time", "min", True, False),
        ),
        cells=(
            ResultCell(u, g, s, STATIC_TIME, "noise", 99.0, 0.0, 1.0),
            ResultCell(u, g, s, STATIC_TIME, "time", 12.0, 12.0, 12.0),
            ResultCell(UnitId("V"), g, s, STATIC_TIME, "time", None, None, None),
        ),
        samples=(CellSamples(u, g, s, STATIC_TIME, "noise", np.array([1.0, 2.0, 6.0])),)
        if samples
        else (),
    )


def test_summarise_result_uses_samples_and_keeps_deterministic_values() -> None:
    noise, time, missing = summarise_result(_result(samples=True), (0.25, 0.75))
    assert noise.summary is not None
    assert (noise.summary.mean, noise.summary.median) == (3.0, 2.0)  # from samples, not 99
    assert (noise.summary.low, noise.summary.high) == (1.5, 4.0)
    assert time.summary is not None
    assert (time.summary.mean, time.summary.median, time.summary.low) == (12.0, 12.0, 12.0)
    assert time.summary.n_samples == 0
    assert missing.summary is None
    with pytest.raises(ValueError, match="no samples"):
        summarise_result(_result(samples=False))


@pytest.mark.skipif(not packages.PACKAGES.exists(), reason="packages not built")
def test_diagnostic_summary_matches_its_samples_and_its_own_values() -> None:
    """Known answer on demo package 1.0.0: the model's own mean and 5/95 % bounds are reproduced,
    and the median is the median of the same samples (the model itself is unchanged)."""
    result = run_diagnostic(packages.load("1.0.0"), None, {"n_samples": 200}, 3, lambda _: None)
    summaries = summarise_result(result)
    samples = {(s.unit, s.group, s.service, s.indicator): s.values for s in result.samples}
    noise = [c for c in summaries if c.cell.indicator == "diagnostic_noise"]
    assert noise
    for c in noise:
        assert c.summary is not None
        draws = samples[(c.cell.unit, c.cell.group, c.cell.service, c.cell.indicator)]
        assert c.summary.mean == pytest.approx(c.cell.value)
        assert c.summary.low == pytest.approx(c.cell.low)
        assert c.summary.high == pytest.approx(c.cell.high)
        assert c.summary.median == pytest.approx(float(np.median(draws)))
        assert c.summary.n_samples == 200
    walk = [c for c in summaries if c.cell.indicator == "travel_time_walk_min"]
    assert all(c.summary is None or c.summary.median == c.cell.value for c in walk)

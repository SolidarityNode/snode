"""Summary statistics of Monte Carlo samples (Spec 00 §5; ADR 0017).

Every stored result value is summarised by its **mean**, its **median** and two **quantiles**
that bound its interval (default 5 % and 95 %, a 90 % interval). Uncertainty is never collapsed
to a single number (AGENTS.md invariant 6).

**Totals** across units or groups are computed from the samples: the draws are added sample by
sample, then summarised (:func:`summarise_total`). Medians, means of skewed outputs and interval
bounds are never added, because the median of a sum is not the sum of medians and interval
bounds do not add.

These are generic statistics of model output, not a scientific method.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from solidaritynode_core.model.registry import CellSamples, ModelResult, ResultCell

__all__ = [
    "DEFAULT_INTERVAL",
    "CellSummary",
    "SampleSummary",
    "check_interval",
    "summarise",
    "summarise_result",
    "summarise_total",
]

DEFAULT_INTERVAL: tuple[float, float] = (0.05, 0.95)
"""Default interval quantiles: the 5th and 95th percentiles (a central 90 % interval)."""


@dataclass(frozen=True, slots=True)
class SampleSummary:
    """Summary of the draws of one value.

    Attributes:
        mean: Mean of the draws.
        median: Median of the draws (the central value shown on maps and tables).
        low: Lower interval bound, the ``interval[0]`` quantile.
        high: Upper interval bound, the ``interval[1]`` quantile.
        interval: Quantile levels of ``low`` and ``high`` (for example ``(0.05, 0.95)``).
        n_samples: Number of draws (0 for a deterministic value).
    """

    mean: float
    median: float
    low: float
    high: float
    interval: tuple[float, float]
    n_samples: int


@dataclass(frozen=True, slots=True)
class CellSummary:
    """A :class:`~solidaritynode_core.model.ResultCell` with its full summary.

    ``summary`` is ``None`` when the value is not computable (``cell.value is None``).
    """

    cell: ResultCell
    summary: SampleSummary | None


def check_interval(interval: Sequence[float]) -> tuple[float, float]:
    """Validate interval quantile levels and return them as a pair (Spec 00 §5; ADR 0017).

    Args:
        interval: Two quantile levels ``(low, high)`` with ``0 < low < 0.5 < high < 1``, so the
            interval contains the median.

    Raises:
        ValueError: If the levels are not two numbers in that order.
    """
    if len(interval) != 2:
        raise ValueError(f"interval needs two quantile levels, got {list(interval)}")
    low, high = float(interval[0]), float(interval[1])
    if not 0.0 < low < 0.5 < high < 1.0:
        raise ValueError(
            f"interval quantiles must satisfy 0 < low < 0.5 < high < 1, got {low, high}"
        )
    return low, high


def summarise(values: npt.ArrayLike, interval: Sequence[float] = DEFAULT_INTERVAL) -> SampleSummary:
    """Summarise the draws of one value (Spec 00 §5).

    Args:
        values: One-dimensional draws (any unit; the summary keeps it).
        interval: Quantile levels of the interval bounds.

    Returns:
        Mean, median and the two quantiles (linear interpolation, NumPy's default).

    Raises:
        ValueError: If there are no draws, they are not one-dimensional or not finite.
    """
    levels = check_interval(interval)
    draws = np.asarray(values, dtype=np.float64)
    if draws.ndim != 1 or draws.size == 0:
        raise ValueError("summarise needs a non-empty one-dimensional array of draws")
    if not np.all(np.isfinite(draws)):
        raise ValueError("draws must be finite")
    low, median, high = np.quantile(draws, [levels[0], 0.5, levels[1]])
    return SampleSummary(
        mean=float(draws.mean()),
        median=float(median),
        low=float(low),
        high=float(high),
        interval=levels,
        n_samples=int(draws.size),
    )


def summarise_total(
    samples: Sequence[npt.ArrayLike], interval: Sequence[float] = DEFAULT_INTERVAL
) -> SampleSummary:
    """Summarise a total across units or groups from its parts' samples (Spec 00 §5; ADR 0017).

    Draw ``i`` of the total is the sum of draw ``i`` of every part, so all parts must come from
    the same Monte Carlo run and have the same number of draws, and be the same indicator for
    the same service and period (AGENTS.md core rules). Never add medians or interval bounds
    instead.

    Args:
        samples: Draws of each part, all of the same length.
        interval: Quantile levels of the interval bounds.

    Raises:
        ValueError: If there are no parts or their lengths differ.
    """
    if not samples:
        raise ValueError("summarise_total needs at least one part")
    arrays = [np.asarray(s, dtype=np.float64) for s in samples]
    if len({a.shape for a in arrays}) != 1:
        raise ValueError("all parts must have the same number of draws (one Monte Carlo run)")
    return summarise(np.sum(arrays, axis=0), interval)


def summarise_result(
    result: ModelResult, interval: Sequence[float] = DEFAULT_INTERVAL
) -> tuple[CellSummary, ...]:
    """Summarise every cell of a model result (Spec 00 §5; ADR 0017).

    Sampled indicators are summarised from their samples (the model's own ``value``, ``low`` and
    ``high`` are not used for them). Deterministic indicators have mean = median = low = high =
    the value. A non-deterministic indicator without samples is refused: its median and interval
    levels would be unknown.

    Args:
        result: Model output.
        interval: Quantile levels of the interval bounds.

    Raises:
        ValueError: If a non-deterministic cell has no samples, or a deterministic cell has an
            interval of non-zero width.
    """
    levels = check_interval(interval)
    deterministic = {i.id: i.deterministic for i in result.indicators}
    by_key: dict[tuple[str, str, str, str, str], CellSamples] = {
        (s.unit, s.group, s.service, s.time, s.indicator): s for s in result.samples
    }
    out: list[CellSummary] = []
    for cell in result.cells:
        if cell.value is None:
            out.append(CellSummary(cell, None))
            continue
        key = (cell.unit, cell.group, cell.service, cell.time, cell.indicator)
        sampled = by_key.get(key)
        if sampled is not None:
            out.append(CellSummary(cell, summarise(sampled.values, levels)))
        elif deterministic.get(cell.indicator, False):
            if cell.low not in (None, cell.value) or cell.high not in (None, cell.value):
                raise ValueError(f"deterministic cell {key} has an interval")
            v = cell.value
            out.append(CellSummary(cell, SampleSummary(v, v, v, v, levels, 0)))
        else:
            raise ValueError(f"cell {key} is not deterministic but has no samples")
    return tuple(out)

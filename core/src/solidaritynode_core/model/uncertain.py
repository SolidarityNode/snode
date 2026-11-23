"""Types for uncertain quantities (CLAUDE.md invariant 6; Paper 1 §11, Paper 2 §14, Paper 3 §22).

An uncertain quantity is one of:

* :class:`PointValue`: a single value. Allowed for inputs known exactly; outputs should prefer
  samples or distributions.
* :class:`Samples`: Monte Carlo draws of a scalar.
* :class:`DiscreteDistribution`: probabilities over the named states of a discrete variable,
  for example ``P(V = Low/Medium/High)``.

These are containers only. How samples are drawn is the job of ``uncertainty`` (not yet
implemented).
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

import numpy as np
import numpy.typing as npt

__all__ = ["DiscreteDistribution", "PointValue", "Samples", "Uncertain"]

_PROBABILITY_TOLERANCE = 1e-9


@dataclass(frozen=True, slots=True)
class PointValue:
    """A single known value (Spec 00 §4 kinds ``INPUT``/``PARAMETER``).

    Attributes:
        value: Finite real number. Units are carried by the enclosing quantity.
    """

    value: float

    def __post_init__(self) -> None:
        """Validate that the value is finite."""
        if not math.isfinite(self.value):
            raise ValueError("PointValue must be finite")


@dataclass(frozen=True, slots=True, eq=False)
class Samples:
    """Monte Carlo samples of a scalar quantity (Paper 1 §11).

    Attributes:
        values: One-dimensional, non-empty array of finite draws. Stored read-only.
    """

    values: npt.NDArray[np.float64]

    def __post_init__(self) -> None:
        """Validate shape and finiteness, and freeze the array."""
        array = np.array(self.values, dtype=np.float64, copy=True)
        if array.ndim != 1 or array.size == 0:
            raise ValueError("Samples must be a non-empty one-dimensional array")
        if not np.all(np.isfinite(array)):
            raise ValueError("Samples must be finite")
        array.setflags(write=False)
        object.__setattr__(self, "values", array)

    @property
    def size(self) -> int:
        """Return the number of samples."""
        return int(self.values.size)


@dataclass(frozen=True, slots=True)
class DiscreteDistribution:
    """Probabilities over the named states of a discrete variable (Spec 00 §2, index ``l``).

    Attributes:
        probabilities: Mapping ``state -> probability``. Probabilities are in ``[0, 1]`` and sum
            to 1. Order of insertion is the state order.
    """

    probabilities: Mapping[str, float]

    def __post_init__(self) -> None:
        """Validate probabilities and freeze the mapping."""
        frozen = MappingProxyType(dict(self.probabilities))
        if not frozen:
            raise ValueError("DiscreteDistribution needs at least one state")
        for state, prob in frozen.items():
            if not (0.0 <= prob <= 1.0) or not math.isfinite(prob):
                raise ValueError(f"probability of {state!r} must be in [0, 1]")
        total = math.fsum(frozen.values())
        if abs(total - 1.0) > _PROBABILITY_TOLERANCE:
            raise ValueError(f"probabilities must sum to 1, got {total}")
        object.__setattr__(self, "probabilities", frozen)

    @property
    def states(self) -> tuple[str, ...]:
        """Return the state names in order."""
        return tuple(self.probabilities)

    def probability(self, state: str) -> float:
        """Return ``P(X = state)``.

        Raises:
            KeyError: If ``state`` is not a state of this distribution.
        """
        return self.probabilities[state]


#: An uncertain scalar: a point value, Monte Carlo samples or a discrete distribution.
type Uncertain = PointValue | Samples | DiscreteDistribution

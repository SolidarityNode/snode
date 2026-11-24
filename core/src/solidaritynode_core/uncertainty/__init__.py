"""Monte Carlo propagation of uncertainty (Paper 1 §11, Paper 2 §14, Paper 3 §22). Interfaces only.

Sample uncertain inputs and CPT parameters, run the model, collect ``P(·)`` or a distribution
(Spec 00 §5). Randomness always goes through an explicit :class:`numpy.random.Generator`
(CLAUDE.md conventions). Outputs carry a ``sample`` dimension; uncertainty is never collapsed
silently (CLAUDE.md invariant 6).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Protocol

import numpy as np

from solidaritynode_core.model import IndexedValues

__all__ = ["MonteCarloRunner", "ParameterSampler"]


class ParameterSampler(Protocol):
    """Draw samples of uncertain parameters (for example ``p``, ``k``, demand rate)."""

    def sample(self, n_samples: int, rng: np.random.Generator) -> Mapping[str, IndexedValues]:
        """Return samples per parameter name, each with a ``sample`` dimension of size ``n``."""
        ...


class MonteCarloRunner(Protocol):
    """Run a model over parameter samples (Paper 1 §11)."""

    def run(
        self,
        model: Callable[[Mapping[str, IndexedValues]], Mapping[str, IndexedValues]],
        sampler: ParameterSampler,
        n_samples: int,
        rng: np.random.Generator,
    ) -> Mapping[str, IndexedValues]:
        """Return model outputs, each with a ``sample`` dimension."""
        ...

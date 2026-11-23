"""Sensitivity analysis (Paper 1 §12, Paper 2 §16, Paper 3 §23). Interfaces only.

Ranks factors by their influence on outputs. Mandatory analyses already decided include the
sensitivity of hidden need to need prevalence ``p`` (OQ-8) and of results to the rationing case
(OQ-24); Need Pressure and the baseline gap are examined here, not inside the BN (OQ-12). The
method (one-at-a-time, variance-based, …) is not chosen.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol

from solidaritynode_core.model import IndexedValues

__all__ = ["SensitivityAnalyser"]


class SensitivityAnalyser(Protocol):
    """Rank input factors by influence on an output (Spec 00 §5)."""

    def rank(
        self,
        inputs: Mapping[str, IndexedValues],
        output: IndexedValues,
        factors: Sequence[str],
    ) -> Sequence[tuple[str, float]]:
        """Return ``(factor, influence)`` pairs in decreasing order of influence."""
        ...

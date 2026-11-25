"""Validation tools (Paper 1 §14, Paper 2 §18, Paper 3 §24). Interfaces only.

Expert validation, plausibility and monotonicity checks, sensitivity, and later calibration
against observed data (Spec 00 §5). Decided checks to support include: a zero-severity scenario
gives zero Service Loss (OQ-12), and aggregate calibration of visible need where aggregate
administrative figures exist (OQ-8). Direct validation of hidden need is future work (N-8c).

The diagnostic model ``diagnostic-v0`` (:mod:`solidaritynode_core.validation.diagnostic`) checks
the platform's mechanics against the demo hand-check table. It is not a research result.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from solidaritynode_core.validation.diagnostic import (
    DIAGNOSTIC_LABEL,
    DIAGNOSTIC_MODEL_ID,
    DIAGNOSTIC_MODEL_VERSION,
    DIAGNOSTIC_V0,
    run_diagnostic,
    shortest_travel_times,
)

__all__ = [
    "DIAGNOSTIC_LABEL",
    "DIAGNOSTIC_MODEL_ID",
    "DIAGNOSTIC_MODEL_VERSION",
    "DIAGNOSTIC_V0",
    "CheckOutcome",
    "CheckResult",
    "ValidationCheck",
    "run_diagnostic",
    "shortest_travel_times",
]


class CheckOutcome(StrEnum):
    """Outcome of a validation check."""

    PASSED = "passed"
    FAILED = "failed"
    INCONCLUSIVE = "inconclusive"


@dataclass(frozen=True, slots=True)
class CheckResult:
    """Result of one validation check.

    Attributes:
        check: Name of the check.
        outcome: Outcome.
        details: Human-readable explanation.
        spec_ref: Spec section the check verifies, for example ``"Paper 3 §15"``.
    """

    check: str
    outcome: CheckOutcome
    details: str
    spec_ref: str


class ValidationCheck(Protocol):
    """A named check of model behaviour (Paper 1 §14)."""

    @property
    def name(self) -> str:
        """Return the check name."""
        ...

    def run(self) -> Sequence[CheckResult]:
        """Run the check and return its results."""
        ...

"""Ordinal three-state type Low / Medium / High.

Used by Social Susceptibility (Paper 2 §6–7, OQ-9), Service Gap states (Paper 1 §8), the
non-take-up level (Paper 2 §10, OQ-8) and Vulnerability (Paper 3 §17, OQ-15: three states
decided). Discretisation thresholds are **not** defined here (OQ-4, OQ-7, OQ-15).
"""

from __future__ import annotations

from enum import IntEnum

__all__ = ["LevelLMH"]


class LevelLMH(IntEnum):
    """Ordered state ``Low < Medium < High`` of a discrete variable (Spec 00 §4).

    The integer value encodes order only; it is not a score and must not be averaged.
    """

    LOW = 0
    MEDIUM = 1
    HIGH = 2

    @property
    def label(self) -> str:
        """Return the human-readable label (``"Low"``, ``"Medium"``, ``"High"``)."""
        return self.name.capitalize()

    @classmethod
    def from_label(cls, label: str) -> LevelLMH:
        """Parse a label case-insensitively.

        Args:
            label: ``"low"``, ``"medium"`` or ``"high"`` in any case.

        Returns:
            The matching state.

        Raises:
            ValueError: If the label is not one of the three states (for example the removed
                "Very High" state, OQ-15).
        """
        try:
            return cls[label.strip().upper()]
        except KeyError as exc:
            raise ValueError(f"unknown Low/Medium/High state: {label!r}") from exc

    @classmethod
    def labels(cls) -> tuple[str, ...]:
        """Return the state labels in order."""
        return tuple(member.label for member in cls)

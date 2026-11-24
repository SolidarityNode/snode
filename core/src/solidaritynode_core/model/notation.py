"""Index notation and named dimensions (Spec 00 §2, OQ-1 decided).

The papers' original symbols differ; OQ-1 fixed one notation for all four papers:

=========  ====================================================
Symbol     Meaning
=========  ====================================================
``i``      spatial unit (first application: Greek ΤΚ, kept generic)
``f``      facility
``g``      population group
``s``      service
``m``      transport mode
``c``      scenario (counterfactual or disruption)
``t``      time
``l``      state of a discrete variable
=========  ====================================================

``k`` (intensity, OQ-24), ``p`` (need prevalence) and ``τ`` (take-up, OQ-8) are parameters,
not dimensions.
"""

from __future__ import annotations

from enum import StrEnum

__all__ = ["UNIT_OF_ANALYSIS", "Dim"]


class Dim(StrEnum):
    """Named dimension of an indexed quantity (Spec 00 §2, OQ-1).

    The string value is the dimension name used in labelled arrays; :attr:`symbol` gives the
    paper symbol.
    """

    UNIT = "unit"
    FACILITY = "facility"
    GROUP = "group"
    SERVICE = "service"
    MODE = "mode"
    SCENARIO = "scenario"
    TIME = "time"
    STATE = "state"
    # Not a paper index: the Monte Carlo sample axis used to carry uncertainty
    # (Paper 1 §11, Paper 2 §14, Paper 3 §22; CLAUDE.md invariant 6).
    SAMPLE = "sample"

    @property
    def symbol(self) -> str:
        """Return the paper symbol of the dimension (OQ-1), or ``"n"`` for samples."""
        return _SYMBOLS[self]


_SYMBOLS: dict[Dim, str] = {
    Dim.UNIT: "i",
    Dim.FACILITY: "f",
    Dim.GROUP: "g",
    Dim.SERVICE: "s",
    Dim.MODE: "m",
    Dim.SCENARIO: "c",
    Dim.TIME: "t",
    Dim.STATE: "l",
    Dim.SAMPLE: "n",
}

#: The unit of analysis, Paper 4 §3: spatial unit × social group × service × time.
UNIT_OF_ANALYSIS: tuple[Dim, Dim, Dim, Dim] = (Dim.UNIT, Dim.GROUP, Dim.SERVICE, Dim.TIME)

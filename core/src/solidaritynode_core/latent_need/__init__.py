"""Social susceptibility, hidden need and total need (Paper 2). Interfaces only.

Decided (OQ-8, OQ-9, OQ-10, OQ-11):

* Need is ``Population × p`` (people) and ``Population × p × k`` (service units, ``ETN``).
* The latent node is the **level of non-take-up** ``1 − τ``, with four parents and no edges
  between them: Social Susceptibility ``SS_{i,g,s}``, need-based gap, access deterrence and
  alternatives outside the network.
* Take-up ``τ`` is the share of people with need who **express** it, served or not.

Observed demand is not need, and a group is not its susceptibility (CLAUDE.md invariants 4,
5). State bounds of non-take-up are set with experts; CPT size: OQ-7, OQ-11.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol

import numpy as np

from solidaritynode_core.model import GroupId, IndexedValues, PopulationGroup, ServiceId

__all__ = [
    "HiddenNeedEstimator",
    "NonTakeUpEvidenceModel",
    "NonTakeUpModel",
    "SocialSusceptibilityModel",
]


class SocialSusceptibilityModel(Protocol):
    """Social Susceptibility ``SS_{i,g,s}`` (Paper 2 §6–7; OQ-9 decided).

    Depends only on social characteristics, never on availability, accessibility or capacity
    (Paper 2 §6.2). Indicators may differ by service; group-definition indicators are never
    reused (enforced by
    :meth:`~solidaritynode_core.model.PopulationGroup.check_susceptibility_indicators`).
    """

    def indicators(self, group: GroupId, service: ServiceId) -> frozenset[str]:
        """Return the indicator names used as evidence for this group and service."""
        ...

    def susceptibility(
        self,
        group_characteristics: IndexedValues,
        groups: Sequence[PopulationGroup],
    ) -> IndexedValues:
        """Return ``P(SS = Low/Medium/High)``.

        Args:
            group_characteristics: Indicator values, dims ``(unit, group)`` plus indicators.
            groups: Group definitions (for the reuse check).

        Returns:
            Probabilities, dims ``(unit, group, service, state)``.
        """
        ...


class NonTakeUpEvidenceModel(Protocol):
    """Evidence for the non-take-up node (Paper 2 §9; OQ-10, OQ-11 decided)."""

    def need_based_gap(
        self,
        population: IndexedValues,
        need_prevalence: IndexedValues,
        intensity: IndexedValues,
        supply: IndexedValues,
    ) -> IndexedValues:
        """Return the need-based gap: shortfall of Paper 1 supply against **total** need (OQ-10).

        Returns:
            Service units per period, dims ``(unit, group, service[, sample])``.
        """
        ...

    def access_deterrence(self, travel_times: IndexedValues) -> IndexedValues:
        """Return access deterrence: accessibility only as a deterrent to seeking (OQ-11).

        Not capacity reaching the unit, which is already in the need-based gap.
        """
        ...

    def outside_alternatives(
        self, estimates: Mapping[tuple[GroupId, ServiceId], float]
    ) -> IndexedValues:
        """Return alternatives **outside** the modelled network (private, family, NGOs; OQ-11).

        Expert estimates where no data exist.
        """
        ...


class NonTakeUpModel(Protocol):
    """``P(non-take-up | SS, need-based gap, access deterrence, outside alternatives)``.

    Paper 2 §10 (OQ-8, OQ-10, OQ-11). CPT learned from observed use by parameter learning
    pooled across units (OQ-8; prior weight OQ-27).
    """

    def posterior(
        self,
        susceptibility: IndexedValues,
        need_based_gap: IndexedValues,
        access_deterrence: IndexedValues,
        outside_alternatives: IndexedValues,
    ) -> IndexedValues:
        """Return ``P(non-take-up level = l)``, dims ``(unit, group, service, state)``."""
        ...


class HiddenNeedEstimator(Protocol):
    """Hidden need, visible need and Estimated Total Need (Paper 2 §12; OQ-8, OQ-24).

    Outputs carry uncertainty: values of ``1 − τ`` are sampled within the posterior state
    ranges (not fixed midpoints) and results are reported with intervals and with sensitivity
    to ``p`` (identifiability limitation, OQ-8).
    """

    def sample_take_up(
        self, non_take_up_posterior: IndexedValues, n_samples: int, rng: np.random.Generator
    ) -> IndexedValues:
        """Return samples of ``τ``, dims ``(unit, group, service, sample)``."""
        ...

    def hidden_need_people(
        self, population: IndexedValues, need_prevalence: IndexedValues, take_up: IndexedValues
    ) -> IndexedValues:
        """Return hidden need in people, dims ``(unit, group, service, sample)``."""
        ...

    def estimated_total_need(
        self, population: IndexedValues, need_prevalence: IndexedValues, intensity: IndexedValues
    ) -> IndexedValues:
        """Return ``ETN`` in service units per period, dims ``(unit, group, service[, sample])``."""
        ...

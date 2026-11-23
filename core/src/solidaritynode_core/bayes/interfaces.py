"""Protocols for discrete Bayesian networks (Spec 00 §5; Paper 1 §9, Paper 2 §10, Paper 3 §17).

Nothing here is an implementation. Concrete classes arrive after ADR 0004 (library) and
ADR 0005 (inference approach and discretisation, OQ-7).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol, runtime_checkable

from solidaritynode_core.model.catalogue import VariableKind
from solidaritynode_core.model.uncertain import DiscreteDistribution

__all__ = [
    "ConditionalProbabilityTable",
    "CptElicitor",
    "DiscreteVariable",
    "ElicitationJudgement",
    "Evidence",
    "InferenceEngine",
    "NetworkStructure",
    "ObservationTable",
    "ParameterLearner",
    "PriorStrength",
]

#: Evidence: variable name → observed state (hard evidence) or a likelihood over states
#: (soft/virtual evidence). Which form each module uses is decided with OQ-7.
type Evidence = Mapping[str, str | Mapping[str, float]]

#: Observed configurations used for parameter learning: one mapping ``variable -> state`` per
#: observation (Paper 4 §10; OQ-8 learning of take-up; OQ-16 learning of vulnerability).
type ObservationTable = Sequence[Mapping[str, str]]


@runtime_checkable
class DiscreteVariable(Protocol):
    """A discrete random variable of a BN (Spec 00 §2, state index ``l``; §4 kinds).

    Attributes:
        name: Unique name within a network; should match a catalogue key
            (:data:`~solidaritynode_core.model.CATALOGUE`).
        states: Ordered state names, for example ``("Low", "Medium", "High")``.
        kind: Catalogue kind; must be a BN node kind (evidence, parent, target or latent).
    """

    @property
    def name(self) -> str:
        """Return the variable name."""
        ...

    @property
    def states(self) -> tuple[str, ...]:
        """Return the ordered state names."""
        ...

    @property
    def kind(self) -> VariableKind:
        """Return the catalogue kind."""
        ...


@runtime_checkable
class ConditionalProbabilityTable(Protocol):
    """``P(child | parents)`` for discrete variables (Paper 1 §9, Paper 2 §10, Paper 3 §17).

    Under OQ-16 the CPT of Vulnerability **is** the vulnerability relationship.
    """

    @property
    def child(self) -> DiscreteVariable:
        """Return the child variable."""
        ...

    @property
    def parents(self) -> tuple[DiscreteVariable, ...]:
        """Return the parent variables in table order."""
        ...

    def distribution(self, parent_states: Mapping[str, str]) -> DiscreteDistribution:
        """Return ``P(child | parents = parent_states)``.

        Args:
            parent_states: One state for every parent, keyed by parent name.

        Returns:
            Distribution over the child's states.
        """
        ...


@runtime_checkable
class ElicitationJudgement(Protocol):
    """One expert judgement for a CPT row (Spec 00 §4.2 for Paper 2; Paper 3 §21; OQ-7).

    Experts answer frequency questions about scenarios, for example "out of 100 older people
    who need care, in an area with low accessibility and few alternatives, how many do not
    receive it?" (Paper 2, OQ-8). Format and aggregation across experts are open (OQ-7).
    """

    @property
    def parent_states(self) -> Mapping[str, str]:
        """Return the parent configuration the judgement refers to."""
        ...

    @property
    def child_frequencies(self) -> Mapping[str, float]:
        """Return judged frequencies (or weights) per child state."""
        ...

    @property
    def expert_id(self) -> str:
        """Return a pseudonymous expert identifier (never a name)."""
        ...


class CptElicitor(Protocol):
    """Build a CPT from expert judgements (Spec 00 §5; OQ-7, OQ-11 CPT size).

    Handling of large tables (intermediate nodes, ranked nodes) and of implausible
    combinations is open (OQ-7, OQ-11).
    """

    def elicit(
        self,
        child: DiscreteVariable,
        parents: Sequence[DiscreteVariable],
        judgements: Sequence[ElicitationJudgement],
    ) -> ConditionalProbabilityTable:
        """Return a CPT consistent with the judgements."""
        ...


class NetworkStructure(Protocol):
    """Directed acyclic graph of discrete variables with their CPTs (Spec 00 §5)."""

    @property
    def variables(self) -> tuple[DiscreteVariable, ...]:
        """Return all variables."""
        ...

    def parents_of(self, name: str) -> tuple[str, ...]:
        """Return the parent names of ``name``."""
        ...

    def cpt(self, name: str) -> ConditionalProbabilityTable:
        """Return the CPT of ``name``."""
        ...


class InferenceEngine(Protocol):
    """Posterior inference in a discrete BN (Spec 00 §5; ADR 0004, ADR 0005, OQ-7)."""

    def query(
        self,
        network: NetworkStructure,
        targets: Sequence[str],
        evidence: Evidence,
    ) -> Mapping[str, DiscreteDistribution]:
        """Return marginal posteriors of ``targets`` given ``evidence``.

        Args:
            network: The network.
            targets: Variable names to query.
            evidence: Observed states or likelihoods.

        Returns:
            One distribution per target, for example ``P(V = High | evidence)`` (Paper 3 §22).
        """
        ...


class PriorStrength(Protocol):
    """How strongly an expert CPT resists observed data (OQ-27, open).

    Candidates in OQ-27: a fixed equivalent sample size per row, elicited confidence per row,
    or hierarchical pooling across units and groups.
    """

    def equivalent_sample_size(self, child: str, parent_states: Mapping[str, str]) -> float:
        """Return the equivalent sample size of the prior for one CPT row."""
        ...


class ParameterLearner(Protocol):
    """Bayesian parameter learning of a CPT with an expert CPT as prior.

    Paper 4 §10 as revised by OQ-16 (vulnerability relationship) and OQ-8 (take-up, Paper 2),
    for example Dirichlet priors per CPT row (Koller & Friedman, 2009). Weight of the prior:
    OQ-27. Only observations from facilities with full or known recording coverage may be used
    (OQ-8); cell-level updating is restricted by privacy rules (OQ-21).
    """

    def learn(
        self,
        prior: ConditionalProbabilityTable,
        observations: ObservationTable,
        strength: PriorStrength,
    ) -> ConditionalProbabilityTable:
        """Return the posterior CPT (point estimate or posterior mean).

        Args:
            prior: Expert-elicited CPT.
            observations: Complete or partial observed configurations.
            strength: Prior weight (OQ-27).

        Returns:
            Updated CPT over the same variables.
        """
        ...

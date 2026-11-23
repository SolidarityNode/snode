"""Variable catalogue: what each quantity is, not how it is computed (Spec 00 §4).

Every quantity of Papers 1–4 is classified by **kind**, so that BN nodes, computed simulation
variables, evidence and scenario parameters stay distinct (Spec 00 §4; CLAUDE.md). The
catalogue holds no formulas. The "As stated" column of Spec 00 §4 remains the source of truth;
this module mirrors it and is checked by tests. Where Spec 00 gives no paper section, the
Spec 00 section is cited instead.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Final

from solidaritynode_core.model.notation import Dim

__all__ = ["CATALOGUE", "VariableKind", "VariableSpec", "variables_of_kind"]


class VariableKind(StrEnum):
    """Kind of a catalogue variable (Spec 00 §4)."""

    INPUT = "input"
    #: Uncertain input, sampled in Monte Carlo.
    PARAMETER = "parameter"
    #: Simulation variable; **not** a BN node.
    COMPUTED = "computed"
    #: Computed outside the BN and fed in as evidence.
    EVIDENCE = "evidence"
    BN_PARENT = "bn_parent"
    BN_TARGET = "bn_target"
    LATENT = "latent"
    OBSERVED = "observed"
    OUTPUT = "output"
    #: State of the operational or territorial system (Paper 4).
    STATE = "state"


#: Kinds that are nodes of a Bayesian network (static BN or DBN).
BN_NODE_KINDS: Final = frozenset(
    {VariableKind.EVIDENCE, VariableKind.BN_PARENT, VariableKind.BN_TARGET, VariableKind.LATENT}
)


@dataclass(frozen=True, slots=True)
class VariableSpec:
    """Specification of one catalogue variable (Spec 00 §4).

    Attributes:
        key: Stable identifier used in code and results (snake_case).
        symbol: Paper symbol in the OQ-1 notation.
        kinds: One or more kinds (a few variables are, for example, computed and also a BN node).
        dims: Dimensions the variable is indexed by; ``()`` when the paper leaves them open.
        paper: Source section, for example ``"Paper 1 §8"``.
        open_questions: Related open or decided questions (``"OQ-n"``).
    """

    key: str
    symbol: str
    kinds: frozenset[VariableKind]
    dims: tuple[Dim, ...]
    paper: str
    open_questions: tuple[str, ...] = ()


def _v(
    key: str,
    symbol: str,
    kinds: set[VariableKind],
    dims: tuple[Dim, ...],
    paper: str,
    *oqs: str,
) -> VariableSpec:
    return VariableSpec(key, symbol, frozenset(kinds), dims, paper, oqs)


K = VariableKind
U, F, G, S, M, C, T = (
    Dim.UNIT,
    Dim.FACILITY,
    Dim.GROUP,
    Dim.SERVICE,
    Dim.MODE,
    Dim.SCENARIO,
    Dim.TIME,
)

_SPECS: tuple[VariableSpec, ...] = (
    # --- Paper 1: baseline (Spec 00 §4.1) ---
    _v("population", "Population_{i,g}", {K.INPUT}, (U, G), "Paper 1 §4", "OQ-6"),
    _v("demand_rate", "DemandRate^g", {K.PARAMETER}, (G, S), "Paper 1 §6", "OQ-8", "OQ-24"),
    _v(
        "people_making_requests",
        "Population × DemandRate",
        {K.COMPUTED},
        (U, G, S),
        "Paper 1 §6",
        "OQ-8",
    ),
    _v("intensity", "k_{g,s}", {K.PARAMETER}, (G, S), "Paper 1 §6", "OQ-24"),
    _v("estimated_demand", "D_{i,g,s}", {K.COMPUTED}, (U, G, S), "Paper 1 §6", "OQ-24", "OQ-25"),
    _v("travel_time", "T_if^{g,m}", {K.COMPUTED}, (U, F, G, M), "Paper 1 §5", "OQ-1"),
    _v("access_weight", "w(T)", {K.COMPUTED}, (), "Paper 1 §5", "OQ-3"),
    _v("accessibility", "Accessibility_i^{g,m}", {K.COMPUTED}, (U, G, M), "Paper 1 §5", "OQ-5"),
    _v("physical_capacity", "C_f^physical", {K.INPUT, K.PARAMETER}, (F,), "Paper 1 §7"),
    _v("availability", "Availability_f", {K.PARAMETER}, (F,), "Paper 1 §7"),
    _v("functional_capacity", "C_f^functional", {K.COMPUTED}, (F,), "Paper 1 §7"),
    _v("effective_capacity", "2SFCA share", {K.COMPUTED}, (F, U, G), "Paper 1 §7", "OQ-2"),
    _v("supply", "S_{i,g,s}", {K.COMPUTED}, (U, G, S), "Paper 1 §7", "OQ-2"),
    _v(
        "service_gap",
        "SG_{i,g,s}",
        {K.COMPUTED, K.BN_TARGET},
        (U, G, S),
        "Paper 1 §8–9",
        "OQ-4",
        "OQ-8",
    ),
    # --- Paper 2: hidden need (Spec 00 §4.2) ---
    _v("group_characteristics", "indicators", {K.INPUT}, (U, G), "Paper 2 §7", "OQ-9"),
    _v("social_susceptibility", "SS_{i,g,s}", {K.BN_PARENT}, (U, G, S), "Paper 2 §6–7", "OQ-9"),
    _v(
        "need_based_gap",
        "max(0, Population·p·k − S)",
        {K.EVIDENCE},
        (U, G, S),
        "Paper 2 §9.2",
        "OQ-10",
    ),
    _v("access_deterrence", "access deterrence", {K.EVIDENCE}, (U, G, S), "Paper 2 §9.3", "OQ-11"),
    _v(
        "outside_alternatives",
        "alternatives outside the network",
        {K.EVIDENCE},
        (U, G, S),
        "Paper 2 §9.4",
        "OQ-11",
    ),
    _v("need_prevalence", "p_{i,g,s}", {K.PARAMETER}, (U, G, S), "Paper 2 §12", "OQ-8"),
    _v(
        "non_take_up_level",
        "Hidden Need node (1 − τ)",
        {K.LATENT},
        (U, G, S),
        "Paper 2 §10",
        "OQ-8",
        "OQ-10",
        "OQ-11",
    ),
    _v("take_up", "τ_{i,g,s}", {K.COMPUTED}, (U, G, S), "Paper 2 §12", "OQ-8"),
    _v("hidden_need_people", "Population·p·(1 − τ)", {K.OUTPUT}, (U, G, S), "Paper 2 §12", "OQ-8"),
    _v("visible_need_people", "Population·p·τ", {K.COMPUTED}, (U, G, S), "Paper 2 §12", "OQ-8"),
    _v("observed_use", "observed use", {K.OBSERVED}, (U, G, S, T), "Spec 00 §4.2", "OQ-8"),
    _v(
        "estimated_total_need",
        "ETN = Population·p·k",
        {K.OUTPUT},
        (U, G, S),
        "Paper 2 §4",
        "OQ-8",
        "OQ-24",
    ),
    # --- Paper 3: disruption and vulnerability (Spec 00 §4.3) ---
    _v("need_pressure", "NP", {K.COMPUTED}, (U, G, S), "Paper 3 §6"),
    _v("disruption_severity", "DS_{f,c}", {K.PARAMETER}, (F, C), "Paper 3 §7–10"),
    _v("disrupted_capacity", "C^D_f", {K.COMPUTED}, (F, C), "Paper 3 §7–10"),
    _v("disrupted_accessibility", "Accessibility^D", {K.COMPUTED}, (U, G, M, C), "Paper 3 §7–10"),
    _v("group_exposure", "GE", {K.EVIDENCE}, (U, G, C), "Paper 3 §11", "OQ-13"),
    _v("baseline_available_service", "AS⁰", {K.COMPUTED}, (U, G, S), "Paper 3 §13", "OQ-14"),
    _v("disrupted_available_service", "ASᴰ", {K.COMPUTED}, (U, G, S, C), "Paper 3 §13", "OQ-14"),
    _v("baseline_gap", "PUN⁰", {K.COMPUTED}, (U, G, S), "Paper 3 §14", "OQ-12"),
    _v("potential_unmet_need", "PUNᴰ", {K.COMPUTED}, (U, G, S, C), "Paper 3 §14", "OQ-12"),
    _v(
        "disruption_loss",
        "ΔPUN",
        {K.COMPUTED, K.OUTPUT},
        (U, G, S, C),
        "Paper 3 §14–15",
        "OQ-12",
        "OQ-24",
    ),
    _v("service_loss", "SL", {K.EVIDENCE}, (U, G, S, C), "Paper 3 §15", "OQ-12"),
    _v("relative_service_loss", "SL′", {K.OUTPUT}, (U, G, S, C), "Paper 3 §15", "OQ-12"),
    _v("rationing", "rationing case", {K.PARAMETER}, (C,), "Paper 3 §13–15", "OQ-24"),
    _v("loss_breadth", "breadth", {K.OUTPUT}, (U, G, S, C), "Paper 3 §13–15", "OQ-24"),
    _v("loss_depth", "depth", {K.OUTPUT}, (U, G, S, C), "Paper 3 §13–15", "OQ-24"),
    _v("loss_severity", "severity", {K.OUTPUT}, (U, G, S, C), "Paper 3 §13–15", "OQ-24"),
    _v(
        "vulnerability_relationship",
        "P(V | GE, SL, SS)",
        {K.BN_TARGET},
        (G,),
        "Paper 3 §17",
        "OQ-15",
        "OQ-16",
    ),
    _v(
        "vulnerability_at_scenario", "V_{i,g,s,c}", {K.OUTPUT}, (U, G, S, C), "Paper 3 §17", "OQ-16"
    ),
    _v("risk", "Σ_c P(c)·V_c", {K.OUTPUT}, (U, G, S), "Paper 3 §17", "OQ-16"),
    # --- Paper 4: operations, dynamics, resilience (Spec 00 §4.4) ---
    _v("ticket", "ticket", {K.OBSERVED}, (U, G, S, T), "Paper 4 §4.1", "OQ-6", "OQ-8", "OQ-21"),
    _v("recording_coverage", "recording coverage", {K.OBSERVED}, (F, T), "Paper 4 §4.1", "OQ-8"),
    _v("operational_indicators", "operational indicators", {K.COMPUTED}, (F, S, T), "Paper 4 §4.2"),
    _v(
        "facility_functional_state",
        "FunctionalState_f(t)",
        {K.LATENT, K.STATE},
        (F, T),
        "Paper 4 §5",
        "OQ-17",
    ),
    _v(
        "support_need",
        "need for support / resource mobilisation",
        {K.STATE},
        (F, T),
        "Paper 4 §6",
        "OQ-20",
    ),
    _v(
        "territorial_state",
        "territorial coverage and functional state",
        {K.STATE},
        (U, S, T),
        "Paper 4 §7–9",
    ),
    _v("observed_exposure", "GE(t)", {K.COMPUTED}, (U, G, T), "Paper 4 §8", "OQ-12", "OQ-16"),
    _v(
        "observed_service_loss", "SL(t)", {K.COMPUTED}, (U, G, S, T), "Paper 4 §8", "OQ-12", "OQ-16"
    ),
    _v(
        "expected_consequence",
        "ExpectedConsequence(t)",
        {K.COMPUTED},
        (U, G, S, T),
        "Paper 4 §8",
        "OQ-16",
    ),
    _v(
        "observed_consequence",
        "ObservedConsequence(t)",
        {K.OBSERVED},
        (U, G, S, T),
        "Paper 4 §9",
        "OQ-18",
    ),
    _v(
        "recovery_trajectory",
        "ServiceLoss(t) or ObservedConsequence(t)",
        {K.OBSERVED},
        (U, G, S, T),
        "Paper 4 §11",
        "OQ-12",
    ),
    _v(
        "resilience",
        "P(Resilience_{i,g,s} | trajectory)",
        {K.OUTPUT},
        (U, G, S),
        "Paper 4 §13",
        "OQ-19",
    ),
    _v(
        "facility_operational_output",
        "facility operational output",
        {K.OUTPUT},
        (F, T),
        "Spec 00 §4.4",
    ),
)

#: The catalogue, keyed by :attr:`VariableSpec.key`.
CATALOGUE: Final = MappingProxyType({spec.key: spec for spec in _SPECS})

if len(CATALOGUE) != len(_SPECS):  # pragma: no cover - guards against duplicate keys
    raise RuntimeError("duplicate keys in variable catalogue")


def variables_of_kind(kind: VariableKind) -> tuple[VariableSpec, ...]:
    """Return the catalogue variables that have ``kind`` among their kinds (Spec 00 §4)."""
    return tuple(spec for spec in CATALOGUE.values() if kind in spec.kinds)

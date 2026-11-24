"""Variable catalogue keeps BN nodes, computed variables and parameters distinct (Spec 00 §4)."""

from __future__ import annotations

from solidaritynode_core.model import CATALOGUE, Dim, VariableKind
from solidaritynode_core.model.catalogue import BN_NODE_KINDS

K = VariableKind


def test_every_variable_cites_a_section() -> None:
    for spec in CATALOGUE.values():
        assert spec.paper.startswith(("Paper ", "Spec 00 ")), spec.key
        assert "§" in spec.paper, spec.key
        assert spec.kinds, spec.key


def test_scenario_parameters_are_not_bn_nodes() -> None:
    for key in ("disruption_severity", "rationing"):
        assert CATALOGUE[key].kinds == {K.PARAMETER}


def test_computed_simulation_variables_are_not_bn_nodes() -> None:
    for key in (
        "need_pressure",
        "baseline_gap",
        "potential_unmet_need",
        "take_up",
        "estimated_demand",
        "supply",
    ):
        assert not CATALOGUE[key].kinds & BN_NODE_KINDS, key


def test_secondary_loss_indicators_are_outputs_only() -> None:
    for key in ("relative_service_loss", "loss_breadth", "loss_depth", "loss_severity"):
        assert CATALOGUE[key].kinds == {K.OUTPUT}, key


def test_decided_bn_roles() -> None:
    assert CATALOGUE["service_loss"].kinds == {K.EVIDENCE}  # OQ-12
    assert CATALOGUE["group_exposure"].kinds == {K.EVIDENCE}
    assert CATALOGUE["social_susceptibility"].kinds == {K.BN_PARENT}  # OQ-9
    assert CATALOGUE["non_take_up_level"].kinds == {K.LATENT}  # OQ-8
    for key in ("need_based_gap", "access_deterrence", "outside_alternatives"):  # OQ-10, OQ-11
        assert CATALOGUE[key].kinds == {K.EVIDENCE}


def test_susceptibility_is_per_unit_group_service() -> None:
    assert CATALOGUE["social_susceptibility"].dims == (Dim.UNIT, Dim.GROUP, Dim.SERVICE)


def test_demand_is_estimated_not_need() -> None:
    assert K.OBSERVED not in CATALOGUE["estimated_demand"].kinds
    assert CATALOGUE["observed_use"].kinds == {K.OBSERVED}


def test_vulnerability_and_resilience_are_separate() -> None:
    assert CATALOGUE["resilience"].kinds == {K.OUTPUT}
    assert "OQ-19" in CATALOGUE["resilience"].open_questions
    assert "OQ-16" in CATALOGUE["vulnerability_relationship"].open_questions

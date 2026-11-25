"""Messages for people: one catalogue of English templates with stable codes.

Every reference problem, recorded-only line and change description that core shows to people
is rendered from a template here, never written inline. ``make schemas`` exports these
templates together with the backend's (``docs/schemas/messages.json``); the frontend matches
a message's English text against them to recover the code and parameters, and shows the
translation of that code (``frontend/src/i18n``, terms per ``docs/i18n/glossary.md``). Texts of
stored runs therefore stay unchanged and still translate.

Templates use :meth:`str.format` fields (optionally with a format spec, ``{value:g}``).
Changing a template's wording changes the stored text of new runs: keep the old wording
recognisable or add a new code.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

__all__ = ["CORE_MESSAGES", "message", "render"]

CORE_MESSAGES: Final[Mapping[str, str]] = MappingProxyType(
    {
        # Scenario references (check_references; Spec 00 §3)
        "scenario.new_facility_exists": "new facility {facility}: id already exists",
        "scenario.new_facility_node_missing": (
            "new facility {facility}: network node {node} missing"
        ),
        "scenario.new_edge_exists": "new edge {edge}: id already exists",
        "scenario.new_edge_node_missing": "new edge {edge}: network node {node} missing",
        "scenario.facility_missing_in": "facility {facility}: closed or missing in data {version}",
        "scenario.facility_missing": "facility {facility}: closed or missing in the data version",
        "scenario.service_not_offered": "facility {facility}: does not offer service {service}",
        "scenario.input_not_set": "facility {facility}: {capacity_input} is not set",
        "scenario.input_negative": "facility {facility}: {capacity_input} would become negative",
        "scenario.edge_missing_in": "edge {edge}: closed or missing in data {version}",
        "scenario.edge_not_closable": "edge {edge}: cannot be closed (closable = false)",
        "scenario.edge_mode_missing": "edge {edge}: has no {mode} travel time to change",
        "scenario.edge_time_not_positive": (
            "edge {edge}: {mode} travel time would not stay positive; "
            "to close a road use closed edges"
        ),
        "scenario.unit_missing_in": "unit {unit}: missing in data {version}",
        "scenario.group_missing_in": "group {group}: missing in data {version}",
        "scenario.population_negative": (
            "unit {unit}, group {group}: population would become negative"
        ),
        # Interventions recorded without behaviour yet (ADR 0016; OQ-30)
        "recorded.edge_change_relative": "edge {edge} {mode} {quantity} {amount} % (recorded only)",
        "recorded.edge_change_absolute": (
            "edge {edge} {mode} {quantity} {amount} {unit} (recorded only)"
        ),
        "recorded.new_edge": "new edge {edge} {nodes} ({times}) (recorded only)",
        "recorded.travel_time": "{mode} {minutes:g} min",
        "recorded.population_relative": (
            "unit {unit} group {group} population {amount} % (recorded only)"
        ),
        "recorded.population_absolute": (
            "unit {unit} group {group} population {amount} persons (recorded only)"
        ),
        "recorded.new_edge_closed": (
            "new edge {edge} is closed by the same scenario: added, then closed, "
            "so no net effect (OQ-30)"
        ),
        # Changes per facility and unit (overlay; diagnostic unit_changes table)
        "change.new_facility": "new at {node}",
        "change.capacity": "{service} {capacity_input} {before:g} -> {after:g}",
        "change.severity": "DS = {severity:g} (recorded only)",
        "change.facility": "{facility}: {detail}",
        "change.edge_closed": "edge {edge} closed",
    }
)
"""Core message templates by code."""


def render(catalogue: Mapping[str, str], code: str, /, **params: object) -> str:
    """Return the English text of message ``code`` of ``catalogue`` with ``params`` filled in.

    Args:
        catalogue: Templates by code (:data:`CORE_MESSAGES` or the backend's).
        code: Message code; must be in ``catalogue``.
        **params: Values for the template's fields.

    Returns:
        The rendered text (the frontend translates it by matching the template).
    """
    return catalogue[code].format(**params)


def message(code: str, /, **params: object) -> str:
    """Return core message ``code`` rendered with ``params`` (see :func:`render`)."""
    return render(CORE_MESSAGES, code, **params)

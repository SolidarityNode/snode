"""Scenarios router (placeholder, no endpoints yet).

Will manage counterfactual and disruption scenarios (Paper 1 §13, Paper 3 §7–10), mirroring
``solidaritynode_core.model.Scenario``: severities in ``[0, 1]``, optional network disruption,
rationing case (OQ-24) and reference scenarios (OQ-16).
"""

from fastapi import APIRouter

router = APIRouter(prefix="/scenarios", tags=["scenarios"])

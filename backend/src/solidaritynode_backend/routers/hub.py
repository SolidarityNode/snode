"""Hub router (ADR 0012): mounted only when ``DEPLOYMENT_MODE=hub``.

Onboarding, package publishing and the upward flow (ADR 0014) come in later PRs. In a municipal
installation this router is not mounted, so every ``/hub`` path answers 404.
"""

from fastapi import APIRouter

from solidaritynode_backend.auth import CurrentUser
from solidaritynode_backend.schemas.api import RoleFeatureOut

router = APIRouter(prefix="/hub", tags=["hub"])


@router.get("/status", response_model=RoleFeatureOut)
def hub_status(user: CurrentUser) -> RoleFeatureOut:
    """What the hub offers in this version: nothing yet (onboarding is the next PR)."""
    return RoleFeatureOut(
        role="hub",
        feature="onboarding",
        implemented=False,
        note="Hub onboarding and package publishing are not implemented yet (ADR 0012).",
    )

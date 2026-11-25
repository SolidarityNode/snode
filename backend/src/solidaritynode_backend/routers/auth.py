"""Login, logout, the current user and public configuration (ADR 0015)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from solidaritynode_core.validation import DIAGNOSTIC_LABEL
from sqlalchemy.orm import Session

import solidaritynode_backend
from solidaritynode_backend.auth import (
    COOKIE_NAME,
    CurrentUser,
    IdentityProvider,
    get_identity_provider,
)
from solidaritynode_backend.config import Settings, get_settings
from solidaritynode_backend.db import get_session
from solidaritynode_backend.messages import msg
from solidaritynode_backend.orm import User
from solidaritynode_backend.schemas.api import AppConfigOut, LoginIn, UserOut
from solidaritynode_backend.services.throttle import Throttle, client_address, throttle_keys

GENERIC_FAILURE = msg("error.wrong_credentials")
TOO_MANY = msg("error.too_many_attempts")

router = APIRouter(tags=["auth"])

Db = Annotated[Session, Depends(get_session)]
Idp = Annotated[IdentityProvider, Depends(get_identity_provider)]
Config = Annotated[Settings, Depends(get_settings)]


@router.get("/config", response_model=AppConfigOut)
def app_config(settings: Config) -> AppConfigOut:
    """Public configuration: deployment mode, basemap, build identity and user-guide address."""
    return AppConfigOut(
        docs_url=settings.docs_url(solidaritynode_backend.__version__),
        deployment_mode=settings.deployment_mode,
        basemap=settings.basemap,
        app_env=settings.app_env,
        version=solidaritynode_backend.__version__,
        git_commit=settings.git_commit,
        diagnostic_label=DIAGNOSTIC_LABEL,
    )


@router.post(
    "/auth/login",
    response_model=UserOut,
    responses={
        status.HTTP_401_UNAUTHORIZED: {"description": "Wrong username or password"},
        status.HTTP_429_TOO_MANY_REQUESTS: {
            "description": "Too many failed attempts for this username or client address"
        },
    },
)
def login(
    body: LoginIn, request: Request, response: Response, db: Db, idp: Idp, settings: Config
) -> UserOut:
    """Check credentials and set the session cookie (HttpOnly, SameSite=Strict).

    Throttled per username and per client address (ADR 0015): while delayed or locked the answer
    is a generic 429 with ``Retry-After``, whether or not the user exists, and the password is
    not checked; a 429 is not counted and does not extend the delay or lock. Failures answer the
    same 401 for unknown users and wrong passwords. The client address comes from a trusted
    proxy's headers only (``SOLIDARITYNODE_TRUSTED_PROXIES``); when it is unknown, only the
    per-username limit applies.
    """
    throttle = Throttle(settings)
    address = client_address(
        request.client.host if request.client else None,
        request.headers.get("x-real-ip"),
        request.headers.get("x-forwarded-for"),
        settings.trusted_networks(),
    )
    keys = throttle_keys(body.username, address)
    wait = throttle.retry_after(db, keys)
    if wait:
        db.commit()
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, TOO_MANY, headers={"Retry-After": str(wait)}
        )
    outcome = idp.login(db, body.username, body.password)
    if outcome is None:
        throttle.failure(db, keys)
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, GENERIC_FAILURE)
    throttle.success(db, keys)
    db.commit()
    principal, token = outcome
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=int(settings.session_hours * 3600),
        httponly=True,
        samesite="strict",
        # Always Secure in production (the settings refuse production without it).
        secure=settings.session_cookie_secure or settings.app_env == "production",
        path="/",
    )
    return UserOut(id=principal.id, username=principal.username, role=principal.role, active=True)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, response: Response, db: Db, idp: Idp) -> None:
    """End the session and clear the cookie."""
    token = request.cookies.get(COOKIE_NAME)
    if token:
        idp.logout(db, token)
    response.delete_cookie(COOKIE_NAME, path="/")


@router.get("/auth/me", response_model=UserOut)
def me(user: CurrentUser, db: Db) -> UserOut:
    """Return the logged-in user (401 if not logged in)."""
    row = db.get(User, user.id)
    assert row is not None
    return UserOut(id=row.id, username=row.username, role=row.role, active=row.active)

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
from solidaritynode_backend.orm import User
from solidaritynode_backend.schemas.api import AppConfigOut, LoginIn, UserOut

router = APIRouter(tags=["auth"])

Db = Annotated[Session, Depends(get_session)]
Idp = Annotated[IdentityProvider, Depends(get_identity_provider)]
Config = Annotated[Settings, Depends(get_settings)]


@router.get("/config", response_model=AppConfigOut)
def app_config(settings: Config) -> AppConfigOut:
    """Public configuration: deployment mode, basemap and build identity."""
    return AppConfigOut(
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
    responses={status.HTTP_401_UNAUTHORIZED: {"description": "Wrong username or password"}},
)
def login(body: LoginIn, response: Response, db: Db, idp: Idp, settings: Config) -> UserOut:
    """Check credentials and set the session cookie (HttpOnly, SameSite=Strict)."""
    outcome = idp.login(db, body.username, body.password)
    if outcome is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "wrong username or password")
    principal, token = outcome
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=int(settings.session_hours * 3600),
        httponly=True,
        samesite="strict",
        secure=settings.session_cookie_secure,
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

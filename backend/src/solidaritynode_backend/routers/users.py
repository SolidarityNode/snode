"""User management (admin only; ADR 0015)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session as DbSession

from solidaritynode_backend.auth import Principal, create_user, hash_password, require_role
from solidaritynode_backend.db import get_session
from solidaritynode_backend.orm import Session, User
from solidaritynode_backend.schemas.api import UserIn, UserOut, UserPatch

router = APIRouter(prefix="/users", tags=["users"])

Db = Annotated[DbSession, Depends(get_session)]
Admin = Annotated[Principal, Depends(require_role("admin"))]


def _out(user: User) -> UserOut:
    return UserOut(id=user.id, username=user.username, role=user.role, active=user.active)


@router.get("", response_model=list[UserOut])
def list_users(_: Admin, db: Db) -> list[UserOut]:
    """List all users."""
    return [_out(u) for u in db.scalars(select(User).order_by(User.username))]


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def add_user(body: UserIn, _: Admin, db: Db) -> UserOut:
    """Create a local account."""
    try:
        user = create_user(db, body.username, body.password, body.role)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None
    db.commit()
    return _out(user)


@router.patch("/{user_id}", response_model=UserOut)
def change_user(user_id: int, body: UserPatch, admin: Admin, db: Db) -> UserOut:
    """Change role, active flag or password. Admins cannot demote or disable themselves."""
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user not found")
    if user.id == admin.id and (body.active is False or (body.role and body.role != "admin")):
        raise HTTPException(status.HTTP_409_CONFLICT, "you cannot demote or disable yourself")
    if body.role is not None:
        user.role = body.role
    if body.active is not None:
        user.active = body.active
        if not body.active:
            db.execute(delete(Session).where(Session.user_id == user.id))
    if body.password is not None:
        user.password_hash = hash_password(body.password)
        db.execute(delete(Session).where(Session.user_id == user.id))
    db.commit()
    return _out(user)

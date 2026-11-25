"""Authentication and roles (ADR 0015, accepted for v0.1, to be revisited).

v0.1 uses **local accounts**: passwords hashed with Argon2id (``argon2-cffi``), opaque session
tokens in an HttpOnly, SameSite=Strict cookie, and only the SHA-256 of each token in the
database. Routers depend on :class:`IdentityProvider`, so an external identity provider (for
example OpenID Connect) can replace :class:`LocalIdentityProvider` without touching them.

Roles: ``viewer`` sees shared scenarios and results; ``analyst`` also creates, edits, runs and
shares their own scenarios; ``admin`` also manages users and imports data packages.

Password policy: at least 12 characters and not in the bundled list of common passwords
(``resources/common_passwords.txt``, SecLists, MIT); no composition rules. It applies when a
password is set; existing hashes keep working.
"""

from __future__ import annotations

import hashlib
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from importlib.resources import files
from typing import Annotated, Literal, Protocol

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session as DbSession

from solidaritynode_backend.config import Settings, get_settings
from solidaritynode_backend.db import get_session
from solidaritynode_backend.orm import Session, User

__all__ = [
    "COOKIE_NAME",
    "MIN_PASSWORD_LENGTH",
    "ROLES",
    "CurrentUser",
    "IdentityProvider",
    "LocalIdentityProvider",
    "PasswordPolicyError",
    "Principal",
    "Role",
    "check_password",
    "create_user",
    "ensure_not_last_admin",
    "get_identity_provider",
    "hash_password",
    "require_role",
    "verify_password",
]

Role = Literal["admin", "analyst", "viewer"]
ROLES: tuple[Role, ...] = ("admin", "analyst", "viewer")
COOKIE_NAME = "sn_session"
MIN_PASSWORD_LENGTH = 12

_hasher = PasswordHasher()


class PasswordPolicyError(ValueError):
    """A new password does not meet the policy (the message says why)."""


@lru_cache
def _common_passwords() -> frozenset[str]:
    text = (
        files("solidaritynode_backend")
        .joinpath("resources/common_passwords.txt")
        .read_text(encoding="utf-8")
    )
    return frozenset(
        line.strip().casefold() for line in text.splitlines() if line and not line.startswith("#")
    )


def check_password(password: str) -> None:
    """Check a new password against the policy (ADR 0015).

    Raises:
        PasswordPolicyError: If it is shorter than 12 characters or a common password.
    """
    if len(password) < MIN_PASSWORD_LENGTH:
        raise PasswordPolicyError(f"password must have at least {MIN_PASSWORD_LENGTH} characters")
    if password.strip().casefold() in _common_passwords():
        raise PasswordPolicyError(
            "this password is on the list of commonly used passwords; choose another one"
        )


def hash_password(password: str) -> str:
    """Return the Argon2id hash of a new ``password`` after checking the policy."""
    check_password(password)
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    """Return whether ``password`` matches ``password_hash``."""
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class Principal:
    """The authenticated user of a request."""

    id: int
    username: str
    role: Role

    @property
    def is_admin(self) -> bool:
        """Return whether the user is an administrator."""
        return self.role == "admin"

    @property
    def can_edit(self) -> bool:
        """Return whether the user may create and run scenarios (analyst or admin)."""
        return self.role in ("admin", "analyst")


def _principal(user: User) -> Principal:
    return Principal(user.id, user.username, user.role)  # type: ignore[arg-type]


class IdentityProvider(Protocol):
    """Resolve who is calling, and start or end a session (ADR 0015)."""

    def login(self, db: DbSession, username: str, password: str) -> tuple[Principal, str] | None:
        """Check credentials; return the principal and a session token, or ``None``."""
        ...

    def logout(self, db: DbSession, token: str) -> None:
        """End the session of ``token``."""
        ...

    def resolve(self, db: DbSession, token: str | None) -> Principal | None:
        """Return the principal of a session token, or ``None``."""
        ...


class LocalIdentityProvider:
    """Local accounts with Argon2id hashes and server-side sessions."""

    def __init__(self, session_hours: float) -> None:
        """Configure the session lifetime."""
        self._lifetime = timedelta(hours=session_hours)

    def login(self, db: DbSession, username: str, password: str) -> tuple[Principal, str] | None:
        """Check credentials and create a session."""
        user = db.scalar(select(User).where(User.username == username))
        if user is None or not user.active:
            # Hash anyway so timing does not reveal which usernames exist.
            verify_password(_DUMMY_HASH, password)
            return None
        if not verify_password(user.password_hash, password):
            return None
        token = secrets.token_urlsafe(32)
        now = datetime.now(UTC)
        db.add(
            Session(token_hash=_token_hash(token), user_id=user.id, expires_at=now + self._lifetime)
        )
        db.execute(delete(Session).where(Session.expires_at < now))
        db.commit()
        return _principal(user), token

    def logout(self, db: DbSession, token: str) -> None:
        """Delete the session."""
        db.execute(delete(Session).where(Session.token_hash == _token_hash(token)))
        db.commit()

    def resolve(self, db: DbSession, token: str | None) -> Principal | None:
        """Return the active user of a valid, unexpired session."""
        if not token:
            return None
        row = db.execute(
            select(User)
            .join(Session, Session.user_id == User.id)
            .where(Session.token_hash == _token_hash(token))
            .where(Session.expires_at > datetime.now(UTC))
            .where(User.active)
        ).scalar_one_or_none()
        return _principal(row) if row else None


_DUMMY_HASH = _hasher.hash("timing-equaliser")


def get_identity_provider(
    settings: Annotated[Settings, Depends(get_settings)],
) -> IdentityProvider:
    """Return the configured identity provider (only ``local`` in v0.1)."""
    return LocalIdentityProvider(settings.session_hours)


def current_user(
    request: Request,
    db: Annotated[DbSession, Depends(get_session)],
    idp: Annotated[IdentityProvider, Depends(get_identity_provider)],
) -> Principal:
    """FastAPI dependency: the logged-in user, or 401."""
    principal = idp.resolve(db, request.cookies.get(COOKIE_NAME))
    if principal is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "login required")
    return principal


CurrentUser = Annotated[Principal, Depends(current_user)]


def require_role(*roles: Role) -> Callable[[Principal], Principal]:
    """Return a dependency that allows only ``roles`` (403 otherwise)."""

    def check(user: CurrentUser) -> Principal:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"requires role {' or '.join(roles)}")
        return user

    return check


def create_user(db: DbSession, username: str, password: str, role: Role) -> User:
    """Create a local account (caller commits).

    Raises:
        ValueError: On an unknown role or existing username.
        PasswordPolicyError: If the password does not meet the policy.
    """
    if role not in ROLES:
        raise ValueError(f"unknown role {role!r}")
    if db.scalar(select(User.id).where(User.username == username)) is not None:
        raise ValueError(f"user {username!r} already exists")
    user = User(username=username, password_hash=hash_password(password), role=role, active=True)
    db.add(user)
    db.flush()
    return user


def ensure_not_last_admin(
    db: DbSession, user: User, new_role: Role | None, new_active: bool | None
) -> None:
    """Refuse a change that would leave no active administrator (ADR 0015).

    The active admin rows are locked (``FOR UPDATE``) until the caller commits, so two admins
    demoting each other at the same time cannot both succeed.

    Raises:
        ValueError: If ``user`` is the last active admin and would be demoted or disabled.
    """
    demoted = new_role is not None and new_role != "admin"
    disabled = new_active is False
    if user.role != "admin" or not user.active or not (demoted or disabled):
        return
    admins = db.scalars(
        select(User.id).where(User.role == "admin", User.active).with_for_update()
    ).all()
    if not set(admins) - {user.id}:
        raise ValueError("the last active administrator cannot be disabled or demoted")

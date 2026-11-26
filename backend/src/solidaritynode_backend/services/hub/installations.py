"""Registry of municipal installations and their tokens (ADR 0014 Part A, A2).

A hub administrator registers each installation (name, the one study area it serves) and
issues a token, shown once. The hub keeps only:

* ``token_hash = SHA-256(token)``, to authenticate the installation's API calls;
* ``offline_key = HMAC-SHA256(key=token, msg=OFFLINE_KEY_LABEL)``, to verify its offline
  submission files.

Neither gives back the token. Someone who reads the hub database could forge offline files for
an installation (they still go through validation and a hub administrator's review, marked
offline) but not call the API as it. Issuing a new token revokes the old one at once.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from solidaritynode_backend.services.hub.common import HubError

__all__ = [
    "OFFLINE_KEY_LABEL",
    "authenticate",
    "issue_token",
    "list_installations",
    "offline_key",
    "register_installation",
    "revoke",
    "token_hash",
]

OFFLINE_KEY_LABEL = b"solidaritynode offline submission v1"
TOKEN_PREFIX = "sn_inst_"


def token_hash(token: str) -> str:
    """Return the SHA-256 of a token, as stored to authenticate API calls."""
    return hashlib.sha256(token.encode()).hexdigest()


def offline_key(token: str) -> str:
    """Return the key that signs and verifies offline submission files (hex)."""
    return hmac.new(token.encode(), OFFLINE_KEY_LABEL, hashlib.sha256).hexdigest()


_COLUMNS = (
    "i.id, i.name, i.study_area_id, i.token_issued_at, i.revoked_at, i.last_contact_at, "
    "i.last_contact_address, i.created_at, (i.token_hash IS NOT NULL AND i.revoked_at IS NULL) "
    "AS active, EXISTS (SELECT 1 FROM hub_study_areas a WHERE a.id = i.study_area_id) "
    "AS study_area_registered"
)


def list_installations(db: Session) -> list[dict[str, Any]]:
    """Return every registered installation (never a token)."""
    return [
        dict(r)
        for r in db.execute(
            text(f"SELECT {_COLUMNS} FROM hub_installations i ORDER BY i.name")
        ).mappings()
    ]


def get_installation(db: Session, installation_id: uuid.UUID) -> dict[str, Any]:
    """Return one installation.

    Raises:
        HubError: If it does not exist.
    """
    row = (
        db.execute(
            text(f"SELECT {_COLUMNS} FROM hub_installations i WHERE i.id = :i"),
            {"i": installation_id},
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise HubError("hub.installation.not_found", status=404, id=installation_id)
    return dict(row)


def register_installation(
    db: Session,
    name: str,
    study_area_id: str,
    user_id: int | None,
    *,
    token: str | None = None,
    require_study_area: bool = True,
) -> tuple[dict[str, Any], str]:
    """Register an installation and issue its first token; return the row and the token.

    Args:
        db: Session (the caller commits).
        name: Installation name, unique.
        study_area_id: The one study area it serves.
        user_id: Hub administrator.
        token: A given token (development provisioning only, ``make uat-hub``); otherwise one
            is generated.
        require_study_area: Refuse an unknown study area (the screen always does; development
            provisioning may register before the study area exists).

    Raises:
        HubError: On a duplicate name or an unknown study area.
    """
    if (
        require_study_area
        and not db.execute(
            text("SELECT 1 FROM hub_study_areas WHERE id = :s"), {"s": study_area_id}
        ).first()
    ):
        raise HubError("hub.error.study_area_not_found", status=404, id=study_area_id)
    if db.execute(text("SELECT 1 FROM hub_installations WHERE name = :n"), {"n": name}).first():
        raise HubError("hub.installation.exists", status=409, name=name)
    installation_id = uuid.uuid4()
    db.execute(
        text(
            "INSERT INTO hub_installations (id, name, study_area_id, created_by) "
            "VALUES (:i, :n, :s, :u)"
        ),
        {"i": installation_id, "n": name, "s": study_area_id, "u": user_id},
    )
    issued = issue_token(db, installation_id, token=token)
    return get_installation(db, installation_id), issued


def issue_token(db: Session, installation_id: uuid.UUID, *, token: str | None = None) -> str:
    """Issue a new token (shown once); the previous token stops working at once."""
    get_installation(db, installation_id)
    token = token or TOKEN_PREFIX + secrets.token_urlsafe(32)
    db.execute(
        text(
            "UPDATE hub_installations SET token_hash = :h, offline_key = :k, "
            "token_issued_at = now(), revoked_at = NULL WHERE id = :i"
        ),
        {"h": token_hash(token), "k": offline_key(token), "i": installation_id},
    )
    return token


def revoke(db: Session, installation_id: uuid.UUID) -> None:
    """Revoke the installation's token at once."""
    get_installation(db, installation_id)
    db.execute(
        text("UPDATE hub_installations SET revoked_at = now() WHERE id = :i"),
        {"i": installation_id},
    )


def authenticate(db: Session, token: str, address: str | None) -> dict[str, Any]:
    """Return the installation of a token and record the contact.

    Raises:
        HubError: 401 with one generic message for a missing, unknown or revoked token.
    """
    row = (
        db.execute(
            text("SELECT * FROM hub_installations WHERE token_hash = :h AND revoked_at IS NULL"),
            {"h": token_hash(token)},
        )
        .mappings()
        .one_or_none()
        if token
        else None
    )
    if row is None:
        raise HubError("hub.installation.unauthorised", status=401)
    db.execute(
        text(
            "UPDATE hub_installations SET last_contact_at = :t, last_contact_address = :a "
            "WHERE id = :i"
        ),
        {"t": datetime.now(UTC), "a": address, "i": row["id"]},
    )
    return dict(row)

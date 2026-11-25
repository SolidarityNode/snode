"""Installation role: lock and separation (ADR 0012).

One database serves **one** role, ``municipality`` or ``hub``. The role is recorded in table
``installation`` when the database is first initialised (migration 0007, from
``DEPLOYMENT_MODE``). The API, the worker and the CLI call :func:`check_role` on start and refuse
to run when ``DEPLOYMENT_MODE`` differs.

Role separation:

* **routers** of the other role are not mounted at all (``main.create_app``), so their paths
  answer 404 and do not appear in the OpenAPI schema;
* **tables** of one role are created only by migrations guarded with :func:`stored_role`, for
  example ``if stored_role(op.get_bind()) != "municipality": return`` in a future ticket
  migration (tickets are municipality-only; none are stored yet, ADR 0010).
"""

from __future__ import annotations

from sqlalchemy import Connection, Engine, text

from solidaritynode_backend.config import DeploymentMode

__all__ = [
    "HUB_ONLY_TABLES",
    "MUNICIPALITY_ONLY_TABLES",
    "RoleMismatchError",
    "check_role",
    "stored_role",
]

MUNICIPALITY_ONLY_TABLES: tuple[str, ...] = ()
"""Tables that exist only in municipal installations (tickets will be added here, ADR 0010)."""
HUB_ONLY_TABLES: tuple[str, ...] = ()
"""Tables that exist only in the hub (onboarding will be added here)."""


class RoleMismatchError(RuntimeError):
    """``DEPLOYMENT_MODE`` differs from the role recorded in the database."""


def stored_role(conn: Connection) -> str | None:
    """Return the role recorded in the database, or ``None`` if none is recorded yet."""
    return conn.execute(
        text("SELECT deployment_mode FROM installation WHERE id = 1")
    ).scalar_one_or_none()


def check_role(engine: Engine, mode: DeploymentMode) -> str:
    """Compare ``DEPLOYMENT_MODE`` with the stored role; record it if none is stored yet.

    Returns:
        The role in force.

    Raises:
        RoleMismatchError: If the database was initialised for the other role.
    """
    with engine.begin() as conn:
        role = stored_role(conn)
        if role is None:
            conn.execute(
                text("INSERT INTO installation (deployment_mode) VALUES (:m)"), {"m": mode}
            )
            return mode
    if role != mode:
        raise RoleMismatchError(
            f"This database was initialised for a {role!r} installation, but DEPLOYMENT_MODE is "
            f"{mode!r}. Refusing to start: one database serves one role (ADR 0012). Set "
            f"DEPLOYMENT_MODE={role}, or use a new database for the {mode} role."
        )
    return role

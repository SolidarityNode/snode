"""Login throttling per account and per client address (ADR 0015).

After a failed sign-in, the next attempt for the same username is refused for an increasing
delay (``login_delay_base_s × 2^(n-1)``, capped). A client address gets the same increasing
delay only from half its limit on (so one person's typo does not delay colleagues behind the
same office address), and after
``login_max_failures_account`` (per username) or ``login_max_failures_address`` (per address)
failures within ``login_lock_minutes`` the key is locked for that long. While a key is delayed
or locked, credentials are **not checked** and the answer is the same generic 429 for existing
and unknown usernames, so throttling reveals nothing about which accounts exist. A successful
sign-in clears the username and the address.

Keys are stored as SHA-256 hashes (migration 0009). The client address is the peer address
the API sees; behind the bundled nginx it is the browser's address (nginx overwrites
``X-Forwarded-For``, and uvicorn trusts it only from the addresses in ``FORWARDED_ALLOW_IPS``).
"""

from __future__ import annotations

import hashlib
import math
from datetime import UTC, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.orm import Session

from solidaritynode_backend.config import Settings

__all__ = ["Throttle", "throttle_keys"]


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def throttle_keys(username: str, address: str | None) -> list[tuple[str, str]]:
    """Return the ``(kind, key hash)`` pairs a sign-in attempt is counted against."""
    keys = [("account", _hash(username.strip().casefold()))]
    if address:
        keys.append(("address", _hash(address)))
    return keys


class Throttle:
    """Check and record sign-in attempts in table ``login_throttle``."""

    def __init__(self, settings: Settings) -> None:
        """Use the limits of ``settings``."""
        self._limits = {
            "account": settings.login_max_failures_account,
            "address": settings.login_max_failures_address,
        }
        self._window = timedelta(minutes=settings.login_lock_minutes)
        self._base = settings.login_delay_base_s
        self._max = settings.login_delay_max_s
        # Failure count from which each kind is delayed (addresses: half their lock limit).
        self._delay_from = {
            "account": 1,
            "address": max(1, -(-settings.login_max_failures_address // 2)),
        }

    def retry_after(self, db: Session, keys: list[tuple[str, str]]) -> int:
        """Return the seconds to wait before an attempt is allowed (0: allowed now)."""
        now = datetime.now(UTC)
        db.execute(
            text(
                "DELETE FROM login_throttle WHERE last_failure_at < :old "
                "AND (locked_until IS NULL OR locked_until < :now)"
            ),
            {"old": now - self._window, "now": now},
        )
        wait = 0.0
        for kind, key in keys:
            row = db.execute(
                text(
                    "SELECT next_allowed_at, locked_until FROM login_throttle "
                    "WHERE kind = :k AND key_hash = :h"
                ),
                {"k": kind, "h": key},
            ).one_or_none()
            if row is None:
                continue
            for until in (row.next_allowed_at, row.locked_until):
                if until is not None and until > now:
                    wait = max(wait, (until - now).total_seconds())
        return math.ceil(wait)

    def failure(self, db: Session, keys: list[tuple[str, str]]) -> None:
        """Record a failed attempt for every key (caller commits)."""
        now = datetime.now(UTC)
        for kind, key in keys:
            row = db.execute(
                text(
                    "SELECT failures, last_failure_at FROM login_throttle "
                    "WHERE kind = :k AND key_hash = :h FOR UPDATE"
                ),
                {"k": kind, "h": key},
            ).one_or_none()
            failures = 1
            if row is not None and row.last_failure_at >= now - self._window:
                failures = row.failures + 1
            start = self._delay_from[kind]
            delay = (
                min(self._base * 2 ** (failures - start), self._max)
                if self._base and failures >= start
                else 0.0
            )
            locked = now + self._window if failures >= self._limits[kind] else None
            db.execute(
                text(
                    """
                    INSERT INTO login_throttle
                        (kind, key_hash, failures, last_failure_at, next_allowed_at, locked_until)
                    VALUES (:k, :h, :f, :now, :next, :locked)
                    ON CONFLICT (kind, key_hash) DO UPDATE SET failures = :f,
                        last_failure_at = :now, next_allowed_at = :next, locked_until = :locked
                    """
                ),
                {
                    "k": kind,
                    "h": key,
                    "f": failures,
                    "now": now,
                    "next": now + timedelta(seconds=delay),
                    "locked": locked,
                },
            )

    def success(self, db: Session, keys: list[tuple[str, str]]) -> None:
        """Forget the failures of every key after a successful sign-in (caller commits)."""
        for kind, key in keys:
            db.execute(
                text("DELETE FROM login_throttle WHERE kind = :k AND key_hash = :h"),
                {"k": kind, "h": key},
            )

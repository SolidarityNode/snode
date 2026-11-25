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

Keys are stored as SHA-256 hashes (migration 0009). A refused (429) attempt is not a failure:
it neither counts nor extends a delay or lock, so a lock ends at the stated time.

**Client address** (:func:`client_address`): the peer address of the connection, unless the
peer is a trusted proxy (``SOLIDARITYNODE_TRUSTED_PROXIES``); then ``X-Real-IP`` (or the
nearest untrusted ``X-Forwarded-For`` entry) set by that proxy. If what the proxy reports is
itself a proxy address, the proxy could not see the client: behind rootless Podman's port
forwarder every browser reaches nginx from nginx's own address. Counting those together would
let one person's typos lock out everyone, so the address is then **unknown** and only the
per-username limit applies (a warning is logged once).
"""

from __future__ import annotations

import hashlib
import logging
import math
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from ipaddress import IPv4Network, IPv6Network, ip_address

from sqlalchemy import text
from sqlalchemy.orm import Session

from solidaritynode_backend.config import Settings

__all__ = ["Throttle", "client_address", "throttle_keys"]

_log = logging.getLogger(__name__)
_warned = False


def _trusted(address: str, networks: Sequence[IPv4Network | IPv6Network]) -> bool | None:
    """Whether ``address`` is in ``networks``; ``None`` if it is not an IP address."""
    try:
        ip = ip_address(address.strip())
    except ValueError:
        return None
    return any(ip in network for network in networks)


def client_address(
    peer: str | None,
    x_real_ip: str | None,
    x_forwarded_for: str | None,
    trusted: Sequence[IPv4Network | IPv6Network],
) -> str | None:
    """Return the client address for per-address throttling, or ``None`` if it is unknown.

    Args:
        peer: Address of the TCP peer (``request.client.host``).
        x_real_ip: ``X-Real-IP`` header, used only when ``peer`` is a trusted proxy.
        x_forwarded_for: ``X-Forwarded-For`` header, used only when ``peer`` is a trusted proxy
            and ``X-Real-IP`` is absent (its nearest entry that is not a trusted proxy).
        trusted: Networks of the trusted reverse proxies (``Settings.trusted_networks``).

    Returns:
        The client's address; ``None`` when there is no peer, when a trusted proxy sends no
        usable header, or when the address it reports is itself a proxy address (it could not
        see the client).
    """
    global _warned
    if peer is None:
        return None
    if not _trusted(peer, trusted):
        return peer  # a direct client: its headers are never trusted
    candidate: str | None = None
    if x_real_ip and x_real_ip.strip():
        candidate = x_real_ip.strip()
    elif x_forwarded_for:
        for hop in reversed([h.strip() for h in x_forwarded_for.split(",") if h.strip()]):
            candidate = hop
            if not _trusted(hop, trusted):
                break
    if candidate is None or _trusted(candidate, trusted) is not False:
        if candidate is not None and not _warned:
            _warned = True
            _log.warning(
                "sign-in throttling: the proxy reports client address %s, itself a trusted "
                "proxy address, so client addresses are not visible (for example behind "
                "rootless Podman's port forwarder); only per-username limits apply (ADR 0015)",
                candidate,
            )
        return None
    return candidate


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

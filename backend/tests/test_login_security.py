"""Sign-in throttling, Secure cookie in production, last admin and password policy (ADR 0015)."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from solidaritynode_backend.auth import PasswordPolicyError, check_password, ensure_not_last_admin
from solidaritynode_backend.orm import User
from tests.conftest import PASSWORDS, login


def _app(settings: Any, **limits: Any) -> Any:
    from solidaritynode_backend.config import get_settings
    from solidaritynode_backend.main import create_app

    configured = settings.model_copy(update=limits)
    app = create_app(configured)
    app.dependency_overrides[get_settings] = lambda: configured
    return app


def _try(client: TestClient, username: str, password: str) -> Any:
    return client.post("/auth/login", json={"username": username, "password": password})


# --- 1. Throttling -------------------------------------------------------------------------------


def test_account_is_locked_after_repeated_failures_with_generic_messages(
    settings: Any, users: Any
) -> None:
    app = _app(settings, login_max_failures_account=3, login_delay_base_s=0)
    client = TestClient(app)
    for _ in range(3):
        wrong = _try(client, "analyst", "wrong-password-1")
        assert (wrong.status_code, wrong.json()["detail"]) == (401, "wrong username or password")
    locked = _try(client, "analyst", PASSWORDS["analyst"])  # even the right password
    assert locked.status_code == 429
    assert locked.json()["detail"] == "too many failed sign-in attempts; try again later"
    assert int(locked.headers["Retry-After"]) > 0
    # An unknown username behaves exactly the same: same messages, same lock.
    for _ in range(3):
        unknown = _try(client, "nobody-here", "wrong-password-1")
        assert (unknown.status_code, unknown.json()["detail"]) == (401, wrong.json()["detail"])
    assert _try(client, "nobody-here", "x" * 12).json()["detail"] == locked.json()["detail"]
    # Another account from the same address is not affected (address limit not reached).
    assert _try(client, "viewer", PASSWORDS["viewer"]).status_code == 200


def test_client_address_is_locked_across_usernames(settings: Any, users: Any) -> None:
    app = _app(
        settings, login_max_failures_account=100, login_max_failures_address=4, login_delay_base_s=0
    )
    client = TestClient(app)
    for name in ("a1", "a2", "a3", "a4"):
        assert _try(client, name, "wrong-password-1").status_code == 401
    assert _try(client, "admin", PASSWORDS["admin"]).status_code == 429


def test_increasing_delay_between_failures(settings: Any, users: Any, engine: Any) -> None:
    app = _app(settings, login_delay_base_s=10, login_delay_max_s=25)
    client = TestClient(app)
    assert _try(client, "analyst", "wrong-password-1").status_code == 401
    delayed = _try(client, "analyst", PASSWORDS["analyst"])
    assert delayed.status_code == 429
    assert 1 <= int(delayed.headers["Retry-After"]) <= 10
    with engine.begin() as conn:  # the delay has passed
        conn.execute(text("UPDATE login_throttle SET next_allowed_at = now() - interval '1 s'"))
    assert _try(client, "analyst", "wrong-password-2").status_code == 401
    with engine.connect() as conn:
        waits = conn.execute(
            text("SELECT extract(epoch FROM next_allowed_at - last_failure_at) FROM login_throttle")
        ).scalars()
        assert sorted(round(float(w)) for w in waits) == [0, 20]  # account 10 × 2; address none
    with engine.begin() as conn:
        conn.execute(text("UPDATE login_throttle SET next_allowed_at = now() - interval '1 s'"))
    assert _try(client, "analyst", PASSWORDS["analyst"]).status_code == 200
    with engine.connect() as conn:  # success forgets the failures
        assert conn.execute(text("SELECT count(*) FROM login_throttle")).scalar_one() == 0


def test_one_users_typo_does_not_delay_others_at_the_same_address(
    settings: Any, users: Any
) -> None:
    app = _app(settings, login_delay_base_s=10, login_max_failures_address=6)
    client = TestClient(app)
    assert _try(client, "analyst", "wrong-password-1").status_code == 401
    assert _try(client, "viewer", PASSWORDS["viewer"]).status_code == 200  # no address delay
    for name in ("b1", "b2"):  # address failures 1 to 3 (the viewer's success reset it)
        assert _try(client, name, "wrong-password-1").status_code == 401
    assert _try(client, "b3", "wrong-password-1").status_code == 401  # 3rd: delay starts (6 / 2)
    assert _try(client, "admin", PASSWORDS["admin"]).status_code == 429  # address delayed now


def test_lock_expires(settings: Any, users: Any, engine: Any) -> None:
    app = _app(settings, login_max_failures_account=2, login_delay_base_s=0)
    client = TestClient(app)
    for _ in range(2):
        _try(client, "analyst", "wrong-password-1")
    assert _try(client, "analyst", PASSWORDS["analyst"]).status_code == 429
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE login_throttle SET locked_until = now() - interval '1 s', "
                "last_failure_at = now() - interval '1 hour'"
            )
        )
    assert _try(client, "analyst", PASSWORDS["analyst"]).status_code == 200


def test_attempted_usernames_and_addresses_are_stored_only_as_hashes(
    settings: Any, users: Any, engine: Any
) -> None:
    client = TestClient(_app(settings))
    _try(client, "typo-Secret-Passw0rd", "wrong-password-1")
    with engine.connect() as conn:
        stored = " ".join(
            str(v) for row in conn.execute(text("SELECT * FROM login_throttle")) for v in row
        )
    assert "typo" not in stored.lower()
    assert "testclient" not in stored


NGINX = ("10.89.0.6", 40000)  # the bundled proxy on the compose network


def _via_proxy(app: Any) -> TestClient:
    return TestClient(app, client=NGINX)


def _proxied(client: TestClient, username: str, password: str, browser: str) -> Any:
    return client.post(
        "/auth/login",
        json={"username": username, "password": password},
        headers={"X-Real-IP": browser, "X-Forwarded-For": browser},
    )


@pytest.mark.parametrize(
    ("peer", "real_ip", "forwarded", "expected"),
    [
        ("203.0.113.9", "198.51.100.1", None, "203.0.113.9"),  # direct client: headers ignored
        ("10.89.0.6", "198.51.100.1", None, "198.51.100.1"),  # trusted proxy: X-Real-IP
        ("10.89.0.6", None, "198.51.100.7, 10.0.0.3", "198.51.100.7"),  # nearest untrusted hop
        ("10.89.0.6", "10.89.0.6", None, None),  # proxy reports itself: unknown (rootless Podman)
        ("10.89.0.6", None, None, None),  # trusted proxy without headers: unknown
        ("10.89.0.6", "not-an-address", None, None),
        (None, None, None, None),
    ],
)
def test_client_address_only_from_trusted_proxies(
    peer: str | None, real_ip: str | None, forwarded: str | None, expected: str | None
) -> None:
    from solidaritynode_backend.config import Settings
    from solidaritynode_backend.services.throttle import client_address

    trusted = Settings().trusted_networks()
    assert client_address(peer, real_ip, forwarded, trusted) == expected


def test_step_4a_through_a_proxy_that_hides_client_addresses(settings: Any, users: Any) -> None:
    """UAT 4a behind rootless Podman: nginx reports its own address for every browser.

    Counting that address would lock out everyone; it is treated as unknown, so a wrong username
    tried six times never blocks another user, even with a tiny address limit.
    """
    app = _app(settings, login_max_failures_account=5, login_max_failures_address=2)
    client = _via_proxy(app)
    answers = [_proxied(client, "uat-nobody", "wrong-password-1", NGINX[0]) for _ in range(6)]
    assert [a.status_code for a in answers] == [401] * 5 + [429]
    assert _proxied(client, "analyst", PASSWORDS["analyst"], NGINX[0]).status_code == 200


def test_proxy_forwarded_addresses_are_throttled_separately(settings: Any, users: Any) -> None:
    app = _app(settings, login_max_failures_account=100, login_max_failures_address=3)
    client = _via_proxy(app)
    for name in ("c1", "c2", "c3"):
        assert _proxied(client, name, "wrong-password-1", "198.51.100.1").status_code == 401
    assert _proxied(client, "admin", PASSWORDS["admin"], "198.51.100.1").status_code == 429
    # Another browser behind the same proxy is not affected.
    assert _proxied(client, "admin", PASSWORDS["admin"], "198.51.100.2").status_code == 200


def test_client_cannot_spoof_its_address(settings: Any, users: Any) -> None:
    """A client that is not a trusted proxy cannot pick a fresh address per attempt."""
    app = _app(settings, login_max_failures_account=100, login_max_failures_address=2)
    client = TestClient(app, client=("203.0.113.9", 5000))
    for i in range(2):
        assert _proxied(client, f"d{i}", "wrong-password-1", f"198.51.100.{i}").status_code == 401
    assert _proxied(client, "admin", PASSWORDS["admin"], "198.51.100.99").status_code == 429


def test_refused_attempts_do_not_extend_the_lock(settings: Any, users: Any, engine: Any) -> None:
    app = _app(settings, login_max_failures_account=2, login_delay_base_s=0)
    client = TestClient(app)
    for _ in range(2):
        _try(client, "analyst", "wrong-password-1")
    query = text("SELECT kind, failures, locked_until, next_allowed_at FROM login_throttle")
    with engine.connect() as conn:
        before = sorted(conn.execute(query).all())
    for _ in range(5):  # refused while locked: neither counted nor extending the lock
        assert _try(client, "analyst", "wrong-password-1").status_code == 429
    with engine.connect() as conn:
        assert sorted(conn.execute(query).all()) == before
    account = next(row for row in before if row.kind == "account")
    minutes = (account.locked_until - account.next_allowed_at).total_seconds() / 60
    assert round(minutes) == settings.login_lock_minutes  # the stated 15 minutes


def test_clear_login_locks_command(
    settings: Any, users: Any, engine: Any, monkeypatch: Any, capsys: Any
) -> None:
    from solidaritynode_backend import cli

    app = _app(settings, login_max_failures_account=1)
    client = TestClient(app)
    _try(client, "analyst", "wrong-password-1")
    _try(client, "viewer", "wrong-password-1")
    assert _try(client, "analyst", PASSWORDS["analyst"]).status_code == 429
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    monkeypatch.setattr(cli, "check_role", lambda *_: None)
    assert cli.main(["clear-login-locks", "--username", "Analyst"]) == 0
    assert "Cleared 1 " in capsys.readouterr().out
    assert _try(client, "viewer", PASSWORDS["viewer"]).status_code == 429  # still locked
    assert cli.main(["clear-login-locks", "--all"]) == 0
    assert _try(client, "viewer", PASSWORDS["viewer"]).status_code == 200
    assert _try(client, "analyst", PASSWORDS["analyst"]).status_code == 200


# --- 2. Secure cookie in production -----------------------------------------------------------


def test_session_cookie_is_secure_in_production(settings: Any, users: Any) -> None:
    app = _app(settings, app_env="production", session_cookie_secure=False)
    response = _try(TestClient(app), "analyst", PASSWORDS["analyst"])
    assert response.status_code == 200
    cookie = response.headers["set-cookie"]
    assert "Secure" in cookie
    assert "HttpOnly" in cookie
    plain = _try(TestClient(_app(settings)), "viewer", PASSWORDS["viewer"])
    assert "Secure" not in plain.headers["set-cookie"]  # development over http


# --- 3. Last active admin ---------------------------------------------------------------------


def test_last_active_admin_cannot_be_disabled_or_demoted(db: Session, users: Any) -> None:
    admin = db.get(User, users["admin"])
    assert admin is not None
    with pytest.raises(ValueError, match="last active administrator"):
        ensure_not_last_admin(db, admin, None, False)
    with pytest.raises(ValueError, match="last active administrator"):
        ensure_not_last_admin(db, admin, "analyst", None)
    ensure_not_last_admin(db, admin, "admin", True)  # no change of role or status
    db.rollback()
    second = db.get(User, users["analyst2"])
    assert second is not None
    second.role = "admin"
    db.commit()
    ensure_not_last_admin(db, admin, "viewer", None)  # another active admin exists
    db.rollback()
    second.active = False
    db.commit()
    with pytest.raises(ValueError, match="last active administrator"):
        ensure_not_last_admin(db, admin, None, False)  # the other admin is disabled


def test_admins_api_keeps_one_active_admin(app: Any, users: Any) -> None:
    client = login(app, "admin")
    me = client.get("/auth/me").json()
    response = client.patch(f"/users/{me['id']}", json={"role": "viewer"})
    assert response.status_code == 409
    other = client.post(
        "/users", json={"username": "admin-two", "password": "second-admin-pass", "role": "admin"}
    ).json()
    assert client.patch(f"/users/{other['id']}", json={"active": False}).status_code == 200


# --- 4. Password policy -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("password", "message"),
    [
        ("eleven-char", "at least 12 characters"),
        ("qwerty123456", "commonly used passwords"),
        ("QWERTY123456", "commonly used passwords"),  # case does not matter
        ("1q2w3e4r5t6y", "commonly used passwords"),
    ],
)
def test_password_policy_refuses_short_and_common_passwords(password: str, message: str) -> None:
    with pytest.raises(PasswordPolicyError, match=message):
        check_password(password)


def test_password_policy_has_no_composition_rules() -> None:
    check_password("correct horse battery staple")  # only letters and spaces: fine
    check_password("a" * 12 + "z")


def test_api_and_cli_apply_the_policy(app: Any, users: Any, monkeypatch: Any, capsys: Any) -> None:
    client = login(app, "admin")
    common = client.post(
        "/users", json={"username": "new-user", "password": "qwerty123456", "role": "viewer"}
    )
    assert common.status_code == 422
    assert "commonly used passwords" in common.json()["detail"]
    short = client.post(
        "/users", json={"username": "new-user", "password": "short-pass1", "role": "viewer"}
    )
    assert short.status_code == 422  # rejected by the schema (min 12)
    me = client.get("/auth/me").json()
    change = client.patch(f"/users/{me['id']}", json={"password": "1qaz2wsx3edc"})
    assert change.status_code == 422

    from solidaritynode_backend import cli

    answers = iter(["qwerty123456", "qwerty123456"])
    monkeypatch.setattr("builtins.input", lambda _: "new-admin")
    monkeypatch.setattr(cli.getpass, "getpass", lambda _: next(answers))
    assert cli.create_admin(cli.get_settings()) == 1
    assert "commonly used passwords" in capsys.readouterr().err

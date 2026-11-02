"""Phase 2 authentication, session, CSRF and rate-limit behaviour.

These run against the real database and the real HTTP stack. A mocked repository
would prove the wiring and nothing else, and it is precisely these endpoints where
a session bug becomes a security problem.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from tests.conftest import Session, signed_in_client


def test_register_returns_no_secrets(make_account: Callable[[], Session]) -> None:
    account = make_account()
    assert account.user_id
    body = account.api.get("/api/v1/auth/session").json()
    assert "password_hash" not in str(body)
    assert "session_token" not in str(body)


def test_duplicate_email_is_rejected_case_insensitively(
    make_account: Callable[[], Session],
) -> None:
    """Mailboxes are case-insensitive. Accepting 'A@x' and 'a@x' as two accounts
    would give two owners claims over the same identity."""
    account = make_account()
    duplicate = account.api.post(
        "/api/v1/auth/register",
        json={
            "email": account.email.upper(),
            "password": "another-long-password",
            "display_name": "Duplicate",
        },
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "conflict"


def test_password_below_the_configured_minimum_is_refused(
    make_account: Callable[[], Session],
) -> None:
    account = make_account()
    response = account.api.post(
        "/api/v1/auth/register",
        json={
            "email": f"weak-{account.user_id[:8]}@sparkxflow.dev",
            "password": "ten-chars!",
            "display_name": "Weak",
        },
    )
    assert response.status_code == 400
    assert "12 characters" in response.json()["error"]["message"]


def test_login_sets_a_readable_session_cookie(make_account: Callable[[], Session]) -> None:
    account = make_account()
    assert account.api.cookies.get("sparkx_session")
    assert account.csrf


def test_wrong_password_and_unknown_email_are_indistinguishable(
    make_account: Callable[[], Session],
) -> None:
    """Same status, same body. Anything more specific tells an attacker which
    mailbox has an account."""
    account = make_account()
    wrong_password = account.api.post(
        "/api/v1/auth/login",
        json={"email": account.email, "password": "definitely-not-the-password"},
    )
    unknown_email = account.api.post(
        "/api/v1/auth/login",
        json={"email": f"ghost-{account.user_id[:8]}@nowhere.dev", "password": "whatever-123456"},
    )
    assert wrong_password.status_code == unknown_email.status_code == 401
    # Compare the security-relevant fields only. The correlation id differs per
    # request by design; comparing whole bodies would assert the opposite.
    assert wrong_password.json()["error"]["code"] == unknown_email.json()["error"]["code"]
    assert wrong_password.json()["error"]["message"] == unknown_email.json()["error"]["message"]


def test_session_endpoint_requires_a_valid_session(make_account: Callable[[], Session]) -> None:
    account = make_account()
    anonymous = signed_in_client()
    assert anonymous.get("/api/v1/auth/session").status_code == 401
    assert account.api.get("/api/v1/auth/session").json()["user"]["email"] == account.email


def test_logout_revokes_the_session_server_side(make_account: Callable[[], Session]) -> None:
    """Logout must invalidate the token in the database, not just clear cookies.

    Otherwise a client that kept a copy of the cookie stays authenticated — the
    'logout that only logs out the browser' failure.
    """
    account = make_account()
    stolen = account.api.cookies.get("sparkx_session")
    assert stolen

    assert (
        account.api.post("/api/v1/auth/logout", headers=account.csrf_headers()).status_code == 200
    )

    replay = signed_in_client()
    replay.cookies.set("sparkx_session", stolen)
    assert replay.get("/api/v1/auth/session").status_code == 401


def test_unsafe_request_without_a_csrf_header_is_rejected(
    make_account: Callable[[], Session],
) -> None:
    account = make_account()
    response = account.api.post(f"/api/v1/businesses/{account.user_id}/shortlist")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "permission_denied"


def test_csrf_header_must_pair_with_the_callers_own_cookie(
    make_account: Callable[[], Session],
) -> None:
    a = make_account()
    b = make_account()
    response = a.api.post(f"/api/v1/businesses/{a.user_id}/shortlist", headers=b.csrf_headers())
    assert response.status_code == 403


def test_forged_csrf_cookie_is_not_accepted(make_account: Callable[[], Session]) -> None:
    """The signature is checked, so an attacker-chosen cookie value cannot simply
    be echoed back to itself."""
    account = make_account()
    account.api.cookies.set("sparkx_csrf", "anything")
    response = account.api.post(
        f"/api/v1/businesses/{account.user_id}/shortlist",
        headers={"X-CSRF-Token": "anything"},
    )
    assert response.status_code == 403


def test_login_is_rate_limited_and_advertises_retry_after(
    make_account: Callable[[], Session],
) -> None:
    account = make_account()
    statuses = [
        account.api.post(
            "/api/v1/auth/login",
            json={"email": account.email, "password": f"wrong-password-{i}"},
        ).status_code
        for i in range(12)
    ]
    assert 429 in statuses

    limited = account.api.post(
        "/api/v1/auth/login",
        json={"email": account.email, "password": "wrong-password-final"},
    )
    assert limited.status_code == 429
    assert "Retry-After" in limited.headers
    assert limited.json()["error"]["code"] == "rate_limited"


def test_registration_can_be_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """A private tool should not offer open signup forever by default. When the
    operator closes it, the API refuses rather than accepting quietly."""
    monkeypatch.setenv("SPARKX_ALLOW_REGISTRATION", "false")
    from app.core.config import get_settings

    get_settings.cache_clear()

    api = signed_in_client()
    response = api.post(
        "/api/v1/auth/register",
        json={
            "email": "closed@sparkxflow.dev",
            "password": "long-enough-password",
            "display_name": "Closed",
        },
    )
    assert response.status_code == 403
    assert "disabled" in response.json()["error"]["message"]


def test_failed_login_is_written_to_the_audit_trail(make_account: Callable[[], Session]) -> None:
    """Whoever is guessing, the record says an address was probed. The row must
    not contain the password that was tried."""
    import asyncio

    import asyncpg

    from app.core.config import get_settings

    account = make_account()
    account.api.post(
        "/api/v1/auth/login",
        json={"email": account.email, "password": "wrong-password-for-audit"},
    )

    dsn = get_settings().database_url.replace("postgresql+asyncpg://", "postgresql://")

    async def read() -> list:
        connection = await asyncpg.connect(dsn=dsn, timeout=10)
        try:
            return await connection.fetch(
                "select action, metadata from audit_logs where action = 'auth.login_failed'"
            )
        finally:
            await connection.close()

    rows = asyncio.run(read())
    assert rows, "a failed login must leave an audit row"
    assert "wrong-password-for-audit" not in str(rows)

from __future__ import annotations

import secrets
from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends, Request, Response

from app.core.config import Settings, get_settings
from app.core.database import AsyncSessionDep
from app.core.exceptions import AuthenticationError, PermissionDeniedError
from app.core.security import sign_value, unsign_value
from app.modules.auth.models import User
from app.modules.auth.service import resolve_session

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})


def session_token_from_request(request: Request) -> str | None:
    settings = get_settings()
    token = request.cookies.get(settings.session_cookie_name)
    if token:
        return token
    # A bearer header is supported for scripted clients; the browser path is the
    # cookie. Both resolve through the same hashed-token lookup, so there is
    # only one session implementation to get wrong.
    authorization = request.headers.get("Authorization", "")
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip() or None
    return None


async def get_current_user(
    request: Request,
    session: AsyncSessionDep,
) -> User:
    user = await resolve_session(session, session_token_from_request(request))
    if user is None:
        raise AuthenticationError("A valid session is required for this request")
    return user


async def get_optional_user(
    request: Request,
    session: AsyncSessionDep,
) -> User | None:
    return await resolve_session(session, session_token_from_request(request))


CurrentUser = Annotated[User, Depends(get_current_user)]
OptionalUser = Annotated[User | None, Depends(get_optional_user)]


def issue_csrf_token(response: Response, settings: Settings) -> str:
    """Set a readable double-submit cookie and return the value to echo back.

    The cookie is intentionally not HttpOnly — the client must copy its partner
    value into a header. Security comes from two properties together: the cookie
    is signed, so only this server can mint one that verifies, and the echoed
    value is unguessable, so a cross-site page that cannot read the cookie
    cannot construct the header either. A deterministic echo value would make the
    whole scheme forgeable from the URL alone.
    """
    nonce = secrets.token_urlsafe(24)
    response.set_cookie(
        key=settings.csrf_cookie_name,
        value=sign_value(nonce),
        httponly=False,
        samesite=settings.cookie_samesite,  # type: ignore[arg-type]
        secure=settings.cookie_secure,
        path="/",
    )
    return nonce


def require_csrf_for_state_changes() -> Callable[..., Awaitable[None]]:
    """Dependency factory enforcing double-submit CSRF on unsafe requests.

    Only enforced when a session cookie is present. Login and registration are
    exempt by necessity — there is no session to protect yet — and are instead
    covered by SameSite, rate limiting and the generic credential error.
    """

    async def _guard(
        request: Request,
        settings: Annotated[Settings, Depends(get_settings)],
    ) -> None:
        if request.method.upper() in SAFE_METHODS:
            return
        if session_token_from_request(request) is None:
            return

        cookie = request.cookies.get(settings.csrf_cookie_name)
        supplied = request.headers.get(settings.csrf_header_name)
        if not cookie or not supplied:
            raise PermissionDeniedError("Missing CSRF token")

        expected = unsign_value(cookie)
        if expected is None or expected != supplied:
            raise PermissionDeniedError("CSRF token does not match the session")

    return _guard


CsrfGuard = Depends(require_csrf_for_state_changes())

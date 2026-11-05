from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response, status

from app.core.audit import client_ip, record_attempt, record_audit
from app.core.config import Settings, get_settings
from app.core.database import AsyncSessionDep
from app.core.exceptions import DomainError, PermissionDeniedError, TooManyRequestsError
from app.core.logging import get_logger
from app.core.ratelimit import RateLimitRule, get_rate_limiter
from app.core.security import unsign_value
from app.modules.auth.dependencies import (
    CurrentUser,
    issue_csrf_token,
    require_csrf_for_state_changes,
    session_token_from_request,
)
from app.modules.auth.models import User
from app.modules.auth.schemas import LoginRequest, MessageOut, RegisterRequest, SessionInfo, UserOut
from app.modules.auth.service import (
    authenticate,
    create_session,
    create_user,
    revoke_session,
)
from app.shared.normalization import normalize_email

logger = get_logger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


def _guard(rate_scope: str, actor: str, rule: RateLimitRule) -> None:
    allowed, retry_after = get_rate_limiter().check(rate_scope, actor, rule)
    if not allowed:
        raise TooManyRequestsError(
            "Too many attempts. Try again later.",
            headers={"Retry-After": str(int(retry_after))},
            details={"retry_after_seconds": int(retry_after)},
        )


def _set_session_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=settings.session_ttl_hours * 3600,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,  # type: ignore[arg-type]
        path="/",
    )


def _clear_session_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(settings.session_cookie_name, path="/")
    response.delete_cookie(settings.csrf_cookie_name, path="/")


@router.get("/status")
async def auth_status(settings: Settings = Depends(get_settings)) -> dict[str, bool]:
    """Expose only whether this instance permits account creation.

    The login screen needs this to show the signup action accurately; it must
    not have to infer registration state from a failed protected request.
    """
    return {"allow_registration": settings.registration_open}


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest,
    request: Request,
    session: AsyncSessionDep,
    settings: Settings = Depends(get_settings),
) -> User:
    """Create an account.

    Registration is switchable off (`SPARKX_ALLOW_REGISTRATION`) because this is a
    private tool: an always-open signup turns a loopback app into a hosted one the
    moment someone forwards a port.
    """
    if not settings.registration_open:
        raise PermissionDeniedError("Registration is disabled on this instance")

    _guard(
        "register",
        client_ip(request) or "unknown",
        RateLimitRule(settings.register_max_attempts, settings.register_window_seconds),
    )

    user = await create_user(
        session, email=payload.email, password=payload.password, display_name=payload.display_name
    )
    await record_audit(
        session,
        action="auth.register",
        owner_user_id=user.id,
        entity_type="user",
        entity_id=user.id,
        ip_address=client_ip(request),
    )
    return user


@router.post("/login", response_model=SessionInfo)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    session: AsyncSessionDep,
    settings: Settings = Depends(get_settings),
) -> SessionInfo:
    login_email = (
        "local1@sparkxflow.dev"
        if settings.app_env == "development" and payload.email == "1"
        else payload.email
    )
    actor = f"{client_ip(request) or 'unknown'}|{normalize_email(login_email) or 'no-email'}"
    _guard(
        "login", actor, RateLimitRule(settings.login_max_attempts, settings.login_window_seconds)
    )

    try:
        user = await authenticate(session, email=login_email, password=payload.password)
    except DomainError as exc:
        # Committed on its own: the raise below rolls the request transaction
        # back, and a brute-force trail that records nothing tells us nothing.
        await record_attempt(
            action="auth.login_failed",
            owner_user_id=None,
            entity_type="user",
            ip_address=client_ip(request),
            metadata={"reason": exc.code, "attempted_email": normalize_email(login_email)},
        )
        raise

    token, _record = await create_session(
        session,
        user=user,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    await record_audit(
        session,
        action="auth.login",
        owner_user_id=user.id,
        entity_type="user",
        entity_id=user.id,
        ip_address=client_ip(request),
    )

    _set_session_cookie(response, token, settings)
    csrf = issue_csrf_token(response, settings)
    get_rate_limiter().reset("login", actor)
    return SessionInfo(authenticated=True, user=UserOut.model_validate(user), csrf_token=csrf)


@router.post("/logout", response_model=MessageOut)
async def logout(
    request: Request,
    response: Response,
    session: AsyncSessionDep,
    user: CurrentUser,
    settings: Settings = Depends(get_settings),
    _: None = Depends(require_csrf_for_state_changes()),
) -> MessageOut:
    await revoke_session(session, session_token_from_request(request))
    await record_audit(
        session,
        action="auth.logout",
        owner_user_id=user.id,
        entity_type="user",
        entity_id=user.id,
        ip_address=client_ip(request),
    )
    _clear_session_cookie(response, settings)
    return MessageOut(message="Signed out")


@router.get("/session", response_model=SessionInfo)
async def session_info(
    request: Request,
    response: Response,
    user: CurrentUser,
    settings: Settings = Depends(get_settings),
) -> SessionInfo:
    """Who the caller is, plus a CSRF token for subsequent writes."""
    cookie = request.cookies.get(settings.csrf_cookie_name)
    existing_csrf = unsign_value(cookie) if cookie else None
    if existing_csrf:
        csrf = existing_csrf
    else:
        csrf = issue_csrf_token(response, settings)
    return SessionInfo(authenticated=True, user=UserOut.model_validate(user), csrf_token=csrf)

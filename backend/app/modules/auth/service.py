from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import AuthenticationError, ConflictError, DomainError
from app.core.security import (
    generate_session_token,
    hash_password,
    hash_session_token,
    needs_rehash,
    verify_password_for_login,
)
from app.modules.auth.models import User, UserSession
from app.shared.normalization import normalize_email

# A deliberately generic message. "No account with that email" and "wrong
# password" are two different answers to the same question, and the difference
# is an enumeration oracle.
_INVALID_CREDENTIALS = "Email or password is incorrect"


def _rowcount(result: object) -> int:
    """Row count from an UPDATE/DELETE result.

    SQLAlchemy types `execute()` as a generic Result, but returns a CursorResult
    for DML. Checking rather than casting keeps a wrong assumption from silently
    reporting zero revoked sessions.
    """
    return result.rowcount if isinstance(result, CursorResult) else 0


async def create_user(
    session: AsyncSession, *, email: str, password: str, display_name: str
) -> User:
    settings = get_settings()
    normalized = normalize_email(email)
    if normalized is None:
        raise DomainError("Email address is not valid")
    if len(password) < settings.password_min_length:
        raise DomainError(f"Password must be at least {settings.password_min_length} characters")

    existing = await session.scalar(select(User.id).where(User.email == normalized))
    if existing:
        # 409 rather than a silent success: two accounts with one mailbox would
        # make ownership of every future record ambiguous.
        raise ConflictError("An account with that email already exists")

    user = User(
        email=normalized,
        password_hash=hash_password(password),
        display_name=display_name.strip()[:150],
        is_active=True,
    )
    session.add(user)
    await session.flush()
    return user


async def authenticate(session: AsyncSession, *, email: str, password: str) -> User:
    """Verify credentials without leaking which half was wrong.

    A missing account still pays for an Argon2 verification, so response time
    does not distinguish 'unknown email' from 'wrong password'.
    """
    normalized = normalize_email(email)
    user: User | None = None
    stored_hash: str | None = None
    if normalized:
        user = await session.scalar(select(User).where(User.email == normalized))
        stored_hash = user.password_hash if user else None

    if not verify_password_for_login(password, stored_hash):
        raise AuthenticationError(_INVALID_CREDENTIALS)
    if user is None:  # pragma: no cover - verification would have failed first
        raise AuthenticationError(_INVALID_CREDENTIALS)
    if not user.is_active:
        raise AuthenticationError("This account is not active")

    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)

    return user


async def create_session(
    session: AsyncSession,
    *,
    user: User,
    ip_address: str | None,
    user_agent: str | None,
) -> tuple[str, UserSession]:
    settings = get_settings()
    token = generate_session_token()
    record = UserSession(
        user_id=user.id,
        session_token_hash=hash_session_token(token),
        expires_at=datetime.now(UTC) + timedelta(hours=settings.session_ttl_hours),
        ip_address=ip_address,
        user_agent=(user_agent or "")[:500] or None,
    )
    session.add(record)
    user.last_login_at = datetime.now(UTC)
    await session.flush()
    return token, record


async def resolve_session(session: AsyncSession, token: str | None) -> User | None:
    """Return the user for a live session token, or None.

    Expired and revoked rows are treated identically to an unknown token: no
    distinguishing signal for an attacker probing the table.
    """
    if not token:
        return None
    record = await session.scalar(
        select(UserSession).where(UserSession.session_token_hash == hash_session_token(token))
    )
    if record is None or record.revoked_at is not None:
        return None
    now = datetime.now(UTC)
    if record.expires_at <= now:
        return None
    user = await session.get(User, record.user_id)
    if user is None or not user.is_active:
        return None
    return user


async def current_session_row(session: AsyncSession, token: str | None) -> UserSession | None:
    if not token:
        return None
    return await session.scalar(
        select(UserSession).where(UserSession.session_token_hash == hash_session_token(token))
    )


async def revoke_session(session: AsyncSession, token: str | None) -> bool:
    record = await current_session_row(session, token)
    if record is None or record.revoked_at is not None:
        return False
    record.revoked_at = datetime.now(UTC)
    await session.flush()
    return True


async def revoke_all_sessions(session: AsyncSession, user_id: uuid.UUID) -> int:
    result = await session.execute(
        update(UserSession)
        .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
    return _rowcount(result)


async def purge_expired_sessions(session: AsyncSession) -> int:
    """Delete session rows past their expiry. Called by the retention worker."""
    from sqlalchemy import delete

    result = await session.execute(
        delete(UserSession).where(UserSession.expires_at <= datetime.now(UTC))
    )
    return _rowcount(result)

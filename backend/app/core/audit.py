from __future__ import annotations

import uuid
from typing import Any

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import correlation_id_var
from app.modules.notifications.models import AuditLog

# Actions worth a durable record. Anything not listed is not logged, which keeps
# the audit trail a security artefact rather than a request echo.
SENSITIVE_ACTIONS = frozenset(
    {
        "auth.register",
        "auth.login",
        "auth.login_failed",
        "auth.logout",
        "auth.session_revoked",
        "business.shortlist",
        "business.archive",
        "business.delete",
        "business.bulk_update",
        "crm.stage_change",
        "discovery.job_created",
        "discovery.job_cancelled",
        "export.create",
        "source.configure",
        "source.enable",
        "source.disable",
        "settings.update",
    }
)


def client_ip(request: Request) -> str | None:
    """Originating address, taken from the connection rather than a header.

    `X-Forwarded-For` is attacker-supplied when the app is directly reachable, so
    trusting it would let anyone forge the audit trail's source address. If a
    proxy is introduced, the trusted-hop count must be configured explicitly.

    Validated because the column is `INET`: a non-address (a test client, a
    socket name, a proxy that put a hostname there) would make the audit insert
    fail and take the whole request with it. Recording no address is better than
    losing the event.
    """
    import ipaddress

    client = request.client
    if client is None or not client.host:
        return None
    try:
        ipaddress.ip_address(client.host)
    except ValueError:
        return None
    return client.host


async def record_audit(
    session: AsyncSession,
    *,
    action: str,
    owner_user_id: uuid.UUID | None,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    ip_address: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> AuditLog:
    """Write one audit row.

    `metadata` is filtered here rather than at every call site: a future caller
    passing a password or token must not be able to put it in the log by
    accident, and that is the one thing an audit table must never become.
    """
    if action not in SENSITIVE_ACTIONS:
        raise ValueError(f"'{action}' is not a declared auditable action")

    entry = AuditLog(
        owner_user_id=owner_user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        metadata_=_redact(metadata or {}),
        ip_address=ip_address,
        correlation_id=correlation_id_var.get(),
    )
    session.add(entry)
    return entry


_REDACT_KEYS = {"password", "token", "secret", "authorization", "cookie", "session"}


async def record_attempt(
    *,
    action: str,
    owner_user_id: uuid.UUID | None,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    ip_address: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Record an attempt that is about to fail the request.

    `record_audit` joins the caller's transaction, which is right for a change
    that actually happened and useless for a rejected one: the exception that
    follows rolls the audit row straight back, and a failed-login trail that
    records nothing is worse than none, because it looks like there were no
    attempts. This opens its own session and commits before the caller raises.
    """
    from app.core.database import session_scope

    async with session_scope() as session:
        await record_audit(
            session,
            action=action,
            owner_user_id=owner_user_id,
            entity_type=entity_type,
            entity_id=entity_id,
            ip_address=ip_address,
            metadata=metadata,
        )


def _redact(values: dict[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for key, value in values.items():
        lowered = key.lower()
        if any(banned in lowered for banned in _REDACT_KEYS):
            cleaned[key] = "[redacted]"
        elif isinstance(value, dict):
            cleaned[key] = _redact(value)
        elif isinstance(value, str) and len(value) > 500:
            cleaned[key] = value[:500] + "…"
        else:
            cleaned[key] = value
    return cleaned

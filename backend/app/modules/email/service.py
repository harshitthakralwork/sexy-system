from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.modules.businesses.models import Business
from app.modules.email import provider as provider_mod
from app.modules.email.models import (
    Campaign,
    EmailAccount,
    EmailEvent,
    EmailMessage,
    SuppressionEntry,
)
from app.modules.email.provider import EmailProvider
from app.modules.email.schemas import (
    CampaignCreateIn,
    CampaignUpdateIn,
    EmailAccountCreateIn,
    EmailAccountUpdateIn,
    EmailMessageCreateIn,
    SuppressionCreateIn,
)
from app.shared.normalization import normalize_email

# --- Accounts ---------------------------------------------------------------


async def list_accounts(
    session: AsyncSession, owner_user_id: uuid.UUID
) -> list[EmailAccount]:
    rows = await session.scalars(
        select(EmailAccount).where(EmailAccount.owner_user_id == owner_user_id)
    )
    return list(rows)


async def get_account(
    session: AsyncSession, owner_user_id: uuid.UUID, account_id: uuid.UUID
) -> EmailAccount | None:
    return await session.scalar(
        select(EmailAccount).where(
            EmailAccount.id == account_id,
            EmailAccount.owner_user_id == owner_user_id,
        )
    )


async def create_account(
    session: AsyncSession, owner_user_id: uuid.UUID, data: EmailAccountCreateIn
) -> EmailAccount:
    normalized = normalize_email(str(data.email_address))
    if normalized is None:
        raise ValidationFailedError("A valid email address is required")
    duplicate = await session.scalar(
        select(EmailAccount).where(
            EmailAccount.owner_user_id == owner_user_id,
            EmailAccount.email_address == normalized,
        )
    )
    if duplicate is not None:
        raise ConflictError("An account with this address already exists")
    account = EmailAccount(
        owner_user_id=owner_user_id,
        provider=data.provider,
        email_address=normalized,
        secret_reference=data.secret_reference,
    )
    session.add(account)
    await session.flush()
    await session.refresh(account)
    return account


async def update_account(
    session: AsyncSession,
    owner_user_id: uuid.UUID,
    account_id: uuid.UUID,
    data: EmailAccountUpdateIn,
) -> EmailAccount:
    account = await get_account(session, owner_user_id, account_id)
    if account is None:
        raise NotFoundError("Email account not found")
    if data.status is not None:
        account.status = data.status
        if data.status == "connected":
            account.connected_at = datetime.now(UTC)
        elif data.status in ("pending", "failed", "disabled"):
            account.connected_at = None
    if data.secret_reference is not None:
        account.secret_reference = data.secret_reference
    await session.flush()
    await session.refresh(account)
    return account


async def delete_account(
    session: AsyncSession, owner_user_id: uuid.UUID, account_id: uuid.UUID
) -> None:
    account = await get_account(session, owner_user_id, account_id)
    if account is None:
        raise NotFoundError("Email account not found")
    await session.delete(account)
    await session.flush()


# --- Campaigns --------------------------------------------------------------


async def list_campaigns(
    session: AsyncSession, owner_user_id: uuid.UUID
) -> list[Campaign]:
    rows = await session.scalars(
        select(Campaign).where(Campaign.owner_user_id == owner_user_id)
    )
    return list(rows)


async def create_campaign(
    session: AsyncSession, owner_user_id: uuid.UUID, data: CampaignCreateIn
) -> Campaign:
    campaign = Campaign(
        owner_user_id=owner_user_id,
        name=data.name,
        workflow_id=data.workflow_id,
        settings=data.settings,
    )
    session.add(campaign)
    await session.flush()
    await session.refresh(campaign)
    return campaign


async def update_campaign(
    session: AsyncSession,
    owner_user_id: uuid.UUID,
    campaign_id: uuid.UUID,
    data: CampaignUpdateIn,
) -> Campaign:
    campaign = await session.scalar(
        select(Campaign).where(
            Campaign.id == campaign_id, Campaign.owner_user_id == owner_user_id
        )
    )
    if campaign is None:
        raise NotFoundError("Campaign not found")
    if data.name is not None:
        campaign.name = data.name
    if data.status is not None:
        campaign.status = data.status
    if data.settings is not None:
        campaign.settings = data.settings
    await session.flush()
    await session.refresh(campaign)
    return campaign


async def delete_campaign(
    session: AsyncSession, owner_user_id: uuid.UUID, campaign_id: uuid.UUID
) -> None:
    campaign = await session.scalar(
        select(Campaign).where(
            Campaign.id == campaign_id, Campaign.owner_user_id == owner_user_id
        )
    )
    if campaign is None:
        raise NotFoundError("Campaign not found")
    await session.delete(campaign)
    await session.flush()


# --- Suppression ------------------------------------------------------------


async def list_suppression(
    session: AsyncSession, owner_user_id: uuid.UUID, *, limit: int, offset: int
) -> tuple[list[SuppressionEntry], int]:
    where = SuppressionEntry.owner_user_id == owner_user_id
    total = await session.scalar(
        select(func.count()).select_from(SuppressionEntry).where(where)
    )
    rows = await session.scalars(
        select(SuppressionEntry).where(where).order_by(SuppressionEntry.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(rows), int(total or 0)


async def add_suppression(
    session: AsyncSession, owner_user_id: uuid.UUID, data: SuppressionCreateIn
) -> SuppressionEntry:
    normalized = normalize_email(str(data.email_address))
    if normalized is None:
        raise ValidationFailedError("A valid email address is required")
    existing = await session.scalar(
        select(SuppressionEntry).where(
            SuppressionEntry.owner_user_id == owner_user_id,
            SuppressionEntry.normalized_email == normalized,
        )
    )
    if existing is not None:
        return existing
    entry = SuppressionEntry(
        owner_user_id=owner_user_id,
        email_address=str(data.email_address).strip(),
        normalized_email=normalized,
        reason=data.reason,
        source=data.source,
    )
    session.add(entry)
    await session.flush()
    await session.refresh(entry)
    return entry


async def remove_suppression(
    session: AsyncSession, owner_user_id: uuid.UUID, entry_id: uuid.UUID
) -> None:
    entry = await session.scalar(
        select(SuppressionEntry).where(
            SuppressionEntry.id == entry_id,
            SuppressionEntry.owner_user_id == owner_user_id,
        )
    )
    if entry is None:
        raise NotFoundError("Suppression entry not found")
    await session.delete(entry)
    await session.flush()


async def is_suppressed(
    session: AsyncSession, owner_user_id: uuid.UUID, email: str
) -> bool:
    normalized = normalize_email(email)
    if normalized is None:
        return False
    row = await session.scalar(
        select(SuppressionEntry.id).where(
            SuppressionEntry.owner_user_id == owner_user_id,
            SuppressionEntry.normalized_email == normalized,
        )
    )
    return row is not None


# --- Messages ---------------------------------------------------------------


async def list_messages(
    session: AsyncSession,
    owner_user_id: uuid.UUID,
    *,
    status: str | None = None,
    campaign_id: uuid.UUID | None = None,
    limit: int,
    offset: int,
) -> tuple[list[EmailMessage], int]:
    where = EmailMessage.owner_user_id == owner_user_id
    if status is not None:
        where = where & (EmailMessage.status == status)
    if campaign_id is not None:
        where = where & (EmailMessage.campaign_id == campaign_id)
    total = await session.scalar(select(func.count()).select_from(EmailMessage).where(where))
    rows = await session.scalars(
        select(EmailMessage).where(where).order_by(EmailMessage.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(rows), int(total or 0)


async def get_message(
    session: AsyncSession, owner_user_id: uuid.UUID, message_id: uuid.UUID
) -> EmailMessage | None:
    return await session.scalar(
        select(EmailMessage).where(
            EmailMessage.id == message_id,
            EmailMessage.owner_user_id == owner_user_id,
        )
    )


def render_draft(
    business: Business,
    *,
    recipient_name: str | None,
    service_name: str | None,
    sender_name: str,
) -> tuple[str, str]:
    """A deterministic draft from real lead context, never invented numbers.

    The hook branches on `website_status` so "we could not reach it" and "there is
    no website" produce different — and accurate — openings.
    """
    name = business.name or "your business"
    if business.website_status == "missing":
        hook = f"I noticed {name} doesn't have a website yet."
    elif business.website_status == "inaccessible":
        hook = f"I tried to look {name} up online and couldn't reach a website."
    elif business.normalized_domain:
        hook = f"I was looking at {business.normalized_domain} and wanted to reach out."
    else:
        hook = (
            f"I came across {name} while researching businesses "
            f"in {business.city or 'your area'}."
        )
    offer = service_name or "websites, automation and AI integration"
    greeting = f"Hi {recipient_name}," if recipient_name else "Hello,"
    subject = f"A quick note about {name}"
    body = (
        f"{greeting}\n\n"
        f"{hook} I build {offer} for local businesses, and I'd love to show you "
        f"what's possible for {name}.\n\n"
        f"If you're open to a quick chat this week, just reply and I'll work around "
        f"your schedule.\n\nThanks,\n{sender_name}"
    )
    return subject, body


async def create_draft(
    session: AsyncSession,
    owner_user_id: uuid.UUID,
    data: EmailMessageCreateIn,
    *,
    workflow_execution_id: uuid.UUID | None = None,
) -> EmailMessage:
    normalized = normalize_email(str(data.recipient_email))
    if normalized is None:
        raise ValidationFailedError("A valid recipient email is required")
    if await is_suppressed(session, owner_user_id, normalized):
        raise ConflictError("This address is on the suppression list and cannot be emailed")
    message = EmailMessage(
        owner_user_id=owner_user_id,
        campaign_id=data.campaign_id,
        email_account_id=data.email_account_id,
        business_id=data.business_id,
        contact_id=data.contact_id,
        workflow_execution_id=workflow_execution_id,
        recipient_email=normalized,
        subject=data.subject,
        body=data.body,
        # A draft made from a workflow step is gated; a manual draft stays editable.
        status="pending_approval" if workflow_execution_id is not None else "draft",
    )
    session.add(message)
    await session.flush()
    await session.refresh(message)
    return message


async def approve_message(
    session: AsyncSession, owner_user_id: uuid.UUID, message_id: uuid.UUID
) -> EmailMessage:
    message = await get_message(session, owner_user_id, message_id)
    if message is None:
        raise NotFoundError("Email message not found")
    if message.status not in ("draft", "pending_approval"):
        raise ConflictError(f"Cannot approve a message in status '{message.status}'")
    message.status = "approved"
    message.approved_at = datetime.now(UTC)
    await session.flush()
    await session.refresh(message)
    return message


async def record_event(
    session: AsyncSession,
    *,
    message_id: uuid.UUID,
    event_type: str,
    event_data: dict | None = None,
    provider_event_id: str | None = None,
) -> None:
    session.add(
        EmailEvent(
            email_message_id=message_id,
            event_type=event_type,
            provider_event_id=provider_event_id,
            event_data=event_data or {},
            occurred_at=datetime.now(UTC),
        )
    )


async def send_message(
    session: AsyncSession,
    owner_user_id: uuid.UUID,
    message_id: uuid.UUID,
    *,
    settings: Settings | None = None,
    provider: EmailProvider | None = None,
) -> dict:
    """Send one approved message. Refuses loudly when a guard fails.

    Returns a status dict rather than raising for the refusal cases, so a workflow
    `send` step can aggregate many messages without one suppressed address aborting
    the run. Approval and ownership violations still raise.
    """
    active = settings or get_settings()
    message = await get_message(session, owner_user_id, message_id)
    if message is None:
        raise NotFoundError("Email message not found")

    if await is_suppressed(session, owner_user_id, message.recipient_email):
        message.status = "suppressed"
        await record_event(
            session,
            message_id=message.id,
            event_type="failed",
            event_data={"reason": "suppressed"},
        )
        await session.flush()
        return {"status": "suppressed", "error": "Recipient is on the suppression list"}

    if message.status != "approved":
        raise ConflictError(
            f"Message must be approved before sending (current status: '{message.status}')"
        )

    if message.email_account_id is None:
        return await _refuse(
            session, message, "No sending account is attached to this message"
        )
    account = await get_account(session, owner_user_id, message.email_account_id)
    if account is None:
        return await _refuse(session, message, "Attached email account not found")
    if account.status != "connected":
        return await _refuse(
            session, message, f"Email account is not connected (status: '{account.status}')"
        )

    sender = provider or provider_mod.build_provider(active, account.provider)
    if not sender.configured():
        return await _refuse(
            session,
            message,
            f"Provider '{account.provider}' is not configured on this deployment",
        )

    from_address = active.smtp_from_email or account.email_address
    outcome = await sender.send(
        from_address=from_address,
        to_address=message.recipient_email,
        subject=message.subject or "",
        body=message.body or "",
    )
    if not outcome.ok:
        message.status = "failed"
        await record_event(
            session,
            message_id=message.id,
            event_type="failed",
            event_data={"reason": outcome.error or "send failed"},
        )
        await session.flush()
        return {"status": "failed", "error": outcome.error}

    now = datetime.now(UTC)
    message.status = "sent"
    message.sent_at = now
    message.provider_message_id = outcome.provider_message_id
    await record_event(
        session,
        message_id=message.id,
        event_type="sent",
        provider_event_id=outcome.provider_message_id,
        event_data={"from": from_address, "to": message.recipient_email},
    )
    await session.flush()
    return {"status": "sent", "provider_message_id": outcome.provider_message_id}


async def _refuse(session: AsyncSession, message: EmailMessage, reason: str) -> dict:
    await record_event(
        session, message_id=message.id, event_type="failed", event_data={"reason": reason}
    )
    await session.flush()
    return {"status": "blocked", "error": reason}

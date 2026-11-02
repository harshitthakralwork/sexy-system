from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select

from app.core.audit import client_ip, record_audit
from app.core.database import AsyncSessionDep
from app.modules.auth.dependencies import CurrentUser, require_csrf_for_state_changes
from app.modules.email import service
from app.modules.email.models import Campaign, EmailAccount, EmailEvent, EmailMessage
from app.modules.email.schemas import (
    CampaignCreateIn,
    CampaignListOut,
    CampaignOut,
    CampaignUpdateIn,
    EmailAccountCreateIn,
    EmailAccountListOut,
    EmailAccountOut,
    EmailAccountUpdateIn,
    EmailEventOut,
    EmailMessageCreateIn,
    EmailMessageListOut,
    EmailMessageOut,
    SendResultOut,
    SuppressionCreateIn,
    SuppressionListOut,
    SuppressionOut,
)

router = APIRouter(prefix="/email", tags=["email"])

Csrf = Depends(require_csrf_for_state_changes())


def _account_out(row: EmailAccount) -> EmailAccountOut:
    return EmailAccountOut(
        id=row.id,
        provider=row.provider,
        email_address=row.email_address,
        secret_reference=row.secret_reference,
        status=row.status,
        connected_at=row.connected_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _campaign_out(row: Campaign) -> CampaignOut:
    return CampaignOut(
        id=row.id,
        workflow_id=row.workflow_id,
        name=row.name,
        status=row.status,
        settings=row.settings,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _message_out(row: EmailMessage) -> EmailMessageOut:
    return EmailMessageOut(
        id=row.id,
        campaign_id=row.campaign_id,
        email_account_id=row.email_account_id,
        business_id=row.business_id,
        contact_id=row.contact_id,
        workflow_execution_id=row.workflow_execution_id,
        recipient_email=row.recipient_email,
        subject=row.subject,
        body=row.body,
        status=row.status,
        provider_message_id=row.provider_message_id,
        approved_at=row.approved_at,
        sent_at=row.sent_at,
        delivered_at=row.delivered_at,
        bounced_at=row.bounced_at,
        replied_at=row.replied_at,
        created_at=row.created_at,
    )


# --- Accounts ---------------------------------------------------------------


@router.get("/accounts", response_model=EmailAccountListOut)
async def list_accounts(session: AsyncSessionDep, user: CurrentUser) -> EmailAccountListOut:
    rows = await service.list_accounts(session, user.id)
    return EmailAccountListOut(
        items=[_account_out(row) for row in rows], total=len(rows), limit=len(rows), offset=0
    )


@router.post("/accounts", response_model=EmailAccountOut, status_code=201, dependencies=[Csrf])
async def create_account(
    data: EmailAccountCreateIn, session: AsyncSessionDep, user: CurrentUser, request: Request
) -> EmailAccountOut:
    account = await service.create_account(session, user.id, data)
    await record_audit(
        session,
        action="email.account_created",
        owner_user_id=user.id,
        entity_type="email_account",
        entity_id=account.id,
        ip_address=client_ip(request),
        metadata={"provider": account.provider, "email_address": account.email_address},
    )
    return _account_out(account)


@router.patch("/accounts/{account_id}", response_model=EmailAccountOut, dependencies=[Csrf])
async def update_account(
    account_id: uuid.UUID,
    data: EmailAccountUpdateIn,
    session: AsyncSessionDep,
    user: CurrentUser,
) -> EmailAccountOut:
    account = await service.update_account(session, user.id, account_id, data)
    return _account_out(account)


@router.delete("/accounts/{account_id}", status_code=204, dependencies=[Csrf])
async def delete_account(
    account_id: uuid.UUID, session: AsyncSessionDep, user: CurrentUser, request: Request
) -> None:
    await service.delete_account(session, user.id, account_id)
    await record_audit(
        session,
        action="email.account_deleted",
        owner_user_id=user.id,
        entity_type="email_account",
        entity_id=account_id,
        ip_address=client_ip(request),
    )


# --- Campaigns --------------------------------------------------------------


@router.get("/campaigns", response_model=CampaignListOut)
async def list_campaigns(session: AsyncSessionDep, user: CurrentUser) -> CampaignListOut:
    rows = await service.list_campaigns(session, user.id)
    return CampaignListOut(
        items=[_campaign_out(row) for row in rows], total=len(rows), limit=len(rows), offset=0
    )


@router.post("/campaigns", response_model=CampaignOut, status_code=201, dependencies=[Csrf])
async def create_campaign(
    data: CampaignCreateIn, session: AsyncSessionDep, user: CurrentUser
) -> CampaignOut:
    campaign = await service.create_campaign(session, user.id, data)
    return _campaign_out(campaign)


@router.patch("/campaigns/{campaign_id}", response_model=CampaignOut, dependencies=[Csrf])
async def update_campaign(
    campaign_id: uuid.UUID,
    data: CampaignUpdateIn,
    session: AsyncSessionDep,
    user: CurrentUser,
) -> CampaignOut:
    campaign = await service.update_campaign(session, user.id, campaign_id, data)
    return _campaign_out(campaign)


@router.delete("/campaigns/{campaign_id}", status_code=204, dependencies=[Csrf])
async def delete_campaign(
    campaign_id: uuid.UUID, session: AsyncSessionDep, user: CurrentUser
) -> None:
    await service.delete_campaign(session, user.id, campaign_id)


# --- Messages ---------------------------------------------------------------


@router.get("/messages", response_model=EmailMessageListOut)
async def list_messages(
    session: AsyncSessionDep,
    user: CurrentUser,
    status: str | None = Query(default=None),
    campaign_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> EmailMessageListOut:
    rows, total = await service.list_messages(
        session, user.id, status=status, campaign_id=campaign_id, limit=limit, offset=offset
    )
    return EmailMessageListOut(
        items=[_message_out(row) for row in rows], total=total, limit=limit, offset=offset
    )


@router.post("/messages", response_model=EmailMessageOut, status_code=201, dependencies=[Csrf])
async def create_message(
    data: EmailMessageCreateIn, session: AsyncSessionDep, user: CurrentUser
) -> EmailMessageOut:
    message = await service.create_draft(session, user.id, data)
    return _message_out(message)


@router.get("/messages/{message_id}", response_model=EmailMessageOut)
async def get_message(
    message_id: uuid.UUID, session: AsyncSessionDep, user: CurrentUser
) -> EmailMessageOut:
    from app.core.exceptions import NotFoundError

    message = await service.get_message(session, user.id, message_id)
    if message is None:
        raise NotFoundError("Email message not found")
    return _message_out(message)


@router.post("/messages/{message_id}/approve", response_model=EmailMessageOut, dependencies=[Csrf])
async def approve_message(
    message_id: uuid.UUID, session: AsyncSessionDep, user: CurrentUser
) -> EmailMessageOut:
    message = await service.approve_message(session, user.id, message_id)
    return _message_out(message)


@router.post("/messages/{message_id}/send", response_model=SendResultOut, dependencies=[Csrf])
async def send_message(
    message_id: uuid.UUID, session: AsyncSessionDep, user: CurrentUser, request: Request
) -> SendResultOut:
    result = await service.send_message(session, user.id, message_id)
    await record_audit(
        session,
        action="email.send",
        owner_user_id=user.id,
        entity_type="email_message",
        entity_id=message_id,
        ip_address=client_ip(request),
        metadata={"status": result["status"]},
    )
    return SendResultOut(
        message_id=message_id,
        status=result["status"],
        provider_message_id=result.get("provider_message_id"),
        error=result.get("error"),
    )


@router.get("/messages/{message_id}/events", response_model=list[EmailEventOut])
async def list_message_events(
    message_id: uuid.UUID, session: AsyncSessionDep, user: CurrentUser
) -> list[EmailEventOut]:
    message = await service.get_message(session, user.id, message_id)
    if message is None:
        from app.core.exceptions import NotFoundError

        raise NotFoundError("Email message not found")
    rows = list(
        await session.scalars(
            select(EmailEvent)
            .where(EmailEvent.email_message_id == message_id)
            .order_by(EmailEvent.occurred_at)
        )
    )
    return [
        EmailEventOut(
            id=row.id,
            email_message_id=row.email_message_id,
            event_type=row.event_type,
            provider_event_id=row.provider_event_id,
            event_data=row.event_data,
            occurred_at=row.occurred_at,
            created_at=row.created_at,
        )
        for row in rows
    ]


# --- Suppression ------------------------------------------------------------


@router.get("/suppression", response_model=SuppressionListOut)
async def list_suppression(
    session: AsyncSessionDep,
    user: CurrentUser,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> SuppressionListOut:
    rows, total = await service.list_suppression(session, user.id, limit=limit, offset=offset)
    return SuppressionListOut(
        items=[
            SuppressionOut(
                id=row.id,
                email_address=row.email_address,
                normalized_email=row.normalized_email,
                reason=row.reason,
                source=row.source,
                created_at=row.created_at,
            )
            for row in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/suppression", response_model=SuppressionOut, status_code=201, dependencies=[Csrf])
async def add_suppression(
    data: SuppressionCreateIn, session: AsyncSessionDep, user: CurrentUser, request: Request
) -> SuppressionOut:
    entry = await service.add_suppression(session, user.id, data)
    await record_audit(
        session,
        action="email.suppression_added",
        owner_user_id=user.id,
        entity_type="suppression_entry",
        entity_id=entry.id,
        ip_address=client_ip(request),
        metadata={"email_address": entry.email_address},
    )
    return SuppressionOut(
        id=entry.id,
        email_address=entry.email_address,
        normalized_email=entry.normalized_email,
        reason=entry.reason,
        source=entry.source,
        created_at=entry.created_at,
    )


@router.delete("/suppression/{entry_id}", status_code=204, dependencies=[Csrf])
async def remove_suppression(
    entry_id: uuid.UUID, session: AsyncSessionDep, user: CurrentUser, request: Request
) -> None:
    await service.remove_suppression(session, user.id, entry_id)
    await record_audit(
        session,
        action="email.suppression_deleted",
        owner_user_id=user.id,
        entity_type="suppression_entry",
        entity_id=entry_id,
        ip_address=client_ip(request),
    )

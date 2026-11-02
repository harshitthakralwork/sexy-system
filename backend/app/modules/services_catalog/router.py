from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select

from app.core.audit import client_ip, record_audit
from app.core.database import AsyncSessionDep
from app.core.exceptions import NotFoundError, ValidationFailedError
from app.modules.auth.dependencies import CurrentUser, require_csrf_for_state_changes
from app.modules.services_catalog import service
from app.modules.services_catalog.models import BusinessOpportunity, OpportunityEvidence
from app.modules.services_catalog.schemas import (
    EvidenceOut,
    OpportunityListOut,
    OpportunityOut,
    ProfileOut,
    RuleOut,
    ServiceCreateIn,
    ServiceDetailOut,
    ServiceListOut,
    ServiceOut,
)

router = APIRouter(prefix="/services", tags=["services"])

Csrf = Depends(require_csrf_for_state_changes())


@router.get("", response_model=ServiceListOut)
async def list_services(session: AsyncSessionDep, user: CurrentUser) -> ServiceListOut:
    """The catalog, seeded with one default service so qualification is reachable."""
    await service.ensure_default_catalog(session, user.id)
    rows = await service.list_services(session, user.id)
    return ServiceListOut(items=[ServiceOut.model_validate(row) for row in rows], total=len(rows))


@router.post("", response_model=ServiceOut, status_code=201, dependencies=[Csrf])
async def create_service(
    request: Request,
    payload: ServiceCreateIn,
    session: AsyncSessionDep,
    user: CurrentUser,
) -> ServiceOut:
    try:
        row = await service.create_service(
            session, owner_user_id=user.id, name=payload.name, description=payload.description
        )
    except ValueError as exc:
        raise ValidationFailedError(str(exc)) from exc
    await record_audit(
        session,
        action="service.create",
        owner_user_id=user.id,
        entity_type="service",
        entity_id=row.id,
        ip_address=client_ip(request),
        metadata={"name": row.name, "slug": row.slug},
    )
    return ServiceOut.model_validate(row)


@router.get("/opportunities", response_model=OpportunityListOut)
async def list_opportunities(
    session: AsyncSessionDep,
    user: CurrentUser,
    business_id: uuid.UUID = Query(),
) -> OpportunityListOut:
    rows = await service.opportunities_for_business(session, user.id, business_id)
    items = [await _opportunity_out(session, row) for row in rows]
    return OpportunityListOut(items=items, total=len(items))


@router.get("/{service_id}", response_model=ServiceDetailOut)
async def service_detail(
    service_id: uuid.UUID, session: AsyncSessionDep, user: CurrentUser
) -> ServiceDetailOut:
    row = await service.get_service(session, user.id, service_id)
    if row is None:
        raise NotFoundError("Service not found")
    profiles = await service.list_profiles(session, service_id)
    profile_outs: list[ProfileOut] = []
    for profile in profiles:
        rules = await service.list_rules(session, profile.id)
        profile_outs.append(
            ProfileOut(
                **ProfileOut.model_validate(profile).model_dump(exclude={"rules"}),
                rules=[RuleOut.model_validate(rule) for rule in rules],
            )
        )
    return ServiceDetailOut(**ServiceOut.model_validate(row).model_dump(), profiles=profile_outs)


@router.post(
    "/{service_id}/qualify/{business_id}",
    response_model=OpportunityOut,
    dependencies=[Csrf],
)
async def qualify(
    service_id: uuid.UUID,
    business_id: uuid.UUID,
    session: AsyncSessionDep,
    user: CurrentUser,
) -> OpportunityOut:
    """Evaluate a business against a service and store the result with evidence.

    The score is deterministic — derived from the stored rules and the observed
    signals — not a model opinion. Re-running replaces the previous result.
    """
    try:
        opportunity = await service.qualify_business(
            session,
            owner_user_id=user.id,
            business_id=business_id,
            service_id=service_id,
        )
    except LookupError as exc:
        raise NotFoundError(str(exc)) from exc
    except ValueError as exc:
        raise ValidationFailedError(str(exc)) from exc
    return await _opportunity_out(session, opportunity)


async def _opportunity_out(
    session: AsyncSessionDep, opportunity: BusinessOpportunity
) -> OpportunityOut:
    evidence_rows = list(
        await session.scalars(
            select(OpportunityEvidence)
            .where(OpportunityEvidence.opportunity_id == opportunity.id)
            .order_by(OpportunityEvidence.score_contribution.desc())
        )
    )
    return OpportunityOut(
        **OpportunityOut.model_validate(opportunity).model_dump(exclude={"evidence"}),
        evidence=[EvidenceOut.model_validate(row) for row in evidence_rows],
    )

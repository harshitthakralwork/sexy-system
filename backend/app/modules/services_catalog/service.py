from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.businesses.models import Business, BusinessSocialProfile
from app.modules.discovery.models import SourceRecord, SourceRecordLink
from app.modules.services_catalog.models import (
    BusinessOpportunity,
    OpportunityEvidence,
    ScoringRuleRecord,
    Service,
    ServiceProfile,
)
from app.shared import signals as S
from app.shared.scoring import Operator, ScoringRule, evaluate

DEFAULT_SERVICE = {
    "name": "Web & Digital Presence",
    "slug": "web-presence",
    "description": (
        "Businesses whose web presence is absent or broken are prospects for a "
        "site build or redesign. Absence of a stated website is an opportunity "
        "signal, not proof that the business needs one."
    ),
}
DEFAULT_PROFILE_NAME = "Indian SMB web presence"
DEFAULT_PROFILE_THRESHOLD = 60
# (rule_name, signal_key, weight, operator, threshold) — canonical signal keys.
DEFAULT_RULES: list[tuple[str, str, float, str, Any]] = [
    ("No website stated", S.WEBSITE_CLAIMED, 40.0, "eq", False),
    ("Website unreachable", "website_status", 20.0, "eq", "inaccessible"),
    ("Phone reported", S.PHONE_PRESENT, 15.0, "eq", True),
    ("Email reported", S.EMAIL_PRESENT, 15.0, "eq", True),
    ("Category known", S.CATEGORY_MATCHED, 10.0, "eq", True),
]


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "service"


def signals_from_business(
    business: Business,
    *,
    social_profile_count: int = 0,
    source_record_count: int = 0,
) -> dict[str, Any]:
    """The observation set a scoring profile runs against.

    Enrichment signals (the canonical vocabulary) are the base; column-backed
    observations that enrichment does not store as signals are added on top.

    Presence is only derived when the column actually holds a value. A null
    column means "not observed", not "absent", so it is left missing and the
    evaluator lowers confidence instead of inventing a negative.
    """
    signals: dict[str, Any] = dict((business.enrichment or {}).get("signals", {}))

    def mark_present(key: str, value: object) -> None:
        if value and key not in signals:
            signals[key] = True

    signals.setdefault(S.NAME_PRESENT, bool(business.name))
    mark_present(S.DOMAIN_PRESENT, business.normalized_domain)
    mark_present(S.PHONE_PRESENT, business.normalized_phone)
    mark_present(S.EMAIL_PRESENT, business.normalized_email)
    mark_present(S.ADDRESS_PRESENT, business.address)
    if business.latitude is not None and business.longitude is not None:
        mark_present(S.GEO_PRESENT, True)
    mark_present(S.CATEGORY_MATCHED, business.primary_category)
    mark_present(S.WEBSITE_CLAIMED, business.website_url)

    # Derived classification and column-backed observations.
    signals["website_status"] = business.website_status
    if business.rating is not None:
        signals[S.RATING] = float(business.rating)
    if business.review_count is not None:
        signals[S.REVIEW_COUNT] = int(business.review_count)
    if business.last_researched_at is not None:
        signals[S.DAYS_SINCE_LAST_RESEARCH] = max(
            (datetime.now(UTC) - business.last_researched_at).days, 0
        )
    signals[S.SOCIAL_PROFILE_COUNT] = social_profile_count
    signals[S.SOURCE_RECORD_COUNT] = source_record_count
    return signals


async def ensure_default_catalog(session: AsyncSession, owner_user_id: uuid.UUID) -> Service:
    """Create the default service, profile and rules once per owner.

    Idempotent by lookup, mirroring the CRM pipeline seed. A catalog with no
    service would make qualification unreachable, so the seed is the entry point
    rather than an empty list.
    """
    service = await session.scalar(
        select(Service).where(
            Service.owner_user_id == owner_user_id, Service.slug == DEFAULT_SERVICE["slug"]
        )
    )
    if service is not None:
        return service

    service = Service(
        owner_user_id=owner_user_id,
        name=DEFAULT_SERVICE["name"],
        slug=DEFAULT_SERVICE["slug"],
        description=DEFAULT_SERVICE["description"],
        is_active=True,
    )
    session.add(service)
    await session.flush()

    profile = ServiceProfile(
        service_id=service.id,
        name=DEFAULT_PROFILE_NAME,
        qualification_threshold=DEFAULT_PROFILE_THRESHOLD,
        is_active=True,
        version=1,
    )
    session.add(profile)
    await session.flush()

    for rule_name, signal_key, weight, operator, threshold in DEFAULT_RULES:
        session.add(
            ScoringRuleRecord(
                service_profile_id=profile.id,
                rule_name=rule_name,
                signal_key=signal_key,
                weight=weight,
                operator=operator,
                threshold=threshold,
                is_required=False,
                is_active=True,
            )
        )
    await session.flush()
    return service


async def list_services(session: AsyncSession, owner_user_id: uuid.UUID) -> list[Service]:
    return list(
        await session.scalars(
            select(Service)
            .where(Service.owner_user_id == owner_user_id)
            .order_by(Service.created_at)
        )
    )


async def get_service(
    session: AsyncSession, owner_user_id: uuid.UUID, service_id: uuid.UUID
) -> Service | None:
    return await session.scalar(
        select(Service).where(
            Service.id == service_id, Service.owner_user_id == owner_user_id
        )
    )


async def create_service(
    session: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    name: str,
    description: str | None = None,
) -> Service:
    """Add a service, refusing duplicate slugs rather than silently aliasing."""
    slug = slugify(name)
    clash = await session.scalar(
        select(Service).where(Service.owner_user_id == owner_user_id, Service.slug == slug)
    )
    if clash is not None:
        raise ValueError(f"A service with slug '{slug}' already exists")
    service = Service(
        owner_user_id=owner_user_id,
        name=name,
        slug=slug,
        description=description,
        is_active=True,
    )
    session.add(service)
    await session.flush()
    return service


async def active_profile_for(session: AsyncSession, service_id: uuid.UUID) -> ServiceProfile | None:
    return await session.scalar(
        select(ServiceProfile)
        .where(ServiceProfile.service_id == service_id, ServiceProfile.is_active.is_(True))
        .order_by(ServiceProfile.version.desc())
    )


async def list_profiles(session: AsyncSession, service_id: uuid.UUID) -> list[ServiceProfile]:
    return list(
        await session.scalars(
            select(ServiceProfile)
            .where(ServiceProfile.service_id == service_id)
            .order_by(ServiceProfile.version.desc())
        )
    )


async def list_rules(session: AsyncSession, profile_id: uuid.UUID) -> list[ScoringRuleRecord]:
    return list(
        await session.scalars(
            select(ScoringRuleRecord)
            .where(ScoringRuleRecord.service_profile_id == profile_id)
            .order_by(ScoringRuleRecord.rule_name)
        )
    )


def _to_scoring_rule(row: ScoringRuleRecord) -> ScoringRule:
    return ScoringRule(
        rule_name=row.rule_name,
        signal_key=row.signal_key,
        weight=float(row.weight),
        operator=Operator(row.operator),
        threshold=row.threshold,
        is_required=row.is_required,
        is_active=row.is_active,
    )


async def _counts_for_business(
    session: AsyncSession, owner_user_id: uuid.UUID, business_id: uuid.UUID
) -> tuple[int, int]:
    social = await session.scalar(
        select(func.count())
        .select_from(BusinessSocialProfile)
        .where(BusinessSocialProfile.business_id == business_id)
    )
    source = await session.scalar(
        select(func.count())
        .select_from(SourceRecordLink)
        .join(SourceRecord, SourceRecord.id == SourceRecordLink.source_record_id)
        .where(
            SourceRecordLink.entity_type == "business",
            SourceRecordLink.entity_id == business_id,
            SourceRecord.owner_user_id == owner_user_id,
        )
    )
    return int(social or 0), int(source or 0)


def _status_for(result: Any) -> str:
    if result.qualified:
        return "qualified"
    return "candidate" if result.score > 0 else "unqualified"


def _summary(result: Any) -> str:
    parts = [f"Score {result.score}/100", f"{result.confidence}% of signals observed"]
    if result.unmet_required_signals:
        parts.append(f"missing required: {', '.join(result.unmet_required_signals)}")
    return ". ".join(parts) + "."


async def qualify_business(
    session: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    business_id: uuid.UUID,
    service_id: uuid.UUID,
) -> BusinessOpportunity:
    """Evaluate one business against one service and persist the result.

    The score comes from the stored rule set and observed signals only — this
    function applies the deterministic evaluator; it does not judge. Each run
    rewrites the opportunity and its evidence, so a re-run after new discovery
    replaces the previous opinion instead of stacking a contradictory one.
    """
    from app.modules.businesses.repository import get_business

    business = await get_business(session, owner_user_id, business_id)
    if business is None:
        raise LookupError("Business not found")
    service = await get_service(session, owner_user_id, service_id)
    if service is None:
        raise LookupError("Service not found")

    profile = await active_profile_for(session, service_id)
    if profile is None:
        raise ValueError("This service has no active scoring profile")

    rule_rows = list(
        await session.scalars(
            select(ScoringRuleRecord).where(
                ScoringRuleRecord.service_profile_id == profile.id,
                ScoringRuleRecord.is_active.is_(True),
            )
        )
    )
    if not rule_rows:
        raise ValueError("This service's profile has no active scoring rules")

    social_count, source_count = await _counts_for_business(session, owner_user_id, business_id)
    signals = signals_from_business(
        business, social_profile_count=social_count, source_record_count=source_count
    )
    result = evaluate(
        signals,
        [_to_scoring_rule(row) for row in rule_rows],
        qualification_threshold=float(profile.qualification_threshold),
        profile_version=profile.version,
    )

    opportunity = await session.scalar(
        select(BusinessOpportunity).where(
            BusinessOpportunity.business_id == business_id,
            BusinessOpportunity.service_id == service_id,
            BusinessOpportunity.owner_user_id == owner_user_id,
        )
    )
    now = datetime.now(UTC)
    if opportunity is None:
        opportunity = BusinessOpportunity(
            business_id=business_id,
            service_id=service_id,
            service_profile_id=profile.id,
            owner_user_id=owner_user_id,
            score=0,
            confidence=0,
            status="unqualified",
            missing_information=[],
            profile_version=profile.version,
            evaluated_at=now,
        )
        session.add(opportunity)
        await session.flush()

    opportunity.service_profile_id = profile.id
    opportunity.score = result.score
    opportunity.confidence = result.confidence
    opportunity.status = _status_for(result)
    opportunity.evidence_summary = _summary(result)
    opportunity.missing_information = result.missing_signals
    opportunity.profile_version = profile.version
    opportunity.evaluated_at = now

    await session.execute(
        delete(OpportunityEvidence).where(OpportunityEvidence.opportunity_id == opportunity.id)
    )
    rule_ids = {row.rule_name: row.id for row in rule_rows}
    for evidence in result.evidence:
        session.add(
            OpportunityEvidence(
                opportunity_id=opportunity.id,
                scoring_rule_id=rule_ids.get(evidence.rule_name),
                evidence_type=evidence.signal_key,
                description=evidence.description,
                source_url=None,
                evidence_value={
                    "observed_value": evidence.observed_value,
                    "satisfied": evidence.satisfied,
                },
                score_contribution=evidence.score_contribution,
                confidence=result.confidence,
                observed_at=now,
            )
        )
    await session.flush()
    return opportunity


async def opportunities_for_business(
    session: AsyncSession, owner_user_id: uuid.UUID, business_id: uuid.UUID
) -> list[BusinessOpportunity]:
    return list(
        await session.scalars(
            select(BusinessOpportunity)
            .where(
                BusinessOpportunity.owner_user_id == owner_user_id,
                BusinessOpportunity.business_id == business_id,
            )
            .order_by(BusinessOpportunity.evaluated_at.desc())
        )
    )

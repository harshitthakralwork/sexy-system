"""Analytics & Reports — aggregate counts over the operator's own data (master plan #27).

Every figure is a GROUP BY the operator's rows; nothing is sampled or fabricated, and
an empty surface stays empty rather than showing a placeholder number. Reports capture
that same summary as a point-in-time snapshot so a saved report does not silently drift
from what it recorded. Reuses existing models; adds no new dependencies.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.modules.analytics.models import SavedReport
from app.modules.businesses.models import Business
from app.modules.crm.models import CrmBusinessRecord, CrmStage
from app.modules.discovery.models import DiscoveryJob
from app.modules.services_catalog.models import BusinessOpportunity
from app.modules.social.models import SocialContent, SocialPlatform
from app.modules.startups.models import Startup

_REPORT_TYPES = ("analytics", "leads", "social", "startups")


def _buckets(rows: Sequence[Any]) -> list[dict]:
    return [
        {"key": str(key) if key is not None else "—", "count": int(count)}
        for key, count in rows
    ]


async def _group(
    session: AsyncSession, label_col: Any, count_col: Any, *conditions: Any
) -> list[dict]:
    stmt = (
        select(label_col.label("key"), func.count())
        .where(*conditions)
        .group_by(label_col)
        .order_by(func.count().desc())
    )
    return _buckets((await session.execute(stmt)).all())


async def _group_join(
    session: AsyncSession,
    from_model: Any,
    join_target: Any,
    on_clause: Any,
    label_col: Any,
    *conditions: Any,
) -> list[dict]:
    stmt = (
        select(label_col.label("key"), func.count())
        .select_from(from_model)
        .join(join_target, on_clause)
        .where(*conditions)
        .group_by(label_col)
        .order_by(func.count().desc())
    )
    return _buckets((await session.execute(stmt)).all())


async def analytics_summary(session: AsyncSession, owner_user_id: uuid.UUID) -> dict[str, Any]:
    active = Business.owner_user_id == owner_user_id
    alive = active & Business.deleted_at.is_(None)
    leads_total = int(
        await session.scalar(select(func.count()).select_from(Business).where(alive)) or 0
    )

    return {
        "generated_at": datetime.now(UTC),
        "leads_total": leads_total,
        "businesses_by_website_status": await _group(
            session, Business.website_status, Business.id, alive
        ),
        "businesses_by_lifecycle": await _group(
            session, Business.lifecycle_status, Business.id, alive
        ),
        "crm_by_stage": await _group_join(
            session,
            CrmBusinessRecord,
            CrmStage,
            CrmBusinessRecord.stage_id == CrmStage.id,
            CrmStage.name,
            CrmBusinessRecord.owner_user_id == owner_user_id,
        ),
        "opportunities_by_status": await _group(
            session, BusinessOpportunity.status, BusinessOpportunity.id,
            BusinessOpportunity.owner_user_id == owner_user_id,
        ),
        "discovery_jobs_by_status": await _group(
            session, DiscoveryJob.status, DiscoveryJob.id,
            DiscoveryJob.owner_user_id == owner_user_id,
        ),
        "social_by_classification": await _group(
            session,
            func.coalesce(SocialContent.classification, "Unclassified"),
            SocialContent.id,
            SocialContent.owner_user_id == owner_user_id,
        ),
        "social_by_platform": await _group_join(
            session,
            SocialContent,
            SocialPlatform,
            SocialContent.platform_id == SocialPlatform.id,
            SocialPlatform.slug,
            SocialContent.owner_user_id == owner_user_id,
        ),
        "social_by_track_type": await _group(
            session,
            func.coalesce(SocialContent.track_type, "none"),
            SocialContent.id,
            SocialContent.owner_user_id == owner_user_id,
        ),
        "startups_by_funding_stage": await _group(
            session,
            func.coalesce(Startup.funding_stage, "unknown"),
            Startup.id,
            Startup.owner_user_id == owner_user_id,
            Startup.deleted_at.is_(None),
        ),
    }


# --- Saved reports ----------------------------------------------------------


async def create_report(
    session: AsyncSession,
    owner_user_id: uuid.UUID,
    *,
    name: str,
    description: str | None,
    report_type: str,
) -> SavedReport:
    if report_type not in _REPORT_TYPES:
        report_type = "analytics"
    summary = await analytics_summary(session, owner_user_id)
    report = SavedReport(
        owner_user_id=owner_user_id,
        name=name,
        description=description,
        report_type=report_type,
        snapshot={k: v for k, v in summary.items() if k != "generated_at"} | {
            "generated_at": summary["generated_at"].isoformat()
        },
        captured_at=summary["generated_at"].isoformat(),
    )
    session.add(report)
    await session.flush()
    await session.refresh(report)
    return report


async def list_reports(
    session: AsyncSession, owner_user_id: uuid.UUID, *, limit: int, offset: int
) -> tuple[list[SavedReport], int]:
    where = SavedReport.owner_user_id == owner_user_id
    total = int(
        await session.scalar(select(func.count()).select_from(SavedReport).where(where)) or 0
    )
    rows = list(
        await session.scalars(
            select(SavedReport)
            .where(where)
            .order_by(SavedReport.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    )
    return rows, total


async def get_report(
    session: AsyncSession, owner_user_id: uuid.UUID, report_id: uuid.UUID
) -> SavedReport | None:
    return await session.scalar(
        select(SavedReport).where(
            SavedReport.id == report_id, SavedReport.owner_user_id == owner_user_id
        )
    )


async def delete_report(
    session: AsyncSession, owner_user_id: uuid.UUID, report_id: uuid.UUID
) -> None:
    report = await get_report(session, owner_user_id, report_id)
    if report is None:
        raise NotFoundError("Report not found")
    await session.delete(report)
    await session.flush()

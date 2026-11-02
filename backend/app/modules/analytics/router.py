from __future__ import annotations

import csv
import io
import uuid

from fastapi import APIRouter, Depends, Query, Request, Response

from app.core.audit import client_ip, record_audit
from app.core.database import AsyncSessionDep
from app.core.exceptions import NotFoundError
from app.modules.analytics import service
from app.modules.analytics.schemas import (
    AnalyticsBucket,
    AnalyticsOut,
    ReportCreateIn,
    ReportListOut,
    ReportOut,
)
from app.modules.auth.dependencies import CurrentUser, require_csrf_for_state_changes

router = APIRouter(prefix="/analytics", tags=["analytics"])
Csrf = Depends(require_csrf_for_state_changes())

_BUCKET_PREFIXES = (
    "businesses_by_",
    "crm_by_",
    "opportunities_by_",
    "discovery_jobs_by_",
    "social_by_",
    "startups_by_",
)


def _to_out(summary: dict) -> AnalyticsOut:
    data = dict(summary)
    for key, value in data.items():
        if key.startswith(_BUCKET_PREFIXES):
            data[key] = [AnalyticsBucket(**b) for b in value]
    return AnalyticsOut(**data)


def _flatten_csv(summary: dict) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["section", "key", "count"])
    writer.writerow(["leads_total", "", summary.get("leads_total", 0)])
    for key, value in summary.items():
        if key in ("generated_at", "leads_total"):
            continue
        for bucket in value:
            writer.writerow([key, bucket["key"], bucket["count"]])
    return buffer.getvalue()


def _csv_response(body: str, filename: str) -> Response:
    return Response(
        content=body,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("", response_model=AnalyticsOut)
async def analytics(session: AsyncSessionDep, user: CurrentUser) -> AnalyticsOut:
    summary = await service.analytics_summary(session, user.id)
    return _to_out(summary)


@router.get("/export", response_class=Response)
async def export_analytics(
    request: Request, session: AsyncSessionDep, user: CurrentUser
) -> Response:
    summary = await service.analytics_summary(session, user.id)
    await record_audit(
        session,
        action="export.create",
        owner_user_id=user.id,
        entity_type="export_job",
        ip_address=client_ip(request),
        metadata={"format": "csv", "module": "analytics"},
    )
    return _csv_response(_flatten_csv(summary), "sparkxflow-analytics.csv")


@router.get("/reports", response_model=ReportListOut)
async def list_reports(
    session: AsyncSessionDep,
    user: CurrentUser,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> ReportListOut:
    rows, total = await service.list_reports(session, user.id, limit=limit, offset=offset)
    return ReportListOut(
        items=[ReportOut.model_validate(r) for r in rows], total=total, limit=limit, offset=offset
    )


@router.post("/reports", response_model=ReportOut, status_code=201, dependencies=[Csrf])
async def create_report(
    payload: ReportCreateIn,
    session: AsyncSessionDep,
    user: CurrentUser,
    request: Request,
) -> ReportOut:
    report = await service.create_report(
        session,
        user.id,
        name=payload.name,
        description=payload.description,
        report_type=payload.report_type,
    )
    await record_audit(
        session,
        action="report.saved",
        owner_user_id=user.id,
        entity_type="saved_report",
        entity_id=report.id,
        ip_address=client_ip(request),
        metadata={"report_type": report.report_type},
    )
    return ReportOut.model_validate(report)


@router.get("/reports/{report_id}", response_model=ReportOut)
async def get_report(
    report_id: uuid.UUID, session: AsyncSessionDep, user: CurrentUser
) -> ReportOut:
    report = await service.get_report(session, user.id, report_id)
    if report is None:
        raise NotFoundError("Report not found")
    return ReportOut.model_validate(report)


@router.delete("/reports/{report_id}", status_code=204, dependencies=[Csrf])
async def delete_report(
    report_id: uuid.UUID, session: AsyncSessionDep, user: CurrentUser, request: Request
) -> None:
    await service.delete_report(session, user.id, report_id)
    await record_audit(
        session,
        action="report.deleted",
        owner_user_id=user.id,
        entity_type="saved_report",
        entity_id=report_id,
        ip_address=client_ip(request),
    )


@router.get("/reports/{report_id}/export", response_class=Response)
async def export_report(
    report_id: uuid.UUID, session: AsyncSessionDep, user: CurrentUser
) -> Response:
    report = await service.get_report(session, user.id, report_id)
    if report is None:
        raise NotFoundError("Report not found")
    return _csv_response(_flatten_csv(report.snapshot), f"sparkxflow-report-{report_id}.csv")

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from app.modules.businesses.models import Business

from app.core.config import Settings, get_settings
from app.core.database import session_scope
from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.core.logging import get_logger
from app.modules.automation.models import (
    Schedule,
    Workflow,
    WorkflowApproval,
    WorkflowExecution,
    WorkflowStepExecution,
)
from app.modules.automation.schemas import (
    ApprovalReviewIn,
    ScheduleCreateIn,
    ScheduleUpdateIn,
    WorkflowCreateIn,
    WorkflowUpdateIn,
)

logger = get_logger(__name__)

RUN_TASK_NAME = "sparkxflow.automation.run_workflow"
TICK_TASK_NAME = "sparkxflow.automation.tick_schedules"

# --- Workflows --------------------------------------------------------------


async def list_workflows(
    session: AsyncSession, owner_user_id: uuid.UUID, *, limit: int, offset: int
) -> tuple[list[Workflow], int]:
    where = Workflow.owner_user_id == owner_user_id
    total = await session.scalar(select(func.count()).select_from(Workflow).where(where))
    rows = await session.scalars(
        select(Workflow).where(where).order_by(Workflow.created_at.desc()).limit(limit).offset(offset)
    )
    return list(rows), int(total or 0)


async def get_workflow(
    session: AsyncSession, owner_user_id: uuid.UUID, workflow_id: uuid.UUID
) -> Workflow | None:
    return await session.scalar(
        select(Workflow).where(
            Workflow.id == workflow_id, Workflow.owner_user_id == owner_user_id
        )
    )


def _definition_from_steps(steps: list[Any]) -> dict:
    return {
        "steps": [
            {"key": step.key, "type": step.type, "config": step.config} for step in steps
        ]
    }


async def create_workflow(
    session: AsyncSession, owner_user_id: uuid.UUID, data: WorkflowCreateIn
) -> Workflow:
    workflow = Workflow(
        owner_user_id=owner_user_id,
        name=data.name,
        description=data.description,
        module=data.module,
        workflow_definition=_definition_from_steps(data.steps),
        status="draft",
        version=1,
    )
    session.add(workflow)
    await session.flush()
    await session.refresh(workflow)
    return workflow


async def update_workflow(
    session: AsyncSession,
    owner_user_id: uuid.UUID,
    workflow_id: uuid.UUID,
    data: WorkflowUpdateIn,
) -> Workflow:
    workflow = await get_workflow(session, owner_user_id, workflow_id)
    if workflow is None:
        raise NotFoundError("Workflow not found")
    definition_changed = False
    if data.name is not None:
        workflow.name = data.name
    if data.description is not None:
        workflow.description = data.description
    if data.module is not None:
        workflow.module = data.module
    if data.status is not None:
        workflow.status = data.status
    if data.steps is not None:
        workflow.workflow_definition = _definition_from_steps(data.steps)
        definition_changed = True
    if definition_changed:
        workflow.version += 1
    await session.flush()
    await session.refresh(workflow)
    return workflow


async def delete_workflow(
    session: AsyncSession, owner_user_id: uuid.UUID, workflow_id: uuid.UUID
) -> None:
    workflow = await get_workflow(session, owner_user_id, workflow_id)
    if workflow is None:
        raise NotFoundError("Workflow not found")
    await session.delete(workflow)
    await session.flush()


# --- Schedules --------------------------------------------------------------


def _validated_timezone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise ValidationFailedError(f"Unknown timezone '{name}'") from exc


def _parse_cron_field(field: str, lo: int, hi: int) -> set[int]:
    values: set[int] = set()
    for part in field.split(","):
        if "/" in part:
            base, step_str = part.split("/", 1)
            step = int(step_str)
        else:
            base, step = part, 1
        if step <= 0:
            raise ValueError("cron step must be positive")
        if base == "*":
            values.update(range(lo, hi + 1, step))
        elif "-" in base:
            start, end = base.split("-", 1)
            values.update(range(int(start), int(end) + 1, step))
        else:
            values.add(int(base))
    for value in values:
        if not lo <= value <= hi:
            raise ValueError(f"cron field value {value} outside {lo}-{hi}")
    return values


def _parse_cron(expr: str) -> tuple[set[int], set[int], set[int], set[int], set[int]]:
    parts = expr.split()
    minute = _parse_cron_field(parts[0], 0, 59)
    hour = _parse_cron_field(parts[1], 0, 23)
    dom = _parse_cron_field(parts[2], 1, 31)
    month = _parse_cron_field(parts[3], 1, 12)
    dow = _parse_cron_field(parts[4], 0, 7)
    # Cron days run 0-7 where both 0 and 7 are Sunday; normalise 7 -> 0.
    dow = {day % 7 for day in dow}
    return minute, hour, dom, month, dow


def _field_is_unrestricted(field: str) -> bool:
    return field == "*"


def next_cron(expr: str, after: datetime, *, horizon_days: int = 366 * 5) -> datetime | None:
    """The next wall-clock minute matching a five-field cron expression.

    A minute-by-minute scan is intentionally simple rather than clever; it is
    bounded by `horizon_days` so a schedule like ``0 0 29 2 *`` (Feb 29) that has
    no occurrence inside the horizon returns None instead of looping forever.
    """
    minute, hour, dom, month, dow = _parse_cron(expr)
    parts = expr.split()
    dom_restricted = not _field_is_unrestricted(parts[2])
    dow_restricted = not _field_is_unrestricted(parts[4])

    candidate = (after + timedelta(minutes=1)).replace(second=0, microsecond=0)
    limit = after + timedelta(days=horizon_days)
    while candidate <= limit:
        dom_ok = candidate.day in dom if dom_restricted else True
        # Python weekday(): Monday=0..Sunday=6; cron dow: Sunday=0..Saturday=6.
        dow_ok = (candidate.weekday() + 1) % 7 in dow if dow_restricted else True
        day_ok = (
            (dom_ok or dow_ok)
            if (dom_restricted and dow_restricted)
            else (dom_ok and dow_ok)
        )
        matches = (
            candidate.month in month
            and day_ok
            and candidate.hour in hour
            and candidate.minute in minute
        )
        if matches:
            return candidate
        candidate += timedelta(minutes=1)
    return None


def compute_next_run(
    config: dict,
    *,
    start_at: datetime,
    last_run_at: datetime | None,
    now: datetime,
    timezone: str = "UTC",
) -> datetime | None:
    """The next time a recurrence fires, or None if none exists within its horizon."""
    tz = _validated_timezone(timezone)
    if "interval_seconds" in config:
        interval = timedelta(seconds=int(config["interval_seconds"]))
        base = last_run_at if last_run_at is not None else start_at
        if base > now:
            return base
        nxt = base + interval
        while nxt <= now:
            nxt += interval
        return nxt
    local_now = now.astimezone(tz)
    local_next = next_cron(config["cron"], local_now)
    if local_next is None:
        return None
    return local_next.astimezone(UTC)


async def list_schedules(
    session: AsyncSession, owner_user_id: uuid.UUID, *, limit: int, offset: int
) -> tuple[list[Schedule], int]:
    where = Schedule.owner_user_id == owner_user_id
    total = await session.scalar(select(func.count()).select_from(Schedule).where(where))
    rows = await session.scalars(
        select(Schedule).where(where).order_by(Schedule.created_at.desc()).limit(limit).offset(offset)
    )
    return list(rows), int(total or 0)


async def create_schedule(
    session: AsyncSession, owner_user_id: uuid.UUID, data: ScheduleCreateIn
) -> Schedule:
    workflow = await get_workflow(session, owner_user_id, data.workflow_id)
    if workflow is None:
        raise NotFoundError("Workflow not found")
    _validated_timezone(data.timezone)
    if data.end_at is not None and data.end_at <= data.start_at:
        raise ValidationFailedError("end_at must be after start_at")
    now = datetime.now(UTC)
    schedule = Schedule(
        workflow_id=data.workflow_id,
        owner_user_id=owner_user_id,
        timezone=data.timezone,
        recurrence_config=data.recurrence_config,
        start_at=data.start_at,
        end_at=data.end_at,
        is_enabled=data.is_enabled,
        next_run_at=compute_next_run(
            data.recurrence_config,
            start_at=data.start_at,
            last_run_at=None,
            now=now,
            timezone=data.timezone,
        ),
    )
    session.add(schedule)
    await session.flush()
    await session.refresh(schedule)
    return schedule


async def update_schedule(
    session: AsyncSession,
    owner_user_id: uuid.UUID,
    schedule_id: uuid.UUID,
    data: ScheduleUpdateIn,
) -> Schedule:
    schedule = await session.scalar(
        select(Schedule).where(
            Schedule.id == schedule_id, Schedule.owner_user_id == owner_user_id
        )
    )
    if schedule is None:
        raise NotFoundError("Schedule not found")
    if data.timezone is not None:
        _validated_timezone(data.timezone)
        schedule.timezone = data.timezone
    if data.recurrence_config is not None:
        schedule.recurrence_config = data.recurrence_config
    if data.end_at is not None:
        schedule.end_at = data.end_at
    if data.is_enabled is not None:
        schedule.is_enabled = data.is_enabled
    schedule.next_run_at = compute_next_run(
        schedule.recurrence_config,
        start_at=schedule.start_at,
        last_run_at=schedule.last_run_at,
        now=datetime.now(UTC),
        timezone=schedule.timezone,
    )
    await session.flush()
    await session.refresh(schedule)
    return schedule


async def delete_schedule(
    session: AsyncSession, owner_user_id: uuid.UUID, schedule_id: uuid.UUID
) -> None:
    schedule = await session.scalar(
        select(Schedule).where(
            Schedule.id == schedule_id, Schedule.owner_user_id == owner_user_id
        )
    )
    if schedule is None:
        raise NotFoundError("Schedule not found")
    await session.delete(schedule)
    await session.flush()


# --- Executions -------------------------------------------------------------


async def start_execution(
    session: AsyncSession,
    *,
    workflow_id: uuid.UUID,
    owner_user_id: uuid.UUID,
    trigger_type: str,
    input_data: dict,
) -> WorkflowExecution:
    workflow = await get_workflow(session, owner_user_id, workflow_id)
    if workflow is None:
        raise NotFoundError("Workflow not found")
    if workflow.status == "archived":
        raise ConflictError("An archived workflow cannot be run")
    execution = WorkflowExecution(
        workflow_id=workflow_id,
        owner_user_id=owner_user_id,
        trigger_type=trigger_type,
        status="pending",
        input_data=input_data,
    )
    session.add(execution)
    await session.flush()
    await session.refresh(execution)
    return execution


async def list_executions(
    session: AsyncSession,
    owner_user_id: uuid.UUID,
    *,
    workflow_id: uuid.UUID | None = None,
    limit: int,
    offset: int,
) -> tuple[list[WorkflowExecution], int]:
    where = WorkflowExecution.owner_user_id == owner_user_id
    if workflow_id is not None:
        where = where & (WorkflowExecution.workflow_id == workflow_id)
    total = await session.scalar(
        select(func.count()).select_from(WorkflowExecution).where(where)
    )
    rows = await session.scalars(
        select(WorkflowExecution).where(where).order_by(WorkflowExecution.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(rows), int(total or 0)


async def get_execution(
    session: AsyncSession, owner_user_id: uuid.UUID, execution_id: uuid.UUID
) -> WorkflowExecution | None:
    return await session.scalar(
        select(WorkflowExecution).where(
            WorkflowExecution.id == execution_id,
            WorkflowExecution.owner_user_id == owner_user_id,
        )
    )


async def list_step_executions(
    session: AsyncSession, execution_id: uuid.UUID
) -> list[WorkflowStepExecution]:
    rows = await session.scalars(
        select(WorkflowStepExecution)
        .where(WorkflowStepExecution.execution_id == execution_id)
        .order_by(WorkflowStepExecution.created_at)
    )
    return list(rows)


# --- Approvals --------------------------------------------------------------


async def list_approvals(
    session: AsyncSession,
    owner_user_id: uuid.UUID,
    *,
    status: str | None = None,
    limit: int,
    offset: int,
) -> tuple[list[WorkflowApproval], int]:
    where: ColumnElement[bool] = WorkflowApproval.execution_id.in_(
        select(WorkflowExecution.id).where(WorkflowExecution.owner_user_id == owner_user_id)
    )
    if status is not None:
        where = where & (WorkflowApproval.status == status)
    total = await session.scalar(
        select(func.count()).select_from(WorkflowApproval).where(where)
    )
    rows = await session.scalars(
        select(WorkflowApproval).where(where).order_by(WorkflowApproval.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(rows), int(total or 0)


async def review_approval(
    session: AsyncSession,
    owner_user_id: uuid.UUID,
    approval_id: uuid.UUID,
    data: ApprovalReviewIn,
) -> WorkflowApproval:

    approval = await session.scalar(
        select(WorkflowApproval).where(WorkflowApproval.id == approval_id)
    )
    if approval is None:
        raise NotFoundError("Approval not found")
    execution = await session.get(WorkflowExecution, approval.execution_id)
    if execution is None or execution.owner_user_id != owner_user_id:
        raise NotFoundError("Approval not found")
    if approval.status != "pending":
        raise ConflictError(f"Approval already {approval.status}")

    now = datetime.now(UTC)
    if data.decision == "rejected":
        approval.status = "rejected"
        approval.reviewed_by_user_id = owner_user_id
        approval.reviewed_at = now
        await _set_message_status(session, approval, "rejected")
        await session.flush()
        await session.refresh(approval)
        return approval

    approval.status = "approved"
    approval.approved_content = data.content or approval.original_content
    approval.reviewed_by_user_id = owner_user_id
    approval.reviewed_at = now
    await _set_message_status(session, approval, "approved")
    await session.flush()
    await session.refresh(approval)
    return approval


async def _set_message_status(
    session: AsyncSession, approval: WorkflowApproval, status: str
) -> None:
    from app.modules.email.models import EmailMessage

    raw_id = approval.original_content.get("message_id")
    if raw_id is None:
        return
    message = await session.get(EmailMessage, uuid.UUID(str(raw_id)))
    if message is None:
        return
    message.status = status
    if status == "approved":
        message.approved_at = datetime.now(UTC)
        message.subject = (approval.approved_content or approval.original_content).get(
            "subject", message.subject
        )
        message.body = (approval.approved_content or approval.original_content).get(
            "body", message.body
        )


# --- Step engine ------------------------------------------------------------


async def run_workflow_execution(
    execution_id: uuid.UUID, *, settings: Settings | None = None
) -> str:
    """Run a pending execution's steps in order, recording each step's history.

    Idempotent by status: a re-delivered execution that is already past `pending`
    returns its current status without re-running, mirroring the discovery job's
    atomic claim.
    """
    active = settings or get_settings()
    async with session_scope() as session:
        execution = await session.get(WorkflowExecution, execution_id)
        if execution is None:
            logger.warning("workflow_execution_missing", execution_id=str(execution_id))
            return "missing"
        if execution.status != "pending":
            return execution.status

        workflow = await session.get(Workflow, execution.workflow_id)
        if workflow is None:
            execution.status = "failed"
            execution.error_details = {"reason": "Workflow was deleted"}
            execution.completed_at = datetime.now(UTC)
            await session.commit()
            return "failed"

        execution.status = "running"
        execution.started_at = datetime.now(UTC)
        await session.commit()

        steps = workflow.workflow_definition.get("steps", [])
        ctx: dict[str, Any] = {
            "business_ids": list(execution.input_data.get("business_ids", [])),
        }
        outputs: dict[str, dict] = {}
        failed = False
        try:
            for step_def in steps:
                step = await _run_step(session, execution, step_def, ctx, outputs, active)
                outputs[step.step_key] = step.output_data
                if step.status == "failed":
                    failed = True
                    break
            execution.output_data = {"steps": outputs}
            execution.status = "failed" if failed else "completed"
            if failed:
                execution.error_details = {"reason": "One or more steps failed"}
            execution.completed_at = datetime.now(UTC)
            await session.commit()
            return execution.status
        except Exception as exc:  # noqa: BLE001 - a crashed run must still be recorded
            logger.error(
                "workflow_execution_crashed",
                execution_id=str(execution_id),
                error_type=type(exc).__name__,
            )
            execution.status = "failed"
            execution.error_details = {"reason": f"{type(exc).__name__}: {exc}"[:500]}
            execution.completed_at = datetime.now(UTC)
            await session.commit()
            return "failed"


async def _run_step(
    session: AsyncSession,
    execution: WorkflowExecution,
    step_def: dict,
    ctx: dict[str, Any],
    outputs: dict[str, dict],
    settings: Settings,
) -> WorkflowStepExecution:
    step = WorkflowStepExecution(
        execution_id=execution.id,
        step_key=step_def["key"],
        step_type=step_def["type"],
        status="running",
        input_data={"config": step_def.get("config", {})},
        started_at=datetime.now(UTC),
    )
    session.add(step)
    await session.commit()

    handler = _STEP_HANDLERS[step_def["type"]]
    try:
        output = await handler(session, execution, step, step_def.get("config", {}), ctx, settings)
        step.status = "completed"
        step.output_data = output
    except Exception as exc:  # noqa: BLE001 - step failures are recorded, not fatal
        reason = f"{type(exc).__name__}: {exc}"[:500]
        step.status = "failed"
        step.error_details = {"reason": reason}
        step.output_data = {"error": reason}
    step.completed_at = datetime.now(UTC)
    await session.commit()
    return step


def _business_ids(ctx: dict[str, Any]) -> list[uuid.UUID]:
    return [uuid.UUID(str(raw)) for raw in ctx.get("business_ids", [])]


async def _step_qualify(
    session: AsyncSession,
    execution: WorkflowExecution,
    step: WorkflowStepExecution,
    config: dict,
    ctx: dict[str, Any],
    settings: Settings,
) -> dict:
    del step, settings
    from app.modules.services_catalog.service import qualify_business

    service_id = uuid.UUID(str(config["service_id"]))
    results: list[dict] = []
    qualified = 0
    for business_id in _business_ids(ctx):
        try:
            opportunity = await qualify_business(
                session,
                owner_user_id=execution.owner_user_id,
                business_id=business_id,
                service_id=service_id,
            )
            if opportunity.status in ("qualified", "shortlisted"):
                qualified += 1
            results.append(
                {
                    "business_id": str(business_id),
                    "status": opportunity.status,
                    "score": float(opportunity.score or 0),
                }
            )
        except (LookupError, ValueError) as exc:
            results.append(
                {"business_id": str(business_id), "error": f"{type(exc).__name__}: {exc}"}
            )
    return {"qualified": qualified, "evaluated": len(results), "results": results}


async def _step_shortlist(
    session: AsyncSession,
    execution: WorkflowExecution,
    step: WorkflowStepExecution,
    config: dict,
    ctx: dict[str, Any],
    settings: Settings,
) -> dict:
    del step, settings
    from app.modules.businesses import repository
    from app.modules.services_catalog.service import opportunities_for_business

    only_qualified = bool(config.get("only_qualified", True))
    shortlisted = 0
    skipped: list[dict] = []
    for business_id in _business_ids(ctx):
        try:
            if only_qualified:
                opportunities = await opportunities_for_business(
                    session, execution.owner_user_id, business_id
                )
                statuses = {o.status for o in opportunities}
                if not statuses & {"qualified", "shortlisted"}:
                    skipped.append(
                        {"business_id": str(business_id), "reason": "not qualified"}
                    )
                    continue
            await repository.shortlist(
                session, owner_user_id=execution.owner_user_id, business_id=business_id
            )
            shortlisted += 1
        except LookupError as exc:
            skipped.append({"business_id": str(business_id), "reason": str(exc)})
    return {"shortlisted": shortlisted, "skipped": skipped}


async def _step_email_draft(
    session: AsyncSession,
    execution: WorkflowExecution,
    step: WorkflowStepExecution,
    config: dict,
    ctx: dict[str, Any],
    settings: Settings,
) -> dict:
    from app.modules.businesses.repository import get_business
    from app.modules.email import service as email_service
    from app.modules.email.models import EmailMessage
    from app.modules.email.schemas import EmailMessageCreateIn

    account_id = _optional_uuid(config.get("email_account_id"))
    campaign_id = _optional_uuid(config.get("campaign_id"))
    service_name = config.get("service_name")
    drafted: list[dict] = []
    skipped: list[dict] = []
    for business_id in _business_ids(ctx):
        business = await get_business(session, execution.owner_user_id, business_id)
        if business is None:
            skipped.append({"business_id": str(business_id), "reason": "not found"})
            continue
        recipient, recipient_name = _recipient_for(business)
        if recipient is None:
            skipped.append({"business_id": str(business_id), "reason": "no contactable email"})
            continue
        existing = await session.scalar(
            select(EmailMessage).where(
                EmailMessage.owner_user_id == execution.owner_user_id,
                EmailMessage.business_id == business_id,
                EmailMessage.recipient_email == recipient,
                EmailMessage.status.in_(("draft", "pending_approval", "approved")),
            )
        )
        if existing is not None:
            skipped.append({"business_id": str(business_id), "reason": "already drafted"})
            continue
        subject, body = email_service.render_draft(
            business,
            recipient_name=recipient_name,
            service_name=service_name,
            sender_name=settings.app_name,
        )
        message = await email_service.create_draft(
            session,
            execution.owner_user_id,
            EmailMessageCreateIn(
                recipient_email=recipient,
                subject=subject,
                body=body,
                business_id=business_id,
                campaign_id=campaign_id,
                email_account_id=account_id,
            ),
            workflow_execution_id=execution.id,
        )
        session.add(
            WorkflowApproval(
                execution_id=execution.id,
                step_execution_id=step.id,
                approval_type="email_send",
                status="pending",
                original_content={
                    "message_id": str(message.id),
                    "recipient_email": message.recipient_email,
                    "subject": message.subject,
                    "body": message.body,
                },
            )
        )
        drafted.append(
            {
                "business_id": str(business_id),
                "message_id": str(message.id),
                "recipient_email": message.recipient_email,
            }
        )
    await session.flush()
    return {"drafted": len(drafted), "skipped": skipped, "messages": drafted}


async def _step_send(
    session: AsyncSession,
    execution: WorkflowExecution,
    step: WorkflowStepExecution,
    config: dict,
    ctx: dict[str, Any],
    settings: Settings,
) -> dict:
    del step, ctx
    from app.modules.email import service as email_service
    from app.modules.email.models import EmailMessage

    rows = list(
        await session.scalars(
            select(EmailMessage).where(
                EmailMessage.owner_user_id == execution.owner_user_id,
                EmailMessage.workflow_execution_id == execution.id,
                EmailMessage.status == "approved",
            )
        )
    )
    if not rows:
        raise ValueError(
            "No approved messages to send. Approve drafts first, then re-run this workflow."
        )
    sent = 0
    failed = 0
    outcomes: list[dict] = []
    for message in rows:
        result = await email_service.send_message(
            session, execution.owner_user_id, message.id, settings=settings
        )
        outcomes.append({"message_id": str(message.id), **result})
        if result["status"] == "sent":
            sent += 1
        else:
            failed += 1
    return {"sent": sent, "failed": failed, "outcomes": outcomes}


def _optional_uuid(value: object) -> uuid.UUID | None:
    if value in (None, ""):
        return None
    return uuid.UUID(str(value))


def _recipient_for(business: Business) -> tuple[str | None, str | None]:
    if business.email:
        normalized = business.email.strip().lower()
        if "@" in normalized:
            return normalized, None
    for contact in business.contacts:
        if contact.email:
            normalized = contact.email.strip().lower()
            if "@" in normalized:
                return normalized, contact.full_name
    return None, None


_STEP_HANDLERS = {
    "qualify": _step_qualify,
    "shortlist": _step_shortlist,
    "email_draft": _step_email_draft,
    "send": _step_send,
}


# --- Task dispatch ----------------------------------------------------------


from app.workers.tasks import register_task  # noqa: E402


@register_task(RUN_TASK_NAME)
async def run_execution_task(*, execution_id: str) -> str:
    return await run_workflow_execution(uuid.UUID(execution_id))


@register_task(TICK_TASK_NAME)
async def run_due_schedules(*, settings: Settings | None = None) -> int:
    """Run every enabled schedule whose next_run_at has passed, advancing each.

    Configured as a periodic task; without a broker it is never invoked, and the
    "run now" path covers development. Returns how many executions were started.
    """
    active = settings or get_settings()
    started = 0
    now = datetime.now(UTC)
    async with session_scope() as session:
        due = list(
            await session.scalars(
                select(Schedule).where(
                    Schedule.is_enabled.is_(True),
                    Schedule.next_run_at.is_not(None),
                    Schedule.next_run_at <= now,
                )
            )
        )
        for schedule in due:
            if schedule.end_at is not None and now >= schedule.end_at:
                schedule.is_enabled = False
                continue
            execution = await start_execution(
                session,
                workflow_id=schedule.workflow_id,
                owner_user_id=schedule.owner_user_id,
                trigger_type="scheduled",
                input_data={},
            )
            schedule.last_run_at = now
            schedule.next_run_at = compute_next_run(
                schedule.recurrence_config,
                start_at=schedule.start_at,
                last_run_at=now,
                now=now,
                timezone=schedule.timezone,
            )
            await session.commit()
            await run_workflow_execution(execution.id, settings=active)
            started += 1
    return started


async def mark_run_checked(schedule_id: uuid.UUID, *, now: datetime) -> None:
    """Advance one schedule after a manual "run now" (owner-agnostic helper)."""
    async with session_scope() as session:
        schedule = await session.get(Schedule, schedule_id)
        if schedule is None:
            return
        schedule.last_run_at = now
        schedule.next_run_at = compute_next_run(
            schedule.recurrence_config,
            start_at=schedule.start_at,
            last_run_at=now,
            now=now,
            timezone=schedule.timezone,
        )
        await session.commit()

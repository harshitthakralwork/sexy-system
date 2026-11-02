from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request
from sqlalchemy import select

from app.core.audit import client_ip, record_audit
from app.core.database import AsyncSessionDep
from app.modules.auth.dependencies import CurrentUser, require_csrf_for_state_changes
from app.modules.automation import service
from app.modules.automation.models import (
    Schedule,
    Workflow,
    WorkflowExecution,
)
from app.modules.automation.schemas import (
    ApprovalListOut,
    ApprovalOut,
    ApprovalReviewIn,
    ExecutionListOut,
    ExecutionOut,
    ExecutionRunIn,
    ScheduleCreateIn,
    ScheduleListOut,
    ScheduleOut,
    ScheduleUpdateIn,
    StepExecutionOut,
    WorkflowCreateIn,
    WorkflowListOut,
    WorkflowOut,
    WorkflowRunOut,
    WorkflowUpdateIn,
)
from app.workers.dispatcher import SynchronousDispatcher, get_dispatcher

router = APIRouter(prefix="/workflows", tags=["automation"])

Csrf = Depends(require_csrf_for_state_changes())


def _workflow_out(row: Workflow) -> WorkflowOut:
    return WorkflowOut(
        id=row.id,
        name=row.name,
        description=row.description,
        module=row.module,
        workflow_definition=row.workflow_definition,
        status=row.status,
        version=row.version,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _schedule_out(row: Schedule) -> ScheduleOut:
    return ScheduleOut(
        id=row.id,
        workflow_id=row.workflow_id,
        timezone=row.timezone,
        recurrence_config=row.recurrence_config,
        start_at=row.start_at,
        end_at=row.end_at,
        next_run_at=row.next_run_at,
        last_run_at=row.last_run_at,
        is_enabled=row.is_enabled,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _execution_out(
    row: WorkflowExecution, steps: list[StepExecutionOut] | None = None
) -> ExecutionOut:
    return ExecutionOut(
        id=row.id,
        workflow_id=row.workflow_id,
        trigger_type=row.trigger_type,
        status=row.status,
        input_data=row.input_data,
        output_data=row.output_data,
        started_at=row.started_at,
        completed_at=row.completed_at,
        error_details=row.error_details,
        created_at=row.created_at,
        steps=steps,
    )


async def _dispatch(
    session: AsyncSessionDep,
    execution: WorkflowExecution,
    background: BackgroundTasks,
) -> str:
    dispatcher = get_dispatcher()
    if isinstance(dispatcher, SynchronousDispatcher):
        await session.commit()
        background.add_task(service.run_execution_task, execution_id=str(execution.id))
        return "inline"
    try:
        dispatcher.submit(service.RUN_TASK_NAME, {"execution_id": str(execution.id)})
    except Exception as exc:  # noqa: BLE001 - a missing broker is a reportable state
        execution.status = "failed"
        execution.error_details = {
            "reason": f"No worker could accept this run ({type(exc).__name__}). "
            "Set SPARKX_RUN_JOBS_SYNCHRONOUSLY=true to run inline in development."
        }
        execution.completed_at = datetime.now(UTC)
        return "blocked"
    return "queued"


# --- Workflows (collection) -------------------------------------------------
# Static sub-resource routes are declared before the dynamic ``/{workflow_id}``
# route: FastAPI matches in registration order, and ``GET /workflows/approvals``
# would otherwise be captured by ``/{workflow_id}`` and fail UUID validation.


@router.get("", response_model=WorkflowListOut)
async def list_workflows(
    session: AsyncSessionDep,
    user: CurrentUser,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> WorkflowListOut:
    rows, total = await service.list_workflows(session, user.id, limit=limit, offset=offset)
    return WorkflowListOut(
        items=[_workflow_out(row) for row in rows], total=total, limit=limit, offset=offset
    )


@router.post("", response_model=WorkflowOut, status_code=201, dependencies=[Csrf])
async def create_workflow(
    data: WorkflowCreateIn, session: AsyncSessionDep, user: CurrentUser, request: Request
) -> WorkflowOut:
    workflow = await service.create_workflow(session, user.id, data)
    await record_audit(
        session,
        action="automation.workflow_created",
        owner_user_id=user.id,
        entity_type="workflow",
        entity_id=workflow.id,
        ip_address=client_ip(request),
        metadata={"name": workflow.name, "steps": len(data.steps)},
    )
    return _workflow_out(workflow)


# --- Executions -------------------------------------------------------------


@router.get("/executions", response_model=ExecutionListOut)
async def list_executions(
    session: AsyncSessionDep,
    user: CurrentUser,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> ExecutionListOut:
    rows, total = await service.list_executions(session, user.id, limit=limit, offset=offset)
    return ExecutionListOut(
        items=[_execution_out(row) for row in rows], total=total, limit=limit, offset=offset
    )


@router.get("/executions/{execution_id}", response_model=ExecutionOut)
async def get_execution(
    execution_id: uuid.UUID, session: AsyncSessionDep, user: CurrentUser
) -> ExecutionOut:
    from app.core.exceptions import NotFoundError

    execution = await service.get_execution(session, user.id, execution_id)
    if execution is None:
        raise NotFoundError("Execution not found")
    steps = [
        StepExecutionOut(
            id=step.id,
            execution_id=step.execution_id,
            step_key=step.step_key,
            step_type=step.step_type,
            status=step.status,
            input_data=step.input_data,
            output_data=step.output_data,
            retry_count=step.retry_count,
            started_at=step.started_at,
            completed_at=step.completed_at,
            error_details=step.error_details,
        )
        for step in await service.list_step_executions(session, execution_id)
    ]
    return _execution_out(execution, steps=steps)


# --- Schedules --------------------------------------------------------------


@router.get("/schedules", response_model=ScheduleListOut)
async def list_schedules(
    session: AsyncSessionDep,
    user: CurrentUser,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> ScheduleListOut:
    rows, total = await service.list_schedules(session, user.id, limit=limit, offset=offset)
    return ScheduleListOut(
        items=[_schedule_out(row) for row in rows], total=total, limit=limit, offset=offset
    )


@router.post("/schedules", response_model=ScheduleOut, status_code=201, dependencies=[Csrf])
async def create_schedule(
    data: ScheduleCreateIn, session: AsyncSessionDep, user: CurrentUser, request: Request
) -> ScheduleOut:
    schedule = await service.create_schedule(session, user.id, data)
    await record_audit(
        session,
        action="automation.schedule_created",
        owner_user_id=user.id,
        entity_type="schedule",
        entity_id=schedule.id,
        ip_address=client_ip(request),
    )
    return _schedule_out(schedule)


@router.patch("/schedules/{schedule_id}", response_model=ScheduleOut, dependencies=[Csrf])
async def update_schedule(
    schedule_id: uuid.UUID,
    data: ScheduleUpdateIn,
    session: AsyncSessionDep,
    user: CurrentUser,
    request: Request,
) -> ScheduleOut:
    schedule = await service.update_schedule(session, user.id, schedule_id, data)
    await record_audit(
        session,
        action="automation.schedule_updated",
        owner_user_id=user.id,
        entity_type="schedule",
        entity_id=schedule.id,
        ip_address=client_ip(request),
    )
    return _schedule_out(schedule)


@router.delete("/schedules/{schedule_id}", status_code=204, dependencies=[Csrf])
async def delete_schedule(
    schedule_id: uuid.UUID, session: AsyncSessionDep, user: CurrentUser, request: Request
) -> None:
    await service.delete_schedule(session, user.id, schedule_id)
    await record_audit(
        session,
        action="automation.schedule_deleted",
        owner_user_id=user.id,
        entity_type="schedule",
        entity_id=schedule_id,
        ip_address=client_ip(request),
    )


@router.post(
    "/schedules/{schedule_id}/run",
    response_model=WorkflowRunOut,
    status_code=201,
    dependencies=[Csrf],
)
async def run_schedule_now(
    schedule_id: uuid.UUID,
    session: AsyncSessionDep,
    user: CurrentUser,
    request: Request,
    background: BackgroundTasks,
) -> WorkflowRunOut:
    from app.core.exceptions import NotFoundError

    schedule = await session.scalar(
        select(Schedule).where(Schedule.id == schedule_id, Schedule.owner_user_id == user.id)
    )
    if schedule is None:
        raise NotFoundError("Schedule not found")
    execution = await service.start_execution(
        session,
        workflow_id=schedule.workflow_id,
        owner_user_id=user.id,
        trigger_type="scheduled",
        input_data={},
    )
    mode = await _dispatch(session, execution, background)
    await service.mark_run_checked(schedule_id, now=datetime.now(UTC))
    await record_audit(
        session,
        action="automation.schedule_run",
        owner_user_id=user.id,
        entity_type="schedule",
        entity_id=schedule_id,
        ip_address=client_ip(request),
        metadata={"execution_id": str(execution.id), "dispatch": mode},
    )
    return WorkflowRunOut(execution_id=execution.id, status=execution.status)


# --- Approvals --------------------------------------------------------------


@router.get("/approvals", response_model=ApprovalListOut)
async def list_approvals(
    session: AsyncSessionDep,
    user: CurrentUser,
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> ApprovalListOut:
    rows, total = await service.list_approvals(
        session, user.id, status=status, limit=limit, offset=offset
    )
    return ApprovalListOut(
        items=[
            ApprovalOut(
                id=row.id,
                execution_id=row.execution_id,
                step_execution_id=row.step_execution_id,
                approval_type=row.approval_type,
                status=row.status,
                original_content=row.original_content,
                approved_content=row.approved_content,
                reviewed_by_user_id=row.reviewed_by_user_id,
                reviewed_at=row.reviewed_at,
                created_at=row.created_at,
            )
            for row in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/approvals/{approval_id}/review", response_model=ApprovalOut, dependencies=[Csrf])
async def review_approval(
    approval_id: uuid.UUID,
    data: ApprovalReviewIn,
    session: AsyncSessionDep,
    user: CurrentUser,
    request: Request,
) -> ApprovalOut:
    approval = await service.review_approval(session, user.id, approval_id, data)
    await record_audit(
        session,
        action="automation.approval_reviewed",
        owner_user_id=user.id,
        entity_type="workflow_approval",
        entity_id=approval.id,
        ip_address=client_ip(request),
        metadata={"decision": approval.status},
    )
    return ApprovalOut(
        id=approval.id,
        execution_id=approval.execution_id,
        step_execution_id=approval.step_execution_id,
        approval_type=approval.approval_type,
        status=approval.status,
        original_content=approval.original_content,
        approved_content=approval.approved_content,
        reviewed_by_user_id=approval.reviewed_by_user_id,
        reviewed_at=approval.reviewed_at,
        created_at=approval.created_at,
    )


# --- Workflows (item) -------------------------------------------------------


@router.get("/{workflow_id}", response_model=WorkflowOut)
async def get_workflow(
    workflow_id: uuid.UUID, session: AsyncSessionDep, user: CurrentUser
) -> WorkflowOut:
    workflow = await service.get_workflow(session, user.id, workflow_id)
    if workflow is None:
        from app.core.exceptions import NotFoundError

        raise NotFoundError("Workflow not found")
    return _workflow_out(workflow)


@router.patch("/{workflow_id}", response_model=WorkflowOut, dependencies=[Csrf])
async def update_workflow(
    workflow_id: uuid.UUID,
    data: WorkflowUpdateIn,
    session: AsyncSessionDep,
    user: CurrentUser,
    request: Request,
) -> WorkflowOut:
    workflow = await service.update_workflow(session, user.id, workflow_id, data)
    await record_audit(
        session,
        action="automation.workflow_updated",
        owner_user_id=user.id,
        entity_type="workflow",
        entity_id=workflow.id,
        ip_address=client_ip(request),
    )
    return _workflow_out(workflow)


@router.delete("/{workflow_id}", status_code=204, dependencies=[Csrf])
async def delete_workflow(
    workflow_id: uuid.UUID, session: AsyncSessionDep, user: CurrentUser, request: Request
) -> None:
    await service.delete_workflow(session, user.id, workflow_id)
    await record_audit(
        session,
        action="automation.workflow_deleted",
        owner_user_id=user.id,
        entity_type="workflow",
        entity_id=workflow_id,
        ip_address=client_ip(request),
    )


@router.post(
    "/{workflow_id}/run", response_model=WorkflowRunOut, status_code=201, dependencies=[Csrf]
)
async def run_workflow(
    workflow_id: uuid.UUID,
    session: AsyncSessionDep,
    user: CurrentUser,
    request: Request,
    background: BackgroundTasks,
    data: ExecutionRunIn | None = None,
) -> WorkflowRunOut:
    execution = await service.start_execution(
        session,
        workflow_id=workflow_id,
        owner_user_id=user.id,
        trigger_type="manual",
        input_data=data.input_data if data else {},
    )
    mode = await _dispatch(session, execution, background)
    await record_audit(
        session,
        action="automation.workflow_run",
        owner_user_id=user.id,
        entity_type="workflow",
        entity_id=workflow_id,
        ip_address=client_ip(request),
        metadata={"execution_id": str(execution.id), "dispatch": mode},
    )
    return WorkflowRunOut(execution_id=execution.id, status=execution.status)


@router.get("/{workflow_id}/executions", response_model=ExecutionListOut)
async def list_workflow_executions(
    workflow_id: uuid.UUID,
    session: AsyncSessionDep,
    user: CurrentUser,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> ExecutionListOut:
    rows, total = await service.list_executions(
        session, user.id, workflow_id=workflow_id, limit=limit, offset=offset
    )
    return ExecutionListOut(
        items=[_execution_out(row) for row in rows], total=total, limit=limit, offset=offset
    )

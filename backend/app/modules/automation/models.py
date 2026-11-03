from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.base import JSONType, TimestampMixin, UUIDPrimaryKeyMixin, UUIDType

WORKFLOW_STATUSES = ("draft", "active", "paused", "archived")
EXECUTION_STATUSES = ("pending", "running", "completed", "failed", "cancelled")
STEP_STATUSES = ("pending", "running", "completed", "failed", "skipped")
TRIGGER_TYPES = ("manual", "scheduled")
APPROVAL_STATUSES = ("pending", "approved", "rejected")
APPROVAL_TYPES = ("email_send",)

# The step vocabulary the engine can actually execute. `discovery` and `research`
# are deliberately absent: discovery is an independently schedulable job (Phase 1/3),
# and accepting a step the engine cannot run would turn a workflow into a mock. The
# approval gate is embodied by the workflow_approvals table + the send step's refusal
# to send unapproved messages, not by a runnable `approval` step.
STEP_TYPES = ("qualify", "shortlist", "email_draft", "send")


class Workflow(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A named, versioned sequence of steps the Automation Engine can run.

    `workflow_definition` is a validated JSON object: `{"steps": [{"key","type",...}]}`.
    `version` increments whenever the definition changes, so an execution keeps the
    definition it actually ran under.
    """

    __tablename__ = "workflows"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft','active','paused','archived')",
            name="ck_workflow_status",
        ),
        CheckConstraint("version >= 1", name="ck_workflow_version"),
    )

    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType,
        ForeignKey("users.id", name="fk_workflows_owner_user_id_users"),
        nullable=False, index=True,
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    module: Mapped[str] = mapped_column(
        String(50), nullable=False, default="leads", server_default=text("'leads'")
    )
    workflow_definition: Mapped[dict] = mapped_column(
        JSONType, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="draft", server_default=text("'draft'")
    )
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )


class WorkflowExecution(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One run of a workflow: trigger details, status, and in/output references.

    `input_data` and `output_data` are JSON documents; the step history lives in
    `workflow_step_executions` so every execution is independently inspectable.
    """

    __tablename__ = "workflow_executions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','running','completed','failed','cancelled')",
            name="ck_workflow_execution_status",
        ),
        CheckConstraint(
            "trigger_type IN ('manual','scheduled')",
            name="ck_workflow_execution_trigger",
        ),
        Index("ix_workflow_execution_workflow", "workflow_id", "created_at"),
    )

    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False, index=True
    )
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType,
        ForeignKey("users.id", name="fk_workflow_executions_owner_user_id_users"),
        nullable=False, index=True,
    )
    trigger_type: Mapped[str] = mapped_column(
        String(50), nullable=False, default="manual", server_default=text("'manual'")
    )
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="pending", server_default=text("'pending'")
    )
    input_data: Mapped[dict] = mapped_column(
        JSONType, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    output_data: Mapped[dict] = mapped_column(
        JSONType, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_details: Mapped[dict | None] = mapped_column(JSONType, nullable=True)


class WorkflowStepExecution(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One step's record inside one execution."""

    __tablename__ = "workflow_step_executions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','running','completed','failed','skipped')",
            name="ck_workflow_step_status",
        ),
        CheckConstraint(
            "step_type IN ('qualify','shortlist','email_draft','send')",
            name="ck_workflow_step_type",
        ),
        CheckConstraint("retry_count >= 0", name="ck_workflow_step_retry"),
        Index("ix_workflow_step_execution", "execution_id", "step_key"),
    )

    execution_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType,
        ForeignKey("workflow_executions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    step_key: Mapped[str] = mapped_column(String(100), nullable=False)
    step_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="pending", server_default=text("'pending'")
    )
    input_data: Mapped[dict] = mapped_column(
        JSONType, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    output_data: Mapped[dict] = mapped_column(
        JSONType, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    retry_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_details: Mapped[dict | None] = mapped_column(JSONType, nullable=True)


class Schedule(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A recurring trigger for a workflow.

    `recurrence_config` is one of two shapes, validated in the service:
    `{"interval_seconds": N}` or `{"cron": "..."}` (a five-field cron subset).
    `next_run_at` is computed and stored, never derived at read time, so a paused
    schedule keeps a stable answer to "when next?".
    """

    __tablename__ = "schedules"
    __table_args__ = (Index("ix_schedule_owner_workflow", "owner_user_id", "workflow_id"),)

    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType, ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False, index=True
    )
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType,
        ForeignKey("users.id", name="fk_schedules_owner_user_id_users"),
        nullable=False, index=True,
    )
    timezone: Mapped[str] = mapped_column(
        String(100), nullable=False, default="UTC", server_default=text("'UTC'")
    )
    recurrence_config: Mapped[dict] = mapped_column(
        JSONType, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )


class WorkflowApproval(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """The human-approval gate. Preserves original and edited content separately.

    `original_content` is what the engine generated; `approved_content` is what the
    reviewer actually signed off (identical unless they edited). Approval is distinct
    from delivery: an approved message can still fail to send.
    """

    __tablename__ = "workflow_approvals"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','approved','rejected')",
            name="ck_workflow_approval_status",
        ),
        CheckConstraint(
            "approval_type IN ('email_send')",
            name="ck_workflow_approval_type",
        ),
    )

    execution_id: Mapped[uuid.UUID] = mapped_column(
        UUIDType,
        ForeignKey("workflow_executions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    step_execution_id: Mapped[uuid.UUID | None] = mapped_column(
        UUIDType,
        ForeignKey("workflow_step_executions.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    approval_type: Mapped[str] = mapped_column(
        String(50), nullable=False, default="email_send", server_default=text("'email_send'")
    )
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="pending", server_default=text("'pending'")
    )
    original_content: Mapped[dict] = mapped_column(
        JSONType, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    approved_content: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUIDType, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

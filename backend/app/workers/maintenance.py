"""Scheduled maintenance that keeps background job state honest.

These run on a Celery beat schedule in production, and are also directly
callable so tests and operators can run them without a beat process.
"""

from __future__ import annotations

from app.core.config import get_settings
from app.core.database import session_scope
from app.core.logging import get_logger
from app.modules.discovery import job_service
from app.workers.tasks import register_task

logger = get_logger(__name__)

RECOVER_TASK_NAME = "sparkxflow.maintenance.recover_stale_jobs"


async def recover_stale_jobs(*, stale_after_seconds: int | None = None) -> int:
    """Fail jobs a dead worker left in `running`, so they can be retried.

    Idempotent: a job already moved on by another pass is simply not selected.
    """
    seconds = (
        stale_after_seconds
        if stale_after_seconds is not None
        else get_settings().stale_job_after_seconds
    )
    async with session_scope() as session:
        count = await job_service.recover_stale_jobs(session, stale_after_seconds=seconds)
    if count:
        logger.warning("stale_jobs_recovered", count=count)
    return count


@register_task(RECOVER_TASK_NAME)
async def run_recover_stale_jobs() -> int:
    """Inline/synchronous entry point under the same name the beat schedule uses."""
    return await recover_stale_jobs()

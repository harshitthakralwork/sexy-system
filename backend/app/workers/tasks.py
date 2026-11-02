from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable
from typing import Any

from app.workers.celery_app import celery_app

# name -> callable. Populated by the modules that own the work, not by the runner.
TASK_REGISTRY: dict[str, Callable[..., Any]] = {}


def register_task(name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Register a locally executable task under its Celery task name.

    One name, two execution paths: the same callable is what a Celery worker
    would run and what the synchronous dispatcher runs inline. Keeping the
    names identical prevents the two paths from drifting apart.
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        TASK_REGISTRY[name] = func
        return func

    return decorator


@celery_app.task(name="sparkxflow.discovery.run_job")
def run_discovery_job(job_id: str) -> str:
    """Worker entry point for a queued discovery job.

    It only adapts Celery's synchronous calling convention to the shared job
    body in `discovery.runner`. Importing that lazily keeps this module free of
    module-level dependencies on business code, and the deferred import is what
    stops the queue and the module owning the work from importing each other.
    """
    from app.modules.discovery.runner import execute

    return asyncio.run(execute(uuid.UUID(job_id)))


@celery_app.task(name="sparkxflow.maintenance.recover_stale_jobs")
def recover_stale_jobs_task() -> int:
    """Worker entry point for the scheduled stale-job recovery pass."""
    from app.workers.maintenance import recover_stale_jobs

    return asyncio.run(recover_stale_jobs())


@celery_app.task(name="sparkxflow.automation.run_workflow")
def run_workflow_task(execution_id: str) -> str:
    """Worker entry point for a queued workflow execution."""
    from app.modules.automation.service import run_workflow_execution

    return asyncio.run(run_workflow_execution(uuid.UUID(execution_id)))


@celery_app.task(name="sparkxflow.automation.tick_schedules")
def tick_schedules_task() -> int:
    """Worker entry point for the recurring-schedule sweep."""
    from app.modules.automation.service import run_due_schedules

    return asyncio.run(run_due_schedules())


@celery_app.task(name="sparkxflow.social.run_track")
def social_run_track_task(run_id: str) -> str:
    """Worker entry point for a queued social intelligence track run."""
    from app.modules.social.tracks import execute_track_run

    return asyncio.run(execute_track_run(uuid.UUID(run_id)))


@celery_app.task(name="sparkxflow.social.tick_tracks")
def social_tick_tracks_task() -> int:
    """Worker entry point for the scheduled social-track sweep."""
    from app.modules.social.tracks import run_due_tracks

    return asyncio.run(run_due_tracks())

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

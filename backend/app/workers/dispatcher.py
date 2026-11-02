from __future__ import annotations

import asyncio
import inspect
import uuid
from collections.abc import Callable
from typing import Any, Protocol

from app.core.config import get_settings
from app.core.exceptions import DomainError
from app.core.logging import correlation_id_var
from app.workers.celery_app import celery_app
from app.workers.tasks import TASK_REGISTRY


class TaskDispatcher(Protocol):
    """Runner-agnostic job submission.

    Business modules depend on this protocol, never on Celery, so the execution
    backend can change without touching them (architecture.md section 3.2).
    """

    def submit(self, task_name: str, payload: dict[str, Any]) -> str:
        """Queue a task and return an id usable for status tracking."""
        ...


class CeleryDispatcher:
    """Production path: publish to the broker, a worker executes later."""

    def submit(self, task_name: str, payload: dict[str, Any]) -> str:
        correlation_id = correlation_id_var.get()
        headers = {"X-Correlation-ID": correlation_id} if correlation_id else {}
        result = celery_app.send_task(task_name, kwargs=payload, headers=headers)
        return str(result.id)


class SynchronousDispatcher:
    """Fallback path for machines with no broker: execute inline and return.

    This exists so development is not blocked without Redis, not because it is
    a good production choice. It blocks the caller until the work finishes, so
    a large discovery sweep will hang the request. Scheduled workflows and
    anything long-running require the Celery path.
    """

    def __init__(self, registry: dict[str, Callable[..., Any]] | None = None) -> None:
        self.registry = TASK_REGISTRY if registry is None else registry

    def submit(self, task_name: str, payload: dict[str, Any]) -> str:
        handler = self.registry.get(task_name)
        if handler is None:
            raise DomainError(
                f"No locally registered task named '{task_name}'",
                details={"task": task_name, "known": sorted(self.registry)},
            )
        result = handler(**payload)
        if inspect.isawaitable(result):
            # An async task called from a synchronous request path has no loop
            # to join, so it gets its own. Never nest this inside a running loop.
            result = asyncio.run(_await_once(result))
        del result
        return f"sync-{uuid.uuid4().hex}"


async def _await_once(awaitable: Any) -> Any:
    return await awaitable


def get_dispatcher() -> TaskDispatcher:
    """Dispatcher selection is configuration, so tests and the fallback host
    path can use it without any module knowing which runner is active."""
    if get_settings().run_jobs_synchronously:
        return SynchronousDispatcher()
    return CeleryDispatcher()

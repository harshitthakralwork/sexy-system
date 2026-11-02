from __future__ import annotations

from collections.abc import Callable
from typing import Any

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

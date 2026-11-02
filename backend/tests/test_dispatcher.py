from __future__ import annotations

from typing import Any

import pytest

from app.core.config import Settings
from app.core.exceptions import DomainError
from app.workers.dispatcher import CeleryDispatcher, SynchronousDispatcher, get_dispatcher


def test_synchronous_dispatcher_runs_a_registered_task() -> None:
    calls: list[dict[str, Any]] = []

    def handler(**kwargs: Any) -> None:
        calls.append(kwargs)

    dispatcher = SynchronousDispatcher(registry={"sparkxflow.discovery.demo": handler})
    task_id = dispatcher.submit("sparkxflow.discovery.demo", {"job_id": "abc"})

    assert calls == [{"job_id": "abc"}]
    assert task_id.startswith("sync-")


def test_synchronous_dispatcher_awaitables_complete() -> None:
    seen: list[str] = []

    async def handler(value: str) -> None:
        seen.append(value)

    dispatcher = SynchronousDispatcher(registry={"async.task": handler})
    dispatcher.submit("async.task", {"value": "done"})
    assert seen == ["done"]


def test_unknown_task_fails_loudly_instead_of_silently_noopping() -> None:
    """A submission that quietly does nothing is the worst possible outcome:
    the job row would read 'queued' forever."""
    dispatcher = SynchronousDispatcher(registry={})
    with pytest.raises(DomainError, match="No locally registered task"):
        dispatcher.submit("sparkxflow.discovery.missing", {})


def test_synchronous_dispatcher_is_not_valid_in_production() -> None:
    problems = Settings(
        _env_file=None,
        app_env="production",
        signing_secret="x" * 32,
        cookie_secure=True,
        database_url="postgresql+asyncpg://u:p@db.internal/sparkxflow",
        run_jobs_synchronously=True,
    ).validate_for_startup()
    assert any("RUN_JOBS_SYNCHRONOUSLY" in problem for problem in problems)


def test_default_selection_is_the_queued_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SPARKX_RUN_JOBS_SYNCHRONOUSLY", raising=False)
    from app.core import config as config_module

    config_module.get_settings.cache_clear()
    assert isinstance(get_dispatcher(), CeleryDispatcher)
    config_module.get_settings.cache_clear()


def test_configuration_can_select_the_inline_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPARKX_RUN_JOBS_SYNCHRONOUSLY", "true")
    from app.core import config as config_module

    config_module.get_settings.cache_clear()
    assert isinstance(get_dispatcher(), SynchronousDispatcher)
    config_module.get_settings.cache_clear()

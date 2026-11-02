from __future__ import annotations

from celery import Celery

from app.core.config import get_settings


def make_celery() -> Celery:
    """Celery app wired from settings.

    The API layer never imports this directly — it goes through
    ``app.workers.dispatcher`` so the runner can be swapped without touching
    business modules, as required by architecture.md section 3.2.
    """
    settings = get_settings()
    celery = Celery(
        "sparkxflow",
        broker=settings.celery_broker_url,
        backend=settings.celery_result_backend,
    )
    celery.conf.update(
        timezone="UTC",
        enable_utc=True,
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        worker_prefetch_multiplier=1,
        task_track_started=True,
        result_expires=60 * 60 * 24,
        task_default_queue="default",
        task_routes={
            "sparkxflow.discovery.*": {"queue": "discovery"},
            "sparkxflow.enrichment.*": {"queue": "enrichment"},
            "sparkxflow.qualification.*": {"queue": "qualification"},
            "sparkxflow.exports.*": {"queue": "io"},
            "sparkxflow.retention.*": {"queue": "scheduled"},
            "sparkxflow.maintenance.*": {"queue": "scheduled"},
        },
        # Scheduled work runs from a separate `celery beat` process; the schedule
        # is data here so the worker image and the beat image stay in lockstep.
        beat_schedule={
            "recover-stale-jobs": {
                "task": "sparkxflow.maintenance.recover_stale_jobs",
                "schedule": 600.0,
            },
        },
        broker_transport_options={"visibility_timeout": 3600},
    )
    celery.autodiscover_tasks(["app.workers"], related_name="tasks")
    return celery


celery_app = make_celery()

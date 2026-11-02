from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import get_settings

router = APIRouter(tags=["system"])


class RuntimeInfo(BaseModel):
    app_name: str
    environment: str
    api_version: str
    default_region: str
    execution_model: str
    ai_enabled: bool
    registration_open: bool
    modules_enabled: list[str]


@router.get("/info", response_model=RuntimeInfo)
async def info() -> RuntimeInfo:
    """Runtime configuration the frontend needs before it renders anything.

    Exposes capabilities and limits, never secrets. `ai_enabled` and
    `registration_open` are reported honestly so the UI cannot imply a feature
    that is switched off, or a signup flow that the operator has closed.
    """
    settings = get_settings()
    return RuntimeInfo(
        app_name=settings.app_name,
        environment=settings.app_env,
        api_version="v1",
        default_region=settings.default_region,
        execution_model="local_first",
        ai_enabled=False,
        registration_open=settings.allow_registration,
        modules_enabled=[
            "auth",
            "sources",
            "discovery",
            "businesses",
            "crm",
            "services_catalog",
            "startups",
            "exports",
        ],
    )

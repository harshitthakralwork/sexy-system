from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import get_settings

api_router = APIRouter()


class RuntimeInfo(BaseModel):
    app_name: str
    environment: str
    api_version: str
    default_region: str
    execution_model: str
    ai_enabled: bool
    modules_enabled: list[str]


@api_router.get("/info", response_model=RuntimeInfo, tags=["system"])
async def info() -> RuntimeInfo:
    """Runtime configuration the frontend needs before it renders anything.

    Exposes capabilities and limits, never secrets. ``ai_enabled`` is reported
    honestly so the UI cannot imply a feature that is switched off.
    """
    settings = get_settings()
    return RuntimeInfo(
        app_name=settings.app_name,
        environment=settings.app_env,
        api_version="v1",
        default_region=settings.default_region,
        execution_model="local_first",
        ai_enabled=False,
        modules_enabled=["auth", "sources", "discovery", "businesses", "crm", "exports"],
    )

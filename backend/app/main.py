from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import api_router
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.core.middleware import CorrelationIdMiddleware, RequestResponseLoggingMiddleware
from app.modules.health.router import router as health_router
from app.shared.version import APP_VERSION

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging()

    problems = settings.validate_for_startup()
    if problems:
        # Refuse to serve rather than run with a misconfigured security setting.
        for problem in problems:
            logger.error("startup_configuration_error", problem=problem)
        raise RuntimeError("Invalid configuration for production startup")

    settings.export_dir.mkdir(parents=True, exist_ok=True)
    logger.info(
        "application_started",
        environment=settings.app_env,
        version=APP_VERSION,
        execution_model="local_first",
    )
    yield
    logger.info("application_stopping")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=APP_VERSION,
        docs_url="/docs",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    app.add_middleware(RequestResponseLoggingMiddleware)
    app.add_middleware(CorrelationIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Correlation-ID"],
    )

    register_exception_handlers(app)
    app.include_router(health_router, prefix="/health", tags=["health"])
    app.include_router(api_router, prefix=settings.api_v1_prefix)

    @app.get("/", include_in_schema=False)
    async def root() -> dict[str, str]:
        return {"name": settings.app_name, "version": APP_VERSION, "docs": "/docs"}

    return app


app = create_app()

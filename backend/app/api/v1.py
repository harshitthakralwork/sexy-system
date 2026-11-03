from __future__ import annotations

from fastapi import APIRouter

from app.api.info import router as info_router
from app.modules.analytics.router import router as analytics_router
from app.modules.auth.router import router as auth_router
from app.modules.automation.router import router as automation_router
from app.modules.businesses.router import router as businesses_router
from app.modules.crm.router import router as crm_router
from app.modules.discovery.router import router as discovery_router
from app.modules.email.router import router as email_router
from app.modules.exports.router import exports_router, imports_router
from app.modules.search.router import router as search_router
from app.modules.services_catalog.router import router as services_router
from app.modules.social.router import router as social_router
from app.modules.sources.router import router as sources_router
from app.modules.startups.router import router as startups_router

api_router = APIRouter()
api_router.include_router(info_router)
api_router.include_router(auth_router)
api_router.include_router(discovery_router)
api_router.include_router(businesses_router)
api_router.include_router(crm_router)
api_router.include_router(services_router)
api_router.include_router(startups_router)
api_router.include_router(social_router)
api_router.include_router(automation_router)
api_router.include_router(email_router)
api_router.include_router(search_router)
api_router.include_router(analytics_router)
api_router.include_router(sources_router)
api_router.include_router(exports_router)
api_router.include_router(imports_router)

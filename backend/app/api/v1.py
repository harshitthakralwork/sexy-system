from __future__ import annotations

from fastapi import APIRouter

from app.api.info import router as info_router
from app.modules.auth.router import router as auth_router
from app.modules.businesses.router import router as businesses_router
from app.modules.crm.router import router as crm_router
from app.modules.discovery.router import router as discovery_router
from app.modules.services_catalog.router import router as services_router
from app.modules.social.router import router as social_router
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

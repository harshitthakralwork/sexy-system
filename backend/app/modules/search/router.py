from __future__ import annotations

from fastapi import APIRouter, Query

from app.core.database import AsyncSessionDep
from app.modules.auth.dependencies import CurrentUser
from app.modules.search import service
from app.modules.search.schemas import GlobalSearchOut, SearchGroup

router = APIRouter(prefix="/search", tags=["search"])


@router.get("", response_model=GlobalSearchOut)
async def global_search(
    session: AsyncSessionDep,
    user: CurrentUser,
    q: str = Query(default="", max_length=200),
    limit: int = Query(default=10, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
) -> GlobalSearchOut:
    result = await service.search_all(session, user.id, q, limit=limit, offset=offset)
    groups = {name: SearchGroup(**group) for name, group in result["groups"].items()}
    return GlobalSearchOut(
        query=result["query"],
        limit=limit,
        offset=offset,
        groups=groups,
        total=result["total"],
    )

"""Global Search — one cross-entity query over everything the operator owns.

It calls the existing per-entity list functions rather than re-implementing any of
them, so ownership scoping, ILIKE matching and totals stay exactly where they
already live. It searches the surfaces that actually have text to match — leads,
startups, collected social intelligence, saved items and discovery tracks — and
returns them grouped so the UI can offer a real destination per hit. No ranking is
invented: each group is the underlying query's own ordering (recent first), and the
only aggregate number reported is the sum of the per-group totals the queries
returned.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import Text, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.businesses.repository import BusinessFilters, list_businesses
from app.modules.social import tracks as social_tracks
from app.modules.social.models import SocialSearchTrack
from app.modules.startups.service import list_startups

# The five entity kinds the global search covers.
KINDS = ("businesses", "startups", "social_results", "saved", "tracks")


def _empty_group() -> dict[str, Any]:
    return {"items": [], "total": 0}


async def _search_tracks(
    session: AsyncSession, owner: uuid.UUID, q: str, limit: int, offset: int
) -> tuple[list[dict[str, Any]], int]:
    pattern = f"%{q}%"
    conds = [
        SocialSearchTrack.owner_user_id == owner,
        SocialSearchTrack.name.ilike(pattern)
        | cast(SocialSearchTrack.keywords, Text).ilike(pattern),
    ]
    total = await session.scalar(
        select(func.count()).select_from(SocialSearchTrack).where(*conds)
    )
    rows = list(
        await session.scalars(
            select(SocialSearchTrack)
            .where(*conds)
            .order_by(SocialSearchTrack.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    )
    items = [
        {
            "kind": "track",
            "id": str(track.id),
            "title": track.name,
            "subtitle": f"{track.track_type} · {', '.join(track.platforms) or 'no sources'}",
            "url": None,
            "confidence": None,
        }
        for track in rows
    ]
    return items, int(total or 0)


def _intelligence_items(rows: list[tuple], saved_only: bool) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for content, slug, username in rows:
        preview = (content.title or content.snippet or content.content_text or "")[:120]
        confidence = (
            float(content.confidence_score) if content.confidence_score is not None else None
        )
        bits = [content.classification or "Unclassified", slug]
        if username:
            bits.append(str(username))
        items.append(
            {
                "kind": "saved" if saved_only else "social_result",
                "id": str(content.id),
                "title": preview or "(untitled)",
                "subtitle": " · ".join(b for b in bits if b),
                "url": content.content_url,
                "confidence": confidence,
            }
        )
    return items


async def search_all(
    session: AsyncSession, owner_user_id: uuid.UUID, q: str, *, limit: int, offset: int
) -> dict[str, Any]:
    query = (q or "").strip()
    groups: dict[str, dict[str, Any]] = {kind: _empty_group() for kind in KINDS}
    if not query:
        return {"query": query, "groups": groups, "total": 0}

    # Leads: reuse the businesses filter (matches name / domain / city / category).
    businesses, businesses_total = await list_businesses(
        session, owner_user_id, BusinessFilters(query=query, limit=limit, offset=offset)
    )
    groups["businesses"] = {
        "items": [
            {
                "kind": "business",
                "id": str(b.id),
                "title": b.name,
                "subtitle": " · ".join(x for x in (b.primary_category, b.city) if x) or None,
                "url": None,
                "confidence": None,
            }
            for b in businesses
        ],
        "total": businesses_total,
    }

    # Startups: reuse the startups list (name / description / domain).
    startups, startups_total = await list_startups(
        session,
        owner_user_id=owner_user_id,
        query=query,
        industry=None,
        country=None,
        funding_stage=None,
        status=None,
        watchlist_id=None,
        limit=limit,
        offset=offset,
    )
    groups["startups"] = {
        "items": [
            {
                "kind": "startup",
                "id": str(s.id),
                "title": s.name,
                "subtitle": " · ".join(x for x in (s.industry, s.city or s.country) if x) or None,
                "url": s.website_url,
                "confidence": None,
            }
            for s in startups
        ],
        "total": startups_total,
    }

    # Social intelligence results (content text / title).
    results, results_total = await social_tracks.list_intelligence(
        session, owner_user_id, query=query, limit=limit, offset=offset
    )
    groups["social_results"] = {
        "items": _intelligence_items(results, saved_only=False),
        "total": results_total,
    }

    # Saved items, matched through their underlying collected content.
    saved, saved_total = await social_tracks.list_intelligence(
        session, owner_user_id, query=query, saved_only=True, limit=limit, offset=offset
    )
    groups["saved"] = {"items": _intelligence_items(saved, saved_only=True), "total": saved_total}

    # Discovery tracks (name / keywords).
    tracks, tracks_total = await _search_tracks(session, owner_user_id, query, limit, offset)
    groups["tracks"] = {"items": tracks, "total": tracks_total}

    total = sum(group["total"] for group in groups.values())
    return {"query": query, "groups": groups, "total": total}

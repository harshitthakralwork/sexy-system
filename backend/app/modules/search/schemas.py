from __future__ import annotations

from pydantic import BaseModel


class GlobalSearchItem(BaseModel):
    kind: str
    id: str
    title: str
    subtitle: str | None = None
    url: str | None = None
    confidence: float | None = None


class SearchGroup(BaseModel):
    items: list[GlobalSearchItem]
    total: int


class GlobalSearchOut(BaseModel):
    query: str
    limit: int
    offset: int
    groups: dict[str, SearchGroup]
    total: int

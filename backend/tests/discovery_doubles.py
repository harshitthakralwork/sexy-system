"""Test doubles shared by the discovery job and map tests.

Stub adapters stand in for the *network* only. The pipeline, the store, the job
rows and the tile planner are the real ones, so a passing test here still proves
the product code ran.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

import pytest

from app.modules.discovery import runner
from app.modules.discovery.adapters.base import (
    AdapterCapabilities,
    DiscoveredItem,
    HealthResult,
)

CAPABILITIES = AdapterCapabilities(
    adapter_key="overpass",
    name="OpenStreetMap (Overpass API)",
    slug="overpass",
    category="geographic",
    supported_query_types=("category", "radius"),
    supported_filters=("radius_km",),
    available_fields=("name", "latitude", "longitude"),
    geographic_coverage="Fixture coverage note, standing in for the real source.",
)


class StubAdapter:
    """Returns prepared items, or fails on purpose when asked to."""

    def __init__(
        self,
        items: list[DiscoveredItem] | None = None,
        error: Exception | None = None,
        *,
        capabilities: AdapterCapabilities = CAPABILITIES,
        capped: bool = False,
    ):
        self._items = items or []
        self._error = error
        self._capabilities = capabilities
        self._capped = capped
        self.requests_made = 0
        self.queries: list[Any] = []

    @property
    def capabilities(self) -> AdapterCapabilities:
        return self._capabilities

    @property
    def last_capped(self) -> bool:
        return self._capped

    async def validate_config(self, config: dict[str, Any]) -> None:
        del config

    async def health_check(self) -> HealthResult:
        return HealthResult(status="working")

    async def discover(self, query: Any) -> list[DiscoveredItem]:
        self.queries.append(query)
        self.requests_made += 1
        if self._error is not None:
            raise self._error
        return list(self._items)

    async def aclose(self) -> None:
        return None


def item(domain: str, name: str, *, external_id: str | None = None) -> DiscoveredItem:
    """A distinct business. The phone is unique per fixture so two items are
    never merged as duplicates of each other by accident."""
    phone = f"+91 9{str(uuid.uuid4().int % 10**9).zfill(9)}"
    return DiscoveredItem(
        external_id=external_id or f"node-{domain}",
        source_url=f"https://{domain}/",
        title_hint=name,
        raw_data={
            "name": name,
            "website": f"https://{domain}",
            "city": "Bengaluru",
            "phone": phone,
        },
    )


def unidentified() -> DiscoveredItem:
    """A record with no name and no domain: real noise from a real source."""
    return DiscoveredItem(
        external_id="node-junk",
        source_url=None,
        raw_data={"description": "something was mentioned here"},
    )


def unique_domain() -> str:
    return f"stub-{uuid.uuid4().hex[:8]}.dev"


@pytest.fixture()
def stub_adapters(monkeypatch: pytest.MonkeyPatch) -> Callable[[list[StubAdapter]], None]:
    """Replace adapter construction with the given stubs."""

    def install(adapters: list[StubAdapter]) -> None:
        built = [(adapter.capabilities.slug, adapter) for adapter in adapters]

        def build(settings: Any, slugs: Any) -> list[tuple[str, Any]]:
            del settings, slugs
            return built

        monkeypatch.setattr(runner, "build_adapters", build)

    return install

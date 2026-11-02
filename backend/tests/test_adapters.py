from __future__ import annotations

from typing import Any

import httpx
import pytest

from app.modules.discovery.adapters.base import (
    AccessDeniedError,
    DiscoveryQuery,
    LocationSpec,
    MalformedResponseError,
    RateLimitedError,
    UnsupportedQueryError,
)
from app.modules.discovery.adapters.overpass import OverpassAdapter
from app.modules.discovery.adapters.searxng import SearxngAdapter


def client_for(handler: Any) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://stub")


SEARX_RESULTS = {
    "results": [
        {
            "title": "Spark Coffee | Indiranagar Bengaluru",
            "url": "https://sparkcoffee.in/",
            "content": "Specialty coffee roastery and cafe",
            "engine": "google",
        },
        {
            "title": "Brew Theory",
            "url": "https://www.brewtheory.co.uk",
            "content": "Coffee shop",
            "engine": "bing",
        },
    ],
    "answers": [],
}


@pytest.mark.asyncio
async def test_searxng_maps_results_without_inventing_fields() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["format"] == "json"
        return httpx.Response(200, json=SEARX_RESULTS)

    adapter = SearxngAdapter("http://searxng.local", client=client_for(handler))
    items = await adapter.discover(DiscoveryQuery(keywords=("coffee",), max_results=10))

    assert [item.title_hint for item in items] == [
        "Spark Coffee | Indiranagar Bengaluru",
        "Brew Theory",
    ]
    assert items[0].source_url == "https://sparkcoffee.in/"
    # No phone or email was in the payload, so none appears.
    assert "phone" not in items[0].raw_data


@pytest.mark.asyncio
async def test_searxng_paginates_until_results_run_short() -> None:
    pages_seen: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        page = request.url.params["pageno"]
        pages_seen.append(page)
        if page == "1":
            body = {
                "results": [{"title": f"hit {i}", "url": f"https://a{i}.test"} for i in range(20)]
            }
        else:
            body = {"results": [{"title": "last", "url": "https://z.test"}]}
        return httpx.Response(200, json=body)

    adapter = SearxngAdapter(
        "http://searxng.local", results_per_page=20, max_pages=3, client=client_for(handler)
    )
    items = await adapter.discover(DiscoveryQuery(keywords=("cafes",), max_results=50))

    assert pages_seen == ["1", "2"]
    assert len(items) == 21


@pytest.mark.asyncio
async def test_searxng_respects_max_results() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"results": [{"title": f"t{i}", "url": f"https://x{i}.test"} for i in range(20)]},
        )

    adapter = SearxngAdapter("http://searxng.local", client=client_for(handler))
    items = await adapter.discover(DiscoveryQuery(keywords=("cafes",), max_results=5))
    assert len(items) == 5


@pytest.mark.asyncio
async def test_non_json_body_is_reported_as_json_being_disabled() -> None:
    """The most common real failure: an instance serving HTML because the JSON
    format was never enabled. The message has to name the cause."""

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>limiter message</html>")

    adapter = SearxngAdapter("http://searxng.local", client=client_for(handler))
    with pytest.raises(MalformedResponseError, match="JSON format"):
        await adapter.discover(DiscoveryQuery(keywords=("coffee",)))


@pytest.mark.asyncio
async def test_blocked_instance_reports_access_denied_not_empty_results() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, text="forbidden")

    adapter = SearxngAdapter("http://searxng.local", client=client_for(handler))
    with pytest.raises(AccessDeniedError):
        await adapter.discover(DiscoveryQuery(keywords=("coffee",)))


@pytest.mark.asyncio
async def test_rate_limit_is_classified_as_retryable() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429)

    adapter = SearxngAdapter("http://searxng.local", client=client_for(handler))
    with pytest.raises(RateLimitedError) as excinfo:
        await adapter.discover(DiscoveryQuery(keywords=("coffee",)))
    assert excinfo.value.retryable is True


@pytest.mark.asyncio
async def test_searxng_health_check_flags_an_instance_without_json() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<!doctype html><html>")

    adapter = SearxngAdapter("http://searxng.local", client=client_for(handler))
    health = await adapter.health_check()
    assert health.status == "degraded"
    assert "JSON" in (health.detail or "")


@pytest.mark.asyncio
async def test_empty_query_is_rejected_before_any_network_call() -> None:
    calls: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, json=SEARX_RESULTS)

    adapter = SearxngAdapter("http://searxng.local", client=client_for(handler))
    with pytest.raises(UnsupportedQueryError):
        await adapter.discover(DiscoveryQuery())
    assert calls == []


OSM_PAYLOAD = {
    "elements": [
        {
            "type": "node",
            "id": 1234,
            "lat": 12.9716,
            "lon": 77.5946,
            "tags": {
                "name": "Spark Coffee",
                "shop": "coffee",
                "phone": "+91 98765 43210",
                "website": "https://sparkcoffee.in",
                "addr:street": "100 Feet Road",
                "addr:city": "Bengaluru",
            },
        },
        {"type": "node", "id": 5678, "lat": 12.98, "lon": 77.60, "tags": {"shop": "bakery"}},
        {"type": "way", "id": 99, "tags": {"highway": "residential"}},
    ]
}


@pytest.mark.asyncio
async def test_overpass_maps_named_elements_and_keeps_attribution() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/interpreter" or request.url.path.endswith("interpreter")
        return httpx.Response(200, json=OSM_PAYLOAD)

    adapter = OverpassAdapter("https://overpass.test", client=client_for(handler))
    items = await adapter.discover(
        DiscoveryQuery(
            category="shop",
            location=LocationSpec(center=(12.9716, 77.5946), radius_km=2),
            max_results=50,
        )
    )

    # The unnamed shop and the residential way are not business records.
    assert len(items) == 2
    assert items[0].title_hint == "Spark Coffee"
    assert items[0].external_id == "node/1234"
    assert items[0].source_url == "https://www.openstreetmap.org/node/1234"
    assert items[0].raw_data["phone"] == "+91 98765 43210"


@pytest.mark.asyncio
async def test_overpass_query_uses_metre_radius() -> None:
    adapter = OverpassAdapter(client=client_for(lambda request: httpx.Response(200, json={})))
    query = DiscoveryQuery(
        category="amenity=cafe",
        location=LocationSpec(center=(12.9, 77.5), radius_km=3.5),
        max_results=20,
    )
    body = adapter.build_query(query)
    assert "around:3500,12.9,77.5" in body
    assert '["amenity"="cafe"]' in body
    assert "out center 20;" in body


@pytest.mark.asyncio
async def test_overpass_union_statements_terminate_with_semicolons() -> None:
    """D4 found the shipped query was rejected by the real interpreter.

    Overpass QL requires every statement inside a union block to end with a
    semicolon; the old builder emitted `(node[...](around:...))` and the live
    endpoint answered `parse error: ';' expected - ')' found`. Mocked transports
    could never have caught that, which is why the shape is asserted here.
    """
    adapter = OverpassAdapter(client=client_for(lambda request: httpx.Response(200, json={})))
    body = adapter.build_query(
        DiscoveryQuery(
            category="shop", location=LocationSpec(center=(12.9, 77.5), radius_km=1), max_results=5
        )
    )
    assert "(nwr[\"shop\"](around:1000,12.9,77.5););" in body


@pytest.mark.asyncio
async def test_overpass_searches_ways_and_relations_not_only_nodes() -> None:
    """A hospital mapped as a building is a way. Reading nodes only would report
    an area as thinly covered when the data is there in another element type."""
    adapter = OverpassAdapter(client=client_for(lambda request: httpx.Response(200, json={})))
    body = adapter.build_query(
        DiscoveryQuery(
            category="amenity=hospital",
            location=LocationSpec(center=(29.1499, 75.7211), radius_km=5),
            max_results=10,
        )
    )
    assert body.count("nwr[") == 1
    assert "(node[" not in body


@pytest.mark.asyncio
async def test_overpass_uses_centre_of_a_way_as_the_pin_location() -> None:
    payload = {
        "elements": [
            {
                "type": "way",
                "id": 4444,
                "center": {"lat": 28.61, "lon": 77.21},
                "tags": {"amenity": "hospital", "name": "St. Stephen's"},
            }
        ]
    }

    async def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(200, json=payload)

    adapter = OverpassAdapter("https://overpass.test", client=client_for(handler))
    items = await adapter.discover(
        DiscoveryQuery(
            category="amenity=hospital",
            location=LocationSpec(center=(28.61, 77.21), radius_km=5),
            max_results=10,
        )
    )
    assert items[0].latitude == 28.61
    assert items[0].longitude == 77.21
    assert items[0].external_id == "way/4444"


@pytest.mark.asyncio
async def test_overpass_reports_a_truncated_answer_as_truncated() -> None:
    """Exactly `limit` elements means the source stopped early, not that the area
    is empty. Tiles and coverage claims depend on telling those apart."""

    def elements(count: int) -> dict[str, object]:
        return {
            "elements": [
                {
                    "type": "node",
                    "id": index,
                    "lat": 12.9,
                    "lon": 77.5,
                    "tags": {"name": f"Shop {index}"},
                }
                for index in range(count)
            ]
        }

    async def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(200, json=elements(3))

    adapter = OverpassAdapter("https://overpass.test", client=client_for(handler))
    await adapter.discover(
        DiscoveryQuery(
            category="shop", location=LocationSpec(center=(12.9, 77.5), radius_km=1), max_results=3
        )
    )
    assert adapter.last_capped is True

    async def short(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(200, json=elements(2))

    capped_adapter = OverpassAdapter("https://overpass.test", client=client_for(short))
    await capped_adapter.discover(
        DiscoveryQuery(
            category="shop", location=LocationSpec(center=(12.9, 77.5), radius_km=1), max_results=9
        )
    )
    assert capped_adapter.last_capped is False


@pytest.mark.asyncio
async def test_overpass_cannot_be_searched_by_place_name_alone() -> None:
    """Place names need geocoding first. Pretending otherwise would silently
    return a different city's businesses."""
    adapter = OverpassAdapter(client=client_for(lambda request: httpx.Response(200, json={})))
    with pytest.raises(UnsupportedQueryError, match="geocode"):
        await adapter.discover(
            DiscoveryQuery(category="cafe", location=LocationSpec(place_name="Indiranagar"))
        )


@pytest.mark.asyncio
async def test_overpass_throttle_is_reported_as_rate_limited() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, text="<html>too many requests</html>")

    adapter = OverpassAdapter("https://overpass.test", client=client_for(handler))
    with pytest.raises(RateLimitedError):
        await adapter.discover(
            DiscoveryQuery(category="cafe", location=LocationSpec(center=(12.9, 77.5), radius_km=1))
        )


@pytest.mark.asyncio
async def test_overpass_html_error_body_is_malformed_not_silently_empty() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>query timed out</html>")

    adapter = OverpassAdapter("https://overpass.test", client=client_for(handler))
    with pytest.raises(MalformedResponseError):
        await adapter.discover(
            DiscoveryQuery(category="cafe", location=LocationSpec(center=(12.9, 77.5), radius_km=1))
        )


@pytest.mark.asyncio
async def test_capabilities_state_their_own_limits() -> None:
    """The Source Manager shows these strings; they must be honest about what a
    source cannot do, not marketing copy."""
    coverage = OverpassAdapter().capabilities.geographic_coverage
    assert "Volunteer" in coverage
    assert "patchy" in coverage.lower()

    search_coverage = SearxngAdapter("http://x").capabilities.geographic_coverage
    assert "not exhaustive" in search_coverage.lower()


@pytest.mark.asyncio
async def test_health_check_failure_never_raises() -> None:
    """A probe that throws would take down the Source Manager page."""

    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    adapter = SearxngAdapter("http://searxng.local", client=client_for(handler))
    health = await adapter.health_check()
    assert health.status == "failed"
    assert health.detail == "ConnectError"

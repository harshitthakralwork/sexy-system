from __future__ import annotations

import re
import time
from typing import Any

import httpx

from app.modules.discovery.adapters.base import (
    HEALTH_DEGRADED,
    HEALTH_FAILED,
    HEALTH_WORKING,
    AccessDeniedError,
    AdapterCapabilities,
    DiscoveredItem,
    DiscoveryQuery,
    HealthResult,
    MalformedResponseError,
    RateLimitedError,
    UnsupportedQueryError,
)
from app.shared.url_safety import validate_service_base_url

# Configuration is the service *origin*; the path belongs to the adapter. A
# configured value with a path could quietly point at a different resource than
# the one this code was written and reviewed for.
DEFAULT_BASE_URL = "https://overpass-api.de"
INTERPRETER_PATH = "/api/interpreter"

# OSM shop/amenity/craft values that represent a real business premises.
BUSINESS_KEYS = ("shop", "amenity", "craft", "office", "tourism")

# Overpass QL has no parameter binding, so the category is the one place in this
# adapter where untrusted text reaches a query language. Overpass tags are plain
# ASCII-ish keys; anything outside this class is rejected rather than escaped,
# because an escaping bug in a hand-rolled quote would be a query-injection
# primitive that lets a caller run arbitrary (and arbitrarily expensive) queries
# against a shared public instance.
_CATEGORY_PATTERN = re.compile(r"^[A-Za-z0-9:_-]{1,40}$")

MAX_RADIUS_KM = 50.0
MAX_ELEMENTS_PER_QUERY = 1000


def _validate_category(category: str) -> str:
    candidate = category.strip()
    if not _CATEGORY_PATTERN.match(candidate):
        raise UnsupportedQueryError(
            "Category must be an OSM tag value (letters, digits, colon, underscore, "
            f"hyphen; up to 40 characters). Received {len(candidate)} characters of "
            "unusable input."
        )
    return candidate


def _validate_coordinate(lat: float, lon: float) -> None:
    if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
        raise UnsupportedQueryError(f"Coordinates {lat},{lon} are outside valid ranges")


def _build_around_clause(query: DiscoveryQuery) -> str:
    location = query.location
    if location is None:
        raise UnsupportedQueryError("Overpass needs a geographic scope for area queries")
    if location.center is not None and location.radius_km is not None:
        lat, lon = location.center
        _validate_coordinate(lat, lon)
        radius_km = float(location.radius_km)
        if not (0 < radius_km <= MAX_RADIUS_KM):
            raise UnsupportedQueryError(
                f"radius_km must be between 0 and {MAX_RADIUS_KM}. A city-wide sweep in a "
                "single query is how shared Overpass instances get DoS'd; narrow the area "
                "or split it into tiles."
            )
        return f"around:{int(radius_km * 1000)},{lat},{lon}"
    if location.query_bbox is not None:
        west, south, east, north = location.query_bbox
        _validate_coordinate(south, west)
        _validate_coordinate(north, east)
        if max(east - west, north - south) * 111.0 > MAX_RADIUS_KM:
            raise UnsupportedQueryError(
                f"Bounding box spans more than {MAX_RADIUS_KM} km; tile it instead."
            )
        return f"(around:25000,{(south + north) / 2},{(west + east) / 2})"
    raise UnsupportedQueryError(
        "Overpass cannot search by place name alone — geocode it first, then query by "
        "centre and radius or a bounding box."
    )


class OverpassAdapter:
    """Geographic discovery from OpenStreetMap via the Overpass API.

    Coverage is honest and stated up front: OSM holds what volunteers mapped.
    For local businesses in India that is a real subset, so this source
    supplements SearXNG rather than carrying discovery on its own.
    """

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        *,
        timeout_seconds: float = 30.0,
        user_agent: str = "SparkXFlow-Nexus/0.1 (single-operator research tool)",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        origin = validate_service_base_url(base_url, field="Overpass base_url")
        self._endpoint = f"{origin}{INTERPRETER_PATH}"
        self._timeout = timeout_seconds
        self._user_agent = user_agent
        self._client = client
        self._owns_client = client is None
        self.requests_made = 0

    @property
    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            adapter_key="overpass",
            name="OpenStreetMap (Overpass API)",
            slug="overpass",
            category="geographic",
            supported_query_types=("category", "radius", "bbox"),
            supported_filters=("category", "radius_km", "bbox", "name_present"),
            available_fields=("name", "category", "address tags", "latitude", "longitude"),
            geographic_coverage=(
                "Volunteer-mapped data. Coverage for local businesses in India is "
                "patchy; absence of an unmapped shop is an OSM gap, not evidence the "
                "shop does not exist."
            ),
            access_requirements=("Public internet access to an Overpass endpoint",),
            rate_limit_notes=(
                "Overpass throttles by IP and rejects concurrent heavy queries. Keep one "
                "request in flight and back off on 429/504 rather than retrying tightly."
            ),
            terms_notes=(
                "OSM data is OpenDatabase-licensed and attribution is required; the "
                "public Overpass instances ask for considerate use, which is why this "
                "adapter caps radius and page size."
            ),
            max_results_per_query=1000,
        )

    async def validate_config(self, config: dict[str, Any]) -> None:
        origin = str(config.get("base_url", DEFAULT_BASE_URL)).strip()
        validate_service_base_url(origin, field="Overpass base_url")

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is not None:
            return self._client
        # Redirects stay off. Following a redirect would let the endpoint hand us
        # a different host than the one the configuration was approved for.
        self._client = httpx.AsyncClient(timeout=self._timeout, follow_redirects=False)
        return self._client

    async def aclose(self) -> None:
        if self._client is not None and self._owns_client:
            await self._client.aclose()

    def build_query(self, query: DiscoveryQuery) -> str:
        scope = _build_around_clause(query)
        category = (query.category or "").strip()
        # Whitelisted, never escaped: the category is the only untrusted string
        # that reaches the query language.
        tags = (
            f'["{_validate_category(category)}"]'
            if category
            else "".join(f'["{key}"]' for key in BUSINESS_KEYS)
        )
        limit = min(max(int(query.max_results), 1), MAX_ELEMENTS_PER_QUERY)
        return f"[out:json][timeout:25];(node{tags}{scope});out body {limit};"

    async def discover(self, query: DiscoveryQuery) -> list[DiscoveredItem]:
        client = await self._get_client()
        response = await client.post(
            self._endpoint,
            data={"data": self.build_query(query)},
            headers={"User-Agent": self._user_agent},
        )
        self.requests_made += 1
        self._raise_for_response(response)

        try:
            payload = response.json()
        except ValueError as exc:
            raise MalformedResponseError(
                "Overpass replied with a non-JSON body. Overpass returns HTML/XML "
                "when it rejects a query for rate limiting or timeout."
            ) from exc

        elements = payload.get("elements") if isinstance(payload, dict) else None
        if elements is None:
            raise MalformedResponseError("Overpass response had no elements field")

        return [item for item in (self._to_item(element) for element in elements) if item]

    def _raise_for_response(self, response: httpx.Response) -> None:
        if response.status_code in (200, 204):
            return
        if response.status_code in (429, 504) or response.status_code >= 500:
            raise RateLimitedError(
                f"Overpass is overloaded or throttling this client ({response.status_code}). "
                "Retry later with fewer concurrent queries."
            )
        if response.status_code in (401, 403):
            raise AccessDeniedError(f"Overpass refused the request ({response.status_code})")
        raise UnsupportedQueryError(f"Overpass returned HTTP {response.status_code}")

    def _to_item(self, element: Any) -> DiscoveredItem | None:
        if not isinstance(element, dict):
            return None
        tags = element.get("tags") or {}
        if not isinstance(tags, dict):
            return None
        name = tags.get("name")
        category = next((tags[key] for key in BUSINESS_KEYS if key in tags), None)
        if not name and not category:
            # An element with neither is not a business record; passing it on
            # would create noise the pipeline then has to guess about.
            return None

        osm_type = element.get("type", "node")
        osm_id = element.get("id")
        reference = f"{osm_type}/{osm_id}" if osm_id is not None else None
        address = " ".join(
            part
            for part in (
                tags.get("addr:housenumber"),
                tags.get("addr:street"),
                tags.get("addr:city"),
                tags.get("addr:postcode"),
            )
            if part
        )

        return DiscoveredItem(
            external_id=reference,
            source_url=(
                f"https://www.openstreetmap.org/{osm_type}/{osm_id}" if reference else None
            ),
            title_hint=name,
            latitude=element.get("lat"),
            longitude=element.get("lon"),
            raw_data={
                "osm_reference": reference,
                "tags": tags,
                "name": name,
                "category": category,
                "address": address or None,
                "phone": tags.get("phone") or tags.get("contact:phone"),
                "website": tags.get("website") or tags.get("contact:website"),
                "email": tags.get("email") or tags.get("contact:email"),
                "opening_hours": tags.get("opening_hours"),
                "osm_version": element.get("version"),
            },
        )

    async def health_check(self) -> HealthResult:
        """A one-element query proves reachability without loading a whole city."""
        started = time.perf_counter()
        probe = "[out:json][timeout:10];node[shop](around:500,12.9716,77.5946);out 1;"
        try:
            client = await self._get_client()
            response = await client.post(
                self._endpoint, data={"data": probe}, headers={"User-Agent": self._user_agent}
            )
            elapsed = int((time.perf_counter() - started) * 1000)
            self._raise_for_response(response)
            payload = response.json()
            if not isinstance(payload, dict) or "elements" not in payload:
                return HealthResult(
                    status=HEALTH_DEGRADED,
                    detail="Responding without an elements array",
                    response_time_ms=elapsed,
                )
            return HealthResult(status=HEALTH_WORKING, response_time_ms=elapsed)
        except AccessDeniedError as exc:
            return HealthResult(status=HEALTH_FAILED, detail=exc.message)
        except httpx.HTTPError as exc:
            return HealthResult(status=HEALTH_FAILED, detail=type(exc).__name__)
        except Exception as exc:  # noqa: BLE001 - a health probe reports, never raises
            return HealthResult(status=HEALTH_FAILED, detail=type(exc).__name__)
